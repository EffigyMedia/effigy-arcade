#!/usr/bin/env python3
"""TUNNEL TEST - dark by day, through the one lamp clock, and the mouth is a ramp.

    .venv/Scripts/python tools/tunnel-test.py

RLG-105. Owner, 2026-08-31: canyon and tunnel are the two structural places to build.
"NOTHING ON THE BOARD IS DARK BY DAY, AND THAT IS THE WHOLE POINT."

THREE CLAIMS, AND THE SECOND IS THE ONE WITH A RULING BEHIND IT.

    IT IS DARK AT MIDDAY. Every other place in the game is lit by the hour and the weather
    alone, so a tunnel at noon would have been a bright corridor.

    AND THE DARKNESS COMES THROUGH `lampsOn`, WHICH MUST STAY ONE FUNCTION. Every lamp in
    the game asks it - the headlight beams, the street lighting, and all 178 declared lamps
    across 59 vehicles. A tunnel that lit its cars by a second route would be two answers to
    one question, and the fragment says so explicitly because the jungle's canopy is going
    to ask the same question next. So the check does not merely ask "is it dark": it asks
    whether the darkness arrives through the shared clock.

    AND THE MOUTH IS A RAMP RATHER THAN A CUT. Coming out is a large sudden brightening at
    speed, repeated every time the place ends - the same photosensitivity hazard RLG-060
    gave the lightning a comfort option for. The darkness rides the biome crossing, so this
    checks that it passes through intermediate values instead of stepping.

WHAT IT CANNOT DO. It cannot say whether the bore LOOKS like a tunnel, whether the ceiling
lamps read at speed, or whether the exit is comfortable on a real screen. `tools/biome-shot.py`
takes the picture; the owner judges it.

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

/* ---- THE CANVAS AFTER A FRAME, AND ONLY THE CEILING BAND ----------------
   Read after a finished paint, or the answer is half a picture. The band is
   from a fifth of the way down - below the rear-view mirror, which shows the
   road BEHIND and moves whatever the bore does - to just above the horizon,
   where the road itself starts. Inside a tunnel that band holds the vault, the
   tops of the walls and the lamps, and nothing else. */
window.__ceil = function(){
  return new Promise(function(res){
    requestAnimationFrame(function(){
      requestAnimationFrame(function(){
        var c = document.getElementById('cv'), g = c.getContext('2d');
        var dpr = c.width / c.getBoundingClientRect().width;
        var hz = window.__probe.road.horizon();
        var y0 = Math.round(c.height * 0.20);
        var y1 = Math.round((hz - 12) * dpr);
        window.__band = { y0: y0, y1: y1,
          d: g.getImageData(0, y0, c.width, Math.max(1, y1 - y0)).data };
        res({ y0: y0, y1: y1, w: c.width });
      });
    });
  });
};
window.__hold = function(){ window.__heldBand = window.__band; return true; };
window.__moved = function(tol){
  var a = window.__heldBand, b = window.__band;
  if(!a || !b || a.d.length !== b.d.length) return null;
  var n = 0, lit = 0;
  for(var i = 0; i < a.d.length; i += 4){
    if(a.d[i+3] > 8 && (a.d[i] > 8 || a.d[i+1] > 8 || a.d[i+2] > 8)) lit++;
    if(Math.abs(a.d[i]-b.d[i]) > tol || Math.abs(a.d[i+1]-b.d[i+1]) > tol ||
       Math.abs(a.d[i+2]-b.d[i+2]) > tol) n++;
  }
  return { moved: n, lit: lit, total: a.d.length/4 };
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--headed', action='store_true')
    args = ap.parse_args()
    console_utf8()
    res = Results()
    httpd, port = serve(ROOT)
    print('tunnel-test  .  dark by day, through the one lamp clock')
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
        until(page, '!!window.__probe.road', timeout=10000)
        page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
        page.click('[data-act="play"]')
        page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
        page.click('[data-act="drive"]')
        page.wait_for_timeout(1600)

        def light(biome, hour, wet=0.0):
            page.evaluate("""([k, h, w]) => {
              const R = window.__probe.road;
              R.setBiomePair(k, k); R.setPhase(h);
              R.setWet(w); R.setSnow(0); R.setPool(0);
            }""", [biome, hour, wet])
            page.wait_for_timeout(220)
            return page.evaluate("() => window.__probe.road.lightLevels()")

        # --------------------------------------------- dark by day
        print()
        print('  DARK BY DAY, WHICH NOTHING ELSE ON THE BOARD IS')
        noon_tun = light('TUNNEL', 0.75)
        noon_farm = light('FARMLAND', 0.75)
        night_farm = light('FARMLAND', 0.25)
        print('      midday in a TUNNEL:   lamps %.2f   (the day clock alone says %.2f)'
              % (noon_tun['lamps'], noon_tun['clock']))
        print('      midday in FARMLAND:   lamps %.2f' % noon_farm['lamps'])
        print('      midnight in FARMLAND: lamps %.2f' % night_farm['lamps'])
        res.check(noon_tun['lamps'] > 0.95,
                  'the lamps are FULL ON at midday in a tunnel',
                  'lamps %.2f' % noon_tun['lamps'])
        res.check(noon_farm['lamps'] < 0.05,
                  'and off at the same hour anywhere with a sky, so it is the PLACE',
                  'farmland at the same hour reads %.2f' % noon_farm['lamps'])
        # THE DAY CLOCK ITSELF MUST STILL SAY MIDDAY. If the tunnel worked by moving the
        # hour, every other thing that reads the clock - the sky, the sun, the golden hour -
        # would move with it, and this would be a very different change.
        res.check(noon_tun['clock'] < 0.05,
                  'and the clock still says midday, so the place did not move the sun',
                  'the day clock reads %.2f inside the tunnel' % noon_tun['clock'])

        # --------------------------------------------- one function, not two
        print()
        print('  AND IT ARRIVES THROUGH THE ONE LAMP CLOCK, NOT A SECOND ROUTE')
        # `lightLevels` reports what `lampsOn()` returns. If a tunnel lit its cars by any
        # other path, `lamps` here would stay at the clock value and the cars would light
        # anyway - so this is the check that the seam was respected. The jungle's canopy is
        # about to ask the same question, and that is why it matters now.
        res.check(abs(noon_tun['lamps'] - 1.0) < 0.05 and noon_tun['clock'] < 0.05,
                  'the shared clock returns full lamps while its own day term is zero',
                  'lamps %.2f against a day term of %.2f'
                  % (noon_tun['lamps'], noon_tun['clock']))
        # AND WEATHER STILL WORKS THROUGH THE SAME EXPRESSION, which is what says the place
        # was added as one more term rather than as an override.
        wet_farm = light('FARMLAND', 0.75, 1.0)
        print('      midday in FARMLAND, heavy rain: lamps %.2f' % wet_farm['lamps'])
        res.check(wet_farm['lamps'] > 0.95,
                  'and weather still lights them too, so the place is a term and not an override',
                  'rain at midday reads %.2f' % wet_farm['lamps'])

        # --------------------------------------------- no weather under a roof
        print()
        print('  AND A ROOF MEANS NO WEATHER, WHICH FALLS OUT RATHER THAN BEING A RULE')
        odds = page.evaluate("() => window.__probe.road.climateFor('TUNNEL')")
        print('      precip %.2f, canRain %s, canSnow %s'
              % (odds['precip'], odds['canRain'], odds['canSnow']))
        res.check(odds['precip'] == 0,
                  'a tunnel precipitates on none of its rolls', 'precip %.3f' % odds['precip'])
        res.check(not odds['canRain'] and not odds['canSnow'],
                  'and it can do neither, which comes from a precipitation of zero rather than a branch',
                  'canRain %s, canSnow %s' % (odds['canRain'], odds['canSnow']))
        page.evaluate("() => window.__probe.road.setBiomePair('TUNNEL','TUNNEL')")
        page.wait_for_timeout(200)
        rolls = page.evaluate("(n) => window.__probe.road.sampleWeatherRolls(n)", 600)
        res.check(rolls['dry'] == 1.0,
                  'and 600 rolls of the engine own weather produce nothing at all',
                  'it produced weather on %.3f of rolls' % (1 - rolls['dry']))

        # --------------------------------------------- the mouth is a ramp
        print()
        print('  AND THE MOUTH IS A RAMP RATHER THAN A CUT, which is the comfort answer')
        # The darkness rides the biome crossing, so driving at a mouth should pass through
        # intermediate values. A cut would step from 0 to 1 between two samples - and it is
        # the EXIT that matters for comfort, because that is the brightening.
        page.evaluate("() => { const R = window.__probe.road;"
                      " R.setBiomePair('TUNNEL','TUNNEL'); R.setPhase(0.75); }")
        page.wait_for_timeout(300)
        page.evaluate("() => window.__probe.road.startBiomeChange('FARMLAND')")
        # THE CAR HAS TO ACTUALLY REACH THE MOUTH. The boundary is placed DRAW segments
        # ahead and the weather band straddles it, so the crossing does not begin until the
        # car has covered about 186 segments - 37,000 units. The first version of this drove
        # for 3.6 seconds in 120ms steps and never left the tunnel: it read 1.00 thirty
        # times and reported a cut, which is the harness measuring its own patience.
        # biome-test learnt exactly this and holds the speed the same way.
        # SAMPLED FINELY, because the ramp is about a second long. The weather band is 72
        # segments - 14,400 units - and at nine tenths of top speed the car crosses it in
        # roughly a second. A 250ms sample caught ONE intermediate value and reported a cut;
        # the ramp was there the whole time and the harness could not see it. This is the
        # same fault as the bend measurement earlier today, run past the resolution its
        # subject needs.
        ramp, cross = [], []
        for _ in range(110):
            page.evaluate("() => window.__probe.road.setSpd(window.__probe.road.MAX_SPD * 0.90)")
            page.wait_for_timeout(70)
            L = page.evaluate("() => window.__probe.road.lightLevels()")
            ramp.append(L['dark'])
            cross.append(page.evaluate("() => window.__probe.road.biomeSweep()")['atCarWeather'])
        first = next((i for i, v in enumerate(cross) if v > 0), 0)
        show = ramp[max(0, first - 1):first + 13]
        print('      the crossing ran from 0 to %.2f of the weather band' % max(cross))
        print('      driving OUT of a tunnel into daylight: %s'
              % ' '.join('%.2f' % v for v in show))
        mids = [v for v in ramp if 0.06 < v < 0.94]
        res.check(ramp[0] > 0.9 and min(ramp) < 0.1,
                  'the run really did cross from full dark to full daylight',
                  'it went %.2f to %.2f' % (ramp[0], min(ramp)))
        secs = len(mids) * 0.07
        print('      the fade took about %.1f second(s) of driving at nine tenths of top speed'
              % secs)
        res.check(len(mids) >= 3,
                  'and it passes through intermediate values rather than cutting',
                  'only %d sample(s) were part-way' % len(mids))
        biggest = max(abs(b - a) for a, b in zip(ramp, ramp[1:]))
        res.check(biggest < 0.5,
                  'no single step is most of the way, which is what makes it comfortable',
                  'the largest step was %.2f' % biggest)

        # --------------------------------------------- and it has no horizon
        print()
        print('  AND IT HAS NO SKYLINE, BECAUSE THE PLACE HAS NO DISTANCE IN IT')
        forms = page.evaluate("""() => {
          const R = window.__probe.road, out = {};
          for(const k of R.BIOME_KEYS()) out[k] = R.skyForm ? R.skyForm(k) : null;
          return out;
        }""")
        if forms.get('TUNNEL') is not None:
            print('      horizon forms: %s' % forms)
            res.check(forms['TUNNEL'] == 'none',
                      'a tunnel states that it draws no horizon at all',
                      'it states %r' % forms['TUNNEL'])
            res.check(forms.get('FARMLAND') == 'open',
                      'and farmland states the open sky the owner asked for',
                      'it states %r' % forms.get('FARMLAND'))
            # AND NOTHING FALLS THROUGH TO TOWERS BY ACCIDENT, which is the fault that put a
            # city skyline on the first farmland capture: the form was a list of NAMES and
            # anything unrecognised got the default.
            res.check(all(v for v in forms.values()),
                      'and every place states a form, so nothing gets towers by fall-through',
                      str(forms))

        # --------------------------------------------- and a run cannot open in one
        print()
        print('  AND A RUN CANNOT OPEN IN ONE, BUT THE ROAD MUST STILL REACH IT (RLG-140)')
        # Owner, 2026-09-01: "runs can never start in a tunnel or on a bridge." THE WAY
        # THIS FIX GOES WRONG IS BY DELETING THE TUNNEL FROM THE GAME - filter the one
        # list the engine has and the place becomes unreachable, which no check on the
        # opening draw alone would notice. So both lists are read, and the second
        # assertion is the one that matters.
        opens = page.evaluate("() => window.__probe.road.OPEN_KEYS()")
        allk = page.evaluate("() => window.__probe.road.BIOME_KEYS()")
        passages = [k for k in allk if page.evaluate(
            "(k) => window.__probe.road.isPassage(k)", k)]
        print('      passages:      %s' % passages)
        print('      a run may open in %d of the %d places' % (len(opens), len(allk)))
        # THE BRIDGE JOINED THIS LIST BY STATING ONE FIELD (RLG-112). That is the whole
        # claim RLG-140 made when the property was chosen over a name the picker knows -
        # a second event place needed no second edit anywhere - so the check asserts BOTH
        # rather than being loosened to let the new one through.
        res.check(sorted(passages) == ['BRIDGE', 'TUNNEL'],
                  'the tunnel and the bridge are the passages on the board',
                  'passages are %s' % passages)
        res.check('TUNNEL' not in opens and 'BRIDGE' not in opens,
                  'and a run cannot open in either of them',
                  'OPEN_KEYS is %s' % opens)
        res.check(set(allk) - set(opens) == {'TUNNEL', 'BRIDGE'},
                  'and nothing else was excluded with them',
                  'excluded: %s' % sorted(set(allk) - set(opens)))
        res.check('TUNNEL' in allk,
                  'and the tunnel is still a place the road can reach, which is the point',
                  'BIOME_KEYS is %s' % allk)

        # AND THE DRAW ITSELF, not the list it reads. `rollOpening` calls the same
        # function `openBiome` does, so this samples the engine rather than a harness's
        # copy of it. At a tenth of the board, 400 rolls without a tunnel is not luck.
        rolls = page.evaluate("() => window.__probe.road.rollOpening(400)")
        seen = sorted(set(rolls))
        print('      400 opening rolls landed on: %s' % seen)
        res.check('TUNNEL' not in rolls and 'BRIDGE' not in rolls,
                  'and four hundred opening rolls never landed in either',
                  '%d tunnels and %d bridges'
                  % (rolls.count('TUNNEL'), rolls.count('BRIDGE')))
        res.check(len(seen) == len(opens),
                  'and they still reach every place a run may open in',
                  'reached %d of %d' % (len(seen), len(opens)))

        # --------------------------------------------- and the walls are not a fade
        print()
        print('  AND THE BORE IS SOLID, BECAUSE A TUNNEL IS THERE OR IT IS NOT (RLG-144)')
        # Owner, 2026-09-01, on a capture of the mouth: "why is that tunnel transparent?"
        # Its opacity WAS the crossing ramp - the bore was laid over the ordinary world
        # with the place's own darkness as its alpha, so halfway through a transition the
        # whole thing was at half opacity and the farmland behind it showed through.
        #
        # TWO THINGS WERE FUSED. How dark it is inside is a property of the place and
        # should ramp; whether the walls EXIST is not a matter of degree. So the extent is
        # what the crossing decides now - the tube is built from the tunnel's own mouth,
        # which the event record holds to the world unit - and the darkness keeps its real
        # job. Both halves are checked, because fixing one by breaking the other would
        # pass a check that only looked at the walls.
        # THE CAR HAS TO ACTUALLY REACH THE MOUTH, and the first version of this did not
        # get near it: fourteen samples at 140ms read every value as zero and reported that
        # the tube never started ahead of the camera. The boundary is placed DRAW segments
        # away, so the car has about 37,000 units to cover - which is the same trap the
        # ramp measurement above records falling into, and the note there is why this one
        # was recognised rather than chased.
        page.evaluate("() => { const R = window.__probe.road;"
                      " R.setBiomePair('FARMLAND','FARMLAND'); R.setPhase(0.75); }")
        page.wait_for_timeout(300)
        page.evaluate("() => window.__probe.road.startBiomeChange('TUNNEL')")
        seen = []
        for _ in range(110):
            page.evaluate("() => window.__probe.road.setSpd(window.__probe.road.MAX_SPD * 0.90)")
            page.wait_for_timeout(70)
            seen.append(page.evaluate("() => window.__probe.road.boreTrace()"))
        aheads = [t['ahead'] for t in seen]
        darks = [t['dark'] for t in seen]
        print('      the mouth ahead of the camera: %s' % ' '.join(str(a) for a in aheads[::12]))
        print('      and the darkness meanwhile:    %s' % ' '.join('%.2f' % d for d in darks[::12]))
        res.check(all(t['alpha'] == 1 for t in seen),
                  'the walls are drawn solid rather than at the crossing amount',
                  'alphas seen: %s' % sorted({t['alpha'] for t in seen}))
        res.check(max(aheads) > 0,
                  'and the tube starts AHEAD of the camera while the mouth is still ahead',
                  'it never started anywhere but at the camera')
        res.check(min(aheads) == 0,
                  'and at the camera once the mouth is behind, so the extent is the crossing',
                  'it never reached the camera: %s' % aheads)
        # AND THE DARKNESS STILL RAMPS, which is what the alpha used to be doing and is
        # the job it gets back. Losing this would be fixing the walls by breaking the
        # comfort ramp RLG-060 asked for.
        res.check(len(set(darks)) > 2,
                  'while the darkness goes on ramping through the crossing',
                  'it took only these values: %s' % sorted(set(darks)))

        # --------------------------------------------- the inside of it MOVES
        print()
        print('  AND THE INSIDE OF IT GOES PAST YOU, WHICH IS WHAT SAYS SPEED')
        # Owner, 2026-09-01, from the device: "the main offender is that the walls and
        # ceiling of the tunnel are static. They don't move. They should obviously be
        # moving based on your speed."
        #
        # THIS CANNOT BE ASKED OF THE GEOMETRY, ONLY OF THE PIXELS. `borePoints` samples
        # the tube at `z0 + t*t*reach` where `z0` is the camera once you are inside, so
        # every rib, joint and lamp sits at a FIXED offset ahead of you. The shape is
        # right and the picture never changes: a painted backdrop. Reading the sample
        # list would not show that, because the list is correct.
        #
        # THE BAND IS THE CEILING, so the road's own stripes cannot answer for it. It runs
        # from below the mirror to just above the horizon, and inside a bore it holds the
        # vault, the wall tops and the lamps.
        page.evaluate("""() => { const R = window.__probe.road;
            R.setBiomePair('TUNNEL','TUNNEL'); R.setPhase(0.75);
            R.setWet(0); R.setSnow(0); R.setPool(0); R.clearTraffic(); }""")
        for _ in range(40):
            st = page.evaluate("() => window.__probe.road.startLine()")
            if st['left'] <= 0 and st['go'] <= 0:
                break
            page.wait_for_timeout(90)
        for _ in range(12):
            page.evaluate("() => { const R = window.__probe.road;"
                          " R.clearTraffic(); R.setSpd(R.MAX_SPD*0.7); }")
            page.wait_for_timeout(50)

        # THE CONTROL FIRST, AND IT IS PARKED. A difference count means nothing without
        # one: if a parked bore also differs then something is animating on its own and
        # the driving figure below is not motion.
        page.evaluate("() => { const R = window.__probe.road; R.setSpd(0); }")
        page.wait_for_timeout(200)
        page.evaluate("() => window.__ceil()")
        page.evaluate("() => window.__hold()")
        page.wait_for_timeout(200)
        page.evaluate("() => window.__ceil()")
        still = page.evaluate("(t) => window.__moved(t)", 10)
        print('      parked, two frames 200ms apart: %d of %d pixels differ (%d are lit)'
              % (still['moved'], still['total'], still['lit']))
        res.check(still['lit'] > still['total'] * 0.5,
                  'the band really is full of bore rather than of sky',
                  'only %d of %d pixels carry anything' % (still['lit'], still['total']))
        res.check(still['moved'] < still['total'] * 0.02,
                  'and a parked bore holds still, so a difference below means MOTION',
                  '%d pixels moved with the car stopped' % still['moved'])

        # AND NOW DRIVING.
        page.evaluate("() => { const R = window.__probe.road;"
                      " R.clearTraffic(); R.setSpd(R.MAX_SPD*0.7); }")
        page.wait_for_timeout(120)
        page.evaluate("() => window.__ceil()")
        page.evaluate("() => window.__hold()")
        for _ in range(4):
            page.evaluate("() => { const R = window.__probe.road;"
                          " R.clearTraffic(); R.setSpd(R.MAX_SPD*0.7); }")
            page.wait_for_timeout(45)
        page.evaluate("() => window.__ceil()")
        drove = page.evaluate("(t) => window.__moved(t)", 10)
        share = drove['moved'] / max(1, drove['total'])
        print('      driving, two frames ~180ms apart: %d of %d pixels differ (%.1f%%)'
              % (drove['moved'], drove['total'], share * 100))
        # 6 PER CENT IS NOT A TASTE NUMBER. A static bore measures a fraction of one per
        # cent - it is the same picture twice - and ribs and lamps sweeping past at speed
        # move a large part of the band. The threshold sits well above the first and well
        # below what a working tunnel returns.
        res.check(share > 0.06,
                  'the ceiling and the walls go past you when you drive',
                  'only %.2f%% of the band changed over 180ms at seven tenths of top speed'
                  % (share * 100))

        errs = page.evaluate("() => window.__probe.errors")
        res.check(not errs, 'no page errors', '; '.join(errs[:3]))
        browser.close()
    httpd.shutdown()

    print()
    if res.fails:
        print('FAILED: ' + '; '.join(res.fails))
        return 1
    print('all checks passed')
    print('  what the bore LOOKS like is not measured here - see tools/biome-shot.py')
    return 0


sys.exit(main())
