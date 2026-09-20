#!/usr/bin/env python3
"""BOARD TEST - a local leaderboard, one board per mode and one per test-drive state.

    .venv/Scripts/python tools/board-test.py

RLG-292. The owner, 2026-09-19/20: "we should be recording times for everything, like a little local
leaderboard." A test drive scores the DISTANCE DRIVEN and has a board per STATE - the checkpoints
and hot pursuit switches, four states - a single race and a tournament score their TIME, and a drag
race its own. Ten entries a board, three initials tapped in, and the name is asked only when a run
makes the ten.

WHAT IT ASSERTS, driving real runs:
  . the title offers LEADERBOARD, the modes are there, a test drive opens its four states, and an
    empty board says so;
  . a drag race that makes the board asks for initials, and what is entered is what is stored - the
    letters, the car and the race's own time;
  . a test drive writes its distance to the board of the STATE it was driven in, and the same drive
    under a different switch writes a different board;
  . a test drive with NEITHER switch keeps no board at all: it is practice;
  . a run that would not make the ten asks for nothing and ends as it always did.

WHAT IT CANNOT SEE: whether tapping three letters feels right on a phone. The owner's.

Exit code 0 if every check passed, 1 otherwise.
"""
import sys, functools, http.server, socketserver, threading, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
INIT = (ROOT / 'tools' / 'collide-test.py').read_text(encoding='utf-8').split('INIT = r"""')[1].split('"""')[0]
from harness import console_utf8, launch_chromium, boot, until, garage_screen
from playwright.sync_api import sync_playwright
console_utf8()

fails = []


def check(ok, label, detail=''):
    print('  %s  %s%s' % ('ok  ' if ok else 'FAIL', label, '   ' + detail if detail else ''))
    if not ok:
        fails.append(label)


class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


DRIVER = """(manual) => {
  const R = window.__probe.road;
  if (window.__bd) cancelAnimationFrame(window.__bd);
  const tick = () => {
    R.gas(true);
    if (manual) { const g = R.gate().gear; if (g === 0) R.putGear(1); else if (R.shiftDue()) R.putGear(g + 1); }
    window.__bd = requestAnimationFrame(tick);
  };
  window.__bd = requestAnimationFrame(tick);
}"""


def veil_text(pg):
    return pg.evaluate("() => { const v = document.querySelector('#veil:not(.hidden)');"
                       " return v ? v.innerText : ''; }")


def acts(pg):
    return pg.evaluate("() => [...document.querySelectorAll('#veil:not(.hidden) [data-act]')]"
                       ".map(b => b.dataset.act)")


def tap(pg, act, wait=250):
    pg.click('#veil [data-act="%s"]' % act)
    pg.wait_for_timeout(wait)


def wait_act(pg, act, limit_s):
    t0 = time.time()
    while time.time() - t0 < limit_s:
        if pg.query_selector('#veil:not(.hidden) [data-act="%s"]' % act):
            return True
        pg.wait_for_timeout(400)
    return False


def set_mode(pg, body, want):
    pg.evaluate("(k) => { const R = window.__probe.road; R.setBody(k); R.showGarage(); }", body)
    pg.wait_for_timeout(250)
    garage_screen(pg, 'main')
    for _ in range(6):
        lab = pg.evaluate("() => (document.querySelector('#veil [data-act=\"mode\"] b') || {}).textContent")
        if (lab or '').strip() == want:
            return True
        tap(pg, 'mode', 140)
    return False


def switches(pg, timed, pursuit):
    """Put the two test-drive switches where they are wanted, on the SETTINGS screen."""
    garage_screen(pg, 'settings')
    for act, want in (('timed', 'ON' if timed else 'OFF'), ('chase', 'ON' if pursuit else 'OFF')):
        for _ in range(3):
            lab = pg.evaluate("(a) => { const b = document.querySelector('#veil [data-act=\"' + a + '\"] b');"
                              " return b ? b.textContent.trim() : null; }", act)
            if lab is None or lab == want:
                break
            tap(pg, act, 140)
    garage_screen(pg, 'main')


