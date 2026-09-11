#!/usr/bin/env python3
"""ROADBLOCK TEST - the police build a wall, and it always has a way through.

    .venv/Scripts/python tools/roadblock-test.py

A roadblock is panels tiled across the road with one deliberate opening, and a cruiser
parked well clear of it. The opening is the whole design: it is a wall you have to thread
rather than a wall you have to survive, which is the same promise `keepLaneOpen` makes
about traffic and this is its equivalent for something the police built.

IT HAD NO CHECK, AND COULD NOT HAVE HAD ONE. Nothing exposed the roadblock array, so the
police audit of 2026-09-07 could only infer that one existed from a boolean about the road
immediately ahead. A stage of the pursuit nobody can count is a stage nobody can test.

WHAT IT ASSERTS:

  * one goes up when the conditions are met
  * it really does span the road - a "roadblock" of two panels is a chicane
  * the opening is wide enough for the car to fit through, MEASURED FROM THE PANELS
    rather than read from the field that claims where the gap is
  * and it goes up ahead of you, not on top of you

THE THIRD IS THE ONE THAT MATTERS. `gapX` says where the opening was meant to be; the
panels say where it actually is. A tiling bug that closed the gap would leave `gapX`
perfectly correct and make the game unplayable, and reading `gapX` would never see it.
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

PLAYER_W = 0.265        # the car's own width, from road.js


def main():
    bad = 0

    def ok(cond, label, detail=''):
        nonlocal bad
        if not cond:
            bad += 1
        print(f'  {"ok  " if cond else "FAIL"}  {label}' + (f'   {detail}' if detail else ''))

    print('roadblock-test  .  a wall with a way through it')
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
        page.wait_for_timeout(400)
        page.click('[data-act="chase"]')
        page.wait_for_timeout(200)
        page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
        page.click('[data-act="drive"]')
        page.wait_for_timeout(1500)

        # ---- ONE GOES UP ON ITS OWN, GIVEN THE CONDITIONS --------------------
        # Heat two and a straight stretch. It is held there because driving earns more
        # heat and this is measuring what a given level puts up, not how heat is earned.
        page.evaluate("() => window.__road.heat(3)")
        organic = 0
        for _ in range(150):
            page.evaluate('() => { const R = window.__road;'
                          ' R.setSpd(0.55 * R.MAX_SPD); R.heat(3); }')
            page.wait_for_timeout(200)
            organic = max(organic, len(page.evaluate("() => window.__road.roadblocks()")))
            if organic:
                break
        ok(organic > 0, 'a roadblock goes up on its own at heat 3',
           f'{organic} on the road' if organic else 'none in 30s of driving')

        # ---- AND WHAT IT IS MADE OF ------------------------------------------
        # Forced through the REAL spawner, so what is measured is the wall the game
        # builds rather than one the harness assembled to its own taste.
        page.evaluate("() => window.__road.forceRoadblock()")
        rows = page.evaluate("() => window.__road.roadblocks()")
        ok(bool(rows), 'and one can be put up on demand', f'{len(rows)} on the road')
        if rows:
            r = max(rows, key=lambda x: x['dz'])
            print(f"  ..    {r['panels']} panels, {r['cops']} cruiser, opening {r['gap']} wide,"
                  f" {r['dz']} units ahead")
            ok(r['panels'] >= 4, 'it spans the road rather than being a chicane',
               f"{r['panels']} panels")
            ok(r['cops'] >= 1, 'and there is a cruiser parked at it', f"{r['cops']}")
            # THE ASSERTION THIS FILE IS FOR. Measured off the panels, not off `gapX`:
            # a tiling bug that closed the opening would leave `gapX` perfectly correct.
            ok(r['gap'] > PLAYER_W, 'the opening is wider than the car',
               f"{r['gap']} against the car's {PLAYER_W}")
            ok(r['dz'] > 8000, 'and it goes up well ahead of you, not on top of you',
               f"{r['dz']} units ahead")
        else:
            for label in ('it spans the road rather than being a chicane',
                          'and there is a cruiser parked at it',
                          'the opening is wider than the car',
                          'and it goes up well ahead of you, not on top of you'):
                ok(False, label, 'no roadblock to measure')
        ok(errs == [], 'no page errors', errs[0][:100] if errs else '')
        ctx.close()
        b.close()
    srv.shutdown()
    print(f"\n  {'there is always a way through' if not bad else str(bad) + ' FAILURES'}")
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
