#!/usr/bin/env python3
"""AURORA TEST - stars belong to a clear night, and a tundra sometimes has a curtain.

    .venv/Scripts/python tools/aurora-test.py
    .venv/Scripts/python tools/aurora-test.py --shots

Owner, 2026-09-01 (RLG-151): "Can the clear night sky have stars? The tundra should have a
small chance to have an aurora borealis."

THE SKY ALREADY HAD STARS, so the first half was never "add stars" - it was that the owner
had been driving at night and had not been reading them. The ruling named three candidates
and told this session to MEASURE before changing any of them. It found the first: a clear sky
and a nine-tenths overcast one put out 2,499 and 2,580 bright points, the same sky twice,
because the star alpha never mentioned the cover at all.

WHAT THIS HARNESS ASSERTS IS THE AURORA, NOT THE STARS, and the star lines are printed with
the reason. Run against a build with the star gate taken back out, the point ordering still
held - cloud is drawn OVER a star as well as dimming it, so a count cannot tell the two
apart. An assertion that cannot fail on a broken engine is worse than no assertion.

BOTH HALVES ARE THE SAME MECHANISM SEEN TWICE - something in the sky that a clear night shows
and cloud takes away - which is why they are one unit and one harness.

THE AURORA IS FORCED RATHER THAN WAITED FOR. One tundra in four, and a tundra is one place in
eleven, so a harness that waited for one would be measuring the random number generator for
an afternoon. The odds are counted separately, through the engine's own roll.
"""
import sys, threading, http.server, socketserver, functools
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from harness import launch_chromium, console_utf8
from playwright.sync_api import sync_playwright

SHOTS = '--shots' in sys.argv

console_utf8()
handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
srv = socketserver.TCPServer(('127.0.0.1', 0), handler)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = 'http://127.0.0.1:%d' % PORT

# THE UPPER SKY ONLY. Below the halfway line there is a skyline, a treeline and a horizon
# glow in most places, and none of them is a star. A star is a POINT: brighter than its own
# row by a clear margin and one or two pixels wide, which finds points and not gradients.
COUNT = """() => {
  const R = window.__road;
  const cv = document.getElementById('cv');
  const g = cv.getContext('2d');
  /* BELOW THE MIRROR AND ABOVE THE HORIZON. The rear-view glass sits across the top
     of the screen and is a bright rectangle full of road - it put thousands of
     "points" into every reading and swamped the forty this is counting. The band that
     is actually sky starts under it. */
  /* A FIXED BAND, NOT ONE MEASURED FROM THE HORIZON. The horizon moves with the
     road's relief, which is generated fresh per run, so a band defined against it
     included a different amount of treeline and ground every time - the same
     nominal sky counted 187 points on one run and 484 on the next. This slice is
     sky in every place at every relief: under the mirror, well above anything on
     the ground. */
  const y0 = Math.round(cv.height * 0.17), y1 = Math.round(cv.height * 0.30);
  const d = g.getImageData(0, y0, cv.width, y1 - y0).data;
  const w = cv.width, rows = y1 - y0;
  let pts = 0, sum = 0, green = 0, n = 0;
  for(let y = 0; y < rows; y++){
    let rs = 0;
    for(let x = 0; x < w; x++){
      const i = (y * w + x) * 4;
      rs += 0.299*d[i] + 0.587*d[i+1] + 0.114*d[i+2];
    }
    const rm = rs / w;
    sum += rm;
    const lum = (x) => { const i = (y * w + x) * 4;
                         return 0.299*d[i] + 0.587*d[i+1] + 0.114*d[i+2]; };
    for(let x = 0; x < w; x++){
      const i = (y * w + x) * 4;
      const L = lum(x);
      /* ---- A STAR IS ISOLATED AND A CLOUD IS NOT ------------------------
         Counting every pixel brighter than its row found MORE of them under
         half a cover than on a clear night - 7,773 against 2,079 - because a
         cloud is a large bright shape and its edges are bright pixels too. A
         star is one or two pixels with dark sky either side of it, so the
         neighbours a few pixels out have to be dark for it to count. That is
         the difference between a point of light and a lit shape.
         --------------------------------------------------------------- */
      if(L > rm + 22 && x > 3 && x < w - 4
         && lum(x - 4) < rm + 10 && lum(x + 4) < rm + 10) pts++;
      // HOW GREEN THE SKY IS, which is the aurora's own signature - a night sky is
      // blue, and blue is what a curtain of green has to be told apart from. Only
      // pixels where green genuinely leads are counted, not merely bright ones.
      if(d[i+1] > d[i+2] + 6 && d[i+1] > d[i] + 10) green++;
      n++;
    }
  }
  return { points: pts, mean: +(sum/rows).toFixed(2),
           green: +(green / Math.max(1, n)).toFixed(4) };
}"""


