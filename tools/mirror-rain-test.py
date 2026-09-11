#!/usr/bin/env python3
"""
MIRROR RAIN TEST - the weather falls in the rear-view as well.

    .venv/Scripts/python tools/mirror-rain-test.py
    .venv/Scripts/python tools/mirror-rain-test.py --headed --shots

RLG-092. Owner, 2026-08-31: rain and snow should be shown in the rear view - the precipitation
itself, not the drops on the glass, which belong to the windscreen. RLG-079 had already ruled that
the mirror shows the world state it is in and asks the SAME functions the windscreen asks; falling
weather was the part of that world state which never got carried across.

WHY THIS DOES NOT MEASURE THE OBVIOUS THING. "The mirror looks different when it rains" was true
BEFORE this was built, and it would pass on the old engine: the mirror already darkens its tarmac
and lifts its ground toward white, because those come from the shared surface code RLG-079 wired
up. A check written that way would report a feature that is not there.

SO THE COMPARISON IS PARTICLES AGAINST NO PARTICLES, in one and the same wet scene. `mirrorRain`
takes a count and zero means off, so the harness can remove the feature through the public API
without touching the engine, and the only difference between the two frames is the thing that was
asked for. The world is frozen for both - biome pinned, car parked, sky pinned - so nothing else
can move between them.

AND THE CHECK IS SHOWN TO FAIL. The last section runs the same assertion with the count at zero and
requires it to go red. A check nobody has watched fail is not evidence, and four guards in this
project passed with the bug present before they were fixed.

WHAT IT CANNOT SAY. Whether twenty particles in a pane 59 pixels tall reads as weather or as static
is a judgement on a device. `--shots` writes the glass enlarged so that judgement can be made from a
picture instead of from this number.

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
window.__probe = { errors: [], road: null, slots: {} };
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

/* WHERE THE GLASS IS COMES FROM THE ENGINE. `tools/mirror-shot.py` keeps its own copy of the
   layout formula and the copy is three changes out of date - it still reads 0.62 of the width
   capped at 250 with a fixed height of 44, against 0.80 capped at 340. `API.mirrorRect()` is
   written by the same code that draws the pane, so it cannot drift. */
window.__probe.pane = function(){
  var R = window.__probe.road, c = document.querySelector('canvas');
  var r = R.mirrorRect();
  var dpr = c.width / c.getBoundingClientRect().width;
  return { x: Math.round(r.x*dpr), y: Math.round(r.y*dpr),
           w: Math.round(r.w*dpr), h: Math.round(r.h*dpr), css: r, dpr: dpr };
};

/* The pane's luminance, pixel by pixel, kept in the page. Twenty thousand numbers per frame is not
   something to send over the wire once per sample, and the comparison is a subtraction. */
window.__probe.grab = function(slot){
  var p = window.__probe.pane();
  var c = document.querySelector('canvas'), g = c.getContext('2d');
  var d = g.getImageData(p.x, p.y, p.w, p.h).data;
  var out = new Float64Array(d.length/4), sum = 0;
  for(var i = 0, j = 0; i < d.length; i += 4, j++){
    out[j] = 0.2126*d[i] + 0.7152*d[i+1] + 0.0722*d[i+2];
    sum += out[j];
  }
  window.__probe.slots[slot] = out;
  return { n: out.length, mean: sum/out.length, w: p.w, h: p.h };
};

/* HOW MANY PIXELS THE WEATHER LIT, and by how much. Precipitation ADDS light - a streak is a pale
   line and a flake is a white disc - so the measure is one-sided on purpose. A two-sided
   difference would also count the scene getting darker, which is the surface code's job and was
   already there before this. */
/* AND A TWO-SIDED ONE, because a checkpoint gantry is dark steel and a green board against a
   road and a sky: it DARKENS about as much of the glass as it lightens, and the one-sided
   measure below would score half of it as nothing. Weather keeps the one-sided measure for the
   reason stated there; furniture needs this one. */
window.__probe.changed = function(a, b, thr){
  var A = window.__probe.slots[a], B = window.__probe.slots[b];
  if(!A || !B || A.length !== B.length) return null;
  var n = 0, sum = 0;
  for(var i = 0; i < A.length; i++){
    var d = Math.abs(A[i] - B[i]);
    if(d > thr){ n++; sum += d; }
  }
  return { px: n, share: n/A.length, ink: sum/A.length };
};
window.__probe.brighter = function(a, b, thr){
  var A = window.__probe.slots[a], B = window.__probe.slots[b];
  if(!A || !B || A.length !== B.length) return null;
  var n = 0, sum = 0;
  for(var i = 0; i < A.length; i++){
    var d = A[i] - B[i];
    if(d > thr){ n++; sum += d; }
  }
  return { px: n, share: n/A.length, light: sum/A.length };
};

/* ---- THE ROAD BEHIND IS SWEPT EVERY FRAME -------------------------------------------------
   Parking the car is what CAUSES this. Below 42 per cent of top speed for two seconds the engine
   starts feeding traffic in from behind, faster the slower you are - so a harness that stops the
   car to hold the scene still has asked for cars to arrive in the one view it is measuring. Two
   of them turned up in a ten-second run and lit 1.6 per cent of the pane, which is four times the
   threshold this file asserts against.

   Clearing once is not enough and clearing every frame is not quite enough either: a car that
   spawns and is drawn in the same tick is swept before the next frame but is in that one. So the
   sweeper counts what it removed, and the sampling below takes a MEDIAN rather than a maximum,
   which one contaminated frame in six cannot move.
   ------------------------------------------------------------------------------------------ */
window.__probe.swept = 0;
window.__probe.holdEmpty = false;
(function sweep(){
  var R = window.__probe.road;
  if(R && window.__probe.holdEmpty && R.trafficCount() > 0){
    window.__probe.swept += R.trafficCount();
    R.clearTraffic();
  }
  requestAnimationFrame(sweep);
})();

/* the glass, enlarged, for the judgement this harness cannot make */
window.__probe.shot = function(zoom){
  var p = window.__probe.pane(), c = document.querySelector('canvas');
  var out = document.createElement('canvas');
  out.width = Math.round(p.w*zoom); out.height = Math.round(p.h*zoom);
  var g = out.getContext('2d');
  g.imageSmoothingEnabled = false;
  g.drawImage(c, p.x, p.y, p.w, p.h, 0, 0, out.width, out.height);
  return out.toDataURL('image/png');
};
"""

