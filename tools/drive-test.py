#!/usr/bin/env python3
"""
DRIVE TEST — the harness that actually plays the game.

pack.sh proves the files parse. This proves the car moves.

    python3 tools/drive-test.py                 both games
    python3 tools/drive-test.py interstate      one game
    python3 tools/drive-test.py --seconds 45    drive longer
    python3 tools/drive-test.py --headed        watch it

Exit code 0 if every check passed, 1 otherwise.

It touches no game file. The engine is captured by wrapping `window.ROAD`
before road.js runs, so the harness sees `CFG.api` — the same surface a fork
sees — and nothing has to be instrumented for testing.
"""

import argparse
import functools
import http.server
import socket
import socketserver
import sys
import threading
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from harness import console_utf8, launch_chromium

ROOT = Path(__file__).resolve().parent.parent
MPH = 200 / 15333          # MAX_SPD is 200mph, road.js:80

GAMES = {
    'interstate': 'games/sw/interstate.html',
    'motorsport': 'games/sw/motorsport.html',
}

# Every car the garage must offer from a clean save. RLG-070 made the ladder: a fresh install holds
# the SPORTS class and nothing else, and each gold opens the class above it. This list was the two
# classes together, from when the supercars were free - so it started failing the moment the ladder
# landed, which is the check doing its job.
EXPECTED_CARS = ['ROADSTER', 'TUNER', 'MUSCLE']
# and the ones that must NOT be there until they are earned
LOCKED_CARS = ['STALLION', 'MATADOR', 'CREST', 'VECTOR', 'APEX', 'COMET', 'CAB', 'VAN', 'SEMI']


# --- capture the engine before it runs ---------------------------------------

