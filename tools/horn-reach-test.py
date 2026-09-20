#!/usr/bin/env python3
"""HORN REACH TEST - the horn asks a few car lengths, and the siren still asks two seconds.

    .venv/Scripts/python tools/horn-reach-test.py
    .venv/Scripts/python tools/horn-reach-test.py --falsify

RLG-296, owner 2026-09-20, from the device: "The horn affects much too far forward! It should
only really be a few car lengths."

RLG-205 gave the siren two seconds of road and said in as many words that it widened the HORN
too, "which is intended rather than incidental - they are one function". The owner has driven
that and ruled against it for the horn alone, so the two reaches have parted. THIS HARNESS
EXISTS TO PROVE THEY PARTED RATHER THAN BOTH GOT SHORTER, which is the one way this change can
quietly go wrong - a siren that no longer clears the road would be a real loss and nothing in
the windscreen would say so.

WHAT IS MEASURED IS THE LOOP'S OWN GATE, not whether a car moved. `scatter` rolls 40% against
a driver's `obedience`, which starts at the personality's own value and falls with every
refusal, so a car well inside the reach legitimately stays put most of the time - traffic-test
records that over 40 presses only 6 were ever even in range. `API.scatterStat` counts what the
loop REJECTED and why: with exactly one car on the road, `far` rises by one when that car was
outside the window and stays put when it was inside. That is the number this ruling is about.

  1. A CAR A FEW LENGTHS AHEAD IS ASKED AND ONE FURTHER UP THE ROAD IS NOT. One car is parked
     in the player's own line at each distance in turn and the horn is sounded once.

  2. AND THE STEP IS WHERE THE RULING PUT IT. The nearest distance that is refused must sit
     just past the stated reach rather than anywhere at all, which is what separates "the horn
     was shortened" from "the horn stopped working".

  3. THE SIREN IS UNTOUCHED. Two seconds of road at the speed being driven, which at the test
     speed is several times the horn's. THIS ONE IS A FORMULA READ AND NOT A DRIVE, and it is
     labelled as one: `API.sirenReach` returns what the siren would ask for, and no car is
     moved to confirm it. It is here because the alternative - putting the player in a police
     car and turning the bar on - needs a seeded save and a debug unlock, and the thing at risk
     is the NUMBER rather than the plumbing, which has not been touched.

Run with `--falsify` to serve the engine with the horn taking the siren's reach again, which is
the behaviour the owner reported. Questions 1 and 2 must fail and question 3 must still pass -
the siren was never the thing that changed.

Exit code 0 if every check passed, 1 otherwise.
"""
import argparse
import functools
import http.server
import importlib.util
import socketserver
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from harness import console_utf8, launch_chromium, boot, until   # noqa: E402
from playwright.sync_api import sync_playwright            # noqa: E402

# how far ahead of the player's nose the parked car is put, in world units. `scatter` ignores
# anything nearer than 120, so the closest here is well clear of that floor.
DISTANCES = (400, 800, 1400, 1800, 3000, 8000, 16000)
# the speed the run is held at. High enough that the siren's two seconds is far longer than the
# horn's few lengths, which is the whole point of question 3.
PACE = 0.55

