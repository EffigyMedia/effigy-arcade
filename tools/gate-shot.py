#!/usr/bin/env python3
"""
GATE SHOT - the manual shifter's gate, enlarged, for a car of each gear count.

    .venv/Scripts/python tools/gate-shot.py

RLG-069. The gate drew three rails and six slots for every car, and the plate was a six-speed's
footprint whatever the car had. Both halves are geometry, and geometry is settled by looking at it -
this project has spent three fixes on the mirror's eye height reasoning from a description.

It asserts nothing. It is an instrument, not a gate.
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

/* the shifter's own box, in CSS pixels, so a screenshot can be cropped to it */
window.__probe.gateBox = function(){
  var el = document.getElementById('shifter');
  if(!el || el.hidden) return null;
  var r = el.getBoundingClientRect();
  var k = document.getElementById('knob').getBoundingClientRect();
  return { x:r.x, y:r.y, w:r.width, h:r.height,
           knob:{ x:+(k.x - r.x).toFixed(1), y:+(k.y - r.y).toFixed(1) },
           cls:document.body.className.split(/\s+/).filter(function(c){
                 return /^gears|^manual$/.test(c); }).join(' ') };
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=None)
    ap.add_argument('--cars', default='SEMI,MUSCLE,ROADSTER,TUNER,SUPERCRUISER')
    args = ap.parse_args()
    console_utf8()
    out = Path(args.out) if args.out else ROOT / '_gate'
    out.mkdir(parents=True, exist_ok=True)
    httpd, port = serve(ROOT)
    print('gate-shot  .  the gate, for a car of each gear count')
    with sync_playwright() as p:
        browser = launch_chromium(p, headless=True)
        # A PHONE, BECAUSE THE THUMB CLUSTER IS NOT DRAWN WITHOUT ONE. The shell adds
        # `no-touch` to the body when the device reports no touch, and the whole cluster -
        # wheel, pedals and shifter - is display:none under it. A desktop context captures
        # an empty rectangle and reports success.
        page = browser.new_context(viewport={'width': 480, 'height': 900},
                                   device_scale_factor=2, has_touch=True,
                                   is_mobile=True).new_page()
        page.add_init_script(INIT)
        page.goto('http://127.0.0.1:%d/%s' % (port, GAME), wait_until='load')
        try:
            page.wait_for_function(
                '() => navigator.serviceWorker && navigator.serviceWorker.controller', timeout=5000)
            page.wait_for_timeout(1200)
        except Exception:
            pass
        page.wait_for_function('!!window.__probe.road', timeout=10000)
        page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
        page.click('[data-act="play"]')
        page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
        # the manual box, which is what draws a gate at all
        for _ in range(4):
            label = page.eval_on_selector('[data-act="box"] b', 'el => el.textContent').strip()
            if label.startswith('MANUAL'):
                break
            page.click('[data-act="box"]')
            page.wait_for_timeout(80)
        print('      gearbox: %s'
              % page.eval_on_selector('[data-act="box"] b', 'el => el.textContent').strip())
        page.click('[data-act="drive"]')
        page.wait_for_timeout(1200)

        for key in args.cars.split(','):
            page.evaluate('(k) => window.__probe.road.setBody(k)', key)
            page.wait_for_timeout(260)
            gears = page.evaluate('(k) => (window.__probe.road.BODY[k]||{}).gears || 6', key)
            box = page.evaluate('() => window.__probe.gateBox()')
            if not box:
                print('      %-14s %d-speed   NO GATE (paddles)' % (key, gears))
                continue
            print('      %-14s %d-speed   plate %.0fx%.0f  knob at %s  [%s]'
                  % (key, gears, box['w'], box['h'], box['knob'], box['cls']))
            pad = 8
            shot = page.screenshot(clip={'x': box['x'] - pad, 'y': box['y'] - pad,
                                         'width': box['w'] + pad*2, 'height': box['h'] + pad*2})
            (out / ('gate-%s-%dspd.png' % (key.lower(), gears))).write_bytes(shot)
        print('      wrote %s' % out)
        errs = page.evaluate('() => window.__probe.errors')
        print('      errors:', errs or 'none')
        browser.close()
    httpd.shutdown()
    return 0


if __name__ == '__main__':
    sys.exit(main())
