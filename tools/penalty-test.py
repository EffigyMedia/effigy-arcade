"""A PENALTY COSTS YOU GROUND, AND A RIVAL CAN SERVE ONE TOO.

    .venv/Scripts/python tools/penalty-test.py

Owner, 2026-09-06: "we need it so they can get damaged too and incite the same 2sec penalty.
When the player gets the 2 seconds penalty, the world shouldn't freeze. The world should
continue."

TWO CLAIMS, AND THE FIRST ONE IS THE INTERESTING ONE.

  1. THE WORLD KEEPS RUNNING WHILE THE PLAYER SERVES. The step used to `return` early during
     a penalty, skipping the biome, the weather, the traffic, the police and `stepRacers` -
     so two seconds of penalty cost the clock and nothing else. The field sat frozen exactly
     where it was and you lost NO GROUND, which is the opposite of a penalty. So the check
     is not "does time pass" but "did the field move while you did not".

  2. A RIVAL KEEPS A HEALTH BAR. Damage accumulates on a rival as it does on the player, and
     at a hundred it serves WRECK_SECS - the same constant, so the two penalties cannot drift
     apart.

AND THE CLOCK IS CHECKED SEPARATELY, because unfreezing the world created a trap worth
guarding: the clock used to be decremented inside the penalty branch precisely because the
early return skipped the clock's own code. With the frame now running to the end, both would
tick it and the countdown would run at DOUBLE SPEED for exactly two seconds - which nobody
would notice until a run ended early. So this measures the clock's rate through a penalty
against its rate in normal driving.

THE CRASH IS FORCED RATHER THAN DRIVEN INTO. A harness cannot reliably crash on cue, and what
is under test is what the world does DURING the penalty, not the collision that caused it.

Exit code 0 if every check passed, 1 otherwise.
"""
import sys, threading, http.server, socketserver, functools

