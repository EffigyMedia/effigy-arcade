#!/usr/bin/env python3
"""BUST TEST - stopping with the law alongside ends the run, and nothing else does.

    .venv/Scripts/python tools/bust-test.py

A cruiser that gets level with a stationary car boxes it in, and three seconds later the
run is over. The light bar is the only warning, and the only way out is to move.

IT HAD NO CHECK AT ALL until the police audit of 2026-09-07, and writing one caught the
auditor out first: the bust LOOKED broken - six seconds stopped with a cruiser alongside
and the game state never changed - because a wreck with time left on the clock is a
two-second penalty and not a state change, by the owner's own ruling that the world must
not freeze. The bust had been firing the whole time. Read `wreckWait`, not `state`.

THE THREE CASES, and the last two are the ones that catch a bust that fires on anything:

  stopped, cruiser alongside, pursuit ON   -> BUSTED
  stopped, road clear                      -> nothing
  stopped, cruiser alongside, pursuit OFF  -> nothing

`lastWreck` is what makes the first assertable. During a run the flash says WRECKED
whatever caused it, so from the outside a bust and a head-on collision look identical.
"""
import sys, threading, http.server, socketserver, functools
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from harness import launch_chromium, console_utf8, boot as engine_boot, until
from playwright.sync_api import sync_playwright

console_utf8()
handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
srv = socketserver.TCPServer(('127.0.0.1', 0), handler)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = f'http://127.0.0.1:{PORT}'

# ---- A BUST IS THE END OF A PURSUIT, SO THE SCENE NEEDS ONE (owner, 2026-09-08) ----
# This staged a cruiser beside a driver with NO HEAT and expected an arrest. That case
# used to fire because every cruiser adopted the player as its default target whatever
# they had done - which is the owner's own report: "an overwhelming amount of cops just
# coming back at me one after the other engaged to me". A clean, stopped driver being
# boxed in and arrested is that fault, not a feature, so the check would have held the
# defect in place.
#
# THE SCENE NOW CARRIES WHAT A BUST NEEDS: heat on the car and a cruiser that is on it.
# `onPlayer` is set because a real dispatched cruiser has it set by the target search,
# and a staged one that omits it is not a cruiser in pursuit - it is a parked car.
PLACE_COP = """() => { const R = window.__road;
    R.copsClear();
    R.heat(2);
    R.cops().push({ z: R.pos + R.PLAYER_Z + 200, x: 0.30, spd: 0,
                    wreck:0, ang:0, grace:0, cool:0, side:1, onPlayer:true,
                    w:0.27, len:400, phase:0, dmg:0, from:'test' }); }"""

# and the same scene with nothing on the car, which is the owner's complaint as a check
PLACE_COP_CLEAN = """() => { const R = window.__road;
    R.copsClear();
    R.heatSet(0);
    R.cops().push({ z: R.pos + R.PLAYER_Z + 200, x: 0.30, spd: 0,
                    wreck:0, ang:0, grace:0, cool:0, side:1,
                    w:0.27, len:400, phase:0, dmg:0, from:'test' }); }"""


def boot(b, pursuit):
    ctx = b.new_context(viewport={'width': 480, 'height': 900})
    page = ctx.new_page()
    errs = []
    page.on('pageerror', lambda e: errs.append(str(e)))
    engine_boot(page, f'{BASE}/games/sw/interstate.html')
    try:
        until(page, '() => navigator.serviceWorker && navigator.serviceWorker.controller', timeout=5000)
        page.wait_for_timeout(1200)
    except Exception:
        pass
    page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
    page.click('[data-act="play"]')
    page.wait_for_timeout(400)
    if pursuit:
        page.click('[data-act="chase"]')
        page.wait_for_timeout(200)
    page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
    page.click('[data-act="drive"]')
    page.wait_for_timeout(1500)
    page.evaluate("() => { window.__road.traffic.length = 0; }")
    return ctx, page, errs


def stop_and_wait(page, seconds=7):
    """Hold the car at a standstill and report the first thing that wrecks it."""
    page.evaluate("() => window.__road.clearWreck()")
    for _ in range(int(seconds * 5)):
        page.evaluate("() => window.__road.setSpd(0)")
        page.wait_for_timeout(200)
        why = page.evaluate("() => window.__road.lastWreck()")
        if why:
            return why
    return ''


def main():
    bad = 0

    def ok(cond, label, detail=''):
        nonlocal bad
        if not cond:
            bad += 1
        print(f'  {"ok  " if cond else "FAIL"}  {label}' + (f'   {detail}' if detail else ''))

    print('bust-test  .  stopping with the law alongside ends the run')
    with sync_playwright() as p:
        b = launch_chromium(p, headless=True,
                            args=['--mute-audio', '--autoplay-policy=no-user-gesture-required'])

        # ---- STOPPED, CRUISER ALONGSIDE, PURSUIT ON --------------------------
        ctx, page, errs = boot(b, pursuit=True)
        page.evaluate(PLACE_COP)
        why = stop_and_wait(page)
        print(f'  ..    stopped beside a cruiser with pursuit ON  -> {why or "nothing"}')
        ok(why == 'BUSTED', 'stopping beside a cruiser gets you busted',
           f'ended by {why!r}' if why else 'nothing happened in seven seconds')
        ctx.close()

        # ---- STOPPED ON A CLEAR ROAD -----------------------------------------
        # THE CHECK THAT KEEPS THE FIRST HONEST. A bust that fires on stopping alone
        # would pass the case above and ruin the game, and nothing else here would see it.
        ctx, page, errs2 = boot(b, pursuit=True)
        page.evaluate("() => window.__road.copsClear()")
        why = stop_and_wait(page)
        print(f'  ..    stopped on an empty road            -> {why or "nothing"}')
        ok(why == '', 'but stopping on an empty road is free',
           f'ended by {why!r}' if why else '')
        ctx.close()

        # ---- STOPPED BESIDE A CRUISER, BUT WANTED FOR NOTHING ----------------
        # The owner's report as an assertion: a driver who has done nothing is not
        # chased, and cannot be arrested for stopping near a police car.
        ctx, page, errs4 = boot(b, pursuit=True)
        page.evaluate(PLACE_COP_CLEAN)
        why = stop_and_wait(page)
        print(f'  ..    stopped beside a cruiser, no heat   -> {why or "nothing"}')
        ok(why == '', 'and a driver wanted for nothing cannot be busted',
           f'ended by {why!r}' if why else '')
        ctx.close()

        # ---- STOPPED, CRUISER ALONGSIDE, PURSUIT OFF -------------------------
        ctx, page, errs3 = boot(b, pursuit=False)
        page.evaluate(PLACE_COP)
        why = stop_and_wait(page)
        print(f'  ..    stopped beside a cruiser, pursuit OFF -> {why or "nothing"}')
        ok(why == '', 'and with HOT PURSUIT off nobody can box you in',
           f'ended by {why!r}' if why else '')

        errs = errs + errs2 + errs3 + errs4
        ok(errs == [], 'no page errors', errs[0][:100] if errs else '')
        ctx.close()
        b.close()
    srv.shutdown()
    print(f"\n  {'the bust fires, and only when it should' if not bad else str(bad) + ' FAILURES'}")
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
