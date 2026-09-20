#!/usr/bin/env python3
"""FAR ROAD TEST - the tarmac reaches the horizon, and there is no step where it joins.

    .venv/Scripts/python tools/farroad-test.py
    .venv/Scripts/python tools/farroad-test.py --shots

Owner, 2026-08-31 (RLG-101): "another thing that would be really cool is if we did the same
thing for the highway, so that the highway is interpreted and drawn to the horizon."

MEASURED THE WAY THE SEA WAS MEASURED, which the ruling asked for by name: not as a picture,
but as the tone step across the join, sampled either side, swept inside single frames -
because this world is generated per load and two runs cannot be compared.

TWO CLAIMS AND THEY ARE DIFFERENT. That the tarmac REACHES the horizon is about whether
anything is drawn up there at all; that the join does not SHOW is about whether what is drawn
is the same colour as what it meets. A band that reached the skyline in the wrong tone would
pass the first and fail the second, and it is the second that the sea's own band got wrong.

AND ONLY THE FIRST IS ASSERTED HERE. The tone step is printed with the reasons: four sampling
schemes were tried and each was dominated by something other than the seam, and the last of
them still swung 34, 84 and 39 across three runs of one unchanged build. The quantity is real
and this instrument cannot hold it still. THE JOIN NEEDS A DEVICE, and that is said plainly
rather than dressed up as a threshold that happened to pass.
"""
import sys, threading, http.server, socketserver, functools
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from harness import launch_chromium, console_utf8, boot, garage_screen
from playwright.sync_api import sync_playwright

SHOTS = '--shots' in sys.argv

console_utf8()
handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
srv = socketserver.TCPServer(('127.0.0.1', 0), handler)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = 'http://127.0.0.1:%d' % PORT

