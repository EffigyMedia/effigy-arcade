#!/usr/bin/env python3
"""LIVERY TEST - the police on the road share one colour a run, from the regular police colours.

    .venv/Scripts/python tools/livery-test.py

RLG-204. Owner, 2026-09-19: the road police all wear the same paint for a run, drawn from the regular
police colours - "NPC police can use the regular police unlocked paint even before they are unlocked.
Only the player doesn't have access to those until they are unlocked" - and never the iridescent paints.

WHAT IT ASSERTS, over many runs in a fresh save where the player has won no police colour:
  . every run's livery is one of the regular police colours, and none is iridescent;
  . the livery varies between runs, and colours the player has NOT unlocked do appear;
  . the drawn CRUISER changes with the livery - read as a fingerprint of the sprite's pixels, so a
    livery that is chosen and never painted fails here. That was the defect: `copLivery` was chosen
    every run and read by nothing.

WHAT IT CANNOT SEE: whether the colours look right on the road. That is the owner's call on a device.

Exit code 0 if every check passed, 1 otherwise.
"""
import sys, functools, http.server, socketserver, threading
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
INIT = (ROOT / 'tools' / 'collide-test.py').read_text(encoding='utf-8').split('INIT = r"""')[1].split('"""')[0]
from harness import console_utf8, launch_chromium, boot, until
from playwright.sync_api import sync_playwright
console_utf8()

fails = []
IRIDESCENT = {'ORACLE', 'PRISM', 'ABALONE', 'SCARAB', 'EMBER'}
LOCKED_FOR_PLAYER = {'FORCEBLUE', 'FORCEGREEN', 'CHARCOAL', 'SILVER'}


def check(ok, label, detail=''):
    print('  %s  %s%s' % ('ok  ' if ok else 'FAIL', label, '   ' + detail if detail else ''))
    if not ok:
        fails.append(label)


class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


s = socketserver.TCPServer(('127.0.0.1', 0), functools.partial(Q, directory=str(ROOT)))
port = s.server_address[1]
threading.Thread(target=s.serve_forever, daemon=True).start()
print('livery-test  .  the force wears one regular colour a run')
with sync_playwright() as p:
    b = launch_chromium(p, headless=True)
    pg = b.new_page(viewport={'width': 480, 'height': 900})
    pg.add_init_script(INIT)
    boot(pg, f'http://127.0.0.1:{port}/games/sw/interstate.html')
    until(pg, '!!window.__probe.road', timeout=10000)
    pg.click('[data-act="play"]')
    pg.wait_for_selector('#veil:not(.hidden) [data-act="drive"]')
    pg.click('[data-act="drive"]')
    pg.wait_for_timeout(1500)
    rows = []
    for _ in range(30):
        pg.evaluate("() => window.__probe.road.restart()")
        pg.wait_for_timeout(60)
        rows.append(pg.evaluate("() => window.__probe.road.copLivery()"))
    allowed = set(rows[0]['from'])
    seen = [r['livery'] for r in rows]
    prints = {}
    for r in rows:
        prints.setdefault(r['livery'], set()).add(r['print'])
    print('      allowed: %s' % sorted(allowed))
    print('      seen over 30 runs: %s' % {k: seen.count(k) for k in sorted(set(seen))})
    check(set(seen) <= allowed, 'every livery is a regular police colour', '%s' % sorted(set(seen) - allowed))
    check(not (set(seen) & IRIDESCENT) and not (allowed & IRIDESCENT), 'and none is iridescent',
          '%s' % sorted((set(seen) | allowed) & IRIDESCENT))
    check(len(set(seen)) >= 3, 'the livery varies between runs', '%d distinct' % len(set(seen)))
    check(bool(set(seen) & LOCKED_FOR_PLAYER),
          'and colours the player has not unlocked are worn by the force',
          '%s' % sorted(set(seen) & LOCKED_FOR_PLAYER))
    one_print_each = all(len(v) == 1 for v in prints.values())
    distinct_prints = len({next(iter(v)) for v in prints.values()})
    check(one_print_each and distinct_prints == len(prints),
          'and the drawn CRUISER changes with the livery',
          '%d liveries drew %d distinct cars' % (len(prints), distinct_prints))
    errs = pg.evaluate("() => window.__probe.errors")
    check(not errs, 'no page errors', '; '.join(errs[:2]))
    b.close()
print()
print('  %s' % ('all checks passed' if not fails else '%d check(s) FAILED' % len(fails)))
sys.exit(1 if fails else 0)
