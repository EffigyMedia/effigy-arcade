#!/usr/bin/env python3
"""WHEEL ANGLE TEST - the rim follows the INPUT to the front wheels, not the forces on the car.

    .venv/Scripts/python tools/wheel-angle-test.py
    .venv/Scripts/python tools/wheel-angle-test.py --falsify

RLG-298, owner 2026-09-20: "the steering wheel rotates based on the movement of the car e.g. all
the forces acting upon it, but it should only follow the inputs to the front wheels", with "some
force feedback based on the friction of the road, coming back up through the tires through the
steering column."

WHY THE OBVIOUS CHECK PROVES NOTHING. Under a first-order lag the car's lateral VELOCITY is very
nearly the outstanding lateral ERROR times a constant - `playerX` chases the aim at `STEER.snap`,
so velocity is about 14 times the error. The two models therefore agree, up to a gain, on every
ordinary lane change: both wind on when you ask, both saturate on a snatch, both unwind to
straight as the car arrives. A harness that steers and watches the rim move scores a pass on
either one.

WHAT SEPARATES THEM IS A FORCE THE DRIVER DID NOT ASK FOR. Every other force in this engine -
the corner's push, the wet road's carry - is applied to `targetX`, so it moves the aim and the car
together and both models answer it the same way. A SHUNT does not: it moves the car across the
road and leaves the aim where it was. A rim driven by the car's movement follows the shove; a rim
driven by the demand turns the OTHER way, because the car now has to be steered back. That is a
SIGN, which cannot come out right by accident, and it is question 1.

  1. THE FRAME A SHOVE LANDS ON TURNS THE RIM THE OTHER WAY. `API.shove` moves the car right with
     the thumb still. THE RECOVERY PROVES NOTHING and the first version of this check was written
     against it: the car is steered back LEFT, so a rim reading the car's movement goes left as
     well, and that version passed its own falsify arm with the old wheel served back. What
     separates the two models is the ONE frame on which the car has been moved and has not yet
     been steered back - the movement model turns RIGHT there and the demand model turns LEFT. So
     the reading comes from `API.wheelTrace`, which the engine fills one row per STEP. A frame
     carries two steps here, and a reading taken per frame folds the flick into the recovery.

  2. THE RIM IS STRAIGHT WHEN THE CAR IS SETTLED ON A DRY ROAD. Without this, question 1 passes
     on a build where the rim is stuck at full left lock for any reason at all.

  3. PINNED AGAINST THE SHOULDER WITH THE THUMB STILL ASKING FOR MORE, NOTHING IS BEING STEERED.
     This is the ORIGINAL defect the movement model was introduced to fix, and it must stay fixed:
     the aim and the car clamp to the same edge, so the demand is zero there. It is the INPUT term
     that is read, not the whole rim - the car is off the tarmac at the shoulder and the verge is
     the loudest feedback in the engine, so reading the rim would score that shiver as steering.
     The rim itself is checked separately, against the ceiling a shiver may not pass.

  4. A ROAD WITH NOTHING LEFT IN IT SHIVERS THE RIM AND A DRY ONE DOES NOT - and the shiver stays
     small enough that it cannot be read as steering. Its own falsifier runs inside this question:
     with `WHEEL.grain` served at zero through `API.wheelModel`, the snow arm must go quiet. A
     feedback check that cannot be switched off is not evidence that feedback is what it measured.

Run with `--falsify` to serve the engine with the OLD movement-driven wheel put back. Question 1
must fail - and questions 2, 3 and 4 must still be judged on their own, because a falsify arm that
takes everything down with it says nothing about which check was doing the work.

Exit code 0 if every check passed, 1 otherwise.
"""
import argparse
import functools
import http.server
import importlib.util
import socketserver
import statistics
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from harness import console_utf8, launch_chromium, boot   # noqa: E402
from playwright.sync_api import sync_playwright            # noqa: E402

# the shove, in lanes. Two thirds of a lane is a hard rub down the side rather than a tap, and it
# is well inside EDGE_X from the middle of the road, so nothing clamps and hides the answer.
SHOVE = 0.66
# how much of full lock counts as the rim having actually turned. WHEEL.lock is 0.55 of a lane, so
# a 0.66 shove asks for more than full lock and the rim has a tenth of a second to get there.
TURNED = 0.45
# the rim eases toward the demand at WHEEL.ease, so one step at 60fps carries about a fifth of
# full lock. A tenth is comfortably clear of that and nowhere near zero.
FIRST = 0.10
# settled means settled: anything under this is the rim straight
STRAIGHT = 0.05
# the shiver must be a shiver. Above this it is being read as steering.
SHIVER_CAP = 0.10