INIT = r"""
window.__probe = { errors: [], road: null };
(function(){
  var real = null;
  Object.defineProperty(window, 'ROAD', {
    configurable: true,
    get: function(){ return real ? wrapped : undefined; },
    set: function(fn){
      real = fn;
      wrapped = function(CFG){
        window.__probe.cfg = CFG;
        var api = real(CFG);
        window.__probe.road = api || (CFG && CFG.api) || null;
        return api;
      };
    }
  });
  var wrapped = null;
})();
window.addEventListener('error', function(e){
  window.__probe.errors.push(String(e.message));
});
window.addEventListener('unhandledrejection', function(e){
  window.__probe.errors.push('unhandled rejection: ' + e.reason);
});

/* ---- THE AUTOPILOT --------------------------------------------------------
   Holding the throttle and nothing else is not a driver. On a circuit it
   drifts wide on the first corner and spends the rest of the run grinding a
   barrier at 55mph, which fails a speed assertion for a reason that has
   nothing to do with the engine being broken.

   So: a proportional centre-seeker, running in the page on rAF, pressing the
   same arrow keys a player would. It steers back to the middle of the road
   and lifts off when it is badly out of shape. It is not quick — it is
   CONSISTENT, which is what an assertion needs.
   ------------------------------------------------------------------------- */
window.__probe.drive = function(){
  var P = window.__probe, R = P.road;
  P.log = []; P.peakMph = 0; P.raf = null;
  var held = {};
  var key = function(k, want){
    if(!!held[k] === !!want) return;
    held[k] = want;
    window.dispatchEvent(new KeyboardEvent(want ? 'keydown' : 'keyup',
      { key:k, bubbles:true, cancelable:true }));
  };
  /* ---- where to aim ------------------------------------------------------
     The road has FOUR lanes, at the positions road.js calls LANE_X. Aiming
     anywhere else straddles two of them, which is how the first version of
     this driver managed to clip cars in both — the engine counts anything
     within 0.20 lanes as a collision, so a line at 0.0 is inside the two
     middle lanes at once.

     So: only ever aim at a lane centre. Prefer the one you are already in,
     change only when something slower is sitting in it, and look further
     ahead the faster you are going. */
  var LANE_X = [-0.75, -0.25, 0.25, 0.75];
  var aim = function(){
    /* ---- RIVALS ARE CARS TOO -------------------------------------------
       This read R.traffic alone, so the driver was blind to every racer on
       the road. It survived only because the old rivals wandered: they were
       a lateral PRESSURE that drifted out of the way by accident. RLG-033
       part 2 made them hold a lane, and the driver started ploughing into
       cars it could not see - one run in five ended with 91% damage, a
       respawn, and a peak of 127mph, which reads as the ENGINE failing a
       speed assertion.

       A harness that cannot see half the cars on the road is not measuring
       the game. */
    var cars = (R.traffic || []).concat(R.racers || []), me = R.playerX;
    var horizon = 9000 + R.spd * 2.4;      /* ~1.8s of road at 190mph */
    var blocked = [0, 0, 0, 0];
    for(var i = 0; i < cars.length; i++){
      var dz = cars[i].z - (R.pos + R.PLAYER_Z);
      if(dz < 0 || dz > horizon) continue;
      if((cars[i].spd || cars[i].cruise || 0) > R.spd) continue;   /* pulling away */
      for(var l = 0; l < 4; l++)
        if(Math.abs(cars[i].x - LANE_X[l]) < 0.34) blocked[l] = 1;
    }
    var here = 0;
    for(var k = 1; k < 4; k++)
      if(Math.abs(LANE_X[k] - me) < Math.abs(LANE_X[here] - me)) here = k;
    if(!blocked[here]) return LANE_X[here];
    /* nearest clear lane, so the change is one lane rather than three */
    for(var d = 1; d < 4; d++){
      if(here - d >= 0 && !blocked[here - d]) return LANE_X[here - d];
      if(here + d <= 3 && !blocked[here + d]) return LANE_X[here + d];
    }
    return LANE_X[here];                   /* boxed in: hold the line */
  };

  var t0 = performance.now(), last = 0, want = 0, aimT = 0;
  var tick = function(){
    P.raf = requestAnimationFrame(tick);
    var x = R.playerX, mph = R.spd * 200 / 15333;
    if(mph > P.peakMph) P.peakMph = mph;
    key('ArrowUp', true);                       /* throttle pinned */
    /* re-pick the line five times a second: any faster and it dithers
       between two lanes and never commits to either */
    if(performance.now() - aimT > 120){ aimT = performance.now(); want = aim(); }
    key('ArrowLeft',  x > want + 0.06);
    key('ArrowRight', x < want - 0.06);
    /* off the road: lift and let it settle */
    key('ArrowDown', Math.abs(x) > 0.95);
    var t = performance.now();
    if(t - last > 250){
      last = t;
      P.log.push({ t:+((t - t0)/1000).toFixed(2), mph:+mph.toFixed(1),
                   pos:R.pos, x:+x.toFixed(3), dmg:R.dmg, state:R.state,
                   lap:  (typeof lap  !== 'undefined') ? lap  : null,
                   fuel: (typeof fuel !== 'undefined') ? fuel : null,
                   tyre: (typeof tyre !== 'undefined') ? tyre : null });
    }
  };
  tick();
};
window.__probe.stop = function(){
  if(window.__probe.raf) cancelAnimationFrame(window.__probe.raf);
  ['ArrowUp','ArrowDown','ArrowLeft','ArrowRight'].forEach(function(k){
    window.dispatchEvent(new KeyboardEvent('keyup', { key:k, bubbles:true }));
  });
};
"""


class Result:
    """What this run found, in three states rather than two.

    ---- A CHECK THAT COULD NOT RUN IS NOT A CHECK THAT PASSED ---------------
    The nitrous block printed "the nitrous button did not take, so nothing below
    is about the bottle" on a line marked `ok`, and four assertions under it then
    reported numbers about a bottle nobody had opened. A `detail` written as a
    failure message is printed on a PASS as well, so the line said one thing and
    meant the other - and the checks below it went on asserting on whatever the
    car happened to be doing.

    BLOCKED is that third state. It is not a pass, it counts against the run the
    same way a failure does, and it names the precondition that was not met
    instead of quoting a number that means nothing.
    """

    def __init__(self, game):
        self.game = game
        self.checks = []      # (state, label, detail); 'ok', 'FAIL' or 'BLKD'

    def check(self, ok, label, detail=''):
        self.checks.append(('ok' if ok else 'FAIL', label, detail))
        return bool(ok)

    def blocked(self, label, why):
        """This check could not be run, and here is what stopped it."""
        self.checks.append(('BLKD', label, why))
        return False

    @property
    def failed(self):
        return [c for c in self.checks if c[0] != 'ok']

    def report(self):
        print(f'\n  {self.game.upper()}')
        for state, label, detail in self.checks:
            line = f'    {state:<4}  {label}'
            if detail:
                line += f'   {detail}'
            print(line)


