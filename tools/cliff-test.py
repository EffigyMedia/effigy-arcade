#!/usr/bin/env python3
"""CLIFF TEST - the mountain's cliff edge is broken rock, not a kerb.

    .venv/Scripts/python tools/cliff-test.py

RLG-284. Owner, 2026-09-16: "The cliff edge in the mountain biome should be jagged a
non-uniform."

TWO HALVES, AND THEY FAIL DIFFERENTLY.

  THE NUMBERS read `API.rimJag`, the rim's offset beyond the rail per segment. The rim must
  never come inside the rail, must not be one even value, must be NON-UNIFORM - some stretches
  deeply broken and some only rough - and must be the same when asked twice, because a rim that
  re-rolls moves under the player.

  THE PICTURE is differential, for the reason hazard-test gives: absolute positions on a
  converging road cannot be read. The same mountain is rendered with the jag set to zero - the
  straight rim this ruling replaced - and with the default, and the difference must be real
  pixels, on the drop side of the road, in the windscreen AND in the mirror. A renderer that
  ignored `rimJag` would produce two identical frames.

WHAT IT CANNOT SEE: whether the edge reads as rock at speed on a phone, and whether the bites
are too deep or too shallow. That is the owner call on a device.

Exit code 0 if every check passed, 1 otherwise.
"""

import functools
import http.server
import io
import socketserver
import statistics
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

# the same bar hazard-test measured between "nothing changed" and "something was drawn"
BARE = 120
# the glass is a small pane; measured 4-6 without the jag and 33-56 with it
MIRROR_BARE = 18


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def serve(root):
    handler = functools.partial(QuietHandler, directory=str(root))
    httpd = socketserver.TCPServer(('127.0.0.1', 0), handler)
    httpd.allow_reuse_address = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.socket.getsockname()[1]


def changed(a, b, band):
    """How many pixels differ between two frames in one view, and their mean x."""
    from PIL import Image
    ia = Image.open(io.BytesIO(a)).convert('RGB')
    ib = Image.open(io.BytesIO(b)).convert('RGB')
    w, h = ia.size
    pa, pb = ia.load(), ib.load()
    y0, y1 = ((int(h * 0.42), h) if band == 'road'
              else (int(h * 0.045), int(h * 0.125)))
    n = sx = 0
    for y in range(y0, y1, 2):
        for x in range(0, w, 2):
            ca, cb = pa[x, y], pb[x, y]
            if abs(ca[0]-cb[0]) + abs(ca[1]-cb[1]) + abs(ca[2]-cb[2]) > 24:
                n += 1
                sx += x
    return n, (sx / n if n else w / 2.0), w


STRAIGHT = {'amp': 0, 'bite': 0}


