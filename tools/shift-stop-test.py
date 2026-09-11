"""A RACER IS STOPPED, NOT DESTROYED - AND THE RACE FINISHING IS THE LOSS. RLG-203.

    .venv/Scripts/python tools/shift-stop-test.py

Owner, 2026-09-10, on what counts as taken out: "Just destroying them is kinda boring. I
suppose the only other option IS to box them in. Maybe there should be other friendly
cruiser to help, but its up to YOU! to get in front and slow them down." And on what
happens if the race finishes with racers left: "You lose and the shift ends."

WHAT THIS PROVES, AND WHAT IT DELIBERATELY DOES NOT.

  THE MANOEUVRE CANNOT BE FLOWN BY A HARNESS. Getting in front of a rival and holding it
  under a fifth of top speed is a driving task; drive-test's autopilot steers to a lane and
  holds a throttle, and this project has already been told once what happens when a harness
  is trusted to drive (Raceway's tyres, killed in twenty seconds by an autopilot sawing at
  the wheel). So the CONDITION is staged and the RULE is what is measured. Whether a player
  can actually bring a rival to that speed is a question only the device answers, and it is
  said here rather than implied.

  EVERY POSITIVE CHECK HAS A NEGATIVE BESIDE IT, because "the rule fired" is worth nothing
  without "and it does not fire when it should not". A rival that is slow but AHEAD of the
  player must not count - that is a car stuck behind traffic, not a car you caught - and a
  rival that is in front but quick must not count either.

  AND THE THRESHOLDS ARE READ OFF THE ENGINE, never hardcoded. `API.shift()` reports the
  hold, the speed and the reach. A harness carrying its own copy of them would keep passing
  after they were retuned and would be measuring a build that no longer exists.

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
    print(f'  {"ok  " if ok else "FAIL"}  {label:<54} {detail}')
    if not ok:
        bad[0] += 1


def note(text):
    print(f'  ..    {text}')


def settle(pg):
    try:
        until(pg, '() => navigator.serviceWorker && navigator.serviceWorker.controller',
              timeout=5000)
        pg.wait_for_timeout(1000)
    except Exception:
        pass


def control(pg, act):
    return pg.evaluate("""(act) => {
      const b = document.querySelector('[data-act="' + act + '"]');
      return b ? { label: b.textContent.trim() } : null; }""", act)


def on_shift(pg):
    """Boot into a CRUISER, put it on INTERCEPT, and drive."""
    boot(pg, f'http://127.0.0.1:{PORT}/{GAME}')
    settle(pg)
    pg.evaluate("""() => window.Arcade.save.merge('interstate-opts',
                     { super:true, cruiser:true, supercruiser:true })""")
    reboot(pg)
    settle(pg)
    pg.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
    pg.click('[data-act="play"]')
    pg.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
    for _ in range(40):
        if pg.evaluate("() => window.__road.body()") == 'CRUISER':
            break
        pg.click('[data-act="next"]')
        pg.wait_for_timeout(90)
    for _ in range(4):
        if control(pg, 'mode')['label'].endswith('INTERCEPT'):
            break
        pg.click('[data-act="mode"]')
        pg.wait_for_timeout(120)
    pg.click('[data-act="drive"]')
    pg.wait_for_timeout(2000)
    # RLG-125: a run starts with sixty seconds and a harness that holds the car
    # still reaches no checkpoint to buy more, after which every number freezes.
    pg.evaluate("() => window.__road.setTimed(false)")


with sync_playwright() as p:
    b = launch_chromium(p, headless=True,
                        args=['--mute-audio', '--autoplay-policy=no-user-gesture-required'])

    # ================================================= THE FIELD AND THE WINGMEN
    print('\n  THE SHIFT STARTS')
    pg = b.new_context(viewport={'width': 480, 'height': 900}).new_page()
    errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    on_shift(pg)

    sh = pg.evaluate("() => window.__road.shift()")
    check(sh['on'] is True, 'the run is on shift', f"duty={sh['on']}")
    check(sh['running'] == sh['field'],
          'the whole field is running at the start',
          f"{sh['running']} of {sh['field']}")
    check(sh['stopped'] == 0, 'and none of it is stopped yet', f"{sh['stopped']}")
    # ---- THE WINGMEN, COUNTED ON THE ROAD RATHER THAN IN THE RULE -----------
    # The first version of this asserted `dispatchCap() >= WINGMEN`, and that is
    # the mistake this file exists to catch: the cap said two and the road put
    # out NONE, because the radio only reinforces a pursuit already in progress
    # and on shift nothing is ever on the player. A cap is a permission. What the
    # owner asked for is cars. So this counts cars.
    #
    # Held at a speed a cruiser can match: a patrol car tops out at 0.71 of the
    # player's, and a harness at full throttle culls its own wingmen.
    note(f"the dispatch cap on shift is {sh['cap']} - the floor is NOT a cap")
    pg.evaluate("() => window.__road.holdSpd(window.__road.MAX_SPD * 0.45)")
    best = 0
    for _ in range(14):
        pg.wait_for_timeout(5000)
        n = pg.evaluate("() => window.__road.copCensus()['chasers']")
        best = max(best, n)
        if best >= sh['wingmen']:
            break
    note(f"cruisers on the road, most seen at once: {best}")
    check(best >= sh['wingmen'], 'the shift keeps its wingmen out',
          f"{best} against a floor of {sh['wingmen']}")

    # ============================================================== THE NEGATIVES
    # Run these BEFORE the positive, so a rule that fires on everything is caught
    # by a check that has not already ended the shift.
    print('\n  WHEN IT MUST NOT FIRE')
    sh = pg.evaluate("() => window.__road.shift()")
    hold = sh['hold']

    # AHEAD OF THE PLAYER AND SLOW: a car stuck behind traffic, not one you caught.
    # THE REST OF THE FIELD IS PARKED OUT OF REACH FIRST. Staging one rival and
    # then changing the player's speed for the next check meant the player
    # overtook an earlier one, and the rule - correctly - stopped it: the tally
    # moved during a check about a different car. A measurement of one rival has
    # to be a measurement of one rival.
    pg.evaluate("""() => { const R = window.__road;
        R.parkRivals(0);
        R.stageStop(0, -4000, R.MAX_SPD * 0.05);   /* negative dz = up the road */
        R.holdSpd(R.MAX_SPD * 0.05); }""")
    pg.wait_for_timeout(int((hold + 2.5) * 1000))
    st = pg.evaluate("() => window.__road.rivalState()[0]")
    sh = pg.evaluate("() => window.__road.shift()")
    note(f"slow, but {st['dz']} up the road: out={st['out']} hold={st['stopT']}s of {hold}s")
    check(st['out'] is False, 'a rival AHEAD of you is not stopped by being slow',
          f"dz {st['dz']}, out={st['out']}")
    check(st['stopT'] == 0, 'and the hold never even starts',
          f"{st['stopT']}s banked")

    # IN FRONT OF THE PLAYER BUT QUICK: you are behind it, not blocking it.
    pg.evaluate("""() => { const R = window.__road;
        R.parkRivals(1);
        R.stageStop(1, 1200, R.MAX_SPD * 0.62);
        R.holdSpd(R.MAX_SPD * 0.62); }""")
    pg.wait_for_timeout(int((hold + 2.5) * 1000))
    st = pg.evaluate("() => window.__road.rivalState()[1]")
    note(f"behind you but quick: out={st['out']} hold={st['stopT']}s of {hold}s")
    check(st['out'] is False, 'and a rival that is still quick is not stopped either',
          f"out={st['out']}, hold {st['stopT']}s")

    # ==================================================================== THE STOP
    print('\n  WHEN IT MUST FIRE')

    pg.evaluate("""() => { const R = window.__road;
        R.parkRivals(2);
        /* just behind the player, in the player's line, going nowhere */
        R.stageStop(2, 1200, R.MAX_SPD * 0.04);
        R.holdSpd(R.MAX_SPD * 0.04); }""")
    before = pg.evaluate("() => window.__road.shift()")
    # sampled part-way through, so a rule that fired instantly is not mistaken
    # for one that held for the time it is supposed to hold for
    pg.wait_for_timeout(int(hold * 1000 * 0.5))
    mid = pg.evaluate("() => window.__road.rivalState()[2]")
    note(f"half way through the hold: out={mid['out']} banked {mid['stopT']}s of {hold}s")
    check(mid['out'] is False and mid['stopT'] > 0,
          'the hold runs before it lands, rather than firing at once',
          f"{mid['stopT']}s of {hold}s banked, out={mid['out']}")
    pg.wait_for_timeout(int((hold + 2.0) * 1000))
    st = pg.evaluate("() => window.__road.rivalState()[2]")
    after = pg.evaluate("() => window.__road.shift()")
    note(f"after the hold: out={st['out']}, {after['running']} of {after['field']} left")
    check(st['out'] is True, 'a rival held slow in front of you IS stopped',
          f"out={st['out']}")
    check(after['running'] == before['running'] - 1,
          'and the field is one car smaller',
          f"{before['running']} -> {after['running']}")
    check(after['stopped'] == before['stopped'] + 1, 'and the shift has counted it',
          f"{before['stopped']} -> {after['stopped']}")
    # NOT WRECKED. The whole of the owner's answer is that it is a manoeuvre.
    check(after['finished'] is False, 'and the shift is still running',
          f"finished={after['finished']}")
    check(errs == [], 'no page errors so far', errs[0][:90] if errs else '')

    # ===================================================================== THE LOSS
    # A racer reaching the line ends it, and the PLAYER reaching the line does not:
    # the player is policing, and where they are on the road decides nothing.
    print('\n  THE RACE FINISHING IS THE LOSS')
    pg2 = b.new_context(viewport={'width': 480, 'height': 900}).new_page()
    errs2 = []
    pg2.on('pageerror', lambda e: errs2.append(str(e)))
    on_shift(pg2)
    # THE FIELD HAS TO BE PUT BEHIND THE LINE FIRST, and the first version of
    # this check did not: rivals start AHEAD of the player, so a line the player
    # has crossed has been crossed by all eleven of them, and the shift ended as
    # a loss before the question could be asked. The configuration that asks it
    # is the player past the line with the field still short of it.
    pg2.evaluate("""() => { const R = window.__road;
        for(let i = 0; i < R.shift().field; i++) R.stageStop(i, 9000 + i*600, 0);
        R.parkFinish(1200); }""")
    pg2.wait_for_timeout(2500)
    sh = pg2.evaluate("() => window.__road.shift()")
    rs = pg2.evaluate("() => window.__road.rivalState()")
    note(f"the player is past the line and the field is not "
         f"(nearest rival {max(r['dz'] for r in rs)}): finished={sh['finished']}")
    check(sh['finished'] is False,
          'the PLAYER crossing the line does not end the shift',
          f"finished={sh['finished']} outcome='{sh['outcome']}'")
    # now put a rival over it
    pg2.evaluate("""() => { const R = window.__road;
        R.parkFinish(0); R.stageStop(0, -600, R.MAX_SPD * 0.4); }""")
    pg2.wait_for_timeout(3000)
    sh = pg2.evaluate("() => window.__road.shift()")
    note(f"a rival is past the line: finished={sh['finished']} outcome='{sh['outcome']}'")
    check(sh['finished'] is True, 'a RIVAL crossing it ends the shift',
          f"finished={sh['finished']}")
    check(sh['outcome'] == 'THEY GOT THROUGH', 'and it ends as a loss',
          f"'{sh['outcome']}'")
    check(errs2 == [], 'and the loss raised no page error', errs2[0][:90] if errs2 else '')

    # ============================================== AND STOPPING THEM ALL WINS
    # The other end condition, and the one a player is trying to reach. The whole
    # field is staged into the stop at once - all eleven in the player's line,
    # all going nowhere - so the hold lands on them together. That is not a
    # situation a player would produce; the RULE being measured is "the last one
    # out ends the shift, and it ends it as a win", which is.
    print('')
    print('  AND STOPPING THEM ALL IS THE WIN')
    pg3 = b.new_context(viewport={'width': 480, 'height': 900}).new_page()
    errs3 = []
    pg3.on('pageerror', lambda e: errs3.append(str(e)))
    on_shift(pg3)
    hold = pg3.evaluate("() => window.__road.shift()")['hold']
    # STAGED IN PASSES, NOT ALL AT ONCE. Eleven cars dropped into one lane at
    # forty units apart shove each other sideways, and a car pushed out of the
    # player's line stops satisfying the condition - one rival in eleven survived
    # that way, on two runs in three. Re-staging whoever is still running is both
    # more robust and more honest: what is being measured is that the field CAN
    # be brought to zero and that the last one out ends the shift.
    for _ in range(5):
        left = pg3.evaluate("() => window.__road.shift()['running']")
        if left == 0:
            break
        pg3.evaluate("""() => { const R = window.__road;
            R.rivalState().forEach((r, i) => {
              if(!r.out) R.stageStop(i, 900 + (i % 3) * 700, R.MAX_SPD * 0.03); });
            R.holdSpd(R.MAX_SPD * 0.03); }""")
        pg3.wait_for_timeout(int((hold + 2.0) * 1000))
    sh = pg3.evaluate("() => window.__road.shift()")
    note(f"{sh['stopped']} stopped, {sh['running']} running, "
         f"finished={sh['finished']} outcome='{sh['outcome']}'")
    check(sh['running'] == 0, 'the whole field can be stopped',
          f"{sh['running']} still running")
    check(sh['stopped'] == sh['field'], 'and every one of them is counted',
          f"{sh['stopped']} of {sh['field']}")
    check(sh['finished'] is True, 'and the shift ends', f"finished={sh['finished']}")
    check(sh['outcome'] == 'SHIFT CLEAR', 'and it ends as a WIN, not a loss',
          f"'{sh['outcome']}'")
    check(errs3 == [], 'and the win raised no page error', errs3[0][:90] if errs3 else '')

print(f"\n  {'all checks passed' if not bad[0] else str(bad[0]) + ' FAILURES'}")
sys.exit(1 if bad[0] else 0)
