#!/usr/bin/env python3
"""TREE WALL TEST - a wooded place shows a rank of trees at its boundary, ahead and in the glass.

    .venv/Scripts/python tools/tree-wall-test.py
    .venv/Scripts/python tools/tree-wall-test.py --falsify

RLG-312, owner 2026-09-21: "The biomes with trees should have a wall of trees running along side
the approaching face and leaving face (mirror)."

  1. THE TABLE DECIDES WHICH PLACES ARE WOODED. FOREST, JUNGLE and SWAMP are; a place with a rock
     face or a mass of its own (CANYON, MOUNTAIN) is not, and neither is open ground.

  2. DRIVING AT A WOODED PLACE, THE WINDSCREEN DRAWS ITS FACE - and the glass does not, because
     the wood is not behind you yet.

  3. HAVING LEFT ONE, THE GLASS DRAWS THE FACE YOU DROVE OUT OF - and the windscreen does not,
     because the wood is behind you.

  4. AND THE GLASS STOPS WHEN THE BOUNDARY LEAVES ITS REACH. The canyon's first face was pinned
     at the back of the pane 52,000 units after it had gone; this asks the same question.

  5. A PLACE THAT IS NOT WOODED DRAWS NO WALL, either way round.

  6. AND IT IS ON THE SCREEN: the same frame with the wall switched off differs, in the
     windscreen and in the glass.

WHAT IS COUNTED IS TREES DRAWN, per view, since the count was reset. Run with `--falsify` to
serve the engine with the wall never drawn: 2, 3 and 6 must fail, and 1, 4 and 5 must still
PASS, because those are the checks that say the wall is ABSENT where it should be.

Exit code 0 if every check passed, 1 otherwise.
"""
import argparse
import functools
import http.server
import importlib.util
import io
import socketserver
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from harness import console_utf8, launch_chromium, boot   # noqa: E402
from playwright.sync_api import sync_playwright            # noqa: E402

WOODED = ('FOREST', 'JUNGLE', 'SWAMP')
NOT_WOODED = ('CANYON', 'MOUNTAIN', 'DESERT', 'CITY', 'FARMLAND', 'COASTAL', 'TUNDRA')
# in SEGMENTS from the boundary; negative is past it. The glass looks 170 segments back.
AHEAD = (150, 60)
BEHIND = (-25, -110)
GONE = -240
CHAN = 24
BARE = 150
# the glass is a sixth of the frame, so it has a threshold of its own
BARE_GLASS = 40
# the mirror's pane, as a fraction of the 480 x 900 viewport. Measured from a screenshot of the
# running game rather than read from the source, so a moved mirror shows up as a failed diff.
MIRROR = (0.0, 0.16)


