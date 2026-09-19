#!/usr/bin/env python3
"""BUST ENDS - when the busted bar completes the run is over, however much clock is left.

    .venv/Scripts/python tools/bust-ends-test.py
    .venv/Scripts/python tools/bust-ends-test.py --root <an older checkout> --expect-fail

RLG-267. Owner, 2026-09-16, in Hot Pursuit: "When the busted bar completes, the race is over and you
are busted. Right now that doesn't work... The bar empties, you take some damage, and then it pops
full again and then empties again, and repeats and repeats and repeats."

WHAT IT WAS. `wreck(reason)` treats a wreck as a cost against the clock rather than an ending: two
seconds, a fresh car in the middle of the road, carry on - which is right for hitting a lorry and
wrong for being caught. BUSTED went down that path whenever the clock was above zero, so the penalty
was paid, the cruisers were still alongside a car that was now stopped, and the bar filled again.

  BUSTED   Hot Pursuit, sixty seconds on the clock, the player pinned under PURSUIT_STOP.spd with a
           cruiser held in its line: the run must END - the game-over veil, reading BUSTED - within
           eight seconds, and the clock must still have been running when it did.
  ONCE     and the veil must appear ONCE. A build that pays the crash penalty instead shows the
           WRECKED flash again and again, which is what the owner watched.
  CRASH    control: with the same clock, damage driven to the limit ends in a WRECK that does NOT
           end the run - the car is driving again a few seconds later. Without this arm, a build
           that ended the run on every wreck would pass the two above.

WHAT THIS CANNOT SAY. Whether the bar's own fill reads as three seconds on a phone is the owner's
verdict; this measures the ending it leads to.

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

# hold the player slow with a cruiser in its line, and watch for the run to end
BUST = """async (a) => {
  const R = window.__road;
  R.holdSpd(null); R.copsClear(); R.parkTraffic(9, 60000); R.heat(3); R.clearWreck();
  R.setClock(60); R.setLane(0);
  R.holdSpd(a.hold * R.MAX_SPD);
  const t0 = performance.now();
  const out = { ended: null, clockAt: null, flashes: 0, wrecks: [] };
  let last = '';
  await new Promise((done) => {
    const tick = () => {
      const t = (performance.now() - t0) / 1000;
      /* a fresh chasing cruiser, held 1,500 ahead in the line - see stop-zone-test for why
         it is re-placed rather than mutated */
      if(out.ended === null){
        R.placeCop(1500, 0);
        const k = R.cops()[0];
        if(k){ k.grace = 99; k.cool = 99; k.spd = R.pursuit().mph / 200 * R.MAX_SPD; }
      }
      const w = R.lastWreck();
      if(w && w !== last){ out.wrecks.push([+t.toFixed(1), w]); last = w; }
      const veil = document.querySelector('#veil:not(.hidden) .eyebrow');
      if(veil && out.ended === null){
        out.ended = +t.toFixed(1);
        out.banner = veil.textContent.trim();
        out.clockAt = R.startLine().clock;
      }
      if(t < a.secs) requestAnimationFrame(tick); else done();
    };
    requestAnimationFrame(tick);
  });
  R.holdSpd(null);
  return out;
}"""

CRASH = """async (a) => {
  const R = window.__road;
  R.holdSpd(null); R.copsClear(); R.heat(0); R.clearWreck();
  R.setClock(60); R.setLane(0);
  /* A REAL COLLISION, because `setDmg` is clamped at 99 and can never reach the limit on its
     own - the first version of this arm staged nothing and reported no wreck at all. The car
     is put one point from the limit and driven into a parked lorry. */
  R.parkTraffic(0, 1600, 'truck');
  R.setDmg(99);
  R.holdSpd(0.5 * R.MAX_SPD);
  const t0 = performance.now();
  const out = { wreck: '', ended: null };
  await new Promise((done) => {
    const tick = () => {
      const t = (performance.now() - t0) / 1000;
      if(!out.wreck) out.wreck = R.lastWreck();
      const veil = document.querySelector('#veil:not(.hidden) .eyebrow');
      if(veil && out.ended === null) out.ended = veil.textContent.trim();
      if(t < a.secs) requestAnimationFrame(tick); else done();
    };
    requestAnimationFrame(tick);
  });
  R.holdSpd(null);
  out.clock = R.startLine().clock;
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
    print('bust-ends  .  the busted bar completing is the end of the run')
    print('      serving %s' % root)
    with sync_playwright() as p:
        b = launch_chromium(p, headless=True, args=['--mute-audio'])

        def drive():
            pg = b.new_context(viewport={'width': 480, 'height': 900}).new_page()
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
            return pg

        pg = drive()
        errs = []
        pg.on('pageerror', lambda e: errs.append(str(e)))
        got = pg.evaluate(BUST, {'hold': 0.10, 'secs': 8})
        print('      BUSTED  the run ended at %ss showing %r, with %.1fs still on the clock'
              % (got['ended'], got.get('banner'), got['clockAt'] or 0))
        print('      wrecks recorded: %s' % got['wrecks'])
        ok(got['ended'] is not None, 'the run ends when the bar completes',
           'it was still driving after 8s; wrecks seen: %s' % got['wrecks'])
        ok((got.get('banner') or '').upper().find('BUST') >= 0, 'and the end screen says BUSTED',
           'it said %r' % got.get('banner'))
        ok((got['clockAt'] or 0) > 0, 'with time still on the clock, which is what swallowed it before',
           'the clock read %s' % got['clockAt'])
        ok(len(got['wrecks']) <= 1, 'and it happens once, not over and over',
           'wrecks: %s' % got['wrecks'])
        pg.close()

        pg = drive()
        pg.on('pageerror', lambda e: errs.append(str(e)))
        got = pg.evaluate(CRASH, {'secs': 6})
        print('      CRASH   wreck %r, end screen %r, clock %.1f'
              % (got['wreck'], got['ended'], got['clock']))
        ok(got['wreck'] and 'BUST' not in got['wreck'].upper(), 'the control really wrecked the car',
           'lastWreck %r' % got['wreck'])
        ok(got['ended'] is None, 'and an ordinary wreck still costs seconds rather than the run',
           'the run ended showing %r' % got['ended'])
        pg.close()

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
    print('the busted bar completing ends the run')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
