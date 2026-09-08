#!/usr/bin/env python3
"""DEER TEST - something crosses the road, and it is not driving.

    .venv/Scripts/python tools/deer-test.py

Owner, 2026-09-01 (RLG-152): "in the forest biome I'd like a very very small chance for deer
to sprint across the road from one tree line to the other."

IT IS THE FIRST THING IN THIS GAME THAT MOVES ACROSS THE ROAD, and that is what has to be
proved: not that a sprite exists, but that a thing enters at one tree line, travels the whole
width, and is gone at the other. A scenery object with a moving offset would look identical
in a screenshot and would fail every line below.

THE ODDS ARE MEASURED SEPARATELY FROM THE CROSSING, because they are different claims and
one of them is a random number. A harness that waited for one forest in ten to produce a deer
would spend its time measuring the generator; `placeDeer` stages a crossing so the movement
can be watched, and the odds are counted by opening forests and asking what was planned.
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

    print('deer-test  .  something crosses the road')
    with sync_playwright() as p:
        b = launch_chromium(p, headless=True,
                            args=['--mute-audio', '--autoplay-policy=no-user-gesture-required'])
        ctx = b.new_context(viewport={'width': 480, 'height': 900})
        page = ctx.new_page()
        errs = []
        page.on('pageerror', lambda e: errs.append(str(e)))
        page.goto(BASE + '/games/sw/interstate.html', wait_until='load')
        page.wait_for_timeout(1200)
        page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
        page.click('[data-act="play"]')
        page.wait_for_timeout(400)
        page.click('[data-act="chase"]')
        page.wait_for_timeout(200)
        page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
        page.click('[data-act="drive"]')
        page.wait_for_timeout(1500)
        # a crossing takes about a second and the run's clock would end part way
        # through the sample - the same clock that froze three other harnesses (RLG-169)
        page.evaluate('() => window.__road.setTimed(false)')

        cfg = page.evaluate('() => window.__road.deerOdds()')
        print('  ..    one forest in %d, crossing at %g lane units a second from %g out'
              % (round(1 / cfg['odds']), cfg['cross'], cfg['from']))

        # ---- IT ENTERS FROM OUTSIDE THE ROAD ------------------------------------
        page.evaluate('() => { const R = window.__road; R.setSpd(0);'
                      ' window.__hold = setInterval(() => R.setSpd(0), 20); }')
        n = page.evaluate('() => window.__road.placeDeer(3000, 1)')
        ok(n == 1, 'a crossing can be put on the road', '%d staged' % n)
        first = page.evaluate('() => window.__road.crossings()')
        ok(bool(first) and abs(first[0]['x']) > 1.0,
           'it starts outside the road, at the tree line',
           'at %.2f lane units' % (first[0]['x'] if first else 0))

        # ---- AND IT CROSSES, WHICH IS THE WHOLE FEATURE -------------------------
        # THE PATH IS SAMPLED, NOT THE ENDPOINTS. A thing that vanished on one side
        # and reappeared on the other would satisfy a start-and-finish check; what is
        # asserted is that it was seen on the near side, in the middle of the road,
        # and then on the far side, in that order.
        seen = []
        for _ in range(40):
            page.wait_for_timeout(50)
            c = page.evaluate('() => window.__road.crossings()')
            if not c:
                break
            seen.append(c[0]['x'])
        page.evaluate('() => clearInterval(window.__hold)')
        print('  ..    it went from %.2f to %.2f over %d readings'
              % (seen[0], seen[-1], len(seen)))
        ok(len(seen) > 3, 'it is on the road for long enough to be seen',
           '%d readings' % len(seen))
        ok(seen[0] > 1.0 and seen[-1] < seen[0],
           'and it travels toward the other side', '%.2f -> %.2f' % (seen[0], seen[-1]))
        ok(any(abs(x) < 0.5 for x in seen),
           'and it goes through the middle of the road rather than round it',
           'nearest the centre was %.2f' % min(abs(x) for x in seen))
        ok(all(seen[i] >= seen[i + 1] - 0.001 for i in range(len(seen) - 1)),
           'and it never turns back', 'the path was not one-way')

        # ---- AND IT LEAVES -------------------------------------------------------
        for _ in range(60):
            page.wait_for_timeout(50)
            if not page.evaluate('() => window.__road.crossings()'):
                break
        ok(page.evaluate('() => window.__road.crossings()') == [],
           'and it is gone when it reaches the far side')

        # ---- IT CROSSES THE OTHER WAY TOO ---------------------------------------
        # The side is rolled, so a crossing that only worked in one direction would
        # be right half the time and look right all of it.
        page.evaluate('() => { const R = window.__road; R.setSpd(0);'
                      ' window.__hold = setInterval(() => R.setSpd(0), 20); }')
        page.evaluate('() => window.__road.placeDeer(3000, -1)')
        other = []
        for _ in range(40):
            page.wait_for_timeout(50)
            c = page.evaluate('() => window.__road.crossings()')
            if not c:
                break
            other.append(c[0]['x'])
        page.evaluate('() => clearInterval(window.__hold)')
        ok(bool(other) and other[0] < -1.0 and other[-1] > other[0],
           'and one from the other side runs the other way',
           '%.2f -> %.2f' % (other[0], other[-1]) if other else 'none staged')

        # ---- IT IS SOMETHING YOU CAN HIT ----------------------------------------
        # The ruling's third question: nothing at all makes it decoration. It is in
        # `traffic`, so the collision it already has is the answer - and this is what
        # says so rather than assuming it.
        # ---- NOSE-ON, WHICH IS HOW YOU MEET ONE --------------------------------
        # The severity the engine computes is a shape as well as a speed: something
        # exactly alongside is a rub and something ahead of you is a strike. Pinning
        # the animal at the player's own z made every measurement a flank rub and
        # halved the damage - 12.2 where a nose-on hit costs 20.3 - which is a fact
        # about where the harness put it, not about the deer. It is held a little
        # AHEAD, because a thing crossing your path is in front of you.
        #
        # AND THE PARTICLE COUNT IS A PEAK, NOT A SNAPSHOT. The bright spray lives a
        # fifth of a second and the heavy pieces a second; a reading taken 600ms
        # after the hit finds only the heavy ones and reports 14 of a burst of 40.
        page.evaluate("""() => { const R = window.__road;
            R.setDamage(0); R.setLane(0);
            // THE CAR HAS TO BE MOVING. A collision at a standstill is not one -
            // this read zero damage with the animal sitting exactly on the player,
            // because nothing had run into anything.
            R.setSpd(0.8 * R.MAX_SPD);
            R.placeDeer(300, 1);
            window.__peak = 0;
            window.__hold = setInterval(() => { R.setSpd(0.8 * R.MAX_SPD); R.setLane(0);
              const k = R.traffic.filter(c => c.type === 'deer')[0];
              if(k){ k.x = 0; k.z = R.pos + R.PLAYER_Z + 150; k.spd = 0; }
              const f = R.fxNow(); if(f.red > window.__peak) window.__peak = f.red; },
              8); }""")
        page.wait_for_timeout(600)
        after = page.evaluate("() => ({ dmg: window.__road.damage(),"
                              " fx: { n: window.__road.fxNow().n, red: window.__peak },"
                              " left: window.__road.crossings().length })")
        page.evaluate('() => clearInterval(window.__hold)')
        hurt = after['dmg']
        ok(hurt > 0, 'hitting one costs you, so a forest is a place to slow down for',
           '%.1f damage' % hurt)

        # ---- AND IT DOES NOT WALK AWAY (owner, 2026-09-08) ----------------------
        # The ruling left this open as a tone decision and the owner made it: the
        # animal is killed. A car takes damage and drives on; this does not.
        ok(after['left'] == 0, 'and the animal does not survive it',
           '%d still crossing' % after['left'])
        # THE PARTICLES ARE READ AS THE PAINTER'S INPUT, not off the screen. A frame
        # has tail lights, a sunset and a flashing police bar in it, so counting red
        # PIXELS would find red on a build that drew nothing at all.
        print('  ..    the burst peaked at %d red particles' % after['fx']['red'])
        ok(after['fx']['red'] >= 20,
           'and what is left of it is a bloody mess rather than debris',
           'peaked at %d red particles' % after['fx']['red'])

        # ---- AND IT COSTS MORE THAN CLIPPING A CAR AT THE SAME SPEED -----------
        # "Appropriate damage" is a comparison, not a number. The severity the engine
        # computes is about GEOMETRY and closing speed and says nothing about what was
        # hit - so before this, an animal cost exactly what clipping a saloon costs.
        # The same staged collision is run against an ordinary traffic car at the same
        # speed, in the same place, so everything except the thing hit is identical.
        car = page.evaluate("""() => { const R = window.__road;
            R.setDamage(0); R.setLane(0); R.setSpd(0.8 * R.MAX_SPD);
            R.parkTraffic(0, 300, 'sedan');
            window.__hold = setInterval(() => { R.setSpd(0.8 * R.MAX_SPD); R.setLane(0);
              const k = R.traffic[0];
              if(k){ k.x = 0; k.z = R.pos + R.PLAYER_Z + 150; k.spd = 0; } }, 8);
            return true; }""")
        page.wait_for_timeout(600)
        car_dmg = page.evaluate('() => window.__road.damage()')
        page.evaluate('() => clearInterval(window.__hold)')
        strike = page.evaluate('() => window.__road.deerOdds().strike')
        print('  ..    a deer costs %.1f against %.1f for a car at the same speed,'
              ' declared multiplier %g' % (hurt, car_dmg, strike))
        # THE THRESHOLD IS SET UNDER THE MEASURED SPREAD, not at the multiplier. The
        # ratio came in at 1.54, 1.61, 1.72, 1.99 and 2.09 across runs - the severity
        # term depends on exactly where the two met, and that varies frame to frame.
        # A bound of 1.4 sits below all of them and well above the 0.79 an engine
        # without the strike factor produces.
        ok(car_dmg > 0 and hurt > car_dmg * 1.4,
           'and it costs more than clipping a car at the same speed does',
           '%.1f against %.1f, a ratio of %.2f'
           % (hurt, car_dmg, hurt / max(0.01, car_dmg)))

        # ---- AND IT ONLY HAPPENS IN A FOREST ------------------------------------
        # `planDeer` is the whole of the rarity and the whole of the placement rule,
        # so it is asked directly: a hundred openings of each place, counting how many
        # planned a crossing. A desert that ever plans one is the ruling broken.
        counts = page.evaluate("""() => {
            const R = window.__road;
            const out = {};
            for(const key of ['FOREST', 'DESERT', 'CITY']){
              let n = 0;
              for(let i = 0; i < 400; i++) if(R.deerPlan(key, false)) n++;
              out[key] = n / 400;
            }
            // AND A FOREST WITH WATER DOWN ONE SIDE IS NOT TWO TREE LINES. The
            // owner asked for one to the other, so a coastal wood has nothing for
            // the animal to come out of on one side.
            let sea = 0;
            for(let i = 0; i < 400; i++) if(R.deerPlan('FOREST', true)) sea++;
            out.COASTAL_FOREST = sea / 400;
            return out; }""")
        print('  ..    planned in %.1f%% of forests, %.1f%% of deserts, %.1f%% of cities'
              % (counts['FOREST'] * 100, counts['DESERT'] * 100, counts['CITY'] * 100))
        ok(counts['DESERT'] == 0 and counts['CITY'] == 0,
           'nowhere but a forest ever plans one', str(counts))
        ok(counts['COASTAL_FOREST'] == 0,
           'and not a forest with water down one side, which has one tree line',
           '%.3f of 400' % counts['COASTAL_FOREST'])
        # 400 openings at one in ten: a band wide enough that an honest engine does not
        # fail it by chance, narrow enough that one in three or one in a hundred does.
        ok(0.05 <= counts['FOREST'] <= 0.18,
           'and a forest plans one about one time in ten',
           '%.3f over 400 openings' % counts['FOREST'])

        ok(errs == [], 'no page errors', errs[0][:120] if errs else '')
        ctx.close()
        b.close()
    srv.shutdown()
    print()
    print('  ' + ('something crosses the road' if not bad else str(bad) + ' FAILURES'))
    return 1 if bad else 0


sys.exit(main())
