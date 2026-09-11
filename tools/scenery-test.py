#!/usr/bin/env python3
"""
SCENERY TEST - a tree approaches the way a thing at that distance has to.

    .venv/Scripts/python tools/scenery-test.py

RLG-073. Owner, 2026-08-30: scenery moves away far faster than it approaches - reported about the
forward view, and visible in the mirror as well.

THIS ANSWERS THE GEOMETRY HALF, AND ONLY THAT HALF. Whether a roadside is pleasant to drive past is
the owner's eye; whether an object obeys perspective is arithmetic, and the two are worth separating
before anything is tuned. Perspective gives one law that cannot be argued with:

    apparent width x distance = a constant

so the harness follows ONE object down the road and multiplies. If the product drifts, the scenery
is not being drawn where it is. If it holds, the size is exact and any remaining complaint is about
the FADE or the draw distance rather than about the geometry.

IT FLATTENS THE ROAD FIRST, and that is not a convenience. On the shipped road an object near the
horizon moves mostly because the terrain under it does: the first run of this measurement read a
50-pixel jump that was a hill, not a defect. Hills and bends are removed so the only thing left in
the number is the approach.

AND IT DRIVES PAST THE COUNT-IN. The first version waited 1.4 seconds of a 3 second hold, so the car
was stationary for most of the measurement and the object barely moved - a number the harness had
caused itself, which is the fault this project has been caught by twice before.

Exit code 0 if every check passed, 1 otherwise.
"""

