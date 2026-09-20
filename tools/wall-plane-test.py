#!/usr/bin/env python3
"""WALL PLANE TEST - a canyon wall is a plane far ABOVE the road, and it is in both views.

    .venv/Scripts/python tools/wall-plane-test.py
    .venv/Scripts/python tools/wall-plane-test.py --falsify

RLG-297, owner 2026-09-20, from the device: "The canyon walls might look better if they are built
like the cliff face of the mountain biome, but going up off screen instead. Maybe the same for the
upwards wall of mountain."

THE DROP'S OWN CHECK IS THE MODEL FOR THIS ONE, AND SO ARE ITS MISTAKES (RLG-278). Sampling a
strip of verge at a fixed row measures the SCENERY, not the surface behind it - the FARMLAND
control, which has no wall at all, swings nineteen brightness levels between its own two sides.
So the wall is found the way the drop and the rail are: render it away through `API.wallOff`, diff
the two frames, and whatever changed IS the wall.

  1. A CANYON IS WALLED ON BOTH SIDES AND A FARMLAND ON NEITHER. The diff has to be large on both
     halves of the canyon's frame and near zero on farmland's, which is the control that stops
     every later question passing on a build where the diff measures the weather.

  2. A MOUNTAIN IS WALLED ON ONE SIDE - THE SIDE THE DROP IS NOT ON. Rendered with the hazard
     left and again with it right, the wall's own mean position must move to the other half of
     the screen, and it must sit opposite the drop. An absolute position cannot settle this on
     its own, which is the rail's lesson: a surface converging on the vanishing point crosses the
     middle of the screen whichever side it is on. The DIFFERENCE between the two answers can.

  3. AND IT IS A PLANE ABOVE THE ROAD, NOT A BAND STANDING ON THE HORIZON. This is the question
     the picture is actually about, and it is the drop's own question turned over: at the far end
     of the draw the wall's top edge comes DOWN to the horizon, and near the car it has left the
     top of the frame. So the trace's top edge must fall as the slice number rises, and the
     nearest slices must be at zero - off the screen. A skyline band does neither: it stands at
     one height at every distance, because it is drawn once at the horizon.

  4. AND IT IS BEHIND YOU TOO. The drop had to be put in the mirror twice - once for the rail
     standing on open ground, and again when the owner reported a mountain's glass still showing
     "rocks on both sides". The glass is a second road pass with its own walk and its own scale,
     so anything beside the road has to be drawn twice or it does not exist behind you.

Run with `--falsify` to serve the engine with CANYON and MOUNTAIN struck out of the walled places.
Every question about the wall must fail and every CONTROL must stay green - the noise floor and the
farmland line say what this instrument can and cannot see, and a falsify arm that took them down
with it would prove only that the harness had stopped working.

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

# the sum of the three channel deltas that counts as a different surface rather than the same one
# dithered. `hazard-test`'s number, so the two harnesses report in one unit.
CHAN = 24
# below this many changed pixels a side is not walled. Every pixel here is one of four, so a
# walled side measures thousands and the farmland control measures single figures.
BARE = 300
# the windscreen is 480x900 and the mirror sits in the top fifth of it, so the wall diff is read
# from the road's own half of the frame and the glass is read separately
ROAD_TOP = 0.42

def pixels(a, b, y0f, y1f):
    """where the pixels that changed between two frames sit, and how many there are.

    THE FRAMES ARE SCREENSHOTS AND NOT `getImageData` ON THE CANVAS, and that is not a
    convenience. The road pass paints progressively, so a canvas read taken at an arbitrary
    moment catches a half-drawn frame: measured here at 94,116 changed pixels between two
    renders with NOTHING altered between them, on a place that has no wall at all. A
    screenshot waits for a settled frame, which is why `hazard-test` gets 0 to 7 on the same
    control. The sampling and the threshold are that harness's, so the two report in one unit.
    """
    import io
    from PIL import Image
    ia = Image.open(io.BytesIO(a)).convert('RGB')
    ib = Image.open(io.BytesIO(b)).convert('RGB')
    w, h = ia.size
    pa, pb = ia.load(), ib.load()
    n = sx = left = right = 0
    for y in range(int(h * y0f), int(h * y1f), 2):
        for x in range(0, w, 2):
            ca, cb = pa[x, y], pb[x, y]
            if abs(ca[0] - cb[0]) + abs(ca[1] - cb[1]) + abs(ca[2] - cb[2]) <= CHAN:
                continue
            n += 1
            sx += x
            if x < w / 2:
                left += 1
            else:
                right += 1
    return {'n': n, 'x': (sx / n) if n else 0, 'left': left, 'right': right}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--falsify', action='store_true',
                    help='serve the engine with no place walled; every check must fail')
    args = ap.parse_args()
    console_utf8()

    dt_path = ROOT / 'tools' / 'drive-test.py'
    spec = importlib.util.spec_from_file_location('dt', dt_path)
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

    print('wall-plane-test  .  a wall is a plane above the road, in both views')
    if args.falsify:
        print('  FALSIFY: no place is walled. Every check must fail.')
    try:
        with sync_playwright() as p:
            b = launch_chromium(p, headless=True, args=['--mute-audio'])
            ctx = b.new_context(viewport={'width': 480, 'height': 900})
            ctx.add_init_script(dt.INIT)
            if args.falsify:
                # the flag struck out of the ENGINE's own recipes rather than out of this file's
                # idea of them, so the check meets the picture it would have met before the work
                src = (ROOT / 'road.js').read_text(encoding='utf-8')
                need = '              wall:1,\n'
                if src.count(need) != 2:
                    raise SystemExit('[wall-plane-test] --falsify expects two walled places, '
                                     'found %d' % src.count(need))
                src = src.replace(need, '')
                ctx.route('**/road.js', lambda route: route.fulfill(
                    status=200, content_type='application/javascript', body=src))
            pg = ctx.new_page()
            errs = []
            pg.on('pageerror', lambda e: errs.append(str(e)))
            boot(pg, 'http://127.0.0.1:%d/games/sw/interstate.html' % port)
            pg.wait_for_timeout(1200)
            pg.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
            pg.click('[data-act="play"]')
            pg.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
            pg.click('[data-act="drive"]')
            pg.wait_for_timeout(1500)

            need = ('wallOff', 'wallTrace', 'wallSidesOf', 'setBiomePair', 'setHazardSide')
            have = pg.evaluate("(ns) => ns.every(n => typeof window.__probe.road[n] === 'function')",
                               list(need))
            if not have:
                ok(False, 'the engine answers the wall seam', ', '.join(need))
                b.close()
                print('  1 check(s) FAILED')
                return 1

            def settle(k, side):
                """pin the place, the light, the curve and the car, with the hazard on `side`"""
                pg.evaluate("([k, s]) => { const R = window.__probe.road;"
                            " R.setTimed(false); R.holdCurve(0); R.holdSpd(null);"
                            " R.setBiomePair(k, k); R.setPhase(0.5);"
                            " R.setWet(0); R.setSnow(0); R.setPool(0); R.clearTraffic();"
                            " R.setHazardSide(s); R.setSeaSide(s);"
                            " R.setSpd(R.MAX_SPD * 0.35); }", [k, side])
                for _ in range(14):
                    pg.evaluate("() => { const R = window.__probe.road;"
                                " R.clearTraffic(); R.setSpd(R.MAX_SPD * 0.35); }")
                    pg.wait_for_timeout(40)
                # ---- FORTY, NOT TWELVE, AND THE NUMBER IS MEASURED -------------
                # A CANYON TAKES LONGER TO GO STILL THAN ANYWHERE ELSE ON THE BOARD.
                # `hazard-test` settles in twelve of these and its farmland control
                # reports single figures; at twelve holds a canyon still moved 7,349
                # pixels between two renders with NOTHING changed - 2,849 of them in
                # the mirror's band and 4,500 on the road - which is the same size as
                # the wall this harness is trying to measure. At forty it is ZERO, and
                # at eighty it is still zero. The place has the tallest skyline band on
                # the board and the densest roadside, and both are chased frame to
                # frame rather than set; it is the CHASE that has to finish.
                for _ in range(40):
                    pg.evaluate("() => { const R = window.__probe.road;"
                                " R.clearTraffic(); R.holdSpd(0); R.setPhase(0.5); }")
                    pg.wait_for_timeout(40)

            def wall_diff(k, side, top, bottom, still=False):
                """the same place rendered with the wall and without it, from one standstill.

                `still` renders it twice the SAME way, which is the noise floor: whatever that
                reports is what this instrument cannot tell apart, and every other number here
                has to stand above it."""
                settle(k, side)
                pg.evaluate("() => window.__probe.road.wallOff(true)")
                pg.wait_for_timeout(120)
                off = pg.screenshot()
                pg.evaluate("(v) => window.__probe.road.wallOff(v)", bool(still))
                pg.wait_for_timeout(120)
                on = pg.screenshot()
                return pixels(on, off, top, bottom)

            # ---- 1. walled on both sides, and a control with no wall at all ------------------
            print()
            print('  WHAT IS WALLED AND WHAT IS NOT')
            still = wall_diff('CANYON', -1, ROAD_TOP, 1.0, still=True)
            can = wall_diff('CANYON', -1, ROAD_TOP, 1.0)
            far = wall_diff('FARMLAND', -1, ROAD_TOP, 1.0)
            print('      two straight renders %6d px' % still['n'])
            print('      CANYON    %6d px   left %6d  right %6d' % (can['n'], can['left'], can['right']))
            print('      FARMLAND  %6d px   left %6d  right %6d' % (far['n'], far['left'], far['right']))
            ok(still['n'] < BARE, 'two straight renders do not differ, so the diff IS the wall',
               '%d pixel(s)' % still['n'])
            ok(can['left'] > BARE and can['right'] > BARE,
               'a canyon is walled on BOTH sides',
               'left %d, right %d pixel(s)' % (can['left'], can['right']))
            ok(far['n'] < BARE, 'and a farmland is walled on neither',
               '%d pixel(s) changed' % far['n'])

            # ---- 2. a mountain is walled opposite its drop -----------------------------------
            print()
            print('  AND A MOUNTAIN IS WALLED OPPOSITE ITS DROP')
            mL = wall_diff('MOUNTAIN', -1, ROAD_TOP, 1.0)
            mR = wall_diff('MOUNTAIN', 1, ROAD_TOP, 1.0)
            print('      hazard left   wall %6d px at x=%5.1f' % (mL['n'], mL['x']))
            print('      hazard right  wall %6d px at x=%5.1f' % (mR['n'], mR['x']))
            ok(mL['n'] > BARE and mR['n'] > BARE, 'a mountain paints a wall either way round',
               '%d and %d pixel(s)' % (mL['n'], mR['n']))
            # the hazard LEFT puts the drop left, so the wall is RIGHT: the mean must move the
            # other way from the drop's, which cliff-test measures at 85 left and 403 right
            ok(mL['x'] - mR['x'] > 60,
               'and the wall stands opposite the drop, whichever side that is',
               'x=%.1f with the hazard left, x=%.1f with it right' % (mL['x'], mR['x']))

            # ---- 3. it is a plane ABOVE the road, not a band on the horizon -------------------
            print()
            print('  AND IT IS A PLANE ABOVE THE ROAD')
            settle('CANYON', -1)
            tr = pg.evaluate("() => window.__probe.road.wallTrace()")
            rows = {}
            for n, side, top in tr:
                rows.setdefault(int(n), []).append(float(top))
            # THE BANDS ARE THE TRACE'S OWN ENDS, NOT TWO TYPED SLICE NUMBERS. How far the
            # walk reaches is terrain: a crest hides slices and the count swings from 53 to 150
            # on one unchanged build, which is the recorded reason never to quote a single
            # occlusion run. A fixed `n >= 120` therefore fails on a hilly road with the wall
            # working perfectly, which it did on the first run of this check.
            ns = sorted(rows)
            if not ns:
                # A HARNESS REPORTS, IT DOES NOT CRASH. With the wall struck out the trace is
                # empty and every index below is out of range, so the falsify arm died here
                # instead of printing the two failures it had already found.
                ok(False, 'the wall pass ran over the length of the draw', 'nothing traced')
                ok(False, 'beside the car the wall has left the top of the frame', 'nothing traced')
                ok(False, 'and at the far end of the draw it has come down toward the horizon',
                   'nothing traced')
                ns = None
            cut = max(1, len(ns) // 5) if ns else 0
            # the NEAREST HANDFUL for the near end, not a fifth of the draw: the top edge
            # climbs off the frame within a few slices of the car and a fifth of 147 slices
            # reaches out to n=33, where it is legitimately back on screen at 49 pixels
            near = [min(rows[k]) for k in ns[:6]] if ns else []
            deep = [min(rows[k]) for k in ns[-cut:]] if ns else []
            if ns:
                print('      %d slice(s) traced, n %d to %d   nearest six: top %.1f   '
                      'furthest fifth: top %.1f'
                      % (len(rows), ns[0], ns[-1], sum(near)/len(near), sum(deep)/len(deep)))
                ok(len(rows) > 40, 'the wall pass ran over the length of the draw',
                   '%d slice(s), n %d to %d' % (len(rows), ns[0], ns[-1]))
                ok(max(near) <= 0.5,
                   'beside the car the wall has left the top of the frame',
                   'top edge at %.1f' % max(near))
                ok(min(deep) > 0.5 and sum(deep)/len(deep) > sum(near)/len(near) + 40,
                   'and at the far end of the draw it has come down toward the horizon',
                   'top edge %.1f far against %.1f near'
                   % (sum(deep)/len(deep), sum(near)/len(near)))

            # ---- 4. and it is behind you too --------------------------------------------------
            print()
            print('  AND IT IS BEHIND YOU TOO')
            glass = wall_diff('CANYON', -1, 0.0, ROAD_TOP)
            print('      CANYON    mirror %6d px' % glass['n'])
            ok(glass['n'] > 200, 'the glass carries the wall as well as the windscreen',
               '%d pixel(s) in the mirror' % glass['n'])

            if errs:
                ok(False, 'page errors', errs[0][:140])
            b.close()
    finally:
        srv.shutdown()

    print()
    print('  %s' % ('all checks passed' if not bad else '%d check(s) FAILED' % bad))
    print('  it says nothing about whether the wall reads as ROCK at speed, or whether')
    print('  WALL_RISE leaves the right strip of sky - which is the owner call on a device.')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
