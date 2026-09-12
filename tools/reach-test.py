#!/usr/bin/env python3
"""REACH - how far does a timed test drive go WITH NOBODY STEERING? A FLOOR, not a
ceiling.

    .venv/Scripts/python tools/reach-test.py

READ THIS FIRST. THIS HARNESS CANNOT ANSWER "HOW FAR CAN A RUN GO", AND IT WAS
WRITTEN BELIEVING THAT IT COULD. Its first results were reported to the owner as
proof that the 25- and 50-mile unlocks were unreachable. The owner had driven over
100 miles in one run, repeatedly. The measurement was of a driver, not of a game -
see RLG-215, where the finding is withdrawn in full.

WHAT IT ACTUALLY MEASURES. A car with the throttle held down and THE WHEEL NEVER
TOUCHED. That matters because of two things it therefore never does:

    CRATES ARE PARKED ON THE SHOULDER, at x = +/- 0.86 to 1.02, and the engine's
    own comment says "taking one means leaving the road". Driving straight down
    the middle collects a crate only by accident - zero to four in a whole run,
    measured. A player steers to them. A crate pays CRATE_SECS (10s) and arrives
    on a TIMER, `nextCrateT = rnd(20, 34)`, so a driver who takes all of them
    earns 0.29 to 0.50 seconds a second and one who takes none earns nothing.

    AND IT NEVER REACHES THE SPEED THE CAR HAS. Peak speeds of 98 to 156mph were
    measured in a fleet whose top car declares 194, headless, at whatever frame
    rate the machine chose. Checkpoint credit is v/360 seconds a second, so speed
    is the other half of the budget.

THE BUDGET, WHICH IS THE THING TO REASON WITH RATHER THAN THIS HARNESS:

    net = v/360 + crate - 1     seconds of clock, per second of driving

    194mph, every crate, fast end   +0.04   the clock CLIMBS and the run is endless
    194mph, every crate, mean       -0.09   about 11 minutes, ~35 miles
    150mph, every crate, mean       -0.21   about 4.7 minutes, ~12 miles
    150mph, no crates               -0.58   about 1.7 minutes, ~4 miles

The last row is what this harness reports. The first is what the game is played at.

SO USE IT FOR WHAT IT IS. It is a floor, and a floor is worth having: it is the
same code path, it ends a run properly, and a change that moves THIS number has
moved something real. It is not evidence about what a player can reach, and any
sentence that uses it that way is the error this file exists to stop repeating.

A FALSIFIER DOES NOT MAKE A DRIVER REPRESENTATIVE, which is the lesson underneath
all of it. The one below proves this harness can report a run twice past its own
measured ceiling with the clock climbing - true, and it says nothing at all about
whether the car was being driven the way a player drives it. `driver_limits` is the
check that was missing: every distance is now printed with FLOOR ONLY beside it, and
the reason, whenever the peak speed fell short of what the car declares or no crate
was taken. It warns rather than failing, because a floor is worth measuring - what
must not happen again is a floor being quoted as a ceiling.

THE FALSIFIER, WHICH RUNS FIRST. A harness that reports "the run ended at 6 miles"
is worthless if it cannot report 60. So the first arm PINS the speed far above any
car's top end with `API.holdSpd`: the car then covers two miles in well under twenty
seconds, the clock GAINS, and the same code path must report a large distance.

A RUN THAT NEVER STARTED IS BLKD AND NOT A ZERO. The first version of this harness
reported "SALOON 0.00 miles" and "STALLION 0.00 miles", which reads as a finding and
was a defect: both cars are LOCKED, the garage would not hand them over, and the run
never began. A car whose peak speed is zero did not drive, so it is blocked and its
distance is not printed at all. `API.dbgTraffic` opens the production and utility
classes without writing an unlock flag, which is what lets the SALOON be measured;
there is no equivalent for the racing classes, so the supercars are out of reach from
here and are not asked for.

AND IT REPEATS, BECAUSE CRATES ARE THE FREE VARIABLE even for a driver that only
collects them by accident. One run of this decides nothing.

Exit code 0 if the falsifier cleared its bar, 1 otherwise. THE PER-CAR RESULTS ARE A
MEASUREMENT AND NOT A PASS OR A FAIL, and they are a FLOOR - they are printed with
the driver's own limits beside them so that they cannot be quoted as a ceiling.
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
from harness import console_utf8, launch_chromium, boot, until

GAME = 'games/sw/interstate.html'

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

# DRIVE UNTIL THE CLOCK ENDS THE RUN, or until the wall-clock cap. It samples every
# frame and reports the LAST row plus the lowest clock it saw - a run that ended is a
# run whose clock reached zero, and saying so is how the caller tells the two outcomes
# apart without guessing from the distance.
DRIVE_OUT = """(capSecs) => {
  const R = window.__probe.road;
  return new Promise((done) => {
    const t0 = performance.now();
    let low = 1e9, peak = 0;
    const tick = () => {
      const st = R.startLine();
      if(st.clock < low) low = st.clock;
      if(st.spd > peak) peak = st.spd;
      const wall = (performance.now() - t0) / 1000;
      if(st.clock <= 0.05 || wall >= capSecs){
        done({ dist: st.dist, pos: st.pos, clock: st.clock, low: low, peak: peak,
               wall: wall, ended: st.clock <= 0.05,
               crates: R.cratesTaken ? R.cratesTaken() : null });
      } else requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  });
}"""


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def serve(root):
    handler = functools.partial(QuietHandler, directory=str(root))
    httpd = socketserver.TCPServer(('127.0.0.1', 0), handler)
    httpd.allow_reuse_address = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.socket.getsockname()[1]


def open_game(page, port):
    boot(page, 'http://127.0.0.1:%d/%s' % (port, GAME))
    until(page, '!!window.__probe.road', timeout=10000)
    page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
    page.click('[data-act="play"]')
    page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)


def out_body(r):
    """what the engine says it is driving, or a plain admission that it does not say"""
    return r.get('body') or 'not reported by the engine'


DECLARED = {}      # body -> the top speed the engine says it has, filled by `read_declared`


def read_declared(browser, port):
    """ASK THE ENGINE what each car's top end is, instead of keeping a copy of it.

    This was a hand-written table of seven numbers, under a docstring admitting it was
    "copied from BODY and will go stale if a car is retuned". IT WENT STALE THE FIRST
    TIME A CAR WAS RETUNED: RLG-217 moved the SALOON from 112mph to 124 and the HATCH
    to 110, and this file would have gone on printing the old pair - as a shortfall
    against a ceiling no longer there.

    The numbers are print-only and fail nothing, which is exactly why nobody would have
    caught it. `MAX_SPD` and every body's `vmax` are both on the probe already.
    """
    page = browser.new_page(viewport={'width': 480, 'height': 900})
    page.add_init_script(INIT)
    page.add_init_script(SEED)
    open_game(page, port)
    got = page.evaluate("""() => {
      const R = window.__probe.road, out = {};
      for (const k of Object.keys(R.BODY)) {
        if (R.BODY[k].npc) continue;
        out[k] = Math.round(R.MAX_SPD * R.BODY[k].vmax * (200 / R.MAX_SPD));
      }
      return out;
    }""")
    page.close()
    DECLARED.clear()
    DECLARED.update(got)
    return got


def declared_mph(body):
    """the top speed the ENGINE claims for this car. None if it was never read."""
    return DECLARED.get(body)


def driver_limits(r, mph, declared):
    """SAY HOW THE DRIVER FELL SHORT, on the same line as the number it produced.

    THIS IS THE CHECK THAT WAS MISSING and it is the whole lesson of RLG-215. The
    falsifier below proves the harness can report a LONG run; nothing proved that the
    car was being driven the way a player drives it, and it was not. A distance from
    a driver that never reached the car's speed and never took a crate is a FLOOR, and
    printing it bare is what let it be quoted as a ceiling.

    It warns rather than failing, because a floor is still worth measuring - what must
    not happen is a floor being read as something else.
    """
    out = []
    crates = r.get('crates')
    # A CRATE ARRIVES ON A TIMER, `nextCrateT = rnd(20, 34)`, so the number that were
    # PUT OUT during the run is the wall clock over the mean of 27 seconds. Comparing
    # what was taken against what appeared is the check; comparing against zero is not,
    # and a run that took 1 of about 3 passed the first version of this.
    if crates is not None and r.get('wall'):
        offered = r['wall'] / 27.0
        if offered >= 1 and crates < offered * 0.75:
            out.append('FLOOR ONLY - took %d crate(s) of about %.0f put out in %.0fs.'
                       ' They sit on the shoulder and this driver never steers;'
                       ' each one is 10s of clock' % (crates, offered, r['wall']))
    if declared and mph < declared * 0.9:
        out.append('FLOOR ONLY - peak %d mph against the %d this car declares,'
                   ' and checkpoint credit is v/360 a second' % (mph, declared))
    return out


# THE UNLOCK FLAGS, WRITTEN BEFORE THE GAME BOOTS. `API.dbgTraffic` is NOT enough, and
# that is a defect in the debug switch rather than in this harness: it widens `openBy`,
# which decides what the garage LISTS, and `carLocked` - which is what the DRIVE button
# guards on - never consults it. So a SALOON appeared in the garage, could be selected,
# and the DRIVE button returned without starting anything. The run then sat on the menu
# with the clock frozen at 60.0, and the first version of this harness reported that as
# zero miles driven.
#
# Writing the real flag into the save slot is what the game itself does at 25 and 50
# miles, so this drives the car the same way a player who earned it would.
SEED = r"""
try {
  localStorage.setItem('effigyarcade.save.v1.interstate-opts',
    JSON.stringify({ production: true, utility: true, traffic: true }));
} catch (e) {}
"""


def run_arm(browser, port, body, cap, hold=None):
    page = browser.new_page(viewport={'width': 480, 'height': 900})
    page.add_init_script(INIT)
    page.add_init_script(SEED)
    open_game(page, port)
    # every arm drives with the TIMER ON, because that is the only state the unlock
    # branch is ever asked in
    page.evaluate("() => window.__probe.road.setTimed(true)")
    page.evaluate("(b) => window.__probe.road.setBody(b)", body)
    page.click('[data-act="drive"]')
    page.wait_for_timeout(400)
    if hold is not None:
        page.evaluate("(v) => window.__probe.road.holdSpd(v)", hold)
    page.dispatch_event('#gas', 'pointerdown')
    out = page.evaluate(DRIVE_OUT, cap)
    page.dispatch_event('#gas', 'pointerup')
    # WHAT THE CAR ACTUALLY IS, read back rather than assumed. A `setBody` that did
    # not take leaves the previous car on the road and the arm is then labelled with
    # a body it never drove.
    out['body'] = page.evaluate("() => window.__probe.road.bodyKey "
                                "? window.__probe.road.bodyKey() : null")
    out['state'] = page.evaluate("() => window.__probe.road.startLine()")
    out['mode'] = page.evaluate("() => window.__probe.road.mode "
                                "? window.__probe.road.mode() : null")
    out['errors'] = page.evaluate("() => window.__probe.errors.slice(0, 3)")
    page.close()
    return out


def selftest():
    """PROVE THE DRIVER CHECK BOTH FIRES AND STAYS SILENT, without a browser.

    A warning that can never be silent is not a check, it is a banner - and a driver
    check that only catches a crate count of ZERO is what let a run that took one of
    about three go by unmarked. So this drives `driver_limits` with rows that are
    fabricated rather than measured, which is the point: the arithmetic is what is
    under test here, and a real run cannot be made to order.
    """
    cases = [
        # (label, row, mph, declared, how many warnings are expected)
        ('the run this harness actually produces - no crates, slow',
         {'crates': 0, 'wall': 103.0}, 113, 160, 2),
        ('one crate of about four, at the full declared speed - the case that slipped',
         {'crates': 1, 'wall': 103.0}, 146, 146, 1),
        ('a representative driver - most crates taken, at speed',
         {'crates': 4, 'wall': 103.0}, 146, 146, 0),
        ('too short for a crate to have been put out at all',
         {'crates': 0, 'wall': 12.0}, 146, 146, 0),
    ]
    bad = 0
    print('  SELFTEST - does the driver check fire, and can it stay silent?')
    for label, row, mph, declared, want in cases:
        got = driver_limits(row, mph, declared)
        ok = len(got) == want
        if not ok:
            bad += 1
        print(('  ok    ' if ok else '  FAIL  ') + '%d warning(s), %s' % (want, label))
        for line in got:
            print('            ' + line)
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--selftest', action='store_true',
                    help='check the driver check itself, with no browser')
    ap.add_argument('--headed', action='store_true')
    ap.add_argument('--cap', type=float, default=180.0,
                    help='wall-clock seconds before an arm is abandoned')
    ap.add_argument('--no-falsifier', action='store_true',
                    help='skip the falsifier - for a cheap diagnostic run only')
    ap.add_argument('--runs', type=int, default=3,
                    help='how many times each car is driven - crates are scattered')
    ap.add_argument('--bodies', default='SALOON,TUNER,MUSCLE')
    args = ap.parse_args()
    console_utf8()
    if args.selftest:
        return 1 if selftest() else 0
    httpd, port = serve(ROOT)
    fails = []
    print('reach  .  a FLOOR for a timed test drive, with nobody steering')
    with sync_playwright() as p:
        browser = launch_chromium(p, headless=not args.headed)

        # ---- THE FALSIFIER, FIRST -------------------------------------------------
        # 766,650 world units is 10,000mph on the engine's own scale (15,333 is 200mph).
        # At that speed two miles take 0.72 seconds and pay 20, so the clock climbs and
        # the run cannot end - which is the only way this harness is able to report a
        # distance in the tens of miles. If it cannot, nothing below is readable.
        #
        # THE BAR IS 12 MILES AND IT IS NOT 100, WHICH IS WORTH SAYING PLAINLY.
        # The engine cannot be driven at an arbitrary speed: pinned at 1,000mph it
        # covers ground at about 630mph and pinned at 10,000mph it covers ground at
        # about 630mph again, because the frame rate rather than `spd` is what limits
        # it once the road is being consumed that fast. So a 100-mile arm would take
        # ten minutes of wall clock to prove a point that 20 miles already makes.
        #
        # WHAT IT PROVES: the odometer and the run-end detection both scale to twice
        # the largest timed distance measured below, and the clock CLIMBS instead of
        # draining - so a short answer there is the game and not this harness.
        # WHAT IT DOES NOT PROVE: that a 100-mile run would be reported. Nothing here
        # can show that, and the 100-mile case is settled by arithmetic instead - a
        # checkpoint pays 20s every 2 miles, so breaking even needs 360mph and the
        # fastest car in the fleet declares 194.
        print()
        print('  FALSIFIER - can this harness report a LONG run at all?')
        if args.no_falsifier:
            print('      SKIPPED by --no-falsifier - this run is a diagnostic and')
            print('      NOTHING BELOW IT IS EVIDENCE. It exits 1 to say so.')
            fails.append('the falsifier was skipped, so this run proves nothing')
        else:
            f = run_arm(browser, port, 'TUNER', 90.0, hold=76665)
            print('      TUNER with the speed pinned at 1,000mph, timer ON')
            print('        %.2f miles in %.0fs of wall clock, clock 60.0 -> %.1f (lowest %.1f)'
                  % (f['dist'], f['wall'], f['clock'], f['low']))
            ok = f['dist'] > 12 and not f['ended']
            print(('  ok    ' if ok else '  FAIL  ')
                  + 'the harness reports a run twice past the timed ceiling, and the clock CLIMBS')
            print('        and it says NOTHING about whether this driver is representative.')
            print('        It is not: read the budget at the top of this file.')
            if not ok:
                fails.append('the falsifier did not clear 12 miles'
                             ' - every number below is unreadable')

        # ---- AND NOW THE REAL QUESTION --------------------------------------------
        print()
        # read the declared top speeds off the engine before the loop, so the shortfall
        # lines below are measured against what the cars are TODAY
        read_declared(browser, port)
        print('  HOW FAR DOES A CAR GET FLAT OUT WITH NOBODY STEERING - A FLOOR')
        print('      checkpoints are 2 miles apart and pay 20s, a crate pays 10s,')
        print('      and the run starts with 60s on the clock')
        for body in [b.strip() for b in args.bodies.split(',') if b.strip()]:
            reached = []
            for n in range(args.runs):
                r = run_arm(browser, port, body, args.cap)
                mph = round(r['peak'] / 15333.0 * 200)
                # A CAR THAT NEVER MOVED DID NOT DRIVE THREE MILES IN NO TIME - it
                # was never handed over. Printing a distance for it would be a
                # finding invented by the harness.
                if mph <= 0:
                    print('      %-10s BLKD  the run never started - peak speed was zero'
                          % body)
                    print('                 the car on the road was %s in mode %s, the'
                          ' count-in had %s left, and the clock read %.1f'
                          % (out_body(r), r.get('mode'), r['state'].get('left'),
                             r['state'].get('clock', -1)))
                    if r['errors']:
                        print('                 page errors: %s' % '; '.join(r['errors']))
                    continue
                end = 'the clock ran out' if r['ended'] else 'ABANDONED at the cap'
                reached.append(r['dist'])
                print('      %-10s %6.2f miles   %s after %3.0fs   %s crate(s), peak %d mph'
                      % (body, r['dist'], end, r['wall'],
                         r['crates'] if r['crates'] is not None else '?', mph))
                for line in driver_limits(r, mph, declared_mph(body)):
                    print('                 %s' % line)
            if len(reached) > 1:
                print('      %-10s   -> %.2f to %.2f miles over %d runs'
                      % ('', min(reached), max(reached), len(reached)))
        browser.close()
    httpd.shutdown()
    print()
    if fails:
        print('FAILED: ' + '; '.join(fails))
        return 1
    print('the falsifier cleared its bar, so the distances above are a REAL FLOOR -')
    print('and a floor is all they are. A player steers to the crates and reaches the')
    print("car's own top end, and the budget at the top of this file is what says how")
    print('far THAT goes. See RLG-215.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
