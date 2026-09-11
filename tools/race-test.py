#!/usr/bin/env python3
"""
RACE TEST - a race has checkpoints, whatever the timed toggle says.

    .venv/Scripts/python tools/race-test.py

RLG-089. Owner, 2026-08-30: turn TIMED off under TEST DRIVE, and a RACE started afterwards has no
checkpoints in it - and turning TIMED back on before switching to RACE does not fix it.

IT REPRODUCES THE SEQUENCE, NOT THE SYMPTOM. Starting a race with the toggle off would have found
the first half of this and missed the second. The owner found it by turning the toggle off under one
mode, back on, and then changing mode, which is what says the state was being decided once and kept
rather than read at the start of the run. So the harness walks the same path.

AND IT COUNTS BOARDS ON THE ROAD, not a setting. `clockRuns()` was already the correct predicate and
was already wrapping the code that places them; the defect was a second, wrong question asked inside
it. A check written against the predicate would therefore have passed on the broken build, which is
the same trap `lamp-test` and `beam-test` were each rewritten to get out of.

Exit code 0 if every check passed, 1 otherwise.
"""

import argparse
import re
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


def read_toggle(page, act):
    el = page.query_selector('#veil [data-act="%s"] b' % act)
    return el.text_content().strip() if el else None


def set_toggle(page, act, want):
    """Tap a toggle until it reads what is wanted. It cycles, so this is how a thumb does it."""
    for _ in range(6):
        if read_toggle(page, act) == want:
            return True
        b = page.query_selector('#veil [data-act="%s"]' % act)
        if not b:
            return False
        b.click()
        page.wait_for_timeout(90)
    return read_toggle(page, act) == want


