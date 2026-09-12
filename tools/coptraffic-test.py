#!/usr/bin/env python3
"""COPTRAFFIC - does a cruiser BEHIND you take damage from the traffic it weaves past?

    .venv/Scripts/python tools/coptraffic-test.py

RLG-171. The cruiser-versus-traffic collision used to run only under a guard,
`k.z > pz - 900`, so a cruiser more than 900 units behind the player was tested
against nothing at all. RLG-157 established that the police only ever arrive from
behind, so that was most of them for most of a chase: they drove through the traffic
they were weaving past and took no damage for it.

THE OWNER REPORTED THE OPPOSITE AND COULD NOT BE REPRODUCED, and the guard is why.
They wrote that the police "are constantly crashing into traffic and destroying
themselves"; no harness run on either engine ever put a single cruiser out that way.
A harness drives straight at a fixed speed, which leaves its cruisers BEHIND the
guard, where it was shut. A real player's cruisers get level and ahead, where it was
open. So this check drives exactly the way that used to prove nothing - straight, at
a held speed - and asserts the thing that used to be impossible.

IT COUNTS HITS AND NOT KILLS, WHICH IS THE CORRECTION THAT MADE IT WORK. The first
version asked whether a cruiser was WRECKED by traffic while it was behind the guard,
and it read zero on the fixed build and zero on the broken one. The guard blocked
HITS: a cruiser needs several to go out, so the hit that finally kills one usually
lands after it has closed back onto the player, and counting kills asks the question
at the wrong moment. `k.dmg` rising is the hit, and it is visible from outside.

WHAT MAKES IT NON-VACUOUS. A cruiser's damage also rises at a BARRIER, so a rise is
only counted while the car is inside the road - `Math.abs(k.x) <= 1.16` is the
engine's own barrier test. And the rise is only counted while the cruiser is more
than 900 units BEHIND the player, which is the exact band the old guard excluded.
Put `k.z > pz - 900` back and every one of these becomes impossible.

TRAFFIC REALLY IS BACK THERE, which is what makes the band worth testing: both the
traffic and the cop arrays are culled at 34,000 units behind, because the mirror
draws that far. So a cruiser 900 to 34,000 units back is weaving through cars.

Exit code 0 if a cruiser behind the guard's old limit takes traffic damage, 1
otherwise.
"""

import argparse
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

