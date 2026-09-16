#!/usr/bin/env python3
"""TOUR SAVE - a lost round offers retries, and a quit tournament waits per class.

    .venv/Scripts/python tools/tour-save-test.py
    .venv/Scripts/python tools/tour-save-test.py --selftest

RLG-268. Owner, 2026-09-16: "When you run out of time or get busted, the options should be retry from
that race or quit the tournament. And if you quit the tournament, the state of the tournament is
saved for that class of vehicle... Quitting a single race is not persistent."

▶ WHAT WAS THERE BEFORE, AND WHY THE FIRST CHECK BELOW IS THE IMPORTANT ONE. `wreck()` and the OUT OF
TIME branch both call `showEnd` directly, and `showEnd` had no tournament awareness at all - so
losing a round drew the ORDINARY end card (RUN IT AGAIN / CHANGE CAR / MAIN MENU) while `tourRound`
and `tourPts` sat untouched behind it. The tournament was neither ended nor acknowledged. A check
that only asked "is there a retry button" would pass the moment one was added anywhere; this asks the
run to actually end in a tournament and reads which card came up.

▶ AND IT DRIVES THE REAL BUTTONS. The tournament is reached the way a player reaches it - a car in
the garage, MODE pressed until it reads TOURNAMENT, DRIVE - and left the way a player leaves it.
`API.tourState` is read for the numbers, never for the navigation, because a check that sets the
state it then asserts agrees with itself and proves nothing (RLG-065).

  RETRY OFFERED    lose a round on the clock and the card is the tournament's, with a retry on it.
  RETRY SPENDS ONE and re-runs the SAME round, with the standings untouched.
  QUIT SAVES       quitting writes the ladder under its class, and it is still there after a reload.
  CLASS IS THE KEY a supercar shows the super ladder, not the sports one.
  SINGLE RACE      quitting one saves nothing.
  OUT OF RETRIES   the last attempt ends the tournament and clears the save.

`--selftest` puts the old behaviour back - it forces the tournament flag off at the moment the run
ends, which is exactly a `showEnd` with no tournament branch - and asserts this file reports it.

Exit code 0 if every check passed, 1 otherwise.
"""
import argparse
import functools
import http.server
import socketserver
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
from harness import console_utf8, launch_chromium, boot, reboot, until  # noqa: E402


class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


