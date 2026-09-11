#!/usr/bin/env python3
"""BORE ORDER TEST - a car inside a tunnel is in front of the tunnel wall.

    .venv/Scripts/python tools/bore-order-test.py

RLG-145 item 4. Owner, 2026-09-01, with a capture: traffic inside the bore had the wall and
the floor painted straight across it.

THE SUBJECT IS A DRAW ORDER, AND A DRAW ORDER IS SETTLED BY THE PIXELS. `draw()` calls
`drawRoad`, which paints the road AND emits the sprites, and then calls `drawBore`. So the
question this asks is not "is the order right", which would be a check agreeing with the code
it is checking, but "is the car ON THE SCREEN when there is a tunnel around it".

HOW IT ASKS. The road is frozen, the place is pinned to TUNNEL at both ends of the blend so no
frame lands mid-crossing, and one car is parked at a stated distance and a stated offset
across the road. The canvas is read twice - once with the car and once without - and the
pixels that differ ARE the car.

AND THE CONTROL IS THAT SAME CAR MOVED BACK TO THE MIDDLE OF THE ROAD. That is the whole
design, and it is the second design: the first compared a car in a tunnel with the same car in
FARMLAND and was useless twice over. Farmland has moving scenery, so two frames of it differ
by hundreds of pixels on their own. And the car it compared stood at the CENTRE of the
carriageway, where the bore never covered it - so the check passed with the defect present,
which was watched happening before this was rewritten.

THE WALLS CONVERGE ON THE VANISHING POINT, so they close over the EDGES of the road long
before they reach the middle. A car half a lane out is behind the wall and the same car in the
middle is not. Comparing the two is comparing an identical sprite at an identical size under
identical light with no scenery anywhere to move by itself, so anything the offset car has
lost, the bore took.

MEASURED BOTH WAYS BEFORE THE THRESHOLD WAS CHOSEN. With the bore painted over the traffic, a
car at the road edge keeps 15 to 75 per cent of itself and its box is visibly cut off at the
bottom. With the bore drawn under it, 82 to 99. The check reads the WORST of twelve
placements, so it sits at 55 with the two populations far to either side.

WHAT IT CANNOT DO. It cannot say the tunnel LOOKS right, and it deliberately asserts nothing
about the far end: a car deep in the bore SHOULD be swallowed by the depth fade, exactly as
the tarmac is, so that decay is printed and not gated. `tools/biome-shot.py` takes the picture.

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

/* THE CANVAS AFTER A FRAME, NOT DURING ONE. A read taken at any moment lands
   halfway through a paint, and half a picture cannot be compared with another
   half. This waits for a frame to finish before it reads. */
window.__grab = function(){
  return new Promise(function(res){
    requestAnimationFrame(function(){
      requestAnimationFrame(function(){
        var c = document.getElementById('cv');
        var g = c.getContext('2d');
        window.__last = g.getImageData(0, 0, c.width, c.height).data;
        res({ w: c.width, h: c.height });
      });
    });
  });
};
window.__keep = function(){ window.__held = window.__last; return true; };
/* how many pixels differ, and the box they fall in. The box is what says the
   change is A CAR standing on the road rather than the sky flickering. The diff
   runs here so no image library is needed and nothing is re-encoded. */
window.__diff = function(tol, skipTop){
  var a = window.__held, b = window.__last;
  if(!a || !b || a.length !== b.length) return null;
  var n = 0, x0 = 1e9, x1 = -1e9, y0 = 1e9, y1 = -1e9;
  var c = document.getElementById('cv'), W = c.width;
  /* THE MIRROR IS NOT THE ROAD. The rear-view sits across the top of the canvas
     and it redraws whenever the traffic array changes, so a car parked a mile
     AHEAD moves pixels up there and inflates the count by hundreds. The forward
     view is what this measures, so the top of the frame is not read at all. */
  var from = Math.round(c.height * (skipTop || 0)) * W * 4;
  for(var i = from; i < a.length; i += 4){
    if(Math.abs(a[i]-b[i]) > tol || Math.abs(a[i+1]-b[i+1]) > tol ||
       Math.abs(a[i+2]-b[i+2]) > tol){
      n++;
      var p = i/4, x = p % W, y = (p/W)|0;
      if(x < x0) x0 = x;
      if(x > x1) x1 = x;
      if(y < y0) y0 = y;
      if(y > y1) y1 = y;
    }
  }
  return { n:n, x0:x0, x1:x1, y0:y0, y1:y1, total: a.length/4 };
};
"""


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


