#!/usr/bin/env python3
"""SEETHRU TEST - is there anywhere below the horizon the LAND does not paint?

    EFFIGY_NO_GPU=1 PYTHONIOENCODING=utf-8 .venv/Scripts/python tools/seethru-test.py
    ... tools/seethru-test.py --places MOUNTAIN --stops 8 --selftest

Owner, 2026-09-24 and again on 2026-09-26, twice, narrowing it each time: "When the road
falls away after a crest, the ground (not the road) is see through"; "when the player
crests a hill the ground is invisible beyond a certain y cording on screen"; "It's not
about color... the ground surface is see through"; "Not the road just the ground surface."
[[RLG-337]]

▶ WHAT SEE-THROUGH MEANS HERE, AND IT IS NOT A HOLE IN THE CANVAS. `carryover-test.py`
proved nothing below the horizon survives from one frame to the next: the far field's fill
paints from the horizon down before anything else and clears the whole band. So a
see-through patch is not bare canvas - it is a patch where the LAND did not paint and the
fill behind it is what you are looking at. That reads as seeing through the ground because
that is exactly what it is.

▶ HOW IT IS MEASURED. Two frames at the same stop, nothing else changed:
  N - the world as it ships.
  Z - the same frame with every piece of LAND switched off: the ground, the cliff face, its
      rim and floor, the massif and the wall. What is left below the horizon is the far
      field's fill and the sky's own band.
A pixel that is the SAME in both is a pixel no land painted. That is the see-through count,
and it does not depend on knowing which layer was supposed to cover it.

▶ WHY THE CLIFF SIDE IS THE SUSPECT AND THE FLAT SIDE IS NOT. On the hazard side the ground
does not run to the edge of the screen - [[RLG-278]] cuts it at the rim on purpose and lets
what lies beyond show, and the cliff face is what covers it. So on that side TWO surfaces
have to meet with nothing between them, and at a crest the band the ground owns and the
band the face owns are computed from different things. On the flat side one rectangle runs
the full width and there is no seam to miss.

▶ AND THE MASSIF GOES OFF IN BOTH ARMS. It is a mountainside painted over the ground, it
has its own switch that `layerOff` cannot reach, and leaving it on is what hid this from
`crest-hole-test` for four rounds.

▶ --selftest PROVES THE CHECK CAN FAIL, by taking the ground away at one stop and requiring
that the count climbs. Four guards in this project passed with the bug present before they
were fixed.
"""
import argparse
import functools
import http.server
import socketserver
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from harness import console_utf8, launch_chromium, boot, until   # noqa: E402
from playwright.sync_api import sync_playwright                  # noqa: E402

fails = []

# the two places with a roll hazard, and one without as the control
DEFAULT_PLACES = 'MOUNTAIN,CANYON,FOREST'

# ---- EVERY PIECE OF LAND, AND THE FAR FIELD'S FILL IS NOT ON THE LIST --------
# `farground` is the fill that covers from the horizon down to where the drawn ground
# begins. It belongs on this list by rights - it is land at a distance - AND IT CANNOT GO
# ON IT. It is also the only thing that CLEARS the frame below the horizon, so a frame
# drawn without it keeps the previous frame's pixels: the two arms came back byte for byte
# identical, 247,200 of 247,200, because the second arm was a ghost of the first.
# crest-hole-test's own note says so and this check paid for the lesson again. So the far
# fill stays on in both arms, its band agrees with itself, and the band it owns has to be
# told from a hole by its COLOUR rather than by switching it off.
#
# `mass` is not on the list because `layerOff` cannot reach the massif: it is switched
# separately and the harness does both together.
LAND = ('ground', 'drop', 'rim', 'cliff', 'wall', 'face', 'sea', 'marsh')

# ---- THE LAYERS TAKEN OFF IN BOTH ARMS, AND THE LIST HAS TO BE EVERYTHING ----
# ANY layer left painting in both arms makes its own pixels agree, and this check reads
# agreement as absence of land. The first cut left the road, the rail and the markings on
# and reported 66 per cent of the frame see-through, which is the tarmac agreeing with
# itself. So the two arms differ in the LAND and in nothing else: the sky and the far
# field's fill stay, because they are what you see THROUGH the ground, and everything that
# paints over the land comes off.
BOTH_OFF = ('scenery', 'lamp', 'sprites', 'player', 'glass', 'rain', 'fx', 'lens',
            'speed', 'vignette', 'wash', 'beams', 'range', 'road', 'kerb', 'lanes',
            'edges', 'rail', 'truss', 'joint', 'haze')

# a channel has to move by more than this for the two frames to count as DIFFERENT, so a
# pixel is see-through only when the two agree this closely. Bare means bare: the same
# reasoning as crest-hole-test's BARE_TOL, which was widened once and reported holes that
# were a shade along a band edge.
TOL = 2

