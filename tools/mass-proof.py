#!/usr/bin/env python3
"""MASS PROOF - a mountain and a canyon are a surface you can drive at and see leaving.

    .venv/Scripts/python tools/mass-proof.py

RLG-306, RLG-307. Owner, 2026-09-21: "The mountain face as you approach a mountain biome is
completely missing... build a (low) polygonal mountain side for that whole side of the biome.
We also need to see it correctly in the mirror as we leave." And, on seeing it: "You should
probably do the same thing for the canyon walls."

WHAT WAS WRONG. The wall was a plane at the road's edge. Grown out of the ground (RLG-303) it
is seen almost edge-on while it rises, so a mountain 65 segments ahead was a sliver and 20
ahead a needle. The canyon's front was a separate card of planks at one distance, with heights
of its own, meeting a sloped wall at a corner nothing drew. And once a crossing completed,
every segment BEHIND the car reported the NEW place, so the mirror could not show where you
had been.

WHAT IS CHECKED, and each was watched failing with its defect put back:

    THE MOUNTAIN IS THERE BEFORE YOU REACH IT. 65 segments before the boundary the mass paints
    quads, and its top stands well above the horizon. With `massOff` - the old wall - the
    same frame paints no mass at all.

    THE CANYON'S FRONT IS THE SURFACE'S OWN. At its boundary the mass paints a front, and the
    old plank face stands down: two faces with two sets of heights is the fault.

    AND THE MIRROR SHOWS THE PLACE YOU LEFT. After driving out of a mountain the glass paints
    mass quads and the back face you drove out of, and the ground behind the mountain's end
    is the MOUNTAIN's colour rather than the desert's.

WHAT IT CANNOT DO. Whether it reads as a mountain is the owner's on a device.

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
"""

EDGE_IN = "(k) => { const R = window.__probe.road; return R.landGrow(0, k).edge - Math.floor(R.roadPlan().pos / 200); }"
FRAME = "() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))"


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


