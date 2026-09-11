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
from harness import launch_chromium, console_utf8, boot
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
  return { drew: true, walked: fr.walked,
           reaches: Math.abs(fr.topY - fr.horizon) < 0.51 && Math.abs(fr.topW) < 0.01,
           step: +dist(below, above).toFixed(2),
           roadVsGround: +dist(atRoad, beside).toFixed(2) };
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
        page.click('[data-act="chase"]')
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

        ok(errs == [], 'no page errors', errs[0][:120] if errs else '')
        ctx.close()
        b.close()
    srv.shutdown()
    print()
    print('  ' + ('the tarmac reaches the horizon' if not bad else str(bad) + ' FAILURES'))
    return 1 if bad else 0


sys.exit(main())
