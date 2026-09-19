#!/usr/bin/env python3
"""TRAP DARK - a parked speed trap shows no lights, and the same car lights up when it engages.

    .venv/Scripts/python tools/trap-dark-test.py
    .venv/Scripts/python tools/trap-dark-test.py --root <an older checkout> --expect-fail

RLG-253. Owner, 2026-09-15: "Speed traps should not have their lights on. It should only turn their
lights on if you pass them and they engage."

WHAT WAS MEASURED BEFORE THE BUILD. `drawCopLights` ran for every police car in both views and did
not ask whether the car was a parked trap. In 90 seconds of Hot Pursuit the road put eighteen parked
traps ahead of the player, and every one of them was drawn with its bar flashing.

THE CHECK READS PIXELS, NOT A FLAG. One trap from the road's own spawner is held at a fixed distance
from the player's car every frame. The canvas is read over 40 frames, so both beats of the bar are
seen, and the vivid bar colours are counted: police blue and police red. Three arms:

  EMPTY    no police car at all. This is the baseline: the HUD and the scenery carry some of the
           same colours.
  PARKED   the trap, armed.
  ENGAGED  the SAME car at the same place, with `trap` and `armed` cleared.

The front view is held 1,500 units ahead of the player's car. The mirror is held 2,000 behind, and
the mirror's strip at the top of the canvas is counted on its own.

A PARKED trap must add almost nothing over EMPTY: under a fifth of what ENGAGED adds. ENGAGED must
add a clear amount, which is what shows the count can see a lit bar at all. Without that second
check a count that saw nothing would pass the first.

WHAT THIS CANNOT SAY. Whether a dark trap reads as a police car on a phone at night, and whether
the change removes what the owner calls the rogue cruiser, are the owner's verdict on the device.

Exit code 0 if every check passed (or, with --expect-fail, if one failed), 1 otherwise.
"""
import argparse
import functools
import http.server
import socketserver
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
from harness import console_utf8, launch_chromium, boot, until, garage_screen  # noqa: E402

GAME = 'games/sw/interstate.html'

# ---- HOLD ONE COP AT dz AND COUNT VIVID BAR PIXELS, SPLIT INTO MIRROR STRIP AND ROAD ----------
COUNT = """(a) => {
  const R = window.__road;
  const cv = document.getElementById('cv');
  const g = cv.getContext('2d');
  return new Promise((done) => {
    let n = 0; const best = { mirror: 0, road: 0 };
    const tick = () => {
      const k = R.cops()[0];
      if(k){
        k.z = R.startLine().pos + R.PLAYER_Z + a.dz;
        k.x = a.x;
        k.trap = a.parked; k.armed = a.parked;
        if(!a.parked){ k.onPlayer = false; k.wreck = 0; }
      }
      if(n > 4){
        const d = g.getImageData(0, 0, cv.width, cv.height).data;
        const split = Math.round(cv.height * 0.13);
        let mirror = 0, road = 0;
        for(let i = 0; i < d.length; i += 4){
          const r = d[i], gg = d[i+1], b = d[i+2];
          const blue = b > 200 && r < 110 && gg < 160;
          const red  = r > 220 && gg < 90 && b < 110;
          if(!(blue || red)) continue;
          if((i / 4 / cv.width) < split) mirror++; else road++;
        }
        best.mirror = Math.max(best.mirror, mirror);
        best.road = Math.max(best.road, road);
      }
      if(++n < 45) requestAnimationFrame(tick); else done(best);
    };
    requestAnimationFrame(tick);
  });
}"""


class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default=str(TOOLS.parent))
    ap.add_argument('--expect-fail', action='store_true')
    args = ap.parse_args()
    console_utf8()
    root = Path(args.root)
    fails = []

    def ok(c, label, detail=''):
        print(('  ok    ' if c else '  FAIL  ') + label + ('' if c else '   [' + str(detail) + ']'))
        if not c:
            fails.append(label)

    httpd = socketserver.TCPServer(('127.0.0.1', 0), functools.partial(Q, directory=str(root)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.socket.getsockname()[1]
    print('trap-dark  .  a parked speed trap is dark, and lights up when it engages')
    print('      serving %s' % root)
    with sync_playwright() as p:
        b = launch_chromium(p, headless=True, args=['--mute-audio'])
        pg = b.new_context(viewport={'width': 430, 'height': 900}).new_page()
        errs = []
        pg.on('pageerror', lambda e: errs.append(str(e)))
        boot(pg, 'http://127.0.0.1:%d/%s' % (port, GAME))
        pg.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
        pg.click('[data-act="play"]')
        pg.wait_for_timeout(400)
        # the drive's settings are on the SETTINGS screen (RLG-071)
        garage_screen(pg, 'settings')
        pg.click('[data-act="chase"]')      # HOT PURSUIT on
        garage_screen(pg, 'main')
        pg.wait_for_timeout(200)
        pg.click('[data-act="drive"]')
        until(pg, '() => window.__road.startLine().left <= 0', timeout=10000)
        pg.evaluate('() => { const R = window.__road; R.setTimed(false); R.heat(0); R.setLane(0);'
                    ' R.holdSpd(0.3 * R.MAX_SPD); }')

        # `seen` is the least an engaged bar must add. The mirror is a strip a few dozen pixels
        # high, so its lit bar is measured at 14 to 18 pixels where the road's is about 70.
        def arm(view, dz, x, seen):
            pg.evaluate('() => { const R = window.__road; R.copsClear(); R.heat(0); R.parkTraffic(9, 60000); }')
            empty = pg.evaluate(COUNT, {'dz': dz, 'x': x, 'parked': True})
            pg.evaluate('() => { const R = window.__road; R.copsClear(); R.spawnTrap(); }')
            parked = pg.evaluate(COUNT, {'dz': dz, 'x': x, 'parked': True})
            engaged = pg.evaluate(COUNT, {'dz': dz, 'x': x, 'parked': False})
            e, pk, en = empty[view], parked[view], engaged[view]
            print('      %-6s vivid bar pixels: empty %d, parked %d, engaged %d' % (view.upper(), e, pk, en))
            ok(en - e >= seen, '%s: an engaged cruiser adds a lit bar the count can see' % view,
               'engaged adds %d' % (en - e))
            ok(pk - e <= (en - e) * 0.2, '%s: a parked trap adds almost nothing' % view,
               'parked adds %d against engaged %d' % (pk - e, en - e))

        arm('road', 1500, 0.9, 40)
        arm('mirror', -2000, 0.0, 10)

        ok(not errs, 'no page errors', errs[0][:120] if errs else '')
        b.close()
    httpd.shutdown()
    print()
    if args.expect_fail:
        print('expected at least one failure: %s' % ('got %d' % len(fails) if fails else 'got NONE'))
        return 0 if fails else 1
    if fails:
        print('FAILED: ' + '; '.join(fails))
        return 1
    print('a parked trap is dark, and the same car lights up when it engages')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