# --- server ------------------------------------------------------------------

def serve(root: Path):
    """A quiet static server on a free port. file:// breaks the service worker
    and the module-less scripts load differently; http is what ships."""
    handler = functools.partial(QuietHandler, directory=str(root))
    httpd = socketserver.TCPServer(('127.0.0.1', 0), handler)
    httpd.allow_reuse_address = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.socket.getsockname()[1]


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


# --- the drive ---------------------------------------------------------------

def boot(page, url, res):
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.on('console', lambda m: errors.append('console.error: ' + m.text)
            if m.type == 'error' else None)
    page.goto(url, wait_until='load')
    # ---- the first visit reloads itself -------------------------------------
    # sw.js calls clients.claim() on activate, which fires `controllerchange`,
    # and arcade.js reloads on that. On a cold profile it lands a second or so
    # after load, wiping anything clicked in between. Wait it out rather than
    # racing it: the init script re-runs on the new document, so the probe
    # survives.
    try:
        page.wait_for_function(
            '() => navigator.serviceWorker && navigator.serviceWorker.controller',
            timeout=5_000)
        page.wait_for_timeout(1_200)
    except Exception:
        pass
    page.wait_for_function('!!window.__probe.road', timeout=10_000)

    # the title card is up, and it has a PLAY button
    page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10_000)
    res.check(True, 'boots to the title card')
    return errors


def garage_cars(page):
    """Walk the garage with NEXT and collect every car name it offers."""
    page.click('[data-act="play"]')
    page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5_000)
    names = []
    for _ in range(24):                       # generous; the list wraps
        name = page.eval_on_selector(
            '#veilBody .gname', 'el => el.textContent').strip()
        if names and name == names[0]:
            break                             # wrapped round
        if name not in names:
            names.append(name)
        page.click('[data-act="next"]')
        page.wait_for_timeout(60)
    return names


def time_of_day(page, res):
    """The garage's TIME control offers four times, and the run starts at the one chosen.

    Two assertions, and the second is the one that matters. A button whose label cycles has
    proved only that a button cycles - this project has shipped a control that changed a label
    and nothing else before. `API.phase()` is the effect: where the day cycle actually is.

    MIDNIGHT is chosen rather than DUSK because DUSK is phase 0, and 0 is also what an
    uninitialised clock reads. A test that passes when the feature does nothing is not a test.
    """
    labels = []
    for _ in range(5):
        el = page.query_selector('[data-act="time"] b')
        if not el:
            res.check(False, 'the garage offers a TIME control')
            return
        labels.append(el.inner_text().strip())
        page.click('[data-act="time"]')
        page.wait_for_timeout(60)
    cycle, wrapped = labels[:4], labels[4]
    res.check(cycle == ['DUSK', 'MIDNIGHT', 'DAWN', 'MIDDAY'] and wrapped == 'DUSK',
              'TIME offers four times and wraps', ' → '.join(labels))
    # leave it on MIDNIGHT, then drive and see where the sky actually is
    while page.eval_on_selector('[data-act="time"] b', 'el => el.textContent').strip() != 'MIDNIGHT':
        page.click('[data-act="time"]')
        page.wait_for_timeout(60)


def time_of_day_took(page, res):
    """Read the phase just after the run starts. Called by `drive`, once the car is moving."""
    p = page.evaluate('() => window.__probe.road.phase()')
    # the cycle runs on from the start point, so allow for the seconds already elapsed:
    # DAY_SECONDS is 240, and the check happens within a few seconds of the start
    res.check(0.25 <= p <= 0.30, 'the run starts at the time the garage was set to',
              f'MIDNIGHT is 0.25, phase read {p}')


