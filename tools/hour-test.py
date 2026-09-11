#!/usr/bin/env python3
"""
HOUR TEST - the light changes by degrees, and nothing in the world jumps.

    .venv/Scripts/python tools/hour-test.py

RLG-091. Owner, 2026-08-30: going from night to day, and day to night, is a gigantic snap. It should
lerp.

IT WALKS THE WHOLE DAY AND MEASURES THE BIGGEST SINGLE STEP. `nightFall` and `goldenHour` have
always returned smooth ramps and the SKY read them properly; three places took the same smooth
numbers and thresholded them, so the ground flipped between three fixed looks in one frame while the
sky above it crossfaded. A check that sampled four times a day would have seen three plausible
colours and no snap at all - the fault only exists between the samples.

SO THE STEP IS COMPARED WITH THE SPREAD, not with a number picked by hand. Across a whole day the
ground legitimately travels a long way, and what makes a snap a snap is one step carrying a large
share of that journey. A threshold in brightness levels would have to be re-tuned the day anybody
changed a biome's palette; a share of the day's own range does not.

AND IT ASKS THE GROUND, THE SEA AND THE MIRROR, because all three read the same two fractions and
all three had the same three branches in them.

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

STEPS = 360          # one sample per degree of the day
# a single step may carry at most this share of the whole day's travel
WORST_SHARE = 0.06


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


def parse(c):
    """'rgb(1,2,3)' or '#aabbcc' to a triple."""
    if c.startswith('#'):
        n = int(c[1:], 16)
        return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
    q = c[c.index('(') + 1:].rstrip(')').split(',')
    return [float(x) for x in q[:3]]


def dist(a, b):
    return sum(abs(x - y) for x, y in zip(a, b))


def worst_step(series):
    """The biggest one-sample jump, and where it happened."""
    worst, at = 0.0, 0
    for i in range(1, len(series)):
        d = dist(series[i - 1][1], series[i][1])
        if d > worst:
            worst, at = d, series[i][0]
    return worst, at


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--headed', action='store_true')
    args = ap.parse_args()
    console_utf8()
    res = Results()
    httpd, port = serve(ROOT)
    print('hour-test  .  the light changes by degrees')

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
        page.wait_for_timeout(1400)
        # a dry, settled, unchanging place: the hour is the only thing moving
        page.evaluate("""() => { const R = window.__probe.road;
            R.setWet(0); R.setSnow(0); R.setSky(0.05); R.setSpd(0);
            R.setBiomePair('FOREST', 'FOREST'); R.clearTraffic(); }""")
        page.wait_for_timeout(400)

        # ---- WALK THE WHOLE DAY, ASKING THE ENGINE FOR ITS OWN COLOURS -------
        # setPhase does not repaint on its own, so the tones are asked for directly at
        # each hour rather than read off a screenshot. That also keeps the measurement
        # free of the sky, the road markings and everything else in a frame.
        rows = page.evaluate("""(steps) => {
            const R = window.__probe.road, out = [];
            for(let i = 0; i <= steps; i++){
                const ph = i / steps;
                R.setPhase(ph);
                out.push({ p: ph,
                           ground: R.groundToneAt(0, false),
                           verge:  R.groundToneAt(0, true),
                           night:  R.nightAmount ? R.nightAmount() : null });
            }
            return out;
        }""", STEPS)
        res.check(len(rows) == STEPS + 1, 'the day was walked end to end',
                  '%d samples' % len(rows))

        for name in ('ground', 'verge'):
            series = [(r['p'], parse(r[name])) for r in rows]
            span = max(dist(a[1], b[1]) for a in series for b in series[::37])
            worst, at = worst_step(series)
            share = worst / span if span else 0
            print('      %-6s travels %.0f across the day, worst single step %.0f '
                  '(%.1f%%) at phase %.3f' % (name, span, worst, share * 100, at))
            res.check(share <= WORST_SHARE,
                      'the %s changes by degrees, with no one frame carrying the change'
                      % name,
                      'one step carried %.1f%% of the day at phase %.3f' % (share * 100, at))

        errs = page.evaluate('() => window.__probe.errors')
        res.check(not errs, 'no page errors', str(errs))
        browser.close()

    httpd.shutdown()
    if res.fails:
        print('')
        print('  %d check(s) failed' % len(res.fails))
        return 1
    print('')
    print('  all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
