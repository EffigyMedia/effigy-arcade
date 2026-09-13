#!/usr/bin/env python3
"""TUNNEL WALL TEST - the car and the camera stay inside a bore's wall.

    .venv/Scripts/python tools/tunnel-wall-test.py
    .venv/Scripts/python tools/tunnel-wall-test.py --falsify near
    .venv/Scripts/python tools/tunnel-wall-test.py --falsify edge

RLG-237. Owner, 2026-09-13, from the device: "The tunnel walls can be clipped through by the
camera." The owner chose a SOLID wall: the car scrapes to a stop against it, as at the road edge.

THE CAMERA NEVER LEFT THE BORE. The first diagnosis said it did, and the first version of this file
could not make the camera fail. What the owner photographed was a tube drawn from the CAR rather
than the camera, so the road between the two had no wall and the world outside showed past a hard
edge. The car's side also passed through the wall. So there are two faults and two checks.

WHAT IS MEASURED IS THE PICTURE. `API.boreClearance` reads the nearest section the last frame drew,
and the wall at the car off `borePointAt`, the function the walls are painted from, in pixels.

  1. THE CAR IS HELD HARD OVER inside the bore, on both sides. Without this every check below is
     true of a car that drove down the middle.
  2. NO OPEN WORLD SHOWS PAST THE WALL near the camera: on the side the car is held against, the
     wall at the nearest drawn section runs off the glass.
  3. THE CAR'S SIDES NEVER PASS THROUGH THE WALL.
  4. THE OPEN ROAD IS UNCHANGED. Before the bore, the same steering reaches past 1.12, which is
     where the old edge pin holds a car.

`--falsify near` serves the tube starting at the car again: only check 2 must fail, on both sides.
`--falsify edge` serves the bore limit removed: only check 3 must fail, on both sides.

Exit code 0 if every check passed, 1 otherwise.
"""
import argparse
import functools
import http.server
import importlib.util
import socketserver
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from harness import console_utf8, launch_chromium, boot   # noqa: E402
from playwright.sync_api import sync_playwright            # noqa: E402

