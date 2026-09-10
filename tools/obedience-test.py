#!/usr/bin/env python3
"""OBEDIENCE TEST - four personalities, four different answers to a siren.

    .venv/Scripts/python tools/obedience-test.py

RLG-206. Owner, 2026-09-10: "personalities should behave correctly, eg an outlaw will never move out
of the way, a speeder and driver will" - and then the four, by name and by rule:

    COMMUTER  obeys the traffic laws.        HIGH obedience to horns and sirens.
    SPEEDER   fast within reason, pulls over. MODERATE.
    OUTLAW    fast and reckless, will not.    LOW.
    RACER     an outlaw in a race.            NONE.

And, when it was asked whether this belonged to the new mode: "These aren't just intercept
behaviors, but global." So this measures the ordinary road, not INTERCEPT.

WHY IT STAGES THE CAR RATHER THAN WAITING FOR ONE. The road hands out an OUTLAW to about one car in
twenty, so a check that drove until it met enough of them would be measuring the spawn odds - the
thing `mind-test` already measures - rather than the obedience tiers. `parkTraffic` puts a car of a
named personality directly in front of the player, inside the window the siren actually reaches, and
the siren is sounded at it. That is the same loop, the same gates and the same random draw; only the
sample is arranged.

WHAT IS ASSERTED, AND WHY IT IS THE ORDER RATHER THAN THE NUMBERS. Each tier is a probability, so a
run of trials gives a rate and not a verdict - and the rates move the moment the owner tunes the
table, which is what the table is for. What must hold whatever the numbers are is the ORDER: a
commuter answers more often than a speeder, a speeder more than an outlaw, and a racer never. The
two ends are hard: a commuter at 0.90 effective odds must move sometimes, and a racer must move
NEVER, because zero is not a small number.

AND EACH TRIAL USES A FRESH CAR. A car worn down by being asked repeatedly settles at a share of what
it started with rather than at a flat floor, so a tired outlaw stays more stubborn than a tired
commuter - but that is the fatigue's claim and not this one. Measuring the tiers means measuring them
unworn.

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
TRIALS = 40
NAMES = ('COMMUTER', 'SPEEDER', 'OUTLAW', 'RACER')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--headed', action='store_true')
    ap.add_argument('--trials', type=int, default=TRIALS)
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

    print('obedience-test  .  four personalities, four answers to a siren')
    with sync_playwright() as p:
        b = launch_chromium(p, headless=not args.headed,
                            args=['--mute-audio', '--autoplay-policy=no-user-gesture-required'])
        ctx = b.new_context(viewport={'width': 480, 'height': 900})
        page = ctx.new_page()
        errs = []
        page.on('pageerror', lambda e: errs.append(str(e)))

        page.goto('%s/%s' % (base, GAME), wait_until='load')
        page.wait_for_timeout(600)
        page.evaluate("() => window.Arcade.save.merge('interstate-opts', { cruiser:true })")
        page.reload(wait_until='load')
        page.wait_for_timeout(700)
        page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
        page.click('[data-act="play"]')
        page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
        page.evaluate("() => window.__road.setBody('CRUISER')")
        page.click('[data-act="drive"]')
        page.wait_for_timeout(1200)
        page.evaluate("""() => {
            const R = window.__road;
            R.setTimed(false);      /* RLG-125: a held car reaches no checkpoint, and an
                                       expired clock freezes every number where it stood */
            R.holdSpd(0);           /* THE PLAYER IS HELD STILL, so the staged car stays at the
                                       distance it was staged at. Driving past it would make the
                                       measurement a race between the cooldown and the closing
                                       speed rather than a measurement of obedience. */
            R.setBar(true);         /* the latch itself is bar-scatter-test's claim, not this one */
        }""")

        minds = page.evaluate('() => window.__road.MINDS()')
        table = page.evaluate("""(m) => {
            const R = window.__road, out = {};
            for(const k of Object.keys(m)) out[k] = R.obeyOf(m[k]);
            return out;
        }""", minds)
        print('  declared: %s'
              % '  '.join('%s=%s' % (n, table[n]) for n in NAMES))
        ok(table['COMMUTER'] > table['SPEEDER'] > table['OUTLAW'] > table['RACER'],
           'the table itself runs high, moderate, low, none')
        ok(table['RACER'] == 0, 'and a racer is a hard zero, not a small number')

        def trial_run(name):
            """A fresh car of this personality, in front of the player. Did it move?

            The sim runs on the browser's own clock - `drawFrame` reports a frame, it does
            not step one - so a trial is real time. 650ms is ONE pass of the 0.55s cooldown,
            deliberately: at 1.4s every car got asked twice, and two asks blur the tiers
            together - a COMMUTER and a SPEEDER both read 95 per cent, because 0.90 and
            0.54 are hard to tell apart once you have had two goes at each."""
            return page.evaluate("""async ([mind, n]) => {
                const R = window.__road;
                const wait = ms => new Promise(r => setTimeout(r, ms));
                let moved = 0, asked = 0;
                for(let i = 0; i < n; i++){
                    /* a fresh car each time: the tiers are measured UNWORN */
                    R.parkTraffic(0, 1800, 'sedan', mind);
                    R.scatterStat(true);
                    await wait(650);
                    const st = R.scatterStat(true);
                    asked += st.moved + st.obey + st.gap + st.deaf;
                    /* ONE PER TRIAL, capped. A staged car sits in the window for the
                       whole 1.4s, so the cooldown lets it be asked twice - and counting
                       both made a rate read 135 per cent, which is a count wearing a
                       percentage sign. The trial asks "did this car move over", once. */
                    if(st.moved > 0) moved++;
                }
                return { moved: moved, asked: asked };
            }""", [minds[name], args.trials])

        print('  -- %d trials each, one fresh car per trial' % args.trials)
        rate = {}
        for name in NAMES:
            r = trial_run(name)
            rate[name] = r['moved'] / max(1, args.trials)
            print('    %-9s moved %2d of %d  (%.0f%%)   reached the car %d time(s)'
                  % (name, r['moved'], args.trials, rate[name] * 100, r['asked']))

        # ---- THE ORDER IS THE CLAIM, NOT THE RATES -----------------------
        ok(rate['COMMUTER'] > 0,
           'a commuter moves over for a siren', '%.0f%%' % (rate['COMMUTER'] * 100))
        ok(rate['RACER'] == 0,
           'a racer never does, in any trial', '%d move(s)' % (rate['RACER'] * args.trials))
        ok(rate['COMMUTER'] > rate['OUTLAW'],
           'and a commuter answers more often than an outlaw',
           '%.0f%% against %.0f%%' % (rate['COMMUTER'] * 100, rate['OUTLAW'] * 100))
        ok(rate['COMMUTER'] > rate['SPEEDER'] > rate['OUTLAW'],
           "and all four tiers are separated, in the owner's order",
           '%.0f%% > %.0f%% > %.0f%% > 0%%'
           % (rate['COMMUTER'] * 100, rate['SPEEDER'] * 100, rate['OUTLAW'] * 100))
        # Measured 2026-09-10 at 40 trials: 82%, 52%, 18%, 0% against declared
        # effective odds of 0.90, 0.54, 0.225 and 0.

        ok(not errs, 'the run was clean', '; '.join(errs[:2]))
        ctx.close()
        b.close()

    print('  %s' % ('all checks passed' if not bad else '%d check(s) failed' % bad))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
