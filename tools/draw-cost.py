#!/usr/bin/env python3
"""DRAW COST - what changing the draw distance costs a frame, measured by alternating two builds.

    .venv/Scripts/python tools/draw-cost.py
    .venv/Scripts/python tools/draw-cost.py --to 300 --places MOUNTAIN,CANYON,FOREST

IT ASSERTS NOTHING. It is an instrument, not a gate. RLG-295 asks for exactly this measurement
before the number is changed: "MEASURE THE FRAME RATE BEFORE AND AFTER with fps-test, on the
phone's own terms, and read what else reads DRAW before changing it."

`DRAW` IS A `const` READ IN OVER A HUNDRED PLACES, so it cannot be toggled at runtime the way
`API.wallOff` toggles the wall. It is served instead: the engine is fetched through a route that
rewrites the one line, and the two builds are ALTERNATED in ONE page, reloading between arms.

WHY ALTERNATED, AND WHY NOT TWO PAGES. Two sequential fps-test runs cannot be compared on this
machine: one put MOUNTAIN at 52.0-59.2 and the next at 40.4-50.0, and COASTAL, which had not been
touched, moved with it. And the first attempt at THIS opened the two builds in two pages, which
failed twice over - a hidden tab gets no animation frames at all, and the service worker cached
the first build and served it to the second page, which reported a draw distance of 30,000 for
both arms. The service worker is blocked here for that reason.

A COST IS ONLY REAL IF THE TWO RANGES DO NOT OVERLAP, which is fps-test's own rule.
"""
import argparse
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

COUNT = """(ms) => new Promise(res => {
  let n = 0; const t0 = performance.now();
  (function tick(){ n++;
    if (performance.now() - t0 < ms) requestAnimationFrame(tick);
    else res(n / ((performance.now() - t0) / 1000));
  })();
})"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--to', type=int, default=300, help='the draw distance to compare against')
    ap.add_argument('--places', default='MOUNTAIN,CANYON,FOREST')
    ap.add_argument('--rounds', type=int, default=3)
    args = ap.parse_args()
    console_utf8()

    spec = importlib.util.spec_from_file_location('dt', ROOT / 'tools' / 'drive-test.py')
    dt = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dt)

    src = (ROOT / 'road.js').read_text(encoding='utf-8')
    # the committed value is read out of the engine rather than typed here, so this cannot
    # quietly compare against a number the build stopped using
    import re
    m = re.search(r'^const DRAW = (\d+);', src, re.M)
    if not m:
        raise SystemExit('[draw-cost] cannot find the DRAW line in road.js')
    base = int(m.group(1))
    bodies = {base: src, args.to: src.replace(m.group(0), 'const DRAW = %d;' % args.to, 1)}
    state = {'draw': base}

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
    srv = socketserver.TCPServer(('127.0.0.1', 0), handler)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    print('draw-cost  .  DRAW at %d against DRAW at %d, alternating in one page'
          % (base, args.to))
    try:
        with sync_playwright() as p:
            b = launch_chromium(p, headless=True, args=['--mute-audio'])
            ctx = b.new_context(viewport={'width': 480, 'height': 900})
            ctx.add_init_script(dt.INIT)
            # the service worker would cache the first build and serve it to the second arm
            ctx.route('**/sw.js', lambda r: r.abort())
            ctx.route('**/road.js', lambda r: r.fulfill(
                status=200, content_type='application/javascript', body=bodies[state['draw']]))
            pg = ctx.new_page()

            def enter(place):
                boot(pg, 'http://127.0.0.1:%d/games/sw/interstate.html' % port)
                pg.wait_for_timeout(1000)
                pg.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
                pg.click('[data-act="play"]')
                pg.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
                pg.click('[data-act="drive"]')
                pg.wait_for_timeout(1400)
                pg.evaluate("""(k) => { const R = window.__probe.road;
                    R.setTimed(false); R.holdCurve(0); R.setBiomePair(k, k); R.setPhase(0.5);
                    R.setWet(0); R.setSnow(0); R.setPool(0);
                    R.holdSpd(R.MAX_SPD * 0.55); }""", place)
                pg.wait_for_timeout(1600)
                # READ BACK WHAT THE PAGE ACTUALLY GOT. The route can be bypassed, and when it
                # was, both arms reported the same draw distance and the numbers meant nothing.
                return pg.evaluate("() => window.__probe.road.drawDistance()")

            print()
            for place in args.places.split(','):
                got = {base: [], args.to: []}
                reach = {}
                for _ in range(args.rounds):
                    for d in (base, args.to):
                        state['draw'] = d
                        reach[d] = enter(place)
                        got[d].append(pg.evaluate(COUNT, 2000))
                span = lambda v: '%.1f - %.1f' % (min(v), max(v))
                print('  %-9s  %d (%d units)  %-15s   %d (%d units)  %s'
                      % (place, base, reach[base], span(got[base]),
                         args.to, reach[args.to], span(got[args.to])))
            b.close()
    finally:
        srv.shutdown()
    print()
    print('  a cost is only real if the two ranges do not overlap')
    return 0


if __name__ == '__main__':
    sys.exit(main())
