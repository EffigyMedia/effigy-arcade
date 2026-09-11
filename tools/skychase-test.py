#!/usr/bin/env python3
"""
SKY CHASE TEST - the skyline answers a corner in seconds, not in frames.

    .venv/Scripts/python tools/skychase-test.py
    .venv/Scripts/python tools/skychase-test.py --headed

RLG-096. The skyline's parallax is chased toward the bend a long way ahead, and the chase was a fixed
fraction PER FRAME: a time constant of about 22 frames, which is 0.37 seconds at 60fps and 0.18 at
120. How fast the city answered a corner was decided by the refresh rate of the device it happened to
be running on.

WORSE THAN A WRONG NUMBER, IT WAS AN UNSTEADY ONE. The frame rate is not constant within one run -
`fps-test` measures FOREST between 45 and 60 on one unchanged build - so the chase sped up and slowed
down as the scenery thickened. That is a horizon that surges and lags for no reason visible on
screen, and it is the kind of fault that produces a jitter report nobody can reproduce, because
reproducing it needs the reporter's frame rate.

HOW THIS MEASURES IT WITHOUT A SECOND DEVICE. The car is parked, so `bendPx(pos + 30000)` is
constant and the chase has a fixed target. `API.setSkySmooth` pushes the value away from that
target; after a fixed WALL-CLOCK time the residual says how fast it came back. Then the same
measurement runs again with the CPU throttled, which cuts the frame rate without touching the clock.

A chase in seconds returns the same residual at both frame rates. A chase in frames does not: at
half the rate it gets half as far, so its residual is many times larger. The assertion is that the
two residuals AGREE, and the check prints the frame rate it actually measured at, because a run
where the throttle did not bite would compare a rate with itself and pass on any build.

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

# how far to push the chase off its target, and how long to let it come back
PUSH = 100.0
SETTLE_MS = 1500
# the two residuals must agree to within this share of the larger. The old form differed by a
# factor of about fifteen at half the frame rate, so this is not a tight rope to walk.
AGREE = 0.35
# the throttled run has to be meaningfully slower or the comparison is a rate against itself
MIN_SLOWDOWN = 1.6
# ...and it has to stay ABOVE the sky's own step clamp. Below that the chase is deliberately not
# time-correct - a backgrounded tab must not snap the city across the glass when the player comes
# back - so a run throttled past it measures the CLAMP and reports it as a frame-counting chase.
# The first version of this file throttled to 4.7fps against a clamp at 8, and failed a build that
# was correct. The margin is a safety factor over the clamp, not a taste.
CLAMP_MARGIN = 1.5


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def serve(root):
    handler = functools.partial(QuietHandler, directory=str(root))
    httpd = socketserver.TCPServer(('127.0.0.1', 0), handler)
    httpd.allow_reuse_address = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.socket.getsockname()[1]


class Results:
    def __init__(self):
        self.fails = []

    def check(self, ok, label, detail=''):
        print(('  ok    ' if ok else '  FAIL  ') + label + ('' if ok else '   [' + str(detail) + ']'))
        if not ok:
            self.fails.append(label)


def run_once(page):
    """Push the chase off its target, wait a fixed wall-clock time, report what is left.

    The residual is measured against the TARGET, not against zero: the car is parked on whatever
    piece of road it stopped on, and the chase converges on that bend rather than on nothing.
    """
    # THE TARGET, NOT THE RAW BEND. `want` in the trace is `bendPx(pos + 30000)`; the chase
    # converges on `-want * 0.55`, which is a different number. Measuring the residual against
    # `want` compares the chase with a value it never approaches, and the first version of this
    # file did exactly that: it reported 34 left of 100 after a second and a half of a chase that
    # should have been at 1.9, and passed.
    target = page.evaluate("() => window.__probe.road.skyTrace().target")
    page.evaluate("(v) => window.__probe.road.setSkySmooth(v)", target + PUSH)
    f0 = page.evaluate("() => window.__probe.road.skyFrames()")
    page.wait_for_timeout(SETTLE_MS)
    tr = page.evaluate("() => window.__probe.road.skyTrace()")
    f1 = page.evaluate("() => window.__probe.road.skyFrames()")
    return {'residual': abs(tr['smooth'] - tr['target']),
            'frames': f1 - f0,
            'fps': (f1 - f0) / (SETTLE_MS / 1000.0)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--headed', action='store_true')
    ap.add_argument('--throttle', type=float, default=3.0,
                    help='CPU throttling rate for the slow run')
    args = ap.parse_args()
    console_utf8()
    res = Results()
    httpd, port = serve(ROOT)
    print('skychase-test  .  the skyline answers a corner in seconds, not in frames')
    with sync_playwright() as p:
        browser = launch_chromium(p, headless=not args.headed)
        page = browser.new_page(viewport={'width': 480, 'height': 900})
        page.add_init_script(INIT)
        boot(page, 'http://127.0.0.1:%d/%s' % (port, GAME))
        try:
            until(page, '() => navigator.serviceWorker && navigator.serviceWorker.controller', timeout=5000)
            page.wait_for_timeout(1000)
        except Exception:
            pass
        until(page, '!!window.__probe.road', timeout=10000)
        page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
        page.click('[data-act="play"]')
        page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
        page.click('[data-act="drive"]')
        page.wait_for_timeout(2500)

        # PARKED, so the chase has a target that does not move. Everything measured below is the
        # chase rate; a car still travelling would be changing the target underneath it.
        page.evaluate("() => window.__probe.road.setSpd(0)")
        page.wait_for_timeout(400)

        cdp = page.context.new_cdp_session(page)

        fast = run_once(page)
        print('  full speed:  %5.1f fps over %d frames, %.4f left of %.0f'
              % (fast['fps'], fast['frames'], fast['residual'], PUSH))

        cdp.send('Emulation.setCPUThrottlingRate', {'rate': args.throttle})
        page.wait_for_timeout(500)
        slow = run_once(page)
        cdp.send('Emulation.setCPUThrottlingRate', {'rate': 1})
        print('  throttled:   %5.1f fps over %d frames, %.4f left of %.0f'
              % (slow['fps'], slow['frames'], slow['residual'], PUSH))
        print()

        # ---- the instrument -----------------------------------------------------------------
        # If the throttle did not bite, the run compared one frame rate with itself and would pass
        # on any build at all.
        slowdown = (fast['fps'] / slow['fps']) if slow['fps'] > 0 else 0
        res.check(slowdown >= MIN_SLOWDOWN,
                  'the throttle actually cut the frame rate, so two rates were compared',
                  'only %.2fx slower - raise --throttle' % slowdown)
        print('        the slow run ran %.2fx slower' % slowdown)
        res.check(slow['frames'] > 5,
                  'and it kept drawing, so the chase had frames to run in',
                  'only %d frames' % slow['frames'])
        clamp_fps = 1.0 / page.evaluate("() => window.__probe.road.skyStepMax()")
        res.check(slow['fps'] >= clamp_fps * CLAMP_MARGIN,
                  'and it stayed above the step clamp, so the chase was measured and not the clamp',
                  'ran at %.1f fps against a clamp at %.1f - lower --throttle'
                  % (slow['fps'], clamp_fps))
        print('        the clamp sits at %.1f fps; the slow run held %.1f'
              % (clamp_fps, slow['fps']))

        # ---- the chase is in seconds ---------------------------------------------------------
        big = max(fast['residual'], slow['residual'])
        gap = abs(fast['residual'] - slow['residual'])
        share = (gap / big) if big else 0
        res.check(share <= AGREE,
                  'the chase gets equally far in equal TIME, whatever the frame rate',
                  'residuals %.4f and %.4f differ by %.0f%% - the chase is counting frames'
                  % (fast['residual'], slow['residual'], share * 100))
        print('        residuals %.4f and %.4f, differing by %.0f%%'
              % (fast['residual'], slow['residual'], share * 100))
        print()

        # ---- and the same check, with the defect put back ------------------------------------
        # Reverting the engine cannot falsify this file: the instrument that displaces the chase
        # and reads its target does not exist on the old build. So the fault goes back instead -
        # `skyChaseFrames` returns the chase to a fixed fraction per FRAME, which is what it was.
        print('  the same check, with the chase counting frames again')
        page.evaluate("() => window.__probe.road.skyChaseFrames(true)")
        bad_fast = run_once(page)
        cdp.send('Emulation.setCPUThrottlingRate', {'rate': args.throttle})
        page.wait_for_timeout(500)
        bad_slow = run_once(page)
        cdp.send('Emulation.setCPUThrottlingRate', {'rate': 1})
        page.evaluate("() => window.__probe.road.skyChaseFrames(false)")
        bad_big = max(bad_fast['residual'], bad_slow['residual'])
        bad_share = (abs(bad_fast['residual'] - bad_slow['residual']) / bad_big) if bad_big else 0
        res.check(bad_share > AGREE,
                  'counting frames makes the check go red, so it was measuring the chase',
                  'residuals %.4f and %.4f still agree to %.0f%%'
                  % (bad_fast['residual'], bad_slow['residual'], bad_share * 100))
        print('        %5.1f fps -> %.4f left, %5.1f fps -> %.4f left, differing by %.0f%%'
              % (bad_fast['fps'], bad_fast['residual'],
                 bad_slow['fps'], bad_slow['residual'], bad_share * 100))
        print()

        errs = page.evaluate("() => window.__probe.errors")
        res.check(not errs, 'no page errors', '; '.join(errs[:3]))
        browser.close()
    httpd.shutdown()

    print()
    if res.fails:
        print('FAILED: ' + ', '.join(res.fails))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