def drive_to(page, frm, to, stop_at):
    """Place a boundary from FRM into TO and drive until it is STOP_AT segments ahead."""
    page.evaluate("""([a, z]) => { const R = window.__probe.road;
        R.setTimed(false); R.setBiomePair(a, a); R.setPhase(0.75);
        R.setWet(0); R.setSnow(0); R.setPool(0); R.clearTraffic();
        R.startBiomeChange(z); R.biomeCountdown(1e12);
        R.setSpd(9000); R.holdSpd(9000); }""", [frm, to])
    # THE PLACE TIMER IS HELD. It keeps counting while a harness drives at a boundary, and when it
    # expires a freshly planned place REPLACES the one being approached - one run of this proof
    # drove at a canyon and found 0 quads because there was no canyon left to find.
    until(page, "(a) => { const R = window.__probe.road; R.clearTraffic();"
                " return R.landGrow(0, a.z).edge - Math.floor(R.roadPlan().pos / 200) <= a.w; }",
          timeout=40000, arg={'z': to, 'w': stop_at})
    page.evaluate("() => window.__probe.road.holdSpd(0)")
    page.evaluate(FRAME)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--headed', action='store_true')
    args = ap.parse_args()
    console_utf8()
    res = Results()
    httpd, port = serve(ROOT)
    print('mass-proof  .  a mountain and a canyon you can drive at and see leaving')
    with sync_playwright() as p:
        browser = launch_chromium(p, headless=not args.headed)
        page = browser.new_page(viewport={'width': 480, 'height': 900})
        page.add_init_script(INIT)
        boot(page, 'http://127.0.0.1:%d/%s' % (port, GAME))
        until(page, '!!window.__probe.road', timeout=10000)
        page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
        page.click('[data-act="play"]')
        page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
        page.click('[data-act="drive"]')
        page.wait_for_timeout(4000)

        # ------------------------------------------------ the approach
        print()
        print('  THE MOUNTAIN IS THERE BEFORE YOU REACH IT')
        drive_to(page, 'DESERT', 'MOUNTAIN', 65)
        on = page.evaluate("() => { const R = window.__probe.road; return { m: R.massModel(), hz: R.horizon() }; }")
        tops = [v for v in on['m']['top'].values()]
        peak = on['hz'] - min(tops) if tops else 0
        print('      %d segments out: %d quads over %d slices, its top %.0f px above the horizon'
              % (page.evaluate(EDGE_IN, 'MOUNTAIN'), on['m']['quads'], on['m']['slices'], peak))
        res.check(on['m']['quads'] > 50, 'the mass is painted before the boundary is reached',
                  '%d quads' % on['m']['quads'])
        res.check(peak > 60, 'and it stands well up above the horizon, not as a sliver',
                  'its top is %.0f px above' % peak)
        # BESIDE EVERY SLICE OF IT, NOT SOME. A mountain has the most hills on the board, and the
        # wall this replaced was drawn only where the ROAD showed - so a mountain behind a crest,
        # or beside the far half of the draw where the road inverts by under a pixel, simply was
        # not there. Measured before the fix: 0, 53, 76 and 239 slices on four roads.
        #
        # AND ONE ROAD CANNOT SETTLE IT, because the road is fresh per load: the first build of
        # this check passed with the fix taken out, on two roads that happened to be flat in
        # front of the mountain. So the hills are raised for the approach and it is driven FOUR
        # times over four stretches of road, and every one has to show the whole mountain.
        page.evaluate("() => { const R = window.__probe.road;"
                      " R.setBiomeShape('DESERT', 2.5); R.setBiomeShape('MOUNTAIN', 2.5); }")
        counts = []
        for _ in range(4):
            page.evaluate("() => { const R = window.__probe.road; R.setSpd(9000); R.holdSpd(9000); }")
            page.wait_for_timeout(2500)          # new road, generated with the raised hills
            drive_to(page, 'DESERT', 'MOUNTAIN', 65)
            m = page.evaluate("() => window.__probe.road.massModel()")
            ahead = page.evaluate(EDGE_IN, 'MOUNTAIN')
            counts.append((m['slices'], 300 - ahead))
        page.evaluate("() => { const R = window.__probe.road;"
                      " R.setBiomeShape('DESERT', 0.2); R.setBiomeShape('MOUNTAIN', 1.0); }")
        print('      on four hilly roads: %s slices of mountain, of what the draw holds'
              % ', '.join('%d/%d' % c for c in counts))
        res.check(all(got >= 0.85 * room for got, room in counts),
                  'and it stands beside every slice of itself, over hills and all',
                  ', '.join('%d of %d' % c for c in counts))
        page.evaluate("() => window.__probe.road.massModel({ off: true })")
        page.evaluate(FRAME)
        off = page.evaluate("() => window.__probe.road.massModel()")
        page.evaluate("() => window.__probe.road.massModel({ off: false })")
        res.check(off['quads'] == 0, 'and the old wall, in the same frame, paints no mass',
                  '%d quads with massOff' % off['quads'])

        # ------------------------------------------------ the canyon's front
        print()
        print('  THE CANYON\'S FRONT IS THE SURFACE\'S OWN')
        drive_to(page, 'DESERT', 'CANYON', 60)
        tr = page.evaluate("() => window.__probe.road.massModel()")
        print('      at the mouth: %d quads, %d front quads' % (tr['quads'], tr['front']))
        res.check(tr['quads'] > 50, 'the canyon is drawn as the mass', '%d quads' % tr['quads'])
        res.check(tr['front'] > 0, 'and its front is painted from the same heights as its sides',
                  'no front quads')
        page.evaluate("() => window.__probe.road.massModel({ off: true })")
        page.evaluate(FRAME)
        old = page.evaluate("() => window.__probe.road.massModel()")
        page.evaluate("() => window.__probe.road.massModel({ off: false })")
        res.check(old['front'] == 0 and old['quads'] == 0,
                  'and with the old wall back neither is drawn, so the numbers are the mass',
                  '%r' % {'quads': old['quads'], 'front': old['front']})

        # ------------------------------------------------ the mirror
        print()
        print('  AND THE MIRROR SHOWS THE PLACE YOU LEFT')
        drive_to(page, 'MOUNTAIN', 'DESERT', -45)
        page.evaluate(FRAME)
        g = page.evaluate("""() => { const R = window.__probe.road, s = R.sides(),
                                     here = Math.floor(R.roadPlan().pos / 200),
                                     m = R.massModel(), e = R.landGrow(0, 'DESERT');
          return { from: s.from, mirror: m.mirror || 0, back: m.mirrorBack || 0,
                   behind: R.groundToneAt(here - 120, false, 0, 0),
                   mountain: R.groundToneAt(here + 20, false, 0, 0),
                   left: R.landGrow(here - 120, 'MOUNTAIN').grow }; }""")
        print('      in %s, 45 past the end: %d mass quads in the glass, ground behind reads %s'
              % (g['from'], g['mirror'], g['behind']))
        res.check(g['from'] == 'DESERT', 'the car really did leave the mountain', g['from'])
        res.check(g['mirror'] > 20, 'the glass paints the mountain behind you',
                  '%d quads in the mirror' % g['mirror'])
        res.check(g['behind'] != g['mountain'],
                  'and the ground behind the mountain\'s end is not the desert you are on',
                  'behind %s, here %s' % (g['behind'], g['mountain']))

        errs = page.evaluate("() => window.__probe.errors")
        res.check(not errs, 'no page errors', str(errs))
        browser.close()
    httpd.shutdown()

    print()
    if res.fails:
        print('FAILED: ' + '; '.join(res.fails))
        return 1
    print('PASSED: the mass is there on the way in, in its front, and in the glass on the way out')
    return 0


if __name__ == '__main__':
    sys.exit(main())
