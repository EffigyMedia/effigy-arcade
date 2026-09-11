#!/usr/bin/env python3
"""
SKYLINE TEST - the city is the place's, not the hour's.

    .venv/Scripts/python tools/skyline-test.py
    .venv/Scripts/python tools/skyline-test.py --headed --shots

RLG-094. The owner reported the skyline jittering and popping, in both the forward view and the
rear-view. It was not a parallax fault. The plan - where every building, peak and tree stands, how
wide and how tall, and which of a tower's windows exist - was built from `Math.random()` inside
`buildSkyline`, and RLG-080 makes that function run whenever the hour BUCKET moves: one fortieth of
a 240-second day, so EVERY SIX SECONDS. The whole horizon was replaced by a different horizon ten
times a minute, in both views at the same instant, because both draw from one cache.

WHAT THIS ASSERTS, AND THE ORDER MATTERS. The silhouette must not change while the car is in one
place. The colour must change all day, because that is what RLG-080 was built for and it is still
wanted. A check that only asserted the first would pass on a skyline frozen at midnight, which is a
different fault and a worse one.

AND IT HAS TO CROSS A BUCKET BOUNDARY OR IT PROVES NOTHING. The fault does not exist inside a
bucket - the broken engine returns a cached sprite there and is stable. So the bucket is read
alongside every sample and the run asserts it moved. That assertion is the whole difference between
this file and one that passes on both builds.

THE SILHOUETTE IS READ AS A PROFILE, not as a pixel count. Two different cities can cover the same
area; `API.skylineProfile` returns the topmost opaque row in each of the sprite's 1024 columns,
which is the outline a player actually sees against the sky.

Exit code 0 if every check passed, 1 otherwise.
"""

import argparse
import base64
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

/* one sample: the hour, the bucket that decides when the sprite is rebuilt, the SHAPE, and the
   COLOUR. The last two are the two halves of the ruling and they are read together so a run cannot
   report one without the other. */
window.__probe.sample = function(key){
  var R = window.__probe.road;
  return { phase: R.phase(), bucket: R.skyBucket(), lamps: R.lampsOn(),
           prof: R.skylineProfile(key), pix: R.skylinePixel(key),
           lit: R.skylineLit(key), clock: R.windowClock() };
};

