"""THE FIELD'S OWN LAWLESSNESS DECIDES HOW MANY POLICE ARE OUT - RLG-203.

    .venv/Scripts/python tools/lawless-test.py

Owner, 2026-09-10, on the one difference between INTERCEPT and a race with hot pursuit on:
"there's no single racer accruing heat." That left the mode without the dial that decides
how much force is on the road, and the owner chose the replacement: the field's own
lawlessness.

WHAT THIS ASKS, IN THE ORDER THE CHAIN RUNS.

  1. THE COUNT. `lawless` is the rivals still running AND still over the limit. A rival that
     has been stopped is parked on the verge and is the most law-abiding thing out there, so
     it must not count - and that is asserted rather than assumed, because a count that
     included them would keep the road busy while the player emptied it, which is the exact
     opposite of what the mode is for.

  2. THE LEVEL. It follows the count rather than jumping to it, and the same rate governs
     both directions. A level that snapped would flicker a star every time a rival braked
     for traffic, and the HUD announces every change.

  3. WHAT THE LEVEL BUYS. A wanted level that moves and buys nothing is a different failure
     from one that never moves, so the complement the shift asks for is read separately, and
     the cars actually on the road are read separately again.

THE TWO THINGS THAT WOULD MAKE THIS VACUOUS, both guarded:

  A LEVEL THAT WAS ALWAYS HIGH. The field starts at racing speed, so "the level is high"
  proves nothing on its own. The field is quietened - every rival brought under the limit -
  and the level has to COME DOWN. Rising and falling are asserted separately.

  A FLOOR MISTAKEN FOR A LADDER. Two wingmen are kept whatever the field does, so a road
  with two cruisers on it says nothing about lawlessness. What is asserted is the complement
  ABOVE the floor, and that it returns to the floor when the field goes quiet.

WHAT THIS CANNOT CHECK. Whether the road FEELS busier with a lawless field, and whether
thinning out to a duel at the end reads as relief or as the mode running out - both are the
owner's on a device. And it measures the complement the shift ASKS for; how quickly the road
actually fills is the spawner's business and is reported rather than asserted.

Exit code 0 if every check passed, 1 otherwise.
"""
import sys, threading, http.server, socketserver, functools

