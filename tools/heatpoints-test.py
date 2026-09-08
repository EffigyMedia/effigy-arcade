#!/usr/bin/env python3
"""HEAT POINTS TEST - the wanted level is a total, and it can reach nothing.

    .venv/Scripts/python tools/heatpoints-test.py

Owner, 2026-09-07: "instead of a single instance of something raising it one star, we could
do heat POINTS - and every instance of speeding where a new cop sees you speeding, or you
being directly responsible for a cop getting destroyed, or you running a roadblock, adds to
these points. Cooling off removes these points, so your wanted level can go down to empty
as well."

THE OLD MODEL COULD NOT REACH EMPTY. `heat` was an integer that moved in whole steps and
floored at ONE, so there was no such thing as being clean and no such thing as being
part-way through a level. This asserts the three things that were impossible before: a
total that moves by less than a star, a level you can be part-way through, and zero.

`heat` IS STILL THE STAR COUNT and everything that reads it - trap density, when a
roadblock may go up, when an interceptor is dispatched, how well a cruiser drives - goes on
reading the same number meaning the same thing. Only its source moved, and the last check
here is what says so.
"""
import sys, threading, http.server, socketserver, functools
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from harness import launch_chromium, console_utf8
from playwright.sync_api import sync_playwright

console_utf8()
handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
srv = socketserver.TCPServer(('127.0.0.1', 0), handler)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = 'http://127.0.0.1:%d' % PORT


