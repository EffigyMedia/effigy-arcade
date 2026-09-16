#!/usr/bin/env python3
"""GRID ORDER - a tournament round lines you up where the championship put you.

    .venv/Scripts/python tools/grid-order-test.py
    .venv/Scripts/python tools/grid-order-test.py --selftest

RLG-274. Owner, 2026-09-16: "when you finish the first race, you start the second race in the
position that you earned in, the third race starts in your position, and the fourth race, the same.
Is this how it works?"

▶ IT WAS NOT. `buildField` strung all eleven rivals out AHEAD of the player every time and set
`place = 12`, reading nothing from the standings - so the championship was scored like a
championship and gridded like four unrelated races. The owner assumed it already worked.

▶ WHAT THIS COUNTS IS CARS BEHIND THE PLAYER AT THE LINE, which is the thing that could not happen
before and cannot be faked by a slot number. `API.grid` reports each rival's `dz` from the player, so
the check reads the road rather than the variable that is supposed to have arranged it - a check that
asserts the same number the code just set agrees with itself and proves nothing (RLG-065).

  ROUND ONE        nobody has a standing yet, so the whole field is ahead and the player is last.
  SINGLE RACE      has no standings at all and must be untouched by this.
  MID-TABLE        seeded second in the championship, the player lines up second: one car ahead.
  THE LINE HOLDS   the numbers painted on the cars still run 1 at the front to 12 at the back.
  THE HUD AGREES   the P x/12 readout opens on the slot the car is actually in.

`--selftest` seeds the same standing and asserts the check fails when the grid is forced back to
last, which is the build this replaces.

Exit code 0 if every check passed, 1 otherwise.
"""
import argparse
import functools
import http.server
import socketserver
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
from harness import console_utf8, launch_chromium, boot, reboot, until  # noqa: E402


class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


