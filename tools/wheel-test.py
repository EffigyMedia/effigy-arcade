#!/usr/bin/env python3
"""WHEEL TEST - a working vehicle is driven with a working wheel.

    .venv/Scripts/python tools/wheel-test.py
    .venv/Scripts/python tools/wheel-test.py --falsify

The owner reported from the device on 2026-09-12 that the AMBULANCE was holding a sports car's
steering wheel. `PLAIN_WHEEL` in `drawWheel` names every production and utility body, and the
ambulance was not in it, so `plain` was false for that one vehicle: carbon weave across the top,
chrome inserts down the spokes, a silver bezel round the switchgear, a racing tick at twelve
o'clock and a rim at TH 9.5 against a working wheel's 8.6.

WHY IT SURVIVED SO LONG. `roundRim` already names MEDICAL, so the RIM was the right shape. The
wheel was a plain rim wearing a supercar's jewellery, which is a harder thing to see than a
flat-bottomed wheel in an ambulance would have been.

WHAT IS MEASURED IS THE DRAWN WHEEL, not the list that drew it. Reading `PLAIN_WHEEL` back and
asserting AMBULANCE is in it tests this file's copy of the fix against the fix. So the check asks
the engine for two finished wheels through `API.wheelOf` and compares them pixel by pixel:

  1. OUTSIDE THE BOSS, THE AMBULANCE'S WHEEL AND THE VAN'S ARE THE SAME DRAWING. An ambulance is a
     van underneath and the rim, the spokes and the horn pad are the van's. Not one pixel may
     differ.

  2. INSIDE THE BOSS THEY DIFFER. That is the badge - a red cross against the van's GENERIC marque
     - and without this question the first one passes by returning the same blank canvas twice.

  3. A SPORTS WHEEL IS STILL TELLABLE FROM A WORKING ONE. The MATADOR against the VAN, outside the
     boss, must differ in hundreds of pixels. Without this the first question passes on a build
     where every car got the plain wheel, or on one where `wheelOf` stopped drawing.

Run with `--falsify` to serve the engine with AMBULANCE struck back out of `PLAIN_WHEEL` and watch
question 1 fail. A check that cannot be made to fail is not evidence.

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

# the badge is drawn at radius 12 on a 10-unit design, so nothing of it reaches past 13 CSS pixels
# from the middle of the wheel. 15 leaves room for the stroke and keeps the question honest - the
# larger this disc, the less of the wheel question 1 is still looking at.
BADGE_R = 15
# a pixel this far apart in any channel is a different drawing rather than the same one antialiased
CHAN = 8

PROBE = r"""(a) => {
  const R = window.__probe.road;
  const grab = (k) => {
    const c = R.wheelOf(k);
    if (!c) return null;
    const g = c.getContext('2d');
    return { w: c.width, h: c.height, d: g.getImageData(0, 0, c.width, c.height).data };
  };
  const out = {};
  for (const pair of a.pairs) {
    const x = grab(pair[0]), y = grab(pair[1]);
    if (!x || !y) { out[pair.join('/')] = null; continue; }
    if (x.w !== y.w || x.h !== y.h) { out[pair.join('/')] = { size: 1 }; continue; }
    /* the canvas is 115 CSS pixels square whatever the device ratio, so the middle and the badge
       radius scale by the same factor the canvas did */
    const sc = x.w / 115, cx = 57.5 * sc, cy = 57.5 * sc, rr = (a.r * sc) * (a.r * sc);
    let inside = 0, outside = 0, ink = 0;
    for (let py = 0; py < x.h; py++) {
      for (let px = 0; px < x.w; px++) {
        const i = (py * x.w + px) * 4;
        if (x.d[i+3] > 8 || y.d[i+3] > 8) ink++;
        const diff = Math.abs(x.d[i] - y.d[i]) > a.ch || Math.abs(x.d[i+1] - y.d[i+1]) > a.ch
                  || Math.abs(x.d[i+2] - y.d[i+2]) > a.ch || Math.abs(x.d[i+3] - y.d[i+3]) > a.ch;
        if (!diff) continue;
        const dx = px - cx, dy = py - cy;
        if (dx*dx + dy*dy <= rr) inside++; else outside++;
      }
    }
    out[pair.join('/')] = { inside: inside, outside: outside, ink: ink, w: x.w, h: x.h };
  }
  return out;
}"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--falsify', action='store_true',
                    help='serve the engine with AMBULANCE struck out of PLAIN_WHEEL; check 1 must fail')
    args = ap.parse_args()
    console_utf8()

    dt_path = ROOT / 'tools' / 'drive-test.py'
    spec = importlib.util.spec_from_file_location('dt', dt_path)
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

    print("wheel-test  .  the ambulance is driven with the van's wheel")
    if args.falsify:
        print('  FALSIFY: AMBULANCE is served out of PLAIN_WHEEL. Check 1 must fail.')
    try:
        with sync_playwright() as p:
            b = launch_chromium(p, headless=True, args=['--mute-audio'])
            ctx = b.new_context(viewport={'width': 480, 'height': 900})
            ctx.add_init_script(dt.INIT)
            if args.falsify:
                # the defect, put back from the outside. It is struck out of the ENGINE's list
                # rather than out of this file's idea of one, so the check meets the drawing it
                # would have met before the fix.
                src = (ROOT / 'road.js').read_text(encoding='utf-8')
                need = '                        AMBULANCE:1,\n'
                if need not in src:
                    raise SystemExit('[wheel-test] --falsify cannot find the line it removes')
                src = src.replace(need, '', 1).replace('van:1, truck:1, ambulance:1 };',
                                                       'van:1, truck:1 };', 1)
                ctx.route('**/road.js', lambda route: route.fulfill(
                    status=200, content_type='application/javascript', body=src))
            pg = ctx.new_page()
            errs = []
            pg.on('pageerror', lambda e: errs.append(str(e)))
            boot(pg, 'http://127.0.0.1:%d/games/sw/interstate.html' % port)
            pg.wait_for_timeout(1600)
            pg.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
            pg.click('[data-act="play"]')
            pg.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
            pg.click('[data-act="drive"]')
            pg.wait_for_timeout(1500)

            pairs = [['AMBULANCE', 'VAN'], ['MATADOR', 'VAN']]
            r = pg.evaluate(PROBE, {'pairs': pairs, 'r': BADGE_R, 'ch': CHAN})

            amb = r.get('AMBULANCE/VAN')
            spo = r.get('MATADOR/VAN')
            if not amb or 'inside' not in amb:
                ok(False, 'AMBULANCE/VAN  no wheel to compare')
            else:
                ok(amb['ink'] > 2000, 'a wheel was actually drawn',
                   '%d painted pixel(s) of %dx%d' % (amb['ink'], amb['w'], amb['h']))
                # 1. the same drawing everywhere but the badge
                ok(amb['outside'] == 0,
                   'AMBULANCE matches VAN outside the boss',
                   '' if amb['outside'] == 0
                   else "%d pixel(s) differ - the wheel is not the van's" % amb['outside'])
                # 2. and the badge is still its own
                ok(amb['inside'] > 0,
                   'AMBULANCE carries its own badge on the boss',
                   '%d pixel(s) differ' % amb['inside'] if amb['inside']
                   else 'the boss is identical - the marque is not being drawn')
            if not spo or 'inside' not in spo:
                ok(False, 'MATADOR/VAN  no wheel to compare')
            else:
                # 3. the control - the comparison can still see a sports wheel
                ok(spo['outside'] > 200,
                   'a sports wheel is still tellable from a working one',
                   '%d pixel(s) differ outside the boss' % spo['outside'])

            if errs:
                ok(False, 'page errors', errs[0][:140])
            b.close()
    finally:
        srv.shutdown()

    print('  %s' % ('all checks passed' if not bad else '%d check(s) FAILED' % bad))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
