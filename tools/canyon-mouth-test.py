#!/usr/bin/env python3
"""CANYON MOUTH TEST - a walled place shows its face as you drive at it, and behind you as you leave.

    .venv/Scripts/python tools/canyon-mouth-test.py
    .venv/Scripts/python tools/canyon-mouth-test.py --falsify

RLG-301, owner 2026-09-20, from the device: "What we do need is the canyon walls facing the
roadway when you're driving towards the canyon and also in the rearview mirror when you exit
one."

A CANYON USED TO ARRIVE AS A HAIRLINE. RLG-297's walls run ALONGSIDE the road and nothing stood
at the end of them, so a canyon seen from a mile of desert was a thin vertical sliver at the
vanishing point that widened as you reached it - you never drove AT anything. The face is the
massif: the place's own rock across the whole view with the slot the two walls leave, and the
road goes through the slot.

  1. IT IS THERE WHEN THE BOUNDARY IS AHEAD, and it is drawn into the WINDSCREEN.

  2. IT IS THERE WHEN THE BOUNDARY IS BEHIND, and then it is drawn into the GLASS. This is the
     half the drop needed twice and the wall needed once, so it is asked for here rather than
     waited for.

  3. AND IT STOPS WHEN THE BOUNDARY LEAVES THE GLASS'S REACH. `widx >= biomeEdge` is true for
     EVERY step once the edge has fallen past `MIRROR_BACK`, so the first version pinned the
     massif at the back of the pane and left it there: measured still painting with the boundary
     52,000 units behind a glass that looks 34,000 back. THIS IS THE CHECK THAT CAUGHT IT.

  4. AND A PLACE WITH NO WALL SHOWS NONE, either way round. Without this every question above
     passes on a build that paints a face at every boundary there is.

WHAT IS COUNTED IS FRAMES PAINTED, not pixels. How much of the face shows is the road's slope
and how far the boundary is - the same reason the valley range's check had to stop counting - so
the pass reports how many frames it painted on since the count was reset, and a pixel diff
through `API.endWallOff` is kept for the one question a count cannot answer: that something
actually changed on screen.

Run with `--falsify` to serve the engine with the face never drawn. Questions 1, 2 and the pixel
diff must fail; questions 3 and 4 must still PASS, because they are the two that say the face is
ABSENT where it should be - a falsify arm that takes those down has broken the harness rather
than removed the feature.

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

# in SEGMENTS from the boundary. Negative is past it. The mirror looks MIRROR_BACK - 34,000
# units, which is 170 segments, so -240 is comfortably beyond the glass.
AHEAD = (120, 40)
BEHIND = (-30, -120)
GONE = -240
# the sum of the three channel deltas that counts as a different surface
CHAN = 24
BARE = 300


def pixels(a, b, y0f, y1f):
    import io
    from PIL import Image
    ia = Image.open(io.BytesIO(a)).convert('RGB')
    ib = Image.open(io.BytesIO(b)).convert('RGB')
    w, h = ia.size
    pa, pb = ia.load(), ib.load()
    n = 0
    for y in range(int(h * y0f), int(h * y1f), 2):
        for x in range(0, w, 2):
            ca, cb = pa[x, y], pb[x, y]
            if abs(ca[0]-cb[0]) + abs(ca[1]-cb[1]) + abs(ca[2]-cb[2]) > CHAN:
                n += 1
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--falsify', action='store_true',
                    help='serve the engine with the face never drawn')
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

    print('canyon-mouth-test  .  a walled place has a face at its boundary')
    if args.falsify:
        print('  FALSIFY: the face is never drawn. 1, 2 and the diff must fail; 3 and 4 must not.')
    try:
        with sync_playwright() as p:
            b = launch_chromium(p, headless=True, args=['--mute-audio'])
            ctx = b.new_context(viewport={'width': 480, 'height': 900})
            ctx.add_init_script(dt.INIT)
            if args.falsify:
                src = (ROOT / 'road.js').read_text(encoding='utf-8')
                need = '  if(!B || !B.wall || wallOff || endWallOff) return 0;'
                if need not in src:
                    raise SystemExit('[canyon-mouth-test] --falsify cannot find its line')
                src = src.replace(need, '  return 0;', 1)
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

            need = ('endWall', 'endWallOff', 'startBiomeChange', 'jumpTo', 'flattenRoad')
            if not pg.evaluate("(ns) => ns.every(n => typeof window.__probe.road[n] === 'function')",
                               list(need)):
                ok(False, 'the engine answers the boundary seam', ', '.join(need))
                b.close()
                print('  1 check(s) FAILED')
                return 1

            def arrive(place):
                """a flat, still, empty road in a desert, with `place` planned ahead"""
                pg.evaluate("""() => { const R = window.__probe.road;
                    R.setTimed(false); R.holdCurve(0); R.flattenRoad(); R.setPhase(0.5);
                    R.setWet(0); R.setSnow(0); R.setPool(0); R.clearTraffic();
                    R.setBiomePair('DESERT','DESERT'); R.holdSpd(0); }""")
                pg.wait_for_timeout(500)
                pg.evaluate("(k) => window.__probe.road.startBiomeChange(k)", place)
                pg.wait_for_timeout(300)

            def at(gap):
                """put the car `gap` segments short of the boundary and let it settle.

                THE SETTLE IS LONG ON PURPOSE. `jumpTo` moves the car and the run restarts
                with its own count-in, during which nothing is stepped - a short wait reads
                a frozen frame and reports whatever was on it."""
                pg.evaluate("""(g) => { const R = window.__probe.road;
                    const s = R.biomeSweep(); R.jumpTo((s.edge - g) * 200);
                    R.clearTraffic(); R.holdSpd(0); }""", gap)
                pg.wait_for_timeout(2400)
                pg.evaluate("() => window.__probe.road.endWall(true)")
                pg.wait_for_timeout(400)
                return pg.evaluate("() => window.__probe.road.endWall(false)")['frames']

            # ---- 1 and 2. the face, ahead and behind -----------------------------------------
            print()
            print('  A CANYON, DRIVEN AT AND LEFT BEHIND')
            arrive('CANYON')
            seen = {}
            for gap in AHEAD + BEHIND + (GONE,):
                seen[gap] = at(gap)
                print('      %5d segments from the boundary   painted on %2d frame(s)'
                      % (gap, seen[gap]))
            ok(all(seen[g] > 0 for g in AHEAD),
               'driving at a canyon, its face is in the windscreen',
               'at %s segments: %s' % (AHEAD, [seen[g] for g in AHEAD]))
            ok(all(seen[g] > 0 for g in BEHIND),
               'and having left one, its face is in the glass',
               'at %s segments: %s' % (BEHIND, [seen[g] for g in BEHIND]))
            ok(seen[GONE] == 0,
               'and it stops once the boundary is past what the glass can see',
               '%d segments back, painted on %d frame(s)' % (GONE, seen[GONE]))

            # ---- 3. and something actually changed on screen ---------------------------------
            print()
            print('  AND IT IS ON THE SCREEN, NOT ONLY IN THE COUNT')
            arrive('CANYON')
            pg.evaluate("""() => { const R = window.__probe.road;
                const s = R.biomeSweep(); R.jumpTo((s.edge - 90) * 200);
                R.clearTraffic(); R.holdSpd(0); }""")
            pg.wait_for_timeout(2400)
            pg.evaluate("() => window.__probe.road.endWallOff(true)")
            pg.wait_for_timeout(200)
            off = pg.screenshot()
            pg.evaluate("() => window.__probe.road.endWallOff(false)")
            pg.wait_for_timeout(200)
            on = pg.screenshot()
            moved = pixels(on, off, 0.0, 1.0)
            print('      with the face and without it: %d pixel(s) differ' % moved)
            ok(moved > BARE, 'taking the face away changes the picture',
               '%d pixel(s)' % moved)

            # ---- 4. the control ---------------------------------------------------------------
            print()
            print('  AND A PLACE WITH NO WALL HAS NO FACE')
            arrive('FOREST')
            bare = {}
            for gap in (120, -30):
                bare[gap] = at(gap)
                print('      %5d segments from a forest boundary   painted on %2d frame(s)'
                      % (gap, bare[gap]))
            ok(all(v == 0 for v in bare.values()),
               'a place with no wall paints no face, ahead or behind',
               'painted on %s frame(s)' % list(bare.values()))

            if errs:
                ok(False, 'page errors', errs[0][:140])
            b.close()
    finally:
        srv.shutdown()

    print()
    print('  %s' % ('all checks passed' if not bad else '%d check(s) FAILED' % bad))
    print('  whether the massif reads as rock you are driving at, and whether its')
    print('  broken top is broken enough, is the owner call on a device.')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