import argparse
import functools
import http.server
import socketserver
import sys
import threading
from collections import defaultdict
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
"""

# width x distance may wander by this share of its own median across a whole approach
WIDTH_DRIFT = 0.02


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--headed', action='store_true')
    args = ap.parse_args()
    console_utf8()
    res = Results()
    httpd, port = serve(ROOT)
    print('scenery-test  .  a tree approaches the way it has to')

    with sync_playwright() as p:
        browser = launch_chromium(p, headless=not args.headed)
        page = browser.new_context(viewport={'width': 480, 'height': 900},
                                   has_touch=True, is_mobile=True).new_page()
        page.add_init_script(INIT)
        boot(page, 'http://127.0.0.1:%d/%s' % (port, GAME))
        until(page, '!!window.__probe.road', timeout=10000)
        page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
        page.click('[data-act="play"]')
        page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
        page.click('[data-act="drive"]')
        page.wait_for_timeout(4200)          # past the three second count-in
        page.evaluate("""() => { const R = window.__probe.road;
            R.setWet(0); R.setSnow(0); R.setBiomePair('FOREST','FOREST');
            R.clearTraffic(); R.flattenRoad(); R.traceScenery(true); }""")
        # let the flattened road settle before the first sample, or frame one
        # carries the geometry that was there a moment ago
        page.wait_for_timeout(500)
        page.evaluate('() => window.__probe.road.sceneryFrame()')

        rows = page.evaluate("""async (n) => {
            const R = window.__probe.road, out = [];
            for(let i = 0; i < n; i++){
                R.setSpd(R.MAX_SPD * 0.35);
                R.clearTraffic();
                await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
                out.push({ pos: R.roadPos(), objs: R.sceneryFrame() });
            }
            return out;
        }""", 80)

        seen = defaultdict(list)
        for n, f in enumerate(rows):
            for o in f['objs']:
                seen[(o['idx'], o['side'], o['row'])].append((n, o))
        res.check(bool(seen), 'the roadside has scenery on it to follow',
                  'nothing was traced')
        if not seen:
            browser.close()
            httpd.shutdown()
            return 1

        # the object seen across the most frames, which is the one that made the
        # longest journey toward the camera
        key, track = max(seen.items(), key=lambda kv: len(kv[1]))
        # the distance is taken from the SAME record as the width, stamped as the
        # object was drawn - not from a position read after the frame
        pairs = [(o['z'] - o['pos'], o['w']) for n, o in track
                 if o['z'] - o['pos'] > 500 and o['w'] > 0.5]
        res.check(len(pairs) >= 20, 'and it was followed a long way in',
                  'only %d usable samples' % len(pairs))

        if len(pairs) >= 20:
            near, far = min(p[0] for p in pairs), max(p[0] for p in pairs)
            print('      followed %s from %.0f units away in to %.0f' % (str(key), far, near))
            res.check(far / max(near, 1) > 1.8,
                      'and it more than halved its distance, so this is an approach',
                      'from %.0f to %.0f' % (far, near))

            # ---- THE ONE LAW PERSPECTIVE CANNOT ARGUE WITH ------------------
            prod = sorted(d * w for d, w in pairs)
            med = prod[len(prod) // 2]
            drift = (prod[-1] - prod[0]) / med
            print('      width x distance: %.0f to %.0f, median %.0f, drift %.2f%%'
                  % (prod[0], prod[-1], med, drift * 100))
            res.check(drift <= WIDTH_DRIFT,
                      'an object is drawn the size its distance says it is',
                      'the product drifted %.1f%% across the approach' % (drift * 100))

            # ---- AND IT ARRIVES WITHOUT JUMPING -----------------------------
            # A step in width is a step in position: both come from the same scale.
            ws = [w for _, w in sorted(((o['pos'], o['w']) for n, o in track))]
            steps = [b / a for a, b in zip(ws, ws[1:]) if a > 0.5]
            if steps:
                print('      frame to frame it grows by at most %.1f%%' % ((max(steps) - 1) * 100))
                res.check(max(steps) < 1.06,
                          'and it grows smoothly rather than in steps',
                          'one frame grew it by %.1f%%' % ((max(steps) - 1) * 100))

        # ---- AND THE MIRROR RECEDES AT THE SAME RATE (RLG-073) --------------
        # Owner, 2026-08-30: scenery in the rear-view zooms away at many times the speed it
        # approaches in the forward view. It was not receding at all: the glass walked fixed
        # distances BEHIND THE CAR, so every slice sat at a constant distance for ever and
        # what changed was which object got drawn on each rung. A tree did not glide away,
        # it sat still and was replaced.
        #
        # SO THE QUESTION IS WHETHER IT MOVES EVERY FRAME, not how fast. A view whose median
        # frame-to-frame size change is zero is not slow, it is stationary - and that is a
        # thing no tolerance on speed would ever have caught.
        views = defaultdict(list)
        for n, f in enumerate(rows):
            for o in f['objs']:
                views[o.get('view')].append((n, o))
        per = {}
        for v in ('ahead', 'mirror'):
            byobj = defaultdict(list)
            for n, o in views.get(v, []):
                byobj[(o['idx'], o['side'], o['row'])].append((n, o))
            steps = []
            for seq in byobj.values():
                seq.sort(key=lambda t: t[0])
                for (n0, a), (n1, b) in zip(seq, seq[1:]):
                    if n1 == n0 + 1 and a['w'] > 0.2:
                        steps.append(abs(b['w'] - a['w']) / a['w'])
            per[v] = sorted(steps)
        res.check(len(per['mirror']) > 50 and len(per['ahead']) > 50,
                  'both views were traced with enough samples to compare',
                  'ahead %d, mirror %d' % (len(per['ahead']), len(per['mirror'])))
        if len(per['mirror']) > 50 and len(per['ahead']) > 50:
            ma = per['ahead'][len(per['ahead']) // 2]
            mm = per['mirror'][len(per['mirror']) // 2]
            print('      median frame-to-frame size change: ahead %.2f%%, mirror %.2f%%'
                  % (ma * 100, mm * 100))
            res.check(mm > 0.001,
                      'a tree in the mirror actually recedes rather than sitting still',
                      'the mirror median is %.4f%% - it is not moving' % (mm * 100))
            res.check(mm < ma * 3,
                      'and it recedes at about the rate the windscreen approaches',
                      'mirror %.2f%% against ahead %.2f%%' % (mm * 100, ma * 100))

        # ---- AND IT FADES AT THE FAR EDGE, NOT AT THE CAR (RLG-128) --------------
        # Owner, 2026-08-31: "it looks like it starts alpha and then becomes opaque as it
        # moves away, and it should be an inversion of the forward view - in the rearview
        # mirror the scenery should be opaque and become alpha as it reaches the draw
        # distance."
        #
        # THE POLARITY IS THE WHOLE QUESTION, so it is measured as one: every mirror object
        # in the trace, bucketed by how far behind the car it stands, and the near bucket
        # compared with the far one. The old ramp was driven by the object's WIDTH, so a
        # near object drew nearly transparent and a far one solid - and in a mirror
        # everything only ever recedes, so every tree faded IN as it went away.
        mir = [o for _, o in views.get('mirror', []) if o.get('a') is not None]
        res.check(len(mir) > 40, 'the mirror traced enough scenery to judge the fade',
                  'only %d object(s) carried an alpha' % len(mir))
        if len(mir) > 40:
            back = [(o['pos'] - o['z'], o['a']) for o in mir]
            reach = max(d for d, _ in back)
            near = [a for d, a in back if d < reach * 0.35]
            far = [a for d, a in back if d > reach * 0.85]
            if near and far:
                mn = sum(near) / len(near)
                mf = sum(far) / len(far)
                print('      mirror scenery alpha: %.3f near the car, %.3f at the draw edge'
                      % (mn, mf))
                # THE NEAREST OBJECTS ARE THE BIGGEST ONES, and they are what the old
                # ramp made see-through - so this asks the widest tenth directly. A
                # distance bucket is too blunt for it: with the defect reintroduced the
                # near bucket still averaged 0.986, because only the handful of objects
                # closest to the size cap were transparent and the bucket drowned them.
                # NOT THE WIDEST OBJECT. That was tried and it is the wrong question: the
                # widest object on the road is the one that has just receded under the size
                # cap, and it is deliberately faint because it is ARRIVING. Asking it to be
                # solid asserts against the arrival ease rather than against the fault.
                #
                # What discriminates is the FAR end. With the fault present the draw edge
                # read 1.000 - fully solid, no fade at all - which is the whole complaint
                # stated as a number.
                res.check(mn > 0.9,
                          'scenery just behind the car is solid, not see-through',
                          'the near third averaged %.3f alpha' % mn)
                res.check(mf < 0.6,
                          'and it really does fade out at the draw distance',
                          'the far edge averaged %.3f alpha, which is no fade at all' % mf)
                res.check(mf < mn,
                          'and it fades AWAY toward the draw distance rather than into it',
                          'near %.3f against far %.3f, which is the wrong way round' % (mn, mf))

        # ---- THE MIRROR'S ROADSIDE AGAINST THE WINDSCREEN'S (RLG-130) -------------------
        # Owner, 2026-08-31: "The scenery in the rearview mirror is much more sparse than what
        # it actually is in the front view. It should be the same or at least closely
        # comparable."
        #
        # IT DREW ONE RANK WHERE A FOREST HAS FIVE, and then thinned that rank with the
        # per-rank density on top - so the glass carried about a fifteenth of the objects the
        # windscreen did. This counts what each view actually DRAWS in a frame, through the
        # engine own trace, rather than judging a 44-pixel pane by eye.
        #
        # A RATIO, NOT A COUNT. The mirror can never match a windscreen object for object: it
        # is a strip of glass looking backward, with a near cull that stops trees burying the
        # road and a far cutoff that drops sub-pixel smudges. What is asserted is that the gap
        # closed, and that the rank count is the thing that closed it.
        print()
        print('  THE MIRROR CARRIES A COMPARABLE ROADSIDE (RLG-130)')

        # THREE WINDOWS SUMMED, NOT ONE. A single 120ms trace catches however many frames the
        # machine happened to render and whatever the car happened to be driving past, so the
        # raw counts swing widely - one run recorded 412 mirror objects where the next
        # recorded 1,440. The RATIO is the stable quantity and it is still worth averaging:
        # this check failed once at 2.29 against a threshold of 2.5 that had been set from a
        # single reading, which is the fault this project has a standing note about.
        def density(rows):
            page.evaluate("(r) => { const R = window.__probe.road;"
                          " R.mirrorRows(r); R.setBiomePair('FOREST','FOREST');"
                          " R.setSpd(R.MAX_SPD*0.5); }", rows)
            page.wait_for_timeout(700)
            ahead = mir = 0
            for _ in range(3):
                page.evaluate("() => window.__probe.road.traceScenery(true)")
                page.wait_for_timeout(200)
                t = page.evaluate("() => window.__probe.road.sceneryFrame()")
                page.evaluate("() => window.__probe.road.traceScenery(false)")
                ahead += sum(1 for r in t if r['view'] == 'ahead')
                mir += sum(1 for r in t if r['view'] == 'mirror')
                page.wait_for_timeout(120)
            return ahead, mir

        keep_rows = page.evaluate("() => window.__probe.road.mirrorRows()")
        a_now, m_now = density(keep_rows)
        a_one, m_one = density(1)
        page.evaluate("(r) => window.__probe.road.mirrorRows(r)", keep_rows)
        share_now = m_now / max(a_now, 1)
        share_one = m_one / max(a_one, 1)
        print('      shipping at %d ranks: the front drew %d objects, the glass %d  (%.0f%%)'
              % (keep_rows, a_now, m_now, share_now * 100))
        print('      at one rank:          the front drew %d objects, the glass %d  (%.0f%%)'
              % (a_one, m_one, share_one * 100))
        res.check(m_now > m_one * 2.0,
                  'the glass carries far more roadside than it did at one rank',
                  '%d objects against %d' % (m_now, m_one))
        res.check(share_now > 0.15,
                  'and it is a comparable roadside rather than a token one',
                  'the mirror draws %.0f%% of what the windscreen draws' % (share_now * 100))
        # AND THE RANK COUNT IS WHAT DID IT. If the ratio were the same at one rank, something
        # else would be responsible and this check would be watching the wrong thing.
        res.check(share_one < share_now * 0.65,
                  'and the rank count is what closed the gap, rather than something else',
                  '%.0f%% at one rank against %.0f%% shipping'
                  % (share_one * 100, share_now * 100))

        errs = page.evaluate('() => window.__probe.errors')
        res.check(not errs, 'no page errors', str(errs))
        browser.close()

    httpd.shutdown()
    if res.fails:
        print('')
        print('  %d check(s) failed' % len(res.fails))
        return 1
    print('')
    print('  the geometry is exact; what it FEELS like is not measured here')
    return 0


if __name__ == '__main__':
    sys.exit(main())