class Stuck(RuntimeError):
    pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default=str(TOOLS.parent))
    ap.add_argument('--selftest', action='store_true',
                    help='force the grid back to last, the way the old build did')
    args = ap.parse_args()
    console_utf8()
    root = Path(args.root)
    fails = []

    def ok(c, label, detail=''):
        print(('  ok    ' if c else '  FAIL  ') + label + ('' if c else '   [' + str(detail) + ']'))
        if not c:
            fails.append(label)

    httpd = socketserver.TCPServer(('127.0.0.1', 0), functools.partial(Q, directory=str(root)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.socket.getsockname()[1]
    print('grid-order  .  a tournament round grids you by the championship')
    print('      serving %s' % root)
    with sync_playwright() as p:
        b = launch_chromium(p, headless=True, args=['--mute-audio'])
        pg = b.new_context(viewport={'width': 480, 'height': 900}).new_page()
        errs = []
        pg.on('pageerror', lambda e: errs.append(str(e)))
        boot(pg, 'http://127.0.0.1:%d/games/sw/interstate.html' % port)
        pg.evaluate("""() => window.Arcade.save.merge('interstate-opts', { sports:true })""")
        reboot(pg)

        def has(act):
            return bool(pg.query_selector('#veil:not(.hidden) [data-act="%s"]' % act))

        def tap(act, wait=300):
            if not has(act):
                raise Stuck('no %s button on the screen' % act.upper())
            pg.click('#veil:not(.hidden) [data-act="%s"]' % act)
            pg.wait_for_timeout(wait)

        def to_garage():
            """stand in the garage, from wherever the last arm left us.

            EVERY ARM HERE ENDS MID-RACE, which is the state with no way out on screen: the
            veil is hidden, so there is no button to press at all. A reload is the honest way
            back - it is what the shell's own RESTART does - and it costs nothing here because
            each arm seeds the state it needs after it arrives.
            """
            for _ in range(3):
                for _ in range(8):
                    if has('drive'):
                        return
                    hit = False
                    for a in ('garage', 'play', 'quit'):
                        if has(a):
                            tap(a, 500)
                            hit = True
                            break
                    if not hit:
                        pg.wait_for_timeout(300)
                reboot(pg)
                pg.wait_for_timeout(500)
            raise Stuck('never reached the garage')

        def pick(body):
            to_garage()
            for _ in range(24):
                if pg.evaluate('() => window.__road.body()') == body:
                    return
                tap('next', 150)
            raise Stuck('never reached %s' % body)

        def set_mode(want):
            for _ in range(5):
                label = pg.evaluate("""() => { const b =
                    document.querySelector('#veil:not(.hidden) [data-act="mode"]');
                    return b ? b.textContent.trim() : ''; }""")
                if label.endswith(want):
                    return
                tap('mode', 200)
            raise Stuck('MODE never reached %s' % want)

        def read_grid():
            """the road as it actually is at the line, plus what the HUD says"""
            # AN EMPTY GRID IS A MODE, NOT A TIMEOUT. `buildField` only runs for
            # `mode === 'race'`, so a walk that did not actually reach a race reads as a
            # field that never appeared - two very different failures behind one message.
            if not until(pg, '() => window.__road.grid().length > 0', timeout=8000,
                         required=False):
                raise Stuck('no field on the road: mode=%s, tournament=%s'
                            % (pg.evaluate('() => window.__road.mode()'),
                               pg.evaluate('() => JSON.stringify(window.__road.tourState())')))
            g = pg.evaluate('() => window.__road.grid()')
            s = pg.evaluate('() => window.__road.gridSlot()')
            ahead = len([r for r in g if r['dz'] > 0])
            behind = len([r for r in g if r['dz'] < 0])
            return g, s, ahead, behind

        try:
            # ---- ROUND ONE: nobody has a standing, so nothing changes -----------------
            pick('ROADSTER')
            set_mode('TOURNAMENT')
            tap('drive', 1800)
            g, s, ahead, behind = read_grid()
            print('      ROUND ONE       %d ahead, %d behind, slot %d, HUD P%d'
                  % (ahead, behind, s['slot'], s['place']))
            ok(behind == 0 and ahead == len(g),
               'round one still puts the whole field ahead of you',
               '%d ahead, %d behind' % (ahead, behind))

            # ---- A SINGLE RACE IS UNTOUCHED -------------------------------------------
            to_garage()
            set_mode('SINGLE RACE')
            tap('drive', 1800)
            g, s, ahead, behind = read_grid()
            print('      SINGLE RACE     %d ahead, %d behind, slot %d, HUD P%d'
                  % (ahead, behind, s['slot'], s['place']))
            ok(behind == 0 and s['slot'] == s['last'],
               'a single race has no standings and grids you last',
               '%d behind, slot %d of %d' % (behind, s['slot'], s['last']))

            # ---- MID-TABLE: seeded second, you line up second --------------------------
            # THE STANDING IS SEEDED, NOT DRIVEN. Winning a real round takes a full race
            # and the question here is what the NEXT grid does with a standing, not
            # whether the player can earn one - race-test already drives a finish.
            to_garage()
            set_mode('TOURNAMENT')
            pg.evaluate("""(pin) => {
              const R = window.__road;
              /* round two, and a points total that puts the player second overall: one
                 rival above them and the rest below. `tourScore` is not called - this is
                 the state a finished round would have left. */
              R.seedTour({ round:1, pts:18, field:[25,15,12,10,8,6,4,2,1,0,0] });
              /* the falsifier: the old build gridded last whatever the standings said */
              R.gridPin(pin);
            }""", bool(args.selftest))
            tap('drive', 1800)
            g, s, ahead, behind = read_grid()
            print('      MID-TABLE       standing P%d -> slot %d, %d ahead, %d behind, HUD P%d'
                  % (s['standing'], s['slot'], ahead, behind, s['place']))
            ok(s['standing'] == 2, 'the seeded standing is second overall',
               'standing P%s' % s['standing'])
            ok(ahead == 1 and behind == len(g) - 1,
               'lying second grids you second, with one car ahead and the rest behind',
               '%d ahead, %d behind' % (ahead, behind))
            ok(s['place'] == 2, 'and the HUD opens on P2, not P12', 'HUD P%s' % s['place'])

            # ---- THE LINE IS STILL A LINE ---------------------------------------------
            # The numbers painted on the cars run 1 at the front to 12 at the back, and
            # the player holds one of the twelve. A grid that put two cars on #4 would
            # look right in a count of dz and be wrong on the road.
            nums = sorted(r['num'] for r in g)
            expect = [n for n in range(1, len(g) + 2) if n != s['slot'] + 1]
            ok(nums == expect, 'every car still carries its own number, and one is yours',
               'numbers %s, expected %s' % (nums, expect))
            # and they run in order along the road: the car furthest up has the lowest
            by_road = [r['num'] for r in sorted(g, key=lambda r: -r['dz'])]
            ok(by_road == sorted(by_road),
               'and the numbers run in order along the road, lowest at the front',
               'along the road: %s' % by_road)
        except Stuck as e:
            ok(False, 'the walk completed', str(e))

        ok(not errs, 'no page errors', errs[0][:160] if errs else '')
        b.close()
    httpd.shutdown()
    print()
    if args.selftest:
        if fails:
            print('the grid was forced back to last and this file reported it')
            return 0
        print('SELFTEST FAILED: the grid was forced to last and nothing noticed')
        return 1
    if fails:
        print('FAILED: ' + '; '.join(fails))
        return 1
    print('a tournament round grids you by the championship')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