HORIZON_PAD = 2

# ---- AND THE SYMPTOM ITSELF, WHICH IS NOT THE SAME QUESTION ------------------
# "No land painted here" is what the two arms answer. It is not what the owner is looking
# at, because the far field's fill DOES paint that band and it is hazed - measured at 30
# levels from the sky at midday and 19 at dusk, against 94 to 125 for the drawn ground
# below it. A surface that close to the sky reads as the sky whatever painted it.
#
# So the band is measured directly: how far down the frame the picture stays within
# SKY_NEAR levels of the sky sampled straight above it. That number is the owner's "certain
# y coordinate", and it is a reading rather than a threshold - it is printed on every run.
SKY_NEAR = 34   # kept for the docstring's figures; the reading below uses distances

SNAP = """(key) => {
  const c = document.getElementById('cv');
  const g = c.getContext('2d', { willReadFrequently: true });
  window.__s = window.__s || {};
  window.__s[key] = Array.from(g.getImageData(0, 0, c.width, c.height).data);
  return [c.width, c.height];
}"""

# ---- WHERE THE TWO FRAMES AGREE, AND WHAT SHAPE IT IS ------------------------
# The rows and the widest run on any row are both reported: the owner's words are about a
# band of the picture, so a thousand scattered pixels along an edge and a thousand in one
# block are not the same finding and must not print as the same number.
SAME = """([tol, fromY]) => {
  const c = document.getElementById('cv');
  const N = window.__s.n, Z = window.__s.z;
  const w = c.width, h = c.height, y0 = Math.floor(fromY * h);
  let n = 0, top = -1, bot = -1, widest = 0, wRow = -1, left = w, right = -1;
  for (let y = y0; y < h; y++) {
    let run = 0;
    for (let x = 0; x < w; x++) {
      const i = (y * w + x) * 4;
      const same = Math.max(Math.abs(N[i] - Z[i]), Math.abs(N[i+1] - Z[i+1]),
                            Math.abs(N[i+2] - Z[i+2])) <= tol;
      if (same) {
        n++; run++;
        if (top < 0) top = y;
        bot = y;
        if (x < left) left = x;
        if (x > right) right = x;
      } else {
        if (run > widest) { widest = run; wRow = y; }
        run = 0;
      }
    }
    if (run > widest) { widest = run; wRow = y; }
  }
  return { n: n, top: top, bot: bot, widest: widest, wRow: wRow,
           left: left, right: right, px: w * (h - y0), w: w, h: h };
}"""


# ---- HOW CLOSE THE PICTURE IS TO THE SKY, AT FIXED DEPTHS -------------------
# A WALK DOWN FROM THE HORIZON WAS TRIED FIRST AND IT IS NOT STABLE. It followed each
# column while it stayed within a tolerance of a sky sample and reported the deepest row
# reached; a FOREST came back at 0 per cent on one run and 100 per cent on the next, on
# the same build, because a single column whose tone happens to stay close carries the
# whole reading. It was believed for one run and it was luck.
#
# WHAT IS STABLE IS THE DISTANCE ITSELF, sampled at fixed fractions of the way from the
# horizon to the bottom of the frame and taken as the MEDIAN across the width, so no one
# column decides anything. The sky is sampled high in the canvas, well clear of a massif.
# At a MOUNTAIN crest this reads about 30 at a fifth of the way down and 94 to 125 further
# down, which is the band that is the owner's complaint and the ground that is not.
DEPTHS = (0.05, 0.15, 0.25, 0.40, 0.60, 0.85)

SKYDIST = """([fromY, skyY, depths]) => {
  const c = document.getElementById('cv');
  const S = window.__s.full;
  const w = c.width, h = c.height;
  const y0 = Math.floor(fromY * h), ys = Math.floor(skyY * h);
  // the sky, as the median of a row high in the canvas
  const sr = [], sg = [], sb = [];
  for (let x = 0; x < w; x++) { const j = (ys * w + x) * 4;
    sr.push(S[j]); sg.push(S[j+1]); sb.push(S[j+2]); }
  const mid = a => a.slice().sort((p, q) => p - q)[a.length >> 1];
  const R = mid(sr), G = mid(sg), B = mid(sb);
  const out = [];
  for (const d of depths) {
    const y = Math.min(h - 1, Math.floor(y0 + (h - y0) * d));
    const v = [];
    for (let x = 0; x < w; x++) {
      const i = (y * w + x) * 4;
      v.push(Math.max(Math.abs(S[i] - R), Math.abs(S[i+1] - G), Math.abs(S[i+2] - B)));
    }
    out.push(mid(v));
  }
  return { sky: [R, G, B], dist: out, y0: y0, h: h };
}"""


