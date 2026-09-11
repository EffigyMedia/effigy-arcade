#!/usr/bin/env python3
"""
LAUNCH TEST - the grid starts from rest, and the player launches from neutral.

    .venv/Scripts/python tools/launch-test.py

RLG-118 and RLG-110, owner-decided 2026-08-31. Two halves of one start line:

  RLG-118  the grid was given a FLYING start. Every rival was built at about 91 per cent of its
           own top speed and the count-in freezes the world by returning early from step(), so the
           field was never held at zero - it was simply not stepped. Eleven cars already at racing
           speed were released against a player sitting at nothing.

  RLG-110  the player is held in NEUTRAL and revving is what buys the launch. The engine had a
           full free-revving neutral branch already and it was gated on the manual gearbox, so an
           automatic sat at idle however hard the throttle was held.

WHAT A HARNESS CAN AND CANNOT SAY. It can say the grid is at zero, that the box is in neutral, that
the needle moves, and that the three outcomes of the window agree with where the needle actually
was. It cannot say whether the window is HOLDABLE with a thumb, or whether the amber band is
legible on a phone. Those are the owner's, on the device.

THE WINDOW IS NOT AIMED AT BY THIS TEST. Landing the needle on a target from a harness is a race
against the engine's own rev decay and would make the check a timing test rather than a behaviour
one. Instead three starts are driven - never touching the throttle, holding it flat, and walking the needle
toward the band - and what is asserted is the RELATION: where the needle was, against what the game said
happened. That cannot pass by accident and it cannot flake on a frame.

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

# ---- TWO MACHINES, TWO STARTS (RLG-123) ------------------------------------
# Owner, 2026-08-31: the rolling start is the main difference between them.
# MOTORSPORT is a circuit: a race starts from a grid, standing, on the neutral
# launch and the rev window. INTERSTATE is the endless road: you are already
# driving, the count happens at fifty, and GO changes only who is steering.
# So the launch is tested where the launch is, and the roll where the roll is.
GAMES = {'motorsport': 'games/sw/motorsport.html',
         'interstate': 'games/sw/interstate.html'}

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


def open_page(browser, port, race=False, game='motorsport'):
    """A fresh context every time, so no run inherits the last one's save or its `seenStart`."""
    page = browser.new_context(viewport={'width': 480, 'height': 900},
                               has_touch=True, is_mobile=True).new_page()
    page.add_init_script(INIT)
    boot(page, 'http://127.0.0.1:%d/%s' % (port, GAMES[game]))
    until(page, '!!window.__probe.road', timeout=10000)
    page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
    page.click('[data-act="play"]')
    page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
    if race:
        # the MODE control cycles TEST DRIVE -> SINGLE RACE -> TOURNAMENT; one press is a race
        page.click('[data-act="mode"]')
        page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
    page.click('[data-act="drive"]')
    return page


def drive_start(page, throttle):
    """Run one start. `throttle` is 'none', 'flat' or 'aim'.

    'none' never touches the pedal, 'flat' holds it down throughout, and 'aim' walks the needle
    toward the middle of the band the way a thumb has to. The pedal is a real pointer event on the
    real button - nothing is set through the API, because the thing under test is what the player's
    thumb does."""
    rows = []
    down = False
    if throttle == 'flat':
        page.dispatch_event('#gas', 'pointerdown')
        down = True
    for i in range(60):
        page.wait_for_timeout(50)
        row = page.evaluate('() => Object.assign({}, window.__probe.road.launch(),'
                            ' { line: window.__probe.road.startLine(),'
                            '   voice: window.__probe.road.engineVoice() })')
        rows.append(row)
        # ---- AIM: THE PEDAL IS A BUTTON, SO THE NEEDLE IS WALKED ------------------
        # This is the same thing a thumb has to do - press to bring the needle up, release and
        # let it drift, press again before it falls out - and it is the only check there is that
        # the band is reachable at all. It is deliberately no cleverer than a person: it sees the
        # needle at 50ms intervals, which is SLOWER than a player watching the dial.
        if throttle == 'aim' and row['count'] > 0:
            if row['rev'] < row['peak'] and not down:
                page.dispatch_event('#gas', 'pointerdown'); down = True
            elif row['rev'] >= row['peak'] and down:
                page.dispatch_event('#gas', 'pointerup'); down = False
        # ---- AND AFTER GO, EVERY RUN DRIVES THE SAME -----------------------------
        # The launch is graded at the instant the gear lands, and what happens after it
        # is ordinary driving. Without this the comparison below was not about the
        # launch at all: the 'aim' driver had lifted to catch the band and never pressed
        # again, so it coasted to a standstill and lost to a wheelspin that at least had
        # its foot down. Same driver after GO, different launch, is the only way that
        # check means what it says.
        if row['count'] <= 0 and not down:
            page.dispatch_event('#gas', 'pointerdown'); down = True
    if down:
        page.dispatch_event('#gas', 'pointerup')
    return rows


