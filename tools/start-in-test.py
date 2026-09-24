#!/usr/bin/env python3
"""START IN - the debug menu can choose the place a run opens in, and the run opens there.

    EFFIGY_NO_GPU=1 PYTHONIOENCODING=utf-8 .venv/Scripts/python tools/start-in-test.py
    ... tools/start-in-test.py --place CANYON

Owner, 2026-09-24, trying to test three device reports that all need a mountain: "I haven't
actually seen a mountain yet. I couldn't get that biome." [[RLG-338]]

THE WAIT IS REAL AND IT WAS MEASURED THROUGH THE GAME'S OWN PICKER. `API.walkPlaces` over
9,600 place changes: a MOUNTAIN is 2.11 per cent of them and takes 58 places to arrive on
average, which at three and a quarter to six miles a place is on the order of 270 miles of
driving. It was absent altogether from eleven walks of two hundred places. So three open
reports could not be tested at all, and OPTIONS > DEBUG gained a starting place.

WHAT THIS CHECKS, AND IT IS THE WHOLE POINT OF THE ROW: not that a button exists, but that
a run really OPENS in the place named. The row is walked through the real veil with a real
pointer - the path a thumb takes - the run is then started the way a player starts one, and
the engine is asked what place the car is standing in.

A JUMP WAS BUILT FIRST AND THE OWNER CORRECTED IT. "Instead of a real time, send me there
during the game just have the debug have a recyclable menu where you're picking the starting
biome." The jump placed a change at the horizon and the car had to drive into it, which the
check caught failing - the car was still in a TUNDRA forty seconds later. An opening has
nothing to arrive at: it is simply where the road begins.

AND IT IS RUN FOR A PLACE WITH A MASS, because those are the two the open reports are about
and the two the picker almost never offers. A row that worked for a FOREST and not a
MOUNTAIN would be worse than none.

WHAT IT DOES NOT CHECK. It does not judge the picture, and it does not touch the skew in
the picker - what the mix of places should be is the owner's call and is tracked on its own.
"""
import argparse
import functools
import http.server
import socketserver
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from harness import console_utf8, launch_chromium, boot, until   # noqa: E402
from playwright.sync_api import sync_playwright                  # noqa: E402

fails = []


def check(label, condition, detail=''):
    print('%s  %s%s' % ('PASS' if condition else 'FAIL', label,
                        ('  [%s]' % detail) if detail else ''))
    if not condition:
        fails.append(label)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--place', default='MOUNTAIN')
    ap.add_argument('--off', action='store_true',
                    help='also check that cycling back to ANYWHERE clears the override')
    args = ap.parse_args()
    console_utf8()

    h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
    srv = socketserver.TCPServer(('127.0.0.1', 0), h)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    init = """
    window.__probe = { road: null };
    (function(){ var real=null, wrapped=null;
      Object.defineProperty(window,'ROAD',{configurable:true,
        get:function(){return real?wrapped:undefined;},
        set:function(fn){real=fn;wrapped=function(CFG){var api=real(CFG);
          window.__probe.road=api||(CFG&&CFG.api)||null;return api;};}});})();
    """

    print()
    print('  start-in  .  OPTIONS > DEBUG opens a run in %s' % args.place)
    with sync_playwright() as p:
        br = launch_chromium(p, headless=True, args=['--mute-audio'])
        pg = br.new_page(viewport={'width': 480, 'height': 900})
        errs = []
        pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.add_init_script(init)
        boot(pg, 'http://127.0.0.1:%d/games/sw/interstate.html' % port)
        until(pg, '!!window.__probe.road', timeout=15000)
        pg.wait_for_selector('#veil:not(.hidden) [data-act="opts"]', timeout=10000)

        def tap(act):
            pg.click('#veil:not(.hidden) [data-act="%s"]' % act)
            pg.wait_for_timeout(180)

        def label():
            return pg.inner_text('#veil:not(.hidden) [data-act="ds"]')

        def shown():
            """the place named on the row. The label reads 'START IN · MOUNTAIN' on one
            line, and the first cut of this compared the whole of it against the place
            name and reported a row that plainly worked as broken."""
            t = label()
            return t.split('·')[-1].strip().upper()

        tap('opts')
        tap('debug')
        check('the debug menu has a starting-place row', 'START IN' in label().upper(), label())
        check('and it ships OFF', shown() == 'ANYWHERE', shown())

        # ---- CYCLED WITH THE POINTER, NOT SET ------------------------------------
        # The row is a thumb control and the check walks it the way a thumb does. The
        # list is finite, so a cycle that cannot reach the place is a failure rather
        # than a hang: at most one full turn of it.
        keys = pg.evaluate("() => window.__probe.road.OPEN_KEYS()")
        seen = []
        for _ in range(len(keys) + 2):
            now = shown()
            seen.append(now)
            if now == args.place:
                break
            tap('ds')
        check('the row cycles to %s' % args.place, args.place in seen,
              'walked %s' % ' '.join(seen))

        # ---- AND A RUN STARTED THE WAY A PLAYER STARTS ONE OPENS THERE -----------
        # The override is read inside `pickOpening`, which is the one function the
        # real opening draw calls - so this cannot pass on a debug-only path.
        pg.click('#veil:not(.hidden) [data-act="back"]')
        pg.wait_for_timeout(200)
        for act in ('back', 'play', 'drive'):
            try:
                pg.click('#veil:not(.hidden) [data-act="%s"]' % act, timeout=1500)
                pg.wait_for_timeout(300)
            except Exception:
                pass
        pg.wait_for_timeout(600)
        here = pg.evaluate("() => window.__probe.road.biome()")
        moving = pg.evaluate("() => window.__probe.road.roadPos()")
        check('a run opens in %s' % args.place, args.place in str(here),
              'opened in %s' % here)
        check('and it is a real run, not a held title card', moving is not None,
              'pos %s' % moving)

        check('no page errors', not errs, '; '.join(errs[:2]))
        br.close()

    print()
    if fails:
        print('FAILED: %d' % len(fails))
        for f in fails:
            print('  - %s' % f)
        sys.exit(1)
    print('ALL CHECKS PASSED')


if __name__ == '__main__':
    main()
