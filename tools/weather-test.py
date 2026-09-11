#!/usr/bin/env python3
"""
WEATHER PAINT TEST - the weather is on the surfaces, not over the frame.

    .venv/Scripts/python tools/weather-test.py
    .venv/Scripts/python tools/weather-test.py --headed

RLG-057. Snow cover and rain darkening used to be screen-wide rectangles drawn after the road
and after the player, so the car got as snowed on as the ground it was standing on, and a hill a
quarter of a mile away got as wet as the tarmac under the wheels. The owner rejected the snow
half of that on sight. Both are painted per segment now, mixed into each surface's own colour.

WHAT MAKES THIS A TEST AND NOT A SCREENSHOT. Reading pixels off a live frame proves nothing in
this engine - the road scrolls, the sky turns, and the tarmac strobes light and dark by segment.
This project has been burnt by that already: `lamp-test.py` read 100% and then 35% on
consecutive runs of one unchanged build. So the world is stopped first. The car is parked at a
fixed `z` at zero speed with the sky pinned, and every reading comes from that frozen frame with
nothing changed between samples except the weather.

AND THE CHECK IS SHOWN TO FAIL. The assertion that carries this file is that the PLAYER'S CAR
does not change colour when the weather does - which is precisely what the rejected build got
wrong. A check nobody has watched fail is not evidence, so the last section puts the old
full-screen wash back through `CFG.afterDraw`, touching no game file, and asserts that the same
check goes red. If it does not, this harness is measuring nothing.

Exit code 0 if every check passed, 1 otherwise.
"""

import argparse
import functools
import http.server
import socketserver
import sys
import threading
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from harness import console_utf8, launch_chromium, boot, until

ROOT = Path(__file__).resolve().parent.parent
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
        window.__probe.cfg = CFG;
        var api = real(CFG);
        window.__probe.road = api || (CFG && CFG.api) || null;
        return api;
      };
    }
  });
})();
window.addEventListener('error', function(e){ window.__probe.errors.push(String(e.message)); });

/* The mean colour of a box on the canvas, read out of the backing store. A screenshot would go
   through a PNG encode and the page's own scaling; these are the pixels the engine drew. */
window.__probe.sample = function(x, y, w, h){
  var c = document.querySelector('canvas');
  var g = c.getContext('2d');
  var d = g.getImageData(Math.round(x), Math.round(y), Math.max(1, Math.round(w)),
                         Math.max(1, Math.round(h))).data;
  var r = 0, gg = 0, b = 0, n = d.length / 4;
  for(var i = 0; i < d.length; i += 4){ r += d[i]; gg += d[i+1]; b += d[i+2]; }
  return { r: r/n, g: gg/n, b: b/n, lum: (0.2126*r + 0.7152*gg + 0.0722*b) / n };
};
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


FREEZE = """() => {
  const R = window.__probe.road;
  /* THE BIOME IS PINNED, and to the DARKEST of them. It is picked fresh on every
     load, and the rain darkening has least room to show on a dark ground - the
     verge check went red on runs that landed in FOREST and passed on runs that
     landed in DESERT, on one unchanged build. Pinning to the worst case means a
     pass here is a pass everywhere, which a random biome could never promise. */
  if(R.setBiomePair) R.setBiomePair('FOREST', 'FOREST');
  R.jumpTo(12000);
  R.setLane(0);
  R.setSpd(0);
  R.setSky(0.2, 0);
  R.setWet(0);
  R.setSnow(0);
}"""

GEO = """() => {
  const R = window.__probe.road, c = document.querySelector('canvas');
  return { W: c.width, H: c.height, horizon: R.horizon(), player: R.playerScreen() };
}"""

