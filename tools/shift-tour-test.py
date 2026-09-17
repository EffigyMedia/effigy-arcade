"""INTERCEPT HAS A TOURNAMENT AND ITS ROUNDS GET SHORTER - RLG-212.

    .venv/Scripts/python tools/shift-tour-test.py

Owner, 2026-09-11: "There should be a tournament mode for intercept, but instead of the
races getting longer, they get shorter, so they get harder." And, correcting an earlier
session that had read the ruling's own caution as a block, 2026-09-16: "I actually did want
the distances of a rate inverse. I never said otherwise. If it turns out not to work, then
we can rebalance."

WHAT THIS ASKS, IN THREE PARTS.

  THE CONTROL half reads what the player sees. A police car's MODE button has three stops
  now - TEST DRIVE, INTERCEPT, INTERCEPT TOURNAMENT - which is the symmetry the owner asked
  for, and it is read off the DOM by clicking the real button rather than by asking the
  engine what it thinks it would say.

  THE LADDER half is the ruling's substance. Both ladders are read through the SAME call in
  the SAME run, and each is asserted to run the right WAY: the shift's strictly down, the
  racing one strictly up. That is what makes this check capable of failing. If the seam that
  chooses a ladder were missing, both arms would read the same four numbers and one of the
  two assertions is wrong whichever four they are - there is no build where a single shared
  ladder passes both.

  THE ROUNDS half drives it. A shift is cleared, and the check watches the round advance,
  the next distance fall, and the finish line move with it. Four rounds, then the trophy.

WHAT IS STAGED AND WHAT IS MEASURED. The clear is staged - `API.stageCleared` puts every
rival out through the game's own `stopRacer`, for the reason `stageStop` gives and repeats:
the manoeuvre cannot be flown by a harness. What is MEASURED is everything the tournament
owns on top of that: the ladder, the advance, the finish distance, the attempts, and the
end. None of it is staged and none of it is read back from a value this file wrote.

WHAT THIS CANNOT CHECK, STATED PLAINLY. It does not say the ladder is WELL CHOSEN. Nobody
has played the mode on a device, so whether ten miles is enough road to stop eleven cars is
open - the owner's word for it is "rebalance", and the four distances are tunables with
committed defaults rather than a finding. This proves the ladder falls, not that it is
right.

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


def open_garage(pg):
    """Boot, WIN the police cars, and walk in through the title card.

    The same path duty-test takes and for the same reason: the DEBUG screen's police toggle
    LISTS a car without unlocking it, so DRIVE stays disabled and the road half could never
    run. Writing the flag the tournament writes is the honest route to the road."""
    boot(pg, f'http://127.0.0.1:{PORT}/{GAME}')
    settle(pg)
    pg.evaluate("""() => window.Arcade.save.merge('interstate-opts',
                     { super:true, cruiser:true, supercruiser:true })""")
    reboot(pg)
    settle(pg)
    pg.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
    pg.click('[data-act="play"]')
    pg.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)


def label(pg, act='mode'):
    return pg.evaluate("""(act) => {
      const b = document.querySelector('[data-act="' + act + '"]');
      return b ? b.textContent.trim().split('\\u00b7').pop().trim() : '';
    }""", act)


def car(pg):
    return pg.evaluate("() => window.__road.body()")


def walk_to(pg, want, limit=40):
    seen = []
    for _ in range(limit):
        k = car(pg)
        if k == want:
            return k, seen
        if k in seen:
            break
        seen.append(k)
        pg.click('[data-act="next"]')
        pg.wait_for_timeout(90)
    return (car(pg) if car(pg) == want else None), seen


def cycle_to(pg, want, limit=6):
    """Click MODE like a thumb until the control reads `want`."""
    for _ in range(limit):
        if label(pg) == want:
            return True
        pg.click('[data-act="mode"]')
        pg.wait_for_timeout(110)
    return label(pg) == want


def tour(pg):
    return pg.evaluate("() => window.__road.tourState()")


def strictly_down(xs):
    return all(b < a for a, b in zip(xs, xs[1:]))


def strictly_up(xs):
    return all(b > a for a, b in zip(xs, xs[1:]))


with sync_playwright() as p:
    b = launch_chromium(p, headless=True,
                        args=['--mute-audio', '--autoplay-policy=no-user-gesture-required'])

    # ================================================================== THE CONTROL
    print('\n  THE CONTROL - three stops, the same shape a racing car has')
    pg = b.new_context(viewport={'width': 480, 'height': 900}).new_page()
    errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    open_garage(pg)

    found, _ = walk_to(pg, 'CRUISER')
    check(found == 'CRUISER', 'the garage reaches a police car', f'{found}')

    if found != 'CRUISER':
        print('\n  the walk never reached a police car - every check below is blocked')
        bad[0] += 1
    else:
        stops = []
        for _ in range(6):
            stops.append(label(pg))
            pg.click('[data-act="mode"]')
            pg.wait_for_timeout(110)
        # THE CYCLE, NOT A SET. Three distinct stops that come back round, which is
        # what "the same three-stop shape" means - a fourth would be a control the
        # player has to press four times to get home.
        first3 = stops[:3]
        check(sorted(first3) == sorted(['TEST DRIVE', 'INTERCEPT', 'INTERCEPT TOURNAMENT']),
              'the MODE control has exactly three stops', ' -> '.join(stops[:4]))
        check(stops[3] == stops[0], 'and the fourth press is back to the first',
              f"{stops[0]} ... {stops[3]}")
        # the racing modes are still gone, and a BARE 'TOURNAMENT' is the racing one
        check('SINGLE RACE' not in stops and 'TOURNAMENT' not in stops,
              'and no RACING mode is reachable in a police car', ' -> '.join(stops[:4]))

        # =============================================================== THE LADDER
        print('\n  THE LADDER - which way each one runs')
        check(cycle_to(pg, 'INTERCEPT TOURNAMENT'),
              'the shift tournament can be set', f"'{label(pg)}'")
        shift = tour(pg)
        check(shift['on'] is True, 'and the tournament is in effect', f"on={shift['on']}")
        check(strictly_down(shift['ladder']),
              'the SHIFT ladder runs DOWN', f"{shift['ladder']}")
        check(shift['round'] == 0 and shift['miles'] == shift['ladder'][0],
              'and round one is its longest leg',
              f"round {shift['round'] + 1}, {shift['miles']} mi")

        # THE OTHER ARM, IN THE SAME RUN AND THROUGH THE SAME CALL. This is what
        # makes the check above capable of failing: one shared ladder cannot be
        # both strictly down and strictly up, so a missing seam fails here.
        # A PRODUCTION CAR, because it is the class the player starts in and is
        # the only racing car guaranteed to be unlocked in this save (RLG-213).
        # A locked car draws no MODE control at all (RLG-223), so walking to one
        # would fail this arm for a reason that has nothing to do with a ladder.
        racer, _ = walk_to(pg, 'SALOON')
        check(racer == 'SALOON', 'the garage gets back to a racing car', f'{racer}')
        check(cycle_to(pg, 'TOURNAMENT'), 'and its tournament can be set',
              f"'{label(pg)}'")
        race = tour(pg)
        check(strictly_up(race['ladder']),
              'the RACING ladder runs UP, unchanged', f"{race['ladder']}")
        check(list(reversed(race['ladder'])) == list(shift['ladder']),
              "and the shift's is the racing one reversed",
              f"{race['ladder']} vs {shift['ladder']}")

        check(errs == [], 'the garage raised no page error', errs[0][:90] if errs else '')

        # =============================================================== THE ROUNDS
        print('\n  THE ROUNDS - a clear advances, and the next leg is shorter')
        pg = b.new_context(viewport={'width': 480, 'height': 900}).new_page()
        errs = []
        pg.on('pageerror', lambda e: errs.append(str(e)))
        open_garage(pg)
        got, _ = walk_to(pg, 'CRUISER')
        if got != 'CRUISER' or not cycle_to(pg, 'INTERCEPT TOURNAMENT'):
            check(False, 'the road arm reached a police car on the tournament', f'{got}')
        else:
            ladder = tour(pg)['ladder']
            seen_legs, seen_rounds = [], []
            for n in range(len(ladder)):
                # ROUND ONE IS ENTERED FROM THE GARAGE AND THE REST FROM THE
                # ROUND CARD, which is the player's own path through a ladder -
                # DRIVE once, then NEXT SHIFT three times. Clicking DRIVE every
                # round would be asking the garage for a tournament it is in the
                # middle of, which is not a screen the mode offers.
                pg.click('[data-act="drive"]' if n == 0 else '[data-act="next"]')
                pg.wait_for_timeout(1500)
                # RLG-125: a parked car runs the clock out and every driving number
                # freezes where it stood, which does not look like a clock fault.
                pg.evaluate("() => window.__road.setTimed(false)")
                st = tour(pg)
                seen_rounds.append(st['round'])
                seen_legs.append(st['miles'])
                # WHAT THE ROAD WAS ACTUALLY BUILT TO, not what the state says it
                # should be: `finishZ` is laid down by `buildField` and is the thing
                # the loss condition reads. A ladder the screens agree about and the
                # road ignores is exactly the defect worth catching.
                laid = pg.evaluate("() => window.__road.raceLeg && window.__road.raceLeg()")
                if laid is not None:
                    check(abs(laid - st['miles']) < 0.15,
                          f'  round {n + 1}: the road is laid to the ladder',
                          f"{laid:.2f} mi against {st['miles']}")
                cleared = pg.evaluate("() => window.__road.stageCleared()")
                check(cleared['running'] == 0,
                      f'  round {n + 1}: the field is cleared',
                      f"{cleared['stopped']} stopped, {cleared['running']} left")
                # WAIT ON THE CONDITION, NOT ON A CLOCK. A fixed pause read the
                # last round as unfinished on this machine and the round before
                # it as finished, which is the shape of a harness measuring its
                # own timeout rather than the game - the end card is behind a
                # frame, a 700ms hand-off and a coast-down, and none of the three
                # is a duration this file should be asserting.
                want = n + 1
                moved = until(pg, "(w) => { const t = window.__road.tourState();"
                                  "         return t.round >= w || t.done === true; }",
                              arg=want, timeout=15000, required=False)
                check(moved, f'  round {n + 1}: the shift ended and the ladder moved',
                      'still on the same round after 15s' if not moved else '')

            check(seen_legs == list(ladder),
                  'the four rounds ran the ladder, in order', f'{seen_legs}')
            check(seen_rounds == list(range(len(ladder))),
                  'and the round advanced on each clear', f'{seen_rounds}')

            # THE END OF IT. `done` is the flag the garage retires a spent ladder
            # on (RLG-232), and it is the honest test of "the last round ended the
            # tournament" - a fifth round would leave it false.
            st = tour(pg)
            check(st['done'] is True, 'a clear of the last round ends the tournament',
                  f"done={st['done']} round={st['round'] + 1}")
            # NOT `#veil:not(.hidden)`: the trophy takes the veil's hidden class
            # OFF and marks the body `trophying`, so that selector matched
            # nothing on any screen in this mode and read '' for every round -
            # a check that can only report absence proves nothing about presence.
            trophy = pg.evaluate(
                "() => { const v = document.getElementById('veil');"
                "        return (v && !v.classList.contains('hidden')) ? v.textContent : ''; }")
            check('TOURNAMENT COMPLETE' in trophy, 'and the trophy screen is up',
                  trophy[:60].strip())
            # IT PAYS NOTHING YET, AND THAT IS ASSERTED RATHER THAN LEFT OPEN.
            # RLG-212's third part is the owner's open question, so a build that
            # quietly invented a prize is a build that answered it without them.
            check('UNLOCKED' not in trophy.upper(),
                  'and claims no prize - RLG-212 part 3 is the owner\'s',
                  'a prize was announced' if 'UNLOCKED' in trophy.upper() else 'nothing claimed')

        check(errs == [], 'the road raised no page error', errs[0][:90] if errs else '')

    print(f"\n  {'PASS' if not bad[0] else str(bad[0]) + ' FAILED'}\n")
    b.close()

sys.exit(1 if bad[0] else 0)
