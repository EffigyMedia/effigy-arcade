"""Do the cars do what the table says, and does everything on the road share one physics?

RLG-042, and it changes nothing. The owner ruled that "all cars, even the traffic, play off the same
reality and physics", that racer vehicles mirror the player-capable cars, and that a traffic car has
real stats with its DRIVER as the limitation. Before any of that is built, and before RLG-043 lowers
a single number, this says what is true today.

A code read says there are three models and a fourth for the garage card. A code read is not
evidence - RLG-029 established that at some cost, where the rubber band's tow was believed to be a
weak effect wanting a tune and was in fact arithmetically unreachable. So each claim here is put to
an experiment that could refute it.

THREE EXPERIMENTS
-----------------
1. CARS        Every driveable body, from a standstill, in cleared air: the real 0-60 and the real
               top speed, against `zeroSixty()` - which is what the garage card prints - and against
               `MAX_SPD * vmax`, which is what the table declares.

               The air is cleared rather than avoided: `traffic` and `cops` are emptied every tick
               for the duration. A 0-60 measured while something drives into you is a measurement of
               the collision.

2. GEARBOX     The decisive one, and it settles by EFFECT what a code read can only suggest.
               `aiGearFactor` calls `gearTable()`, which reads `optBody` - the PLAYER's car. If that
               matters, then changing the player's gearbox must change how fast the RIVALS
               accelerate, which is absurd and therefore worth proving rather than asserting.

               A rival is held two miles behind, in clean air, where the rubber band is saturated
               and identical in both arms. Its speed is knocked down to 40% of its target and the
               recovery to 90% is timed. Then the same rival, the same seed, the same grid - with
               the player sitting in a four-speed MUSCLE, and again in a six-speed FORMULA.

               Note what this does NOT test. `aiGearFactor` derives its rev fraction as
               `(rpm - IDLE) / (redline - IDLE)` where `rpm` was built from the same `redline`, so
               the redline cancels exactly and cannot be the signal. GEAR COUNT is the signal: four
               ratios against six.

3. TRAFFIC     What the traffic on the road is actually doing, by type, against what `BODY` says
               that vehicle can do. If traffic never reads `BODY`, these two columns are unrelated
               numbers and lowering one will not move the other.

4. STOP & TURN RLG-055 is blocked on this one. Every body declares a `brake` and a `grip` and
               nothing has ever measured either, so the fleet table cannot be rewritten without
               changing numbers whose honesty is unknown - which is exactly the trap RLG-042 found,
               where the top-speed column was true and three comments around it were false.

               BRAKE is a stopping distance. From 140mph, brake held, in cleared air, to 40mph:
               the distance covered and the time taken. Distance is the figure that matters,
               because a corner arrives at a place rather than at a moment.

               GRIP is measured WITHOUT A DRIVER, and that is the whole design of it. The engine
               pushes the car to the outside of a bend at a rate set by `cornerG()`, which is
               `0.42 / grip`. So the car is pinned at one position on the road - one constant
               curvature - held at one speed, and NOBODY TOUCHES THE WHEEL. The time it takes to
               drift a fixed distance across the road is the grip, and no steering input can
               contaminate it.

               That matters here more than anywhere. The project has already been told once that
               Raceway's tyres died in twenty seconds, when the cause was the drive-test autopilot
               sawing at the wheel: lateral load is what wears a tyre, and a driver in the loop is
               the thing being measured. There is no driver in this loop.
"""

import argparse
import functools
import http.server
import importlib.util
import json
import re
import socketserver
import statistics
import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GAME = 'games/sw/interstate.html'
MPH = 200 / 15333


def _handover():
    """Run under whatever Python is on PATH; hand over to the venv if it lacks Playwright (RLG-039)."""
    try:
        import playwright  # noqa: F401
        return
    except ImportError:
        pass
    for candidate in (ROOT / '.venv' / 'Scripts' / 'python.exe', ROOT / '.venv' / 'bin' / 'python'):
        if candidate.exists() and candidate.resolve() != Path(sys.executable).resolve():
            sys.exit(subprocess.run([str(candidate), str(Path(__file__).resolve())]
                                    + sys.argv[1:]).returncode)
    raise SystemExit('[stat-test] playwright is not importable and there is no project .venv.')


