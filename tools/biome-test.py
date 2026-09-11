#!/usr/bin/env python3
"""
BIOME TEST - a biome change is a place you drive into, not a colour that flips.

    .venv/Scripts/python tools/biome-test.py
    .venv/Scripts/python tools/biome-test.py --headed

RLG-022. The owner asked for the new biome's colour to be taken by the road slices "from the
furthest point forward" so it travels toward the camera, with a blend band between the two, and for
the band under the horizon to match the foreground and sit slightly darker. RLG-059 adds that each
biome must be strict about its ground colour.

WHY THIS NEEDS A HARNESS AND NOT A SCREENSHOT. The transition takes as long as it takes to drive the
length of the drawn road. One frame cannot show travel, and two frames of a moving game differ for a
dozen reasons that have nothing to do with the biome. So this reads the sweep as numbers over time -
where the boundary is, and how much of the new place each end of the draw is showing - and asserts
the SHAPE of the change rather than any single value.

WHAT IT WOULD CATCH. A flip - the old behaviour - shows the same mix at the car and at the horizon
at every instant. A sweep shows the horizon ahead of the car for the whole transition, and the gap
closing as the player drives at it. The last section puts the flip back and checks that this
distinction actually fails.

Exit code 0 if every check passed, 1 otherwise.
"""

import argparse
import functools
import http.server
import socketserver
import sys
import time
from pathlib import Path
import threading

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


SET_SNOWY_TUNDRA = """() => {
  const R = window.__probe.road;
  R.setBiomePair('TUNDRA', 'TUNDRA');
  R.setWet(0.9); R.setSnow(0.8);
}"""

# park the car just short of the band, so the crossing happens inside the run
# rather than 150 segments of driving later
PARK_AT_BAND = """() => {
  const R = window.__probe.road, s = R.biomeSweep();
  R.jumpTo((s.edge - s.band * 5) * 200);
}"""

READ_WEATHER = """() => {
  const R = window.__probe.road, s = R.biomeSweep();
  return { cross:s.atCar, wcross:s.atCarWeather, wet:R.wet(),
           settle:R.settle(), inb:s.player };
}"""

READ_FLOORS = """() => {
  const R = window.__probe.road, out = {};
  const keep = R.biomeSweep().player;
  for(const k of R.BIOME_KEYS()){ R.setBiomePair(k, k); out[k] = R.snowFloor(); }
  R.setBiomePair(keep, keep);
  return out;
}"""

BARE_THEN_TUNDRA = """() => {
  const R = window.__probe.road;
  R.setBiomePair('DESERT', 'DESERT');
  R.setWet(0); R.setSnow(0); R.setPool(0);
  R.setBiomePair('TUNDRA', 'TUNDRA');
}"""

# snow ON TOP of the floor, so the unwind has somewhere above it to come down from
TUNDRA_DEEP = """() => {
  const R = window.__probe.road;
  R.setBiomePair('TUNDRA', 'TUNDRA');
  R.setWet(0.9); R.setSnow(0.95);
}"""

DRY_DESERT = """() => {
  const R = window.__probe.road;
  R.setBiomePair('DESERT', 'DESERT');
  R.setWet(0); R.setSnow(0); R.setPool(0);
}"""

# IT HAS TO SNOW FIRST, and that is not set dressing. The unwind runs at the rate
# the last fall was depositing at, and a run that never accumulated falls back to
# 0.006 a second - which moves settle by 0.025 over the whole reading and reaches
# no floor at all. The first version of this check set the level directly and then
# measured a slope so shallow that a floor and no floor were indistinguishable.
SNOW_FIRST = """(k) => {
  const R = window.__probe.road;
  R.setBiomePair(k, k);
  R.setWet(0.9); R.setSnow(0.30);
}"""

# then stop it, just above the floor, with the fall rate now set.
#
# 0.34, NOT 0.58, AND THE NUMBER HAS TO TRACK THE FLOOR. This read 0.58 when the tundra's
# floor was 0.48 - a tenth above it, which is what "just above" meant and what makes the
# floor the only thing that can stop the unwind. The owner cut the floor to a quarter cover
# on 2026-08-31, and left at 0.58 the reading ended with the ground still sliding through
# 0.46 on its way down: the check was then measuring the length of the run rather than the
# floor, and it said so by failing. This keeps the same margin above the new floor.
STOP_JUST_ABOVE = """() => {
  const R = window.__probe.road;
  R.setSnow(0.34); R.setWet(0);
}"""

GRIP_IN_TUNDRA = """() => {
  const R = window.__probe.road;
  R.setBiomePair('TUNDRA', 'TUNDRA');
  R.setWet(0); R.setSnow(0.5); R.setPool(0);
  return R.wetGrip();
}"""

CAR_AND_ROAD = """() => {
  const R = window.__probe.road;
  const p = R.playerScreen();
  const v = R.vergeGap(12000);
  return { car: p ? +p.w.toFixed(2) : null, edge: v ? v.edge : null };
}"""

READ_SETTLE = "() => window.__probe.road.settle()"

# THE WEATHER TIMER KEEPS RUNNING while a measurement is going on, and in a tundra
# it starts snowing again within seconds - snow chance 0.62. The first version of
# the unwind check watched settle fall to 0.536 and then climb back to 0.554, and
# read that as the floor holding it. It was fresh snow. This holds the sky dry for
# the length of the reading, which is the only way to measure what the GROUND does.
HOLD_DRY = """() => { const R = window.__probe.road; R.setWet(0); return R.settle(); }"""