def main():
    bad = 0

    def ok(cond, label, detail=''):
        nonlocal bad
        if not cond:
            bad += 1
        print('  %s  %s%s' % ('ok  ' if cond else 'FAIL', label,
                              ('   ' + detail) if detail else ''))

    print('heatpoints-test  .  a wanted level you can be part-way through')
    with sync_playwright() as p:
        b = launch_chromium(p, headless=True,
                            args=['--mute-audio', '--autoplay-policy=no-user-gesture-required'])
        ctx = b.new_context(viewport={'width': 480, 'height': 900})
        page = ctx.new_page()
        errs = []
        page.on('pageerror', lambda e: errs.append(str(e)))
        page.goto(BASE + '/games/sw/interstate.html', wait_until='load')
        try:
            page.wait_for_function(
                '() => navigator.serviceWorker && navigator.serviceWorker.controller', timeout=5000)
            page.wait_for_timeout(1200)
        except Exception:
            pass
        page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
        page.click('[data-act="play"]')
        page.wait_for_timeout(400)
        page.click('[data-act="chase"]')
        page.wait_for_timeout(200)
        page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
        page.click('[data-act="drive"]')
        page.wait_for_timeout(1500)

        hp = page.evaluate('() => window.__road.heatPoints()')
        print('  ..    a star is %d points; seen %d, roadblock %d, takedown %d, '
              'decay %s/s after %ss'
              % (hp['perStar'], hp['rates']['seen'], hp['rates']['block'],
                 hp['rates']['takedown'], hp['rates']['decayPerSec'], hp['rates']['grace']))

        # ---- IT STARTS AT NOTHING, WHICH THE OLD ONE COULD NOT -------------------
        page.evaluate('() => { window.__road.copsClear(); window.__road.setSpd(0); }')
        page.wait_for_timeout(400)
        start = page.evaluate('() => window.__road.heatPoints()')
        ok(start['pts'] == 0 and start['stars'] == 0,
           'a clean run starts at zero stars, not one',
           '%d points, %d stars' % (start['pts'], start['stars']))

        # ---- ONE SIGHTING IS LESS THAN A STAR ------------------------------------
        # The whole point of the change: an instance moves the total without moving the
        # level, so the level becomes something you can be part-way through.
        page.evaluate('() => { const R = window.__road; R.copsClear();'
                      ' R.setSpd(0.75 * R.MAX_SPD); R.placePatrol(1500); }')
        for _ in range(40):
            page.evaluate('() => window.__road.setSpd(0.75 * window.__road.MAX_SPD)')
            page.wait_for_timeout(100)
            if page.evaluate('() => window.__road.heatPoints().pts') > 0:
                break
        one = page.evaluate('() => window.__road.heatPoints()')
        print('  ..    after being caught once: %d points, %d stars, %d into the next'
              % (one['pts'], one['stars'], one['into']))
        ok(one['pts'] > 0, 'being caught earns points', '%d' % one['pts'])
        ok(one['pts'] < one['perStar'] or one['into'] > 0,
           'and one instance is less than a whole star',
           '%d points against %d to a star' % (one['pts'], one['perStar']))

        # ---- AND IT BLEEDS AWAY TO NOTHING ---------------------------------------
        # A CLEAN ROAD HAS TO STAY CLEAN, AND CLEARING IT FROM HERE DOES NOT DO THAT.
        # Nothing cools while a live cruiser is on you: the engine resets the cooling
        # clock on any such frame and then serves the grace again. Dispatch fires every
        # six to fourteen seconds at three stars, so a driver that clears the road four
        # times a second still leaves each new cruiser alive for a frame, and each one
        # costs the whole grace. Measured, that ran the decay at about a third of its
        # stated rate - which read as a broken tunable and was a leaky harness. The
        # sweeper runs INSIDE the page instead, faster than the frame it has to beat.
        # AND THE RUN HAS TO OUTLIVE THE COOLING. Shedding three stars takes longer
        # than the sixty seconds a run starts with, and a parked car reaches no
        # checkpoint to buy more - so the clock expired, the update stopped, and both
        # the total and the cooling clock froze mid-fall. Traced: 350 points fell to
        # 162 and then sat there unchanged for another two minutes. That read exactly
        # like a broken tunable. `setTimed(false)` is the affordance for it (RLG-125).
        page.evaluate('() => { const R = window.__road; R.setTimed(false);'
                      ' R.heat(3); R.copsClear();'
                      ' window.__sweep = setInterval(() => { R.copsClear(); R.setSpd(0); }, 4); }')
        page.wait_for_timeout(200)
        before = page.evaluate('() => window.__road.heatPoints()')
        seen = []
        # LONG ENOUGH TO ACTUALLY GET THERE, AND IT ASKS THE ENGINE HOW LONG THAT IS.
        # The first version watched for 35 seconds and reported a failure that was only
        # impatience; the second hardcoded 210 quarter-seconds against a decay of 8.33 a
        # second, which was the same mistake one retune away from biting. The decay is a
        # tunable, so the budget is computed from it: the points on the clock divided by
        # the rate they leave at, plus the grace, plus half again for slack.
        need = (before['pts'] / max(0.01, before['rates']['decayPerSec'])
                + before['rates']['grace'])
        rounds = int(need * 1.5 / 0.25) + 8
        print('  ..    %d points at %s/s: watching for %ds'
              % (before['pts'], before['rates']['decayPerSec'], rounds * 0.25))
        for _ in range(rounds):
            page.wait_for_timeout(250)
            seen.append(page.evaluate('() => window.__road.heatPoints()'))
            if seen[-1]['pts'] == 0:
                break
        page.evaluate('() => clearInterval(window.__sweep)')
        end = seen[-1]
        mids = [h['pts'] for h in seen]
        print('  ..    from %d points, cooling ran to %d' % (before['pts'], end['pts']))
        ok(end['pts'] < before['pts'], 'the total falls while nobody is on you',
           '%d to %d' % (before['pts'], end['pts']))
        # CONTINUOUS, NOT IN STEPS. The old model could only ever show multiples of a
        # star, so readings between two of them prove the TOTAL is the thing moving.
        between = sum(1 for v in mids if 0 < (v % before['perStar']) < before['perStar'])
        ok(between > 3, 'and it falls continuously rather than a star at a time',
           '%d readings landed between two stars' % between)
        ok(end['pts'] == 0 and end['stars'] == 0,
           'and it reaches EMPTY, which the old level could not',
           '%d points, %d stars' % (end['pts'], end['stars']))

        # ---- AND THE STARS STILL DRIVE EVERYTHING ELSE ---------------------------
        lv = page.evaluate('() => { const R = window.__road; R.heat(4);'
                           ' return { stars:R.pursuit().heat, cap:R.copCensus().cap }; }')
        ok(lv['stars'] == 4 and lv['cap'] > 0,
           'and the star count still drives the rest of the pursuit',
           'heat %d, dispatch cap %d' % (lv['stars'], lv['cap']))
        ok(errs == [], 'no page errors', errs[0][:100] if errs else '')
        ctx.close()
        b.close()
    srv.shutdown()
    print()
    print('  ' + ('the wanted level is a total' if not bad else str(bad) + ' FAILURES'))
    return 1 if bad else 0


sys.exit(main())