def drive_a_while(page, seconds):
    """Hold the car at speed past the count-in, long enough that a board must have been placed.

    FAR ENOUGH IS FURTHER THAN IT LOOKS. A checkpoint sits every two miles, which is about
    167,000 world units, and the loop that places one only looks 90,000 units ahead. Four
    seconds at nine tenths of top speed covers 55,000 - so the first version of this drove a
    third of the way to the first board and reported that none had been placed, which is the
    defect it was looking for. It has to reach the first one honestly.
    """
    steps = int(seconds / 0.12)
    for _ in range(steps):
        page.evaluate('() => window.__probe.road.setSpd(window.__probe.road.MAX_SPD * 0.9)')
        page.wait_for_timeout(120)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--headed', action='store_true')
    args = ap.parse_args()
    console_utf8()
    res = Results()
    httpd, port = serve(ROOT)
    print('race-test  .  a race has checkpoints, whatever the toggle says')

    with sync_playwright() as p:
        browser = launch_chromium(p, headless=not args.headed)
        page = browser.new_context(viewport={'width': 480, 'height': 900},
                                   has_touch=True, is_mobile=True).new_page()
        page.add_init_script(INIT)
        boot(page, 'http://127.0.0.1:%d/%s' % (port, GAME))
        until(page, '!!window.__probe.road', timeout=10000)
        page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
        page.click('[data-act="play"]')
        page.wait_for_timeout(700)

        # ---- THE OWNER'S OWN SEQUENCE ---------------------------------------
        # Timed OFF under test drive, timed back ON, then change mode to race.
        res.check(set_toggle(page, 'mode', 'TEST DRIVE'),
                  'the garage starts on TEST DRIVE', read_toggle(page, 'mode'))
        res.check(set_toggle(page, 'timed', 'OFF'),
                  'and TIMED can be turned off there', read_toggle(page, 'timed'))
        res.check(set_toggle(page, 'timed', 'ON'),
                  'and back on again', read_toggle(page, 'timed'))
        # the control cycles TEST DRIVE, SINGLE RACE, TOURNAMENT and the label is what it
        # says on the button - a harness that guessed 'RACE' sat on TEST DRIVE and reported
        # the defect it was looking for
        res.check(set_toggle(page, 'mode', 'SINGLE RACE'),
                  'then the mode changes to a race', read_toggle(page, 'mode'))

        page.click('[data-act="drive"]')
        drive_a_while(page, 18.0)
        boards = page.evaluate('() => window.__probe.road.gantries()')
        print('      TIMED off then on, then a race: %d board(s)' % boards)
        res.check(boards > 0,
                  'a race puts checkpoint boards on the road',
                  'none were placed')

        # ---- AND THE CASE THAT ACTUALLY DISCRIMINATES -----------------------
        # The sequence above does NOT reproduce the defect: it leaves TIMED on, so the old
        # code placed the board anyway and the check passed on the broken build. What breaks
        # it is TIMED left OFF while a race runs - the clock runs, because `clockRuns()`
        # knows a race is timed, and the boards did not, because the line beside it asked
        # the toggle instead. Recorded here rather than quietly swapped in, because the
        # owner's own steps are still the report and this is what they were pointing at.
        page2 = browser.new_context(viewport={'width': 480, 'height': 900},
                                    has_touch=True, is_mobile=True).new_page()
        page2.add_init_script(INIT)
        boot(page2, 'http://127.0.0.1:%d/%s' % (port, GAME))
        until(page2, '!!window.__probe.road', timeout=10000)
        page2.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
        page2.click('[data-act="play"]')
        page2.wait_for_timeout(700)
        res.check(set_toggle(page2, 'timed', 'OFF'),
                  'TIMED can be left off', read_toggle(page2, 'timed'))
        res.check(set_toggle(page2, 'mode', 'SINGLE RACE'),
                  'with the mode set to a race', read_toggle(page2, 'mode'))
        page2.click('[data-act="drive"]')
        drive_a_while(page2, 18.0)
        boards2 = page2.evaluate('() => window.__probe.road.gantries()')
        clock2 = page2.evaluate('() => window.__probe.road.startLine().clock')
        print('      TIMED left OFF, then a race: %d board(s), clock at %.1f'
              % (boards2, clock2))
        res.check(boards2 > 0,
                  'a race with TIMED off still puts boards on the road',
                  'none were placed, though the clock was running')

        # ---- AND CROSSING ONE SAYS WHAT IT PAID YOU (RLG-106) ---------------------
        # Owner, 2026-08-31: "when you're rewarded more time, it just has a number '+20',
        # it should be '+20 sec'." A bare number reads as points, or a multiplier, or a
        # place - anything but seconds, which is the one thing it is. It is also the ONLY
        # moment the clock is ever added to: everything else about the timer counts down in
        # the HUD, where context says what it is.
        #
        # SO THE CAR HAS TO ACTUALLY CROSS ONE. Placing a board is not crossing it, and the
        # check above only proves boards exist. A checkpoint sits two miles out, about
        # 257,000 world units, so this drives on until the flash fires or gives up.
        seen_flash = ''
        for _ in range(90):
            page.evaluate('() => window.__probe.road.setSpd(window.__probe.road.MAX_SPD)')
            page.wait_for_timeout(120)
            t = page.eval_on_selector('#warn', 'e => e.textContent') or ''
            if 'CHECKPOINT' in t:
                seen_flash = t.strip()
                break
        print('      the checkpoint flash reads: %r' % seen_flash)
        res.check(bool(seen_flash), 'a checkpoint is actually crossed',
                  'no CHECKPOINT flash appeared in the whole run')
        if seen_flash:
            m = re.search(r'\+(\d+)\s+([A-Za-z]+)', seen_flash)
            res.check(m is not None,
                      'and it names a unit rather than a bare number',
                      'it read %r, which is a number with nothing to say what of' % seen_flash)
            if m:
                # AND THE NUMBER IS THE REWARD, not a literal that can drift from it. The
                # clock jumps by the award at the same moment, so the two are compared
                # rather than the text being trusted on its own.
                print('      it awarded %s %s' % (m.group(1), m.group(2)))
                res.check(int(m.group(1)) > 0 and len(m.group(2)) >= 1,
                          'and the unit is a word and the award is a real number',
                          'it read %r' % seen_flash)

        errs = page.evaluate('() => window.__probe.errors')
        res.check(not errs, 'no page errors', str(errs))
        browser.close()

    httpd.shutdown()
    if res.fails:
        print('')
        print('  %d check(s) failed' % len(res.fails))
        return 1
    print('')
    print('  all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
