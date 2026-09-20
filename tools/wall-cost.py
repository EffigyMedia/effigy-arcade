#!/usr/bin/env python3
"""WALL COST - what the canyon and mountain walls cost a frame, measured against themselves.

    .venv/Scripts/python tools/wall-cost.py

IT ASSERTS NOTHING. It is an instrument, not a gate.

WHY IT EXISTS RATHER THAN A SECOND fps-test RUN. Two builds on two runs cannot be compared on
this machine and the attempt produced a wrong answer that was nearly acted on: one fps-test run
put MOUNTAIN at 52.0-59.2 and the next at 40.4-50.0, and COASTAL - which has no wall at all -
moved with it, because a second harness was running beside it. Frame rate here is a measurement
of what else the machine is doing.

SO BOTH ARMS RUN INSIDE ONE PAGE, ON ONE ROAD, ALTERNATING. `API.wallOff` takes the wall away
and gives it back without a reload, so the place, the hour, the weather, the terrain, the
browser and the machine's load are all shared and cancel. That is the same differential the
rail and the drop are measured with, for the same reason.

WHAT IT FOUND. Painted from each slice's rim OUT TO THE EDGE OF THE SCREEN - the way the drop's
floor is painted to the bottom of it - a CANYON ran at 43.6-51.8 fps with the wall and 60.6-60.7
without. Tiled instead, so each slice paints only the band it contributes, the same place runs
at 57.5-60.6 against 60.6-60.7. RLG-297.
"""
import functools
import http.server
import importlib.util
import socketserver
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from harness import console_utf8, launch_chromium, boot   # noqa: E402
from playwright.sync_api import sync_playwright            # noqa: E402

PLACES = ('MOUNTAIN', 'CANYON')
SAMPLES = 4
# two seconds a sample. A shorter window lands inside the rhythm of the engine's own work and a
# longer one is four minutes of harness for a number that is stable by one second.
WINDOW = 2000

# counted from INSIDE the page, on the engine's own animation frames. Counting round trips from
# Python measures the round trips.
COUNT = """(ms) => new Promise(res => {
  let n = 0; const t0 = performance.now();
  (function tick(){ n++;
    if (performance.now() - t0 < ms) requestAnimationFrame(tick);
    else res(n / ((performance.now() - t0) / 1000));
  })();
})"""


def main():
    console_utf8()
    spec = importlib.util.spec_from_file_location('dt', ROOT / 'tools' / 'drive-test.py')
    dt = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dt)

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
    srv = socketserver.TCPServer(('127.0.0.1', 0), handler)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    print('wall-cost  .  the wall on and off, alternating, in one page')
    try:
        with sync_playwright() as p:
            b = launch_chromium(p, headless=True, args=['--mute-audio'])
            ctx = b.new_context(viewport={'width': 480, 'height': 900})
            ctx.add_init_script(dt.INIT)
            pg = ctx.new_page()
            boot(pg, 'http://127.0.0.1:%d/games/sw/interstate.html' % port)
            pg.wait_for_timeout(1200)
            pg.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
            pg.click('[data-act="play"]')
            pg.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
            pg.click('[data-act="drive"]')
            pg.wait_for_timeout(1500)
            print()
            for place in PLACES:
                pg.evaluate("""(k) => { const R = window.__probe.road;
                    R.setTimed(false); R.holdCurve(0); R.setBiomePair(k, k); R.setPhase(0.5);
                    R.setWet(0); R.setSnow(0); R.setPool(0); R.clearTraffic();
                    R.holdSpd(R.MAX_SPD * 0.55); }""", place)
                pg.wait_for_timeout(2500)
                on, off = [], []
                for _ in range(SAMPLES):
                    # OFF first each time, so neither arm always gets the warm cache
                    for flag, bucket in ((True, off), (False, on)):
                        pg.evaluate("(v) => window.__probe.road.wallOff(v)", flag)
                        pg.wait_for_timeout(400)
                        bucket.append(pg.evaluate(COUNT, WINDOW))
                span = lambda v: '%.1f - %.1f' % (min(v), max(v))
                print('  %-9s  wall ON  %-15s  wall OFF  %s'
                      % (place, span(on), span(off)))
            b.close()
    finally:
        srv.shutdown()
    print()
    print('  a cost is only real if the two ranges do not overlap')
    return 0


if __name__ == '__main__':
    sys.exit(main())