# Thunder's own calls and nobody else's. The wrap goes on, the sound is made, and the wrap comes off
# inside one evaluate, so nothing another system happens to play in the same window can land in the
# list. An earlier version wrapped, waited four seconds and read whatever had accumulated: the engine
# and the tyres use the same `sfx.noise`, and the total came to 10.0 against a master bus of 0.85,
# which is not a measurement of thunder at all.
#
# It also calls `snd.thunder` rather than `API.strike`. `strike` is the LIGHTNING - it sets the flash
# and its magnitude and returns, and the sound is scheduled seconds later by the step loop from
# `thunderIn`. A harness that strikes and then listens hears nothing it caused.
# The two sounds are told apart by their FILTER, which is what makes them two sounds: the rumble is
# lowpass and the crack is highpass. Reading the gains alone could not say which was which, and a
# check that cannot name what it measured cannot tell a quiet crack from a quiet rumble.
THUNDER_BEDS = """([mag, far]) => {
  const AR = window.Arcade, R = window.__probe.road;
  const beds = [], real = AR.sfx.noise;
  AR.sfx.noise = function(o){
    beds.push({ gain: o.gain, filter: o.filter, freq: o.freq, dur: o.dur });
    return real.call(AR.sfx, o);
  };
  try { R.snd.thunder(mag, far); } finally { AR.sfx.noise = real; }
  return beds;
}"""


def split(beds):
    """The rumble is everything lowpassed; the crack is the highpassed bed, or nothing."""
    rumble = [b for b in beds if b['filter'] == 'lowpass']
    crack = [b for b in beds if b['filter'] == 'highpass']
    return rumble, crack

SAMPLE = """(spots) => {
  const S = window.__probe.sample, out = {};
  for(const k in spots){ const b = spots[k]; out[k] = S(b[0], b[1], b[2], b[3]); }
  return out;
}"""