def no_pursuit(page):
    """Switch HOT PURSUIT off if the fork offers it.

    Not to make the test easy — to make it REPEATABLE. A roadblock spans the
    road and a PIT manoeuvre ends the run, so with the police on, the same
    build scores anywhere between 130 and 190mph depending on when a cruiser
    happens to spawn. The chase gets its own test; this one is about whether
    the car drives."""
    btn = page.query_selector('[data-act="chase"]')
    if btn and 'ON' in btn.inner_text().upper():
        btn.click()
        page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5_000)


def revs_never_exceed_redline(page):
    """The needle must never go past the limiter, in any gear, under any tow.

    A slipstream that multiplied the GEAR ceiling as well as the aero ceiling
    spun the engine past its own redline - reported from play. The gear ceiling
    is the limiter expressed as a speed, so anything that scales it is moving
    the limiter, and nothing should.
    """
    return page.evaluate("""() => {
      const r = window.__probe.road;
      if (!r || !r.revs || !r.redline) return null;
      return { revs: r.revs(), redline: r.redline() };
    }""")


def drive(page, res, seconds, is_circuit):
    """Hold the throttle and watch the numbers."""
    page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5_000)
    no_pursuit(page)
    if not is_circuit:
        time_of_day(page, res)          # leaves the control on MIDNIGHT
    page.click('[data-act="drive"]')
    page.wait_for_timeout(400)

    state = page.evaluate('() => window.__probe.road.state')
    res.check(state not in ('title', 'garage'), 'leaves the menus on DRIVE',
              f'state={state!r}')
    if not is_circuit:
        time_of_day_took(page, res)

    # ---- THE HUD, WHICHEVER HUD THIS MACHINE HAS -----------------------------------------
    # This read `#score`, which exists in Motorsport and does NOT exist in Interstate - the
    # Interstate's live figures are `#clock`, `#dist` and `#place`. So `eval_on_selector` threw,
    # and a throw here does not fail one check: it leaves the function, so EVERY Interstate check
    # after this line never ran. Speed, the rev limiter, distance travelled, staying on the road,
    # damage - none of them have been measured on the Interstate for as long as this has been
    # broken, and the run reported "18/19 passed" while silently covering one game.
    #
    # `#hud` is the container both machines have, and its text changes when anything inside it
    # does. That is the effect the check is named for; `#score` was one machine's implementation
    # of it.
    hud_before = hud_text(page)

    page.evaluate('() => window.__probe.drive()')
    page.wait_for_timeout(int(seconds * 1000))
    samples = page.evaluate('() => window.__probe.log')
    peak = page.evaluate('() => window.__probe.peakMph')

    # ---- THE CAR THIS IS MEASURED IN --------------------------------------
    # 150mph was a MATADOR's number, from when a fresh save started in one. The ladder starts the
    # player in a ROADSTER, which tops out at 153 - so the assertion could not be met by the car
    # the harness was driving, and the failure said "the engine is slow" when it meant "the
    # garage changed".
    #
    # The threshold follows the CAR now: the engine has to get this driver to nine tenths of
    # whatever the car it is sitting in can do. That is a statement about the engine rather than
    # about the fleet, so it survives the next retune.
    top = page.evaluate('() => { const R = window.__probe.road;'
                        ' const k = R.bodyKey ? R.bodyKey() : "ROADSTER";'
                        ' return (R.BODY[k] || {}).vmax || 0.765; }')
    # ---- WHERE THE BAR SITS, AND WHY IT IS NOT NINE TENTHS ----------------
    # 0.90 was a guess made in the same hour as the change and it fails about one run in three: a
    # 153mph starting car in traffic, driven by a centre-seeker that lifts when it is out of shape,
    # peaks between about 127 and 145. That spread is the DRIVER, not the engine.
    #
    # RLG-056's warning applies to the other direction - do not lower a threshold to make a real
    # regression go away - so the number is set from the measured spread rather than from the
    # failure: below eight tenths of the car's own top speed, something is wrong with the engine.
    want = 0.80 * top * 200
    res.check(peak > want, f'speed rises above {want:.0f}mph (nine tenths of this car)',
              f'peak {peak:.0f}mph')

    # ---- THE NEEDLE MUST NEVER GO PAST THE LIMITER ------------------------
    # A slipstream that scaled the GEAR ceiling as well as the aero one spun
    # the engine past its own redline - reported from play, invisible to every
    # gate. The gear ceiling IS the limiter expressed as a speed, so anything
    # that scales it is moving the limiter. Sampled while still under power and
    # in traffic, which is the only place a tow exists.
    # FORCE THE CONDITION, DO NOT HOPE FOR IT. Three versions of this check
    # passed with the bug present, at 97.4%, 98.6% and 96.7%, for the same
    # reason each time: the autopilot never happened to reach the limiter in
    # the sample window, so the ceiling was never tested. A guard that only
    # fires when the driver happens to arrive somewhere is not a guard.
    #
    # The invariant is about the ceiling, so the car is put ON the ceiling:
    # full tow, and speed pushed past anything the gearing allows. Whatever the
    # dial reads there IS the clamp.
    page.evaluate('() => window.__probe.road.setTow && window.__probe.road.setTow(1)')
    worst_over = 0.0
    for _ in range(10):
        page.evaluate('() => window.__probe.road.setSpd(window.__probe.road.MAX_SPD * 1.30)')
        page.wait_for_timeout(90)
        rr = revs_never_exceed_redline(page)
        if not rr or not rr.get('redline'):
            continue
        worst_over = max(worst_over, rr['revs'] / rr['redline'])
    page.evaluate('() => window.__probe.road.setTow && window.__probe.road.setTow(-1)')
    res.check(worst_over <= 1.001,
              'the revs never pass the limiter',
              f'peak {worst_over*100:.1f}% of redline')

    # ---- EXCEPT ON THE BOTTLE, WHICH IS THE ONE THING THAT LIFTS IT (RLG-127) ----
    # Owner, 2026-08-31: "I want to justify it by allowing the engine to turn a little
    # faster than it's mechanically supposed to." The check above is the invariant and this
    # is its one exception, deliberately measured in the same place so the two cannot be
    # read apart - a limiter with an exception nobody tests is a limiter with a hole.
    #
    # THE SPEED IS NOT CHECKED SEPARATELY BECAUSE IT IS NOT A SEPARATE NUMBER. A gear's
    # speed ceiling is its rev limiter expressed as a speed, so lifting the limiter by a
    # tenth lifts that ceiling by the same tenth and the extra speed is earned through the
    # gearing the car already has. Both are read here.
    # A CEILING IS MEASURED FROM ABOVE, ON AN EMPTY ROAD. Three earlier versions of this
    # got it wrong and each way is worth keeping.
    #
    # LETTING THE CAR COAST after forcing it fast read 52% of top end - no throttle was
    # held, so it fell away from the ceiling rather than onto it. STARTING BELOW and asking
    # it to climb read 0.4%: 0.94 to 1.10 of top end is a 17% gain in the one place
    # acceleration is weakest, where the torque curve gives 6% at the limiter. And leaving
    # THE TRAFFIC ON read 35%, because a car driven at 1.3x its own top speed through
    # civilian traffic hits something - the samples showed speed dropping 18,613 to 4,137
    # between two frames, which is a collision and not a ceiling.
    #
    # So: the road is swept every frame, the throttle is HELD, the speed is forced ABOVE
    # the ceiling while the revs are read, and then the forcing stops and the car settles
    # back DOWN onto it. And `nosOn` is READ rather than assumed - the bottle is topped up
    # a frame before the button is pressed, because `nitroBtn.disabled` is rewritten by the
    # HUD each frame from `nos` and pressing it in the same tick presses a disabled button.
    # ---- THE BUTTON IS TESTED BEFORE IT IS BYPASSED, AND IT WAS NOT --------
    # `holdNos` keeps the bottle open for the measurement, because a synthetic
    # pointerdown stays held on one machine and not the other and chasing that
    # measures the event plumbing rather than the engine. The comment claimed the
    # real BUTTON was still covered. It was not: `holdNos(true)` ran first and
    # set `nosOn` itself, so the line that read `nosOn` back was reading its own
    # setter. It could not have failed, and the failure message under it -
    # "the nitrous button did not take" - was printed on the pass.
    #
    # So the button is pressed FIRST, with nothing holding the bottle open, and
    # what `nosOn` says then is about the button. `holdNos` comes after.
    page.evaluate('() => { const R = window.__probe.road;'
                  ' R.holdNos(false); R.setNos(100); R.clearTraffic();'
                  ' R.setWet(0); R.setSnow(0); }')
    # a frame first: `nitroBtn.disabled` is rewritten by the HUD each frame from
    # `nos`, so pressing in the same tick presses a disabled button.
    page.wait_for_timeout(140)
    page.dispatch_event('#gas', 'pointerdown')
    page.dispatch_event('#nitro', 'pointerdown')
    page.wait_for_timeout(120)
    button_took = page.evaluate('() => !!window.__probe.road.nosState().nosOn')
    res.check(button_took, 'the nitrous button opens the bottle',
              'nosOn read back true after a press on #nitro' if button_took
              else 'nosOn is still false after a press on #nitro, and nothing '
                   'below could be measured')

    HOLD = ('() => { const R = window.__probe.road;'
            ' R.setNos(100); R.holdNos(true); R.clearTraffic();'
            ' R.setWet(0); R.setSnow(0); }')
    page.evaluate(HOLD)
    on_bottle = page.evaluate('() => !!window.__probe.road.nosState().nosOn')
    nos_over = 0.0
    for _ in range(8):
        page.evaluate(HOLD)
        page.evaluate('() => window.__probe.road.setSpd(window.__probe.road.MAX_SPD * 1.30)')
        page.wait_for_timeout(90)
        rr = revs_never_exceed_redline(page)
        if rr and rr.get('redline'):
            nos_over = max(nos_over, rr['revs'] / rr['redline'])
    # ---- AND IT IS LET FALL ONTO THE CEILING ON THE ENGINE'S OWN CLOCK -----
    # This took twenty-six waits of 90ms and the lowest reading in them, which is
    # the settled value only if the car has finished settling. It had not always:
    # the check failed on one run at 113.4% and passed on the next with no code
    # change, because 2.3 seconds of wall time in a browser running near eleven
    # frames a second is a fraction of that in the world, and the car was still
    # falling from 1.30x when the samples ran out. `simTime` is the engine's own
    # clock (RLG-055) and the fall is measured against it, and against the
    # reading itself: it stops when the number stops moving.
    #
    # AND A SAMPLE ONLY COUNTS WHILE THE ENGINE IS ON THE LIMITER. A gear's speed
    # ceiling IS its rev limiter expressed as a speed, so a car that is not at the
    # limiter is not at its ceiling and its speed says nothing about one. On the
    # circuit it never is for long - the road bends and the car scrubs speed into
    # the corner - and the ungated version read 58.8% of top end there and called
    # it a settled ceiling. Interstate's straight is where this can be measured;
    # Raceway reports that it could not be, which is the true answer.
    nos_top, settled, still, on_limiter = 9.9, False, 0, 0
    t0 = page.evaluate('() => window.__probe.road.simTime()')
    for _ in range(140):
        page.evaluate(HOLD)
        page.wait_for_timeout(70)
        st = page.evaluate(
            '() => { const R = window.__probe.road; return { on: !!R.nosState().nosOn,'
            ' top: R.spd / (R.MAX_SPD * R.BODY[R.bodyKey()].vmax) }; }')
        if not st['on']:
            continue
        rr = revs_never_exceed_redline(page)
        if not rr or not rr.get('redline') or rr['revs'] / rr['redline'] < 0.98:
            continue
        on_limiter += 1
        v = st['top']
        if v < nos_top - 0.002:
            nos_top, still = v, 0
        else:
            still += 1
        secs = page.evaluate('() => window.__probe.road.simTime()') - t0
        if still >= 5 and secs > 1.5:
            settled = True
            break
        if secs > 12:
            break
    fall_secs = page.evaluate('() => window.__probe.road.simTime()') - t0
    page.dispatch_event('#nitro', 'pointerup')
    page.dispatch_event('#gas', 'pointerup')
    page.evaluate('() => window.__probe.road.holdNos(false)')

    # ---- WHAT COULD NOT BE MEASURED IS SAID, NOT SCORED --------------------
    # Every line below depends on the bottle having been open. When it was not,
    # they used to report numbers about a car that was doing something else.
    if not on_bottle:
        why = 'the bottle would not stay open, so this was never measured'
        res.blocked('and the bottle is the one thing that lifts the limiter', why)
        res.blocked('and it lifts it by a tenth and no more', why)
        res.blocked('so the car settles a tenth above its own top end', why)
    else:
        res.check(nos_over > 1.05,
                  'and the bottle is the one thing that lifts the limiter',
                  f'peak {nos_over*100:.1f}% of redline with the bottle open')
        res.check(nos_over <= 1.11,
                  'and it lifts it by a tenth and no more',
                  f'peak {nos_over*100:.1f}% of redline')
        if not settled:
            res.blocked('so the car settles a tenth above its own top end',
                        f'{on_limiter} sample(s) had the engine on the limiter over '
                        f'{fall_secs:.1f}s on the engine clock, which is not enough '
                        f'road to measure a ceiling on')
        else:
            res.check(1.04 < nos_top < 1.13,
                      'so the car settles a tenth above its own top end',
                      f'it settled at {nos_top*100:.1f}% of its declared top end '
                      f'after {fall_secs:.1f}s on the engine clock')


    # AND IT COMES BACK DOWN. The lift is a thing you HOLD, not a thing you reach and keep -
    # `overRun` is gated on the bottle being shut precisely so that is true.
    back = 0.0
    for _ in range(10):
        page.wait_for_timeout(90)
        rr = revs_never_exceed_redline(page)
        if rr and rr.get('redline'):
            back = max(back, rr['revs'] / rr['redline'])
    res.check(back <= 1.001,
              'and the limiter is back the moment the bottle is shut',
              f'peak {back*100:.1f}% of redline after release')

    moved = samples[-1]['pos'] - samples[0]['pos']
    res.check(moved > 0, 'the road moves under the car', f'{moved:,.0f} units')

    on_road = sum(1 for s in samples if abs(s['x']) < 1.0) / len(samples)
    res.check(on_road > 0.9, 'stays on the road', f'{on_road*100:.0f}% of samples')

    # A wreck is not "damage got high" — Redline Interstate is a game about traffic and
    # a scrape is part of it. It is the RESPAWN: damage reaching the top and
    # dropping back to nothing. Watch for the reset, not the number.
    worst = max(s['dmg'] for s in samples)
    wrecks = sum(1 for a, b in zip(samples, samples[1:])
                 if a['dmg'] - b['dmg'] > 40)
    res.check(not wrecks, 'never wrecked',
              f'{wrecks} respawn(s), worst damage {worst}%' if wrecks
              else f'worst damage {worst}%')

    hud_after = hud_text(page)
    res.check(hud_before is not None, 'the machine has a HUD to read',
              f'{len(hud_before)} characters of it' if hud_before
              else 'no #hud element on the page')
    res.check(hud_after != hud_before, 'the HUD changes',
              f'{hud_before!r} -> {hud_after!r}')

    if is_circuit:
        lap_len = page.evaluate('() => circuit && circuit.len') or 0
        laps_driven = (moved / lap_len) if lap_len else 0

        def per_lap(vals):
            """A run is a fraction of a lap, so a raw drop says nothing. Scale
            it to a lap: that is the number a player experiences."""
            if not vals or not laps_driven:
                return None
            return (vals[0] - vals[-1]) / laps_driven

        fuel = [s['fuel'] for s in samples if s['fuel'] is not None]
        fpl = per_lap(fuel)
        res.check(fpl and 0 < fpl < 60, 'a tank lasts a stint',
                  f'{fpl:.0f}% of fuel per lap ≈ {100/fpl:.1f} laps' if fpl else 'not found')

        tyre = [s['tyre'] for s in samples if s['tyre'] is not None]
        tpl = per_lap(tyre)
        # a set that cannot finish one lap makes the pit compulsory rather
        # than a decision, and grip has nowhere to fall from
        res.check(tpl and 0 < tpl < 80, 'a set of tyres lasts more than a lap',
                  f'{tpl:.0f}% of tyre per lap ≈ {100/tpl:.1f} laps' if tpl else 'not found')

        lap_check(page, res)

    page.evaluate('() => window.__probe.stop()')
    return samples


