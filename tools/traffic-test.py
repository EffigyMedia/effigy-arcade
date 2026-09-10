"""INTERSTATE TRAFFIC - is there always a way through?

The rule is that traffic must never pile up into a wall the player cannot pass.
The engine has had a guarantee for that all along and it still let walls form,
because it was asking the wrong question: it counted distinct LANE INDICES
inside fixed buckets, and neither of those is the road.

Cars drift inside a lane and a shunt moves one bodily sideways while its lane
field still says where it was assigned, so four cars can report four different
lanes and leave no opening a car could fit through. And a bucket keyed by
round(z / 1500) splits a wall that straddles its boundary into two halves, each
of which looks passable alone.

`API.blockedAhead()` reports how many sliding windows of road ahead had no
car-width corridor in them on the last pass. Zero is the contract.

This drives at speed for a long stretch - long enough for waves to spawn, for
cars to drift and for the field to bunch - and samples that number continuously.
A single blocked window is a failure, because the guarantee is absolute: the
player must never round a bend into a wall.

---- A QUIET RUN IS NOT A PROOF, AND THIS CHECK USED TO IMPLY IT WAS ---------
The corridor was measured over 24 runs of this length, twelve with the fixer
running and twelve with its correction switched off in the server. It closes on
about one run in three WITH the guarantee running, and the failures are not near
misses: they sit at 0.175 to 0.26 lane units against a passing band of 0.34 to
0.56. Two populations with a gap between them.

So the threshold is not drawn too fine. The engine really does let the road
close, and [[RLG-037]] carries that as an open defect. What that costs THIS
harness is that a green tick here means "this road did not close", which is a
weaker claim than "the guarantee holds" - and the old wording made the stronger
one. Both lines below are worded to the run.

AND THE SAME FACT WAS REPORTED TWICE. `blockedAhead > 0` and
`tightestAhead < 0.34` are one measurement: the engine counts a window as
blocked precisely when its corridor is under the limit. Two failing lines for
one closure read as two defects. The contract is asserted once now, and the
narrowest corridor is the size of the failure rather than a second one.

WHERE IT CLOSED IS HALF THE MEASUREMENT. The sweep runs 26,000 units ahead,
which at the pace driven here is two and a third seconds of road. A corridor
that tight at the far end has time to open before the car arrives; the same
number 3,200 units out is a wall. `tightestAt` and `blockedNearest` are the
engine's own record of where, and a failure now says which of the two it was.
"""
import sys, threading, http.server, socketserver, functools