# EVERYTHING IN ONE FRAME. The road is generated per load and the light is always turning, so
# a value read now and compared with one read a second later is comparing two worlds. The
# join, the band above it and the ground beside it are all sampled from the same getImageData.
SAMPLE = """() => {
  const R = window.__road;
  const fr = R.farRoad();
  if(!fr || !fr.drew) return { drew: false, faY: fr && fr.faY, hz: fr && fr.hz };
  const cv = document.getElementById('cv');
  const g = cv.getContext('2d');
  const W = cv.width;
  const hz = fr.horizon, jy = fr.joinY, vx = fr.vx, jw = fr.joinW, joinX = fr.joinX;
  const d = g.getImageData(0, Math.max(0, Math.round(hz) - 2),
                           W, Math.min(cv.height - Math.round(hz) + 2,
                                       Math.round(jy - hz) + 12)).data;
  const top = Math.max(0, Math.round(hz) - 2);
  const at = (x, y) => {
    const i = ((y - top) * W + Math.round(x)) * 4;
    return [d[i], d[i+1], d[i+2]];
  };
  /* ---- THE DARKEST PIXEL, NOT THE AVERAGE ----------------------------------
     A road has lane markings, a centre line and rumble strips on it, and all of
     them are BRIGHTER than the tarmac. An average across the road's width is
     therefore partly a measure of how many stripes happened to fall in the row
     that was sampled - it put the worst tone step at 197 of a possible 441, which
     is a white marking against grey asphalt rather than a seam. The darkest pixel
     in the span is the road surface itself, on both sides of the join. */
  const darkest = (y, x0, x1) => {
    let best = null, bl = 1e9;
    for(let x = Math.max(0, Math.round(x0)); x <= Math.min(W - 1, Math.round(x1)); x++){
      const c = at(x, y);
      const L = 0.299*c[0] + 0.587*c[1] + 0.114*c[2];
      if(L < bl){ bl = L; best = c; }
    }
    return best;
  };
  /* ---- AND THE MEDIAN FOR THE JOIN, WHICH IS A DIFFERENT QUESTION ----------
     The darkest pixel is the right answer to "is there a road here", because it
     finds a narrow dark ribbon among ground. It is the wrong answer to "are these
     two the same colour", because the road below the join carries a rumble strip
     and a shadow line that are darker than the tarmac while the band above it is
     uniform - so the comparison picked the darkest thing on one side against the
     only thing on the other and read a step of 39 where the surfaces agreed. The
     median pixel rejects a bright marking and a dark edge alike. */
  const median = (y, x0, x1) => {
    const row = [];
    for(let x = Math.max(0, Math.round(x0)); x <= Math.min(W - 1, Math.round(x1)); x++){
      const c = at(x, y);
      row.push([0.299*c[0] + 0.587*c[1] + 0.114*c[2], c]);
    }
    if(!row.length) return null;
    row.sort((a, b) => a[0] - b[0]);
    return row[row.length >> 1][1];
  };
  const mean = (y, x0, x1) => {
    let r = 0, g2 = 0, b = 0, n = 0;
    for(let x = Math.max(0, Math.round(x0)); x <= Math.min(W - 1, Math.round(x1)); x++){
      const c = at(x, y); r += c[0]; g2 += c[1]; b += c[2]; n++;
    }
    return n ? [r/n, g2/n, b/n] : null;
  };
  /* JUST INSIDE EACH SIDE OF THE JOIN. Two rows either side rather than one, so a
     single anti-aliased boundary row is not the whole measurement. */
  /* ---- AROUND THE ROAD, NOT AROUND THE VANISHING POINT ---------------------
     The road's centre at the join is `joinX`, and the vanishing point is where it
     ends up - on a bend those are tens of pixels apart. Sampling both sides of the
     join around the vanishing point put both samples on the VERGE, where they
     agreed with each other perfectly and said nothing about the road: the colours
     came back green. The centre is interpolated between the two, and the width
     shrinks with it, so each row is sampled where the tarmac actually is.
     ------------------------------------------------------------------------ */
  const span = Math.max(1, jy - hz);
  const centreAt = (y) => { const f = Math.min(1, Math.max(0, (jy - y) / span));
                            return [joinX + (vx - joinX) * f, jw * (1 - f)]; };
  /* ---- THE JOIN IS WHERE THE ROAD PASS ACTUALLY STOPPED --------------------
     `joinY` is the far slice's own projection; the road pass paints to whichever
     slice is highest AFTER the crest guards drop the ones hidden behind a rise,
     and the engine already records that as `roadTop` for the sea's sake. On a
     rolling road the two are tens of pixels apart, so a sample taken either side
     of `joinY` was inside the BAND on both sides - where it agreed with itself
     perfectly and said nothing. The readings swung 8.8, 10.8 and 63.4 across
     three runs of the same build for that reason alone.
     ------------------------------------------------------------------------ */
  const rt = R.farSea().roadTop;
  const jrow = (rt !== undefined && rt !== null && rt > hz && rt < jy + 2) ? rt : jy;
  const yB = Math.round(jrow) + 3, yA = Math.round(jrow) - 3;
  const cB = centreAt(yB), cA = centreAt(yA);
  if(!(cB[1] > 0.7)) return { drew: false, thin: true };
  const below = median(yB, cB[0] - cB[1] * 0.55, cB[0] + cB[1] * 0.55);
  const above = median(yA, cA[0] - Math.max(1, cA[1] * 0.55),
                           cA[0] + Math.max(1, cA[1] * 0.55));
  /* ---- AND HALFWAY UP THE BAND, NOT AT THE HORIZON ITSELF ------------------
     The road converges to a POINT at the vanishing point, so a sample two pixels
     either side of it up there is mostly ground however well the band is drawn -
     it read a difference of 9.9 on a working build. Halfway between the join and
     the skyline the ribbon is still a few pixels wide, which is where the
     question "is that road or is that ground" can actually be asked. */
  const midY = Math.round((jy + hz) / 2);
  const midX = centreAt(midY)[0];
  /* A WIDE-ENOUGH SPAN TO CONTAIN A NARROW RIBBON. The road is only two or
     three pixels across up here and the bend moves it, so a span of a pixel or
     two centred on an estimate misses it; the darkest pixel within sixteen
     either side is the tarmac if there is any tarmac to find. The comparison is
     against the darkest pixel WELL out to the side in the same row, so a dark
     biome does not read as a road. */
  const atRoad = darkest(midY, midX - 16, midX + 16);
  const beside = darkest(midY, midX + 55, midX + 95);
  const dist = (a, b) => a && b
    ? Math.sqrt((a[0]-b[0])**2 + (a[1]-b[1])**2 + (a[2]-b[2])**2) : null;
  /* ---- A MISSING READING IS A MISSING READING, NOT A CRASH ---------------
     `dist` already answers null when either sample came back empty, and the two
     lines below then called `.toFixed` on it and threw - so the whole harness
     died with a TypeError instead of reporting which frame it could not read.
     It surfaced when RLG-295 doubled the draw and moved the rows these samples
     are taken at. A probe reports what it could not see. */
  const round2 = (v) => v === null ? null : +v.toFixed(2);
  return { drew: true, walked: fr.walked, capped: !!fr.capped, missed: fr.missed || 0,
           ahead0: fr.ahead0,
           reaches: Math.abs(fr.topY - fr.horizon) < 0.51 && Math.abs(fr.topW) < 0.01,
           step: round2(dist(below, above)),
           roadVsGround: round2(dist(atRoad, beside)) };
}"""