/* the horizon band as the player sees it, for the eye */
window.__probe.shot = function(){
  var R = window.__probe.road, c = document.querySelector('canvas');
  var dpr = c.width / c.getBoundingClientRect().width;
  var hz = R.horizon() * dpr, band = c.height * 0.14;
  var out = document.createElement('canvas');
  out.width = c.width; out.height = Math.round(band);
  var g = out.getContext('2d');
  g.drawImage(c, 0, Math.round(hz - band*0.80), c.width, out.height, 0, 0, out.width, out.height);
  return out.toDataURL('image/png');
};
"""

# the day is 240 seconds and a bucket is a fortieth of it, so this many phase steps walk well past
# several boundaries without waiting six real seconds for each
PHASES = [0.10, 0.14, 0.18, 0.22, 0.30, 0.42, 0.55, 0.68, 0.80, 0.92]
# the colour has to travel at least this far across the day, in summed RGB distance. A silhouette
# that never changed colour would satisfy every shape check in this file and be the opposite fault.
MIN_COLOUR_TRAVEL = 24
# where to move the windows' own clock to. A window's cycle is between 26 and 190 seconds, so these
# have to be minutes apart to see the slow ones turn over, and a check that waited in real time
# would take three minutes to ask one question.
WINDOW_CLOCK = [0, 40, 95, 170, 260, 400]


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


def prof_diff(a, b):
    """How many of the 1024 columns changed height, and by how much at worst."""
    n = sum(1 for x, y in zip(a, b) if x != y)
    worst = max((abs(x - y) for x, y in zip(a, b)), default=0)
    return n, worst


def rgb_dist(a, b):
    return abs(a['r'] - b['r']) + abs(a['g'] - b['g']) + abs(a['b'] - b['b'])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--headed', action='store_true')
    ap.add_argument('--shots', action='store_true')
    ap.add_argument('--out', default=None)
    ap.add_argument('--biome', default='CITY')
    args = ap.parse_args()
    console_utf8()
    res = Results()
    out = Path(args.out) if args.out else ROOT / '_skyline'
    httpd, port = serve(ROOT)
    print('skyline-test  .  the city is the place\'s, not the hour\'s')
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
        page.wait_for_timeout(2000)

        # ONE PLACE, PINNED. The skyline is per biome, so a biome change between two samples would
        # legitimately change the silhouette and this file would be measuring the wrong thing.
        biomes = page.evaluate("() => window.__probe.road.biomeNames "
                               "? window.__probe.road.biomeNames() : null")
        key = args.biome
        if biomes and key not in biomes:
            key = biomes[0]
        page.evaluate("(k) => { const R = window.__probe.road;"
                      " if(R.setBiomePair) R.setBiomePair(k, k); R.setSpd(0); }", key)
        page.wait_for_timeout(300)
        print('  the place: %s' % key)

        samples = []
        for ph in PHASES:
            page.evaluate("(v) => window.__probe.road.setPhase(v)", ph)
            page.wait_for_timeout(180)
            samples.append(page.evaluate("(k) => window.__probe.sample(k)", key))
            if args.shots:
                out.mkdir(parents=True, exist_ok=True)
                data = page.evaluate("() => window.__probe.shot()").split(',', 1)[1]
                (out / ('hz-%03d.png' % round(ph * 1000))).write_bytes(base64.b64decode(data))

        buckets = [s['bucket'] for s in samples]
        print('  buckets walked: ' + ' '.join(str(b) for b in buckets))
        print()

        # ---- the instrument -----------------------------------------------------------------
        # The fault does not exist inside one bucket. If the run never crossed a boundary, every
        # shape check below would pass on the broken engine too.
        res.check(len(set(buckets)) >= 5,
                  'the run crossed several hour buckets, so the rebuild actually fired',
                  'only %d distinct bucket(s) in %d samples' % (len(set(buckets)), len(samples)))

        # ---- the shape holds ----------------------------------------------------------------
        base = samples[0]
        worst_cols, worst_px, worst_at = 0, 0, None
        for s in samples[1:]:
            cols, px = prof_diff(base['prof'], s['prof'])
            if cols > worst_cols:
                worst_cols, worst_px, worst_at = cols, px, s['bucket']
        res.check(worst_cols == 0,
                  'the silhouette does not change as the day turns',
                  '%d of %d columns moved, worst by %dpx, by bucket %s'
                  % (worst_cols, len(base['prof']), worst_px, worst_at))
        print('        columns that moved across the whole day: %d of %d'
              % (worst_cols, len(base['prof'])))

        # ---- and the colour still travels ----------------------------------------------------
        # Without this the fix could be "never rebuild the sprite", which passes every check above
        # and is the fault RLG-080 was raised to remove.
        cols = [s['pix'] for s in samples]
        travel = max(rgb_dist(a, b) for a in cols for b in cols)
        res.check(travel >= MIN_COLOUR_TRAVEL,
                  'and it still takes the hour\'s light, so the sprite is not simply frozen',
                  'colour travelled only %d across the day, wanted %d' % (travel, MIN_COLOUR_TRAVEL))
        print('        colour travelled %d across the day  (%s -> %s)'
              % (travel,
                 'rgb(%d,%d,%d)' % (cols[0]['r'], cols[0]['g'], cols[0]['b']),
                 'rgb(%d,%d,%d)' % (cols[-1]['r'], cols[-1]['g'], cols[-1]['b'])))

        # ---- the area is a second, blunter witness -------------------------------------------
        px = [s['pix']['px'] for s in samples]
        res.check(len(set(px)) == 1,
                  'and the silhouette covers the same area at every hour',
                  'pixel counts %s' % sorted(set(px)))
        print()

        # ---- THE CITY IS AWAKE, AND NOT ALL AT ONCE (RLG-095) -------------------------------
        # Owner: the skyline does not have dynamic window lights like it used to. It never had them
        # by design - one sheet at one global alpha - and what was moving was RLG-094's defect
        # regenerating the sheet every six seconds. The habit is on the window now.
        #
        # THE HOUR IS PINNED TO NIGHT AND THE DAY DOES NOT MOVE for this section. The windows run on
        # their own clock, so nothing here needs the sun; leaving the hour walking as well would
        # mean two things changing at once and no way to say which did it.
        print('  the windows')
        page.evaluate("() => window.__probe.road.setPhase(0.25)")
        # AND THE WINDOW CLOCK IS HELD, so a sample is taken at exactly the time it was set to.
        # Without the hold the clock keeps running while the read happens, so each sample lands at
        # `t` plus a hundred-odd milliseconds of wall clock - and a window sitting on the edge of
        # its cycle flips between two samples that were meant to be identical. The frozen-clock
        # control below went red on about one run in three for exactly that reason, reporting a
        # defect that was in the harness.
        page.evaluate("() => window.__probe.road.holdWindowClock(true)")
        page.wait_for_timeout(200)
        night = []
        for t in WINDOW_CLOCK:
            page.evaluate("(t) => window.__probe.road.windowClock(t)", t)
            page.wait_for_timeout(160)
            night.append(page.evaluate("(k) => window.__probe.sample(k)", key))

        res.check(all(n['lamps'] > 0.5 for n in night),
                  'the hour is dark enough for the city to be lit at all',
                  'lampsOn read %s' % [n['lamps'] for n in night])

        # 1. THE PATTERN MOVES.
        base_cols = night[0]['lit']['cols']
        moved = max(sum(1 for a, b in zip(base_cols, n['lit']['cols']) if a != b) for n in night[1:])
        res.check(moved > 0,
                  'windows switch on and off as the night goes on',
                  'not one of %d columns changed across %s seconds of window clock'
                  % (len(base_cols), WINDOW_CLOCK[-1] - WINDOW_CLOCK[0]))
        print('        columns whose lit count changed: %d of %d' % (moved, len(base_cols)))

        # 2. AND THE SILHOUETTE STILL DOES NOT. This is what stops RLG-095 being built by putting
        #    RLG-094's defect back: regenerating the city would satisfy the check above.
        shape_moved = max(prof_diff(night[0]['prof'], n['prof'])[0] for n in night[1:])
        res.check(shape_moved == 0,
                  'and the buildings do not move while their windows do',
                  '%d columns of silhouette moved - the city is being rebuilt again' % shape_moved)

        # 3. NOT ALL AT ONCE. A city where every window shares one clock is a pulse, not a place -
        #    the same fault RLG-012 recorded about a thruster on a single sine.
        counts = [n['lit']['px'] for n in night]
        swing = max(counts) - min(counts)
        res.check(0 < swing < max(counts) * 0.5,
                  'and they do not switch in unison',
                  'lit pixels ran %s - a swing of %d against a peak of %d'
                  % (counts, swing, max(counts)))
        print('        lit pixels across the night: %s' % counts)
        print()

        # AND THE SAME CHECK WITH THE CLOCK HELD STILL. The assertion above is about change over
        # time, so the way to show it is not vacuous is to take the time away: same hour, same
        # clock, six samples. If the pattern still "moves" it is reading noise.
        held = []
        for _ in WINDOW_CLOCK:
            page.evaluate("(t) => window.__probe.road.windowClock(t)", 120)
            page.wait_for_timeout(160)
            held.append(page.evaluate("(k) => window.__probe.sample(k)", key))
        still = max(sum(1 for a, b in zip(held[0]['lit']['cols'], h['lit']['cols']) if a != b)
                    for h in held[1:])
        res.check(still == 0,
                  'with the window clock held still nothing switches, so the check reads time',
                  '%d columns changed with the clock frozen' % still)
        print('        with the clock held at 120s: %d columns changed' % still)

        page.evaluate("() => window.__probe.road.holdWindowClock(false)")
        print()

        # ---- and the same check, with the defect put back ------------------------------------
        # Reverting the engine cannot falsify this file: the instrument that reads the silhouette
        # does not exist on the broken build. So the FAULT is reintroduced instead. Forgetting the
        # plan cache between samples is precisely what the old engine did on every rebuild - the
        # plan came from `Math.random()` inside the painter, so a new sprite was a new city.
        print('  the same check, with the plan forgotten between samples')
        broken = []
        for ph in PHASES[:5]:
            page.evaluate("() => window.__probe.road.forgetSkylinePlans()")
            page.evaluate("(v) => window.__probe.road.setPhase(v)", ph)
            page.wait_for_timeout(180)
            broken.append(page.evaluate("(k) => window.__probe.sample(k)", key))
        bad_cols = max(prof_diff(broken[0]['prof'], b['prof'])[0] for b in broken[1:])
        res.check(bad_cols > 0,
                  'with the plan re-rolled the silhouette check goes red, so it was measuring shape',
                  'the city was rebuilt from scratch and not one of %d columns moved'
                  % len(broken[0]['prof']))
        print('        columns that moved: %d of %d' % (bad_cols, len(broken[0]['prof'])))
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
    if args.shots:
        print('  shots in ' + str(out))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
