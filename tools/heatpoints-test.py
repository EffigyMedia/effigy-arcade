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
from harness import launch_chromium, console_utf8, boot, until
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
        boot(page, BASE + '/games/sw/interstate.html')
        try:
            until(page, '() => navigator.serviceWorker && navigator.serviceWorker.controller', timeout=5000)
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

        # ---- AND A PURSUIT YOU STAY IN EARNS BY THE MILE -------------------------
        # Owner, 2026-09-08: "we can also increment 2 heat per mile while actively
        # pursued." The other three earners are EVENTS; this one is a distance, and it
        # is the floor under a chase a good driver could otherwise hold open forever
        # without being seen again.
        #
        # BOTH ARMS ARE MEASURED, and the clean one is what makes this evidence. A rate
        # that fires whether or not anyone is chasing would pass a check that only ever
        # drives with a cruiser behind it - so the same distance is covered twice, once
        # with the road empty and once with a cruiser pinned on the player, and the
        # clean arm has to earn NOTHING.
        def run_miles(units, chased):
            page.evaluate("""([u, ch]) => {
                const R = window.__road;
                R.setTimed(false); R.copsClear(); R.heatSet(0);
                window.__road.__z0 = R.pos;
                // ONE CRUISER, PUT BACK EVERY TICK, AND NOTHING ELSE ON THE ROAD.
                // The road is rebuilt rather than added to: a SPEED TRAP arms itself
                // as the player passes and charges a 20-point sighting, which is ten
                // miles of the rate under test arriving at random - it put 40 points
                // into this measurement before the road was cleared this way.
                const only = () => { const a = R.cops(); a.length = 0;
                    a.push({ z: R.pos + 200, x: 0, spd: 0, wreck: 0, ang: 0,
                      grace: 0, cool: 0, side: 1, w: 0.27, len: 400, phase: 0,
                      dmg: 0, from: 'test', onPlayer: true }); };
                window.__hold = setInterval(() => {
                    R.setSpd(0.9 * R.MAX_SPD);
                    // AND NOTHING MAY SEE THE PLAYER. This drives at 180mph past a
                    // limit of 80, so an ordinary patrol promoted to a cruiser earns
                    // a 20-point SIGHTING - ten miles' worth of the rate under test,
                    // arriving at random. Parking the traffic far up the road is the
                    // same affordance heat-test uses for the same reason.
                    R.parkTraffic(9, 60000);
                    // THE CRUISER IS PINNED ON THE PLAYER rather than driven. A cop
                    // that has to keep up is a second thing being measured, and one
                    // that falls behind LOST_AT stops the charge without saying so.
                    if(ch) only(); else R.copsClear();
                }, 4);
            }""", [units, chased])
            for _ in range(240):
                page.wait_for_timeout(250)
                if page.evaluate('() => window.__road.pos - window.__road.__z0') >= units:
                    break
            d = page.evaluate('() => ({ gone: window.__road.pos - window.__road.__z0,'
                              ' pts: window.__road.heatPoints().pts,'
                              ' why: window.__road.heatPoints().why,'
                              ' chasing: window.__road.pursuit().chasing })')
            page.evaluate('() => clearInterval(window.__hold)')
            return d

        mile = hp['rates']['mileUnits']
        per = hp['rates']['perMile']
        clean = run_miles(mile * 3, False)
        print('  ..    %.2f miles with the road empty: %d points (last cause %r, %d chasing)'
              % (clean['gone'] / mile, clean['pts'], clean['why'], clean['chasing']))
        ok(clean['pts'] == 0, 'clean miles earn nothing', '%d points' % clean['pts'])

        hot = run_miles(mile * 3, True)
        want = hot['gone'] / mile * per
        print('  ..    %.2f miles with a cruiser on you: %d points, %d expected'
              ' (last cause %r, %d chasing)'
              % (hot['gone'] / mile, hot['pts'], round(want), hot['why'], hot['chasing']))
        # TWO ASSERTIONS, AND THE FIRST ONE IS WHY. Comparing the total against a rate
        # read off the engine cannot fail when the rate is ZERO: it expects nothing,
        # gets nothing, and calls that agreement. Watched doing exactly that with
        # HEAT_PER_MILE set to 0 - the check went green on an engine with the feature
        # switched off. So the mechanism is asserted to EXIST first, against the clean
        # arm, and only then to charge at the declared rate.
        ok(hot['pts'] > clean['pts'] and hot['pts'] > 0,
           'and a pursuit you stay in earns heat the clean road did not',
           '%d points against %d over the same %.2f miles'
           % (hot['pts'], clean['pts'], hot['gone'] / mile))
        ok(abs(hot['pts'] - want) <= max(2, want * 0.15),
           'and it charges the %g points a mile the engine declares' % per,
           '%d points over %.2f miles against %d expected'
           % (hot['pts'], hot['gone'] / mile, round(want)))

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