def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--falsify', action='store_true',
                    help='serve the engine with the old movement-driven wheel; check 1 must fail')
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

    print('wheel-angle-test  .  the rim follows the input, not the forces on the car')
    if args.falsify:
        print('  FALSIFY: the movement-driven wheel is served back. Check 1 must fail.')
    try:
        with sync_playwright() as p:
            b = launch_chromium(p, headless=True, args=['--mute-audio'])
            ctx = b.new_context(viewport={'width': 480, 'height': 900})
            ctx.add_init_script(dt.INIT)
            if args.falsify:
                # the defect, put back in the ENGINE rather than in this file's idea of one. The
                # body of stepWheel's driver half is replaced by what it read before RLG-298: the
                # car's own lateral movement, scaled the way the old code scaled it.
                src = (ROOT / 'road.js').read_text(encoding='utf-8')
                need = '  const want = clamp((steerAim - playerX) / WHEEL.lock, -1, 1);'
                if need not in src:
                    raise SystemExit('[wheel-angle-test] --falsify cannot find the line it replaces')
                old = ('  if (window.__oldPrevX === undefined) window.__oldPrevX = playerX;\n'
                       '  const moved = (playerX - window.__oldPrevX) / Math.max(1/240, dt);\n'
                       '  window.__oldPrevX = playerX;\n'
                       '  const want = clamp(moved / 2.4, -1, 1);')
                src = src.replace(need, old, 1)
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

            api = pg.evaluate("() => !!(window.__probe.road && window.__probe.road.wheelModel "
                              "&& window.__probe.road.wheelTrace && window.__probe.road.shove "
                              "&& window.__probe.road.setLane)")
            if not api:
                ok(False, 'the engine answers wheelModel, wheelTrace, shove and setLane')
                b.close()
                print('  %d check(s) FAILED' % (bad or 1))
                return 1

            # ---- a straight, empty road at a held speed ---------------------------------------
            # THE RUN CLOCK KILLS ANY HARNESS THAT PARKS THE CAR, and this one holds it for well
            # over a minute across four questions - `setTimed(false)` is the affordance (RLG-125).
            # The traffic is parked off the road before every window, because the one thing that
            # would forge question 1 is a car shunting the player while nobody was looking.
            def clear():
                pg.evaluate("""() => { const R = window.__probe.road;
                    R.parkTraffic(9, 60000); R.copsClear(); R.clearWreck(); }""")

            pg.evaluate("""(a) => { const R = window.__probe.road;
                R.setTimed(false); R.holdCurve(0); R.setWet(0);
                R.holdSpd(R.MAX_SPD * a.pace); R.setLane(0); }""", {'pace': 0.6})
            clear()
            pg.wait_for_timeout(900)

            # ---- 2. settled and dry, the rim is straight -------------------------------------
            clear()
            pg.evaluate("() => window.__probe.road.wheelTrace(true)")
            pg.wait_for_timeout(900)
            calm = pg.evaluate("() => window.__probe.road.wheelTrace(false)")
            calm_pk = max((abs(r['turn']) for r in calm), default=9)
            ok(len(calm) > 20 and calm_pk < STRAIGHT,
               'settled on a dry road, the rim is straight',
               '%d step(s), peak %.3f of lock' % (len(calm), calm_pk))

            # ---- 1. a shove the driver did not ask for ---------------------------------------
            # ---- THE STEP THE SHOVE LANDS ON IS THE WHOLE QUESTION --------------------------
            # The recovery is NOT: with the aim still at zero the car is steered back LEFT, and a
            # rim driven by the car's movement reads that leftward travel and goes left too. Both
            # models therefore show a large left excursion for the tenth of a second the car takes
            # to come back, which is why the first version of this check passed its own falsify arm
            # and proved nothing. What separates them is the ONE step on which the car has just
            # been moved right and has not yet been steered back: the movement model reads a large
            # RIGHTWARD travel and turns right; the demand model reads a large leftward error and
            # turns left.
            #
            # AND IT HAS TO BE ONE STEP, NOT ONE FRAME. `FIXED` is 1/120 and a display is 60, so
            # `frameLoop` advances the world TWICE in an animation frame - always twice, not
            # sometimes - and a reading taken on `requestAnimationFrame` folds the movement
            # model's rightward flick and its leftward recovery into one number. Measured at
            # -0.014 where the step itself reads +0.12: sign right, evidence gone. So this reads
            # `API.wheelTrace`, which the engine fills on its OWN clock, one row a step.
            pg.evaluate("() => { const R = window.__probe.road; R.setLane(0); }")
            clear()
            pg.wait_for_timeout(500)
            pg.evaluate("() => window.__probe.road.wheelTrace(true)")
            pg.wait_for_timeout(120)
            pg.evaluate("(d) => window.__probe.road.shove(d)", SHOVE)
            pg.wait_for_timeout(400)
            shoved = pg.evaluate("() => window.__probe.road.wheelTrace(false)")
            # the step the shove landed on is the first one whose x jumped across the road
            land = next((i for i, r in enumerate(shoved) if r['x'] > 0.3), None)
            ok(land is not None, 'the shove actually moved the car',
               'furthest across %.3f of a lane' % max((r['x'] for r in shoved), default=0))
            if land is None:
                ok(False, 'the step the shove landed on turns the rim LEFT', 'no landing step')
            else:
                first = shoved[land]
                ok(first['turn'] < -FIRST,
                   'the step a shove RIGHT lands on turns the rim LEFT',
                   '%+.3f of lock at step %d of %d, car at %+.3f - the rim %s'
                   % (first['turn'], land, len(shoved), first['x'],
                      'answers the demand' if first['turn'] < -FIRST
                      else 'follows the car' if first['turn'] > FIRST
                      else 'barely moved'))
            # and the control: the rim really does carry lock while the car is being brought back.
            # This passes under BOTH models and is here to stop the question above passing on a
            # build where the wheel has stopped moving at all.
            pk = min((r['turn'] for r in shoved), default=0)
            ok(pk < -TURNED, 'and it carries real lock while the car comes back',
               'peak %+.3f of lock' % pk)

            # ---- 3. pinned on the shoulder, the thumb still asking ---------------------------
            pg.evaluate("() => { const R = window.__probe.road; R.setLane(0); }")
            clear()
            pg.wait_for_timeout(400)
            # ask for far more road than there is, over a second, and hold there
            pg.evaluate("() => window.__probe.road.steerOver(9, 1.0)")
            pg.wait_for_timeout(2200)
            pg.evaluate("() => window.__probe.road.wheelTrace(true)")
            pg.wait_for_timeout(800)
            pinned = pg.evaluate("() => window.__probe.road.wheelTrace(false)")
            pin_x = min((r['x'] for r in pinned), default=0)
            pin_in = max((abs(r['input']) for r in pinned), default=9)
            pin_pk = max((abs(r['turn']) for r in pinned), default=9)
            ok(pin_x > 0.9, 'the car really is pinned against the shoulder',
               'sitting at %.3f of a lane' % pin_x)
            # ---- IT IS THE INPUT TERM THAT MUST BE ZERO HERE, NOT THE RIM -------------------
            # The car is pinned at about 1.13 of a lane, which is PAST 1.0 and therefore off the
            # tarmac, so the verge is sending its own shiver up the column - `WHEEL.rough`, the
            # loudest source of feedback there is. Reading the whole rim here would score that
            # shiver as steering and fail a build that is behaving exactly as designed. The
            # question is whether the DEMAND is zero, which is what the original defect was about.
            ok(pin_in < STRAIGHT,
               'pinned on the shoulder with the thumb still asking, nothing is being steered',
               'peak input %.3f of lock' % pin_in)
            ok(pin_pk < SHIVER_CAP,
               'and the verge shivers the rim without taking it over',
               'peak %.3f of lock against a %.2f ceiling' % (pin_pk, SHIVER_CAP))

            # ---- 4. the road coming back up the column ---------------------------------------
            def shiver(wet, snow, grain):
                pg.evaluate("""(a) => { const R = window.__probe.road;
                    R.wheelModel({ grain: a.grain });
                    R.setWet(a.wet); R.setLane(0);
                    R.parkTraffic(9, 60000); R.copsClear(); R.clearWreck(); }""",
                            {'wet': wet, 'grain': grain})
                if snow:
                    pg.evaluate("() => { const R = window.__probe.road;"
                                " if (R.setSnow) R.setSnow(true); }")
                pg.wait_for_timeout(1400)
                pg.evaluate("() => window.__probe.road.wheelTrace(true)")
                pg.wait_for_timeout(1200)
                rows = pg.evaluate("() => window.__probe.road.wheelTrace(false)")
                vals = [r['turn'] for r in rows]
                return (statistics.pstdev(vals) if len(vals) > 5 else 0.0,
                        max((abs(v) for v in vals), default=0.0), len(vals))

            dry_sd, dry_pk, dry_n = shiver(0.0, False, 0.055)
            wet_sd, wet_pk, wet_n = shiver(1.0, True, 0.055)
            off_sd, off_pk, off_n = shiver(1.0, True, 0.0)
            ok(dry_n > 20 and wet_n > 20 and off_n > 20, 'all three arms were sampled',
               'dry %d, no-grip %d, grain off %d step(s)' % (dry_n, wet_n, off_n))
            ok(wet_sd > dry_sd * 3 and wet_sd > 0.002,
               'a road with nothing left in it shivers the rim',
               'no grip %.4f against dry %.4f' % (wet_sd, dry_sd))
            ok(wet_pk < SHIVER_CAP,
               'and the shiver is too small to be read as steering',
               'peak %.3f of lock against a %.2f ceiling' % (wet_pk, SHIVER_CAP))
            # the falsifier, run inside the question: switch the term off and it must go quiet
            ok(off_sd < wet_sd * 0.34,
               'FALSIFIER: with WHEEL.grain at zero the shiver goes',
               'off %.4f against on %.4f' % (off_sd, wet_sd))

            if errs:
                ok(False, 'page errors', errs[0][:140])
            b.close()
    finally:
        srv.shutdown()

    print('  %s' % ('all checks passed' if not bad else '%d check(s) FAILED' % bad))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