def rgb_of(v):
    """parse an rgb(...) string, keeping NaN as NaN so a check can report it.

    A first version cast straight to int and died with a traceback on the very defect it
    was written for, which is not a failure anyone can read."""
    out = []
    for x in v[v.index('(') + 1:-1].split(','):
        try:
            out.append(float(x))
        except ValueError:
            out.append(float('nan'))
    return out


SAMPLE_TONE = """() => {
  const R = window.__road, fr = R.farRoad();
  if(!fr || !fr.drew) return null;
  const cv = document.getElementById('cv'), g = cv.getContext('2d');
  const dpr = cv.width / cv.clientWidth;
  const read = (x, y) => { const d = g.getImageData(Math.round(x*dpr),
                             Math.round(y*dpr), 1, 1).data; return [d[0],d[1],d[2]]; };
  /* SAMPLED JUST ABOVE THE JOIN, NOT HALF WAY UP. The two meet at the join, so
     immediately above it the band is as wide as the road itself, while half way
     to the horizon it is one or two pixels and a sample misses it on a third to
     two thirds of frames - runs of one correct build read [115,128,84] and
     [113,127,81], which is the FIELD. The fill is one flat colour over the whole
     band, so a sample anywhere inside it answers the same question, and this
     picks the widest place there is. */
  const y = Math.max(fr.topY + 1, fr.joinY - 3);
  return { near: read(fr.joinX, fr.joinY + 4), far: read(fr.joinX, y) };
}"""