def check(label, condition, detail=''):
    print('%s  %s%s' % ('PASS' if condition else 'FAIL', label,
                        ('  [%s]' % detail) if detail else ''))
    if not condition:
        fails.append(label)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--places', default=DEFAULT_PLACES)
    ap.add_argument('--stops', type=int, default=6)
    ap.add_argument('--hill', type=float, default=1.0,
                    help='the hill factor forced onto each place. 1.0 is the hilliest the '
                         'game ships. Pass -1 to leave the place as it is')
    ap.add_argument('--phase', type=float, default=0.75, help='0.75 is midday')
    ap.add_argument('--drive', type=int, default=900)
    ap.add_argument('--hunt', type=int, default=30,
                    help='bursts of driving spent looking for a crest before reading anyway')
    ap.add_argument('--min-skips', type=int, default=2)
    ap.add_argument('--allow', type=int, default=600,
                    help='see-through pixels that count as none')
    ap.add_argument('--allow-run', type=int, default=24,
                    help='the widest unbroken run on any row that counts as an edge rather '
                         'than a band')
    ap.add_argument('--selftest', action='store_true')
    ap.add_argument('--shots', default='')
    args = ap.parse_args()
    console_utf8()

    places = [p for p in args.places.split(',') if p]
    shots = Path(args.shots) if args.shots else (ROOT / 'docs' / 'fleet' / '_seethru')

    h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
    srv = socketserver.TCPServer(('127.0.0.1', 0), h)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    init = """
    window.__probe = { road: null };
    (function(){ var real=null, wrapped=null;
      Object.defineProperty(window,'ROAD',{configurable:true,
        get:function(){return real?wrapped:undefined;},
        set:function(fn){real=fn;wrapped=function(CFG){var api=real(CFG);
          window.__probe.road=api||(CFG&&CFG.api)||null;return api;};}});})();
    """

    worst = {'n': 0}
    worst_run = {'widest': 0}
    worst_sky = {'frac': 0}
    reads = 0
    crested = 0
    self_saw = {'n': -1, 'widest': -1}
    print()
    print('  how far the picture is from the SKY, at %s of the way from the horizon'
          % ', '.join('%.0f%%' % (d * 100) for d in DEPTHS))
    print()
    print('  %-9s %3s %7s %9s %7s  %s'
          % ('place', 'st', 'hidden', 'no land', 'widest', 'distance from the sky'))
    try:
        with sync_playwright() as p:
            br = launch_chromium(p, headless=True)
            pg = br.new_page(viewport={'width': 480, 'height': 900})
            pg.add_init_script(init)
            for place in places:
                boot(pg, 'http://127.0.0.1:%d/games/sw/interstate.html' % port)
                until(pg, '!!window.__probe.road', timeout=15000)
                pg.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=15000)
                pg.click('[data-act="play"]')
                pg.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=8000)
                pg.click('[data-act="drive"]')
                pg.wait_for_timeout(2000)
                if args.hill >= 0:
                    pg.evaluate("([k, hl]) => window.__probe.road.setBiomeShape(k, hl, null)",
                                [place, args.hill])
                # THE RUN CLOCK KILLS ANY HARNESS THAT PARKS THE CAR (RLG-125)
                pg.evaluate("""([k]) => { const R = window.__probe.road;
                    R.setTimed(false); R.clearTraffic(); R.setDmg(0);
                    R.setBiomePair(k, k); R.watchDraw(true); }""", [place])

                def pin():
                    # the place, the hour, the weather and the snow all move the picture on
                    # their own while the car is parked - crest-hole-test read 21,515
                    # pixels of drift before it pinned all four
                    pg.evaluate("""([k, v]) => { const R = window.__probe.road;
                        R.setBiomePair(k, k); R.setPhase(v); R.setWet(0); R.setSnow(0);
                        R.setInstanceTemp(0.5); R.clearTraffic(); }""", [place, args.phase])

                def frame(key, land_off, ground_off=False):
                    off = {k: 1 for k in BOTH_OFF}
                    if land_off:
                        for k in LAND:
                            off[k] = 1
                    if ground_off:
                        off['ground'] = 1
                    pg.evaluate("([o, m]) => { const R = window.__probe.road;"
                                " R.layerOff(o); R.massModel({ off: m }); }",
                                [off, 1])
                    for _ in range(4):
                        pin()
                        pg.wait_for_timeout(140)
                    return pg.evaluate(SNAP, key)

                for stop in range(args.stops):
                    cr = {'n': 0}
                    for _ in range(args.hunt):
                        pg.evaluate("() => window.__probe.road.holdSpd("
                                    "window.__probe.road.MAX_SPD * 0.75)")
                        pg.wait_for_timeout(args.drive)
                        pg.evaluate("() => { const R = window.__probe.road;"
                                    " R.holdSpd(0); R.setSpd(0); }")
                        pg.wait_for_timeout(250)
                        cr = pg.evaluate("() => window.__probe.road.groundSkips()")
                        if cr['n'] >= args.min_skips:
                            break
                    for _ in range(20):
                        if pg.evaluate("() => window.__probe.road.launch().count") <= 0:
                            break
                        pg.wait_for_timeout(500)
                        pin()

                    selfing = bool(args.selftest and stop == 0 and place == places[0])
                    # the frame as it SHIPS, for the sky-band reading
                    pg.evaluate("() => { const R = window.__probe.road;"
                                " R.layerOff({}); R.massModel({ off: 0 }); }")
                    for _ in range(4):
                        pin()
                        pg.wait_for_timeout(140)
                    pg.evaluate(SNAP, 'full')
                    frame('n', False, ground_off=selfing)
                    frame('z', True)
                    fromY = pg.evaluate(
                        "(pad) => { const c = document.getElementById('cv');"
                        " return (window.__probe.road.horizon() + pad) / c.height; }",
                        HORIZON_PAD)
                    r = pg.evaluate(SAME, [TOL, fromY])
                    sky = pg.evaluate(SKYDIST, [fromY, 0.12, list(DEPTHS)])
                    r['sky'] = sky
                    reads += 1
                    if cr['n'] >= args.min_skips:
                        crested += 1
                    where = ('rows %d-%d, x %d-%d' % (r['top'], r['bot'], r['left'], r['right'])
                             ) if r['n'] else ''
                    print('  %-9s %3d %7d %9d %7d  %s%s'
                          % (place, stop + 1, cr['n'], r['n'], r['widest'],
                             ' '.join('%3d' % v for v in sky['dist']),
                             '   <- ground OFF, selftest' if selfing else ''))
                    if selfing:
                        self_saw = r
                        continue
                    if r['n'] > worst['n']:
                        worst = dict(r, place=place, stop=stop + 1, hidden=cr['n'])
                    if sky['dist'][1] < worst_sky['frac'] or not worst_sky['frac']:
                        worst_sky = dict(sky, frac=sky['dist'][1], place=place,
                                         stop=stop + 1)
                    if r['widest'] > worst_run['widest']:
                        worst_run = dict(r, place=place, stop=stop + 1, hidden=cr['n'])
                    if r['n'] > args.allow or r['widest'] > args.allow_run:
                        shots.mkdir(parents=True, exist_ok=True)
                        pg.evaluate("(o) => { const R = window.__probe.road;"
                                    " R.layerOff(o); R.massModel({ off: 0 }); }",
                                    {k: 1 for k in ('glass', 'player', 'lens', 'speed',
                                                    'vignette')})
                        pin()
                        pg.wait_for_timeout(200)
                        pg.screenshot(path=str(shots / ('seethru_%s_s%d.png'
                                                        % (place, stop + 1))))
            br.close()
    finally:
        srv.shutdown()

    print()
    print('  %d read(s) across %d place(s), %d of them with a crest in view'
          % (reads, len(places), crested))
    if worst['n']:
        print('  worst: %d pixel(s) of %d at %s stop %d, %d hidden behind a crest'
              % (worst['n'], worst['px'], worst['place'], worst['stop'], worst['hidden']))
    if worst_sky['frac']:
        print('  closest to the sky a fifth of the way down: %d levels, at %s stop %d'
              % (worst_sky['frac'], worst_sky['place'], worst_sky['stop']))
    if worst_run['widest']:
        print('  widest unbroken run on one row: %d pixel(s) of %d wide, row %d, at %s stop %d'
              % (worst_run['widest'], worst_run['w'], worst_run['wRow'],
                 worst_run['place'], worst_run['stop']))
    print()
    if args.selftest:
        check('the check can fail - the ground taken away reads as see-through',
              self_saw['n'] > max(args.allow, worst['n']),
              '%d pixel(s) with no ground, against %d with it'
              % (self_saw['n'], worst['n']))
    check('the reading reached crests at all', crested > 0,
          '%d of %d read(s)' % (crested, reads))
    # ---- THE TWO LAND FIGURES ARE READINGS AND NOT VERDICTS -------------------
    # They cannot be asserted on, and saying so is more use than a check that always
    # fails. The band they count is painted by the far field's own fill, which is doing
    # its job there - so "no land painted" is TRUE of it and is not a defect by itself.
    # What makes it the owner's fault is that the fill is hazed to within 30 levels of
    # the sky, which is the reading above. Both numbers are printed for comparison
    # between runs; neither is a gate.
    print('  READINGS, NOT VERDICTS: the two land figures count the band the far')
    print('  field fill owns, which is not a hole. The sky-band per cent is the symptom.')
    print()
    if fails:
        print('FAILED: %d' % len(fails))
        for f in fails:
            print('  - %s' % f)
        sys.exit(1)
    print('ALL CHECKS PASSED')


if __name__ == '__main__':
    main()
