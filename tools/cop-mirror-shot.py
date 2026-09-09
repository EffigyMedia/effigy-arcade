#!/usr/bin/env python3
"""COP MIRROR SHOT - what is actually drawn on a cruiser in the rear-view glass.

    .venv/Scripts/python tools/cop-mirror-shot.py

RLG-177. Owner, 2026-09-08: "Why is there something that looks like a health bar or something
only visible on the police cruisers in the rearview mirror? Is this a render defect? I don't
want health bars in either view."

IT ASSERTS NOTHING. It is an instrument, like `mirror-shot.py`, and it exists because the two
candidate explanations cannot be told apart by reading code:

  a bar really is being drawn from the hidden `dmg` stat, and it must go; or

  the cruiser's LIGHT BAR - a short coloured horizontal rectangle across the roof - is being
  read as a health bar at 44-pixel mirror scale, and nothing is wrong except the size.

So a cruiser is parked behind the player at several distances and the glass is captured on its
own, enlarged, at both an undamaged and a heavily damaged cruiser. **If the thing changes with
damage it is a bar; if it does not, it is the light bar.** That comparison is the whole point of
the file, and it is why the same shot is taken twice.

The captures land in the scratchpad path given by --out.
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

/* the mirror pane, blown up, on its own - read out of the canvas rather than cropped from a
   screenshot, so it stays at the device pixels the engine actually drew */
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

# A cruiser directly behind, in the player's own lane, held there. `placeCop` clears the array
# first, so nothing else is in the glass to confuse the picture.
STAGE = """([dz, dmg]) => {
  const R = window.__probe.road;
  R.copsClear();
  R.placeCop(dz, 0.0);
  const k = R.cops()[0];
  k.from = 'test';
  k.dmg = dmg;
  k.onPlayer = true; k.engaged = true; k.tgt = null;
  k.tz = R.pos + R.PLAYER_Z; k.tx = 0; k.tSpd = 0;
  window.__hold = setInterval(() => {
    const kk = R.cops()[0];
    if(!kk) return;
    kk.z = R.pos + R.PLAYER_Z + dz; kk.x = 0; kk.dmg = dmg; kk.spd = R.MAX_SPD * 0.30;
  }, 8);
  return true;
}"""


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=None)
    ap.add_argument('--dz', default='-1400,-3000,-6000')
    ap.add_argument('--time', default='MIDDAY')
    args = ap.parse_args()
    console_utf8()
    out = Path(args.out) if args.out else ROOT / '_copmirror'
    out.mkdir(parents=True, exist_ok=True)

    handler = functools.partial(QuietHandler, directory=str(ROOT))
    srv = socketserver.TCPServer(('127.0.0.1', 0), handler)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    print('cop-mirror-shot  .  a cruiser in the glass, undamaged and wrecked')
    with sync_playwright() as p:
        browser = launch_chromium(p, headless=True)
        page = browser.new_page(viewport={'width': 480, 'height': 900})
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
        page.wait_for_timeout(300)
        page.click('[data-act="chase"]')
        page.wait_for_timeout(150)
        for _ in range(6):
            if page.eval_on_selector(
                    '[data-act="time"] b', 'el => el.textContent').strip() == args.time:
                break
            page.click('[data-act="time"]')
            page.wait_for_timeout(70)
        page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
        page.click('[data-act="drive"]')
        page.wait_for_timeout(2500)
        page.evaluate("() => window.__probe.road.setSpd(window.__probe.road.MAX_SPD * 0.30)")
        page.wait_for_timeout(1200)

        for dz in [float(v) for v in args.dz.split(',')]:
            for label, dmg in (('clean', 0), ('hurt', 95)):
                page.evaluate("() => { if(window.__hold) clearInterval(window.__hold); }")
                page.evaluate(STAGE, [dz, dmg])
                page.wait_for_timeout(700)
                data = page.evaluate('() => window.__probe.mirrorShot(8)')
                name = out / ('cop-dz%d-%s.png' % (int(dz), label))
                name.write_bytes(base64.b64decode(data.split(',', 1)[1]))
                look = page.evaluate("""() => {
                    const R = window.__probe.road, k = R.cops()[0];
                    return k ? { dmg: Math.round(k.dmg || 0),
                                 look: R.hurtLooks ? null : null } : null; }""")
                print('  wrote %s   (%s)' % (name, look))
        errs = page.evaluate('() => window.__probe.errors')
        if errs:
            print('  page errors: %s' % errs[:2])
        browser.close()
    srv.shutdown()
    return 0


if __name__ == '__main__':
    sys.exit(main())
