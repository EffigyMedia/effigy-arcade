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

  THE PRIZE half (owner, 2026-09-17). A CRUISER ladder pays the dozen colours and a
  SUPERCRUISER ladder the iridescent paints, both for the police livery only. It checks the
  flag written, the palette the garage then draws on both force cars and on a racing car, that
  a second win announces nothing, and that a police car keeps its own colour.

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


def paint_after(pg, body):
    """The palette `body` offers, read from the swatches the garage draws.

    It opens the garage first: after a ladder the trophy is on screen, and a
    walk that starts there reads no swatches at all - zero, which looks like a
    palette that shrank rather than like a screen that was never the garage."""
    if not pg.evaluate("() => !!document.querySelector('[data-act=\"next\"]')"):
        pg.evaluate("() => { document.body.classList.remove('trophying');"
                    "        window.__road.showGarage(); }")
        pg.wait_for_timeout(200)
    walk_to(pg, body)
    return pg.evaluate("""() => [...document.querySelectorAll('[data-act^="paint:"]')]
                                 .map(b => b.dataset.act.slice(6))""")


def last_round(pg, body):
    """Win the LAST round of `body`'s shift ladder, and return the trophy text.

    The first three rounds are proven above by driving them; this seeds the
    ladder at its last round so a second prize can be asked about without
    another four-round drive."""
    pg.evaluate("() => { document.body.classList.remove('trophying'); window.__road.showGarage(); }")
    pg.wait_for_timeout(200)
    walk_to(pg, body)
    cycle_to(pg, 'INTERCEPT TOURNAMENT')
    pg.evaluate("() => window.__road.seedTour({ round: 3 })")
    pg.click('[data-act="drive"]')
    pg.wait_for_timeout(1500)
    pg.evaluate("() => window.__road.setTimed(false)")
    pg.evaluate("() => window.__road.stageCleared()")
    if not until(pg, "() => window.__road.tourState().done === true",
                 timeout=15000, required=False):
        return ''
    pg.wait_for_timeout(300)
    return pg.evaluate("() => { const v = document.getElementById('veil');"
                       "        return (v && !v.classList.contains('hidden')) ? v.textContent : ''; }")


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
            before = pg.evaluate("""() => [...document.querySelectorAll('[data-act^="paint:"]')]
                                        .map(b => b.dataset.act.slice(6))""")
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
            # ---- WHAT IT PAID (owner, 2026-09-17) -------------------------------
            # The CRUISER ladder pays the dozen colours for the police livery,
            # and only that: not the racing flip paints, and not the police ones.
            opts = pg.evaluate("() => window.Arcade.save.get('interstate-opts') || {}")
            check('POLICE COLOURS UNLOCKED' in trophy,
                  'the CRUISER ladder announces the police colours', trophy[60:130].strip())
            check(opts.get('copcolours') is True, 'and writes them into the save',
                  f"copcolours={opts.get('copcolours')}")
            check(not opts.get('copiridescent') and not opts.get('iridescent'),
                  'and writes neither iridescent flag',
                  f"copiridescent={opts.get('copiridescent')} iridescent={opts.get('iridescent')}")
            after = paint_after(pg, 'CRUISER')
            check(len(before) == 2 and len(after) == 12,
                  'the CRUISER palette grew from two to twelve',
                  f'{len(before)} -> {len(after)}')
            check(after[:2] == ['WHITE', 'BLACK'] and 'ORACLE' not in after,
                  'white and black first, and no flip paint yet', ', '.join(after[:4]) + ' ...')
            # THE PRIZE STAYS WITH THE FORCE. A racing car's palette is the base
            # dozen before and after - `copcolours` must not open anything there.
            check(len(paint_after(pg, 'HATCH')) == 12 and
                  'ORACLE' not in paint_after(pg, 'HATCH'),
                  'and a racing car gained nothing', ', '.join(paint_after(pg, 'HATCH')[-2:]))

            # ---- A SECOND WIN CLAIMS NOTHING NEW (RLG-202) --------------------
            # Run the last round again: the flag is already held, so the trophy
            # must not announce it a second time.
            again = last_round(pg, 'CRUISER')
            check(again and 'UNLOCKED' not in again,
                  'a second CRUISER ladder announces nothing', again[:60].strip() if again else 'no trophy')

            # ---- AND THE SUPERCRUISER LADDER PAYS THE FLIP PAINTS -------------
            sup = last_round(pg, 'SUPERCRUISER')
            opts = pg.evaluate("() => window.Arcade.save.get('interstate-opts') || {}")
            check(sup and 'IRIDESCENT POLICE PAINT UNLOCKED' in sup,
                  'the SUPERCRUISER ladder announces iridescent police paint',
                  sup[60:140].strip() if sup else 'no trophy')
            check(opts.get('copiridescent') is True and not opts.get('iridescent'),
                  'and writes the POLICE flag, not the racing one',
                  f"copiridescent={opts.get('copiridescent')} iridescent={opts.get('iridescent')}")
            cr = paint_after(pg, 'CRUISER')
            check(len(cr) == 17 and 'ORACLE' in cr,
                  'both force cars now offer the flip paints', f'CRUISER {len(cr)} choices')
            check('ORACLE' not in paint_after(pg, 'HATCH'),
                  'and a racing car still does not', '')

            # ---- A POLICE COLOUR IS ITS OWN (RLG-212) ------------------------
            # Paint the HATCH pink and the CRUISER lime through the real
            # swatches: neither may take the other's colour.
            walk_to(pg, 'HATCH'); pg.click('[data-act="paint:PINK"]'); pg.wait_for_timeout(120)
            walk_to(pg, 'CRUISER')
            first = pg.evaluate("() => window.__road.paint ? window.__road.paint() : null")
            pg.click('[data-act="paint:LIME"]'); pg.wait_for_timeout(120)
            walk_to(pg, 'HATCH')
            hatch = pg.evaluate("() => window.__road.paint()")
            walk_to(pg, 'CRUISER')
            cop = pg.evaluate("() => window.__road.paint()")
            check(first != 'PINK', 'the cruiser did not take the racing colour', f'{first}')
            check(hatch == 'PINK' and cop == 'LIME',
                  'and each keeps its own', f'HATCH {hatch}, CRUISER {cop}')

        check(errs == [], 'the road raised no page error', errs[0][:90] if errs else '')

    print(f"\n  {'PASS' if not bad[0] else str(bad[0]) + ' FAILED'}\n")
    b.close()

sys.exit(1 if bad[0] else 0)