# EVERY DOWNED CRUISER, WITH WHAT PUT IT OUT AND WHERE IT WAS. Sampled from the
# engine rather than inferred from a count, because a cruiser that goes out and is
# replaced looks identical to one that never went out if only the live total is read.
WATCH = """(secs) => {
  const R = window.__road;
  return new Promise((done) => {
    const out = { hitsBehind: [], kills: [], sawBehind: 0, frames: 0 };
    const t0 = performance.now();
    const tick = () => {
      const pz = R.startLine().pos + R.PLAYER_Z;
      out.frames++;
      for(const k of R.cops()){
        const behind = pz - k.z;
        // a cruiser BEHIND the old guard's limit, and inside the road rather than
        // scraping the barrier - a barrier also raises `dmg` and is not this
        const inBand = behind > 900 && Math.abs(k.x) <= 1.16 && k.wreck <= 0;
        if(inBand) out.sawBehind++;
        const was = k.__lastDmg === undefined ? 0 : k.__lastDmg;
        const now = k.dmg || 0;
        // ONLY A TRAFFIC HIT, WHICH IS 45. A ROADBLOCK also raises `dmg` and it does
        // so from INSIDE the road, so the barrier test above cannot separate them -
        // a 60 turned up in the band on the first run and it was a roadblock.
        if(inBand && Math.round(now - was) === 45){
          out.hitsBehind.push({ behind: Math.round(behind), by: Math.round(now - was) });
        }
        k.__lastDmg = now;
        if(k.wreck > 0 && k.downedBy && !k.__seenDown){
          k.__seenDown = true;
          out.kills.push({ how: k.downedBy, behind: Math.round(behind) });
        }
      }
      if(performance.now() - t0 < secs * 1000) requestAnimationFrame(tick);
      else done(out);
    };
    requestAnimationFrame(tick);
  });
}"""


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
    ap.add_argument('--seconds', type=float, default=90.0)
    ap.add_argument('--heat', type=int, default=4)
    args = ap.parse_args()
    console_utf8()
    httpd, port = serve(ROOT)
    base = 'http://127.0.0.1:%d' % port
    fails = []
    print('coptraffic  .  a cruiser behind you still hits the traffic it weaves past')
    with sync_playwright() as p:
        b = launch_chromium(p, headless=not args.headed,
                            args=['--mute-audio',
                                  '--autoplay-policy=no-user-gesture-required'])
        ctx = b.new_context(viewport={'width': 480, 'height': 900})
        page = ctx.new_page()
        errs = []
        page.on('pageerror', lambda e: errs.append(str(e)))
        boot(page, base + '/games/sw/interstate.html')
        try:
            until(page, '() => navigator.serviceWorker'
                        ' && navigator.serviceWorker.controller', timeout=5000)
            page.wait_for_timeout(1200)
        except Exception:
            pass
        page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
        page.click('[data-act="play"]')
        page.wait_for_timeout(400)
        page.click('[data-act="chase"]')          # HOT PURSUIT on, through the real menu
        page.wait_for_timeout(200)
        page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
        page.click('[data-act="drive"]')
        page.wait_for_timeout(1500)
        # THE RUN CLOCK WOULD END THIS BEFORE THE CHASE DID. A timed run starts with
        # sixty seconds and this drives for ninety; when it expires every driving
        # number freezes where it stood and the result reads as a tunable that stopped
        # working. RLG-125 records that costing two harnesses a day each.
        page.evaluate("() => window.__road.setTimed(false)")
        page.evaluate('(h) => window.__road.heat(h)', args.heat)
        # STRAIGHT, AT A HELD SPEED - the driver that used to prove nothing.
        page.evaluate("() => window.__road.holdSpd(0.72 * window.__road.MAX_SPD)")

        def hold():
            page.evaluate('(h) => window.__road.heat(h)', args.heat)

        hits, kills, saw, frames = [], [], 0, 0
        left = args.seconds
        while left > 0:
            hold()
            got = page.evaluate(WATCH, min(10.0, left))
            hits += got['hitsBehind']
            kills += got['kills']
            saw += got['sawBehind']
            frames += got['frames']
            left -= 10.0
        page.evaluate("() => window.__road.holdSpd(null)")

        print('      %d cruiser-frame(s) spent more than 900 units behind the player,'
              ' over %d frames' % (saw, frames))
        print('      %d traffic hit(s) landed in that band' % len(hits))
        for r in hits[:6]:
            print('        %d damage at %d units behind' % (r['by'], r['behind']))
        print('      %d cruiser(s) put out altogether: %s'
              % (len(kills), ', '.join(sorted({r['how'] for r in kills})) or 'none'))

        # THE PRECONDITION IS ITS OWN CHECK. If no cruiser ever sat behind the old
        # guard's limit, the run had nothing to say and must not score a pass - that
        # is the shape a check passes in while the defect is present.
        if saw == 0:
            print('  BLKD  no cruiser was ever behind the old guard, so this run'
                  ' could not test it')
            fails.append('no cruiser was ever in the band - the run proves nothing')
        else:
            okk = len(hits) > 0
            print(('  ok    ' if okk else '  FAIL  ')
                  + 'a cruiser behind the old guard takes traffic damage'
                  + ('' if okk else '   [k.z > pz - 900 forbade exactly this]'))
            if not okk:
                fails.append('no traffic hit landed on a cruiser behind the old guard')
        if errs:
            print('  FAIL  the page reported errors: %s' % '; '.join(errs[:3]))
            fails.append('page errors')
        b.close()
    httpd.shutdown()
    print()
    if fails:
        print('FAILED: ' + '; '.join(fails))
        return 1
    print('the guard is open and a cruiser is solid to traffic wherever it is')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
