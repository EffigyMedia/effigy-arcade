#!/usr/bin/env python3
"""TRAP SLOTS - a speed trap engages a car only into an open slot for that car's heat.

    .venv/Scripts/python tools/trap-slots-test.py
    .venv/Scripts/python tools/trap-slots-test.py --root <an older checkout> --expect-fail

RLG-256. Owner, 2026-09-15: "We want speed traps to only actively pull out and engage if the car in
question has open engagement slots per its heat level, otherwise it just adds to its heat level and
waits for another car with open slots. This means racers in the lead don't pull ALL the traps."
Answers the same day: stars + 1 slots with no maximum, two separate slots for Interceptors, and every
racer and NPC keeps its own heat.

EVERY ARM WATCHES ONE TRAP, spawned by the road's own spawner and moved into place, on a road with the
traffic parked away. Cruisers that fill slots are committed to their car with `API.commitCop`. The staged NPC is found by a
tag, not an index, because the traffic array is reordered as the road runs.

  PLAYER   the player is held at 90 % of top speed and a trap is put 1,500 units ahead.
           OPEN   0 stars (1 slot), nobody on the player: the trap engages, committed to the player.
           FULL   0 stars, one cruiser on the player: the trap stays parked, and the player's heat
                  still rises by one sighting (15 to 25 points).
           STARS  2 stars (3 slots): with two on, it engages; with three on, it does not.
  NPC      the player is held at 30 % (under the limit, so the player cannot be clocked). A traffic
           Speeder at 60 % is put 1,000 behind the player and the trap 600 behind.
           OPEN   an NPC with no heat and nobody on it: the trap engages, committed to that car.
           FULL   one cruiser on it: the trap stays parked and the NPC's own heat rises 15 to 25.
           STARS  250 points (2 stars, 3 slots) with two on: it engages.
  COOL     an NPC with 150 points and nobody on it cools after the 3 s grace at a star per 30 s: after
           6 s it holds 130 to 149 points.

  PATROL   RLG-257: a patrol car put 1,200 ahead, passed at 90 % with the player at 0 stars. With no
           cruiser on the player it engages; with one on it stays in the traffic and adds one
           sighting of heat.

WHAT THIS CANNOT SAY. Racers go through the same check as NPCs in `trapWatch`, but no race is staged
here. Whether the police feel right in a race is the owner's verdict on the device.

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

# Stage one arm and watch its trap. Returns whether the trap engaged, who it committed to, and heat.
ARM = """async (a) => {
  const R = window.__road;
  const has = !!R.slots;
  R.holdSpd(null); R.copsClear(); R.parkTraffic(9, 60000);
  let npc = null;
  if(a.npc){
    R.parkTraffic(0.5, -1000, 'sedan', R.MINDS().SPEEDER, true);
    if(has) R.tagTraffic(R.trafficCount() - 1, 'npc');
    npc = 'tag:npc';
    if(has) R.trafficSpeed(npc, 0.6 * R.MAX_SPD);
    R.heat(0);
    if(has) R.slots(npc, a.pts || 0);
    R.holdSpd(0.3 * R.MAX_SPD);
  } else {
    R.heat(a.stars);
    R.holdSpd(0.9 * R.MAX_SPD);
  }
  for(let i = 0; i < a.on; i++) if(has) R.commitCop(a.npc ? npc : 'player', -3000 - i * 600);
  R.spawnTrap();
  const cs = R.cops();
  const k = cs[cs.length - 1];
  k.__mine = 1;
  k.z = R.startLine().pos + R.PLAYER_Z + (a.npc ? -600 : 1500);
  const who = a.npc ? npc : 'player';
  const before = has ? R.slots(who) : null;
  /* THE FIRST FRAME IT LEAVES ITS POST IS THE READING. A cruiser that runs its NPC into the
     barrier loses it, gives up and parks again inside the window, so a trap state read at the
     end once reported "did not engage" for a trap that had engaged on its first frame. */
  const t0 = performance.now();
  let engaged = false, onPlayer = false, onNpc = false;
  await new Promise((done) => {
    const tick = () => {
      if(!engaged && !k.trap){
        engaged = true; onPlayer = k.onPlayer === true; onNpc = k.onPlayer === false && !!k.tgt;
      }
      if(performance.now() - t0 < a.secs * 1000) requestAnimationFrame(tick); else done();
    };
    requestAnimationFrame(tick);
  });
  const after = has ? R.slots(who) : null;
  return { engaged, onPlayer, onNpc,
           before, after, rise: (before && after) ? after.pts - before.pts : null };
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
    print('trap-slots  .  a trap engages a car only into an open slot for its heat')
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
        pg.evaluate('() => window.__road.setTimed(false)')

        def arm(name, **a):
            a.setdefault('secs', 2)
            a.setdefault('on', 0)
            got = pg.evaluate(ARM, a)
            print('      %-13s engaged %-5s  before %s  after %s' % (name, got['engaged'], got['before'], got['after']))
            return got

        # ---- PLAYER ----------------------------------------------------------------------
        g = arm('PLAYER OPEN', stars=0)
        ok(g['engaged'] and g['onPlayer'], 'player, 0 stars, nobody on: the trap engages the player',
           'engaged %s, on the player %s' % (g['engaged'], g['onPlayer']))
        g = arm('PLAYER FULL', stars=0, on=1)
        ok(not g['engaged'], 'player, 0 stars, one on: the trap stays parked', 'it engaged')
        ok(g['rise'] is not None and 15 <= g['rise'] <= 25, 'and the player\'s heat still rises by one sighting',
           'rise %s' % g['rise'])
        g = arm('PLAYER 2*, 2', stars=2, on=2)
        ok(g['engaged'] and g['onPlayer'], 'player, 2 stars, two on: the third slot is open and it engages',
           'engaged %s' % g['engaged'])
        g = arm('PLAYER 2*, 3', stars=2, on=3)
        ok(not g['engaged'], 'player, 2 stars, three on: the trap stays parked', 'it engaged')

        # ---- NPC -------------------------------------------------------------------------
        g = arm('NPC OPEN', npc=True)
        ok(g['engaged'] and g['onNpc'], 'NPC with no heat, nobody on: the trap engages that car',
           'engaged %s, on the NPC %s' % (g['engaged'], g['onNpc']))
        g = arm('NPC FULL', npc=True, on=1)
        ok(not g['engaged'], 'NPC with no heat, one on: the trap stays parked', 'it engaged')
        ok(g['rise'] is not None and 15 <= g['rise'] <= 25, 'and the NPC\'s own heat rises by one sighting',
           'rise %s' % g['rise'])
        g = arm('NPC 2*, 2', npc=True, pts=250, on=2)
        ok(g['engaged'] and g['onNpc'], 'NPC at 2 stars, two on: it engages into the third slot',
           'engaged %s' % g['engaged'])

        # ---- COOL ------------------------------------------------------------------------
        cool = pg.evaluate("""async () => {
          const R = window.__road;
          if(!R.slots) return null;
          R.copsClear(); R.parkTraffic(9, 60000);
          R.parkTraffic(0.5, 3000, 'sedan', R.MINDS().SPEEDER, true);
          R.tagTraffic(R.trafficCount() - 1, 'cool');
          const i = 'tag:cool';
          R.slots(i, 150);
          await new Promise(r => setTimeout(r, 6000));
          const s = R.slots(i);
          return s ? s.pts : null; }""")
        print('      COOL          150 points after 6 s: %s' % cool)
        ok(cool is not None and 130 <= cool < 150, 'an NPC with nobody on it cools, at the player\'s rate', 'points %s' % cool)

        # ---- PATROL (RLG-257) --------------------------------------------------------------
        def patrol(name, on):
            got = pg.evaluate("""async (on) => {
              const R = window.__road;
              R.holdSpd(null); R.copsClear(); R.parkTraffic(9, 60000); R.heat(0);
              for(let i = 0; i < on; i++) if(R.commitCop) R.commitCop('player', -3000 - i * 600);
              R.placePatrol(1200);
              const w0 = R.patrols().woken, p0 = R.pursuit().pts;
              R.holdSpd(0.9 * R.MAX_SPD);
              await new Promise(r => setTimeout(r, 2500));
              const out = { woke: R.patrols().woken - w0, rise: R.pursuit().pts - p0,
                            patrolling: R.patrols().patrolling };
              R.holdSpd(null);
              return out; }""", on)
            print('      %-13s %s' % (name, got))
            return got
        g = patrol('PATROL OPEN', 0)
        ok(g['woke'] == 1, 'a patrol passed over the limit with a slot open engages', 'woke %d' % g['woke'])
        g = patrol('PATROL FULL', 1)
        ok(g['woke'] == 0 and g['patrolling'] >= 1, 'with the slot full it stays in the traffic',
           'woke %d, still patrolling %d' % (g['woke'], g['patrolling']))
        ok(15 <= g['rise'] <= 25, 'and still adds one sighting of heat', 'rise %s' % g['rise'])

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
    print('a trap engages a car only into an open slot for its heat')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
