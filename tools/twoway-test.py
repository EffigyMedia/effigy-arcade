#!/usr/bin/env python3
"""TWO-WAY TEST - the traffic can see the police, and does not drive through them.

    .venv/Scripts/python tools/twoway-test.py

Owner, 2026-09-07 (RLG-159): "seems like traffic doesn't avoid crashing into the police
either, so it's two-sided." Every avoidance sweep in the engine read `traffic`, then the
PLAYER as a named special case, and `cops` not at all - so a cruiser was invisible to every
civilian on the road.

THE PROOF IS A CONTROLLED APPROACH, NOT A STATISTIC. One cruiser is parked in one lane and
one traffic car is put behind it in the same lane, closing. A driver that cannot see it
arrives at the same piece of road; a driver that can either slows or leaves the lane. That
is a question with two outcomes and no tuning in it, and it fails loudly on an engine whose
sweeps ignore the police.

TWO STATISTICS WERE TRIED FIRST AND NEITHER MEASURED ANYTHING, which is worth recording so
the afternoon is not spent again:

  - INTERPENETRATION. Counting frames in which a traffic car sat inside a cruiser gave 2.3
    readings per hundred samples before the fix and 3.2 after. The collision code resolves
    an overlap within a frame or two, so the state barely exists to be sampled.
  - CRUISERS PUT OUT BY TRAFFIC, which is RLG-158's own sentence as a number. It reads ZERO
    over ninety seconds of pursuit, and zero across five conditions from one star at half
    speed to five stars at nine tenths - two to six damage events in forty-five seconds and
    never the three hits a cruiser needs. The owner's "constantly crashing into traffic and
    destroying themselves" does not reproduce in a harness, and that is a fact about the
    harness or about how a real player drives, NOT evidence that it does not happen.

AND ONE OF THE TWO ASSERTIONS BELOW IS THE PROOF WHILE THE OTHER IS ONLY A GUARD. Run
against the engine whose sweeps ignore the police, the REACTION check goes red - 0.00 lanes
of movement against 0.78 - and the OVERLAP check stays green, because at a 120ms sample the
few frames of interpenetration are usually stepped over and the collision code resolves the
rest. Do not read a green overlap line as evidence of anything. The reaction is the sight.
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

# THE APPROACH. One cruiser stands still in the middle lane; one traffic car is placed
# behind it in the same lane and pointed at it. Everything else is swept off the road every
# tick, so what the car does is a reaction to the cruiser and to nothing else.
#
# THE CRUISER IS PARKED, NOT DRIVEN. A cop that chases is a second behaviour inside the
# measurement, and one that drifts out of the lane answers the question by accident.
APPROACH = """([dz, withCop]) => {
  const R = window.__road;
  clearInterval(window.__hold);
  const pz = R.pos + R.PLAYER_Z;
  R.copsClear();
  R.parkTraffic(9, 90000);
  const car = R.traffic[0];
  if(!car) return null;
  car.x = 0; car.lane = 1;
  car.z = pz + 6000;
  car.spd = car.cruise = 0.42 * R.MAX_SPD;
  car.mind = car.mind;
  window.__car = car;
  if(withCop)
    R.cops().push({ z: pz + 6000 + dz, x: 0, spd: 0, wreck: 0, ang: 0, grace: 9,
                    cool: 0, side: 1, w: 0.27, len: 400, phase: 0, dmg: 0,
                    from: 'test', onPlayer: false, iframe: 9 });
  window.__hold = setInterval(() => {
    R.setSpd(0);
    // the cruiser stands still and stays whole: `grace` and `iframe` keep the
    // engine's own collision code from resolving the meeting before the driver
    // has had to answer for it
    const k = R.cops()[0];
    if(k){ k.spd = 0; k.grace = 9; k.iframe = 9; k.wreck = 0; }
    // and nothing else joins the experiment
    for(const c of R.traffic) if(c !== window.__car){ c.z = R.pos + 90000; c.x = 2.4; }
  }, 8);
  return { carZ: car.z, carX: car.x };
}"""

WATCH = """() => {
  const R = window.__road;
  const c = window.__car;
  const k = R.cops()[0];
  /* OVERLAP IS THE QUESTION, NOT THE GAP. The cruiser stands still and the car is
     moving, so the car passes it and the gap goes through zero to a large negative
     number by design - a closest-approach reading would be measuring the length of
     the experiment. What matters is whether the two ever occupied the same road:
     inside half their combined length AND half their combined width, which is the
     same test the collision code makes. */
  const hit = !!k && Math.abs(k.z - c.z) < (c.len + k.len) / 2
                  && Math.abs(k.x - c.x) < (c.w + k.w) / 2;
  return { x: +c.x.toFixed(3), spd: Math.round(c.spd), hit: hit,
           gap: k ? Math.round(k.z - c.z) : null,
           cruise: Math.round(c.cruise) };
}"""


def main():
    bad = 0

    def ok(cond, label, detail=''):
        nonlocal bad
        if not cond:
            bad += 1
        print('  %s  %s%s' % ('ok  ' if cond else 'FAIL', label,
                              ('   ' + detail) if detail else ''))

    print('twoway-test  .  the traffic can see the police')
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
        # the clock would end the run part way through the approach (RLG-169)
        page.evaluate('() => window.__road.setTimed(false)')

        def approach(with_cop):
            page.evaluate(APPROACH, [2600, with_cop])
            page.wait_for_timeout(300)
            first = page.evaluate(WATCH)
            moved = 0.0
            slowed = 0
            hits = 0
            passed = False
            for _ in range(60):
                page.wait_for_timeout(120)
                w = page.evaluate(WATCH)
                if w['hit']:
                    hits += 1
                if w['gap'] is not None and w['gap'] < -2000:
                    passed = True
                moved = max(moved, abs(w['x'] - first['x']))
                slowed = max(slowed, first['spd'] - w['spd'])
            page.evaluate('() => clearInterval(window.__hold)')
            return {'hits': hits, 'passed': passed, 'moved': round(moved, 3),
                    'slowed': slowed, 'cruise': first['cruise']}

        # ---- THE CONTROL: NO CRUISER, AND THE CAR JUST DRIVES ----------------
        # Without this the check could pass on a car that slows or wanders for any
        # reason at all, which is most of them.
        free = approach(False)
        print('  ..    with the lane empty: moved %.2f lanes, slowed by %d'
              % (free['moved'], free['slowed']))

        met = approach(True)
        print('  ..    with a cruiser parked ahead: moved %.2f lanes, slowed by %d of a'
              ' cruise of %d, %d frames inside it, got past: %s'
              % (met['moved'], met['slowed'], met['cruise'], met['hits'], met['passed']))

        # ONE OR THE OTHER, NOT BOTH. The engine's repertoire is to slow for the thing
        # in front or to go round it, and which one a given approach produces depends on
        # whether the lane beside it is clear. Insisting on a particular answer would be
        # asserting the tuning rather than the sight.
        saw = met['slowed'] > free['slowed'] + 200 or met['moved'] > free['moved'] + 0.20
        ok(saw, 'a civilian reacts to a police car standing in its lane',
           'slowed by %d against %d, moved %.2f against %.2f'
           % (met['slowed'], free['slowed'], met['moved'], free['moved']))
        # AND IT DOES NOT ARRIVE ANYWAY. A driver that lifts and then drives into the
        # back of it has not avoided anything.
        # OVERLAP IS PRINTED AND NOT ASSERTED, deliberately. It stays at or near zero on
        # the engine that CANNOT see the police - a 120ms sample steps over the few
        # frames of contact and the collision code resolves the rest - so it separates
        # nothing, and an assertion that cannot fail on a broken engine is worse than no
        # assertion at all. It is here because a large number would mean something.
        print('  ..    (diagnostic, not an assertion: %d frames inside the cruiser)'
              % met['hits'])
        ok(met['passed'], 'and the approach actually completed',
           'the car never reached the cruiser, so nothing was avoided')
        # ================= THE OTHER SIDE: THE POLICE (RLG-158) =================
        # Owner, 2026-09-07: the police "need to be just as interested in navigating the
        # traffic as they are stopping and arresting you".
        #
        # THE DODGE STEERED AND NEVER LIFTED. A cruiser read the road ahead and picked a
        # LINE around it, and its speed came from the chase and from nothing else - so a
        # car it could not go round was driven into at full chase speed.
        #
        # THIS IS A CONTROLLED FORCED LIFT, and the wall is what makes it evidence. A
        # cruiser given a gap will steer through it and prove nothing about lifting, so
        # the lane it is in is blocked and BOTH neighbours are blocked too. The only
        # answer left is the throttle.
        #
        # A STATISTIC WAS TRIED FIRST AND COULD NOT SETTLE IT: damage events taken from
        # traffic over ninety seconds of pursuit ran 6.0, 5.3 and 8.7 a minute before the
        # change and 2.7, 7.3 and 5.3 after. The means move the right way and the ranges
        # overlap, so three runs an arm say nothing - the same trap RLG-056 records.
        WALL = """([back]) => {
          const R = window.__road;
          clearInterval(window.__hold);
          const pz = R.pos + R.PLAYER_Z;
          R.copsClear();
          // THE TRAFFIC IS NOT PARKED OUT OF THE WAY FIRST. `parkTraffic` puts cars
          // far enough up the road that the culler takes them, so the array was empty
          // by the time the wall was built out of it.
          const wall = R.traffic.slice(0, 3);
          if(wall.length < 3) return null;
          const lanes = [-0.66, 0, 0.66];
          wall.forEach((c, i) => { c.x = lanes[i]; c.z = pz - back + 5200;
                                   c.spd = c.cruise = 0.30 * R.MAX_SPD; });
          window.__wall = wall;
          const k = { z: pz - back, x: 0, spd: 0.80 * R.MAX_SPD, wreck: 0, ang: 0,
                      grace: 0, cool: 0, side: 1, w: 0.27, len: 400, phase: 0, dmg: 0,
                      from: 'test', onPlayer: true, tz: pz, tx: 0 };
          R.cops().push(k);
          window.__cop = k;
          window.__hold = setInterval(() => {
            R.setSpd(0.92 * R.MAX_SPD);
            // the wall holds its speed and its lanes; nothing else is on the road
            for(const c of R.traffic){
              if(wall.indexOf(c) >= 0){ c.spd = c.cruise = 0.30 * R.MAX_SPD; }
              else { c.z = R.pos + 26000; c.x = 2.4; }
            }
          }, 8);
          return true;
        }"""
        COPWATCH = """() => {
          const k = window.__cop, w = window.__wall;
          if(!k) return null;
          let inside = false, gap = 1e9;
          for(const c of w){
            const d = (c.z - k.z) - (c.len + k.len) / 2;
            if(d < gap) gap = d;
            if(Math.abs(c.x - k.x) < (c.w + k.w) / 2
               && Math.abs(c.z - k.z) < (c.len + k.len) / 2) inside = true;
          }
          return { spd: Math.round(k.spd), dmg: Math.round(k.dmg || 0),
                   wreck: +(k.wreck || 0).toFixed(2), gap: Math.round(gap),
                   wallSpd: Math.round(w[0].spd), inside: inside };
        }"""

        # THE ROAD HAS TO REPOPULATE FIRST. The approach above pushed every other car
        # far enough up the road to be culled, so the array is empty when this starts -
        # it is refilled by DRIVING, which is what lays the next wave.
        page.evaluate('() => { clearInterval(window.__hold);'
                      ' window.__hold = setInterval(() => window.__road.setSpd('
                      '0.6 * window.__road.MAX_SPD), 50); }')
        for _ in range(60):
            page.wait_for_timeout(250)
            if page.evaluate('() => window.__road.traffic.length') >= 4:
                break
        ok(page.evaluate(WALL, [9000]) is True, 'the forced-lift scene was built',
           '%d cars on the road' % page.evaluate('() => window.__road.traffic.length'))
        page.wait_for_timeout(200)
        opened = page.evaluate(COPWATCH)
        hit = 0
        slowest = opened['spd']
        for _ in range(70):
            page.wait_for_timeout(100)
            w = page.evaluate(COPWATCH)
            if w['inside']:
                hit += 1
            slowest = min(slowest, w['spd'])
        end = page.evaluate(COPWATCH)
        page.evaluate('() => clearInterval(window.__hold)')
        print('  ..    a cruiser closing on three cars abreast: opened at %d, slowed to %d,'
              ' the wall runs at %d'
              % (opened['spd'], slowest, end['wallSpd']))
        print('  ..    %d frames inside the wall, %d damage taken' % (hit, end['dmg']))

        # IT HAS TO LIFT TO THE WALL'S OWN SPEED, near enough. A cruiser that merely
        # eases a little and still arrives has not navigated anything.
        ok(slowest <= end['wallSpd'] * 1.25,
           'a cruiser lifts for traffic it cannot go round',
           'slowed to %d against a wall running at %d' % (slowest, end['wallSpd']))
        ok(end['dmg'] == 0 and end['wreck'] <= 0,
           'and it does not destroy itself on it',
           '%d damage, wreck %s' % (end['dmg'], end['wreck']))

        # ---- AND THE BOX DOES NOT WAIT FOR YOU TO STOP (RLG-158) ---------------
        # Owner, 2026-09-07: "their main method of attack should be to surround you and
        # slow you down so that you get arrested/busted." The box was written to make
        # the BUSTED rule reachable and asked whether the player was under a tenth of
        # top speed - which makes being surrounded the CONSEQUENCE of stopping rather
        # than the method of causing it.
        #
        # THE FLAG IS READ, NOT THE POSITIONS. Where a cruiser sits is the result of the
        # decision, and several other things put one off to the side - the cooling phase
        # already stations a cruiser wide. A check reading positions could not tell the
        # box from a car that had peeled off.
        page.evaluate("""() => {
          const R = window.__road;
          clearInterval(window.__hold);
          const pz = R.pos + R.PLAYER_Z;
          R.copsClear();
          for(let i = 0; i < 3; i++)
            R.cops().push({ z: pz - 300 + i * 200, x: 0, spd: 0.9 * R.MAX_SPD, wreck: 0,
                            ang: 0, grace: 0, cool: 0, side: 1, w: 0.27, len: 400,
                            phase: 0, dmg: 0, from: 'test', onPlayer: true, tz: pz, tx: 0 });
          window.__hold = setInterval(() => {
            R.setSpd(0.85 * R.MAX_SPD);
            for(const k of R.cops()){ k.cool = 0; k.onPlayer = true; k.tz = R.pos + R.PLAYER_Z; }
          }, 8);
        }""")
        boxed = 0
        wide = 0.0
        for _ in range(40):
            page.wait_for_timeout(100)
            c = page.evaluate('() => window.__road.copCensus()')
            boxed = max(boxed, c.get('boxing', 0))
            wide = max(wide, c.get('boxWide', 0) or 0)
        page.evaluate('() => clearInterval(window.__hold)')
        moving = page.evaluate('() => Math.round(window.__road.spd)')
        px = page.evaluate('() => +window.__road.playerX.toFixed(2)')
        # the widest station is a DISTANCE FROM THE PLAYER, so it is only readable
        # next to where the player was - a car pinned wide of a player who has drifted
        # to the far lane is a large number and an ordinary station
        print('  ..    at %d units a second, %d cruisers took a station, the widest %.2f'
              ' lanes from a player sitting at %.2f' % (moving, boxed, wide, px))
        ok(boxed >= 1, 'the police take stations around a car that is still moving',
           '%d on station at %d units a second' % (boxed, moving))
        ok(errs == [], 'no page errors', errs[0][:120] if errs else '')
        ctx.close()
        b.close()
    srv.shutdown()
    print()
    print('  ' + ('the traffic can see the police' if not bad else str(bad) + ' FAILURES'))
    return 1 if bad else 0


sys.exit(main())
