#!/usr/bin/env python3
"""SUPER TRIGGER - an Interceptor needs three stars and a pass over 170 past a trap or a patrol.

    .venv/Scripts/python tools/super-trigger-test.py
    .venv/Scripts/python tools/super-trigger-test.py --root <an older checkout> --expect-fail

RLG-262. Owner, 2026-09-15: "150 held shouldn't be a condition. Simply having at least three stars and
passing a patrol or a speed trap over 170 is the trigger."

IT REPLACES tools/super-gate-proof.py, which measured the held-speed condition this ruling removes.
RLG-030's two conditions stay: the stars are the standing state, the 170 is the event.

  TRAP     at three stars, a trap from the road's own spawner is driven past at 88 % (176mph). The
           player then SLOWS to 50 % - under the old 150 condition - and an Interceptor must still
           be sent. A second pass sends no second car, because three stars hold one.
  PATROL   the same with a patrol car, which earned nothing before this ruling.
  STARS    at two stars, with the pass already banked, none arrives.
  CLEAN    at three stars, held at 84 % - 168mph, over the speed limit and under the 170 the rule
           watches - none arrives. It is driven UNDER the threshold rather than with the bank held
           empty, because the road lays traps of its own and one pass at 190mph fills the bank and
           dispatches in the SAME frame, before a harness could clear it. Without this arm a build
           that sent Interceptors to everybody would pass the two above.
  SLOTS    three stars hold ONE Interceptor and four hold two, and that is a CAPACITY: each pass
           sends at most one car, so four stars with a single pass still send one. Two passes at four
           stars send two, at least a second apart. Each arm runs 14 seconds, several times the
           2.2 s stagger, so a second car would have had time to arrive.

WHAT THIS CANNOT SAY. Whether an Interceptor arriving without the held speed reads as fair on the
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
from harness import console_utf8, launch_chromium, boot, until, garage_screen  # noqa: E402

# Drive past whatever was put ahead, then hold `after` and watch for Interceptors.
ARM = """async (a) => {
  const R = window.__road;
  R.holdSpd(null); R.copsClear(); R.parkTraffic(9, 60000); R.earnSupers(false); R.heat(a.stars);
  if(a.banked) R.earnSupers(true);
  /* ONE CLOCK FOR THE WHOLE ARM, and the passes are inside it. An Interceptor is sent on the
     frame the 170 is banked, so a watch that started after a pass timed the next one against
     a zero that was already late - it read a 2.2 s stagger as 0.5. */
  const t0 = performance.now(); const at = []; let pass = 0, passed = 0, placed = -1;
  await new Promise((done) => {
    const tick = () => {
      const t = (performance.now() - t0) / 1000;
      R.heat(a.stars);                                   /* over the limit earns more of it */
      /* each pass: put one ahead, hold the pass speed, and give it 1.8 s to go by */
      if(pass < a.passes && placed < 0){
        if(a.what === 'trap'){ R.spawnTrap(); const cs = R.cops();
                               cs[cs.length - 1].z = R.startLine().pos + R.PLAYER_Z + 1500; }
        if(a.what === 'patrol') R.placePatrol(1200);
        R.holdSpd(a.pass * R.MAX_SPD);
        placed = t;
      } else if(placed >= 0 && t - placed > 1.8){
        pass++; placed = -1; passed = t;
        if(pass >= a.passes) R.holdSpd(a.after * R.MAX_SPD);
      }
      for(const k of R.cops()) if(k.superc && k.__at === undefined){
        k.__at = t; at.push(+t.toFixed(1));
      }
      if(t < a.secs) requestAnimationFrame(tick); else done();
    };
    requestAnimationFrame(tick);
  });
  R.holdSpd(null);
  /* HOW MANY WERE SENT is `at.length`, and it is the stable count: the arm starts from an empty
     road, and an Interceptor that catches a slow player can wreck itself inside the window, so
     counting what is still alive at the end read 0 for an arm that had correctly sent one. */
  return { earned: R.pursuit().earned, at, passedAt: +passed.toFixed(1),
           supers: R.cops().filter(k => k.superc && k.wreck <= 0).length,
           mph: Math.round(R.pursuit().mph) };
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
    print('super-trigger  .  three stars and a pass over 170, and no held speed')
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
        slots = pg.evaluate('() => { const s = window.__road.copCensus ? window.__road.copCensus() : null;'
                            ' return 2; }')

        def arm(name, **a):
            a.setdefault('secs', 14)
            a.setdefault('pass', 0.88)
            a.setdefault('after', 0.50)
            a.setdefault('banked', False)
            a.setdefault('what', 'trap')
            a.setdefault('passes', 1)
            got = pg.evaluate(ARM, a)
            print('      %-8s %d pass(es): %d Interceptor(s) sent at %s; %d still out; banked %s'
                  % (name, a['passes'], len(got['at']), got['at'], got['supers'], got['earned']))
            return got

        g = arm('TRAP', stars=3)
        ok(len(g['at']) == 1, 'three stars, one pass over 170 past a trap: one Interceptor',
           '%d sent' % len(g['at']))
        g = arm('TRAP x2', stars=3, passes=2)
        ok(len(g['at']) == 1, 'three stars, two passes: still one, because three stars hold one',
           '%d sent' % len(g['at']))

        g = arm('FOUR', stars=4)
        ok(len(g['at']) == 1, 'FOUR stars, one pass: still ONE - the capacity is two, the pass sends one',
           '%d sent' % len(g['at']))
        g = arm('FOUR x2', stars=4, passes=2)
        ok(len(g['at']) == slots, 'four stars, two passes: two', '%d sent' % len(g['at']))
        ok(len(g['at']) >= 2 and g['at'][1] - g['at'][0] >= 1.0,
           'and the second follows the first rather than sharing its frame', 'sent at %s' % g['at'])

        g = arm('PATROL', stars=3, what='patrol')
        ok(len(g['at']) == 1, 'a pass over 170 past a PATROL sends one too', '%d sent' % len(g['at']))

        g = arm('STARS', stars=2, banked=True)
        ok(not g['at'], 'two stars sends none, however the pass went', 'sent at %s' % g['at'])

        g = arm('CLEAN', stars=3, what='none', **{'pass': 0.84, 'after': 0.84})
        ok(not g['at'], 'three stars and 168mph - over the limit, under 170 - sends none',
           'sent at %s' % g['at'])

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
    print('three stars and a pass over 170 are the whole trigger')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