# a pixel has to gain this much luminance before it counts as lit by the weather. Below about 2 the
# canvas's own rounding of a translucent fill starts to register on pixels nothing was drawn on.
THR = 3.0
# and this share of the pane has to be lit before the weather is visible rather than incidental. A
# single streak 15 pixels long at one pixel wide is 0.05 per cent of a 340x59 pane, so a field that
# reads as weather sits well above this and a field that has been switched off sits at zero.
MIN_SHARE = 0.004
# the frozen scene, sampled twice with nothing changed, must not move by more than this. If it does,
# the instrument is measuring the world rather than the weather and no number below means anything.
CONTROL_SHARE = 0.0008


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


FREEZE = """() => {
  const R = window.__probe.road;
  /* the biome is pinned so the scenery behind the glass cannot change between two samples, and
     pinned to the DARKEST of them, because pale weather has least room to show on a dark ground */
  if(R.setBiomePair) R.setBiomePair('FOREST', 'FOREST');
  R.jumpTo(12000);
  R.setLane(0);
  R.setSpd(0);
  R.setSky(0.35, 0);
  R.setWet(0);
  R.setSnow(0);
  /* AND THE ROAD BEHIND IS EMPTIED, which parking the car does not do. Traffic keeps driving when
     the player stops, and the mirror is the one view that watches it - so a car crossing the glass
     between two samples lit 21.9 per cent of the pane on a build with the weather switched off,
     four times what the rain itself lights. The dry control caught it; it read 0.0000 on the run
     before, which is a scene that happened to be empty at that moment rather than a stable one. */
  R.clearTraffic();
}"""

