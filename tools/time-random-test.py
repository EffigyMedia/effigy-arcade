#!/usr/bin/env python3
"""TIME RANDOM - RANDOM is one of the times of day, it is the default, and it really rolls.

    EFFIGY_NO_GPU=1 PYTHONIOENCODING=utf-8 .venv/Scripts/python tools/time-random-test.py

Owner, 2026-09-24: "I'd like one of the time of day choices to be random and that should be
the default." [[RLG-339]]

THREE CLAIMS, AND THE THIRD IS THE ONE THAT CAN ROT QUIETLY. That the row offers RANDOM is
visible. That it is the default on a fresh machine is visible. That it ROLLS - that two runs
started under it do not get the same hour - is not visible at all from the menu, and a
RANDOM that always returned dusk would look exactly like a RANDOM that worked.

SO THE HOUR IS READ OFF THE ENGINE, once per run, over many runs. `API.restart` takes the
same path DRIVE and RETRY take (RLG-090), so what is measured is the hour a real run opens
at. The check asserts that more than one of the four turns up, and prints the spread.

AND THAT A SAVED CHOICE STILL WINS. RANDOM is the default for a machine with NOTHING stored;
a player who has set a time keeps it. The option is saved as an index into the table, so
RANDOM was appended rather than put first - had it gone first, every index already written
would have shifted and a player's MIDDAY would have become a DAWN. This check sets a time,
reloads, and asserts the choice survived.

WHAT IT DOES NOT CHECK. It does not judge the light. Whether a given hour looks right is the
owner's call on a device and no harness can take it.
"""
import argparse
import functools
import http.server
import socketserver
import sys
import threading
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from harness import console_utf8, launch_chromium, boot, until   # noqa: E402
from playwright.sync_api import sync_playwright                  # noqa: E402

fails = []


def check(label, condition, detail=''):
    print('%s  %s%s' % ('PASS' if condition else 'FAIL', label,
                        ('  [%s]' % detail) if detail else ''))
    if not condition:
        fails.append(label)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--runs', type=int, default=40, help='runs to start under RANDOM')
    args = ap.parse_args()
    console_utf8()

    h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
    srv = socketserver.TCPServer(('127.0.0.1', 0), h)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    init = """
    window.__probe = { road: null };
    (function(){ var real=null, wrapped=null;
      Object.defineProperty(window,'ROAD',{configurable:true,
        get:function(){return real?wrapped:undefined;},
        set:function(fn){real=fn;wrapped=function(CFG){var api=real(CFG);
          window.__probe.road=api||(CFG&&CFG.api)||null;return api;};}});})();
    """
    url = 'http://127.0.0.1:%d/games/sw/interstate.html' % port

    print()
    print('  time-random  .  RANDOM is offered, is the default, and rolls')
    with sync_playwright() as p:
        br = launch_chromium(p, headless=True, args=['--mute-audio'])
        ctx = br.new_context(viewport={'width': 480, 'height': 900})
        ctx.add_init_script(init)
        pg = ctx.new_page()
        errs = []
        pg.on('pageerror', lambda e: errs.append(str(e)))
        boot(pg, url)
        until(pg, '!!window.__probe.road', timeout=15000)

        # ---- THE ROW, ON A MACHINE WITH NOTHING SAVED ----------------------------
        # THE TIME ROW LIVES IN THE GARAGE'S SETTINGS VIEW, not on the title card. The
        # first cut of this waited for it straight after PLAY and timed out.
        pg.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=15000)
        pg.click('[data-act="play"]')
        pg.wait_for_selector('#veil:not(.hidden) [data-act="settings"]', timeout=8000)
        pg.click('#veil:not(.hidden) [data-act="settings"]')
        pg.wait_for_selector('#veil:not(.hidden) [data-act="time"]', timeout=8000)
        row = pg.inner_text('#veil:not(.hidden) [data-act="time"]')
        shown = row.split('·')[-1].strip().upper()
        check('a fresh machine offers RANDOM on the TIME row', 'TIME' in row.upper(), row)
        check('and RANDOM is what it starts on', shown == 'RANDOM', shown)

        # ---- AND IT ROLLS ---------------------------------------------------------
        # `restart` is the path DRIVE and RETRY both take, so this is the hour a real
        # run opens at rather than a number a harness computed for itself.
        for act in ('back', 'done', 'drive'):
            try:
                pg.click('#veil:not(.hidden) [data-act="%s"]' % act, timeout=1500)
                pg.wait_for_timeout(300)
            except Exception:
                pass
        pg.wait_for_timeout(900)
        seen = Counter()
        for _ in range(args.runs):
            pg.evaluate("() => window.__probe.road.restart()")
            pg.wait_for_timeout(90)
            seen[round(pg.evaluate("() => window.__probe.road.phase()"), 2)] += 1
        spread = sorted(seen.items())
        print('     hours drawn over %d run(s): %s' % (args.runs, spread))
        check('RANDOM draws more than one hour', len(seen) > 1,
              'every run opened at %s' % list(seen)[0] if len(seen) == 1 else '%d distinct' % len(seen))
        # the four the table names. A draw that produced a fifth value would mean the
        # roll had stopped reading the table, which is worth catching separately.
        check('and every hour it draws is one of the four',
              all(v in (0.0, 0.25, 0.5, 0.75) for v in seen),
              'drew %s' % sorted(seen))

        # ---- A SAVED CHOICE STILL WINS -------------------------------------------
        # Set a time through the row, reload the page, and it must come back. This is
        # what says appending RANDOM did not shift what an existing index means.
        pg.goto(url)
        until(pg, '!!window.__probe.road', timeout=15000)
        pg.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=15000)
        pg.click('[data-act="play"]')
        pg.click('#veil:not(.hidden) [data-act="settings"]')
        pg.wait_for_selector('#veil:not(.hidden) [data-act="time"]', timeout=8000)
        pg.click('#veil:not(.hidden) [data-act="time"]')
        pg.wait_for_timeout(250)
        picked = pg.inner_text('#veil:not(.hidden) [data-act="time"]').split('·')[-1].strip().upper()
        pg.goto(url)
        until(pg, '!!window.__probe.road', timeout=15000)
        pg.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=15000)
        pg.click('[data-act="play"]')
        pg.click('#veil:not(.hidden) [data-act="settings"]')
        pg.wait_for_selector('#veil:not(.hidden) [data-act="time"]', timeout=8000)
        after = pg.inner_text('#veil:not(.hidden) [data-act="time"]').split('·')[-1].strip().upper()
        check('a time the player chooses survives a reload', after == picked,
              'chose %s, came back %s' % (picked, after))
        check('no page errors', not errs, '; '.join(errs[:2]))
        br.close()

    print()
    if fails:
        print('FAILED: %d' % len(fails))
        for f in fails:
            print('  - %s' % f)
        sys.exit(1)
    print('ALL CHECKS PASSED')


if __name__ == '__main__':
    main()