class Stuck(RuntimeError):
    """a button the walk needs is not on the screen - the arm never happened"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default=str(TOOLS.parent))
    ap.add_argument('--selftest', action='store_true',
                    help='drop the tournament flag as the run ends, the way the old build did')
    args = ap.parse_args()
    console_utf8()
    root = Path(args.root)
    fails = []

    def ok(c, label, detail=''):
        print(('  ok    ' if c else '  FAIL  ') + label + ('' if c else '   [' + str(detail) + ']'))
        if not c:
            fails.append(label)

    httpd = socketserver.TCPServer(('127.0.0.1', 0), functools.partial(Q, directory=str(root)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.socket.getsockname()[1]
    print('tour-save  .  a lost round retries, and a quit tournament waits per class')
    print('      serving %s' % root)
    with sync_playwright() as p:
        b = launch_chromium(p, headless=True, args=['--mute-audio'])
        pg = b.new_context(viewport={'width': 480, 'height': 900}).new_page()
        errs = []
        pg.on('pageerror', lambda e: errs.append(str(e)))
        url = 'http://127.0.0.1:%d/games/sw/interstate.html' % port
        boot(pg, url)
        # every class open, so a supercar can be selected without winning one first
        pg.evaluate("""() => window.Arcade.save.merge('interstate-opts',
                       { sports:true, super:true, cruiser:true })""")
        reboot(pg)

        def screen():
            return pg.evaluate("""() => {
              const el = document.getElementById('veil');
              if(!el) return 'no veil';
              if(el.classList.contains('hidden')) return 'veil hidden - a run is on screen';
              const a = [...el.querySelectorAll('[data-act]')].map(x => x.dataset.act);
              return 'veil offers ' + (a.join(', ') || 'nothing');
            }""")

        def has(act):
            return bool(pg.query_selector('#veil:not(.hidden) [data-act="%s"]' % act))

        def tap(act, wait=300):
            if not has(act):
                raise Stuck('no %s button - %s' % (act.upper(), screen()))
            pg.click('#veil:not(.hidden) [data-act="%s"]' % act)
            pg.wait_for_timeout(wait)

        def to_garage():
            # THE DOORS ARE DIFFERENT ON EVERY CARD and the walk has to read the screen rather
            # than assume one: the ordinary end card offers CHANGE CAR, the tournament card
            # offers only its way out, and the title offers PLAY. `garage` is tried first
            # because it is the shortest way in from wherever we are.
            for _ in range(10):
                if has('drive') or has('next'):
                    return
                if has('garage'):
                    tap('garage', 500)
                    continue
                if has('play'):
                    tap('play', 500)
                    continue
                if has('quit'):
                    tap('quit', 500)
                    continue
                pg.wait_for_timeout(350)
            raise Stuck('never reached the garage - %s' % screen())

        def pick(body):
            """walk the garage arrows to a named car, the way a thumb does"""
            to_garage()
            for _ in range(24):
                if pg.evaluate('() => window.__road.body()') == body:
                    return
                tap('next', 150)
            raise Stuck('never reached %s in the garage' % body)

        def set_mode(want):
            """press MODE until the button says what we want"""
            for _ in range(5):
                label = pg.evaluate("""() => { const b =
                    document.querySelector('#veil:not(.hidden) [data-act="mode"]');
                    return b ? b.textContent.trim() : ''; }""")
                if label.endswith(want):
                    return label
                tap('mode', 200)
            raise Stuck('MODE never reached %s - %s' % (want, screen()))

        def state():
            return pg.evaluate('() => window.__road.tourState()')

        def lose_the_round():
            """drive, then run the clock out - the losing exit the ruling is about.

            BOTH HALVES ARE NEEDED: `setClock` does nothing on a run that does not count seconds
            (RLG-125), and an empty clock is not the end either - the engine waits for the car to
            come to REST as well, so a car left rolling sits on an expired clock forever.
            """
            # RETRY STARTS THE RUN ITSELF, so this is reached both from a garage with a DRIVE
            # button on it and from a car that is already moving. Tapping DRIVE unconditionally
            # failed the second time round with "no DRIVE button - a run is on screen", which is
            # the harness describing its own assumption rather than a defect.
            if has('drive'):
                tap('drive', 1800)
            until(pg, '() => window.__road.startLine().left <= 0', timeout=12000)
            if args.selftest:
                # THE DEFECT, PUT BACK: a run that ends with the tournament flag already down is
                # exactly what `showEnd` saw before it had a tournament branch.
                pg.evaluate('() => { window.__road.tourOff && window.__road.tourOff(); }')
            pg.evaluate('() => { window.__road.setTimed(true); window.__road.setClock(0.2); }')
            for _ in range(70):
                pg.evaluate('() => window.__road.setSpd(0)')
                if pg.evaluate("""() => { const el = document.getElementById('veil');
                    return !!el && !el.classList.contains('hidden')
                           && !!el.querySelector('[data-act]'); }"""):
                    pg.wait_for_timeout(400)
                    return
                pg.wait_for_timeout(250)
            raise Stuck('the run never ended on the clock - %s' % screen())

        try:
            # ---- RETRY IS OFFERED --------------------------------------------------------
            pick('ROADSTER')
            set_mode('TOURNAMENT')
            before = state()
            lose_the_round()
            card = pg.evaluate("""() => [...document.querySelectorAll(
                '#veil:not(.hidden) [data-act]')].map(x => x.dataset.act).join(',')""")
            st = state()
            print('      LOST A ROUND    card offers [%s], retries %s of %s, round %s'
                  % (card, st['retries'], st['max'], st['round']))
            ok(has('again') and has('quit'),
               'losing a tournament round offers a retry and a way out', 'card offers ' + card)
            ok(not has('garage'), 'and it is the tournament card, not the ordinary end card',
               'card offers ' + card)
            ok(st['retries'] == before['retries'],
               'the attempt is not spent by losing, only by pressing retry',
               '%s -> %s' % (before['retries'], st['retries']))

            # ---- RETRY SPENDS ONE AND RE-RUNS THE SAME ROUND -----------------------------
            was = state()
            tap('again', 2500)
            now = state()
            print('      RETRY           retries %s -> %s, round %s -> %s, points %s -> %s'
                  % (was['retries'], now['retries'], was['round'], now['round'],
                     was['pts'], now['pts']))
            ok(now['retries'] == was['retries'] - 1, 'pressing retry spends one attempt',
               '%s -> %s' % (was['retries'], now['retries']))
            ok(now['round'] == was['round'], 'and re-runs the SAME round',
               '%s -> %s' % (was['round'], now['round']))
            ok(now['pts'] == was['pts'], 'and the round that was lost scored nobody',
               '%s -> %s' % (was['pts'], now['pts']))

            # ---- QUITTING SAVES IT, UNDER ITS CLASS --------------------------------------
            lose_the_round()
            st = state()
            tap('quit', 900)
            after = state()
            saved = after['saved'].get('sports')
            print('      QUIT            saved rows %s' % list(after['saved'].keys()))
            ok(bool(saved), 'quitting the tournament saves it', 'saved rows %s'
               % list(after['saved'].keys()))
            ok(bool(saved) and saved.get('retries') == st['retries'],
               'and the attempts left are saved with it',
               'saved %s, had %s' % (saved and saved.get('retries'), st['retries']))

            # ---- AND IT SURVIVES A RELOAD ------------------------------------------------
            reboot(pg)
            pick('ROADSTER')
            set_mode('TOURNAMENT')
            back = state()
            print('      AFTER A RELOAD  round %s, points %s, retries %s'
                  % (back['round'], back['pts'], back['retries']))
            ok(back['retries'] == st['retries'] and back['pts'] == st['pts'],
               'and a reload comes back to the ladder where it was left',
               'retries %s pts %s, expected %s / %s'
               % (back['retries'], back['pts'], st['retries'], st['pts']))

            # ---- THE CLASS IS THE KEY ----------------------------------------------------
            # STALLION, not VECTOR. `BODY_CLASS` puts VECTOR, APEX and COMET in `formula`, and a
            # formula car has NO LEAGUE at all (RLG-213) - it is the one class that can never
            # hold a tournament, so picking one here asked the question of the wrong car.
            pick('STALLION')
            set_mode('TOURNAMENT')
            other = state()
            print('      A SUPERCAR      class %s, round %s, points %s, retries %s'
                  % (other['cls'], other['round'], other['pts'], other['retries']))
            ok(other['cls'] == 'super', 'a supercar puts you in the super league', other['cls'])
            ok(other['retries'] == other['max'] and other['pts'] == 0,
               'and gets its OWN tournament, not the sports one',
               'retries %s, points %s' % (other['retries'], other['pts']))

            # and the sports one is still waiting
            pick('ROADSTER')
            set_mode('TOURNAMENT')
            again = state()
            ok(again['pts'] == st['pts'] and again['retries'] == st['retries'],
               'and the sports ladder is still where it was left',
               'pts %s retries %s' % (again['pts'], again['retries']))

            # ---- A SINGLE RACE SAVES NOTHING ---------------------------------------------
            pick('TUNER')
            set_mode('SINGLE RACE')
            lose_the_round()
            single = pg.evaluate("""() => [...document.querySelectorAll(
                '#veil:not(.hidden) [data-act]')].map(x => x.dataset.act).join(',')""")
            print('      SINGLE RACE     card offers [%s]' % single)
            ok('garage' in single, 'losing a single race gives the ordinary end card',
               'card offers ' + single)

            # ---- OUT OF RETRIES ENDS IT ---------------------------------------------------
            to_garage()
            pick('ROADSTER')
            set_mode('TOURNAMENT')
            spent = None
            for _ in range(state()['max'] + 2):
                lose_the_round()
                spent = state()
                if not has('again'):
                    break
                tap('again', 2500)
            print('      OUT OF RETRIES  retries %s, card offers [%s]'
                  % (spent['retries'], pg.evaluate("""() => [...document.querySelectorAll(
                     '#veil:not(.hidden) [data-act]')].map(x => x.dataset.act).join(',')""")))
            ok(spent['retries'] == 0, 'the attempts run out', 'retries %s' % spent['retries'])
            ok(not has('again'), 'and the last one takes the retry button away')
            ok('sports' not in spent['saved'],
               'and running out clears the saved tournament for that class',
               'saved rows %s' % list(spent['saved'].keys()))
        except Stuck as e:
            ok(False, 'the walk completed', str(e))

        ok(not errs, 'no page errors', errs[0][:160] if errs else '')
        b.close()
    httpd.shutdown()
    print()
    if args.selftest:
        if fails:
            print('the old behaviour was put back and this file reported it')
            return 0
        print('SELFTEST FAILED: the tournament branch was disabled and nothing noticed')
        return 1
    if fails:
        print('FAILED: ' + '; '.join(fails))
        return 1
    print('a lost round retries, and a quit tournament waits under its class')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
