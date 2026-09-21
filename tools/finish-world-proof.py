#!/usr/bin/env python3
"""FINISH WORLD PROOF - the run ends, the world does not.

    .venv/Scripts/python tools/finish-world-proof.py

RLG-305. Owner, 2026-09-21, from the device: 'When the race is over all the traffic comes to
a dead stop they should just keep moving just like the player.'

IT WAS ONE ASSIGNMENT. Crossing the line set `state = 'wrecked'`, and nothing reads that
value - its only effect is to send `frameLoop` down the branch that does not call `step()`
at all. So the traffic, the rivals, the police, the weather and the biome all stopped, while
the player's own car rolled on through them under the frozen branch's `spd *= 0.985`.

AND IT MADE THE FINISH'S OWN PROMISE DEAD CODE, which is the second half of this proof. The
note at the finish says the car is handed to the AI, which 'lifts, holds its lane, and coasts
down'. That AI is `if(coasting && state === 'driving')`, so it had never once run after a
finish. The crude decay in the frozen branch does not centre the car and does not keep it off
the barriers.

WHAT IS MEASURED, AND WHY IT IS THESE FOUR:

    THE WORLD KEEPS MOVING. The traffic's MEAN position, before the line and after it. A
    count of cars cannot answer this and neither can a speed - a world that has stopped
    being stepped keeps whatever speeds it had. The mean is used rather than one car,
    because the traffic array is re-sorted by z every frame and a car picked by index is a
    different car a frame later.

    THE AI HAS THE CAR. The wheel is turned away from centre before the line and has to come
    back on its own. This is the binary of the two: under the AI `targetX` unwinds toward 0,
    and in the frozen branch `step` is not called at all so it cannot move.

    THE ODOMETER STOPS. The run's distance is what it was when it ended, and `bestDist` was
    written from it one frame earlier.

    AND NOTHING CAN WRECK A CAR THAT HAS FINISHED. The world running means the traffic the
    player was racing through is still there, still moving, and the car is no longer being
    steered. The finish's own note records that fault in as many words: 'you could still
    crash after winning'.

WHAT IT CANNOT DO. It cannot say whether the roll-out READS right - whether a living road
around a finished car looks better than a frozen one. That is the owner's on a device.

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

# Where the wheel is put before the line, in the engine's own lateral units. It has to be
# well away from centre, because what is being watched is the AI bringing it back.
OFF_CENTRE = 0.6

# How long the road is watched either side of the line, and how often it is read.
SPAN, TICK = 8, 250


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
        print(('  ok    ' if ok else '  FAIL  ') + label + ('' if ok else '   [' + detail + ']'))
        if not ok:
            self.fails.append(label)


def watch(page, n):
    out = []
    for _ in range(n):
        out.append(page.evaluate("() => window.__probe.road.motion()"))
        page.wait_for_timeout(TICK)
    return out


def advance(rows):
    """How far the traffic's mean position moved over the samples, per second."""
    if len(rows) < 2:
        return 0.0
    span = (len(rows) - 1) * TICK / 1000.0
    return (rows[-1]['traffic']['meanZ'] - rows[0]['traffic']['meanZ']) / span


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--headed', action='store_true')
    args = ap.parse_args()
    console_utf8()
    res = Results()
    httpd, port = serve(ROOT)
    print('finish-world-proof  .  the run ends, the world does not')
    with sync_playwright() as p:
        browser = launch_chromium(p, headless=not args.headed)
        page = browser.new_page(viewport={'width': 480, 'height': 900})
        page.add_init_script(INIT)
        boot(page, 'http://127.0.0.1:%d/%s' % (port, GAME))
        until(page, '!!window.__probe.road', timeout=10000)
        page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
        page.click('[data-act="play"]')
        page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
        page.click('[data-act="drive"]')
        page.wait_for_timeout(2500)
        # A HELD SPEED IS THE HARNESS, NOT THE GAME, and it is released at the line - it
        # overrides the coast-down, so leaving it on would measure the pin rather than the AI.
        page.evaluate("""() => {
          const R = window.__probe.road;
          R.setTimed(false); R.setSpd(9000); R.holdSpd(9000);
        }""")
        page.wait_for_timeout(2500)

        print()
        print('  BEFORE THE LINE')
        before = watch(page, SPAN // 2)
        run = advance(before)
        print('      the traffic advances %d units a second' % run)
        res.check(before[0]['traffic']['n'] > 0, 'there is traffic on the road to watch',
                  '%d cars' % before[0]['traffic']['n'])
        res.check(run > 500, 'and it is moving before the line',
                  'it advanced %d units a second' % run)

        page.evaluate("(x) => window.__probe.road.setTarget(x)", OFF_CENTRE)
        page.wait_for_timeout(300)
        at_line = page.evaluate("() => window.__probe.road.motion()")
        page.evaluate("""() => {
          const R = window.__probe.road;
          R.parkFinish(2000);
          R.holdSpd(null);
        }""")
        page.wait_for_timeout(200)

        print()
        print('  AFTER IT')
        after = watch(page, SPAN)
        end = after[-1]
        roll = advance(after)
        print('      the traffic advances %d units a second, and the car rolls %d to %d'
              % (roll, after[0]['spd'], end['spd']))
        res.check(end['finished'], 'the run really did end', '%r' % end)
        res.check(roll > run * 0.5,
                  'the traffic keeps moving, at something like the rate it did',
                  'it advanced %d units a second against %d before the line' % (roll, run))

        print()
        print('  AND THE CAR IS THE AI\'S')
        print('      the wheel goes %.3f -> %.3f, the odometer %.3f -> %.3f, iframe %.2f'
              % (at_line['targetX'], end['targetX'], at_line['dist'], end['dist'],
                 end['iframe']))
        res.check(abs(at_line['targetX']) > OFF_CENTRE * 0.5,
                  'the wheel was away from centre when the line was crossed',
                  'it was at %.3f' % at_line['targetX'])
        res.check(abs(end['targetX']) < abs(at_line['targetX']) * 0.5,
                  'and the AI brings it back, which the frozen branch cannot do at all',
                  '%.3f against %.3f' % (end['targetX'], at_line['targetX']))
        res.check(end['spd'] < after[0]['spd'] * 0.5, 'the car is coasting down',
                  '%d against %d' % (end['spd'], after[0]['spd']))
        res.check(abs(end['dist'] - at_line['dist']) < 0.01,
                  'the odometer stopped at the line',
                  '%.4f against %.4f' % (end['dist'], at_line['dist']))
        res.check(end['iframe'] > 0,
                  'and nothing can wreck a car that has already finished',
                  'iframe is %.2f' % end['iframe'])

        errs = page.evaluate("() => window.__probe.errors")
        res.check(not errs, 'no page errors', str(errs))
        browser.close()
    httpd.shutdown()

    print()
    if res.fails:
        print('FAILED: ' + '; '.join(res.fails))
        return 1
    print('PASSED: the road keeps running and the car is handed to the AI')
    return 0


if __name__ == '__main__':
    sys.exit(main())
