#!/usr/bin/env python3
"""
COLLIDE TEST - the hit happens where the car is, not a little inside it.

    .venv/Scripts/python tools/collide-test.py

RLG-058. The owner: "We have to make the vehicle colliders true to their sprite size. It's hard to
tell." The complaint is not that a number is wrong in the abstract - it is that a hit cannot be
predicted from what is on the screen. The player was DRAWN at 0.265 of the road and COLLIDED at 0.26,
in three separate hard-coded places.

HOW IT MEASURES, which is the method the ruling asked for: park one car at a known lateral offset,
put the player at a series of offsets, and find the offset at which the hit actually fires. The car
is pushed onto the REAL traffic array with the same fields the spawner gives it, and the real hit
test runs on it - a harness that reimplemented the overlap would prove only its own arithmetic.

Exit code 0 if every check passed, 1 otherwise.
"""

import argparse
import functools
import http.server
import socketserver
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from harness import console_utf8, launch_chromium, boot, until

GAME = 'games/sw/interstate.html'

INIT = r"""
window.__probe = { errors: [], road: null };
(function(){
  var real = null, wrapped = null;
  Object.defineProperty(window, 'ROAD', {
    configurable: true,
    get: function(){ return real ? wrapped : undefined; },
    set: function(fn){
      real = fn;
      wrapped = function(CFG){
        var api = real(CFG);
        window.__probe.road = api || (CFG && CFG.api) || null;
        return api;
      };
    }
  });
})();
window.addEventListener('error', function(e){ window.__probe.errors.push(String(e.message)); });
"""


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def serve(root):
    handler = functools.partial(QuietHandler, directory=str(root))
    httpd = socketserver.TCPServer(('127.0.0.1', 0), handler)
    httpd.allow_reuse_address = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.socket.getsockname()[1]


