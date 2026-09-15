#!/usr/bin/env python3
"""NOVELTY TEST - the work vehicles are traffic, and the player cannot own one.

    .venv/Scripts/python tools/novelty-test.py

RLG-249. Owner, 2026-09-14: "let's just get rid of unlocking the non-racing vehicles. That means we
can get rid of the hiding toggle."

This file tested the WORK VEHICLES toggle (RLG-194) until that toggle was removed. It now tests the
removal. A check that only asks "is the toggle gone" passes on a garage that still lists a van, so
every check here is about WHICH cars the player can reach:

  a fresh save lists no work vehicle, and the garage has no WORK VEHICLES control;

  a save that already holds the old `utility` unlock flag still lists no work vehicle, and the flag
  itself is left in the save untouched;

  a save that has a work vehicle SELECTED loads onto a car the player owns, and that choice is
  written back to the save, so the next boot does not start in the van again;

  and the work vehicles are still built as traffic sprites, because only the player's access went.

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
from harness import console_utf8, launch_chromium, boot, reboot
from playwright.sync_api import sync_playwright

GAME = 'games/sw/interstate.html'
WORK = {'CAB', 'PICKUP', 'VAN', 'SEMI', 'AMBULANCE'}


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

    print('novelty-test  .  the work vehicles are traffic, not the player\'s')
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

        # ---- A FRESH SAVE ----------------------------------------------------
        boot(page, '%s/%s' % (base, GAME))
        page.wait_for_timeout(600)
        open_garage()
        clean = bodies()
        ok(len(clean) >= 3, 'the garage lists cars', 'listed %d' % len(clean))
        ok(not (set(clean) & WORK), 'a fresh save lists no work vehicle',
           ', '.join(sorted(set(clean) & WORK)))
        ok(page.query_selector('[data-act="novelty"]') is None,
           'and the garage has no WORK VEHICLES control')
        fleet = page.evaluate('() => window.__road.garageFleet()')
        ok(not (set(fleet) & WORK), 'no work vehicle is in the fleet a garage can ever hold',
           ', '.join(sorted(set(fleet) & WORK)))

        # ---- A SAVE THAT WON THEM UNDER THE OLD RULE, SITTING IN A VAN -------
        page.evaluate("""() => {
            window.Arcade.save.merge('interstate-opts', { utility:true, body:'VAN' });
        }""")
        reboot(page)
        page.wait_for_timeout(600)
        open_garage()
        won = bodies()
        ok(not (set(won) & WORK), 'the old unlock flag does not list them',
           ', '.join(sorted(set(won) & WORK)))
        owned = page.evaluate('() => window.__road.playableBodies()')
        cur = page.eval_on_selector('#veilBody .gname', 'el => el.textContent').strip()
        saved = page.evaluate("() => (window.Arcade.save.get('interstate-opts') || {})")
        ok(saved.get('body') in owned,
           'a save sitting in a work vehicle loads onto a car the player owns',
           'saved body %r, card reads %r' % (saved.get('body'), cur))
        ok(saved.get('utility') is True, 'and the old flag is left in the save untouched')

        # ---- THE BODIES ARE STILL TRAFFIC -------------------------------------
        # `API.fleet` is every vehicle the engine can put on the road. Its rows are named by
        # body key or by traffic rig, so each work vehicle is looked for under both names.
        names = {'CAB': 'taxi', 'PICKUP': 'pickup', 'VAN': 'van', 'SEMI': 'truck',
                 'AMBULANCE': 'ambulance'}
        rows = page.evaluate("() => window.__road.fleet().map(r => String(r.name || r.label || ''))")
        seen = {k for k, r in names.items()
                if any(n.split(' ')[0] in (k, r) for n in rows)}
        ok(seen == WORK, 'every work vehicle is still on the road\'s fleet',
           'found: %s of %d rows' % (', '.join(sorted(seen)), len(rows)))

        ok(not errs, 'the run was clean', '; '.join(errs[:2]))
        ctx.close()
        b.close()

    print('  %s' % ('all checks passed' if not bad else '%d check(s) failed' % bad))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