def lum(css):
    """Perceived brightness of an 'rgb(r,g,b)' string."""
    r, g, b = [float(v) for v in css[css.index('(') + 1:css.index(')')].split(',')]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def rgb(css):
    return tuple(float(v) for v in css[css.index('(') + 1:css.index(')')].split(','))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--headed', action='store_true')
    args = ap.parse_args()
    console_utf8()
    res = Results()
    httpd, port = serve(ROOT)
    print('biome-test  .  a biome change is a place you drive into')
    with sync_playwright() as p:
        browser = launch_chromium(p, headless=not args.headed)
        page = browser.new_page(viewport={'width': 480, 'height': 900})
        page.add_init_script(INIT)
        boot(page, 'http://127.0.0.1:%d/%s' % (port, GAME))
        try:
            until(page, '() => navigator.serviceWorker && navigator.serviceWorker.controller', timeout=5000)
            page.wait_for_timeout(1200)
        except Exception:
            pass
        until(page, '!!window.__probe.road', timeout=10000)
        page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
        page.click('[data-act="play"]')
        page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
        # MIDDAY, so the ground reads its daylight branch. The night and golden branches
        # are asserted separately below, by asking for them directly.
        for _ in range(6):
            if page.eval_on_selector('[data-act="time"] b', 'el => el.textContent').strip() == 'MIDDAY':
                break
            page.click('[data-act="time"]')
            page.wait_for_timeout(70)
        page.click('[data-act="drive"]')
        page.wait_for_timeout(1500)

        api = page.evaluate('() => Object.keys(window.__probe.road).filter(k => /biome|ground/i.test(k))')
        res.check('biomeSweep' in api and 'startBiomeChange' in api,
                  'the engine reports the sweep', str(sorted(api)))

        # ---------------------------------- a run starts in one place
        # THIS IS READ BEFORE ANYTHING ELSE TOUCHES THE STATE. The owner's first
        # test run "started with a raining desert": biomeNext began at 0 so the
        # first frame fired the biome timer, and the guard for "first call" tested
        # whether the frame was longer than a SECOND. A real first frame is 16ms,
        # so it took the CHANGE branch - the car started in the declared default of
        # FOREST with a transition placed at the horizon, and the weather rolled
        # against FOREST, which rains 42% of the time. Seconds later the car drove
        # into whatever had been placed ahead.
        start = page.evaluate('() => window.__probe.road.biomeSweep()')
        odds = page.evaluate('() => window.__probe.road.biomeOdds()')
        wx0 = page.evaluate("""() => { const R = window.__probe.road;
          return { wet: R.wet(), snowy: R.snowy() }; }""")
        print('      started in %s at temp %.2f (rain %.2f snow %.2f), wet %.2f snowy %d, from=%s to=%s'
              % (odds['name'], odds['temp'], odds['rain'], odds['snow'],
                 wx0['wet'], wx0['snowy'], start['from'], start['to']))
        res.check(odds['instance'],
                  'and the odds being read are THIS place, not the recipe it came from',
                  'instance=%s temp %.3f' % (odds['instance'], odds['temp']))
        res.check(start['from'] == start['to'],
                  'a run does not begin part-way through a biome change',
                  'from %s, to %s' % (start['from'], start['to']))
        res.check(start['player'] == start['from'],
                  'and the place the car is in is the place it started in',
                  '%s vs %s' % (start['player'], start['from']))
        # ---- CAPABILITY, NOT A CHANCE ABOVE ZERO (RLG-109) -----------------------------
        # This asked whether the odds were above zero, which is no longer the same
        # question. A coast's instance rains and never snows ON AVERAGE, and a single
        # cold moment within `swing` of that average snows perfectly well - so a chance of
        # 0.000 is not a statement that it cannot happen here.
        possible = odds['canSnow'] if wx0['snowy'] else odds['canRain']
        res.check(wx0['wet'] < 0.02 or possible,
                  'and whatever is falling is weather this place can produce',
                  '%s at temp %.2f: wet %.2f snowy %d, canSnow %s canRain %s'
                  % (odds['name'], odds['temp'], wx0['wet'], wx0['snowy'],
                     odds['canSnow'], odds['canRain']))

        # ------------------------------------------------------ the ground is strict
        print()
        print('  STRICT - each biome has its own ground, at every hour')
        keys = page.evaluate('() => window.__probe.road.BIOME_KEYS()')
        res.check(len(keys) >= 5, 'all the biomes are there', str(keys))
        # The night and golden branches used to be flat constants shared by every biome,
        # so this compared equal for all five and the sweep was invisible after dark.
        for label, night, gold in (('day', 0, 0), ('night', 1, 0), ('golden', 0, 1)):
            tones = page.evaluate(
                """([n, g]) => {
                  const R = window.__probe.road, out = {};
                  for(const k of R.BIOME_KEYS()){
                    R.setBiomePair(k, k);
                    out[k] = R.groundToneAt(0, false, n, g);
                  }
                  return out;
                }""", [night, gold])
            distinct = len(set(tones.values()))
            res.check(distinct == len(tones),
                      'at %s, every biome paints a different ground' % label,
                      '%d distinct of %d: %s' % (distinct, len(tones), tones))

        # ------------------------------------------------------ the far field matches
        print()
        print('  THE BAND UNDER THE HORIZON - the same ground, slightly darker')
        page.evaluate("() => window.__probe.road.setBiomePair('FOREST', 'FOREST')")
        page.wait_for_timeout(200)
        pair = page.evaluate("""() => {
          const R = window.__probe.road;
          const here = R.biomeSweep().here;
          return { far: R.groundToneAt(here + 150, false), band: R.groundBase() };
        }""")
        f, b = lum(pair['far']), lum(pair['band'])
        res.check(b < f, 'the band is DARKER than the ground it sits behind',
                  'furthest slice %.1f, band %.1f' % (f, b))
        res.check(b > f * 0.55, 'and not so much darker that it reads as a different place',
                  'band is %.0f%% of the slice' % (100 * b / f))
        fr, br = rgb(pair['far']), rgb(pair['band'])
        # SAME COLOUR, not merely a similar brightness. A grey band of the right darkness
        # would pass a brightness test and fail the owner's request, which was that it
        # MATCH the foreground. Channel ratios say hue; brightness does not.
        spread = max(br[i] / max(fr[i], 1) for i in range(3)) - min(br[i] / max(fr[i], 1) for i in range(3))
        res.check(spread < 0.35, 'and it is the same colour, not a grey of the same weight',
                  'channel ratio spread %.3f  %s vs %s' % (spread, pair['far'], pair['band']))

        # ------------------------------------------------------ the sweep itself
        print()
        print('  THE SWEEP - the new place arrives at the horizon first')
        start = page.evaluate("() => window.__probe.road.startBiomeChange()")
        res.check(start['from'] != start['to'], 'a change was placed',
                  '%s -> %s at segment %d, car at %d' % (start['from'], start['to'],
                                                         start['edge'], start['here']))
        res.check(start['atHorizon'] > start['atCar'],
                  'the moment it is placed, the horizon shows the new place and the car does not',
                  'horizon %.3f, car %.3f' % (start['atHorizon'], start['atCar']))
        res.check(start['player'] == start['from'],
                  'and the player is still in the OLD one, so the weather has not changed yet',
                  '%s' % start['player'])

        # THE CAR HAS TO ACTUALLY GET THERE. The boundary is placed DRAW segments
        # ahead - the far edge of the drawn road - and a car rolling off the line
        # covered 16 of those 150 in five seconds, so the first version of this
        # watched a sweep that had not moved yet and called it stationary. Speed is
        # held directly rather than by holding a throttle, because nothing here is
        # testing the throttle.
        track = [start]
        for _ in range(26):
            page.evaluate("() => window.__probe.road.setSpd(window.__probe.road.MAX_SPD * 0.9)")
            page.wait_for_timeout(300)
            track.append(page.evaluate("() => window.__probe.road.biomeSweep()"))
        for row in track[::3]:
            print('      car seg %-7d edge %-7d  mix at car %.3f  at horizon %.3f  in: %s'
                  % (row['here'], row['edge'], row['atCar'], row['atHorizon'], row['player']))

        cars = [r['atCar'] for r in track]
        res.check(all(b >= a - 0.001 for a, b in zip(cars, cars[1:])),
                  'the new place never retreats - it only comes closer',
                  ' '.join('%.2f' % v for v in cars[:8]))
        res.check(cars[-1] > cars[0],
                  'and it does come closer as the car drives at it',
                  '%.3f -> %.3f' % (cars[0], cars[-1]))
        # THE WHOLE POINT: a flip would show these equal at every instant.
        gap = [r['atHorizon'] - r['atCar'] for r in track if r['atCar'] < 1]
        res.check(gap and max(gap) > 0.3,
                  'the horizon leads the car by a wide margin - this is a sweep, not a flip',
                  'largest gap %.3f' % (max(gap) if gap else 0))
        crossed = [r for r in track if r['player'] == r['to']]
        if crossed:
            print('      the car arrived: player biome became %s' % crossed[0]['to'])

        # ------------------------------------------------ the horizon leads the car
        print()
        print('  THE SKYLINE BELONGS TO THE HORIZON, NOT TO THE CAR')
        res.check(page.evaluate("() => window.__probe.road.skySwap()") in ('move', 'fade'),
                  'the swap mechanism is switchable, so both can be judged',
                  page.evaluate("() => window.__probe.road.skySwap()"))
        page.evaluate("() => window.__probe.road.setBiomePair('DESERT', 'DESERT')")
        page.wait_for_timeout(200)
        placed = page.evaluate("() => window.__probe.road.startBiomeChange('FOREST')")
        # The horizon shows what the far segments show. At the moment a change is
        # placed the far segments are already half into the new place while the car is
        # not in it at all, so the skyline must be mid-swap while the player is still
        # wholly in the old biome. Before this the skyline was rebuilt on ARRIVAL, so
        # it would have read as the old place for the whole transition.
        res.check(placed['atHorizon'] > 0.4,
                  'the moment a change is placed, the skyline is already handing over',
                  'horizon mix %.3f' % placed['atHorizon'])
        res.check(placed['player'] == 'DESERT' and placed['atCar'] == 0,
                  'while the car is still wholly in the old place',
                  'player %s, mix at car %.3f' % (placed['player'], placed['atCar']))

        # --------------------------------------------- the weather crosses with you
        print()
        print('  THE WEATHER TRANSITIONS AS YOU CROSS, rather than switching at a line')
        # Snow falling, driving into a place that cannot hold it. The old behaviour
        # zeroed the target and went to full melt the instant the car passed the
        # boundary segment. It should thin out across the band instead.
        page.evaluate(SET_SNOWY_TUNDRA)
        page.wait_for_timeout(300)
        page.evaluate("() => window.__probe.road.startBiomeChange('DESERT')")
        page.evaluate(PARK_AT_BAND)
        wx = []
        for _ in range(22):
            page.evaluate("() => window.__probe.road.setSpd(window.__probe.road.MAX_SPD * 0.35)")
            page.wait_for_timeout(220)
            wx.append(page.evaluate(READ_WEATHER))
        crossing = [r for r in wx if 0 < r['wcross'] < 1]
        for r in wx[::4]:
            print('      ground %.2f  weather %.2f   wet %.3f   settle %.3f   in %s'
                  % (r['cross'], r['wcross'], r['wet'], r['settle'], r['inb']))
        res.check(len(crossing) >= 2,
                  'the run actually spent time inside the band, so this measured something',
                  '%d of %d samples were mid-crossing' % (len(crossing), len(wx)))
        wets = [r['wet'] for r in wx]
        res.check(wets[-1] < wets[0],
                  'the snow thins out as the desert arrives',
                  '%.3f -> %.3f' % (wets[0], wets[-1]))
        # A SWITCH WOULD SHOW ONE STEP. A transition shows several intermediate
        # values, and that is the difference being asserted.
        mids = [w for w in wets if 0.05 < w < wets[0] * 0.95]
        res.check(len(mids) >= 2,
                  'and it passes through intermediate values rather than stepping off',
                  '%d intermediate: %s' % (len(mids), ' '.join('%.2f' % w for w in mids[:6])))

        # -------------------------------------------------- the tundra lies under snow
        print()
        print('  THE TUNDRA IS WHITE BEFORE ANYTHING FALLS')
        floors = page.evaluate(READ_FLOORS)
        print('      floors: %s' % floors)
        # 0.25 IS THE OWNER'S RULING, 2026-08-31, and it replaced the 0.48 this model first
        # derived - which the owner drove and found about twice too white. The engine lands
        # on 0.247 because two stated points fix two constants exactly; the tolerance is for
        # that fit and nothing else. The number is written here rather than read from the
        # engine so a build that deleted the floor cannot satisfy the check by agreeing with
        # itself.
        res.check(0.24 <= floors.get('TUNDRA', 0) <= 0.26,
                  'the tundra holds the quarter cover the owner asked for, before anything falls',
                  'floor %.3f against a ruled 0.25' % floors.get('TUNDRA', 0))
        res.check(0.09 <= floors.get('MOUNTAIN', 0) <= 0.11,
                  'and the mountain holds the tenth it was ruled, which one coefficient could not give with it',
                  'floor %.3f against a ruled 0.10' % floors.get('MOUNTAIN', 0))
        # ---- THE FLOOR IS DERIVED FROM THE TEMPERATURE NOW (RLG-109) --------------------
        # This used to read "and nowhere else does", against a `snowFloor` typed into the
        # tundra's recipe alone. The floor derives from the instance's temperature, so
        # COLD is what puts white on the ground and the tundra is simply the coldest
        # place. The mountain at 0.15 gains 0.24 of it, which is the model working rather
        # than a place being given a property.
        #
        # THE ASSERTION IS THE ORDERING, and it says the same thing the old one meant:
        # the tundra is whiter than anywhere else, and a place that is not cold has
        # nothing on the ground at all.
        cold = {k: v for k, v in floors.items() if v > 0}
        warm = {k: v for k, v in floors.items() if v == 0}
        res.check(all(floors['TUNDRA'] > v for k, v in floors.items() if k != 'TUNDRA'),
                  'and it is whiter than anywhere else, because it is the coldest place',
                  str(floors))
        res.check(set(cold) == {'TUNDRA', 'MOUNTAIN'} and len(warm) >= 4,
                  'only the places below freezing hold any, and the temperate ones hold none',
                  'under snow: %s   bare: %s' % (sorted(cold), sorted(warm)))
        # AND IT IS THE TEMPERATURE, NOT THE NAME. The same city is bare when it rolls warm
        # and lies under snow when it rolls cold, with nothing in the table saying so. This
        # cannot pass against a build that reads the recipe: the recipe has one city in it.
        swing = page.evaluate("""() => {
          const R = window.__probe.road, keep = R.biomeSweep().player;
          R.setBiomePair('CITY', 'CITY', 0.85, 0.85); const hot = R.snowFloor();
          R.setBiomePair('CITY', 'CITY', 0.02, 0.02); const cold = R.snowFloor();
          R.setBiomePair(keep, keep);
          return { hot: hot, cold: cold };
        }""")
        print('      the same CITY: rolled warm floor %.2f, rolled cold floor %.2f'
              % (swing['hot'], swing['cold']))
        res.check(swing['hot'] == 0 and swing['cold'] > 0.25,
                  'and ONE city recipe gives a bare city or a snowed-in one, by its rolled temperature',
                  'warm %.3f, cold %.3f' % (swing['hot'], swing['cold']))

        # Bare ground, then a tundra arrives. It must CLIMB to the floor rather than
        # snapping to it - a Math.max would have yanked it up in one frame, which is
        # the switch this whole piece of work exists to remove.
        page.evaluate(BARE_THEN_TUNDRA)
        climb = []
        for _ in range(12):
            page.wait_for_timeout(250)
            climb.append(page.evaluate(READ_SETTLE))
        print('      settle climbing: %s' % ' '.join('%.3f' % v for v in climb))
        res.check(climb[-1] > climb[0], 'it whitens when you arrive somewhere that lies under snow',
                  '%.3f -> %.3f' % (climb[0], climb[-1]))
        steps = [b - a for a, b in zip(climb, climb[1:])]
        res.check(max(steps) < 0.10,
                  'and it CLIMBS rather than snapping - no single step is most of the way',
                  'largest step %.3f' % max(steps))

        # It must also not unwind past the floor. The first version of this check
        # let a deep fall unwind for five seconds and asserted it was still above
        # 0.5 - and it rested at 0.823, which is nowhere near the floor. That would
        # have passed with the floor ignored completely: it was measuring that the
        # unwind is slow, not that it stops. So it starts JUST above the floor, where
        # the only thing that can hold it is the floor itself.
        page.evaluate(SNOW_FIRST, 'TUNDRA')
        page.wait_for_timeout(900)
        page.evaluate(STOP_JUST_ABOVE)
        deep0 = page.evaluate(READ_SETTLE)
        rest = []
        for _ in range(14):
            page.wait_for_timeout(300)
            rest.append(page.evaluate(HOLD_DRY))
        print('      settle unwinding: %.3f -> %s' % (deep0, ' '.join('%.3f' % v for v in rest[-6:])))
        res.check(rest[0] < deep0, 'a fall on top of the floor does unwind',
                  '%.3f -> %.3f' % (deep0, rest[0]))
        # NEVER BELOW, rather than exactly at. It rests a little above the floor
        # because a tundra's own weather timer keeps putting snow back during the
        # reading - snow chance 0.62 - and that is the game working, not the check
        # failing. What the floor claims is that nothing takes the ground below it,
        # so that is what is asserted, over every sample rather than the last one.
        # AGAINST THE OWNER'S NUMBER, not against whatever the engine reports. Read
        # from `floors` this compared `min(rest) >= 0 - 0.02` on a build with the
        # floor deleted, which is true of anything - the check switched itself off
        # exactly when its subject went missing. 0.50 is the ruling; it is written
        # here so the assertion cannot be neutralised by the fault it tests for.
        #
        # THE RULED NUMBER IS NOW 0.25, not 0.50. The owner drove the derived 0.48 and cut it
        # to a quarter cover on 2026-08-31. What is asserted is unchanged in kind - the floor
        # holds the ground up and nothing takes it below - and only the height moved.
        res.check(min(rest) >= 0.24,
                  'and nothing takes it below the quarter cover the owner asked for, at any point',
                  'lowest %.3f against a ruled 0.25' % min(rest))
        res.check(abs(rest[-1] - rest[-4]) < 0.01,
                  'and it settles rather than still sliding',
                  '%.3f then %.3f, four samples apart' % (rest[-4], rest[-1]))
        # AND THE SAME START WITHOUT A FLOOR MUST NOT STOP. If it did, this would be
        # measuring the unwind running out rather than the floor holding it.
        page.evaluate(SNOW_FIRST, 'DESERT')
        page.wait_for_timeout(900)
        page.evaluate(STOP_JUST_ABOVE)
        noFloor = []
        for _ in range(14):
            page.wait_for_timeout(300)
            noFloor.append(page.evaluate(HOLD_DRY))
        print('      the same, in a place with no floor: %s'
              % ' '.join('%.3f' % v for v in noFloor[-6:]))
        res.check(min(noFloor) < 0.47,
                  'in a place with no floor the same snow goes straight past that level, '
                  'so the floor is what held it',
                  'desert reached %.3f, tundra never below %.3f' % (min(noFloor), min(rest)))
        grip_tundra = page.evaluate(GRIP_IN_TUNDRA)
        page.evaluate(DRY_DESERT)
        page.wait_for_timeout(300)
        grip_desert = page.evaluate("() => window.__probe.road.wetGrip()")
        res.check(grip_tundra < grip_desert - 0.05,
                  'and the tundra is permanently slipperier for it, with nothing added to say so',
                  'tundra %.3f, dry desert %.3f' % (grip_tundra, grip_desert))

        # ------------------------------------ the roadside is lit by the hour
        print()
        print('  THE ROADSIDE TAKES THE HOUR, not only the horizon')
        # The scenery sprites bake their colours, so without a rebuild keyed to the
        # hour a tree stays a daylight tree at midnight. Measured as the mean colour
        # of the built sprite, because the eye is not reliable here: the same rock
        # that measures (64,72,93) at night READS as pale against a very dark sky,
        # and chasing that impression cost a round of probing before the numbers
        # settled it.
        lightness = {}
        for label, ph in (('midday', 0.75), ('night', 0.25)):
            page.evaluate('(v) => window.__probe.road.setPhase(v)', ph)
            page.wait_for_timeout(250)
            rock = page.evaluate("() => window.__probe.road.sceneryPixel('MOUNTAIN', 0)")
            tree = page.evaluate("() => window.__probe.road.sceneryPixel('FOREST', 0)")
            sky = page.evaluate("() => window.__probe.road.skylinePixel('MOUNTAIN')")
            # NOT named `lum`: there is a module-level lum() used earlier in this
            # function, and assigning the name here makes it local for the WHOLE
            # function - so the earlier call died with an unbound local.
            bright = lambda c: 0.2126*c['r'] + 0.7152*c['g'] + 0.0722*c['b']
            lightness[label] = (bright(rock), bright(tree), bright(sky))
            print('      %-8s rock %.1f   tree %.1f   skyline %.1f' % ((label,) + lightness[label]))
        res.check(lightness['night'][0] < lightness['midday'][0] - 8,
                  'the roadside rock is darker at night than at midday',
                  '%.1f vs %.1f' % (lightness['night'][0], lightness['midday'][0]))
        res.check(lightness['night'][1] < lightness['midday'][1] - 4,
                  'and so is the forest',
                  '%.1f vs %.1f' % (lightness['night'][1], lightness['midday'][1]))
        res.check(lightness['night'][2] < lightness['midday'][2],
                  'and the skyline behind them, which is what made the mismatch visible',
                  '%.1f vs %.1f' % (lightness['night'][2], lightness['midday'][2]))
        page.evaluate('() => window.__probe.road.setPhase(0.75)')

        # ------------------------------- the road widens and the cars do not
        print()
        print('  A WIDER ROAD, THE SAME CARS')
        # The owner widened the road to make the lanes bigger and got everything
        # scaled up instead, because a vehicle's width was a fraction of ROAD. The
        # car's drawn width must not move when the road does; the road's must.
        sizes = {}
        for road in (1900, 2300, 3000):
            page.evaluate('(r) => window.__probe.road.setRoadHalfWidth(r)', road)
            page.wait_for_timeout(220)
            got = page.evaluate(CAR_AND_ROAD)
            sizes[road] = got
            print('      ROAD %-6d car %-8s road edge %-8s' % (road, got['car'], got['edge']))
        cars = [sizes[r]['car'] for r in (1900, 2300, 3000)]
        edges = [sizes[r]['edge'] for r in (1900, 2300, 3000)]
        res.check(cars[0] and max(cars) - min(cars) < 0.5,
                  'the player car is the same width at every road width',
                  ' '.join(str(c) for c in cars))
        res.check(edges[0] and edges[2] > edges[0] * 1.3,
                  'while the road itself is visibly wider - so the check is not vacuous',
                  ' '.join(str(e) for e in edges))
        page.evaluate('(r) => window.__probe.road.setRoadHalfWidth(r)', 2300)

        # ------------------------------- a beam is only visible in the dark
        print()
        print('  HEADLIGHT BEAMS FOLLOW THE CLOCK, NOT THE WEATHER')
        # The owner saw beams on the road at midday and guessed it was the rain.
        # It was: lampsOn() treats weather as night by their own earlier ruling, so
        # a shower at noon switched the beams on. The LAMPS should still do that -
        # everyone drives with lights on in rain - but the pool of light lying on
        # the tarmac is invisible in daylight however wet it is.
        page.evaluate('() => window.__probe.road.setPhase(0.75)')
        page.evaluate("() => { const R = window.__probe.road; R.setSnow(0); R.setWet(1); }")
        page.wait_for_timeout(250)
        noon = page.evaluate('() => window.__probe.road.lightLevels()')
        page.evaluate('() => window.__probe.road.setPhase(0.25)')
        page.wait_for_timeout(250)
        dark = page.evaluate('() => window.__probe.road.lightLevels()')
        print('      midday in heavy rain: lamps %.2f  beam %.2f' % (noon['lamps'], noon['clock']))
        print('      midnight, same rain:  lamps %.2f  beam %.2f' % (dark['lamps'], dark['clock']))
        res.check(noon['lamps'] > 0.5,
                  'the LAMPS still come on in daytime rain, which is the owner ruling that stands',
                  '%.2f' % noon['lamps'])
        res.check(noon['clock'] < 0.04,
                  'but the BEAM does not - a light pool is invisible at noon however wet it is',
                  '%.2f' % noon['clock'])
        res.check(dark['clock'] > 0.5, 'and at night the beam is on',
                  '%.2f' % dark['clock'])
        page.evaluate("() => { const R = window.__probe.road; R.setWet(0); R.setPool(0); R.setPhase(0.75); }")

        # --------------------------- the destination sets the taper rate
        print()
        print('  SNOW LEAVING A FOREST, AND WHERE IT IS GOING')
        # Owner's three cases, in their words: to a tundra it should "more than
        # likely not even taper off at all", to a city "a normal rate", to a desert
        # "quickly taper off instead of just snapping off". Before this the engine
        # asked only whether the destination could produce the weather AT ALL, so a
        # tundra and a city were treated identically and a desert like both.
        taper = {}
        for dest in ('TUNDRA', 'CITY', 'FOREST', 'DESERT'):
            taper[dest] = page.evaluate('([d, s]) => window.__probe.road.weatherTaper(d, s)',
                                        [dest, True])
            print('      snow into %-9s support %.2f   taper over %.2f of the crossing'
                  % (dest, taper[dest]['support'], taper[dest]['span']))
        res.check(taper['TUNDRA']['span'] == 0,
                  'snow carried into a TUNDRA does not taper at all - it belongs there',
                  'span %.2f at support %.2f' % (taper['TUNDRA']['span'], taper['TUNDRA']['support']))
        res.check(taper['CITY']['span'] == 1,
                  'into a CITY it thins over the ordinary crossing',
                  'span %.2f at support %.2f' % (taper['CITY']['span'], taper['CITY']['support']))
        res.check(0 < taper['DESERT']['span'] < 0.5,
                  'and into a DESERT it goes quickly - but it still goes, rather than snapping',
                  'span %.2f at support %.2f' % (taper['DESERT']['span'], taper['DESERT']['support']))
        res.check(taper['DESERT']['span'] < taper['CITY']['span'] < 1.01
                  and taper['TUNDRA']['span'] < taper['DESERT']['span'],
                  'so the three cases the owner named are three different behaviours',
                  'tundra %.2f, city %.2f, desert %.2f'
                  % (taper['TUNDRA']['span'], taper['CITY']['span'], taper['DESERT']['span']))

        # ---------------------------- a place has a climate, a day has weather
        # ---- THE TWO-TEMPERATURE MODEL (RLG-109) ---------------------------------------
        # The table states a temperature and a precipitation chance and NOTHING ELSE about
        # weather. Rain, snow and the ground floor all derive, and they derive at two
        # different moments - the instance when the place opens, the fall when the weather
        # rolls. Everything below is about that split, because it is the whole design and
        # none of it can be read off the recipes.
        print()
        print('  A PLACE HAS A CLIMATE, A DAY HAS WEATHER')
        keys = page.evaluate('() => window.__probe.road.BIOME_KEYS()')
        clim = {}
        for k in keys:
            clim[k] = page.evaluate('(k) => window.__probe.road.climateFor(k)', k)
        for k in sorted(keys, key=lambda x: -clim[x]['temp']):
            c = clim[k]
            print('      %-9s temp %.2f  precip %.2f  ->  rain %.3f  snow %.3f  floor %.2f'
                  % (k, c['temp'], c['precip'], c['rain'], c['snow'], c['snowFloor']))

        # THE IMPOSSIBLE STATE IS GONE, and this is the check that says so. MOUNTAIN used to
        # declare rain 0.30 AND snow 0.34 - two independent rolls summing to 0.64 - so the
        # place was asked twice whether it had any weather at all. One chance, split by
        # temperature, cannot express that. The split must be EXACT, not merely close.
        worst = max(abs(clim[k]['rain'] + clim[k]['snow'] - clim[k]['precip']) for k in keys)
        res.check(worst < 1e-3,
                  'rain and snow are one precipitation chance split, never two chances summed',
                  'the largest disagreement between rain+snow and precip is %.5f' % worst)

        # THE INSTANCE IS ROLLED, AND `vary` IS HOW WIDELY. A city has no climate of its own
        # and rolls the widest range on the board; a desert is defined by its extreme and
        # barely moves. This is what replaced a `neutral` boolean - neutrality by degrees.
        spread = {}
        for k in ('CITY', 'DESERT', 'TUNDRA'):
            t = page.evaluate('([k, n]) => window.__probe.road.rollClimateFor(k, n)', [k, 400])
            spread[k] = {'lo': min(t), 'hi': max(t), 'n': len(set(t))}
            print('      %-8s rolls temperatures from %.2f to %.2f over 400 visits'
                  % (k, spread[k]['lo'], spread[k]['hi']))
        # 200 distinct of 400, not 400 of 400. A tundra at 0.05 with a range of 0.10 rolls
        # BELOW freezing about a quarter of the time and every one of those clamps to
        # exactly 0, so a hundred rolls legitimately share one value. What this has to
        # falsify is a build that reads the table, and that build returns 1.
        res.check(all(spread[k]['n'] > 200 for k in spread),
                  'the temperature is ROLLED each visit rather than read from the table',
                  '%s distinct values of 400 rolls each' % {k: spread[k]['n'] for k in spread})
        res.check(spread['CITY']['hi'] - spread['CITY']['lo']
                  > (spread['DESERT']['hi'] - spread['DESERT']['lo']) * 3,
                  'and a place with no climate of its own ranges far wider than one defined by its extreme',
                  'city spans %.2f, desert spans %.2f'
                  % (spread['CITY']['hi'] - spread['CITY']['lo'],
                     spread['DESERT']['hi'] - spread['DESERT']['lo']))

        # ---- SNOW IS AN EVENT, NOT A PROPERTY -----------------------------------------
        # Owner, 2026-08-31: "I wonder if snow is too rare. Like for example, farmland can
        # be snowy, but you have snow chance at zero."
        #
        # THE MOMENT IS WHAT ANSWERS THAT, and it is why there are two temperatures rather
        # than one wider one. Computing the split from the PLACE's temperature dry-locks
        # everything above 0.50 out of snow for ever. The moment rolls within `swing` of the
        # instance, so a temperate place has snowy days without being a cold place - and the
        # same one number leaves the desert dry and the tundra white.
        print()
        print('  THE MOMENT DECIDES WHAT FALLS, so a temperate place still has snowy days')
        mom = {}
        for k in ('FOREST', 'CITY', 'DESERT', 'TUNDRA', 'SWAMP'):
            mom[k] = page.evaluate('([k, n]) => window.__probe.road.rollMomentsFor(k, undefined, n)',
                                   [k, 1200])
            print('      %-8s at its stated %.2f: snow on %.1f%% of events, rain on %.1f%%'
                  % (k, mom[k]['temp'],
                     100 * mom[k]['snow'] / max(1 - mom[k]['dry'], 1e-9),
                     100 * mom[k]['rain'] / max(1 - mom[k]['dry'], 1e-9)))
        forest_share = mom['FOREST']['snow'] / max(1 - mom['FOREST']['dry'], 1e-9)
        res.check(0.05 < forest_share < 0.60,
                  'a temperate place snows on some of its falls and rains on most of them',
                  'the forest snows on %.1f%% of what falls on it' % (100 * forest_share))
        res.check(mom['DESERT']['snow'] == 0 and mom['SWAMP']['snow'] == 0,
                  'and the hot places never do, over 1,200 events each',
                  'desert %.4f, swamp %.4f' % (mom['DESERT']['snow'], mom['SWAMP']['snow']))
        # AND NOT "EFFECTIVELY EVERYTHING", which is what this asserted first and is wrong
        # by the model rather than by the tuning. A tundra at 0.05 has moments up to 0.30,
        # and 0.30 is above freezing - so about a fifth of what falls on it falls as cold
        # rain. That is the swing doing its job at the cold end as well as the warm one,
        # and a place where it can ONLY ever snow would be the property this model exists
        # to delete. What matters is that it is far snowier than a temperate place.
        tundra_share = mom['TUNDRA']['snow'] / max(1 - mom['TUNDRA']['dry'], 1e-9)
        res.check(tundra_share > 0.70,
                  'and the coldest one snows on most of what it gets, though not on all of it',
                  'the tundra snows on %.1f%% of what falls on it' % (100 * tundra_share))
        res.check(tundra_share > forest_share * 2,
                  'so the cold place is markedly snowier than the temperate one, which is the ordering',
                  'tundra %.1f%% against forest %.1f%%'
                  % (100 * tundra_share, 100 * forest_share))
        # ONE NUMBER FIXING ALL THREE is the test of a model rather than of a tuning, so the
        # three above are asserted against ONE `swing`, read from the engine rather than
        # assumed by the harness.
        res.check(0 < clim['FOREST']['swing'] < 0.5,
                  'and all three come off one global swing rather than three tuned numbers',
                  'swing %.2f' % clim['FOREST']['swing'])

        # ---- THE FALSIFICATION: A CHECK THAT READS THE RECIPE STAYS GREEN --------------
        # This is the failure the whole refactor had to avoid, so it is asserted directly.
        # A cold-rolled city snows and a warm-rolled one cannot, and the RECIPE cannot tell
        # them apart - it has one city in it. If the engine ever goes back to answering
        # from the table, these two reads become identical and this check fails.
        cold_city = page.evaluate("() => window.__probe.road.climateFor('CITY', 0.05)")
        hot_city = page.evaluate("() => window.__probe.road.climateFor('CITY', 0.85)")
        recipe = page.evaluate("() => window.__probe.road.climateFor('CITY')")
        print('      one CITY recipe: cold instance snows %.3f, warm instance snows %.3f, '
              'the recipe says %.3f'
              % (cold_city['snow'], hot_city['snow'], recipe['snow']))
        res.check(cold_city['snow'] > 0.25 and hot_city['snow'] == 0,
                  'ONE recipe gives a city that snows and a city that cannot, by its instance',
                  'cold %.3f, warm %.3f' % (cold_city['snow'], hot_city['snow']))
        res.check(cold_city['canSnow'] and not hot_city['canSnow'],
                  'and the capability follows the instance too, which is what ends weather that cannot happen',
                  'cold canSnow %s, warm canSnow %s' % (cold_city['canSnow'], hot_city['canSnow']))

        # ---- AND THE GAME ITSELF ROLLS AGAINST IT, WHICH IS THE ONLY CLAIM THAT MATTERS -
        # Everything above re-runs the model through a probe, and a probe would go on
        # agreeing with itself on a build whose `rollWeather` had quietly gone back to the
        # recipe. This calls the ENGINE's own roll, in the place the car is standing in,
        # and counts what came out of it.
        #
        # THIS IS THE CHECK THAT CATCHES THE HALF-MIGRATION. Against a build that rolls the
        # weather off the recipe, both cities below give the recipe's answer - about a
        # tenth snow - and the cold one stops being a snowy city.
        live = {}
        for label, t in (('cold', 0.02), ('warm', 0.85)):
            page.evaluate('(t) => window.__probe.road.setBiomePair("CITY","CITY",t,t)', t)
            live[label] = page.evaluate('(n) => window.__probe.road.sampleWeatherRolls(n)', 600)
            print('      the ENGINE rolling in a %s CITY (temp %.2f): snow %.3f  rain %.3f  dry %.3f'
                  % (label, live[label]['temp'], live[label]['snow'],
                     live[label]['rain'], live[label]['dry']))
        # 0.10, NOT 0.25. This was calibrated against the table's own precipitation, before
        # RLG-136 scaled how often it rains at all - a cold city rolled snow on 0.362 of
        # rolls and now rolls it on 0.167. What is asserted is unchanged in kind: a cold
        # city snows and a warm one cannot. Only the frequency behind it moved.
        res.check(live['cold']['snow'] > 0.10 and live['warm']['snow'] == 0,
                  'the ENGINE rolls its weather against the instance, so a cold city snows and a warm one cannot',
                  'cold %.3f, warm %.3f' % (live['cold']['snow'], live['warm']['snow']))
        # AND THE PLACE'S TOTAL WEATHER IS UNCHANGED BY ITS TEMPERATURE, which is the
        # property the two stored chances could violate: the temperature decides WHAT falls
        # and the precipitation decides WHETHER, and the two are separate questions.
        wet_cold = 1 - live['cold']['dry']
        wet_warm = 1 - live['warm']['dry']
        res.check(abs(wet_cold - wet_warm) < 0.08,
                  'and it rolls weather as often either way - the temperature says what falls, not whether',
                  'cold has weather on %.1f%% of rolls, warm on %.1f%%'
                  % (100 * wet_cold, 100 * wet_warm))
        page.evaluate("() => window.__probe.road.setBiomePair('FOREST','FOREST')")

        # ---- AND HOW OFTEN IT RAINS AT ALL (RLG-136) ------------------------------------
        # Owner, 2026-08-31, after twenty to thirty minutes of play: "it seemed to precipitate
        # a lot. Maybe we should reduce the overall chances of precipitation." The table
        # averaged 0.366 and the weather rolls every 35 to 80 seconds, which is nine or ten
        # events in a twenty-five minute session.
        #
        # THE LEVER IS ASSERTED, NOT THE NUMBER. How much weather a session should carry is
        # the owner's to choose by playing, so what this checks is that ONE multiplier moves
        # the whole board and that the places keep their relationship to each other - which is
        # what makes it a lever rather than eleven separate edits.
        print()
        print('  AND HOW OFTEN IT RAINS AT ALL, AS ONE LEVER')
        scale = page.evaluate('() => window.__probe.road.precipScale()')
        page.wait_for_timeout(150)
        here = page.evaluate('(n) => window.__probe.road.sampleWeatherRolls(n)', 900)
        page.evaluate('() => window.__probe.road.precipScale(1.0)')
        full = page.evaluate('(n) => window.__probe.road.sampleWeatherRolls(n)', 900)
        page.evaluate('(v) => window.__probe.road.precipScale(v)', scale)
        back = page.evaluate('() => window.__probe.road.precipScale()')
        wet_now, wet_full = 1 - here['dry'], 1 - full['dry']
        print('      a forest: weather on %.0f%% of rolls at a scale of %.2f, %.0f%% unscaled'
              % (wet_now * 100, scale, wet_full * 100))
        res.check(0 < scale < 1,
                  'the board is scaled back from the table it states',
                  'the scale is %.2f' % scale)
        res.check(wet_now < wet_full * 0.8,
                  'and it really does rain less often, measured through the engine own roll',
                  '%.3f of rolls against %.3f unscaled' % (wet_now, wet_full))
        res.check(abs(back - scale) < 1e-9,
                  'and the lever is live, so it can be dialled on a device without a rebuild',
                  'it read %.2f after being set back' % back)
        # AND THE PLACES KEEP THEIR ORDER. A lever that flattened the board would make every
        # place equally wet, which is a different change from making everywhere drier.
        page.evaluate("() => window.__probe.road.setBiomePair('SWAMP','SWAMP')")
        page.wait_for_timeout(200)
        swamp = page.evaluate('(n) => window.__probe.road.sampleWeatherRolls(n)', 900)
        page.evaluate("() => window.__probe.road.setBiomePair('DESERT','DESERT')")
        page.wait_for_timeout(200)
        desert = page.evaluate('(n) => window.__probe.road.sampleWeatherRolls(n)', 900)
        print('      a swamp still has weather on %.0f%% of rolls, a desert on %.0f%%'
              % ((1 - swamp['dry']) * 100, (1 - desert['dry']) * 100))
        res.check((1 - swamp['dry']) > (1 - desert['dry']) * 5,
                  'and a swamp is still far wetter than a desert, so the board was scaled not flattened',
                  'swamp %.3f against desert %.3f' % (1 - swamp['dry'], 1 - desert['dry']))
        page.evaluate("() => window.__probe.road.setBiomePair('FOREST','FOREST')")

        # ------------------------------ the biome shapes the road itself
        print()
        print('  THE BIOME SHAPES THE ROAD')
        shapes = {}
        for k in ('MOUNTAIN', 'TUNDRA', 'FOREST', 'DESERT', 'CITY'):
            shapes[k] = page.evaluate('(k) => window.__probe.road.roadShape(k)', k)
            print('      %-9s climbs %.2f   turns %.2f'
                  % (k, shapes[k]['hill'], shapes[k]['bend']))
        order = ['MOUNTAIN', 'TUNDRA', 'FOREST', 'DESERT', 'CITY']
        hills = [shapes[k]['hill'] for k in order]
        res.check(all(a >= b for a, b in zip(hills, hills[1:])),
                  'the ordering is the owner\'s: mountain at one extreme, city at the other',
                  ' '.join('%.2f' % v for v in hills))
        res.check(shapes['MOUNTAIN']['hill'] > shapes['DESERT']['hill'] > shapes['CITY']['hill'],
                  'and desert climbs more than city, which is the pair the owner named',
                  'desert %.2f, city %.2f' % (shapes['DESERT']['hill'], shapes['CITY']['hill']))
        res.check(min(shapes[k]['hill'] for k in order) > 0
                  and min(shapes[k]['bend'] for k in order) > 0,
                  'NEVER COMPLETELY FLAT - the owner said so twice, so nothing is zero',
                  'flattest climb %.2f, straightest turn %.2f'
                  % (min(shapes[k]['hill'] for k in order),
                     min(shapes[k]['bend'] for k in order)))
        res.check(shapes['MOUNTAIN']['hill'] <= 1.0 and shapes['MOUNTAIN']['bend'] <= 1.0,
                  'and nothing exceeds the road as it was, because the corner cap is a renderer limit',
                  'mountain climbs %.2f turns %.2f'
                  % (shapes['MOUNTAIN']['hill'], shapes['MOUNTAIN']['bend']))

        # the FACTORS are one thing; what the generator actually produces is another
        print('    the generator over 4,000 segments each')
        gen = {}
        for k in order:
            gen[k] = page.evaluate('([k, n]) => window.__probe.road.sampleShape(k, n)', [k, 4000])
            print('      %-9s mean turn %.2f   mean climb %.2f'
                  % (k, gen[k]['bend'], gen[k]['hill']))
        gbend = [gen[k]['bend'] for k in order]
        ghill = [gen[k]['hill'] for k in order]
        res.check(all(a > b for a, b in zip(ghill, ghill[1:])),
                  'the road the generator MAKES climbs less at every step down the order',
                  ' '.join('%.2f' % v for v in ghill))
        res.check(gen['MOUNTAIN']['bend'] > gen['CITY']['bend'] * 2.5,
                  'and a mountain turns more than twice as hard as a city',
                  'mountain %.2f, city %.2f' % (gen['MOUNTAIN']['bend'], gen['CITY']['bend']))


        # ------------------------------- the sea is beside the road, one side
        print()
        # ---- THE COAST HAS AN OPEN SKY (RLG-059) ------------------------------------------
        # Owner, with the coastal rename: the coast gets an open sky. Cloud cover comes from a
        # place's own rain and snow, so a coast that rains a third of the time was as grey as
        # anywhere else that does. `sky` is a multiplier on that tendency, and every place that
        # does not state one gets 1.
        #
        # SAMPLED FROM THE GAME'S OWN ROLL, not from the formula. A check that computed
        # `rain * 1.6 * sky` itself would agree with a copy of the code rather than with the code,
        # and would go on agreeing after somebody changed it.
        print()
        print('  THE COAST HAS AN OPEN SKY, AND IT IS A TENDENCY RATHER THAN A SPECIAL CASE')
        cover = {}
        for k in ('COASTAL', 'FOREST', 'SWAMP', 'DESERT', 'CITY'):
            rolls = page.evaluate('([k, n]) => window.__probe.road.rollSkyFor(k, n)', [k, 400])
            rolls.sort()
            cover[k] = {'median': rolls[len(rolls) // 2], 'worst': rolls[-1],
                        'clear': sum(1 for v in rolls if v < 0.25) / len(rolls)}
            print('      %-8s median cover %.3f   heaviest %.3f   clear %.0f%% of the time'
                  % (k, cover[k]['median'], cover[k]['worst'], cover[k]['clear'] * 100))

        # A coast rains almost as often as a forest - 0.34 against 0.42 - so before this they sat
        # within a whisker of each other. The point of the ruling is that they should not.
        res.check(cover['COASTAL']['median'] < cover['FOREST']['median'] * 0.75,
                  'the coast is clearer than a forest that rains about as often',
                  'coast %.3f against forest %.3f'
                  % (cover['COASTAL']['median'], cover['FOREST']['median']))
        res.check(cover['COASTAL']['clear'] > 0.5,
                  'and it is clear more often than not',
                  'clear on only %.0f%% of rolls' % (cover['COASTAL']['clear'] * 100))
        # AND IT IS STILL A SKY. An open sky is not a switched-off one: the coast rains, and rain
        # needs a sky to fall out of. A `sky` of zero would pass both checks above.
        res.check(cover['COASTAL']['worst'] > 0.30,
                  'and it still clouds over sometimes, because it still rains',
                  'the heaviest cover a coast ever rolls is %.3f' % cover['COASTAL']['worst'])
        res.check(cover['FOREST']['median'] > cover['DESERT']['median'] * 3,
                  'and a place that states no bias still takes its cloud from its own weather',
                  'forest %.3f against desert %.3f - they should be far apart'
                  % (cover['FOREST']['median'], cover['DESERT']['median']))
        # ---- AND THE BIAS IS WHAT DOES IT, WHICH THIS PAIR ISOLATES (RLG-109) ----------
        # This used to read "the coast is the only place carrying a number", and under the
        # derived table that is no longer true - the swamp carries 1.10 and the tundra
        # 0.90. The claim that survives is the mechanism rather than the exclusivity.
        #
        # COAST AGAINST CITY IS THE CONTROLLED PAIR, and it is better than what was here:
        # both precipitate on exactly 0.38 of rolls, so precipitation is held constant and
        # the bias is the ONLY thing left that can separate them. The old comparison took
        # the minimum of three places whose rain differed, which measured the rain as much
        # as it measured the bias.
        biasC = page.evaluate("() => window.__probe.road.climateFor('COASTAL')")
        biasT = page.evaluate("() => window.__probe.road.climateFor('CITY')")
        print('      coast precip %.2f bias %.2f   against city precip %.2f bias %.2f'
              % (biasC['precip'], biasC['bias'], biasT['precip'], biasT['bias']))
        res.check(abs(biasC['precip'] - biasT['precip']) < 1e-6,
                  'the coast and the city rain equally often, so only the bias can separate them',
                  'coast %.3f, city %.3f' % (biasC['precip'], biasT['precip']))
        res.check(cover['CITY']['median'] > cover['COASTAL']['median'] * 1.6,
                  'and the coast is markedly clearer for the same rainfall, which is the bias',
                  'city %.3f against the coast %.3f, a ratio of %.2f against a stated %.2f'
                  % (cover['CITY']['median'], cover['COASTAL']['median'],
                     cover['CITY']['median'] / max(cover['COASTAL']['median'], 1e-6),
                     biasT['bias'] / biasC['bias']))
        # AND NO SKY IS EVER TOTAL. The owner's "always allow for some clear sky, no matter
        # what", as one ceiling rather than as a habit of the roll. The wettest place on the
        # board is the one that tests it.
        res.check(max(cover[k]['worst'] for k in cover) <= 0.881,
                  'and nowhere fills the whole sky, however wet it is',
                  'the heaviest cover any place rolled is %.3f'
                  % max(cover[k]['worst'] for k in cover))

        print('  THE COASTAL IS ON ONE SIDE, AND WHICH SIDE IS ROLLED')
        seaB = page.evaluate("() => window.__probe.road.roadShape('COASTAL')")
        sides = []
        for _ in range(40):
            page.evaluate("() => window.__probe.road.startBiomeChange('COASTAL')")
            sides.append(page.evaluate('() => window.__probe.road.seaSide()'))
        left = sides.count(-1)
        print('      over 40 placements: %d left, %d right' % (left, len(sides) - left))
        res.check(all(v in (-1, 1) for v in sides),
                  'the water is on a side, never both and never neither', str(set(sides)))
        res.check(3 < left < 37,
                  'and the side is genuinely rolled rather than fixed',
                  '%d left of 40' % left)
        page.evaluate("() => window.__probe.road.setBiomePair('FOREST','FOREST')")

        # ------------------------- swamp and coast are the flattest of all
        flat = {}
        for k in ('SWAMP', 'COASTAL', 'CITY', 'MOUNTAIN'):
            flat[k] = page.evaluate('(k) => window.__probe.road.roadShape(k)', k)
        print('      climb: swamp %.2f  ocean %.2f  city %.2f  mountain %.2f'
              % (flat['SWAMP']['hill'], flat['COASTAL']['hill'],
                 flat['CITY']['hill'], flat['MOUNTAIN']['hill']))
        res.check(flat['SWAMP']['hill'] < flat['CITY']['hill']
                  and flat['COASTAL']['hill'] < flat['CITY']['hill'],
                  'swamp and coast are flatter than the city - both are at sea level',
                  'swamp %.2f, ocean %.2f, city %.2f'
                  % (flat['SWAMP']['hill'], flat['COASTAL']['hill'], flat['CITY']['hill']))
        res.check(flat['SWAMP']['hill'] > 0 and flat['COASTAL']['hill'] > 0,
                  'and still never completely flat',
                  '%.2f and %.2f' % (flat['SWAMP']['hill'], flat['COASTAL']['hill']))

        # ------------------------------------------- and the distinction can fail
        print()
        print('  NOT VACUOUS - the old flip goes back and the sweep check must catch it')
        flip = page.evaluate("""() => {
          const R = window.__probe.road;
          /* the old behaviour: the biome changes everywhere at once, so every segment
             reports the same mix and there is no travel to see */
          R.setBiomePair('DESERT', 'DESERT');
          const s = R.biomeSweep();
          return { atCar:s.atCar, atHorizon:s.atHorizon };
        }""")
        res.check(abs(flip['atHorizon'] - flip['atCar']) < 0.001,
                  'with the flip back, the car and the horizon agree - which the check above forbids',
                  'car %.3f, horizon %.3f' % (flip['atCar'], flip['atHorizon']))

        # ---------------------------------- and a place is a DISTANCE, not a wait
        # Owner, 2026-08-30, from the device: park at the side of the road and the biome
        # changes anyway, without the car having moved. It did - the countdown was
        # `biomeNext -= dt`, so a place lasted seventy to a hundred and thirty SECONDS of
        # sitting still as readily as of driving.
        #
        # THE COUNTDOWN IS PUT WITHIN REACH RATHER THAN WAITED OUT. It runs to between six
        # and a half and twelve miles, so a harness cannot drive or sit through one. The
        # boundary is placed a few hundred units ahead instead, which is under a tenth of a
        # second at speed and for ever at a standstill. That is the whole distinction.
        page.evaluate("""() => { const R = window.__probe.road;
            R.setBiomePair('DESERT', 'DESERT'); R.setSpd(0); R.biomeCountdown(600); }""")
        page.wait_for_timeout(2500)
        parked = page.evaluate("""() => { const R = window.__probe.road;
            const s = R.biomeSweep();
            return { left: R.biomeCountdown(), from: s.from, to: s.to }; }""")
        print('      parked for 2.5s with 600 units to run: %.0f left, from=%s to=%s'
              % (parked['left'], parked['from'], parked['to']))
        res.check(parked['from'] == parked['to'],
                  'parking at the side of the road does not change the biome',
                  'it went from %s to %s without the car moving'
                  % (parked['from'], parked['to']))
        res.check(abs(parked['left'] - 600) < 1.0,
                  'and the distance to the next place does not run down while stopped',
                  '%.1f units left of 600 after two and a half seconds parked'
                  % parked['left'])

        # AND DRIVING SPENDS IT. Without this the check above passes on a build where the
        # countdown never moves at all, which is a different bug wearing the same result.
        #
        # WHAT SPENDING IT DOES CHANGED AT 0.11.20 (RLG-150). It used to place the boundary
        # at the horizon there and then, so the pair flipped within a second of driving.
        # It now PLANS the place at the generator's own frontier and tells the picture
        # later, when the car arrives - because the road that far ahead is already made,
        # and a place chosen after its road was built got the previous place's bendiness
        # for its first 70,000 units. So the countdown running out and the pair changing
        # are two events with a drive between them, and this checks both.
        page.evaluate("""() => { const R = window.__probe.road;
            R.setSpd(R.MAX_SPD * 0.8); }""")
        page.wait_for_timeout(900)
        drove = page.evaluate("""() => { const R = window.__probe.road;
            const s = R.biomeSweep(), pl = R.roadPlan();
            return { left: R.biomeCountdown(), from: s.from, to: s.to,
                     plan: pl.key, edgeZ: pl.edgeZ, pos: pl.pos, madeTo: pl.madeTo }; }""")
        print('      then driving for 0.9s: %.0f left, from=%s to=%s, planned=%s at %s'
              % (drove['left'], drove['from'], drove['to'], drove['plan'], drove['edgeZ']))
        res.check(drove['left'] > 600,
                  'and driving spends the distance, which re-arms it for the next place',
                  'still %.0f units left after driving' % drove['left'])
        res.check(drove['plan'] is not None,
                  'and what it buys is a PLANNED place, chosen before its road is made',
                  'nothing was planned when the countdown ran out')
        # NOT `edgeZ >= madeTo` HERE, WHICH IS WHAT THIS ASKED FIRST AND WHY IT FAILED.
        # That holds at the INSTANT of planning and is asserted there, in
        # `place-shape-test`. Nine tenths of a second later the generator has quite
        # properly run on past the planned edge - and everything it made out there is
        # inside the new place, with the new place's factor, which is the fix working.
        # What is true for as long as a plan is pending is that its edge is still more
        # than a draw distance ahead, because arriving within one is what places it.
        res.check(drove['edgeZ'] is not None
                  and drove['edgeZ'] > drove['pos'] + 150 * 200 - 400,
                  'whose edge is still beyond the horizon, which is why the picture has '
                  'not been told (RLG-150)',
                  'edge %s with the car at %s' % (drove['edgeZ'], drove['pos']))
        res.check(drove['from'] == drove['to'],
                  'and the picture is NOT told yet - it is still one place, all the way out',
                  'the pair already reads %s to %s' % (drove['from'], drove['to']))

        # AND DRIVING TO THE PLANNED EDGE IS WHAT CHANGES THE PICTURE. The boundary still
        # enters at the horizon and travels in, which is RLG-022 - it is just placed at a
        # point that was decided earlier.
        target = drove['edgeZ']
        for _ in range(900):
            page.evaluate('() => { const R = window.__probe.road; R.setSpd(R.MAX_SPD); }')
            page.wait_for_timeout(40)
            if page.evaluate('() => window.__probe.road.roadPlan()')['key'] is None:
                break
        arrived = page.evaluate("""() => { const R = window.__probe.road;
            const s = R.biomeSweep();
            return { from: s.from, to: s.to, edge: s.edge, here: s.here }; }""")
        print('      driving on to the planned edge at %s: from=%s to=%s'
              % (target, arrived['from'], arrived['to']))
        res.check(arrived['from'] != arrived['to'],
                  'and driving up to that edge is what puts the new place in the picture',
                  'still %s to %s after driving to the planned edge'
                  % (arrived['from'], arrived['to']))
        res.check(arrived['here'] + 150 >= arrived['edge'] > arrived['here'],
                  'and it is placed AT THE HORIZON, a draw distance ahead, not underfoot',
                  'edge at segment %s with the car at %s' % (arrived['edge'], arrived['here']))

        errs = page.evaluate('() => window.__probe.errors')
        res.check(not errs, 'no page errors during the run', '; '.join(errs[:3]))
        browser.close()
    httpd.shutdown()

    print()
    if res.fails:
        print('  %d FAILED: %s' % (len(res.fails), '; '.join(res.fails)))
        return 1
    print('  the biome arrives at the horizon and drives toward you')
    return 0


if __name__ == '__main__':
    sys.exit(main())
