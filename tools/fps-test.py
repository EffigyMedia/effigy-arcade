#!/usr/bin/env python3
"""
FPS TEST - how many frames a biome costs, WITH ITS SPREAD.

    .venv/Scripts/python tools/fps-test.py

NEVER QUOTE A SINGLE RUN OF THIS. Measured on one unchanged build, a forest came
back 54.5, 60.2 and 57.0 fps in three consecutive runs. Two rounds of scenery
tuning were done against single readings inside that spread before the spread was
measured - which is to say, against noise. `occlusion-test.py` carries the same
warning about its cull count for the same reason.

So this takes several samples per biome and prints the LOWEST and the highest. A
change is only real if the ranges do not overlap.

It asserts nothing. It is an instrument, not a gate.
"""
import argparse, sys, functools, http.server, socketserver, threading
from pathlib import Path
# it finds its own root, like every other harness here. This started life as a
# scratchpad probe with the path typed in, and the pre-commit guard caught it:
# an authored file carrying an absolute path breaks the next time the tree moves.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from harness import console_utf8, launch_chromium, boot, until
from playwright.sync_api import sync_playwright
console_utf8()
# ---- THE HOUR IS AN ARGUMENT NOW ----------------------------------------
# It used to start at the DUSK default and let the clock run, so a two-second
# sample landed somewhere between no street lighting and all of it, and the
# headlight beams switched on partway through. Neither is a thing to average
# over when the change being measured is a light. Pass --phase to pin it.
ap = argparse.ArgumentParser()
ap.add_argument('--phase', type=float, default=None,
                help='pin the time of day: 0.00 dusk, 0.25 midnight, 0.50 dawn, 0.75 midday')
ap.add_argument('--samples', type=int, default=3)
ARGS = ap.parse_args()
h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
srv = socketserver.TCPServer(('127.0.0.1', 0), h); PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
INIT = """
window.__probe = { errors: [], road: null, frames: 0 };
(function(){ var real=null, wrapped=null;
  Object.defineProperty(window,'ROAD',{configurable:true,
    get:function(){return real?wrapped:undefined;},
    set:function(fn){real=fn;wrapped=function(CFG){var api=real(CFG);
      window.__probe.road=api||(CFG&&CFG.api)||null;return api;};}});})();
(function tick(){ window.__probe.frames++; requestAnimationFrame(tick); })();
"""
with sync_playwright() as p:
    b = launch_chromium(p, headless=True)
    pg = b.new_page(viewport={'width':480,'height':900})
    pg.add_init_script(INIT)
    boot(pg, 'http://127.0.0.1:%d/games/sw/interstate.html' % PORT)
    try:
        until(pg, '() => navigator.serviceWorker && navigator.serviceWorker.controller', timeout=5000)
        pg.wait_for_timeout(1200)
    except Exception: pass
    until(pg, '!!window.__probe.road', timeout=10000)
    pg.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
    pg.click('[data-act="play"]')
    pg.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
    pg.click('[data-act="drive"]'); pg.wait_for_timeout(2000)
    print()
    print("  frames per second, lowest to highest of %d samples each" % ARGS.samples)
    if ARGS.phase is not None:
        print("  the hour is pinned at phase %.2f" % ARGS.phase)
    print("  a change is only real if two ranges do not overlap")
    SAMPLES = ARGS.samples
    for k in ('CITY','DESERT','FOREST','MOUNTAIN','TUNDRA','COASTAL','SWAMP'):
        pg.evaluate("(k) => { const R = window.__probe.road; R.setBiomePair(k,k); }", k)
        runs = []
        for _ in range(SAMPLES):
            pg.evaluate("() => window.__probe.road.setSpd(window.__probe.road.MAX_SPD*0.8)")
            if ARGS.phase is not None:
                # re-pinned per sample, because the clock keeps running under it
                pg.evaluate("(v) => window.__probe.road.setPhase(v)", ARGS.phase)
            pg.wait_for_timeout(500)
            a = pg.evaluate("() => window.__probe.frames")
            pg.wait_for_timeout(2500)
            bb = pg.evaluate("() => window.__probe.frames")
            runs.append((bb-a)/2.5)
        print("  %-10s %5.1f - %5.1f fps   (%s)"
              % (k, min(runs), max(runs), ", ".join("%.1f" % r for r in runs)))
    b.close()
srv.shutdown()
