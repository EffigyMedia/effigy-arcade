#!/usr/bin/env python3
"""WALL TEST - the barrier holds you against it, and it never steers for you.

    .venv/Scripts/python tools/wall-test.py

Owner, 2026-09-07: "I don't want the player car to bounce back into the roadway. If you
hit the playable edge right now it pushes you back in."

THE LINE THAT DID IT WAS `targetX = playerX*0.7`, inside the off-road block, and it ran on
every frame the wall was touched. It parked the steering target three tenths of the way
back toward the middle, so the car drove itself off the barrier - and because it wrote the
target every frame, it also threw away whatever the thumb had just asked for. Against the
edge, the player was not the one steering.

WHAT THIS ASSERTS, and the middle one is the owner's sentence:

  * steering hard into the barrier actually REACHES it
  * letting go of the wheel leaves the car there, rather than returning it to the road
  * the verge still COSTS - `offRoad` caps the whole thing at OFF_SPD, and taking the
    shove away must not have taken the punishment with it

THE THIRD IS NOT DECORATION. The cheap way to satisfy the first two is to delete the
off-road block, which would also delete the speed cap and the scrub, and this file would
have gone green on a change that gave the verge away for free.

IT CANNOT PASS FALSELY. Run against the old line it reports the car pinning at 0.94 rather
than the wall - it never gets there, because the push-back fights the steering all the way -
and then drifting 0.16 back toward the middle once the wheel is released.
"""
import sys, threading, http.server, socketserver, functools
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from harness import launch_chromium, console_utf8
from playwright.sync_api import sync_playwright

console_utf8()
handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
srv = socketserver.TCPServer(('127.0.0.1', 0), handler)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = f'http://127.0.0.1:{PORT}'

WALL = 1.13          # where the off-road block pins the car
OFF_SPD = 4200       # the verge's speed ceiling, from road.js


def main():
    bad = 0

    def ok(cond, label, detail=''):
        nonlocal bad
        if not cond:
            bad += 1
        print(f'  {"ok  " if cond else "FAIL"}  {label}' + (f'   {detail}' if detail else ''))

    print('wall-test  .  the barrier holds, and it does not steer for you')
    with sync_playwright() as p:
        b = launch_chromium(p, headless=True,
                            args=['--mute-audio', '--autoplay-policy=no-user-gesture-required'])
        ctx = b.new_context(viewport={'width': 480, 'height': 900})
        page = ctx.new_page()
        errs = []
        page.on('pageerror', lambda e: errs.append(str(e)))
        page.goto(f'{BASE}/games/sw/interstate.html', wait_until='load')
        # the first visit reloads itself when the service worker claims the client
        try:
            page.wait_for_function(
                '() => navigator.serviceWorker && navigator.serviceWorker.controller', timeout=5000)
            page.wait_for_timeout(1200)
        except Exception:
            pass
        page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
        page.click('[data-act="play"]')
        page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
        page.click('[data-act="drive"]')
        page.wait_for_timeout(1500)
        page.evaluate("() => window.__road.setSpd && window.__road.setSpd(5000)")

        # PRESS INTO THE WALL. `setTarget` writes the steering target exactly as a thumb
        # does (RLG-048), so what follows is the car a player would have.
        for _ in range(20):
            page.evaluate("() => window.__road.setTarget(1.18)")
            page.wait_for_timeout(50)
        pinned = page.evaluate("() => window.__road.playerX")
        held_spd = page.evaluate("() => window.__road.spd")

        # AND NOW LET GO. Nothing writes the wheel from here; only the game moves the car.
        trace = []
        for _ in range(24):
            page.wait_for_timeout(50)
            trace.append(round(page.evaluate("() => window.__road.playerX"), 4))
        rest = trace[-1]

        print(f'  ..    pinned at {pinned:.4f}, released, came to rest at {rest:.4f}')
        print(f'  ..    the 1.2s after letting go: {trace[:12]}')
        ok(abs(pinned) >= WALL - 0.01,
           'steering into the barrier actually reaches it',
           f'pinned at {pinned:.4f}, the wall is {WALL}')
        # THE OWNER'S SENTENCE. The road's own corner push presses the car back onto the
        # wall and the clamp returns it, so the resting figure sawtooths by a hundredth or
        # two around the wall - which is the road steering, not the barrier. The old line
        # moved it by 0.16, an order of magnitude clear of that.
        ok(abs(pinned - rest) < 0.05,
           'letting go of the wheel leaves the car ON the wall',
           f'it moved {pinned - rest:+.4f} toward the middle')
        ok(held_spd <= OFF_SPD * 1.02,
           'and the verge still costs the speed it always did',
           f'{held_spd:.0f} against the off-road ceiling of {OFF_SPD}')
        ok(errs == [], 'no page errors', errs[0][:100] if errs else '')
        ctx.close()
        b.close()
    srv.shutdown()
    print(f"\n  {'the wall holds' if not bad else str(bad) + ' FAILURES'}")
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