# emptied again before every baseline, and counted afterwards, because a spawn between two samples
# would be the same fault wearing a different hat
CLEAR = "() => window.__probe.road.clearTraffic()"
COUNT = "() => window.__probe.road.trafficCount()"

# THE STANDING WATER AND THE SETTLED SNOW ARE PINNED AT THEIR CEILING, not left to fill.
# Both accumulate for as long as the weather lasts - `pool` at about 0.054 a second - and a wet
# road is BRIGHTER in the distance because it reflects the sky, so a road that is still filling
# gets brighter between two samples all on its own. That drift read as 12.5 per cent of the pane
# on the first version of this file, which is three times what the rain itself lights, and it was
# indistinguishable from the feature working. At the ceiling neither can move.
DRY = "() => { const R = window.__probe.road; R.setWet(0); R.setSnow(0); R.setPool(0); }"
RAIN = "() => { const R = window.__probe.road; R.setSnow(0); R.setWet(0.9); R.setPool(1); }"
SNOW = "() => { const R = window.__probe.road; R.setWet(0.9); R.setSnow(1); R.setPool(0); }"
SET_N = "(n) => window.__probe.road.mirrorRain({ n: n })"

GRAB = "(s) => window.__probe.grab(s)"
DIFF = "([a,b,t]) => window.__probe.brighter(a,b,t)"
SHOT = "(z) => window.__probe.shot(z)"


