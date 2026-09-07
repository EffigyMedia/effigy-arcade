#!/usr/bin/env python3
"""PATROL TEST - police drive as traffic, and only engage when you earn it.

    .venv/Scripts/python tools/patrol-test.py

Owner, 2026-09-07: "We should put police into the traffic as standard vehicles. They just
don't engage you if hot pursuit has turned off. If hot pursuit is turned on then these
random police in the traffic will engage you if you pass them going beyond the speed limit."

A PATROL IS TRAFFIC UNTIL IT IS NOT. While it patrols it is an ordinary car in the traffic
array with a Civilian at the wheel and its bar dark. When it engages it is moved into the
cops array, where every piece of pursuit behaviour already lives.

THE THREE CASES, AND THE FIRST TWO ARE THE ONES THAT CATCH A LAZY IMPLEMENTATION:

  pursuit OFF, passed at speed    -> it must NOT engage
  pursuit ON,  passed UNDER the limit -> it must NOT engage
  pursuit ON,  passed OVER the limit  -> it MUST engage

An implementation that engages on proximity, or on any pass, or that ignores the switch,
passes the third and fails one of the first two. A file that only tested the third would go
green on all of them.

AND IT MUST NOT POLICE ITSELF. A speed trap pulls over any traffic car above the limit and a
cruiser retargets onto the nearest thing that is moving; a patrol car is exempt from both, or
the force spends the run arresting itself.
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


def boot(b, pursuit):
    """A fresh road, with HOT PURSUIT on or off, stopped and ready."""
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
    if pursuit:
        page.click('[data-act="chase"]')     # the switch, through the real menu
        page.wait_for_timeout(200)
    page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
    page.click('[data-act="drive"]')
    page.wait_for_timeout(1500)
    return ctx, page, errs


def drive_past(page, frac, dz=2000, ticks=90):
    """Put a patrol ahead, hold `frac` of top speed, and go by it.

    SAMPLED THROUGHOUT, not read at the end. A cruiser that engages and is then left
    behind is culled 34,000 units back, so a reading taken after the drive can report
    nothing chasing on a run where a chase certainly started. What matters is whether one
    began, and the moment it began is the only place to see it.
    """
    page.evaluate("() => { window.__road.traffic.length = 0; }")
    page.evaluate('(d) => window.__road.placePatrol(d)', dz)
    before = page.evaluate("() => window.__road.patrols()")['woken']
    chasing, passed = 0, 0
    for _ in range(ticks):
        page.evaluate('(f) => window.__road.setSpd(f * window.__road.MAX_SPD)', frac)
        page.wait_for_timeout(100)
        st = page.evaluate("() => window.__road.patrols()")
        chasing = max(chasing, st['chasing'])
        # a patrol still in the traffic array but BEHIND the player has been gone by
        passed = max(passed, sum(1 for c in st['cars'] if c['z'] < -200))
    st = page.evaluate("() => window.__road.patrols()")
    st['engaged'] = st['woken'] - before
    st['limit'] = page.evaluate("() => window.__road.speedLimit()")
    st['chasing'] = chasing
    # engaging IS passing: the car leaves the traffic array at the moment it happens
    st['passed'] = passed + st['engaged']
    return st


def main():
    bad = 0

    def ok(cond, label, detail=''):
        nonlocal bad
        if not cond:
            bad += 1
        print(f'  {"ok  " if cond else "FAIL"}  {label}' + (f'   {detail}' if detail else ''))

    print('patrol-test  .  traffic until you give it a reason')
    with sync_playwright() as p:
        b = launch_chromium(p, headless=True,
                            args=['--mute-audio', '--autoplay-policy=no-user-gesture-required'])

        # ---- IT IS ON THE ROAD AT ALL -------------------------------------------
        ctx, page, errs = boot(b, pursuit=True)
        # THE SPEED IS HELD, and that is not a detail. `setSpd` once lets the car coast to
        # a stop, and a stopped player generates no waves - the first version of this check
        # reported no patrols at all on an engine that was spawning them perfectly well.
        # UNDER THE LIMIT on purpose too, so nothing engages and gets taken out of traffic
        # while this is counting what is IN traffic.
        # SIGHTINGS OVER THE WHOLE DRIVE, not the count at one moment. A patrol is a
        # small share of the traffic and only one is usually on the road at a time, so
        # "how many right now" is a coin toss and asserting on it is asserting on the road.
        seen, met, minds = 0, 0, set()
        for _ in range(180):
            page.evaluate('() => window.__road.setSpd(0.30 * window.__road.MAX_SPD)')
            page.wait_for_timeout(250)
            st = page.evaluate("() => window.__road.patrols()")
            n = st['patrolling']
            seen = max(seen, n)
            met += n
            # GATHERED AS WE GO. Reading the drivers at the END asks about whatever
            # happens to be on the road in that one frame, and usually that is nothing -
            # the check reported "none on the road to read" and passed, which is a check
            # that proves nothing while looking like it proved something.
            for c in st['cars']:
                minds.add(c['mind'])
        ok(met > 0, 'a patrol car turns up in ordinary traffic',
           f'{met} sightings over 45s, at most {seen} on the road at once')

        # ---- AND IT DRIVES LIKE TRAFFIC, NOT LIKE A CHASE ------------------------
        print(f'  ..    drivers seen at the wheel of one: {sorted(minds)}')
        ok(bool(minds) and minds == {0},
           'and a Civilian is driving it, so it cruises at the limit',
           f'minds seen {sorted(minds)}, where Civilian is 0'
           if minds else 'no patrol was ever read, so this proved nothing')
        ctx.close()

        # ---- PURSUIT OFF: PASSING IT AT SPEED MUST DO NOTHING --------------------
        # THE CASE THAT CATCHES A LAZY IMPLEMENTATION. Everything else about a patrol
        # works identically with the switch off, so an engagement that forgets to ask
        # is invisible until you play with pursuit off and get chased anyway.
        ctx, page, errs2 = boot(b, pursuit=False)
        off = drive_past(page, 0.75)
        print(f"  ..    pursuit OFF, went by at 0.75 of top speed (limit {off['limit']})")
        ok(off['engaged'] == 0, 'with HOT PURSUIT off, blasting past a patrol does nothing',
           f"{off['engaged']} engaged, {off['chasing']} chasing")
        ctx.close()

        # ---- PURSUIT ON, UNDER THE LIMIT: STILL NOTHING --------------------------
        ctx, page, errs3 = boot(b, pursuit=True)
        # 0.38 AND NOT 0.30, AND THE DIFFERENCE IS THE WHOLE CHECK. A patrol cruises at
        # 0.34, so a player doing 0.30 never catches it and never passes it - the check
        # went green because nothing happened rather than because the limit was respected,
        # and it stayed green with the speed test taken out. 0.38 is under the 0.40 limit
        # and over the patrol's own pace, so the pass really happens and is really legal.
        legal = drive_past(page, 0.38)
        print(f"  ..    pursuit ON, went by at 0.38 of top speed, under the {legal['limit']} limit")
        ok(legal['passed'] > 0, 'the legal run actually GOT past the patrol',
           f"{legal['passed']} of the patrols placed were passed")
        ok(legal['engaged'] == 0, 'and going past one legally does nothing either',
           f"{legal['engaged']} engaged")

        # ---- PURSUIT ON, OVER THE LIMIT: IT ENGAGES ------------------------------
        fast = drive_past(page, 0.75)
        print(f"  ..    pursuit ON, went by at 0.75 of top speed")
        ok(fast['engaged'] > 0, 'but speeding past one starts a pursuit',
           f"{fast['engaged']} engaged, {fast['chasing']} now chasing")
        ok(fast['chasing'] > 0, 'and it is chasing you rather than merely gone',
           f"{fast['chasing']} cruisers on the road")

        errs = errs + errs2 + errs3 + page.evaluate("() => []")
        ok(errs == [], 'no page errors', errs[0][:100] if errs else '')
        ctx.close()
        b.close()
    srv.shutdown()
    print(f"\n  {'a patrol is traffic until you earn it' if not bad else str(bad) + ' FAILURES'}")
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
