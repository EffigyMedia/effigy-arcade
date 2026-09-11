#!/usr/bin/env python3
"""MESSAGE BAND TEST - a transient message sits under the mirror, not over the road.

    .venv/Scripts/python tools/message-band-test.py

RLG-134. Owner, 2026-08-31: "the UI elements that pop up in the dead center of the screen
block my view of the upcoming road, so I think we should move that to just under the other
information that's below the rearview mirror."

WHY THIS NEEDS A HARNESS. There are TWO mechanisms printing in the middle of the screen -
the DOM banner `#warn` and the canvas labels in `fx` - and moving one while leaving the
other is a change that looks finished and is half done. Only one kind of message is on
screen at a time, so a screenshot of either cannot tell you about the other.

WHAT IT ASSERTS, and deliberately not "the banner is at some particular pixel":

    the engine publishes a band at all
    the banner is BELOW the information row, which is where the owner put it
    it is still in the top half - "below the row" is also satisfied by shoving it off screen
    the canvas labels read the SAME band as the DOM banner
    it clears the horizon, so it is not over the road ahead
    and the band MOVES when the mirror does, which is the difference between
      anchored and merely placed somewhere better

THE LAST TWO ARE THE POINT. A percentage put the banner at 38%, which is why it landed on
the road on the owner's phone; a hardcoded pixel would pass everything above it and fail
the move. Both cabinets are checked, because both carry the rule.

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

GAMES = [('interstate', 'games/sw/interstate.html'),
         ('motorsport', 'games/sw/motorsport.html')]

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

# Every number in ONE coordinate space. The canvas is sized in CSS pixels, so a DOM rect
# and a canvas y are directly comparable - which is the assumption the engine itself makes
# when it publishes `--msg-top`, and asserting on it here is what would catch it changing.
GEOM = """() => {
  const R = window.__probe.road;
  const cv = document.getElementById('cv');
  const cr = cv.getBoundingClientRect();
  const row = document.querySelector('.toprow');
  const rr = row ? row.getBoundingClientRect() : null;
  const warn = document.getElementById('warn');
  const wr = warn ? warn.getBoundingClientRect() : null;
  const css = getComputedStyle(document.documentElement).getPropertyValue('--msg-top');
  return {
    canvasH: cr.height, canvasW: cr.width,
    rowBottom: rr ? rr.bottom - cr.top : null,
    rowTop: rr ? rr.top - cr.top : null,
    warnTop: wr ? wr.top - cr.top : null,
    warnH: wr ? wr.height : null,
    msgTopVar: (css || '').trim(),
    mirror: R && R.mirrorRect ? R.mirrorRect() : null,
    labelY: R && R.msgBand ? R.msgBand() : null,
    horizon: R && R.horizon ? R.horizon() : null
  };
}"""


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


def px(v):
    """'123px' -> 123.0, and None for anything that is not a length yet."""
    try:
        return float(str(v).replace('px', '').strip())
    except (TypeError, ValueError):
        return None


def drive(page):
    until(page, '!!window.__probe.road', timeout=10000)
    page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
    page.click('[data-act="play"]')
    page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
    page.click('[data-act="drive"]')
    page.wait_for_timeout(1800)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--headed', action='store_true')
    args = ap.parse_args()
    console_utf8()
    res = Results()
    httpd, port = serve(ROOT)
    print('message-band-test  .  a message sits under the mirror, not over the road')
    with sync_playwright() as p:
        browser = launch_chromium(p, headless=not args.headed)
        for name, path in GAMES:
            print()
            print('  ' + name.upper())
            page = browser.new_page(viewport={'width': 480, 'height': 900})
            page.add_init_script(INIT)
            boot(page, 'http://127.0.0.1:%d/%s' % (port, path))
            try:
                until(page, '() => navigator.serviceWorker && navigator.serviceWorker.controller',
                    timeout=5000)
                page.wait_for_timeout(1000)
            except Exception:
                pass
            drive(page)

            g = page.evaluate(GEOM)
            band = px(g['msgTopVar'])
            mbot = (g['mirror']['y'] + g['mirror']['h']) if g['mirror'] else None
            print('      mirror ends %s, information row %s-%s, band %s, banner top %s'
                  % (fmt(mbot), fmt(g['rowTop']), fmt(g['rowBottom']),
                     g['msgTopVar'] or 'unset', fmt(g['warnTop'])))

            res.check(band is not None,
                      'the engine publishes a message band',
                      'the --msg-top variable is %r' % g['msgTopVar'])
            res.check(g['rowBottom'] is not None and g['warnTop'] is not None
                      and g['warnTop'] >= g['rowBottom'] - 1,
                      'the banner is BELOW the information row, which is where the owner put it',
                      'banner at %s, row ends at %s' % (fmt(g['warnTop']), fmt(g['rowBottom'])))
            # AND IT IS STILL ON THE SCREEN. "Below the row" is also satisfied by shoving it
            # off the bottom edge, and a message the player cannot see is not an improvement
            # on one in the way.
            res.check(g['warnTop'] is not None and g['warnTop'] < g['canvasH'] * 0.5,
                      'and it is still in the top half rather than pushed out of sight',
                      'banner at %s of %s' % (fmt(g['warnTop']), fmt(g['canvasH'])))
            # THE TWO MECHANISMS AGREE. This is what stops half the messages moving - the
            # failure that is invisible in any single screenshot.
            # AGAINST WHERE THE BANNER ACTUALLY IS, not against the variable it was told to
            # use. Comparing the labels to `--msg-top` compares the engine with itself: a
            # cabinet whose stylesheet still read `top:38%` would publish a correct variable,
            # ignore it, and pass. The banner's own rect is the only honest witness.
            res.check(g['labelY'] is not None and g['warnTop'] is not None
                      and abs(g['labelY'] - g['warnTop']) < 2,
                      'and the canvas labels land where the DOM banner actually is',
                      'labels at %s, banner at %s, band says %s'
                      % (fmt(g['labelY']), fmt(g['warnTop']), g['msgTopVar']))
            # CLEAR OF THE ROAD, which is the owner's actual complaint. The horizon is where
            # the road ahead begins, so a message that ends above it is not over the road.
            if g['horizon'] is not None:
                ends = (g['warnTop'] or 0) + (g['warnH'] or 0)
                res.check(ends < g['horizon'] + 4,
                          'and it clears the horizon, so it is not over the road ahead',
                          'banner ends at %s, horizon at %s' % (fmt(ends), fmt(g['horizon'])))

            # ---- ANCHORED, NOT PLACED -------------------------------------------------
            # The band has to FOLLOW the mirror, and the only way to show that is to move
            # the mirror and watch it come along. A number typed in at the right place today
            # passes every check above and fails this one.
            before = g['labelY']
            page.set_viewport_size({'width': 360, 'height': 780})
            page.wait_for_timeout(700)
            g2 = page.evaluate(GEOM)
            m2 = (g2['mirror']['y'] + g2['mirror']['h']) if g2['mirror'] else None
            print('      at 360x780: mirror ends %s, band %s' % (fmt(m2), g2['msgTopVar']))
            res.check(g2['labelY'] is not None and before is not None
                      and abs(g2['labelY'] - before) > 1,
                      'the band MOVES with the mirror, so it is anchored rather than placed',
                      'it was %s and is %s on a narrower screen'
                      % (fmt(before), fmt(g2['labelY'])))
            res.check(g2['rowBottom'] is not None and g2['warnTop'] is not None
                      and g2['warnTop'] >= g2['rowBottom'] - 1,
                      'and it is still below the row at the new size',
                      'banner at %s, row ends at %s' % (fmt(g2['warnTop']), fmt(g2['rowBottom'])))

            errs = page.evaluate("() => window.__probe.errors")
            res.check(not errs, 'no page errors', '; '.join(errs[:3]))
            page.close()
        browser.close()
    httpd.shutdown()

    print()
    if res.fails:
        print('FAILED: ' + '; '.join(res.fails))
        return 1
    print('all checks passed')
    return 0


def fmt(v):
    return 'none' if v is None else ('%.0f' % v)


sys.exit(main())
