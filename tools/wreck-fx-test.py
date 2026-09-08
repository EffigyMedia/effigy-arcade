#!/usr/bin/env python3
"""WRECK FX TEST - a destroyed car goes on smoking, because that is the state of it.

    .venv/Scripts/python tools/wreck-fx-test.py

Owner, 2026-09-07: "when a car is destroyed - police, traffic, doesn't matter - the damage
VFX go away. They need to keep their smoking fire, cause that is the state of things."

IT WAS TRUE OF ALL THREE KINDS AND FOR TWO DIFFERENT REASONS, which is what this file
pins down. `hurtCop` and `hurtRival` both clear the damage counter in the same breath as
taking the car out - correct for what they were written for, since the counter has to be
clear before the car is put back in play, and it meant the plume stopped at the exact
moment it was most earned. Traffic never had the problem and never had the effect either:
`hurtTraffic` keeps its counter and NO PAINTER EVER ASKED, so a lorry you had put into the
barrier rolled to the shoulder looking showroom fresh.

WHAT IT ASSERTS: that what the painter is given - `look` - reads full for a car that is
out, whatever the counter says. Reading the counter instead is the mistake this file
exists to catch, because on a wrecked cruiser the counter reads zero: undamaged.
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


def main():
    bad = 0

    def ok(cond, label, detail=''):
        nonlocal bad
        if not cond:
            bad += 1
        print(f'  {"ok  " if cond else "FAIL"}  {label}' + (f'   {detail}' if detail else ''))

    print('wreck-fx-test  .  a destroyed car goes on smoking')
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
        page.wait_for_timeout(400)
        page.click('[data-act="chase"]')
        page.wait_for_timeout(200)
        page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
        page.click('[data-act="drive"]')
        page.wait_for_timeout(1500)

        # ---- A CRUISER, TAKEN OUT THROUGH THE ENGINE'S OWN DAMAGE PATH -------
        # `hurtCop` is what a barrier and a traffic car call, so this is the real
        # takedown rather than a flag set from outside.
        page.evaluate("() => window.__road.placeCop(3000, 0.4)")
        page.evaluate("() => { for(let i = 0; i < 8; i++) window.__road.hurtCop(0, 60); }")
        page.wait_for_timeout(200)
        cop = [r for r in page.evaluate("() => window.__road.hurtLooks()") if r['what'] == 'cop']
        if cop:
            c = cop[0]
            print(f"  ..    a downed cruiser: counter reads {c['dmg']}, painter is given {c['look']}")
            ok(c['out'], 'the cruiser really is out', f"out={c['out']}")
            ok(c['look'] > 25, 'and it is still drawn smoking',
               f"the painter is given {c['look']}")
            # THE LINE THAT MATTERS. Reading `dmg` here would report an undamaged car.
            ok(c['dmg'] <= 25 < c['look'],
               'even though its damage counter has been cleared to put it back in play',
               f"counter {c['dmg']}, drawn at {c['look']}")
        else:
            for label in ('the cruiser really is out', 'and it is still drawn smoking',
                          'even though its damage counter has been cleared to put it back in play'):
                ok(False, label, 'no cruiser to read')

        # ---- AND TRAFFIC, WHICH NEVER SHOWED DAMAGE AT ALL -------------------
        # THROUGH THE REAL DAMAGE PATH, and the first version of this did not.
        # Setting `dead` from outside skips `slide`, which the dead-car step needs to
        # know which shoulder to coast to - without it the car's lateral position goes
        # non-finite and takes the tyre smoke's gradient down with it. The harness was
        # building an impossible car and the page error it produced was its own.
        page.evaluate("() => window.__road.parkTraffic(0, 3000, 'van')")
        page.evaluate("() => { for(let i = 0; i < 6; i++) window.__road.hurtTraffic(0, 60); }")
        page.wait_for_timeout(150)
        tr = [r for r in page.evaluate("() => window.__road.hurtLooks()")
              if r['what'] == 'traffic' and r['out']]
        ok(bool(tr) and tr[0]['look'] > 25,
           'and a wrecked traffic car smokes too, which it never did',
           f"drawn at {tr[0]['look']}" if tr else 'no wrecked traffic to read')
        ok(errs == [], 'no page errors', errs[0][:100] if errs else '')
        ctx.close()
        b.close()
    srv.shutdown()
    print(f"\n  {'the wreck goes on burning' if not bad else str(bad) + ' FAILURES'}")
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
