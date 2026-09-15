#!/usr/bin/env python3
"""TRAP SWITCH - a speed trap engages the player by default, and the debug switch stops it.

    .venv/Scripts/python tools/trap-switch-test.py
    .venv/Scripts/python tools/trap-switch-test.py --root <an older checkout> --expect-fail

RLG-253. Owner, 2026-09-15: "Why don't we just stop speed traps from engaging the player completely
as a temporary test to see if it still happens or not?"

THIS TEST IS TEMPORARY WITH THE SWITCH. Delete it when RLG-253 is settled and the switch goes.

  MENU     on a fresh boot, OPTIONS > DEBUG shows SPEED TRAPS ENGAGE · ON (0.14.32; it booted OFF in
           0.14.30 and 0.14.31). Tapping it shows OFF and the engine reads OFF; tapping again shows ON.
  OFF      with the switch OFF, three traps from the road's own spawner are driven past at
           90 % of top speed on a road with the traffic parked away. None engages, but each pass
           still adds the trap's heat once and still earns the Interceptors, so the test build
           changes nothing about the police except the trap turning into a cruiser.
  DEFAULT  with the switch as it boots, the same drive engages at least two of three, and each one engages at
           or behind the player's car (the RLG-247 rule is still there).

WHAT THIS CANNOT SAY. Whether the owner still sees engaged cruisers ahead with traps switched off is
the whole point of the test, and only the owner on the device can say it. Whether a trap pulls over a
speeding NPC is seen only when one happens to pass; it is not staged here.

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

# each trap that turned into a moving cruiser, and where. The traffic is parked away for the drive,
# so nothing but the player can wake one. onPlayer cannot say who woke it: the trap's own target
# search runs on the frame it wakes and can overwrite the NPC branch's onPlayer = false.
TRAP = """(secs) => {
  const R = window.__road;
  return new Promise((done) => {
    const out = [];
    const t0 = performance.now();
    const pts0 = R.pursuit().pts; let top = pts0;
    const tick = () => {
      const pz = R.startLine().pos + R.PLAYER_Z;
      top = Math.max(top, R.pursuit().pts);
      for(const k of R.cops()){
        if(k.__wasTrap === undefined) k.__wasTrap = !!k.trap;
        if(k.__wasTrap && !k.trap && !k.__logged){ k.__logged = 1;
          out.push(Math.round(k.z - pz)); }
      }
      if(performance.now() - t0 < secs * 1000) requestAnimationFrame(tick);
      else done({ engaged: out, rise: top - pts0, earned: R.pursuit().earned });
    };
    requestAnimationFrame(tick);
  });
}"""

LABEL = """() => { const b = document.querySelector('#veil:not(.hidden) [data-act="dt"]');
                   return b ? b.textContent.replace(/\\s+/g, ' ').trim() : null; }"""


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
    print('trap-switch  .  speed traps engage the player by default, and the debug switch stops them')
    print('      serving %s' % root)
    with sync_playwright() as p:
        b = launch_chromium(p, headless=True, args=['--mute-audio'])
        pg = b.new_context(viewport={'width': 480, 'height': 900}).new_page()
        errs = []
        pg.on('pageerror', lambda e: errs.append(str(e)))
        boot(pg, 'http://127.0.0.1:%d/%s' % (port, GAME))
        pg.wait_for_selector('#veil:not(.hidden) [data-act="opts"]', timeout=10000)

        def tap(act):
            sel = '#veil:not(.hidden) [data-act="%s"]' % act
            if pg.query_selector(sel):
                pg.click(sel)
            pg.wait_for_timeout(200)

        # ---- MENU ------------------------------------------------------------------------
        tap('opts')
        tap('debug')
        first = pg.evaluate(LABEL)
        ok(first is not None and first.endswith('ON'), 'the debug menu boots with SPEED TRAPS ENGAGE ON',
           'label %r' % first)
        tap('dt')
        on = pg.evaluate(LABEL)
        engine_on = pg.evaluate('() => window.__road.trapsEngage ? window.__road.trapsEngage() : null')
        ok(on is not None and on.endswith('OFF') and engine_on is False, 'tapping it shows OFF, and the engine reads OFF',
           'label %r, engine %r' % (on, engine_on))
        tap('dt')
        off = pg.evaluate(LABEL)
        engine_off = pg.evaluate('() => window.__road.trapsEngage ? window.__road.trapsEngage() : null')
        ok(off is not None and off.endswith('ON') and engine_off is True, 'tapping again shows ON',
           'label %r, engine %r' % (off, engine_off))
        tap('back')
        tap('back')

        pg.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
        pg.click('[data-act="play"]')
        pg.wait_for_timeout(400)
        pg.click('[data-act="chase"]')      # HOT PURSUIT on
        pg.wait_for_timeout(200)
        pg.click('[data-act="drive"]')
        until(pg, '() => window.__road.startLine().left <= 0', timeout=10000)
        pg.evaluate('() => window.__road.setTimed(false)')

        # 90 % of top speed, because a pass must be OVER 170 of 200 to earn the Interceptors.
        def drive_past():
            got, passes = [], []
            for _ in range(3):
                pg.evaluate('() => { const R = window.__road; R.holdSpd(null); R.copsClear();'
                            ' R.heat(1); R.earnSupers(false); R.setLane(0); R.parkTraffic(9, 60000);'
                            ' R.spawnTrap(); R.holdSpd(0.9 * R.MAX_SPD); }')
                one = pg.evaluate(TRAP, 8)
                got += one['engaged']
                passes.append((one['rise'], one['earned']))
            pg.evaluate('() => window.__road.holdSpd(null)')
            return got, passes

        # ---- OFF -------------------------------------------------------------------------
        pg.evaluate('() => window.__road.trapsEngage && window.__road.trapsEngage(false)')
        none, passes = drive_past()
        print('      OFF       engaged at dz %s; each pass (heat points gained, Interceptors earned) %s'
              % (none, passes))
        ok(not none, 'with the switch OFF, no trap driven past at speed engages the player',
           '%d engaged' % len(none))
        # HEAT_SEEN is 20 points. Measured per pass: 10 to 29, because heat cools during the drive
        # and the road lays traps of its own as well. The band is there to catch a trap that
        # clocked the player on every frame of its 7,000-unit window, which adds hundreds.
        ok(all(5 <= r <= 60 for r, _ in passes), 'but each pass still adds the trap\'s heat, once',
           'points gained per pass: %s' % [r for r, _ in passes])
        ok(all(e for _, e in passes), 'and a pass over 170 still earns the Interceptors',
           'earned per pass: %s' % [e for _, e in passes])

        # ---- DEFAULT: a fresh boot, so the switch is as the product ships it ------------------
        from harness import reboot  # noqa: E402
        reboot(pg)
        pg.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
        pg.click('[data-act="play"]')
        pg.wait_for_timeout(400)
        pg.click('[data-act="chase"]')
        pg.wait_for_timeout(200)
        pg.click('[data-act="drive"]')
        until(pg, '() => window.__road.startLine().left <= 0', timeout=10000)
        pg.evaluate('() => window.__road.setTimed(false)')
        some, _ = drive_past()
        print('      DEFAULT   engaged at dz %s (positive is up the road)' % some)
        ok(len(some) >= 2, 'with the switch as it boots, traps driven past at speed engage', '%d engaged' % len(some))
        ok(some and max(some) <= 400, 'and each engages at or behind the player',
           'the furthest ahead was %s' % (max(some) if some else None))

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
    print('speed traps engage the player by default, and the debug switch stops them')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
