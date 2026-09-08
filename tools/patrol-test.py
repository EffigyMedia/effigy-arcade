#!/usr/bin/env python3
"""PATROL TEST - police drive as traffic, and only engage when you earn it.

    .venv/Scripts/python tools/patrol-test.py

Owner, 2026-09-07: "We should put police into the traffic as standard vehicles. They just
don't engage you if hot pursuit has turned off. If hot pursuit is turned on then these
random police in the traffic will engage you if you pass them going beyond the speed limit."

A PATROL IS TRAFFIC UNTIL IT IS NOT. While it patrols it is an ordinary car in the traffic
array with a Civilian at the wheel and its bar dark. When it engages it is moved into the
cops array, where every piece of pursuit behaviour already lives.

THE THREE CASES, AND THE FIRST TWO ARE THE ONES THAT CATCH A LAZY IMPLEMENTATION:

  pursuit OFF, passed at speed    -> it must NOT engage
  pursuit ON,  passed UNDER the limit -> it must NOT engage
  pursuit ON,  passed OVER the limit  -> it MUST engage

An implementation that engages on proximity, or on any pass, or that ignores the switch,
passes the third and fails one of the first two. A file that only tested the third would go
green on all of them.

AND IT MUST NOT POLICE ITSELF. A speed trap pulls over any traffic car above the limit and a
cruiser retargets onto the nearest thing that is moving; a patrol car is exempt from both, or
the force spends the run arresting itself.
"""
import sys, threading, http.server, socketserver, functools
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from harness import launch_chromium, console_utf8
from playwright.sync_api import sync_playwright

console_utf8()
handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
srv = socketserver.TCPServer(('127.0.0.1', 0), handler)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = f'http://127.0.0.1:{PORT}'


def boot(b, pursuit):
    """A fresh road, with HOT PURSUIT on or off, stopped and ready."""
    ctx = b.new_context(viewport={'width': 480, 'height': 900})
    page = ctx.new_page()
    errs = []
    page.on('pageerror', lambda e: errs.append(str(e)))
    page.goto(f'{BASE}/games/sw/interstate.html', wait_until='load')
    try:
        page.wait_for_function(
            '() => navigator.serviceWorker && navigator.serviceWorker.controller', timeout=5000)
        page.wait_for_timeout(1200)
    except Exception:
        pass
    page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
    page.click('[data-act="play"]')
    page.wait_for_timeout(400)
    if pursuit:
        page.click('[data-act="chase"]')     # the switch, through the real menu
        page.wait_for_timeout(200)
    page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
    page.click('[data-act="drive"]')
    page.wait_for_timeout(1500)
    return ctx, page, errs


def drive_past(page, frac, dz=2000, ticks=90):
    """Put a patrol ahead, hold `frac` of top speed, and go by it.

    SAMPLED THROUGHOUT, not read at the end. A cruiser that engages and is then left
    behind is culled 34,000 units back, so a reading taken after the drive can report
    nothing chasing on a run where a chase certainly started. What matters is whether one
    began, and the moment it began is the only place to see it.
    """
    page.evaluate("() => { window.__road.traffic.length = 0; }")
    page.evaluate('(d) => window.__road.placePatrol(d)', dz)
    before = page.evaluate("() => window.__road.patrols()")['woken']
    chasing, passed = 0, 0
    for _ in range(ticks):
        page.evaluate('(f) => window.__road.setSpd(f * window.__road.MAX_SPD)', frac)
        page.wait_for_timeout(100)
        st = page.evaluate("() => window.__road.patrols()")
        chasing = max(chasing, st['chasing'])
        # a patrol still in the traffic array but BEHIND the player has been gone by
        passed = max(passed, sum(1 for c in st['cars'] if c['z'] < -200))
    st = page.evaluate("() => window.__road.patrols()")
    st['engaged'] = st['woken'] - before
    st['limit'] = page.evaluate("() => window.__road.speedLimit()")
    st['chasing'] = chasing
    # engaging IS passing: the car leaves the traffic array at the moment it happens
    st['passed'] = passed + st['engaged']
    return st


