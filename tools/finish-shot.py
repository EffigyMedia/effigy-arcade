#!/usr/bin/env python3
"""FINISH SHOT - a car on the finish line, so the draw order can be seen.

    .venv/Scripts/python tools/finish-shot.py --out <dir>

RLG-179. Owner, 2026-09-08: "the finish line renders before vehicles. The part of the finish line
it's on the ground should render after vehicles, but the gantry up above it up and across the road
should render after vehicles vehicles drive through it."

IT ASSERTS NOTHING. The report is dictated and its middle contradicts itself - both halves say
"after vehicles" - so the first job is to SEE what the frame actually does rather than to argue
from the sentence. `cop-mirror-shot.py` was written for the same reason on the same day, and it
turned a two-way guess into a one-line answer.

A CAR IS PUT ON THE LINE ON PURPOSE. The whole question is what happens where the two overlap, and
a finish line with no car near it shows nothing at all.
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

# The finish put a set distance AHEAD (parkFinish takes a distance BEHIND, so this is
# negative), with traffic parked across it in three lanes.
STAGE = """(dz) => {
  const R = window.__road, M = R.MAX_SPD;
  R.parkFinish(-dz);
  R.traffic.length = 0;
  /* BUILT BY THE ENGINE, NOT BY THIS FILE. A hand-written traffic object is enough
     to be in the array and not enough to be PAINTED - a first version pushed four of
     them across the line and captured a finish line with no cars anywhere near it.
     `placePatrol` is the road's own builder and it puts a real car at a chosen
     distance, so what is photographed is a car the game made. */
  R.placePatrol(dz - 520);
  window.__hold = setInterval(() => {
    R.parkFinish(-dz);
    if(!R.traffic.length) R.placePatrol(dz - 520);
    const now = R.pos + R.PLAYER_Z;
    /* HALF A CAR SHORT OF THE LINE, which is where the overlap actually is. Sat
       exactly ON it, the car's base and the line's top edge only touch - the first
       captures showed a car hovering just above the chequer and settled nothing. */
    for(const c of R.traffic){ c.z = now + dz - 520; c.spd = M * 0.30; c.x = 0.30; }
  }, 16);
  return R.traffic.length;
}"""


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=None)
    ap.add_argument('--dz', default='2600,4200,7000')
    args = ap.parse_args()
    console_utf8()
    out = Path(args.out) if args.out else ROOT / '_finish'
    out.mkdir(parents=True, exist_ok=True)

    handler = functools.partial(QuietHandler, directory=str(ROOT))
    srv = socketserver.TCPServer(('127.0.0.1', 0), handler)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    print('finish-shot  .  a car on the line')
    with sync_playwright() as p:
        browser = launch_chromium(p, headless=True,
                                  args=['--mute-audio',
                                        '--autoplay-policy=no-user-gesture-required'])
        ctx = browser.new_context(viewport={'width': 480, 'height': 900},
                                  device_scale_factor=2)
        page = ctx.new_page()
        errs = []
        page.on('pageerror', lambda e: errs.append(str(e)))
        boot(page, 'http://127.0.0.1:%d/%s' % (port, GAME))
        try:
            until(page, '() => navigator.serviceWorker && navigator.serviceWorker.controller',
                timeout=5000)
            page.wait_for_timeout(1200)
        except Exception:
            pass
        page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
        page.click('[data-act="play"]')
        page.wait_for_timeout(300)
        for _ in range(6):
            t = page.eval_on_selector('[data-act="time"] b', 'el => el.textContent').strip()
            if t == 'MIDDAY':
                break
            page.click('[data-act="time"]')
            page.wait_for_timeout(70)
        page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
        page.click('[data-act="drive"]')
        page.wait_for_timeout(2500)
        page.evaluate('() => window.__road.setSpd(window.__road.MAX_SPD * 0.25)')
        page.wait_for_timeout(600)

        for dz in [int(v) for v in args.dz.split(',')]:
            page.evaluate("() => { if(window.__hold) clearInterval(window.__hold); }")
            n = page.evaluate(STAGE, dz)
            page.wait_for_timeout(700)
            name = out / ('finish-dz%d.png' % dz)
            # THE WHOLE FRAME, not a crop. A crop of the middle hid the close case
            # entirely: at 1,500 units the car is drawn low and large and fell below
            # the window, which read as "the car vanished" on a build that was fine.
            name.write_bytes(page.screenshot())
            print('  wrote %s   (%d cars on the line)' % (name, n))
        if errs:
            print('  page errors: %s' % errs[:2])
        ctx.close()
        browser.close()
    srv.shutdown()
    return 0


if __name__ == '__main__':
    sys.exit(main())
