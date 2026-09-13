#!/usr/bin/env python3
"""FUEL GAUGE TEST - the clock as a fuel dial above and between the other two.

    .venv/Scripts/python tools/fuel-gauge-test.py
    .venv/Scripts/python tools/fuel-gauge-test.py --falsify lamp
    .venv/Scripts/python tools/fuel-gauge-test.py --falsify grow

RLG-240. Owner, 2026-09-13: "I want the actual fuel gauge, but placed above and in between the other
two gauges so they form a triangle of gauges... I want the fuel gauge pump indicator to turn YELLOW
when under 1/8 tank."

WHAT IS MEASURED IS WHAT IS PAINTED AND WHERE THE BOX SITS.

  1. THE PUMP IS DIM ABOVE AN EIGHTH OF A TANK, read off the dial canvas's pixels at the lamp.
  2. AND LIT YELLOW BELOW IT.
  3. THE FUEL DIAL IS PAINTED WHILE THE CLOCK COUNTS, and 4. NOT WHEN THE TIMER IS OFF.
  5. THE CLUSTER GROWS UPWARD. With the gauge shown, the canvas is taller and its bottom edge is where
     it was without it, so nothing below the dials moves.

`--falsify lamp` serves the pump in its dim colour always: only check 2 must fail.
`--falsify grow` serves the #dials box without its height following the canvas, so the taller
canvas hangs down out of it: only check 5 must fail.

Exit code 0 if every check passed, 1 otherwise.
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

GAME = 'games/sw/interstate.html'
FALSIFY = {
    'lamp': ('  const ink = low ? FUEL_LAMP : FUEL_DIM;', '  const ink = FUEL_DIM;'),
    'grow': ("    if(dialCv.parentElement) dialCv.parentElement.style.height = DH + 'px';", ''),
}

# the lamp's colour, and the dial face's, read off the dial canvas in its own units
READ = r"""() => {
  const R = window.__probe.road, f = R.fuelGauge(), cv = document.getElementById('gauges');
  const g = cv.getContext('2d'), s = cv.width / 115;
  const at = (x, y) => Array.from(g.getImageData(Math.round(x * s), Math.round(y * s), 1, 1).data);
  const r = cv.getBoundingClientRect();
  return { f: f, lamp: f.lamp ? at(f.lamp.x, f.lamp.y) : null,
           /* the top of the gap between the two lower faces: inside the fuel dial when
              it is drawn, and clear of both faces when it is not */
           face: at(57.5, 3), bottom: r.bottom, height: r.height };
}"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--falsify', choices=sorted(FALSIFY))
    args = ap.parse_args()
    console_utf8()

    spec = importlib.util.spec_from_file_location('dt', ROOT / 'tools' / 'drive-test.py')
    dt = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dt)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
    srv = socketserver.TCPServer(('127.0.0.1', 0), handler)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    bad = 0

    def ok(cond, label, detail=''):
        nonlocal bad
        if not cond:
            bad += 1
        print('  %s  %s%s' % ('ok  ' if cond else 'FAIL', label,
                              ('   ' + detail) if detail else ''))

    print('fuel-gauge-test  .  the clock as a fuel dial in a triangle')
    if args.falsify:
        print('  FALSIFY %s' % args.falsify)
    try:
        with sync_playwright() as p:
            b = launch_chromium(p, headless=True, args=['--mute-audio'])
            ctx = b.new_context(viewport={'width': 414, 'height': 896}, device_scale_factor=2,
                                has_touch=True, is_mobile=True)
            ctx.add_init_script(dt.INIT)
            if args.falsify:
                need, put = FALSIFY[args.falsify]
                src = (ROOT / 'road.js').read_text(encoding='utf-8')
                if need not in src:
                    raise SystemExit('[fuel-gauge] --falsify cannot find %r' % need)
                src = src.replace(need, put, 1)

                def serve(route):
                    route.fulfill(status=200, content_type='application/javascript', body=src)
                ctx.route('**/road.js', serve)
            pg = ctx.new_page()
            errs = []
            pg.on('pageerror', lambda e: errs.append(str(e)))
            boot(pg, 'http://127.0.0.1:%d/%s' % (port, GAME))
            pg.wait_for_timeout(1500)
            pg.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
            pg.click('[data-act="play"]')
            pg.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
            pg.click('[data-act="drive"]')
            pg.wait_for_timeout(2000)

            def at_clock(timed, secs):
                pg.evaluate("([t, c]) => { const R = window.__probe.road; R.setTimed(t); R.setClock(c); }",
                            [timed, secs])
                pg.wait_for_timeout(400)
                pg.evaluate("(c) => window.__probe.road.setClock(c)", secs)
                pg.wait_for_timeout(150)
                return pg.evaluate(READ)

            off = at_clock(False, 60)
            dim = at_clock(True, 120 * 0.20)
            lit = at_clock(True, 120 * 0.08)

            def yellow(px):
                return px is not None and px[0] > 190 and px[1] > 150 and px[2] < 120 and px[3] > 200

            ok(dim['lamp'] is not None and not yellow(dim['lamp']),
               'the pump is dim at a fifth of a tank', 'lamp pixel %s' % dim['lamp'])
            ok(yellow(lit['lamp']), 'the pump lights yellow below an eighth of a tank',
               'lamp pixel %s at %.3f of a tank' % (lit['lamp'], lit['f']['frac']))
            ok(dim['f']['shown'] and dim['face'][3] > 200, 'the fuel dial is painted while the clock counts',
               'shown %s, face alpha %d' % (dim['f']['shown'], dim['face'][3]))
            ok(not off['f']['shown'] and off['face'][3] < 20, 'and not with the timer off',
               'shown %s, face alpha %d' % (off['f']['shown'], off['face'][3]))
            ok(dim['height'] > off['height'] + 20 and abs(dim['bottom'] - off['bottom']) < 1,
               'the cluster grows upward and its bottom edge stays put',
               'height %.0f to %.0f, bottom %.1f to %.1f'
               % (off['height'], dim['height'], off['bottom'], dim['bottom']))
            if errs:
                ok(False, 'page errors', errs[0][:140])
            b.close()
    finally:
        srv.shutdown()

    print('  %s' % ('all checks passed' if not bad else '%d check(s) FAILED' % bad))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
