#!/usr/bin/env python3
"""
BEAM TEST - the headlights lay light on the road, and only when the road is dark.

    .venv/Scripts/python tools/beam-test.py
    .venv/Scripts/python tools/beam-test.py --shots

RLG-060. Owner, 2026-08-30: the beams do not look right, and they seem to be on all the time.

IT PHOTOGRAPHS THE SAME ROAD TWICE, once with the beam and once without, and subtracts. That is the
only way to ask what the BEAM did rather than what the scene looks like. Comparing two times of day
instead would change the sky, the ground tone and every lamp in the picture along with the one thing
being measured, which is the mistake `lamp-test.py` was rewritten to stop making.

AND IT MEASURES ITS OWN NOISE, ROW BY ROW. The scene does not hold still: traffic drives and the sky
turns, and at midday a bright sky moves ten times the brightness a dark one does. One number for the
whole picture is useless in both directions - it failed a correct build at night, and at midday it
grew so large that a beam drawing in broad daylight would have passed underneath it. So every run
takes TWO beam-off frames first, keeps the difference between them per row, and then asks of each row
whether the beam added more light than that row moves on its own.

The four questions:

  1. does the light reach the tarmac beside the car - the fault the owner saw, where the throw began
     above the car's own roofline and the road at the bumper stayed dark;
  2. does it stay on the ground - a beam has no business above the horizon;
  3. does it die out on the road rather than stopping at a line;
  4. is it off in daylight, and off because of the CLOCK rather than by luck.

Exit code 0 if every check passed, 1 otherwise.
"""

import argparse
import functools
import http.server
import io
import socketserver
import sys
import threading
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from harness import console_utf8, launch_chromium, boot, until

GAME = 'games/sw/interstate.html'

INIT = r"""
window.__probe = { errors: [], api: null };
(function(){
  var real = null, wrapped = null;
  Object.defineProperty(window, 'ROAD', {
    configurable: true,
    get: function(){ return real ? wrapped : undefined; },
    set: function(fn){
      real = fn;
      wrapped = function(CFG){
        var api = real(CFG);
        window.__probe.api = api || (CFG && CFG.api) || null;
        return api;
      };
    }
  });
})();
window.addEventListener('error', function(e){ window.__probe.errors.push(String(e.message)); });
"""