_handover()

from playwright.sync_api import sync_playwright   # noqa: E402

from harness import console_utf8, launch_chromium, boot as engine_boot, until  # noqa: E402


SEED_RNG = r"""
(function(){
  var s = 0x9E3779B9;
  Math.random = function(){
    s |= 0; s = (s + 0x6D2B79F5) | 0;
    var t = Math.imul(s ^ (s >>> 15), 1 | s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
})();
"""


def drive_test_module():
    path = Path(__file__).resolve().parent / 'drive-test.py'
    spec = importlib.util.spec_from_file_location('drive_test', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def serve(root):
    httpd = socketserver.TCPServer(
        ('127.0.0.1', 0), functools.partial(Quiet, directory=str(root)))
    httpd.allow_reuse_address = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.socket.getsockname()[1]


# --- experiment 1: what a car actually does ----------------------------------

CARS = r"""
(async function(bodies){
  var P = window.__probe, R = P.road, out = [];
  var sleep = function(ms){ return new Promise(function(r){ setTimeout(r, ms); }); };
  /* ---- CLEAR THE AIR -----------------------------------------------------
     A 0-60 measured while a van drives into the back of you is a measurement of
     the van. Traffic and police are emptied every tick for the whole run; they
     respawn and are emptied again. */
  var sweep = setInterval(function(){
    if(R.traffic) R.traffic.length = 0;
    var c = R.cops && R.cops(); if(c) c.length = 0;
  }, 50);
  try {
    for(var i = 0; i < bodies.length; i++){
      var key = bodies[i];
      /* ---- REFUSE TO MEASURE A GAME THAT IS NOT RUNNING --------------------
         This is the guard the first version did not have. A car cannot be timed
         while the run is over, and a harness that reports 0mph for that has not
         found a slow car - it has stopped measuring and not noticed. */
      if(R.state !== 'driving')
        throw new Error('the run left `driving` before ' + key + ' (state=' + R.state +
                        '). Nothing after this point would be a measurement.');
      R.setBody(key);
      await sleep(250);
      /* --- 0 to 60, best of three. The BEST rather than the mean: a slow run
         has a cause (a nudge, a frame hitch) and a fast one does not, so the
         minimum is the closest thing to the car's own figure. */
      var times = [];
      for(var a = 0; a < 2; a++){
        R.setSpd(0);
        await sleep(120);                       /* let the gearbox settle at rest */
        var t0 = performance.now(), t = 0;
        while(performance.now() - t0 < 20000){
          await sleep(16);
          if(R.spd * (200/15333) >= 60){ t = (performance.now() - t0) / 1000; break; }
        }
        if(t > 0) times.push(t);
      }
      /* --- top speed: hold it flat and take the peak ------------------------
         30 seconds, not 10. The first version held for ten seconds starting from
         a standstill it had just created, and reported STALLION at 135mph
         against a declared 206 - which is not a top speed, it is how far a car
         gets in ten seconds. */
      var peak = 0, t1 = performance.now();
      while(performance.now() - t1 < 30000){
        if(R.state !== 'driving')
          throw new Error('the run left `driving` while timing the top speed of ' + key);
        await sleep(50);
        if(R.spd > peak) peak = R.spd;
      }
      out.push({ key: key, zeroSixty: times.length ? Math.min.apply(null, times) : null,
                 attempts: times.length, topUnits: peak, state: R.state });
    }
  } finally { clearInterval(sweep); }
  return out;
})
"""


# --- experiment 2: whose gearbox are the rivals using? -----------------------

GEARBOX = r"""
(async function(cfg){
  var P = window.__probe, R = P.road, mile = cfg.mile;
  var sleep = function(ms){ return new Promise(function(r){ setTimeout(r, ms); }); };
  R.setBody(cfg.body);
  await sleep(300);
  /* the middle of the field by pace, held two miles back: clean air, and a
     rubber band that is saturated and therefore identical in both arms */
  var live = R.racers.filter(function(r){ return !r.wreck; });
  if(live.length < 3) return null;
  live.sort(function(a, b){ return a.base - b.base; });
  var r = live[(live.length/2)|0];
  var pin = setInterval(function(){ r.z = R.pos - 2*mile; }, 40);
  var runs = [];
  try {
    for(var a = 0; a < cfg.reps; a++){
      r.spd = r.base * 0.40;
      var target = r.base * 0.90, t0 = performance.now(), t = 0;
      while(performance.now() - t0 < 15000){
        await sleep(16);
        if(r.wreck > 0){ t = 0; break; }
        if(r.spd >= target){ t = (performance.now() - t0) / 1000; break; }
      }
      if(t > 0) runs.push(t);
      await sleep(200);
    }
  } finally { clearInterval(pin); }
  return { body: cfg.body, gears: (R.BODY[cfg.body] && R.BODY[cfg.body].gears) || 6,
           runs: runs, base: r.base, vmax: r.vmax, rivalBody: r.body };
})
"""


# --- experiment 4: what do `brake` and `grip` actually do? -------------------

STOPTURN = r"""
(async function(cfg){
  var P = window.__probe, R = P.road, out = [];
  var MPH = 200/15333;
  var sleep = function(ms){ return new Promise(function(r){ setTimeout(r, ms); }); };
  /* the same cleared air the 0-60 runs in: a stopping distance measured into
     the back of a van is a measurement of the van */
  var sweep = setInterval(function(){
    if(R.traffic) R.traffic.length = 0;
    var c = R.cops && R.cops(); if(c) c.length = 0;
  }, 50);
  /* ---- SACK THE DRIVER --------------------------------------------------
     THE FIRST RUN OF THIS EXPERIMENT REPORTED NO DRIFT AT ALL, for all
     sixteen cars, and it looked like a clean result. It was the autopilot:
     `__probe.drive()` is a centre-seeker holding the arrow keys, so it was
     steering out every bit of push as fast as the corner made it. A grip
     measurement with a driver in it measures the driver.

     It also holds the throttle, which has no place in a braking distance.
     So the driver is stopped for the whole experiment, and `stop()` releases
     every key it was holding.
     ------------------------------------------------------------------- */
  if(P.stop) P.stop();
  await sleep(200);
  /* ---- FIND ONE CORNER, AND USE IT FOR EVERY CAR ------------------------
     The seed is fixed, so a world position is the same bend for every body in
     this session. The tightest bend within the scan is chosen and its
     curvature is reported, so the numbers below are comparable to each other
     and honest about what they were measured on. */
  var z0 = R.pos + R.PLAYER_Z, best = 0, bestZ = z0;
  for(var z = z0 + 4000; z < z0 + cfg.scan; z += 400){
    var k = Math.abs(R.curvatureAt(z));
    if(k > best){ best = k; bestZ = z; }
  }
  try {
    for(var i = 0; i < cfg.bodies.length; i++){
      var key = cfg.bodies[i];
      if(R.state !== 'driving')
        throw new Error('the run left `driving` before ' + key + ' (state=' + R.state + ')');
      R.setBody(key);
      await sleep(200);

      /* ---- 1. STOPPING ------------------------------------------------- */
      var stops = [];
      for(var a = 0; a < cfg.reps; a++){
        R.setBrake(false);
        R.setSpd(cfg.fromMph / MPH);
        await sleep(120);
        var p0 = R.pos, t0 = performance.now();
        R.setBrake(true);
        var d = 0, t = 0;
        while(performance.now() - t0 < 15000){
          await sleep(16);
          if(R.spd * MPH <= cfg.toMph){
            t = (performance.now() - t0)/1000; d = R.pos - p0; break;
          }
        }
        R.setBrake(false);
        if(t > 0) stops.push({ t: t, d: d });
        await sleep(120);
      }

      /* ---- 2. TURNING, WITH NOBODY DRIVING ------------------------------
         Pinned at one place on the road so the curvature cannot change under
         the measurement, and at one speed so the v-squared term is identical
         for every car. What is left is `cornerG`, which is grip. */
      /* THE CAR DRIVES INTO THE BEND; IT IS NOT HELD IN ONE.
         The first version pinned the car at one world position with `jumpTo`
         on a 16ms timer, so the curvature could not change under the
         measurement. It drifted nowhere: `jumpTo` rebuilds the bend cache, and
         rebuilding it sixty times a second is not a corner, it is a car being
         teleported to the start of one. Nothing accumulates.

         So the car is put on the road a little before the bend, held at one
         speed, and left alone. Same seed, same bend, same speed for every
         body - what differs is only the car. */
      var drift = null, kUsed = 0;
      R.jumpTo(bestZ - cfg.runup);
      if(R.setLane) R.setLane(0);
      await sleep(250);
      if(R.setLane) R.setLane(0);
      var pin = setInterval(function(){ R.setSpd(cfg.cornerMph / MPH); }, 16);
      /* wait until the car is IN the bend rather than approaching it */
      var tw = performance.now();
      while(performance.now() - tw < 8000){
        await sleep(16);
        if(Math.abs(R.curvatureAt()) > cfg.kMin) break;
      }
      kUsed = R.curvatureAt();
      /* ---- A RATE, NOT A TIME TO A THRESHOLD -----------------------------
         Timing the car to a fixed drift reported nothing twice, because that
         shape cannot tell "this car did not move" from "the bend ended first" -
         both come back as "did not reach it". A RATE reports either way: how
         far across the road per second, with the mean curvature it happened in
         and why the window closed, so a short window is still a number.
         --------------------------------------------------------------- */
      /* ---- INTEGRATE THE PUSH, DIVIDE THE DRIFT BY IT --------------------
         A rate in lanes per second is only comparable between two cars if they
         were pushed by the same amount, and they never are: a bend is entered
         at a different point every time and `pushK` lags the road by
         CORNER_LAG, so the first half-second of any corner is a different push
         from the rest of it.

         So the push is integrated as the engine applies it -
         `pushK * v^2 * dt`, exactly the expression in `stepCar` - and the
         drift is divided by it. What comes out is `cornerG` as MEASURED, and
         `cornerG` is 0.42/grip by definition. Multiply the measurement by the
         declared grip and every car should read 0.42. Any car that does not is
         a car whose grip is not doing what it says.

         `targetX` and not `playerX`: the corner moves the target and the car
         follows it a moment later, so measuring the follower measures a lag
         that has nothing to do with grip.
         --------------------------------------------------------------- */
      var td = performance.now(), x0 = R.targetX, xEnd = x0;
      var push = 0, kSum = 0, kN = 0, why = 'window', tPrev = performance.now();
      while(performance.now() - td < cfg.window){
        await sleep(16);
        var now = performance.now(), dtS = (now - tPrev)/1000; tPrev = now;
        var v = R.spd / R.MAX_SPD;
        push += Math.abs(R.pushK()) * v * v * dtS;
        kSum += Math.abs(R.pushK()); kN++;
        xEnd = R.targetX;
        if(Math.abs(xEnd - x0) >= cfg.driftLanes){ why = 'ran wide'; break; }
        if(Math.abs(R.curvatureAt()) < cfg.kMin*0.5){ why = 'left the bend'; break; }
      }
      var dt2 = (performance.now() - td)/1000;
      /* a window with almost no push in it divides a small drift by a smaller
         number and reports anything at all - refused rather than reported */
      drift = (push > cfg.minPush) ? Math.abs(xEnd - x0)/push : null;
      kUsed = kN ? kSum/kN : kUsed;
      clearInterval(pin);
      await sleep(150);

      var B = R.BODY[key] || {};
      out.push({ key: key,
                 /* DERIVED now, not declared: `brake` is grip times the mechanical
                    brakes and `accel` is power to weight. Reading `B.brake` after that
                    change reported `undefined || 1` for every car - a table of ones,
                    which is what a harness reading a stat that no longer exists looks
                    like when nothing throws. */
                 brake: R.brakeOf ? R.brakeOf(key) : (B.brake || 1),
                 accel: R.accelOf ? R.accelOf(key) : (B.pull || 1),
                 grip: B.grip || 1, mass: B.mass || null,
                 stopT: stops.length ? Math.min.apply(null, stops.map(function(o){ return o.t; })) : null,
                 stopD: stops.length ? Math.min.apply(null, stops.map(function(o){ return o.d; })) : null,
                 runs: stops.length,
                 cornerG: drift, driftX: Math.abs(xEnd - x0), driftFor: dt2,
                 push: push, why: why, k: kUsed, mph: R.spd*MPH });
    }
  } finally { clearInterval(sweep); }
  return out;
})
"""


# --- experiment 3: is traffic reading the table? -----------------------------

TRAFFIC = r"""
(function(){
  var R = window.__probe.road, seen = {};
  (R.traffic || []).forEach(function(o){
    var t = o.type || '?';
    (seen[t] = seen[t] || []).push(o.cruise || o.spd || 0);
  });
  return seen;
})
"""

# what a traffic object of each type would be if it read BODY. `sedan2` is the second
# saloon sprite and shares SALOON's record.
TYPE_TO_BODY = {'truck': 'SEMI', 'van': 'VAN', 'pickup': 'PICKUP', 'coupe': 'COUPE',
                'tuner': 'TUNER', 'muscle': 'MUSCLE', 'taxi': 'CAB',
                'sedan': 'SALOON', 'sedan2': 'SALOON'}


def boot(page, base_url, race):
    engine_boot(page, base_url + '/' + GAME)
    try:
        until(page, '() => navigator.serviceWorker && navigator.serviceWorker.controller', timeout=5_000)
        page.wait_for_timeout(1_200)
    except Exception:
        pass
    until(page, '!!window.__probe.road', timeout=10_000)
    page.click('[data-act="play"]')
    page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5_000)
    # hot pursuit off: a roadblock or a PIT in the middle of a 0-60 is not a 0-60
    el = page.query_selector('[data-act="chase"] b')
    if el and el.inner_text().strip() == 'ON':
        page.click('[data-act="chase"]')
        page.wait_for_timeout(120)
    # ---- AND THE CLOCK OFF -------------------------------------------------
    # The first run of this harness measured fourteen cars and reported zero mph for nine of
    # them. TEST DRIVE has a countdown, experiment 1 takes longer than the countdown, and
    # everything after it expired was measured on a game that had ENDED. The numbers looked
    # like results.
    el = page.query_selector('[data-act="timed"] b')
    if el and el.inner_text().strip() == 'ON':
        page.click('[data-act="timed"]')
        page.wait_for_timeout(120)
    if race:
        page.click('[data-act="mode"]')
        page.wait_for_timeout(150)
    page.click('[data-act="drive"]')
    page.wait_for_timeout(400)
    page.evaluate('() => window.__probe.drive()')


