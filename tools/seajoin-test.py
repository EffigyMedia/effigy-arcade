#!/usr/bin/env python3
"""
SEA JOIN TEST - the water runs to the horizon as one body.

    .venv/Scripts/python tools/seajoin-test.py
    .venv/Scripts/python tools/seajoin-test.py --headed --shots

RLG-093. Owner, 2026-08-31: the ocean drawn into the background - can the angle it is drawn at be
interpolated from the slice segment's ocean, so it runs to the horizon seamlessly and reads as one
body of water.

THE RULING SUPPOSED AN ANGLE AND THE FAULT WAS A COLOUR. That is why this file measures both, and
why only one of them is a gate. The band above the furthest drawn slice is painted inside `drawSky`,
BEFORE `drawHaze()`, so the distance wash falls on it; the road's own sea is painted after and gets
none, and `seaTone` had no distance term at all. So the water changed colour at the join - by up to
45 in summed RGB, a pale blue meeting a dark green-grey - while its SHAPE was continuous the whole
time.

THE ANGLE WAS MEASURED BEFORE IT WAS BELIEVED. Across 13 bands in 40 places, the straight line
creased by at most 2.0 times the edge's own curvature, which is pixel quantisation. The shoreline is
carried on rather than straightened - it is the right construction, and it is asserted structurally -
but it is not what anybody could see, and this file says so rather than claiming a fix.

AND THE TONE IS SWEPT INSIDE SINGLE FRAMES, NEVER ACROSS RUNS. The road is generated per load and the
day is always turning, so two runs differ in the road, the hour and the sea's own colour at once -
RLG-062's lesson, written after a claim was made and withdrawn on exactly that. `API.seaHaze` moves
the value live, so every comparison here is made on one band at one hour with one thing changed.

Exit code 0 if every check passed, 1 otherwise.
"""

import argparse
import base64
import functools
import http.server
import socketserver
import statistics
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

/* THE WATER'S EDGE, ROW BY ROW, IN THE ENGINE'S OWN PIXELS. The same colour window `coast-test`
   uses, because two definitions of "this pixel is water" is one too many and the far band is drawn
   before the haze so it sits at the pale end of the range. */
window.__probe.edge = function(y0, y1, side){
  var c = document.querySelector('canvas');
  var dpr = c.width / c.getBoundingClientRect().width;
  var g = c.getContext('2d');
  var top = Math.max(0, Math.round(y0*dpr));
  var hh = Math.max(1, Math.round((y1-y0)*dpr));
  var d = g.getImageData(0, top, c.width, hh).data;
  var isSea = function(i){
    var R = d[i], G = d[i+1], B = d[i+2];
    return B > 55 && B < 170 && B > R*1.4 && G > R && G < B;
  };
  var out = [];
  for(var y = 0; y < hh; y++){
    var found = null;
    if(side < 0){
      if(isSea((y*c.width)*4))
        for(var x = 1; x < c.width; x++){ if(!isSea((y*c.width + x)*4)){ found = x; break; } }
    } else {
      if(isSea((y*c.width + c.width-1)*4))
        for(var x = c.width-2; x >= 0; x--){ if(!isSea((y*c.width + x)*4)){ found = x; break; } }
    }
    out.push({ y: (top + y) / dpr, x: found === null ? null : found / dpr });
  }
  return out;
};

/* THE MEAN COLOUR OF THE WATER ON EACH ROW, ignoring every pixel that is not water - so the sample
   cannot be dragged about by the shoreline wandering across the strip as the band narrows. */
window.__probe.rowTone = function(y0, y1){
  var c = document.querySelector('canvas');
  var dpr = c.width / c.getBoundingClientRect().width;
  var g = c.getContext('2d');
  var top = Math.max(0, Math.round(y0*dpr)), hh = Math.max(1, Math.round((y1-y0)*dpr));
  var d = g.getImageData(0, top, c.width, hh).data;
  var out = [];
  for(var y = 0; y < hh; y++){
    var r=0, gg=0, b=0, n=0;
    for(var x = 0; x < c.width; x++){
      var i = (y*c.width + x)*4, R=d[i], G=d[i+1], B=d[i+2];
      if(B > 55 && B < 170 && B > R*1.4 && G > R && G < B){ r+=R; gg+=G; b+=B; n++; }
    }
    out.push(n ? { y:(top+y)/dpr, r:r/n, g:gg/n, b:b/n, n:n } : { y:(top+y)/dpr, n:0 });
  }
  return out;
};

