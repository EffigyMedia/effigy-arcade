#!/usr/bin/env python3
"""
COAST TEST - nothing stands in the sea, and the land beside it has palms and houses on it.

    .venv/Scripts/python tools/coast-test.py
    .venv/Scripts/python tools/coast-test.py --shots

RLG-059. The owner, 2026-08-30: "we need to make sure that scenery objects aren't generated in the
side with the ocean and we might want random palm trees and beach houses on the opposing side."

WHY IT READS A COUNTER AND NOT THE PICTURE. The scenery pass places from a hash of the segment, so
what is on screen at any instant is whatever happened to be rolled for the segments in view. A pixel
test for "no palm in the water" would have to find a palm-coloured pixel inside a sea-coloured
region, at two pixels wide, in a frame where the sky, the road and the cars are all moving. The
engine counts what it actually DREW, per side, at the point of drawing - so this reads the outcome
of the real pass rather than a second copy of its rules.

AND THE SPRITES ARE READ OFF THEIR OWN CANVAS, not off a live frame. A live-frame diff is not a
visual test (RLG-053): between two frames of this game the whole picture moves. `sceneryProbe` runs
the real builders into a blank canvas and reports where the ink is, which is how a beach house is
shown to be house-shaped and to have its windows lit.

WHAT WOULD CATCH THE DEFECT. Take the two `continue` lines out of `drawScenery` and the mirror's own
loop, and the seaward counts go from 0 to a number about equal to the landward one. That was watched
failing before this was believed.

Exit code 0 if every check passed, 1 otherwise.
"""

import argparse
import base64
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

/* The mirror pane's own pixels, split left and right of its centre line, counting how many of
   them are water. The pane's geometry belongs to the shell rather than to the engine, so it is
   repeated here the way mirror-shot.py repeats it. */
window.__probe.mirrorWater = function(){
  var c = document.querySelector('canvas');
  var r = c.getBoundingClientRect();
  var dpr = c.width / r.width;
  var mw = Math.min(r.width * 0.62, 250), mh = 44;
  var mx = (r.width - mw) / 2, my = 6;
  var g = c.getContext('2d');
  /* the lower two thirds only: the top of the glass is sky and skyline */
  var y0 = Math.round((my + mh*0.34) * dpr), hh = Math.round(mh*0.62 * dpr);
  var x0 = Math.round(mx * dpr), ww = Math.round(mw * dpr);
  var d = g.getImageData(x0, y0, ww, hh).data;
  var left = 0, right = 0, half = ww/2;
  for(var y = 0; y < hh; y++){
    for(var x = 0; x < ww; x++){
      var i = (y*ww + x)*4;
      var R = d[i], G = d[i+1], B = d[i+2];
      /* the sea is dark and decidedly blue: half again more blue than red */
      if(B > 55 && B < 150 && B > R*1.5 && G > R && G < B) {
        if(x < half) left++; else right++;
      }
    }
  }
  return { left: left, right: right, area: ww*hh };
};


/* The band just under the horizon, split left and right of the road's vanishing point. It is the
   strip where the road has stopped being drawn and the far field takes over, which is where a coast
   used to run out of water. */
window.__probe.farBand = function(hz, gapY, split){
  var c = document.querySelector('canvas');
  var r = c.getBoundingClientRect();
  var dpr = c.width / r.width;
  var g = c.getContext('2d');
  /* ONLY THE GAP ITSELF. The band between the horizon and the furthest drawn slice is the strip
     this feature paints; below it the road pass paints its own sea, which would answer the
     question with the feature removed. Sampling wider made the check pass two runs in three
     without the code. */
  var y0 = Math.round((hz + 2) * dpr), hh = Math.max(1, Math.round((gapY - hz - 4) * dpr));
  var d = g.getImageData(0, y0, c.width, hh).data;
  /* SPLIT AT THE SHORELINE, NOT AT THE MIDDLE OF THE SCREEN. On a bend the road's vanishing point
     is well off centre, so a coast on the left can legitimately have water to the right of the
     centre line. What must never happen is water on the LANDWARD side of the shore itself, which
     is what an inverted fill would produce. */
  var half = (split === undefined ? c.width/2 : split * dpr);
  var left = 0, right = 0;
  for(var y = 0; y < hh; y++){
    for(var x = 0; x < c.width; x++){
      var i = (y*c.width + x)*4;
      var R = d[i], G = d[i+1], B = d[i+2];
      if(B > 55 && B < 160 && B > R*1.4 && G > R && G < B){ if(x < half) left++; else right++; }
    }
  }
  return { left: left, right: right, area: c.width*hh };
};


