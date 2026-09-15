#!/usr/bin/env python3
"""DEBUG UNLOCK - the two debug switches open cars for driving, and write nothing to the save.

    .venv/Scripts/python tools/debug-unlock-test.py
    .venv/Scripts/python tools/debug-unlock-test.py --root <an older checkout> --expect-fail

Owner, 2026-09-15: "the debug toggles we have in our debug menu no longer work".

WHAT WAS FOUND BEFORE THE BUILD. OPTIONS > DEBUG flips `dbgRacers` and `dbgPolice`, and nothing in
the engine read either. `carLocked` decided alone, so a locked car stayed locked with both switches
ON. RLG-249 already recorded that `carLocked` never read the switches.

THE SWITCHES ARE PRESSED, NOT SET. Each cabinet is booted on a fresh save and the real buttons are
tapped from the title: OPTIONS, DEBUG, then the switch. Ownership is asked of
`playableBodies`, which is what the garage's DRIVE button obeys (RLG-223 records why the card name is
the wrong instrument).

  RACERS   with UNLOCK ALL RACERS on, every non-police car in the garage is playable, and a police
           car that was locked is still locked.
  POLICE   with UNLOCK POLICE on as well, every car in the garage is playable.
  DRIVE    the garage on a car that only the switch opened shows DRIVE.
  SAVE     the save's unlock flags are the same after the switches as before them.
  FRESH    a reload turns both switches off again. They are deliberately not saved.

Both driving cabinets are walked, because Motorsport's garage lists fewer cars.

WHAT THIS CANNOT SAY. Whether a car opened this way can finish every event is not checked here.

Exit code 0 if every check passed (or, with --expect-fail, if one failed), 1 otherwise.
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
from harness import console_utf8, launch_chromium, boot, reboot  # noqa: E402

STATE = """(cab) => {
  const R = window.__road;
  const all = R.garageBodies(), own = R.playableBodies();
  const police = all.filter(k => R.BODY && R.BODY[k] && R.BODY[k].force);
  /* the save's own flags, minus the body the garage writes when it is shown */
  const sv = Object.assign({}, window.Arcade.save.get(cab + '-opts') || {});
  delete sv.body;
  return { all, own, police, save: JSON.stringify(sv) };
}"""

ACTS = """() => Array.from(document.querySelectorAll('#veil:not(.hidden) [data-act]')).map(b => b.dataset.act)"""


class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default=str(TOOLS.parent))
    ap.add_argument('--expect-fail', action='store_true')
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
    print('debug-unlock  .  the debug switches open cars, and write nothing to the save')
    print('      serving %s' % root)
    with sync_playwright() as p:
        b = launch_chromium(p, headless=True, args=['--mute-audio'])
        for cab in ('interstate', 'motorsport'):
            print('  -- %s' % cab)
            ctx = b.new_context(viewport={'width': 480, 'height': 900})
            pg = ctx.new_page()
            errs = []
            pg.on('pageerror', lambda e: errs.append(str(e)))
            boot(pg, 'http://127.0.0.1:%d/games/sw/%s.html' % (port, cab))
            pg.wait_for_selector('#veil:not(.hidden) [data-act="opts"]', timeout=10000)

            def tap(act):
                pg.click('#veil:not(.hidden) [data-act="%s"]' % act)
                pg.wait_for_timeout(200)

            before = pg.evaluate(STATE, cab)
            locked = [k for k in before['all'] if k not in before['own']]
            locked_racers = [k for k in locked if k not in before['police']]
            locked_police = [k for k in locked if k in before['police']]
            print('      locked on a fresh save: racers %s, police %s' % (locked_racers, locked_police))
            if not locked_racers:
                ok(False, 'a fresh save has a locked racer to open', 'none locked')
                ctx.close()
                continue

            tap('opts')
            tap('debug')
            tap('dr')
            racers = pg.evaluate(STATE, cab)
            still = [k for k in locked_racers if k not in racers['own']]
            ok(not still, 'UNLOCK ALL RACERS opens every locked racer', 'still locked: %s' % still)
            leaked = [k for k in locked_police if k in racers['own']]
            ok(not leaked, 'and leaves the police cars locked', 'opened: %s' % leaked)

            tap('dp')
            both = pg.evaluate(STATE, cab)
            still = [k for k in both['all'] if k not in both['own']]
            ok(not still, 'UNLOCK POLICE as well opens every car in the garage', 'still locked: %s' % still)
            ok(both['save'] == before['save'], 'and neither switch wrote to the save',
               'before %s, after %s' % (before['save'], both['save']))

            k = locked_racers[-1]
            pg.evaluate('(k) => { const R = window.__road; R.setBody(k); R.showGarage(); }', k)
            pg.wait_for_timeout(200)
            acts = pg.evaluate(ACTS)
            ok('drive' in acts, 'the garage on %s, opened by the switch, offers DRIVE' % k,
               'on screen: %s' % ', '.join(acts))

            reboot(pg)
            pg.wait_for_selector('#veil:not(.hidden) [data-act="opts"]', timeout=10000)
            fresh = pg.evaluate(STATE, cab)
            ok(sorted(fresh['own']) == sorted(before['own']), 'a reload turns both switches off again',
               'playable after reload: %s' % fresh['own'])

            ok(not errs, 'no page errors', errs[0][:120] if errs else '')
            ctx.close()
        b.close()
    httpd.shutdown()
    print()
    if args.expect_fail:
        print('expected at least one failure: %s' % ('got %d' % len(fails) if fails else 'got NONE'))
        return 0 if fails else 1
    if fails:
        print('FAILED: ' + '; '.join(fails))
        return 1
    print('the debug switches open cars, and write nothing to the save')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
