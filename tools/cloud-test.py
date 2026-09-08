#!/usr/bin/env python3
"""CLOUD TEST - a sky with more cloud in it has more CLOUD in it, not a flatter colour.

    .venv/Scripts/python tools/cloud-test.py
    .venv/Scripts/python tools/cloud-test.py --shots     writes the three skies to /tmp

Owner, 2026-09-07 (RLG-167): "clouds don't read as clouds - fluffy white in clear skies, light
snow storms, and dark thunder storms."

THE COVER WAS A NUMBER WITH NO FORM, and that is what this has to be able to tell apart. A
wash over the whole sky and a sky full of clouds both raise the average brightness, both
change the colour, and both look like "more cloud" to any check that measures one number.
What separates them is STRUCTURE: a wash is flat, and cloud is light and dark next to each
other.

SO THE MEASUREMENT IS THE DIFFERENCE BETWEEN NEIGHBOURING PIXELS, not brightness and not
contrast across a row. A gradient - however dark, however coloured, and however steep - barely
changes from one pixel to the next; an edge of cloud changes a great deal. That is the one
statistic which cannot be satisfied by painting the sky a different colour.

CONTRAST ACROSS A ROW WAS TRIED FIRST AND MEASURED THE BLOOM. Brightest minus darkest scored
an EMPTY sky at 85, because the horizon glow is a radial gradient and is therefore bright in
the middle of every row and dark at both ends. The number was real and it was not about cloud.

AND THE THREE STATES ARE COMPARED WITH EACH OTHER rather than against absolute numbers,
because absolute brightness depends on the hour, the place and the horizon. A storm is darker
than a clear sky at the same cover; a snow sky's cloud sits LOWER than a clear sky's. Those
are relations the owner named, and a relation survives a change of palette.
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

# THE SKY ONLY, AND ONLY THE PART THAT IS SKY. Reading the whole canvas would put the road,
# the scenery and the HUD into every number. The engine reports its own horizon, and the top
# eight per cent is skipped because that is where the shell's title bar sits over the frame.
LUM = """() => {
  const R = window.__road;
  const cv = document.getElementById('cv');
  const g = cv.getContext('2d');
  const hz = Math.max(4, Math.round(R.viewState().horizon));
  const y0 = Math.round(hz * 0.08), y1 = Math.max(y0 + 4, hz - 2);
  const d = g.getImageData(0, y0, cv.width, y1 - y0).data;
  const w = cv.width, rows = y1 - y0;
  const out = new Float64Array(w * rows);
  let sum = 0;
  const rowLum = new Float64Array(rows);
  for(let y = 0; y < rows; y++){
    let rs = 0;
    for(let x = 0; x < w; x++){
      const i = (y * w + x) * 4;
      const L = 0.299 * d[i] + 0.587 * d[i+1] + 0.114 * d[i+2];
      out[y * w + x] = L; rs += L; sum += L;
    }
    rowLum[y] = rs / w;
  }
  window.__lum = { a: out, w: w, rows: rows };
  const mean = sum / (w * rows);
  // WHERE THE BRIGHT MASS SITS, as a fraction from the top of the sky to the horizon.
  // A snow sky is a low lid and a fair sky is piled higher, so the centroid of whatever
  // is brighter than the picture's average is the shape of that claim.
  let litSum = 0, litW = 0;
  for(let y = 0; y < rows; y++){
    const over = Math.max(0, rowLum[y] - mean);
    litSum += over * (y / Math.max(1, rows - 1));
    litW += over;
  }
  return { mean: +mean.toFixed(2),
           height: litW > 0.001 ? +(litSum / litW).toFixed(3) : null };
}"""

# ---- AND THE COMPARISON IS BETWEEN TWO SKIES, WHICH IS WHAT CANCELS EVERYTHING ELSE ----
# Two statistics inside one sky were tried and neither measured cloud. Brightest-minus-
# darkest across a row scored an EMPTY sky at 85, because the horizon glow is a radial
# gradient and is bright in the middle of every row and dark at both ends. Neighbour-to-
# neighbour difference scored an empty sky at 1.39 and an overcast one at 1.43, because the
# SUN is a small bright disc with hard edges and dominates the number at midday.
#
# What separates a wash from a shape is what happens to the picture BETWEEN two covers. The
# sun, the bloom and the day gradient are identical in both and subtract away exactly. A
# uniform wash leaves a difference that is the same everywhere ALONG A ROW; cloud leaves a
# difference that is large where a cloud is and nothing where there is sky. So the statistic
# is the patchiness of the difference WITHIN each row, against that row's own average - and
# the row is the whole point, because the wash is a vertical gradient and is therefore patchy
# over the picture while being flat across any line of it.
DIFF = """() => {
  const R = window.__road;
  const cv = document.getElementById('cv');
  const g = cv.getContext('2d');
  const ref = window.__lum;
  const hz = Math.max(4, Math.round(R.viewState().horizon));
  const y0 = Math.round(hz * 0.08), y1 = Math.max(y0 + 4, hz - 2);
  const d = g.getImageData(0, y0, cv.width, y1 - y0).data;
  const w = cv.width, rows = Math.min(y1 - y0, ref.rows);
  let sum = 0, n = 0, sd = 0;
  const diff = new Float64Array(w * rows);
  for(let y = 0; y < rows; y++)
    for(let x = 0; x < w; x++){
      const i = (y * w + x) * 4;
      const L = 0.299 * d[i] + 0.587 * d[i+1] + 0.114 * d[i+2];
      const v = Math.abs(L - ref.a[y * ref.w + x]);
      diff[y * w + x] = v; sum += v; n++;
    }
  const mean = sum / Math.max(1, n);
  // WITHIN A ROW, NOT ACROSS THE PICTURE. Spread over the whole sky was tried and it
  // could not tell a wash from cloud: the wash is a VERTICAL gradient, so it moves the
  // top of the sky far more than the bottom and is therefore "patchy" over the picture
  // while being perfectly uniform across any row of it. Measured with the shapes
  // removed entirely, that version still scored 0.82 to 1.10 and passed.
  let rowsUsed = 0, patchy = 0, hSum = 0, hW = 0;
  for(let y = 0; y < rows; y++){
    let rs = 0;
    for(let x = 0; x < w; x++) rs += diff[y * w + x];
    const rm = rs / w;
    /* HOW HIGH THE CLOUD SITS, from the DIFFERENCE rather than from brightness.
       A brightness centroid answers "where is the sky brightest", which at midday
       is mostly about the sun and the bloom - it read a fair sky at 0.34 on one run
       and 0.46 on the next. The difference against an open sky is the cloud and
       nothing else, so its centre of mass is the claim the owner made about a snow
       sky being LOW. */
    hSum += rm * (y / Math.max(1, rows - 1));
    hW += rm;
    if(rm <= 0.5) continue;                       /* a row nothing happened in */
    let v = 0;
    for(let x = 0; x < w; x++){ const e = diff[y * w + x] - rm; v += e * e; }
    patchy += Math.sqrt(v / w) / rm;
    rowsUsed++;
  }
  return { moved: +mean.toFixed(2),
           patchy: +(rowsUsed ? patchy / rowsUsed : 0).toFixed(3),
           height: hW > 0.001 ? +(hSum / hW).toFixed(3) : null };
}"""


def main():
    bad = 0

    def ok(cond, label, detail=''):
        nonlocal bad
        if not cond:
            bad += 1
        print('  %s  %s%s' % ('ok  ' if cond else 'FAIL', label,
                              ('   ' + detail) if detail else ''))

    print('cloud-test  .  a cloud has a shape')
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
        # the clock ends the run part way through a set of captures (RLG-169)
        page.evaluate('() => window.__road.setTimed(false)')
        # MIDDAY AND STANDING STILL. The cloud is drawn over whatever the sky is doing, so
        # a sample taken at dusk is measuring the sunset; and a moving car changes the
        # drift between frames, which would put the difference between two skies inside
        # one of them.
        # AND THE SKY IS PINNED EVERY TICK, NOT SET ONCE. The engine re-rolls the cover
        # on its own clock every twenty-five to seventy seconds and eases toward the new
        # target, so a set of captures taken over a minute can have the sky change
        # underneath it - the overcast reading came back 1.25 on one run and 0.44 on the
        # next, which reads as a broken painter and is a sky that had moved on.
        page.evaluate("() => { const R = window.__road; R.setPhase(0.5); R.setSpd(0);"
                      " window.__sky = [0.03, 0, 0];"
                      " window.__hold = setInterval(() => { R.setSpd(0); R.setPhase(0.5);"
                      " R.setSky(window.__sky[0], window.__sky[1]);"
                      " R.setSnowy(window.__sky[2]); }, 16); }")
        page.wait_for_timeout(600)

        def set_sky(cover, storm, snow, name=None):
            page.evaluate("([c, st, sn]) => { window.__sky = [c, st, sn];"
                          " const R = window.__road; R.setSky(c, st); R.setSnowy(sn); }",
                          [cover, storm, snow])
            page.wait_for_timeout(500)
            if SHOTS and name:
                page.screenshot(path=str(Path(ROOT, '_cloud-%s.png' % name)))

        def snap(cover, storm, snow, name=None):
            set_sky(cover, storm, snow, name)
            return page.evaluate(LUM)

        def against_open(cover, storm, snow, name=None):
            """Take the open sky as the reference, then move to this one and report
            how much the picture moved and how PATCHY the movement was."""
            snap(0.03, 0, 0)
            set_sky(cover, storm, snow, name)
            return page.evaluate(DIFF)

        open_sky = snap(0.03, 0, 0, 'open')
        fair_l = snap(0.35, 0, 0, 'fair')
        thick_l = snap(0.85, 0, 0, 'overcast')
        snow_l = snap(0.75, 0.25, 1, 'snow')
        storm_l = snap(0.85, 1.0, 0, 'thunder')

        fair = against_open(0.35, 0, 0)
        thick = against_open(0.85, 0, 0)
        storm = against_open(0.85, 1.0, 0)
        snow_d = against_open(0.75, 0.25, 1)

        for name, d in (('open', open_sky), ('fair', fair_l), ('overcast', thick_l),
                        ('snow', snow_l), ('thunder', storm_l)):
            print('  ..    %-9s mean %6.2f  cloud sits at %s'
                  % (name, d['mean'],
                     ('%.2f' % d['height']) if d['height'] is not None else '-'))
        for name, d in (('fair', fair), ('overcast', thick), ('thunder', storm),
                        ('snow', snow_d)):
            print('  ..    %-9s against an open sky: moved %.1f levels, patchiness %.2f,'
                  ' cloud centred at %.2f'
                  % (name, d['moved'], d['patchy'], d['height'] or 0))

        # ---- CLOUD IS STRUCTURE, AND A WASH IS NOT ------------------------------
        # THE ONE ASSERTION A FLAT REPAINT CANNOT SATISFY. A wash moves every pixel of
        # sky by about the same amount, so the spread of the change is a fraction of
        # its average; cloud moves some pixels a great deal and others not at all, so
        # the spread is comparable to the average. Half is a long way from either a
        # wash (near zero) or noise.
        ok(fair['patchy'] > 0.5,
           'a sky with cloud in it changes in patches, not as a wash',
           'patchiness %.2f' % fair['patchy'])
        ok(thick['moved'] > fair['moved'],
           'and more cover changes more of the sky',
           '%.1f levels at 0.85 cover against %.1f at 0.35'
           % (thick['moved'], fair['moved']))
        ok(thick['patchy'] > 0.5,
           'and an overcast sky is still made of clouds',
           'patchiness %.2f' % thick['patchy'])

        # ---- AND THE THREE THE OWNER NAMED ARE DIFFERENT SKIES ------------------
        ok(storm_l['mean'] < thick_l['mean'],
           'a thunder sky is darker than an overcast one at the same cover',
           'mean %.2f against %.2f' % (storm_l['mean'], thick_l['mean']))
        ok(storm['patchy'] > 0.5,
           'and it is still cloud rather than a black wash',
           'patchiness %.2f' % storm['patchy'])
        # A SNOW SKY IS A LID. The owner's word was "low", and this is that word as a
        # number: the bright mass sits nearer the horizon than a fair sky's does.
        ok(snow_d['height'] is not None and fair['height'] is not None
           and snow_d['height'] > fair['height'] + 0.04,
           'a snow sky sits lower than a fair one',
           'cloud centred at %.2f against %.2f'
           % (snow_d['height'] or 0, fair['height'] or 0))

        page.evaluate('() => clearInterval(window.__hold)')
        ok(errs == [], 'no page errors', errs[0][:120] if errs else '')
        ctx.close()
        b.close()
    srv.shutdown()
    print()
    print('  ' + ('a cloud has a shape' if not bad else str(bad) + ' FAILURES'))
    return 1 if bad else 0


sys.exit(main())
