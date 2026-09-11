#!/usr/bin/env python3
"""LEAGUE TEST - which field is built around the car you chose.

    .venv/Scripts/python tools/league-test.py

RLG-202. Owner, 2026-09-10: "the cruiser and supercruiser are eligible for their class of race",
and then, deciding what INTERCEPT runs against: "in a symmetrical fashion, the cruiser intercepts
against a sports class race and the supercruiser intercepts against a super class race."

SO THE CLASS OF A POLICE CAR IS LOAD-BEARING TWICE - once for which grid it lines up on, and once
for which race INTERCEPT sends it to break up. It was wrong for both. There are two class systems in
`road.js`: `BODY_CLASS` is the UNLOCK class and knows `cruiser` and `supercruiser`, and `classOf` is
the RACE class, which read two lists and fell through to `super` for everything else. A patrol car
was put on a grid of STALLIONs, MATADORs and CRESTs.

AND THE CODE ALREADY SAID SO IN TWO PLACES - the SUPERCRUISER's own note ("the floor of the supercar
class, exactly as the CRUISER is the floor of the sports class") and the tournament's police prize
("a cruiser is comparable to the sports class and a super cruiser to the supers"). Both comments
were right and the function was wrong. Nothing could see it, because until RLG-181 shipped this
morning neither car could be selected.

WHAT THIS READS. `gridBodies` is new and reports the field `buildField` ACTUALLY built, not the plan
`racerBodies` returns - a check that read the plan would be agreeing with the plan. The two ordinary
cars are the controls: if a MUSCLE stopped drawing a sports grid, the fault would be the harness or
the engine rather than this ruling.

AND THE LAST ARM IS THE POINT. The league is declared on the BODY record so that a third force car
needs no edit to `classOf`. So the falsification takes the declaration off the live record and
requires the CRUISER to fall back into the supercar field - the exact defect, watched.

Exit code 0 if every check passed, 1 otherwise.
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
from harness import console_utf8, launch_chromium, boot, reboot
from playwright.sync_api import sync_playwright

GAME = 'games/sw/interstate.html'
SPORTS = {'ROADSTER', 'TUNER', 'MUSCLE'}
SUPER = {'STALLION', 'MATADOR', 'CREST'}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--headed', action='store_true')
    args = ap.parse_args()
    console_utf8()

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
    srv = socketserver.TCPServer(('127.0.0.1', 0), handler)
    base = 'http://127.0.0.1:%d' % srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    bad = 0

    def ok(cond, label, detail=''):
        nonlocal bad
        if not cond:
            bad += 1
        print('  %s  %s%s' % ('ok  ' if cond else 'FAIL', label,
                              ('   ' + detail) if detail else ''))

    print('league-test  .  which field is built around the car you chose')
    with sync_playwright() as p:
        b = launch_chromium(p, headless=not args.headed,
                            args=['--mute-audio', '--autoplay-policy=no-user-gesture-required'])
        ctx = b.new_context(viewport={'width': 480, 'height': 900})
        page = ctx.new_page()
        errs = []
        page.on('pageerror', lambda e: errs.append(str(e)))

        boot(page, '%s/%s' % (base, GAME))
        page.wait_for_timeout(600)
        # both police cars won, so the garage will stand in front of them
        page.evaluate("""() => {
            window.Arcade.save.merge('interstate-opts',
                { super:true, cruiser:true, supercruiser:true });
        }""")
        reboot(page)
        page.wait_for_timeout(700)

        def grid_for(car):
            """Put the car on the road in a race and report the field that was built."""
            return page.evaluate("""(k) => {
                const R = window.__road;
                R.setBody(k);
                R.setMode('race');
                R.restart();
                return { cls: R.raceClass(k), grid: R.gridBodies() };
            }""", car)

        # ---- THE TWO CONTROLS FIRST -------------------------------------
        print('  -- the two ordinary cars, which decide whether this file works at all')
        for car, want, pool in (('MUSCLE', 'sports', SPORTS), ('STALLION', 'super', SUPER)):
            r = grid_for(car)
            ok(r['cls'] == want, 'a %s runs the %s league' % (car, want),
               'reads %r' % r['cls'])
            ok(bool(r['grid']) and set(r['grid']) <= pool,
               'and its field is drawn from that class',
               '%d cars: %s' % (len(r['grid']), ', '.join(sorted(set(r['grid'])))))

        # ---- THE RULING ITSELF ------------------------------------------
        print('  -- the two police cars')
        for car, want, pool in (('CRUISER', 'sports', SPORTS),
                                ('SUPERCRUISER', 'super', SUPER)):
            r = grid_for(car)
            ok(r['cls'] == want, 'a %s runs the %s league' % (car, want),
               'reads %r' % r['cls'])
            ok(bool(r['grid']) and set(r['grid']) <= pool,
               'and the field around it is that class',
               '%d cars: %s' % (len(r['grid']), ', '.join(sorted(set(r['grid'])))))

        # ---- AND THE CAR ITSELF IS NEVER ON ITS OWN GRID -----------------
        r = grid_for('CRUISER')
        ok('CRUISER' not in r['grid'],
           'a police car does not race other police cars')

        # ---- THE FALSIFICATION -------------------------------------------
        print('  -- with the declaration taken off the record')
        r = page.evaluate("""() => {
            const R = window.__road;
            const keep = R.BODY.CRUISER.raceClass;
            delete R.BODY.CRUISER.raceClass;
            R.setBody('CRUISER'); R.setMode('race'); R.restart();
            const out = { cls: R.raceClass('CRUISER'), grid: R.gridBodies() };
            R.BODY.CRUISER.raceClass = keep;
            return out;
        }""")
        ok(r['cls'] == 'super',
           'the CRUISER falls back into the supercar league - the defect, watched',
           'reads %r' % r['cls'])
        ok(bool(r['grid']) and set(r['grid']) <= SUPER,
           'and its field is supercars again',
           ', '.join(sorted(set(r['grid']))))
        back = grid_for('CRUISER')
        ok(back['cls'] == 'sports', 'and putting the declaration back restores it')

        ok(not errs, 'the run was clean', '; '.join(errs[:2]))
        ctx.close()
        b.close()

    print('  %s' % ('all checks passed' if not bad else '%d check(s) failed' % bad))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
