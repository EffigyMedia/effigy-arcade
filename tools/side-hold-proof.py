#!/usr/bin/env python3
"""SIDE HOLD PROOF - a place keeps its side of the road for as long as you are in it.

    .venv/Scripts/python tools/side-hold-proof.py

RLG-308. Owner, 2026-09-21, from the device: 'For some reason I've seen the coastal biome
flip sides randomly.'

IT WAS ONE GLOBAL, AND THE COIN WAS THROWN FOR THE WRONG PLACE. `rollSide()` runs when the
NEXT place is planned - the moment its boundary enters the far end of the drawn road, three
hundred segments ahead of the car. The place the player was still driving through read the
same variable, so planning the next place moved the sea of THIS one, half the time, from one
frame to the next. The same shape as RLG-150: the place the picture shows and the place the
generator builds for, held in one variable.

WHAT IS MEASURED, AND IT IS THE PAINT RATHER THAN THE VARIABLE:

    THE SEA STAYS WHERE IT WAS DRAWN. A coast is put on a known side, then the next place
    is planned again and again while the car sits in the coast, and after every plan the
    near road is sampled for water with `coast-test`'s own classifier. A side that belongs
    to the place never moves; a shared coin moves it about half the time.

    THE PLACE AHEAD STILL GETS A FRESH COIN. Holding the current side still must not be
    done by never rolling at all - two oceans in one run are meant to be able to put the
    water on different sides, which is what the roll was for.

    AND THE HAND-OVER CARRIES IT. Once the car has crossed, the place it is now in keeps the
    side it was drawn with on the way in, rather than inheriting whatever the next plan
    throws. Read from `API.sides` when the build has it.

    AND A DEER IS PLANNED IN A REAL RUN, WHICH IT NEVER WAS. `planDeer` asked the coin whether
    a place had a sea - `if(biome !== 'FOREST' || sideRoll)` - and the coin was never zero, so
    every forest was rejected as a forest by the sea from the day it was written. `deer-test`
    passed throughout because its probe set the coin to zero by hand. So this counts through
    the path a run actually takes: `API.restart` runs the real opening, which calls
    `planDeer()` with nothing overridden. Measured on the build before the fix: 310 forest
    openings, 0 deer.

WHAT IT CANNOT DO. It cannot say whether a player notices a coast that holds its side, which
is the whole point, and which is the owner's on a device.

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

/* WHERE THE WATER IS PAINTED, left or right of the road's own vanishing point, in a band
   below the horizon. The classifier is `coast-test`'s, word for word, so the two harnesses
   agree on what counts as sea. */
window.__probe.waterSide = function(){
  var R = window.__probe.road;
  var c = document.querySelector('canvas');
  var r = c.getBoundingClientRect();
  var dpr = c.width / r.width;
  var g = c.getContext('2d');
  var hz = R.horizon();
  var vx = R.vanishing ? R.vanishing().x : r.width / 2;
  var y0 = Math.round((hz + 40) * dpr), hh = Math.round(120 * dpr);
  var d = g.getImageData(0, y0, c.width, hh).data;
  var split = vx * dpr, left = 0, right = 0;
  for(var y = 0; y < hh; y++){
    for(var x = 0; x < c.width; x++){
      var i = (y*c.width + x)*4;
      var Rr = d[i], G = d[i+1], B = d[i+2];
      if(B > 55 && B < 160 && B > Rr*1.4 && G > Rr && G < B){ if(x < split) left++; else right++; }
    }
  }
  return { left: left, right: right };
};
"""

# How many times the next place is planned while the car sits in the coast. A shared coin
# moves the water on about half of them, so twenty makes a missed flip a one in a million.
PLANS = 20

# How much more water one side must show than the other to say which side it is on.
DOMINANT = 4.0

# How many real run openings the deer is counted over. A tenth of the board is forest and the
# stated odds are a tenth, so 3,000 openings is about thirty deer - enough to tell 10 per cent
# from none, and from every time.
OPENINGS = 3000


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