window.__probe.shot = function(y0, y1){
  var c = document.querySelector('canvas');
  var dpr = c.width / c.getBoundingClientRect().width;
  var top = Math.max(0, Math.round(y0*dpr)), hh = Math.max(1, Math.round((y1-y0)*dpr));
  var out = document.createElement('canvas');
  out.width = c.width; out.height = hh;
  out.getContext('2d').drawImage(c, 0, top, c.width, hh, 0, 0, c.width, hh);
  return out.toDataURL('image/png');
};
"""

# how far below the join to keep walking, so the drawn road's own shore is in the sample too
BELOW = 70
# a crease is a second difference this many times the edge's own median. Measured on the straight
# join it ran to 19x; a smooth edge sits near 1.
KINK = 6.0
# and the join's neighbourhood is this many rows either side of it - the exact row a crease lands on
# depends on rounding, and a curve spreads its bend over two or three rows rather than one
NEAR_JOIN = 3
# how many places down the road to look for the worst join, and how tall a band has to be
# before it is worth measuring at all. Where the road runs level into the draw, the straight
# line and the continued shoreline are very nearly the same picture, so a shallow band cannot
# tell a fixed build from a broken one.
SEARCH = 60
MIN_BAND = 15
# how many bands to measure the tone across, and at which hours. The sea's colour and the
# haze's colour both follow the day, so a value that joins cleanly at dusk and not at noon
# would pass a single-hour check and be wrong for most of the cycle.
BANDS = 5
HOURS = [0.05, 0.30, 0.55, 0.80]
# the step across the join, in summed RGB. Ten is about where a step stops being a seam and
# becomes a gradient: at the measured optimum every sample sat under 8.34, and with the
# recession removed the median alone is 21.88.
SEAM = 10.0


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


def curvature(rows):
    """Second difference of the edge's x, row by row, over the longest unbroken run.

    Broken rows - where the edge left the frame or the colour window missed - are not bridged.
    Joining two points that are fifty rows apart as if they were neighbours reports a bend where
    there is only a gap, which is the mistake `coast-test` records having made once already.
    """
    runs, cur = [], []
    for r in rows:
        if r['x'] is None:
            if len(cur) > 4:
                runs.append(cur)
            cur = []
        else:
            cur.append(r)
    if len(cur) > 4:
        runs.append(cur)
    if not runs:
        return [], []
    run = max(runs, key=len)
    d2 = []
    for i in range(1, len(run) - 1):
        d2.append({'y': run[i]['y'],
                   'v': abs(run[i-1]['x'] - 2*run[i]['x'] + run[i+1]['x'])})
    return run, d2


def measure(run, d2, join_y):
    """How sharply the edge bends AT the join, against what it does everywhere else.

    A ratio, not a pixel count. A shoreline running shallow across the screen moves a hundred
    pixels of x per row on a perfectly straight edge, so any absolute threshold would have to be
    re-tuned by anyone who touched the draw distance or the camera.
    """
    if not d2:
        return None
    near = [v for v in d2 if abs(v['y'] - join_y) <= NEAR_JOIN]
    far = [v for v in d2 if abs(v['y'] - join_y) > NEAR_JOIN]
    if not near or len(far) < 5:
        return None
    at_join = max(v['v'] for v in near)
    base = statistics.median(v['v'] for v in far)
    # A perfectly straight edge has a median of zero, and dividing by that makes everything
    # infinitely worse than nothing. Half a pixel is the floor, which is the quantisation of the
    # reading itself rather than a number chosen to make a check pass.
    ratio = at_join / max(base, 0.5)
    return {'ratio': ratio, 'at_join': at_join, 'base': base, 'rows': len(run)}


def show(name, run, got, join_y):
    if got is None:
        print('        %-9s no unbroken run of edge to measure' % name)
        return
    print('        %-9s %d rows, join at y=%.1f, bend %.2f there against %.2f elsewhere = %.1fx'
          % (name, len(run), join_y, got['at_join'], got['base'], got['ratio']))


def edge_at(page, fs, side):
    rows = page.evaluate("([a,b,s]) => window.__probe.edge(a,b,s)",
                         [fs['horizon'] + 1, fs['y'] + BELOW, side])
    run, d2 = curvature(rows)
    return run, measure(run, d2, fs['y'])


def tone_step(page, fs):
    """How far the water's colour jumps across the join, in summed RGB.

    Four rows either side, not the whole band: the far band legitimately gets paler toward the
    horizon and the drawn sea legitimately darkens toward the bumper, so averaging the whole of
    each would compare two gradients rather than the seam between them.
    """
    rows = page.evaluate("([a,b]) => window.__probe.rowTone(a,b)",
                         [fs['horizon'] + 1, fs['y'] + 40])
    above = [r for r in rows if r['n'] > 6 and r['y'] < fs['y'] - 1.5]
    below = [r for r in rows if r['n'] > 6 and r['y'] > fs['y'] + 1.5]
    if len(above) < 3 or len(below) < 3:
        return None
    a = sorted(above, key=lambda r: -r['y'])[:4]
    b = sorted(below, key=lambda r: r['y'])[:4]
    m = lambda rs, k: sum(r[k] for r in rs) / len(rs)
    return (abs(m(a, 'r') - m(b, 'r')) + abs(m(a, 'g') - m(b, 'g'))
            + abs(m(a, 'b') - m(b, 'b')))


def shot(page, out, name, y0, y1):
    out.mkdir(parents=True, exist_ok=True)
    data = page.evaluate("([a,b]) => window.__probe.shot(a,b)", [y0, y1]).split(',', 1)[1]
    (out / name).write_bytes(base64.b64decode(data))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--headed', action='store_true')
    ap.add_argument('--shots', action='store_true')
    ap.add_argument('--out', default=None)
    args = ap.parse_args()
    console_utf8()
    res = Results()
    out = Path(args.out) if args.out else ROOT / '_seajoin'
    httpd, port = serve(ROOT)
    print('seajoin-test  .  the water runs to the horizon as one body')
    with sync_playwright() as p:
        browser = launch_chromium(p, headless=not args.headed)
        page = browser.new_page(viewport={'width': 480, 'height': 900})
        page.add_init_script(INIT)
        boot(page, 'http://127.0.0.1:%d/%s' % (port, GAME))
        try:
            until(page, '() => navigator.serviceWorker && navigator.serviceWorker.controller', timeout=5000)
            page.wait_for_timeout(1000)
        except Exception:
            pass
        until(page, '!!window.__probe.road', timeout=10000)
        page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
        page.click('[data-act="play"]')
        page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
        page.click('[data-act="drive"]')
        page.wait_for_timeout(2000)

        page.evaluate("() => { const R = window.__probe.road;"
                      " R.setBiomePair('COASTAL','COASTAL'); R.setSpd(0); }")
        page.wait_for_timeout(400)

        # ---- COLLECT THE BANDS ONCE, AND MEASURE EVERYTHING ON THEM ------------------------
        # A band only exists where the furthest drawn slice sits below the horizon; on a road that
        # climbs into the draw there is nothing up there, and a run that measured it anyway would
        # be reading the road's own sea and calling it the background.
        side = page.evaluate("() => window.__probe.road.seaSide()")
        places = []
        for i in range(SEARCH):
            page.evaluate("(n) => window.__probe.road.jumpTo(n)", 200 * 200 * (i + 3))
            page.wait_for_timeout(80)
            fs = page.evaluate("() => window.__probe.road.farSea()")
            if fs.get('drew') and fs.get('y') and fs['y'] - fs['horizon'] > MIN_BAND:
                places.append(200 * 200 * (i + 3))
            if len(places) >= BANDS:
                break

        res.check(len(places) >= 3,
                  'enough bands between the road and the horizon were found to measure',
                  'only %d in %d places over %d px tall' % (len(places), SEARCH, MIN_BAND))
        if len(places) < 3:
            browser.close()
            httpd.shutdown()
            return 1
        print('  %d bands, sea on the %s' % (len(places), 'left' if side < 0 else 'right'))
        print()

        # ---- THE SHAPE, WHICH WAS NEVER THE VISIBLE FAULT ----------------------------------
        # Reported, not gated. The ruling supposed the background met the horizon at the wrong
        # angle; carrying the shoreline on is the right construction and is kept, but across every
        # band found here the straight line it replaces creased by about as much as the reading
        # quantises to. A check that cannot fail is not a check, so this one prints and moves on.
        print('  the shoreline\'s shape at the join')
        page.evaluate("(n) => window.__probe.road.jumpTo(n)", places[0])
        page.wait_for_timeout(200)
        fs = page.evaluate("() => window.__probe.road.farSea()")
        res.check(fs.get('walked', 0) >= 3,
                  'the band is the drawn shoreline carried on, not a straight line to the horizon',
                  'only %s continued points' % fs.get('walked'))
        run, got = edge_at(page, fs, side)
        show('carried', run, got, fs['y'])
        page.evaluate("() => window.__probe.road.seaStraight(true)")
        page.wait_for_timeout(200)
        fs2 = page.evaluate("() => window.__probe.road.farSea()")
        run2, got2 = edge_at(page, fs2, side)
        show('straight', run2, got2, fs2['y'])
        page.evaluate("() => window.__probe.road.seaStraight(false)")
        # Reported, never asserted, and the sentence says which. Measured across 13 bands in 40
        # places while this was built, the straight line creased by at most 2.0 times the edge's
        # own curvature - so the shape is not the fault and this run does not pretend to re-prove
        # it. Where the band is shallow the edge reader finds no unbroken run at all, and saying
        # so is worth more than a number it did not measure.
        print('        recorded when this was built: the straight line creased at most 2.0x, '
              'which is the quantisation of the reading itself')
        print()

        # ---- THE TONE, WHICH WAS ------------------------------------------------------------
        print('  the water\'s colour across the join')
        was = page.evaluate("() => window.__probe.road.seaHaze()")
        results = {}
        for haze in (0.0, was):
            page.evaluate("(v) => window.__probe.road.seaHaze(v)", haze)
            got_steps = []
            for at in places:
                page.evaluate("(n) => window.__probe.road.jumpTo(n)", at)
                page.wait_for_timeout(90)
                for hour in HOURS:
                    page.evaluate("(v) => window.__probe.road.setPhase(v)", hour)
                    page.wait_for_timeout(60)
                    fs = page.evaluate("() => window.__probe.road.farSea()")
                    if not fs.get('drew'):
                        continue
                    st = tone_step(page, fs)
                    if st is not None:
                        got_steps.append(st)
            results[haze] = sorted(got_steps)
        page.evaluate("(v) => window.__probe.road.seaHaze(v)", was)

        for haze in (0.0, was):
            d = results[haze]
            if not d:
                continue
            print('        recession %.2f   median %6.2f   worst %6.2f   %d of %d samples under %.0f'
                  % (haze, statistics.median(d), d[-1],
                     sum(1 for x in d if x < SEAM), len(d), SEAM))

        now = results.get(was, [])
        res.check(bool(now) and statistics.median(now) < SEAM,
                  'the water does not change colour where the background meets the drawn sea',
                  'median step %.2f across %d samples, limit %.2f'
                  % ((statistics.median(now) if now else 0), len(now), SEAM))

        # ---- and the same check, with the recession removed --------------------------------
        # Reverting the engine cannot falsify this file: `API.seaHaze` does not exist on that
        # build. Setting it to zero IS the old behaviour - the sea flat-coloured at every distance
        # while the band above it takes the haze.
        off = results.get(0.0, [])
        res.check(bool(off) and statistics.median(off) >= SEAM,
                  'and with the recession removed it does, so the check is measuring the seam',
                  'median step is only %.2f without it' % (statistics.median(off) if off else 0))
        if args.shots:
            page.evaluate("(n) => window.__probe.road.jumpTo(n)", places[0])
            page.evaluate("() => window.__probe.road.setPhase(0.30)")
            page.wait_for_timeout(200)
            fs = page.evaluate("() => window.__probe.road.farSea()")
            shot(page, out, 'joined.png', fs['horizon'] - 8, fs['y'] + 40)
            page.evaluate("() => window.__probe.road.seaHaze(0)")
            page.wait_for_timeout(200)
            shot(page, out, 'seam.png', fs['horizon'] - 8, fs['y'] + 40)
            page.evaluate("(v) => window.__probe.road.seaHaze(v)", was)
        print()

        errs = page.evaluate("() => window.__probe.errors")
        res.check(not errs, 'no page errors', '; '.join(errs[:3]))
        browser.close()
    httpd.shutdown()

    print()
    if res.fails:
        print('FAILED: ' + ', '.join(res.fails))
        return 1
    print('all checks passed')
    if args.shots:
        print('  shots in ' + str(out))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