from pathlib import Path as _P
ROOT = _P(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from harness import launch_chromium, console_utf8
from playwright.sync_api import sync_playwright
console_utf8()

h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
srv = socketserver.TCPServer(('127.0.0.1', 0), h)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()

bad = [0]


def check(ok, label, detail):
    print(f'  {"ok  " if ok else "FAIL"}  {label:<48} {detail}')
    if not ok:
        bad[0] += 1


with sync_playwright() as p:
    b = launch_chromium(p, headless=True,
                        args=['--mute-audio', '--autoplay-policy=no-user-gesture-required'])
    pg = b.new_context(viewport={'width': 480, 'height': 900}).new_page()
    errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.goto(f'http://127.0.0.1:{PORT}/games/sw/interstate.html', wait_until='load')
    pg.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
    pg.click('[data-act="play"]')
    pg.wait_for_selector('#veil:not(.hidden) [data-act="mode"]', timeout=5000)
    pg.click('[data-act="mode"]')                  # SINGLE RACE, so there is a field
    pg.wait_for_timeout(150)
    pg.click('[data-act="drive"]')
    try:
        pg.wait_for_function(
            "() => { const g = window.__road.rivalGears();"
            "        return g.length && g.some(r => r.gear >= 1); }", timeout=15000)
    except Exception:
        print('\n  FAIL  the grid was never released')
        bad[0] += 1

    # ---- the clock's rate in NORMAL driving, as the control ------------------
    # MEASURE THE ELAPSED TIME, DO NOT ASSUME IT. A first version divided the
    # clock lost by (iterations x 40ms) and got 1.52/s against a 1.03/s control -
    # which looks exactly like a double tick and was not one. The loop body costs
    # real time on top of each sleep, so the assumed duration was short and the
    # rate came out high. `performance.now()` is the only honest denominator.
    base = pg.evaluate("""async () => {
      const R = window.__road, a = R.penalty(), t0 = performance.now();
      await new Promise(z => setTimeout(z, 1000));
      const b = R.penalty();
      return { clock: a.clock - b.clock, secs: (performance.now() - t0) / 1000 };
    }""")

    # ---- force a wreck and watch the world through it ------------------------
    run = pg.evaluate("""async () => {
      const R = window.__road;
      const g0 = R.rivalGears(), p0 = R.penalty();
      const t0 = performance.now();
      R.forceWreck();
      const seen = [];
      for (let k = 0; k < 26; k++) {
        await new Promise(z => setTimeout(z, 40));
        seen.push({ p: R.penalty(), g: R.rivalGears().map(r => r.z) });
      }
      const g1 = R.rivalGears(), p1 = R.penalty();
      return { g0: g0.map(r => r.z), g1: g1.map(r => r.z), p0: p0, p1: p1, seen: seen,
               secs: (performance.now() - t0) / 1000 };
    }""")

    print()
    served = any(s['p']['wreckWait'] > 0 for s in run['seen'])
    check(served, 'the player actually served a penalty',
          f"wreckWait peaked at {max(s['p']['wreckWait'] for s in run['seen']):.2f}s")

    # THE CLAIM: the field moved while the player did not
    moved = [b2 - a2 for a2, b2 in zip(run['g0'], run['g1'])]
    field = sum(moved) / max(1, len(moved))
    player = run['p1']['pos'] - run['p0']['pos']
    check(field > 2000, 'and the field kept racing while it did',
          f'rivals moved {field:.0f} units on average')
    check(player < field / 4, 'while the player did not',
          f'player moved {player} against the field\'s {field:.0f}')

    # the clock must not run double
    lost = run['p0']['clock'] - run['p1']['clock']
    rate = lost / max(0.01, run['secs'])
    ctrl = base['clock'] / max(0.01, base['secs'])
    check(0.75 < rate / max(0.01, ctrl) < 1.25,
          'and the clock did not tick twice for it',
          f'{rate:.2f}/s through the penalty against {ctrl:.2f}/s driving normally '
          f'(over {run["secs"]:.2f}s measured, not assumed)')

    # ---- a rival keeps a health bar -----------------------------------------
    dmg = pg.evaluate("() => window.__road.hurtRival(0, 40)")
    check(dmg and dmg['dmg'] > 0 and dmg['wreck'] == 0,
          'a rival takes damage without being wrecked by it',
          f'dmg {dmg["dmg"] if dmg else "?"} after one hit')

    out = pg.evaluate("() => window.__road.hurtRival(0, 100)")
    check(out and out['wreck'] > 1.5,
          'and at a hundred it serves the same two seconds',
          f'wreck timer {out["wreck"] if out else "?"}s (the player serves 2.0)')

    # ---- and a cruiser is worn down, not dropped by one hit -----------------
    # Owner, 2026-09-07: "this damage system should apply to taking out police as
    # well." Scored against a throwaway cruiser rather than a real one: making
    # this wait for the spawner to deal a cruiser would be testing the SPAWNER,
    # and the claim is about the damage rule.
    # SIZE THE HITS FROM THE CAR'S OWN HARDINESS. A fixed 45 assumed every
    # vehicle had 100 points; a cruiser has half again as much by the owner's
    # ruling, so three 45s stopped being enough the moment hardiness landed and
    # this check failed on working code. Asking for 45% of ITS OWN health keeps
    # the claim - "worn down over three hits, not dropped by one" - true whatever
    # the number is tuned to.
    hp = pg.evaluate("() => window.__road.health()['CRUISER']")
    cop = pg.evaluate("(h) => window.__road.probeCop(3, h * 0.45)", hp)
    check(cop and not cop[0]['downed'] and not cop[1]['downed'] and cop[2]['downed'],
          'a cruiser is worn down rather than dropped',
          f"{hp} health: dmg {cop[0]['dmg']:.0f} then {cop[1]['dmg']:.0f}, "
          f"down on the third" if cop else 'no reading')
    check(cop and cop[2]['wreck'] > 1.5,
          'and serves the same two seconds when it goes',
          f"wreck timer {cop[2]['wreck']}s" if cop else 'no reading')

    check(not errs, 'no page errors', errs[0] if errs else 'clean')
    pg.close()
    b.close()
srv.shutdown()
print()
print('  ' + ('a penalty costs you ground'
              if not bad[0] else f'{bad[0]} FAILURES'))
sys.exit(1 if bad[0] else 0)
