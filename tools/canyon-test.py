#!/usr/bin/env python3
"""CANYON TEST - the horizon is one mass, and it closes on itself.

    .venv/Scripts/python tools/canyon-test.py

RLG-104. Owner, 2026-08-31: of the four gaps offered, canyon and tunnel are the two to
build. THE TUNNEL AND THIS ARE OPPOSITE PROBLEMS - a tunnel has no distance in it, and a
canyon's distance IS a wall.

WHAT IS BEING TESTED IS THE CAPABILITY, NOT THE PLACE. Two places asked the skyline
generator for the same missing thing: this canyon wall and the jungle canopy of RLG-113. So
the checks below are about what a CONTINUOUS form must be, and the canyon is the first place
to state one. (RLG-113 counts the bridge towers as a third request. It is wrong about that,
and RLG-112 says so in as many words: a suspension tower stands ON the road and passes OVER
the camera, which is gantry work rather than a horizon.)

    IT HAS NO GAPS. Every other form walks the horizon placing a free-standing shape and
    then a space. A wall has no space in it, and no column of the sprite may reach the
    ground.

    IT DOES NOT JUMP. Zero gaps is not enough on its own: a row of rectangles packed edge
    to edge also has no gaps, and it is a comb rather than a ridge. The crest of a
    continuous form moves by a bounded step from one column to the next, because it is a
    walk rather than a set of independent rolls.

    AND IT CLOSES ON ITSELF. The skyline sprite TILES across the frame. A crest that ends
    where it likes puts a cliff at the seam and then repeats it across the whole horizon,
    so the last column has to meet the first.

THE CONTROLS ARE THE FALSIFICATION, AND THE THREE RULES ONLY WORK TOGETHER. Every other
place on the board is measured by the same three, and the first version of this harness
asserted the wrong one on its own: a peak line overlaps its own neighbours, so MOUNTAIN
and TUNDRA have no gaps AND a small step, and they are still rows of objects. What only a
closed walk can pass is the SEAM, because nothing else plans the two ends of the tile
together - MOUNTAIN misses it by 60 pixels. So each control breaks at least one rule and
the canyon passes all three, which is what makes this a measurement rather than a
restatement. If the canyon ever falls through to the tower default - which is exactly what
happened to farmland, and is why the form became a stated property - it goes red.

WHAT IT CANNOT DO. It cannot say whether the wall LOOKS like sandstone, whether the strip
of sky between the masses reads as a canyon at speed, or whether a road at 0.90 of bend
between walls is drivable on a phone. `tools/biome-shot.py` takes the picture; the owner
judges it.

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

# How far the crest of a CONTINUOUS form may move between two neighbouring columns of the
# sprite, in pixels. The walk's own ceiling is `rough` times the crest range over `step`,
# which is well under one pixel per column - so 3 is loose enough that a change to the
# table's roughness need not move this number, and far under what any free-standing form
# produces at the edge of an object.
STEP_LIMIT = 3


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


def measure(prof, height):
    """The three numbers a continuous form is defined by, read off the silhouette."""
    gaps = sum(1 for v in prof if v >= height)
    steps = [abs(prof[i + 1] - prof[i]) for i in range(len(prof) - 1)]
    return {
        'gaps': gaps,
        'step': max(steps) if steps else 0,
        'seam': abs(prof[-1] - prof[0]),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--headed', action='store_true')
    args = ap.parse_args()
    console_utf8()
    res = Results()
    httpd, port = serve(ROOT)
    print('canyon-test  .  the horizon is one mass, and it closes on itself')
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

        keys = page.evaluate("() => window.__probe.road.BIOME_KEYS()")
        res.check('CANYON' in keys, 'the canyon is on the board', str(keys))

        forms = page.evaluate("""() => {
          const R = window.__probe.road, out = {};
          for(const k of R.BIOME_KEYS()) out[k] = R.skyForm(k);
          return out;
        }""")
        res.check(forms.get('CANYON') == 'ridge',
                  'and it states a continuous form rather than a row of objects',
                  'it states %r' % forms.get('CANYON'))

        # ------------------------------------------------ the silhouette, place by place
        print()
        print('  THE SILHOUETTE OF EVERY PLACE, BY THE SAME THREE RULES')
        print('      %-10s %-8s %6s %6s %6s' % ('place', 'form', 'gaps', 'step', 'seam'))
        seen = {}
        for k in keys:
            if forms.get(k) == 'none':
                continue
            prof = page.evaluate("(k) => window.__probe.road.skylineProfile(k)", k)
            # an EMPTY column is reported as the sprite's own height, so the harness asks
            # the engine what that is rather than typing the number in
            height = page.evaluate("(k) => window.__probe.road.skylineSize(k).h", k)
            m = measure(prof, height)
            seen[k] = m
            print('      %-10s %-8s %6d %6d %6d'
                  % (k, forms.get(k), m['gaps'], m['step'], m['seam']))

        can = seen.get('CANYON')
        others = {k: v for k, v in seen.items() if k != 'CANYON'}

        print()
        print('  THE CANYON, AGAINST WHAT A CONTINUOUS FORM HAS TO BE')
        res.check(can is not None, 'the canyon has a silhouette to read')
        if can:
            res.check(can['gaps'] == 0,
                      'no column of the wall reaches the ground - it has no gaps in it',
                      '%d columns of sky' % can['gaps'])
            res.check(can['step'] <= STEP_LIMIT,
                      'and the crest walks rather than jumping, so it is not a comb',
                      'the largest step is %d px against a limit of %d'
                      % (can['step'], STEP_LIMIT))
            res.check(can['seam'] <= STEP_LIMIT,
                      'and it closes on itself, so the tiled seam is not a cliff',
                      'the ends differ by %d px' % can['seam'])

        # ------------------------------------------------ and the controls
        print()
        print('  AND THE SAME RULES ON EVERY OTHER PLACE, WHICH IS THE FALSIFICATION')
        # A check that passes everywhere measures nothing. IT IS THE THREE RULES TOGETHER
        # THAT DISCRIMINATE, AND NO ONE OF THEM DOES IT ALONE - which was measured rather
        # than assumed, and the first version of this check asserted the wrong one.
        #
        #   the STEP alone does not separate them. A peak line overlaps its neighbours by
        #   construction, so MOUNTAIN and TUNDRA come in at 3 and 2 px - inside the limit,
        #   and they are still rows of objects.
        #   the GAPS alone do not either, for the same reason: both of those measure zero.
        #   the SEAM is what only a CLOSED WALK can pass while having no gaps, because
        #   nothing else plans the two ends of the tile together. MOUNTAIN misses it by 60
        #   px and TUNDRA by 9.
        #
        # So each control has to break at least one rule, and the canyon is the only place
        # on the board that passes all three at once.
        def broken(v):
            out = []
            if v['gaps'] != 0:
                out.append('gaps')
            if v['step'] > STEP_LIMIT:
                out.append('step')
            if v['seam'] > STEP_LIMIT:
                out.append('seam')
            return out

        for k, v in others.items():
            print('      %-10s breaks %s' % (k, ','.join(broken(v)) or 'NOTHING'))
        clean = [k for k, v in others.items() if not broken(v)]
        res.check(not clean,
                  'no free-standing horizon passes all three, so the rules measure something',
                  'these passed as continuous: %s' % clean)
        # and the seam is named on its own, because it is the rule doing the separating
        res.check(all(v['seam'] > STEP_LIMIT for v in others.values() if v['gaps'] == 0),
                  'and the ones that are already gapless fail on the seam, which is the walk',
                  str({k: v['seam'] for k, v in others.items() if v['gaps'] == 0}))

        # ------------------------------------------------ the band stands taller
        print()
        print('  AND A WALL CANNOT STAND BEHIND ITSELF')
        # Owner, 2026-09-01, having driven it: the skyline should only be as high as the
        # canyon walls. IT WAS SIX TIMES HIGHER, because the height was a number typed
        # into the table - 2.4 of the ordinary band, 281 pixels, against a tallest wall of
        # 47. The horizon read as a mountain range standing behind a canyon.
        #
        # A RATIO CANNOT ANSWER THAT QUESTION, which is why the first version of this
        # check passed on the build the owner rejected: it asserted the band was TALLER
        # than an ordinary horizon, which was true and was the fault. The two heights are
        # compared in pixels now, each computed the way it is actually drawn.
        vs = page.evaluate("""() => {
          const R = window.__probe.road, out = {};
          for(const k of R.BIOME_KEYS()) out[k] = R.skylineVsWall(k);
          return out;
        }""")
        can_vs = vs['CANYON']
        print('      canyon: skyline %.1f px against a tallest wall of %.1f px'
              % (can_vs['sky'], can_vs['wall']))
        res.check(can_vs['wall'] is not None,
                  'the canyon has roadside walls to measure against')
        if can_vs['wall']:
            res.check(can_vs['sky'] <= can_vs['wall'] * 1.05,
                      'the skyline stands no higher than the walls in front of it',
                      'skyline %.1f px against wall %.1f' % (can_vs['sky'], can_vs['wall']))
            # AND NOT NOTHING EITHER. A cap satisfied by drawing no horizon at all would
            # pass the line above and lose the thing that makes the place a canyon.
            res.check(can_vs['sky'] > can_vs['wall'] * 0.5,
                      'and it is still there, rather than capped away to nothing',
                      'skyline %.1f px against wall %.1f' % (can_vs['sky'], can_vs['wall']))
        rises = page.evaluate("""() => {
          const R = window.__probe.road, out = {};
          for(const k of R.BIOME_KEYS()) out[k] = R.skyRise(k);
          return out;
        }""")
        res.check(all(v == 1 for k, v in rises.items() if k != 'CANYON'),
                  'and nothing else changed its band at all',
                  str(rises))
        res.check(rises['CANYON'] != 1,
                  'while the canyon derives its own rather than taking the default',
                  'it derived %r' % rises['CANYON'])

        # ------------------------------------------------ terrain
        print()
        print('  A ROAD THAT TURNS CONSTANTLY AND CLIMBS LITTLE')
        shapes = page.evaluate("""() => {
          const R = window.__probe.road, out = {};
          for(const k of R.BIOME_KEYS()) out[k] = R.roadShape(k);
          return out;
        }""")
        cs = shapes['CANYON']
        print('      CANYON  bend %.2f  hill %.2f' % (cs['bend'], cs['hill']))
        res.check(cs['bend'] > cs['hill'] + 0.3,
                  'the canyon bends far more than it climbs',
                  'bend %.2f against hill %.2f' % (cs['bend'], cs['hill']))
        # THE RULING'S OWN WARNING: it must not become a corridor nobody can drive. The
        # corner cap in this renderer is a limit rather than a taste, so the canyon stays
        # under the one place that already sits at the top of the range.
        res.check(cs['bend'] < shapes['MOUNTAIN']['bend'],
                  'and it stays under the mountain, which is the top of the drivable range',
                  'canyon %.2f, mountain %.2f' % (cs['bend'], shapes['MOUNTAIN']['bend']))
        twins = [k for k, v in shapes.items()
                 if k != 'CANYON' and v['bend'] >= 0.85 and v['hill'] <= 0.50]
        res.check(not twins,
                  'and nothing else on the board is that pair, which is why it is a place',
                  'these are: %s' % twins)

        # ------------------------------------------------ climate
        print()
        print('  AND IT IS DRY, BECAUSE A SLOT CANYON IS CUT IN DESERT ROCK')
        clim = page.evaluate("() => window.__probe.road.climateFor('CANYON')")
        print('      temp %.2f  precip %.2f  rain %.3f  snow %.3f  canSnow %s'
              % (clim['temp'], clim['precip'], clim['rain'], clim['snow'], clim['canSnow']))
        allclim = page.evaluate("""() => {
          const R = window.__probe.road, out = {};
          for(const k of R.BIOME_KEYS()) out[k] = R.climateFor(k).precip;
          return out;
        }""")
        wetter = [k for k, v in allclim.items()
                  if k not in ('CANYON', 'DESERT', 'TUNNEL') and v <= clim['precip']]
        res.check(not wetter,
                  'only the desert is drier, and the tunnel has no weather at all',
                  'these are no wetter: %s' % wetter)
        res.check(not clim['canSnow'],
                  'and it cannot snow there at its own temperature',
                  'canSnow %r' % clim['canSnow'])

        errs = page.evaluate("() => window.__probe.errors")
        res.check(not errs, 'no page errors', '; '.join(errs[:3]))
        browser.close()
    httpd.shutdown()

    print()
    if res.fails:
        print('FAILED: ' + '; '.join(res.fails))
        return 1
    print('all checks passed')
    print('  what the wall LOOKS like is not measured here - see tools/biome-shot.py')
    return 0


sys.exit(main())