def main():
    bad = 0

    def ok(cond, label, detail=''):
        nonlocal bad
        if not cond:
            bad += 1
        print(f'  {"ok  " if cond else "FAIL"}  {label}' + (f'   {detail}' if detail else ''))

    print('patrol-test  .  traffic until you give it a reason')
    with sync_playwright() as p:
        b = launch_chromium(p, headless=True,
                            args=['--mute-audio', '--autoplay-policy=no-user-gesture-required'])

        # ---- IT IS ON THE ROAD AT ALL -------------------------------------------
        ctx, page, errs = boot(b, pursuit=True)
        # THE SPEED IS HELD, and that is not a detail. `setSpd` once lets the car coast to
        # a stop, and a stopped player generates no waves - the first version of this check
        # reported no patrols at all on an engine that was spawning them perfectly well.
        # UNDER THE LIMIT on purpose too, so nothing engages and gets taken out of traffic
        # while this is counting what is IN traffic.
        # SIGHTINGS OVER THE WHOLE DRIVE, not the count at one moment. A patrol is a
        # small share of the traffic and only one is usually on the road at a time, so
        # "how many right now" is a coin toss and asserting on it is asserting on the road.
        seen, met, minds = 0, 0, set()
        for _ in range(180):
            page.evaluate('() => window.__road.setSpd(0.30 * window.__road.MAX_SPD)')
            page.wait_for_timeout(250)
            st = page.evaluate("() => window.__road.patrols()")
            n = st['patrolling']
            seen = max(seen, n)
            met = page.evaluate("() => window.__road.patrolsMade()")
            # GATHERED AS WE GO. Reading the drivers at the END asks about whatever
            # happens to be on the road in that one frame, and usually that is nothing -
            # the check reported "none on the road to read" and passed, which is a check
            # that proves nothing while looking like it proved something.
            for c in st['cars']:
                minds.add(c['mind'])
        # HOW MANY THE ROAD HAS MADE, not how many are standing there. With a four per
        # cent share and one usually out, the instantaneous count is luck: this read 128
        # on one run and ZERO on the next, on an engine spawning them perfectly well.
        ok(met > 0, 'a patrol car turns up in ordinary traffic',
           f'{met} put on the road over 45s, at most {seen} out at once')

        # ---- AND IT DRIVES LIKE TRAFFIC, NOT LIKE A CHASE ------------------------
        print(f'  ..    drivers seen at the wheel of one: {sorted(minds)}')
        # AND IF NONE HAPPENED TO BE IN VIEW WHEN THE DRIVERS WERE READ, one is placed.
        # Reading nothing and passing is the vacuity this file already had once.
        if not minds:
            page.evaluate("() => window.__road.placePatrol(3000)")
            page.wait_for_timeout(300)
            for c in page.evaluate("() => window.__road.patrols()")['cars']:
                minds.add(c['mind'])
        ok(bool(minds) and minds == {0},
           'and a Civilian is driving it, so it cruises at the limit',
           f'minds seen {sorted(minds)}, where Civilian is 0'
           if minds else 'no patrol was ever read, so this proved nothing')
        ctx.close()

        # ---- PURSUIT OFF: PASSING IT AT SPEED MUST DO NOTHING --------------------
        # THE CASE THAT CATCHES A LAZY IMPLEMENTATION. Everything else about a patrol
        # works identically with the switch off, so an engagement that forgets to ask
        # is invisible until you play with pursuit off and get chased anyway.
        ctx, page, errs2 = boot(b, pursuit=False)
        off = drive_past(page, 0.75)
        print(f"  ..    pursuit OFF, went by at 0.75 of top speed (limit {off['limit']})")
        ok(off['engaged'] == 0, 'with HOT PURSUIT off, blasting past a patrol does nothing',
           f"{off['engaged']} engaged, {off['chasing']} chasing")
        ctx.close()

        # ---- PURSUIT ON, UNDER THE LIMIT: STILL NOTHING --------------------------
        ctx, page, errs3 = boot(b, pursuit=True)
        # 0.38 AND NOT 0.30, AND THE DIFFERENCE IS THE WHOLE CHECK. A patrol cruises at
        # 0.34, so a player doing 0.30 never catches it and never passes it - the check
        # went green because nothing happened rather than because the limit was respected,
        # and it stayed green with the speed test taken out. 0.38 is under the 0.40 limit
        # and over the patrol's own pace, so the pass really happens and is really legal.
        legal = drive_past(page, 0.38)
        print(f"  ..    pursuit ON, went by at 0.38 of top speed, under the {legal['limit']} limit")
        ok(legal['passed'] > 0, 'the legal run actually GOT past the patrol',
           f"{legal['passed']} of the patrols placed were passed")
        ok(legal['engaged'] == 0, 'and going past one legally does nothing either',
           f"{legal['engaged']} engaged")

        # ---- PURSUIT ON, OVER THE LIMIT: IT ENGAGES ------------------------------
        fast = drive_past(page, 0.75)
        print(f"  ..    pursuit ON, went by at 0.75 of top speed")
        ok(fast['engaged'] > 0, 'but speeding past one starts a pursuit',
           f"{fast['engaged']} engaged, {fast['chasing']} now chasing")
        ok(fast['chasing'] > 0, 'and it is chasing you rather than merely gone',
           f"{fast['chasing']} cruisers on the road")

        # ================= AND ONLY AS FAST AS ITS OWN CAR =======================
        # Owner, 2026-09-07: "I want the police cruiser to have the same stats - the fact
        # that a supercar can outrun it is the point, and why the super cruiser exists."
        #
        # The chase used to clamp every cruiser to `AI_TOP`, a flat 180 of the player's
        # 200, and never asked the car what it could do: a chasing cruiser was measured at
        # 169mph while the CRUISER in the garage tops out at 142.
        #
        # THE INVARIANT IS CHECKED, NOT THE CEILING. Coaxing one cruiser up to its limit
        # means fighting the chase AI, which backs off, boxes, dodges and peels away for
        # reasons of its own - three attempts at that measured 64, 89 and 102mph and proved
        # nothing about the clamp. "No cruiser ever exceeds its own body's vmax" is the
        # property that actually matters, it holds over a whole pursuit, and it fails
        # immediately if the flat ceiling comes back.
        print('  ..    letting a real pursuit run, and watching what the cruisers do')
        page.evaluate("() => window.__road.heat(4)")
        page.evaluate("() => window.__road.earnSupers(true)")
        worst = {'cruiser': 0.0, 'superCruiser': 0.0}
        seen = {'cruiser': 0, 'superCruiser': 0}
        caps = None
        for _ in range(120):
            page.evaluate('() => { const R = window.__road;'
                          ' R.setSpd(0.99 * R.MAX_SPD); R.heat(4); }')
            page.wait_for_timeout(250)
            cs = page.evaluate("() => window.__road.copSpeeds()")
            caps = cs
            for kind in worst:
                if cs[kind]['fastest'] is not None:
                    worst[kind] = max(worst[kind], cs[kind]['fastest'])
                    seen[kind] = max(seen[kind], cs[kind]['n'])
        for kind, label in (('cruiser', 'CRUISER'), ('superCruiser', 'SUPERCRUISER')):
            cap, mph = caps[kind]['ceiling'], caps[kind]['mph']
            top = worst[kind]
            print(f'  ..    {label:13s} ceiling {cap:8.0f} ({mph}mph)   fastest seen {top:8.0f}'
                  f'   ({seen[kind]} on the road at most)')
            if seen[kind]:
                ok(top <= cap * 1.01,
                   f'a {label} never goes faster than the one you can drive',
                   f'{top:.0f} against its own ceiling of {cap:.0f}')
            else:
                ok(True, f'no {label} appeared, so nothing was measured of it', 'reported only')
        # AND THE TWO ARE NOT THE SAME CAR, which is the owner's whole reason for the
        # second one: a supercar outruns the cruiser, and the interceptor is the answer.
        ok(caps['superCruiser']['ceiling'] > caps['cruiser']['ceiling'] * 1.2,
           'and the interceptor is meaningfully faster than the patrol car',
           f"{caps['superCruiser']['mph']}mph against {caps['cruiser']['mph']}mph")

        # ================= AND THEY ONLY COME FROM BEHIND ========================
        # Owner, 2026-09-07: "I don't think they should spawn in front of you and come back
        # at you. They should only come from behind. The exception to this is when you pass
        # a speed trap or the cop sitting at a roadblock. And the cop at a roadblock never
        # chases you - that's just set dressing."
        #
        # THE RULE IS ASSERTED, NOT THE SPAWNERS. Reading the three that exist would go on
        # passing on the day a fourth is added in front of the car, which is the whole
        # shape of the thing being ruled out. Every cruiser records where it came in
        # relative to the player and which source made it.
        print('  ..    letting the road make police of every kind')
        page.evaluate("() => { const R = window.__road;"
                      " R.watchDraw(true); R.clearCopOrigins(); R.heat(4); }")
        for _ in range(160):
            page.evaluate('() => { const R = window.__road;'
                          ' R.setSpd(0.62 * R.MAX_SPD); R.heat(4); }')
            page.wait_for_timeout(200)
        origins = page.evaluate("() => window.__road.copOrigins()")
        by = {}
        for o in origins:
            by.setdefault(o['from'], []).append(o['dz'])
        for src in sorted(by):
            dzs = [d for d in by[src] if d is not None]
            print(f"  ..    {len(by[src])} from {src:8s} "
                  f"{'nearest ' + str(max(dzs)) if dzs else 'no distance recorded'}")
        ok(bool(origins), 'police of some kind appeared at all', f'{len(origins)} cruisers')
        # A TRAP IS PARKED AHEAD BY ITS NATURE and is the owner's own exception. Everything
        # else has to come in behind the car.
        ahead = [o for o in origins
                 if o['from'] not in ('trap', 'test') and (o['dz'] or 0) > 0]
        ok(not ahead, 'no cruiser is created in front of you except a parked trap',
           f'{len(ahead)} came in ahead: ' + ', '.join(
               f"{o['from']} at {o['dz']}" for o in ahead[:4]) if ahead else '')
        # AND THE ROADBLOCK'S CRUISER IS SET DRESSING. It is a part of the block and never
        # enters the cops array, so it cannot chase - this asserts it stays that way.
        rb = page.evaluate("""() => { const R = window.__road;
            R.forceRoadblock();
            const b = R.roadblocks()[0];
            return { panelsWithCop: b ? b.cops : 0,
                     copsNamedBlock: R.cops().filter(k => k.from === 'block').length }; }""")
        print(f"  ..    the roadblock has {rb['panelsWithCop']} cruiser standing at it")
        ok(rb['panelsWithCop'] >= 1, 'a roadblock has a cruiser at it', str(rb))
        ok(rb['copsNamedBlock'] == 0,
           'and it is set dressing - it never joins the pursuit',
           f"{rb['copsNamedBlock']} in the chase")

        # ---- AND NOTHING ARRIVES FROM UP THE ROAD (RLG-157, owner 2026-09-08) ---
        # "There are still police coming from up ahead." RLG-157 had no harness, which
        # is why it could go wrong silently after being proved once by hand.
        #
        # THE TWO WAYS IT HAPPENS NEED SEPARATING, because they have different fixes: a
        # cruiser can be BORN ahead of you, or it can be born behind and DRIVE in front.
        # So every cruiser is tagged the frame it first exists and two facts are kept -
        # where it arrived, and the furthest ahead it ever got.
        #
        # A SPEED TRAP IS PARKED AHEAD BY ITS NATURE and is the owner's own stated
        # exception, so a cop still in trap state is not counted. What IS counted is a
        # trap that has left its post: that is a moving police car, and where it started
        # moving is the whole question.
        #
        # THE THRESHOLD IS ONE CAR LENGTH. A patrol is promoted the frame you draw level
        # with it, which reads as +16 to +37 units - a tenth of a car - and calling that
        # "ahead" would fail an engine that is behaving exactly as ruled.
        WATCH = """() => {
          const R = window.__road;
          if(!window.__seen){ window.__seen = 0; window.__log = {}; }
          const pz = R.pos + R.PLAYER_Z;
          for(const k of R.cops()){
            if(k.__id === undefined){
              k.__id = ++window.__seen;
              window.__log[k.__id] = { born: Math.round(k.z - pz), from: k.from || '?',
                                       trap: !!k.trap, maxAhead: Math.round(k.z - pz) };
            }
            const e = window.__log[k.__id], dz = Math.round(k.z - pz);
            if(dz > e.maxAhead) e.maxAhead = dz;
          }
          return window.__log; }"""
        # ---- AND THE ROAD IS CLEARED FIRST, WHICH IT WAS NOT ------------------
        # THE WATCHER TAGS A CAR THE FIRST TIME IT SEES IT and calls that position its
        # birthplace. That is right for a car that arrives during the watch and wrong
        # for one that was already out there: a cruiser standing ahead of the player at
        # the first sample is recorded as having been BORN ahead, which is the exact
        # thing being asserted against. It passed for as long as the road happened to
        # be quiet at that moment, and started failing the day the traps were laid more
        # thickly - one cruiser reported "born +891 from trap" on an engine whose
        # arrivals were all correct. So the road is emptied and only genuine arrivals
        # are counted.
        page.evaluate("() => { const R = window.__road; R.copsClear();"
                      " R.clearCopOrigins(); }")
        page.evaluate("() => { const R = window.__road; R.setTimed(false);"
                      " window.__ah = setInterval(() => { R.heat(4);"
                      " R.setSpd(0.72 * R.MAX_SPD); }, 200); }")
        log = {}
        for _ in range(200):
            page.wait_for_timeout(150)
            log = page.evaluate(WATCH)
        page.evaluate("() => clearInterval(window.__ah)")
        CAR = 400
        rows = [r for r in log.values() if not r['trap']]
        born = [r for r in rows if r['born'] > CAR]
        drove = [r for r in rows if r['born'] <= CAR and r['maxAhead'] > CAR]
        print('      %d cruisers that were not parked traps: %d arrived ahead, %d drove ahead'
              % (len(rows), len(born), len(drove)))
        for r in born[:4]:
            print('        born %+d from %s' % (r['born'], r['from']))
        ok(len(rows) >= 4, 'there were cruisers to watch', '%d seen' % len(rows))
        ok(not born, 'no police arrive from up the road',
           '; '.join('%+d from %s' % (r['born'], r['from']) for r in born[:4]))
        # PRINTED, NOT ASSERTED, AND THE REASON MATTERS. This was written while hunting
        # arrivals from up the road and it tests the wrong thing: RLG-158 has a cruiser
        # that has caught you take a station AHEAD and run slightly under your speed, to
        # slow you into a bust. That is the owner's own request, so a cruiser getting in
        # front of you is a feature and this line was failing on it - one born 589 behind
        # reached 515 ahead, which is the box forming exactly as designed. What the
        # complaint was about is where they ARRIVE, and that is the assertion above.
        print('      (%d of %d arrived behind and later got in front - that is the box'
              ' of RLG-158, not an arrival)' % (len(drove), len(rows)))

        # ---- AND A CRUISER WORKING SOMEBODY ELSE KEEPS THEM (owner, 2026-09-08) --
        # "I don't think every cruiser should just inherently switch its targeting to
        # you just because you exist and you are also speeding half a mile behind them."
        #
        # THE DISTANCE HALF IS WHAT IS ASSERTED HERE. A cruiser is put half a mile up
        # the road with a real traffic car as its target, and the player drives past
        # well over the limit: it must keep the car it already has.
        #
        # THE MARGIN HALF - that going by at a similar speed does not take it off
        # somebody - is IMPLEMENTED AND NOT ASSERTED, and the reason is written here
        # rather than left to be rediscovered. Staging it needs the player held a few
        # miles an hour above a traffic car, and both ends fight it: `setSpd` is
        # overwritten by the player's own acceleration between ticks, and the traffic
        # AI drives the NPC's speed toward its own cruise whatever is written to it.
        # Asking for a 4mph gap produced 34. It was checked by hand against the
        # decision's own inputs instead.
        KEEP = """([dz]) => {
          const R = window.__road;
          clearInterval(window.__hold);
          const pz = R.pos + R.PLAYER_Z;
          R.copsClear(); R.heatSet(0);
          const npc = R.traffic[0];
          if(!npc) return false;
          npc.mind = 1; npc.z = pz + dz + 600; npc.x = 0.30;
          /* ---- STAGED AS A COMMITTED CRUISER (RLG-173) ------------------
             `engaged` and `tgt` are the commitment, and a hand-built cop without
             them is a state the engine can no longer produce: a car holding a
             target that has not chosen it. Staged that way this check measured
             a cruiser making its FIRST choice with the player speeding past,
             which it is entitled to take. The claim is about a cruiser that has
             already chosen, so the staging has to be one. */
          const k = { z: pz + dz, x: 0.30, spd: npc.spd, wreck: 0, ang: 0, grace: 9,
                      cool: 0, side: 1, w: 0.27, len: 400, phase: 0, dmg: 0,
                      from: 'test', onPlayer: false, tz: npc.z, tx: npc.x,
                      tSpd: npc.spd, retarget: 0,
                      tgt: npc, engaged: true, commits: 1 };
          R.cops().push(k);
          window.__k = k;
          window.__hold = setInterval(() => {
            R.setSpd(0.80 * R.MAX_SPD);
            k.z = R.pos + R.PLAYER_Z + dz; k.grace = 9;
            npc.z = k.z + 600; npc.x = 0.30; npc.mind = 1;
          }, 8);
          return true; }"""
        staged = page.evaluate(KEEP, [42000])
        took = False
        if staged:
            for _ in range(30):
                page.wait_for_timeout(120)
                if page.evaluate("() => window.__k.onPlayer === true"):
                    took = True
                    break
            page.evaluate("() => clearInterval(window.__hold)")
        print('      a cruiser half a mile up the road, working an NPC, you at 160mph'
              ' -> %s' % ('TOOK YOU' if took else 'kept the NPC'))
        ok(staged, 'the scene could be staged', 'no traffic on the road')
        ok(not took, 'a cruiser working somebody else does not switch to you from'
                     ' half a mile away')

        errs = errs + errs2 + errs3 + page.evaluate("() => []")
        ok(errs == [], 'no page errors', errs[0][:100] if errs else '')
        ctx.close()
        b.close()
    srv.shutdown()
    print(f"\n  {'a patrol is traffic until you earn it' if not bad else str(bad) + ' FAILURES'}")
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
