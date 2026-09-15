#!/usr/bin/env python3
"""TRAP POST - a parked speed trap stays on its verge, whatever lane the player is in.

    .venv/Scripts/python tools/trap-post-test.py
    .venv/Scripts/python tools/trap-post-test.py --root <an older checkout> --expect-fail

RLG-253. Owner, 2026-09-15, of the police cars ahead: "They spawn in the middle of the road and they
follow my lateral position as if they are stopped in the middle of the road." With engagement OFF
they stayed dark, which is the parked-trap state, so they were traps.

WHAT WAS FOUND. A parked trap's speed is held at zero, but the general steering line at the end of the
cruiser update, `k.x += clamp(aim - k.x, ...)`, had no `parked` guard, and `aim` is the player's X. So
a trap slid off the verge into the road and then tracked the player's lane while standing still.
RLG-173 guarded the box steering against parked traps and missed this line.

THE CHECK. Hot Pursuit, traffic parked away. The trap is held ahead of the player, so it is never passed and
stays a trap for the whole watch. One trap is spawned by the road's own spawner and held 6,000 units ahead of the player's
car. The player is moved between the left lane and the right lane every 1.5 seconds for 6 seconds.
Every frame the trap's X is read.

  VERGE    the trap is always at least 1.1 from the centre - on the grass, off the road.
  STILL    it moves less than 0.02 across the whole watch.
  AWAKE    control: a trap the player passes over the limit leaves its post and
           does steer. Without this, a build in which no cruiser could steer at all would pass.

WHAT THIS CANNOT SAY. Whether anything else on the road still looks like a rogue cruiser on the
device is the owner's verdict.

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
from harness import console_utf8, launch_chromium, boot, until  # noqa: E402

GAME = 'games/sw/interstate.html'

WATCH = """(a) => {
  const R = window.__road;
  return new Promise((done) => {
    const t0 = performance.now();
    let minAbs = 9, lo = 9, hi = -9, frames = 0, trap = true, lane = -1;
    const tick = () => {
      const t = (performance.now() - t0) / 1000;
      const want = Math.floor(t / 1.5) % 2 ? 0.6 : -0.6;
      if(want !== lane){ lane = want; R.setLane(want); }
      const k = R.cops()[0];
      if(k){
        if(a.hold) k.z = R.startLine().pos + R.PLAYER_Z + a.hold;
        trap = trap && !!k.trap;
        minAbs = Math.min(minAbs, Math.abs(k.x));
        lo = Math.min(lo, k.x); hi = Math.max(hi, k.x);
        frames++;
      }
      if(t < a.secs) requestAnimationFrame(tick);
      else done({ minAbs, spread: hi - lo, frames, trap });
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
    print('trap-post  .  a parked speed trap stays on its verge')
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
        pg.click('[data-act="chase"]')      # HOT PURSUIT on
        pg.wait_for_timeout(200)
        pg.click('[data-act="drive"]')
        until(pg, '() => window.__road.startLine().left <= 0', timeout=10000)

        # ---- VERGE and STILL ---------------------------------------------------------------
        # The trap is held AHEAD of the player's car, so the player never passes it and it stays a trap.
        pg.evaluate('() => { const R = window.__road; R.setTimed(false); R.heat(3);'
                    ' R.parkTraffic(9, 60000); R.copsClear();'
                    ' R.spawnTrap(); R.holdSpd(0.5 * R.MAX_SPD); }')
        x0 = pg.evaluate('() => window.__road.cops()[0].x')
        got = pg.evaluate(WATCH, {'secs': 6, 'hold': 6000})
        print('      PARKED  spawned at x %.2f; over %d frames the closest to the centre was %.2f and it'
              ' moved %.2f; still a trap throughout: %s'
              % (x0, got['frames'], got['minAbs'], got['spread'], got['trap']))
        ok(got['frames'] > 60 and got['trap'], 'the watch really held a parked trap',
           '%d frames, trap throughout %s' % (got['frames'], got['trap']))
        ok(got['minAbs'] >= 1.1, 'a parked trap stays on the verge, off the road',
           'it came to %.2f from the centre' % got['minAbs'])
        ok(got['spread'] < 0.02, 'and it does not move sideways while the player changes lanes',
           'it moved %.2f' % got['spread'])

        # ---- AWAKE -------------------------------------------------------------------------
        pg.evaluate('() => { const R = window.__road;'
                    ' R.parkTraffic(9, 60000); R.copsClear(); R.spawnTrap();'
                    ' const k = R.cops()[0]; k.z = R.startLine().pos + R.PLAYER_Z - 300;'
                    ' R.holdSpd(0.9 * R.MAX_SPD); }')
        woke = pg.evaluate(WATCH, {'secs': 3, 'hold': 0})
        print('      AWAKE   still a trap: %s; it moved %.2f sideways' % (woke['trap'], woke['spread']))
        ok(not woke['trap'] and woke['spread'] > 0.2, 'control: an engaged trap leaves its post and steers',
           'trap %s, moved %.2f' % (woke['trap'], woke['spread']))
        pg.evaluate('() => window.__road.holdSpd(null)')

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
    print('a parked speed trap stays on its verge')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
