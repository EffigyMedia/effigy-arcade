#!/usr/bin/env python3
"""SKY CAP PROOF - the canyon's horizon is capped to the WALL, and the frame shows it.

    .venv/Scripts/python tools/sky-cap-proof.py

RLG-304. Owner, 2026-09-20: 'as for the skyline, in the canyon, we should rise it up to
meet the height of the now three D canyon walls.'

RLG-104 SET THE RULE AND IT HAS NOT CHANGED: nothing at the horizon may stand taller on
screen than the last thing the road pass draws, or the eye is told that the furthest object
is the nearest one. What changed is the OBJECT. The cap was derived from the tallest rock
SPRITE the road pass could place, because in 2026-09-01 that was the wall. RLG-297 replaced
the rock with a continuous plane and RLG-300 stopped drawing rock on a walled side at all,
so the cap was measuring something the place does not draw.

THIS PROVES THE TWO ARE WIRED TOGETHER, WHICH IS THE WHOLE RULING. `canyon-test` already
asserts that the skyline stands no taller than the wall, and it passed BEFORE this change
as well - both numbers were simply smaller. A ratio that holds at one wall height says
nothing. So the wall is MOVED and the horizon has to move with it, in the arithmetic and
in the pixels.

    THE ARITHMETIC. `skyRiseOf` answers the wall's own expression, so halving `WALL_RISE`
    halves the cap. A cap still reading the rock spec would not move at all, which is the
    falsification and is what this used to do.

    AND THE PAINT. RLG-302's lesson is that a check reporting what a program calculated is
    not evidence that anything was drawn with it. `skyBandDrawn` is written INSIDE `paint`,
    from the height `drawImage` is handed, the way `dropTrace` and `wallTrace` already are.
    So the band the frame was given has to move by the same factor as the cap.

WHAT IT CANNOT DO. It reads the size the band was drawn at, not the pixels that landed - a
clip or an alpha of nothing would still record a height. `canyon-test` reads the silhouette
itself. And nothing here can say whether the taller band still leaves a strip of sky that
reads as a slot canyon: that is the owner's on a device, and RLG-304 says so.

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


def read_at(page, rise):
    """Set the wall's height, let two frames land, and read what the band was drawn at."""
    page.evaluate("(v) => window.__probe.road.wallModel({ rise: v })", rise)
    page.wait_for_timeout(400)
    return page.evaluate("""() => {
      const R = window.__probe.road;
      const px = R.skylineVsWall('CANYON'), drawn = R.skyBandDrawn('CANYON');
      return { skyRise: R.skyRise('CANYON'), sky: px.sky, wall: px.wall, rock: px.rock,
               band: drawn ? drawn.h : null, top: drawn ? drawn.top : null,
               horizon: R.horizon() };
    }""")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--headed', action='store_true')
    args = ap.parse_args()
    console_utf8()
    res = Results()
    httpd, port = serve(ROOT)
    print('sky-cap-proof  .  the canyon horizon is capped to the wall, in the frame')
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

        # ONE PLACE, HELD STILL. The pair is pinned so the horizon is the canyon's alone -
        # with two places on the board the band is painted twice and the trace would hold
        # whichever went last.
        page.evaluate("""() => {
          const R = window.__probe.road;
          R.setTimed(false); R.setSpd(0); R.holdSpd(0);
          R.setBiomePair('CANYON', 'CANYON');
          R.setPhase(0.30);
        }""")
        page.wait_for_timeout(900)

        print()
        print('  THE CAP IS THE WALL, NOT THE ROCK')
        base = read_at(page, 6)
        print('      skyline %.1f px   wall %.1f px   loose rock %.1f px'
              % (base['sky'], base['wall'], base['rock']))
        res.check(abs(base['sky'] - base['wall']) <= 0.6,
                  'the canyon band is the wall height, to the pixel',
                  'skyline %.1f against wall %.1f' % (base['sky'], base['wall']))
        res.check(base['sky'] > base['rock'] * 1.3,
                  'and it stands well above the rock it used to be capped to',
                  'skyline %.1f against rock %.1f' % (base['sky'], base['rock']))

        print()
        print('  AND THE TWO MOVE TOGETHER, WHICH IS THE WHOLE RULING')
        half = read_at(page, 3)
        print('      WALL_RISE 6 -> cap %.4f, band painted %.1f px tall'
              % (base['skyRise'], base['band'] or -1))
        print('      WALL_RISE 3 -> cap %.4f, band painted %.1f px tall'
              % (half['skyRise'], half['band'] or -1))
        res.check(abs(half['skyRise'] - base['skyRise'] / 2) < 0.002,
                  'halving the wall halves the cap',
                  '%.4f against half of %.4f' % (half['skyRise'], base['skyRise']))
        # THE PAINT, NOT THE ARITHMETIC (RLG-302). A cap nothing draws with would leave the
        # band exactly the size it already was.
        res.check(base['band'] and half['band'],
                  'the band was painted at both heights',
                  'bands %r and %r' % (base['band'], half['band']))
        if base['band'] and half['band']:
            res.check(abs(base['band'] - base['sky']) <= 1.0,
                      'and what was painted is the cap, not a second answer to it',
                      'painted %.1f against a cap of %.1f' % (base['band'], base['sky']))
            ratio = half['band'] / float(base['band'])
            print('      the painted band moved by a factor of %.3f' % ratio)
            res.check(0.45 <= ratio <= 0.55,
                      'and the PAINTED band halves with the wall',
                      'the band ratio is %.3f, not about a half' % ratio)

        page.evaluate("() => window.__probe.road.wallModel({ rise: 6 })")
        errs = page.evaluate("() => window.__probe.errors")
        res.check(not errs, 'no page errors', str(errs))
        browser.close()
    httpd.shutdown()

    print()
    if res.fails:
        print('FAILED: ' + '; '.join(res.fails))
        return 1
    print('PASSED: the canyon horizon is the canyon wall, and the frame agrees')
    return 0


if __name__ == '__main__':
    sys.exit(main())
