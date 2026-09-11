#!/usr/bin/env python3
"""
HUD TEST - the thumb cluster stacks up from the pedals, and closes over what a car does not have.

    .venv/Scripts/python tools/hud-test.py
    .venv/Scripts/python tools/hud-test.py --shots

RLG-028. The owner: cars without NOS did not have the gauges collapse down to the pedals. Hiding the
bottle left the space it stood in, so a car without one drove with a hole in its instruments.

IT MEASURES BOXES, NOT PIXELS. Every element in the cluster is a positioned box, so the question
"did the stack close up" is a question about `getBoundingClientRect` - which is exact, and which does
not care what the road behind it is doing.

AND IT RUNS IN A TOUCH CONTEXT, because the shell hides the whole cluster on a device that reports no
touch (RLG-069): a desktop harness measures nothing and reports success.

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

/* every box in the thumb cluster, in CSS pixels from the BOTTOM of the stage - which is the
   direction the cluster is anchored in, so it is the direction to measure in */
/* the HUD's own furniture, measured from the edges it is anchored to. The mirror is drawn on the
   CANVAS rather than in the DOM, so its box is repeated here the way mirror-shot.py repeats it. */
window.__probe.hud = function(){
  var st = document.getElementById('stage') || document.body;
  var sr = st.getBoundingClientRect();
  var cv = document.querySelector('canvas');
  var cr = cv.getBoundingClientRect();
  /* the glass publishes its own size now, so the harness asks rather than repeating it */
  var cs = getComputedStyle(document.documentElement);
  var mh = parseFloat(cs.getPropertyValue('--mirror-h')) || 44;
  var my = parseFloat(cs.getPropertyValue('--mirror-top')) || 6;
  var mw = Math.min(cr.width * 0.80, 340);
  var out = { scale: +getComputedStyle(document.documentElement)
                       .getPropertyValue('--ark-ui').trim(),
              stage: { w:+sr.width.toFixed(1), h:+sr.height.toFixed(1) },
              mirror: { top:my, bottom:my + mh, w:+mw.toFixed(1) } };
  ['.toprow', '.botrow'].forEach(function(sel){
    var el = document.querySelector(sel);
    if(!el) return;
    var r = el.getBoundingClientRect();
    out[sel.slice(1)] = { top:+(r.top - cr.top).toFixed(1),
                          bottom:+(cr.bottom - r.bottom).toFixed(1),
                          h:+r.height.toFixed(1) };
  });
  /* the gap between the mirror's lower edge and the first thing under it */
  /* the row's own box starts at its padding edge, so the CONTENT top is what clears
     the glass - a padding box that overlaps a mirror is not an overlap of anything */
  var tr = document.querySelector('.toprow');
  if(tr){
    var pad = parseFloat(getComputedStyle(tr).paddingTop) || 0;
    out.toprowContent = +(out.toprow.top + pad).toFixed(1);
    out.mirrorGap = +(out.toprowContent - out.mirror.bottom).toFixed(1);
  }
  /* and between the bottom row and the tallest thing in the thumb cluster */
  var tallest = 0;
  ['dials','shifter','nitro','gas','wheel'].forEach(function(id){
    var el = document.getElementById(id);
    if(!el) return;
    var r = el.getBoundingClientRect();
    if(r.width > 2 && r.height > 2) tallest = Math.max(tallest, cr.bottom - r.top);
  });
  out.clusterTop = +tallest.toFixed(1);
  /* the size of a readout, which must grow with the controls beside it */
  var st2 = document.querySelector('.stat b');
  out.statPx = st2 ? +parseFloat(getComputedStyle(st2).fontSize).toFixed(2) : null;
  if(out.botrow) out.clusterGap = +(out.botrow.bottom - tallest).toFixed(1);
  return out;
};

/* ---- WHERE THE INK IS, NOT WHERE THE BOX IS -----------------------------------------
   A canvas box is not the picture in it. The gauges are two round faces drawn into a wider
   canvas, so the box reaches lower than anything painted - and a gap measured to the box is
   smaller than the gap anybody can see. The owner saw it and the check did not.
   -------------------------------------------------------------------------------------- */
window.__probe.inkOf = function(id){
  var c = document.getElementById(id);
  if(!c || !c.getContext) return null;
  var g = c.getContext('2d');
  var d = g.getImageData(0, 0, c.width, c.height).data;
  var top = -1, bot = -1;
  for(var y = 0; y < c.height; y++){
    for(var x = 0; x < c.width; x++){
      if(d[(y*c.width + x)*4 + 3] > 16){ if(top < 0) top = y; bot = y; break; }
    }
  }
  if(bot < 0) return null;
  var r = c.getBoundingClientRect();
  var h = document.documentElement.clientHeight;
  var sy = r.height / c.height;               /* canvas pixels to CSS pixels */
  return { boxBottom:+(h - r.bottom).toFixed(1),
           inkBottom:+(h - (r.top + (bot + 1) * sy)).toFixed(1),
           inkTop:+(h - (r.top + top * sy)).toFixed(1),
           padBelow:+(((c.height - 1 - bot) * sy)).toFixed(1) };
};

/* ---- AND WHERE THE INK IS SIDEWAYS ---------------------------------------------------
   The same lesson as `inkOf`, turned through ninety degrees. The bottle's VALVE and its
   NOZZLE are pseudo-elements hanging off the left of the button, outside the box the
   button occupies, so a bottle whose BOX is centred over the pads is drawn left of them.
   The owner saw exactly that. This hands the harness a strip of the screen to photograph
   and the two numbers to judge it against; the reading itself is done on the picture.
   ------------------------------------------------------------------------------------- */
window.__probe.hideRoad = function(){
  var s = document.createElement('style');
  s.id = '__inkbg';
  /* the road behind, and the wheel beside, are both ink that is not the bottle */
  s.textContent = 'canvas{visibility:hidden !important}'
                + '#wheel,#horn,#shifter,#paddles,#gas,#brake{visibility:hidden !important}';
  document.head.appendChild(s);
};
window.__probe.showRoad = function(){
  var s = document.getElementById('__inkbg');
  if(s) s.remove();
};
window.__probe.bottleBand = function(){
  var nz = document.getElementById('nitro');
  var g = document.getElementById('gas'), br = document.getElementById('brake');
  if(!nz || !g || !br) return null;
  var r = nz.getBoundingClientRect(),
      rg = g.getBoundingClientRect(), rb = br.getBoundingClientRect();
  /* the strip is the bottle's own rows, widened well past both ends of the button so
     anything hanging off it is inside the picture rather than cropped out of it */
  var pad = 48;
  return {
    clip: { x:Math.round(r.left - pad), y:Math.round(r.top),
            width:Math.round(r.width + pad * 2), height:Math.round(r.height) },
    padsMid: +(((rg.left + rg.right) + (rb.left + rb.right)) / 4).toFixed(2),
    boxLeft: +r.left.toFixed(2), boxRight: +r.right.toFixed(2),
    boxMid: +((r.left + r.right) / 2).toFixed(2)
  };
};

window.__probe.cluster = function(){
  var h = document.documentElement.clientHeight;
  var out = {};
  ['pedals','gas','brake','nitro','shifter','paddles','dials','wheel'].forEach(function(id){
    var el = document.getElementById(id);
    if(!el) return;
    var r = el.getBoundingClientRect();
    var shown = r.width > 2 && r.height > 2 && getComputedStyle(el).display !== 'none';
    out[id] = shown ? { bottom:+(h - r.bottom).toFixed(1), top:+(h - r.top).toFixed(1),
                        x:+r.x.toFixed(1), w:+r.width.toFixed(1), h:+r.height.toFixed(1) } : null;
  });
  out.nonos = document.body.classList.contains('nonos');
  out.manual = document.body.classList.contains('manual');
  return out;
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


def ink_span_x(page, clip):
    """The leftmost and rightmost COLUMN of the strip that has anything painted in it.

    A column counts as ink when some pixel in it is far enough from the strip's own corner
    colour to be something a person would see. The bottle's drop shadow is deliberately not
    ink: it is a soft gradient a few shades off the background, and centring a picture on its
    shadow is not what the owner asked for.
    """
    from PIL import Image
    import io
    shot = page.screenshot(clip=clip)
    im = Image.open(io.BytesIO(shot)).convert('RGB')
    w, h = im.size
    px = im.load()
    bg = px[0, h // 2]                       # the strip is padded well past the bottle
    left, right = None, None
    for x in range(w):
        for y in range(h):
            r, g, b = px[x, y]
            if max(abs(r - bg[0]), abs(g - bg[1]), abs(b - bg[2])) > 40:
                if left is None:
                    left = x
                right = x
                break
    return left, right, w, h


class Results:
    def __init__(self):
        self.fails = []

    def check(self, ok, label, detail=''):
        print(('  ok    ' if ok else '  FAIL  ') + label + ('' if ok else '   [' + str(detail) + ']'))
        if not ok:
            self.fails.append(label)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--headed', action='store_true')
    ap.add_argument('--shots', action='store_true')
    ap.add_argument('--out', default=None)
    args = ap.parse_args()
    console_utf8()
    res = Results()
    out = Path(args.out) if args.out else ROOT / '_hud'
    if args.shots:
        out.mkdir(parents=True, exist_ok=True)
    httpd, port = serve(ROOT)
    print('hud-test  .  the cluster stacks up from the pedals')
    with sync_playwright() as p:
        browser = launch_chromium(p, headless=not args.headed)
        page = browser.new_context(viewport={'width': 480, 'height': 900},
                                   has_touch=True, is_mobile=True).new_page()
        page.add_init_script(INIT)
        boot(page, 'http://127.0.0.1:%d/%s' % (port, GAME))
        until(page, '!!window.__probe.road', timeout=10000)
        page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
        page.click('[data-act="play"]')
        page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
        page.click('[data-act="drive"]')
        page.wait_for_timeout(1400)

        def cluster(body):
            # THE DIALS TRANSITION OVER 0.18s AND THE CLASS LANDS BEFORE THEY MOVE, so a fixed
            # wait is a race: 200ms read the layout mid-flight, and 600ms still failed about
            # one run in eight. It waits for the position to STOP MOVING instead, which is the
            # thing it actually needs to be true.
            page.evaluate('(k) => window.__probe.road.setBody(k)', body)
            last, same = None, 0
            for _ in range(40):
                page.wait_for_timeout(80)
                d = page.evaluate('() => window.__probe.cluster()')
                here = (d.get('dials') or {}).get('bottom')
                same = same + 1 if here == last else 0
                last = here
                if same >= 3:
                    return d
            return page.evaluate('() => window.__probe.cluster()')

        withnos = cluster('ROADSTER')
        res.check(withnos.get('nitro') is not None and not withnos['nonos'],
                  'a car with a bottle shows one', str(withnos.get('nitro')))
        res.check(withnos.get('dials') is not None,
                  'and the dials are on screen', str(withnos.get('dials')))

        # SEMI and CAB are the two the fragment names as having a button they could never use
        nonos = cluster('SEMI')
        print('      with a bottle:  nitro %s  dials at %s'
              % (withnos.get('nitro'), (withnos.get('dials') or {}).get('bottom')))
        print('      without one:    nitro %s  dials at %s'
              % (nonos.get('nitro'), (nonos.get('dials') or {}).get('bottom')))
        res.check(nonos.get('nitro') is None and nonos['nonos'],
                  'a car with no bottle shows none', str(nonos.get('nitro')))
        res.check(nonos.get('dials') is not None,
                  'and still has its dials', str(nonos.get('dials')))

        drop = withnos['dials']['bottom'] - nonos['dials']['bottom']
        print('      the dials come down by %.1f px' % drop)
        res.check(drop > 20,
                  'the gauges collapse toward the pedals when there is no bottle',
                  'they moved %.1f px' % drop)

        # AND NOTHING LANDS ON A CONTROL. `#pedals` is a container that the bottle itself sat
        # inside, so measuring against ITS box says nothing - the first version of this check
        # failed on a layout the capture shows to be correct. The pads are the controls, and
        # they are what must stay clear.
        pads = [nonos.get('gas'), nonos.get('brake')]
        pads = [p2 for p2 in pads if p2]
        if pads and nonos.get('dials'):
            highest = max(p2['top'] for p2 in pads)
            res.check(nonos['dials']['bottom'] >= highest - 2,
                      'and they stop above the pedal pads rather than on them',
                      'dials at %.1f, the pads reach %.1f' % (nonos['dials']['bottom'], highest))

        if args.shots:
            page.evaluate('() => window.__probe.road.setBody("ROADSTER")')
            page.wait_for_timeout(250)
            page.screenshot(path=str(out / 'hud-with-nos.png'))
            page.evaluate('() => window.__probe.road.setBody("SEMI")')
            page.wait_for_timeout(250)
            page.screenshot(path=str(out / 'hud-no-nos.png'))
            print('      wrote %s' % out)

        # ---- THE BOTTLE SITS CENTRED OVER THE PADS, EVENLY SPACED (RLG-082) -----
        # Owner: it should be centred above the brake and the accelerator, and have equal
        # padding between them and the gauges. It had neither - 16px right of the pads' own
        # centre, sitting ON them with a 0 gap below and 6 above.
        c0 = cluster('ROADSTER')
        g, br, nz, dl = c0.get('gas'), c0.get('brake'), c0.get('nitro'), c0.get('dials')
        if g and br and nz and dl:
            pads_mid = ((g['x'] + g['w']/2) + (br['x'] + br['w']/2)) / 2                        if 'x' in g else None
            # TO THE INK, NOT TO THE BOX. The gauge faces are drawn into a canvas that
            # reaches lower than anything painted in it, so a gap measured to the box is
            # smaller than the gap on screen - which is how a build whose numbers said
            # 7.4 and 7.4 still looked wrong to the owner.
            ink = page.evaluate('() => window.__probe.inkOf("gauges")')
            below = nz['bottom'] - max(g['top'], br['top'])
            above = (ink['inkBottom'] if ink else dl['bottom']) - nz['top']
            print('      the bottle: %.1f px above the pads, %.1f px below the gauge FACES'
                  ' (the canvas reaches %.1f px lower than its ink)'
                  % (below, above, ink['padBelow'] if ink else 0))
            res.check(abs(below - above) <= 2.0,
                      'the bottle has equal padding above the pads and below the gauges',
                      '%.1f below against %.1f above' % (below, above))

        # ---- AND IT IS CENTRED BY ITS INK, NOZZLE INCLUDED (RLG-082) -----------
        # Owner, 2026-08-30: the bottle still is not laterally centred, because the
        # measurement did not include its NOZZLE - the valve and the tapered outlet are
        # pseudo-elements that hang off the LEFT of the button, outside the box that was
        # being centred. The same lesson the gauges taught vertically: centre the picture,
        # not the container it is drawn in.
        band = page.evaluate('() => window.__probe.bottleBand()')
        if band:
            page.evaluate('() => window.__probe.hideRoad()')
            page.wait_for_timeout(120)
            l, r, sw, sh = ink_span_x(page, band['clip'])
            page.evaluate('() => window.__probe.showRoad()')
            if l is None:
                res.check(False, 'the bottle paints something in its own band', 'no ink found')
            else:
                ink_l = band['clip']['x'] + l
                ink_r = band['clip']['x'] + r + 1
                ink_mid = (ink_l + ink_r) / 2
                print('      the bottle: box %.1f to %.1f (mid %.1f), INK %.1f to %.1f'
                      ' (mid %.1f), the pads centre on %.1f'
                      % (band['boxLeft'], band['boxRight'], band['boxMid'],
                         ink_l, ink_r, ink_mid, band['padsMid']))
                print('      the nozzle and valve hang %.1f px off the left of the button'
                      % (band['boxLeft'] - ink_l))
                res.check(abs(ink_mid - band['padsMid']) <= 1.5,
                          'the bottle is centred over the pads by its INK, nozzle included',
                          'the ink centres on %.1f where the pads centre on %.1f, off by %.1f'
                          % (ink_mid, band['padsMid'], ink_mid - band['padsMid']))

        # ---- AND THE TOP ROW CLEARS THE GLASS, WHATEVER SIZE THE GLASS IS -------
        # The clearance used to be a hardcoded 58 in a different file from the two numbers
        # that decide it. The engine publishes the mirror's height, so this asserts the
        # relationship rather than the number: the row starts below the glass, and close
        # enough to it to be reading as one panel.
        d0 = page.evaluate('() => window.__probe.hud()')
        print('      the glass ends at %s, the top row reads from %s, gap %s px'
              % (d0['mirror']['bottom'], d0['toprowContent'], d0['mirrorGap']))
        gap = d0['mirrorGap']
        # THE GAP IS A DESIGNED 8 PIXELS TIMES THE UI SCALE, not a window of anything
        # plausible. A window wide enough to be safe passed the old hardcoded 58 as well,
        # which is the failure mode of a loose bound: it agrees with whatever is there.
        want_gap = 8.0 * float(d0['scale'] or 1)
        res.check(gap is not None and abs(gap - want_gap) <= 2.0,
                  'the top row clears the glass by the gap it is designed to',
                  'gap %s px where %.1f was designed' % (gap, want_gap))

        # ---- AND THE READOUTS ARE IN THE SAME SPACE AS THE CONTROLS (RLG-082) ----
        # The shell publishes --ark-ui and the cabinet opted its CONTROLS in and left its
        # READOUTS behind, so at 1.8 the wheel and the pedals were half as big again while
        # TIME and DISTANCE were the same 26px they are on a phone. Two viewports, and the
        # readout must have grown by the same factor the scale did.
        sizes = []
        for w, hh in ((390, 844), (820, 1180)):
            pg2 = browser.new_context(viewport={'width': w, 'height': hh},
                                      has_touch=True, is_mobile=True).new_page()
            pg2.add_init_script(INIT)
            boot(pg2, 'http://127.0.0.1:%d/%s' % (port, GAME))
            pg2.wait_for_timeout(1600)
            pg2.click('[data-act="play"]')
            pg2.wait_for_timeout(400)
            pg2.click('[data-act="drive"]')
            pg2.wait_for_timeout(1200)
            d = pg2.evaluate('() => window.__probe.hud()')
            sizes.append((w, d['scale'], d['statPx']))
            pg2.context.close()
        (w1, s1, p1), (w2, s2, p2) = sizes
        print('      a readout is %.1fpx at scale %s and %.1fpx at scale %s' % (p1, s1, p2, s2))
        res.check(s2 > s1 * 1.5, 'the two viewports really are at different UI scales',
                  '%s and %s' % (s1, s2))
        want = p1 * (s2 / s1)
        res.check(abs(p2 - want) < 1.0,
                  'a readout grows with the controls beside it',
                  '%.1fpx where %.1f was expected' % (p2, want))

        errs = page.evaluate('() => window.__probe.errors')
        res.check(not errs, 'no page errors', str(errs))
        browser.close()
    httpd.shutdown()
    print(('\n%d check(s) failed' % len(res.fails)) if res.fails else '\nall checks passed')
    return 1 if res.fails else 0


if __name__ == '__main__':
    sys.exit(main())