# ---- IT FINDS ITS OWN ROOT (RLG-039) --------------------------------------------------
# This served the folder from '.' and imported from 'tools', so it only ran from the project
# directory. `step.py` runs a command with the ENVIRONMENT's root as its working directory, so
# every one of these harnesses 404'd or raised there and recorded a FALSE FAILURE as evidence -
# twice in one session before it was worth fixing. The root is the file's own parent.
from pathlib import Path as _P
ROOT = _P(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from harness import launch_chromium, console_utf8
from playwright.sync_api import sync_playwright

console_utf8()

handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
srv = socketserver.TCPServer(('127.0.0.1', 0), handler)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = f'http://127.0.0.1:{PORT}'

SECONDS = 45
# The pace held through the corridor phase, in world units a second. It is
# quoted rather than read back because it is what the phase IMPOSES, and it
# turns a distance up the road into the time the car has before it arrives.
#
# HELD EVERY FRAME, NOT FOUR TIMES A SECOND. `setSpd` pins the speed once and
# lets go, and between two pins the car is left to the world with nothing on the
# throttle - it sags on the flat and a slope can put it back over, which read as
# a 27mph range from a single request when RLG-199 measured it. The corridor
# phase is exactly that shape, and the distances it now reports are turned into
# SECONDS using this number, so a pace that drifts is a time that lies.
PACE = 11000


# ---- THE AMBER MEASUREMENT, AND WHAT IT HAD TO STOP COUNTING ----------------
# "Nothing else on this road is that shape" was wrong twice over, and the check
# was reading a floor that moved under it: `amber_off`, the count with every
# blink forced off, came out 0, 10, 17 and 196 across four runs of one build.
#
# MEASURED ACROSS FOUR PLACES AND EIGHT HOURS. The floor is 0 in the desert and
# the tundra at every hour, 42 in the city at midday and 183 in the forest -
# sunlit ground and foliage land inside the filter, and so do sodium lamps after
# dark. Pinning the light fixes that half.
#
# IT DOES NOT FIX THE OTHER HALF, AND THAT WAS THE BIGGER ONE. The SIGNAL moves
# too: with the blinks on it ran from 6 pixels to 1,050 across the same sweep,
# because it depends on how many cars are in shot and how far away they are. In
# one condition it came out LOWER with the indicators on than off. And staging
# four cars close to the camera pushed the floor to 370 in bright daylight -
# traffic PAINT, against a lamp signal of 18 to 38. A floor twelve times the
# size of what is being measured is not a measurement.
#
# So the scene is held still - one place, one hour, dry, the car stopped, four
# cars placed abreast in front of it - and the count is of pixels that BECOME
# amber. Anything already amber in the dark frame is subtracted, which removes
# the paint, the ground and the sky in one step and leaves the lamps. Measured
# over eight rounds that reads 0 pixels already there and 49 to 61 newly lit.
COUNT_AMBER = r'''() => {
  const cv = document.querySelector('canvas');
  const c = document.createElement('canvas');
  c.width = cv.width; c.height = cv.height;
  const g = c.getContext('2d'); g.drawImage(cv, 0, 0);
  const d = g.getImageData(0, 0, c.width, c.height).data;
  let n = 0;
  /* amber: red high, green mid, blue low */
  for (let i = 0; i < d.length; i += 4)
    if (d[i] > 232 && d[i+1] > 148 && d[i+1] < 202 && d[i+2] < 74) n++;
  return n;
}'''
# the dark frame, remembered pixel by pixel so the lit one can be compared with it
GRAB_DARK = r'''() => {
  const cv = document.querySelector('canvas');
  const c = document.createElement('canvas');
  c.width = cv.width; c.height = cv.height;
  const g = c.getContext('2d'); g.drawImage(cv, 0, 0);
  const d = g.getImageData(0, 0, c.width, c.height).data;
  const amber = new Uint8Array(d.length / 4);
  let n = 0;
  for (let i = 0, k = 0; i < d.length; i += 4, k++)
    if (d[i] > 232 && d[i+1] > 148 && d[i+1] < 202 && d[i+2] < 74) { amber[k] = 1; n++; }
  window.__amberDark = amber;
  return n;
}'''
# and it reports WHERE the change is. A count alone cannot tell a lamp on a car
# from a warning light in the dial cluster, and both are amber.
NEWLY_AMBER = r'''() => {
  const cv = document.querySelector('canvas');
  const c = document.createElement('canvas');
  c.width = cv.width; c.height = cv.height;
  const g = c.getContext('2d'); g.drawImage(cv, 0, 0);
  const d = g.getImageData(0, 0, c.width, c.height).data;
  const dark = window.__amberDark;
  let fresh = 0, x0 = 1e9, y0 = 1e9, x1 = -1, y1 = -1;
  for (let i = 0, k = 0; i < d.length; i += 4, k++)
    if (d[i] > 232 && d[i+1] > 148 && d[i+1] < 202 && d[i+2] < 74 && !dark[k]) {
      fresh++;
      const x = k % c.width, y = (k / c.width) | 0;
      if (x < x0) x0 = x; if (x > x1) x1 = x;
      if (y < y0) y0 = y; if (y > y1) y1 = y;
    }
  return { n: fresh, box: fresh ? [x0, y0, x1, y1] : null,
           w: c.width, h: c.height };
}'''
SET_BLINK = r'''(v) => { for (const c of window.__road.traffic) { c.blink = v; c.blinkDir = 1; } return window.__road.traffic.length; }'''
# ---- THE SCENE THE MEASUREMENT IS TAKEN IN ----------------------------------
# The place and the hour are pinned the way `biome-shot.py` pins them, and for
# the same reason: two pictures taken at different hours are two pictures of the
# light. Dry as well - rain on the road is another surface to catch the sun.
#
# `setTimed(false)` is here because the car is about to be held still. A run
# starts with sixty seconds, a stopped car reaches no checkpoint to buy more,
# and when they expire every driving-state number freezes where it stood - which
# does not look like a clock fault (RLG-125). This phase and the one that watches
# traffic arrive from behind are both stationary, and together they are longer
# than the clock.
PIN_SCENE = r'''([k, hour]) => {
  const R = window.__road;
  R.setBiomePair(k, k); R.setPhase(hour);
  R.setWet(0); R.setSnow(0); R.setPool(0);
  R.setTimed(false);
  return R.biome();
}'''
# Four cars abreast, close enough to be large in the frame and far enough not to
# be hit, and THE WHOLE ROAD held at a standstill with the player.
#
# STOPPING ONLY THE FOUR WAS NOT ENOUGH, and the falsifier is what said so: it
# refused to claim a proof on a run where 302 pixels turned amber between two
# frames with every blink off. The other thirty cars were still driving through
# the shot, and a car crossing the frame changes far more of it than a lamp does.
# The hour is re-pinned on every pass for the same reason - the day clock keeps
# running, and a shot that takes three seconds is three seconds of moving light.
#
# Every car's cruise is remembered so the phases after this one get their traffic
# back, moving at the pace it was going at.
STAGE_ABREAST = r'''([dz, blink, hour]) => {
  const R = window.__road, pz = R.pos + R.PLAYER_Z, xs = [-0.75, -0.25, 0.25, 0.75];
  /* EVERY CONTROLLED VARIABLE, EVERY PASS. Pinning them once is not pinning
     them: the day clock keeps running and the weather rolls itself back in, and
     both were measured doing it - a floor of 528 amber pixels on one run of a
     scene that reads 0 when it is actually held. RLG-055 lost a whole cornering
     experiment to the same mistake. */
  R.setPhase(hour);
  R.setWet(0); R.setSnow(0); R.setPool(0);
  /* ---- THE SAME FOUR CARS EVERY PASS, AND THEY WERE NOT --------------
     The traffic step sorts the array by `z` on every frame, so "the first four"
     is a different four each time this is called - and each pass teleported a
     fresh set into the shot on top of the last. The drift that failed this
     check was car-shaped, because it WAS a car: one that had just been moved
     there. They are tagged once and found by the tag from then on. */
  let cars = R.traffic.filter(c => c.__shot !== undefined);
  if (cars.length < xs.length) {
    cars = R.traffic.filter(c => c.mind !== 3).slice(0, xs.length);
    cars.forEach((c, i) => { c.__shot = i; });
  }
  cars.sort((a, b) => a.__shot - b.__shot);
  /* ---- AND `cruise` ALONE DOES NOT STOP A CAR ------------------------
     The traffic step keeps `cruiseFloor`, the pace a car returns to once it has
     been made to slow down, and winds `cruise` back up to it every frame - so a
     car set to zero was driving again three frames later, and one of them kept
     arriving in shot from the right-hand edge. Both are held, and both are put
     back afterwards. */
  for (const c of R.traffic) {
    if (c.__keepCruise === undefined) { c.__keepCruise = c.cruise; c.__keepFloor = c.cruiseFloor; }
    c.spd = 0; c.cruise = 0; c.cruiseFloor = 0;
    c.blink = blink; c.blinkDir = 1;
  }
  /* AND THE POLICE, which are not in `traffic` and would be the last thing
     moving. A cruiser crossing the frame changes far more of it than a lamp. */
  for (const k2 of R.cops()) { k2.spd = 0; }
  cars.forEach((c, i) => { c.z = pz + dz; c.x = xs[i]; });
  return cars.length;
}'''
RELEASE_ABREAST = r'''() => {
  let n = 0;
  for (const c of window.__road.traffic) {
    if (c.__keepCruise !== undefined) {
      c.cruise = c.__keepCruise; c.cruiseFloor = c.__keepFloor;
      c.__keepCruise = undefined; c.__keepFloor = undefined; n++;
    }
    c.__shot = undefined;
  }
  return n;
}'''
# how far up the road the staged cars sit. Measured: 2,600 units gives 16 to 23
# newly lit pixels, 1,400 gives 49 to 61, and 900 gives 83 to 107. The middle one
# is about three and a half car lengths - a clear signal with room to spare.
STAGE_DZ = 1400
# How much of the frame may turn amber on its own between two frames with every
# indicator off. Measured over five runs of the settled scene it is 0 four times
# in five, so this is a bar on a still scene rather than a tolerance for a moving
# one - and the shot is retaken rather than accepted when it is missed.
DRIFT_MAX = 12
# The place and the hour the shot is taken in. The desert reads no amber at any
# hour; the city reads 42 at midday and the forest 183, which is sunlit ground
# and foliage rather than any lamp.
PLACE, HOUR = 'DESERT', 0.75


def where(units):
    """A distance up the road, and the time the car has before it gets there.

    A bare figure in world units means nothing to a reader, and the whole point
    of carrying the distance is to separate a wall from a transient - so it is
    printed as both.
    """
    if units is None or units < 0:
        return 'nowhere'
    return f'{units:,} units ahead ({units / PACE:.2f}s at this pace)'


def box(b, frame):
    """Where a difference is, in words rather than in pixel coordinates.

    A count of changed pixels cannot separate a lamp on a car from a warning
    light in the dial cluster, and both are amber. The cars are staged in the
    middle of the frame and the dials are along the bottom, so the band the
    change falls in is enough to tell them apart.
    """
    if not b or not frame:
        return 'nowhere'
    x0, y0, x1, y1 = b
    h = frame[1] or 1
    band = 'the dials' if y0 > h * 0.72 else ('the road' if y1 < h * 0.72 else 'both')
    return f'in {band} (x {x0}-{x1}, y {y0}-{y1} of {frame[0]}x{frame[1]})'


def main():
    bad = 0

    def ok(cond, label, detail=''):
        nonlocal bad
        if not cond:
            bad += 1
        print(f'  {"ok  " if cond else "FAIL"}  {label}' + (f'   {detail}' if detail else ''))

    with sync_playwright() as p:
        b = launch_chromium(p, headless=True,
                            args=['--mute-audio', '--autoplay-policy=no-user-gesture-required'])
        page = b.new_context(viewport={'width': 480, 'height': 900}).new_page()
        errs = []
        page.on('pageerror', lambda e: errs.append(str(e)))
        page.goto(f'{BASE}/games/sw/interstate.html', wait_until='load')
        try:
            page.wait_for_function(
                '() => navigator.serviceWorker && navigator.serviceWorker.controller',
                timeout=5000)
            page.wait_for_timeout(1200)
        except Exception:
            pass
        try:
            page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
            page.click('[data-act="play"]')
            page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
            page.click('[data-act="drive"]')
            page.wait_for_timeout(1200)
        except Exception as e:
            ok(False, 'could reach the drive', f'{type(e).__name__}: {e}')
            b.close(); srv.shutdown(); return 1

        ok(page.evaluate("() => !!(window.__road && window.__road.blockedAhead)"),
           'the engine reports blocked windows')

        worst, blocked_samples, samples, tight = 0, 0, 0, 9.0
        tight_at, nearest = -1, -1
        # a real pace, so waves keep arriving and the field keeps moving
        page.evaluate(f"() => window.__road.holdSpd({PACE})")
        for _ in range(SECONDS * 4):
            page.wait_for_timeout(250)
            st = page.evaluate(
                "() => ({b: window.__road.blockedAhead(), t: window.__road.tightestAhead(),"
                " at: window.__road.tightestAt(), bn: window.__road.blockedNearest()})")
            if st is None:
                continue
            samples += 1
            if st['t'] < tight:
                tight, tight_at = st['t'], st['at']
            if st['b'] > 0:
                blocked_samples += 1
                worst = max(worst, st['b'])
                if nearest < 0 or st['bn'] < nearest:
                    nearest = st['bn']

        held = page.evaluate("() => window.__road.spd")
        page.evaluate("() => window.__road.holdSpd(null)")
        ok(samples > 100, 'the run was long enough to matter', f'{samples} samples')
        # THE PACE IS CHECKED, because every distance below is reported as a time
        # at it. A drifting pace makes those times wrong without making anything
        # look wrong.
        ok(abs(held - PACE) < PACE * 0.02, 'and it was driven at the pace it says',
           f'{held:,.0f} units a second against {PACE:,} asked for')
        # THE MEASUREMENT THAT DISCRIMINATES. The contract line below passes on a
        # road that never crowds at all, which is how the first version of this
        # test passed with the fixer switched off. The narrowest corridor actually
        # seen says whether the road was ever under pressure.
        ok(tight < 9, 'the road was measured under real traffic',
           f'narrowest corridor {tight:.3f} lane units {where(tight_at)}, need 0.34')
        # THE CONTRACT, ASSERTED ONCE. See the header: the engine counts a window
        # as blocked exactly when its corridor is under the limit, so a separate
        # assertion on the corridor was the same closure reported twice.
        detail = (f'{blocked_samples}/{samples} samples blocked, worst {worst} windows, '
                  f'narrowest corridor {tight:.3f}')
        if nearest >= 0:
            detail += f', nearest closure {where(nearest)}'
        ok(blocked_samples == 0,
           'this road never closed to a car in front of the player', detail)

        # ---- IT SIGNALS BEFORE IT MOVES, AND SOMETHING DRAWS IT (RLG-052) ----
        # Two claims, and the second was false for months: `c.blink` has been set on every merge
        # decision since the merge logic was written, and no renderer ever read it. So this checks
        # the ENGINE and then checks the SCREEN.
        #
        # The screen half forces every car to blink and counts amber pixels against a frame with
        # none. A check that only read the engine would have passed the entire time the feature was
        # invisible, which is exactly what happened.
        sig = page.evaluate("() => window.__road.signalling()")
        ok(isinstance(sig, dict) and sig.get('seen', 0) > 0,
           'the engine reports what is signalling', str(sig))
        cars = page.evaluate(SET_BLINK, 0)
        ok(cars > 0, 'there was traffic to signal', f'{cars} cars')

        place = page.evaluate(PIN_SCENE, [PLACE, HOUR])
        # ---- AND IF THE SCENE WILL NOT HOLD, TAKE IT AGAIN --------------------
        # Four runs in five the road comes to a complete stop and nothing at all
        # turns amber on its own. The fifth still had a car's worth of change in
        # it, and the honest answer to a shot that did not come out is another
        # shot rather than a wider tolerance - a bar raised until the bad frames
        # fit is a bar that no longer says the scene was still.
        attempts = 0
        for attempts in range(1, 4):
            # ---- SETTLE ON THE ENGINE'S CLOCK, WHICH IS THE ONLY ONE THAT COUNTS --
            # The car has just been driven for forty-five seconds. Its dials are drawn
            # into this same canvas and its brake lamps are lit while it sheds speed,
            # and both of those are amber enough for the filter: a frame grabbed as
            # soon as the throttle came off held 481 amber pixels where the same scene
            # from a standing start held none.
            #
            # A FIXED WAIT DOES NOT FIX IT. This browser runs near eleven frames a
            # second and the frame loop caps `dt`, so a second and a half of wall time
            # is a fraction of that in the world - and the scene was still coming to
            # rest when the shot was taken. Every remaining drift chased in this phase
            # was the same thing wearing a different hat: a brake lamp fading, the
            # mirror emptying, the needle falling. `simTime` is the engine's own clock
            # (RLG-055) and the settle is measured against it.
            staged = 0
            t_settle = page.evaluate("() => window.__road.simTime()")
            for _ in range(120):
                page.evaluate("() => window.__road.setSpd(0)")
                staged = page.evaluate(STAGE_ABREAST, [STAGE_DZ, 0, HOUR])
                page.wait_for_timeout(60)
                if page.evaluate("() => window.__road.simTime()") - t_settle > 2.5:
                    break
            settled = page.evaluate("() => window.__road.simTime()") - t_settle
            amber_off = page.evaluate(GRAB_DARK)
            # ---- THE CONTROL IS A SECOND DARK FRAME -------------------------------
            # Asserting that the scene has NO amber in it would be asserting on the
            # dials, which are allowed to be amber. What the difference actually needs
            # is a scene that is STILL, and two dark frames measure exactly that: any
            # pixel that turns amber between them turned amber for a reason that is
            # not an indicator.
            drift, drift_box = 0, None
            for _ in range(4):
                page.evaluate("() => window.__road.setSpd(0)")
                page.evaluate(STAGE_ABREAST, [STAGE_DZ, 0, HOUR])
                page.wait_for_timeout(55)
                g = page.evaluate(NEWLY_AMBER)
                if g['n'] > drift:
                    drift, drift_box = g['n'], g['box']
            # ---- SAMPLED BY THE ENGINE'S OWN CLOCK, NOT BY THE WALL'S -----------
            # An indicator is a FLASH: `blinkPhase` advances at 9.4 radians a second
            # and the lamp is lit for the half of the cycle where its sine is
            # positive, so a third of a second on and a third off. This browser runs
            # near eleven frames a second and the frame loop caps `dt`, so simulated
            # time runs a fraction of wall time and a fixed number of 55ms waits can
            # land entirely in the dark half - measured at 17 newly lit pixels on one
            # run and 95 on the next. `simTime` is the clock the flash is on
            # (RLG-055), and this samples until a full cycle of it has gone by.
            fresh, fresh_box, frame = 0, None, None
            BLINK_PERIOD = 6.2832 / 9.4
            t0 = page.evaluate("() => window.__road.simTime()")
            for _ in range(60):
                page.evaluate("() => window.__road.setSpd(0)")
                page.evaluate(STAGE_ABREAST, [STAGE_DZ, 5, HOUR])
                page.wait_for_timeout(45)
                g = page.evaluate(NEWLY_AMBER)
                frame = (g['w'], g['h'])
                if g['n'] > fresh:
                    fresh, fresh_box = g['n'], g['box']
                if page.evaluate("() => window.__road.simTime()") - t0 > BLINK_PERIOD * 1.5:
                    break
            blink_secs = page.evaluate("() => window.__road.simTime()") - t0
            page.evaluate(SET_BLINK, 0)
            page.evaluate(RELEASE_ABREAST)
            if drift <= DRIFT_MAX:
                break
        ok(staged == 4, 'four cars could be put across the road for the shot',
           f'{staged} staged {STAGE_DZ:,} units ahead in {place}, '
           f'left {settled:.2f}s on the engine clock to come to rest')
        ok(drift <= DRIFT_MAX, 'and the scene held still while the shot was taken',
           f'{drift} pixels turned amber between two frames with every blink off '
           f'{box(drift_box, frame)}, {amber_off} were amber to begin with, '
           f'{attempts} attempt(s)')
        # AND THE SIGNAL IS COUNTED AS A CHANGE. `c.blink` has been set on every
        # merge decision since the merge logic was written, and for months no
        # renderer read it - so this has to watch the SCREEN and not the engine.
        #
        # MEASURED IN PLACE OVER FIVE RUNS: 38, 43, 45, 63 and 85 newly lit
        # pixels, against a drift of 0 or 1. The spread is the cars the road
        # happened to hand it - a lorry's lamp is bigger than a hatchback's. With
        # the painter unwired it is 0 in every run, which is the gap that matters:
        # the bar sits between a broken build's nothing and the smallest number a
        # working one has produced.
        ok(blink_secs > BLINK_PERIOD, 'and the shot covered a whole flash of the lamp',
           f'{blink_secs:.2f}s on the engine clock, one flash is {BLINK_PERIOD:.2f}s')
        ok(fresh >= drift + 25, 'an indicating car puts amber on the screen',
           f'{fresh} pixels became amber when the indicators were lit {box(fresh_box, frame)}, '
           f'against {drift} that turn amber on their own')
        # TRAFFIC THAT ONLY BRAKES IS NOT TRAFFIC. Civilians followed the car
        # in front and never once considered the lane beside them, so the road
        # silted up into rolling walls. A merge count of zero over a long run
        # at speed means the decision is not being reached at all.
        # THE HORN HAS TO MOVE SOMEBODY. It was wrong in three separate ways at
        # once - it compared a lane INDEX to a road position, so it asked cars
        # that were not in front of you; a car that agreed only had its lane
        # LABEL changed and never moved; and the search started at the camera
        # rather than the car, about 880 units back, so its window covered road
        # already passed. Any one of those alone makes a horn look inert.
        before_sc = page.evaluate("() => window.__road.scattered()")
        # THE HORN IS STOCHASTIC and this check has to survive that. Whether a
        # car is in front of you at all is the bottleneck - measured over 40
        # presses, only 6 were in range - so a short phase can legitimately move
        # nobody. Longer, and slower, so the run actually meets traffic.
        for _ in range(60):
            page.evaluate("() => window.__road.setSpd(window.__road.MAX_SPD*0.55)")
            page.evaluate("() => document.getElementById('horn')"
                          ".dispatchEvent(new PointerEvent('pointerdown',{bubbles:true}))")
            page.wait_for_timeout(150)
            page.evaluate("() => document.getElementById('horn')"
                          ".dispatchEvent(new PointerEvent('pointerup',{bubbles:true}))")
            page.wait_for_timeout(150)
        moved_over = page.evaluate("() => window.__road.scattered()") - before_sc
        # REPORTED, NOT ASSERTED, AND ON PURPOSE. Whether a car is in front of
        # you at all is the bottleneck - measured over 40 presses, only 6 were
        # ever in range - and of those, 40% odds and a `heed` that falls with
        # every refusal mean a legitimate run can move nobody. Observed across
        # three runs: 2, 4 and 0.
        #
        # Asserting `> 0` on that is asserting on luck, and a check that fails
        # one run in three teaches people to ignore it. The mechanism is proven
        # deterministically elsewhere; this line exists to show the number.
        print(f'  ..    the horn moved {moved_over} cars this run '
              f'(stochastic - see RLG-035)')

        # ---- STOPPING MUST NOT EMPTY THE ROAD -------------------------------
        # There was no forward cull: traffic was removed only once it had fallen 34,000 BEHIND, so
        # anything quicker than the player drove away and stayed in the array for the whole run.
        # Standing still, the array pinned at 30 cars, all of them ahead, and within fifteen
        # seconds every one was past the draw distance - an empty road with thirty invisible cars
        # on it. The spawner that exists to make stopping feel exposed is gated on
        # `traffic.length < 26` and so could never fire. Reported from the device: nothing comes
        # up behind you when you stop.
        #
        # The check tags every car that exists at the moment of stopping, then asks whether any
        # UNTAGGED car has since arrived behind the player. A car that was already behind proves
        # nothing, and the array size alone proves nothing either.
        page.evaluate("() => { window.__road.traffic.forEach(c => c.__wasHere = 1); }")
        arrived, held = 0, 0
        for _ in range(80):
            page.evaluate("() => window.__road.setSpd(0)")
            page.wait_for_timeout(250)
            st = page.evaluate(
                "() => { const R = window.__road, p = R.pos; let fresh = 0; "
                "R.traffic.forEach(c => { if(!c.__wasHere && c.z < p) fresh++; }); "
                "return { fresh: fresh, n: R.traffic.length }; }")
            arrived = max(arrived, st['fresh'])
            held = max(held, st['n'])
        ok(arrived > 0, 'traffic still arrives from behind when you stop',
           f'{arrived} new cars came up behind over 20s, array held {held}')

        merges = page.evaluate("() => window.__road.mergesMade()")
        ok(merges > 0, 'traffic decides to go round slower cars',
           f'{merges} merges over the run')

        # NOTHING MAY ARRIVE IN VIEW. The road is drawn to DRAW*SEG, and
        # anything placed nearer appears out of nothing in front of the player -
        # which is indistinguishable from a rendering pop, and was reported as
        # one. Traps used to spawn as close as 26,000 into a 30,000 draw.
        near = page.evaluate("() => window.__road.nearestSpawn()")
        draw = page.evaluate("() => window.__road.drawDistance()")
        ok(near >= draw, 'nothing spawns inside the drawn road',
           f'nearest spawn {near:,} units, road drawn to {draw:,}')

        ok(errs == [], 'no page errors', errs[0][:100] if errs else '')
        b.close()

    srv.shutdown()
    # WORDED TO THE RUN, like the checks above it. "There is always a way
    # through" is a claim about the ENGINE, and one road driven once cannot
    # make it - measured, the road closes on about one run in three.
    print(f"\n  {'this road stayed drivable' if not bad else str(bad) + ' FAILURES'}")
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