s = socketserver.TCPServer(('127.0.0.1', 0), functools.partial(Q, directory=str(ROOT)))
port = s.server_address[1]
threading.Thread(target=s.serve_forever, daemon=True).start()
print('board-test  .  a board per mode, and one per test-drive state')
with sync_playwright() as p:
    b = launch_chromium(p, headless=True, args=['--mute-audio'])
    pg = b.new_page(viewport={'width': 480, 'height': 900})
    pg.add_init_script(INIT)
    boot(pg, f'http://127.0.0.1:{port}/games/sw/interstate.html')
    until(pg, '!!window.__probe.road', timeout=10000)

    # ---- THE SCREENS ---------------------------------------------------------------------
    print('  the screens')
    check('board' in acts(pg), 'the title offers LEADERBOARD', ', '.join(acts(pg)))
    tap(pg, 'board')
    modes = [a for a in acts(pg) if a.startswith('m:')]
    print('      modes: %s' % ', '.join(modes))
    check(sorted(modes) == ['m:drag', 'm:drive', 'm:race', 'm:tour'],
          'and every mode has a board', repr(modes))
    tap(pg, 'm:drive')
    states = [a for a in acts(pg) if a.startswith('s:')]
    # THREE, NOT FOUR (owner, 2026-09-20): a test drive with neither switch is practice,
    # it is effectively infinite, and with the checkpoints off it has no clock to end it.
    check(sorted(states) == ['s:cp', 's:cp+hp', 's:hp'],
          'a test drive opens its three scored states, and practice is not one', repr(states))
    tap(pg, 's:cp')
    check('NOTHING ON THIS BOARD YET' in veil_text(pg), 'and an empty board says so',
          veil_text(pg).replace('\n', ' / ')[:90])
    tap(pg, 'back'); tap(pg, 'back'); tap(pg, 'back')
    check('PLAY' in veil_text(pg), 'and BACK walks out to the title', veil_text(pg).replace('\n', ' / ')[:60])

    # ---- A DRAG RACE ON THE BOARD --------------------------------------------------------
    print('  a drag race')
    tap(pg, 'play')
    check(set_mode(pg, 'HATCH', 'DRAG RACE'), 'DRAG RACE is chosen')
    tap(pg, 'drive', 400)
    pg.evaluate(DRIVER, True)
    check(wait_act(pg, 'ok', 240), 'the race ends by asking for initials, so it made the board')
    head = veil_text(pg)
    tap(pg, 'up0'); tap(pg, 'up0')          # A -> C on the first letter
    tap(pg, 'down2')                        # A -> the last letter on the third
    shown = pg.evaluate("() => window.__probe.road.boards().name")
    tap(pg, 'ok', 500)
    rows = pg.evaluate("() => (window.__probe.road.boards().all || {})['drag'] || []")
    t = pg.evaluate("() => window.__probe.road.drag().result") or {}
    print('      entered %r, stored %s' % (shown, rows[:1]))
    check(len(rows) == 1 and rows[0]['n'] == shown, 'the letters entered are the letters stored',
          '%r against %r' % (rows[0].get('n') if rows else None, shown))
    check(rows and rows[0]['car'] == 'HATCH' and abs(rows[0]['v'] - (t.get('mine') or 0)) < 0.01,
          'with the car and the time the race was run in',
          '%s in %s' % (rows[0].get('v') if rows else None, t.get('mine')))
    check('1ST' in head, 'and it was announced as first on the board', head.replace('\n', ' / ')[:60])
    check('DRAG RACE' in veil_text(pg) and shown.strip() in veil_text(pg),
          'and the board is shown with the new row on it', veil_text(pg).replace('\n', ' / ')[:110])
    tap(pg, 'back', 400)

    # ---- A TEST DRIVE, AND ITS STATE -----------------------------------------------------
    # The clock is cut to a couple of seconds so a run ends without driving twelve miles.
    print('  a test drive, on the board of the state it was driven in')
    seen = {}
    for timed, pursuit, key in ((True, False, 'drive:cp'), (True, True, 'drive:cp+hp')):
        pg.evaluate("() => { const R = window.__probe.road; R.showGarage(); }")
        pg.wait_for_timeout(250)
        check(set_mode(pg, 'HATCH', 'TEST DRIVE'), 'TEST DRIVE is chosen')
        switches(pg, timed, pursuit)
        tap(pg, 'drive', 500)
        pg.evaluate(DRIVER, False)
        pg.wait_for_timeout(2500)
        pg.evaluate("() => window.__probe.road.setClock(1.5)")
        asked = wait_act(pg, 'ok', 60)
        if not asked:
            txt = veil_text(pg).replace(chr(10), ' / ')[:120]
            st = pg.evaluate("() => window.__probe.road.boards().state")
            dg = pg.evaluate("() => { const d = window.__probe.road.drag(); return [d.on, d.finished, d.clock]; }")
            print('      no initials: screen %r; state %s; [dragOn, finished, clock] %s' % (txt, st, dg))
        check(asked, 'the run ends by asking for initials (%s)' % key)
        if asked:
            tap(pg, 'ok', 500)
        rows = pg.evaluate("(k) => (window.__probe.road.boards().all || {})[k] || []", key)
        seen[key] = rows
        print('      %-12s %s' % (key, rows[:1]))
        check(len(rows) == 1 and rows[0]['v'] > 0, 'the distance is on the %s board' % key,
              repr(rows[:1]))
        tap(pg, 'back', 400)
        if 'again' in acts(pg) or 'garage' in acts(pg):
            tap(pg, 'garage', 400)
    check(list(seen) == ['drive:cp', 'drive:cp+hp'] and all(len(v) == 1 for v in seen.values()),
          'and the two states kept two boards, not one',
          ', '.join('%s %d' % (k, len(v)) for k, v in seen.items()))

    # ---- AND A RUN THAT DOES NOT MAKE THE TEN ASKS FOR NOTHING ---------------------------
    print('  a run that does not place')
    # ON THE BOARD OF A STATE THAT HAS A CLOCK. The first version of this drove with both
    # switches off, and a test drive with the checkpoints off HAS NO CLOCK to run out - so
    # cutting the clock ended nothing and the run drove on until the harness gave up. The
    # state is what decides the board here, not the difficulty, so it uses the timed one.
    pg.evaluate("""() => { const A = window.Arcade, k = 'interstate-board';
        const all = A.save.get(k) || {};
        all['drive:cp'] = Array.from({length: 10}, (_, i) => ({ n:'AAA', car:'HATCH', v: 500 - i }));
        A.save.set(k, all); }""")
    pg.evaluate("() => { const R = window.__probe.road; R.showGarage(); }")
    pg.wait_for_timeout(250)
    set_mode(pg, 'HATCH', 'TEST DRIVE')
    switches(pg, True, False)
    tap(pg, 'drive', 500)
    pg.evaluate(DRIVER, False)
    pg.wait_for_timeout(2500)
    pg.evaluate("() => window.__probe.road.setClock(1.5)")
    ended = wait_act(pg, 'again', 60)
    check(ended and not pg.query_selector('#veil [data-act="ok"]'),
          'it ends on its own card and asks for no initials', veil_text(pg).replace('\n', ' / ')[:80])
    rows = pg.evaluate("() => (window.__probe.road.boards().all || {})['drive:cp'] || []")
    check(len(rows) == 10 and all(r['n'] == 'AAA' for r in rows), 'and the board is untouched',
          '%d rows' % len(rows))

    # ---- AND PRACTICE KEEPS NO BOARD (owner, 2026-09-20) --------------------------------
    print('  practice')
    pg.evaluate("() => { const R = window.__probe.road; R.showGarage(); }")
    pg.wait_for_timeout(250)
    set_mode(pg, 'HATCH', 'TEST DRIVE')
    switches(pg, False, False)
    off = pg.evaluate("() => window.__probe.road.boards()")
    switches(pg, True, False)
    on = pg.evaluate("() => window.__probe.road.boards()")
    print('      neither switch: state %r keeps %s; checkpoints on: state %r keeps %s'
          % (off['state'], off['keeps'], on['state'], on['keeps']))
    check(off['state'] == 'none' and off['keeps'] is False,
          'with neither switch a test drive is scored by nothing', repr(off['state']))
    check(on['keeps'] is True, 'and with a switch on it is scored again', repr(on['state']))

    errs = pg.evaluate("() => window.__probe.errors")
    check(not errs, 'no page errors', '; '.join(errs[:2]))
    b.close()
print()
print('  %s' % ('all checks passed' if not fails else '%d check(s) FAILED' % len(fails)))
sys.exit(1 if fails else 0)
