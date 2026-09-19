#!/usr/bin/env python3
"""STOP ZONE - a police car in front drags the car behind it to a stop, and swinging aside frees it.

    .venv/Scripts/python tools/stop-zone-test.py
    .venv/Scripts/python tools/stop-zone-test.py --root <an older checkout> --expect-fail

RLG-259. Owner, 2026-09-15: "We are also missing the proper functionality for them to slow you down if
a cruiser or interceptor is directly in front of you. It should force your car slowly to a stop and
it's up to the player or other racers NPCs - cause they should all function the same - to quickly
swing to the side to get out from behind their slow down triggering zone so you can speed up and go
around them." And: "the same implementation that should be used during the intercept game when the
player is playing as police, except obviously the roles are reversed."

WHAT WAS THERE BEFORE. RLG-247 made the cruiser in front brake, which slows a player who chooses not
to overtake it, and RLG-203 made a rival lift for the player's car on shift. Neither takes hold of the
car behind, which is what the owner is asking for.

THE ARMS. Each holds a speed with `holdSpd`, which stands in for a player holding the throttle down -
the zone must beat it.

  LINED    a cruiser 1,500 ahead in the player's line, player pinned at 60 %: the speed must fall
           below a fifth of what it was pinned at within 6 seconds. The cruiser is held in its own
           lane throughout: a chasing one steers at the player, and left free it follows the car
           across, so the lateral arms would measure that steering race rather than the zone.
  ASIDE    the same, with the player held PURSUIT_STOP.wide + 0.2 across from the cruiser: the speed
           must stay near what it was pinned at. Without this arm, a build that simply slowed every
           pinned car would pass the first.
  RELEASE  lined up first, then moved aside after 2 seconds: the speed must recover past half of the
           pin, which is the owner's escape.
  RIVAL    INTERCEPT, where the player drives the police car: a rival held 1,500 behind it, in its
           line, must be dragged down the same way, and one held aside must not be. That is both the
           "they should all function the same" half of the ruling and the "roles are reversed" half.

WHAT THIS CANNOT SAY. Whether the drag feels like being forced down rather than like a stall, and
whether swinging aside is quick enough on a thumb, are the owner's verdict on the device.

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

ARM = """async (a) => {
  const R = window.__road;
  R.holdSpd(null); R.copsClear(); R.parkTraffic(9, 60000); R.heat(2); R.clearWreck();
  /* ---- AND THE RUN IS RESTARTED IF THE LAST ARM ENDED IT (RLG-267) -------
     Being dragged to a stop in a cruiser's line is BUSTED, and since RLG-267 that ENDS the
     run rather than costing two seconds. So the arm before this one leaves a game-over veil
     up, `holdSpd` moves nothing, and every reading afterwards is zero - measured, the aside
     arm read 0 of a 120mph pin on a build that never touched it. */
  const again = document.querySelector('#veil:not(.hidden) [data-act="again"], #veil:not(.hidden) [data-act="drive"], #veil:not(.hidden) [data-act="play"]');
  if(again){ again.click(); await new Promise(r => setTimeout(r, 1200));
             const go = document.querySelector('#veil:not(.hidden) [data-act="drive"]');
             if(go){ go.click(); await new Promise(r => setTimeout(r, 1500)); }
             R.setTimed(false); R.copsClear(); R.parkTraffic(9, 60000); R.heat(2); R.clearWreck(); }
  R.setLane(0);
  R.holdSpd(a.hold * R.MAX_SPD);
  /* AND THE CAR IS UP TO THE PIN BEFORE ANYTHING IS READ. A restarted run comes out of the
     countdown at a rolling start and climbs to the pinned speed over about a second, so an
     arm that began at once read its first samples at 50 of a 120mph pin and called it a
     drag. */
  await new Promise((r) => {
    const t = performance.now();
    const wait = () => {
      const up = R.pursuit().mph >= a.hold * 200 * 0.95;
      if(up || performance.now() - t > 4000) r(); else requestAnimationFrame(wait);
    };
    requestAnimationFrame(wait);
  });
  const t0 = performance.now(); const mph = []; const blocker = [];
  let moved = false, inZone = 0;
  await new Promise((done) => {
    const tick = () => {
      const t = (performance.now() - t0) / 1000;
      /* ---- THE CRUISER IS RE-PLACED EVERY FRAME, AT A SPEED OF ITS OWN ------
         It is re-placed because mutating one placed object drifted twice: a cruiser that gives
         up becomes a PARKED TRAP, which is not a blocker (RLG-173), so the arm went on moving
         a trap around and read "no drag" on a build that drags correctly. Leaving it in the
         engine's hands instead was tried when the floor landed and is worse - it brakes itself
         out of its own station, the pinned player goes past, and it was measured 27,000 units
         BEHIND the player having spent 0 of 331 samples inside the zone.

         WHAT CHANGED IS THE SPEED IT IS GIVEN. It used to be handed the PLAYER'S OWN speed
         every frame, which was harmless while the zone ramped to zero and became the whole
         measurement once the zone gained a floor at the BLOCKER's speed (RLG-271): the floor
         sat exactly on top of the car it was supposed to be slowing, so the drag could never
         be more than one frame's worth. It read 108 of a 120mph pin on the same build that had
         just been measured taking the same car to 59.

         `blockAt` is a speed of its own, below the player's pin, and that is the situation the
         rule is actually about - a slower police car in front of you. The player should be
         dragged DOWN TO IT and no further, which is both halves of the ruling in one arm and
         neither of them recomputed here (RLG-065). */
      R.placeCop(1500, 0);
      const cop = R.cops()[0];
      cop.grace = 99; cop.cool = 99;
      cop.spd = a.blockAt * R.MAX_SPD;
      /* ---- AND THE LINE IS HELD EVERY FRAME, NOT SET ONCE (RLG-271) --------
         `setLane(0)` before the loop was the whole of it, and the car did not stay there: it
         wandered to x 1.12 - the barrier - over six seconds, so the blocker kept dropping out
         of the zone and the drag kept being released and re-seeded. That is what made this arm
         swing between 66 and 100mph on one unchanged build. The aside arm has always re-issued
         its lane every frame; the lined arm now does the same, which is the only way the
         question it asks stays the question it asks. */
      if(a.aside) R.setLane(Math.max(-0.95, Math.min(0.95, a.gap)));
      else if(a.moveAt && t > a.moveAt) moved = true;
      if(moved) R.setLane(Math.max(-0.95, Math.min(0.95, a.gap)));
      else if(!a.aside) R.setLane(0);
      mph.push(Math.round(R.pursuit().mph));
      /* WHAT THE BLOCKER WAS DOING, sampled alongside the speed it was supposed to be taking.
         "no drag" and "no blocker" look identical in a column of mph and are completely
         different failures - one is a broken rule and the other is a broken arm. */
      const k = R.stagedCop();
      if(k){
        /* IN THE ZONE IS ASKED HERE, not afterwards. The player's x is part of the test and it
           MOVES - the release arm swings out half way through - so asking at the end of the
           run scores every earlier sample against a position the car was not in. It read 0 of
           331 that way on an arm that was plainly being dragged down. */
        const z = R.pursuitStop();
        if(k.dz > 0 && k.dz < z.near && Math.abs(k.dx - z.playerX) < z.wide) inZone++;
        k.px = +z.playerX.toFixed(3);
        blocker.push(k);
      }
      if(t < a.secs) requestAnimationFrame(tick); else done();
    };
    requestAnimationFrame(tick);
  });
  R.holdSpd(null);
  const last = blocker[blocker.length - 1] || null;
  return { mph, first: mph[0], last: mph[mph.length - 1], low: Math.min.apply(null, mph),
           blocker: last, sawBlocker: blocker.length, inZone: inZone };
}"""

RIVAL = """async (a) => {
  const R = window.__road;
  /* INTERCEPT: the player IS the police car, so the zone in front of it is the same zone with
     the roles reversed - the owner's own words. The rival is held 1,500 behind the player, in
     the player's line or aside from it, and the field is pinned with `holdField` so a rival
     racing or lifting for traffic cannot be mistaken for the zone. */
  /* ---- THE RIVAL IS PINNED FASTER THAN THE PLAYER (RLG-271) ---------------
     The zone's floor is the BLOCKER's own speed, and on shift the blocker is the
     player's police car. Pinning both cars at the same speed leaves the rival
     already sitting on its own floor, so the arm measured a drag of nothing on a
     build that drags correctly - it read 9200 of 9200. The rival is held ABOVE
     the player now, which is the situation the mode is actually about: a racer
     coming up behind a police car that is slower than it. */
  R.holdSpd(a.hold * R.MAX_SPD);
  R.holdField((a.fieldHold === undefined ? a.hold : a.fieldHold) * R.MAX_SPD);
  R.parkRivals(0, 60000);
  R.setLane(0);
  /* THE WINGMEN ARE CLEARED, and that is not tidying up. On shift the player has friendly
     cruisers (RLG-203), they are police cars, and a rival that falls in behind one is
     dragged down by this very zone - correctly. Measured with them left on the road: the
     aside arm dipped to 55 % while the rival sat behind a wingman. Cleared, the player's
     own car is the only thing that can be the blocker, which is what this arm is about. */
  R.copsClear();
  /* and the traffic away: a rival lifts for any car in front of it, which is not the zone */
  R.parkTraffic(9, 60000);
  await new Promise(r => setTimeout(r, 400));
  const t0 = performance.now(); const sp = [];
  await new Promise((done) => {
    const tick = () => {
      R.copsClear();
      R.placeRival(0, -1500, a.aside ? a.gap : 0);
      const st = R.rivalState();
      if(st && st.length) sp.push(st[0].spd);
      if(performance.now() - t0 < a.secs * 1000) requestAnimationFrame(tick); else done();
    };
    requestAnimationFrame(tick);
  });
  R.holdField(null); R.holdSpd(null);
  return { sp, first: sp[0], last: sp[sp.length - 1], low: Math.min.apply(null, sp),
           /* what the floor is supposed to be, read off the car that sets it */
           player: Math.round(a.hold * R.MAX_SPD) };
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
    print('stop-zone  .  a police car in front drags you down, and swinging aside frees you')
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
        wide = pg.evaluate('() => window.__road.pursuitStop().wide')
        pinned = 0.60 * 200                  # the pin, in mph on the readout

        def arm(name, **a):
            a.setdefault('hold', 0.60)
            a.setdefault('secs', 6)
            a.setdefault('aside', False)
            a.setdefault('gap', wide + 0.2)
            a.setdefault('moveAt', None)
            # the blocker's own pace: a third of the fleet's top, against a 60 % pin. It is
            # BELOW the player because that is what a car you are stuck behind is.
            a.setdefault('blockAt', 0.33)
            got = pg.evaluate(ARM, a)
            k = got.get('blocker')
            print('      %-8s pinned %dmph: started %d, lowest %d, ended %d'
                  % (name, pinned, got['first'], got['low'], got['last']))
            print('               blocker %s, in the zone for %d of %d samples'
                  % (('none' if not k else 'dz %d, dx %.2f, player x %.2f'
                      % (k['dz'], k['dx'], k.get('px', 0))),
                     got.get('inZone', 0), got.get('sawBlocker', 0)))
            return got

        g = arm('LINED')
        # THE LOW POINT, NOT THE LAST READING. Being dragged to a stop in a cruiser's line is
        # what BUSTED counts (RLG-247), and when it fires the run leaves 'driving', the zone
        # lets go, and a pinned throttle takes the car back to the pin within a second. The
        # same arm ended at 0 on one run and at the pin on the next, having been to 0 in both.
        #
        # ---- AND IT IS TWO CHECKS NOW, NOT ONE (owner, 2026-09-16, RLG-271) -----------------
        # This asserted the car reached a FIFTH of the pin, and it did: it reached zero, from a
        # 120mph pin that writes the speed every frame. The owner ruled that the defect - "the
        # amount of deceleration that's forced upon you is way too much. You can't get out of
        # it." The zone must still take a real bite out of the car, and must no longer hold it
        # at a standstill, so BOTH ends are now asserted. A single check on the low point
        # cannot tell a zone that was tuned from one that was switched off.
        blocker_mph = 0.33 * 200
        ok(g['low'] < pinned * 0.75, "a cruiser in the player's line takes a real bite out of "
           "the car", 'the lowest it reached was %dmph of a %dmph pin' % (g['low'], pinned))
        ok(g['low'] > blocker_mph * 0.7, 'and drags it down to the cruiser rather than through '
           'it to a standstill',
           'it reached %dmph behind a cruiser doing %dmph' % (g['low'], blocker_mph))

        g = arm('ASIDE', aside=True)
        ok(g['low'] > pinned * 0.7, 'a player already out of the line keeps its speed',
           'it fell to %dmph of a %dmph pin' % (g['low'], pinned))

        g = arm('RELEASE', moveAt=2.0, secs=8)
        ok(g['last'] > pinned * 0.5, 'and swinging aside releases the car, which speeds up again',
           'it ended at %dmph of a %dmph pin' % (g['last'], pinned))

        # ---- RIVAL, IN INTERCEPT ---------------------------------------------------------
        # The same zone with the roles reversed: the player drives the police car and the
        # rival behind it is the car that must be dragged down. Reached the way
        # shift-stop-test reaches it - the cruiser unlocked, picked in the garage, MODE
        # pressed until it reads INTERCEPT.
        pg.evaluate("""() => window.Arcade.save.merge('interstate-opts',
                         { super:true, cruiser:true, supercruiser:true })""")
        pg.reload()
        until(pg, '() => typeof window.__road === "object" && window.__road !== null', timeout=30000)
        pg.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
        pg.click('[data-act="play"]')
        pg.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
        for _ in range(40):
            if pg.evaluate('() => window.__road.body()') == 'CRUISER':
                break
            pg.click('[data-act="next"]')
            pg.wait_for_timeout(90)
        for _ in range(4):
            label = pg.evaluate("""() => { const b = document.querySelector('[data-act="mode"]');
                                           return b ? b.textContent.trim() : ''; }""")
            if label.endswith('INTERCEPT'):
                break
            pg.click('[data-act="mode"]')
            pg.wait_for_timeout(120)
        pg.click('[data-act="drive"]')
        pg.wait_for_timeout(2000)
        pg.evaluate('() => window.__road.setTimed(false)')
        shift = pg.evaluate('() => window.__road.shift ? window.__road.shift().on : null')
        rivals = pg.evaluate('() => window.__road.rivalState().length')
        print('      INTERCEPT on: %s, %s rivals on the grid' % (shift, rivals))
        ok(bool(shift) and rivals > 0, 'the INTERCEPT arm really started a shift with a field',
           'shift %s, %s rivals' % (shift, rivals))

        if shift and rivals:
            # THE ASIDE ARM RUNS FIRST, AND SHORT. A rival held in the line is STOPPED after
            # STOP_HOLD (2.5 s) and a stopped rival leaves the race (RLG-203), which disturbs
            # the shift for whatever runs next - measured, the aside arm inherited that and
            # read zero. Two seconds is inside the hold, so nothing is stopped by it.
            got = pg.evaluate(RIVAL, {'hold': 0.60, 'fieldHold': 0.85, 'secs': 2,
                                      'aside': True, 'gap': wide + 0.2})
            print('      RIVAL ASIDE  started %d, lowest %d, ended %d'
                  % (got['first'], got['low'], got['last']))
            ok(got['low'] > got['first'] * 0.7, 'a rival out of the line keeps its speed',
               'it fell to %d of %d' % (got['low'], got['first']))

            got = pg.evaluate(RIVAL, {'hold': 0.60, 'fieldHold': 0.85, 'secs': 6,
                                      'aside': False, 'gap': wide + 0.2})
            print('      RIVAL        started %d, lowest %d, ended %d, the police car ahead %d'
                  % (got['first'], got['low'], got['last'], got['player']))
            # ---- WHAT THE ZONE DOES TO A RIVAL NOW (owner, 2026-09-16, RLG-271) -------------
            # This asserted the rival reached a QUARTER of its own speed, which was the old rule
            # taking every blocked car to zero. The floor is the BLOCKER's speed now, and on
            # shift the blocker is the player's own police car - so the mode's verb has become
            # what the owner described it as: "it's up to YOU! to get in front and slow them
            # down." A rival is brought down to the police car's pace and no further, and going
            # slower than that is something the PLAYER has to do.
            #
            # The rival is pinned above the player for this arm. With both pinned at the same
            # speed the rival starts on its own floor and nothing can be measured - that read
            # 9200 of 9200 on a build that works.
            ok(got['low'] < got['first'] * 0.85,
               "and a rival behind the player's police car is dragged down toward it",
               'the lowest it reached was %d of %d' % (got['low'], got['first']))
            ok(got['low'] > got['player'] * 0.75,
               'but no further than the police car it is stuck behind',
               'it reached %d against a police car doing %d' % (got['low'], got['player']))

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
    print('the zone drags the car behind it down, and swinging aside frees it')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
