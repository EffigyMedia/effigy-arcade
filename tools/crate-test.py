#!/usr/bin/env python3
"""
CRATE TEST - a pickup pays what this car can actually use, and says what it paid.

    .venv/Scripts/python tools/crate-test.py

RLG-107. Owner, 2026-08-31: "for cars with no NOS, picking up the pickup says '+0 NOS', but that
should be omitted if they don't have NOS."

THE AWARD WAS WRONG BEFORE THE TEXT WAS, and that is why this checks the car and not just the label.
`nos` was raised in four places without one of them asking whether the car has a bottle - the repair
crate, threading a roadblock gap, putting a cruiser out, and the trickle that refills it over a run.
So a SEMI carried a charge it could never spend, and the crate announced it. Hiding the label would
have left the charge there, so what is asserted is that the CAR did not gain it.

AND THE THIRD CASE, WHICH IS THE OWNER'S DECISION OF 2026-08-31. A car with no bottle at full health
drove over a crate and got NOTHING - the exact problem the bottle top-up was added to solve, left
unsolved for half the fleet. It is paid in SECONDS now, which is the currency Interstate is played
in and the one a checkpoint already pays out.

IT PARKS ITS OWN CRATE. Crates spawn out of sight and sit on the SHOULDER at 0.86 to 1.02 of the
road, so reaching one by driving means measuring the spawner and the verge instead of the pickup.
`API.parkCrate` puts one on the REAL crates array with the fields the spawner gives it, in front of
the car, so the real pickup test runs on it - the same reason `parkTraffic` exists.

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

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from harness import console_utf8, launch_chromium

GAME = 'games/sw/interstate.html'

# A car with a bottle and two without. The garage locks the utility cars behind distance, but
# `setBody` is the same seam every other fleet measurement uses and goes straight to the body.
WITH_BOTTLE = 'ROADSTER'
WITHOUT = ['SEMI', 'VAN']

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
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.socket.getsockname()[1]


class Results:
    def __init__(self):
        self.fails = []

    def check(self, ok, label, detail=''):
        print(('  ok    ' if ok else '  FAIL  ') + label + ('' if ok else '   [' + str(detail) + ']'))
        if not ok:
            self.fails.append(label)


def take_crate(page, body, dmg, timed=True):
    """Set the car up, park a crate in front of it, drive over it, and report what happened.

    The speed is held every frame while it closes on the crate: the pickup is a distance test and a
    car left to coast covers a different distance each time.
    """
    page.evaluate("""(a) => { const R = window.__probe.road;
        R.setBody(a.body); R.setLane(0); R.setTarget(0); R.setDmg(a.dmg);
        R.setWet(0); R.setSnow(0); R.setPool(0); R.setTimed(a.timed);
        R.clearTraffic(); R.parkCrate(900); }""",
                  {'body': body, 'dmg': dmg, 'timed': timed})
    before = page.evaluate("""() => { const R = window.__probe.road;
        return { nos: R.nos(), clock: R.clock, dmg: R.dmg, has: R.hasNos(),
                 taken: R.cratesTaken() }; }""")
    # ---- IT DRIVES THE WHOLE WAY AND WATCHES WHILE IT DOES -------------------------
    # Two earlier versions of this raced, in opposite directions. The first STOPPED as
    # soon as `lastFx()` said something - and the case where a crate pays NOTHING never
    # produces a flash, so it relied on the loop timing out, and a flash still alive from
    # the previous case ended it early instead, before the car had reached its crate. It
    # failed about one run in five. The second drove the full two seconds and then read the
    # flash, by which time it had EXPIRED - a flash lives 1.2 seconds and the drive is 2.4.
    #
    # So it drives the whole way every time and SAMPLES AS IT GOES, keeping the first thing
    # said and the gauges as they were when it was said. Neither the flash nor the gauge
    # light is a state that persists; both have to be caught while they are up.
    seen_fx, seen_gauges = '', {'clock': '', 'nos': ''}
    for _ in range(40):
        page.evaluate("() => { const R = window.__probe.road;"
                      " R.setSpd(R.MAX_SPD * 0.5); R.setTarget(0); }")
        page.wait_for_timeout(60)
        now = page.evaluate("() => { const R = window.__probe.road;"
                            " return { fx: R.lastFx(), g: R.gauges() }; }")
        if now['fx'] and not seen_fx:
            seen_fx = now['fx']
        if 'gain' in now['g']['clock'] and 'gain' not in seen_gauges['clock']:
            seen_gauges['clock'] = now['g']['clock']
        if 'gain' in now['g']['nos'] and 'gain' not in seen_gauges['nos']:
            seen_gauges['nos'] = now['g']['nos']
    after = page.evaluate("""() => { const R = window.__probe.road;
        return { nos: R.nos(), clock: R.clock, dmg: R.dmg,
                 left: R.cratesLeft(), taken: R.cratesTaken() }; }""")
    after['fx'] = seen_fx
    after['gauges'] = seen_gauges
    return before, after


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--headed', action='store_true')
    args = ap.parse_args()
    console_utf8()
    res = Results()
    httpd, port = serve(ROOT)
    print('crate-test  .  a pickup pays what this car can use, and says what it paid')

    with sync_playwright() as p:
        browser = launch_chromium(p, headless=not args.headed)
        page = browser.new_context(viewport={'width': 480, 'height': 900},
                                   has_touch=True, is_mobile=True).new_page()
        page.add_init_script(INIT)
        page.goto('http://127.0.0.1:%d/%s' % (port, GAME), wait_until='load')
        page.wait_for_function('!!window.__probe.road', timeout=10000)
        page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
        page.click('[data-act="play"]')
        page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
        page.click('[data-act="drive"]')
        page.wait_for_timeout(3600)          # past the count-in

        # ---- 1. THE FLEET AGREES ABOUT WHICH CARS HAVE A BOTTLE ------------------
        # If it did not, everything below would be measuring the wrong cars and would say so
        # in a way that looked like a pass.
        has = page.evaluate("""(list) => { const R = window.__probe.road; const out = {};
            for(const k of list){ R.setBody(k); out[k] = R.hasNos(); } return out; }""",
                            [WITH_BOTTLE] + WITHOUT)
        print('      bottles: %s' % has)
        res.check(has.get(WITH_BOTTLE) is True,
                  '%s has a bottle, so it is a fair control' % WITH_BOTTLE, has)
        res.check(all(has.get(k) is False for k in WITHOUT),
                  'and %s have none, so they are the cars the report is about' % ', '.join(WITHOUT),
                  has)

        # ---- 2. A CAR WITH A BOTTLE STILL GETS ONE FILLED ------------------------
        before, after = take_crate(page, WITH_BOTTLE, 0)
        print('      %-8s full health: %r   nos %d -> %d, clock %.1f -> %.1f'
              % (WITH_BOTTLE, after['fx'], before['nos'], after['nos'],
                 before['clock'], after['clock']))
        res.check(bool(after['fx']), 'the crate was actually picked up', 'nothing was said')
        res.check(after['nos'] > before['nos'],
                  'a car with a bottle still has it filled',
                  'nos went %d to %d' % (before['nos'], after['nos']))
        res.check('NOS' in after['fx'], 'and is told so', after['fx'])

        # ---- 3. A CAR WITH NO BOTTLE IS NOT GIVEN ONE, NOR TOLD IT WAS -----------
        for body in WITHOUT:
            before, after = take_crate(page, body, 0)
            print('      %-8s full health: %r   nos %d -> %d, clock %.1f -> %.1f'
                  % (body, after['fx'], before['nos'], after['nos'],
                     before['clock'], after['clock']))
            res.check(bool(after['fx']), '%s picked the crate up' % body, 'nothing was said')
            # THE CAR, NOT THE LABEL. This is the half that hiding the text would have missed.
            # It asserts the car GAINED nothing rather than that it holds nothing: `setBody` is
            # a test seam that goes straight to the body and does not reset the run, so a bottle
            # filled on the control car above is still sitting there. What a run actually starts
            # with is checked separately below, through the same restart a player gets.
            res.check(after['nos'] == before['nos'],
                      '%s is given no nitrous at all' % body,
                      'nos went %d to %d' % (before['nos'], after['nos']))
            res.check('NOS' not in after['fx'],
                      'and is not told about a bottle it has not got',
                      after['fx'])
            # AND IT IS PAID IN THE GAME'S OWN CURRENCY (owner, 2026-08-31)
            gained = after['clock'] - before['clock']
            res.check(gained > 1,
                      'and a car with nothing to gain is paid in seconds instead',
                      'the clock went %.2f to %.2f, so the crate did nothing at all'
                      % (before['clock'], after['clock']))
            res.check('SEC' in after['fx'],
                      'and the flash says so, in the words a checkpoint uses',
                      after['fx'])

        # ---- 4. AND A DAMAGED ONE IS REPAIRED, STILL WITHOUT A BOTTLE ------------
        # The branch that must not mention nitrous is the one that has something else to say.
        before, after = take_crate(page, WITHOUT[0], 60)
        print('      %-8s damaged:     %r   dmg %d -> %d, clock %.1f -> %.1f'
              % (WITHOUT[0], after['fx'], before['dmg'], after['dmg'],
                 before['clock'], after['clock']))
        res.check(after['dmg'] < before['dmg'],
                  'a damaged car with no bottle is repaired',
                  'dmg went %d to %d' % (before['dmg'], after['dmg']))
        res.check('HEALTH' in after['fx'] and 'NOS' not in after['fx'],
                  'and told about the repair, and not about a bottle it has not got',
                  after['fx'])
        # AND IT IS PAID IN SECONDS TOO, because the clock is running and RLG-125 makes each
        # award independent rather than a fallback. RLG-107 paid seconds ONLY when nothing else
        # applied, and this check asserted the opposite of what it now asserts - kept and turned
        # around rather than deleted, because the change of mind is the interesting part.
        res.check(after['clock'] - before['clock'] > 1,
                  'and paid in seconds as well, because every award is its own',
                  'the clock went %.2f to %.2f' % (before['clock'], after['clock']))
        res.check('SEC' in after['fx'] and 'HEALTH' in after['fx'],
                  'and told about both', after['fx'])
        # ONE SHAPE. Every clause is a PLUS of a named amount - the repair used to read
        # `REPAIRED -25%`, which was the only clause of three that counted DOWN, so the line
        # said "minus, plus, plus" for three things that are all gains.
        res.check(after['fx'].count('+') == len([w for w in after['fx'].split('  ') if w]),
                  'and every clause of the line is a gain, in one shape',
                  after['fx'])

        # ---- 4b. AND NO SECONDS IN A MODE THAT DOES NOT COUNT THEM (RLG-125) ----
        # Owner, 2026-08-31: "time isn't even always needed - if we're not in time mode, time
        # is worthless." `clockRuns()` is `mode === 'race' || timedRun`, so on a TEST DRIVE
        # with TIMED off the clock does not count at all - and RLG-107 paid seconds into it
        # anyway, as the reward for a car with nothing else to gain. A reward paid in a
        # currency the mode does not use is the invisible reward that ruling was about.
        page.evaluate("() => window.__probe.road.setTimed(false)")
        runs = page.evaluate("() => window.__probe.road.clockRuns()")
        res.check(runs is False, 'the clock can be turned off for the check',
                  'clockRuns() still says %r' % runs)
        before, after = take_crate(page, WITH_BOTTLE, 60, timed=False)
        print('      %-8s untimed:     %r   clock %.1f -> %.1f'
              % (WITH_BOTTLE, after['fx'], before['clock'], after['clock']))
        res.check(abs(after['clock'] - before['clock']) < 0.5,
                  'a crate pays no seconds when the clock is not running',
                  'the clock moved %.2f in a mode that does not count it'
                  % (after['clock'] - before['clock']))
        res.check('SEC' not in after['fx'],
                  'and does not claim to have paid any', after['fx'])
        res.check('HEALTH' in after['fx'],
                  'while still paying what the mode does use', after['fx'])
        page.evaluate("() => window.__probe.road.setTimed(true)")

        # ---- 4c. A CRATE THAT PAYS NOTHING IS STILL TAKEN (RLG-126) -------------
        # Owner, 2026-08-31: "leaving a crate on the side of the road for later doesn't make
        # any sense cause you'll never see it again. You should just collect it and get
        # nothing." The version before this left it standing, on the argument that the player
        # might want it later - true of a circuit, false of an endless road where you pass a
        # thing once.
        before, after = take_crate(page, WITHOUT[0], 0, timed=False)
        print('      %-8s nothing to give: %r   crates left on the road: %d'
              % (WITHOUT[0], after['fx'], after['left']))
        # COUNTING WHAT IS LEFT CANNOT ANSWER THIS. A crate the car drives past is spliced
        # out 1,500 units later either way, so `cratesLeft` reads 0 whether it was collected
        # or merely passed - and this check passed with the defect reintroduced until the
        # engine started counting the crates it actually TAKES.
        res.check(after['taken'] == before['taken'] + 1,
                  'a crate with nothing to give is collected anyway',
                  'the collected count went %d to %d, so it was driven past rather than taken'
                  % (before['taken'], after['taken']))
        res.check(not after['fx'].strip(),
                  'and says nothing, because there is nothing to say', after['fx'])
        page.evaluate("() => window.__probe.road.setTimed(true)")

        # ---- 4d. AND THE GAUGES LIGHT UP WHERE THE AWARD WENT (RLG-126) ---------
        # A line in the middle of the screen is read once and gone; the clock and the bottle
        # are what the player watches for the rest of the run. This reads the CLASS the
        # element is actually carrying rather than inferring it from the state that should
        # have set it - the gauge lighting is the thing under test, not the award.
        # DRAINED FIRST, or there is no charge to gain and nothing to light. The cases above
        # this one fill the bottle, and a gauge cannot be seen receiving what it already has.
        page.evaluate("() => window.__probe.road.setNos(20)")
        before, after = take_crate(page, WITH_BOTTLE, 60, timed=True)
        print('      %-8s gauges after a crate: clock %r, bottle %r'
              % (WITH_BOTTLE, after['gauges']['clock'], after['gauges']['nos']))
        res.check('gain' in after['gauges']['clock'],
                  'the clock lights when seconds go into it',
                  'its class was %r' % after['gauges']['clock'])
        res.check('gain' in after['gauges']['nos'],
                  'and the bottle lights when the charge does',
                  'its class was %r' % after['gauges']['nos'])

        # ---- 5. AND THE BOTTLE DOES NOT TRICKLE INTO A CAR THAT HAS NOT GOT ONE --
        # The deepest instance of the same fault, and the one no pickup would ever show: the
        # bottle refills on its own over a run, and that ran for every car in the fleet.
        for body, want in ((WITH_BOTTLE, True), (WITHOUT[0], False)):
            # DRAINED FIRST. The checks above this one fill the bottle, and a full bottle
            # cannot be watched filling - the first version of this read 100 to 100 and
            # called it a failure to trickle.
            page.evaluate("(k) => { const R = window.__probe.road; R.setBody(k); R.setNos(20); }",
                          body)
            n0 = page.evaluate("() => window.__probe.road.nos()")
            page.wait_for_timeout(2500)
            n1 = page.evaluate("() => window.__probe.road.nos()")
            print('      %-8s bottle over 2.5s: %d -> %d' % (body, n0, n1))
            res.check((n1 > n0) == want,
                      'the bottle trickles back %s' % ('on a car that has one' if want
                                                       else 'into no car that has not'),
                      '%s went %d to %d' % (body, n0, n1))

        # ---- 6. AND A RUN STARTED IN ONE BEGINS WITH AN EMPTY BOTTLE ------------
        # Through `restart`, which is the same path RETRY and DRIVE both take, so this is what
        # a player gets rather than what a test seam leaves behind. A car that cannot spend a
        # charge should not be holding one.
        for body, want_empty in ((WITHOUT[0], True), (WITH_BOTTLE, False)):
            page.evaluate("(k) => { const R = window.__probe.road; R.setBody(k); R.restart(); }",
                          body)
            page.wait_for_timeout(300)
            n = page.evaluate("() => window.__probe.road.nos()")
            print('      %-8s starts a run holding %d' % (body, n))
            res.check((n == 0) == want_empty,
                      'a run in %s starts with %s' % (body, 'nothing in the bottle' if want_empty
                                                      else 'a charge to spend'),
                      'it started with %d' % n)

        errs = page.evaluate('() => window.__probe.errors')
        res.check(not errs, 'no page errors', errs)
        browser.close()

    httpd.shutdown()
    print('')
    if res.fails:
        print('FAILED: ' + '; '.join(res.fails))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
