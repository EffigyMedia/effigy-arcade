#!/usr/bin/env python3
"""GARAGE ORDER - the arrows walk the garage class by class, from HATCH.

    .venv/Scripts/python tools/garage-order-test.py
    .venv/Scripts/python tools/garage-order-test.py --root <an older checkout> --expect-fail

RLG-250. Owner, 2026-09-15: the garage starts at production and the right arrow goes through the
production cars, then the sports cars, then the supercars, then the formula cars, and "The cruiser and
interceptor should be shown at the end of their group". Production is HATCH, COUPE, SALOON, and "A new
save opens on hatch."

WHAT IT DRIVES. A fresh save, the real PLAY button, and the real right arrow, reading which car the
engine holds after each press. Locked cars are in the walk too, because the garage lists them as
silhouettes, and the owner's lineup is the order the player sees whether or not a car is owned.

  Interstate   opens on HATCH and walks the 14-car lineup, then wraps back to HATCH.
  Motorsport   lists no police car, so it walks the same lineup without CRUISER and SUPERCRUISER.

`--root` serves another checkout; `--expect-fail` exits 0 only if a check failed, which is what a run
against the commit before the build must show.

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
from harness import console_utf8, launch_chromium, boot  # noqa: E402

LINEUP = ['HATCH', 'COUPE', 'SALOON',
          'ROADSTER', 'TUNER', 'MUSCLE', 'CRUISER',
          'STALLION', 'MATADOR', 'CREST', 'SUPERCRUISER',
          'VECTOR', 'APEX', 'COMET']
POLICE = {'CRUISER', 'SUPERCRUISER'}


class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default=str(TOOLS.parent))
    ap.add_argument('--expect-fail', action='store_true')
    args = ap.parse_args()
    console_utf8()
    fails = []

    def ok(c, label, detail=''):
        print(('  ok    ' if c else '  FAIL  ') + label + ('' if c else '   [' + str(detail) + ']'))
        if not c:
            fails.append(label)

    httpd = socketserver.TCPServer(('127.0.0.1', 0),
                                   functools.partial(Q, directory=str(Path(args.root))))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.socket.getsockname()[1]
    print('garage-order  .  the arrows walk the garage class by class, from HATCH')
    with sync_playwright() as p:
        b = launch_chromium(p, headless=True, args=['--mute-audio'])
        for gid, want in [('interstate', LINEUP),
                          ('motorsport', [k for k in LINEUP if k not in POLICE])]:
            pg = b.new_context(viewport={'width': 480, 'height': 900}).new_page()
            errs = []
            pg.on('pageerror', lambda e: errs.append(str(e)))
            boot(pg, 'http://127.0.0.1:%d/games/sw/%s.html' % (port, gid))
            pg.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
            pg.click('[data-act="play"]')
            pg.wait_for_selector('#veil:not(.hidden) [data-act="next"]', timeout=5000)
            car = lambda: pg.evaluate('() => window.__road.body()')
            walk = [car()]
            for _ in range(len(want)):
                pg.click('#veil [data-act="next"]')
                pg.wait_for_timeout(60)
                walk.append(car())
            print('      %-10s %s' % (gid, ' > '.join(walk)))
            ok(walk[0] == 'HATCH', '%s: a new save opens on HATCH' % gid, 'opened on %s' % walk[0])
            ok(walk[:len(want)] == want, '%s: the right arrow walks the lineup in order' % gid,
               'walked %s' % walk[:len(want)])
            ok(walk[len(want)] == want[0], '%s: and wraps from the last car back to the first' % gid,
               'after %s came %s' % (want[-1], walk[len(want)]))
            ok(not errs, '%s: no page errors' % gid, errs[0][:120] if errs else '')
            pg.close()
        b.close()
    httpd.shutdown()
    print()
    if args.expect_fail:
        print('expected at least one failure: %s' % ('got %d' % len(fails) if fails else 'got NONE'))
        return 0 if fails else 1
    if fails:
        print('FAILED: ' + '; '.join(fails))
        return 1
    print('the garage walks class by class')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
