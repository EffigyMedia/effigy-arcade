#!/usr/bin/env python3
"""GARAGE RETURN - leaving a run by any door puts you back on the car you drove.

    .venv/Scripts/python tools/garage-return-test.py
    .venv/Scripts/python tools/garage-return-test.py --selftest

RLG-251. Owner, 2026-09-15: "When you return to the garage from any mode, it should return you to the
car you last used."

▶ THE FIRST VERSION OF THIS FILE PASSED WITHOUT DRIVING ANYWHERE, and that is the reason every helper
below raises. `pick_car` stepped three times off the car the garage opens on and landed on ROADSTER,
which is LOCKED on a fresh save; a locked card carries only the two arrows and BACK (RLG-223), so
there was no DRIVE button, `tap` returned False without saying so, and the arm then read the same car
back out of a garage it had never left. It reported `ok  quitting from pause returns to the car
driven`. NOTHING HAPPENED AND IT SCORED. So: `tap` raises when the button it wants is not on the
screen, `pick_car` will only settle on a car in `playableBodies`, and `drive_a_bit` asserts the run
actually started before anything is measured.

▶ AND THE DOOR THE RULING NAMES FIRST DOES NOT EXIST. There is no quit-to-garage from pause. Pausing
is the SHELL's (`arcade.js`), and its menu offers RESUME, RESTART and EXIT TO ARCADE - RESTART is
`location.reload()` and EXIT leaves the machine for the launcher. The road's own `data-act="quit"`
lives on the TITLE screen and on the tournament card, neither of which is a paused run. So the doors
out of an Interstate run are the three on the end card plus the shell's RESTART, and those are what
is walked here.

  END > CHANGE CAR   the run ends on the clock, then CHANGE CAR off the end screen.
  END > MAIN MENU    the same, by the other door, then PLAY back into the garage.
  PAUSE > RESTART    the shell's pause button, then RESTART - the only pause door that comes back.

The car driven is never the car a fresh save opens on, so a door that quietly resets cannot pass by
accident. `--selftest` proves that: it drives NOTHING and asserts the file refuses to score.

WHAT THIS CANNOT SAY. INTERCEPT and the tournament are not walked here - they need a police car and a
field - and the reward screen (`showUnlock`, which loads the won car into `optBody` to draw it) only
appears when something is actually won, so the fragment's first suspect is still unmeasured.

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
from harness import console_utf8, launch_chromium, boot, until  # noqa: E402


class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


class DoorShut(RuntimeError):
    """a button the walk needs is not on the screen - the arm never happened"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default=str(TOOLS.parent))
    ap.add_argument('--selftest', action='store_true',
                    help='prove the file refuses to score an arm that did not happen')
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
    print('garage-return  .  every door back to the garage keeps the car')
    print('      serving %s' % root)
    with sync_playwright() as p:
        b = launch_chromium(p, headless=True, args=['--mute-audio'])
        pg = b.new_context(viewport={'width': 480, 'height': 900}).new_page()
        errs = []
        pg.on('pageerror', lambda e: errs.append(str(e)))
        url = 'http://127.0.0.1:%d/games/sw/interstate.html' % port
        boot(pg, url)

        def screen():
            """what the veil is offering right now, for an error that can be read"""
            return pg.evaluate("""() => {
              const el = document.getElementById('veil');
              if(!el) return 'no veil on the page';
              if(el.classList.contains('hidden')) return 'the veil is hidden - a run is on screen';
              const acts = [...el.querySelectorAll('[data-act]')].map(x => x.dataset.act);
              return 'veil offers ' + (acts.join(', ') || 'nothing');
            }""")

        def has(act):
            return bool(pg.query_selector('#veil:not(.hidden) [data-act="%s"]' % act))

        def tap(act, wait=250):
            """press one of the road's buttons, and RAISE if it is not there.

            The silent version of this is what let the first arm pass without driving.
            """
            if not has(act):
                raise DoorShut('no %s button to press - %s' % (act.upper(), screen()))
            pg.click('#veil:not(.hidden) [data-act="%s"]' % act)
            pg.wait_for_timeout(wait)

        def to_garage():
            """stand in the garage, from wherever the last door left us.

            Each door lands somewhere different - CHANGE CAR lands IN the garage, MAIN MENU on the
            title, a reload on the title - so this reads the screen rather than assuming one.
            """
            for _ in range(8):
                if has('drive') or has('next'):
                    return
                if has('play'):
                    tap('play', 500)
                    continue
                pg.wait_for_timeout(400)
            raise DoorShut('never reached the garage - %s' % screen())

        def pick_car():
            """settle on a car that can actually be DRIVEN and is not the one the garage opened on.

            OWNERSHIP IS `playableBodies` AND NOTHING ELSE - garage membership lists locked cars as
            silhouettes, and a card's name is no good either because a SECRET class is absent from
            the garage entirely and `setBody` falls back to a ROADSTER. That mistake is recorded
            twice already.
            """
            to_garage()
            opened_on = pg.evaluate('() => window.__road.body()')
            playable = pg.evaluate('() => window.__road.playableBodies()')
            want = [k for k in playable if k != opened_on]
            if not want:
                raise DoorShut('only one car is playable (%s), so no door can be tested against a '
                               'car the garage does not already open on' % opened_on)
            for _ in range(len(playable) + 14):
                tap('next', 180)
                if pg.evaluate('() => window.__road.body()') in want:
                    break
            car = pg.evaluate('() => window.__road.body()')
            if car not in want:
                raise DoorShut('walked the whole fleet and never landed on a playable car other '
                               'than %s' % opened_on)
            if not has('drive'):
                raise DoorShut('%s reports as playable and its garage card has no DRIVE button - '
                               '%s' % (car, screen()))
            return car

        def drive_a_bit():
            """start a run, and prove it started before anything is measured"""
            tap('drive', 1500)
            until(pg, '() => window.__road.startLine().left <= 0', timeout=10000)
            pg.evaluate('() => { const R = window.__road; R.setSpd(0.5 * R.MAX_SPD); }')
            pg.wait_for_timeout(900)
            moved = pg.evaluate('() => window.__road.spdNow()')
            if not moved or moved <= 0:
                raise DoorShut('the car never moved after DRIVE - %s' % screen())
            return moved

        def end_the_run():
            """run the clock out and wait for the end card.

            TWO THINGS END A RUN AND BOTH ARE NEEDED. The clock has to be turned back ON, because
            `setClock` on a run that does not count seconds does nothing at all (RLG-125) - and an
            empty clock is not by itself the end of the run. The engine waits for the car to come to
            REST as well (`clock <= 0 && spd < MAX_SPD*0.004`), so a car left rolling at half speed
            sits on an expired clock forever. The speed is written down every pass because it is one
            of the values the world winds back.
            """
            pg.evaluate('() => { window.__road.setTimed(true); window.__road.setClock(0.2); }')
            for _ in range(60):
                pg.evaluate('() => window.__road.setSpd(0)')
                if pg.evaluate('() => { const el = document.getElementById("veil");'
                               ' return !!el && !el.classList.contains("hidden")'
                               ' && !!el.querySelector(\'[data-act="again"]\'); }'):
                    return
                pg.wait_for_timeout(250)
            raise DoorShut('the run never ended on the clock - %s' % screen())

        def arm(label, walk):
            """drive a car, leave by one door, and say which car the garage came back on"""
            car = None
            try:
                car = pick_car()
                drive_a_bit()
                walk()
                to_garage()
                after = pg.evaluate('() => window.__road.body()')
            except DoorShut as e:
                print('      %-17s BLKD  %s' % (label, e))
                ok(False, '%s returns to the car driven' % label, 'the walk never happened: %s' % e)
                return
            print('      %-17s drove %s, garage shows %s' % (label, car, after))
            ok(after == car, '%s returns to the car driven' % label, '%s -> %s' % (car, after))

        if args.selftest:
            # THE FALSIFIER: ask for a door that is not on any screen and watch the file refuse to
            # score it. The first version of this harness returned False here and passed anyway.
            print()
            print('      selftest  .  an arm whose door is missing must not score')
            arm('MADE-UP DOOR', lambda: tap('there-is-no-such-button'))
            b.close()
            httpd.shutdown()
            print()
            if fails:
                print('the file refused to score a walk that did not happen')
                return 0
            print('SELFTEST FAILED: a missing door scored anyway')
            return 1

        arm('END > CHANGE CAR', lambda: (end_the_run(), tap('garage', 900)))
        arm('END > MAIN MENU', lambda: (end_the_run(), tap('menu', 900)))

        def pause_restart():
            pg.click('.ark-bar .ark-btn')
            pg.wait_for_timeout(400)
            btn = pg.query_selector('.ark-veil.on [data-a="restart"]')
            if not btn:
                raise DoorShut('the shell pause menu did not open, or has no RESTART')
            btn.click()
            until(pg, '() => !!window.__road', timeout=30000)
            pg.wait_for_timeout(600)

        arm('PAUSE > RESTART', pause_restart)

        ok(not errs, 'no page errors', errs[0][:120] if errs else '')
        b.close()
    httpd.shutdown()
    print()
    if fails:
        print('FAILED: ' + '; '.join(fails))
        return 1
    print('every door back to the garage keeps the car')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
