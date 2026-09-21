#!/usr/bin/env python3
"""RANGE DRIFT PROOF - the valley range moves like something at a stated distance.

    .venv/Scripts/python tools/range-drift-proof.py

RLG-309. Owner, 2026-09-21: 'The parallaxing mountain scenery looks weird. They are
parallaxing too fast or something', and on being asked which of the three things parallax
at a mountain: 'I'm talking about the valley range.'

THE RATE WAS THE ONLY THING IN THIS MODEL NOTHING DERIVED. `RANGE_DRIFT` was 0.0042 pixels
of slide per unit of road travelled, picked by hand. A point at lateral `L` and distance
`dz` sits at `CAM_D * L * W/2 / dz` from the vanishing point and sweeps outward at that over
`dz` again - so a slide rate IS a standoff, read backwards. 0.0042 put the range 45,700
units out while it stood 46,800 ahead: forty-four degrees off the road, which is land beside
you rather than across a valley. `RANGE_OUT` states the standoff instead and the rate falls
out of the projection.

THE CORNER TERM IS MEASURED HERE TOO, AND IT IS NOT WHAT WAS WRONG. It was
`skySmooth * 1.55` - the horizon band's smoothed scroll, borrowed and multiplied. Measured
against the range's own bend on held corners it comes out within a few per cent, because the
chase's own 0.55 times 1.55 lands near the turn at the range's distance by accident. What it
did carry was an UNSTATED SIGN, and dropping it on the way to `bendPx` inverted the swing.
That is what the first check here exists to catch, and it caught it.

    THEY TRAVEL THE SAME WAY. The range and the horizon behind it are both distant scenery
    and both are tiled textures, so their offsets move together through a corner.

    AND IT IS COUNTED OVER ORDINARY DRIVING RATHER THAN ASSERTED ON ONE CORNER, because
    the first build of this check failed on a correct engine and the check was wrong, not
    the code. Two reasons, both measured. `skySmooth` is a LAGGING CHASE, so when the road's
    bend passes through zero the two terms cross at different moments and their signs
    genuinely differ for a second - a reading of 8 px is not a direction. And a HELD CURVE
    never settles: `holdCurve` only shapes road that has not been generated yet, so the bend
    at the far end keeps moving for as long as the car drives into road that was already
    made. So the run samples many frames, ignores everything near zero, and asks what
    fraction agree. An inverted sign is not a near miss on that measure - it was watched
    scoring 0 of 6 against the 100 per cent the correct sign scores.

    AND MOVING THE STANDOFF MOVES THE PICTURE. Doubling `RANGE_OUT` doubles the measured
    slide on one road, alternating inside one page and returning to where it started - which
    is what says the stated number reaches the frame rather than sitting in a table. The
    arithmetic is deliberately NOT re-stated: a check that recomputes the same formula from
    the same constants and finds it equal has proved that multiplication works.

WHAT IT CANNOT DO. It cannot say whether the range now reads as land across a valley. That
is the owner's on a device, and `RANGE_OUT` is the one constant that moves it.

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

# How many frames the sign is counted over, a quarter of a second apart. Forty is ten
# seconds of road, which is several corners at the speed this holds.
SAMPLES = 40

# Below this many pixels a term is too near zero for its sign to mean anything. It was 1,
# and a horizon reading of 8.2 px against a range of -16.9 failed the run on an engine that
# was correct - both were sitting on a zero crossing.
FLOOR = 20.0

# The share of clear samples that must agree. A correct sign holds every one of them; an
# inverted sign was watched holding none, so anything between the two separates them.
AGREE = 0.80


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


def slide_per_second(page, out):
    """How far the drift term moves in two seconds at a held speed, at this standoff."""
    page.evaluate("(v) => window.__probe.road.rangeModel({ out: v })", out)
    page.wait_for_timeout(300)
    a = page.evaluate("() => window.__probe.road.rangeModel().terms.drift")
    page.wait_for_timeout(2000)
    b = page.evaluate("() => window.__probe.road.rangeModel().terms.drift")
    return abs(b - a) / 2.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--headed', action='store_true')
    args = ap.parse_args()
    console_utf8()
    res = Results()
    httpd, port = serve(ROOT)
    print('range-drift-proof  .  the valley range moves like something at a stated distance')
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
        page.wait_for_timeout(1600)
        page.evaluate("""() => {
          const R = window.__probe.road;
          R.setTimed(false);
          R.setBiomePair('MOUNTAIN', 'MOUNTAIN');
          R.setPhase(0.30);
          R.setSpd(9000); R.holdSpd(9000);
        }""")
        page.wait_for_timeout(1200)

        # ------------------------------------------------ the rate is the projection
        print()
        print('  WHAT IT IS SET TO')
        m = page.evaluate("() => window.__probe.road.rangeModel()")
        print('      it stands %d units out and %d ahead, and slides %.5f px per unit'
              % (m['outZ'], m['atZ'], m['drift']))
        # THE ARITHMETIC IS NOT RE-STATED HERE. A check that recomputes the same formula
        # from the same constants and finds it equal has proved that multiplication works.
        # What says the standoff reaches the frame is MOVING it, which is the next block.

        # ------------------------------------------------ and moving it moves the picture
        print()
        print('  AND MOVING THE STANDOFF MOVES THE PICTURE')
        near = slide_per_second(page, 12)
        far = slide_per_second(page, 24)
        back = slide_per_second(page, 12)
        print('      12 road-widths out: %.1f px/s      24 out: %.1f px/s      12 again: %.1f'
              % (near, far, back))
        res.check(near > 1 and far > 1, 'the range slides at both standoffs',
                  '%.2f and %.2f px/s' % (near, far))
        if near > 1:
            res.check(abs(far / near - 2.0) < 0.12,
                      'twice as far out is twice the slide, which is what the model says',
                      'the ratio is %.3f' % (far / near))
            res.check(abs(back - near) < max(1.0, near * 0.08),
                      'and it comes back to where it was, so the arms are comparable',
                      '%.2f against %.2f px/s' % (back, near))

        # ------------------------------------------------ the sign
        print()
        print('  THE RANGE AND THE HORIZON TRAVEL THE SAME WAY')
        page.evaluate("() => window.__probe.road.rangeModel({ out: 12 })")
        agreed, read, seen = 0, 0, []
        for i in range(SAMPLES):
            t = page.evaluate("() => window.__probe.road.rangeModel().terms")
            sky, rng = t['smooth'], t['bend']
            if abs(sky) > FLOOR and abs(rng) > FLOOR:
                read += 1
                if (sky > 0) == (rng > 0):
                    agreed += 1
                else:
                    seen.append((round(sky, 1), round(rng, 1)))
            page.wait_for_timeout(250)
        share = agreed / float(read) if read else 0
        print('      %d of %d samples were clear of zero; %d agreed (%.0f%%)'
              % (read, SAMPLES, agreed, share * 100))
        if seen:
            print('      the ones that did not: %s' % (seen[:4],))
        res.check(read >= SAMPLES // 3,
                  'enough of the drive was in a real corner to read a direction',
                  'only %d of %d samples were clear of zero' % (read, SAMPLES))
        res.check(read and share >= AGREE,
                  'and the two move together for almost all of it',
                  'only %.0f%% agreed, against the %.0f%% a correct sign holds'
                  % (share * 100, AGREE * 100))

        errs = page.evaluate("() => window.__probe.errors")
        res.check(not errs, 'no page errors', str(errs))
        browser.close()
    httpd.shutdown()

    print()
    if res.fails:
        print('FAILED: ' + '; '.join(res.fails))
        return 1
    print('PASSED: the range slides at its stated distance and turns with the world')
    return 0


if __name__ == '__main__':
    sys.exit(main())
