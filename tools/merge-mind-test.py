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

  announcements happen and complete;

  and an announcement is ABANDONED when the lane it asked for closes - which is STAGED rather than
  waited for. An ordinary road produces about one announcement a minute, so waiting for a gap to
  close inside one of them is waiting for two rare things to coincide. This watches for a real
  announcement, reads the lane the ENGINE chose, and puts a car in it. `mergesAborted` counts these
  apart from `signalledMerges` on purpose: an announcement that never completes is also exactly what
  a defect looks like, so a check that could not tell them apart would call a working change of mind
  a bug.

IT BOOTS WITH `harness.boot`, AND THIS FILE IS WHERE THAT CAME FROM. On 2026-09-10 this machine
stopped firing `load` for the two driving cabinets while the server handed the same 1.5MB of
`road.js` over in 0.09s, and it failed identically on the last known-good commit. The shape written
here to get round it - navigate on `commit`, then read the engine directly - is now `harness.boot`
and the whole suite uses it (RLG-208). If `load` is working on your machine, nothing differs.

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
from harness import console_utf8, launch_chromium, boot
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

        # THIS FILE IS WHERE THE BOOT HELPER CAME FROM. The loop that used to sit here - navigate
        # on `commit`, then a fixed wait and a direct read - is now `harness.boot`, and every
        # harness in the suite uses it (RLG-208). `required=False` because the line below reports
        # a failure to boot rather than raising on it.
        booted = boot(page, '%s/%s' % (base, GAME), timeout=30000, required=False)
        ok(booted, 'the engine booted', 'window.__road is present')
        if not booted:
            print('  the machine cannot boot the cabinet - nothing below could run')
            ctx.close(); b.close()
            return 1

        # ---- drive an ordinary road, THROUGH THE REAL CONTROLS -----------
        # Starting the run through the API leaves the cabinet on its veil, and a
        # road that is not really being driven barely spawns: the first version of
        # this file did that and met 16 cars in 45 seconds where a run started by
        # pressing DRIVE meets forty. Nothing was under any pressure to merge, so
        # it measured no announcements and read as an engine fault.
        page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=20000)
        page.click('[data-act="play"]')
        page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=10000)
        page.click('[data-act="drive"]')
        page.wait_for_timeout(1500)
        page.evaluate("""() => {
            const R = window.__road;
            R.setTimed(false);      /* RLG-125 */
            R.setPool(1);
            /* SLOW, and that is the whole scenario. Merging is a car being held
               below the speed it wants by the car in front, so the pressure comes
               from a full road and a modest pace rather than from driving fast
               through it. */
            R.holdSpd(R.MAX_SPD * 0.42);
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
        # ---- ANNOUNCE, AND COMPLETE -------------------------------------
        ok(st['started'] > 0, 'moves are announced before they are made',
           '%d announcements' % st['started'])
        ok(st['done'] > 0, 'and they complete',
           '%d completed' % st['done'])

        # ---- AND CHANGE YOUR MIND, STAGED ON PURPOSE --------------------
        # An abandonment needs the target lane to close DURING the one-to-three
        # seconds a car is announcing, and an ordinary road produces about one
        # announcement a minute - so waiting for the two to coincide is waiting
        # for a coincidence. This watches for an announcement and then closes
        # the lane it asked for, which is the event itself rather than a
        # simulation of it: the engine chose the lane, the engine notices.
        print('  -- and now the lane is closed on purpose, mid-announcement')
        before = page.evaluate('() => window.__road.mergesAborted()')
        staged, aborted = 0, 0
        for _ in range(160):
            asking = page.evaluate('() => window.__road.signalling().asking')
            if asking:
                a = asking[0]
                page.evaluate("""([dz, want]) => {
                    const R = window.__road;
                    /* a car dropped into the lane the announcing car asked for,
                       level with it - `keep` so the announcing car survives */
                    R.parkTraffic(R.laneX(want), dz, 'sedan', 0, true);
                }""", [a['dz'], a['want']])
                staged += 1
                page.wait_for_timeout(500)
                now = page.evaluate('() => window.__road.mergesAborted()')
                if now > before:
                    aborted = now - before
                    break
            page.wait_for_timeout(250)
        ok(staged > 0,
           'an announcement was caught in progress to close the lane on',
           '%d caught' % staged)
        ok(aborted > 0,
           'and the driver cancelled: indicator off, stayed in lane',
           '%d abandoned after the lane was closed' % aborted)
        ok(not errs, 'the run was clean', '; '.join(errs[:2]))
        ctx.close()
        b.close()

    print('  %s' % ('all checks passed' if not bad else '%d check(s) failed' % bad))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
