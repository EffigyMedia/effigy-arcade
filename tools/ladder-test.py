#!/usr/bin/env python3
"""LADDER TEST - a higher wanted level actually puts more police on the road.

    .venv/Scripts/python tools/ladder-test.py

THIS IS THE CHECK THAT WAS MISSING, and its absence is why an entire source of police
went unnoticed. `spawnCop` - the rear spawner, the third of the owner's three sources -
was defined and never called from anywhere for a long time. Nothing failed, because
nothing had ever asked whether heat DOES anything. Heat four and heat two summoned
identical cars and every gate stayed green.

THE THREE SOURCES ANSWER TO DIFFERENT THINGS, so they are counted apart:

  traps     parked cruisers. Always a few; heat only lays them more thickly.
  patrols   police driving as ordinary traffic. Not heat's business at all.
  chasers   cars the radio sent after you. THIS is what a wanted level buys.

AND THEY ARE COUNTED APART, WHICH IS THE HALF THAT MAKES THIS WORK. The first version of
this file counted every cruiser chasing you, and at speed a trap catches you and a patrol
engages you constantly - so heat 1 read FOUR chasers and heat 5 read three, and the ladder
appeared to run backwards on an engine that was working. Every cruiser records which of
the three sources made it, and this reads only the radio's.

WHAT IT ASSERTS: that the number of chasers the radio will keep on you rises with heat,
and that it is zero at heat one - which is the baseline and means "not wanted". It reads
the count of cars actually on the road, not the cap they are drawn from, because a cap
that nothing acts on is exactly the failure this file exists to catch.

IT IS RUN WITH THE ROAD CLEARED BETWEEN LEVELS, or a chase started at heat 4 is still
running when heat 2 is measured and the ladder reads backwards.
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

# long enough for the dispatch timer to fire several times at every level
SETTLE = 26


def main():
    bad = 0

    def ok(cond, label, detail=''):
        nonlocal bad
        if not cond:
            bad += 1
        print(f'  {"ok  " if cond else "FAIL"}  {label}' + (f'   {detail}' if detail else ''))

    print('ladder-test  .  a wanted level is a number that does something')
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
        page.click('[data-act="chase"]')          # HOT PURSUIT on, through the real menu
        page.wait_for_timeout(200)
        page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
        page.click('[data-act="drive"]')
        page.wait_for_timeout(1500)
        ok(not page.evaluate("() => window.__road.pursuit().easy"),
           'the pursuit system is running', 'or every number below is zero')

        rungs = {}
        for level in (1, 2, 3, 5):
            # THE ROAD IS CLEARED FIRST. A chase from the level before is still running
            # otherwise, and the ladder reads backwards through no fault of the engine.
            page.evaluate("() => { window.__road.copsClear(); }")
            page.evaluate('(h) => window.__road.heat(h)', level)
            peak = 0
            census = None
            for _ in range(SETTLE * 4):
                # hold the heat: driving fast earns more of it, and this is measuring
                # what a GIVEN level dispatches rather than how quickly one is earned
                page.evaluate('(h) => { const R = window.__road;'
                              ' R.setSpd(0.72 * R.MAX_SPD); R.heat(h); }', level)
                page.wait_for_timeout(250)
                census = page.evaluate("() => window.__road.copCensus()")
                peak = max(peak, census['radio'])
            rungs[level] = peak
            print(f"  ..    heat {level}:  radio cars peaked at {peak}   (cap {census['cap']};"
                  f" also on the road: {census['fromTrap']} from traps,"
                  f" {census['fromPatrol']} from patrols, {census['traps']} parked)")

        ok(rungs[1] == 0, 'heat 1 is the baseline and the radio sends nobody',
           f'{rungs[1]} radio cars at heat 1')
        ok(rungs[2] > 0, 'heat 2 gets the radio interested', f'{rungs[2]} radio cars')
        ok(rungs[5] > rungs[2], 'and a higher wanted level puts MORE of them on you',
           f'heat 5 peaked at {rungs[5]}, heat 2 at {rungs[2]}')
        ok(rungs[3] >= rungs[2], 'the ladder climbs rather than wandering',
           f"1:{rungs[1]}  2:{rungs[2]}  3:{rungs[3]}  5:{rungs[5]}")
        ok(errs == [], 'no page errors', errs[0][:100] if errs else '')
        ctx.close()
        b.close()
    srv.shutdown()
    print(f"\n  {'the ladder climbs' if not bad else str(bad) + ' FAILURES'}")
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