def new_page(browser, dt):
    ctx = browser.new_context(viewport={'width': 480, 'height': 900})
    ctx.add_init_script(SEED_RNG)
    ctx.add_init_script(dt.INIT)
    return ctx, ctx.new_page()


def main():
    console_utf8()
    ap = argparse.ArgumentParser()
    ap.add_argument('--reps', type=int, default=4, help='recovery runs per gearbox arm')
    ap.add_argument('--only', choices=('cars', 'gearbox', 'traffic', 'stopturn'),
                    action='append', help='run just these experiments (repeatable)')
    ap.add_argument('--headed', action='store_true')
    args = ap.parse_args()

    src = (ROOT / 'road.js').read_text(encoding='utf-8')
    mile = 1.0 / float(re.findall(r'const MILE = 1 / ([0-9.]+);', src)[0])
    max_spd = float(re.findall(r'const MAX_SPD = ([0-9]+);', src)[0])

    print('stat-test  -  RLG-042  -  measures only, changes nothing')
    dt = drive_test_module()
    httpd, port = serve(ROOT)
    base = 'http://127.0.0.1:%d' % port
    try:
        with sync_playwright() as p:
            browser = launch_chromium(
                p, headless=not args.headed,
                args=['--autoplay-policy=no-user-gesture-required', '--mute-audio'])

            want = set(args.only or ('cars', 'gearbox', 'traffic', 'stopturn'))
            cars, claims, seen, arms, st = [], [], {}, [], []

            # ---- 1. the cars ------------------------------------------------
            if 'cars' in want:
             ctx, page = new_page(browser, dt)
             boot(page, base, race=False)
             bodies = page.evaluate(
                '() => Object.keys(window.__probe.road.BODY)'
                '.filter(k => !window.__probe.road.BODY[k].npc)')
             cars = page.evaluate(CARS + '(%s)' % json.dumps(bodies))
             claims = page.evaluate(
                '(ks) => ks.map(k => ({ key:k, card: window.__probe.road.zeroSixty(k),'
                ' vmax: window.__probe.road.BODY[k].vmax }))', bodies)
             ctx.close()

            # ---- 4. stopping and turning ------------------------------------
            if 'stopturn' in want:
             ctx, page = new_page(browser, dt)
             boot(page, base, race=False)
             bodies4 = page.evaluate(
                '() => Object.keys(window.__probe.road.BODY)'
                '.filter(k => !window.__probe.road.BODY[k].npc)')
             st = page.evaluate(STOPTURN + '(%s)' % json.dumps(
                {'bodies': bodies4, 'reps': 2, 'fromMph': 140, 'toMph': 40,
                 'cornerMph': 120, 'driftLanes': 0.60, 'scan': 60000,
                 'runup': 9000, 'kMin': 1.2, 'window': 4000, 'minPush': 0.05}))
             ctx.close()

            # ---- 3. the traffic (same session shape, cheap) -----------------
            if 'traffic' in want:
             ctx, page = new_page(browser, dt)
             boot(page, base, race=False)
             page.wait_for_timeout(14_000)
             seen = page.evaluate(TRAFFIC + '()')
             ctx.close()

            # ---- 2. the gearbox --------------------------------------------
            for body in (('MUSCLE', 'APEX') if 'gearbox' in want else ()):
                ctx, page = new_page(browser, dt)
                boot(page, base, race=True)
                page.wait_for_timeout(5_000)
                arms.append(page.evaluate(
                    GEARBOX + '(%s)' % json.dumps(
                        {'body': body, 'mile': mile, 'reps': args.reps})))
                ctx.close()
            browser.close()
    finally:
        httpd.shutdown()

    claim = {c['key']: c for c in claims}

    if cars:
        report_cars(cars, claim)
    if arms:
        report_gearbox(arms)
    if seen:
        report_traffic(seen, src)
    if st:
        report_stopturn(st)
    return 0


