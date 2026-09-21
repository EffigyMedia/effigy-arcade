#!/usr/bin/env python3
"""LAND GROW PROOF - a mountain rises out of the ground, and a canyon does not.

    .venv/Scripts/python tools/land-grow-proof.py

RLG-303. Owner, 2026-09-20, shown a capture of driving at a mountain biome from a desert:
'that is ugly... Notice how it's disconnected. It doesn't read as a mountain. It's supposed
to read as if you're driving into a mountain biome with a mountain on one side and a valley
on the other.'

WHAT WAS WRONG WAS THAT NOTHING LED UP TO IT. `bioMix` runs 0 to 1 across a boundary and
everything that changes COLOUR reads it, while nothing that changes SHAPE did - so the
ground blended and the wall, the drop and the face all switched on at a line. `bioGrow` is
the same ramp for shape, and it is the PLACE'S, declared the way `face` is.

THE TRAP THE RULING NAMES IS THE CANYON, and it is half of this proof. Applied to every
walled place a canyon's walls would grow too, and its boundary face - which the owner
accepted - would stand in front of walls that are not yet full height. So the canyon is run
through the identical measurement and has to come out UNCHANGED.

HOW IT IS MEASURED, AND WHY THIS WAY. Comparing two slices in one frame cannot settle it:
further along the ramp is also further away, so the two effects fight. Instead ONE slice is
read at two settings of `GROW_BAND` - the same slice, the same distance, the same frame -
with the band at its default and then at 1, which is the switch-at-a-line the ruling
replaced. Everything else is held.

    THE WALL, from `wallTrace`, which the wall pass writes as it paints: the top edge of
    the band on screen, per slice. Just past the boundary the grown wall's top has to sit
    far LOWER on screen than the switched one's.

    THE DROP, from `dropFloorAt`, which is `hazard-test`'s own instrument with one number
    added: `deep` is how far below its own rim this slice's floor was painted, in pixels,
    which is the two numbers the drop pass drew subtracted. `floorN` answers whether the
    plane is below the road AT ALL, which is what RLG-278 needed and cannot say how far.
    A valley that has not deepened yet has a floor close under its rim.

WHAT IT CANNOT DO. It cannot say whether 72 segments is the right run, or whether the land
now reads as land. Both are the owner's on a device, and `GROW_BAND` is the one constant
that moves it.

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

# How far past the boundary the slice that is read sits, in segments. It has to be well
# inside the ramp and well inside the draw: at the default band of 72 a slice 12 segments
# in stands at a sixth of full height, which is a difference no rounding can hide.
INTO = 12

# How near the boundary has to come before anything is measured, in segments. The setter
# places it at the far end of the draw, and the DROP cannot be read out there: `dropFloorAt`
# asks which floor quad covers a slice's rim row, and a slice 150 off has its rim within a
# pixel of the horizon, where every floor in the frame is below it and the answer is null
# whatever the depth. `hazard-test` reads slice 40 for the same reason. So the boundary is
# driven to within sight of the car and the slice read lands in the near field with it.
NEAR = 60


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


READ = """(a) => {
  const R = window.__probe.road;
  R.wallModel({ grow: a.band });
  return new Promise(res => {
    requestAnimationFrame(() => { requestAnimationFrame(() => {
      const here = Math.floor(R.roadPlan().pos / 200);
      const lg = R.landGrow(0, a.key);
      const want = lg.edge - here + a.into;
      /* ---- THE SLICE ASKED FOR MAY NOT HAVE BEEN DRAWN --------------------
         A slice hidden behind a crest paints nothing, and the road is generated
         fresh per load, so a fixed index reads null about one run in several and
         that is not a finding. Take the nearest slice that WAS painted instead,
         and hand the same one to the second reading so the two are comparable. */
      const at = (m) => {
        const w = R.wallTrace().filter(t => t[0] === m);
        const f = R.dropFloorAt(m);
        return (w.length && (a.needFloor ? (f && f.deep !== null) : true)) ? { w: w, f: f } : null;
      };
      let n = a.n === undefined ? null : a.n, hit = n === null ? null : at(n);
      for(let k = 0; n === null && k <= 8; k++){
        for(const d of (k ? [k, -k] : [0])){
          const got = at(want + d);
          if(got){ n = want + d; hit = got; break; }
        }
      }
      if(n === null){ n = want; hit = null; }
      res({ band: a.band, n: n, edgeIn: lg.edge - here,
            grow: R.landGrow(here + n, a.key).grow,
            wallTop: hit ? Math.min.apply(null, hit.w.map(t => t[2])) : null,
            walls: hit ? hit.w.length : 0,
            floor: hit ? hit.f : R.dropFloorAt(n),
            horizon: Math.round(R.horizon()) });
    }); });
  });
}"""


def read_at(page, key, band, into=None, n=None, need_floor=True):
    a = {'key': key, 'band': band, 'into': INTO if into is None else into,
         'needFloor': need_floor}
    if n is not None:
        a['n'] = n
    return page.evaluate(READ, a)


def arrive(page, key):
    """Place the boundary and drive at it until it is inside the drawn road."""
    page.evaluate("""(k) => {
      const R = window.__probe.road;
      R.setTimed(false);
      /* THE RUN MAY ALREADY BE IN THE PLACE BEING MEASURED, and `startBiomeChange`
         rolls a DIFFERENT one when asked for the place it is already in - so the
         measurement would be of the mountain being LEFT. The board is put on a
         desert first, which is also the arrival the owner's report was about. */
      R.setBiomePair('DESERT', 'DESERT');
      R.startBiomeChange(k);
      R.setSpd(12000); R.holdSpd(12000);
    }""", key)
    until(page, """(a) => {
      const R = window.__probe.road;
      const here = Math.floor(R.roadPlan().pos / 200);
      return R.landGrow(0, a.key).edge - here <= a.near;
    }""", timeout=20000, arg={'key': key, 'near': NEAR})
    page.evaluate("() => window.__probe.road.holdSpd(0)")
    page.wait_for_timeout(400)


def run(page, res, key, grows):
    print()
    print('  %s' % ('A MOUNTAIN GROWS OUT OF THE GROUND' if grows
                    else 'AND A CANYON DOES NOT, WHICH IS THE TRAP'))
    arrive(page, key)
    grown = read_at(page, key, 72, need_floor=grows)
    switched = read_at(page, key, 1, n=grown['n'], need_floor=grows)
    print('      the boundary is %d segments off; the slice painted and read is %d past it'
          % (grown['edgeIn'], grown['n'] - grown['edgeIn']))
    print('      %-8s band 72 -> grow %.3f, wall top y %s, floor %s px under its rim'
          % (key, grown['grow'], grown['wallTop'], grown['floor'] and grown['floor']['deep']))
    print('      %-8s band  1 -> grow %.3f, wall top y %s, floor %s px under its rim'
          % (key, switched['grow'], switched['wallTop'],
             switched['floor'] and switched['floor']['deep']))

    res.check(grown['walls'] and switched['walls'],
              '%s: the wall pass painted this slice at both settings' % key,
              '%r and %r bands' % (grown['walls'], switched['walls']))
    if grown['walls'] and switched['walls']:
        drop = grown['wallTop'] - switched['wallTop']
        if grows:
            res.check(grown['grow'] < 0.30,
                      '%s: the land is a fraction of its height this soon in' % key,
                      'grow %.3f' % grown['grow'])
            res.check(drop > 20,
                      '%s: and the PAINTED wall stands far lower for it' % key,
                      'the top edge moved %.1f px, which is not a rise' % drop)
        else:
            res.check(grown['grow'] == 1.0,
                      '%s: the land is at full height at its own boundary' % key,
                      'grow %.3f' % grown['grow'])
            res.check(abs(drop) <= 1.5,
                      '%s: and the painted wall does not move when the band does' % key,
                      'the top edge moved %.1f px' % drop)

    gf, sf = grown['floor'], switched['floor']
    if grows:
        res.check(gf and sf and gf['deep'] is not None and sf['deep'] is not None,
                  '%s: a floor was painted under this slice at both settings' % key,
                  '%r and %r' % (gf, sf))
        if gf and sf and gf['deep'] is not None and sf['deep'] is not None:
            res.check(sf['deep'] > 150 and gf['deep'] < sf['deep'] * 0.35,
                      '%s: and the valley has not fallen away yet either' % key,
                      '%.1f px under the rim against a full %.1f' % (gf['deep'], sf['deep']))
        # ---- AND THE BAND ENDS WHERE IT SAYS IT DOES. One band past the boundary the
        # ramp is complete, so the grown land and the switched land are the SAME land -
        # which is the only reading that can tell a ramp from a permanent shortening.
        endG = read_at(page, key, 72, into=72)
        endS = read_at(page, key, 1, n=endG['n'], need_floor=True)
        print('      one band in (%d past): %s px under the rim grown, %s px switched'
              % (endG['n'] - endG['edgeIn'], endG['floor'] and endG['floor']['deep'],
                 endS['floor'] and endS['floor']['deep']))
        if endG['floor'] and endS['floor'] and endG['floor']['deep'] is not None:
            res.check(abs(endG['floor']['deep'] - endS['floor']['deep']) <= 1.0,
                      '%s: and one band in the two are the same valley' % key,
                      '%.1f px against %.1f' % (endG['floor']['deep'], endS['floor']['deep']))
        res.check(endG['wallTop'] is not None and endS['wallTop'] is not None
                  and abs(endG['wallTop'] - endS['wallTop']) <= 1.0,
                  '%s: and the same hillside' % key,
                  'wall tops %r and %r' % (endG['wallTop'], endS['wallTop']))
    else:
        res.check(gf is None or gf['deep'] is None,
                  '%s: has no drop to deepen, so nothing there moves either' % key,
                  '%r' % gf)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--headed', action='store_true')
    args = ap.parse_args()
    console_utf8()
    res = Results()
    httpd, port = serve(ROOT)
    print('land-grow-proof  .  the land rises where it is the place\'s to rise')
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

        # ---------------------------------------------- the ramp itself
        print()
        print('  THE RAMP IS THE PLACE\'S, AND IT STARTS AT ZERO')
        ramp = page.evaluate("""() => {
          const R = window.__probe.road;
          R.setTimed(false); R.setSpd(0); R.holdSpd(0);
          R.wallModel({ grow: 72 });
          R.setBiomePair('DESERT', 'DESERT');
          R.startBiomeChange('MOUNTAIN');
          const e = R.landGrow(0, 'MOUNTAIN').edge, out = { edge: e, m: {}, c: {} };
          for(const d of [0, 18, 36, 54, 72, 150]){
            out.m[d] = R.landGrow(e + d, 'MOUNTAIN').grow;
            out.c[d] = R.landGrow(e + d, 'CANYON').grow;
          }
          return out;
        }""")
        print('      segments past the boundary: ' + '  '.join('%d' % d for d in (0, 18, 36, 54, 72, 150)))
        print('      MOUNTAIN                  : '
              + '  '.join('%.2f' % ramp['m'][str(d)] for d in (0, 18, 36, 54, 72, 150)))
        print('      CANYON                    : '
              + '  '.join('%.2f' % ramp['c'][str(d)] for d in (0, 18, 36, 54, 72, 150)))
        res.check(ramp['m']['0'] == 0, 'the mountain is nothing at all at the line',
                  '%r' % ramp['m']['0'])
        res.check(0.24 < ramp['m']['18'] < 0.26 and 0.49 < ramp['m']['36'] < 0.51,
                  'and it climbs evenly rather than easing on to a step',
                  '%r' % ramp['m'])
        res.check(ramp['m']['72'] == 1 and ramp['m']['150'] == 1,
                  'and it is the whole mountain one band in, and stays',
                  '%r' % ramp['m'])
        # THE CANYON'S ROW IS PRINTED AND NOT ASSERTED, and that is deliberate. It reads
        # 1 here whatever the canyon declares, because the crossing being measured is a
        # MOUNTAIN's: a place that is neither end of the live pair has no boundary to
        # grow out of. Asserting it would be a check that passes with the defect in -
        # watched doing exactly that. The canyon is measured on its OWN crossing below.

        run(page, res, 'MOUNTAIN', True)
        run(page, res, 'CANYON', False)

        page.evaluate("() => window.__probe.road.wallModel({ grow: 72 })")
        errs = page.evaluate("() => window.__probe.errors")
        res.check(not errs, 'no page errors', str(errs))
        browser.close()
    httpd.shutdown()

    print()
    if res.fails:
        print('FAILED: ' + '; '.join(res.fails))
        return 1
    print('PASSED: the mountain grows out of the ground and the canyon is untouched')
    return 0


if __name__ == '__main__':
    sys.exit(main())
