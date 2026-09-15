#!/usr/bin/env python3
"""GARAGE SCALE - every car in the garage is drawn at one scale, so its size on the card is its true size.

    .venv/Scripts/python tools/garage-scale-test.py

RLG-246. Owner, 2026-09-14: "All the cars shown in the garage need to be the same relative size. Do not
normalize the sizes."

THE YARDSTICK IS HOW THE ROAD DRAWS A CAR. On the road every player car's sprite canvas is drawn one
car wide (PLAYER_W), whatever the body - so a sprite pixel is worth `1 / spriteW` of a car width. At one
scale, a car's painted width on the card, times `spriteW / inkW`, is the same number for every car: the
card width of one whole canvas. A card that fits each car to itself makes that number swing with the
ink, because it gives a narrow car and a wide car the same painted width.

THE FIRST YARDSTICK WAS WRONG AND IS RECORDED SO IT IS NOT TRIED AGAIN. It divided the card width by
`playerWidthOf`, the road COLLIDER width. That is the body alone, and the card's ink includes the door
mirrors, which stand out by nearly the same amount on every car - so the ratio varied by 34 % on a
build that was drawing at one scale.

    one scale      card width x spriteW / inkW agrees within 3 % across every ordinary garage car.
                   Card pixels are read off the canvas, so rounding to whole pixels is the tolerance.
    fits           no car's ink touches the card's left or right edge, so one scale clipped nothing.

Oversized bodies (the `big` tier) are left out: they get a taller card by RLG-087, and the width check
still covers them only if they are in the garage.

Exit code 0 if every check passes, 1 otherwise.
"""

import functools
import http.server
import socketserver
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from harness import console_utf8, launch_chromium, boot  # noqa: E402

INK = """() => {
  const cv = document.getElementById('gcar');
  if(!cv) return null;
  const g = cv.getContext('2d'), w = cv.width, h = cv.height;
  const d = g.getImageData(0, 0, w, h).data;
  let x0 = w, x1 = -1;
  for(let y = 0; y < h; y++) for(let x = 0; x < w; x++)
    if(d[(y*w + x)*4 + 3] > 8){ if(x < x0) x0 = x; if(x > x1) x1 = x; }
  const k = w / 300;
  return x1 < 0 ? null : { x0: x0 / k, x1: (x1 + 1) / k, w: (x1 - x0 + 1) / k };
}"""


class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def main():
    console_utf8()
    httpd = socketserver.TCPServer(('127.0.0.1', 0), functools.partial(Q, directory=str(ROOT)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = 'http://127.0.0.1:%d' % httpd.socket.getsockname()[1]
    fails = []

    def ok(good, label, detail=''):
        print(('  ok    ' if good else '  FAIL  ') + label + ('' if good else '   [' + detail + ']'))
        if not good:
            fails.append(label)

    print('garage-scale  .  one scale for every car in the garage')
    with sync_playwright() as p:
        b = launch_chromium(p, headless=True, args=['--mute-audio'])
        page = b.new_context(viewport={'width': 480, 'height': 900}).new_page()
        errs = []
        page.on('pageerror', lambda e: errs.append(str(e)))
        boot(page, base + '/games/sw/interstate.html')
        page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
        page.click('[data-act="play"]')
        page.wait_for_selector('#veil:not(.hidden) [data-act="back"]', timeout=5000)
        ends = page.evaluate("() => window.__road.carEnds()")
        big = page.evaluate("() => window.__road.garageFits().big")
        bodies = page.evaluate("() => window.__road.garageBodies()")
        rows, clipped = [], []
        for k in bodies:
            e = ends.get(k)
            if big.get(k) or not e or not e['front'] or not e['front'].get('spriteW'):
                continue
            page.evaluate("(k) => { const R = window.__road; R.setBody(k); R.showGarage(); }", k)
            page.wait_for_timeout(150)
            ink = page.evaluate(INK)
            if not ink:
                continue
            f = e['front']
            unit = ink['w'] * f['spriteW'] / f['inkW']
            rows.append((k, ink['w'], unit))
            if ink['x0'] <= 0.5 or ink['x1'] >= 299.5:
                clipped.append(k)
        for k, w, u in sorted(rows, key=lambda t: t[1]):
            print('      %-13s card %5.1f px   one car width %6.1f px' % (k, w, u))
        if len(rows) < 3:
            ok(False, 'at least three ordinary cars were measured', 'measured %d' % len(rows))
        else:
            us = [u for *_, u in rows]
            spread = max(us) / min(us)
            ok(spread <= 1.03, 'every car is drawn at one scale',
               'one car width ranges %.1f to %.1f px, %.0f %% apart'
               % (min(us), max(us), (spread - 1) * 100))
        ok(not clipped, 'and no car is clipped by the card', ', '.join(clipped))
        ok(not errs, 'no page errors', errs[0][:120] if errs else '')
        b.close()
    httpd.shutdown()
    print()
    if fails:
        print('FAILED: ' + '; '.join(fails))
        return 1
    print('every car in the garage is at one scale')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
