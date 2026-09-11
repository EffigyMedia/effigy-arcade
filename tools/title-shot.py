#!/usr/bin/env python3
"""
TITLE SHOT - the launcher's attract card and a machine's own title screen, side by side.

    .venv/Scripts/python tools/title-shot.py

RLG-077. The owner reported the wrong tail lights on "the title menu", and the fragment says to
settle which surface that is before building anything: the launcher's attract card and the game's
own title are different code paths, and the report fits either.

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
from harness import console_utf8, launch_chromium, boot


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
    args = ap.parse_args()
    console_utf8()
    out = Path(args.out) if args.out else ROOT / '_title'
    out.mkdir(parents=True, exist_ok=True)
    httpd, port = serve(ROOT)
    print('title-shot  .  which surface has the wrong lamps on it')
    with sync_playwright() as p:
        browser = launch_chromium(p, headless=True)
        ctx = browser.new_context(viewport={'width': 480, 'height': 900},
                                  device_scale_factor=2, has_touch=True, is_mobile=True)
        page = ctx.new_page()

        # ---- the launcher, and the cabinet card for the driving game
        boot(page, 'http://127.0.0.1:%d/index.html' % port)
        page.wait_for_timeout(2600)
        page.screenshot(path=str(out / 'launcher-rack.png'))
        card = page.query_selector('[data-id="interstate"]') or page.query_selector('.cab')
        if card:
            card.screenshot(path=str(out / 'launcher-card-interstate.png'))
            print('      wrote the launcher rack and the interstate card')
        else:
            print('      NO CARD FOUND on the rack')

        # ---- and the machine's own title screen
        boot(page, 'http://127.0.0.1:%d/games/sw/interstate.html' % port)
        page.wait_for_timeout(2600)
        page.screenshot(path=str(out / 'interstate-title.png'))
        print('      wrote the interstate title screen')

        # every canvas on the title, so a car drawn into one of them can be found
        info = page.evaluate("""() => [...document.querySelectorAll('canvas')].map(c => {
            const r = c.getBoundingClientRect();
            return { id:c.id||'(none)', w:c.width, h:c.height,
                     shown:r.width > 2 && r.height > 2,
                     x:Math.round(r.x), y:Math.round(r.y),
                     rw:Math.round(r.width), rh:Math.round(r.height) };
        })""")
        for c in info:
            print('      canvas %-12s %dx%d  on screen %s at %s,%s %sx%s'
                  % (c['id'], c['w'], c['h'], c['shown'], c['x'], c['y'], c['rw'], c['rh']))
        print('      veil: %s' % page.evaluate(
            "() => { const v = document.getElementById('veil');"
            " return v ? v.className + ' | ' + v.innerText.slice(0,60).replace(/\\n/g,' / ') : 'none'; }"))
        browser.close()
    httpd.shutdown()
    print('      wrote %s' % out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
