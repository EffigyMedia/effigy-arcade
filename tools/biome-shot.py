#!/usr/bin/env python3
"""BIOME SHOT - what a place actually looks like, from the road.

    .venv/Scripts/python tools/biome-shot.py
    .venv/Scripts/python tools/biome-shot.py --biomes FARMLAND,TUNNEL --hour 0.75

RLG-102, RLG-105 and the places after them. Owner, 2026-09-01: "Please take screenshots of
all the new biomes as you finish them."

A PLACE IS THE ONE THING IN THIS ENGINE THAT IS SETTLED BY LOOKING. Every check written for
farmland asserts a NUMBER - one distance per rank, both views on the same side, the flattest
relief on the board - and not one of them can say whether a cornfield reads as a cornfield.

IT ASSERTS NOTHING. It is an instrument, not a gate.

WHAT IT HOLDS STILL, so two places can be compared rather than two moments. The hour, the
weather and the speed are all pinned, the road is cleared of traffic, and the biome is set on
BOTH ends of the blend so no capture lands mid-crossing. A place photographed at a different
hour from the one beside it is two pictures of the light.

ONE CAPTURE, ONE FILE, AND THEY ARE THE SAME RENDER. This project has a standing note about
showing one version in chat and saving another: the fleet sheet was shown before a grouping
fix and saved after it, and the owner reasonably reported duplicates that were no longer
there. Each file here is written from the single screenshot that was taken.
"""

import argparse
import base64
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


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def serve(root):
    handler = functools.partial(QuietHandler, directory=str(root))
    httpd = socketserver.TCPServer(('127.0.0.1', 0), handler)
    httpd.allow_reuse_address = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.socket.getsockname()[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--headed', action='store_true')
    ap.add_argument('--biomes', default='',
                    help='comma-separated; default is every place on the board')
    ap.add_argument('--hour', type=float, default=0.75,
                    help='0.75 midday, 0.25 midnight, 0.0 dusk, 0.5 dawn')
    ap.add_argument('--speed', type=float, default=0.55, help='fraction of top speed')
    ap.add_argument('--out', default='_shots')
    ap.add_argument('--approach', default='',
                    help='FROM,TO - drive at the boundary and shoot the mouth')
    ap.add_argument('--at', type=float, default=0.55,
                    help='how far through the approach to shoot, 0 placed to 1 arrived')
    args = ap.parse_args()
    console_utf8()
    out = Path(args.out) if Path(args.out).is_absolute() else ROOT / args.out
    out.mkdir(parents=True, exist_ok=True)
    httpd, port = serve(ROOT)
    print('biome-shot  .  what a place looks like from the road')
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

        keys = page.evaluate("() => window.__probe.road.BIOME_KEYS()")

        # ---- THE MOUTH IS THE FEATURE, so it needs its own capture ---------------------
        # A place photographed from inside cannot show its entrance, and for the tunnel the
        # entrance is what RLG-105 calls the feature: "driving into darkness and back out
        # into daylight is the moment worth building". This places a boundary, drives at it,
        # and shoots partway through the approach.
        if args.approach:
            a, b = [x.strip().upper() for x in args.approach.split(',')][:2]
            page.evaluate(
                "([f, hour]) => { const R = window.__probe.road;"
                " R.setBiomePair(f, f); R.setPhase(hour);"
                " R.setWet(0); R.setSnow(0); R.setPool(0); R.clearTraffic(); }",
                [a, args.hour])
            page.wait_for_timeout(400)
            page.evaluate("(t) => window.__probe.road.startBiomeChange(t)", b)
            for _ in range(200):
                page.evaluate("([spd]) => { const R = window.__probe.road;"
                              " R.clearTraffic(); R.setSpd(R.MAX_SPD * spd); }", [args.speed])
                page.wait_for_timeout(45)
                if page.evaluate("() => window.__probe.road.biomeSweep()")['atCarWeather'] \
                        >= args.at:
                    break
            sw = page.evaluate("() => window.__probe.road.biomeSweep()")
            lv = page.evaluate("() => window.__probe.road.lightLevels()")
            shot = page.screenshot()
            name = out / ('mouth-%s-to-%s.png' % (a.lower(), b.lower()))
            name.write_bytes(shot)
            print('  %s -> %-9s  %.2f through the crossing, lamps %.2f  ->  %s'
                  % (a, b, sw['atCarWeather'], lv['lamps'], name.name))
            browser.close()
            httpd.shutdown()
            print()
            print('  shots in ' + str(out))
            return 0

        want = [b.strip().upper() for b in args.biomes.split(',') if b.strip()] or keys
        print('  hour %.2f, %d%% of top speed, road cleared' % (args.hour, args.speed * 100))
        for b in want:
            if b not in keys:
                print('  %-9s not on the board' % b)
                continue
            # BOTH ENDS OF THE BLEND, so no capture lands mid-crossing and shows two places
            # mixed. And the weather is pinned dry: a place photographed in rain is a
            # picture of the rain.
            page.evaluate("""([k, hour, spd]) => {
              const R = window.__probe.road;
              R.setBiomePair(k, k);
              R.setPhase(hour);
              R.setWet(0); R.setSnow(0); R.setPool(0);
              R.clearTraffic();
              R.setSpd(R.MAX_SPD * spd);
            }""", [b, args.hour, args.speed])
            # PAST THE COUNT-IN FIRST. The first capture of farmland had GO across the
            # middle of it: the count runs for three seconds and a shot taken inside it is
            # a picture of the start line rather than of the place.
            for _ in range(40):
                st = page.evaluate("() => window.__probe.road.startLine()")
                if st['left'] <= 0 and st['go'] <= 0:
                    break
                page.wait_for_timeout(90)
            # let the road repaint and the scenery cache rebuild for this hour
            for _ in range(24):
                page.evaluate("([spd]) => { const R = window.__probe.road;"
                              " R.clearTraffic(); R.setSpd(R.MAX_SPD * spd); }", [args.speed])
                page.wait_for_timeout(40)
            side = page.evaluate("() => window.__probe.road.sideRoll()")
            dark = page.evaluate("() => window.__probe.road.lightLevels()")
            shot = page.screenshot()
            name = out / ('biome-%s.png' % b.lower())
            name.write_bytes(shot)
            print('  %-9s lamps %.2f  side %-5s  ->  %s'
                  % (b, dark['lamps'], 'left' if side < 0 else 'right', name.name))

        errs = page.evaluate("() => window.__probe.errors")
        if errs:
            print('  page errors: ' + '; '.join(errs[:3]))
        browser.close()
    httpd.shutdown()
    print()
    print('  shots in ' + str(out))
    print('  they assert nothing - what a place LOOKS like is the owner call')
    return 0


sys.exit(main())
