#!/usr/bin/env python3
"""
MIRROR SHOT - capture the rear-view glass, enlarged, at several eye heights.

    .venv/Scripts/python tools/mirror-shot.py

RLG-079. The mirror's eye height has been changed three times from a written description of what is
wrong with it, and the owner has reported it wrong after every one. A description is not a picture,
and this project's own guidance says to check the artifact rather than the source.

So this parks a car behind the player at a fixed distance, captures the mirror pane on its own at a
range of eye heights, and writes them to the scratchpad enlarged, so the difference between them can
be SEEN rather than argued from the projection.

It asserts nothing. It is an instrument, not a gate.
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

/* The mirror pane, blown up, on its own. Reading it out of the canvas rather than cropping a
   screenshot keeps it at the device pixels the engine actually drew. */
window.__probe.mirrorShot = function(zoom){
  var c = document.querySelector('canvas');
  var dpr = c.width / c.getBoundingClientRect().width;
  var W = c.getBoundingClientRect().width;
  var mw = Math.min(W * 0.62, 250), mh = 44;
  var mx = (W - mw) / 2, my = 6;
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

PARK_TRAFFIC = """(dz) => {
  const R = window.__probe.road;
  R.setSpd(0);
  /* something to look at: the nearest car behind, put at a known distance */
  return R.parkBehind ? R.parkBehind(dz) : null;
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=None)
    ap.add_argument('--eyes', default='1.20,2.15,3.00')
    ap.add_argument('--horizons', default='0.45')
    ap.add_argument('--weather', default='',
                    help='snow | rain | dry - set the world state before shooting')
    ap.add_argument('--time', default='MIDDAY')
    args = ap.parse_args()
    console_utf8()
    out = Path(args.out) if args.out else ROOT / '_mirror'
    out.mkdir(parents=True, exist_ok=True)
    httpd, port = serve(ROOT)
    print('mirror-shot  .  the glass, enlarged, at several eye heights')
    with sync_playwright() as p:
        browser = launch_chromium(p, headless=True)
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
        for _ in range(6):
            if page.eval_on_selector('[data-act="time"] b', 'el => el.textContent').strip() == args.time:
                break
            page.click('[data-act="time"]')
            page.wait_for_timeout(70)
        page.click('[data-act="drive"]')
        page.wait_for_timeout(2500)
        # let some traffic gather behind, then stop so the frame holds still
        page.evaluate("() => window.__probe.road.setSpd(window.__probe.road.MAX_SPD * 0.5)")
        page.wait_for_timeout(3000)
        page.evaluate("() => window.__probe.road.setSpd(0)")
        page.wait_for_timeout(400)
        if args.weather == 'snow':
            page.evaluate("() => { const R = window.__probe.road;"
                          " R.setBiomePair('TUNDRA','TUNDRA'); R.setWet(0.9); R.setSnow(1); }")
        elif args.weather == 'rain':
            page.evaluate("() => { const R = window.__probe.road;"
                          " R.setSnow(0); R.setWet(1); R.setPool(1); }")
        elif args.weather == 'dry':
            page.evaluate("() => { const R = window.__probe.road;"
                          " R.setWet(0); R.setSnow(0); R.setPool(0); }")
        page.wait_for_timeout(500)

        import base64
        for hz in [float(v) for v in args.horizons.split(',')]:
          page.evaluate('(v) => window.__probe.road.mirrorHorizon(v)', hz)
          for eye in [float(v) for v in args.eyes.split(',')]:
            page.evaluate('(v) => window.__probe.road.mirrorEye(v)', eye)
            page.wait_for_timeout(300)
            data = page.evaluate('() => window.__probe.mirrorShot(4)')
            name = out / ('mirror-h%.2f-e%.2f.png' % (hz, eye))
            name.write_bytes(base64.b64decode(data.split(',', 1)[1]))
            print('  wrote %s' % name)
        browser.close()
    httpd.shutdown()
    return 0


if __name__ == '__main__':
    sys.exit(main())
