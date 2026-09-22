#!/usr/bin/env python3
"""RANGE PEAK TEST - the valley range is peaks standing in the world, in both views.

    .venv/Scripts/python tools/range-peak-test.py
    .venv/Scripts/python tools/range-peak-test.py --falsify

RLG-309 and RLG-316. Owner, 2026-09-21: the valley range "parallax[es] weird", and "as the road
twists and turns they do unnatural things like clipping through the near side mountain. And the
mountain bugs out and renders through the road depending on the road angle and height."

The range was one picture slid across the screen by three offsets and painted once, at one depth,
inside a rectangle. It is now a row of peaks, each a world object drawn by the road walk at its
own slice. The mountain is driven round a held bend and then STOPPED, so every frame read is the
same frame and a peak's position can be recomputed from outside the painter:

  1. THE PEAKS COME FROM MANY DEPTHS, out of the windscreen and out of the glass. One depth is
     the old model.
  2. EVERY WINDSCREEN PEAK IS WHERE THE WORLD PUTS IT. Its drawn near edge is compared with
     `API.projAt` of the world point `RANGE_OUT` road widths out at the peak's own segment - the
     engine's projection asked directly, not the painter. Any screen-space term breaks it.
  3. AND THE RANGE RISES ABOVE THE EYE: some peak's top is above the horizon. A range across a
     valley that never breaks the horizon is a row of hills in the valley floor, and the
     reviewer of UNT-417 showed the first defaults put every top exactly on the eye line.

NOT MEASURED: the glass's placement, because its projection is not exposed (check 1 still asks
that it draws peaks); pixel occlusion on a crest, which follows from the draw order; and how it
looks, which is the owner's call on a device. The previous check 2 compared the painter's
offset with itself, and the review above found it could not fail except by editing that line.

Run with `--falsify` to add a fixed screen-space shift to where each peak is drawn - a lane-like
term. Check 2 must fail; 1 and 3 must pass.

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



def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--falsify', action='store_true', help='add a screen-space drift to the peaks')
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

    print('range-peak-test  .  the valley range is peaks standing in the world')
    if args.falsify:
        print('  FALSIFY: every peak is drawn 12 px off. 2 must fail; 1 and 3 must not.')
    try:
        with sync_playwright() as p:
            b = launch_chromium(p, headless=True, args=['--mute-audio'])
            ctx = b.new_context(viewport={'width': 480, 'height': 900})
            ctx.add_init_script(dt.INIT)
            if args.falsify:
                src = (ROOT / 'road.js').read_text(encoding='utf-8')
                need = '  const xl = side > 0 ? near : near - pw;'
                if src.count(need) != 1:
                    raise SystemExit('[range-peak-test] --falsify cannot find its line')
                src = src.replace(need, '  const xl = (side > 0 ? near : near - pw) + 12;', 1)
                ctx.route('**/road.js', lambda route: route.fulfill(
                    status=200, content_type='application/javascript', body=src))
            pg = ctx.new_page()
            errs = []
            pg.on('pageerror', lambda e: errs.append(str(e)))
            boot(pg, 'http://127.0.0.1:%d/games/sw/interstate.html' % port)
            pg.wait_for_timeout(1000)
            pg.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
            pg.click('[data-act="play"]')
            pg.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
            pg.click('[data-act="drive"]')
            pg.wait_for_timeout(1500)
            need = ('rangeTrace', 'rangeModel', 'watchDraw', 'setBiomePair', 'holdCurve', 'projAt', 'horizon')
            if not pg.evaluate("(ns) => ns.every(n => typeof window.__probe.road[n] === 'function')",
                               list(need)):
                ok(False, 'the engine answers the range seam', ', '.join(need))
                b.close()
                print('  1 check(s) FAILED')
                return 1
            model = pg.evaluate("() => window.__probe.road.rangeModel()")
            print('      the model: %s' % model)
            # the drop is put on a stated side, because the range stands on it; the road
            # is driven round a bend, then the car is stopped so every frame read is the
            # same frame and the peaks can be recomputed from outside the painter
            pg.evaluate("""() => { const R = window.__probe.road;
                R.setTimed(false); R.setPhase(0.5); R.setWet(0); R.setSnow(0); R.clearTraffic();
                R.setBiomePair('MOUNTAIN', 'MOUNTAIN'); R.setHazardSide(1); R.holdCurve(-0.4);
                R.watchDraw(true); }""")
            # THE TERRAIN IS RANDOM, so whether a peak is in view when the car stops is too:
            # an early run stopped with every peak behind a rise. So it drives on and stops
            # again, up to four times, until the windscreen has peaks from three segments.
            for attempt in range(4):
                pg.evaluate("() => { const R = window.__probe.road; R.holdSpd(R.MAX_SPD * 0.4); }")
                pg.wait_for_timeout(2500)
                pg.evaluate("() => { const R = window.__probe.road; R.holdSpd(0); R.clearTraffic(); }")
                pg.wait_for_timeout(1500)
                pg.evaluate("() => window.__probe.road.rangeTrace(true)")
                pg.wait_for_timeout(600)
                t = pg.evaluate("() => window.__probe.road.rangeTrace(false)")
                front = [e for e in t if e['view'] == 'front']
                glass = [e for e in t if e['view'] == 'glass']
                if len(set(e['idx'] for e in front)) >= 3:
                    break
            print('      measured on stop %d' % (attempt + 1))
            want = pg.evaluate("""(a) => { const R = window.__probe.road;
                return a.es.map(e => R.projAt(e.side * a.outZ, e.idx * 200).x); }""",
                               {'es': front, 'outZ': model['outZ']})
            errs_px = [abs(e['x'] - w) for e, w in zip(front, want)]
            worst = max(errs_px) if errs_px else None
            hz = pg.evaluate("() => window.__probe.road.horizon()")
            top = min((e['top'] for e in front), default=None)
            print('      windscreen %4d peak draw(s) from %2d segment(s); worst placement error %s px'
                  % (len(front), len(set(e['idx'] for e in front)),
                     'n/a' if worst is None else '%.2f' % worst))
            print('      glass      %4d peak draw(s) from %2d segment(s)'
                  % (len(glass), len(set(e['idx'] for e in glass))))
            print('      the highest windscreen peak top %s against the horizon at %s' % (top, hz))
            ok(len(set(e['idx'] for e in front)) >= 3,
               '1. the windscreen draws the range from many depths')
            ok(len(set(e['idx'] for e in glass)) >= 2, '1. and so does the glass')
            ok(worst is not None and worst <= 1.0,
               '2. every windscreen peak stands where the projection puts its world point',
               'worst %s px' % (None if worst is None else round(worst, 2)))
            ok(top is not None and top < hz - 2, '3. and the range rises above the eye',
               'highest top %s, horizon %s' % (top, hz))
            if errs:
                ok(False, 'page errors', errs[0][:140])
            b.close()
    finally:
        srv.shutdown()

    print()
    print('  %s' % ('all checks passed' if not bad else '%d check(s) FAILED' % bad))
    print('  whether it reads as a range across a valley is the owner call on a device.')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
