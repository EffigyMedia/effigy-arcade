#!/usr/bin/env python3
"""PURSUIT STOP - Hot Pursuit police come from behind, and one in front forces the stop.

    .venv/Scripts/python tools/pursuit-stop-test.py
    .venv/Scripts/python tools/pursuit-stop-test.py --root <an older checkout> --expect-fail

RLG-247. Owner, 2026-09-14: "there is def cop cars still spawning ahead and waiting on me to catch up
to them already engaged. They need to only come from behind and they need to try and get around you.
If they get in front of you they force you to a stop unless you can get around them (get enough X
distance from them). It's the inverse of how it works in intercept."

WHAT WAS MEASURED BEFORE THE BUILD. Over 80 seconds at four stars, ten of eighteen speed traps
engaged the player 6,900 to 7,100 units AHEAD, because the trap's window was a distance and not a
direction. Every radio, patrol and Interceptor car entered from behind.

THREE ARMS, each from an empty road in Hot Pursuit:

  TRAP     a trap placed by the road's own spawner, driven past at speed. The cruiser it becomes
           must engage at or behind the player's car, never up the road.

  LINED    a cruiser placed 1,500 units ahead in the player's line, with the player held at 15 % of
           top speed. That is above the old crawl bust (10 %) and below the new stop (20 %), so only
           the new rule can bust the player. It must end in BUSTED within five seconds. The cruiser
           is also checked for braking below the player while it is in front.

  AROUND   the same, with the player kept PURSUIT_STOP.wide or more to the side of the cruiser every
           frame. It must NOT end in BUSTED. This is what shows LINED passes because of the line and
           not because any slow car near a cruiser is busted.

`--root` serves another checkout, so the file can be run against the commit before the build.
`--expect-fail` inverts the exit code: it exits 0 only if at least one check FAILED, which is what
that run must show.

WHAT THIS CANNOT SAY. It places cars and holds speeds. Whether a player can see the cruiser coming
across, whether 0.55 of lateral distance feels like getting around, and whether the stop is fair on a
thumb are the owner's verdict on a device.

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

# ---- THE TRAP ARM: the dz at which each trap turns into a chasing cruiser -----------------
TRAP = """(secs) => {
  const R = window.__road;
  return new Promise((done) => {
    const out = [];
    const t0 = performance.now();
    const tick = () => {
      const pz = R.startLine().pos + R.PLAYER_Z;
      for(const k of R.cops()){
        if(k.__wasTrap === undefined) k.__wasTrap = !!k.trap;
        if(k.__wasTrap && !k.trap && !k.__logged){ k.__logged = 1; out.push(Math.round(k.z - pz)); }
      }
      if(performance.now() - t0 < secs * 1000) requestAnimationFrame(tick); else done(out);
    };
    requestAnimationFrame(tick);
  });
}"""

# ---- THE STOP ARMS: a cruiser ahead, the player slow, optionally kept to the side ----------
STOP = """(a) => {
  const R = window.__road;
  return new Promise((done) => {
    const out = { wreck: '', minRatio: 9, frames: 0, aheadFrames: 0, minGap: 9 };
    const t0 = performance.now();
    const tick = () => {
      const pz = R.startLine().pos + R.PLAYER_Z;
      const k = R.cops()[0];
      /* THE SPEED THE PLAYER WAS PINNED AT, not the live one. RLG-259's zone now drags the
         player down while a cruiser is in its line, so measuring the cruiser against a car it
         is itself slowing turns "the cruiser brakes below you" into a ratio of two falling
         numbers - measured at 9.0, on a build braking correctly. */
      const me = a.pin !== undefined ? a.pin : R.pursuit().mph / 200 * R.MAX_SPD;
      if(k && k.wreck <= 0){
        const ahead = k.z - pz;
        if(a.around){
          const side = k.x > 0 ? -1 : 1;
          R.setLane(Math.max(-0.95, Math.min(0.95, k.x + side * a.gap)));
        }
        out.minGap = Math.min(out.minGap, Math.abs(k.x - (R.pursuitStop ? R.pursuitStop().playerX : k.x + 9)));
        if(ahead > 300){ out.aheadFrames++;
                         if(me > 0) out.minRatio = Math.min(out.minRatio, (k.spd || 0) / me); }
      }
      out.frames++;
      const w = R.lastWreck();
      if(w){ out.wreck = w; done(out); return; }
      if(performance.now() - t0 < a.secs * 1000) requestAnimationFrame(tick); else done(out);
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
    print('pursuit-stop  .  police from behind, and a cruiser in front forces the stop')
    print('      serving %s' % root)
    with sync_playwright() as p:
        b = launch_chromium(p, headless=True, args=['--mute-audio'])
        pg = b.new_context(viewport={'width': 480, 'height': 900}).new_page()
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
        pg.evaluate('() => window.__road.setTimed(false)')
        wide = pg.evaluate('() => window.__road.pursuitStop ? window.__road.pursuitStop().wide : 0.55')

        # ---- TRAP ------------------------------------------------------------------------
        engaged = []
        for _ in range(3):
            pg.evaluate('() => { const R = window.__road; R.holdSpd(null); R.copsClear();'
                        ' R.heat(1); R.setLane(0); R.spawnTrap(); R.holdSpd(0.85 * R.MAX_SPD); }')
            engaged += pg.evaluate(TRAP, 8)
        pg.evaluate('() => window.__road.holdSpd(null)')
        print('      TRAP    engaged at dz %s (positive is up the road)' % engaged)
        ok(len(engaged) >= 2, 'traps driven past at speed engaged the player', '%d engaged' % len(engaged))
        ok(engaged and max(engaged) <= 400, 'and every one engaged at or behind the player, never ahead',
           'the furthest ahead was %s' % (max(engaged) if engaged else None))

        def stop_arm(name, around):
            pg.evaluate('() => { const R = window.__road; R.holdSpd(null); R.copsClear();'
                        ' R.clearWreck(); R.heat(3); R.setLane(0); R.parkTraffic(9, 60000); }')
            pg.wait_for_timeout(300)
            pg.evaluate('() => { const R = window.__road; R.holdSpd(0.15 * R.MAX_SPD); }')
            pg.wait_for_timeout(700)
            x0 = 0.8 if around else 0.0
            pg.evaluate('(x) => { const R = window.__road; R.placeCop(1500, x); R.clearWreck(); }', x0)
            got = pg.evaluate(STOP, {'secs': 5, 'around': around, 'gap': wide + 0.2})
            pg.evaluate('() => window.__road.holdSpd(null)')
            print('      %-7s result %r after %d frames; %d frames with the cruiser ahead; the cruiser'
                  ' ran as slow as %.2f of the player; the closest lateral gap was %.2f'
                  % (name, got['wreck'] or 'none', got['frames'], got['aheadFrames'],
                     got['minRatio'], got['minGap']))
            return got

        lined = stop_arm('LINED', around=False)
        ok(lined['wreck'] == 'BUSTED', 'a slow player with a cruiser lined up in front is busted',
           'result %r' % lined['wreck'])
        around = stop_arm('AROUND', around=True)
        ok(around['minGap'] >= wide, 'the AROUND arm really kept the player to the side',
           'the gap closed to %.2f' % around['minGap'])
        ok(around['wreck'] != 'BUSTED', 'and a player who keeps that distance is not',
           'result %r' % around['wreck'])

        # ---- AND THE CRUISER IN FRONT BRAKES ---------------------------------------------
        # Held at a chase speed so the player cannot be busted, which leaves the cruiser's own
        # speed as the only thing measured.
        pg.evaluate('() => { const R = window.__road; R.copsClear(); R.clearWreck(); R.heat(3);'
                    ' R.setLane(0); R.parkTraffic(9, 60000); R.holdSpd(0.6 * R.MAX_SPD); }')
        pg.wait_for_timeout(700)
        pg.evaluate('() => { const R = window.__road; R.placeCop(2200, 0); R.clearWreck(); }')
        brake = pg.evaluate(STOP, {'secs': 2.5, 'around': False, 'gap': 0,
                                   'pin': pg.evaluate('() => 0.6 * window.__road.MAX_SPD')})
        pg.evaluate('() => window.__road.holdSpd(null)')
        print('      BRAKE   the cruiser ran as slow as %.2f of the player over %d frames ahead'
              % (brake['minRatio'], brake['aheadFrames']))
        ok(brake['aheadFrames'] > 10 and brake['minRatio'] < 0.6,
           'a cruiser lined up in front brakes well below the player',
           'slowest %.2f of the player over %d frames' % (brake['minRatio'], brake['aheadFrames']))

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
    print('the police come from behind, and a cruiser in front forces the stop')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