def pixels(a, b, y0f, y1f):
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
                    help='serve the engine with the wall never drawn')
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

    print('tree-wall-test  .  a wooded place has a face of trees at its boundary')
    if args.falsify:
        print('  FALSIFY: the wall is never drawn. 2, 3 and 6 must fail; 1, 4 and 5 must not.')
    try:
        with sync_playwright() as p:
            b = launch_chromium(p, headless=True, args=['--mute-audio'])
            ctx = b.new_context(viewport={'width': 480, 'height': 900})
            ctx.add_init_script(dt.INIT)
            if args.falsify:
                src = (ROOT / 'road.js').read_text(encoding='utf-8')
                need = '  if(!S || alpha <= 0.02) return;'
                if need not in src:
                    raise SystemExit('[tree-wall-test] --falsify cannot find its line')
                src = src.replace(need, '  return;', 1)
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

            need = ('treeWall', 'treeWallOff', 'treeWalled', 'startBiomeChange', 'jumpTo',
                    'flattenRoad', 'biomeSweep', 'setBiomePair')
            if not pg.evaluate("(ns) => ns.every(n => typeof window.__probe.road[n] === 'function')",
                               list(need)):
                ok(False, 'the engine answers the tree wall seam', ', '.join(need))
                b.close()
                print('  1 check(s) FAILED')
                return 1

            def cross(frm, to):
                """a flat, still, empty road in `frm`, with `to` planned ahead"""
                pg.evaluate("""(k) => { const R = window.__probe.road;
                    R.setTimed(false); R.holdCurve(0); R.holdSpd(0); R.flattenRoad(); R.setPhase(0.5);
                    R.setWet(0); R.setSnow(0); R.setPool(0); R.clearTraffic();
                    R.setBiomePair(k, k); }""", frm)
                pg.wait_for_timeout(500)
                pg.evaluate("(k) => window.__probe.road.startBiomeChange(k)", to)
                pg.wait_for_timeout(300)

            def at(gap):
                """put the car `gap` segments short of the boundary, settle, and count a
                window of frames. The settle is long because `jumpTo` restarts the count-in."""
                pg.evaluate("""(g) => { const R = window.__probe.road;
                    const s = R.biomeSweep(); R.jumpTo((s.edge - g) * 200);
                    R.clearTraffic(); R.holdSpd(0); }""", gap)
                pg.wait_for_timeout(2400)
                pg.evaluate("() => window.__probe.road.treeWall(true)")
                pg.wait_for_timeout(400)
                return pg.evaluate("() => window.__probe.road.treeWall(false)")

            # ---- 1. the table ---------------------------------------------------------------
            print()
            print('  WHICH PLACES ARE WOODED')
            walled = pg.evaluate("(ks) => ks.map(k => window.__probe.road.treeWalled(k))",
                                 list(WOODED + NOT_WOODED))
            got = dict(zip(WOODED + NOT_WOODED, walled))
            print('      ' + '  '.join('%s=%s' % (k, 'Y' if v else '-') for k, v in got.items()))
            ok(all(got[k] for k in WOODED) and not any(got[k] for k in NOT_WOODED),
               'the wooded places, and only those, close their faces with trees')

            # ---- 2 to 4. each wooded place, driven at and left behind ---------------------
            for place in WOODED:
                print()
                print('  %s, DRIVEN AT FROM THE DESERT' % place)
                cross('DESERT', place)
                ahead = {}
                for gap in AHEAD:
                    ahead[gap] = at(gap)
                    print('      %5d segments short   windscreen %4d   glass %4d'
                          % (gap, ahead[gap]['ahead'], ahead[gap]['mirror']))
                ok(all(ahead[g]['ahead'] > 0 for g in AHEAD),
                   'driving at a %s, its face is in the windscreen' % place.lower())
                ok(all(ahead[g]['mirror'] == 0 for g in AHEAD),
                   'and not in the glass, because it is not behind you yet')

                print('  %s, LEFT FOR THE DESERT' % place)
                cross(place, 'DESERT')
                left = {}
                for gap in BEHIND + (GONE,):
                    left[gap] = at(gap)
                    print('      %5d segments past    windscreen %4d   glass %4d'
                          % (gap, left[gap]['ahead'], left[gap]['mirror']))
                ok(all(left[g]['mirror'] > 0 for g in BEHIND),
                   'having left a %s, the face you drove out of is in the glass' % place.lower())
                ok(all(left[g]['ahead'] == 0 for g in BEHIND),
                   'and not in the windscreen, because it is behind you')
                ok(left[GONE]['mirror'] == 0,
                   'and it stops once the boundary is past what the glass can see',
                   '%d segments back: %d tree(s)' % (GONE, left[GONE]['mirror']))

            # ---- 5. the control -------------------------------------------------------------
            print()
            print('  AND A PLACE THAT IS NOT WOODED DRAWS NO WALL')
            bare = []
            for frm, to in (('DESERT', 'CANYON'), ('DESERT', 'MOUNTAIN'), ('FARMLAND', 'DESERT')):
                cross(frm, to)
                for gap in (60, -25):
                    c = at(gap)
                    bare.append(c['ahead'] + c['mirror'])
                    print('      %-8s to %-8s %5d segments   windscreen %4d   glass %4d'
                          % (frm, to, gap, c['ahead'], c['mirror']))
            ok(all(v == 0 for v in bare), 'no wall where no wooded place meets the road',
               'trees drawn: %s' % bare)

            # ---- 6. on the screen -----------------------------------------------------------
            print()
            print('  AND IT IS ON THE SCREEN, NOT ONLY IN THE COUNT')

            def diff(frm, to, gap, y0, y1):
                """the wall's own pixels, against the noise of two frames that both have it.

                TRAFFIC IS THE NOISE. A car that moves between two screenshots is a
                difference nobody drew, and in the glass it was enough to pass this check
                with the wall removed: 167 pixels against a threshold of 20. So the road is
                cleared just before every shot, and a third shot with the wall still on
                measures what is left, which the signal has to clear by a margin."""
                cross(frm, to)
                pg.evaluate("""(g) => { const R = window.__probe.road;
                    const s = R.biomeSweep(); R.jumpTo((s.edge - g) * 200);
                    R.clearTraffic(); R.holdSpd(0); }""", gap)
                pg.wait_for_timeout(2400)

                def shot(off):
                    pg.evaluate("(v) => { const R = window.__probe.road; R.treeWallOff(v);"
                                " R.clearTraffic(); }", off)
                    pg.wait_for_timeout(150)
                    return pg.screenshot()
                # ALTERNATED, AND THE SMALLEST DIFFERENCE IS THE SIGNAL. Something other
                # than the wall changes between shots now and then - the falsify arm once
                # found 267 pixels in the glass with no wall drawn and 0 of measured noise.
                # A one-off change can land in one on/off pair; it cannot land in all three.
                on1, off1 = shot(False), shot(True)
                on2, off2 = shot(False), shot(True)
                pg.evaluate("() => window.__probe.road.treeWallOff(false)")
                sig = min(pixels(on1, off1, y0, y1), pixels(off1, on2, y0, y1),
                          pixels(on2, off2, y0, y1))
                noise = max(pixels(on1, on2, y0, y1), pixels(off1, off2, y0, y1))
                return sig, noise

            for label, frm, to, gap, box, bare in (
                    ('windscreen, 60 segments short of a forest', 'DESERT', 'FOREST', 60,
                     (MIRROR[1], 1.0), BARE),
                    ('glass, 25 segments out of a forest', 'FOREST', 'DESERT', -25, MIRROR,
                     BARE_GLASS)):
                sig, noise = diff(frm, to, gap, *box)
                print('      %s: %d pixel(s) differ, against %d of noise' % (label, sig, noise))
                # the noise is printed and not asserted against: two shots of the same
                # frame half a second apart differ by the sky's drift, and the smallest
                # of three on/off pairs is already what shuts a one-off change out
                ok(sig > bare,
                   'taking the wall away changes the %s' % label.split(',')[0],
                   '%d against %d' % (sig, noise))

            if errs:
                ok(False, 'page errors', errs[0][:140])
            b.close()
    finally:
        srv.shutdown()

    print()
    print('  %s' % ('all checks passed' if not bad else '%d check(s) FAILED' % bad))
    print('  whether the rank reads as the edge of a wood rather than a row of')
    print('  trees is the owner call on a device.')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