def main():
    bad = 0

    def ok(cond, label, detail=''):
        nonlocal bad
        if not cond:
            bad += 1
        print('  %s  %s%s' % ('ok  ' if cond else 'FAIL', label,
                              ('   ' + detail) if detail else ''))

    print('farroad-test  .  the tarmac reaches the horizon')
    with sync_playwright() as p:
        b = launch_chromium(p, headless=True,
                            args=['--mute-audio', '--autoplay-policy=no-user-gesture-required'])
        ctx = b.new_context(viewport={'width': 480, 'height': 900})
        page = ctx.new_page()
        errs = []
        page.on('pageerror', lambda e: errs.append(str(e)))
        boot(page, BASE + '/games/sw/interstate.html')
        page.wait_for_timeout(1200)
        page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
        page.click('[data-act="play"]')
        page.wait_for_timeout(400)
        # the drive's settings are on the SETTINGS screen (RLG-071)
        garage_screen(page, 'settings')
        page.click('[data-act="chase"]')
        garage_screen(page, 'main')
        page.wait_for_timeout(200)
        page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
        page.click('[data-act="drive"]')
        page.wait_for_timeout(1200)
        page.evaluate('() => window.__road.setTimed(false)')
        # DRIVING, AND IN DAYLIGHT. The band is a function of the road's relief, so the
        # car has to cover ground for the sample to be about more than one hilltop; and
        # a night sample would be measuring how dark two dark things are.
        page.evaluate("() => { const R = window.__road; window.__hold = setInterval(() => {"
                      " R.setSpd(0.55 * R.MAX_SPD); R.setPhase(0.60); R.setSky(0.12, 0);"
                      " R.setSnowy(0); }, 16); }")
        page.wait_for_timeout(2000)

        # MANY FRAMES, BECAUSE THE ROAD IS NOT ONE SHAPE. A single reading is one hill and
        # one bend; the claim is about the join wherever the road happens to be, so the
        # sample runs over a stretch of road and reports the WORST step it found.
        seen = []
        skipped = 0
        # NINETY FRAMES, NOT SIXTY. How much band there is to draw is a property of
        # the relief, and a run that happens to spend its sample cresting rises has
        # little of it - one run came back with nine frames of band against a floor of
        # ten and failed on the terrain rather than on the code. A longer stretch of
        # road covers more shapes of road.
        for _ in range(90):
            page.wait_for_timeout(160)
            d = page.evaluate(SAMPLE)
            if not d['drew']:
                skipped += 1
                continue
            seen.append(d)
        page.evaluate('() => clearInterval(window.__hold)')
        if SHOTS:
            page.screenshot(path=str(Path(ROOT, '_farroad.png')))

        print('  ..    %d frames with a band, %d without (the far slice was above the'
              ' horizon on those - a climbing road has nothing to fill)'
              % (len(seen), skipped))
        ok(len(seen) >= 10, 'the band is drawn over a stretch of road',
           '%d frames of %d' % (len(seen), len(seen) + skipped))
        if not seen:
            print('\n  1 FAILURES')
            ctx.close()
            b.close()
            srv.shutdown()
            return 1

        walked = [d['walked'] for d in seen]
        steps = sorted(d['step'] for d in seen)
        rvg = sorted(d['roadVsGround'] for d in seen)
        worst = steps[-1]
        med = steps[len(steps)//2]
        print('  ..    it walks %d to %d points to the horizon'
              % (min(walked), max(walked)))
        print('  ..    tone step across the join: median %.1f, worst %.1f (0-441 scale)'
              % (med, worst))
        print('  ..    road against the ground beside it at the horizon: median %.1f'
              % rvg[len(rvg)//2])


        # THE MAXIMUM, NOT THE MEDIAN. How many points a given frame walks depends
        # entirely on how much road there is between the last drawn slice and the
        # skyline, and that is a property of the relief - a frame cresting a rise
        # has almost none and correctly emits nothing. What is stable, and what the
        # ruling actually asks, is that the band FOLLOWS the road rather than being
        # one straight cone: over a stretch of road it has to walk somewhere.
        ok(max(walked) >= 5, 'and it walks rather than drawing one straight cone',
           'up to %d points, median %d' % (max(walked), sorted(walked)[len(walked)//2]))
        # ---- AND IT HOLDS STILL: THE SAME POINTS EVERY FRAME (RLG-281) ---------
        # Owner, 2026-09-19, from the device: "The far road flickers. Maybe
        # z-fighting?" It was the outline re-cutting itself. A point that failed the
        # rising test was DROPPED, so the count changed from frame to frame wherever a
        # point sat on the line - beside the horizon or behind a crest - and a third of
        # all frames drew a differently shaped band. Its points were also placed from a
        # whole segment index, so every one of them jumped each time the car crossed a
        # segment. A point is clamped now rather than dropped, and placed from the car's
        # own position, so the count is the same on every frame the band is drawn.
        # A walk may still END EARLY, by design, where a hard bend takes the road off the
        # screen (the corner cap) or a point will not project. Those frames say so; every
        # other frame must walk every point.
        open_ = [d['walked'] for d in seen if not d.get('capped') and not d.get('missed')]
        print('  ..    %d of %d frames walked with no bend cap and no missed point'
              % (len(open_), len(seen)))
        # AND THE POINTS STAY THE SAME DISTANCE AHEAD. Placed from a whole segment index
        # they jumped a segment along the road each time the car crossed one, which kept
        # the count steady and still re-cut the outline - so it is asked separately.
        ahead = [d['ahead0'] for d in seen if d.get('ahead0') is not None]
        ok(bool(ahead) and max(ahead) - min(ahead) < 1,
           'and its points stay the same distance ahead of the car, so none of them jumps',
           'the first point ranged %.0f to %.0f units ahead' % (min(ahead) if ahead else -1,
                                                              max(ahead) if ahead else -1))
        ok(bool(open_) and min(open_) == max(open_),
           'and its outline keeps the same points on every frame, so it does not re-cut itself',
           'the count ran %s to %s on uncapped frames' % (min(open_) if open_ else None,
                                                          max(open_) if open_ else None))
        # ---- AND THE TONE STEP IS PRINTED, BECAUSE IT COULD NOT BE MEASURED -----
        # THE RULING ASKED FOR THIS NUMBER BY NAME and this session could not make
        # it into an assertion that means anything. Four sampling schemes were tried
        # and each was dominated by something other than the seam:
        #
        #   the MEAN across the road caught the lane markings, which are white on
        #     grey and put a "step" of 197 where the surfaces agreed;
        #   the DARKEST pixel caught the rumble strip and the shadow line below the
        #     join against uniform tarmac above it;
        #   sampling around the VANISHING POINT put both samples on the verge, where
        #     they agreed with each other perfectly and said nothing - the colours
        #     came back green;
        #   and sampling around the far slice's own y put both samples inside the
        #     BAND, because the road pass stops at whichever slice survives the crest
        #     guards and that is tens of pixels lower on a rolling road.
        #
        # Anchoring on `roadTop` fixed the last of those and the reading still swung
        # 34, 84 and 39 across three runs of one unchanged build. The quantity is
        # real; this instrument cannot hold it still, and a threshold tuned until it
        # passed would be a number chosen from noise. THE JOIN NEEDS A DEVICE.
        print('  ..    (printed, not asserted: the tone step reads %.1f here and has'
              ' swung 34, 84 and 39 across runs of one build - see the note in the'
              " source. The join is the owner's to judge.)" % med)
        # ---- AND IT REACHES THE HORIZON, ASSERTED STRUCTURALLY ------------------
        # A pixel comparison was tried for this and could not be made to hold: up
        # there the ribbon is two or three pixels wide, the bend moves it between
        # the join and the vanishing point, and a sample placed by interpolation
        # lands on the verge often enough to read 1.7 on a build whose band is
        # plainly drawn. What IS exact is the polygon's own top vertex, which the
        # engine reports: the band closes at the vanishing point, on the horizon,
        # by construction. With the band removed `drew` is false and every line
        # here goes red, which is the falsification that matters.
        ok(all(d.get('reaches') for d in seen),
           'and every band closes at the vanishing point on the horizon',
           'some did not reach it')
        print('  ..    (diagnostic, not an assertion: road against ground at the'
              ' half-way row reads %.1f - the ribbon is two or three pixels wide'
              ' there and a sample placed by interpolation misses it too often)'
              % rvg[len(rvg)//2])

        # ---- AND IT IS TARMAC, NOT WHATEVER WAS PAINTED LAST (RLG-281) ---------
        # Owner, 2026-09-16: "the simulated roadway that goes off into the horizon,
        # needs to match the color of the road per biome."
        #
        # THE BAND WAS FILLED WITH rgb(NaN,NaN,NaN). mixRGB wants a colour string and an
        # RGB ARRAY and was handed a second string, so every channel came out NaN - and a
        # canvas SILENTLY IGNORES an invalid fillStyle and keeps the one before it, which
        # is the ground or the skyline of the place being drawn. In FARMLAND the road to
        # the horizon measured [115,128,84], PIXEL-IDENTICAL to the grass beside it.
        #
        # PINNED TO ONE PLACE, because the free-driving sample above cannot answer this:
        # its road-against-ground median swung 23.9, 36.6 and 82.2 across three runs of
        # one build, purely on which biome the run happened to spend its time in - a
        # forest's ground is nearly tarmac-coloured and a farmland's is not. Pinning it
        # to the brightest ground on the board turns a number that overlaps into one that
        # does not: 0 when broken, about 150 when right.
        #
        # AND A MISSED SAMPLE CAN ONLY FAIL THIS, NEVER PASS IT. If the two or three
        # pixel ribbon is missed the reading falls toward the ground's own colour, which
        # is the failing direction. That is the safe way round for a check to be wrong.
        page.evaluate("""() => { const R = window.__road;
          R.setTimed(false); R.holdCurve(0);
          R.setBiomePair('FARMLAND','FARMLAND'); R.setPhase(0.75);
          R.setWet(0); R.setSnow(0); R.setPool(0); R.clearTraffic();
          R.setSpd(R.MAX_SPD * 0.30); }""")
        for _ in range(20):
            page.evaluate("() => { const R = window.__road;"
                          " R.clearTraffic(); R.setSpd(R.MAX_SPD * 0.30); }")
            page.wait_for_timeout(45)
        # ---- AND THE WORLD IS HELD STILL BEFORE ANY PIXEL IS READ --------------
        # `farRoad()` is the bookkeeping the LAST completed frame left behind, and
        # getImageData reads whatever is on the canvas NOW. With the car moving, the
        # road has shifted between the two, so a sample placed by the old frame's
        # joinX lands wherever the new frame put the verge - runs of one correct
        # build read [112,127,76], [114,127,82] and [185,166,72], the last of which
        # is a cornfield. `setSpd(0)` is a value the engine moves on from; `holdSpd`
        # pins it, which is the same lesson hazard-test's own note records.
        for _ in range(10):
            page.evaluate("() => { const R = window.__road;"
                          " R.clearTraffic(); R.holdSpd(0); }")
            page.wait_for_timeout(45)
        # ---- DID THE CANVAS ACCEPT THE COLOUR? -------------------------------------
        # This is the ONE question the code cannot answer for itself. The defect was
        # that mixRGB produced rgb(NaN,NaN,NaN) and A CANVAS SILENTLY IGNORES AN INVALID
        # fillStyle, KEEPING THE PREVIOUS ONE - so the computed value was never the
        # painted one, and nothing anywhere said so.
        #
        # ASKED BY A ROUND TRIP, NOT BY SAMPLING A PIXEL. Four placements of a pixel
        # sample were tried and every one was flaky, because the ribbon is one or two
        # pixels wide and the scene moves: readings of [115,128,84], [113,127,81],
        # [112,127,76] and [185,166,72] - grass, grass, grass and a CORNFIELD - all came
        # off builds whose colours were exactly right. Setting a fillStyle and reading it
        # back tests the acceptance itself, deterministically, in one line: a canvas
        # returns the normalised colour if it took it and the PREVIOUS one if it did not.
        #
        # AND IT COVERS EVERY TONE THE ROAD CAN HAVE, which a picture of one frame never
        # could - both parities, a deck and an ordinary road, dry, snow-covered and wet.
        # The deck is in the list because that is where this last bit, DECK_FACE, was
        # still a string long after the far band was fixed.
        print()
        print('  AND THE CANVAS ACCEPTS EVERY TONE THE ROAD CAN HAVE')
        bad_tones = page.evaluate("""() => {
          const R = window.__road;
          const c = document.createElement('canvas').getContext('2d');
          const out = [];
          const weather = [['dry',0,0,0], ['snow-covered',0,0.9,0], ['raining',1,0,0.8]];
          const places = [['an ordinary road','FARMLAND'], ['a bridge deck','BRIDGE']];
          for(const [pn, key] of places){
            R.setBiomePair(key, key);
            for(const [wn, w, sn, po] of weather){
              R.setWet(w); R.setSnow(sn); R.setPool(po);
              const t = R.farRoadTone();
              for(const which of ['far','nearLit','nearDark']){
                c.fillStyle = '#000000';
                c.fillStyle = t[which];
                /* black is what it keeps when it refuses, and no real tone here is black */
                if(c.fillStyle === '#000000')
                  out.push(pn + ', ' + wn + ', ' + which + ': ' + t[which]);
              }
            }
          }
          R.setWet(0); R.setSnow(0); R.setPool(0);
          return out;
        }""")
        print('  ..    18 tones offered to a canvas: 2 parities and the band, over 3'
              ' weathers, on a road and on a deck')
        ok(not bad_tones,
           'the canvas accepts every colour the road computes - none is NaN',
           '; '.join(bad_tones[:4]) if bad_tones else 'all 18 taken')

        page.evaluate('() => window.__road.holdSpd(null)')

        # ---- AND IT TRACKS THE WEATHER, NOT JUST THE DRY CASE (RLG-281) --------
        # Owner, 2026-09-16, on the repaint: does the far road match the near road in
        # every place, "which also includes snowiness?"
        #
        # THE TARMAC HAS NO BIOME TERM - tarmacTone takes a parity, a fade and a deck
        # flag and nothing else - so the road is one colour everywhere and what differs
        # between places is the WEATHER and the light they produce. The question is
        # therefore whether the far band picks those up, and it is asked of the colours
        # the engine COMPUTES rather than of pixels: at the half-way row the ribbon is
        # one or two pixels wide, and two runs of one build sampled [33,32,46] and
        # [73,80,64] from the same place depending on where the bend put it.
        #
        # RAIN IS THE ONE THAT CAN DISAGREE. tarmacTone's last term is the sky coming back
        # off wet tarmac, scaled by 1 - fade, and FADE IS 0 AT THE FAR END OF THE DRAW (the
        # road pass writes it as 1 - n/DRAW) - so the slice the band joins carries the
        # whole sheen. The 2026-09-16 version of this check asked both sides at fade 1,
        # the value at the car, and so passed a band with no sheen at all beside a slice
        # with all of it: the owner saw it on the device on 2026-09-19. `farRoadTone()`
        # now answers at the join's own fade, and its `far` is the renderer's own colour.
        print()
        print('  AND IT TRACKS THE WEATHER')
        rgb = rgb_of
        for label, (w, sn, po) in (('dry', (0, 0, 0)), ('snow-covered', (0, 0.9, 0)),
                                   ('raining', (1, 0, 0.8))):
            page.evaluate("([w, sn, po]) => { const R = window.__road;"
                          " R.setWet(w); R.setSnow(sn); R.setPool(po); }", [w, sn, po])
            page.wait_for_timeout(140)
            t = page.evaluate('() => window.__road.farRoadTone()')
            far, lit, dark = rgb(t['far']), rgb(t['nearLit']), rgb(t['nearDark'])
            mid = [(a + b) / 2.0 for a, b in zip(lit, dark)]
            gap = sum((a - b) ** 2 for a, b in zip(far, mid)) ** 0.5
            print('  ..    %-13s far %-16s near %s / %s   gap %.1f'
                  % (label, str(far), str(lit), str(dark), gap))
            ok(gap < 8, 'the far band matches the road it joins when %s' % label,
               'they differ by %.1f' % gap)
        # AND THE SNOW REALLY MOVED IT, or the check above would pass on a band that
        # ignores the weather as completely as the road does.
        page.evaluate("() => { const R = window.__road;"
                      " R.setWet(0); R.setSnow(0.9); R.setPool(0); }")
        page.wait_for_timeout(140)
        snowy_far = rgb(page.evaluate('() => window.__road.farRoadTone()')['far'])
        page.evaluate("() => { const R = window.__road;"
                      " R.setWet(0); R.setSnow(0); R.setPool(0); }")
        page.wait_for_timeout(140)
        dry_far = rgb(page.evaluate('() => window.__road.farRoadTone()')['far'])
        moved = sum((a - b) ** 2 for a, b in zip(snowy_far, dry_far)) ** 0.5
        ok(moved > 80,
           'and snow really does whiten the far band, so the match is not two constants',
           'dry %s, under snow %s, apart by %.1f' % (dry_far, snowy_far, moved))

        ok(errs == [], 'no page errors', errs[0][:120] if errs else '')
        ctx.close()
        b.close()
    srv.shutdown()
    print()
    print('  ' + ('the tarmac reaches the horizon' if not bad else str(bad) + ' FAILURES'))
    return 1 if bad else 0


sys.exit(main())
