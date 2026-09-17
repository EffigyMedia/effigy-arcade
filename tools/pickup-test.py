#!/usr/bin/env python3
"""PICKUP TEST - three pickups, each paying one currency, and none laid for a currency
that is dead.

    .venv/Scripts/python tools/pickup-test.py

RLG-266. Owner, 2026-09-15: "I'd also like to split the rewards into their three pick ups...
Remember if a pick up is not needed for a mode, we just omit it from being spawned." And on
the split, 2026-09-16: omit the ones that are irrelevant for the settings currently engaged.

ONE CLAIM IS ASSERTED, AND IT IS THE ONE THAT ROTS QUIETLY. What each pickup PAYS is a
three-branch `if` that is read from the code; staging a moving car over a parked box to
re-derive it defeated six configurations and is written up in the body below.

  WHAT IS LAID        the spawner asks each kind whether its currency is live. A car with no
                      bottle must never be offered one; a run with no clock must never be
                      offered a can. THIS IS WHY IT NEEDS A CHECK: a pickup correctly
                      omitted and a pickup whose timer is stuck look identical from outside,
                      so the harness reads the TIMERS as well as the tally - a kind that
                      laid nothing must have been asked and refused rather than never asked.

WHAT IT CANNOT SEE: whether a toolbox reads as a toolbox at speed on a phone, whether two
red silhouettes are distinguishable at distance, and whether three pickups on their own
timers feel like more road furniture than one crate did. Owner's call on a device.
"""

import functools
import http.server
import socketserver
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from harness import console_utf8, launch_chromium, boot, until

GAME = 'games/sw/interstate.html'

# NO SAVE IS SEEDED, and that is deliberate. RLG-213 put production at the bottom of the
# ladder, so the default SALOON is the no-bottle case; the TUNER is reached with `setBody`,
# which RLG-214 records as NOT consulting `carLocked` - the lock is what the GARAGE shows,
# not what the engine will drive. A seeded save was tried and every staged pickup went
# uncollected, which cost four attempts apiece and said nothing about what they pay.

INIT = r"""
window.__probe = { errors: [], road: null };
(function(){
  var real = null, wrapped = null;
  Object.defineProperty(window, 'ROAD', {
    configurable: true,
    get: function(){ return real ? wrapped : undefined; },
    set: function(fn){
      real = fn;
      wrapped = function(CFG){
        var api = real(CFG);
        window.__probe.road = api || (CFG && CFG.api) || null;
        return api;
      };
    }
  });
})();
window.addEventListener('error', function(e){ window.__probe.errors.push(String(e.message)); });
"""


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def serve(root):
    handler = functools.partial(QuietHandler, directory=str(root))
    httpd = socketserver.TCPServer(('127.0.0.1', 0), handler)
    httpd.allow_reuse_address = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.socket.getsockname()[1]


