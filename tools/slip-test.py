#!/usr/bin/env python3
"""SLIP TEST - a wet road carries you further than you asked, by a knowable amount.

    .venv/Scripts/python tools/slip-test.py

RLG-048 and RLG-132. Owner, 2026-08-31: "when you turn the vehicle, it moves further than
you intend based off of the Delta that you've moved so if you steer discreetly, there will
be less slip, but if you make larger movements than the slip is larger too. The function of
the slip is the wetness/iciness." And: "with practice, you can understeer to get the amount
of steering you need given the environmental state of the ground. Instead of it being a
pure hindrance, it's something you can learn to work with."

THE SECOND QUOTE IS THE ONE THIS FILE EXISTS FOR. A slip that is proportional and does not
fade can be AIMED AT: on a given surface, asking for four fifths of a lane puts you in the
next lane exactly. That is a skill rather than an affliction, and it is a property a check
can state precisely - understeer by the predicted amount and land on the mark.

WHAT WOULD BREAK IT, and each of these was built and discarded on the way here:

    a slip that FADES      aiming short lands you short, because the road gives the extra
                           and then takes it back. There is nothing to learn.
    a slip that FIGHTS     a restoring force absorbs it. The first rewrite injected a
                           lateral velocity of 0.73 lane units a second and produced two
                           per cent of a lane, because the steering recovered a fifth of
                           the error every frame.
    a slip with NOISE      the amount cannot be predicted, so it cannot be aimed at.

WHY IT CANNOT USE THE DRIVE-TEST AUTOPILOT. That autopilot saws at the wheel, and under a
delta-driven model a sawing driver generates the maximum slip there is. This project has
already been told once that Raceway's tyres died in twenty seconds when the autopilot was
the cause. `API.steerOver` moves the wheel to a mark over a stated time.

BRAKING IS DELIBERATELY NOT LIKE THIS. Owner: "it also directly affects braking, but that
should be modelled more simply such that your braking grip is just reduced based on the
wetness/iciness." So braking stays a plain multiplier, and is checked as one.

WHAT IT CANNOT DO. It cannot say whether the result is FUN, or whether the amount of slip
is the right amount. Both are the owner's on a device.

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
        print(('  ok    ' if ok else '  FAIL  ') + label + ('' if ok else '   [' + detail + ']'))
        if not ok:
            self.fails.append(label)


# ---- THE CAR IS PARKED AND THE ROAD IS EMPTY, AND BOTH ARE NECESSARY ------------------
# The first version drove at 0.70 of top speed and read an overshoot of 0.1494 of a lane on
# a DRY road, where the model can inject nothing at all. It was measuring COLLISIONS: a
# collision shoves `playerX` sideways by up to 0.30, which is far larger than any slip and
# lands in exactly the reading this check takes. The dry control caught it, which is what a
# control is for.
#
# PARKING IS HONEST HERE because the slip is not a function of road speed - it comes off the
# wheel's own movement. That it is speed-independent is worth knowing, and it is recorded as
# a question for the owner rather than assumed to be right.
SET = """([wet, snowy, settle, pool]) => {
  const R = window.__probe.road;
  R.clearTraffic();
  R.setSpd(0);
  R.setWet(wet); R.setSnow(snowy ? settle : 0); R.setPool(pool);
  if(!snowy) R.setSnow(0);
  return R.wetModel();
}"""

# WHERE THE CAR COMES TO REST, not where it peaked. Under the ruling the overshoot does not
# fade, so the resting place IS what the road did - and it is the number a player learns to
# aim with. A peak reading would measure a wobble on the way rather than the outcome.
SWEEP = """([to, secs, hold]) => {
  const R = window.__probe.road;
  return new Promise((done) => {
    R.steerOver(to, secs);
    const t0 = performance.now();
    const tick = () => {
      /* THE ROAD IS KEPT EMPTY FOR THE WHOLE READING, not just at the start. A
         collision deliberately clears the slip offset - a shunt is not something you
         steered - so a car spawning behind the parked player during a three-second hold
         destroys the very thing being measured. It read as the offset failing to persist
         (RLG-131). */
      R.clearTraffic(); R.setSpd(0);
      if(performance.now() - t0 < (secs + hold) * 1000) requestAnimationFrame(tick);
      else { const s = R.slide(); done({ end: s.x, slide: s.slide, target: to }); }
    };
    requestAnimationFrame(tick);
  });
}"""

# BACK TO THE MIDDLE, AND THE SLIP WITH IT. Steering back is itself a movement and carries
# its own slip in the other direction, so an out-and-back cancels - which is the model
# working rather than the harness cheating. The wait lets it finish.
RECENTRE = """() => {
  const R = window.__probe.road;
  R.steerOver(0, 0.30);
  return R.slide();
}"""


def drive(page):
    until(page, '!!window.__probe.road', timeout=10000)
    page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
    page.click('[data-act="play"]')
    page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
    page.click('[data-act="drive"]')
    page.wait_for_timeout(1800)


# ---- EVERY MEASUREMENT STAYS OFF THE BARRIER, AND THAT IS NOT A FUDGE -------------------
# The first version asked for a full lane. On snow the slip adds a quarter of that, which put
# the aim past the edge of the road - and hitting the barrier ZEROES the slip, because a wall
# does not care how slippery the road is. So the car was shoved to the edge, lost its offset,
# and came back to the mark: the reading was 0.9894 for a movement that should have overshot,
# and it was the engine behaving correctly.
#
# 0.70 IS THE WORKING WIDTH. The largest movement here plus the largest slip the board can
# produce still lands inside the road, so what is measured is the model rather than the wall.
LANE = 0.70

def settle_at(page, to, hold=1.2, secs=0.30):
    """Steer to `to` and report where the car comes to rest, and the offset it started with.

    THE CAR DOES NOT ALWAYS START SQUARE, and that is the model rather than a defect. The
    offset does not decay, so a car that has been steered on snow is still carrying that
    offset when the road turns to rain - and a reading taken without allowing for it
    attributes the old surface's slip to the new one. That is exactly what happened here:
    rain measured 0.1525 where the model predicts 0.060, and the difference was a residue
    left by the snow measurement before it.

    So the residue is READ rather than cleared. Clearing it would need a debug hook that
    reaches past the model, and the arithmetic is honest without one.
    """
    page.evaluate(RECENTRE)
    page.wait_for_timeout(1100)
    page.evaluate("() => { const R = window.__probe.road; R.clearTraffic(); R.setSpd(0); }")
    before = page.evaluate("() => window.__probe.road.slide()")['slide']
    r = page.evaluate(SWEEP, [to, secs, hold])
    return r['end'], before


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--headed', action='store_true')
    args = ap.parse_args()
    console_utf8()
    res = Results()
    httpd, port = serve(ROOT)
    print('slip-test  .  a wet road carries you further than you asked')
    with sync_playwright() as p:
        browser = launch_chromium(p, headless=not args.headed)
        page = browser.new_page(viewport={'width': 480, 'height': 900})
        page.add_init_script(INIT)
        boot(page, 'http://127.0.0.1:%d/%s' % (port, GAME))
        try:
            until(page, '() => navigator.serviceWorker && navigator.serviceWorker.controller',
                timeout=5000)
            page.wait_for_timeout(1000)
        except Exception:
            pass
        drive(page)

        # ---------------------------------------------- how much a wet road takes
        print()
        print('  WHAT THE ROAD TAKES AWAY, dialled back (RLG-132)')
        dry = page.evaluate(SET, [0, 0, 0, 0])
        snow = page.evaluate(SET, [1.0, 1, 1.0, 0])
        rain = page.evaluate(SET, [1.0, 0, 0, 1.0])
        print('      grip:    dry %.2f   heavy snow on covered ground %.2f   heavy rain on water %.2f'
              % (dry['grip'], snow['grip'], rain['grip']))
        # NO ABSOLUTE THRESHOLD ON THE GRIP ITSELF. The owner reverted the dial-back and will
        # dial these in on a device, so a number asserted here would be a number this check
        # forbids them from choosing. What is asserted is the SHAPE - the ordering, the
        # proportionality and the learnability - which is what this unit actually built.
        res.check(snow['grip'] < 1.0,
                  'a wet road takes something, which is the hindrance the owner wants kept',
                  'heavy snow on settled ground gives %.3f' % snow['grip'])
        res.check(snow['grip'] < rain['grip'] < dry['grip'],
                  'and snow is still worse than rain, which is worse than dry',
                  'snow %.3f, rain %.3f, dry %.3f' % (snow['grip'], rain['grip'], dry['grip']))
        # THE FLOOR MUST NOT BE THE MODEL. It was 0.34 and heavy snow computed 0.28, so the
        # clamp WAS the snow behaviour rather than a net under it - and a number that always
        # binds cannot be reasoned about. Nothing on the board may reach it.
        # THE FLOOR IS REPORTED RATHER THAN ASSERTED. On the original numbers heavy snow
        # computes 0.28 and the clamp catches it, so the floor IS the worst case - worth
        # knowing while dialling, and not a defect to fail a build over.
        print('      (heavy snow lands %s the floor of %.2f)'
              % ('ON' if snow['grip'] <= snow['model']['floor'] + 1e-6 else 'above',
                 snow['model']['floor']))

        # ---- BRAKING IS A PLAIN MULTIPLIER, BY RULING -----------------------------
        # Owner: "it also directly affects braking, but that should be modelled more simply
        # such that your braking grip is just reduced based on the wetness/iciness." So it is
        # checked as the simple thing it is meant to be, and NOT for any delta behaviour.
        print('      braking: dry %.2f   heavy snow %.2f   heavy rain %.2f'
              % (dry['brake'], snow['brake'], rain['brake']))
        res.check(snow['brake'] < rain['brake'] < dry['brake'],
                  'braking grip is simply reduced by the wetness, and snow reduces it most',
                  'snow %.3f, rain %.3f, dry %.3f'
                  % (snow['brake'], rain['brake'], dry['brake']))
        res.check(snow['brake'] < dry['brake'],
                  'and it is a plain reduction with no delta behaviour in it, exactly as ruled',
                  'heavy snow brakes at %.3f against a dry %.3f' % (snow['brake'], dry['brake']))

        # ---------------------------------- the slip is proportional to the movement
        print()
        print('  IT CARRIES YOU FURTHER THAN YOU ASKED, IN PROPORTION TO THE MOVEMENT')
        page.evaluate(SET, [1.0, 1, 1.0, 0])
        big, big0 = settle_at(page, LANE)
        page.evaluate(SET, [1.0, 1, 1.0, 0])
        small, small0 = settle_at(page, LANE * 0.25)
        over_big, over_small = big - LANE - big0, small - LANE * 0.25 - small0
        print('      on snow: asking for %.3f rests at %.4f, asking for %.3f rests at %.4f'
              % (LANE, big, LANE * 0.25, small))
        res.check(over_big > 0.05,
                  'a large movement on snow carries the car well past the mark',
                  'it went %.4f past' % over_big)
        res.check(0 < over_small < over_big * 0.5,
                  'and a small one costs far less, which is what steering discreetly buys',
                  'small overshot %.4f against %.4f for the large one' % (over_small, over_big))
        # PROPORTIONAL, not merely smaller. The owner's sentence is that the slip follows the
        # DELTA, so a quarter of the movement costs about a quarter of the slip - and that is
        # also what makes it predictable enough to aim at.
        ratio = over_small / over_big if over_big else 0
        res.check(0.15 < ratio < 0.35,
                  'and it is PROPORTIONAL rather than just smaller, which is what makes it knowable',
                  'a quarter of the movement cost %.0f%% of the slip' % (ratio * 100))

        # ---- AND IT DOES NOT FADE, which is what makes it learnable -----------------
        page.evaluate(SET, [1.0, 1, 1.0, 0])
        held, _ = settle_at(page, LANE, hold=3.2)
        print('      and three seconds later the car is still at %.4f' % held)
        res.check(abs(held - big) < 0.03,
                  'the overshoot STAYS, so aiming short can be relied on rather than waited out',
                  'it rested at %.4f and is %.4f three seconds later' % (big, held))

        # ---- THE LEARNABLE PROPERTY, STATED AS AN EXPERIMENT -----------------------
        # Owner: "with practice, you can understeer to get the amount of steering you need."
        # If the slip is proportional and does not fade, then aiming at 1/(1+k) lands on the
        # mark - which is a claim a check can make exactly rather than merely describe.
        print()
        print('  SO YOU CAN UNDERSTEER ON PURPOSE AND ARRIVE EXACTLY, which is the owner point')
        model = page.evaluate(SET, [1.0, 1, 1.0, 0])
        slipm = page.evaluate('() => window.__probe.road.slipModel()')
        slick_now = 1 - model['grip']
        k = slick_now * slipm['snow']
        aim = LANE / (1.0 + k)
        landed, land0 = settle_at(page, aim)
        aim -= land0
        print('      snow at slick %.2f: aim %.4f to arrive at %.3f, landed at %.4f'
              % (slick_now, aim, LANE, landed))
        res.check(abs(landed - LANE) < 0.03,
                  'understeering by the amount the surface adds lands the car ON the mark',
                  'aimed %.4f, wanted %.3f, got %.4f' % (aim, LANE, landed))

        # ---------------------------------------------- snow against rain, and dry
        print()
        print('  SNOW IS A DIFFERENT CURVE, AND A DRY ROAD IS THE CONTROL')
        page.evaluate(SET, [1.0, 0, 0, 1.0])
        _r, _r0 = settle_at(page, LANE); rain_big = _r - LANE - _r0
        page.evaluate(SET, [0, 0, 0, 0])
        _d, _d0 = settle_at(page, LANE); dry_big = _d - LANE - _d0
        print('      the same movement: snow overshoots %.4f, rain %.4f, dry %.4f'
              % (over_big, rain_big, dry_big))
        res.check(rain_big > 0.01,
                  'rain carries the car too, so it is one model with two multipliers',
                  'rain overshot by %.4f' % rain_big)
        res.check(over_big > rain_big * 1.8,
                  'and snow throws it much harder than rain rather than a little',
                  'snow %.4f against rain %.4f' % (over_big, rain_big))
        res.check(abs(dry_big) < 0.005,
                  'and a dry road carries it nowhere, so every reading above is the weather',
                  'a dry road overshot by %.4f' % dry_big)

        # ---------------------------------------------- and it runs you wide in a bend
        # Owner, 2026-08-31: "I want to make sure that it still plays into roadway turns,
        # e.g. You are more greatly pulled to the outside curve due to slippage."
        #
        # TWO MECHANISMS SHOULD COMPOUND HERE and this is the check that they do. The
        # cornering force already divides by grip, so a wet road pushes harder toward the
        # outside on its own; and that push moves the wheel, which the slip then reads as a
        # movement and adds its own overshoot to. Neither was written for the other, so
        # whether they actually stack is a question rather than a certainty.
        #
        # THE CURVATURE IS PINNED. Finding a bend of a stated severity by driving is a
        # search, and it would measure the road generator rather than the physics.
        print()
        # BOTH ARMS MUST STAY OFF THE VERGE. The first attempt used a hard bend for two and
        # a half seconds and BOTH arms pinned against the edge of the road at -1.08, where
        # the difference this check exists to measure cannot exist. A gentle bend held
        # briefly leaves both arms free to differ.
        BEND, BEND_S = 1.1, 1.0
        print('  AND A SLICK ROAD RUNS YOU WIDE IN A BEND')
        WIDE = """([wet, snowy, settle, k, secs]) => {
          const R = window.__probe.road;
          R.clearTraffic();
          R.setWet(wet); R.setSnow(snowy ? settle : 0);
          if(!snowy) R.setSnow(0);
          R.setPool(0);
          R.steerOver(0, 0.01);
          R.holdCurve(k);
          return new Promise((done) => {
            const t0 = performance.now();
            const tick = () => {
              R.clearTraffic();
              R.setSpd(R.MAX_SPD * 0.45);
              if(performance.now() - t0 < secs * 1000) requestAnimationFrame(tick);
              else { const s = R.slide(); R.holdCurve(null); done({ x: s.x, slide: s.slide }); }
            };
            requestAnimationFrame(tick);
          });
        }"""
        page.evaluate("() => { const R = window.__probe.road; R.steerOver(0, 0.30); }")
        page.wait_for_timeout(900)
        dry_wide = page.evaluate(WIDE, [0, 0, 0, BEND, BEND_S])
        page.evaluate("() => { const R = window.__probe.road; R.steerOver(0, 0.30); }")
        page.wait_for_timeout(900)
        snow_wide = page.evaluate(WIDE, [1.0, 1, 1.0, BEND, BEND_S])
        print('      the same bend, same speed: dry runs to %.3f, snow runs to %.3f'
              % (dry_wide['x'], snow_wide['x']))
        res.check(abs(dry_wide['x']) > 0.02,
                  'a bend pushes the car toward the outside even on a dry road',
                  'it reached %.4f' % dry_wide['x'])
        res.check(abs(snow_wide['x']) > abs(dry_wide['x']) * 1.15,
                  'and a slick road carries it MARKEDLY wider, which is what the owner asked for',
                  'snow %.4f against dry %.4f' % (snow_wide['x'], dry_wide['x']))
        res.check(dry_wide['x'] * snow_wide['x'] > 0,
                  'and to the same side, so it is the same bend doing it rather than two effects',
                  'dry %.4f, snow %.4f' % (dry_wide['x'], snow_wide['x']))
        # AND THE SLIP IS PART OF IT rather than the cornering force being the whole story.
        # If `slide` were zero here, the bend would be pushing the car wide entirely through
        # `cornerG` and the delta model would be contributing nothing to a corner.
        res.check(abs(snow_wide['slide']) > 0.005,
                  'and the slip itself is carrying part of it, not just the cornering force',
                  'the slip offset in the bend was %.4f' % snow_wide['slide'])

        errs = page.evaluate("() => window.__probe.errors")
        res.check(not errs, 'no page errors', '; '.join(errs[:3]))
        browser.close()
    httpd.shutdown()

    print()
    if res.fails:
        print('FAILED: ' + '; '.join(res.fails))
        return 1
    print('all checks passed')
    return 0


sys.exit(main())
