#!/usr/bin/env python3
"""CHECKPOINT PAY TEST - a gantry pays what the car's class is worth.

    .venv/Scripts/python tools/checkpoint-pay-test.py
    .venv/Scripts/python tools/checkpoint-pay-test.py --falsify table
    .venv/Scripts/python tools/checkpoint-pay-test.py --falsify inherit
    .venv/Scripts/python tools/checkpoint-pay-test.py --falsify start

RLG-235, which replaces the numbers of RLG-233. Owner, 2026-09-13: utility 30 seconds a gantry,
production 20, sports 15, super 15, from a 120-second start.

WHAT IS MEASURED IS THE CLOCK, not the table. Reading `CP_SECONDS` back and asserting it holds the
four numbers would test the change against a copy of itself. So this drives each car to a real
gantry and measures the seconds that actually land on the run clock.

  1. EACH GROUP IS PAID ITS OWN NUMBER, measured across a checkpoint on the road.
  2. THE POLICE ARE PAID AS THE CARS THEY ARE BUILT FROM. A CRUISER declares `raceClass: sports` and
     a SUPERCRUISER declares `super`, so they take their seconds through the record rather than
     through rows of their own.
  3. A FORMULA CAR IS PAID AS A SUPER. Formula has no league and no row; `CP_INHERITS` maps it.
  4. A RUN STARTS WITH 120 SECONDS. It is read just after the run starts, so the clock has already
     run down a little.

`--falsify` serves the engine with one part of the change put back, and says which rows must fail:
  table    the table is emptied, so every car is paid the default twenty. Every row fails except the
           production cars, whose ruled number IS twenty - this falsifier cannot see them.
  inherit  the formula mapping is removed. Only VECTOR fails, because formula falls to the default.
  start    the start is 60 again. Only the start check fails.
A falsifier that fails the wrong rows is as much a failure of this harness as one that fails none.

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

GAME = 'games/sw/interstate.html'
VEIL = '#veil:not(.hidden) '

# body, what the owner ruled it is worth, and why this row is in the list
CARS = [
    ('SALOON',       20, 'production'),
    ('COUPE',        20, 'production'),
    ('TUNER',        15, 'sports'),
    ('STALLION',     15, 'super'),
    ('CRUISER',      15, 'a sports saloon underneath - declared, not listed'),
    ('SUPERCRUISER', 15, 'a MATADOR underneath - declared, not listed'),
    ('VECTOR',       15, 'formula: no league, paid as a super'),
    ('VAN',          30, 'utility'),
]

START = 120

# What each falsifier replaces in road.js, and the checks it must fail. 'start' is the
# name of the start check; every other name is a body in CARS.
TABLE = 'const CP_SECONDS = { utility: 30, production: 20, sports: 15, super: 15 };'
FALSIFY = {
    'table':   (TABLE, 'const CP_SECONDS = {};',
                {'TUNER', 'STALLION', 'CRUISER', 'SUPERCRUISER', 'VECTOR', 'VAN'}),
    'inherit': ("const CP_INHERITS = { formula: 'super' };", 'const CP_INHERITS = {};',
                {'VECTOR'}),
    'start':   ('const CLOCK_START = 120,', 'const CLOCK_START = 60,',
                {'start'}),
}

# Drive each car over a gantry and return the seconds the clock actually gained. The
# checkpoints are laid two miles apart, so the player is put just short of one and walked
# over it - the same event a player triggers, rather than a function called by name.
PAY = r"""async (a) => {
  const R = window.__road;
  R.setBody(a.body);
  R.setTimed(true);
  /* ---- WALK FORWARD UNTIL A BOARD IS AHEAD, NEVER BACKWARD ----------------
     Two facts about how the road lays checkpoints, and between them they sank two
     earlier versions of this probe.

     A board is only laid once the car is within 90,000 units of it, and a mile is
     about 128,700 - so the first board sits at 257,400 and does not exist until the
     player passes 167,400. Jumping to 120,000 found nothing at all.

     AND THE COUNTER ONLY EVER MOVES FORWARD. `nextCP` is never rewound, so once one
     car has been jumped a long way up the road, jumping the next one BACK to a lower
     position lays no boards at all - the engine believes it has already placed them.
     A harness that stepped its own base position therefore went blind partway down
     the list, and did it to a different car on each run.

     So this only ever moves forward, and asks the engine after each step rather than
     working out where a board ought to be.
     -------------------------------------------------------------------- */
  let at = a.from, cp = null;
  for (let i = 0; i < 8 && cp === null; i++) {
    R.jumpTo(at);
    await new Promise(r => setTimeout(r, 140));
    cp = R.nextGantry();
    if (cp === null) at += 120000;
  }
  if (cp === null || cp === undefined) return { err: 'no board found by ' + Math.round(at) };
  R.setSpd(0);
  await new Promise(r => setTimeout(r, 60));
  const before = R.clock;
  R.jumpTo(cp + 800);
  await new Promise(r => setTimeout(r, 200));
  /* THE CLOCK IS ALSO RUNNING DOWN while this happens, so the difference is the award
     minus a fraction of a second. The awards are at least five apart, so a second of slack
     costs the check nothing, and claiming more precision than the instrument has would
     be the dishonest option. */
  return { gained: R.clock - before, at: cp };
}"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--falsify', choices=sorted(FALSIFY),
                    help='serve the engine with one part of the change put back')
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
    failed = set()   # the names of the checks that failed, for the falsifier to compare
    blocked = 0      # a check that could not run is never evidence, in either mode

    def ok(cond, label, detail='', name=None):
        nonlocal bad
        if not cond:
            bad += 1
            if name:
                failed.add(name)
        print('  %s  %s%s' % ('ok  ' if cond else 'FAIL', label,
                              ('   ' + detail) if (detail and not cond) else ''))

    print('checkpoint-pay  .  a gantry pays what the class is worth')
    if args.falsify:
        print('  FALSIFY %s: must fail exactly %s' % (
            args.falsify, ', '.join(sorted(FALSIFY[args.falsify][2]))))
    try:
        with sync_playwright() as p:
            b = launch_chromium(p, headless=True, args=['--mute-audio'])
            ctx = b.new_context(viewport={'width': 480, 'height': 900})
            ctx.add_init_script(dt.INIT)
            if args.falsify:
                src = (ROOT / 'road.js').read_text(encoding='utf-8')
                need, put, _ = FALSIFY[args.falsify]
                if need not in src:
                    raise SystemExit('[checkpoint-pay] --falsify cannot find %r' % need)
                src = src.replace(need, put, 1)
                ctx.route('**/road.js', lambda route: route.fulfill(
                    status=200, content_type='application/javascript', body=src))
            pg = ctx.new_page()
            errs = []
            pg.on('pageerror', lambda e: errs.append(str(e)))
            boot(pg, 'http://127.0.0.1:%d/%s' % (port, GAME))
            pg.wait_for_timeout(1600)
            pg.wait_for_selector(VEIL + '[data-act="play"]', timeout=10000)
            pg.click(VEIL + '[data-act="play"]')
            pg.wait_for_timeout(400)
            pg.click(VEIL + '[data-act="drive"]')
            pg.wait_for_timeout(1800)

            # The run is under two seconds of wall time old, and the engine's clock runs
            # slower than wall time here, so a 120 start reads just under 120. The floor is
            # far above the old 60, so the check cannot pass on the old start.
            begun = pg.evaluate('() => window.__road.clock')
            ok(START - 10 < begun <= START, 'a run starts with %d sec' % START,
               'it read %.1f' % begun, name='start')

            # ---- A CROSSING THAT DID NOT HAPPEN IS NOT AN ANSWER -------------------
            # A gain of zero means the board was already hit, or the jump landed the wrong
            # side of it. That is the instrument missing, not the engine paying nothing -
            # and reading it as an award prints "SALOON paid 0" and blames the product.
            # Watched happening: STALLION read 0.0 on one run and 10.0 on the next, on an
            # unchanged build. Each car gets three goes at a fresh board, and one that
            # never crosses is reported BLOCKED, which is not a pass and counts against
            # the run.
            #
            # THE STEP IS NOT ARBITRARY: boards are two miles apart, a mile is about
            # 128,700 units, and one is laid only once the car is within 90,000 of it. So
            # the next board is 257,400 further on and needs the player past 167,400 of
            # that. 175,000 clears it; 150,000 did not, and every car after the first read
            # "no gantry ahead".
            base = 200000
            SPACING = 175000
            for body, want, why in CARS:
                r, got, why_not = None, 0.0, 'no answer'
                for _ in range(3):
                    r = pg.evaluate(PAY, {'body': body, 'from': base})
                    if r and not r.get('err'):
                        base = r['at'] + SPACING
                        got = r['gained']
                        if got > 0:
                            break
                        why_not = 'the clock did not move, so nothing here is a reading'
                    else:
                        why_not = (r or {}).get('err', 'no answer')
                        base += SPACING
                    # the probe walks forward on its own; this only ever nudges the
                    # start of that walk, and never behind where the road has got to
                if got <= 0:
                    blocked += 1
                    ok(False, '%-13s BLKD  no board was crossed in three tries' % body,
                       why_not)
                    continue
                ok(abs(got - want) <= 1,
                   '%-13s pays %2d sec   (%s)' % (body, want, why),
                   'it paid %.1f' % got, name=body)

            if errs:
                blocked += 1
                ok(False, 'page errors', errs[0][:140])
            b.close()
    finally:
        srv.shutdown()

    if args.falsify:
        want = FALSIFY[args.falsify][2]
        good = failed == want and not blocked
        print('  %s' % ('the falsifier failed exactly the rows it should' if good else
                        'FALSIFIER WRONG: failed %s, expected %s, %d blocked'
                        % (sorted(failed) or 'nothing', sorted(want), blocked)))
        return 0 if good else 1
    print('  %s' % ('all checks passed' if not bad else '%d check(s) FAILED' % bad))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