/* THE WATER'S EDGE, ROW BY ROW. A staircase and a line differ in one number: how far the edge moves
   between two neighbouring rows. A line moves by its slope every row; a staircase does not move at
   all for the height of a slice and then jumps by the slope times that height. So this returns the
   edge's x for each row and lets the check compare the biggest step against the average one. */
window.__probe.shoreEdge = function(y0, y1, side){
  var c = document.querySelector('canvas');
  var r = c.getBoundingClientRect();
  var dpr = c.width / r.width;
  var g = c.getContext('2d');
  var top = Math.round(y0*dpr), hh = Math.round((y1-y0)*dpr);
  var d = g.getImageData(0, top, c.width, hh).data;
  var xs = [];
  var isSea = function(i){
    var R = d[i], G = d[i+1], B = d[i+2];
    return B > 55 && B < 170 && B > R*1.4 && G > R && G < B;
  };
  for(var y = 0; y < hh; y++){
    var found = -1;
    if(side < 0){
      /* water on the left: walk in from x=0 to the first pixel that is not water */
      if(!isSea((y*c.width)*4)) { xs.push(null); continue; }
      for(var x = 1; x < c.width; x++){ if(!isSea((y*c.width + x)*4)){ found = x; break; } }
    } else {
      if(!isSea((y*c.width + c.width-1)*4)) { xs.push(null); continue; }
      for(var x = c.width-2; x >= 0; x--){ if(!isSea((y*c.width + x)*4)){ found = x; break; } }
    }
    xs.push(found < 0 ? null : found/dpr);
  }
  return xs;
};

