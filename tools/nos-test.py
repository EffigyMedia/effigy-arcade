"""RIVALS CARRY NITROUS, SPEND IT, AND RACE YOU FOR THE CRATES.

    .venv/Scripts/python tools/nos-test.py

Owner, 2026-09-06: "rival sports cars, supercars, a formula cars should all have nitrous too.
So they need to have the AI behavior to use it appropriately. They will also compete with you
over the pickups, which will award NOS to them the same way it does you. They should also get
the trickle fill of NOS as well."

FOUR CLAIMS, AND THEY FAIL FOR DIFFERENT REASONS, so each is checked on its own:

  1. THE RIGHT CARS HAVE A BOTTLE. Sports, super and formula do; anything else does not. This
     is the CAR's property and is asked of the body, through the same `hasNosFor` the player's
     own award asks - so a rival and a player in the same model can never disagree.
  2. IT TRICKLES. A bottle below full refills on its own, at the player's own rate, from the
     same constant.
  3. IT IS SPENT, AND NOT BY EVERYONE AT ONCE. Drivers must actually open the bottle over a
     race, and they must not all do it identically - `nerve` is per driver, so a field that
     boosts in lockstep would mean the decision is really a class rule wearing a disguise.
  4. A CRATE IS FIRST COME, FIRST SERVED. A crate dropped on a rival is taken BY that rival
     and tops its bottle up.

CHECK 4 IS DEALT RATHER THAN WAITED FOR. Crates arrive on their own schedule and a harness that
drove until one happened to land beside a rival would be slow and flaky. `API.crateAt` puts one
just ahead of a named car, which tests the collection rule without pretending to test the
spawner.

WHAT THIS CANNOT SAY. Whether the AI spends its bottle WELL - whether a boost arrives at a
moment that reads as racecraft rather than as a random surge - is a judgement about feel and
belongs to the owner on a device. This says the bottle exists, refills, is spent, is spent
differently by different drivers, and can be lost to a rival at a crate.

Exit code 0 if every check passed, 1 otherwise.
"""
import sys, threading, http.server, socketserver, functools

