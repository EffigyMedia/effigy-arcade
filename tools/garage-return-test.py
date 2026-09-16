#!/usr/bin/env python3
"""GARAGE RETURN - leaving a run by any door puts you back on the car you drove.

    .venv/Scripts/python tools/garage-return-test.py
    .venv/Scripts/python tools/garage-return-test.py --root <an older checkout> --expect-fail

RLG-251. Owner, 2026-09-15: "When you return to the garage from any mode, it should return you to the
car you last used."

▶ UNFINISHED, AND IT IS A MEASURING TOOL RATHER THAN A GATE. The PAUSE > QUIT arm runs and passes;
the three after it do not get that far, because each door leaves the player on a different screen and
`to_garage` cannot yet find its way from all of them - QUIT lands in the garage, the end screen has
its own buttons, and MAIN MENU goes to the title. Finish the navigation before trusting any result
from this file, and do not add it to the gate until every arm runs.

IT MEASURES BEFORE IT ASSERTS, which is what the ruling asked for: the fragment names three suspects
(the reward screen, `enforceCarRules`, a stale save) and says to find out which doors actually lose
the car before changing anything. Each door is walked with the real buttons and the car the garage
lands on is read from `API.body()`.

  PAUSE > QUIT     drive a test drive, pause, QUIT, and look at the garage.
  END > CHANGE CAR the run ends on the clock, then CHANGE CAR off the end screen.
  END > MAIN MENU  the same, by the other door, then PLAY back into the garage.
  RELOAD           and the car survives a reload, which is the save rather than the menu.

The car used is not the one a fresh save opens on (RLG-250 opens on the first of the production
class), so a door that quietly resets cannot pass by accident.

WHAT THIS CANNOT SAY. INTERCEPT and the tournament are not walked here - they need a police car and a
field - and a reward screen only appears when something is actually won.

Exit code 0 if every check passed (or, with --expect-fail, if one failed), 1 otherwise.
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default=str(TOOLS.parent))
    ap.add_argument('--expect-fail', action='store_true')
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
        boot(pg, 'http://127.0.0.1:%d/games/sw/interstate.html' % port)

        def tap(act, wait=250):
            sel = '#veil:not(.hidden) [data-act="%s"]' % act
            if pg.query_selector(sel):
                pg.click(sel)
                pg.wait_for_timeout(wait)
                return True
            return False

        def to_garage():
            """stand in the garage, from wherever the last door left us.

            QUIT lands IN the garage, not on the title, so waiting for PLAY here timed the
            whole file out after the first arm.
            """
            for _ in range(6):
                if pg.query_selector('#veil:not(.hidden) [data-act="drive"]'):
                    return
                if tap('play', 500):
                    continue
                pg.wait_for_timeout(400)
            pg.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=8000)

        def pick_car():
            """move off the car a fresh save opens on, and say which car we settled on"""
            for _ in range(3):
                tap('next', 150)
            return pg.evaluate('() => window.__road.body()')

        def drive_a_bit():
            tap('drive', 1500)
            until(pg, '() => window.__road.startLine().left <= 0', timeout=10000)
            pg.evaluate('() => { const R = window.__road; R.setTimed(false);'
                        ' R.setSpd(0.5 * R.MAX_SPD); }')
            pg.wait_for_timeout(800)

        # ---- PAUSE > QUIT ----------------------------------------------------------------
        to_garage()
        car = pick_car()
        drive_a_bit()
        pg.click('#pauseBtn') if pg.query_selector('#pauseBtn') else pg.keyboard.press('Escape')
        pg.wait_for_timeout(400)
        tap('quit', 900)
        after = pg.evaluate('() => window.__road.body()')
        print('      PAUSE > QUIT      drove %s, garage shows %s' % (car, after))
        ok(after == car, 'quitting from pause returns to the car driven', '%s -> %s' % (car, after))

        # ---- END > CHANGE CAR ------------------------------------------------------------
        to_garage()
        car = pick_car()
        drive_a_bit()
        pg.evaluate('() => window.__road.setClock(0.2)')     # let the clock run out
        pg.wait_for_timeout(2500)
        tap('garage', 900)
        after = pg.evaluate('() => window.__road.body()')
        print('      END > CHANGE CAR  drove %s, garage shows %s' % (car, after))
        ok(after == car, 'CHANGE CAR off the end screen returns to the car driven',
           '%s -> %s' % (car, after))

        # ---- END > MAIN MENU -------------------------------------------------------------
        to_garage()
        car = pick_car()
        drive_a_bit()
        pg.evaluate('() => window.__road.setClock(0.2)')
        pg.wait_for_timeout(2500)
        tap('menu', 900)
        to_garage()
        after = pg.evaluate('() => window.__road.body()')
        print('      END > MAIN MENU   drove %s, garage shows %s' % (car, after))
        ok(after == car, 'and so does going out to the main menu and back in',
           '%s -> %s' % (car, after))

        # ---- RELOAD ----------------------------------------------------------------------
        reboot(pg)
        to_garage()
        after = pg.evaluate('() => window.__road.body()')
        print('      RELOAD            garage shows %s' % after)
        ok(after == car, 'and the car survives a reload', '%s -> %s' % (car, after))

        ok(not errs, 'no page errors', errs[0][:120] if errs else '')
        b.close()
    httpd.shutdown()
    print()
    if args.expect_fail:
        print('expected at least one failure: %s' % ('got %d' % len(fails) if fails else 'got NONE'))
        return 0 if fails else 1
    if fails:
        print('FAILED: ' + '; '.join(fails))
        return 1
    print('every door back to the garage keeps the car')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
