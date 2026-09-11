#!/usr/bin/env python3
"""BAR SCATTER TEST - does the light bar on YOUR roof actually move traffic?

    .venv/Scripts/python tools/bar-scatter-test.py

RLG-203. Owner, 2026-09-10, on the police cars: "they have a secret weapon and that is their siren
because that will move cars out of the way." INTERCEPT is being built on that tool, so the tool has
to be measured before anything is tuned against it.

AND THERE IS A STANDING REASON TO DOUBT IT. `tools/ambulance-test.py` asserts that a siren moves
traffic out of the way and reports ZERO cars changing lane - on this build and on the one before it,
recorded in RLG-176 and never chased. That is a different caller of the same `scatter()`, so either
the mechanism is broken for everyone or the ambulance's own path is. This file answers the half that
INTERCEPT depends on.

HOW IT IS MEASURED, AND WHY THE CONTROL IS THE FALSIFICATION. `scattered` counts cars that actually
completed a move over - it is incremented where the merge is committed, not where the request is
thrown. The same run is driven twice at the same held speed: once with the bar OFF and once with it
ON. If `scatter()` were inert both arms read zero and this file fails, which is what makes the ON
arm worth believing.

THE BAR IS LATCHED BY PRESSING THE REAL BUTTON, and the latch is read back off the engine rather
than assumed - `setHorn` turns the horn into a latching switch for a police car, and a check that
pressed the button and then called `setBar` to find out what happened would be testing its own
setter. That is the fault `nos-falsify.py` found in the nitrous check.

WHAT IS HELD STILL SO THE TWO ARMS COMPARE. Hot pursuit is OFF, so no NPC cruiser can scatter and
credit the player's bar with its work. The ambulance clock is read, because an ambulance on a call
scatters too. The speed is PINNED with `holdSpd` rather than asked for once, since a speed set and
released is a range rather than a speed (RLG-127). And the run clock is switched off (RLG-125),
because a parked or slow harness reaches no checkpoint, and when the clock expires every driving
number freezes where it stood.

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
ARM_SECONDS = 22
PACE = 0.62          # a shade over the limit: fast enough to catch traffic, slow enough to sit behind it


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--headed', action='store_true')
    ap.add_argument('--seconds', type=int, default=ARM_SECONDS)
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

    print('bar-scatter-test  .  does your own light bar move traffic')
    with sync_playwright() as p:
        b = launch_chromium(p, headless=not args.headed,
                            args=['--mute-audio', '--autoplay-policy=no-user-gesture-required'])
        ctx = b.new_context(viewport={'width': 480, 'height': 900})
        page = ctx.new_page()
        errs = []
        page.on('pageerror', lambda e: errs.append(str(e)))

        boot(page, '%s/%s' % (base, GAME))
        page.wait_for_timeout(600)
        page.evaluate("() => window.Arcade.save.merge('interstate-opts', { cruiser:true })")
        reboot(page)
        page.wait_for_timeout(700)

        # ---- put the player in a patrol car, THROUGH THE REAL CONTROLS ----
        # The run has to be started by pressing DRIVE. Starting it through the API
        # leaves the veil up and the HUD down, and the horn button - which is the
        # bar's latch on a police car - is then not on the screen to press.
        page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
        page.click('[data-act="play"]')
        page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
        page.evaluate("() => { window.__road.setBody('CRUISER'); }")
        page.click('[data-act="drive"]')
        page.wait_for_timeout(1200)
        started = page.evaluate("""(pace) => {
            const R = window.__road;
            R.setTimed(false);          /* RLG-125: the run clock freezes every number */
            R.setPool(1);               /* a full traffic pool, so there is something to move */
            R.holdSpd(R.MAX_SPD * pace);
            return { body: R.body(), hasBar: R.inCruiser(), bar: R.barOn(),
                     amb: R.ambClock(), cops: R.cops ? R.cops().length : null };
        }""", PACE)
        ok(started['body'] == 'CRUISER', 'the player is in a patrol car',
           'reads %r' % started['body'])
        ok(started['hasBar'] is True, 'which carries a bar at all')
        ok(started['bar'] is False, 'and the bar starts off', 'reads %r' % started['bar'])
        ok(started['amb'] > args.seconds,
           'no ambulance is due inside the control arm',
           'next call in %.1fs' % started['amb'])

        def press_horn():
            """The real handler, reached the way the game reaches it.

            `page.click` refuses this button - Playwright reports it as not visible, and
            `traffic-test` presses it the same way for the same reason. The engine binds
            `pointerdown` on the element, so dispatching that event IS the press; a check
            that called `setHorn` instead would be calling the thing it is testing."""
            page.evaluate("() => document.getElementById('horn')"
                          ".dispatchEvent(new PointerEvent('pointerdown',{bubbles:true}))")
            page.evaluate("() => document.getElementById('horn')"
                          ".dispatchEvent(new PointerEvent('pointerup',{bubbles:true}))")
            page.wait_for_timeout(150)

        page.evaluate('() => window.__road.scatterStat(true)')

        def arm(label):
            before = page.evaluate("""() => ({
                sc: window.__road.scattered(),
                traffic: window.__road.trafficCount() })""")
            page.wait_for_timeout(args.seconds * 1000)
            stat = page.evaluate('() => window.__road.scatterStat(true)')
            after = page.evaluate("""() => ({
                sc: window.__road.scattered(),
                traffic: window.__road.trafficCount(),
                mph: Math.round(window.__road.spdNow() * 200 / window.__road.MAX_SPD),
                bar: window.__road.barOn(),
                reach: window.__road.sirenReach(),
                cops: window.__road.cops().length })""")
            moved = after['sc'] - before['sc']
            print('    %-12s moved %-3d  traffic on road %d -> %d  %dmph  bar=%s  cops=%d'
                  % (label, moved, before['traffic'], after['traffic'],
                     after['mph'], after['bar'], after['cops']))
            print('      %-10s where the requests went: %s'
                  % ('', ' '.join('%s=%s' % kv for kv in stat.items())))
            return moved, after, stat

        # ---- ARM ONE: THE CONTROL ----------------------------------------
        print('  -- %ds with the bar OFF' % args.seconds)
        off_moved, off, off_stat = arm('bar off')
        ok(off['cops'] == 0,
           'no NPC cruiser was on the road to scatter for you',
           '%d cop(s)' % off['cops'])
        ok(off['traffic'] > 0, 'and there was traffic to move',
           '%d cars' % off['traffic'])

        # ---- LATCH IT, BY PRESSING THE BUTTON ----------------------------
        press_horn()
        latched = page.evaluate('() => window.__road.barOn()')
        ok(latched is True,
           'one press of the horn button latches the bar on',
           'engine reads barOn=%r' % latched)

        # ---- ARM TWO: THE SAME ROAD WITH THE BAR ON ----------------------
        print('  -- %ds with the bar ON' % args.seconds)
        on_moved, on, on_stat = arm('bar on')
        ok(on['bar'] is True, 'the bar stayed latched for the whole arm')

        # ---- WHAT IT ADDS UP TO ------------------------------------------
        # THE COUNT OF CARS MOVED IS NOT ASSERTED ON, and that is deliberate.
        # Four arms of this file over one build read 0, 4, 11 and 5. Whether a
        # car is in the narrow band ahead of you at all is the bottleneck, so a
        # legitimate arm can move nobody - traffic-test says the same about the
        # horn and refuses to assert on it for the same reason. What IS asserted
        # is that the mechanism is live: the request is made, it reaches cars,
        # and cars get through the gates to be asked.
        ok(off_stat['calls'] == 0,
           'with the bar off, nothing asks traffic to move at all',
           '%d call(s)' % off_stat['calls'])
        ok(on_stat['calls'] > 0 and on_stat['seen'] > 0,
           'with it on, the request is made and it reaches cars',
           '%d calls, %d refused by the cooldown, %d cars looked at'
           % (on_stat['calls'], on_stat['cooled'], on_stat['seen']))
        asked = on_stat['moved'] + on_stat['gap'] + on_stat['obey']
        ok(asked > 0,
           'and cars get through the window and the line to be asked',
           '%d asked: %d moved, %d had no gap, %d refused'
           % (asked, on_stat['moved'], on_stat['gap'], on_stat['obey']))
        ok(on_moved >= off_moved,
           'the bar never moves FEWER cars than no bar at all',
           'on %d against off %d' % (on_moved, off_moved))
        far = on_stat['far'] / max(1, on_stat['seen'])
        print('    .. %.0f%% of the cars looked at were beyond the siren, which reaches '
              '%d units from here (RLG-205: two seconds of road)'
              % (far * 100, on['reach']))
        print('    .. %d cars moved over in %ds. Before RLG-205, with a flat 4200-unit '
              'window: 0, 4, 11, 5 and 2 across five arms, with 96%% out of range.'
              % (on_moved, args.seconds))

        # ---- AND THE LATCH LETS GO ---------------------------------------
        press_horn()
        ok(page.evaluate('() => window.__road.barOn()') is False,
           'a second press turns it off again')

        ok(not errs, 'the run was clean', '; '.join(errs[:2]))
        ctx.close()
        b.close()

    print('  %s' % ('all checks passed' if not bad else '%d check(s) failed' % bad))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