from pathlib import Path as _P
ROOT = _P(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from harness import launch_chromium, console_utf8, boot, until, reboot
from playwright.sync_api import sync_playwright
console_utf8()

h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
srv = socketserver.TCPServer(('127.0.0.1', 0), h)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
GAME = 'games/sw/interstate.html'

bad = [0]


def check(ok, label, detail=''):
    print(f'  {"ok  " if ok else "FAIL"}  {label:<52} {detail}')
    if not ok:
        bad[0] += 1


def note(text):
    print(f'  ..    {text}')


def wait_engine(pg, secs, cap=90):
    """Wait `secs` of the ENGINE's clock, not of the wall's.

    THIS PROJECT HAS ALREADY PAID FOR THIS ONCE. `simTime` runs at a fraction of wall
    time in this browser, so a harness that sleeps for the settling time it wants gets
    a fraction of it - and the first run of this file read one star where it expected
    five, because twenty-four seconds of waiting was about six seconds of engine. The
    level being measured is charged per engine-second, so the wait has to be too.

    `cap` is a wall-clock stop, so a frozen engine fails the check rather than hanging
    the run."""
    t0 = pg.evaluate("() => window.__road.simTime()")
    waited = 0
    while waited < cap * 1000:
        pg.wait_for_timeout(400)
        waited += 400
        if pg.evaluate("() => window.__road.simTime()") - t0 >= secs:
            return True
    return False


def control(pg, act):
    return pg.evaluate("""(act) => {
      const b = document.querySelector('[data-act="' + act + '"]');
      return b ? b.textContent.trim() : null; }""", act)


def on_shift(pg):
    boot(pg, f'http://127.0.0.1:{PORT}/{GAME}')
    try:
        until(pg, '() => navigator.serviceWorker && navigator.serviceWorker.controller',
              timeout=5000)
        pg.wait_for_timeout(1000)
    except Exception:
        pass
    pg.evaluate("""() => window.Arcade.save.merge('interstate-opts',
                     { super:true, cruiser:true, supercruiser:true })""")
    reboot(pg)
    try:
        until(pg, '() => navigator.serviceWorker && navigator.serviceWorker.controller',
              timeout=5000)
        pg.wait_for_timeout(1000)
    except Exception:
        pass
    pg.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
    pg.click('[data-act="play"]')
    pg.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
    for _ in range(40):
        if pg.evaluate("() => window.__road.body()") == 'CRUISER':
            break
        pg.click('[data-act="next"]')
        pg.wait_for_timeout(90)
    for _ in range(4):
        if (control(pg, 'mode') or '').endswith('INTERCEPT'):
            break
        pg.click('[data-act="mode"]')
        pg.wait_for_timeout(120)
    pg.click('[data-act="drive"]')
    pg.wait_for_timeout(2000)
    pg.evaluate("() => window.__road.setTimed(false)")


with sync_playwright() as p:
    b = launch_chromium(p, headless=True,
                        args=['--mute-audio', '--autoplay-policy=no-user-gesture-required'])
    pg = b.new_context(viewport={'width': 480, 'height': 900}).new_page()
    errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    on_shift(pg)

    sh = pg.evaluate("() => window.__road.shift()")
    check(sh['on'] is True, 'the run is on shift', f"duty={sh['on']}")
    swing = sh['swing']
    note(f"the level crosses its range in {swing}s; the limit is {sh['limit']} of top speed")

    # ---- 1: A FIELD AT RACING SPEED IS A LAWLESS FIELD ----------------------
    print('')
    print('  A FIELD RUNNING FLAT OUT')
    # AHEAD OF THE PLAYER AND ACROSS THE LANES, which is what a field looks
    # like. Staged behind the player in one lane they queue, lift for each other
    # and dip under the limit and back over it every few seconds - `lawless`
    # read 11, then 0, then 11, and the level never got past one star.
    pg.evaluate("""() => { const R = window.__road;
        R.stageField(R.MAX_SPD * 0.80);
        R.holdField(R.MAX_SPD * 0.80);   /* held, not nudged - see harness note */
        R.holdSpd(R.MAX_SPD * 0.50); }""")
    wait_engine(pg, swing * 1.2)
    sh = pg.evaluate("() => window.__road.shift()")
    note(f"lawless {sh['lawless']} of {sh['field']}, level {sh['pts']} pts / {sh['stars']} stars, "
         f"asking for {sh['want']} cars")
    check(sh['lawless'] > sh['field'] // 2,
          'most of the field counts as lawless', f"{sh['lawless']} of {sh['field']}")
    check(sh['stars'] > 0, 'and the wanted level has climbed', f"{sh['stars']} stars")
    check(sh['want'] > sh['wingmen'],
          'and it asks for more than the two wingmen',
          f"{sh['want']} against a floor of {sh['wingmen']}")
    hot = dict(sh)

    # ---- 2: QUIETEN THE FIELD AND IT MUST COME DOWN -------------------------
    # THE GUARD AGAINST A LEVEL THAT WAS ALWAYS HIGH. Same cars, same places,
    # under the limit instead of over it.
    print('')
    print('  THE SAME FIELD, UNDER THE LIMIT')
    pg.evaluate("""() => { const R = window.__road;
        const v = R.MAX_SPD * R.shift().limit * 0.6;
        R.stageField(v); R.holdField(v);
        R.holdSpd(R.MAX_SPD * 0.30); }""")
    wait_engine(pg, swing * 1.4)
    sh = pg.evaluate("() => window.__road.shift()")
    note(f"lawless {sh['lawless']} of {sh['field']}, level {sh['pts']} pts / {sh['stars']} stars, "
         f"asking for {sh['want']} cars")
    check(sh['lawless'] == 0, 'a field under the limit is not lawless at all',
          f"{sh['lawless']} still speeding")
    check(sh['pts'] < hot['pts'], 'and the level falls with it',
          f"{hot['pts']} -> {sh['pts']} points")
    check(sh['want'] == sh['wingmen'],
          'and the road is back to the two wingmen and no more',
          f"{sh['want']} against a floor of {sh['wingmen']}")

    # ---- 3: A STOPPED RIVAL IS NOT A LAWLESS ONE ----------------------------
    # The other way the count could be wrong, and the one that matters most: a
    # count that included stopped cars would keep the road busy while the player
    # empties it, which is the opposite of the mode's shape.
    print('')
    print('  AND A STOPPED RIVAL COUNTS FOR NOTHING')
    pg.evaluate("""() => { const R = window.__road;
        R.stageField(R.MAX_SPD * 0.80);
        R.holdField(R.MAX_SPD * 0.80);
        R.holdSpd(R.MAX_SPD * 0.50); }""")
    wait_engine(pg, swing * 1.2)
    before = pg.evaluate("() => window.__road.shift()")
    # take half the field out, leaving the rest exactly as they were
    # THE HOLD HAS TO COME OFF BEFORE ANYTHING CAN BE STOPPED, or the harness
    # is pinning the rivals at the speed the rule is waiting for them to fall
    # below - a check fighting its own fixture.
    pg.evaluate("""() => { const R = window.__road;
        R.holdField(null);
        const half = Math.floor(R.shift().field / 2);
        R.rivalState().forEach((r, i) => {
            if(i < half) R.stageStop(i, 900 + (i % 3) * 700, R.MAX_SPD * 0.03); });
        R.holdSpd(R.MAX_SPD * 0.03); }""")
    for _ in range(6):
        pg.wait_for_timeout(int((before['hold'] + 2.0) * 1000))
        left = pg.evaluate("() => window.__road.shift()['running']")
        if left <= before['field'] - before['field'] // 2:
            break
        pg.evaluate("""() => { const R = window.__road;
            const half = Math.floor(R.shift().field / 2);
            R.rivalState().forEach((r, i) => {
                if(i < half && !r.out) R.stageStop(i, 900 + (i % 3) * 700, R.MAX_SPD * 0.03); });
            R.holdSpd(R.MAX_SPD * 0.03); }""")
    mid = pg.evaluate("() => window.__road.shift()")
    note(f"{mid['stopped']} stopped, {mid['running']} running, lawless {mid['lawless']}")
    check(mid['stopped'] > 0, 'the staging actually stopped some of them',
          f"{mid['stopped']} stopped")
    check(mid['lawless'] <= mid['running'],
          'the lawless count can never exceed the field still running',
          f"lawless {mid['lawless']}, running {mid['running']}")
    check(mid['lawless'] < before['lawless'],
          'and stopping cars takes them out of the count',
          f"{before['lawless']} -> {mid['lawless']}")

    check(errs == [], 'and none of it raised a page error', errs[0][:90] if errs else '')

print('')
print(f"  {'all checks passed' if not bad[0] else str(bad[0]) + ' FAILURES'}")
sys.exit(1 if bad[0] else 0)