PRESS = """() => {
  const b = document.getElementById('horn');
  b.dispatchEvent(new PointerEvent('pointerdown', {bubbles:true}));
  b.dispatchEvent(new PointerEvent('pointerup', {bubbles:true}));
}"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--falsify', action='store_true',
                    help="serve the engine with the horn back on the siren's reach")
    args = ap.parse_args()
    console_utf8()

    dt_path = ROOT / 'tools' / 'drive-test.py'
    spec = importlib.util.spec_from_file_location('dt', dt_path)
    dt = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dt)

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
    srv = socketserver.TCPServer(('127.0.0.1', 0), handler)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    bad = 0

    def ok(cond, label, detail=''):
        nonlocal bad
        if not cond:
            bad += 1
        print('  %s  %s%s' % ('ok  ' if cond else 'FAIL', label,
                              ('   ' + detail) if detail else ''))

    print('horn-reach-test  .  the horn asks a few car lengths, the siren asks two seconds')
    if args.falsify:
        print("  FALSIFY: the horn is served back on the siren's reach. Checks 1 and 2 must fail.")
    try:
        with sync_playwright() as p:
            b = launch_chromium(p, headless=True, args=['--mute-audio'])
            ctx = b.new_context(viewport={'width': 480, 'height': 900})
            ctx.add_init_script(dt.INIT)
            if args.falsify:
                # the defect put back in the ENGINE: the horn stops asking for its own reach and
                # takes the siren's, which is exactly what the owner reported from the device
                src = (ROOT / 'road.js').read_text(encoding='utf-8')
                need = ('  const reach = isHorn ? hornReach()\n'
                        '                      : sirenReach(fromSpd === undefined ? spd : fromSpd);')
                if need not in src:
                    raise SystemExit('[horn-reach-test] --falsify cannot find the line it replaces')
                src = src.replace(
                    need,
                    '  const reach = sirenReach(fromSpd === undefined ? spd : fromSpd);', 1)
                ctx.route('**/road.js', lambda route: route.fulfill(
                    status=200, content_type='application/javascript', body=src))
            pg = ctx.new_page()
            errs = []
            pg.on('pageerror', lambda e: errs.append(str(e)))
            boot(pg, 'http://127.0.0.1:%d/games/sw/interstate.html' % port)
            pg.wait_for_timeout(1200)
            pg.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
            pg.click('[data-act="play"]')
            pg.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
            pg.click('[data-act="drive"]')
            pg.wait_for_timeout(1500)

            need = ('hornReach', 'sirenReach', 'scatterStat', 'parkTraffic', 'setLane')
            have = pg.evaluate("(ns) => ns.every(n => typeof window.__probe.road[n] === 'function')",
                               list(need))
            if not have:
                ok(False, 'the engine answers the horn seam', ', '.join(need))
                b.close()
                print('  1 check(s) FAILED')
                return 1

            pg.evaluate("""(a) => { const R = window.__probe.road;
                R.setTimed(false); R.holdCurve(0); R.copsClear(); R.setWet(0);
                R.holdSpd(R.MAX_SPD * a.pace); R.setLane(0); }""", {'pace': PACE})
            # ---- WAIT FOR THE COUNT, AND READ THE SPEED RATHER THAN ASSUMING IT --------
            # `holdSpd` IS IGNORED WHILE THE CAR IS ON THE LINE, and the engine says so where
            # it happens: "held wins: a car on the line is not going anywhere, whatever a
            # harness asked for". What is measured instead is `startSpeed()`, a quarter of top
            # speed - a perfectly plausible held speed, which is what makes it dangerous. The
            # first version of this read the siren's reach there and compared it against
            # `MAX_SPD * PACE * 2`: 7667 against an expected 16866, which the check reported as
            # the siren having been shortened by this work. It had not been touched.
            want_spd = pg.evaluate("() => window.__probe.road.MAX_SPD") * PACE
            until(pg, "() => window.__probe.road.spdNow() > %d" % int(want_spd * 0.95),
                  timeout=25000, required=False)
            fast = pg.evaluate("() => ({ model: window.__probe.road.hornReach(),"
                               " spd: window.__probe.road.spdNow() })")
            model, at_spd = fast['model'], fast['spd']
            print()
            print('  WHAT THE TWO ARE ASKING FOR')
            print('      horn  %5d units  (%d car length(s) of %d)'
                  % (model['units'], model['cars'], model['carLen']))
            print('      siren %5d units  at a measured %d units a second'
                  % (model['siren'], at_spd))

            # ---- 1 and 2. which cars the horn examines ---------------------------------------
            print()
            print('  WHICH CARS THE HORN ASKS')
            asked = {}
            for dz in DISTANCES:
                # ---- THE CAR IS HELD STILL AND SO IS THE PLAYER ----------------------
                # The first version parked the car and drove at it. `parkTraffic` places the
                # car relative to the player's position AT THAT MOMENT, and at 55% of top
                # speed the player covers about 2,400 units in the 280ms before the horn
                # sounds - so a car parked four lengths ahead was BEHIND the bumper by the
                # time the loop looked at it, and the check read that as out of reach. The
                # horn's reach does not depend on speed, so holding the car at a standstill
                # costs the measurement nothing and removes the whole class of error.
                #
                # AND THE COOLDOWN HAS TO EXPIRE. `scatter` refuses outright while `hornCool`
                # is running, which is 0.55s - so every second press in the first version was
                # swallowed and reported `seen 0`, which read as out of reach as well.
                pg.evaluate("""(a) => { const R = window.__probe.road;
                    R.setTimed(false); R.setLane(0); R.copsClear(); R.holdSpd(0); }""", {})
                pg.wait_for_timeout(700)
                pg.evaluate("""(a) => { const R = window.__probe.road;
                    R.parkTraffic(0, a.dz, 'sedan'); R.scatterStat(true); }""", {'dz': dz})
                pg.wait_for_timeout(60)
                pg.evaluate(PRESS)
                pg.wait_for_timeout(200)
                st = pg.evaluate("() => window.__probe.road.scatterStat(true)")
                # `seen` counts every car the loop looked at across however many scatter calls
                # landed in the window; `far` counts the ones it threw out on distance. A car
                # inside the reach is one the loop got past.
                inside = st['seen'] > 0 and st['far'] < st['seen']
                asked[dz] = inside
                print('      %6d units (%4.1f car lengths)   seen %2d  far %2d   %s'
                      % (dz, dz / model['carLen'], st['seen'], st['far'],
                         'ASKED' if inside else 'out of reach'))

            near = [d for d in DISTANCES if d < model['units'] * 0.9]
            wide = [d for d in DISTANCES if d > model['units'] * 1.1]
            ok(all(asked[d] for d in near),
               'every car inside the stated reach is asked',
               'at %s units' % ', '.join(str(d) for d in near))
            ok(not any(asked[d] for d in wide),
               'and no car beyond it is',
               'at %s units' % ', '.join(str(d) for d in wide))
            first_out = next((d for d in DISTANCES if not asked[d]), None)
            ok(first_out is not None and abs(first_out - model['units']) < model['carLen'] * 2,
               'and the step is where the ruling put it, not just somewhere',
               'the nearest car refused sits at %s against a stated %d'
               % (first_out, model['units']))

            # ---- 3. and the siren is untouched ------------------------------------------------
            print()
            print('  AND THE SIREN IS UNTOUCHED')
            want = round(at_spd * 2.0)
            print('      the siren asks %d units; two seconds of road at the measured %d'
                  ' units a second is %d' % (model['siren'], at_spd, want))
            ok(abs(model['siren'] - want) < max(40, want * 0.02),
               'the siren still asks two seconds of road (a formula read, not a drive)',
               '%d against %d' % (model['siren'], want))
            ok(model['siren'] > model['units'] * 4,
               'and it reaches several times further than the horn',
               '%d against %d units' % (model['siren'], model['units']))

            if errs:
                ok(False, 'page errors', errs[0][:140])
            b.close()
    finally:
        srv.shutdown()

    print()
    print('  %s' % ('all checks passed' if not bad else '%d check(s) FAILED' % bad))
    print('  whether four car lengths is the right ask at 120mph is the owner call')
    print('  on a device - it is HORN_CARS, live through API.hornReach.')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
