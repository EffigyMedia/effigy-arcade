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
from harness import launch_chromium, console_utf8, boot, until, garage_screen
from playwright.sync_api import sync_playwright

console_utf8()
handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
srv = socketserver.TCPServer(('127.0.0.1', 0), handler)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = f'http://127.0.0.1:{PORT}'

NAMES = {'t': 'traffic', 'k': 'police', 'b': 'a roadblock',
         'c': 'a checkpoint board', 'w': 'a bridge tower', 'g': 'a rival',
         'r': 'a repair crate', 'f': 'the finish line'}


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
        boot(page, f'{BASE}/games/sw/interstate.html')
        try:
            until(page, '() => navigator.serviceWorker && navigator.serviceWorker.controller', timeout=5000)
            page.wait_for_timeout(1200)
        except Exception:
            pass
        page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
        page.click('[data-act="play"]')
        page.wait_for_timeout(400)
        # the drive's settings are on the SETTINGS screen (RLG-071)
        garage_screen(page, 'settings')
        page.click('[data-act="chase"]')        # roadblocks and police need pursuit on
        garage_screen(page, 'main')
        page.wait_for_timeout(200)
        page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
        page.click('[data-act="drive"]')
        page.wait_for_timeout(1500)
        page.evaluate("() => window.__road.watchDraw(true)")

        # EVERY KIND HAS TO EXIST BEFORE IT CAN BE MISSED. Heat brings the roadblocks and
        # the police, and driving brings the traffic.
        #
        # THE BOARD AND THE CRATE ARE PARKED BEHIND, and that is not a shortcut. A
        # checkpoint stands two miles out and this drive covers a little under that, so the
        # windscreen was handed a board the car never reached and the glass was marked
        # "missing" for a board that was still up the road - measured 2026-09-15, and the
        # engine hands the glass a parked board at 4,000 and at 20,000 behind perfectly
        # well. A crate has the same problem with the same cause: it depends on one
        # happening to fall behind the car while the sweep is watching, which is why this
        # check reported the crate missing on some runs and not others.
        front, glass = set(), set()
        for i in range(150):
            page.evaluate("""() => { const R = window.__road;
                R.setSpd(0.55 * R.MAX_SPD); R.heat(4);
                if(!R.roadblocks().length) R.forceRoadblock();
                if(R.gantries() === 0) R.parkGantry(20000);
                if(!R.cratesLeft()) R.parkCrate(-20000);
                /* and a cruiser BEHIND, for the same reason: at four stars the road puts
                   police on you, but whether one is behind the camera in the frame this
                   sweep happens to read is chance - measured, one run in several had the
                   glass handed no police at all while the windscreen had them */
                const pz = R.startLine().pos + R.PLAYER_Z;
                if(!R.cops().some(k => k.z < pz - 6000)) R.commitCop('player', -20000); }""")
            page.wait_for_timeout(200)
            vk = page.evaluate("() => window.__road.viewKinds()")
            front |= set(vk['front'])
            glass |= set(vk['glass'])

        # ---- AND THE FINISH LINE, WHICH NEEDS A RACE (RLG-133) -------------------
        # `parkFinish` puts the run into race mode and drops the line behind the car, for
        # the same reason the board is parked: driving to one measures the spawner.
        fin = page.evaluate("""() => { const R = window.__road;
            const st = R.parkFinish(20000); R.setSpd(0.55 * R.MAX_SPD); return st; }""")
        for _ in range(8):
            page.wait_for_timeout(200)
            vk = page.evaluate("() => window.__road.viewKinds()")
            front |= set(vk['front'])
            glass |= set(vk['glass'])
        print(f"  ..    the finish line was parked {fin['back']} units back (mode {fin['wasMode']}"
              f" -> {fin['mode']})")

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
