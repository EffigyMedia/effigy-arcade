#!/usr/bin/env python3
"""GLASS FADE TEST - nothing on the road pops into or out of the mirror; it fades.

    .venv/Scripts/python tools/glass-fade-test.py
    .venv/Scripts/python tools/glass-fade-test.py --falsify

RLG-313, owner 2026-09-21: "Things shouldn't pop in or out in the mirror. I'd rather they faded
in."

A checkpoint board and a finish line are the two things on the road the glass can be made to
hold at a stated distance (`stageGantry`, `parkFinish`), and they are the two worst cases: each
spans the road, so it is wider than the pane the moment it is behind you, and it is dropped from
the glass whole when it passes `MIRROR_BACK`. For each, at a ladder of distances behind the car,
this reads the alpha the glass drew it at (`API.glassTrace`) and asks:

  1. IT ARRIVES: just behind the car it is drawn part-way, not whole.
  2. IT IS SOLID IN BETWEEN: from a few hundred units back to three quarters of the reach.
  3. IT LETS GO: in the last quarter of the reach it is drawn part-way, and less the farther.
  4. AND THE RAMP ONLY EVER GOES ONE WAY at each end, so it is a fade and not a flicker.

Run with `--falsify` to serve the engine with every item drawn solid. 1 and 3 must fail for both
objects; 2 must still pass, because it is the check that says the thing is there at all.

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

# units behind the car. MIRROR_BACK is 34,000, so its last quarter starts at 25,500.
ARRIVE = (260, 400)
SOLID = (1200, 8000, 20000, 25000)
LETGO = (29000, 32000, 33500)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--falsify', action='store_true', help='serve the engine with no glass fade')
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

    print('glass-fade-test  .  nothing pops into or out of the mirror')
    if args.falsify:
        print('  FALSIFY: every item is drawn solid. 1 and 3 must fail; 2 must not.')
    try:
        with sync_playwright() as p:
            b = launch_chromium(p, headless=True, args=['--mute-audio'])
            ctx = b.new_context(viewport={'width': 480, 'height': 900})
            ctx.add_init_script(dt.INIT)
            if args.falsify:
                src = (ROOT / 'road.js').read_text(encoding='utf-8')
                need = "    const gA = Math.min(glassFade(it.o.z), gBig ? glassArrive(it.o.z) : 1);"
                if src.count(need) != 1:
                    raise SystemExit('[glass-fade-test] --falsify cannot find its line')
                src = src.replace(need, "    const gA = 1;", 1)
                ctx.route('**/road.js', lambda route: route.fulfill(
                    status=200, content_type='application/javascript', body=src))
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
            need = ('glassTrace', 'stageGantry', 'parkFinish', 'watchDraw')
            if not pg.evaluate("(ns) => ns.every(n => typeof window.__probe.road[n] === 'function')",
                               list(need)):
                ok(False, 'the engine answers the fade seam', ', '.join(need))
                b.close()
                print('  1 check(s) FAILED')
                return 1
            pg.evaluate("""() => { const R = window.__probe.road;
                R.setTimed(false); R.holdCurve(0); R.holdSpd(0); R.flattenRoad(); R.setPhase(0.5);
                R.setWet(0); R.setSnow(0); R.setPool(0); R.clearTraffic();
                R.setBiomePair('DESERT', 'DESERT'); R.watchDraw(true); }""")
            pg.wait_for_timeout(2400)

            def alpha(kind, dz):
                if kind == 'c':
                    pg.evaluate("(d) => window.__probe.road.stageGantry(-d, true)", dz)
                else:
                    pg.evaluate("(d) => window.__probe.road.parkFinish(d)", dz)
                pg.wait_for_timeout(250)
                pg.evaluate("() => window.__probe.road.glassTrace(true)")
                pg.wait_for_timeout(300)
                t = pg.evaluate("() => window.__probe.road.glassTrace(false)")
                got = [e['a'] for e in t if e['kind'] == kind]
                return (sum(got) / len(got)) if got else None

            for kind, name in (('c', 'a checkpoint board'), ('f', 'the finish line')):
                print()
                print('  %s, HELD BEHIND THE CAR' % name.upper())
                seen = {}
                for dz in ARRIVE + SOLID + LETGO:
                    seen[dz] = alpha(kind, dz)
                    print('      %6d units back   drawn at %s'
                          % (dz, 'nothing' if seen[dz] is None else '%.3f' % seen[dz]))
                if kind == 'c':
                    pg.evaluate("() => window.__probe.road.parkGantry(null)")
                have = all(seen[d] is not None for d in ARRIVE + SOLID + LETGO)
                ok(have, '%s is in the glass at every distance asked' % name,
                   'missing at %s' % [d for d in seen if seen[d] is None] if not have else '')
                if not have:
                    continue
                ok(seen[ARRIVE[0]] < 0.5,
                   '1. just behind the car it arrives rather than appearing whole',
                   '%d back: %.3f' % (ARRIVE[0], seen[ARRIVE[0]]))
                ok(all(seen[d] > 0.97 for d in SOLID),
                   '2. and between, it is solid', str([round(seen[d], 3) for d in SOLID]))
                ok(seen[LETGO[-1]] < 0.5 and seen[LETGO[0]] < 1,
                   '3. and in the last quarter of the reach it lets go',
                   str([round(seen[d], 3) for d in LETGO]))
                up = [seen[d] for d in ARRIVE] + [seen[SOLID[0]]]
                down = [seen[SOLID[-1]]] + [seen[d] for d in LETGO]
                ok(all(a <= b + 1e-6 for a, b in zip(up, up[1:]))
                   and all(a >= b - 1e-6 for a, b in zip(down, down[1:])),
                   '4. and each ramp runs one way', 'up %s, down %s'
                   % ([round(v, 3) for v in up], [round(v, 3) for v in down]))

            if errs:
                ok(False, 'page errors', errs[0][:140])
            b.close()
    finally:
        srv.shutdown()

    print()
    print('  %s' % ('all checks passed' if not bad else '%d check(s) FAILED' % bad))
    print('  whether the arrival reads as smooth at speed is the owner call on a device.')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
