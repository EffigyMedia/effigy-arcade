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
        # AND IT DOES NOT ARRIVE ANYWAY. A driver that lifts or edges over and then
        # drives into the back of it has not avoided anything - so the meeting has to
        # be got THROUGH, not merely started.
        ok(met['hits'] == 0, 'and it never occupies the same road as the cruiser',
           '%d frames inside it' % met['hits'])
        ok(met['passed'], 'and the approach actually completed',
           'the car never reached the cruiser, so nothing was avoided')
        ok(errs == [], 'no page errors', errs[0][:120] if errs else '')
        ctx.close()
        b.close()
    srv.shutdown()
    print()
    print('  ' + ('the traffic can see the police' if not bad else str(bad) + ' FAILURES'))
    return 1 if bad else 0


sys.exit(main())