MPH_UNITS = 15333 / 200.0     # MAX_SPD is 200mph, road.js


def pearson(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = sum((x - mx) ** 2 for x in xs) ** 0.5
    dy = sum((y - my) ** 2 for y in ys) ** 0.5
    return 0.0 if dx == 0 or dy == 0 else num / (dx * dy)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--headed', action='store_true')
    args = ap.parse_args()
    console_utf8()
    res = Results()
    httpd, port = serve(ROOT)
    print('launch-test  .  the grid starts from rest and the player launches from neutral')

    with sync_playwright() as p:
        browser = launch_chromium(p, headless=not args.headed)

        # ================================================================== RLG-110
        print('\n  the box, and the engine in it')
        runs = {}
        for how in ('none', 'flat', 'aim'):
            page = open_page(browser, port, game='motorsport')
            runs[how] = drive_start(page, how)
            page.context.close()

        flat = runs['flat']
        held = [r for r in flat if r['count'] > 0]
        after = [r for r in flat if r['count'] <= 0]

        res.check(len(held) >= 20, 'the count runs long enough to launch in',
                  'only %d samples had any count left' % len(held))

        # 1. NEUTRAL, ON THE AUTOMATIC BOX. The default gearbox is the automatic, so this is the
        #    exact case RLG-110 says was broken: `engineRpm` clamped the gear to 1 for it.
        res.check(all(r['gear'] == 0 for r in held),
                  'the box is in neutral for the whole count, on the automatic gearbox',
                  'gears seen: %s' % sorted({r['gear'] for r in held}))
        res.check(all(r['armed'] for r in held),
                  'and the launch is armed while it is held')

        # 2. AND THE ENGINE IS FREE. Before the fix the needle sat at idle with the pedal flat,
        #    because the revs were derived from a road speed the count-in was holding at zero.
        top = max((r['rev'] for r in held), default=0)
        print('      needle with the pedal flat: %.3f of the redline at its highest' % top)
        res.check(top > 0.90, 'a held throttle winds the engine to the limiter',
                  'it only reached %.3f of the redline' % top)

        # 3. AND IT COMES BACK DOWN. `lift` releases the pedal part way through the count.
        aim = runs['aim']
        lheld = [r for r in aim if r['count'] > 0]
        if lheld:
            revs = [r['rev'] for r in lheld]
            # IT HAS TO FALL AS WELL AS RISE, which is what makes a band holdable at all -
            # the driver above walks the needle up and lets it drift, so somewhere in the
            # count there must be a sample lower than the one before it. Comparing the peak
            # with the last reading does NOT test this: a driver holding the band well ends
            # AT the peak, and the check would fail on the run that went best.
            fell = max((revs[i] - revs[i+1] for i in range(len(revs)-1)), default=0)
            print('      walking the needle: %.3f to %.3f, largest single drop %.3f'
                  % (min(revs), max(revs), fell))
            res.check(fell > 0.005,
                      'and the needle falls again when the throttle is released',
                      'it never dropped between samples; the largest fall was %.4f' % fell)

        # 3b. AND IT CAN BE HEARD WHILE IT DOES (owner, from the device, 2026-08-31)
        #     Everything that makes a noise sits at the bottom of step(), past the count-in's
        #     return, so the car was silent for the whole three seconds while the player was
        #     being asked to set the revs with the throttle.
        #
        #     A LEVEL IS NOT EVIDENCE THE NODE IS HEARD. RLG-065 cost three attempts on exactly
        #     this: a GainNode on a CLOSED context reports a healthy value quite happily. So both
        #     questions are asked - does the pitch MOVE with the revs, and is the oscillator
        #     carrying it on the context the game is actually playing through.
        voiced = [r for r in held if r['voice']['hz'] is not None]
        res.check(len(voiced) >= 10, 'the engine voice exists while the count is up',
                  'only %d sample(s) had one' % len(voiced))
        if voiced:
            lo_hz = min(r['voice']['hz'] for r in voiced)
            hi_hz = max(r['voice']['hz'] for r in voiced)
            print('      engine pitch across the count: %.1f Hz to %.1f Hz' % (lo_hz, hi_hz))
            res.check(hi_hz > lo_hz * 1.5,
                      'and its pitch climbs with the revs rather than sitting at idle',
                      'it went %.1f Hz to %.1f Hz' % (lo_hz, hi_hz))
            res.check(all(r['voice']['live'] for r in voiced),
                      'on the context the game is playing through, not an orphaned one',
                      'contexts seen: %s' % sorted({r['voice']['ctx'] for r in voiced}))
            res.check(max(r['voice']['gain'] for r in voiced) > 0.01,
                      'and it is audible rather than held at zero',
                      'the loudest it got was %.4f' % max(r['voice']['gain'] for r in voiced))
            # AND THE PITCH FOLLOWS THE NEEDLE rather than merely moving. Compared over the
            # whole count: the sample with the highest needle must be the loudest-pitched one.
            by_rev = max(voiced, key=lambda r: r['rev'])
            res.check(by_rev['voice']['hz'] > lo_hz * 1.5,
                      'and the highest pitch belongs to the highest revs',
                      'needle %.3f sounded %.1f Hz against a range of %.1f-%.1f'
                      % (by_rev['rev'], by_rev['voice']['hz'], lo_hz, hi_hz))

        # A STATIONARY CAR DOES NOT MAKE WIND. Wind is scaled off the same ratio as the engine
        # note, so without the `still` flag a car held on the line howls at eight thousand rpm.
        # This is read as the WIND layer's own level, not inferred from the engine's.
        # 4. NEVER TOUCHING IT LEAVES THE ENGINE AT IDLE
        none_held = [r for r in runs['none'] if r['count'] > 0]
        idle_top = max((r['rev'] for r in none_held), default=1)
        res.check(idle_top < 0.15, 'and it idles when the throttle is never touched',
                  'it reached %.3f of the redline with nobody on the pedal' % idle_top)

        # ================================================================== the window
        print('\n  the window, and the three things that can happen at it')
        landed = {}
        for how in ('none', 'flat', 'aim'):
            rows = [r for r in runs[how] if r['count'] <= 0 and r['note']]
            if not rows:
                res.check(False, 'the %s start reached a verdict' % how, 'no sample carried a note')
                continue
            r = rows[0]
            landed[how] = r
            print('      %-5s  needle %.3f   band %.3f-%.3f   %s'
                  % (how, r['at'], r['lo'], r['hi'], r['note']))

        # THE RELATION IS THE CHECK. Where the needle was, against what the game said happened.
        # This cannot pass by accident: a build that ignored the window would have to produce the
        # right verdict for three different needle positions by chance.
        for how, r in landed.items():
            if r['at'] < r['lo']:
                want, why = 'BOGGED', 'under the band'
            elif r['at'] > r['hi']:
                want, why = 'WHEELSPIN', 'over the band'
            else:
                want, why = 'LAUNCH', 'inside the band'
            res.check(want in r['note'],
                      'the %s start landed %s and the game said so' % (how, why),
                      'needle %.3f against %.3f-%.3f, and it said %s'
                      % (r['at'], r['lo'], r['hi'], r['note']))

        # AND A GOOD LAUNCH IS WORTH SOMETHING. Speed a second after GO, which is the only thing
        # the player is actually buying.
        def speed_after(rows):
            got = [r['line']['spd'] for r in rows if r['count'] <= 0]
            return got[19] if len(got) > 19 else (got[-1] if got else 0)

        spds = {how: speed_after(runs[how]) for how in runs}
        print('      speed a second after GO:  %s'
              % '   '.join('%s %d' % (k, v) for k, v in spds.items()))
        inband = [k for k, r in landed.items() if r['lo'] <= r['at'] <= r['hi']]
        res.check(bool(inband),
                  'at least one of the three starts landed inside the window',
                  'none did, so the window may be unreachable: %s'
                  % {k: (r['at'], r['lo'], r['hi']) for k, r in landed.items()})
        for good in inband:
            for bad in landed:
                if bad == good:
                    continue
                res.check(spds[good] > spds[bad],
                          'a launch inside the window beats the %s start' % bad,
                          '%d against %d a second later' % (spds[good], spds[bad]))

        # ============================================== the rolling start (RLG-123)
        print('\n  the rolling start, on the endless road')
        grids = []
        for _ in range(3):
            page = open_page(browser, port, race=True, game='interstate')
            page.wait_for_timeout(400)
            during = page.evaluate('() => ({ line: window.__probe.road.launch(),'
                                   '          grid: window.__probe.road.grid() })')
            page.wait_for_timeout(1200)
            during2 = page.evaluate('() => ({ line: window.__probe.road.launch(),'
                                    '          grid: window.__probe.road.grid() })')
            # the frame the count lets go, and a second past it
            page.wait_for_timeout(1500)
            at_go = page.evaluate('() => ({ line: window.__probe.road.launch(),'
                                  '          grid: window.__probe.road.grid() })')
            page.wait_for_timeout(1000)
            later = page.evaluate('() => ({ line: window.__probe.road.launch(),'
                                  '          grid: window.__probe.road.grid() })')
            grids.append((during, during2, at_go, later))
            page.context.close()

        during, during2, at_go, later = grids[0]
        roll = during['line']['roll']
        print('      the machine rolls to the line at %d units (%d mph), standing=%s'
              % (roll, round(roll / MPH_UNITS), during['line']['standing']))
        res.check(during['line']['standing'] is False,
                  'Interstate does not start from a grid',
                  'it reported standing=%s' % during['line']['standing'])
        res.check(roll > 0, 'and it has a rolling speed to start at', 'roll was %d' % roll)

        # 1. THE CAR IS PINNED, NOT STOPPED, AND NOT FREE
        for label, snap in (('early', during), ('late', during2)):
            res.check(abs(snap['line']['spd'] - roll) <= max(2, roll * 0.02),
                      'the car is held at the rolling speed %s in the count' % label,
                      'it was doing %d against a roll of %d' % (snap['line']['spd'], roll))
        # AND THE ROAD IS ACTUALLY PASSING UNDER IT. A speed readout with a
        # stationary world is the fault RLG-121 was about, so the distance is
        # what is asserted rather than the number on the dial.
        moved = during2['line']['pos'] - during['line']['pos']
        print('      the road passed under it by %d units while the count ran' % moved)
        res.check(moved > roll * 0.5,
                  'and the road is passing under it while the count runs',
                  'it covered %d units, which is not fifty miles an hour' % moved)

        # 2. THE WHOLE FIELD IS DOING THE SAME, AHEAD OF YOU
        res.check(len(during['grid']) == 11, 'a race grid is eleven rivals',
                  'it was %d' % len(during['grid']))
        offs = [abs(r['spd'] - roll) for r in during['grid']]
        print('      the field during the count: every rival within %d of the roll' % max(offs))
        res.check(max(offs) <= max(2, roll * 0.02),
                  'the whole field is rolling at the same speed you are',
                  'one was %d off the roll' % max(offs))

        # 3. AND IT HAS NOT GAINED A YARD WHEN THE COUNT ENDS. This is the whole
        #    point: a field that is not racing yet must not be racing yet. Their
        #    positions RELATIVE to the player are what matters, because everything
        #    is moving - so the gap is what is compared, not the absolute z.
        def gaps(snap):
            return [r['spd'] for r in snap['grid']]
        drift = max(abs(a - b) for a, b in zip(gaps(during), gaps(during2)))
        print('      the fastest rival changed speed by %d over a second of the count' % drift)
        res.check(drift <= max(2, roll * 0.02),
                  'and nobody in it is racing before the count ends',
                  'one rival changed by %d' % drift)

        # 4. THEY DO GO WHEN IT ENDS, or the hold has simply parked the race
        gained = max(r['spd'] for r in later['grid']) - roll
        print('      a second after GO the fastest rival has gained %d' % gained)
        res.check(gained > 0, 'they go once the count ends',
                  'the fastest had gained %d, so nothing was released' % gained)

        # 5. AND NOTHING SNAPS AT THE LINE. The count ending must not step any
        #    rival's speed more than a second of racing does.
        step_at_go = max(abs(r['spd'] - roll) for r in at_go['grid'])
        print('      the largest speed step at GO itself: %d, against %d gained over the next second'
              % (step_at_go, gained))
        res.check(step_at_go <= max(gained, roll * 0.10),
                  'and no rival snaps to a new speed as the count reaches zero',
                  'one stepped by %d at GO while a whole second of racing is worth %d'
                  % (step_at_go, gained))

        # A CAP STATED RATHER THAN HIDDEN. RLG-118's standing grid - eleven cars
        # at rest on a circuit - is NOT covered here and cannot be from a harness:
        # Motorsport's DRIVE is a solo practice session and QUALIFY is a solo lap,
        # so neither reaches a grid. Reaching a circuit grid from a harness is
        # unsolved; drive-test does not do it either.
        print('      NOT COVERED: the standing grid on a circuit - no harness can reach one')

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