window.__probe.shot = function(){ return document.querySelector('canvas').toDataURL('image/png'); };
window.__probe.mirrorShot = function(zoom){
  var c = document.querySelector('canvas');
  var r = c.getBoundingClientRect();
  var dpr = c.width / r.width;
  var mw = Math.min(r.width * 0.62, 250), mh = 44;
  var mx = (r.width - mw) / 2, my = 6;
  var out = document.createElement('canvas');
  out.width = Math.round(mw * zoom); out.height = Math.round(mh * zoom);
  var g = out.getContext('2d');
  g.imageSmoothingEnabled = false;
  g.drawImage(c, Math.round((mx - 3) * dpr), Math.round((my - 3) * dpr),
                 Math.round((mw + 6) * dpr), Math.round((mh + 6) * dpr),
                 0, 0, out.width, out.height);
  return out.toDataURL('image/png');
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
        print(('  ok    ' if ok else '  FAIL  ') + label + ('' if ok else '   [' + str(detail) + ']'))
        if not ok:
            self.fails.append(label)


def set_time(page, want):
    for _ in range(8):
        if page.eval_on_selector('[data-act="time"] b', 'el => el.textContent').strip() == want:
            return True
        page.click('[data-act="time"]')
        page.wait_for_timeout(70)
    return False


def save(page, fn, out, name):
    url = page.evaluate(fn)
    (out / name).write_bytes(base64.b64decode(url.split(',', 1)[1]))
    print('      wrote %s' % (out / name))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--headed', action='store_true')
    ap.add_argument('--shots', action='store_true', help='also write captures')
    ap.add_argument('--out', default=None)
    args = ap.parse_args()
    console_utf8()
    res = Results()
    out = Path(args.out) if args.out else ROOT / '_coast'
    if args.shots:
        out.mkdir(parents=True, exist_ok=True)
    httpd, port = serve(ROOT)
    print('coast-test  .  nothing stands in the sea')
    with sync_playwright() as p:
        browser = launch_chromium(p, headless=not args.headed)
        page = browser.new_page(viewport={'width': 480, 'height': 900})
        page.add_init_script(INIT)
        boot(page, 'http://127.0.0.1:%d/%s' % (port, GAME))
        try:
            until(page, '() => navigator.serviceWorker && navigator.serviceWorker.controller', timeout=5000)
            page.wait_for_timeout(1200)
        except Exception:
            pass
        until(page, '!!window.__probe.road', timeout=10000)
        page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
        page.click('[data-act="play"]')
        page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
        set_time(page, 'MIDDAY')
        page.click('[data-act="drive"]')
        page.wait_for_timeout(1800)

        api = page.evaluate('() => Object.keys(window.__probe.road)')
        res.check('scenerySides' in api and 'sceneryProbe' in api,
                  'the engine reports what the roadside drew')

        # ------------------------------------------------ a coast, driven
        page.evaluate("""() => { const R = window.__probe.road;
          R.setBiomePair('COASTAL','COASTAL'); R.setWet(0); R.setSnow(0); R.setPool(0); }""")
        page.evaluate("() => window.__probe.road.setSpd(window.__probe.road.MAX_SPD*0.45)")
        page.wait_for_timeout(1500)
        page.evaluate('() => window.__probe.road.resetScenerySides()')
        page.wait_for_timeout(1800)
        s = page.evaluate('() => window.__probe.road.scenerySides()')
        print('      seaSide %+d   windscreen L%d R%d   glass L%d R%d'
              % (s['sea'], s['left'], s['right'], s['mLeft'], s['mRight']))
        sea_w = s['left'] if s['sea'] < 0 else s['right']
        land_w = s['right'] if s['sea'] < 0 else s['left']
        sea_m = s['mLeft'] if s['sea'] < 0 else s['mRight']
        land_m = s['mRight'] if s['sea'] < 0 else s['mLeft']
        # ---- THE SEAWARD SIDE CARRIES BOATS NOW, AND NOTHING ELSE. This asked for
        # NOTHING at all until the owner directed boats onto the water as scenery
        # (RLG-059), and the invariant it was really protecting was never "the sea is
        # empty" - it was "no palm stands in the water". That is what it asks now, so the
        # check keeps its teeth instead of being deleted for being in the way.
        BOAT_SPECS = {'COASTAL_BOATS', 'COASTAL_SHIPS'}
        print('      on the water: %s   in the glass: %s'
              % (s.get('seaKeys'), s.get('mSeaKeys')))
        aground = [k for k in (s.get('seaKeys') or {}) if k not in BOAT_SPECS]
        res.check(not aground,
                  'nothing but boats is drawn on the seaward side',
                  'these stood in the water: %s' % aground)
        res.check(sea_w > 0,
                  'and there ARE boats on it, which is what the owner asked for',
                  'the seaward side drew nothing at all')
        res.check(land_w > 20, 'the landward side is populated', 'drew %d' % land_w)
        m_aground = [k for k in (s.get('mSeaKeys') or {}) if k not in BOAT_SPECS]
        res.check(not m_aground,
                  'nothing but boats is drawn on the seaward side in the glass',
                  'these stood in the water: %s' % m_aground)
        res.check(land_m > 0, 'the glass shows the landward side', 'drew %d' % land_m)

        # ------------------------------------------------ and the water is in the glass
        page.evaluate("() => window.__probe.road.setSpd(0)")
        page.wait_for_timeout(400)
        mw = page.evaluate('() => window.__probe.mirrorWater()')
        print('      mirror water pixels  left %d  right %d  (of %d)'
              % (mw['left'], mw['right'], mw['area']))
        wet_side = mw['left'] if s['sea'] < 0 else mw['right']
        dry_side = mw['right'] if s['sea'] < 0 else mw['left']
        res.check(wet_side > 200, 'the glass has water in it', str(mw))
        res.check(wet_side > dry_side * 3, 'and it is on the same side as the coast', str(mw))

        # ------------------------------- and it does not stop where the road does
        hz = page.evaluate('() => window.__probe.road.horizon()')
        # THE BAND ONLY EXISTS WHERE THE ROAD STOPS SHORT OF THE HORIZON. On a rise the furthest
        # slice sits above the horizon line and there is no gap to paint - a real state, and not
        # one this check can read anything into. So it drives until a gap opens.
        # AND IT HOPS RATHER THAN DRIVES. Driving covered a few hundred segments in ten seconds
        # and missed a gap about one run in three; a jump moves the car thousands of segments a
        # step, so the search covers a length of road no amount of waiting would.
        gap = None
        page.evaluate('() => window.__probe.road.setSpd(0)')
        for i in range(40):
            page.wait_for_timeout(90)
            f = page.evaluate('() => window.__probe.road.farSea()')
            if f.get('roadTop') and f['roadTop'] > hz + 10:
                gap = f
                break
            page.evaluate('(n) => window.__probe.road.jumpTo(n)',
                          200 * 200 * (i + 3))
        res.check(gap is not None, 'a gap between the road and the horizon was reached')
        gap_y = gap['roadTop'] if gap else hz + 10
        split = gap['shore'] if gap and gap.get('shore') is not None else None
        fb = page.evaluate('([h, g, sp]) => window.__probe.farBand(h, g, sp === null ? undefined : sp)',
                           [hz, gap_y, split])
        print('      far band water  seaward %d  landward %d  (of %d px, horizon %s to %s)'
              % (fb['right'] if s['sea'] > 0 else fb['left'],
                 fb['left'] if s['sea'] > 0 else fb['right'], fb['area'], hz, gap_y))
        far_wet = fb['left'] if s['sea'] < 0 else fb['right']
        far_dry = fb['right'] if s['sea'] < 0 else fb['left']
        print('      far band decision: %s' % gap)
        # A COUNT, NOT A FRACTION OF THE BAND. How much of the strip is water depends on
        # where the shoreline happens to cross it - on a bend the sea is a narrow wedge and
        # 18 per cent is a correct picture. Measured across runs: 23, 40, 45 and 67 per
        # cent, all of them right. What separates "the sea reaches the horizon" from "it
        # does not" is whether there is water up there at all, and with the far band removed
        # this reads 0 to 40 pixels against thousands.
        res.check(far_wet > 500, 'the sea reaches the horizon', str(fb))
        res.check(far_wet > far_dry * 6, 'and none of it on the landward side of the shore', str(fb))

        # ------------------------------------- and its edge is a line, not a staircase
        # Measured well below the horizon, where a slice is tall enough for a step to exist at
        # all: near the vanishing point a slice is a pixel high and the two shapes agree.
        edge = page.evaluate('([a, b, sd]) => window.__probe.shoreEdge(a, b, sd)',
                             [hz + 40, hz + 130, s['sea']])
        # ---- CURVATURE, NOT STEP, AND THE DIFFERENCE MATTERS ---------------------
        # The first version took the largest change in x between two neighbouring rows. That
        # is only meaningful while the edge is STEEPER than 45 degrees. Where the shoreline
        # runs shallow across the screen - which is exactly what a steeply falling road does
        # to it - one row spans a hundred pixels of x on a perfectly straight edge, and the
        # check reported a 57px "staircase" on a picture that is a clean diagonal. It failed
        # about one run in four and an audit wrote it up as a defect in the game.
        #
        # What separates a line from a staircase is not how fast it moves, it is whether it
        # BENDS. A straight edge at any angle has near-zero second difference; a staircase
        # has a spike at every step. Rows where the edge has left the frame are dropped
        # first, because a clamped value is not a measurement.
        wide = page.evaluate('() => document.querySelector("canvas").getBoundingClientRect().width')
        # AND ONLY BETWEEN ROWS THAT ACTUALLY TOUCH. Dropping the rows where the edge has
        # left the frame leaves GAPS, and comparing across a gap treats two rows thirty
        # apart as neighbours - which reported a 119px "bend" where the shoreline had simply
        # gone off the right of the screen and come back. The profile is cut into contiguous
        # runs first, and each run is measured on its own.
        kept = [(i, x) for i, x in enumerate(edge) if x is not None and 3 < x < wide - 3]
        runs, cur = [], []
        for i, x in kept:
            if cur and i != cur[-1][0] + 1:
                runs.append([v for _, v in cur]); cur = []
            cur.append((i, x))
        if cur: runs.append([v for _, v in cur])
        runs = [r for r in runs if len(r) >= 6]
        run = max(runs, key=len) if runs else []
        # ---- AN OUTLIER AGAINST THE EDGE'S OWN TYPICAL STEP ----------------------
        # Four metrics were tried here and three of them were wrong in the same way: they
        # assumed something about the edge's ANGLE. The largest step between rows is only
        # meaningful while the edge is steeper than 45 degrees - a straight shoreline running
        # shallow reported a 121px "staircase" and an audit wrote it up as a defect in the
        # game. A second difference is large on any shallow edge and on a real bend. A local
        # line fit handles both but cannot separate a staircase from a CREST, where the brow
        # legitimately hides the slices between two shorelines and the edge steps once.
        #
        # What a staircase is, stated without reference to angle: an edge whose steps are
        # mostly nothing and occasionally a jump. So the test is against the edge's OWN
        # typical step - the median - and what it counts is outliers. A smooth edge at any
        # angle has near-constant steps and no outliers; a crest has one; a staircase has one
        # every few rows, for ever.
        steps_all = []
        for r in runs:
            steps_all.append([abs(r[i+1] - r[i]) for i in range(len(r)-1)])
        flat = sorted(v for st in steps_all for v in st)
        median = flat[len(flat)//2] if flat else 0
        limit = max(6.0, 4.0 * median)
        outliers = sum(1 for st in steps_all for v in st if v > limit)
        total = len(flat)
        mean_step = (sum(flat)/total) if total else 0
        worst_bend = max(flat) if flat else 0
        print('      shore edge: %d rows in %d unbroken runs, median step %.2f px, '
              'largest %.2f px, %d outliers past %.1f'
              % (sum(len(r) for r in runs), len(runs), median, worst_bend, outliers, limit))
        res.check(sum(len(r) for r in runs) > 22, "the water's edge was found on the screen",
                  '%d rows in %d unbroken runs' % (sum(len(r) for r in runs), len(runs)))
        # one outlier is a crest, which the ground hides and only the water's edge can show
        res.check(outliers <= 2, "the water's edge is a line, not a staircase",
                  '%d of %d steps are outliers past %.1f px, largest %.2f, median %.2f'
                  % (outliers, total, limit, worst_bend, median))

        # ------------------------------------------------ what the coast is made of
        kinds = [page.evaluate('(k) => window.__probe.road.sceneryProbe("COASTAL", k)', k)
                 for k in range(8)]
        for k, pr in enumerate(kinds):
            b = pr['body']
            print('      kind %d  ink %.3f  x %.2f-%.2f  y %.2f-%.2f  lit ink %.4f'
                  % (k, b['ink'], b['x0'], b['x1'], b['y0'], b['y1'], pr['lit']['ink']))
        palms, rocks, houses = kinds[0:4], kinds[4:6], kinds[6:8]
        res.check(all(p['body']['ink'] > 0.005 for p in kinds), 'every kind draws something')
        res.check(all(p['body']['x1'] - p['body']['x0'] < 0.62 for p in palms),
                  'a palm keeps to the narrow band down the middle',
                  str([round(p['body']['x1'] - p['body']['x0'], 3) for p in palms]))
        res.check(all(p['body']['y1'] - p['body']['y0'] > 0.72 for p in palms),
                  'a palm is as tall as its canvas',
                  str([round(p['body']['y1'] - p['body']['y0'], 3) for p in palms]))
        res.check(all(r['body']['y0'] > 0.55 for r in rocks),
                  'a rock is low and on the ground', str([r['body']['y0'] for r in rocks]))
        res.check(all(h['body']['x1'] - h['body']['x0'] > 0.80 for h in houses),
                  'a beach house is as wide as its canvas',
                  str([round(h['body']['x1'] - h['body']['x0'], 3) for h in houses]))
        res.check(all(h['body']['y1'] > 0.98 for h in houses),
                  'and it stands on the ground', str([h['body']['y1'] for h in houses]))
        res.check(all(h['lit']['ink'] > 0.001 for h in houses),
                  'a beach house has lit windows', str([h['lit']['ink'] for h in houses]))
        res.check(all(p['lit']['ink'] == 0 for p in palms + rocks),
                  'a palm and a rock have none', str([p['lit']['ink'] for p in palms + rocks]))
        # the lit sheet must sit INSIDE the body, or a window shines through a wall
        for k, h in zip((6, 7), houses):
            b, l = h['body'], h['lit']
            res.check(l['x0'] >= b['x0'] - 0.01 and l['x1'] <= b['x1'] + 0.01
                      and l['y0'] >= b['y0'] - 0.01 and l['y1'] <= b['y1'] + 0.01,
                      'kind %d: the lit windows are inside the house' % k,
                      '%s in %s' % (l, b))

        if args.shots:
            save(page, '() => window.__probe.shot()', out, 'coast-midday.png')
            save(page, '() => window.__probe.mirrorShot(4)', out, 'coast-midday-mirror.png')
            # and at night, which is the only time the windows are on
            page.evaluate('() => window.__probe.road.setPhase(0.22)')
            page.evaluate("() => window.__probe.road.setSpd(window.__probe.road.MAX_SPD*0.30)")
            page.wait_for_timeout(1200)
            page.evaluate('() => window.__probe.road.setSpd(0)')
            page.wait_for_timeout(300)
            save(page, '() => window.__probe.shot()', out, 'coast-night.png')
            save(page, '() => window.__probe.mirrorShot(4)', out, 'coast-night-mirror.png')

        errs = page.evaluate('() => window.__probe.errors')
        res.check(not errs, 'no page errors', str(errs))
        browser.close()
    httpd.shutdown()
    print(('\n%d check(s) failed' % len(res.fails)) if res.fails else '\nall checks passed')
    return 1 if res.fails else 0


if __name__ == '__main__':
    sys.exit(main())
