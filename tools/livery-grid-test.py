#!/usr/bin/env python3
"""LIVERY GRID TEST - the rivals wear every stripe pattern, colour and underglow the garage offers.

    .venv/Scripts/python tools/livery-grid-test.py
    .venv/Scripts/python tools/livery-grid-test.py --falsify

RLG-323, owner 2026-09-21: "I want to make sure all the stripe versions, random colors, and
underglows are being used by the racers."

A TALLY, NOT A READING OF THE SOURCE. Many grids are built through `restart`, the path a real
race start takes, and every rival's livery is counted against the full table each part is drawn
from (`API.liveryTables`):

  1. EVERY STRIPE PATTERN appears on some rival - all five, not only the plain pair.
  2. EVERY BASE COLOUR appears as a stripe colour, and as a second tone - the "random colours".
  3. EVERY UNDERGLOW COLOUR appears on some rival.
  4. EVERY PAINT appears as a body colour, except the player's own, which the grid leaves to the
     player on purpose.
  5. AND NOTHING LANDS WHERE IT MAY NOT: a body that takes no livery wears none. A guard: the
     default grid may hold no such body.
  6. AND THEY ARE DRAWN IN IT: a grid raced with every chance at one draws rivals in their livery
     sprites and over their glows.

Run with `--falsify` to put back the plain pair as the only pattern: 1 must fail and nothing else.

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

GRIDS = 120


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--falsify', action='store_true', help='rivals wear the plain pair only')
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

    print('livery-grid-test  .  the rivals wear the whole livery table')
    if args.falsify:
        print('  FALSIFY: rivals wear the plain pair only. 1 must fail; nothing else may.')
    try:
        with sync_playwright() as p:
            b = launch_chromium(p, headless=True, args=['--mute-audio'])
            ctx = b.new_context(viewport={'width': 480, 'height': 900})
            ctx.add_init_script(dt.INIT)
            if args.falsify:
                src = (ROOT / 'road.js').read_text(encoding='utf-8')
                need = "stripes: striped ? pick(pats).stripes : false,"
                if src.count(need) != 1:
                    raise SystemExit('[livery-grid-test] --falsify cannot find its line')
                src = src.replace(need, "stripes: striped ? true : false,", 1)
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
            need = ('gridLiveries', 'liveryTables', 'racerLivery', 'restart', 'setMode')
            if not pg.evaluate("(ns) => ns.every(n => typeof window.__probe.road[n] === 'function')",
                               list(need)):
                ok(False, 'the engine answers the livery seam', ', '.join(need))
                b.close()
                print('  1 check(s) FAILED')
                return 1
            tables = pg.evaluate("() => window.__probe.road.liveryTables()")
            chances = pg.evaluate("() => window.__probe.road.racerLivery()")
            print('      chances: %s' % chances)
            # a race, because racers exist only in race mode (see mind-test)
            pg.evaluate("() => window.__probe.road.setMode('race')")
            cars = []
            for _ in range(GRIDS):
                pg.evaluate("() => window.__probe.road.restart()")
                pg.wait_for_timeout(40)
                cars += pg.evaluate("() => window.__probe.road.gridLiveries()")
            own = pg.evaluate("() => window.__probe.road.paint()")
            print('      %d rival(s) over %d grid(s)' % (len(cars), GRIDS))

            def tally(key):
                t = {}
                for c in cars:
                    v = c.get(key)
                    if v not in (None, False):
                        t[str(v)] = t.get(str(v), 0) + 1
                return t

            pats, stripes, tones, glows, paints = (tally('pattern'), tally('stripe'), tally('tone'),
                                                   tally('glow'), tally('paint'))
            want_p = [str(x) for x in tables['patterns']]
            print('      patterns %s' % pats)
            print('      glows    %s' % glows)
            ok(len(cars) >= GRIDS * 5, 'enough rivals were built to say anything', '%d' % len(cars))
            miss = [x for x in want_p if x not in pats]
            ok(not miss, '1. every stripe pattern appears on a rival', 'never: %s' % miss if miss else '')
            miss_s = [k for k in tables['base'] if k not in stripes]
            miss_t = [k for k in tables['base'] if k not in tones]
            ok(not miss_s and not miss_t, '2. every base colour appears as a stripe colour and a second tone',
               'never as stripes: %s; never as a tone: %s' % (miss_s, miss_t) if (miss_s or miss_t) else
               '%d stripe colours, %d tones' % (len(stripes), len(tones)))
            miss_g = [k for k in tables['glows'] if k not in glows]
            ok(not miss_g, '3. every underglow colour appears on a rival', 'never: %s' % miss_g if miss_g else '')
            miss_c = [k for k in tables['paints'] if k not in paints and k != own]
            ok(not miss_c and own not in paints,
               "4. every paint appears on a rival, but the player's own",
               'the player wears %s; never on a rival: %s' % (own, miss_c))
            # A GUARD, NOT A MEASUREMENT: the default grid is drawn from the player's class,
            # which may hold no body that takes no livery (review of UNT-419)
            wrong = [c for c in cars if not c['takes']
                     and (c['pattern'] or c['stripe'] or c['tone'] or c['glow'])]
            ok(not wrong, '5. a body that takes no livery wears none',
               '%d wrong: %s' % (len(wrong), wrong[:2]) if wrong else '')
            # ---- 6. AND THEY ARE DRAWN IN IT --------------------------------------------------
            # The tally counts rolls. This races a grid with every chance at one and counts
            # the rivals the windscreen actually drew in a livery sprite and over a glow.
            pg.evaluate("""() => { const R = window.__probe.road;
                R.racerLivery({ stripes: 1, twotone: 1, glow: 1 }); R.restart();
                R.setTimed(false); R.setPhase(0.22); }""")
            pg.wait_for_timeout(2500)
            pg.evaluate("() => window.__probe.road.liveryDrawn(true)")
            pg.wait_for_timeout(1000)
            drawn = pg.evaluate("() => window.__probe.road.liveryDrawn(false)")
            pg.evaluate("(c) => window.__probe.road.racerLivery(c)", chances)
            print('      drawn in a second: %s' % drawn)
            ok(drawn['rear'] > 0 and drawn['glow'] > 0,
               '6. and the windscreen draws them in it, glow and all',
               '%d livery sprite(s), %d glow(s)' % (drawn['rear'], drawn['glow']))

            if errs:
                ok(False, 'page errors', errs[0][:140])
            b.close()
    finally:
        srv.shutdown()

    print()
    print('  %s' % ('all checks passed' if not bad else '%d check(s) FAILED' % bad))
    print('  how a rival looks in each livery is the owner call on a device.')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
