#!/usr/bin/env python3
"""AMBULANCE TEST - it is on the road, it is a van's size, and it is quicker than one.

    .venv/Scripts/python tools/ambulance-test.py

Owner, 2026-09-07: "It's a standard traffic vehicle in nonemergency mode... let's make the
ambulance a little bit faster than the van."

BEFORE THIS THE AMBULANCE COULD NOT BE MET. It had a body record, a rig, a light bar, a
siren and a place in the garage, and neither of the two traffic tables listed it - so the
only way to see one was to drive it. That is not a bug in the spawner; it was never in it.

WHAT THIS ASSERTS:

  * an ambulance actually turns up in traffic, within a reasonable drive
  * it is a VAN's size, because it is a van - the size chains used to be written out in
    three places and this is the check that they now agree
  * it is quicker than the van in BOTH speed tables, which is the owner's ruling and the
    thing that would rot silently: `TYPE_VMAX` is what it does as traffic and `BODY.vmax`
    is what it does in your hands, and a vehicle that disagrees with itself about its own
    top end is the fault RLG-042 exists to stop

THE SPAWN IS A ROLL, so the first assertion is about a drive long enough for two per cent
to show rather than about one wave. If it ever goes red on a short road, lengthen the drive
before touching the share - and say so in the record.
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

SECONDS = 45


def main():
    bad = 0

    def ok(cond, label, detail=''):
        nonlocal bad
        if not cond:
            bad += 1
        print(f'  {"ok  " if cond else "FAIL"}  {label}' + (f'   {detail}' if detail else ''))

    print('ambulance-test  .  it is on the road, and it is a quicker van')
    with sync_playwright() as p:
        b = launch_chromium(p, headless=True,
                            args=['--mute-audio', '--autoplay-policy=no-user-gesture-required'])
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
        page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
        page.click('[data-act="drive"]')
        page.wait_for_timeout(1500)

        # ---- THE TWO SPEED TABLES, READ TOGETHER --------------------------------
        amb = page.evaluate("() => window.__road.topOf('ambulance')")
        van = page.evaluate("() => window.__road.topOf('van')")
        print(f"  ..    top end   ambulance traffic {amb['traffic']} garage {amb['garage']}"
              f"   .   van traffic {van['traffic']} garage {van['garage']}")
        ok(amb['traffic'] is not None and van['traffic'] is not None
           and amb['traffic'] > van['traffic'],
           'as traffic, the ambulance is quicker than the van',
           f"{amb['traffic']} against {van['traffic']}")
        ok(amb['garage'] is not None and van['garage'] is not None
           and amb['garage'] > van['garage'],
           'and in your hands too, so the vehicle does not disagree with itself',
           f"{amb['garage']} against {van['garage']}")

        # ---- AND IT IS ACTUALLY OUT THERE ---------------------------------------
        page.evaluate("() => window.__road.setSpd && window.__road.setSpd(7000)")
        seen, sizes = {}, {}
        for _ in range(SECONDS * 4):
            page.wait_for_timeout(250)
            rows = page.evaluate(
                "() => window.__road.traffic.map(c => [c.type, c.w, c.len, !!c.fromBehind])")
            for t, w, ln, behind in rows:
                seen[t] = seen.get(t, 0) + 1
                sizes[t] = (w, ln)
        met = sorted(seen)
        print(f'  ..    bodies met over {SECONDS}s: {met}')
        ok('ambulance' in seen, 'an ambulance turns up in ordinary traffic',
           f"seen on {seen.get('ambulance', 0)} samples" if 'ambulance' in seen
           else 'none in the whole drive')
        if 'ambulance' in sizes and 'van' in sizes:
            ok(sizes['ambulance'] == sizes['van'],
               'and it is a van\'s size, because it is a van',
               f"ambulance {sizes['ambulance']} against van {sizes['van']}")
        else:
            ok(False, 'and it is a van\'s size, because it is a van',
               'never met both bodies, so nothing was compared')
        # ================= AND THE ONE THAT IS ON A CALL =========================
        # Owner, 2026-09-07: "there's a chance for it to spawn behind you in emergency
        # mode. It's given the OUTLAW personality so it wants to go as fast as possible and
        # the siren works just like the police version as far as moving people out of the
        # way." Plus, later: "the police will not try to engage an ambulance."
        print('  ..    calling one out')
        page.evaluate("() => window.__road.setSpd && window.__road.setSpd(5000)")
        called = page.evaluate("() => window.__road.callAmbulance()")
        em = page.evaluate("() => window.__road.emergency()")
        ok(called and em['count'] >= 1, 'an ambulance can be called out and it is on the road',
           f"{em['count']} on a call")
        top = page.evaluate("() => window.__road.topOf('ambulance').traffic")
        maxs = page.evaluate("() => window.__road.MAX_SPD")
        if em['cars']:
            c = em['cars'][0]
            print(f"  ..    it is {c['z']} behind you, doing {c['spd']}, mind {c['mind']}")
            # RACER is 2 in the personality enum. It wants everything the vehicle has, and
            # the VEHICLE is what caps it - a personality that made a car faster would be
            # the fault RLG-042 was written to stop.
            ok(c['mind'] == 2, 'it is driven by a Racer, so it wants everything the van has',
               f"mind {c['mind']}, where Racer is 2")
            ok(abs(c['spd'] - top * maxs) < top * maxs * 0.02,
               "and it is doing the vehicle's own ceiling rather than a special one",
               f"{c['spd']} against the ambulance's {round(top * maxs)}")
        else:
            ok(False, 'it is driven by a Racer', 'nothing was called out')
            ok(False, "and it is doing the vehicle's own ceiling", '')

        # THE SIREN MOVES PEOPLE. `scattered` counts cars that have ACTUALLY moved over -
        # not cars that were asked - so this is the siren doing its job rather than the
        # call being made. Read as a delta, because your own horn adds to the same counter.
        #
        # THIS WAS REPORTED AND NOT ASSERTED FOR ONE BUILD. The ambulance could not get past
        # the player: it came up behind, decided to change lane, put its indicator on - and
        # the merge decision re-ran every frame and reset the signalling wait before it could
        # elapse, so a car that SIGNALS never actually moved. It sat behind you at your speed
        # for ever, and with nothing ahead of it in its own line there was nobody for the
        # siren to move. That was a fault every signalling car had, not one in the ambulance.
        # Fixed, and this is an assertion again.
        before = page.evaluate("() => window.__road.scattered()")
        for _ in range(24):
            page.wait_for_timeout(250)
            page.evaluate("() => window.__road.setSpd(4200)")
        after = page.evaluate("() => window.__road.scattered()")
        moved = page.evaluate("() => window.__road.emergency()")
        print(f'  ..    cars that moved over while it came through: {after - before}')
        print(f"  ..    where it got to: {moved['cars']}")
        ok(after - before > 0, 'the siren actually moves traffic out of the way',
           f'{after - before} cars changed lane')
        # AND IT GOT PAST YOU, which is the owner's Racer ruling in one number: "it shouldn't
        # queue up behind anybody, it should always work to get around obstacles and continue
        # as fast as it can". It starts about 3,000 behind; if it is still behind you after
        # six seconds it is queueing.
        z = moved['cars'][0]['z'] if moved['cars'] else None
        ok(z is not None and z > 0,
           'and it worked its way PAST you rather than queueing behind you',
           f'{z} ahead' if z is not None else 'it is no longer on the road')

        # AND THE POLICE LEAVE IT ALONE. A cruiser retargets onto the nearest thing over
        # 0.44 of MAX_SPD and an emergency ambulance is faster than that BY DESIGN, so
        # without the exemption a patrol would drop a real pursuit to chase the ambulance
        # it was making way for. Trap arming is the other half and is exempted with it.
        chase = page.evaluate("""() => {
            const st = window.__road.pursuit ? window.__road.pursuit() : null;
            return st ? st.chasing : 0; }""")
        amb = page.evaluate("() => window.__road.emergency()")
        print(f'  ..    cruisers chasing anything: {chase}, ambulances still on a call: '
              f"{amb['count']}")
        ok(True, 'reported, not asserted: a pursuit needs heat and this run may have none')

        ok(errs == [], 'no page errors', errs[0][:100] if errs else '')
        ctx.close()
        b.close()
    srv.shutdown()
    print(f"\n  {'the ambulance is on the road' if not bad else str(bad) + ' FAILURES'}")
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
