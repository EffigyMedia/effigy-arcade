#!/usr/bin/env python3
"""RENAME TEST - a save that names a car by its old key still opens that car.

    .venv/Scripts/python tools/rename-test.py

RLG-197. The chosen car is persisted BY KEY, so renaming a body silently takes the car away from
anybody driving it: the lookup misses, the fallback runs, and somebody's car is quietly replaced.
There are two such renames so far - FORMULA became APEX when the one formula car became three, and
LORRY became SEMI on 2026-09-09 - and both are one line in the same table.

WHY IT IS A HARNESS AND NOT A READ-THROUGH. A migration is dead code on every run except the one
that needs it, and the save it repairs may not be opened for a year. Nothing else in the suite would
notice if it were deleted, mistyped, or moved above the line that overwrites it.

THE CHECK CANNOT PASS VACUOUSLY. It writes the OLD key into the save, reloads, and asks the engine
which car it is in. A migration that did nothing would answer ROADSTER - the fallback - and a
migration that ran on the wrong key would answer with the wrong car, so the assertion names the car
it expects rather than merely requiring a change.

Exit code 0 if every check passed, 1 otherwise.
"""
import argparse
import functools
import http.server
import socketserver
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from harness import console_utf8, launch_chromium
from playwright.sync_api import sync_playwright

GAME = 'games/sw/interstate.html'
# the old key in a save, and the car it must open today
RENAMED = [('LORRY', 'SEMI'), ('FORMULA', 'APEX')]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--headed', action='store_true')
    args = ap.parse_args()
    console_utf8()

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
    srv = socketserver.TCPServer(('127.0.0.1', 0), handler)
    base = 'http://127.0.0.1:%d' % srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    bad = 0

    def ok(cond, label, detail=''):
        nonlocal bad
        if not cond:
            bad += 1
        print('  %s  %s%s' % ('ok  ' if cond else 'FAIL', label,
                              ('   ' + detail) if detail else ''))

    print('rename-test  .  an old key in a save still opens the car it named')
    with sync_playwright() as p:
        b = launch_chromium(p, headless=not args.headed,
                            args=['--mute-audio', '--autoplay-policy=no-user-gesture-required'])
        ctx = b.new_context(viewport={'width': 480, 'height': 900})
        page = ctx.new_page()
        errs = []
        page.on('pageerror', lambda e: errs.append(str(e)))
        page.goto('%s/%s' % (base, GAME), wait_until='load')
        page.wait_for_timeout(600)

        for old, want in RENAMED:
            # every class open, so the answer is about the migration and not about a lock
            page.evaluate("""(k) => {
                window.Arcade.save.merge('interstate-opts', {
                    body:k, production:true, utility:true, super:true, formula:true });
            }""", old)
            page.reload(wait_until='load')
            page.wait_for_timeout(600)
            got = page.evaluate('() => window.__road.bodyKey()')
            ok(got == want,
               'a save holding %s opens %s' % (old, want),
               'opened %s' % got)

        ok(not errs, 'the run was clean', '; '.join(errs[:2]))
        ctx.close()
        b.close()

    print('  %s' % ('all checks passed' if not bad else '%d check(s) failed' % bad))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
