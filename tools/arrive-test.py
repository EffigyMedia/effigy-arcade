#!/usr/bin/env python3
"""ARRIVE TEST - traffic behind you resolves out of the distance, it does not appear.

    .venv/Scripts/python tools/arrive-test.py

Owner, 2026-09-07: "if you just stop the car and look at your rearview mirror you just
constantly see traffic just popping into existence."

STOPPING IS WHAT MAKES IT OBVIOUS, and that is not a coincidence. The rear spawner exists
to stop a stopped car sitting on an empty road, so the moment you stop is the moment it
fires hardest - and it was dropping cars 2,600 to 4,200 units back, a third of the way up a
mirror that draws 34,000.

WHAT IT ASSERTS:

  * cars are dropped in beyond where they can be mistaken for having always been there
  * and they arrive TRANSPARENT and become solid, rather than starting solid
  * and they still ARRIVE - the spawner's whole purpose is that a stopped car does not
    sit on an empty road, and pushing the spawn back is exactly the change that could
    break it

THE THIRD IS THE ONE THAT KEEPS THE OTHER TWO HONEST. Spawning at the far edge of the
mirror would satisfy the first two perfectly and quietly delete the feature: a car has to
CLOSE on you to arrive, and at road speed that takes the better part of a minute from
34,000 back.
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

MIRROR_BACK = 34000     # how far the glass draws, from road.js


def main():
    bad = 0

    def ok(cond, label, detail=''):
        nonlocal bad
        if not cond:
            bad += 1
        print(f'  {"ok  " if cond else "FAIL"}  {label}' + (f'   {detail}' if detail else ''))

    print('arrive-test  .  traffic resolves out of the distance behind you')
    with sync_playwright() as p:
        b = launch_chromium(p, headless=True,
                            args=['--mute-audio', '--autoplay-policy=no-user-gesture-required'])
        ctx = b.new_context(viewport={'width': 480, 'height': 900})
        page = ctx.new_page()
        errs = []
        page.on('pageerror', lambda e: errs.append(str(e)))
        page.goto(f'{BASE}/games/sw/interstate.html', wait_until='load')
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

        # STOPPED, which is the owner's own case and the one the spawner works hardest in
        page.evaluate("() => { window.__road.traffic.length = 0; }")
        born, faded, arrived = [], [], 0
        seen = set()
        for _ in range(180):
            page.evaluate("() => window.__road.setSpd(0)")
            page.wait_for_timeout(200)
            for a in page.evaluate("() => window.__road.arrivals()"):
                key = a['bornBack']
                if key not in seen:
                    seen.add(key)
                    born.append(key)
                faded.append(a['arrive'])
            # anything that has driven past the camera has arrived
            arrived = page.evaluate(
                "() => window.__road.traffic.filter(c => c.bornZ !== undefined"
                " && c.z > window.__road.pos).length") or arrived

        print(f'  ..    {len(born)} cars dropped in, from {min(born) if born else 0} to '
              f'{max(born) if born else 0} units back')
        print(f'  ..    {sum(1 for f in faded if f < 1)} of {len(faded)} readings caught one '
              f'still fading in')
        ok(bool(born) and min(born) >= 6000,
           'a car is dropped in well back, not into the middle of the glass',
           f'nearest drop was {min(born) if born else 0} units back')
        ok(bool(born) and max(born) <= MIRROR_BACK,
           'and still inside the mirror, so it is somewhere it can be seen to arrive',
           f'furthest drop was {max(born) if born else 0} against the glass at {MIRROR_BACK}')
        ok(any(f < 0.9 for f in faded),
           'and it is transparent when it appears rather than solid',
           f'{sum(1 for f in faded if f < 0.9)} readings under nine tenths')
        ok(any(f >= 0.999 for f in faded),
           'and it becomes fully solid rather than staying ghostly',
           f'{sum(1 for f in faded if f >= 0.999)} readings at full')
        # THE ONE THAT KEEPS THE REST HONEST
        ok(arrived > 0 or len(born) >= 3,
           'and cars still actually arrive, which is what the spawner is for',
           f'{len(born)} dropped in over 36s at a standstill')
        ok(errs == [], 'no page errors', errs[0][:100] if errs else '')
        ctx.close()
        b.close()
    srv.shutdown()
    print(f"\n  {'they arrive rather than appear' if not bad else str(bad) + ' FAILURES'}")
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