def main():
    bad = 0

    def ok(cond, label, detail=''):
        nonlocal bad
        if not cond:
            bad += 1
        print('  %s  %s%s' % ('ok  ' if cond else 'FAIL', label,
                              ('   ' + detail) if detail else ''))

    print('aurora-test  .  a clear night shows things a cloudy one does not')
    with sync_playwright() as p:
        b = launch_chromium(p, headless=True,
                            args=['--mute-audio', '--autoplay-policy=no-user-gesture-required'])
        ctx = b.new_context(viewport={'width': 480, 'height': 900})
        page = ctx.new_page()
        errs = []
        page.on('pageerror', lambda e: errs.append(str(e)))
        page.goto(BASE + '/games/sw/interstate.html', wait_until='load')
        page.wait_for_timeout(1200)
        page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
        page.click('[data-act="play"]')
        page.wait_for_timeout(400)
        page.click('[data-act="chase"]')
        page.wait_for_timeout(200)
        page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
        page.click('[data-act="drive"]')
        page.wait_for_timeout(1200)
        page.evaluate('() => window.__road.setTimed(false)')
        # MIDNIGHT IS PHASE 0.25, not 0. `nightFall` ramps from dusk at 0 to full dark at
        # a quarter and back to dawn at a half - a first attempt read the sky at 0 and
        # measured a lit afternoon, with a mean of 100 and a count full of city windows.
        # The sky is pinned every tick, because the engine re-rolls the cover on its own
        # clock and a set of captures taken over a minute would drift underneath itself.
        # AND THE PLACE IS PINNED TO A TUNDRA. The counts swung from 1,233 to 122 on the
        # same nominal sky between two runs, because the biome is rolled per run and a
        # city puts a lit skyline in the frame while a tundra does not - and the horizon
        # itself moves with the road's relief, which moves the band being sampled. A
        # tundra is also where the aurora belongs, so it is the honest place to ask.
        page.evaluate("() => window.__road.setBiomePair('TUNDRA', 'TUNDRA')")
        page.wait_for_timeout(400)
        page.evaluate("() => { const R = window.__road;"
                      " window.__sky = [0.03, 0, 0]; window.__au = 0;"
                      " window.__hold = setInterval(() => { R.setSpd(0); R.setPhase(0.25);"
                      " R.setSky(window.__sky[0], window.__sky[1]);"
                      " R.setSnowy(window.__sky[2]); R.aurora(window.__au);"
                      " R.setBiomePair('TUNDRA', 'TUNDRA'); }, 16); }")
        page.wait_for_timeout(800)

        def look(cover, aurora, name=None):
            page.evaluate("([c, a]) => { window.__sky = [c, 0, 0]; window.__au = a; }",
                          [cover, 1 if aurora else 0])
            page.wait_for_timeout(600)
            d = page.evaluate(COUNT)
            if SHOTS and name:
                page.screenshot(path=str(Path(ROOT, '_aurora-%s.png' % name)))
            return d

        clear = look(0.03, False, 'stars-clear')
        half = look(0.45, False)
        shut = look(0.92, False, 'stars-overcast')
        au = look(0.03, True, 'aurora')
        au_shut = look(0.92, True)

        print('  ..    clear night     %4d points, sky mean %5.2f, green %.4f'
              % (clear['points'], clear['mean'], clear['green']))
        print('  ..    half cover      %4d points' % half['points'])
        print('  ..    overcast        %4d points' % shut['points'])
        print('  ..    aurora, clear   %4d points, green %.4f' % (au['points'], au['green']))
        print('  ..    aurora, closed  green %.4f' % au_shut['green'])

        # ---- STARS ARE A PROPERTY OF THERE BEING NOTHING IN THE WAY -------------
        # THE MEASUREMENT THE RULING ASKED FOR, kept as the assertion. Before this, a
        # clear sky and a nine-tenths overcast one put out 2,499 and 2,580 points - the
        # same sky twice - because the star alpha never mentioned the cover at all.
        # ---- PRINTED, NOT ASSERTED, AND THE REASON IS THE POINT ----------------
        # The stars now gate on the cover, which is the fix the measurement called for.
        # THIS HARNESS CANNOT PROVE IT. Run against a build with the gate taken back
        # out, the ordering still held - 65 points clear against 48 at half cover -
        # because cloud is drawn OVER the stars and hides them whatever their alpha
        # says. So the number is true and it is not evidence: it cannot tell a star
        # that was dimmed from one that was covered up. Separating them would need the
        # star layer captured on its own, which the engine has no way to do.
        print('  ..    (printed, not asserted: %d points clear against %d at half cover.'
              ' An ungated build orders the same way, because cloud covers a star as'
              ' well as dimming it - see the note in the source)'
              % (clear['points'], half['points']))
        # THE OVERCAST FIGURE IS PRINTED, NOT ASSERTED, and the reason matters. At nine
        # tenths cover the stars are fully off, so whatever is counted there is the
        # cloud's own speckle - the anti-aliased edge of a lobe is a narrow bright line
        # and passes an isolation test written for a star. A cleaner separation would
        # need the star layer captured on its own, which the engine has no way to do.
        print('  ..    (diagnostic, not an assertion: %d at nine tenths cover, where the'
              ' stars are off entirely - that count is cloud speckle)' % shut['points'])

        # ---- AND THE AURORA IS GREEN, WHICH NOTHING ELSE IN THE NIGHT SKY IS ----
        ok(au['green'] > clear['green'] * 3 and au['green'] > 0.03,
           'an aurora puts green in a sky that is otherwise blue',
           '%.4f against %.4f' % (au['green'], clear['green']))
        # IT WANTS A CLEAR SKY TOO, which is what makes the two halves one mechanism.
        ok(au_shut['green'] < au['green'] * 0.5,
           'and an overcast sky puts it out the same way it puts out the stars',
           '%.4f against %.4f' % (au_shut['green'], au['green']))

        # ---- AND IT IS A TUNDRA THING, ROLLED ONCE ------------------------------
        odds = page.evaluate("""() => {
            const R = window.__road;
            const out = {};
            for(const k of ['TUNDRA', 'DESERT', 'FOREST']){
              let n = 0;
              for(let i = 0; i < 400; i++) if(R.auroraRoll(k)) n++;
              out[k] = n / 400;
            }
            return out; }""")
        print('  ..    rolled in %.1f%% of tundras, %.1f%% of deserts, %.1f%% of forests'
              % (odds['TUNDRA'] * 100, odds['DESERT'] * 100, odds['FOREST'] * 100))
        ok(odds['DESERT'] == 0 and odds['FOREST'] == 0,
           'nowhere but a tundra ever rolls one', str(odds))
        want = page.evaluate('() => window.__road.auroraOdds()')
        ok(abs(odds['TUNDRA'] - want) < 0.06,
           'and a tundra rolls one about one time in four',
           '%.3f over 400 openings against a stated %.2f' % (odds['TUNDRA'], want))

        page.evaluate('() => clearInterval(window.__hold)')
        ok(errs == [], 'no page errors', errs[0][:120] if errs else '')
        ctx.close()
        b.close()
    srv.shutdown()
    print()
    print('  ' + ('the clear night sky has things in it' if not bad
                  else str(bad) + ' FAILURES'))
    return 1 if bad else 0


sys.exit(main())
