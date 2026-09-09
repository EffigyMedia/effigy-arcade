#!/usr/bin/env python3
"""STARS SHOT - the wanted stars in each state, enlarged.

    .venv/Scripts/python tools/stars-shot.py --out <dir>

RLG-178. Owner, 2026-09-08: "If you are actively being engaged then the stars' fill is golden.
If you are on active cooldown the fill is the same colour as the blue edge, to represent being
cold instead of hot. The outline of the stars should be gold when you're hot and blue when
you're cold, along with the fill. Can you make that change and show me screenshots of the
different states?"

IT ASSERTS NOTHING. It is an instrument: the owner asked to SEE this, and a description of a
colour is not a colour. `mirror-shot.py` exists for the same reason and this follows it.

THE STATE IS SET THROUGH THE ENGINE, not by writing a class onto the element. Putting `hot` on
the row by hand would photograph this file's idea of the rule rather than the rule - the engine
decides hot from whether a cruiser is engaged to the player, so the shots stage a cruiser and
let it decide.
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

# A cruiser engaged to the player, held there, so the engine reports hot.
HOT = """() => {
  const R = window.__road;
  R.copsClear();
  R.placeCop(-2600, 0.35);
  const k = R.cops()[0];
  k.from = 'test';
  window.__hold = setInterval(() => {
    const kk = R.cops()[0];
    if(!kk) return;
    kk.z = R.pos + R.PLAYER_Z - 2600;
    kk.onPlayer = true; kk.engaged = true; kk.tgt = null; kk.wreck = 0;
  }, 8);
  return true;
}"""

COLD = """() => {
  const R = window.__road;
  if(window.__hold) clearInterval(window.__hold);
  R.copsClear();
  /* and keep the road clear, or the spawner puts one back mid-shot */
  window.__hold = setInterval(() => { R.copsClear(); }, 60);
  return true;
}"""


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=None)
    args = ap.parse_args()
    console_utf8()
    out = Path(args.out) if args.out else ROOT / '_stars'
    out.mkdir(parents=True, exist_ok=True)

    handler = functools.partial(QuietHandler, directory=str(ROOT))
    srv = socketserver.TCPServer(('127.0.0.1', 0), handler)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    print('stars-shot  .  the wanted row, hot and cold')
    with sync_playwright() as p:
        browser = launch_chromium(p, headless=True,
                                  args=['--mute-audio',
                                        '--autoplay-policy=no-user-gesture-required'])
        # DEVICE SCALE 4, so the row is captured at four times the pixels the phone
        # draws rather than being enlarged afterwards. Scaling a 19px glyph up after
        # the fact photographs the resampling, not the stroke.
        ctx = browser.new_context(viewport={'width': 480, 'height': 900},
                                  device_scale_factor=4)
        page = ctx.new_page()
        errs = []
        page.on('pageerror', lambda e: errs.append(str(e)))
        page.goto('http://127.0.0.1:%d/%s' % (port, GAME), wait_until='load')
        try:
            page.wait_for_function(
                '() => navigator.serviceWorker && navigator.serviceWorker.controller',
                timeout=5000)
            page.wait_for_timeout(1200)
        except Exception:
            pass
        page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
        page.click('[data-act="play"]')
        page.wait_for_timeout(300)
        page.click('[data-act="chase"]')          # the stars only show with pursuit on
        page.wait_for_timeout(150)
        page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
        page.click('[data-act="drive"]')
        page.wait_for_timeout(2500)

        shots = [
            ('1-cold-none',    COLD, 0, 'cold, nothing on you'),
            ('2-cold-partway', COLD, 1, 'cold, one star and part of the next'),
            ('3-cold-three',   COLD, 3, 'cold, three stars'),
            ('4-hot-one',      HOT,  1, 'hot, one star'),
            ('5-hot-three',    HOT,  3, 'hot, three stars'),
            ('6-hot-five',     HOT,  5, 'hot, five stars'),
        ]
        for name, stage, hv, label in shots:
            page.evaluate("() => { if(window.__hold) clearInterval(window.__hold); }")
            page.evaluate(stage)
            page.evaluate('(v) => window.__road.heat(v)', hv)
            page.evaluate('() => window.__road.setSpd(window.__road.MAX_SPD * 0.55)')
            page.wait_for_timeout(700)
            page.evaluate('(v) => window.__road.heat(v)', hv)
            page.wait_for_timeout(400)
            el = page.query_selector('#wantedWrap')
            state = page.evaluate(
                "() => { const w = document.getElementById('wanted');"
                " return { hot: w ? w.classList.contains('hot') : null,"
                "          stars: w ? w.innerHTML.replace(/<[^>]*>/g,'|') : null }; }")
            png = el.screenshot()
            (out / ('stars-%s.png' % name)).write_bytes(png)
            print('  wrote stars-%s.png   %-34s hot=%s' % (name, label, state['hot']))

        # and the whole HUD once, so the row is seen in the place it lives
        page.evaluate("() => { if(window.__hold) clearInterval(window.__hold); }")
        page.evaluate(HOT)
        page.evaluate('() => window.__road.heat(3)')
        page.wait_for_timeout(700)
        hud = page.query_selector('#hud') or page.query_selector('#frame')
        if hud:
            (out / 'stars-7-in-the-hud.png').write_bytes(hud.screenshot())
            print('  wrote stars-7-in-the-hud.png')
        if errs:
            print('  page errors: %s' % errs[:2])
        ctx.close()
        browser.close()
    srv.shutdown()
    return 0


if __name__ == '__main__':
    sys.exit(main())
