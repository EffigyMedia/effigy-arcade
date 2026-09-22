#!/usr/bin/env python3
"""GLASS SURVEY TEST - every layer the windscreen paints beside the road, the mirror paints too.

    .venv/Scripts/python tools/glass-survey-test.py
    .venv/Scripts/python tools/glass-survey-test.py --falsify

RLG-312, owner 2026-09-21: "We need to verify everything can be seen in the mirror."

THE GLASS HAS BEEN FOUND SHORT SIX TIMES, and every time from a device: the rail, the drop
(twice), the wall, the weather, the checkpoint boards and the finish line. `mirror-test` already
closes the question for the things ON the road - cars, boards, blocks, crates - because both
views are handed the same list. Nothing closed it for the LAYERS, which have no list: each one
is a painter, and a missing painter is silent.

So each layer counts itself where it paints, per view (`API.viewLayers`), and this tours the
places and asserts that every layer the windscreen painted, the glass painted too:

  1. EVERY PLACE, STANDING IN IT. Ahead and behind are the same place, so each layer the
     windscreen paints there must be in the glass in the same scene.

  2. EVERY BOUNDARY, BOTH WAYS. A face, a wood's rank of trees and a tunnel's portal stand at
     a boundary, so the windscreen sees them ahead and the glass sees them behind. Each place
     that has one is driven at from the desert, entered, and left for the desert.

  3. THE THINGS ONLY ONE GAME OR ONE WEATHER HAS: a circuit's kerb in Motorsport, a bridge's
     deck, the coast's sea and boats, and rain.

  4. AND THE UNION: nothing the windscreen painted anywhere in the tour is missing from the
     glass everywhere in it.

NOT SURVEYED, AND SAID SO: the sky's own objects - clouds, stars, the sun and the moon. They
are not beside the road, and whether the glass should show them is the owner's ruling
(RLG-312). Camera effects - the lens, the speed lines, the player's own beams and the pursuit
wash - are not in the world, so there is nothing for a mirror to show.

Run with `--falsify` to serve the engine with the five glass layers this survey found missing
taken out again - the street lamps, the valley range, the kerb, the deck's joints and the tunnel's
portal - which is the glass as it stood before RLG-312. The city, the mountain, the bridge, the
tunnel's boundary, the circuit and the union must fail and name them; every other scene must
still pass.

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

PLACES = ('COASTAL', 'FARMLAND', 'SWAMP', 'JUNGLE', 'FOREST', 'DESERT', 'MOUNTAIN', 'CITY',
          'TUNDRA', 'CANYON', 'BRIDGE', 'TUNNEL')
# the places whose boundary carries something of its own
EDGED = ('CANYON', 'FOREST', 'JUNGLE', 'SWAMP', 'TUNNEL', 'MOUNTAIN')
# in segments from the boundary; negative is past it
AHEAD, INSIDE = 60, -25
# the windscreen layers that belong to a boundary, and so are asked of the crossing scenes as
# pairs rather than of one scene
EDGE_LAYERS = {'face', 'treeWall', 'portal'}
# the five layers RLG-312 found missing from the glass
NEW_LAYERS = {'lamp', 'range', 'kerb', 'joint', 'portal'}
# the glass as it stood before RLG-312: each of the five layers the survey found missing, cut
FALSIFY = (
    ("    if(mB.truss || CFG.circuitOnly){\n      const mr1", "    if(false){\n      const mr1"),
    ("    if(mDeck && b2.w > 2){\n      const js", "    if(false){\n      const js"),
    ("        if(li % 8 !== 0 || bioBehind(li).name !== 'CITY') continue;", "        continue;"),
    # since RLG-316 the range is peaks from one painter; the glass's are cut there
    ("function rangePeak(B, side, p, floorY, idx, alpha, grow, kv, x0, x1, view){\n",
     "function rangePeak(B, side, p, floorY, idx, alpha, grow, kv, x0, x1, view){\n"
     "  if(view === 'glass') return 0;\n"),
    ("      if(!!bB.bore !== !!aB.bore && zE < pos - 200 && zE > pos - MIRROR_BACK){",
     "      if(false){"),
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--falsify', action='store_true',
                    help='serve the engine with the five new glass layers cut out')
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

    print('glass-survey-test  .  every layer the windscreen paints, the glass paints too')
    if args.falsify:
        print('  FALSIFY: the five layers are cut from the glass. The city, mountain, bridge,')
        print('  tunnel boundary, circuit and union must fail; nothing else may.')
    front_all, glass_all = set(), set()
    edge_front, edge_glass = {}, {}
    try:
        with sync_playwright() as p:
            b = launch_chromium(p, headless=True, args=['--mute-audio'])

            def page(game):
                ctx = b.new_context(viewport={'width': 480, 'height': 900})
                ctx.add_init_script(dt.INIT)
                if args.falsify:
                    src = (ROOT / 'road.js').read_text(encoding='utf-8')
                    for need, cut in FALSIFY:
                        if src.count(need) != 1:
                            raise SystemExit('[glass-survey-test] --falsify cannot find: '
                                             + need[:60])
                        src = src.replace(need, cut, 1)
                    ctx.route('**/road.js', lambda route: route.fulfill(
                        status=200, content_type='application/javascript', body=src))
                pg = ctx.new_page()
                errs = []
                pg.on('pageerror', lambda e: errs.append(str(e)))
                boot(pg, 'http://127.0.0.1:%d/games/sw/%s.html' % (port, game))
                pg.wait_for_timeout(1000)
                pg.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
                pg.click('[data-act="play"]')
                pg.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
                pg.click('[data-act="drive"]')
                pg.wait_for_timeout(1500)
                pg.evaluate("() => window.__probe.road.watchDraw(true)")
                return ctx, pg, errs

            def settle_and_read(pg, wait=2400):
                pg.wait_for_timeout(wait)
                pg.evaluate("() => window.__probe.road.viewLayers(true)")
                pg.wait_for_timeout(600)
                v = pg.evaluate("() => window.__probe.road.viewLayers(false)")
                return set(v['front']), set(v['glass'])

            def still(pg, frm, to=None, wet=0):
                pg.evaluate("""(o) => { const R = window.__probe.road;
                    R.setTimed(false); R.holdCurve(0); R.holdSpd(0); R.flattenRoad(); R.setPhase(0.5);
                    R.setWet(o.wet); R.setSnow(0); R.setPool(0); R.clearTraffic();
                    R.setBiomePair(o.frm, o.frm); }""", {'frm': frm, 'wet': wet})
                pg.wait_for_timeout(500)
                if to:
                    pg.evaluate("(k) => window.__probe.road.startBiomeChange(k)", to)
                    pg.wait_for_timeout(300)

            def at(pg, gap):
                pg.evaluate("""(g) => { const R = window.__probe.road;
                    const s = R.biomeSweep(); R.jumpTo((s.edge - g) * 200);
                    R.clearTraffic(); R.holdSpd(0); }""", gap)

            def scene(label, f, g, edges=False):
                front_all.update(f)
                glass_all.update(g)
                ask = f - EDGE_LAYERS if not edges else f
                missing = sorted(ask - g)
                ok(not missing, label,
                   ('glass lacks: ' + ', '.join(missing)) if missing else
                   '%d layer(s) in both' % len(ask & g))

            ctx, pg, errs = page('interstate')
            need = ('viewLayers', 'watchDraw', 'startBiomeChange', 'jumpTo', 'setBiomePair')
            if not pg.evaluate("(ns) => ns.every(n => typeof window.__probe.road[n] === 'function')",
                               list(need)):
                ok(False, 'the engine answers the survey seam', ', '.join(need))
                b.close()
                print('  1 check(s) FAILED')
                return 1

            # ---- 1. every place, standing in it -------------------------------------------
            print()
            print('  EVERY PLACE, STANDING IN IT')
            for place in PLACES:
                still(pg, place)
                f, g = settle_and_read(pg)
                scene('%-8s the glass paints what the windscreen paints' % place.lower(), f, g)

            # ---- 2. every boundary, both ways -----------------------------------------------
            print()
            print('  EVERY BOUNDARY, BOTH WAYS')
            for place in EDGED:
                # arriving: the boundary is ahead, so its layers are the windscreen's
                still(pg, 'DESERT', place)
                at(pg, AHEAD)
                f1, g1 = settle_and_read(pg)
                # inside: the boundary you came through is behind you
                at(pg, INSIDE)
                f2, g2 = settle_and_read(pg)
                # leaving: the exit is ahead, and then behind
                still(pg, place, 'DESERT')
                at(pg, AHEAD)
                f3, g3 = settle_and_read(pg)
                at(pg, INSIDE)
                f4, g4 = settle_and_read(pg)
                ef = (f1 | f3) & EDGE_LAYERS
                eg = (g2 | g4) & EDGE_LAYERS
                front_all.update(f1 | f2 | f3 | f4)
                glass_all.update(g1 | g2 | g3 | g4)
                edge_front[place], edge_glass[place] = ef, eg
                missing = sorted(ef - eg)
                ok(not missing,
                   '%-8s what stands at its boundary ahead stands there behind' % place.lower(),
                   ('glass lacks: ' + ', '.join(missing)) if missing else
                   'ahead %s, behind %s' % (sorted(ef) or '-', sorted(eg) or '-'))

            # ---- 3. rain -------------------------------------------------------------------
            print()
            print('  WEATHER')
            still(pg, 'FOREST', wet=1)
            f, g = settle_and_read(pg, 3000)
            scene('rain     the glass paints what the windscreen paints', f, g)
            if errs:
                ok(False, 'page errors (interstate)', errs[0][:140])
            ctx.close()

            # ---- 3. a circuit ----------------------------------------------------------------
            print()
            print('  A CIRCUIT')
            ctx, pg, errs = page('motorsport')
            pg.evaluate("() => { const R = window.__probe.road; R.setTimed && R.setTimed(false);"
                        " R.holdSpd(0); R.clearTraffic(); }")
            f, g = settle_and_read(pg)
            ok('kerb' in f, 'a circuit paints its kerb out of the windscreen',
               'front: %s' % sorted(f))
            scene('circuit  the glass paints what the windscreen paints', f, g)
            if errs:
                ok(False, 'page errors (motorsport)', errs[0][:140])
            ctx.close()

            # ---- 4. the union ----------------------------------------------------------------
            print()
            print('  THE WHOLE TOUR')
            print('      windscreen: %s' % ', '.join(sorted(front_all)))
            print('      glass:      %s' % ', '.join(sorted(glass_all)))
            ok(len(front_all) >= 18, 'the tour saw enough of the road to say anything',
               '%d layer(s) out of the windscreen' % len(front_all))
            # AND THE FIVE THIS SURVEY ADDED WERE ACTUALLY EXERCISED. `front - glass` only asks
            # about what the windscreen painted, so a tour in which the windscreen never paints
            # one of them would pass it empty (RVW, UNT-412, finding 1).
            unseen = sorted(NEW_LAYERS - front_all)
            ok(not unseen, 'the tour painted each of the five layers the glass was missing',
               ('never painted ahead: ' + ', '.join(unseen)) if unseen else ', '.join(sorted(NEW_LAYERS)))
            missing = sorted(front_all - glass_all)
            ok(not missing, 'nothing the windscreen painted anywhere is missing from the glass',
               ('glass lacks: ' + ', '.join(missing)) if missing else '')
            b.close()
    finally:
        srv.shutdown()

    print()
    print('  %s' % ('all checks passed' if not bad else '%d check(s) FAILED' % bad))
    print('  a layer being painted is not the same as it looking right in the glass;')
    print('  that is the owner call on a device.')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