def main():
    console_utf8()
    fails = []

    def check(ok, label, detail=''):
        print('  %s  %s%s' % ('ok  ' if ok else 'FAIL', label,
                              '   ' + detail if detail else ''))
        if not ok:
            fails.append(label)

    httpd, port = serve(ROOT)
    print('cliff-test  .  the cliff edge is broken rock')
    print()
    with sync_playwright() as p:
        browser = launch_chromium(p, headless=True)
        page = browser.new_page(viewport={'width': 480, 'height': 900})
        page.add_init_script(INIT)
        boot(page, 'http://127.0.0.1:%d/%s' % (port, GAME))
        until(page, '!!window.__probe.road', timeout=15000)

        # ---- THE NUMBERS -------------------------------------------------------
        print('  THE RIM, SEGMENT BY SEGMENT')
        a = page.evaluate('() => window.__probe.road.rimJag(1000, 600)')
        b = page.evaluate('() => window.__probe.road.rimJag(1000, 600)')
        jag, tune = a['jag'], a['tune']
        run = int(tune['run'])
        runs = [max(jag[i:i + run]) for i in range(0, len(jag) - run + 1, run)]
        print('      tunables %s' % tune)
        print('      offset beyond the rail: min %.3f  max %.3f  mean %.3f  sd %.3f'
              % (min(jag), max(jag), statistics.mean(jag), statistics.pstdev(jag)))
        check(min(jag) >= 0, 'the rim never comes inside the rail', 'min %.4f' % min(jag))
        check(statistics.pstdev(jag) > 0.03, 'and it is not one even line',
              'sd %.4f' % statistics.pstdev(jag))
        check(len(set(jag)) > 500, 'and neighbouring segments differ',
              '%d distinct of %d' % (len(set(jag)), len(jag)))
        deep = sum(1 for m in runs if m > tune['amp'] + 0.05)
        calm = sum(1 for m in runs if m <= tune['amp'])
        check(deep > 0 and calm > 0,
              'and it is NON-UNIFORM: some stretches bitten deep, some only rough',
              '%d deep and %d rough of %d stretches' % (deep, calm, len(runs)))
        check(a['jag'] == b['jag'], 'and it is the same when asked twice, so it does not shimmer',
              '')

        # ---- THE PICTURE -------------------------------------------------------
        print()
        print('  AND THE RENDER USES IT')
        page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
        page.click('[data-act="play"]')
        page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=8000)
        page.click('[data-act="drive"]')
        page.wait_for_timeout(1600)
        for _ in range(40):
            st = page.evaluate("() => window.__probe.road.startLine()")
            if st['left'] <= 0 and st['go'] <= 0:
                break
            page.wait_for_timeout(90)

        def settle(side):
            page.evaluate("(s) => { const R = window.__probe.road;"
                          " R.setTimed(false); R.holdCurve(0); R.holdSpd(null);"
                          " R.setBiomePair('MOUNTAIN', 'MOUNTAIN'); R.setPhase(0.75);"
                          " R.setWet(0); R.setSnow(0); R.setPool(0); R.clearTraffic();"
                          " R.setHazardSide(s); R.setSpd(R.MAX_SPD * 0.35); }", side)
            for _ in range(14):
                page.evaluate("() => { const R = window.__probe.road;"
                              " R.clearTraffic(); R.setSpd(R.MAX_SPD * 0.35); }")
                page.wait_for_timeout(40)
            for _ in range(12):
                page.evaluate("() => { const R = window.__probe.road;"
                              " R.clearTraffic(); R.holdSpd(0); R.setPhase(0.75); }")
                page.wait_for_timeout(40)

        def jag_vs_straight(side):
            settle(side)
            page.evaluate("(t) => { const R = window.__probe.road; R.holdSpd(0);"
                          " R.rimJag(0, 1, t); }", STRAIGHT)
            page.wait_for_timeout(110)
            straight = page.screenshot()
            page.evaluate("(t) => { const R = window.__probe.road; R.holdSpd(0);"
                          " R.rimJag(0, 1, t); }", tune)
            page.wait_for_timeout(110)
            jagged = page.screenshot()
            return straight, jagged

        for side, name in ((-1, 'left'), (1, 'right')):
            straight, jagged = jag_vs_straight(side)
            n, mx, w = changed(straight, jagged, 'road')
            m, _, _ = changed(straight, jagged, 'mirror')
            on_side = (mx < w / 2) if side < 0 else (mx > w / 2)
            print('      cliff on the %-5s windscreen %5d px at x=%5.1f   mirror %4d px'
                  % (name, n, mx, m))
            check(n > BARE, 'with the cliff on the %s, the jag changes the windscreen' % name,
                  '%d pixels' % n)
            check(on_side, 'and the change is on the %s, where the drop is' % name,
                  'mean x %.1f of %d' % (mx, w))
            # THE GLASS HAS ITS OWN BAR, AND IT WAS MEASURED. The first version asked for
            # `m > 0` and passed with the jag removed: the 44-pixel pane moves a few pixels
            # between frames whatever is pinned. Without the jag it read 4 and 6; with it,
            # 33 to 56 over three runs. The bar sits between the two.
            check(m > MIRROR_BARE, 'and the mirror carries the jag too',
                  '%d pixels against a bar of %d' % (m, MIRROR_BARE))

        # THE CONTROL: two straight renders must NOT differ, or the diff above is noise.
        settle(1)
        page.evaluate("(t) => { const R = window.__probe.road; R.holdSpd(0);"
                      " R.rimJag(0, 1, t); }", STRAIGHT)
        page.wait_for_timeout(110)
        s1 = page.screenshot()
        page.wait_for_timeout(110)
        s2 = page.screenshot()
        page.evaluate("(t) => window.__probe.road.rimJag(0, 1, t)", tune)
        n0, _, _ = changed(s1, s2, 'road')
        check(n0 < BARE, 'and two straight renders do not differ, so the diff is the jag',
              '%d pixels' % n0)

        errs = page.evaluate("() => window.__probe.errors")
        check(not errs, 'no page errors', '; '.join(errs[:2]))
        browser.close()
    httpd.shutdown()

    print()
    if fails:
        print('  %d check(s) FAILED' % len(fails))
        return 1
    print('  the rim is jagged, uneven, fixed to the road, and drawn in both views')
    print('  whether it reads as rock at speed is the owner call on a device.')
    return 0


sys.exit(main())
