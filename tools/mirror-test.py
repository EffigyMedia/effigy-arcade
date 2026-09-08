#!/usr/bin/env python3
"""MIRROR TEST - everything on the road behind you is in the glass.

    .venv/Scripts/python tools/mirror-test.py

Owner, 2026-09-07: "a police roadblock is invisible in the mirror", and then "do a sweep of
all things that should be in the mirror and make sure they are visible in it."

THE SWEEP FOUND THREE, NOT ONE. The forward pass hands its painter eight kinds of thing and
the mirror's list carried five: a ROADBLOCK you had just threaded, a SIGN you had just
passed and a repair CRATE you had just missed all vanished the instant they were behind
you. The crate is the one that costs you something - it is a thing you might want to know
you have gone by.

IT COMPARES THE TWO LISTS RATHER THAN NAMING WHAT SHOULD BE IN THEM. A check that held its
own list of kinds would be a second place to update, and would go on passing on the day a
ninth thing is added to the road and forgotten in the glass - which is precisely the fault
being fixed. The engine records what each view was OFFERED, and this asserts the glass is
offered everything the windscreen is.

OFFERED, NOT PAINTED, and that is deliberate. The fault was never in the painting: a
roadblock was never put in the mirror's list at all, and every line after that point worked
correctly. A check on pixels would also have to contend with a mirror 44 pixels tall in
which a distant sign is a smudge.
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

NAMES = {'t': 'traffic', 'k': 'police', 'b': 'a roadblock', 's': 'a sign',
         'c': 'a checkpoint board', 'w': 'a bridge tower', 'g': 'a rival',
         'r': 'a repair crate'}


def main():
    bad = 0

    def ok(cond, label, detail=''):
        nonlocal bad
        if not cond:
            bad += 1
        print(f'  {"ok  " if cond else "FAIL"}  {label}' + (f'   {detail}' if detail else ''))

    print('mirror-test  .  everything behind you is in the glass')
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
        page.wait_for_timeout(400)
        page.click('[data-act="chase"]')        # roadblocks and police need pursuit on
        page.wait_for_timeout(200)
        page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
        page.click('[data-act="drive"]')
        page.wait_for_timeout(1500)
        page.evaluate("() => window.__road.watchDraw(true)")

        # EVERY KIND HAS TO EXIST BEFORE IT CAN BE MISSED. Heat brings the roadblocks and
        # the police; driving brings the traffic, the signs and the crates; and one of
        # each is forced onto the road behind the car so nothing waits on the spawner.
        front, glass = set(), set()
        for i in range(150):
            page.evaluate("""() => { const R = window.__road;
                R.setSpd(0.55 * R.MAX_SPD); R.heat(4);
                if(!R.roadblocks().length) R.forceRoadblock(); }""")
            page.wait_for_timeout(200)
            vk = page.evaluate("() => window.__road.viewKinds()")
            front |= set(vk['front'])
            glass |= set(vk['glass'])

        print(f"  ..    the windscreen was handed: {sorted(NAMES.get(k, k) for k in front)}")
        print(f"  ..    the glass was handed:      {sorted(NAMES.get(k, k) for k in glass)}")
        missing = sorted(front - glass)
        ok(len(front) >= 5, 'enough kinds appeared on the road to say anything',
           f'{len(front)} kinds seen ahead')
        ok(not missing,
           'everything the road hands the windscreen is also handed to the mirror',
           'missing from the glass: ' + ', '.join(NAMES.get(k, k) for k in missing)
           if missing else '')
        ok(errs == [], 'no page errors', errs[0][:100] if errs else '')
        ctx.close()
        b.close()
    srv.shutdown()
    print(f"\n  {'the glass carries the road' if not bad else str(bad) + ' FAILURES'}")
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
