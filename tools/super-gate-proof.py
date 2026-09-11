#!/usr/bin/env python3
"""
SUPER GATE PROOF - why the interceptor check read zero, and that it no longer can.

    .venv/Scripts/python tools/super-gate-proof.py

A super cruiser needs the car ABOVE 150mph for four unbroken seconds. `heat-test`
asked for 160 by calling `setSpd` once every 250ms and letting go - and between two
of those pins the car is left to the world, with nothing on the throttle. So the
harness did not have a speed, it had a RANGE: three runs of this proof read
144-157, 151-158 and 140-167mph from the same 160 request, the width and the
position of it depending on how much wall-clock passed between round-trips.

The 150 the rule watches sits inside that range. `fastFor` resets to zero every
time the car crosses under it, so the four unbroken seconds were banked or not
banked by chance - which is why the check read 4 supers on one run and 0 on the
next, and why lengthening the hold changed nothing.

Three arms, and the middle one is the fix:

  OLD   the speed re-asked for four times a second, which is what the check did
  NEW   the speed HELD every frame, through `API.holdSpd`
  SLOW  held every frame but BELOW the gate - which must still send nothing

SLOW is why a green in NEW is worth anything: it shows the arrangement can still
report zero when zero is the truth, so NEW is not passing because an interceptor
turns up whatever the car does.

Exit code 0 if the proof holds, 1 otherwise.
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
TICKS = 64                      # 16 seconds at the harness's own quarter-second

INIT = r"""
window.__probe = { errors: [], road: null };
(function(){
  var real = null, wrapped = null;
  Object.defineProperty(window, 'ROAD', { configurable: true,
    get: function(){ return real ? wrapped : undefined; },
    set: function(fn){ real = fn; wrapped = function(CFG){ var a = real(CFG);
      window.__probe.road = a || (CFG && CFG.api) || null; return a; }; } });
})();
window.addEventListener('error', function(e){ window.__probe.errors.push(String(e.message)); });
"""


class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def main():
    console_utf8()
    fails = []

    def ok(c, label, detail=''):
        print(('  ok    ' if c else '  FAIL  ') + label + ('' if c else '   [' + str(detail) + ']'))
        if not c:
            fails.append(label)

    httpd = socketserver.TCPServer(('127.0.0.1', 0), functools.partial(Q, directory=str(ROOT)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.socket.getsockname()[1]
    print('super-gate-proof  .  the check read zero because the car was not going fast enough')
    with sync_playwright() as p:
        b = launch_chromium(p, headless=True)
        pg = b.new_context(viewport={'width': 480, 'height': 900},
                           has_touch=True, is_mobile=True).new_page()
        pg.add_init_script(INIT)
        boot(pg, 'http://127.0.0.1:%d/%s' % (port, GAME))
        until(pg, '!!window.__probe.road', timeout=10000)
        pg.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
        pg.click('[data-act="play"]')
        pg.wait_for_timeout(400)
        pg.click('[data-act="chase"]')      # or the whole pursuit system stands down
        pg.wait_for_timeout(200)
        pg.click('[data-act="drive"]')
        # THE COUNT-IN HOLDS THE CAR, and it wins over any hold a check asks for.
        # Wait it out rather than measuring through it.
        until(pg, '() => window.__probe.road.startLine().left <= 0', timeout=10000)
        pg.evaluate('() => window.__probe.road.setTimed(false)')

        gate = pg.evaluate('() => window.__probe.road.pursuit()')
        print('      the rule under test: above %dmph for %d unbroken seconds, at heat 3 or more'
              % (gate['superMph'], gate['superHold']))

        def arm(name, mph, hold):
            """Run one arm and report what the car DID, not what it was asked for."""
            # ---- EVERY ARM STARTS WITH AN EMPTY BANK --------------------------
            # `fastFor` is engine state and no arm resets it. The first draft of
            # this proof ran the arms back to back, so the SLOW arm inherited the
            # 15.6 seconds the fast one had banked and an interceptor arrived at
            # 140mph - the falsification arm reporting the rule broken when the
            # only broken thing was the setup. Below the gate for long enough
            # clears it, and the assert below says so rather than trusting it.
            pg.evaluate('() => { const R = window.__probe.road;'
                        ' R.holdSpd(R.MAX_SPD*0.5); }')
            pg.wait_for_timeout(700)
            pg.evaluate('() => { const R = window.__probe.road; R.copsClear();'
                        ' R.heat(5); R.earnSupers(true); }')
            banked = pg.evaluate('() => window.__probe.road.pursuit().fastFor')
            assert banked == 0, '%s started with %.2fs already banked' % (name, banked)
            v = mph / 200.0
            pg.evaluate('(v) => window.__probe.road.holdSpd(v === null ? null'
                        ' : window.__probe.road.MAX_SPD*v)', v if hold else None)
            seen = []
            for _ in range(TICKS):
                if not hold:
                    pg.evaluate('(v) => window.__probe.road.setSpd(window.__probe.road.MAX_SPD*v)', v)
                pg.evaluate('() => window.__probe.road.parkTraffic(9, 60000)')
                pg.wait_for_timeout(250)
                seen.append(pg.evaluate('() => { const s = window.__probe.road.pursuit();'
                                        ' return [s.mph, s.fastFor, s.supers]; }'))
            pg.evaluate('() => window.__probe.road.holdSpd(null)')
            mphs = [r[0] for r in seen]
            under = sum(1 for m in mphs if m <= gate['superMph'])
            peak = max(r[1] for r in seen)
            supers = seen[-1][2]
            print('      %-4s asked for %dmph: the car read %d-%dmph, under the gate on %d of %d'
                  ' samples; the longest unbroken stretch banked %.2fs of the %ds needed; %d supers'
                  % (name, mph, min(mphs), max(mphs), under, TICKS, peak, gate['superHold'], supers))
            return {'under': under, 'peak': peak, 'supers': supers,
                    'min': min(mphs), 'max': max(mphs)}

        # ---- THE DEFECT, REINTRODUCED ------------------------------------------
        old = arm('OLD', 160, hold=False)
        # ---- WHAT THIS ARM MAY AND MAY NOT ASSERT ------------------------------
        # THE SPEED IS THE FINDING, NOT THE SUPER COUNT. Sometimes the sag misses
        # a gap and four seconds do get banked, which is exactly why the check was
        # green on one run and red on the next.
        #
        # AND THE DEPTH OF THE SAG IS NOT A CONSTANT EITHER. It is however much
        # wall-clock passes between one round-trip and the next, so a loaded
        # machine sags further than an idle one: measured at 144mph minimum on a
        # busy box and 151 on a quiet one, from the same 160 request. This arm
        # asserted `min <= 150` and went red on the quiet run - a proof failing
        # because the machine was fast, which is the same class of mistake it was
        # written to expose. Do not put that assertion back.
        #
        # AND IT IS NOT A SYSTEMATIC SHORTFALL EITHER. This arm next asserted that
        # the car never REACHES what it was asked for, and that went red too: the
        # run after read 140-167mph, overshooting the request by seven. Between two
        # pins the car is simply left to the world - it sags on the flat, and a
        # slope or a shove can put it back over - so the speed is not low, it is
        # UNCONTROLLED. Three runs read 144-157, 151-158 and 140-167 from the same
        # request.
        #
        # THAT is what is true on every machine, and it is the whole finding: a
        # harness pinning a speed four times a second does not have a speed, it has
        # a range tens of mph wide - and no rule with a threshold inside that range
        # can be measured through it. Held, the same request has a spread of zero.
        asked, gate_mph = 160, gate['superMph']
        spread = old['max'] - old['min']
        ok(spread >= 5,
           'a speed asked for four times a second is a range, not a speed',
           'the car stayed within %dmph of itself, so it is under control here and'
           ' this is not the fault that was found' % spread)
        ok((old['min'] - gate_mph) < (asked - gate_mph) * 0.25,
           'and the bottom of that range eats the headroom over the gate',
           'the slowest the car went was %dmph, still %dmph clear of the %dmph gate,'
           ' so the margin has not collapsed and this is not the fault that was found'
           % (old['min'], old['min'] - gate_mph, gate_mph))

        # ---- AND THE SAME REQUEST, HELD ----------------------------------------
        new = arm('NEW', 160, hold=True)
        ok(new['under'] == 0, 'holding it keeps the car above the gate on every sample',
           'still under on %d of %d' % (new['under'], TICKS))
        ok(new['peak'] > gate['superHold'],
           'so the unbroken seconds the rule asks for are actually banked',
           'the best stretch was %.2fs' % new['peak'])
        ok(new['supers'] > 0, 'and an interceptor is dispatched', str(new))

        # ---- AND ZERO IS STILL REACHABLE ---------------------------------------
        # Without this the green above proves nothing: a rule that fired whatever
        # the car did would pass it too.
        slow = arm('SLOW', 140, hold=True)
        ok(slow['supers'] == 0, 'below the gate, held just as steadily, nothing is sent',
           'zero is no longer reachable, so the green above means nothing: %s' % slow)

        errs = pg.evaluate('() => window.__probe.errors')
        ok(not errs, 'no page errors', str(errs))
        b.close()
    httpd.shutdown()
    print(('\n%d check(s) failed' % len(fails)) if fails else '\nthe proof holds')
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
