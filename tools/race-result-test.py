#!/usr/bin/env python3
"""RACE RESULT TEST - the first thing you see after a race is where you FINISHED.

    EFFIGY_NO_GPU=1 PYTHONIOENCODING=utf-8 .venv/Scripts/python tools/race-result-test.py

Owner, 2026-09-29, from the device: "no matter what place I get in the single race and
possibly even the tournament races it shows I get first place." [[RLG-345]]

THEY DID NOT COME FIRST AND THE PLACE WAS NEVER WRONG. Crossing the line went straight to
the leaderboard's initials card, which is headed `(rank)ST ON THE BOARD` - the rank of the
run's TIME, and on a short or empty board almost any time lands first. A player who came
twelfth of eleven was shown a large 1ST the instant they crossed the line, and `FINISHED
12TH` arrived two taps later.

▶ WHAT IS ASSERTED. A single race is entered from the garage and driven at 18 per cent of
top speed until the whole field is up the road, so the finish is genuinely LAST - a check
that finishes first cannot tell the two ordinals apart, which is the whole question. Then
the line is brought under the car with `API.parkFinish` and the screens are read in order:

  1. the first card carries the FINISHING POSITION, and does not carry the board's wording
  2. the board is still offered afterwards, so the entry was moved and not dropped
  3. the live `place` at the finish agrees with the card

▶ THE THIRD ONE IS NOT DECORATION. If the place itself ever breaks, a check that only read
the card would pass while the card politely reported the wrong number.

▶ IT DRIVES THE MENUS RATHER THAN CALLING THE FUNCTIONS. The fault was an ORDER of screens,
and an order is only real to a player who taps through it.
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
from harness import console_utf8, launch_chromium, boot, until   # noqa: E402
from playwright.sync_api import sync_playwright                  # noqa: E402

fails = []

VEIL = '#veil:not(.hidden) '
TEXT = """() => { const v = document.querySelector('#veil:not(.hidden)');
    return v ? v.innerText.replace(/\\s+/g, ' ').trim() : ''; }"""
ACTS = """() => Array.from(document.querySelectorAll('#veil:not(.hidden) [data-act]'))
    .map(b => b.getAttribute('data-act'))"""


def check(label, condition, detail=''):
    print('%s  %s%s' % ('PASS' if condition else 'FAIL', label,
                        ('  [%s]' % detail) if detail else ''))
    if not condition:
        fails.append(label)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--crawl', type=int, default=9, help='seconds spent letting the field go')
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
    screens = []
    place = None
    ahead = None
    try:
        with sync_playwright() as p:
            br = launch_chromium(p, headless=True)
            pg = br.new_page(viewport={'width': 440, 'height': 950})
            pg.add_init_script(init)
            boot(pg, 'http://127.0.0.1:%d/games/sw/interstate.html' % port)
            until(pg, '!!window.__probe.road', timeout=15000)
            pg.wait_for_selector(VEIL + '[data-act="play"]', timeout=15000)
            pg.click(VEIL + '[data-act="play"]')
            pg.wait_for_selector(VEIL + '[data-act="drive"]', timeout=10000)
            # the garage cycles its MODE button; a race is what this check is about
            for _ in range(5):
                label = pg.evaluate("""() => { const b =
                    document.querySelector('#veil:not(.hidden) [data-act="mode"]');
                    return b ? b.textContent.trim() : ''; }""")
                if label.endswith('RACE'):
                    break
                pg.click(VEIL + '[data-act="mode"]')
                pg.wait_for_timeout(260)
            pg.click(VEIL + '[data-act="drive"]')
            pg.wait_for_timeout(3000)
            # THE RUN CLOCK KILLS ANY HARNESS THAT DAWDLES (RLG-125)
            pg.evaluate("() => window.__probe.road.setTimed(false)")
            # ---- FINISH LAST, WHICH IS THE ONLY WAY TO TELL THE TWO ORDINALS APART
            pg.evaluate("() => window.__probe.road.holdSpd("
                        "window.__probe.road.MAX_SPD * 0.18)")
            pg.wait_for_timeout(args.crawl * 1000)
            st = pg.evaluate("""() => { const R = window.__probe.road;
                const g = R.grid(); let a = 0;
                for (const r of g) if (r.dz > 0) a++;
                return { ahead: a, cars: g.length, place: R.gridSlot().place }; }""")
            ahead, place = st['ahead'], st['place']
            print()
            print('  %d of %d car(s) up the road at the line, live place %d'
                  % (ahead, st['cars'], place))
            pg.evaluate("() => window.__probe.road.parkFinish(2000)")
            # ---- READ THE SCREENS IN ORDER --------------------------------------
            for _ in range(6):
                for _ in range(30):
                    t = pg.evaluate(TEXT)
                    if t:
                        break
                    pg.wait_for_timeout(300)
                if not t:
                    break
                acts = pg.evaluate(ACTS)
                screens.append(t)
                nxt = next((a for a in ('ok', 'back', 'menu') if a in acts), None)
                if nxt is None:
                    break
                pg.click(VEIL + '[data-act="%s"]' % nxt)
                pg.wait_for_timeout(900)
            br.close()
    finally:
        srv.shutdown()

    print()
    for i, t in enumerate(screens):
        print('  screen %d: %s' % (i, t[:120]))
    print()

    first = screens[0] if screens else ''
    check('the race was actually finished LAST', ahead is not None and ahead > 0,
          '%s car(s) up the road' % ahead)
    check('the first card after the line carries the finishing position',
          ('FINISHED' in first or 'WON' in first),
          'it says %r' % first[:60])
    check('and it is not the board card',
          'ON THE BOARD' not in first,
          'it says %r' % first[:60])
    check('the card agrees with the live place',
          place is not None and (str(place) in first if place != 1 else 'WON' in first),
          'place %s, card %r' % (place, first[:60]))
    check('the board is still offered afterwards',
          any('ON THE BOARD' in t for t in screens[1:]),
          'screens after the first: %d' % max(0, len(screens) - 1))
    print()
    if fails:
        print('FAILED: %d' % len(fails))
        for f in fails:
            print('  - %s' % f)
        sys.exit(1)
    print('ALL CHECKS PASSED')


if __name__ == '__main__':
    main()