# how far above its own noise a row has to lift before it counts as lit, and the floor under that
# so a perfectly still row cannot be called lit by one brightness level of rounding
OVER_NOISE = 3.0
FLOOR = 0.8
# and how many rows in a row. A beam is an unbroken band down the picture; a car crossing the
# frame is a handful of rows. Below this, it is traffic.
MIN_RUN = 8
# and how still is still. A fixed wait after a jump from midnight to midday was not enough on
# about one run in three, and the transition it was still measuring read as twenty brightness
# levels of noise - eighty times what the same scene settles to.
SETTLED = 3.0


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def serve(root):
    handler = functools.partial(QuietHandler, directory=str(root))
    httpd = socketserver.TCPServer(('127.0.0.1', 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.socket.getsockname()[1]


class Results:
    def __init__(self):
        self.fails = []

    def check(self, ok, label, detail=''):
        print(('  ok    ' if ok else '  FAIL  ') + label + ('' if ok else '   [' + str(detail) + ']'))
        if not ok:
            self.fails.append(label)


def rows_of(im):
    g = im.convert('L')
    w, h = g.size
    px = g.load()
    return [[px[x, y] for x in range(w)] for y in range(h)]


def gain(a, b):
    """Mean brightness ADDED by b over a, per row. The beam only ever adds light."""
    return [sum(max(0, q - p) for p, q in zip(ra, rb)) / len(ra) for ra, rb in zip(a, b)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--headed', action='store_true')
    ap.add_argument('--shots', action='store_true')
    args = ap.parse_args()
    console_utf8()
    res = Results()
    httpd, port = serve(ROOT)
    print('beam-test  .  the headlights lay light on the road')

    with sync_playwright() as p:
        browser = launch_chromium(p, headless=not args.headed)
        page = browser.new_context(viewport={'width': 480, 'height': 900},
                                   has_touch=True, is_mobile=True).new_page()
        page.add_init_script(INIT)
        boot(page, 'http://127.0.0.1:%d/%s' % (port, GAME))
        until(page, '!!window.__probe.api', timeout=10000)
        page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
        page.click('[data-act="play"]')
        page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
        page.click('[data-act="drive"]')
        page.wait_for_timeout(1700)

        # A DRY, STILL, CLOUDLESS SCENE. Weather darkens everything and motion moves the traffic;
        # neither is what is being measured, and both are noise this can simply switch off.
        page.evaluate("""() => { const a = window.__probe.api;
            a.setWet(0); a.setSnow(0); a.setSky(0.05); a.setSpd(0); }""")
        # ---- AND THE INSTRUMENTS ARE NOT THE ROAD -----------------------------
        # An element screenshot captures whatever the page draws OVER that element, so the first
        # version of this measured the countdown ticking and two dial needles swinging, and called
        # a noise floor of ten brightness levels the truth. The HUD is hidden; the mirror is drawn
        # on the canvas itself and cannot be, so its rows are dropped by number instead.
        page.evaluate("""() => {
            const s = document.createElement('style');
            s.textContent = '.toprow,.botrow,#pedals,#gauges,.speedo,.bars'
                          + '{visibility:hidden!important}';
            document.head.appendChild(s);
        }""")
        page.wait_for_timeout(500)

        canvas = page.query_selector('canvas')

        def frame(phase, beams):
            page.evaluate('([ph, on]) => { const a = window.__probe.api;'
                          '                a.setPhase(ph); a.setBeams(on);'
                          '                a.clearTraffic(); }',
                          [phase, beams])
            page.wait_for_timeout(140)
            return Image.open(io.BytesIO(canvas.screenshot())).convert('RGB')

        took = page.evaluate('() => window.__probe.api.setBeams(false)')
        res.check(took is False, 'the harness can actually turn the beam off',
                  'setBeams(false) returned %r' % took)
        page.evaluate('() => window.__probe.api.setBeams(true)')

        hz = int(page.evaluate('() => window.__probe.api.horizon()'))
        # the glass shows the road BEHIND, which moves on its own. Its rows are not the road.
        mirror_bot = page.evaluate("""() => {
            const cs = getComputedStyle(document.documentElement);
            const h = parseFloat(cs.getPropertyValue('--mirror-h')) || 44;
            const t = parseFloat(cs.getPropertyValue('--mirror-top')) || 6;
            return Math.ceil(t + h + 24);
        }""")

        def sample(phase):
            """Three beam-off frames for the noise, then one with the beam.

            THREE, BECAUSE THE NOISE IS ITSELF NOISY. With one off-pair, a row where the traffic
            happened to sit still between those two frames got a floor of nearly zero, and then
            read as lit the moment a car moved through it during the signal pair. The noise of a
            row is the WORST it was seen to move across two independent pairs.

            AND A BEAM IS A BAND, NOT A SPECKLE. A car crossing a row lifts that row and its
            neighbours for a dozen pixels of width; the beam lifts a long unbroken run of rows.
            Only runs survive, which is what separates the light from the traffic driving through
            it without needing to know where the traffic is.
            """
            # AND THE SCENE HAS TO COME TO REST FIRST. The ground tone, the cloud and the
            # sky all lerp toward the hour rather than snapping to it, so sampling straight
            # after a jump from midnight to midday measures the TRANSITION: the rows moved 20
            # brightness levels between two identical frames, which is eighty times the figure
            # the same scene settles to. It is held at the hour until it stops moving.
            page.evaluate('(ph) => { window.__probe.api.setPhase(ph);'
                          '            window.__probe.api.clearTraffic(); }', phase)
            prev = None
            for _ in range(24):
                page.wait_for_timeout(260)
                page.evaluate('() => window.__probe.api.clearTraffic()')
                here = frame(phase, False)
                if prev is not None:
                    moved = max(gain(rows_of(prev), rows_of(here))[mirror_bot:])
                    if moved < SETTLED:
                        break
                prev = here
            a = frame(phase, False)
            b = frame(phase, False)
            c = frame(phase, False)
            d = frame(phase, True)
            ra, rb, rc, rd = rows_of(a), rows_of(b), rows_of(c), rows_of(d)
            n1, n2 = gain(ra, rb), gain(rb, rc)
            noise = [max(x, y) for x, y in zip(n1, n2)]
            add = gain(rc, rd)
            over = [i for i in range(mirror_bot, len(add))
                    if add[i] > max(OVER_NOISE * noise[i], FLOOR)]
            lit = []
            run = []
            for i in over + [None]:
                if run and i is not None and i == run[-1] + 1:
                    run.append(i)
                    continue
                if len(run) >= MIN_RUN:
                    lit.extend(run)
                run = [] if i is None else [i]
            return c, d, noise, add, sorted(lit), rc, rd

        # THREE ROUNDS AT NIGHT TOO, AND ONLY THE ROWS LIT IN ALL OF THEM COUNT. Traffic
        # drives up the picture and lifts a long run of rows exactly as the beam does; it is
        # somewhere different every round, and the beam is in the same place every round. This
        # is the one mechanism that separates them, so it is used for every reading below.
        rounds, last = [], None
        for _ in range(3):
            last = sample(0.25)
            rounds.append(set(last[4]))
        off, on, noise, add, _, rc, rd = last
        lit = sorted(set.intersection(*rounds))
        H = off.size[1]
        print('      the horizon sits at row %d of %d, the glass ends at row %d'
              % (hz, H, mirror_bot))
        print('      at night the scene moves %.2f a row on its own at worst, and the beam '
              'lights %d row(s)' % (max(noise[mirror_bot:]), len(lit)))

        if args.shots:
            out = ROOT / '_beam'
            out.mkdir(exist_ok=True)
            off.save(out / 'night-off.png')
            on.save(out / 'night-on.png')
            print('      wrote %s' % out)

        # ---- 1. THE LIGHT REACHES THE TARMAC BESIDE THE CAR --------------------
        # The old beam started 485 world units ahead of the car, which projected ABOVE its own
        # roofline, so the road at the bumper stayed dark. This asks the bottom sixth.
        low = [i for i in lit if i >= H * 0.84]
        res.check(bool(low), 'the light reaches the road beside the car',
                  'no row below %d lifts clear of its own noise' % int(H * 0.84))
        if low:
            print('      the bottom sixth is lit on %d row(s), brightest gain %.2f'
                  % (len(low), max(add[i] for i in low)))

        # ---- 2. AND IT STAYS ON THE GROUND ------------------------------------
        sky = [i for i in lit if i < hz - 2]
        res.check(not sky, 'and nothing above the horizon changes',
                  '%d row(s) above the horizon lit, highest gain %.2f'
                  % (len(sky), max((add[i] for i in sky), default=0)))

        # ---- 3. IT DIES OUT ON THE ROAD RATHER THAN STOPPING AT A LINE --------
        # The throw ran to 9000 units and simply ended, which is the hard top edge the owner saw.
        res.check(bool(lit), 'the beam lights something at all', 'no lit rows')
        if lit:
            top = min(lit)
            res.check(top > hz + (H - hz) * 0.12,
                      'the throw ends on the road, not at the horizon',
                      'the highest lit row is %d, the horizon is %d' % (top, hz))
            # the edge is read from the LIT rows in that window, not from whatever
            # else happened to be painted there
            edge = max(add[i] for i in lit if top <= i < top + 6)
            peak = max(add[mirror_bot:])
            res.check(edge < peak * 0.30,
                      'and it fades out rather than cutting off',
                      'the last lit rows still carry %.2f of a peak of %.2f' % (edge, peak))
            print('      the throw reaches up to row %d, peak gain %.2f, far edge %.2f'
                  % (top, peak, edge))

        # ---- WHAT THIS CANNOT CHECK ------------------------------------------
        # THE SHAPE OF THE THROW IS NOT MEASURED, and that is the half of the owner's report
        # this harness cannot answer. A cone that widens linearly in world units projects to a
        # constant width on screen, which is what made the old beam read as two parallel slabs,
        # and the obvious check is to compare the throw's width near and far. It does not work.
        # The light dims faster than it narrows, so by the row where a width comparison would
        # mean anything the beam is too faint to find an edge in; and the rows where it is
        # bright enough are the rows the player's own bodywork is painted over. Three metrics
        # were tried and two of them reported the NEW beam as less convergent than the old one.
        # The shape is judged from the captures and by the owner on the device.

        # ---- 4. AND IT IS OFF IN DAYLIGHT, BECAUSE OF THE CLOCK ---------------
        # Not "the frame looks bright". The question is whether ENABLING the beam at midday
        # changes anything at all: if it does not, the clock is what is holding it off.
        # AND IT ASKS THREE TIMES. A car driving up the picture lifts a long unbroken run of
        # rows exactly as a beam does, so a single pair called midday lit on about half its
        # runs with nothing wrong. Traffic is somewhere different on every pair; a beam would
        # be in the same rows every time. What has to be empty is the INTERSECTION.
        rounds = []
        for _ in range(3):
            _, _, d_noise, d_add, d_lit, _, _ = sample(0.75)
            rounds.append(set(d_lit))
            print('      at midday the scene moves %.2f a row on its own and %d row(s) lift'
                  % (max(d_noise[mirror_bot:]), len(d_lit)))
        always = set.intersection(*rounds)
        res.check(not always,
                  'turning the beam on at midday changes nothing - the clock holds it off',
                  '%d row(s) lit in all three rounds' % len(always))

        errs = page.evaluate('() => window.__probe.errors')
        res.check(not errs, 'no page errors', str(errs))
        browser.close()
    httpd.shutdown()
    print(('\n%d check(s) failed' % len(res.fails)) if res.fails else '\nall checks passed')
    return 1 if res.fails else 0


if __name__ == '__main__':
    sys.exit(main())
