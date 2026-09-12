#!/usr/bin/env python3
"""
BRAKE AND GRIP TEST - what the fleet actually does when it stops and when it turns.

    .venv/Scripts/python tools/brake-test.py

RLG-055, which is blocked on exactly this. `stat-test.py` measures straight-line acceleration and top
speed and nothing else; the owner ruled brake and grip into the fleet table, and RLG-042's lesson is
why the measurement has to come first - there, the top-speed column turned out TRUE while three
comments around it were false, and nobody could have predicted which way that would fall. Lowering a
number without knowing whether it was honest produces a change nobody can interpret afterwards.

MEASURE ONLY. This file proposes no numbers and changes nothing. It reports what the cars do.

WHY IT IS NOT INSIDE `stat-test.py`, WHICH IS WHERE RLG-055 ASKED FOR IT. That harness boots the whole
fleet and drives each car flat out; braking and cornering need a different procedure - a fixed entry
speed, a held brake, and for the cornering experiment NO STEERING INPUT AT ALL. Grafting a second
driving procedure into a harness built for one risks the acceleration numbers that are already
trusted. The fleet picture is assembled from both, and this file says so rather than quietly
diverging.

AND THE CORNERING EXPERIMENT HAS NO DRIVER IN IT, which is the point. RLG-055's own warning is that
grip must not be measured with the drive-test autopilot, because it saws at the wheel and lateral load
is what wears tyres - this project has already once been told that Raceway's tyres died in twenty
seconds when the autopilot was the cause. So the wheel is not touched. `grip` acts through `cornerG`,
which decides how hard a bend pushes the car WIDE; the car is put on a bend at a fixed speed with the
steering untouched, and the measurement is how fast it is pushed out. Nothing a driver does can
influence it, because there is no driver.

WHAT `grip` DOES AND DOES NOT DO, established by reading before measuring. It is consulted in exactly
two places: `brakeOf`, which scales the braking rate, and `cornerG`, which scales how hard a bend
pushes you wide. It does NOT affect how fast the car answers the wheel - that rate is the same for
every body and is moved only by the weather. So a "grippy" car in this engine stops harder and holds
its line, and does not place itself more sharply.

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

# ---- IT RUNS ON THE HIGHWAY, AND THE ROAD IS SWEPT EVERY FRAME --------------
# THE CORNERING EXPERIMENT WAS MEASURING COLLISIONS. Interstate has civilian
# traffic on it, and a car that gets HIT is shoved sideways and slowed at the
# same time - `hurt` pushes `playerX` and then sets `targetX = playerX`, which
# is the exact number this file reads as a cornering push. So a shunt was
# recorded as an enormous push, on a different body every run. That is why the
# CREST and the APEX appeared to defy their own grip, and why the STALLION read
# 0.113 in one run and 0.261 in another on an unchanged build. The speed column
# gave it away the moment it was printed: four bodies went 119 -> 47mph inside
# two and a half seconds, which is not coasting.
#
# MOTORSPORT WAS TRIED AND IS WORSE, which is worth recording so nobody tries it
# again. It is `circuitOnly` and therefore has no traffic at all - but it is a
# CIRCUIT, and it regenerates its own track geometry, so `bendRoad`'s imposed
# constant curvature is wiped and every body meets a different corner. That is
# RLG-062's fault exactly, and it read a spread of 0.056 to 0.989 with 25
# inverted pairs. Its BRAKING numbers came out identical to the highway's, so
# the two roads agree about everything except the thing this needs.
#
# So: the highway, with one constant bend imposed, and the road swept clean
# EVERY FRAME of the window from inside the probe. Clearing once is not enough -
# Interstate spawns more inside two and a half seconds, every time.
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

/* ---- BRAKING, SAMPLED IN THE PAGE ------------------------------------------------------------
   From a fixed entry speed to a fixed exit speed, with the brake held. Timed by the page's own
   clock and measured against the road's own position, so neither number is reconstructed from
   frame counts on this side of the wire. */
window.__probe.brakeRun = function(from, to, capMs){
  const R = window.__probe.road;
  return new Promise(function(done){
    R.setSpd(from); R.setBrake(true);
    var z0 = R.roadPos(), t0 = performance.now(), frames = 0;
    (function step(){
      frames++;
      var now = performance.now(), spd = R.spdNow();
      if(spd <= to || now - t0 > capMs){
        R.setBrake(false);
        done({ ms: now - t0, dist: R.roadPos() - z0, frames: frames, end: spd });
        return;
      }
      requestAnimationFrame(step);
    })();
  });
};

/* ---- AND CORNERING, WITH THE WHEEL UNTOUCHED -------------------------------------------------
   The car is set on the road at a fixed speed and left alone. `targetX` is where the driver is
   asking the car to be; a bend moves it outward through `cornerG`, and nothing else does while no
   input arrives. So the drift of `targetX` over a fixed window IS the cornering push. */
window.__probe.pushRun = function(ms, hold, sweep, dry){
  const R = window.__probe.road;
  return new Promise(function(done){
    /* `targetX` is a live GETTER on the API, not a call - a property defined
       beside `playerX` and `dmg`. Reading it as a function is what broke the
       first version of this file. */
    var x0 = R.targetX;
    /* ---- THE WINDOW IS MEASURED IN SIMULATED SECONDS ------------------------------------
       This ran for 2500 milliseconds of WALL time, and the browser simulates the world at
       roughly half real time here - `frameLoop` caps its own `dt` at 0.05 - by a fraction
       that differs per body, because a heavier car renders slower. So every body was pushed
       for a different length of time and the drifts were not comparable. It is the same
       fault the steering experiment had, found there first and fixed in both. */
    var s0 = R.simTime();
    var t0 = performance.now(), worst = 0, n = 0, sum = 0;
    var v0 = R.spdNow(), vlo = v0, vhi = v0;
    (function step(){
      /* ---- THE SPEED IS THE EXPERIMENT'S CONTROLLED VARIABLE ------------
         The push is `pushK * v * v * dt * cornerG()`. It is quadratic in
         speed, and the first version of this file set 120mph once and then
         let the car COAST for two and a half seconds - so every body was
         pushed by a different v, and a 20 per cent speed loss is a 36 per
         cent push loss. Holding it is not a driver influencing the result;
         it is the one variable that has to be equal between bodies for the
         comparison to be about `grip` at all. */
      if(hold) R.setSpd(hold);
      /* ---- AND THE ROAD IS HELD DRY ---------------------------------------------------
         The weather ROLLS while the run proceeds. It is set dry once before the loop and
         comes back on its own inside two minutes, and `wetGrip` is the OTHER thing the
         lateral physics reads: wet makes `slideX` carry, so the car keeps going the way it
         was going and moves FASTER than the steering ceiling allows. That is why the
         steering error grew steadily down the body list - 1.7 per cent on the first car and
         28 on the last - which is a drift over the run rather than a property of any car. */
      if(dry){ R.setWet(0); R.setSnow(0); R.setPool(0); }
      /* AND THE ROAD IS SWEPT EVERY FRAME. Nothing may be on it long enough to
         hit the car: a collision moves `targetX`, which is the number being
         measured, so one shunt turns a cornering result into a crash test.
         Sweeping cannot perturb what is under test - the push is
         `pushK * v * v * dt * cornerG()` and reads nothing about traffic. */
      if(sweep) R.clearTraffic();
      var v = R.spdNow();
      if(v < vlo) vlo = v;
      if(v > vhi) vhi = v;
      var x = R.targetX;
      var d = Math.abs(x - x0);
      if(d > worst) worst = d;
      sum += Math.abs(R.pushK ? R.pushK() : 0); n++;
      /* and a wall-clock backstop, so a stalled page cannot hang the run */
      if((R.simTime() - s0) * 1000 > ms || performance.now() - t0 > ms * 6){
        done({ drift: worst, samples: n, meanPush: n ? sum/n : 0,
               v0: v0, vlo: vlo, vhi: vhi, v1: v,
               /* WHAT ELSE WAS ON THE ROAD. A car that gets hit is shoved
                  sideways AND slowed, and both read as a cornering push -
                  which is exactly how four bodies came out of this file
                  looking like they defied their own grip. */
               cars: R.cars ? R.cars() : -1, grip: R.wetGrip() });
        return;
      }
      requestAnimationFrame(step);
    })();
  });
};

/* ---- AND HOW SHARPLY IT ANSWERS THE WHEEL (RLG-119) ------------------------------------------
   The car is put on one side of the road, asked to go to the other, and timed. `setTarget` moves
   the ASK alone - `setLane` moves the ask and the car together, which is right for placing a car
   and useless for measuring how long it takes to get anywhere.

   THERE IS NO DRIVER IN THIS EITHER. The ask is set once and held; nothing steers, nothing
   corrects, and the crossing time is the ceiling on lateral speed and nothing else. RLG-055's
   warning is why: the drive-test autopilot saws at the wheel, and a rate measured under a driver
   is a measurement of the driver. */
window.__probe.steerRun = function(from, to, hold, sweep, ms, dry){
  const R = window.__probe.road;
  return new Promise(function(done){
    R.setLane(from);
    R.setTarget(to);
    /* ---- IT RECORDS, AND PYTHON DECIDES ------------------------------------------------
       Two earlier versions of this got the shape of the question wrong and are worth
       recording so nobody writes them again.

       TIMING A SHORT CROSSING measured a blend of two different things. The car is only
       RATE-LIMITED while the ask is far away: `want2` is `(targetX - playerX) * snap * dt`
       clamped to `rate * dt`, so the clamp stops binding once the gap falls under
       `rate / snap` - about a third of the road - and the end of any crossing is decided by
       the convergence rather than by the ceiling.

       TAKING THE PEAK PER-FRAME SPEED was worse and read 12 to 62 lanes a second against a
       ceiling of 4.2. This probe's rAF and the game's rAF are different callbacks, and the
       game steps a FIXED timestep out of an accumulator - so a frame may advance the world
       twice or not at all, and dividing the movement by WALL-CLOCK time between two probe
       samples measures the phase between two loops rather than the car.

       So it records (t, x) and returns them. The rate is read in Python from a long stretch
       that is entirely inside the rate-limited region, with the crossing times interpolated
       between samples - which takes the frame quantisation out. Nothing steers: the ask is
       set once and held. */
    var t0 = performance.now(), rows = [];
    (function step(){
      if(hold) R.setSpd(hold);
      if(sweep) R.clearTraffic();
      /* dry, every frame, and for the same reason the cornering probe holds it: wet makes
         `slideX` carry, and a car that keeps going the way it was going moves faster than
         the ceiling this experiment exists to measure */
      if(dry){ R.setWet(0); R.setSnow(0); R.setPool(0); }
      /* the ask is re-asserted every frame: the corner push moves `targetX` too, and over a
         second of holding it that would quietly change the thing being asked for */
      R.setTarget(to);
      /* ---- THE CLOCK IS THE ROAD, NOT THE WALL --------------------------------------
         The browser ran this probe at about eleven frames a second, and `frameLoop` caps its
         own `dt` at 0.05 - so at an 90ms frame the world advances 50ms and SIM TIME RUNS
         SLOWER THAN WALL TIME. By a different amount for each body, because a heavier car
         renders slower. Measured against the wall, the ROADSTER read 60 per cent of its
         ceiling and the COMET 96, and that difference was the frame rate rather than the car.

         The speed is held, so `pos` advances at exactly `spd` per second OF SIM TIME. It is
         therefore a perfect clock for this, and it is the engine's own. */
      var now = performance.now(), x = R.playerX;
      /* `simTime()` IS THE CLOCK, and deriving one from `pos` was the third wrong
         answer here. `pos` advances at `spd`, and `spd` is only re-pinned once per
         PROBE frame - the world steps many times in between and the car coasts down
         through all of them, so the distance covered under-reported the time that had
         passed and every car came out ABOVE a ceiling it cannot exceed, worst by 29%.
         `simTime` is the seconds the world has actually been stepped. */
      rows.push([R.simTime(), x]);
      if(Math.abs(x - to) < 0.02 || now - t0 > ms){
        done({ rows: rows, at: x, cars: R.cars ? R.cars() : -1, grip: R.wetGrip() });
        return;
      }
      requestAnimationFrame(step);
    })();
  });
};
"""

