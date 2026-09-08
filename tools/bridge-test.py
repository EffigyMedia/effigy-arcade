#!/usr/bin/env python3
"""BRIDGE TEST - the water is on both sides, it reaches the horizon, and it recedes.

    .venv/Scripts/python tools/bridge-test.py

RLG-112. Owner, 2026-08-31: a bridge over water, where the water "wouldn't be level with the
bridge - it would be drawn as a complete surface underneath the bridge".

THE FRAGMENT NAMES THE HARD PART AND THEN SAYS NOT TO SOLVE IT YET. Every surface this
engine draws sits on one ground plane, so a second altitude is not something the projection
can express. A second plane is the honest answer; a fill from the horizon down is the cheat.
It says to build the CHEAP one first and let the picture decide, and the reason is in this
project's own record - the far sea was built twice and the version that measured better was
the one that made no estimate at all.

SO THE CHEAT IS THAT THE PLACE'S GROUND IS WATER, and these are the claims that makes:

    IT IS ON BOTH SIDES. A coast has water on ONE side, from a shoreline a fixed distance
    out from the tarmac. A bridge has no shoreline at all - the water reaches both frame
    edges - and every hard part of the coast is therefore absent.

    IT REACHES THE HORIZON. The strip between the skyline and the furthest drawn slice is
    painted by the far field rather than by the road pass. A place whose ground is water and
    whose far field is not shows a band of land above a sea, which is where the coast ran
    out before RLG-093.

    AND IT RECEDES. Water at one flat colour from the bumper to the skyline reads as a
    painted floor. The distance term is the coast's own, measured at its join.

THE COAST IS THE CONTROL AND IT IS RUN ON EVERY CLAIM. A check that passed on both places
would not be measuring a bridge - it would be measuring "is there water on the screen". The
coast must still come back with land on one side, and if the shoreline work is ever broken
by this, that is where it shows.

WHAT IT CANNOT DO. It cannot say whether the crossing reads as a bridge rather than a
causeway - it will not until the towers and the deck are built - or whether the water looks
right in motion. `tools/biome-shot.py` takes the picture; the owner judges it.

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
from harness import console_utf8, launch_chromium

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

/* Is this pixel water? The same test coast-test uses, and deliberately the same one: two
   definitions of "sea-coloured" that drift apart would let one harness pass a frame the
   other fails, and neither would be wrong about its own definition. */
window.__probe.isSea = function(R, G, B){
  return B > 55 && B < 170 && B > R*1.4 && G > R && G < B;
};

/* One row of the frame, counting water either side of a split. `y` is in CSS pixels. */
window.__probe.waterRow = function(y, split){
  var c = document.querySelector('canvas');
  var r = c.getBoundingClientRect();
  var dpr = c.width / r.width;
  var g = c.getContext('2d');
  var d = g.getImageData(0, Math.round(y*dpr), c.width, 1).data;
  var half = (split === undefined ? c.width/2 : split * dpr);
  var left = 0, right = 0;
  for(var x = 0; x < c.width; x++){
    var i = x*4;
    if(window.__probe.isSea(d[i], d[i+1], d[i+2])){ if(x < half) left++; else right++; }
  }
  return { left: left, right: right, width: c.width, half: half };
};

/* The band between the horizon and the furthest drawn slice - the strip the far field owns.
   Sampling wider than the gap itself answers the question with the feature removed, which
   coast-test records having been caught by. */
window.__probe.farBand = function(hz, gapY){
  var c = document.querySelector('canvas');
  var r = c.getBoundingClientRect();
  var dpr = c.width / r.width;
  var g = c.getContext('2d');
  var y0 = Math.round((hz + 2) * dpr), hh = Math.max(1, Math.round((gapY - hz - 4) * dpr));
  var d = g.getImageData(0, y0, c.width, hh).data;
  var left = 0, right = 0;
  for(var y = 0; y < hh; y++){
    for(var x = 0; x < c.width; x++){
      var i = (y*c.width + x)*4;
      if(window.__probe.isSea(d[i], d[i+1], d[i+2])){ if(x < c.width/2) left++; else right++; }
    }
  }
  return { left: left, right: right, area: c.width*hh, rows: hh };
};

/* The mean colour of one row's water pixels, so recession can be measured rather than
   asserted from the code that produces it. */
window.__probe.waterTone = function(y){
  var c = document.querySelector('canvas');
  var r = c.getBoundingClientRect();
  var dpr = c.width / r.width;
  var g = c.getContext('2d');
  var d = g.getImageData(0, Math.round(y*dpr), c.width, 1).data;
  var R = 0, G = 0, B = 0, n = 0;
  for(var x = 0; x < c.width; x++){
    var i = x*4;
    if(window.__probe.isSea(d[i], d[i+1], d[i+2])){ R += d[i]; G += d[i+1]; B += d[i+2]; n++; }
  }
  return n ? { r: R/n, g: G/n, b: B/n, n: n } : null;
};

/* Is this pixel the ironwork? International Orange is strongly red-dominant with a
   little green and almost no blue.

   THE FIRST VERSION OF THIS TEST CAUGHT THE RUMBLE STRIP, and a COAST - which has no
   ironwork anywhere - came back with 250 orange pixels. Sampling them settled it in one
   run: they were rgb(146,86,85) and rgb(144,73,79), the antialiased edge between the
   rumble's red stripe and its pale one. That blend sits at R = 1.7 x G, and the ironwork
   sits at 2.4 to 3.6 - so the ratio is the discriminator and 2.0 separates them with
   room on both sides. Guessing a threshold would not have found this; looking at the
   pixels did. */
window.__probe.isIron = function(R, G, B){
  return R > 90 && R > G * 2.0 && R > B * 2.5;
};
/* Is this pixel LAND? The bridge's own unused ground colours are a headland green,
   chosen so that a build with the water removed looks obviously wrong rather than
   quietly similar. So "no land at the skyline" is the sharp form of "the water reaches
   the skyline": on a build without the water treatment that row is entirely this. */
window.__probe.isLand = function(R, G, B){
  return G > 40 && R < 150 && G > R * 1.05 && G > B * 1.15;
};
/* Scanning down from the skyline, the first row at which the deck appears in the
   road's own vanishing column. On a bridge that must be the skyline itself. */
window.__probe.deckTop = function(vx, hz){
  var c = document.querySelector('canvas');
  var r = c.getBoundingClientRect();
  var dpr = c.width / r.width;
  var g = c.getContext('2d');
  var x0 = Math.max(0, Math.round((vx - 3) * dpr)), ww = Math.round(7 * dpr);
  var top = Math.round(hz * dpr), hh = Math.round(160 * dpr);
  var d = g.getImageData(x0, top, ww, hh).data;
  for(var y = 0; y < hh; y++){
    var dark = 0;
    for(var x = 0; x < ww; x++){
      var i = (y*ww + x)*4;
      /* tarmac is the darkest thing up there by a long way - the water it sits
         in never gets near this, even at its most shadowed */
      if(d[i] < 70 && d[i+1] < 75 && d[i+2] < 95) dark++;
    }
    if(dark >= ww * 0.5) return Math.round(top/dpr) + Math.round(y/dpr);
  }
  return null;
};
window.__probe.landRow = function(y){
  var c = document.querySelector('canvas');
  var r = c.getBoundingClientRect();
  var dpr = c.width / r.width;
  var g = c.getContext('2d');
  var d = g.getImageData(0, Math.round(y*dpr), c.width, 1).data;
  var n = 0;
  for(var x = 0; x < c.width; x++){
    var i = x*4;
    if(window.__probe.isLand(d[i], d[i+1], d[i+2])) n++;
  }
  return n;
};
window.__probe.ironRow = function(y0, y1, split){
  var c = document.querySelector('canvas');
  var r = c.getBoundingClientRect();
  var dpr = c.width / r.width;
  var g = c.getContext('2d');
  var top = Math.round(y0*dpr), hh = Math.max(1, Math.round((y1-y0)*dpr));
  var d = g.getImageData(0, top, c.width, hh).data;
  var half = (split === undefined ? c.width/2 : split * dpr);
  var left = 0, right = 0;
  for(var y = 0; y < hh; y++){
    for(var x = 0; x < c.width; x++){
      var i = (y*c.width + x)*4;
      if(window.__probe.isIron(d[i], d[i+1], d[i+2])){ if(x < half) left++; else right++; }
    }
  }
  return { left: left, right: right, area: c.width*hh };
};
window.__probe.mirrorIron = function(){
  var c = document.querySelector('canvas');
  var r = c.getBoundingClientRect();
  var dpr = c.width / r.width;
  var mw = Math.min(r.width * 0.62, 250), mh = 44;
  var mx = (r.width - mw) / 2, my = 6;
  var g = c.getContext('2d');
  var x0 = Math.round(mx * dpr), y0 = Math.round(my * dpr);
  var ww = Math.round(mw * dpr), hh = Math.round(mh * dpr);
  var d = g.getImageData(x0, y0, ww, hh).data;
  var n = 0;
  for(var i = 0; i < d.length; i += 4)
    if(window.__probe.isIron(d[i], d[i+1], d[i+2])) n++;
  return { px: n, area: ww*hh };
};
window.__probe.mirrorWater = function(){
  var c = document.querySelector('canvas');
  var r = c.getBoundingClientRect();
  var dpr = c.width / r.width;
  var mw = Math.min(r.width * 0.62, 250), mh = 44;
  var mx = (r.width - mw) / 2, my = 6;
  var g = c.getContext('2d');
  var y0 = Math.round((my + mh*0.34) * dpr), hh = Math.round(mh*0.62 * dpr);
  var x0 = Math.round(mx * dpr), ww = Math.round(mw * dpr);
  var d = g.getImageData(x0, y0, ww, hh).data;
  var left = 0, right = 0, half = ww/2;
  for(var y = 0; y < hh; y++){
    for(var x = 0; x < ww; x++){
      var i = (y*ww + x)*4;
      if(window.__probe.isSea(d[i], d[i+1], d[i+2])){ if(x < half) left++; else right++; }
    }
  }
  return { left: left, right: right, area: ww*hh };
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


def settle(page, place):
    """Pin both ends of the blend to one place and let a few frames draw.

    THE ROAD IS CLEARED EVERY TIME, and that is not tidiness. A red car is
    orange too: the ironwork check below counts International Orange pixels,
    and traffic put 221 of them into a COAST - a place with no ironwork at all -
    which is enough to make the control meaningless. `biome-shot.py` clears the
    road for the same reason before it takes a picture.
    """
    page.evaluate("(k) => { const R = window.__probe.road;"
                  " R.setBiomePair(k, k); R.clearTraffic(); }", place)
    page.wait_for_timeout(500)
    page.evaluate("() => window.__probe.road.clearTraffic()")
    page.wait_for_timeout(120)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--headed', action='store_true')
    args = ap.parse_args()
    console_utf8()
    res = Results()
    httpd, port = serve(ROOT)
    print('bridge-test  .  water on both sides, to the horizon, receding')
    with sync_playwright() as p:
        browser = launch_chromium(p, headless=not args.headed)
        page = browser.new_page(viewport={'width': 480, 'height': 900})
        page.add_init_script(INIT)
        page.goto('http://127.0.0.1:%d/%s' % (port, GAME), wait_until='load')
        try:
            page.wait_for_function(
                '() => navigator.serviceWorker && navigator.serviceWorker.controller',
                timeout=5000)
            page.wait_for_timeout(1000)
        except Exception:
            pass
        page.wait_for_function('!!window.__probe.road', timeout=10000)
        page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
        page.click('[data-act="play"]')
        page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
        page.click('[data-act="drive"]')
        page.wait_for_timeout(1600)
        # midday, dry, so nothing below is about the weather or the hour
        page.evaluate("() => { const R = window.__probe.road;"
                      " R.setPhase(0.75); R.setWet(0); R.setSnow(0); R.setPool(0); }")
        page.wait_for_timeout(300)

        # ------------------------------------------------ what the place states
        print()
        print('  WHICH PLACES ARE OVER WATER')
        states = page.evaluate("""() => {
          const R = window.__probe.road, out = {};
          for(const k of R.BIOME_KEYS()) out[k] = R.waterKind(k);
          return out;
        }""")
        for k, v in states.items():
            if v['sea'] or v['overWater']:
                print('      %-10s sea=%s  overWater=%s' % (k, v['sea'], v['overWater']))
        res.check(states['BRIDGE']['overWater'] is True,
                  'the bridge states that it is over water',
                  str(states['BRIDGE']))
        res.check(states['COASTAL']['overWater'] is False and states['COASTAL']['sea'] is True,
                  'and the coast does not - it has a shoreline, which is the difference',
                  str(states['COASTAL']))
        res.check([k for k, v in states.items() if v['overWater']] == ['BRIDGE'],
                  'and nothing else on the board is over water',
                  str([k for k, v in states.items() if v['overWater']]))

        # ------------------------------------------------ both sides
        print()
        print('  WATER ON BOTH SIDES, WHICH IS WHAT A COAST NEVER HAS')
        settle(page, 'BRIDGE')
        hz = page.evaluate("() => window.__probe.road.horizon()")
        row = hz + (900 - hz) * 0.28
        b = page.evaluate("(y) => window.__probe.waterRow(y)", row)
        print('      bridge, one row a quarter down from the horizon:'
              '  left %d  right %d  of %d' % (b['left'], b['right'], b['width']))
        settle(page, 'COASTAL')
        c = page.evaluate("(y) => window.__probe.waterRow(y)", row)
        print('      coast,  the same row:                            '
              '  left %d  right %d  of %d' % (c['left'], c['right'], c['width']))
        # A SYMMETRY RATHER THAN A COUNT, and the count is why. This asked for more than
        # 20 pixels a side and read 26 and 26 - then the ironwork was built, the kerb and
        # the railing took a few of them at this row, and a correct build came back 21 and
        # 20 and failed. What the check is actually about is that the water is on BOTH
        # sides, which is a shape claim; a magnitude picked from one reading is a threshold
        # waiting to be tripped by the next feature that legitimately paints there.
        bmin, bmax = min(b['left'], b['right']), max(b['left'], b['right'])
        res.check(bmin > 8 and bmin >= bmax * 0.5,
                  'the bridge has water to left AND right of the road, in comparable amounts',
                  'left %d, right %d' % (b['left'], b['right']))
        # THE CONTROL. A coast puts its water on ONE rolled side, so one of its two counts
        # must be near nothing - otherwise this check is measuring "is there water".
        res.check(min(c['left'], c['right']) < bmax * 0.25,
                  'and the coast still has land on one side, so this measures a bridge',
                  'the coast read left %d, right %d' % (c['left'], c['right']))

        # ------------------------------------------------ to the horizon
        print()
        print('  AND IT REACHES THE HORIZON, WHERE THE ROAD PASS STOPS PAINTING')
        settle(page, 'BRIDGE')
        fs = page.evaluate("() => window.__probe.road.farSea()")
        hz = page.evaluate("() => window.__probe.road.horizon()")
        print('      the far field: drew=%s, horizon %.1f, the road stops at %s'
              % (fs.get('drew'), hz, fs.get('roadTop')))
        # NOT `drew`. That flag says a SHORELINE BAND was walked, and a bridge walks
        # none - the far field's own ground fill is already water, because `groundBase`
        # answers the water question for the far field ahead and the mirror's band at
        # once. A rectangle written here first was dead code, and this harness is what
        # proved it: taking it out changed the row below by nothing at all.
        res.check(fs.get('sea') is True,
                  'the far field knows the place it is painting has water in it',
                  str(fs))
        gap = fs.get('roadTop')
        # ---- THE ROW UNDER THE SKYLINE IS THE CLAIM, AND THE BAND'S COVERAGE IS NOT.
        # The first version of this check compared how much of the far band was water
        # against a coast measured the same way, and the coast came back at 67% against the
        # bridge's 77% - the band is nine rows tall at the vanishing point, where a coast's
        # shore has converged to the centre and its own water fills half of it anyway. Two
        # numbers that close are not a discriminator, and asserting on them would have been
        # a check that passes because water is on the screen.
        #
        # WHAT ONLY A PLACE WITH NO SHORELINE CAN DO is fill the row immediately under the
        # skyline from edge to edge. That row is above everything the road pass paints, so
        # it is the far field's alone, and a coast can never have more than one side of it.
        row_hz = hz + 3
        settle(page, 'BRIDGE')
        bb = page.evaluate("(y) => window.__probe.waterRow(y)", row_hz)
        settle(page, 'COASTAL')
        cb = page.evaluate("(y) => window.__probe.waterRow(y)", row_hz)
        print('      the row just under the skyline, which only the far field paints:')
        print('        bridge  %d of %d pixels are water' % (bb['left'] + bb['right'], bb['width']))
        print('        coast   %d of %d' % (cb['left'] + cb['right'], cb['width']))
        settle(page, 'BRIDGE')
        # THE IRONWORK STANDS IN THIS ROW TOO, and that is not a fault. A cable and a
        # tower cross the skyline exactly where the water is, so the claim is that the row
        # is water EXCEPT where the bridge itself is - which is what "the water reaches
        # the skyline" actually means. This check read 480 of 480 before the ironwork was
        # built and would now fail on a correct build without the second term.
        bbi = page.evaluate("([a, b]) => window.__probe.ironRow(a, b)", [row_hz, row_hz + 1])
        bland = page.evaluate("(y) => window.__probe.landRow(y)", row_hz)
        covered = bb['left'] + bb['right'] + bbi['left'] + bbi['right']
        print('        bridge  %d water + %d ironwork + %d land, of %d'
              % (bb['left'] + bb['right'], bbi['left'] + bbi['right'], bland, bb['width']))
        # NOT "water plus ironwork fills the row", which was asked first and failed one run
        # in three on a correct build: at every boundary between water and orange there is
        # an antialiased pixel that is neither, and there are about forty of them. A
        # threshold sitting on that blend is a threshold that fails at random.
        #
        # THE SHARP CLAIM IS THAT THERE IS NO LAND UP THERE. The bridge's unused ground
        # colour is a headland green precisely so a build without the water treatment looks
        # wrong rather than similar - and on that build this row is entirely land and no
        # water at all. Both halves are asserted, so neither a missing far field nor a
        # blank row can pass.
        res.check(bland == 0,
                  'there is no land at the skyline - the water runs all the way to it',
                  '%d land pixels in the row' % bland)
        # DELIBERATELY LOOSE, AND IT HAS BEEN MOVED TWICE FOR THE SAME REASON. This started
        # at 90% of the row as water; then the ironwork was built and a cable and a tower
        # legitimately crossed it, and then the fleet was built and a liner at the horizon
        # took another chunk. Every one of those is a thing that is SUPPOSED to stand on the
        # sea. Chasing the fraction each time is how a check ends up measuring the last
        # feature added, so the sharp claim is the LAND count above and this one only says
        # the row has not stopped being water.
        res.check((bb['left'] + bb['right']) > bb['width'] * 0.55,
                  'and the row is still mostly water, with the bridge and its shipping in the rest',
                  'only %d water of %d, plus %d ironwork'
                  % (bb['left'] + bb['right'], bb['width'], bbi['left'] + bbi['right']))
        # THE COAST'S FIGURE IS PRINTED AND NOT ASSERTED ON, and that was measured rather
        # than assumed. It came back 238, 183 and 340 of 480 on three runs of one unchanged
        # build: the shore converges on the road's own vanishing point, which the bend
        # moves across the frame, so on a hard corner a coast can legitimately fill most of
        # that row. An assertion on it would fail at random, which is the failure mode
        # occlusion-test.py was written against. The bridge's own edge-to-edge figure is
        # the claim, and the section below proves it can go red.
        if gap and gap > hz + 6:
            band = page.evaluate("([h, g]) => window.__probe.farBand(h, g)", [hz, gap])
            print('      the band as a whole: %d rows, water left %d right %d of %d'
                  ' - reported, not asserted on, see above'
                  % (band['rows'], band['left'], band['right'], band['area']))

        # ------------------------------------------------ and it recedes
        print()
        print('  AND IT RECEDES, OR IT IS A PAINTED FLOOR')
        # THE NEAREST WATER IS NOT AT THE BOTTOM OF THE FRAME. Down there the road fills
        # the width and there is no water left to read, so the near sample is taken at the
        # lowest row that still has some. That is a shorter span than the whole draw, and
        # the threshold below is set against it rather than against the recession's full
        # range - a smaller travel measured honestly beats a larger one measured nowhere.
        near = None
        for f in (0.34, 0.30, 0.26, 0.22):
            near = page.evaluate("(y) => window.__probe.waterTone(y)", hz + (900 - hz) * f)
            if near and near['n'] > 12:
                break
        far = page.evaluate("(y) => window.__probe.waterTone(y)", hz + 4)
        if near and far:
            print('      near  rgb(%.0f,%.0f,%.0f) from %d pixels' % (near['r'], near['g'], near['b'], near['n']))
            print('      far   rgb(%.0f,%.0f,%.0f) from %d pixels' % (far['r'], far['g'], far['b'], far['n']))
            travel = abs(far['r'] - near['r']) + abs(far['g'] - near['g']) + abs(far['b'] - near['b'])
            res.check(travel > 12,
                      'the water at the skyline is not the water at the bumper',
                      'the colour travelled only %.0f across the whole draw' % travel)
        else:
            res.check(False, 'there is water at both ends of the draw to compare',
                      'near=%s far=%s' % (bool(near), bool(far)))

        # ------------------------------------------------ and the mirror
        print()
        print('  AND THE GLASS CARRIES IT TOO')
        mw = page.evaluate("() => window.__probe.mirrorWater()")
        print('      mirror water pixels: left %d  right %d  of %d'
              % (mw['left'], mw['right'], mw['area']))
        res.check(mw['left'] > 30 and mw['right'] > 30,
                  'the mirror shows water on both sides as well',
                  'left %d, right %d' % (mw['left'], mw['right']))

        # ------------------------------------------------ suspended, not floating
        print()
        print('  AND IT IS SUSPENDED OVER THE WATER RATHER THAN FLOATING ON IT')
        # Owner, 2026-09-01, correcting the first cut: draw it "so the bridge looks
        # suspended hundreds of feet above water".
        #
        # MEASURED ON THE FUNCTION, NOT ON THE PIXELS, and that was decided after trying
        # the other way. The claim is that the water is a plane far below, which this
        # engine draws as DISTANCE - so the water at the foot of the frame is as far off
        # as water near the horizon. Sampling the colour to prove it conflates two
        # separate haze passes: `seaTone`'s own recession and `drawHaze` over the whole
        # frame. A tone comparison read a travel of 135 on a build that was correct, and
        # the coast - the obvious control - had no water in frame at all on most rows,
        # because its rolled side and the bend move the sea about.
        wp = page.evaluate("() => window.__probe.road.waterPlane()")
        print('      the water lies %d units below the deck (%d camera heights)'
              % (wp['unitsBelow'], wp['drop']))
        print('      at the foot of the frame it reads %.2f of the draw away;'
              '  at road level it would read %.2f' % (wp['atBottom'], wp['ifFlat']))
        res.check(wp['atBottom'] > wp['ifFlat'] * 4,
                  'the water at your wheels is far further off than the road under them',
                  'water %.3f against flat %.3f' % (wp['atBottom'], wp['ifFlat']))
        res.check(wp['atBottom'] > 0.20,
                  'and far enough off to be hazed, which is what says it is below you',
                  'it reads only %.3f of the draw away' % wp['atBottom'])

        # AND NO GROUND IS PAINTED AT THE ROAD'S LEVEL, which is the fault being fixed:
        # every slice used to paint water from the road's own line downward, so the sea
        # met the kerb and converged at the tarmac's rate. That is a causeway.
        settle(page, 'BRIDGE')
        near = page.evaluate("(y) => window.__probe.waterRow(y)", hz + (900 - hz) * 0.20)
        print('      water either side at a fifth down: left %d right %d'
              % (near['left'], near['right']))
        res.check(near['left'] > 5 and near['right'] > 5,
                  'and there is still water either side of the deck to be suspended over',
                  'left %d, right %d' % (near['left'], near['right']))

        # ------------------------------------------------ the deck reaches the skyline
        print()
        print('  AND THE DECK RUNS TO THE SKYLINE RATHER THAN ENDING IN MID-WATER')
        # Owner, 2026-09-01: "the end of the rendered bridge ends under the horizon, which
        # wouldn't happen." The road is drawn for DRAW segments and stops short of the
        # vanishing point - on land the far field fills the gap with more ground and nobody
        # reads it as an end, but on a bridge the STRUCTURE stops in the middle of a stretch
        # of water.
        settle(page, 'BRIDGE')
        van = page.evaluate("() => window.__probe.road.vanishing()")
        df = page.evaluate("() => window.__probe.road.deckFar()")
        print('      the skyline is at %.1f and the road pass stops painting at %s'
              % (van['horizon'], van['roadStops']))
        print('      the deck walks on from %s to %s in %s steps'
              % (df['from'], df['to'], df['walked']))
        # READ FROM THE WALK, NOT FROM THE PIXELS, and that was decided after trying the
        # other way. Two things sit exactly where the deck's tip is and cannot be told
        # from it by colour - the skyline's own headlands, which are dark silhouettes on
        # the horizon line, and the ironwork's stanchions. Scanning the road's vanishing
        # COLUMN is worse: near the horizon the road is at a finite distance and the bend
        # puts it well off that column, so one unchanged build read 353, 356, 358 and 397.
        res.check(df['walked'] > 0,
                  'the deck walks on past where the road pass stops',
                  'it emitted %s extra points' % df['walked'])
        if df['to'] is not None:
            res.check(df['to'] < van['roadStops'],
                      'and it ends above where the road pass ended',
                      'the walk ended at %s, the road pass at %s' % (df['to'], van['roadStops']))
            # IT CANNOT REACH THE SKYLINE EXACTLY, and that is geometry rather than a
            # shortfall: a road converging on a vanishing point is a point there.
            # THE LAST FEW PIXELS ARE THE CLOSING LINE, and they are exact rather than
            # sampled. The walk emits only points the projection gives - a shorter walk is
            # its failure mode, never a wrong one - and the polygon then closes on the
            # vanishing point itself, which is a value and not a trend. So the deck DOES
            # reach the skyline; what this bounds is how much of it is sampled rather than
            # spanned. Measured at 4.3 px of span from a 12.6 px gap.
            res.check(df['to'] - van['horizon'] < 8,
                      'and it samples to within a few pixels, the rest being the closing line',
                      'it stopped %.1f px under the skyline' % (df['to'] - van['horizon']))

        # ------------------------------------------------ boats on the water
        print()
        print('  AND BOATS ON THE WATER, WHICH IS WHAT GIVES THE DROP ITS SCALE')
        # Owner, 2026-09-01: "little boats ... out in the water scattered down below",
        # and smaller than the coastal ones would be "since they are further away". The
        # smallness is not a setting - a boat sits on the water plane, so the nearest one
        # that can appear is already about ten thousand units off and the painter comes out
        # tiny without being told to.
        settle(page, 'BRIDGE')
        b1 = page.evaluate("() => window.__probe.road.boats()")
        print('      %d boats placed on the water, %d of them on screen'
              % (b1['total'], b1['drawn']))
        if b1['sample']:
            print('      the nearest few: %s'
                  % ', '.join('%dpx at %d units' % (s['w'], s['dz']) for s in b1['sample'][:4]))
        res.check(b1['drawn'] >= 3,
                  'there are boats on the water below',
                  'only %d of %d were on screen' % (b1['drawn'], b1['total']))
        # ---- AND THE KINDS ARE IN REAL PROPORTION TO EACH OTHER. Owner, 2026-09-01:
        # "we need to make sure the boats are all the correct relative sizes." The first
        # set was not, and not by a little - a liner was nine times a speedboat where the
        # real ratio is forty, the small craft were about twice life size and the big ships
        # less than half. Four numbers picked to look spaced out are not four sizes.
        #
        # THERE IS ONE KNOWN LENGTH IN THIS ENGINE and everything hangs off it: a car is
        # 380 units and about four and a half metres. So the check is in METRES, against
        # what these things actually measure, and it is the ratio that is asserted rather
        # than any one figure.
        kinds = page.evaluate("() => window.__probe.road.boatKinds()")
        want = {'speed': 7, 'sail': 11, 'liner': 300, 'tanker': 330}
        print('      the fleet, in metres against the car own 4.5:')
        for k in kinds:
            print('        %-7s %6.1f m  (wanted about %d)' % (k['name'], k['metres'], want[k['name']]))
        for k in kinds:
            res.check(abs(k['metres'] - want[k['name']]) < want[k['name']] * 0.15,
                      'a %s measures about %d metres' % (k['name'], want[k['name']]),
                      'it is %.1f m' % k['metres'])
        by = {k['name']: k['metres'] for k in kinds}
        res.check(by['liner'] / by['speed'] > 30,
                  'and a liner is more than thirty times a speedboat, as one is',
                  'it is %.0f times' % (by['liner'] / by['speed']))

        # ---- AND THE SPEEDS GIVE THE OWNER'S ORDERING WITHOUT BEING TUNED TO. Owner,
        # 2026-09-01: "tankers will barely be moving, sailboats will be a little bit
        # faster than that and speedboats will be ripping." In ABSOLUTE terms a tanker at
        # fifteen knots is faster than a sailboat at six - so the ordering the owner
        # described is about what the EYE reads, and that is the angular rate: a tanker is
        # a mile out and a sailboat is a few hundred metres. The check asks for the
        # apparent ordering and the real knots produce it, which is the point.
        rates = page.evaluate("() => window.__probe.road.boatRates()")
        print('      apparent motion, in pixels a second at each kind own distance:')
        for r in rates:
            print('        %-7s %5.1f kn at %6d units -> %5.2f px/s'
                  % (r['name'], r['knots'], r['at'], r['px']))
        rate = {r['name']: r['px'] for r in rates}
        res.check(rate['tanker'] < rate['sail'] < rate['speed'],
                  'a tanker crawls, a sailboat is a little faster, a speedboat rips',
                  'tanker %.2f, sail %.2f, speed %.2f'
                  % (rate['tanker'], rate['sail'], rate['speed']))
        res.check(rate['speed'] > rate['tanker'] * 8,
                  'and the speedboat really is ripping beside the tanker',
                  'only %.1f times' % (rate['speed'] / max(0.01, rate['tanker'])))

        # AND THE CONSEQUENCE IS CORRECT AND WORTH EXPECTING: from a bridge deck you see
        # ships, not dinghies. The near water is behind the deck - as it is from a real
        # bridge - so small craft are rarely in view here, and the coastal boats, which sit
        # at ground level and far nearer, are what carry the small end of the fleet.
        spread = [s['w'] for s in b1['sample']]
        res.check(max(spread) / max(0.1, min(spread)) > 5,
                  'and the fleet on screen spans a wide range of sizes rather than one',
                  'the range was %.1f to %.1f px' % (min(spread), max(spread)))

        # A BOAT IS A PLACE IN THE WORLD, AND THIS IS THE CHECK THAT MATTERS. Two versions
        # of the scatter derived the lateral offset from the car's own position, so the
        # boats swam sideways to stay on screen - and both looked perfectly fine in a still
        # picture. It is the same class of fault as the mirror slices pinned to the segment
        # behind the player, which this engine has been caught by four times: anything whose
        # world position is derived from `pos` is not in the world.
        #
        # THE SEA CLOCK IS HELD FIRST, and without that this check cannot mean anything now
        # that the boats move: "did it move?" has two answers - because time passed, which
        # is the feature, and because the camera moved, which is the fault. Freezing the
        # clock and then driving isolates the second exactly.
        page.evaluate("() => window.__probe.road.holdSeaClock(true)")
        b1 = page.evaluate("() => window.__probe.road.boats()")
        page.evaluate("() => window.__probe.road.setSpd(window.__probe.road.MAX_SPD)")
        page.wait_for_timeout(900)
        b2 = page.evaluate("() => window.__probe.road.boats()")
        by1 = {s['i']: s['lx'] for s in b1['sample'] + b1['missed']}
        moved = [i for s in (b2['sample'] + b2['missed'])
                 for i in [s['i']] if i in by1 and by1[i] != s['lx']]
        common = [s['i'] for s in (b2['sample'] + b2['missed']) if s['i'] in by1]
        print('      %d boats seen in both samples after driving on; %d of them moved'
              % (len(common), len(moved)))
        res.check(len(common) > 0,
                  'the same boats are still there after driving on, so this can be compared',
                  'no boat appeared in both samples')
        res.check(not moved,
                  'and with time held still, not one changed its place as the car moved',
                  'these moved: %s' % moved[:5])
        # AND THEY DO MOVE WHEN TIME RUNS, or the owner's request is not built at all.
        page.evaluate("() => window.__probe.road.holdSeaClock(false)")
        b3 = page.evaluate("() => window.__probe.road.boats()")
        page.wait_for_timeout(700)
        b4 = page.evaluate("() => window.__probe.road.boats()")
        was = {s['i']: s['lx'] for s in b3['sample'] + b3['missed']}
        sailed = [s['i'] for s in (b4['sample'] + b4['missed'])
                  if s['i'] in was and was[s['i']] != s['lx']]
        print('      with time running again, %d of the shared boats had sailed on'
              % len(sailed))
        res.check(len(sailed) > 0,
                  'and they DO cross the water once time is running',
                  'not one moved in three quarters of a second')
        page.evaluate("() => window.__probe.road.holdSeaClock(false)")

        # ------------------------------------------------ the ironwork
        print()
        print('  AND THE RED TRUSS, WHICH IS WHAT MAKES IT A BRIDGE')
        plan = page.evaluate("() => window.__probe.road.trussPlan()")
        print('      %d towers over %d units: a bay of %d against a draw of %d'
              % (plan['towers'], plan['span'], plan['bay'], plan['reach']))
        # THE ONE CONSTRAINT THAT IS GEOMETRIC RATHER THAN TASTE. A tower is culled at the
        # draw distance like everything else, and the cable rises to tower height wherever
        # a tower stands. So towers further apart than the draw leave the cable climbing to
        # a peak with nothing at the top of it - measured at four towers, where a probe of
        # the live game found NO tower inside the draw at all.
        res.check(plan['bay'] <= plan['reach'],
                  'a tower always stands inside the draw, so the cable has something to hang on',
                  'bays are %d against a draw of %d' % (plan['bay'], plan['reach']))

        cable = page.evaluate("() => window.__probe.road.cableProfile(80)")
        print('      the cable across the crossing, in world units above the deck:')
        print('      %s' % ' '.join('%d' % v for v in cable[::8]))
        res.check(cable[0] <= plan['railH'] + 1 and cable[-1] <= plan['railH'] + 1,
                  'it is anchored at the deck at both ends',
                  'ends at %d and %d' % (cable[0], cable[-1]))
        res.check(max(cable) >= plan['towerH'] * 0.98,
                  'and it reaches the top of a tower',
                  'the highest it got was %d against a tower of %d'
                  % (max(cable), plan['towerH']))
        # AND IT SAGS. A cable that went straight from anchor to tower to anchor would pass
        # both checks above and be a set of wires rather than a suspension bridge.
        #
        # NOT AT THE MIDDLE OF THE CROSSING, which is where this asked first and why it
        # failed on a correct build: with seven towers there are eight bays, so the middle
        # of the span lands exactly ON a tower and reads full height. The sag lives INSIDE
        # a bay, so that is where it has to be measured.
        interior = cable[len(cable)//8:-len(cable)//8]
        dip = min(interior)
        res.check(dip < plan['towerH'] * 0.6,
                  'and it sags inside each bay rather than running straight between towers',
                  'the lowest it got between the end anchors was %d against a tower of %d'
                  % (dip, plan['towerH']))

        settle(page, 'BRIDGE')
        band = (hz + (900 - hz) * 0.10, hz + (900 - hz) * 0.55)
        iron = page.evaluate("([a, b]) => window.__probe.ironRow(a, b)", list(band))
        settle(page, 'COASTAL')
        ciron = page.evaluate("([a, b]) => window.__probe.ironRow(a, b)", list(band))
        print('      orange pixels over the road band:  bridge left %d right %d,'
              '  coast left %d right %d'
              % (iron['left'], iron['right'], ciron['left'], ciron['right']))
        res.check(iron['left'] > 40 and iron['right'] > 40,
                  'there is ironwork down BOTH sides of the deck',
                  'left %d, right %d' % (iron['left'], iron['right']))
        res.check(ciron['left'] + ciron['right'] < 20,
                  'and none at all in a place with no truss, so this measures the bridge',
                  'the coast had %d orange pixels' % (ciron['left'] + ciron['right']))

        # AND THE GLASS. Owner, 2026-09-01: all of it "needs to be properly visible in the
        # mirror". One painter serves both views, so this is a check that the mirror was
        # actually given the call rather than that a second copy agrees with the first.
        #
        # WHAT IT DOES NOT SEPARATE, measured rather than assumed. The glass carries two
        # things - the railing and the towers - and this counts both together: 319 orange
        # pixels with both, 253 with the towers alone, 72 with the railing alone, 0 with
        # neither. So it proves ironwork reaches the mirror and would NOT catch one of the
        # two going missing on its own. Splitting it would need the pane divided by
        # something that separates a rail from a tower's legs, and neither is confined to
        # a part of the glass the other stays out of.
        settle(page, 'BRIDGE')
        mi = page.evaluate("() => window.__probe.mirrorIron()")
        settle(page, 'COASTAL')
        mc = page.evaluate("() => window.__probe.mirrorIron()")
        print('      orange pixels in the glass:  bridge %d, coast %d  (of %d)'
              % (mi['px'], mc['px'], mi['area']))
        res.check(mi['px'] > 60,
                  'the mirror carries the ironwork too',
                  'only %d orange pixels in the glass' % mi['px'])
        res.check(mc['px'] < 20,
                  'and not in a place without it',
                  'the coast put %d orange pixels in the glass' % mc['px'])
        settle(page, 'BRIDGE')

        # ---- THE SHAPE OF GETTING ONTO IT (owner, 2026-09-07) ---------------------
        # "It should be a sharp ramp up for maybe a quarter of a mile, then absolutely
        # flat for the duration of the bridge, and then for the quarter mile before
        # transitioning into the next biome, the sharp ramp down."
        #
        # THE ARRANGEMENT WAS ALREADY RIGHT AND THE SHAPE WAS NOT, which is why this
        # reads the ramp's PROFILE rather than merely checking there is one. The old
        # build climbed, held level and descended exactly as it should - but over 0.34 of
        # a mile, and as a soft hump rather than a ramp: height gained per step ran 0.50,
        # 7.26, 9.12, 4.17, which is a bell. A ramp is a constant slope.
        for key, sign in (('BRIDGE', 1), ('TUNNEL', -1)):
            prof = page.evaluate('(k) => window.__probe.road.riseProfile(k, 40)', key)
            span = page.evaluate('(k) => window.__probe.road.placeSpan(k)', key)['stated']
            if not prof:
                res.check(False, '%s states a profile' % key, 'none found')
                continue
            step = [prof[i + 1] - prof[i] for i in range(len(prof) - 1)]
            flat = [i for i, v in enumerate(step) if abs(v) < 0.02]
            moving = [v for v in step if abs(v) >= 0.02]
            climb = [v for v in step if v * sign > 0.02]
            # the ramp, as a fraction of the crossing and then as miles
            ramp_steps = len(moving) / 2.0
            ramp_miles = span * ramp_steps / len(step)
            print('    %-7s ramp %.2f mi each end, deck flat for %d of %d steps, '
                  'steepest step %.2f' % (key, ramp_miles, len(flat), len(step),
                                          max(abs(v) for v in step)))
            # 0.32 AND NOT 0.40. The old build's bridge ramped over 0.34 of a mile and
            # passed a looser tolerance, which made the length half of this change
            # unassertable - the ramp used to be a SHARE of the crossing, sixteen per
            # cent, so a longer bridge got a longer climb and "a quarter of a mile"
            # could not be expressed at all. It is a distance now and the check says so.
            res.check(0.18 <= ramp_miles <= 0.32,
                      '%s ramps over about a quarter of a mile' % key,
                      '%.2f miles' % ramp_miles)
            res.check(len(flat) >= len(step) * 0.5,
                      'and %s is dead flat for the length of the crossing' % key,
                      '%d of %d steps level' % (len(flat), len(step)))
            # A CONSTANT SLOPE, WHICH IS WHAT "SHARP" MEANS HERE. On the old easing the
            # ramp's own steps varied by a factor of eighteen, 0.50 against 9.12. A ramp
            # with its corners taken off varies by about two.
            # HOW MUCH OF THE RAMP IS AT FULL SLOPE, which is what "sharp" means and
            # what a bell can never satisfy. Trimming a fixed number of corner steps was
            # tried first and does not work: where the rounding lands relative to this
            # forty-step grid is arbitrary, so the tunnel kept one corner and the bridge
            # did not, and the same engine read as two different shapes.
            #
            # A constant ramp spends nearly all of itself at its own slope. A smoothed
            # hump - which is what shipped until 2026-09-07 - spends almost none of
            # itself there, because the peak is a single instant in the middle.
            peak = max(abs(v) for v in climb) if climb else 0
            atfull = [v for v in climb if peak and abs(v) >= peak * 0.85]
            share = len(atfull) / len(climb) if climb else 0
            print('        %s: %d of %d ramp steps within 15%% of the steepest'
                  % (key, len(atfull), len(climb)))
            res.check(len(climb) >= 3 and share >= 0.5,
                      'and the %s ramp is a steady slope rather than a hump' % key,
                      '%d of %d ramp steps are at full slope' % (len(atfull), len(climb)))

        errs = page.evaluate("() => window.__probe.errors")
        res.check(not errs, 'no page errors', '; '.join(errs[:3]))
        browser.close()
    httpd.shutdown()

    print()
    if res.fails:
        print('FAILED: ' + '; '.join(res.fails))
        return 1
    print('all checks passed')
    print('  whether the ironwork reads as the Golden Gate at speed is not measured here,')
    print('  and neither is the deck surface, which is not built. See tools/biome-shot.py')
    return 0


sys.exit(main())