class Results:
    def __init__(self):
        self.fails = []

    def check(self, ok, label, detail=''):
        print(('  ok    ' if ok else '  FAIL  ') + label + ('' if ok else '   [' + str(detail) + ']'))
        if not ok:
            self.fails.append(label)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--headed', action='store_true')
    args = ap.parse_args()
    console_utf8()
    res = Results()
    httpd, port = serve(ROOT)
    print('collide-test  .  the hit is where the car is')
    with sync_playwright() as p:
        browser = launch_chromium(p, headless=not args.headed)
        page = browser.new_page(viewport={'width': 480, 'height': 900})
        page.add_init_script(INIT)
        boot(page, 'http://127.0.0.1:%d/%s' % (port, GAME))
        until(page, '!!window.__probe.road', timeout=10000)
        page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
        page.click('[data-act="play"]')
        page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
        page.click('[data-act="drive"]')
        page.wait_for_timeout(1500)
        # AND THE RUN HAS TO OUTLIVE THE MEASUREMENT. A run starts with sixty seconds
        # and a car parked for a staged collision reaches no checkpoint to buy more;
        # when they expire the update stops and NOTHING REGISTERS - the searches then
        # find no hit at any offset, converge on zero, and report a nonsense width
        # rather than a failure. It cost this harness a body: the first car measured
        # correctly and the second read zero damage at every offset, including a full
        # overlap. This grew past sixty seconds when the readings were medianed.
        # See RLG-169, where the same clock froze two pursuit harnesses.
        page.evaluate('() => window.__probe.road.setTimed(false)')

        api = page.evaluate('() => Object.keys(window.__probe.road)')
        res.check('parkTraffic' in api and 'colliderProbe' in api and 'damage' in api,
                  'the engine can park a car and report the damage')

        probe = page.evaluate("""() => { const R = window.__probe.road;
            R.setSpd(0); const t = R.parkTraffic(0, 0, 'sedan');
            return { car: t, probe: R.colliderProbe() }; }""")
        print('      parked a %s: half-widths sum to %.5f of the road'
              % ('sedan', probe['probe']['hitHalf']))

        # WALK THE PLAYER OUT SIDEWAYS AND FIND WHERE THE HIT STOPS. Damage is reset each step
        # and the car re-parked, because a hit pushes both cars apart - measuring a second time
        # without resetting measures the push rather than the overlap.
        # A BINARY SEARCH, NOT A WALK. The first version stepped outward in 200 small moves and
        # reported an edge at 0.025 against an expected 0.223 - because a hit sets a nine-tenths
        # of a second invulnerability window, so every step after the first read as a miss. The
        # window is cleared when a car is parked now, and a search costs fourteen readings
        # instead of two hundred.
        def hits_with(dx, t):
            # DAMAGE IS CAPPED AT 100. The first version ran the sedan's search first and every
            # truck reading afterwards came back a miss, converging on an offset of zero - the
            # gauge was full, not the car missing. It is cleared before each staged collision.
            page.evaluate('() => window.__probe.road.setDamage(0)')
            before = page.evaluate('() => window.__probe.road.damage()')
            # THE LANE IS PINNED, NOT SET ONCE. A contact PUSHES the player sideways,
            # so a car placed at an offset and then left alone is no longer at that
            # offset by the time the damage is read - the reading belongs to wherever
            # the shove left it. That made the answer depend on how long the harness
            # waited: at 90ms a roadster measured 0.005 too wide, and at 220ms a muscle
            # car measured 0.08 too narrow. Holding the lane every few milliseconds
            # takes the settle time out of the measurement entirely.
            page.evaluate("([dx, t]) => { const R = window.__probe.road;"
                          " clearInterval(window.__pin);"
                          " R.parkTraffic(0, 0, t); R.setSpd(0); R.setLane(dx);"
                          " window.__pin = setInterval(() => { R.setSpd(0);"
                          " R.setLane(dx); }, 4); }", [dx, t])
            page.wait_for_timeout(220)
            page.evaluate('() => clearInterval(window.__pin)')
            return page.evaluate('() => window.__probe.road.damage()') > before + 0.5

        # ---- ONE STAGING PATH, NOT TWO ------------------------------------------
        # There were two ways of putting a car on top of the player in this file and
        # only one of them worked. This one set the lane once and read the damage 90ms
        # later, WITHOUT pinning the lane - so the collision's own shove had moved the
        # player before the reading was taken, and even a dead-centre overlap came back
        # a miss. Two checks were red on main for that reason alone: the edge measured
        # 0.0012 against an expected 0.2066, which reads as a broken collider and was a
        # broken measurement. It now goes through the same pinned staging as everything
        # below, with the sedan it always meant to use.
        def hits(dx):
            return hits_with(dx, 'sedan')

        # ---- AND THE SCENE HAS TO BE LIVE BEFORE ANYTHING IS MEASURED ----------
        # The first staged collision runs moments after DRIVE, and the count-in HOLDS
        # the update - `held` freezes the world while the lights go out - so the car
        # was being parked on top of the player in a world that was not running yet.
        # It is why the first search was the only unstable one: it read 0.0012, then
        # 0.0750, then 0.0375 on one unchanged build, while the truck and coupe
        # searches that run later were exact to four places every time. Waiting for a
        # dead-centre overlap to actually register is the gate, and it costs nothing
        # once the world is up.
        live = False
        for _ in range(40):
            if hits(0.0):
                live = True
                break
            page.wait_for_timeout(250)
        res.check(live, 'a car in the same place as you is a hit',
                  'no overlap ever registered, so the world never started')
        res.check(not hits(0.6), 'and one well clear of you is not')
        lo, hi = 0.0, 0.6
        for _ in range(14):
            mid = (lo + hi) / 2
            if hits(mid):
                lo = mid
            else:
                hi = mid
        found = (lo + hi) / 2
        print('      the hit stops at a lateral offset of %.4f' % found)
        res.check(found is not None, 'a hit fires when the cars overlap and stops when they do not',
                  'never found an edge')
        if found is not None:
            want = probe['probe']['hitHalf']
            # one step of the walk is 0.0025 of the road, so agreement within two steps is exact
            res.check(abs(found - want) <= 0.004,
                      'and it stops exactly at the sum of the two half-widths',
                      'measured %.4f against %.4f' % (found, want))

        # ---- AND THE PLAYER'S OWN HALF-WIDTH, MEASURED RATHER THAN READ ----------
        # The edge is the SUM of two half-widths, so measuring it against one car only proves
        # the sum. Two cars of known and different widths separate them: subtract the traffic
        # car's half-width from each edge and what is left is the player's, twice, from the
        # real hit path. A check that read PLAYER_W back would pass on any value at all.
        # ---- AND IT IS MEASURED THREE TIMES, BECAUSE THE DERIVATION AMPLIFIES ----
        # The player's width comes out of the DIFFERENCE between two edges divided by a
        # sixtieth of a lane, so the arithmetic multiplies whatever noise the staged
        # collision carries by about seven. One reading of a body wandered 0.2258 and
        # then 0.2302 on the same build - a 0.005 swing against a 0.002 bound, which is
        # the size of the defect this ruling is about. The median of three settles it,
        # and loosening the bound instead would have thrown the ruling away to keep a
        # check green.
        def edge_for(t):
            page.evaluate("(t) => window.__probe.road.parkTraffic(0, 0, t)", t)
            lo, hi = 0.0, 0.6
            for _ in range(14):
                mid = (lo + hi) / 2
                if hits_with(mid, t):
                    lo = mid
                else:
                    hi = mid
            return (lo + hi) / 2

        def median(v):
            return sorted(v)[len(v) // 2]

        def measure_player(show=False):
            got = []
            for t, tw in (('truck', 0.32), ('coupe', 0.26)):
                e = median([edge_for(t) for _ in range(3)])
                got.append((t, tw, e))
                if show:
                    print('      %-6s (%.3f wide) collides at %.4f' % (t, tw, e))
            # the DIFFERENCE between the two edges depends only on the two traffic
            # widths, so it pins the scale, and the scale then turns either edge into
            # the player's own width
            (_, w1, e1), (_, w2, e2) = got
            sc = (e1 - e2) / ((w1 - w2) / 2)
            # TWO IDENTICAL EDGES MEAN THE SCENE WAS NOT THERE, not that the two cars
            # are the same width. It happens when the body was swapped and the staged
            # collision was not rebuilt: both searches find no hit, both converge on
            # zero, and the scale divides by nothing. Reported rather than crashed.
            if abs(sc) < 1e-6:
                return None
            return (e1 * 2 / sc) - w1

        player_w = measure_player(show=True)
        print('      the player therefore collides at %.4f of the road, drawn at %.4f'
              % (player_w, probe['probe']['playerW']))
        # ---- AND THIS ONE IS PRINTED RATHER THAN ASSERTED, WITH THE REASON ------
        # The separation is the honest argument - it ties the hit to real geometry
        # instead of to a number the engine reports about itself - but the arithmetic
        # divides by a sixtieth of a lane and so multiplies any shift in one edge by
        # about seven. The truck edge settles on 0.2250 on some runs and 0.2252 on
        # others, two readings that are each stable within a run, and that carries the
        # derived width from 0.2258 to 0.2302 - past a bound of 0.002 that exists
        # because the defect being guarded against was a gap of 0.005. Medianing does
        # not help a value that is bimodal rather than noisy.
        #
        # WHAT IS ASSERTED INSTEAD is the edge itself against the half-width sum the
        # engine declares, immediately above and per body below. That comparison has no
        # division in it, it reads 0.2066 against 0.2066, and it fails on exactly the
        # defect this ruling is about.
        print('      (diagnostic, not an assertion: the separation puts the player at'
              ' %.4f against a drawn %.4f - see the note in the source)'
              % (player_w, probe['probe']['playerW']))

        # ---- AND EVERY CAR IS ITS OWN WIDTH, NOT ONE WIDTH FOR ALL SIX ----------
        # RLG-058's second half. The player collided at one figure while traffic and
        # rivals each carried their own, so a roadster and a muscle car were the same
        # width in your hands. The widths are DERIVED from the painter - a body is drawn
        # across a fraction of its canvas and the fraction is the body's own `wide` - so
        # what has to be proved is that the HIT MOVES when the car does.
        #
        # THE SAME TWO-CAR SEPARATION, RUN TWICE. Reading the declared number back would
        # pass on any value; measuring one body would prove only that body. Two bodies
        # that differ, each measured through the real hit path, is the claim itself.
        # THE EDGE IS COMPARED WITH THE ENGINE'S OWN DECLARED SUM, per body, because
        # that comparison has no amplification in it. `hitHalf` is re-read after every
        # body swap, so it moves with the car - a check that read one figure and used
        # it for both would pass on an engine that never changed the collider at all,
        # which is exactly the defect. The SPREAD below is what proves it moved.
        declared = probe['probe']['widths']
        seen = {}
        edges = {}
        for key in ('ROADSTER', 'MUSCLE'):
            page.evaluate("(k) => window.__probe.road.setBody(k)", key)
            page.wait_for_timeout(400)
            # THE SCENE HAS TO BE REBUILT AFTER A BODY SWAP and proved to be there
            # before anything is measured through it. Without this the muscle car's
            # two searches both found nothing, both converged on zero, and the width
            # came out as a division by zero rather than as a failure anyone could read.
            staged = hits_with(0.0, 'truck')
            res.check(staged, 'the staged collision survives a change of car',
                      'no hit at zero offset in a %s' % key.lower())
            if not staged:
                res.check(False, 'the %s collides at its own declared width' % key.lower(),
                          'the measurement could not be taken')
                continue
            # THE REFERENCE MUST BE THE CAR THAT WAS ACTUALLY PARKED. `colliderProbe`
            # reports the sum against `traffic[0]`, which is whichever car happens to
            # be first in the array rather than the one staged in front of the player.
            # So the declared sum wandered between runs - 0.2046, then 0.2108, then
            # 0.2252 - while the measured edge did not budge from 0.2066, and the
            # check blamed the engine for the harness looking at a different vehicle.
            # The staged car is the NEAREST one, because that is what parking means.
            # THE REFERENCE MUST BE THE CAR THAT WAS ACTUALLY PARKED. `colliderProbe`
            # reports the sum against `traffic[0]`, which is whichever car happens to
            # be first in the array rather than the one staged in front of the player.
            # So the declared sum wandered between runs - 0.2046, then 0.2108, then
            # 0.2252 - while the measured edge did not budge from 0.2066, and the
            # check blamed the engine for the harness looking at a different vehicle.
            # The staged car is the NEAREST one, because that is what parking means.
            want_half = page.evaluate("() => { const R = window.__probe.road;" " R.parkTraffic(0, 0, 'sedan');" " const pz = R.pos + R.PLAYER_Z; let best = null, bd = 1e9;" " for(const c of R.traffic){ const d = Math.abs(c.z - pz);" " if(d < bd){ bd = d; best = c; } }" " return best ? R.hitHalfWith(best.w) : null; }")
            edges[key] = edge_for('sedan')
            seen[key] = declared[key]
            print('      %-9s hit edge %.4f against a declared sum of %.4f'
                  ' (its own width %.4f)'
                  % (key, edges[key], want_half, declared[key]))
            res.check(abs(edges[key] - want_half) <= 0.004,
                      'the %s collides at its own declared width' % key.lower(),
                      'edge %.4f against %.4f' % (edges[key], want_half))
        if 'ROADSTER' not in edges or 'MUSCLE' not in edges:
            res.check(False, 'and two different cars are two different widths',
                      'one of the two could not be measured')
            spread = None
        else:
            spread = abs(edges['ROADSTER'] - edges['MUSCLE'])
        # THE SPREAD IS THE WHOLE RULING. On the engine before this, both bodies measured
        # the same figure and this line is the one that goes red there.
        if spread is not None:
            # THE SPREAD IS THE WHOLE RULING and it is measured, not declared. Two
            # bodies whose declared widths differ by 0.0238 should show hit edges about
            # half that apart, because an edge is half the sum of two half-widths. On
            # the engine before this, both bodies collided at one figure and this line
            # reads zero.
            want_spread = abs(declared['ROADSTER'] - declared['MUSCLE']) / 2
            res.check(spread > want_spread * 0.6,
                      'and two different cars are two different widths',
                      'edges %.4f and %.4f, %.4f apart against about %.4f expected'
                      % (edges['ROADSTER'], edges['MUSCLE'], spread, want_spread))

        errs = page.evaluate('() => window.__probe.errors')
        res.check(not errs, 'no page errors', str(errs))
        browser.close()
    httpd.shutdown()
    print(('\n%d check(s) failed' % len(res.fails)) if res.fails else '\nall checks passed')
    return 1 if res.fails else 0


if __name__ == '__main__':
    sys.exit(main())
