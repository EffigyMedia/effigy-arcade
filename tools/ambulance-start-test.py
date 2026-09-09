#!/usr/bin/env python3
"""AMBULANCE START TEST - a run does not open with a siren going past.

    .venv/Scripts/python tools/ambulance-start-test.py [--runs 10]

RLG-176. Owner, 2026-09-08: "It's not a big deal, but pretty often a run will start with an
ambulance blowing by me."

IT IS A FREQUENCY CLAIM, SO IT IS COUNTED. "Pretty often" cannot be answered by reading the
spawner - the fragment lists three candidate causes that lead to three different fixes, and this
project has already diagnosed one police defect from a code read and been wrong about it. So the
road is booted from scratch a number of times and the first ten seconds of each run are watched
for an emergency vehicle.

WHAT COUNTS AS "AT THE START" is the first ten seconds of driving. An ambulance is meant to come
through roughly every ninety seconds to three minutes, so at that rate the expected number of
runs out of ten that open with one is well under one. Anything approaching every run is the
defect.

EACH RUN IS A FRESH PAGE, and that is the whole experiment rather than a detail. The clock that
calls an ambulance out is module state; whether it survives a restart, and what it holds when a
run begins, is exactly the question. Reusing one page and restarting the run would measure
something else.

AND THE CLOCK ITSELF IS REPORTED ALONGSIDE THE COUNT, because a rate alone says a thing is wrong
without saying what - `ambClock` is the seconds left before the next call-out, read the moment
the run starts.

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


def one_run(b, base, seconds):
    """Boot the road from nothing, drive, and report what the first seconds held."""
    ctx = b.new_context(viewport={'width': 480, 'height': 900})
    page = ctx.new_page()
    errs = []
    page.on('pageerror', lambda e: errs.append(str(e)))
    page.goto('%s/%s' % (base, GAME), wait_until='load')
    try:
        page.wait_for_function(
            '() => navigator.serviceWorker && navigator.serviceWorker.controller', timeout=5000)
        page.wait_for_timeout(900)
    except Exception:
        pass
    page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
    page.click('[data-act="play"]')
    page.wait_for_timeout(300)
    page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
    page.click('[data-act="drive"]')
    page.wait_for_timeout(700)

    clock = page.evaluate("() => window.__road.ambClock ? window.__road.ambClock() : null")
    seen = False
    for _ in range(int(seconds / 0.15)):
        page.evaluate('() => window.__road.setSpd(0.45 * window.__road.MAX_SPD)')
        page.wait_for_timeout(150)
        if page.evaluate("() => window.__road.traffic.some(c => c.emergency)"):
            seen = True
            break
    ctx.close()
    return seen, clock, errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--runs', type=int, default=10)
    ap.add_argument('--seconds', type=float, default=10.0)
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

    print('ambulance-start-test  .  %d fresh runs, first %.0fs of each'
          % (args.runs, args.seconds))
    hits, clocks, allerrs = 0, [], []
    with sync_playwright() as p:
        b = launch_chromium(p, headless=not args.headed,
                            args=['--mute-audio', '--autoplay-policy=no-user-gesture-required'])
        for i in range(args.runs):
            seen, clock, errs = one_run(b, base, args.seconds)
            allerrs += errs
            if seen:
                hits += 1
            if clock is not None:
                clocks.append(clock)
            print('    run %2d  %s   clock at start %s'
                  % (i + 1, 'AMBULANCE' if seen else '  -      ',
                     ('%.1fs' % clock) if clock is not None else 'not reported'))
        b.close()

    rate = hits / float(args.runs)
    print('  ..    %d of %d runs opened with one (%.0f%%)' % (hits, args.runs, rate * 100))
    if clocks:
        print('  ..    call-out clock at the start of a run: %.1f to %.1f seconds'
              % (min(clocks), max(clocks)))

    # ONE IN TEN IS THE LINE, and it is chosen from the design rather than from the
    # measurement. An ambulance is called out every 90 to 190 seconds, so in a ten-second
    # window the honest expectation is about one run in fourteen. A threshold set at two
    # in ten leaves room for luck without leaving room for the defect, which was every run.
    ok(hits <= 2, 'a run rarely opens with an ambulance',
       '%d of %d' % (hits, args.runs))
    ok(bool(clocks) and min(clocks) > 5,
       'and the call-out clock never starts a run near zero',
       'lowest %.1fs' % min(clocks) if clocks else 'ambClock not exposed')
    ok(not allerrs, 'and every run was clean', '; '.join(allerrs[:2]))

    print('  %s' % ('all checks passed' if not bad else '%d check(s) failed' % bad))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
