#!/usr/bin/env python3
"""COP COP - police cars collide with each other, and lift and steer to avoid it.

    .venv/Scripts/python tools/cop-cop-test.py
    .venv/Scripts/python tools/cop-cop-test.py --root <an older checkout> --expect-fail

RLG-258. Owner, 2026-09-15: "It still seems like police cruisers, and possibly also interceptors, do
not collide with each other. They need to have their own navigation behaviour so that they avoid
collisions with traffic and each other intelligently." And earlier, of the same thing: "the chasing
cruisers don't seem like they collide with each other as well, so they just pile on you and kind of
stun lock you into a location".

WHAT WAS FOUND. A cruiser was tested against the traffic, the roadblocks and the player, and against
another police car by nothing at all. Its two navigation loops were blind the same way: the lift
(`room`/`lead`) and the swerve (`dodge`) both scanned `traffic` only.

  THROUGH      two cruisers are placed in the same lane, overlapping, and held there for two
               seconds. On a build with no police-to-police collision neither is marked; here both
               take damage. It is read from `copState`, which reports each car's damage.
  AVOID        two cruisers are left to drive themselves for five seconds and the frames they spend
               in the same place are counted. IT IS AN INVARIANT, NOT THE DISCRIMINATOR: the staged
               pair separate on the build before this one too (0 % on both), so it cannot fail on
               the old engine and is kept to catch a future change that makes them merge. THROUGH is
               what tells the two builds apart. An earlier version of this arm asked whether the car
               behind ended up slower or across, which is true of a cruiser doing anything at all,
               and passed on the engine with no avoidance in it.
  TRAP         a parked trap is scenery, as everywhere else (RLG-173): a cruiser overlapping one
               takes no damage from it.

WHAT THIS CANNOT SAY. Whether the box around the player still forms, and whether the road reads as
police driving rather than bumper cars, are the owner's verdict on the device. The swerve between two
police cars is deliberately weaker than the one round traffic so the box survives.

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

# two cruisers, placed by hand, watched for damage and for what they do about each other
PAIR = """async (a) => {
  const R = window.__road;
  R.holdSpd(null); R.copsClear(); R.parkTraffic(9, 60000); R.heat(3); R.clearWreck();
  R.setLane(-0.6);
  R.holdSpd(0.55 * R.MAX_SPD);
  const pz = () => R.startLine().pos + R.PLAYER_Z;
  /* two chasing cruisers, in one lane, at the player's own speed */
  R.placeCop(a.dzA, a.x);
  R.commitCop('player', a.dzB - 0);
  const cs = R.cops();
  const A = cs[0], B = cs[1];
  if(!A || !B) return null;
  for(const k of [A, B]){ k.trap = false; k.armed = false; k.wreck = 0; k.dmg = 0;
                          k.grace = 0; k.iframe = 0; k.spd = 0.55 * R.MAX_SPD; }
  B.z = pz() + a.dzB; B.x = a.x;
  if(a.trap){ B.trap = true; B.armed = true; B.spd = 0; }
  const start = { ax: A.x, bx: B.x, bspd: B.spd };
  const out = { overlap: 0, frames: 0 };
  const t0 = performance.now();
  await new Promise((done) => {
    const tick = () => {
      if(a.hold){                       /* the THROUGH arm keeps them overlapping */
        A.z = pz() + a.dzA; A.x = a.x;
        B.z = pz() + a.dzB; B.x = a.x;
      } else if(Math.abs(A.z - B.z) < ((A.len || 400) + (B.len || 400))/2 &&
                Math.abs(A.x - B.x) < ((A.w || 0.27) + (B.w || 0.27))/2){
        out.overlap++;                  /* frames the two spent in the same place */
      }
      out.frames++;
      if(performance.now() - t0 < a.secs * 1000) requestAnimationFrame(tick); else done();
    };
    requestAnimationFrame(tick);
  });
  R.holdSpd(null);
  return { adm: Math.round(A.dmg || 0), bdm: Math.round(B.dmg || 0),
           bspd: Math.round(B.spd || 0), startB: Math.round(start.bspd),
           dx: +Math.abs(A.x - B.x).toFixed(3), wrecks: (A.wreck > 0 ? 1 : 0) + (B.wreck > 0 ? 1 : 0),
           overlap: out.overlap, frames: out.frames };
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
    print('cop-cop  .  police collide with each other, and drive to avoid it')
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

        g = pg.evaluate(PAIR, {'dzA': 900, 'dzB': 1000, 'x': -0.6, 'secs': 2, 'hold': True})
        print('      THROUGH  damage A %s, B %s; %s wrecked' % (g['adm'], g['bdm'], g['wrecks']))
        ok(g['adm'] > 0 and g['bdm'] > 0, 'two cruisers in the same place damage each other',
           'A took %s and B took %s' % (g['adm'], g['bdm']))

        # THE EFFECT, NOT THE INTENTION. The first version of this arm asked whether the car
        # behind ended up slower or across, and both are true of a cruiser doing anything at
        # all - it passed on the build with no avoidance in it, which is a vacuous check. What
        # the owner reported is two police cars ENDING UP IN THE SAME PLACE, so that is what is
        # counted: frames where the pair overlap while they drive themselves.
        g = pg.evaluate(PAIR, {'dzA': 1400, 'dzB': 900, 'x': -0.6, 'secs': 5, 'hold': False})
        share = 100.0 * g['overlap'] / max(1, g['frames'])
        print('      AVOID    they overlapped on %d of %d frames (%.1f%%), ending %s across'
              % (g['overlap'], g['frames'], share, g['dx']))
        ok(share < 10, 'two cruisers left to drive do not end up in the same place',
           'they overlapped on %.1f%% of frames' % share)

        g = pg.evaluate(PAIR, {'dzA': 900, 'dzB': 1000, 'x': -0.6, 'secs': 2, 'hold': True, 'trap': True})
        print('      TRAP     damage A %s (the trap is scenery)' % g['adm'])
        ok(g['adm'] == 0, 'a parked trap damages nothing it overlaps', 'A took %s' % g['adm'])

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
    print('police collide with each other, and drive to avoid it')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
