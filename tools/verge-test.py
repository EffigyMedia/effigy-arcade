#!/usr/bin/env python3
"""VERGE TEST - rough ground shakes a car that is rolling over it, and nothing else.

    .venv/Scripts/python tools/verge-test.py

Owner, 2026-09-07: "When parked (stopped) on the shoulder of the road, the car still
shutters like I'm driving offroad but I'm stopped. It shouldn't do that."

The off-road shake was a constant. Being off the tarmac was the whole test, so a car
parked on the verge juddered exactly as hard as one crossing it at 90mph - which reads as
a fault in the picture rather than as rough ground, because nothing on screen is moving.

WHAT IT ASSERTS, and the third line is the one that keeps this honest:

  * parked on the verge, the picture is still
  * driving across it, the picture shakes
  * and the difference between the two is the SPEED, not the position

THE SECOND IS WHAT STOPS THE CHEAP FIX. Deleting the off-road handling would satisfy the
first on its own; with the block gone there is no shake at any speed and the second goes
red. What the verge COSTS you is `wall-test`'s subject and is untouched by this.
"""
import sys, threading, http.server, socketserver, functools
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from harness import launch_chromium, console_utf8, boot, until
from playwright.sync_api import sync_playwright

console_utf8()
handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
srv = socketserver.TCPServer(('127.0.0.1', 0), handler)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = f'http://127.0.0.1:{PORT}'


def main():
    bad = 0

    def ok(cond, label, detail=''):
        nonlocal bad
        if not cond:
            bad += 1
        print(f'  {"ok  " if cond else "FAIL"}  {label}' + (f'   {detail}' if detail else ''))

    print('verge-test  .  rough ground shakes a car that is moving')
    with sync_playwright() as p:
        b = launch_chromium(p, headless=True,
                            args=['--mute-audio', '--autoplay-policy=no-user-gesture-required'])
        ctx = b.new_context(viewport={'width': 480, 'height': 900})
        page = ctx.new_page()
        errs = []
        page.on('pageerror', lambda e: errs.append(str(e)))
        boot(page, f'{BASE}/games/sw/interstate.html')
        try:
            until(page, '() => navigator.serviceWorker && navigator.serviceWorker.controller', timeout=5000)
            page.wait_for_timeout(1200)
        except Exception:
            pass
        page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
        page.click('[data-act="play"]')
        page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
        page.click('[data-act="drive"]')
        page.wait_for_timeout(1500)
        # onto the verge, and the traffic out of the way so nothing else can shake it
        page.evaluate("() => { window.__road.traffic.length = 0; window.__road.copsClear(); }")

        def sample(frac, ticks=20):
            """Hold the car off the tarmac at `frac` of top speed and read the shake.

            IT SETTLES FIRST, and that is not a nicety. The car is still carrying speed
            from the launch for a second or two after the run begins, and a shake read
            during that is a reading of a car that has not stopped yet - which is exactly
            what the first version of this file measured, and it reported the fix broken.
            """
            for _ in range(14):
                page.evaluate('(f) => { const R = window.__road;'
                              ' R.setTarget(1.10); R.setSpd(f * R.MAX_SPD); }', frac)
                page.wait_for_timeout(100)
            worst = 0.0
            for _ in range(ticks):
                page.evaluate('(f) => { const R = window.__road;'
                              ' R.setTarget(1.10); R.setSpd(f * R.MAX_SPD); }', frac)
                page.wait_for_timeout(100)
                worst = max(worst, page.evaluate("() => window.__road.shake()"))
            return worst

        parked = sample(0.0)
        print(f'  ..    parked on the verge:      worst shake {parked:.4f}')
        ok(parked < 0.02, 'parked on the shoulder, the picture is still',
           f'worst shake {parked:.4f}')

        rolling = sample(0.30)
        print(f'  ..    driving across it at 60mph: worst shake {rolling:.4f}')
        ok(rolling > 0.15, 'and driving across it, the ground is rough again',
           f'worst shake {rolling:.4f}')
        ok(rolling > parked * 4 + 0.1, 'so the shake is about the SPEED, not the position',
           f'{rolling:.4f} moving against {parked:.4f} parked')

        # AND THE OFF-ROAD SPEED CEILING IS NOT CHECKED HERE, DELIBERATELY. It was, in the
        # first version, and the check was worthless: `setSpd` writes the speed straight
        # into the engine, past the acceleration model the ceiling lives in, so the car
        # read 13,280 against a 4,200 limit on a build where the limit was working
        # perfectly. That measured the harness, not the game.
        #
        # The second assertion above is what guards against the off-road handling being
        # deleted to make the first one pass: with the block gone there is no shake at any
        # speed, and it goes red. `wall-test` covers the speed the verge costs.
        ok(errs == [], 'no page errors', errs[0][:100] if errs else '')
        ctx.close()
        b.close()
    srv.shutdown()
    print(f"\n  {'the verge is rough, not haunted' if not bad else str(bad) + ' FAILURES'}")
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