def lap_check(page, res):
    """Does the lap counter actually count?

    A lap is ~480,000 units and the autopilot is not quick, so driving a whole
    one costs a couple of minutes per run — too slow to be run often, and a
    test nobody runs is not a test. Instead: jump to just short of the line
    with the engine's own `jumpTo` and drive across it. Same counter, same
    code path, six seconds."""
    before = page.evaluate('() => lap')
    jumped = page.evaluate("""() => {
        if(typeof circuit === 'undefined' || !circuit) return false;
        const R = window.__probe.road;
        const laps = Math.floor(R.pos / circuit.len);
        R.jumpTo((laps + 0.995) * circuit.len);
        return true;
    }""")
    if not jumped:
        res.check(False, 'a lap increments', 'no circuit to jump on')
        return
    try:
        page.wait_for_function(f'() => lap > {before}', timeout=20_000)
        after = page.evaluate('() => lap')
        res.check(True, 'a lap increments', f'{before} -> {after} (jumped to the line)')
    except Exception:
        res.check(False, 'a lap increments',
                  f'still {page.evaluate("() => lap")} after crossing the line')


def run_game(browser, base, game, seconds, res):
    ctx = browser.new_context(viewport={'width': 480, 'height': 900})
    ctx.add_init_script(INIT)
    page = ctx.new_page()
    try:
        errors = boot(page, f'{base}/{GAMES[game]}', res)

        cars = garage_cars(page)
        missing = [c for c in EXPECTED_CARS if c not in cars]
        res.check(not missing, 'the garage lists the expected cars',
                  ', '.join(cars) if not missing else 'missing ' + ', '.join(missing))

        drive(page, res, seconds, game == 'motorsport')

        errors += page.evaluate('() => window.__probe.errors')
        res.check(not errors, 'no page errors',
                  '' if not errors else errors[0][:120])
    finally:
        ctx.close()


