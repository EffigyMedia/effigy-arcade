#!/usr/bin/env python3
"""NOVELTY TEST - the garage toggle that puts the work vehicles away.

    .venv/Scripts/python tools/novelty-test.py

RLG-194. Owner, 2026-09-09: "there needs to be a toggle that hides the unlocked production and
utility vehicles from the garage to prevent clutter since they are novelty vehicles."

WHAT IT PROVES, AND WHAT IT WOULD MISS IF IT ASKED A NARROWER QUESTION. The easy check is that the
list gets shorter, and a toggle that emptied the garage would pass it. So every check here is about
WHICH cars moved:

  the control is absent until one of the two secret classes is won, because a switch for something
  the player has never seen advertises a thing the game is not ready to explain;

  turning it off removes EXACTLY the production and utility cars and leaves every other car in
  place, in the same order;

  the unlock is not touched - turning it back on returns the same cars;

  and a player sitting IN a work vehicle when they turn it off is moved to a car the garage will
  still list, rather than left selecting something that is not there.

The unlock flags are written into the save before the reload, because the two classes are the
game's only secret unlocks and are absent from the garage until they are earned - the toggle has
nothing to act on before that, which is itself one of the checks below.

Exit code 0 if every check passed, 1 otherwise.
"""
import argparse
import functools
import http.server
import socketserver
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from harness import console_utf8, launch_chromium
from playwright.sync_api import sync_playwright

GAME = 'games/sw/interstate.html'
WORK = {'COUPE', 'SALOON', 'CAB', 'PICKUP', 'VAN', 'LORRY', 'AMBULANCE'}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--headed', action='store_true')
    args = ap.parse_args()
    console_utf8()

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
    srv = socketserver.TCPServer(('127.0.0.1', 0), handler)
    base = 'http://127.0.0.1:%d' % srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    bad = 0

    def ok(cond, label, detail=''):
        nonlocal bad
        if not cond:
            bad += 1
        print('  %s  %s%s' % ('ok  ' if cond else 'FAIL', label,
                              ('   ' + detail) if detail else ''))

    print('novelty-test  .  the garage puts the work vehicles away')
    with sync_playwright() as p:
        b = launch_chromium(p, headless=not args.headed,
                            args=['--mute-audio', '--autoplay-policy=no-user-gesture-required'])
        ctx = b.new_context(viewport={'width': 480, 'height': 900})
        page = ctx.new_page()
        errs = []
        page.on('pageerror', lambda e: errs.append(str(e)))

        def open_garage():
            page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
            page.click('[data-act="play"]')
            page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)

        def bodies():
            return page.evaluate('() => window.__road.garageBodies()')

        def toggle():
            return page.query_selector('[data-act="novelty"]')

        # ---- BEFORE THE UNLOCK: the control must not be there -------------
        page.goto('%s/%s' % (base, GAME), wait_until='load')
        page.wait_for_timeout(600)
        open_garage()
        clean = bodies()
        ok(toggle() is None,
           'the control is absent on a save that has not won the work vehicles')
        ok(not (set(clean) & WORK),
           'and those cars are absent too, as the secret unlock intends',
           'listed %d cars' % len(clean))

        # ---- WIN THEM, the way the road does -----------------------------
        page.evaluate("""() => {
            const A = window.Arcade;
            A.save.merge('interstate-opts', { production:true, utility:true });
        }""")
        page.reload(wait_until='load')
        page.wait_for_timeout(600)
        open_garage()
        shown = bodies()
        work_shown = sorted(set(shown) & WORK)
        ok(bool(work_shown), 'winning them puts them in the garage',
           '%d work vehicle(s): %s' % (len(work_shown), ', '.join(work_shown)))
        ok(toggle() is not None, 'and the control appears with them')

        # ---- SIT IN ONE, so the swap is exercised rather than assumed ----
        page.evaluate('(k) => window.__road.setBody(k)', work_shown[0])
        page.evaluate('() => window.__road.showGarage && window.__road.showGarage()')

        # ---- TURN IT OFF -------------------------------------------------
        page.click('[data-act="novelty"]')
        page.wait_for_timeout(120)
        hidden = bodies()
        ok(not (set(hidden) & WORK),
           'turning it off removes every work vehicle',
           '%d left' % len(hidden))
        ok(sorted(hidden) == sorted(set(shown) - WORK),
           'and removes ONLY those - every other car is still listed',
           'expected %d, got %d' % (len(set(shown) - WORK), len(hidden)))
        ok([k for k in shown if k not in WORK] == hidden,
           'and the order of what is left is unchanged')
        label = page.eval_on_selector('[data-act="novelty"] b', 'el => el.textContent').strip()
        ok(label == 'HIDDEN', 'the control says so', 'reads %r' % label)

        cur = page.eval_on_selector('#veilBody .gname', 'el => el.textContent').strip()
        ok(cur in hidden,
           'a player sitting in a work vehicle is moved to one the garage lists',
           'now showing %s' % cur)

        # ---- AND BACK -----------------------------------------------------
        page.click('[data-act="novelty"]')
        page.wait_for_timeout(120)
        again = bodies()
        ok(sorted(again) == sorted(shown),
           'turning it back on returns exactly the same cars',
           '%d cars' % len(again))

        # ---- IT IS A VIEW, NOT AN UNLOCK ----------------------------------
        won = page.evaluate("""() => {
            const sv = window.Arcade.save.get('interstate-opts') || {};
            return !!sv.production && !!sv.utility;
        }""")
        ok(won, 'and the unlock itself was never touched')
        ok(not errs, 'the run was clean', '; '.join(errs[:2]))
        ctx.close()
        b.close()

    print('  %s' % ('all checks passed' if not bad else '%d check(s) failed' % bad))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
