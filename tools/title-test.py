#!/usr/bin/env python3
"""
TITLE TEST - the car on the title card wears the engine's own lamps.

    .venv/Scripts/python tools/title-test.py

RLG-077. The owner: the title menu shows the wrong tail lights, and it may be that the title is not
using the right renderer. It WAS using the right renderer and then painting over it - two red
rectangles at hand-written coordinates and a halo at two more, on a sprite that already knew where
its lamps were.

HOW THIS PROVES THE DIFFERENCE, and it is not a picture. Strip the sprite's lamp DECLARATION at
runtime and look at the title again. If the lamps come from the declaration they go out; if the
title is painting its own rectangles, nothing changes at all - which is exactly what the old code
would have done. So the check is a comparison between two states of the same running title rather
than a comparison with an expected image.

AND IT COUNTS RED PIXELS IN A BAND RATHER THAN DIFFING FRAMES. The title car sways, the sun's bands
creep and the stars twinkle, so a frame-to-frame diff is mostly churn - the fault RLG-053 already
paid for twice. A count of strongly-red pixels across the car's own horizontal band does not care
where in its sway the car happens to be.

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

/* Strongly-red pixels in the band the car occupies. Not a diff: the picture moves for a dozen
   reasons that have nothing to do with a lamp. */
window.__probe.lampRed = function(box){
  var c = document.getElementById('titleArt');
  var g = c.getContext('2d');
  var dpr = c.width / c.clientWidth;
  var y0 = Math.max(0, Math.round((box.y + box.h*0.30) * dpr));
  var y1 = Math.min(c.height, Math.round((box.y + box.h*0.95) * dpr));
  var d = g.getImageData(0, y0, c.width, Math.max(1, y1 - y0)).data;
  var n = 0;
  for (var i = 0; i < d.length; i += 4){
    var R = d[i], G = d[i+1], B = d[i+2];
    if (R > 120 && R > G*2.0 && R > B*1.7) n++;
  }
  return n;
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--headed', action='store_true')
    args = ap.parse_args()
    console_utf8()
    res = Results()
    httpd, port = serve(ROOT)
    print('title-test  .  the title card wears the engine own lamps')
    with sync_playwright() as p:
        browser = launch_chromium(p, headless=not args.headed)
        page = browser.new_context(viewport={'width': 480, 'height': 900},
                                   device_scale_factor=2, has_touch=True,
                                   is_mobile=True).new_page()
        page.add_init_script(INIT)
        boot(page, 'http://127.0.0.1:%d/%s' % (port, GAME))
        until(page, '!!window.__probe.road', timeout=10000)
        page.wait_for_timeout(2200)

        lamps = page.evaluate("() => { const s = window.__probe.road.playerSprite();"
                              " return s && s.lamps ? Object.keys(s.lamps) : null; }")
        print('      the player sprite declares: %s' % (lamps or 'nothing'))
        res.check(bool(lamps) and 'tail' in lamps,
                  'the player sprite declares a tail lamp', str(lamps))

        box = page.evaluate('() => window.__probe.road.titleCar()')
        print('      the title car was drawn at %s' % box)
        res.check(bool(box) and box['w'] > 10,
                  'the title reports where it drew the car', str(box))

        # several samples, because the car sways through its own red band
        def red(n=4):
            out = []
            for _ in range(n):
                page.wait_for_timeout(180)
                b = page.evaluate('() => window.__probe.road.titleCar()')
                out.append(page.evaluate('(b) => window.__probe.lampRed(b)', b))
            return out

        lit = red()
        print('      red pixels with the declaration in place: %s' % lit)
        res.check(min(lit) > 40, 'the title car has lit lamps on it', str(lit))

        # ---- AND NOW TAKE THE DECLARATION AWAY -------------------------------------
        # If the title paints its own rectangles this changes nothing, which is the
        # whole point of doing it this way round.
        page.evaluate("() => { const s = window.__probe.road.playerSprite(); s.lamps = {}; }")
        page.wait_for_timeout(300)
        dark = red()
        print('      red pixels with the declaration stripped: %s' % dark)
        res.check(max(dark) < min(lit) * 0.5,
                  'and they come from the sprite declaration, not from the title',
                  'stripped %s against %s lit' % (dark, lit))

        # ---- A GARAGE TAP REBUILDS ONE CAR, NOT THE WHOLE ROAD (RLG-086) ----
        # Owner, 2026-08-30, from the device: choosing a colour takes about half a second
        # before the selection changes, and toggling is the same, and it is probably having
        # to rebuild the vehicle. It was rebuilding all of them - the two player sprites,
        # then the entire rival cache and every traffic sprite, none of which depend on the
        # colour that was tapped. Measured at 215 to 335 ms a tap on a desktop.
        #
        # AND THIS IS NOT A STOPWATCH. A time is a number the machine decides, so a check
        # written against one agrees with whatever machine ran it. A sprite is a canvas, so
        # the exact question - was this rebuilt - is a question about IDENTITY. The harness
        # writes a mark on two of them and looks for it afterwards.
        page.click('[data-act="play"]')
        page.wait_for_timeout(900)
        swatches = page.query_selector_all('#veil [data-act^="paint:"]')
        res.check(len(swatches) >= 2, 'the garage offers colours to tap',
                  '%d swatch(es)' % len(swatches))
        if len(swatches) >= 2:
            marked = page.evaluate("""() => {
                const R = window.__probe.road;
                const t = R.fleetSprite('truck'), pl = R.playerSprite();
                if(!t || !pl) return null;
                t.__mark = 'before'; pl.__mark = 'before';
                return true;
            }""")
            res.check(bool(marked), 'the engine hands over its sprites to be marked')
            # tap a colour that is not the one already chosen
            page.evaluate("""() => {
                const b = document.querySelectorAll('#veil [data-act^="paint:"]');
                b[b.length - 1].click();
            }""")
            page.wait_for_timeout(300)
            after = page.evaluate("""() => {
                const R = window.__probe.road;
                const t = R.fleetSprite('truck'), pl = R.playerSprite();
                return { truck: t ? t.__mark || null : 'missing',
                         player: pl ? pl.__mark || null : 'missing' };
            }""")
            print('      after tapping a colour: the lorry is %s, the player %s'
                  % ('the same object' if after['truck'] == 'before' else 'REBUILT',
                     'the same object' if after['player'] == 'before' else 'rebuilt'))
            res.check(after['truck'] == 'before',
                      'a colour tap does not rebuild the traffic',
                      'the lorry sprite was rebuilt as well (%r)' % after['truck'])
            res.check(after['player'] != 'before',
                      'and it does rebuild the car whose colour changed',
                      'the player sprite was not rebuilt (%r)' % after['player'])

        # ---- AND THE CARD HOLDS STILL BETWEEN CARS (RLG-087) ----------------
        # Owner, 2026-08-30: set the car render to the same static height, using the tallest
        # car as the reference, so switching cars does not collapse and expand the layout.
        # It moved between 79 and 90 px across the cars a player starts with - small, which
        # is the complaint rather than a defence of it: a large change reads as a transition
        # and a small one reads as the page failing to hold still.
        fits = page.evaluate('() => window.__probe.road.garageFits()')
        each = {k: v for k, v in fits['each'].items() if v}
        big = {k for k in each if fits['big'].get(k)}
        small = {k for k in each if k not in big}
        res.check(bool(big) and bool(small),
                  'the fleet has both ordinary cars and oversized ones',
                  'big=%s' % sorted(big))
        want_s = max(each[k] for k in small)
        want_b = max(each[k] for k in big) if big else want_s
        print('      ordinary cars want up to %d px (%s), the big ones up to %d px (%s)'
              % (want_s, max(small, key=lambda k: each[k]),
                 want_b, max(big, key=lambda k: each[k]) if big else '-'))
        print('      reserved: %d for the ordinary cars, %d for the big ones'
              % (fits['reserved']['small'], fits['reserved']['big']))
        # EXACTLY the tallest of its own tier, not merely big enough. A reservation with
        # slack over every car would satisfy a covers-them-all check while wasting the
        # difference on all of them - which is the fault the single tier had.
        res.check(fits['reserved']['small'] == want_s,
                  'the ordinary cars reserve exactly their own tallest',
                  '%d reserved where %d was needed' % (fits['reserved']['small'], want_s))
        res.check(fits['reserved']['big'] == want_b,
                  'and the big ones reserve exactly theirs',
                  '%d reserved where %d was needed' % (fits['reserved']['big'], want_b))
        # AND THE TIERS ARE WORTH HAVING. If the biggest ordinary car were as tall as the
        # lorry there would be nothing to separate, and this check would be theatre.
        res.check(fits['reserved']['big'] > fits['reserved']['small'],
                  'and the two tiers are actually different sizes',
                  'both are %d' % fits['reserved']['small'])

        # and the drawn card holds still while the car is an ordinary one
        heights = []
        for _ in range(4):
            h = page.evaluate("""() => {
                const c = document.getElementById('gcar');
                return c ? Math.round(parseFloat(c.style.height) || c.height) : null;
            }""")
            if h:
                heights.append(h)
            nxt = page.query_selector('#veil [data-act="next"]')
            if not nxt:
                break
            nxt.click()
            page.wait_for_timeout(240)
        print('      the drawn card across four ordinary cars: %s' % heights)
        res.check(len(set(heights)) == 1,
                  'the drawn card does not change height between ordinary cars',
                  'it measured %s' % heights)
        res.check(not heights or heights[0] == fits['reserved']['small'],
                  'and it is the ordinary reservation, not the big one',
                  'drawn at %s, reserved %d'
                  % (heights[0] if heights else None, fits['reserved']['small']))

        errs = page.evaluate('() => window.__probe.errors')
        res.check(not errs, 'no page errors', str(errs))
        browser.close()
    httpd.shutdown()
    print(('\n%d check(s) failed' % len(res.fails)) if res.fails else '\nall checks passed')
    return 1 if res.fails else 0


if __name__ == '__main__':
    sys.exit(main())