from pathlib import Path as _P
ROOT = _P(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from harness import launch_chromium, console_utf8, boot, until
from playwright.sync_api import sync_playwright
console_utf8()

h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
srv = socketserver.TCPServer(('127.0.0.1', 0), h)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()

bad = [0]


def check(ok, label, detail):
    print(f'  {"ok  " if ok else "FAIL"}  {label:<46} {detail}')
    if not ok:
        bad[0] += 1


SAMPLE = """async (n) => {
  const R = window.__road, out = [];
  for (let i = 0; i < n; i++) {
    await new Promise(r => setTimeout(r, 40));
    out.push(R.rivalGears());
  }
  return out;
}"""

with sync_playwright() as p:
    b = launch_chromium(p, headless=True,
                        args=['--mute-audio', '--autoplay-policy=no-user-gesture-required'])
    pg = b.new_context(viewport={'width': 480, 'height': 900}).new_page()
    errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    boot(pg, f'http://127.0.0.1:{PORT}/games/sw/interstate.html')
    pg.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
    pg.click('[data-act="play"]')
    pg.wait_for_selector('#veil:not(.hidden) [data-act="mode"]', timeout=5000)
    pg.click('[data-act="mode"]')                 # SINGLE RACE, so there is a field
    pg.wait_for_timeout(150)
    pg.click('[data-act="drive"]')
    try:
        until(pg, "() => { const g = window.__road.rivalGears();"
            "        return g.length && g.some(r => r.gear >= 1); }", timeout=15000)
    except Exception:
        print('\n  FAIL  the grid was never released')
        bad[0] += 1

    frames = pg.evaluate(SAMPLE, 300)
    live = [f for f in frames if f]

    print()
    if not live:
        check(False, 'there is a field to measure', 'no rivals returned')
    else:
        first = live[0]

        # 1. the right cars, decided by class.
        # A FRESH SAVE FIELDS ONLY SPORTS CARS, so every rival on the grid has a
        # bottle and "they all have one" would pass however broken the rule was.
        # The negative case has to be asked directly, of bodies that must NOT
        # have one - otherwise this check cannot fail.
        classes = {r['body']: r['hasNos'] for r in first}
        yes = pg.evaluate("() => ['ROADSTER','MATADOR','APEX'].map(k =>"
                          "   [k, window.__road.hasNosFor(k)])")
        no = pg.evaluate("() => ['VAN','SEMI','CAB','AMBULANCE'].map(k =>"
                         "   [k, window.__road.hasNosFor(k)])")
        check(all(v for _, v in yes) and not any(v for _, v in no),
              'the right cars carry a bottle, and only those',
              'with: ' + ', '.join(k for k, v in yes) +
              ' | without: ' + ', '.join(k for k, v in no))
        check(all(classes.values()),
              'and every rival on this grid has one',
              ', '.join(sorted(classes)) + ' (a fresh save fields sports cars only)')

        # 2. it trickles: some car's bottle rises while it is not boosting
        rose = 0
        for a, b2 in zip(live, live[1:]):
            for x, y in zip(a, b2):
                if x['hasNos'] and not y['nosOn'] and y['nos'] > x['nos']:
                    rose += 1
        check(rose > 0, 'and the bottle trickles back on its own',
              f'{rose} samples where a bottle refilled unspent')

        # 3. it is spent, and not by everyone at once
        opened = {i for f in live for i, r in enumerate(f) if r['nosOn']}
        anyon = sum(1 for f in live if any(r['nosOn'] for r in f))
        allon = sum(1 for f in live
                    if all(r['nosOn'] for r in f if r['hasNos'])
                    and any(r['nosOn'] for r in f))
        check(len(opened) > 0, 'and drivers actually spend it',
              f'{len(opened)} different cars opened the bottle, on {anyon} samples')
        check(anyon == 0 or allon < anyon,
              'and not all of them at the same moment',
              f'{allon} of {anyon} boosting samples had the whole field on it')

        nerves = {r['nerve'] for r in first if r['hasNos']}
        check(len(nerves) > 1, 'and each driver has its own nerve',
              f'{len(nerves)} distinct values across the field')

        # 4. a crate dropped on a rival is taken by that rival
        idx = next((i for i, r in enumerate(first) if r['hasNos']), None)
        if idx is None:
            check(False, 'a rival can take a crate', 'no rival with a bottle to test')
        else:
            # LOOK FOR A SINGLE-FRAME JUMP, NOT A NET CHANGE. Comparing the
            # bottle before and after failed once with 16.8 -> 5.9: the car was
            # BOOSTING, and the drain at 26/s outruns a +25 award over a 1.4s
            # window. A net change measures the drain as much as the award.
            # A crate is instantaneous, so one sample to the next jumping by
            # most of 25 is the award and nothing else can counterfeit it -
            # the trickle adds 1.1 a second and the drain only subtracts.
            # DROP AND SAMPLE IN ONE PAGE CALL. The award is instantaneous and
            # the crate is taken on the very next frame, so a "before" reading
            # taken in one round trip and a trail started in the next MISSES IT
            # ENTIRELY - the jump happens in the gap between the two calls. That
            # read as "not collected" three runs in a row while a probe showed
            # the bottle going 40 -> 63.7 on the frame after the drop.
            #
            # It also watches the WHOLE FIELD: the engine gives the crate to the
            # first rival in range, which need not be the car it was dropped on.
            # A car alongside taking it first is the contest working.
            trail = pg.evaluate("""async () => {
              const R = window.__road, out = [];
              out.push(R.rivalGears().map(x => x.nos));
              R.crateAt(0, 150);
              for (let k = 0; k < 40; k++) {
                await new Promise(z => setTimeout(z, 40));
                out.push(R.rivalGears().map(x => x.nos));
              }
              return out; }""")
            jump = 0
            for a2, b2 in zip(trail, trail[1:]):
                jump = max(jump, max((y - x for x, y in zip(a2, b2)), default=0))
            check(jump > 15, 'and a crate is taken by a rival, and pays it',
                  f'biggest single-frame gain across the field {jump:.1f} '
                  f'(a crate pays 25, the trickle 1.1/s)')

    check(not errs, 'no page errors', errs[0] if errs else 'clean')
    pg.close()
    b.close()
srv.shutdown()
print()
print('  ' + ('rivals carry nitrous and race you for it'
              if not bad[0] else f'{bad[0]} FAILURES'))
sys.exit(1 if bad[0] else 0)