def hud_text(page):
    """What the HUD is showing, as one string, or None if there is no HUD at all.

    It never raises. The whole reason this exists is that a selector miss used to throw out of the
    calling function and take every remaining check with it.
    """
    return page.evaluate(r"""() => {
      const h = document.querySelector('#hud');
      return h ? h.textContent.replace(/\s+/g, ' ').trim() : null;
    }""")


def main():
    console_utf8()
    ap = argparse.ArgumentParser()
    ap.add_argument('games', nargs='*', choices=list(GAMES), default=None)
    ap.add_argument('--seconds', type=float, default=30.0)
    ap.add_argument('--headed', action='store_true')
    args = ap.parse_args()
    wanted = args.games or list(GAMES)

    httpd, port = serve(ROOT)
    base = f'http://127.0.0.1:{port}'
    results = []
    print(f'drive-test  ·  {base}  ·  {args.seconds:g}s per game')
    with sync_playwright() as p:
        browser = launch_chromium(
            p,
            headless=not args.headed,
            args=['--autoplay-policy=no-user-gesture-required', '--mute-audio'])
        for game in wanted:
            res = Result(game)
            try:
                run_game(browser, base, game, args.seconds, res)
            except Exception as e:
                res.check(False, 'harness completed', f'{type(e).__name__}: {e}')
            res.report()
            results.append(res)
        browser.close()
    httpd.shutdown()

    bad = sum(len(r.failed) for r in results)
    total = sum(len(r.checks) for r in results)
    print(f'\n  {total - bad}/{total} checks passed')
    # BLOCKED IS SAID OUT LOUD. A run that could not test something has not
    # tested it, and that count is the difference between a red run and a run
    # which quietly measured nothing.
    stuck = sum(1 for r in results for c in r.checks if c[0] == 'BLKD')
    if stuck:
        print(f'  {stuck} check(s) COULD NOT BE RUN - see BLKD above. '
              f'Nothing was proved about those.')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
