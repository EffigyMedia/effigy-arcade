#!/usr/bin/env python3
"""SURF FLAG TEST - the debug surface flags paint, and they paint nothing when off.

    EFFIGY_NO_GPU=1 PYTHONIOENCODING=utf-8 .venv/Scripts/python tools/surf-flag-test.py

OPTIONS > DEBUG > SURFACE FLAGS paints each piece of the land in a flat colour of its own,
so the owner can drive to the spot where the ground reads see-through and say which surface
is there - or that none is. [[RLG-337]]

A DEBUG AID THAT LIES IS WORSE THAN NO DEBUG AID, because the owner would report a colour
that was never painted, or report an absence that is only the switch not working. So this
asserts both directions:

  OFF - not one pixel of any flag colour is on the canvas. If a flag colour collided with
        a colour the game actually paints, the owner would see it with the switch off and
        read the picture wrongly. This is what says the seven colours are unused.
  ON  - the two surfaces a MOUNTAIN always has beside the road are on the canvas: the
        cliff side of the ground, and the massif.

▶ WHICH SURFACES ARE VISIBLE IS NOT A PROPERTY OF THE SWITCH, and two cuts of this check
got that wrong. Asking for all seven failed because a surface can be painted and then
covered: the flat branch runs about fifteen times against three hundred bands, since a roll
hazard sends nearly every band down the cliff branch. Asking for five failed on the next
load, because THE ROAD IS GENERATED FRESH AT EVERY LOAD and the far field's fill came back
at 1,775 pixels on one run and nothing on the next. What this check owns is that the switch
paints when it is on and paints nothing when it is off. Every count is printed, and the
ones that are zero are named rather than judged.

▶ IT READS THE CANVAS, NOT A SCREENSHOT. The dials are drawn on a canvas of their own and
the shell draws the title bar over the top; neither is the road's and neither should be
counted.
"""
import argparse
import functools
import http.server
import socketserver
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from harness import console_utf8, launch_chromium, boot, until   # noqa: E402
from playwright.sync_api import sync_playwright                  # noqa: E402

fails = []

COUNT = """(cols) => {
  const c = document.getElementById('cv');
  const g = c.getContext('2d', { willReadFrequently: true });
  const d = g.getImageData(0, 0, c.width, c.height).data;
  const want = {}, out = {};
  for (const k in cols) {
    const h = cols[k];
    want[k] = [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16),
               parseInt(h.slice(5, 7), 16)];
    out[k] = 0;
  }
  for (let i = 0; i < d.length; i += 4)
    for (const k in want) {
      const w = want[k];
      // exact, not near: these are flat fills and the canvas does not shade them
      if (d[i] === w[0] && d[i+1] === w[1] && d[i+2] === w[2]) { out[k]++; break; }
    }
  return out;
}"""


def check(label, condition, detail=''):
    print('%s  %s%s' % ('PASS' if condition else 'FAIL', label,
                        ('  [%s]' % detail) if detail else ''))
    if not condition:
        fails.append(label)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--place', default='MOUNTAIN')
    ap.add_argument('--drive', type=int, default=6000,
                    help='ms of driving before the frame is read, so the land is built')
    args = ap.parse_args()
    console_utf8()

    h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
    srv = socketserver.TCPServer(('127.0.0.1', 0), h)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    init = """
    window.__probe = { road: null };
    (function(){ var real=null, wrapped=null;
      Object.defineProperty(window,'ROAD',{configurable:true,
        get:function(){return real?wrapped:undefined;},
        set:function(fn){real=fn;wrapped=function(CFG){var api=real(CFG);
          window.__probe.road=api||(CFG&&CFG.api)||null;return api;};}});})();
    """
    try:
        with sync_playwright() as p:
            br = launch_chromium(p, headless=True)
            pg = br.new_page(viewport={'width': 480, 'height': 900})
            pg.add_init_script(init)
            boot(pg, 'http://127.0.0.1:%d/games/sw/interstate.html' % port)
            until(pg, '!!window.__probe.road', timeout=15000)
            pg.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=15000)
            pg.click('[data-act="play"]')
            pg.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=8000)
            pg.click('[data-act="drive"]')
            pg.wait_for_timeout(2000)
            pg.evaluate("([k, hl]) => window.__probe.road.setBiomeShape(k, hl, null)",
                        [args.place, 1.0])
            pg.evaluate("""([k]) => { const R = window.__probe.road;
                R.setTimed(false); R.clearTraffic(); R.setDmg(0);
                R.setBiomePair(k, k); R.setPhase(0.75); }""", [args.place])
            pg.evaluate("() => window.__probe.road.holdSpd("
                        "window.__probe.road.MAX_SPD * 0.6)")
            pg.wait_for_timeout(args.drive)
            cols = pg.evaluate("() => window.__probe.road.surfCols()")
            print()
            print('  the flag colours: %s' % cols)

            pg.evaluate("() => window.__probe.road.surfFlags(false)")
            pg.wait_for_timeout(400)
            off = pg.evaluate(COUNT, cols)
            pg.evaluate("() => window.__probe.road.surfFlags(true)")
            pg.wait_for_timeout(400)
            on = pg.evaluate(COUNT, cols)
            br.close()
    finally:
        srv.shutdown()

    print()
    print('  %-7s %10s %10s' % ('surface', 'flags off', 'flags on'))
    for k in cols:
        print('  %-7s %10d %10d' % (k, off[k], on[k]))
    print()

    stray = {k: v for k, v in off.items() if v}
    check('with the flags off, no flag colour is anywhere on the canvas',
          not stray, ('%s' % stray) if stray else 'all seven unused by the game')
    WANT = ('shelf', 'mass')
    missing = [k for k in WANT if not on.get(k)]
    check('with them on, every surface this hunt is about is on the canvas',
          not missing, ('missing: %s' % missing) if missing
          else 'both of %s painted' % ' and '.join(WANT))
    covered = [k for k, v in on.items() if not v]
    if covered:
        print('       %s painted nothing visible on this road, which is not a fault - see'
              % ', '.join(covered))
        print('       the note at the top of this file')
    check('and the switch changes the picture at all',
          sum(on.values()) > 0, '%d pixel(s) flagged' % sum(on.values()))
    print()
    if fails:
        print('FAILED: %d' % len(fails))
        for f in fails:
            print('  - %s' % f)
        sys.exit(1)
    print('ALL CHECKS PASSED')


if __name__ == '__main__':
    main()
