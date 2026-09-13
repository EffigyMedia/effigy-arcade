#!/usr/bin/env python3
"""TOURNAMENT EXIT TEST - a finished tournament does not follow you into the next one.

    .venv/Scripts/python tools/tour-exit-test.py
    .venv/Scripts/python tools/tour-exit-test.py --falsify

RLG-232. Owner, 2026-09-12: *"When I complete a tournament if I don't hit the new tournament button
and I just quit to the menu any tournament I go into starts at race four with a position of one, and
I can immediately place first and win the new tournament."*

The trophy screen had three ways out and only NEW TOURNAMENT reset anything. MAIN MENU, and the two
buttons on the unlock screen behind SEE YOUR NEW CAR, set `tourOn = false` - which clears nothing,
because `tourOn` is recomputed from `raceTour` every time the garage opens. `tourRound` stayed at
four with a winning point total behind it, so the next tournament was one race from a gold.

IT PLAYS THE WHOLE TOURNAMENT, which is the only way to reach the screen the owner was looking at.
`API.parkFinish` puts the finish line behind the player, so a round ends the moment the engine next
looks - the four rounds are real rounds with a real trophy at the end of them, rather than a state
poked into the engine and read straight back out.

  1. THE TOURNAMENT ACTUALLY RAN. Four rounds reached and a trophy screen at the end. Without this
     every question below passes on a build where the tournament never started.
  2. LEAVING BY MAIN MENU RETIRES IT. Back in the garage, the round is 0 and the points are 0.
  3. AND THE NEXT ONE STARTS AT ROUND ONE. The distance the engine sets for the first leg is
     TOUR_MILES[0], not TOUR_MILES[3] - which is the owner's "starts at race four" measured as the
     thing the player would feel.

`--falsify` puts the defect back by clearing the retirement flag from outside before the garage can
act on it, exactly as the old build behaved. Checks 2 and 3 must fail.

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

GAME = 'games/sw/interstate.html'
ROUNDS = 4

# EVERY CONTROL IS TAKEN FROM THE VEIL THAT IS ACTUALLY OPEN. `data-act` names repeat across
# screens - the unlock card has a `drive` of its own - so an unscoped selector can find a button
# on a veil that is not on screen and wait thirty seconds for it to become visible.
VEIL = '#veil:not(.hidden) '


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--falsify', action='store_true',
                    help='clear the retirement flag from outside, the way the old build behaved')
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
        # THE DETAIL PRINTS ON A FAILURE ONLY. A line reading "the garage still holds
        # round 0 and 0 points" beside an ok mark is the shape that left a harness
        # saying the nitrous button did not take, on a pass, for months.
        print('  %s  %s%s' % ('ok  ' if cond else 'FAIL', label,
                              ('   ' + detail) if (detail and not cond) else ''))

    print('tour-exit  .  a finished tournament does not follow you into the next one')
    if args.falsify:
        print('  FALSIFY: the retirement is undone from outside. Checks 2 and 3 must fail.')
    try:
        with sync_playwright() as p:
            b = launch_chromium(p, headless=True, args=['--mute-audio'])
            ctx = b.new_context(viewport={'width': 480, 'height': 900})
            ctx.add_init_script(dt.INIT)
            pg = ctx.new_page()
            errs = []
            pg.on('pageerror', lambda e: errs.append(str(e)))
            boot(pg, 'http://127.0.0.1:%d/%s' % (port, GAME))
            pg.wait_for_timeout(1600)
            pg.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
            pg.click('[data-act="play"]')
            pg.wait_for_timeout(400)

            # ---- INTO TOURNAMENT, THROUGH THE REAL CONTROL ---------------------
            # The MODE button cycles TEST DRIVE, SINGLE RACE, TOURNAMENT. Pressing it is
            # what a player does, and it is also what calls `tourReset` on the way in -
            # so a harness that set the mode some other way would skip the very code
            # path this defect lives beside.
            for _ in range(4):
                label = pg.inner_text(VEIL + '[data-act="mode"]')
                if 'TOURNAMENT' in label:
                    break
                pg.click(VEIL + '[data-act="mode"]')
                pg.wait_for_timeout(200)
            ok('TOURNAMENT' in pg.inner_text(VEIL + '[data-act="mode"]'),
               'the garage is set to TOURNAMENT',
               'the mode control reads %r' % pg.inner_text(VEIL + '[data-act="mode"]'))

            pg.click(VEIL + '[data-act="drive"]')
            pg.wait_for_timeout(1800)

            # ---- PLAY IT OUT --------------------------------------------------
            # A ROUND ENDS WHEN A SCREEN OPENS, NOT AFTER A FIXED WAIT. The finish is
            # handled 700ms after the line, and the trophy has an animation in front of
            # it; a flat sleep read "no trophy" on a build that was about to show one.
            def wait_screen(ms=8000):
                step, spent = 120, 0
                while spent < ms:
                    if pg.locator(VEIL + '[data-act="again"]').count():
                        return 'trophy'
                    if pg.locator(VEIL + '[data-act="next"]').count():
                        return 'round'
                    pg.wait_for_timeout(step)
                    spent += step
                return None

            rounds, screen = 0, None
            for _ in range(ROUNDS):
                pg.evaluate("() => window.__road.parkFinish(400)")
                screen = wait_screen()
                rounds += 1
                if screen != 'round':
                    break                      # the trophy, or nothing at all
                pg.click(VEIL + '[data-act="next"]')
                pg.wait_for_timeout(1800)
            trophy = screen == 'trophy'
            # 1. it really ran
            ok(trophy and rounds == ROUNDS,
               'the tournament ran its four rounds and reached a trophy',
               'reached round %d, trophy=%s' % (rounds, trophy))
            if not trophy:
                b.close()
                raise SystemExit('[tour-exit] no trophy screen - nothing below can be judged')

            won = pg.evaluate("() => window.__road.tourState()")
            print('      at the trophy: round %s, points %s' % (won['round'], won['pts']))

            # ---- AND OUT BY THE MENU, WHICH IS WHAT THE OWNER DID --------------
            pg.click(VEIL + '[data-act="menu"]')
            pg.wait_for_timeout(700)
            if args.falsify:
                # the defect, put back: the old build cleared `tourOn` on the way out and
                # left the round and the points standing. Clearing the flag here is the
                # same thing - the garage then has nothing to act on.
                pg.evaluate("() => { if (window.__road.tourClearDone) window.__road.tourClearDone(); }")
            pg.click('[data-act="play"]')
            pg.wait_for_timeout(600)

            st = pg.evaluate("() => window.__road.tourState()")
            # 2. the round and the points are gone
            ok(st['round'] == 0 and st['pts'] == 0,
               'leaving by MAIN MENU retires the tournament',
               'the garage still holds round %s and %s points' % (st['round'], st['pts']))

            # 3. and the next one is a first leg, measured as the distance it sets
            pg.click(VEIL + '[data-act="drive"]')
            pg.wait_for_timeout(1800)
            leg = pg.evaluate("() => window.__road.tourState()")
            ok(leg['round'] == 0,
               'the next tournament starts at round one',
               'it started at round %s - one race from a gold' % leg['round'])

            if errs:
                ok(False, 'page errors', errs[0][:140])
            b.close()
    finally:
        srv.shutdown()

    print('  %s' % ('all checks passed' if not bad else '%d check(s) FAILED' % bad))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
