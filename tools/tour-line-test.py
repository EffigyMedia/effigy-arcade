#!/usr/bin/env python3
"""TOUR LINE TEST - a tournament won on the last of the clock has one ending, and stays won.

    .venv/Scripts/python tools/tour-line-test.py
    .venv/Scripts/python tools/tour-line-test.py --falsify clock
    .venv/Scripts/python tools/tour-line-test.py --falsify save

RLG-322, owner 2026-09-21: "I just finished a tournament while coasting out of time. I got the
initials entry screen, which was quickly covered up by the victory screen, which was quickly
covered up by the you lost out of time screen. Looks like I did unlock the sports cars but the
tournament is not considered finished because I chose save and quit."

IT PLAYS THE OWNER'S PATH. Three rounds are raced; after the third the player takes QUIT & SAVE,
so a row for the ladder is on disk exactly as it would be for anyone who stopped mid-tournament;
the ladder is resumed from the garage; and the fourth round is crossed with the clock at zero and
the car still rolling, so it coasts to a stop after the line.

  1. THE LAST ROUND WAS REACHED from the saved ladder. Without it nothing below means anything.
  2. ONE ENDING. For eight seconds after the line, every screen that opens is recorded, and OUT OF
     TIME is never one of them.
  3. THE LADDER IS DONE AT THE LINE. By the time the first screen after the line opens - the
     earliest a player can act - the ladder in memory is marked done and its row is gone.
  4. AND IT STAYS DONE IF THE PLAYER LEAVES. The page is reloaded with the initials entry still up,
     which is closing the app, and the saved row is still gone.

`--falsify clock` puts back the out-of-time test that ignored the finish: 2 must fail.
`--falsify save` puts back the ladder retired only by the trophy screen: 3 and 4 must fail.

Exit code 0 if every check passed, 1 otherwise.
"""
import argparse
import functools
import http.server
import importlib.util
import socketserver
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from harness import console_utf8, launch_chromium, boot   # noqa: E402
from playwright.sync_api import sync_playwright            # noqa: E402