def report_stopturn(rows):
    """Braking distance and cornering drift, per body, against what each declares."""
    print('\n  4. STOPPING AND TURNING   (air cleared; nobody touches the wheel)')
    print('     brake: 140 to 40 mph, best of two, no throttle.')
    print('     turn: driven into one bend at 120mph with NO steering input; drift across')
    print('           the road in lanes per second, and that rate multiplied by `grip`.')
    row = '    {:<12} {:>6} {:>8} {:>7}   {:>5} {:>8} {:>8} {:>6}  {}'
    print(row.format('BODY', 'brake', 'stop(m)', 'stop(s)', 'grip',
                     'cornerG', 'x grip', 'drift', 'window ended'))
    print('    ' + '-' * 88)
    xs = []
    for r in sorted(rows, key=lambda r: -(r.get('brake') or 0)):
        d = r.get('stopD')
        dist = ('%.0f' % (d / 12.0)) if d else '-'   # about twelve units to the metre
        secs = ('%.2f' % r['stopT']) if r.get('stopT') else '-'
        cg = r.get('cornerG')
        cgs = ('%.3f' % cg) if cg is not None else '-'
        xg = None
        if cg is not None:
            xg = cg * (r.get('grip') or 1)
            xs.append(xg)
        print(row.format(r['key'], '%.2f' % (r.get('brake') or 0), dist, secs,
                         '%.2f' % (r.get('grip') or 0), cgs,
                         ('%.3f' % xg) if xg is not None else '-',
                         '%.2f' % (r.get('driftX') or 0), r.get('why', '')))
    print('\n    `cornerG` is the measured push: the drift divided by the integrated')
    print('    `pushK * v^2 * dt` the engine applied. The engine defines it as 0.42/grip, so')
    print('    `x grip` should read 0.42 for every car.')
    if xs:
        import statistics as _st
        print('    measured: mean %.3f, spread %.3f to %.3f%s'
              % (_st.mean(xs), min(xs), max(xs),
                 '' if len(xs) < 2 else ', sd %.3f' % _st.pstdev(xs)))

