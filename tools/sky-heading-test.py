#!/usr/bin/env python3
"""SKY HEADING - the horizon swings with the car's heading, not with the road far ahead.

    EFFIGY_NO_GPU=1 PYTHONIOENCODING=utf-8 .venv/Scripts/python tools/sky-heading-test.py

Owner, 2026-09-24, with the diagnosis: "I've also kind of figured out why the horizon
parallax seems weird. It's because you're moving it as the road twists and turns way down
the road not where the player's car is." [[RLG-343]]

THE TWO QUANTITIES ARE BOTH PUBLISHED, which is what makes this checkable rather than a
matter of opinion. `API.skyTrace` reports `heading` - the direction the road points where
the camera sits - and `ahead`, the road's deviation at the far end of the draw, which is
what the skyline used to answer.

SO THE CHECK IS A CORRELATION, NOT A PICTURE. Over a drive it collects both against what
the skyline actually targets, and asserts that the target tracks the HEADING and not the
term ahead. Specifically: across samples where the heading is unchanged, the target must be
unchanged too, however much the road bends in the distance. That case is not hypothetical -
the measurement that prompted the fix caught the heading identical to five decimal places
at two positions thirty thousand units apart while the old target moved thirty-nine pixels.

AND IT WOULD HAVE FAILED BEFORE. With the old driver the target was a function of `ahead`
alone, so every straight stretch under a distant bend breaks the assertion. That is the
falsification and it needs no scratch build: put `-bendPx(pos + ROAD_FAR) * 0.55` back in
place of the heading term in `drawSky` and this goes red.

WHAT IT DOES NOT CHECK. Not how far the horizon should sweep. `SKY_SWING` is a tunable with
a committed default and the amount is taste - the owner judges it on a device, and no
harness can take that from them.
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


def check(label, condition, detail=''):
    print('%s  %s%s' % ('PASS' if condition else 'FAIL', label,
                        ('  [%s]' % detail) if detail else ''))
    if not condition:
        fails.append(label)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--samples', type=int, default=60)
    ap.add_argument('--gap', type=int, default=400, help='ms of driving between samples')
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

    print()
    print('  sky-heading  .  the horizon answers the car, not the road a mile off')
    with sync_playwright() as p:
        br = launch_chromium(p, headless=True, args=['--mute-audio'])
        pg = br.new_page(viewport={'width': 480, 'height': 900})
        errs = []
        pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.add_init_script(init)
        boot(pg, 'http://127.0.0.1:%d/games/sw/interstate.html' % port)
        until(pg, '!!window.__probe.road', timeout=15000)
        pg.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=15000)
        pg.click('[data-act="play"]')
        pg.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=8000)
        pg.click('[data-act="drive"]')
        pg.wait_for_timeout(1800)
        # THE RUN CLOCK WOULD STOP THE CAR PART WAY THROUGH (RLG-125) and every number
        # after that would be the same sample repeated.
        pg.evaluate("() => { const R = window.__probe.road;"
                    " R.setTimed(false); R.clearTraffic(); }")

        rows = []
        for _ in range(args.samples):
            pg.evaluate("() => window.__probe.road.holdSpd("
                        "window.__probe.road.MAX_SPD * 0.8)")
            pg.wait_for_timeout(args.gap)
            rows.append(pg.evaluate("() => window.__probe.road.skyTrace()"))
        br.close()

    swing = rows[0].get('swing')
    print('     %d sample(s), SKY_SWING = %s' % (len(rows), swing))
    check('the trace publishes both quantities',
          'heading' in rows[0] and 'ahead' in rows[0], sorted(rows[0]))

    # ---- THE TARGET IS THE HEADING, TO THE COEFFICIENT ---------------------------
    # Not a correlation but an identity: if the skyline answers the heading then
    # `want` IS the heading times the swing, everywhere, and any sample that breaks it
    # is a sample where something else is steering the horizon.
    worst = 0.0
    for r in rows:
        worst = max(worst, abs(r['want'] - (-r['heading'] * swing)))
    check('the horizon target IS the car heading times the swing', worst < 0.05,
          'worst departure %.4f px over %d samples' % (worst, len(rows)))

    # ---- AND A STRAIGHT UNDER A DISTANT BEND MUST NOT MOVE IT --------------------
    # This is the owner's report stated as an assertion. Pairs of samples whose heading
    # matches are pairs where the car did not turn; the horizon must not have moved,
    # however far apart the two `ahead` readings are.
    pairs = []
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            if abs(rows[i]['heading'] - rows[j]['heading']) < 1e-4:
                pairs.append((rows[i], rows[j]))
    if pairs:
        moved = max(abs(a['want'] - b['want']) for a, b in pairs)
        spread = max(abs(a['ahead'] - b['ahead']) for a, b in pairs)
        check('a car going straight does not swing the horizon', moved < 0.05,
              '%d pair(s) with the same heading; horizon moved %.4f px while the road '
              'ahead differed by up to %.1f' % (len(pairs), moved, spread))
    else:
        # Not a pass. A run that never held a heading twice cannot answer the question,
        # and saying so is the honest outcome rather than a green tick.
        check('the drive held a heading long enough to compare', False,
              'no two samples shared a heading - drive longer or sample faster')

    check('no page errors', not errs, '; '.join(errs[:2]))
    print()
    if fails:
        print('FAILED: %d' % len(fails))
        for f in fails:
            print('  - %s' % f)
        sys.exit(1)
    print('ALL CHECKS PASSED')


if __name__ == '__main__':
    main()