GAME = 'games/sw/interstate.html'
VEIL = '#veil:not(.hidden) '
FALSIFY = {
    'clock': [("state === 'driving' && !raceEnded()){", "state === 'driving'){")],
    'save': [("        tourDone = true;\n        tourClear(tourClass || classOf(optBody));\n"
              "        setTimeout(() => { const total = tourT;",
              "        setTimeout(() => { const total = tourT;")],
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--falsify', choices=sorted(FALSIFY))
    args = ap.parse_args()
    console_utf8()

    spec = importlib.util.spec_from_file_location('dt', ROOT / 'tools' / 'drive-test.py')
    dt = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dt)

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
    srv = socketserver.TCPServer(('127.0.0.1', 0), handler)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    bad = 0

    def ok(cond, label, detail=''):
        nonlocal bad
        if not cond:
            bad += 1
        print('  %s  %s%s' % ('ok  ' if cond else 'FAIL', label,
                              ('   ' + detail) if detail else ''))

    print('tour-line-test  .  a tournament won on the last of the clock has one ending')
    if args.falsify:
        print('  FALSIFY %s' % args.falsify)
    try:
        with sync_playwright() as p:
            b = launch_chromium(p, headless=True, args=['--mute-audio'])
            ctx = b.new_context(viewport={'width': 480, 'height': 900})
            ctx.add_init_script(dt.INIT)
            if args.falsify:
                src = (ROOT / 'road.js').read_text(encoding='utf-8')
                for need, cut in FALSIFY[args.falsify]:
                    if src.count(need) != 1:
                        raise SystemExit('[tour-line-test] --falsify cannot find: ' + need[:60])
                    src = src.replace(need, cut, 1)
                ctx.route('**/road.js', lambda route: route.fulfill(
                    status=200, content_type='application/javascript', body=src))
            pg = ctx.new_page()
            errs = []
            pg.on('pageerror', lambda e: errs.append(str(e)))

            def to_garage():
                pg.wait_for_selector(VEIL + '[data-act="play"]', timeout=10000)
                pg.click(VEIL + '[data-act="play"]')
                pg.wait_for_timeout(400)

            def tournament():
                for _ in range(4):
                    if 'TOURNAMENT' in pg.inner_text(VEIL + '[data-act="mode"]'):
                        return True
                    pg.click(VEIL + '[data-act="mode"]')
                    pg.wait_for_timeout(200)
                return 'TOURNAMENT' in pg.inner_text(VEIL + '[data-act="mode"]')

            def wait_round(ms=8000):
                spent = 0
                while spent < ms:
                    if pg.locator(VEIL + '[data-act="next"]').count():
                        return True
                    pg.wait_for_timeout(120)
                    spent += 120
                return False

            boot(pg, 'http://127.0.0.1:%d/%s' % (port, GAME))
            pg.wait_for_timeout(1600)
            to_garage()
            ok(tournament(), 'the garage is set to TOURNAMENT')
            pg.click(VEIL + '[data-act="drive"]')
            pg.wait_for_timeout(1800)

            # ---- three rounds, then QUIT & SAVE ------------------------------------
            for r in range(3):
                pg.evaluate("() => window.__road.parkFinish(400)")
                if not wait_round():
                    ok(False, 'round %d ended on the round screen' % (r + 1))
                    b.close()
                    return 1
                if r < 2:
                    pg.click(VEIL + '[data-act="next"]')
                    pg.wait_for_timeout(1800)
            pg.click(VEIL + '[data-act="quit"]')
            pg.wait_for_timeout(800)
            saved = pg.evaluate("() => window.__road.tourState().saved")
            print('      after QUIT & SAVE the save holds: %s' % sorted(saved))

            # ---- and back in, to the last round -------------------------------------
            to_garage()
            tournament()
            pg.click(VEIL + '[data-act="drive"]')
            pg.wait_for_timeout(1800)
            st = pg.evaluate("() => window.__road.tourState()")
            last = st['round'] == st['rounds'] - 1
            ok(last and st['cls'] in saved, '1. the saved ladder resumed at its last round',
               'round %d of %d, saved rows %s' % (st['round'] + 1, st['rounds'], sorted(saved)))
            cls = st['cls']

            # ---- across the line on an empty clock, still rolling -------------------
            pg.evaluate("""() => { const R = window.__road;
                R.holdSpd(null); R.setClock(0); R.setSpd(R.MAX_SPD * 0.25);
                R.parkFinish(400); }""")
            seen = []
            done_at_line = None
            for i in range(66):
                pg.wait_for_timeout(120)
                txt = pg.evaluate("() => { const v = document.getElementById('veil');"
                                  " return v && !v.classList.contains('hidden')"
                                  " ? v.innerText.replace(/\\s+/g, ' ').slice(0, 60) : ''; }")
                if txt and (not seen or seen[-1] != txt):
                    seen.append(txt)
                # the first screen after the line is the earliest a player can act
                if seen and done_at_line is None:
                    done_at_line = pg.evaluate("() => window.__road.tourState()")
            for t in seen:
                print('      screen: %s' % t)
            # the ending this guards against needs the car AT REST; a window that closed
            # while it still rolled would pass without asking anything (RVW, UNT-415)
            rest = pg.evaluate("() => window.__road.motion().spd < window.__road.MAX_SPD * 0.004")
            ok(rest, 'the car came to rest after the line, so the clock ending was due')
            ok(seen and not any('OUT OF TIME' in t for t in seen),
               '2. one ending: OUT OF TIME never opens after the line',
               '%d screen(s) seen' % len(seen))
            ok(done_at_line and done_at_line['done'] and cls not in done_at_line['saved'],
               '3. the ladder is done by the first screen after the line, and its row is gone',
               'done=%s saved=%s' % (done_at_line and done_at_line['done'],
                                     done_at_line and sorted(done_at_line['saved'])))

            # ---- and the player leaves without answering anything ---------------------
            pg.reload()
            pg.wait_for_timeout(2000)
            after = pg.evaluate("() => window.__road.tourState().saved")
            ok(cls not in after, '4. leaving the app there leaves no unfinished ladder behind',
               'saved rows after reload: %s' % sorted(after))
            if errs:
                ok(False, 'page errors', errs[0][:140])
            b.close()
    finally:
        srv.shutdown()

    print()
    print('  %s' % ('all checks passed' if not bad else '%d check(s) FAILED' % bad))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
