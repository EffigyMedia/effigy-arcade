#!/usr/bin/env python3
"""TRAP PULLOUT - a trap leaves its post from rest, on the verge, and accelerates like any car.

    .venv/Scripts/python tools/trap-pullout-test.py
    .venv/Scripts/python tools/trap-pullout-test.py --root <an older checkout> --expect-fail

RLG-269. Owner, 2026-09-16: "When they do engage it looks like they just pop onto the middle of the
road. They need to accelerate and pull onto the road like normal. It also seems like they immediately
accelerate up to the player. They need to use proper physics like any other car once they decide to
engage and leave their parked position." And, when told this fought RLG-247: "Well, then it needs to
get rebalanced, because when I passed, it was instantly passing me, and then in front of me."

WHAT IT WAS. `trapEngage` handed the car `spd * 0.95 + 1800` - a speed ABOVE the player's - on the
frame it left the verge. RLG-247 chose that so a cruiser entering from behind was not immediately
lost; the owner has now weighed that against what it looks like and ruled the other way.

  REST     the frame it engages, its speed is under a FIFTH of the player's. It leaves from a
           standstill, and a fifth rather than nothing because this samples the frame AFTER the
           engagement, which already carries one frame of acceleration - measured at 0.147 against
           0.789 on the build before this one.
  VERGE    and it is still on the verge that frame - at least 1.0 from the centre - rather than in
           the middle of the road.
  PULLS    over the next four seconds it both accelerates (its speed rises) and comes in off the
           verge (its distance from the centre falls). Without this arm a build where the trap
           simply never moved would pass the two above.
  BEHIND   and it does not overtake the player in those four seconds, which is the whole of what
           the owner saw.

WHAT THIS CANNOT SAY. Whether a pursuit still has enough pressure in it now that a trap cannot catch
a fast player is the owner's verdict on the device - the cost is written into RLG-269.

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

WATCH = """async (a) => {
  const R = window.__road;
  R.holdSpd(null); R.copsClear(); R.parkTraffic(9, 60000); R.heat(2); R.clearWreck();
  R.setLane(0);
  R.spawnTrap();
  const cs = R.cops(); const k = cs[cs.length - 1];
  k.z = R.startLine().pos + R.PLAYER_Z + 1500;     /* just up the road, to be passed */
  R.holdSpd(a.hold * R.MAX_SPD);
  const pz = () => R.startLine().pos + R.PLAYER_Z;
  const out = { engaged: null, atSpd: null, atX: null, dzMax: -1e9, spdLater: null, xLater: null };
  const t0 = performance.now();
  await new Promise((done) => {
    const tick = () => {
      const t = (performance.now() - t0) / 1000;
      const me = R.pursuit().mph / 200 * R.MAX_SPD;
      if(out.engaged === null && !k.trap){
        out.engaged = +t.toFixed(2);
        out.atSpd = +(k.spd / Math.max(1, me)).toFixed(3);   /* as a share of the player's */
        out.atX = +Math.abs(k.x).toFixed(3);
      }
      if(out.engaged !== null){
        out.dzMax = Math.max(out.dzMax, Math.round(k.z - pz()));
        out.spdLater = Math.round(k.spd);
        out.xLater = +Math.abs(k.x).toFixed(3);
        /* THE CLOSEST IT CAME TO THE CENTRE, not where it happens to be at the end: a
           cruiser that gives up parks on the verge again (RLG-173), so the last reading
           can be 1.15 for a car that drove the whole width of the road first. */
        out.xMin = Math.min(out.xMin === undefined ? 9 : out.xMin, Math.abs(k.x));
        out.spdMax = Math.max(out.spdMax || 0, k.spd);
      }
      if(t < a.secs) requestAnimationFrame(tick); else done();
    };
    requestAnimationFrame(tick);
  });
  R.holdSpd(null);
  return out;
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
    print('trap-pullout  .  a trap pulls out from rest, on the verge')
    print('      serving %s' % root)
    with sync_playwright() as p:
        b = launch_chromium(p, headless=True, args=['--mute-audio'])
        pg = b.new_context(viewport={'width': 480, 'height': 900}).new_page()
        errs = []
        pg.on('pageerror', lambda e: errs.append(str(e)))
        boot(pg, 'http://127.0.0.1:%d/games/sw/interstate.html' % port)
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
        pg.evaluate('() => window.__road.setTimed(false)')

        g = pg.evaluate(WATCH, {'hold': 0.90, 'secs': 6})
        print('      engaged at %ss, at %s of the player\'s speed and %s from the centre'
              % (g['engaged'], g['atSpd'], g['atX']))
        print('      after that: reached %s of speed and came to %s from the centre; furthest up the'
              ' road %s' % (g['spdMax'], g['xMin'], g['dzMax']))

        ok(g['engaged'] is not None, 'the trap was driven past and engaged', 'it never engaged')
        ok(g['atSpd'] is not None and g['atSpd'] < 0.20, 'it leaves its post from rest',
           'it started at %s of the player' % g['atSpd'])
        ok(g['atX'] is not None and g['atX'] >= 1.0, 'and it is still on the verge that frame',
           'it was %s from the centre' % g['atX'])
        ok(g['spdMax'] > 500 and g['xMin'] < g['atX'] - 0.1,
           'then it accelerates and comes in off the verge',
           'it reached %s of speed and %s from the centre, having left at %s'
           % (g['spdMax'], g['xMin'], g['atX']))
        ok(g['dzMax'] < 0, 'and it does not go past the player', 'it reached %s up the road' % g['dzMax'])

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
    print('a trap pulls out from rest, on the verge, and drives from there')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
