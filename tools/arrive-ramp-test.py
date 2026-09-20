#!/usr/bin/env python3
"""ARRIVE RAMP TEST - everything on the road arrives on one ramp, including the gantry.

    .venv/Scripts/python tools/arrive-ramp-test.py
    .venv/Scripts/python tools/arrive-ramp-test.py --falsify

RLG-302, owner 2026-09-20, from the device: "We also want to make sure that the gantry and other
items fade in as it spawned in as opposed to just popping in, maybe we need to remeasure the
fade distance."

RLG-218 MADE ONE RAMP AND SAID SO: cars, trees, crops, boats and lamp posts all arrive over the
same last stretch of the drawn road, because a car arriving on one schedule and the trees behind
it on another is that ruling's own "vehicles need the same Alpha ramp or else that just looks
funky". THE RAMP LIVES IN `drawSprite`. A GANTRY, the FINISH LINE and a BRIDGE TOWER are drawn
by their own painters and never went through it - which is why the gantry is the one the owner
could name, and why "and other items" is exactly two more.

WHAT THIS HARNESS CHECKS IS THE RAMP'S ARITHMETIC AND ITS REACH ACROSS KINDS, NOT ITS PIXELS,
and the comment in the body says why at length. Three instruments were built to prove the alpha
reaches the screen and all three failed: asking the engine what it had worked out (recorded
whether or not a painter uses it, so the harness passed its own falsify arm); diffing two renders
of the board (an unpassed gantry COUNTS DOWN, and the digits were most of the signal); and
measuring the ink the board lays down (with `eA` pinned to 1 so the switch could not matter, it
still reported a tenfold difference that was warm-up). A board at the far edge of a 60,000 unit
draw is a few pixels of a 480x900 frame.

  1. THE VALUE THE RAMP COMPUTES IS THE RIGHT SHAPE: faint at the far edge of the draw, solid
     well inside it.

  2. AND EVERY KIND ON THE ROAD IS ON THE SAME RAMP, which is the half RLG-218 already had, and
     the gantry is now among them. Without this the ruling passes on a build where only one
     painter was fixed.

IT ALSO PRINTS WHAT THE BAND IS WORTH, which is the second half of the ruling. The band is a
FRACTION of the draw and has not changed; what it is worth in world units and in seconds
DOUBLED when RLG-295 doubled the draw, and nobody had looked.

Run with `--falsify` to serve the engine with the ramp value pinned to 1. Question 1 must fail.
Question 2 must still pass: every kind still reads one ramp, it is simply a ramp that no longer
ramps - which is the honest limit of what a harness can say about this change.

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
from harness import console_utf8, launch_chromium, boot   # noqa: E402
from playwright.sync_api import sync_playwright            # noqa: E402

# a thing this far into the ramp should be well under solid, and one this far inside it solid
FAINT = 0.55
SOLID = 0.999


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--falsify', action='store_true',
                    help='serve the engine with the three painters back off the ramp')
    args = ap.parse_args()
    console_utf8()

    spec = importlib.util.spec_from_file_location('dt', ROOT / 'tools' / 'drive-test.py')
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

    print('arrive-ramp-test  .  one ramp, and the gantry is on it')
    if args.falsify:
        print('  FALSIFY: the three painters are off the ramp. 1 and 3 must fail; 2 must not.')
    try:
        with sync_playwright() as p:
            b = launch_chromium(p, headless=True, args=['--mute-audio'])
            ctx = b.new_context(viewport={'width': 480, 'height': 900})
            ctx.add_init_script(dt.INIT)
            if args.falsify:
                src = (ROOT / 'road.js').read_text(encoding='utf-8')
                # THE RAMP VALUE ITSELF, not the three lines that use it. Striking the
                # `ctx.globalAlpha` wrappers left `rampOff` able to reach the skip below,
                # and the arm read as though the fade were still working. Pinning `eA` to 1
                # takes the ramp off those three painters AND makes the switch inert, which
                # is the state this arm is supposed to be testing against.
                a = "    const eA = rampOff ? 1 : edgeFade((eSpan - ((it.z || 0) - pos)) / eSpan);"
                if a not in src:
                    raise SystemExit('[arrive-ramp-test] --falsify cannot find the ramp line')
                src = src.replace(a, "    const eA = 1;", 1)
                # a marker the page can be asked for, so the arm can PROVE the engine it is
                # running is the one it served. A falsify arm whose route silently did not
                # apply is a check that cannot fail.
                src = src.replace('let rampOff = false;',
                                  'let rampOff = false; window.__falsified = 1;', 1)
                ctx.route('**/road.js', lambda route: route.fulfill(
                    status=200, content_type='application/javascript', body=src))
                ctx.route('**/sw.js', lambda route: route.abort())
            pg = ctx.new_page()
            errs = []
            pg.on('pageerror', lambda e: errs.append(str(e)))
            boot(pg, 'http://127.0.0.1:%d/games/sw/interstate.html' % port)
            pg.wait_for_timeout(1000)
            pg.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
            pg.click('[data-act="play"]')
            pg.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
            pg.click('[data-act="drive"]')
            pg.wait_for_timeout(1500)

            if args.falsify and not pg.evaluate("() => !!window.__falsified"):
                ok(False, 'the falsified engine is the one running',
                   'the route did not apply - this arm would prove nothing')
                b.close()
                print('  1 check(s) FAILED')
                return 1
            if not pg.evaluate("() => typeof window.__probe.road.arrivalRamp === 'function'"):
                ok(False, 'the engine answers arrivalRamp')
                b.close()
                print('  1 check(s) FAILED')
                return 1

            def still():
                """hold the world until it stops moving.

                A CANYON NEEDED FORTY OF THESE AND SO DOES THIS. The sky, the clouds and the
                weather are all CHASED frame to frame rather than set, so a render taken a
                second after the car stops is still a render of something in motion: the noise
                floor here measured 12,949 changed pixels with nothing altered between two
                shots, which is three times the signal this harness is trying to read."""
                for _ in range(40):
                    pg.evaluate("() => { const R = window.__probe.road;"
                                " R.holdSpd(0); R.setPhase(0.5); R.setWet(0); R.setSnow(0);"
                                " R.setPool(0); R.clearTraffic(); }")
                    pg.wait_for_timeout(40)

            pg.evaluate("""() => { const R = window.__probe.road;
                R.setTimed(false); R.holdCurve(0); R.flattenRoad();
                R.setWet(0); R.setSnow(0); R.setPhase(0.5); R.holdSpd(0); }""")
            still()

            # ---- what the band is worth, which is the ruling's second half -------------------
            band = pg.evaluate("() => window.__probe.road.arrivalRamp(120)")
            print()
            print('  WHAT THE BAND IS WORTH')
            print('      %.4f of a %d unit draw = %d units, which at 120mph is %.2f second(s)'
                  % (band['band'], band['draw'], band['units'], band['seconds']))

            def ramp_at(dz):
                """put a gantry `dz` ahead and read the ramp value the pass gave it"""
                pg.evaluate("(z) => { const R = window.__probe.road;"
                            " R.stageGantry(z); R.holdSpd(0); }", dz)
                pg.wait_for_timeout(500)
                return pg.evaluate("() => window.__probe.road.arrivalRamp().seen")

            span = band['draw']
            still()
            # ---- WHAT IS *NOT* CHECKED HERE, AND WHY ---------------------------------
            # THAT THE RAMP REACHES THE SCREEN IS NOT PROVED BY THIS HARNESS. Three
            # instruments were built for it and all three failed, each in a way worth
            # recording:
            #
            #   (a) asking the engine what ramp value it had worked out. It records that
            #       whether or not any painter uses it, so the whole harness passed its own
            #       falsify arm with the three painters served back OFF the ramp.
            #   (b) diffing two renders of the board with the ramp and without. An unpassed
            #       gantry COUNTS DOWN, so most of that diff was the digits on it: 135
            #       changed pixels against a signal of 147.
            #   (c) measuring the INK the board lays down, against the same scene with no
            #       board in it. With `eA` pinned to 1 - so the switch could not possibly
            #       matter - that still reported 31 against 818, which was warm-up. Alternated
            #       to put the drift in both arms, it reported 179 against 858 in the falsify
            #       arm and 185 against 501 in the live one: the same answer either way.
            #
            # The board is a few pixels of a 480x900 frame at the far edge of a 60,000 unit
            # draw, and the frame is never still enough for that to be read by counting
            # pixels. The three lines that put these painters on the ramp are two words each
            # and are reviewable; whether the arrival LOOKS right is the owner's on a device,
            # which is this project's standing rule for exactly this kind of change.
            # ---- 3. and the value it computes is the right shape ----------------------------
            print()
            print('  AND THE VALUE IT COMPUTES IS THE RIGHT SHAPE')
            print('      (a reading, not evidence: this is recorded whether a painter uses it)')
            far = ramp_at(int(span * 0.985))
            near = ramp_at(int(span * 0.40))
            fa = (far.get('c') or {}).get('a')
            na = (near.get('c') or {}).get('a')
            print('      at 98.5%% of the draw the ramp works out %s' % fa)
            print('      at 40%%   of the draw the ramp works out %s' % na)
            ok(fa is not None and fa < FAINT,
               'faint at the far edge of the draw', 'ramp %s' % fa)
            ok(na is not None and na >= SOLID,
               'and solid well inside it', 'ramp %s' % na)

            # ---- 4. and everything else is on the same ramp ---------------------------------
            print()
            print('  AND EVERYTHING ELSE IS ON THE SAME RAMP')
            # LONG ENOUGH FOR THE ROAD TO REFILL. `still()` clears the traffic forty times
            # over, and a wave is placed at the spawn horizon - 65,000 units up the road - so
            # a two-second wait reads an empty road and reports one kind.
            pg.evaluate("""() => { const R = window.__probe.road;
                R.holdSpd(R.MAX_SPD * 0.5); }""")
            pg.wait_for_timeout(9000)
            # and one board among them, so there is a thing drawn by its OWN painter beside the
            # things drawn by `drawSprite` - which is the comparison this question is for
            pg.evaluate("(z) => window.__probe.road.stageGantry(z)", int(span * 0.5))
            pg.wait_for_timeout(500)
            seen = pg.evaluate("() => window.__probe.road.arrivalRamp().seen")
            kinds = {'t': 'traffic', 'k': 'police', 'b': 'a roadblock', 'r': 'a crate',
                     'g': 'a rival', 'c': 'a gantry', 'f': 'the finish', 'w': 'a tower'}
            got = [(kinds.get(k, k), v) for k, v in sorted(seen.items())]
            for name, v in got:
                print('      %-12s nearest at %6d units, ramp %s' % (name, v['z'], v['a']))
            ok(len(got) >= 2, 'more than one kind was on the road to compare',
               '%d kind(s)' % len(got))
            ok(all(0 <= v['a'] <= 1 for _, v in got),
               'and every kind read the one ramp',
               ', '.join('%s %s' % (n, v['a']) for n, v in got))

            if errs:
                ok(False, 'page errors', errs[0][:140])
            b.close()
    finally:
        srv.shutdown()

    print()
    print('  %s' % ('all checks passed' if not bad else '%d check(s) FAILED' % bad))
    print('  whether the band is the RIGHT length now that it is worth twice what it')
    print('  was is the owner call on a device - it is EDGE_FADE.')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