def drawn_side(page):
    """-1 if the water is painted on the left, +1 on the right, 0 if it cannot be said."""
    page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
    w = page.evaluate("() => window.__probe.waterSide()")
    if w['left'] > w['right'] * DOMINANT and w['left'] > 500:
        return -1, w
    if w['right'] > w['left'] * DOMINANT and w['right'] > 500:
        return 1, w
    return 0, w


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--headed', action='store_true')
    args = ap.parse_args()
    console_utf8()
    res = Results()
    httpd, port = serve(ROOT)
    print('side-hold-proof  .  a place keeps its side for as long as you are in it')
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
        # A STRAIGHT road, a still car, midday, and a coast with its water pinned on the LEFT.
        #
        # STRAIGHT MEANS FLATTENED, NOT HELD. The first build of this used `holdCurve(0)`, which
        # only shapes road not yet generated - so the road already made at load kept its bends,
        # and the road is generated fresh per load. On one load it was straight and the proof
        # passed; under step.py the next load was curved, the near road's centre sat well off
        # the far vanishing point the split is taken at, and the coast read as water on BOTH
        # sides (left 2385, right 982). `flattenRoad` replaces the whole table.
        page.evaluate("""() => {
          const R = window.__probe.road;
          R.setTimed(false); R.setSpd(0); R.holdSpd(0);
          R.flattenRoad();
          R.setPhase(0.30);
          R.setBiomePair('COASTAL', 'COASTAL');
          R.setSeaSide(-1);
        }""")
        page.wait_for_timeout(1200)

        print()
        print('  THE SEA STAYS WHERE IT WAS DRAWN')
        start, w0 = drawn_side(page)
        print('      before any plan: water %s (left %d, right %d)'
              % ({-1: 'LEFT', 1: 'RIGHT', 0: 'UNCLEAR'}[start], w0['left'], w0['right']))
        res.check(start == -1, 'the coast is painted with its water on the side it was given',
                  'left %d, right %d' % (w0['left'], w0['right']))
        # A MOVE IS ONLY A MOVE AWAY FROM A SIDE THAT COULD BE READ. Scored against an unclear
        # baseline, every clear reading after it counted as the water changing sides - which is
        # how one bad load reported 15 moves in 20 on an engine that holds the side.
        if start == 0:
            res.check(False, 'and the side could be read before anything was planned',
                      'the baseline was unclear, so no move can be scored against it')

        moved, unclear, ahead = 0, 0, set()
        for i in range(PLANS if start != 0 else 0):
            page.evaluate("""() => {
              const R = window.__probe.road;
              R.setBiomePair('COASTAL', 'COASTAL');
              R.startBiomeChange('DESERT');
            }""")
            got, w = drawn_side(page)
            if got == 0:
                unclear += 1
            elif got != start:
                moved += 1
            s = page.evaluate("() => window.__probe.road.sides ? window.__probe.road.sides() : null")
            if s:
                ahead.add(s['sideTo'])
        print('      %d plans of the next place: the water moved %d times, %d unclear'
              % (PLANS, moved, unclear))
        res.check(unclear <= PLANS // 4, 'the water could be read after nearly every plan',
                  '%d of %d were unclear' % (unclear, PLANS))
        res.check(moved == 0, 'and planning the place ahead never moved the one you are in',
                  'the water changed sides %d times in %d plans' % (moved, PLANS))

        print()
        print('  THE PLACE AHEAD STILL GETS A FRESH COIN')
        if ahead:
            print('      the place ahead was dealt: %s' % sorted(ahead))
            res.check(ahead == {-1, 1},
                      'both sides came up for the place ahead, so the roll still does its job',
                      'only %s in %d plans' % (sorted(ahead), PLANS))
        else:
            print('      (this build has no per-place side to read, so nothing to check here)')

        print()
        print('  AND THE HAND-OVER CARRIES IT')
        s = page.evaluate("() => window.__probe.road.sides ? window.__probe.road.sides() : null")
        if s:
            dealt = s['sideTo']
            page.evaluate("() => { const R = window.__probe.road; R.setSpd(14000); R.holdSpd(14000); }")
            until(page, "() => { const s = window.__probe.road.sides(); return s.from === s.to; }",
                  timeout=30000)
            page.evaluate("() => window.__probe.road.holdSpd(0)")
            after = page.evaluate("() => window.__probe.road.sides()")
            print('      the place ahead was dealt %+d; across the line the place you are in reads %+d'
                  % (dealt, after['sideFrom']))
            res.check(after['from'] == 'DESERT', 'the car really did cross into the next place',
                      'it is in %s' % after['from'])
            res.check(after['sideFrom'] == dealt,
                      'and it keeps the side it was drawn with on the way in',
                      'dealt %+d, now %+d' % (dealt, after['sideFrom']))
        else:
            print('      (this build has no per-place side to read, so nothing to check here)')

        print()
        print('  AND A DEER IS PLANNED IN A REAL RUN')
        page.evaluate("() => window.__probe.road.holdCurve(null)")
        by = page.evaluate("""() => {
          const R = window.__probe.road, by = {};
          for(let i = 0; i < OPENINGS; i++){
            R.restart();
            const k = R.biome(), o = by[k] || (by[k] = { n: 0, deer: 0 });
            o.n++; if(R.deerDue() !== null) o.deer++;
          }
          return by;
        }""".replace('OPENINGS', str(OPENINGS)))
        forest = by.get('FOREST', {'n': 0, 'deer': 0})
        elsewhere = sum(v['deer'] for k, v in by.items() if k != 'FOREST')
        share = forest['deer'] / float(forest['n']) if forest['n'] else 0
        print('      %d forest openings planned %d deer (%.1f%%); every other place, %d'
              % (forest['n'], forest['deer'], share * 100, elsewhere))
        res.check(forest['n'] >= 100, 'enough runs opened in a forest to count',
                  'only %d' % forest['n'])
        res.check(share > 0.04,
                  'a forest plans a deer in a real run - it planned none before this',
                  '%d in %d' % (forest['deer'], forest['n']))
        res.check(share < 0.20, 'and at about the stated odds rather than every time',
                  '%.1f%% against a stated 10%%' % (share * 100))
        res.check(elsewhere == 0, 'and nowhere but a forest', '%d elsewhere' % elsewhere)

        errs = page.evaluate("() => window.__probe.errors")
        res.check(not errs, 'no page errors', str(errs))
        browser.close()
    httpd.shutdown()

    print()
    if res.fails:
        print('FAILED: ' + '; '.join(res.fails))
        return 1
    print('PASSED: a place keeps its side, and the place ahead still rolls its own')
    return 0


if __name__ == '__main__':
    sys.exit(main())