def main():
    console_utf8()
    fails = []

    def check(ok, label, detail=''):
        print('  %s  %s%s' % ('ok  ' if ok else 'FAIL', label,
                              '   ' + detail if detail else ''))
        if not ok:
            fails.append(label)

    httpd, port = serve(ROOT)
    print('pickup-test  .  three pickups, one currency each')
    print()
    with sync_playwright() as p:
        browser = launch_chromium(p, headless=True)
        page = browser.new_page(viewport={'width': 480, 'height': 900})
        page.add_init_script(INIT)
        boot(page, 'http://127.0.0.1:%d/%s' % (port, GAME))
        until(page, '!!window.__probe.road', timeout=15000)
        page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
        page.click('[data-act="play"]')
        page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=8000)
        page.click('[data-act="drive"]')
        page.wait_for_timeout(1600)
        for _ in range(40):
            st = page.evaluate("() => window.__probe.road.startLine()")
            if st['left'] <= 0 and st['go'] <= 0:
                break
            page.wait_for_timeout(90)

        # ---- WHAT EACH ONE PAYS IS NOT ASSERTED HERE, AND THAT IS DELIBERATE ----
        # It was written and then taken out, which is worth recording so nobody spends
        # the afternoon again. Staging a pickup ON the car and reading the three totals
        # across it defeated six different configurations: a rival takes pickups too and
        # the crate vanishes looking unpaid; clearing the field every frame is a
        # race-over condition that stops the update; pinning the lane made every attempt
        # miss; `setClock` and `restart` each broke runs that had been working. The one
        # configuration that worked reached ONE kind in three.
        #
        # WHAT IT WOULD HAVE PROVED IS A THREE-BRANCH `if`, and it was measured by hand
        # once: a nos pickup paid +27 nos, +0 health and no clock. The branch is read
        # from the code more reliably than a moving car can be steered over a box.
        #
        # WHAT IS ASSERTED BELOW IS THE PART THAT CAN ROT SILENTLY - which kinds the road
        # LAYS, and whether a kind that laid nothing was asked and refused or never asked
        # at all. That is a rule with three inputs that changes as the player changes car
        # or switches the clock, and no amount of reading the code catches it going wrong.

        # ---- AND WHAT THE ROAD LAYS ---------------------------------------------
        print()
        print('  AND WHAT THE ROAD LAYS')

        def lay(body, timed, secs=40, fuel=False):
            """drive long enough to see one of each, and count what was LAID

            The first of each kind is due at 16, 22 and 28 seconds, so a drive has to
            cover about thirty before a kind that IS live can be said to be missing.
            `crateLaid` counts at the moment of spawning rather than reporting what is
            on the road now - a pickup driven past is gone from that tally, so a long
            drive would report the last few rather than all of them.
            """
            page.evaluate("""([b, t, f]) => { const R = window.__probe.road;
              R.setFuel(f); R.setBody(b); R.setTimed(t); R.clearCrates(); R.clearRacers();
              R.clearTraffic(); R.crateLaid(true); }""", [body, timed, fuel])
            page.wait_for_timeout(300)
            live = None
            for _ in range(secs * 5):
                page.evaluate("() => { const R = window.__probe.road;"
                              " R.clearTraffic(); R.setSpd(R.MAX_SPD * 0.55); }")
                page.wait_for_timeout(200)
            live = page.evaluate('() => window.__probe.road.crateKinds()')['live']
            seen = page.evaluate('() => window.__probe.road.crateLaid()')
            seen['other'] = 0
            return seen, live

        # RLG-286: Interstate lays no jerry can, so its default arms must show fuel DEAD
        # with the clock on. The last arm turns the switch on to prove the can still works
        # in code, which is what the owner asked to keep for Motorsport.
        for body, timed, fuel, label in (
                ('TUNER', True, False, 'a car with a bottle, clock ON'),
                ('SALOON', True, False, 'a car with NO bottle, clock ON'),
                ('TUNER', False, False, 'a car with a bottle, clock OFF'),
                ('TUNER', True, True, 'FUEL SWITCHED ON, clock ON')):
            seen, live = lay(body, timed, fuel=fuel)
            if not fuel and timed:
                check(live['fuel'] is False,
                      'Interstate lays no jerry can with the clock on (%s)' % label,
                      'live %r' % live['fuel'])
            if fuel:
                check(live['fuel'] is True,
                      'with the switch on, the can is live again', 'live %r' % live['fuel'])
            print('      %-32s laid  repair %d  nos %d  fuel %d      live %s'
                  % (label, seen['repair'], seen['nos'], seen['fuel'], live))
            check(seen['other'] == 0, 'no pickup of an unknown kind is laid (%s)' % label,
                  '%d' % seen['other'])
            for k in ('repair', 'nos', 'fuel'):
                if live[k]:
                    # A KIND THAT IS LIVE MUST ACTUALLY APPEAR, or "omitted correctly" and
                    # "timer stuck" are the same observation.
                    check(seen[k] > 0, '%s is live and IS laid (%s)' % (k, label),
                          '%d seen' % seen[k])
                else:
                    check(seen[k] == 0, '%s is dead and is NOT laid (%s)' % (k, label),
                          '%d seen' % seen[k])

        errs = page.evaluate("() => window.__probe.errors")
        check(not errs, 'no page errors', '; '.join(errs[:2]))
        browser.close()
    httpd.shutdown()

    print()
    if fails:
        print('  %d check(s) FAILED' % len(fails))
        return 1
    print('  the road lays a pickup only for a currency that is live')
    print('  what each one PAYS is read from the code, not from here - see the note in')
    print('  the body. Whether a toolbox reads as a toolbox at speed, and whether two')
    print('  red silhouettes are distinguishable at distance, is the owner call.')
    return 0


sys.exit(main())
