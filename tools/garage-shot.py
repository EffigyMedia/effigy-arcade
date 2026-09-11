#!/usr/bin/env python3
"""GARAGE SHOT - the garage card for a car you own and one you have not won.

    .venv/Scripts/python tools/garage-shot.py --out <dir>

RLG-180. The owner asked for locked cars as grey silhouettes with the way to win them written
underneath, and a silhouette is a thing to look at rather than a thing to describe.

IT ASSERTS NOTHING. It walks the garage with the real arrows - the same taps a thumb makes - and
captures the card at each car, so what is photographed is the screen rather than a staged element.
"""
import argparse, functools, http.server, socketserver, sys, threading
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from harness import console_utf8, launch_chromium, boot, until

GAME = 'games/sw/interstate.html'


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=None)
    ap.add_argument('--cars', type=int, default=14)
    ap.add_argument('--only', default=None, help='capture just this car, by name')
    args = ap.parse_args()
    console_utf8()
    out = Path(args.out) if args.out else ROOT / '_garage'
    out.mkdir(parents=True, exist_ok=True)
    srv = socketserver.TCPServer(('127.0.0.1', 0),
                                 functools.partial(Quiet, directory=str(ROOT)))
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    print('garage-shot  .  walking the garage')
    with sync_playwright() as p:
        b = launch_chromium(p, headless=True,
                            args=['--mute-audio', '--autoplay-policy=no-user-gesture-required'])
        ctx = b.new_context(viewport={'width': 480, 'height': 900}, device_scale_factor=2)
        page = ctx.new_page()
        errs = []
        page.on('pageerror', lambda e: errs.append(str(e)))
        boot(page, 'http://127.0.0.1:%d/%s' % (port, GAME))
        try:
            until(page, '() => navigator.serviceWorker && navigator.serviceWorker.controller', timeout=5000)
            page.wait_for_timeout(1200)
        except Exception:
            pass
        page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
        page.click('[data-act="play"]')
        page.wait_for_timeout(500)
        # HOW MANY CARS THE GARAGE HOLDS, asked of the engine. The walk used to stop
        # when a name repeated, which broke the moment locked cars started showing
        # `???` - every one of them has the same name now, so the second locked card
        # looked like a car already seen and the walk ended three cards in.
        total = page.evaluate("() => window.__road.garageBodies().length")
        print('  the garage lists %d car(s)' % total)
        seen = []
        for i in range(total):
            page.wait_for_timeout(300)
            info = page.evaluate("""() => {
                const n = document.querySelector('.gname');
                const l = document.querySelector('.gnote.lock');
                const d = document.querySelector('[data-act="drive"]');
                const how = document.querySelectorAll('.gwrap .gnote');
                return { name: n ? n.textContent.trim() : null,
                         locked: !!l,
                         how: how.length > 1 ? how[1].textContent.trim() : null,
                         drive: d ? d.textContent.trim() : null,
                         disabled: d ? d.hasAttribute('disabled') : null };
            }""")
            seen.append(info['name'])
            real = page.evaluate("() => window.__road.currentBody()") or ('car%02d' % i)
            tag = 'locked' if info['locked'] else 'owned'
            # AND THE FILE IS NAMED BY POSITION, not by the card. `???` is not a legal
            # Windows filename and the capture died on it.
            el = page.query_selector('.gwrap')
            if el and (not args.only or args.only.upper() == (info['name'] or '').upper()
                       or args.only.upper() == real.upper()):
                el.screenshot(path=str(out / ('garage-%02d-%s-%s.png' % (i, tag, real))))
            print('  %-14s %-7s drive=%-7s disabled=%s   %s'
                  % (info['name'], tag, info['drive'], info['disabled'], info['how'] or ''))
            page.click('[data-act="next"]')
        if errs:
            print('  page errors: %s' % errs[:2])
        ctx.close()
        b.close()
    srv.shutdown()
    return 0


if __name__ == '__main__':
    sys.exit(main())