GAME = 'games/sw/interstate.html'
FALSIFY = {
    'edge': ('  if(!inBore()) return 1.18;', '  return 1.18;'),
    'near': ('  const own = pos + BORE.near;', '  const own = pos + PLAYER_Z + 40;'),
}
SIDE_SAMPLES = 40


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--falsify', choices=sorted(FALSIFY),
                    help='serve one half of the fault back; see the docstring')
    args = ap.parse_args()
    console_utf8()

    spec = importlib.util.spec_from_file_location('dt', ROOT / 'tools' / 'drive-test.py')
    dt = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dt)

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
    srv = socketserver.TCPServer(('127.0.0.1', 0), handler)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    bad = 0

    def ok(cond, label, detail=''):
        nonlocal bad
        if not cond:
            bad += 1
        print('  %s  %s%s' % ('ok  ' if cond else 'FAIL', label,
                              ('   ' + detail) if detail else ''))

    print('tunnel-wall-test  .  the car and the camera stay inside the bore')
    if args.falsify:
        print('  FALSIFY %s: one half of the fault is served back.' % args.falsify)
    try:
        with sync_playwright() as p:
            b = launch_chromium(p, headless=True, args=['--mute-audio'])
            ctx = b.new_context(viewport={'width': 480, 'height': 900})
            ctx.add_init_script(dt.INIT)
            if args.falsify:
                need, put = FALSIFY[args.falsify]
                src = (ROOT / 'road.js').read_text(encoding='utf-8')
                if need not in src:
                    raise SystemExit('[tunnel-wall] --falsify cannot find %r' % need)
                src = src.replace(need, put, 1)

                def serve(route):
                    route.fulfill(status=200, content_type='application/javascript', body=src)
                ctx.route('**/road.js', serve)
            pg = ctx.new_page()
            errs = []
            pg.on('pageerror', lambda e: errs.append(str(e)))
            boot(pg, 'http://127.0.0.1:%d/%s' % (port, GAME))
            pg.wait_for_timeout(1600)
            pg.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
            pg.click('[data-act="play"]')
            pg.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
            pg.click('[data-act="drive"]')
            pg.wait_for_timeout(1600)

            # A PARKED OR SLOW CAR RUNS THE CLOCK OUT and every number freezes (thread
            # constraint, RLG-125), so the run clock is switched off for the whole test.
            pg.evaluate("""() => { const R = window.__probe.road; R.setTimed(false);
              R.setBiomePair('FARMLAND','FARMLAND'); R.setPhase(0.75); }""")
            pg.wait_for_timeout(300)

            HOLD = """(side) => { const R = window.__probe.road;
              R.setSpd(R.MAX_SPD * 0.45); R.steerOver(side * 1.18, 0.05);
              return R.boreClearance(); }"""

            # 4. the open road first, with the same steering
            open_x = 0.0
            for _ in range(40):
                c = pg.evaluate(HOLD, 1)
                pg.wait_for_timeout(60)
                if not c['inBore']:
                    open_x = max(open_x, c['playerX'])
            pg.evaluate("() => window.__probe.road.startBiomeChange('TUNNEL')")

            samples = {1: [], -1: []}
            side, polls = 1, 0
            while polls < 900 and len(samples[-1]) < SIDE_SAMPLES:
                c = pg.evaluate(HOLD, side)
                polls += 1
                pg.wait_for_timeout(60)
                if c['inBore']:
                    samples[side].append(c)
                    if side == 1 and len(samples[1]) >= SIDE_SAMPLES:
                        side = -1
                elif samples[1]:
                    break   # driven out of the far end before both sides were measured

            ok(open_x > 1.12, 'on the open road the car still reaches the old edge',
               'furthest out %.3f' % open_x)
            for s, name in ((1, 'right'), (-1, 'left')):
                got = samples[s]
                if len(got) < 10:
                    ok(False, 'BLKD  %-5s too few samples inside the bore' % name,
                       '%d samples in %d polls' % (len(got), polls))
                    continue
                # the last half of the samples, once the steering has carried the car over
                tail = got[len(got) // 2:]
                reach = max(abs(t['playerX']) for t in tail)
                ok(reach > 1.0, '%-5s the car is held hard over inside the bore' % name,
                   'furthest out %.3f, %d samples' % (reach, len(got)))
                # the wall on the side the car is held against, at the nearest section drawn:
                # it must run off the glass, or the outside world shows past its edge. Only
                # frames with the CAMERA past the mouth count: before that the tube rightly
                # begins at the mouth, ahead of the eye.
                drawn = [t for t in got if t['nearXr'] is not None and t['camInside']]
                if len(drawn) < 10:
                    ok(False, 'BLKD  %-5s too few frames with the camera inside' % name,
                       '%d frames' % len(drawn))
                    drawn = []
                if s == 1:
                    worst = min(t['nearXr'] - t['W'] for t in drawn) if drawn else None
                else:
                    worst = min(-t['nearXl'] for t in drawn) if drawn else None
                ok(worst is not None and worst >= 0,
                   '%-5s no open world shows past the wall near the camera' % name,
                   'the wall edge sits %s px inside the glass at worst, nearest section %s units out'
                   % (None if worst is None else -worst,
                      max(t['nearDz'] for t in drawn) if drawn else None))
                car = min(t['carGap'] for t in got if t['carGap'] is not None)
                ok(car >= 0, '%-5s the car never passes through the wall' % name,
                   'closest to the wall %.1f px' % car)

            if errs:
                ok(False, 'page errors', errs[0][:140])
            b.close()
    finally:
        srv.shutdown()

    print('  %s' % ('all checks passed' if not bad else '%d check(s) FAILED' % bad))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
