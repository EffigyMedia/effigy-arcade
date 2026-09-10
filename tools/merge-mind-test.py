#!/usr/bin/env python3
"""MERGE MIND TEST - the indicator is a habit, and a driver can change their mind.

    .venv/Scripts/python tools/merge-mind-test.py

RLG-207. Owner, 2026-09-10, on how a lane change is decided: the chance to indicate is assigned when
the vehicle is SPAWNED; a car that was given one announces the move, waits one to three seconds, and
keeps evaluating throughout - and if the circumstances change enough that it should not merge, it
CANCELS the indicator, stays in its lane, and starts the process again a few seconds later. And,
asked whether the habit follows the personality: it does.

WHAT THIS ASSERTS, AND WHY EACH ONE IS SEPARATE.

  the habit exists on cars that have never merged - which is the whole of what "assigned at spawn"
  means, and the old code could not satisfy it because it rolled the habit inside the merge branch;

  the habit follows the personality, so a COMMUTER is likelier to carry one than an OUTLAW, and a
  RACER never does. Measured as a rate over the cars the road happens to deal;

  announcements happen, and some of them are ABANDONED. `mergesAborted` counts a driver thinking
  better of it, and it is counted apart from `signalledMerges` on purpose: an announcement that
  never completes is also exactly what a defect looks like, so a check that could not tell them
  apart would call a working change of mind a bug.

IT NAVIGATES WITH `wait_until="commit"` RATHER THAN "load", and that is not a preference. On
2026-09-10 this machine entered the wedge RLG-141's neighbour records: chromium stops firing `load`
for the two driving cabinets while the server hands the same 1.5MB of `road.js` over in 0.09s, and
it fails identically on the last known-good commit. The page parses, runs and answers on `commit`.
If `load` is working on your machine, nothing here behaves differently.

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
NAMES = {0: 'COMMUTER', 1: 'SPEEDER', 2: 'OUTLAW', 3: 'RACER'}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--headed', action='store_true')
    ap.add_argument('--seconds', type=int, default=45)
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

    print('merge-mind-test  .  the indicator is a habit, and a mind can change')
    with sync_playwright() as p:
        b = launch_chromium(p, headless=not args.headed,
                            args=['--mute-audio', '--autoplay-policy=no-user-gesture-required'])
        ctx = b.new_context(viewport={'width': 480, 'height': 900})
        page = ctx.new_page()
        errs = []
        page.on('pageerror', lambda e: errs.append(str(e)))

        page.goto('%s/%s' % (base, GAME), wait_until='commit', timeout=30000)
        # A FIXED WAIT AND A DIRECT READ, not `wait_for_function`. On the wedged
        # machine of 2026-09-10 the polling form timed out at 20s while a single
        # `evaluate` after a plain wait answered immediately - the page's own rAF
        # loop starves the poller. This is the shape that worked.
        booted = False
        for _ in range(6):
            page.wait_for_timeout(4000)
            if page.evaluate('() => typeof window.__road') == 'object':
                booted = True
                break
        ok(booted, 'the engine booted', 'window.__road is present')
        if not booted:
            print('  the machine cannot boot the cabinet - nothing below could run')
            ctx.close(); b.close()
            return 1

        # ---- drive an ordinary road, with plenty of traffic on it --------
        page.evaluate("""() => {
            const R = window.__road;
            R.setMode('endless');
            R.restart();
            R.setTimed(false);      /* RLG-125 */
            R.setPool(1);
            R.holdSpd(R.MAX_SPD * 0.55);
        }""")
        page.wait_for_timeout(args.seconds * 1000)

        st = page.evaluate("""() => ({
            sig: window.__road.signalling(),
            started: window.__road.signalsStarted(),
            done: window.__road.signalledMerges(),
            aborted: window.__road.mergesAborted(),
            made: window.__road.mergesMade() })""")
        sig = st['sig']

        print('  -- after %ds on a full road' % args.seconds)
        print('     %d cars: %d announcing now, %d mid-announcement, %d will never signal'
              % (sig['seen'], sig['now'], sig['waiting'], sig['never']))
        for m in sorted(sig['byMind']):
            b_ = sig['byMind'][m]
            print('     %-9s %2d of %2d carry the habit'
                  % (NAMES.get(int(m), m), b_['signals'], b_['seen']))
        print('     announced %d, completed %d, ABANDONED %d, merges in all %d'
              % (st['started'], st['done'], st['aborted'], st['made']))

        ok(sig['seen'] > 0, 'there is traffic on the road', '%d cars' % sig['seen'])
        # ---- ASSIGNED AT SPAWN ------------------------------------------
        # every car reports true or false, never undefined - which is what
        # `never` + the habit count adding up to `seen` means.
        carry = sum(v['signals'] for v in sig['byMind'].values())
        ok(carry + sig['never'] == sig['seen'],
           'every car on the road has been given a habit, merged or not',
           '%d carry it, %d refuse it, %d cars' % (carry, sig['never'], sig['seen']))
        # ---- IT FOLLOWS THE PERSONALITY ---------------------------------
        racers = sig['byMind'].get('3') or sig['byMind'].get(3)
        ok(racers is None or racers['signals'] == 0,
           'a racer never carries the habit',
           'none seen in traffic' if racers is None else '%d of %d' % (racers['signals'], racers['seen']))
        com = sig['byMind'].get('0') or sig['byMind'].get(0)
        out = sig['byMind'].get('2') or sig['byMind'].get(2)
        if com and out and out['seen'] >= 3:
            ok(com['signals'] / com['seen'] > out['signals'] / max(1, out['seen']),
               'and a commuter carries it more often than an outlaw',
               '%.0f%% against %.0f%%' % (100 * com['signals'] / com['seen'],
                                          100 * out['signals'] / out['seen']))
        else:
            print('  ..    too few outlaws on the road to rate them (%d) - mind-test '
                  'measures the mix, this file measures the habit'
                  % (out['seen'] if out else 0))
        # ---- ANNOUNCE, AND CHANGE YOUR MIND -----------------------------
        ok(st['started'] > 0, 'moves are announced before they are made',
           '%d announcements' % st['started'])
        ok(st['aborted'] > 0,
           'and some announcements are abandoned - a driver changing their mind',
           '%d abandoned against %d completed' % (st['aborted'], st['done']))
        ok(st['done'] > 0, 'while others complete',
           '%d completed' % st['done'])
        ok(not errs, 'the run was clean', '; '.join(errs[:2]))
        ctx.close()
        b.close()

    print('  %s' % ('all checks passed' if not bad else '%d check(s) failed' % bad))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