def report_cars(cars, claim):
    print('\n  1. WHAT EACH CAR ACTUALLY DOES   (air cleared: no traffic, no police)')
    row = '    {:<14} {:>9} {:>9} {:>7}   {:>9} {:>9} {:>7}'
    print(row.format('car', 'card 0-60', 'real', 'delta', 'table top', 'real', 'delta'))
    for c in cars:
        k = c['key']
        card = claim[k]['card']
        real = c['zeroSixty']
        top_claim = claim[k]['vmax'] * 200
        top_real = c['topUnits'] * MPH
        print(row.format(
            k,
            '%.1fs' % card,
            ('%.1fs' % real) if real else '-',
            ('%+.1f' % (real - card)) if real else '-',
            '%.0f' % top_claim,
            '%.0f' % top_real,
            '%+.0f' % (top_real - top_claim)))


def report_gearbox(arms):
    print('\n  2. WHOSE GEARBOX ARE THE RIVALS USING?')
    print('     One rival, held two miles back in clean air, knocked to 40% of its target and')
    print('     timed back to 90%. Only the PLAYER changes between the two arms.')
    for a in arms:
        if not a or not a['runs']:
            print('    %-10s no clean recovery measured' % (a['body'] if a else '?'))
            continue
        print('    player in %-8s (%d-speed)   rival %-9s recovery %.2fs   runs %s'
              % (a['body'], a['gears'], a['rivalBody'],
                 statistics.fmean(a['runs']),
                 ', '.join('%.2f' % t for t in a['runs'])))
    if all(a and a['runs'] for a in arms):
        m, f = statistics.fmean(arms[0]['runs']), statistics.fmean(arms[1]['runs'])
        print('\n    The rival was the same car in both arms: %s.'
              % ('yes, ' + arms[0]['rivalBody'] if arms[0]['rivalBody'] == arms[1]['rivalBody']
                 else 'NO - %s then %s, so this comparison is void'
                      % (arms[0]['rivalBody'], arms[1]['rivalBody'])))
        print('    Difference: %+.2fs (%+.1f%%). A rival that ran its OWN gearbox would show none.'
              % (f - m, (f / m - 1) * 100))


def report_traffic(seen, src):
    print('\n  3. IS THE TRAFFIC READING THE TABLE?')
    row3 = '    {:<10} {:>7} {:>12} {:>14} {:>10}'
    print(row3.format('type', 'seen', 'on the road', 'BODY says', 'ratio'))
    for t in sorted(seen):
        vals = [v for v in seen[t] if v]
        if not vals:
            continue
        obs = statistics.fmean(vals) * MPH
        bk = TYPE_TO_BODY.get(t)
        declared = page_body_vmax(src, bk) * 200 if bk else None
        print(row3.format(
            t, len(vals), '%.0f mph' % obs,
            ('%s %.0f' % (bk, declared)) if declared else '-',
            ('%.2f' % (obs / declared)) if declared else '-'))
    print('\n  A ratio far from 1.00, and different for every type, means the two columns are')
    print('  unrelated numbers - the road is not reading the table.')


def page_body_vmax(src, key):
    """Read a body's declared vmax straight out of road.js, so the report cannot drift from it."""
    m = re.search(r"'%s':\s*\{.*?vmax:\s*([0-9.]+)" % re.escape(key), src, re.S)
    return float(m.group(1)) if m else None


if __name__ == '__main__':
    sys.exit(main())