def typical(page, base, frames=7):
    """How much of the pane the weather lights, in a typical frame. The MEDIAN of several.

    Not the maximum, which was the first version of this. The field is steady enough for a median
    to be fair - the particle count never changes, they only wrap from the bottom back to the top -
    and a maximum is exactly the statistic a single contaminated frame can walk away with. A car
    spawning behind the player is drawn once before the sweeper removes it, and under a maximum
    that one frame became the answer.
    """
    got = []
    for _ in range(frames):
        page.wait_for_timeout(70)
        page.evaluate(GRAB, 'live')
        r = page.evaluate(DIFF, ['live', base, THR])
        if r:
            got.append(r)
    if not got:
        return {'px': 0, 'share': 0.0, 'light': 0.0}
    got.sort(key=lambda r: r['share'])
    return got[len(got)//2]


def write_shot(page, out, name):
    out.mkdir(parents=True, exist_ok=True)
    data = page.evaluate(SHOT, 4).split(',', 1)[1]
    (out / name).write_bytes(base64.b64decode(data))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--headed', action='store_true')
    ap.add_argument('--shots', action='store_true', help='write the glass enlarged, for the eye')
    ap.add_argument('--out', default=None)
    args = ap.parse_args()
    console_utf8()
    res = Results()
    out = Path(args.out) if args.out else ROOT / '_mirror-rain'
    httpd, port = serve(ROOT)
    print('mirror-rain-test  .  the weather falls in the rear-view as well')
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

        page.evaluate(FREEZE)
        page.evaluate("() => { window.__probe.holdEmpty = true; window.__probe.swept = 0; }")
        page.wait_for_timeout(600)

        pane = page.evaluate("() => window.__probe.pane()")
        print('  the glass: %dx%d device pixels (%.0fx%.0f css, dpr %.2f)'
              % (pane['w'], pane['h'], pane['css']['w'], pane['css']['h'], pane['dpr']))
        num = page.evaluate("() => window.__probe.road.mirrorRain()")
        print('  its numbers: %d particles, streak %.2f of the pane, fall %.2f against the screen'
              % (num['n'], num['len'], num['fall']))
        print()

        # ---- the instrument ----------------------------------------------------------------
        # Nothing may move in a frozen scene. If it does, every number below is noise.
        print('  the instrument')
        page.evaluate(DRY)
        page.wait_for_timeout(400)
        page.evaluate(CLEAR)
        page.evaluate(GRAB, 'dry')
        page.wait_for_timeout(300)
        ctl = typical(page, 'dry', frames=5)
        res.check(ctl['share'] <= CONTROL_SHARE,
                  'the frozen dry scene holds still between samples',
                  'moved on %.4f%% of the pane, limit %.4f%%'
                  % (ctl['share'] * 100, CONTROL_SHARE * 100))
        print('        dry against dry: %.4f%% of the pane' % (ctl['share'] * 100))
        if args.shots:
            write_shot(page, out, 'dry.png')
        print()

        # ---- rain ---------------------------------------------------------------------------
        print('  rain')
        page.evaluate(RAIN)
        page.evaluate(SET_N, 0)          # the wet world, with the falling weather removed
        page.wait_for_timeout(600)
        page.evaluate(CLEAR)
        page.evaluate(GRAB, 'rainOff')
        wet_dry = page.evaluate(DIFF, ['rainOff', 'dry', THR])
        print('        the wet scene without particles, against dry: %.3f%% of the pane brighter'
              % (wet_dry['share'] * 100))
        # THE SAME CHECK, WITH THE FEATURE REMOVED, AND IT RUNS FIRST. The count is still zero
        # here, so this is the assertion below measuring a mirror with no weather in it. It is
        # taken in the same settled scene, seconds apart, because a negative control run at the
        # end of the file measured a different world and reported the drift between them.
        gone = typical(page, 'rainOff', frames=5)
        res.check(gone['share'] < MIN_SHARE,
                  'with no particles the check goes red, so it measures them and nothing else',
                  'still lit %.3f%% of the pane with the weather off' % (gone['share'] * 100))
        print('        with the weather in the glass off: %.4f%% of the pane lit, against a '
              '%.3f%% threshold' % (gone['share'] * 100, MIN_SHARE * 100))
        if args.shots:
            write_shot(page, out, 'rain-off.png')

        page.evaluate(SET_N, num['n'])
        page.wait_for_timeout(400)
        rain = typical(page, 'rainOff')
        res.check(rain['share'] >= MIN_SHARE,
                  'rain falls in the mirror',
                  'lit %.3f%% of the pane over the same wet scene, wanted %.3f%%'
                  % (rain['share'] * 100, MIN_SHARE * 100))
        print('        with them: %.3f%% of the pane lit, %d pixels'
              % (rain['share'] * 100, rain['px']))
        if args.shots:
            write_shot(page, out, 'rain.png')

        # ---- and it MOVES, which is what tells it from a drop on the lens --------------------
        page.evaluate(GRAB, 'r1')
        page.wait_for_timeout(90)
        page.evaluate(GRAB, 'r2')
        moved = page.evaluate(DIFF, ['r2', 'r1', THR])
        res.check(moved['share'] > CONTROL_SHARE,
                  'and it is falling, not sitting on the glass',
                  'two consecutive frames differ on only %.4f%% of the pane'
                  % (moved['share'] * 100))
        print('        frame to frame: %.3f%% of the pane changed' % (moved['share'] * 100))
        print()

        # ---- snow ---------------------------------------------------------------------------
        print('  snow')
        page.evaluate(SNOW)
        page.evaluate(SET_N, 0)
        page.wait_for_timeout(600)
        page.evaluate(CLEAR)
        page.evaluate(GRAB, 'snowOff')
        snowGone = typical(page, 'snowOff', frames=5)
        res.check(snowGone['share'] < MIN_SHARE,
                  'and the snow check goes red with the particles off as well',
                  'still lit %.3f%% of the pane' % (snowGone['share'] * 100))
        print('        with the weather in the glass off: %.4f%% of the pane lit'
              % (snowGone['share'] * 100))
        if args.shots:
            write_shot(page, out, 'snow-off.png')
        page.evaluate(SET_N, num['n'])
        page.wait_for_timeout(400)
        snow = typical(page, 'snowOff')
        res.check(snow['share'] >= MIN_SHARE,
                  'snow falls in the mirror',
                  'lit %.3f%% of the pane over the same snowy scene, wanted %.3f%%'
                  % (snow['share'] * 100, MIN_SHARE * 100))
        print('        with them: %.3f%% of the pane lit, %d pixels'
              % (snow['share'] * 100, snow['px']))
        if args.shots:
            write_shot(page, out, 'snow.png')
        print()

        swept = page.evaluate("() => window.__probe.swept")
        print('  the sweeper removed %d vehicle%s that spawned behind the parked car'
              % (swept, '' if swept == 1 else 's'))
        res.check(page.evaluate(COUNT) == 0, 'the road behind is empty at the end')

        # ---- AND THE CHECKPOINT BOARDS ARE IN THERE (RLG-108) --------------------
        # Owner, 2026-08-31: "checkpoint signs aren't shown in the rearview mirror by the
        # way." They are road furniture standing in the world, and the mirror is a picture of
        # the world behind the car - the same gap RLG-079 closed for the sky, the ground, the
        # scenery, the treeline and the cars.
        #
        # IT LIVES HERE because this file already owns the machinery the ruling asked for: the
        # pane's own rectangle taken from the engine, a per-pixel grab kept in the page, and a
        # difference between two grabs. Copying that into a fourth file to ask one more question
        # of the same glass would be three chances for the copies to drift apart.
        #
        # THE WORLD IS HELD STILL FOR IT. The car is stopped, the road is swept and the weather
        # is off, so the ONLY thing differing between the two grabs is whether a board is
        # standing behind the car. Without that the glass changes on its own every frame and the
        # difference would be measuring the traffic.
        print('\n  the checkpoint boards in the glass (RLG-108)')
        # HELD EVERY FRAME, NOT ONCE. The weather rolls back on its own, the road refills
        # with traffic, and either one repaints the glass - so a scene set still at the top
        # of a measurement is not still by the time it is sampled. Measured with the board
        # pass removed, a run that set them once read 27.47% of the pane changing between
        # two grabs of an unchanged world; held every frame it reads 0.07%.
        HOLD = """() => { const R = window.__probe.road;
            R.setWet(0); R.setSnow(0); R.setPool(0); R.clearTraffic(); R.setSpd(0); }"""

        def settle(page, frames=14):
            for _ in range(frames):
                page.evaluate(HOLD)
                page.wait_for_timeout(24)

        def median_change(page, boards, base):
            """How much the glass differs from `base`, in a TYPICAL frame rather than in one.

            THE MEDIAN, and this file already learnt why: a car spawning behind the player is
            drawn once before the sweeper removes it, and a single contaminated frame is exactly
            what a maximum walks away with. Sweeping every frame is not enough either - the
            spawner puts a car on the road between two sweeps and it is drawn in between.
            """
            got = []
            for _ in range(9):
                page.evaluate("(n) => window.__probe.road.parkGantry(n)", boards)
                settle(page, 4)
                page.evaluate(GRAB, 'live')
                r = page.evaluate("([a,b,t]) => window.__probe.changed(a,b,t)",
                                  ['live', base, THR])
                if r:
                    got.append(r)
            got.sort(key=lambda r: r['share'])
            return got[len(got)//2]

        page.evaluate("() => window.__probe.road.parkGantry(null)")
        settle(page, 20)
        none_there = page.evaluate('() => window.__probe.road.gantries()')
        page.evaluate(GRAB, 'nosign')
        # ---- 20,000, NOT 4,000 (RLG-133) --------------------------------------------------
        # This read 4,000, and boards used to be deleted at 8,000 - so the probe parked one
        # INSIDE the range that survived and the check answered yes on a build where a real
        # board, passed at speed, had already gone. A probe whose default sits inside the bug
        # cannot see the bug. 20,000 is past the old cull and well inside the glass's 34,000,
        # so a board only reaches it if the retention is right.
        with_board = median_change(page, 20000, 'nosign')
        one_there = page.evaluate('() => window.__probe.road.gantries()')
        # AND A CONTROL: the same measurement with NO board parked. The world is held still, so
        # this is what "nothing changed" looks like - and it is what stops the check above
        # passing on a glass that merely churns. With the board pass removed from the engine and
        # the scene set still only once, a run read 27.48% with a board against 27.47% without.
        still = median_change(page, None, 'nosign')
        print('      boards on the road: %d with none parked, %d with one'
              % (none_there, one_there))
        print('      the glass changed by %.2f%% with a board, %.2f%% with nothing'
              % (with_board['share'] * 100, still['share'] * 100))
        res.check(none_there == 0 and one_there == 1,
                  'a board can be parked behind the car and only one is there',
                  '%d then %d' % (none_there, one_there))
        # THE CONTROL IS CHECKED FIRST, because everything after it depends on the glass
        # being still. With the board pass removed and the world set still only once, a run
        # read 27.48% with a board against 27.47% without - and a bare "did the glass change"
        # check passes happily on that. It is not evidence of a board; it is evidence that
        # the measurement is worthless.
        res.check(still['share'] < 0.02,
                  'the glass is still when nothing is behind the car, so the rest can be read',
                  'it changed %.2f%% on its own, which is more than a board is worth'
                  % (still['share'] * 100))
        res.check(with_board['share'] > 0.01,
                  'a checkpoint board behind the car shows up in the mirror',
                  'only %.3f%% of the glass differs, which is nothing appearing'
                  % (with_board['share'] * 100))
        res.check(with_board['share'] > still['share'] * 4 + 0.005,
                  'and it is the board rather than the glass simply moving',
                  'a board changed %.2f%% against %.2f%% for an unchanged world'
                  % (with_board['share'] * 100, still['share'] * 100))

        # ---- AND THE FINISH LINE, WHICH WAS NEVER IN THE GLASS AT ALL (RLG-133) -----------
        # Owner, 2026-08-31: "I still don't think I see the back of the checkpoints or the
        # finish line in the rearview mirror." Two faults in one sentence: the boards above
        # were being deleted, and the banner had no mirror painter on any build. `drawFinish`
        # is a forward painter that stops 600 units past the line.
        #
        # THE SAME SHAPE OF MEASUREMENT, and it needs the same control. `parkFinish` puts the
        # run into a race, because the banner does not exist outside one - it reports the mode
        # it found so this cannot pass by measuring a mode that never draws it.
        page.evaluate("() => window.__probe.road.parkGantry(null)")
        far = page.evaluate("() => window.__probe.road.parkFinish(400000)")
        settle(page, 20)
        page.evaluate(GRAB, 'nofin')
        fin_still = []
        fin_seen = []
        for _ in range(9):
            page.evaluate("() => window.__probe.road.parkFinish(400000)")
            settle(page, 4)
            page.evaluate(GRAB, 'live')
            r = page.evaluate("([a,b,t]) => window.__probe.changed(a,b,t)", ['live', 'nofin', THR])
            if r: fin_still.append(r['share'])
            page.evaluate("() => window.__probe.road.parkFinish(20000)")
            settle(page, 4)
            page.evaluate(GRAB, 'live')
            r = page.evaluate("([a,b,t]) => window.__probe.changed(a,b,t)", ['live', 'nofin', THR])
            if r: fin_seen.append(r['share'])
        fin_still.sort(); fin_seen.sort()
        m_still = fin_still[len(fin_still)//2] if fin_still else 0
        m_seen = fin_seen[len(fin_seen)//2] if fin_seen else 0
        print('      the race mode for the banner: was %s, now %s' % (far['wasMode'], far['mode']))
        print('      the glass changed by %.2f%% with the finish line behind, %.2f%% with it far away'
              % (m_seen * 100, m_still * 100))
        res.check(far['mode'] == 'race',
                  'the banner is measured in the mode that draws it', 'mode %s' % far['mode'])
        res.check(m_still < 0.02,
                  'and the glass is still with the line out of range, so the rest can be read',
                  'it changed %.2f%% on its own' % (m_still * 100))
        res.check(m_seen > 0.01,
                  'the FINISH LINE behind the car shows up in the mirror',
                  'only %.3f%% of the glass differs, which is nothing appearing' % (m_seen * 100))
        res.check(m_seen > m_still * 4 + 0.005,
                  'and it is the banner rather than the glass simply moving',
                  'the line changed %.2f%% against %.2f%% for an unchanged world'
                  % (m_seen * 100, m_still * 100))

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
