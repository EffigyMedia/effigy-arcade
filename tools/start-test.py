#!/usr/bin/env python3
"""
START TEST - the car is HELD on the line, not merely covered by a number.

    .venv/Scripts/python tools/start-test.py

RLG-088. Owner, 2026-08-30: hitting DRIVE should give a three, two, one, GO countdown, with some
flare.

THE FLARE IS NOT WHAT THIS CHECKS, and it cannot be. Whether a number lands with a punch is the
owner's eye on the device; what a harness can say is whether the countdown is TRUE. A countdown
drawn over a car that is already accelerating is a lie the first frame gives away, so this asks the
three questions that make it real:

  1. the car does not move while the count is up;
  2. the run clock does not start either, so the count is not eating the player's time;
  3. and it does release - the car moves afterwards, or the game has simply stopped.

AND IT ASKS WHETHER THE COUNT IS SKIPPABLE ONLY AFTER THE FIRST RUN, because a start that can be
hurried the very first time is a start most players never see, and one that can never be hurried is
a toll on the player who is enjoying it most.

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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--headed', action='store_true')
    args = ap.parse_args()
    console_utf8()
    res = Results()
    httpd, port = serve(ROOT)
    print('start-test  .  the car is held on the line')

    with sync_playwright() as p:
        browser = launch_chromium(p, headless=not args.headed)
        page = browser.new_context(viewport={'width': 480, 'height': 900},
                                   has_touch=True, is_mobile=True).new_page()
        page.add_init_script(INIT)
        boot(page, 'http://127.0.0.1:%d/%s' % (port, GAME))
        until(page, '!!window.__probe.road', timeout=10000)
        page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
        page.click('[data-act="play"]')
        page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
        page.click('[data-act="drive"]')

        # ---- THE THROTTLE IS HELD DOWN THE WHOLE TIME ------------------------
        # This is what makes the hold a real question rather than an observation. A car
        # nobody is asking to move will sit still whether it is held or not, so the first
        # version of this check passed on a build with no countdown in it at all. The pedal
        # goes down before the count starts and stays down: the car must not move anyway,
        # and it must move the moment the count lets go.
        page.dispatch_event('#gas', 'pointerdown')

        # sample the whole count, from the frame after DRIVE to well past GO
        seen = []
        for _ in range(26):
            page.wait_for_timeout(160)
            row = page.evaluate('() => window.__probe.road.startLine()')
            b = page.evaluate('() => window.__probe.road.biomeSweep()')
            # the HORIZON as well as the ground: the owner's second report was that the
            # ground held still and the far end snapped to the next place at GO, which a
            # check on `player` alone reads as one unchanged biome
            row['biome'] = b['player']
            row['ahead'] = b['to']
            row['view'] = page.evaluate('() => window.__probe.road.viewState()')
            seen.append(row)

        held = [s for s in seen if s['left'] > 0]
        after = [s for s in seen if s['left'] <= 0 and s['go'] <= 0]
        res.check(len(held) >= 8,
                  'the count actually runs for about three seconds',
                  'only %d sample(s) had any count left' % len(held))
        if held:
            print('      the count ran from %.2f down to %.2f over %d samples'
                  % (held[0]['left'], held[-1]['left'], len(held)))

        # ---- 1. THE CAR IS HELD, AND ON THIS MACHINE THAT MEANS PINNED -------
        # THIS CHECK USED TO READ "the car does not move", and that was right while every
        # start was a standing one. Interstate rolls to the line now (RLG-123): the car is
        # pinned at fifty and the count happens around it, so a car at zero would be the
        # fault rather than the proof.
        #
        # What the check was ever ABOUT survives unchanged - a countdown drawn over a car
        # that is already ACCELERATING is a lie the first frame gives away. So what is
        # asserted is that the speed does not move, with the pedal held down throughout.
        roll = held[0]['roll'] if held else 0
        spds = [s['spd'] for s in held]
        print('      the car was pinned at %d units (%d mph) and read %d to %d'
              % (roll, round(roll / (15333 / 200.0)), min(spds), max(spds)))
        res.check(max(spds) - min(spds) <= max(2, roll * 0.02),
                  'the car neither speeds up nor slows down while the count is up',
                  'it ran from %d to %d with the pedal down' % (min(spds), max(spds)))
        res.check(abs(spds[0] - roll) <= max(2, roll * 0.02),
                  'and it is pinned at the speed this machine starts from',
                  'it read %d against a roll of %d' % (spds[0], roll))

        # AND THE ROAD PASSES UNDER IT WHILE THE ODOMETER DOES NOT. Two different
        # questions that a standing start could not tell apart. The road MUST move - a
        # speed readout over a frozen world is exactly the fault RLG-121 was about - and
        # the distance must NOT be credited, because distance unlocks cars and the count
        # is not the player's to spend.
        if len(held) >= 2:
            crept = held[-1]['dist'] - held[0]['dist']
            rolled = held[-1]['pos'] - held[0]['pos']
            print('      the road passed under it by %d units; the odometer counted %.4f miles'
                  % (rolled, crept))
            res.check(abs(crept) < 1e-6,
                      'and no distance is credited for sitting through the count',
                      'it counted %.4f miles while held' % crept)
            if roll > 0:
                res.check(rolled > roll * 0.5,
                          'while the road really does pass under it',
                          'it covered %d units, which is not a rolling start' % rolled)

        # ---- 2. THE CLOCK DOES NOT START -------------------------------------
        if len(held) >= 2:
            lost = held[0]['clock'] - held[-1]['clock']
            print('      run clock during the count: %.2f to %.2f'
                  % (held[0]['clock'], held[-1]['clock']))
            res.check(abs(lost) < 0.05,
                      'and the count does not eat the run clock',
                      '%.2f seconds went while the car was held' % lost)

        # ---- 3. AND IT LETS GO -----------------------------------------------
        res.check(bool(after), 'the count ends', 'it never reached zero')
        res.check(any(s['spd'] > 0 for s in after),
                  'and the car moves once it does, on a throttle that was already down',
                  'still stationary %d sample(s) after GO' % len(after))
        if after:
            print('      with the pedal down throughout: 0 while held, %d after'
                  % max(s['spd'] for s in after))

        # ---- 4. THE PIPS FIRE ONCE EACH, NOT EVERY FRAME ----------------------
        pips = [s['pip'] for s in held]
        runs = [p for i, p in enumerate(pips) if i == 0 or p != pips[i-1]]
        print('      the numbers sounded in the order %s' % runs)
        res.check(runs == sorted(set(runs), reverse=True) and len(runs) == len(set(runs)),
                  'each number is sounded once, and they count down',
                  'the sequence was %s' % runs)

        # ---- 5. THE FIRST START IS SEEN WHOLE, THE NEXT CAN BE HURRIED --------
        # A start that can be skipped the very first time is a start most players never
        # see; one that can never be skipped is a toll on whoever is enjoying it most.
        first = seen[0]
        res.check(first['seen'] is False,
                  'the first count of a session cannot be hurried',
                  'the game already thought a start had been seen')
        later = [s for s in seen if s['seen']]
        res.check(bool(later), 'and it is remembered once it has been seen',
                  'no sample reported a start had been seen')

        # ---- 5b. THE WORLD IS ALIVE BEHIND THE NUMBERS (RLG-121) -------------
        # The comment at the top of step() said "everything below this runs, so the road, the
        # traffic and the sky are all alive behind the numbers" - and the code RETURNED two lines
        # under it. So the whole world was frozen for three seconds and resumed in one frame, which
        # is what the owner reported four times as a pop on GO.
        #
        # `viewShift` IS THE CLEAREST OF THEM. It is the forward view's horizontal offset, it is
        # set nowhere but inside step(), and on a touch device it goes from 0 to minus 8.5 per cent
        # of the screen width. Frozen through the count, it snapped on the first driving frame and
        # took the entire picture - and the player's own car with it - sideways in one frame. That
        # is exactly "everything shifts at once, and my car jumps to a different place".
        vs_held = [s2['view']['viewShift'] for s2 in held]
        vs_after = [s2['view']['viewShift'] for s2 in after]
        print('      the view offset during the count: %s   after GO: %s'
              % (sorted(set(vs_held)), sorted(set(vs_after))))
        if vs_held and vs_after:
            res.check(set(vs_held) == set(vs_after),
                      'the forward view is in the same place during the count as after it',
                      'it was %s while held and %s after' % (sorted(set(vs_held)), sorted(set(vs_after))))
            res.check(vs_after[0] != 0,
                      'and that place is the shifted one, so the check is not passing on two zeroes',
                      'the offset was 0 throughout, which a desktop viewport would also produce')

        # AND THE ROAD IS BEING RE-INTEGRATED WHILE THE COUNT RUNS. The bend cache is rebuilt on a
        # timer inside step(), so behind the old return it was never rebuilt and the first driving
        # frame did it in front of the player. This is the general form of the question: is the
        # world TICKING, or is it waiting.
        if len(held) >= 2:
            builds = held[-1]['view']['bendBuilds'] - held[0]['view']['bendBuilds']
            print('      the road was re-integrated %d time(s) while the count was up' % builds)
            res.check(builds > 0, 'the road is re-integrated while the count is up',
                      'it was rebuilt %d times, so it was waiting for GO' % builds)

        # ---- 6. AND THE WORLD DOES NOT CHANGE AT GO (RLG-088) ----------------
        # Owner, 2026-08-30: when the countdown finishes, the entire world changes - you
        # arrive in a brand new biome on GO. Two correct changes met badly: the reset was
        # made to clear the opening-place flag so each run picks its own, and the count-in
        # was made to return from step() before the biome runs. So the place was chosen on
        # the first frame AFTER the count, in front of the player, as a snap.
        #
        # THE PLACE IS SAMPLED ACROSS THE WHOLE COUNT AND PAST IT. The question is not
        # whether a biome exists but whether it is the SAME ONE the player was looking at,
        # so what is compared is the first sample against every later one.
        places = [s['biome'] for s in seen] + [s['ahead'] for s in seen]
        print('      the place across the count and past GO: %s'
              % ' '.join(dict.fromkeys(places)))
        res.check(len(set(places)) == 1,
                  'the world the player looks at during the count is the one they drive into',
                  'it went %s' % ' then '.join(dict.fromkeys(places)))

        # ---- 7. AND NOTHING IS SAVED UP TO HAPPEN ON GO (RLG-090) ------------
        # Owner, 2026-08-31: there is still a pop on GO - can the state not be started on
        # load and persisted through the countdown and the drive start.
        #
        # A COUNTER LEFT AT ZERO MEANS A ROLL IS DUE. The count-in returns from step()
        # before the world runs, so anything due was deferred to the first frame after GO
        # and happened in front of the player. The biome had this fault and was fixed; the
        # weather and the cloud had it too, in the two counters beside it.
        #
        # So this compares the world at the START of the count with the world after GO. It
        # is deliberately not a check on any one field: the question is whether ANYTHING
        # was saved up, and a list would only cover what somebody remembered to add.
        page2 = browser.new_context(viewport={'width': 480, 'height': 900},
                                    has_touch=True, is_mobile=True).new_page()
        page2.add_init_script(INIT)
        boot(page2, 'http://127.0.0.1:%d/%s' % (port, GAME))
        until(page2, '!!window.__probe.road', timeout=10000)
        page2.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
        page2.click('[data-act="play"]')
        page2.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
        page2.click('[data-act="drive"]')
        page2.wait_for_timeout(200)
        during = page2.evaluate('() => window.__probe.road.worldState()')
        page2.wait_for_timeout(4200)          # past GO, and a moment beyond it
        after = page2.evaluate('() => window.__probe.road.worldState()')
        print('      during the count: %s' % during)
        print('      after GO:         %s' % after)
        # the place, what is falling, and the sky it falls out of. `wet` and `settle` move
        # on their own once the car is driving, so what is compared is what was CHOSEN.
        keys = ('biome', 'from', 'to', 'snowy', 'wetTarget', 'storm')
        def same(a, b):
            if isinstance(a, str) or isinstance(b, str):
                return a == b
            return abs(float(a) - float(b)) <= 1e-6
        moved = [k for k in keys if not same(during.get(k, 0), after.get(k, 0))]
        res.check(not moved,
                  'the world the player waits in is the world they are let go into',
                  'these changed at GO: %s' % ', '.join(moved))

        # AND THE DIRECT QUESTION, WHICH IS NOT A LOTTERY. Comparing the two pictures only
        # catches this when the deferred roll happens to produce weather - it came up dry
        # one run in three and the check passed on a broken build. A counter at zero means
        # a roll is DUE, so asking the counters answers it every time.
        due = [k for k in ('wetIn', 'cloudIn', 'biomeIn') if float(during.get(k, 1)) <= 0]
        print('      time until the next change, during the count: '
              'weather %s, cloud %s, biome %s'
              % (during.get('wetIn'), during.get('cloudIn'), during.get('biomeIn')))
        res.check(not due,
                  'and nothing is sitting due, waiting for the count to end',
                  'these were already due while the car was held: %s' % ', '.join(due))

        errs = page.evaluate('() => window.__probe.errors')
        res.check(not errs, 'no page errors', str(errs))
        browser.close()
    httpd.shutdown()
    print(('\n%d check(s) failed' % len(res.fails)) if res.fails else '\nall checks passed')
    return 1 if res.fails else 0


if __name__ == '__main__':
    sys.exit(main())
