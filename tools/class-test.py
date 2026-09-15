"""THE EVENTS ARE FOR THE CARS BUILT TO ENTER THEM - RLG-115.

    .venv/Scripts/python tools/class-test.py

Owner, 2026-08-31: "if you have a production or utility vehicle selected, the only mode
available is test drive." Owner, 2026-09-05, on the three questions that blocked it: the
race modes GREY OUT WITH THE REASON GIVEN rather than disappearing; production and utility
vehicles are NOT OFFERED AT ALL in Motorsport; and a save is never allowed to hold a car
and a mode that disagree.

WHAT THIS ASKS, AND WHY IT ASKS IT THAT WAY.

The rule is not "the game refuses to start a race in a van" - RLG-115 names that as the
WRONG build. It is "the menu does not offer what the car cannot do". So every check here
reads the GARAGE, not the start of a run: what the MODE control says, whether it is
disabled, and what the note under it reads.

AND IT DRIVES THE REAL CONTROLS. A harness that called `raceLegal()` and agreed with it
would prove only that the function agrees with itself. This clicks the arrows the thumb
clicks until it reaches a production car, then reads what the player would see.

THE THREE THINGS THAT WOULD MAKE THIS VACUOUS, each guarded:

  1. Reaching no production car at all. If the arrows never land on one - because the
     class is locked on a fresh save - every "the modes are shut" check would pass by
     never being tested. So the debug switch that opens the traffic classes is turned on
     first, and the walk ASSERTS it found one.

  2. Motorsport's list being empty for the wrong reason. "No production car found" is the
     PASS condition there and the FAIL condition in Interstate, so the same silence means
     opposite things in the two games. Both are asserted, and Interstate's is what stops a
     broken walk from reading as a green circuit.

  3. The mode never having been a race in the first place. A control that says TEST DRIVE
     because nothing ever set it otherwise proves nothing. So the walk sets a TOURNAMENT
     on a race-legal car FIRST, confirms it took, and only then goes looking for the van.

RLG-249 CHANGED WHAT THIS CAN FIND. The owner removed the work vehicles from the garage on
2026-09-14, and they were the only garage cars with no event to enter. Guards 1 and 2 above
describe the file before that. Now both games assert that the garage lists NO car that cannot
race, and that the walk saw at least three cars, so an empty walk still fails.

Exit code 0 if every check passed, 1 otherwise.
"""
import sys, threading, http.server, socketserver, functools

# it finds its own root (RLG-039) - step.py runs a command from the environment's root
from pathlib import Path as _P
ROOT = _P(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from harness import launch_chromium, console_utf8, boot, until
from playwright.sync_api import sync_playwright
console_utf8()

h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
srv = socketserver.TCPServer(('127.0.0.1', 0), h)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()

bad = [0]


def check(ok, label, detail):
    print(f'  {"ok  " if ok else "FAIL"}  {label:<44} {detail}')
    if not ok:
        bad[0] += 1


def open_garage(pg, path):
    boot(pg, f'http://127.0.0.1:{PORT}/{path}')
    try:
        until(pg, '() => navigator.serviceWorker && navigator.serviceWorker.controller', timeout=5000)
        pg.wait_for_timeout(1000)
    except Exception:
        pass
    pg.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
    pg.click('[data-act="play"]')
    pg.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)


def mode_state(pg):
    """What the player can see about the MODE control, read off the DOM."""
    return pg.evaluate("""() => {
      const b = document.querySelector('[data-act="mode"]');
      const notes = [...document.querySelectorAll('.gnote')].map(n => n.textContent.trim());
      return b ? { label: b.textContent.trim(),
                   shut: b.disabled === true || b.classList.contains('shut'),
                   notes } : null;
    }""")


def car(pg):
    return pg.evaluate("() => window.__road && window.__road.body ? window.__road.body() : null")


with sync_playwright() as p:
    b = launch_chromium(p, headless=True,
                        args=['--mute-audio', '--autoplay-policy=no-user-gesture-required'])

    for gid, path in [('interstate', 'games/sw/interstate.html'),
                      ('motorsport', 'games/sw/motorsport.html')]:
        print(f'\n  {gid.upper()}')
        pg = b.new_context(viewport={'width': 480, 'height': 900}).new_page()
        errs = []
        pg.on('pageerror', lambda e: errs.append(str(e)))
        open_garage(pg, path)

        # ---- guard 3: put a real race mode on a race-legal car first --------------
        start_car = car(pg)
        pg.click('[data-act="mode"]')          # TEST DRIVE -> SINGLE RACE
        pg.wait_for_timeout(120)
        pg.click('[data-act="mode"]')          # SINGLE RACE -> TOURNAMENT
        pg.wait_for_timeout(120)
        armed = mode_state(pg)
        check(armed and armed['label'].endswith('TOURNAMENT'),
              'a race mode can be set at all',
              f"{start_car} reads '{armed['label'] if armed else 'no control'}'")

        # ---- walk the arrows until a car that cannot race turns up ----------------
        # AND A POLICE CAR IS NOT THE CAR THIS FILE IS ABOUT (RLG-203). `raceLegal`
        # is false for a van and false for a patrol car, and the two are opposite
        # shapes: a van's MODE control is SHUT with the reason given, a patrol
        # car's is open and offers INTERCEPT instead. When the police cars joined
        # RACE_BANNED this walk landed on a SUPERCRUISER and asserted a van's rule
        # against it - three failures, all of them this harness being out of date
        # rather than the rule being broken. RLG-115 is about the cars that have
        # NO event to enter, so the walk asks for exactly those.
        found, seen, shut_at = None, [], None
        for _ in range(40):
            pg.click('[data-act="next"]')
            pg.wait_for_timeout(90)
            k = car(pg)
            if k in seen:
                break
            seen.append(k)
            st = pg.evaluate("""() => ({
                race: window.__road.raceLegal ? window.__road.raceLegal() : true,
                duty: window.__road.dutyLegal ? window.__road.dutyLegal() : false })""")
            if not st['race'] and not st['duty']:
                found, shut_at = k, mode_state(pg)
                break

        # RLG-249: the work vehicles were the only garage cars with no event to enter, and
        # they left the garage. So BOTH games now list no such car. The shut MODE control is
        # still in `road.js` for a car that cannot race; it has no car in the garage to show on.
        check(found is None,
              'the garage lists NO car that cannot race',
              f'{len(seen)} cars walked, none banned' if found is None
              else f'{found} was offered and should not have been')
        check(len(seen) >= 3,
              'and the walk actually walked',
              f'{len(seen)} distinct cars seen')
        check(not errs, 'no page errors', errs[0] if errs else 'clean')
        pg.close()
    b.close()

srv.shutdown()
print()
print('  ' + ('the classes decide what a car is for'
              if not bad[0] else f'{bad[0]} FAILURES'))
sys.exit(1 if bad[0] else 0)
