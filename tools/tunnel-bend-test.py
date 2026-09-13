#!/usr/bin/env python3
"""TUNNEL BEND TEST - a nearer wall hides the road beyond a bend.

    .venv/Scripts/python tools/tunnel-bend-test.py
    .venv/Scripts/python tools/tunnel-bend-test.py --falsify winding
    .venv/Scripts/python tools/tunnel-bend-test.py --falsify dark

RLG-238. Owner, 2026-09-13: "The future roadway is shown through the tunnel wall." Every capture of
a winding tunnel showed it: the road round the bend was drawn over the wall that stands between it
and the eye.

THE CAUSE WAS THE FILL RULE. Each tube surface was one polygon that folded over itself on a bend,
and canvas fills with the nonzero rule, under which the two layers of a fold cancel. The surfaces
are now built span by span with every quad wound the same way.

WHAT IS MEASURED. `API.boreOcclusion` takes every road segment inside the tube, finds the road
points that a NEARER wall span hides in the geometry, and asks the canvas, with `isPointInPath`
against the paths the last frame filled, whether each one is covered. A hidden point that is not
covered is road showing through the wall.

  1. ENOUGH ROAD IS HIDDEN BEHIND A WALL for the answer to mean something. A straight tunnel hides
     nothing, and "none showed through" is then true of any build.
  2. NONE OF IT SHOWS THROUGH.
  3. ENOUGH FAR DARKNESS LIES BEHIND A NEARER WALL to test, and 4. NONE OF THAT PAINTS BLACK OVER THE
     WALL. The owner, the same day: "The black showing THROUGH the tunnel walls." The dark far end is
     painted after the walls, and it is now clipped by every nearer wall span. This is read off the
     canvas pixels: the wall is pale, so a hidden point that reads near-black is the darkness.

`--falsify winding` serves the engine without the winding step, so overlapping quads of opposite
winding cancel again: only check 2 must fail. `--falsify dark` serves it without the clip on the dark
far end: only check 4 must fail.

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
    'winding': ('    if(s < 0) c.reverse();\n', ''),
    'dark': ('      ctx.clip(p);\n', ''),
}
ENOUGH = 60


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--falsify', choices=sorted(FALSIFY),
                    help='serve one half of the fix back; see the docstring')
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

    print('tunnel-bend-test  .  a nearer wall hides the road beyond a bend')
    if args.falsify:
        print('  FALSIFY %s: one half of the fix is removed.' % args.falsify)
    try:
        with sync_playwright() as p:
            b = launch_chromium(p, headless=True, args=['--mute-audio'])
            ctx = b.new_context(viewport={'width': 414, 'height': 900})
            ctx.add_init_script(dt.INIT)
            if args.falsify:
                src = (ROOT / 'road.js').read_text(encoding='utf-8')
                need, put = FALSIFY[args.falsify]
                if need not in src:
                    raise SystemExit('[tunnel-bend] --falsify cannot find %r' % need)
                src = src.replace(need, put, 1)

                def serve(route):
                    route.fulfill(status=200, content_type='application/javascript', body=src)
                ctx.route('**/road.js', serve)
            pg = ctx.new_page()
            errs = []
            pg.on('pageerror', lambda e: errs.append(str(e)))
            boot(pg, 'http://127.0.0.1:%d/%s' % (port, GAME))
            pg.wait_for_timeout(1600)
            pg.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
            pg.click('[data-act="play"]')
            pg.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
            pg.click('[data-act="drive"]')
            pg.wait_for_timeout(1600)
            # the clock off so a slow run cannot end mid-test (RLG-125), and a hard-winding
            # tunnel so there are bends for a wall to hide the road behind
            pg.evaluate("""() => { const R = window.__probe.road; R.setTimed(false);
              R.setBiomePair('FARMLAND','FARMLAND'); R.setPhase(0.5);
              R.setBiomeShape('TUNNEL', null, 1.0); R.startBiomeChange('TUNNEL'); }""")

            hidden = through = frames = dhidden = dthrough = 0
            first = None
            for _ in range(900):
                c = pg.evaluate("""() => { const R = window.__probe.road;
                  R.setSpd(R.MAX_SPD * 0.45); R.steerOver(0, 0.05);
                  /* no traffic: a car is drawn over the walls, and its dark glass reads
                     as black to the pixel check without being the darkness */
                  R.clearTraffic();
                  const b = R.boreClearance();
                  return { inside: b.camInside, occ: R.boreOcclusion(), dark: R.boreDarkThrough() }; }""")
                pg.wait_for_timeout(60)
                if not c['inside'] or not c['occ']:
                    if frames:
                        break   # driven out of the far end
                    continue
                frames += 1
                hidden += c['occ']['hidden']
                through += c['occ']['through']
                if c['dark']:
                    dhidden += c['dark']['hidden']
                    dthrough += c['dark']['dark']
                if c['occ']['through'] and first is None:
                    first = c['occ']['firstAt']
                if frames >= 60 and hidden >= ENOUGH * 3 and dhidden >= ENOUGH:
                    break

            ok(hidden >= ENOUGH, 'enough road is hidden behind a nearer wall to test',
               '%d hidden road points over %d frames' % (hidden, frames))
            ok(through == 0, 'none of it shows through the wall',
               '%d of %d hidden points were not painted over%s'
               % (through, hidden, '' if first is None else ', first %d units ahead' % first))
            ok(dhidden >= ENOUGH, 'enough far darkness lies behind a nearer wall to test',
               '%d hidden dark points over %d frames' % (dhidden, frames))
            ok(dthrough == 0, 'none of the darkness paints black over the wall',
               '%d of %d hidden dark points read near-black' % (dthrough, dhidden))
            if errs:
                ok(False, 'page errors', errs[0][:140])
            b.close()
    finally:
        srv.shutdown()

    print('  %s' % ('all checks passed' if not bad else '%d check(s) FAILED' % bad))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