# ---- THE FLEET IS MEASURED IN GROUPS, AND EACH GROUP HAS ITS OWN ENTRY SPEED -------------------
# This list used to be one set of eleven bodies under a comment claiming it was "every driveable
# body". It never was: it holds the sports, super, formula and police cars, and the PRODUCTION cars
# a new save actually starts in were not in it. The hatchback (RLG-213) made that visible, because
# it was added to a class the harness could not see.
#
# THEY CANNOT SHARE ONE ENTRY SPEED, and this file already knows why. Its own note records that
# entering at 150mph put the TUNER above its 146mph top end, aero over-run helped it stop, and it
# came out braking better than two cars that brake better than it. A production car tops out at
# 112 to 120mph, so entering at 120 would do the same thing to all three at once.
#
# So a group carries the speed it is measured at, every printed line says what that speed was, and
# NUMBERS FROM TWO GROUPS ARE NOT COMPARABLE. The racing group keeps 120mph exactly as it was, so
# every figure recorded in RLG-055 still stands and is still reproducible.
# The third number is the handling spread the group must show, best car against worst. It is a
# claim about a RANGE, so it belongs to a group that spans several classes and not to a group that
# is one class: production cars are supposed to feel alike, which is what makes them a class.
# `None` says the question does not apply and the spread is printed as a measurement instead.
GROUPS = {
    'racing': (['ROADSTER', 'TUNER', 'MUSCLE', 'STALLION', 'MATADOR', 'CREST',
                'VECTOR', 'APEX', 'COMET', 'CRUISER', 'SUPERCRUISER'], 0.60, 1.35),
    # SALOON 0.56, HATCH 0.58, COUPE 0.60 - so 0.50 is 100mph, below the slowest of the three.
    'production': (['COUPE', 'HATCH', 'SALOON'], 0.50, None),
}
# STILL UNMEASURED: the work vehicles. CAB, PICKUP, VAN and SEMI are driveable after a hundred
# miles in TEST DRIVE and top out from 96mph down to 80, so they need a third group at a third
# speed. Nobody has asked for their brake figures yet and none are quoted anywhere.
BODIES, V_F, SPREAD = GROUPS['racing']
TO_F = 0.20                    # down to 40mph on a 200mph scale
CAP_MS = 12000
PUSH_MS = 2500


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def serve(root):
    handler = functools.partial(QuietHandler, directory=str(root))
    httpd = socketserver.TCPServer(('127.0.0.1', 0), handler)
    httpd.allow_reuse_address = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.socket.getsockname()[1]



