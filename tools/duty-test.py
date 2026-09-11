"""INTERCEPT IS A MODE A POLICE CAR CAN ENTER, AND THE RACE MODES ARE NOT - RLG-203.

    .venv/Scripts/python tools/duty-test.py

Owner, 2026-09-10: "if you have them unlocked, and you have them selected, one of the game
mode choices would be a mode where you play as a cop taking out racers before they finish a
race", and later: "I feel like the smarter design is to replace their race modes with
Intercept." And on what the mode is: "it should play like a standard race with hot pursuit
enabled, its just you arent a racer - you are a cop... identical except for the fact that
there's no single racer accruing heat."

WHAT THIS ASKS. Two halves, and they fail in opposite directions.

  THE GARAGE half reads what the PLAYER sees - the label on the MODE control, whether it is
  shut, and the note under it - exactly as class-test.py does for RLG-115, and for the same
  reason: the rule is "the menu offers what the car can do", not "the game refuses later".
  It drives the real buttons. A harness that asked `dutyLegal()` and then asserted
  `dutyLegal()` would agree with itself and prove nothing.

  THE ROAD half asks whether the world has stopped coming after the player. That is four
  separate mechanisms and they are asserted separately, because three of them passing is
  exactly what a half-built guard looks like: heat accrual, a cruiser's target search, a
  patrol or a trap engaging, and the bust.

THE THREE THINGS THAT WOULD MAKE THIS VACUOUS, each guarded:

  1. Never reaching a police car. They are won by taking a tournament gold with hot pursuit
     on, so a fresh save has none. The unlock is written into the save the way the
     tournament writes it, and the walk ASSERTS it found one - otherwise every "the race
     modes are gone" check would pass by never being tested. NOT the DEBUG screen's police
     toggle: that lists the car without unlocking it, so DRIVE stays disabled and the road
     half of this file could never run.

  2. Reading TEST DRIVE on a control that was never anything else. A label that says TEST
     DRIVE because nothing ever set it proves nothing, so the walk puts a TOURNAMENT on a
     racing car FIRST and confirms it took.

  3. The road half passing because nothing was happening anyway. A player who never speeds
     is never chased in an ordinary race either, so each road check is run TWICE - once on
     shift and once in the same car off shift - and the OFF arm has to show the thing
     happening. A guard that is never exercised is not a guard.

WHAT THIS CANNOT CHECK. It does not play INTERCEPT: there is no scoring, no win and no loss
yet, and nothing here asserts that stopping a racer does anything, because none of that is
built. It reads the mode's shape and its four guards, and that is all it claims.

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


def settle(pg):
    try:
        until(pg, '() => navigator.serviceWorker && navigator.serviceWorker.controller',
              timeout=5000)
        pg.wait_for_timeout(1000)
    except Exception:
        pass


def open_garage(pg):
    """Boot, WIN the police cars, and walk in through the title card.

    THE UNLOCK IS GRANTED, NOT FAKED, AND THE DEBUG SWITCH IS THE WRONG TOOL HERE. The
    DEBUG screen's police toggle widens `garageBodies` only: it LISTS the car without
    writing the unlock flag, so `carLocked` is still true and the DRIVE button is disabled.
    A harness driving the real buttons gets as far as the garage and then cannot leave it -
    which is what the first run of this file did. Writing the flag the tournament writes is
    both the honest path and the only one that reaches the road."""
    boot(pg, f'http://127.0.0.1:{PORT}/{GAME}')
    settle(pg)
    pg.evaluate("""() => window.Arcade.save.merge('interstate-opts',
                     { super:true, cruiser:true, supercruiser:true })""")
    reboot(pg)
    settle(pg)
    pg.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
    pg.click('[data-act="play"]')
    pg.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)


def control(pg, act):
    """What the player can see about one garage control, read off the DOM."""
    return pg.evaluate("""(act) => {
      const b = document.querySelector('[data-act="' + act + '"]');
      const notes = [...document.querySelectorAll('.gnote')].map(n => n.textContent.trim());
      return b ? { label: b.textContent.trim(),
                   shut: b.disabled === true || b.classList.contains('shut'),
                   notes } : null;
    }""", act)


def car(pg):
    return pg.evaluate("() => window.__road.body()")


def walk_to(pg, want, limit=40):
    """Click NEXT like a thumb until the garage is standing in front of `want`."""
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


def drive(pg):
    """Leave the menus and get on the road."""
    pg.click('[data-act="drive"]')
    pg.wait_for_timeout(1500)


with sync_playwright() as p:
    b = launch_chromium(p, headless=True,
                        args=['--mute-audio', '--autoplay-policy=no-user-gesture-required'])

    # ===================================================================== GARAGE
    print('\n  THE GARAGE - what the player is offered')
    pg = b.new_context(viewport={'width': 480, 'height': 900}).new_page()
    errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    open_garage(pg)

    # guard 2: a race mode that was really set, on a car that can race
    pg.click('[data-act="mode"]')
    pg.wait_for_timeout(120)
    pg.click('[data-act="mode"]')
    pg.wait_for_timeout(120)
    armed = control(pg, 'mode')
    check(armed and armed['label'].endswith('TOURNAMENT'),
          'a race mode can be set at all',
          f"{car(pg)} reads '{armed['label'] if armed else 'no control'}'")

    found, seen = walk_to(pg, 'CRUISER')
    check(found == 'CRUISER', 'the garage lists a police car',
          f'{found}' if found else f'NONE in {len(seen)} cars - the walk found nothing')

    if found != 'CRUISER':
        print('\n  the walk never reached a police car - every check below is blocked')
        bad[0] += 1
    else:
        st = control(pg, 'mode')
        check(not st['shut'], 'and its MODE control is NOT shut',
              f"disabled/greyed: {st['shut']}")
        check(st['label'].endswith('TEST DRIVE'),
              'and a police car starts on TEST DRIVE', f"'{st['label']}'")
        # NOT `'INTERCEPT' in n`: the garage also writes the INTERCEPTOR's own
        # blurb as a `.gnote`, and the loose form matched THAT and passed while
        # this note was missing entirely. Match the statement, not the word.
        pol = next((n for n in st['notes'] if 'NO RACE ENTRY' in n), None)
        check(pol is not None, 'and it says what its other mode is',
              f"'{pol}'" if pol else f"not among {st['notes']}")

        # ---- ONE PRESS REACHES INTERCEPT, AND A SECOND COMES BACK -------------
        pg.click('[data-act="mode"]')
        pg.wait_for_timeout(120)
        st = control(pg, 'mode')
        check(st['label'].endswith('INTERCEPT'), 'one press reaches INTERCEPT',
              f"'{st['label']}'")
        # THE WHOLE OF "replace their race modes": the cycle has two stops, so a
        # second press must come back rather than reaching SINGLE RACE.
        pg.click('[data-act="mode"]')
        pg.wait_for_timeout(120)
        back = control(pg, 'mode')
        check(back['label'].endswith('TEST DRIVE'),
              'and a second press returns to TEST DRIVE, not to a race',
              f"'{back['label']}'")

        # walk the whole cycle and prove no race mode is reachable at all
        labels = []
        for _ in range(6):
            labels.append(control(pg, 'mode')['label'].split('·')[-1].strip())
            pg.click('[data-act="mode"]')
            pg.wait_for_timeout(90)
        check('SINGLE RACE' not in labels and 'TOURNAMENT' not in labels,
              'no race mode is reachable in a police car',
              ' -> '.join(labels[:4]))
        check('INTERCEPT' in labels, 'and INTERCEPT is', ' -> '.join(labels[:4]))

        # ---- HOT PURSUIT IS NOT A CHOICE ON SHIFT ----------------------------
        while not control(pg, 'mode')['label'].endswith('INTERCEPT'):
            pg.click('[data-act="mode"]')
            pg.wait_for_timeout(90)
        ch = control(pg, 'chase')
        check(ch['label'].endswith('ON'), 'HOT PURSUIT reads ON on shift', f"'{ch['label']}'")
        check(ch['shut'], 'and the control is shut', f"disabled/greyed: {ch['shut']}")
        # ---- THE SECOND LOCK, EXERCISED THE WAY IT IS MEANT TO BE ------------
        # `disabled` is the first lock and Playwright will not click through it,
        # which is the point: a thumb cannot. The lock in the ACTION exists for
        # the case `disabled` cannot cover - a veil rendered in one state and
        # pressed in another - so the button is re-enabled in the DOM first,
        # which is exactly that stale veil, and then pressed.
        pg.eval_on_selector('[data-act="chase"]',
                            "el => { el.disabled = false; el.classList.remove('shut'); }")
        pg.click('[data-act="chase"]')
        pg.wait_for_timeout(120)
        check(pg.evaluate("() => window.__road.duty().pursuit") is True,
              'and a stale veil cannot turn it off either',
              f"pursuit={pg.evaluate('() => window.__road.duty().pursuit')}")
        # the DOM was deliberately corrupted above; put the real screen back
        pg.evaluate("() => window.__road.showGarage()")
        pg.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)

        # ---- THE FIELD IS SYMMETRICAL ----------------------------------------
        # Owner: "the cruiser intercepts against a sports class race and the
        # supercruiser intercepts against a super class race."
        cls = pg.evaluate("() => window.__road.raceClass()")
        check(cls == 'sports', 'a CRUISER intercepts the sports class', f"'{cls}'")
        sup, _ = walk_to(pg, 'SUPERCRUISER')
        if sup == 'SUPERCRUISER':
            check(pg.evaluate("() => window.__road.raceClass()") == 'super',
                  'and a SUPERCRUISER the super class',
                  pg.evaluate("() => window.__road.raceClass()"))
            check(control(pg, 'mode')['label'].endswith('INTERCEPT'),
                  'and INTERCEPT survives the walk between the two police cars',
                  f"'{control(pg, 'mode')['label']}'")
        else:
            note('SUPERCRUISER not in the garage - two checks blocked')
            bad[0] += 1

        # ---- WALKING OUT OF A POLICE CAR TAKES THE SHIFT WITH YOU ------------
        # Left set, the player would be on a sports grid with the world refusing
        # to chase them and no control anywhere that could turn it off.
        racer, _ = walk_to(pg, 'ROADSTER')
        check(racer == 'ROADSTER', 'the garage can get back to a racing car', f'{racer}')
        if racer == 'ROADSTER':
            d = pg.evaluate("() => window.__road.duty()")
            # THE CHOICE MAY SURVIVE; THE SHIFT MAY NOT. `chosen` is what the
            # player picked and `on` is whether this car can act on it, and the
            # separation is the whole fix for the CRUISER-to-SUPERCRUISER walk.
            check(d['on'] is False, 'and the shift is not in effect in a racing car',
                  f"on={d['on']} chosen={d['chosen']} legal={d['legal']}")
            # IT KEPT ITS TOURNAMENT, and that is the check rather than a
            # convenience: the racing car was left on TOURNAMENT at the top of
            # this run, and going to look at the police cars must not quietly
            # reset it - which is exactly what one shared `mode` did.
            check(control(pg, 'mode')['label'].endswith('TOURNAMENT'),
                  'and the racing car still holds the mode it was left on',
                  f"'{control(pg, 'mode')['label']}'")

    check(errs == [], 'the garage raised no page error', errs[0][:90] if errs else '')

    # ====================================================================== ROAD
    # Each guard is run on shift AND off shift in the same car. The OFF arm is
    # what proves the check is capable of failing.
    for on_shift in (False, True):
        print(f"\n  THE ROAD - {'ON SHIFT (INTERCEPT)' if on_shift else 'OFF SHIFT (the control)'}")
        pg = b.new_context(viewport={'width': 480, 'height': 900}).new_page()
        errs = []
        pg.on('pageerror', lambda e: errs.append(str(e)))
        open_garage(pg)
        got, _ = walk_to(pg, 'CRUISER')
        if got != 'CRUISER':
            check(False, 'the road arm reached a police car', f'{got}')
            continue
        # The SAME CAR both times. Off shift it is a patrol car on a test drive,
        # which is a thing the game already allows and is the honest control: the
        # only difference between the arms is the flag.
        if on_shift:
            while not control(pg, 'mode')['label'].endswith('INTERCEPT'):
                pg.click('[data-act="mode"]')
                pg.wait_for_timeout(90)
        else:
            while not control(pg, 'mode')['label'].endswith('TEST DRIVE'):
                pg.click('[data-act="mode"]')
                pg.wait_for_timeout(90)
            # HOT PURSUIT through the real button, because off shift it is a real
            # choice and the control arm has to be a thing a player could set up.
            for _ in range(3):
                if control(pg, 'chase')['label'].endswith('ON'):
                    break
                pg.click('[data-act="chase"]')
                pg.wait_for_timeout(120)
        drive(pg)

        d = pg.evaluate("() => window.__road.duty()")
        check(d['on'] is on_shift, 'the run started on the mode that was chosen',
              f"duty={d['on']} pursuit={d['pursuit']}")

        # ---- 0: A PATROL, WHICH IS THE GUARD NOTHING ELSE HERE TOUCHES --------
        # A patrol is a traffic car that becomes a cruiser the moment you overtake
        # it above the limit. It is a DIFFERENT guard from the target search - the
        # cruiser it produces is created already engaged - so it is staged and
        # asked separately. Twenty points in one event (HEAT_SEEN) is also a far
        # sharper heat signal than the per-mile trickle, which is two points a
        # MILE and rounds away over a few seconds.
        pg.evaluate("""() => { const R = window.__road;
            R.setTimed(false);                 /* RLG-125: a parked car runs the clock out */
            R.copsClear(); R.heatSet(0);
            R.placePatrol(9000);               /* ahead, so it can be overtaken */
            R.holdSpd(R.MAX_SPD * 0.92); }""")
        pg.wait_for_timeout(9000)
        pur = pg.evaluate("() => window.__road.pursuit()")
        pat = pg.evaluate("() => window.__road.patrols()")
        # `patrolsWoken` IS A TALLY AND THE COP LIST IS A SNAPSHOT. Counting live
        # cruisers with `from === 'patrol'` read ZERO on a control arm that had
        # plainly engaged one - the heat had gone up by a sighting's worth, and
        # then the cruiser, which tops out at 0.71 of the player's speed, fell
        # behind and was culled before the read. A tally cannot be outrun.
        note(f"patrols woken: {pat['woken']}, still patrolling {pat['patrolling']}, "
             f"wanted level {pur['pts']} points")
        if on_shift:
            check(pat['woken'] == 0, 'a patrol does not engage a car on shift',
                  f"{pat['woken']} woken")
            check(pur['pts'] == 0, 'and a sighting buys it no heat',
                  f"{pur['pts']} points, {pur['heat']} stars")
        else:
            check(pat['woken'] > 0, 'the control IS engaged, so the check can fail',
                  f"{pat['woken']} woken")
            check(pur['pts'] > 0, 'and the control DOES earn heat, so that one can too',
                  f"{pur['pts']} points, {pur['heat']} stars")

        # ---- 1 AND 2: THE TARGET SEARCH, AND WHAT IT BILLS --------------------
        # A CRUISER IS PLACED RATHER THAN WAITED FOR, and that is not a shortcut.
        # Left to the radio, the on-shift arm met NO cruiser at all on one run -
        # and "no cruiser adopted the player" is trivially true when there is no
        # cruiser, which is a check that cannot fail. `placeCop` puts one
        # alongside with `onPlayer` undefined, which is precisely the case the
        # guard has to get right: not a car that already chose somebody, but one
        # that is about to choose.
        pg.evaluate("""() => { const R = window.__road;
            R.setTimed(false);                 /* RLG-125: a parked car runs the clock out */
            R.copsClear();
            R.heatSet(240);                    /* a level the radio and the search both read */
            R.placeCop(-2600, 0.30);           /* just behind, in the next lane */
            /* AND AT A SPEED A CRUISER CAN HOLD. A patrol car tops out at 142mph
               against the player's 200 (`copTop`), so a harness holding 0.92 of
               top speed leaves every staged cruiser behind and culls it - which
               read as "no cruiser adopted the player" on an arm that had nothing
               left to be adopted by. Half throttle keeps it in the frame. */
            R.holdSpd(R.MAX_SPD * 0.50); }""")
        pg.wait_for_timeout(12000)
        pur = pg.evaluate("() => window.__road.pursuit()")
        cen = pg.evaluate("() => window.__road.copCensus()")
        note(f"{cen['chasers']} cruiser(s) on the road, {pur['onYou']} of them ADOPTED the player")
        note(f"wanted level {pur['pts']} points from a staged 240")
        check(cen['chasers'] > 0, 'there was a cruiser to be adopted by at all',
              f"{cen['chasers']} on the road")
        if on_shift:
            check(pur['onYou'] == 0, 'no cruiser adopts a player on shift',
                  f"{pur['onYou']} of {cen['chasers']}")
            # RLG-170 bills two points a mile WHILE PURSUED, so a shift that is
            # not pursued cannot be billed - and `addHeat` refuses anyway. The
            # staged 240 may DECAY; what it must never do is climb.
            check(pur['pts'] <= 240, 'and nothing bills the wanted level up',
                  f"{pur['pts']} points from 240")
        else:
            check(pur['onYou'] > 0, 'the control IS adopted, so the check can fail',
                  f"{pur['onYou']} of {cen['chasers']}")
            check(pur['pts'] > 240, 'and the control IS billed, so that check can fail too',
                  f"{pur['pts']} points from 240")

        # ---- 3: THE BUST ------------------------------------------------------
        # Stop the car with cruisers alongside. Off shift this is the three-second
        # arrest; on shift it must be a police car parked next to its own side.
        # STOP FIRST, THEN PLACE THE CRUISER. Coming down from speed takes time,
        # and the three-second count only runs while the car is under a tenth of
        # top speed - so a cruiser placed at the moment the brake went on spent
        # most of its window waiting for the car to slow, and the arrest landed
        # outside it. Placed once the car is already stopped, the rule gets the
        # whole window instead of what is left of it.
        pg.evaluate("() => window.__road.holdSpd(0)")
        pg.wait_for_timeout(3000)
        pg.evaluate("() => window.__road.placeCop(0, 0.30)")
        pg.wait_for_timeout(7000)
        # `state` is a property getter on the engine handle, not a call.
        st = pg.evaluate("() => ({ state: window.__road.state,"
                         "          last: window.__road.lastWreck() })")
        note(f"after seven seconds stopped: state={st['state']} last={st['last']}")
        if on_shift:
            check(st['last'] != 'BUSTED', 'a car on shift is not arrested for stopping',
                  f"last wreck: {st['last']}")
        else:
            check(st['last'] == 'BUSTED', 'the control IS arrested, so the check can fail',
                  f"last wreck: {st['last']}")

        check(errs == [], 'and the arm raised no page error', errs[0][:90] if errs else '')

print(f"\n  {'all checks passed' if not bad[0] else str(bad[0]) + ' FAILURES'}")
sys.exit(1 if bad[0] else 0)