TOL = 10
# how much of the top of the frame the diff ignores: the rear-view mirror lives there
SKIP_TOP = 0.20


def box(r):
    return '%dx%d at (%d,%d)' % (r['x1'] - r['x0'] + 1, r['y1'] - r['y0'] + 1,
                                 r['x0'], r['y0'])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--headed', action='store_true')
    ap.add_argument('--bend', type=float, default=None,
                    help='hold the road at this curvature while measuring')
    args = ap.parse_args()
    console_utf8()
    res = Results()
    httpd, port = serve(ROOT)
    print('bore-order-test  .  a car in a tunnel is in front of the wall')
    with sync_playwright() as p:
        browser = launch_chromium(p, headless=not args.headed)
        page = browser.new_page(viewport={'width': 480, 'height': 900})
        page.add_init_script(INIT)
        boot(page, 'http://127.0.0.1:%d/%s' % (port, GAME))
        try:
            until(page, '() => navigator.serviceWorker && navigator.serviceWorker.controller',
                timeout=5000)
            page.wait_for_timeout(1000)
        except Exception:
            pass
        until(page, '!!window.__probe.road', timeout=10000)
        page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
        page.click('[data-act="play"]')
        page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
        page.click('[data-act="drive"]')
        page.wait_for_timeout(1600)
        page.evaluate("(b) => { window.__bend = b; }", args.bend)

        def place(biome):
            page.evaluate("""(k) => {
              const R = window.__probe.road;
              R.setBiomePair(k, k);
              R.setPhase(0.75);
              R.setWet(0); R.setSnow(0); R.setPool(0);
              R.clearTraffic(); R.setSpd(0);
              if(window.__bend !== null) R.bendRoad(window.__bend);
            }""", biome)
            # PAST THE COUNT-IN FIRST. A capture taken inside it has GO across the middle of
            # it, and GO is not a car.
            for _ in range(40):
                st = page.evaluate("() => window.__probe.road.startLine()")
                if st['left'] <= 0 and st['go'] <= 0:
                    break
                page.wait_for_timeout(90)
            for _ in range(12):
                page.evaluate("() => { const R = window.__probe.road;"
                              " R.clearTraffic(); R.setSpd(0); }")
                page.wait_for_timeout(40)

        def hold_empty():
            page.evaluate("() => { const R = window.__probe.road;"
                          " R.clearTraffic(); R.setSpd(0); }")
            page.evaluate("() => window.__grab()")
            page.evaluate("() => window.__keep()")

        def with_car(dz, dx=0.0, kind='truck'):
            page.evaluate("([dz, dx, k]) => { const R = window.__probe.road;"
                          " R.setSpd(0); R.parkTraffic(dx, dz, k); }", [dz, dx, kind])
            page.evaluate("() => window.__grab()")
            return page.evaluate("([t, s]) => window.__diff(t, s)", [TOL, SKIP_TOP])

        def again_empty():
            page.evaluate("() => { const R = window.__probe.road;"
                          " R.clearTraffic(); R.setSpd(0); }")
            page.evaluate("() => window.__grab()")
            return page.evaluate("([t, s]) => window.__diff(t, s)", [TOL, SKIP_TOP])

        # ------------------------------------------------------------ the control
        print()
        print('  THE NOISE FLOOR - two captures of the SAME empty road')
        place('TUNNEL')
        hold_empty()
        floor = again_empty()
        print('      %d pixels of %d differ between two frames of a frozen road'
              % (floor['n'], floor['total']))
        res.check(floor['n'] < 400,
                  'a frozen road is frozen, so a difference below means a car',
                  '%d pixels moved by themselves' % floor['n'])

        # ------------------------------------------------------------ the measurement
        # THE CONTROL IS THE SAME CAR MOVED SIDEWAYS, AND THAT IS THE WHOLE DESIGN.
        #
        # The first build of this check compared a car in a tunnel with the same car in
        # FARMLAND, and it was useless twice over. Farmland has moving scenery, so two frames
        # of it differ by hundreds of pixels on their own and the baseline was noise. And the
        # car it compared was AT THE CENTRE OF THE ROAD, where the bore never covered it - so
        # the check passed with the defect present, which was watched happening.
        #
        # THE WALLS CONVERGE ON THE VANISHING POINT, so they close over the EDGES of the
        # carriageway long before they reach the middle. A car half a lane out is behind the
        # wall; the same car in the middle is not. So the control is that same car, at the
        # same distance, in the same tunnel, moved back to the centre: identical sprite,
        # identical size, identical lighting, and no scenery anywhere to move by itself.
        # Anything the offset car has lost, the bore took.
        DISTANCES = (4200, 6000, 9000)
        OFFSETS = (-1.1, -0.9, 0.9, 1.1)

        print()
        print('  THE SAME CAR, THE SAME DISTANCE, MOVED OUT TO WHERE THE WALL IS')
        place('TUNNEL')
        trace = page.evaluate("() => window.__probe.road.boreTrace()")
        print('      placeDark %.2f, the mouth is %d units ahead'
              % (trace['dark'], trace['ahead']))
        res.check(trace['dark'] > 0.9,
                  'the bore is being drawn at all, so the measurement means something',
                  'placeDark reads %.2f' % trace['dark'])
        print()
        print('      ahead   lane    centre   out here    kept')
        worst = None
        for dz in DISTANCES:
            hold_empty()
            mid = with_car(dz, 0.0)
            for dx in OFFSETS:
                hold_empty()
                r = with_car(dz, dx)
                share = r['n'] / max(1, mid['n'])
                print('      %6d %+5.1f %8d %10d %6.0f%%   %s'
                      % (dz, dx, mid['n'], r['n'], share * 100, box(r)))
                if worst is None or share < worst[3]:
                    worst = (dz, dx, r['n'], share, mid['n'])
        print()
        res.check(worst is not None and worst[4] > 400,
                  'there is a car big enough to lose in the first place',
                  'the centred control drew %d pixels' % (worst[4] if worst else 0))
        # 55 PER CENT, AND THE NUMBER WAS CHOSEN FROM BOTH POPULATIONS. The defect was put
        # back and measured: a car at the road edge kept 15 to 75 per cent of itself, and its
        # box was cut off at the bottom where the wall crossed it. With the bore drawn under
        # the traffic, 82 to 99. This reads the WORST of the twelve placements, so the two
        # answers are 15 and 82 and the threshold sits between them with room on both sides.
        # What is left above it is the sprite being a pixel or two wider at one offset than
        # another, which is projection and not occlusion.
        res.check(worst is not None and worst[3] > 0.55,
                  'a car at the road edge survives the wall instead of being painted over',
                  'worst at %d units, %+.1f lanes: %d pixels against %d at the centre (%.0f%%)'
                  % (worst[0], worst[1], worst[2], worst[4], worst[3] * 100) if worst
                  else 'nothing measured')

        # ------------------------------------------------------------ and the far end
        print()
        print('  AND THE FAR END STILL GOES BLACK, WHICH IS NOT A FAULT')
        print('  (printed, not asserted - a car deep in the bore SHOULD be swallowed)')
        for dz in (2200, 6000, 12000, 18000, 24000):
            hold_empty()
            r = with_car(dz, 0.0)
            print('      %6d units ahead: %5d pixels' % (dz, r['n']))

        errs = page.evaluate("() => window.__probe.errors")
        if errs:
            print()
            res.check(False, 'the page threw nothing', '; '.join(errs[:3]))
        browser.close()
    httpd.shutdown()
    print()
    if res.fails:
        print('  FAILED: ' + '; '.join(res.fails))
        return 1
    print('  all checks passed')
    return 0


sys.exit(main())
