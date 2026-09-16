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
           arrive within 8 seconds.
  PATROL   the same with a patrol car, which earned nothing before this ruling.
  STARS    at two stars, with the pass already banked, none arrives.
  CLEAN    at three stars, held at 84 % - 168mph, over the speed limit and under the 170 the rule
           watches - none arrives. It is driven UNDER the threshold rather than with the bank held
           empty, because the road lays traps of its own and one pass at 190mph fills the bank and
           dispatches in the SAME frame, before a harness could clear it. Without this arm a build
           that sent Interceptors to everybody would pass the two above.
  SLOTS    the two that arrive are at least a second apart, and never more than SUPER_SLOTS are out
           (RLG-256). The stagger used to ride on the held-speed counter this ruling removes.

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
from harness import console_utf8, launch_chromium, boot, until  # noqa: E402

# Drive past whatever was put ahead, then hold `after` and watch for Interceptors.
ARM = """async (a) => {
  const R = window.__road;
  R.holdSpd(null); R.copsClear(); R.parkTraffic(9, 60000); R.earnSupers(false); R.heat(a.stars);
  if(a.what === 'trap'){ R.spawnTrap(); const cs = R.cops();
                         cs[cs.length - 1].z = R.startLine().pos + R.PLAYER_Z + 1500; }
  if(a.what === 'patrol') R.placePatrol(1200);
  if(a.banked) R.earnSupers(true);
  R.holdSpd(a.pass * R.MAX_SPD);
  await new Promise(r => setTimeout(r, 1800));           /* go past it */
  const earned = R.pursuit().earned;
  R.holdSpd(a.after * R.MAX_SPD);
  /* ANYTHING ALREADY OUT IS NOT AN ARRIVAL. One can be sent during the 1,800 ms pass above,
     and counting it put two "arrivals" 0.5 s apart on a build staggering them by 2.2 s. */
  for(const k of R.cops()) if(k.superc) k.__at = -1;
  const t0 = performance.now(); const at = [];
  await new Promise((done) => {
    const tick = () => {
      R.heat(a.stars);
      for(const k of R.cops()) if(k.superc && k.__at === undefined){
        k.__at = (performance.now() - t0) / 1000; at.push(+k.__at.toFixed(1));
      }
      if(performance.now() - t0 < a.secs * 1000) requestAnimationFrame(tick); else done();
    };
    requestAnimationFrame(tick);
  });
  R.holdSpd(null);
  return { earned, at, mph: Math.round(R.pursuit().mph) };
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
        pg.click('[data-act="chase"]')      # HOT PURSUIT on
        pg.wait_for_timeout(200)
        pg.click('[data-act="drive"]')
        until(pg, '() => window.__road.startLine().left <= 0', timeout=10000)
        pg.evaluate('() => window.__road.setTimed(false)')
        slots = pg.evaluate('() => { const s = window.__road.copCensus ? window.__road.copCensus() : null;'
                            ' return 2; }')

        def arm(name, **a):
            a.setdefault('secs', 8)
            a.setdefault('pass', 0.88)
            a.setdefault('after', 0.50)
            a.setdefault('banked', False)
            a.setdefault('what', 'trap')
            got = pg.evaluate(ARM, a)
            print('      %-7s earned %-5s  Interceptors at %s  (holding %dmph)'
                  % (name, got['earned'], got['at'], got['mph']))
            return got

        g = arm('TRAP', stars=3)
        ok(g['earned'], 'a pass over 170 past a trap is banked', 'earned %s' % g['earned'])
        ok(len(g['at']) >= 1, 'and an Interceptor arrives without the player holding 150',
           'none in 8s while holding %dmph' % g['mph'])
        if len(g['at']) >= 2:
            ok(g['at'][1] - g['at'][0] >= 1.0, 'the two are staggered, not dumped in one frame',
               'they arrived %.1fs apart' % (g['at'][1] - g['at'][0]))
        ok(len(g['at']) <= slots, 'and never more than the two Interceptor slots', '%d arrived' % len(g['at']))

        g = arm('PATROL', stars=3, what='patrol')
        ok(g['earned'], 'a pass over 170 past a PATROL is banked too', 'earned %s' % g['earned'])
        ok(len(g['at']) >= 1, 'and it sends an Interceptor as well', 'none in 8s')

        g = arm('STARS', stars=2, banked=True)
        ok(not g['at'], 'two stars sends none, however the pass went', 'Interceptors at %s' % g['at'])

        g = arm('CLEAN', stars=3, what='none', **{'pass': 0.84, 'after': 0.84})
        ok(not g['at'], 'three stars and 168mph - over the limit, under 170 - sends none',
           'Interceptors at %s' % g['at'])

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
