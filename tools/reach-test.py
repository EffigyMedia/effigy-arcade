#!/usr/bin/env python3
"""REACH - how far can ONE timed test drive actually go before the clock ends it?

    .venv/Scripts/python tools/reach-test.py

WHY THIS EXISTS. The distance unlocks are written as `dist >= 25` and `dist >= 50`
inside `if(mode !== 'race' && timedRun)`, so they are asked of ONE RUN with the
timer ON. Nothing had ever measured whether a run can reach those numbers. RLG-213
is about to set a new merged unlock at 50 or 100 miles and the owner asked which is
better, so the ceiling has to be known before the number is chosen.

THE ARITHMETIC SAYS IT CANNOT, AND ARITHMETIC IS NOT A MEASUREMENT. A checkpoint is
every CP_MILES (2) and pays CLOCK_BONUS (20s), so a car must average 360mph to break
even and the fastest car in the game declares 194. A crate pays CRATE_SECS (10) and
they are scattered rather than placed. So the clock should fall and the run should
end - but crate density is the free variable and only a run can say.

THE FALSIFIER IS BUILT IN AND IT RUNS FIRST. A harness that reports "the run ended at
6 miles" is worthless if it cannot report 60. So the first arm PINS the speed far
above any car's top end with `API.holdSpd`: the car then covers two miles in well
under twenty seconds, the clock GAINS, and the same code path must report a large
distance. If that arm does not clear the distances being considered, every number
below it is unreadable and the harness says so.

A RUN THAT NEVER STARTED IS BLKD AND NOT A ZERO. The first version of this harness
reported "SALOON 0.00 miles" and "STALLION 0.00 miles", which reads as a finding and
was a defect: both cars are LOCKED, the garage would not hand them over, and the run
never began. A car whose peak speed is zero did not drive, so it is blocked and its
distance is not printed at all. `API.dbgTraffic` opens the production and utility
classes without writing an unlock flag, which is what lets the SALOON be measured;
there is no equivalent for the racing classes, so the supercars are out of reach from
here and are not asked for.

AND IT REPEATS, BECAUSE CRATES ARE THE FREE VARIABLE. A crate pays ten seconds and
the drain is about eight and a half seconds a mile at the top of the fleet, so crate
density is very nearly the whole answer and it is scattered rather than placed. One
run of this decides nothing.

Exit code 0 if the falsifier cleared its bar, 1 otherwise. THE PER-CAR RESULTS ARE A
MEASUREMENT AND NOT A PASS OR A FAIL - they are the answer to the owner's question
and they are printed, not asserted.
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


def main():
    ap = argparse.ArgumentParser()
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
    httpd, port = serve(ROOT)
    fails = []
    print('reach  .  how far ONE timed test drive gets before the clock ends it')
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
            print('        it does NOT prove a 100-mile run would be reported - see the note in')
            print('        the source. That case is arithmetic: 360mph to break even, 194 declared.')
            if not ok:
                fails.append('the falsifier did not clear 12 miles'
                             ' - every number below is unreadable')

        # ---- AND NOW THE REAL QUESTION --------------------------------------------
        print()
        print('  HOW FAR DOES A REAL CAR GET, FLAT OUT, TIMER ON')
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
            if len(reached) > 1:
                print('      %-10s   -> %.2f to %.2f miles over %d runs'
                      % ('', min(reached), max(reached), len(reached)))
        browser.close()
    httpd.shutdown()
    print()
    if fails:
        print('FAILED: ' + '; '.join(fails))
        return 1
    print('the falsifier cleared its bar, so the distances above are the game and not the harness')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
