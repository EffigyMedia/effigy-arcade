#!/usr/bin/env python3
"""PLACE SHAPE TEST - a place's own bend is in force from its first unit.

    .venv/Scripts/python tools/place-shape-test.py

RLG-150, found while measuring RLG-145 item 5. The owner reported that the bridge and the
tunnel both turn too hard, and those two hold the lowest `bend` values on the board. The
numbers were not the ones in force.

WHAT WAS WRONG. `pushCurve` scales a segment by the place it will be in, AT GENERATION - which
is right, because a bend that changed magnitude as you approached it would be the road moving
under you. But the road is generated to `pos + GEN_AHEAD` while a place used to be chosen at
`biomeEdge = here + DRAW`, which is 30,000 ahead. So roughly the first 70,000 units of every
place were made under the PREVIOUS place's factor and nothing went back for them.

WHAT THIS ASKS. Not "is the plan set", which would be a check agreeing with the code it
checks - it drives a passage and measures how bent the road actually is, in eighths, against
ordinary road driven the same way.

IT MUST LET THE TIMER PLACE THE PASSAGE. `startBiomeChange` and `setBiomePair` both place at
the horizon, because a harness cannot drive 70,000 units before it can begin - so they cancel
the plan and DO NOT reproduce the corrected order. Using either here would measure the old
behaviour and report it as a pass. The countdown is driven to zero instead, which runs the real
path, and the roll is repeated until it plans a passage.

WHY IT CANNOT SAMPLE FROM A STANDSTILL. `curvatureAt` reads the segment list, which is trimmed
behind the camera and generated only so far ahead, so anything outside that window answers 0
and a straight cannot be told from a road that does not exist. Two earlier attempts at this
measurement were wrong for exactly that reason. This drives, and samples at a fixed short
look-ahead that is always inside the window.

MEASURED BEFORE THE FIX, so the threshold sits between two known populations. A bridge wants
0.23 as bent as farmland throughout and read 1.29, 1.39, 0.28, 0.27, 0.11, 0.30, 0.09, 0.24 by
eighths; a tunnel wants 0.29 and read 2.24, 0.72, 0.82, 0.55, 0.43, 0.15, 0.35, 0.36. The
entries were six to eight times too bent.

WHAT IT CANNOT DO. One drive is one roll of the generator, and a passage may honestly contain
no corner at all - so this asserts a CEILING and never a floor. It cannot say the road feels
right; the owner judges that on the device.

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

# far enough ahead to be a real reading, near enough to always be inside the
# generated window - the road is made to 100,000 and drawn to 30,000
LOOK = 5000
EIGHTHS = 8


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


def tick(page, frac=1.0):
    page.evaluate("([f]) => { const R = window.__probe.road;"
                  " R.clearTraffic(); R.setSpd(R.MAX_SPD*f); }", [frac])
    page.wait_for_timeout(40)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--headed', action='store_true')
    ap.add_argument('--places', default='BRIDGE,TUNNEL')
    args = ap.parse_args()
    console_utf8()
    res = Results()
    httpd, port = serve(ROOT)
    print('place-shape-test  .  a place bends by its own number from its first unit')
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

        # ------------------------------------------------------- the plan is past the road
        print()
        print('  THE PLANNED EDGE IS PAST EVERY SEGMENT THAT EXISTS')
        page.evaluate("() => window.__probe.road.restart()")
        page.wait_for_timeout(300)
        for _ in range(40):
            st = page.evaluate("() => window.__probe.road.startLine()")
            if st['left'] <= 0 and st['go'] <= 0:
                break
            page.wait_for_timeout(90)
        for _ in range(10):
            tick(page)
        page.evaluate("() => window.__probe.road.biomeCountdown(0)")
        tick(page)
        pl = page.evaluate("() => window.__probe.road.roadPlan()")
        print('      planned %s, its edge at %s, and the road is made to %d'
              % (pl['key'], pl['edgeZ'], pl['madeTo']))
        res.check(pl['key'] is not None, 'the timer plans a place instead of placing one',
                  'no plan after the countdown ran out')
        res.check(pl['edgeZ'] is not None and pl['edgeZ'] >= pl['madeTo'],
                  'and its edge is past everything already generated, so nothing inside it '
                  'was made under the place behind',
                  'edge %s against road made to %s' % (pl['edgeZ'], pl['madeTo']))
        sweep = page.evaluate("() => window.__probe.road.biomeSweep()")
        res.check(sweep['to'] != pl['key'] or sweep['edge'] >= pl['edge'],
                  'and the picture has not been told yet, so the colour still enters at '
                  'the horizon',
                  'the visible pair is already %s -> %s' % (sweep['from'], sweep['to']))

        # ------------------------------------------------------- and the road obeys it
        tbl = page.evaluate("() => { const R = window.__probe.road; const o = {};"
                            " for(const k of R.BIOME_KEYS()) o[k] = R.roadShape(k); return o; }")
        for place in [x.strip().upper() for x in args.places.split(',') if x.strip()]:
            want = tbl[place]['bend'] / tbl['FARMLAND']['bend']
            print()
            print('  %s - bend %.2f against farmland %.2f, so %.2f as bent ALL THE WAY THROUGH'
                  % (place, tbl[place]['bend'], tbl['FARMLAND']['bend'], want))
            r = drive_one(page, place)
            if not r:
                res.check(False, 'a %s was reached and driven' % place,
                          'the timer never planned one in the tries allowed')
                continue
            bm = sum(r['base']) / max(1, len(r['base']))
            print('      ordinary road driven the same way: mean %.4f over %d reads'
                  % (bm, len(r['base'])))
            print('      span %d, %d reads inside it' % (r['len'], len(r['rows'])))
            bk = bucket(r['rows'], r['len'])
            ratios = [((sum(b) / len(b)) / bm if b and bm else 0) for b in bk]
            print('      eighths, as a multiple of the ordinary road:')
            print('        ' + ' '.join('%5.2f' % x for x in ratios))
            res.check(all(len(b) > 0 for b in bk),
                      'every eighth of the passage was actually sampled',
                      'reads per eighth ' + ' '.join(str(len(b)) for b in bk))
            # A CEILING, NEVER A FLOOR. One drive is one roll and a passage may honestly hold
            # no corner, so a low reading is not a fault. The ceiling is generous against the
            # numbers this replaced: the entry read 1.29 and 2.24 before, and a passage asking
            # for 0.23 is allowed three times that here.
            cap = max(0.75, want * 3)
            worst = max(range(len(ratios)), key=lambda i: ratios[i])
            res.check(max(ratios) <= cap,
                      'no part of the passage is bent like the place before it',
                      'eighth %d reads %.2f against a ceiling of %.2f (it wants %.2f)'
                      % (worst + 1, ratios[worst], cap, want))
            # AND THE ENTRY IS THE POINT. The fault was ALL in the first quarter, so it gets
            # its own claim rather than being averaged away by six good eighths.
            entry = max(ratios[0], ratios[1])
            res.check(entry <= cap,
                      'and its ENTRY is not, which is where the whole fault used to be',
                      'the first two eighths read %.2f and %.2f against a ceiling of %.2f'
                      % (ratios[0], ratios[1], cap))

        errs = page.evaluate("() => window.__probe.errors")
        if errs:
            print()
            res.check(False, 'the page threw nothing', '; '.join(errs[:3]))
        browser.close()
    httpd.shutdown()
    print()
    if res.fails:
        print('  FAILED: ' + '; '.join(res.fails))
        return 1
    print('  all checks passed')
    return 0


def bucket(rows, ln, n=EIGHTHS):
    out = [[] for _ in range(n)]
    for into, k in rows:
        out[min(n - 1, int(into / ln * n))].append(k)
    return out


def drive_one(page, place, tries=60):
    page.evaluate("() => window.__probe.road.restart()")
    page.wait_for_timeout(300)
    for _ in range(40):
        st = page.evaluate("() => window.__probe.road.startLine()")
        if st['left'] <= 0 and st['go'] <= 0:
            break
        page.wait_for_timeout(90)
    # the ordinary road, driven the same way, as the baseline
    base = []
    for _ in range(200):
        tick(page)
        base.append(page.evaluate("([d]) => Math.abs(window.__probe.road.curvatureAt("
                                  "window.__probe.road.pos + d))", [LOOK]))
    # ROLL THE TIMER, NOT THE SETTER. Driving the countdown to zero runs the real
    # placement path; the debug setters cancel the plan and would measure the old order.
    # ---- STAND THE RUN WHERE THE PLACE IS REACHABLE (RLG-142) -----------------------
    # The temperature step means a place may only be followed by one within ten degrees, and
    # forcing the countdown re-plans from the CURRENT instance every time - so rolling over
    # and over from wherever the run opened can never reach a passage that is out of range.
    # A TUNNEL sits at 0.35 to 0.55 and a BRIDGE at 0.30 to 0.80, so 0.45 reaches both.
    page.evaluate("() => window.__probe.road.setInstanceTemp(0.45)")
    got = False
    for _ in range(tries):
        page.evaluate("() => window.__probe.road.biomeCountdown(0)")
        tick(page)
        if page.evaluate("() => window.__probe.road.roadPlan()")['key'] == place:
            got = True
            break
    if not got:
        return None
    ev = None
    for _ in range(900):
        tick(page)
        e = page.evaluate("() => window.__probe.road.eventNow()")
        if e['on'] and e['len'] > 0:
            ev = e
            break
    if not ev:
        return None
    z0, ln = ev['z0'], ev['len']
    rows = []
    for _ in range(2600):
        tick(page)
        d = page.evaluate("([d]) => { const R = window.__probe.road;"
                          " return [R.pos, Math.abs(R.curvatureAt(R.pos + d))]; }", [LOOK])
        into = d[0] + LOOK - z0
        if into < 0:
            continue
        if into > ln:
            break
        rows.append((into, d[1]))
    if len(rows) < EIGHTHS * 2:
        return None
    return {'z0': z0, 'len': ln, 'rows': rows, 'base': base}


sys.exit(main())
