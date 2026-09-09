#!/usr/bin/env python3
"""PURSUIT ROW TEST - the row appears when somebody is chasing you, and not before.

    .venv/Scripts/python tools/pursuit-row-test.py

RLG-178. Owner, 2026-09-08: "Every run starts with a banner that says PURSUIT x1. What is that
and why do we need it?"

THE ROW IS A LIVE COUNT OF THE CRUISERS ON YOU and is worth having during a pursuit. What was
wrong is when it fired: it counted `onPlayer !== false`, and a car that has never chosen a
target has `onPlayer` undefined, which passes. A speed trap is laid in the first seconds of
every run, so every run opened with a blinking PURSUIT x1 for a parked car.

THE THREE CLAIMS:

  1. driving legally, with traps on the road, the row is empty and hidden
  2. and it is really hidden - the count reads zero, not merely a dark row
  3. with a cruiser actually engaged to the player it appears and counts

WHY CLAIM 1 NEEDS TRAPS ON THE ROAD TO MEAN ANYTHING. An empty road passes it trivially. The
defect only exists when there is a parked car for the row to miscount, so the check asserts
that a trap was present the whole time it was reading zero - otherwise it proves nothing, which
is the vacuity this project has been caught by before.

AND THE ROW IS READ FROM THE PAGE, NOT FROM THE ENGINE. The complaint is about something the
owner SAW. Reading `cops` and recomputing the predicate would test this file's idea of the rule
rather than the text on the screen, and would have passed on the broken build.

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


def boot(b, base):
    ctx = b.new_context(viewport={'width': 480, 'height': 900})
    page = ctx.new_page()
    errs = []
    page.on('pageerror', lambda e: errs.append(str(e)))
    page.goto('%s/%s' % (base, GAME), wait_until='load')
    try:
        page.wait_for_function(
            '() => navigator.serviceWorker && navigator.serviceWorker.controller', timeout=5000)
        page.wait_for_timeout(1000)
    except Exception:
        pass
    page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
    page.click('[data-act="play"]')
    page.wait_for_timeout(400)
    page.click('[data-act="chase"]')          # HOT PURSUIT on, or no trap is laid
    page.wait_for_timeout(150)
    page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
    page.click('[data-act="drive"]')
    page.wait_for_timeout(1500)
    return ctx, page, errs


def row(page):
    """What the row says and whether it is showing, read off the page."""
    return page.evaluate("""() => {
        const el = document.getElementById('pursuit');
        if(!el) return null;
        return { text: (el.textContent || '').trim(),
                 on: el.classList.contains('on'),
                 opacity: getComputedStyle(el).opacity };
    }""")


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

    print('pursuit-row-test  .  the row means somebody is chasing you')
    with sync_playwright() as p:
        b = launch_chromium(p, headless=not args.headed,
                            args=['--mute-audio', '--autoplay-policy=no-user-gesture-required'])
        ctx, page, errs = boot(b, base)

        # ---- 1 & 2. A CLEAN RUN, WITH TRAPS OUT, SHOWS NOTHING ------------------
        page.evaluate('() => window.__road.spawnTrap()')
        lit, worst, trapless = 0, '', 0
        for _ in range(90):
            page.evaluate('(f) => window.__road.setSpd(f * window.__road.MAX_SPD)', 0.30)
            page.wait_for_timeout(100)
            traps = page.evaluate("() => window.__road.cops().filter(k => k.trap).length")
            if traps == 0:
                trapless += 1
                page.evaluate('() => window.__road.spawnTrap()')
            r = row(page)
            if r and (r['on'] or r['text'] not in ('PURSUIT ×0', 'PURSUIT')):
                lit += 1
                worst = str(r)
        ok(trapless < 45, 'a trap really was parked on the road while this was read',
           '%d of 90 samples had none' % trapless)
        ok(lit == 0, 'driving legally past parked traps never lights the row',
           '%d of 90 samples lit it; worst %s' % (lit, worst) if lit else '')
        end = row(page)
        ok(bool(end) and end['opacity'] == '0',
           'and the row is invisible rather than merely dark', str(end))

        # ---- 3. AND IT APPEARS FOR A REAL PURSUIT -------------------------------
        # Staged through the engine's own dispatch: a radio car is sent for the player,
        # which is the case the row exists to report.
        page.evaluate("""() => {
            const R = window.__road;
            R.copsClear();
            R.placeCop(-3000, 0.1);
            const k = R.cops()[0];
            k.from = 'radio';
        }""")
        seen = None
        for _ in range(40):
            page.evaluate('(f) => window.__road.setSpd(f * window.__road.MAX_SPD)', 0.75)
            page.wait_for_timeout(100)
            r = row(page)
            if r and r['on']:
                seen = r
                break
        ok(seen is not None, 'a cruiser sent for you does light the row', str(seen or row(page)))
        ok(seen is not None and seen['text'].startswith('PURSUIT ×')
           and seen['text'] != 'PURSUIT ×0',
           'and it counts at least one car', str(seen))
        # THE OPACITY IS READ AFTER A SETTLE, and that is not a detail. The row fades in
        # over 0.2s, so a sample taken the instant the class lands reads opacity 0 on a
        # row that is working perfectly - which would make "it is visible" look like a
        # failing claim, or worse, make the hidden case look proven when it was only early.
        page.wait_for_timeout(400)
        lit_now = row(page)
        ok(bool(lit_now) and float(lit_now['opacity']) > 0.5,
           'and it really is visible once the fade has finished', str(lit_now))

        ok(not errs, 'and the run was clean', '; '.join(errs[:2]))
        ctx.close()
        b.close()

    print('  %s' % ('all checks passed' if not bad else '%d check(s) failed' % bad))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