def spots_for(geo):
    """Where to read. The car's rectangle comes from the engine, never from a guess.

    `playerScreen` is {x: centre, y: BOTTOM, w, h} - the sprite is drawn at (-w/2, -h) - so the
    bodywork box is taken above `y` rather than around it.
    """
    W, H, hz = geo['W'], geo['H'], geo['horizon']
    ground = H - hz
    out = {
        # tarmac, up the road and well clear of the car
        'road':  [W*0.45, hz + ground*0.42, W*0.10, ground*0.06],
        # the land at the edge of the frame, which is ground and never road
        'verge': [W*0.01, hz + ground*0.42, W*0.06, ground*0.06],
        # the band between the furthest drawn slice and the horizon
        'far':   [W*0.30, hz + ground*0.015, W*0.40, ground*0.025],
        # sky, which nothing painted on the ground may reach
        'sky':   [W*0.30, hz*0.40, W*0.40, hz*0.12],
    }
    p = geo['player']
    if p and p.get('w'):
        out['car'] = [p['x'] - p['w']*0.18, p['y'] - p['h']*0.62,
                      p['w']*0.36, p['h']*0.24]
        # TARMAC AT THE CAR'S OWN FEET, taken beside it rather than at a guessed
        # depth. A wet road is dark where you look down at it and bright where
        # you look along it, so one road sample cannot judge rain: this is the
        # near end, and `road` above is the far one.
        out['roadNear'] = [p['x'] + p['w']*0.62, p['y'] - p['h']*0.16,
                           p['w']*0.45, p['h']*0.12]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--headed', action='store_true')
    args = ap.parse_args()
    console_utf8()
    res = Results()
    httpd, port = serve(ROOT)
    print('weather-test  .  the weather is on the surfaces, not over the frame')
    with sync_playwright() as p:
        browser = launch_chromium(p, headless=not args.headed)
        page = browser.new_page(viewport={'width': 480, 'height': 900})
        page.add_init_script(INIT)
        boot(page, 'http://127.0.0.1:%d/%s' % (port, GAME))
        try:
            until(page, '() => navigator.serviceWorker && navigator.serviceWorker.controller',
                timeout=5000)
            page.wait_for_timeout(1200)
        except Exception:
            pass
        until(page, '!!window.__probe.road', timeout=10000)
        page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
        page.click('[data-act="play"]')
        page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
        # THE TIME OF DAY IS PINNED, and it has to be. A run started at DUSK drifts
        # into the night branch part way through, where the ground is already dark
        # and the rain darkening has almost no room to show - the verge check went
        # red on one run in six for exactly that reason, at a margin of about three.
        # Loosening the threshold would have hidden a real thing about the effect;
        # measuring it in daylight is what makes the number mean anything.
        for _ in range(6):
            label = page.eval_on_selector('[data-act="time"] b', 'el => el.textContent').strip()
            if label == 'MIDDAY':
                break
            page.click('[data-act="time"]')
            page.wait_for_timeout(70)
        res.check(page.eval_on_selector('[data-act="time"] b',
                                        'el => el.textContent').strip() == 'MIDDAY',
                  'the run is pinned to MIDDAY, so the readings are comparable')
        page.click('[data-act="drive"]')
        page.wait_for_timeout(1600)

        def settle_frame():
            page.evaluate(FREEZE)
            page.wait_for_timeout(450)

        def weather(wet, snow):
            page.evaluate("([w, s]) => { const R = window.__probe.road;"
                          " R.setSpd(0); R.setWet(w); R.setSnow(s); }", [wet, snow])
            page.wait_for_timeout(400)
            st = page.evaluate("() => { const R = window.__probe.road;"
                               " return { wet: R.wet(), snowy: R.snowy(), settle: R.settle(),"
                               " pool: R.pool(), biome: R.biome(), phase: R.phase() }; }")
            # PRINT WHAT WAS ACTUALLY SET. `setWet` and `setSnow` write variables the weather
            # timer also writes, so a reading taken on trust can be a reading of a state the
            # engine moved out from under the test.
            print('        state: wet %(wet)s  snowy %(snowy)s  settle %(settle)s'
                  '  pool %(pool)s  biome %(biome)s  phase %(phase)s' % st)
            return st

        settle_frame()
        geo = page.evaluate(GEO)
        res.check(bool(geo['player']), 'the engine reports where the player is drawn',
                  str(geo['player'])[:120])
        spots = spots_for(geo)
        res.check('car' in spots, 'the car has a rectangle to read from', str(sorted(spots)))
        dry = page.evaluate(SAMPLE, spots)

        print()
        print('  SNOW - the cover follows the ground')
        weather(0.9, 1.0)
        snow = page.evaluate(SAMPLE, spots)
        d = lambda k: snow[k]['lum'] - dry[k]['lum']
        res.check(d('verge') > 24, 'the ground brightens under full cover',
                  '%.1f -> %.1f' % (dry['verge']['lum'], snow['verge']['lum']))
        res.check(d('road') > 14, 'the road surface brightens with it',
                  '%.1f -> %.1f' % (dry['road']['lum'], snow['road']['lum']))
        res.check(d('far') > 14, 'the band under the horizon brightens too',
                  '%.1f -> %.1f' % (dry['far']['lum'], snow['far']['lum']))
        res.check(snow['road']['lum'] < snow['verge']['lum'],
                  'the road stays darker than the land, so the corridor is still readable',
                  'road %.1f vs verge %.1f' % (snow['road']['lum'], snow['verge']['lum']))
        res.check(abs(d('car')) < 6,
                  'the car is NOT snowed on - the cover is ground, not a wash over the frame',
                  '%.1f -> %.1f' % (dry['car']['lum'], snow['car']['lum']))
        res.check(abs(d('sky')) < 6, 'the sky is not touched by cover on the ground',
                  '%.1f -> %.1f' % (dry['sky']['lum'], snow['sky']['lum']))

        print()
        print('  RAIN - the darkening is on the slices')
        weather(0, 0)
        page.evaluate('() => window.__probe.road.setPool(0)')
        page.wait_for_timeout(300)
        base = page.evaluate(SAMPLE, spots)
        weather(1.0, 0)
        # the water is put on the road directly rather than waited for. Seventeen
        # seconds of real rain is what it takes to reach this, and a harness that
        # waits for it is a harness nobody runs.
        page.evaluate('() => window.__probe.road.setPool(1)')
        page.wait_for_timeout(300)
        # printed again, because the line above changed the state after the last
        # one was reported and a reader would otherwise credit the reading to the
        # wrong weather
        print('        state: ' + str(page.evaluate(
            "() => { const R = window.__probe.road;"
            " return 'wet ' + R.wet() + '  pool ' + R.pool() + '  grip ' + R.wetGrip(); }")))
        rain = page.evaluate(SAMPLE, spots)
        w = lambda k: rain[k]['lum'] - base[k]['lum']
        res.check(w('roadNear') < -4, 'the tarmac at the car soaks and goes dark',
                  '%.1f -> %.1f' % (base['roadNear']['lum'], rain['roadNear']['lum']))
        res.check(w('verge') < -3, 'the land darkens with it',
                  '%.1f -> %.1f' % (base['verge']['lum'], rain['verge']['lum']))
        res.check(w('roadNear') < w('road'),
                  'and the far road gives the sky back, so it loses less light than the near',
                  'near %.1f vs far %.1f' % (w('roadNear'), w('road')))
        res.check(abs(w('car')) < 8,
                  'the car is NOT painted with the road it is standing on',
                  '%.1f -> %.1f' % (base['car']['lum'], rain['car']['lum']))
        res.check(abs(w('sky')) < 4, 'and the sky above the horizon is left alone',
                  '%.1f -> %.1f' % (base['sky']['lum'], rain['sky']['lum']))

        print()
        print('  ACCUMULATION - both weathers build over time and unwind again')

        def slope(reader, seconds=3.0):
            a = page.evaluate(reader)
            time.sleep(seconds)
            b = page.evaluate(reader)
            return (b - a) / seconds, a, b

        def grip():
            return page.evaluate('() => window.__probe.road.wetGrip()')

        SETTLE = '() => window.__probe.road.settle()'
        POOL = '() => window.__probe.road.pool()'

        for name, reader, start, rate_floor in (
                ('snow', SETTLE, "() => { const R = window.__probe.road;"
                                 " R.setSnow(0.30); R.setWet(0.80); }", 0.010),
                ('rain', POOL, "() => { const R = window.__probe.road;"
                               " R.setSnow(0); R.setPool(0.30); R.setWet(0.80); }", 0.020)):
            page.evaluate(start)
            page.wait_for_timeout(400)
            up, u0, u1 = slope(reader)
            slick_building = grip()
            page.evaluate('() => window.__probe.road.setWet(0)')
            page.wait_for_timeout(400)
            # `slope` is signed and an unwind runs downhill, so the rate is its
            # negation. Comparing the raw value asserted that a falling number was
            # rising, which is a check that can only ever fail.
            fall, d0, d1 = slope(reader)
            down = -fall
            slick_after = grip()
            # rain runs off about twice as fast as snow melts, so each weather is
            # asked about its OWN ratio rather than about one shared number
            want = 1.0 if name == 'snow' else 2.0
            res.check(up > rate_floor, '%s: it builds while it falls' % name,
                      '%.4f/s, %s to %s' % (up, u0, u1))
            res.check(down > rate_floor, '%s: and it unwinds once it stops' % name,
                      '%.4f/s, %s to %s' % (down, d0, d1))
            res.check(up > 0 and abs(down - up*want) < up*want*0.35,
                      '%s: it comes off at the rate it went on' % name,
                      'up %.4f/s, down %.4f/s, wanted %.1fx' % (up, down, want))
            res.check(slick_after > slick_building,
                      '%s: and the grip comes back as it goes' % name,
                      'grip %.3f while building, %.3f after' % (slick_building, slick_after))

        print()
        print('  DEEP IS WORSE THAN FALLING - what lies on the road is the hazard')
        for name, deep, shallow in (
                ('snow', "() => { const R = window.__probe.road; R.setWet(0.9); R.setSnow(1); }",
                         "() => { const R = window.__probe.road; R.setWet(0.9); R.setSnow(0.02); }"),
                ('rain', "() => { const R = window.__probe.road;"
                         " R.setSnow(0); R.setWet(0.9); R.setPool(1); }",
                         "() => { const R = window.__probe.road;"
                         " R.setSnow(0); R.setWet(0.9); R.setPool(0); }")):
            page.evaluate(shallow); page.wait_for_timeout(120)
            thin = grip()
            page.evaluate(deep); page.wait_for_timeout(120)
            thick = grip()
            res.check(thick < thin - 0.03,
                      '%s: a covered road is slipperier than the same weather falling' % name,
                      'falling only %.3f, lying %.3f' % (thin, thick))
            res.check(thick >= 0.34,
                      '%s: and it never takes the car away entirely' % name, '%.3f' % thick)

        print()
        print('  THUNDER - loud enough to be thunder')
        # WHAT THE SOUND ASKS FOR, not what the graph reports. RLG-065 cost three
        # attempts on exactly this distinction: a GainNode on a closed context
        # reports a healthy value quite happily, and counting rebuilds read zero on
        # a build that was working. `AR.sfx.noise` is wrapped here and the gains it
        # is handed are recorded, which is the number the mix is actually made of.
        overhead = page.evaluate(THUNDER_BEDS, [1.0, 0.0])
        r_near, c_near = split(overhead)
        res.check(len(r_near) >= 2 and len(c_near) == 1,
                  'a strike overhead is a rumble and a crack',
                  '%d rumble bed(s), %d crack' % (len(r_near), len(c_near)))
        if r_near and c_near:
            loudest = max(b['gain'] for b in r_near)
            # the committed values before the level was raised were 0.26 and 0.20
            res.check(loudest >= 0.40, 'the rumble is well above the 0.26 it used to be',
                      '%.3f' % loudest)
            res.check(c_near[0]['gain'] >= 0.25, 'and the crack is above its old 0.20',
                      '%.3f' % c_near[0]['gain'])
            total = sum(b['gain'] for b in overhead)
            res.check(total * 0.85 < 0.98,
                      'and the beds together stay under the master bus, so it cannot clip',
                      'sum %.3f, %.3f through a master of 0.85' % (total, total*0.85))

        print('    the roll-off, near to far')
        rows = []
        for far in (0.0, 0.25, 0.5, 0.75, 1.0):
            r, c = split(page.evaluate(THUNDER_BEDS, [1 - far*0.62, far]))
            rows.append((far,
                         max([b['gain'] for b in r] or [0]),
                         max([b['gain'] for b in c] or [0]),
                         max([b['dur'] for b in r] or [0])))
            print('      far %.2f   rumble %.3f   crack %.3f   rumble runs %.2fs'
                  % rows[-1])
        rumbles = [r for _, r, _, _ in rows]
        cracks = [c for _, _, c, _ in rows]
        durs = [d for _, _, _, d in rows]
        res.check(all(a > b for a, b in zip(rumbles, rumbles[1:])),
                  'distance lowers the rumble at every step',
                  ' '.join('%.3f' % v for v in rumbles))
        res.check(all(a >= b for a, b in zip(cracks, cracks[1:])),
                  'and it lowers the crack at every step too',
                  ' '.join('%.3f' % v for v in cracks))
        # the whole of what was asked for: BOTH fall, the crack much harder
        res.check(cracks[0] > 0 and rumbles[0] > 0
                  and (cracks[2] / cracks[0]) < (rumbles[2] / rumbles[0]) * 0.5,
                  'the crack is rolled off far harder than the rumble - the air eats the top end',
                  'at half distance the crack keeps %.0f%% and the rumble %.0f%%'
                  % (100*cracks[2]/cracks[0], 100*rumbles[2]/rumbles[0]))
        res.check(cracks[-1] == 0, 'and a strike across the valley has no crack left at all',
                  '%.4f' % cracks[-1])
        res.check(rumbles[-1] > 0.15, 'while its rumble is still clearly there',
                  '%.3f' % rumbles[-1])
        res.check(durs[-1] > durs[0],
                  'the far rumble runs LONGER, because it arrives by several paths',
                  '%.2fs overhead, %.2fs across the valley' % (durs[0], durs[-1]))

        print()
        print('  DISTANCE - the gap between the flash and the sound is how far away it is')
        # 400 rolls of the real function the storm uses, rather than four strikes
        # waited out at 5 to 22 seconds apart. The distribution is the claim.
        rolls = page.evaluate('(n) => { const R = window.__probe.road, out = [];'
                              ' for(let i = 0; i < n; i++) out.push(R.rollStrike());'
                              ' return out; }', 400)
        delays = [r['inSec'] for r in rolls]
        mags = [r['mag'] for r in rolls]
        res.check(min(delays) >= 0.25 and max(delays) <= 5.0,
                  'every strike lands between 250ms and 5s of its flash',
                  '%.3f to %.3f' % (min(delays), max(delays)))
        res.check(min(delays) < 0.6 and max(delays) > 4.5,
                  'and the range is actually used, not clustered in the middle',
                  '%.3f to %.3f over %d rolls' % (min(delays), max(delays), len(rolls)))
        # the correlation is the whole point: a long wait must mean a quiet roll
        pairs = sorted(zip(delays, mags))
        nearest, furthest = pairs[:40], pairs[-40:]
        near_mag = sum(m for _, m in nearest) / len(nearest)
        far_mag = sum(m for _, m in furthest) / len(furthest)
        res.check(near_mag > far_mag + 0.25,
                  'the strikes that arrive soonest are the loudest, so the delay IS the distance',
                  'nearest 40 mean %.3f, furthest 40 mean %.3f' % (near_mag, far_mag))
        res.check(min(mags) >= 0.30,
                  'and the most distant one is still audible - a storm you cannot hear is not one',
                  '%.3f' % min(mags))

        print()
        print('  THE CHECK IS NOT VACUOUS - the old wash goes back and must be caught')
        page.evaluate("""() => {
          const R = window.__probe.road, cfg = window.__probe.cfg;
          window.__probe.priorAfter = cfg.afterDraw || null;
          cfg.afterDraw = function(g){
            /* the rejected build, restored: one screen-wide rectangle from the horizon down,
               painted over the road and over the car exactly as it used to be */
            const c = document.querySelector('canvas'), hz = R.horizon();
            g.fillStyle = 'rgba(228,238,252,0.55)';
            g.fillRect(0, hz, c.width, c.height - hz);
          };
        }""")
        weather(0.9, 1.0)
        washed = page.evaluate(SAMPLE, spots)
        moved = washed['car']['lum'] - dry['car']['lum']
        res.check(abs(moved) >= 6,
                  'with the old wash back the car reading moves, so the check above was real',
                  'car %.1f -> %.1f' % (dry['car']['lum'], washed['car']['lum']))
        page.evaluate("() => { window.__probe.cfg.afterDraw = window.__probe.priorAfter; }")

        # ------------------------------------------------ the glass clears
        print()
        print('  AND THE GLASS CARRIES WHAT IS FALLING, IN THE AMOUNT THAT IS FALLING')
        # Owner, 2026-09-01, from the device: "the snow eventually subsided and the wet drops
        # on the screen kept going." RLG-142.
        #
        # `stepLens` took `Math.max(wet, snowy)` as the amount on the glass, and `snowy` is a
        # KIND - set to 1 or 0 when the weather is rolled and cleared by nothing but the next
        # roll. So it was pinned at 1 from the first flake until the next roll, whatever the
        # sky was doing. This drives both halves of that: it snows, then the snow ends, and
        # the glass has to follow the amount down.
        def lens_after(kind, amount, settle_ms=900):
            page.evaluate("""([k, a]) => { const R = window.__probe.road;
                R.setSnow(k); R.setWet(a); R.setPool(0); R.setSpd(R.MAX_SPD*0.6); }""",
                          [kind, amount])
            page.wait_for_timeout(settle_ms)
            return page.evaluate('() => window.__probe.road.lensDrops()')

        snowing = lens_after(1, 0.9)
        print('      snowing hard:            %d drop(s) on the glass' % snowing)
        res.check(snowing > 0,
                  'weather puts something on the glass in the first place',
                  'nothing arrived in heavy snow')
        stopped = lens_after(1, 0.0, 2400)
        print('      the snow has subsided:   %d drop(s), with snowy still %s'
              % (stopped, page.evaluate('() => window.__probe.road.snowy()')))
        # THE KIND IS DELIBERATELY LEFT SET. That is the state the owner was in - the fall
        # ended and the weather had not been re-rolled - and it is the state the old
        # expression could not tell from heavy snow.
        res.check(stopped == 0,
                  'the glass clears when the fall ends, even though the KIND is still snow',
                  '%d drop(s) survived a fall that had stopped' % stopped)
        # AND IT FOLLOWS THE AMOUNT RATHER THAN JUMPING TO FULL. Without this the check above
        # passes on a build where the glass is simply on or off.
        light = lens_after(0, 0.25)
        heavy = lens_after(0, 1.0)
        print('      light rain %d against heavy rain %d' % (light, heavy))
        res.check(0 < light < heavy,
                  'and it carries more in heavy rain than in light, so it reads the amount',
                  'light %d, heavy %d' % (light, heavy))

        errs = page.evaluate('() => window.__probe.errors')
        res.check(not errs, 'no page errors during the run', '; '.join(errs[:3]))
        browser.close()
    httpd.shutdown()

    print()
    if res.fails:
        print('  %d FAILED: %s' % (len(res.fails), '; '.join(res.fails)))
        return 1
    print('  every check passes - the weather is painted on the geometry')
    return 0


if __name__ == '__main__':
    sys.exit(main())