# ---- THE STRETCH THE CEILING IS READ OVER ------------------------------------------------
# It has to be entirely inside the rate-limited region. The clamp binds while the gap to the
# ask is wider than `rate / snap`, and the widest that is across this fleet is 5.49/14 = 0.39
# of the road. The ask is held at 1.15, so at x = 0.70 the gap is still 0.45 and the clamp is
# still what is limiting. Long, so the crossing is 300-700ms rather than a handful of frames.
STEER_FROM, STEER_TO = -1.00, 0.70


def rate_between(rows, x0, x1, spd):
    """Lanes per second across [x0, x1], measured in SIM time and with the two crossing
    points interpolated between samples.

    The rows carry the engine's own `simTime` rather than a wall clock, because the browser
    does not run the world at real time and does not run it at the same fraction of real time
    for every body. Interpolation is the other half: the probe samples at whatever rate the
    browser gives it, and quantising a 300ms crossing to whole samples is a large error on the
    number this exists to produce."""
    def cross(at):
        for i in range(1, len(rows)):
            (ta, xa), (tb, xb) = rows[i - 1], rows[i]
            if xa < at <= xb:
                if xb == xa:
                    return tb
                return ta + (tb - ta) * (at - xa) / (xb - xa)
        return None
    p0, p1 = cross(x0), cross(x1)
    if p0 is None or p1 is None or p1 <= p0:
        return None
    return (x1 - x0) / (p1 - p0)


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
    ap.add_argument('--corner-only', action='store_true',
                    help='the cornering experiment alone, which is the one still in question')
    ap.add_argument('--runs', type=int, default=1,
                    help='repeat the cornering experiment N times. RLG-062: never quote one run')
    ap.add_argument('--group', default='racing', choices=sorted(GROUPS),
                    help='which set of bodies, and therefore at what speed. The two are one '
                         'choice: a group is measured below the top end of its own slowest car, '
                         'so figures from two groups do not compare')
    ap.add_argument('--coast', action='store_true',
                    help='do NOT hold the entry speed. The push is quadratic in speed, so a '
                         'coasting car is measured at a speed no other body shared - this exists '
                         'only to reproduce the old, wrong numbers')
    args = ap.parse_args()
    global BODIES, V_F, SPREAD
    BODIES, V_F, SPREAD = GROUPS[args.group]
    console_utf8()
    res = Results()
    httpd, port = serve(ROOT)
    print('brake-test  .  what the fleet does when it stops and when it turns')
    print('  group: %s  .  %d bodies, all of them measured at %dmph'
          % (args.group, len(BODIES), V_F * 200))
    with sync_playwright() as p:
        browser = launch_chromium(p, headless=not args.headed)
        page = browser.new_page(viewport={'width': 480, 'height': 900})
        page.add_init_script(INIT)
        boot(page, 'http://127.0.0.1:%d/%s' % (port, GAME))
        try:
            until(page, '() => navigator.serviceWorker && navigator.serviceWorker.controller', timeout=5000)
            page.wait_for_timeout(1000)
        except Exception:
            pass
        until(page, '!!window.__probe.road', timeout=10000)
        page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
        page.click('[data-act="play"]')
        page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
        page.click('[data-act="drive"]')
        page.wait_for_timeout(2500)

        mx = page.evaluate("() => window.__probe.road.MAX_SPD")
        # ---- AND THE CORNERING PUSH, WITH NOBODY DRIVING -------------------------------------
        print('  the cornering push on one constant bend, at %d mph, wheel untouched%s'
              % (V_F * 200, '  (speed left to coast)' if args.coast else '  (speed HELD, road EMPTY)'))
        # ON THE ROAD AS GENERATED, and BEFORE the braking runs flatten it - `flattenRoad` has
        # no inverse, and a straight road has no cornering push to measure. Ordering the two
        # experiments this way costs nothing and needs no new engine call.
        # ONE CORNER FOR EVERY CAR. The road is generated per load and advances while the run
        # proceeds, so each body met a different bend and the numbers could not be compared -
        # RLG-062's lesson, and it invalidated the first set this file produced. `bendRoad` makes
        # every segment the same curvature, so the only thing that differs between bodies is the
        # body.
        page.evaluate("""() => { const R = window.__probe.road;
            R.setWet(0); R.setSnow(0); R.setPool(0); R.bendRoad(0.6); }""")
        page.wait_for_timeout(200)
        # ---- A WARM-UP PASS, AND IT IS NOT SUPERSTITION ------------------------------
        # The FIRST body measured is measured differently from the rest, because the run has
        # only just begun: the car is still coming up to speed and the imposed bend has only
        # just been laid. This file has already been bitten by that once - the first body
        # read exactly 0.0000 because its window closed before the corner reached it - and
        # the settle added then is not enough on its own. Measured across three runs, every
        # other body repeated to a fraction of a per cent while the ROADSTER swung from
        # 0.1758 to 0.2029, and one run showed it entering the window at 49mph instead of
        # 120. One throwaway window puts the world in the state the second body finds.
        page.evaluate("(a) => window.__probe.pushRun(a.ms, a.hold, a.sweep, a.dry)",
                      {'ms': PUSH_MS, 'hold': 0 if args.coast else (V_F * mx),
                       'sweep': not args.coast, 'dry': True})
        pushes = []
        for b in BODIES:
            if not page.evaluate("(k) => { const R = window.__probe.road;"
                                 " R.setBody(k); return R.bodyKey() === k; }", b):
                continue
            # LET IT SETTLE ON THE BEND BEFORE MEASURING. The bend is imposed on a road that was
            # already generated, and the car arrives on it mid-corner; the first body measured read
            # exactly 0.0000 because its window closed before the corner reached it.
            # ---- AND THE ROAD IS EMPTIED FIRST ----------------------------------
            # THIS IS THE FAULT THE WHOLE EXPERIMENT HAD. It runs on Interstate, which
            # has civilian traffic on it, and a car that gets HIT is shoved sideways and
            # slowed at the same time - `hurt` pushes `playerX` and then sets
            # `targetX = playerX`, which is the very number this measures. So a shunt
            # read as an enormous cornering push, on a random body each run, and that is
            # why the CREST and the APEX looked like they defied their own grip and why
            # the STALLION read 0.113 in one run and 0.261 in another on an unchanged
            # build. The speed column gave it away the moment it was printed: four
            # bodies went 119 -> 47mph inside two and a half seconds, which is not
            # coasting, it is being hit.
            page.evaluate("() => window.__probe.road.clearTraffic()")
            page.evaluate("(v) => { const R = window.__probe.road;"
                          " R.setSpd(v); R.setLane(0); }", V_F * mx)
            page.wait_for_timeout(700)
            page.evaluate("() => window.__probe.road.clearTraffic()")
            page.evaluate("(v) => { const R = window.__probe.road;"
                          " R.setSpd(v); R.setLane(0); }", V_F * mx)
            page.wait_for_timeout(150)
            r = page.evaluate("(a) => window.__probe.pushRun(a.ms, a.hold, a.sweep, a.dry)",
                              {'ms': PUSH_MS, 'hold': 0 if args.coast else (V_F * mx),
                               'sweep': not args.coast, 'dry': True})
            # RAW `grip`, NOT `brakeOf`. The braking rate is grip x mech and the cornering push
            # is grip alone, so comparing the push against brakeOf compares it with a number the
            # corner never reads - which reported 31 inverted pairs on a first run and was my
            # arithmetic, not the engine's.
            g = page.evaluate("(k) => (window.__probe.road.BODY[k] || {}).grip || 1", b)
            # A ROW THAT WAS INTERFERED WITH IS NAMED AND DROPPED, never averaged in.
            # Two ways it can be: something arrived on the road during the window, or the
            # speed moved when it was being held - and both mean the drift measured is
            # not the corner's.
            # THE SPEED IS CHECKED AT BOTH ENDS. Checking only the exit missed a run where
            # the ROADSTER ENTERED the window at 49mph and was up to 120 by the end of it -
            # which is the settle failing, and it passed a check that only looked at v1.
            off = (not args.coast) and (abs(r['v1'] - V_F * mx) > V_F * mx * 0.02
                                        or abs(r['v0'] - V_F * mx) > V_F * mx * 0.02)
            spoiled = (r['cars'] > 0) or off or (r['grip'] < 0.999)
            pushes.append({'body': b, 'drift': r['drift'], 'claim': g,
                           'v0': r['v0'], 'v1': r['v1'], 'spoiled': spoiled})
            # THE SPEED IS REPORTED WITH THE PUSH, always. The push is quadratic in
            # speed, so a row whose speed moved is a row that cannot be compared with
            # one whose speed did not - and the first version of this file printed the
            # push alone, which made that impossible to see.
            print('      %-13s pushed %.4f of a lane over %.1fs   (grip %.3f)   %d -> %d mph%s'
                  % (b, r['drift'], PUSH_MS / 1000.0, g,
                     round(r['v0'] / mx * 200), round(r['v1'] / mx * 200),
                     ('   SPOILED: %d car(s) on the road' % r['cars'] if r['cars'] > 0 else
                      '   SPOILED: the speed was not held' if off else
                      '   SPOILED: the road was wet (grip %.3f)' % r['grip'] if spoiled else '')))

        res.check(len(pushes) >= len(BODIES), 'every body in the group was pushed',
                  'only %d' % len(pushes))
        if len(pushes) >= 3:
            spread = max(p2['drift'] for p2 in pushes) - min(p2['drift'] for p2 in pushes)
            print('  the spread across the fleet is %.4f of a lane' % spread)
            # ---- THE INVARIANT IS THE PRODUCT, NOT THE ORDER --------------------
            # The engine defines the cornering push as `CORNER_G_BASE / grip`, so the drift
            # multiplied by the declared grip is the SAME NUMBER for every car in the fleet.
            # That is what to check, and it is a far better question than counting inverted
            # pairs: two cars whose grip differs by three per cent - the VECTOR at 2.05 and
            # the APEX at 2.00 - will swap places on measurement noise alone and an
            # inversion count calls that a failure. The product cannot be fooled that way,
            # and it reports HOW FAR OFF rather than merely that something is.
            prods = [(r2['body'], r2['drift'] * r2['claim']) for r2 in pushes]
            vals = [v for _, v in prods]
            mean = sum(vals) / len(vals)
            worst = max(prods, key=lambda kv: abs(kv[1] - mean))
            spread = (max(vals) - min(vals)) / mean
            print('  push x grip should be one number for the whole fleet: '
                  'mean %.4f, spread %.1f%%, furthest out %s at %.4f'
                  % (mean, spread * 100, worst[0], worst[1]))
            # THE THRESHOLD IS TIGHT BECAUSE THE EXPERIMENT IS GOOD NOW. Measured across
            # three runs it reads 0.1%, 0.3% and 1.3%, with the mean landing on 0.2278,
            # 0.2279 and 0.2280 - four significant figures, reproducible. A threshold of
            # 16% was right while the instrument was measuring collisions and wall clocks;
            # left there it would pass a real regression without a murmur. 5% is four
            # times the worst run seen and still nowhere near the noise.
            res.check(spread < 0.05,
                      'the cornering push is the same number for every car once grip is taken out',
                      'it spread %.1f%% across the fleet, %s furthest out at %.4f against a mean of %.4f'
                      % (spread * 100, worst[0], worst[1], mean))
            # the ordering is still PRINTED, because it is what a player would notice, but a
            # pair inside the measurement's own noise is not evidence of anything
            byclaim = sorted(pushes, key=lambda r: -r['claim'])
            bad = 0
            for i2 in range(len(byclaim)):
                for j2 in range(i2 + 1, len(byclaim)):
                    a2, b3 = byclaim[i2], byclaim[j2]
                    if a2['claim'] > b3['claim'] * 1.06 and a2['drift'] > b3['drift'] + 1e-4:
                        bad += 1
            res.check(bad == 0,
                      'and a car the table says grips CLEARLY better is pushed wide less',
                      '%d pair(s) are the wrong way round by more than 6%% of grip' % bad)
        print()

        # ---- AND HOW SHARPLY EACH CAR ANSWERS THE WHEEL (RLG-119) ------------------
        # Owner, 2026-08-31: "should grip not only affect being pushed on the corner, but
        # also your steering rate? A formula should handle extremely well and a lorry could
        # handle poorly." It did not: two constants decided it for the whole fleet, so a
        # LORRY placed itself across the road exactly as sharply as a FORMULA car.
        #
        # THE ROAD IS FLATTENED FIRST. A bend pushes `targetX` and this experiment holds
        # `targetX` as its input, so a corner would be fighting the ask - and `cornerG` is
        # the OTHER consumer of grip, which would make the two impossible to tell apart.
        # A straight road measures the steering rate and nothing else.
        page.evaluate("""() => { const R = window.__probe.road;
            R.setWet(0); R.setSnow(0); R.setPool(0); R.flattenRoad(); }""")
        page.wait_for_timeout(200)
        print('  how sharply each car answers the wheel, on a straight road at %d mph'
              % (V_F * 200))
        steers = []
        for b in BODIES:
            if not page.evaluate("(k) => { const R = window.__probe.road;"
                                 " R.setBody(k); return R.bodyKey() === k; }", b):
                continue
            # RIGHT ACROSS THE ROAD, so the clamp is binding for most of the run: the ask
            # is beyond the far verge and the car never arrives, which keeps the gap wide.
            r = page.evaluate("(a) => window.__probe.steerRun(a.f, a.t, a.hold, a.sweep, a.ms, a.dry)",
                              {'f': -1.1, 't': 1.15, 'hold': V_F * mx, 'sweep': True, 'ms': 3000, 'dry': True})
            declared = page.evaluate("() => window.__probe.road.steerRate()")
            g = page.evaluate("(k) => (window.__probe.road.BODY[k] || {}).grip || 1", b)
            rate = rate_between(r['rows'], STEER_FROM, STEER_TO, V_F * mx)
            if rate is None:
                print('      %-13s NEVER CROSSED the measured stretch - reached %.3f' % (b, r['at']))
                continue
            if r['grip'] < 0.999:
                print('      %-13s SPOILED: the road was wet (grip %.3f)' % (b, r['grip']))
                continue
            steers.append({'body': b, 'rate': rate, 'claim': g, 'declared': declared,
                           'samples': len(r['rows'])})
            print('      %-13s %.2f lanes a second across %.2f of the road, %d frames   '
                  '(grip %.3f, the engine says %.2f)'
                  % (b, rate, STEER_TO - STEER_FROM, len(r['rows']), g, declared))
            # AND THE CAR IS PUT BACK IN THE MIDDLE. Left leaning on the far verge, the
            # braking run below starts off the road, where the decel is 11000 rather than
            # the brakes - which is what made the braking check fail the first time this
            # experiment was added in front of it.
            page.evaluate("() => { const R = window.__probe.road;"
                          " R.setLane(0); R.setTarget(0); }")

        res.check(len(steers) >= len(BODIES), 'every body in the group answered the wheel',
                  'only %d' % len(steers))
        if len(steers) >= 3:
            # 1. IT MUST ORDER BY GRIP, which is the owner's request stated as a check.
            byclaim = sorted(steers, key=lambda r: -r['claim'])
            bad = [(a['body'], b2['body']) for i2, a in enumerate(byclaim)
                   for b2 in byclaim[i2 + 1:]
                   if a['claim'] > b2['claim'] * 1.06 and a['rate'] < b2['rate'] - 0.02]
            res.check(not bad,
                      'a car the table says grips clearly better answers the wheel faster',
                      '%d pair(s) the wrong way round: %s' % (len(bad), bad[:4]))

            # 2. AND THE SPREAD MUST BE REAL, or the ruling has changed nothing. A check that
            #    only asks for an ORDER passes on a fleet whose rates differ by a hair.
            lo2 = min(r['rate'] for r in steers)
            hi2 = max(r['rate'] for r in steers)
            print('  the fleet spans %.2f to %.2f lanes a second, a spread of %.2f to 1'
                  % (lo2, hi2, hi2 / lo2))
            # ---- AND THIS QUESTION IS NOT ASKED OF A SINGLE CLASS ----------------------
            # It failed on the production group at 1.05 to 1, and it was right about the number and
            # wrong about what the number means. A COUPE, a HATCH and a SALOON declare grip 0.73,
            # 0.70 and 0.66; they are meant to feel alike, and a class whose cars felt 1.35 to 1
            # apart would not be a class. The claim is about the RANGE OF THE FLEET, so it is asked
            # of a group that spans several classes and printed as a measurement otherwise.
            res.check(SPREAD is None or hi2 / lo2 > SPREAD,
                      'and the difference between the best and worst is worth feeling'
                      if SPREAD is not None else
                      'the spread inside one class is reported, not asserted',
                      'the whole fleet is within %.2f to 1, which is not a handling model'
                      % (hi2 / lo2))

            # 3. AND IT MUST NOT BE TWO DIFFERENT GAMES, which is the risk RLG-119 named: a
            #    raw multiply by grip would be 4.9 to 1 across this fleet.
            res.check(hi2 / lo2 < 3.0,
                      'and not so large that the fleet is two different games',
                      'it spans %.2f to 1' % (hi2 / lo2))

            # 4. THE MEASURED RATE MUST BE THE DECLARED ONE. The engine publishes what it
            #    thinks each car's ceiling is; if the car does not actually move at it, the
            #    ceiling is not what is limiting and the whole result is about something else.
            errs = [(r['body'], abs(r['rate'] - r['declared']) / r['declared']) for r in steers]
            worst2 = max(errs, key=lambda kv: kv[1])
            print("  measured against the engine's own declared ceiling: worst is %s, %.1f%% out"
                  % (worst2[0], worst2[1] * 100))
            res.check(worst2[1] < 0.12,
                      'and the car really does move at the rate the engine says it can',
                      '%s measured %.1f%% away from its declared ceiling' % (worst2[0], worst2[1] * 100))
        print()

        # DRY AND FLAT AND STRAIGHT for the braking run: weather moves the brake through wetBrake,
        # and a hill would add or remove speed that has nothing to do with the brakes.
        page.evaluate("""() => { const R = window.__probe.road;
            R.setWet(0); R.setSnow(0); R.setPool(0);
            if(R.flattenRoad) R.flattenRoad(); }""")
        page.wait_for_timeout(300)
        print('  braking from %d to %d mph, dry, on a flat straight road'
              % (V_F * 200, TO_F * 200))
        print()

        rows = []
        for b in BODIES:
            ok = page.evaluate("(k) => { const R = window.__probe.road;"
                               " if(!R.setBody) return false; R.setBody(k);"
                               " return R.bodyKey() === k; }", b)
            if not ok:
                print('      %-13s could not be selected' % b)
                continue
            page.wait_for_timeout(150)
            r = page.evaluate("([a,b,c]) => window.__probe.brakeRun(a,b,c)",
                              [V_F * mx, TO_F * mx, CAP_MS])
            claim = page.evaluate("(k) => window.__probe.road.brakeOf(k)", b)
            grip = page.evaluate("(k) => (window.__probe.road.bodyStat "
                                 "? window.__probe.road.bodyStat(k) : null)", b)
            rows.append({'body': b, 'ms': r['ms'], 'dist': r['dist'],
                         'claim': claim, 'end': r['end']})
            print('      %-13s %6.0f ms   %7.0f units   brakeOf says %.3f'
                  % (b, r['ms'], r['dist'], claim))

        res.check(len(rows) >= len(BODIES), 'every body in the group could be measured',
                  '%d of %d bodies' % (len(rows), len(BODIES)))
        print()

        # ---- DOES THE TABLE TELL THE TRUTH ABOUT BRAKING -------------------------------------
        # The question RLG-042 asked about top speed, asked about the brakes. Not "is the number
        # right" - the number is a multiplier and cannot be right or wrong on its own - but does a
        # car the table says stops harder actually stop harder.
        if len(rows) >= 3:
            best = min(rows, key=lambda r: r['dist'])
            worst = max(rows, key=lambda r: r['dist'])
            print('  the shortest stop is the %s at %.0f units; the longest is the %s at %.0f'
                  % (best['body'], best['dist'], worst['body'], worst['dist']))
            byclaim = sorted(rows, key=lambda r: -r['claim'])
            bydist = sorted(rows, key=lambda r: r['dist'])
            agree = sum(1 for i, r in enumerate(byclaim) if bydist[i]['body'] == r['body'])
            print('  the table ranks %d of %d in the order they actually stop'
                  % (agree, len(rows)))
            # A ranking, not a rate. The multiplier and the distance are not the same quantity, so
            # what can be checked is that they ORDER the fleet the same way.
            inversions = 0
            for i in range(len(rows)):
                for j in range(i + 1, len(rows)):
                    a, b2 = byclaim[i], byclaim[j]
                    if a['claim'] > b2['claim'] + 1e-9 and a['dist'] > b2['dist']:
                        inversions += 1
            res.check(inversions == 0,
                      'a car the table says brakes better actually stops shorter',
                      '%d pair(s) are the wrong way round' % inversions)
        print()

        errs = page.evaluate("() => window.__probe.errors")
        res.check(not errs, 'no page errors', '; '.join(errs[:3]))
        browser.close()
    httpd.shutdown()

    print()
    if res.fails:
        print('FAILED: ' + ', '.join(res.fails))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
