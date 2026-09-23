#!/usr/bin/env python3
"""RUBBER PROOF - every tyre mark is drawn below the bottom of the screen.

    .venv/Scripts/python tools/rubber-proof.py

THE OWNER REPORTED IT FROM THE OTHER END, 2026-09-22: "I think once upon a time
we implemented tire marks but I haven't seen them ever. Tire smoke too."

BOTH HALVES ARE TRUE AND THEY FAIL FOR DIFFERENT REASONS.

THE SMOKE IS DEAD CODE. `tyreSmoke` is declared, aged every frame by
`stepRubber`, drawn every frame by `drawRubber`, and capped by `SMOKE_MAX` - and
NOTHING EVER PUSHES INTO IT. `layRubber` carries the comment that removed it:
the tyre smoke fought with the damage smoke for the same patch of screen. The
array has been empty ever since.

THE MARKS ARE LAID, AGED, PROJECTED, AND MISS THE FRAME. They are laid at
`pos + PLAYER_Z - 340`, which is 340 units BEHIND the player's own car, and the
road behind your own wheels is below the bottom edge of a forward-facing view.
Measured on a 480x862 canvas: of 164 marks on the road, 40 pass both culls and
reach the fill, and they project to y = 1080 down to y = 8112. The frame ends at
862. NOT ONE OF THEM HAS EVER BEEN ON SCREEN.

A FIRST HYPOTHESIS WAS WRONG AND IS RECORDED BECAUSE IT WAS PLAUSIBLE. It looked
like a draw-order fault: `drawRubber` is the first thing `drawWorld` paints and
`drawRoad` paints the tarmac afterwards, so the marks appeared to be buried under
the road surface. That is TRUE of the draw order and IRRELEVANT to the bug - the
marks are off the bottom of the frame before the road ever covers them. Fixing
the order would have changed nothing. A screenshot with the tarmac lifted showed
no marks either, and that is what sent this back to the geometry.

SO A FORWARD VIEW IS THE WRONG PLACE FOR THEM. What is behind the car is what the
MIRROR shows, and `drawRubber` is called only from `drawWorld`, which is the front
pass. The glass has no rubber pass at all.

WHAT THIS PROOF DOES NOT CHECK. It does not say where the marks should be laid or
how they should look, and it does not measure what the wasted pass costs. It runs
at one viewport with the GPU off - but a mark at y=1080 on a frame 862 tall is
arithmetic rather than a rendering judgement, so a device cannot disagree with it.
"""
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

    with sync_playwright() as p:
        br = launch_chromium(p, headless=True)
        pg = br.new_page(viewport={'width': 480, 'height': 900})
        pg.add_init_script(init)
        boot(pg, 'http://127.0.0.1:%d/games/sw/interstate.html' % port)
        until(pg, '!!window.__probe.road', timeout=15000)
        pg.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=15000)
        pg.click('[data-act="play"]')
        pg.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=8000)
        pg.click('[data-act="drive"]')
        pg.wait_for_timeout(2000)

        # ---- lay rubber --------------------------------------------------
        # `scrubOf` wants a real snatch at the wheel rather than a lane change,
        # so the wheel is sawed hard. This is the one job the drive autopilot's
        # sawing is GOOD for; everywhere else here it is what ruins a number.
        pg.evaluate("() => window.__probe.road.setSpd(window.__probe.road.MAX_SPD*0.75)")
        pg.evaluate("() => window.__probe.road.setPhase(0.75)")
        # ---- AND IT IS READ WHILE THE RUBBER IS BEING LAID ---------------
        # The first cut read the counters 300ms after the last steer and found
        # drawn=0 with all 116 marks culled as behind the car - which is true,
        # and is the weaker claim. At 75 per cent of top speed a mark laid 541
        # units ahead is behind you within a fraction of a second, so a reading
        # taken after the sawing stops measures an empty road.
        #
        # So the counters are sampled DURING the sawing and the frame with the
        # MOST marks drawn is the one asserted against. That is the best case
        # this engine can produce for a tyre mark being seen, and the claim is
        # that even the best case never reaches the screen.
        r = {'skids': 0, 'drawn': -1, 'near': 0, 'far': 0,
             'onScreen': 0, 'top': None, 'bot': None, 'H': 0, 'smoke': 0}
        for _ in range(8):
            pg.keyboard.down('ArrowLeft'); pg.wait_for_timeout(130)
            got = pg.evaluate("() => window.__probe.road.rubber()")
            if got['drawn'] > r['drawn']: r = got
            pg.keyboard.up('ArrowLeft')
            pg.keyboard.down('ArrowRight'); pg.wait_for_timeout(130)
            got = pg.evaluate("() => window.__probe.road.rubber()")
            if got['drawn'] > r['drawn']: r = got
            pg.keyboard.up('ArrowRight')
        print()
        print('  marks on the road            %6d' % r['skids'])
        print('  thrown away as behind you    %6d' % r['near'])
        print('  thrown away as too far       %6d' % r['far'])
        print('  drawn, this frame            %6d' % r['drawn'])
        print('  of those, ON THE SCREEN      %6d' % r['onScreen'])
        print('  they land between y=%s and y=%s, on a frame %d tall'
              % (r['top'], r['bot'], r['H']))
        print()

        # ---- THE FIXTURE, CHECKED BEFORE THE CLAIM -----------------------
        # Every assertion below is trivially true of an empty road, and the
        # proof would pass while proving nothing.
        check('there is rubber on the road to look for', r['skids'] > 0,
              'skids=%d' % r['skids'])

        # THE NEGATIVE, AND IT IS THE ONE THAT MATTERS. The pass is not simply
        # switched off and it is not culling everything: marks reach the fill on
        # every frame. Without this, a dead `drawRubber` would pass the claim
        # below for the wrong reason.
        check('marks really are projected and filled every frame', r['drawn'] > 0,
              'drawn=%d of %d' % (r['drawn'], r['skids']))

        # THE CLAIM.
        check('not one drawn mark lands on the screen', r['onScreen'] == 0,
              'onScreen=%d' % r['onScreen'])
        check('even the highest mark is below the bottom edge',
              r['top'] is not None and r['top'] > r['H'],
              'top=%s H=%d' % (r['top'], r['H']))

        # THE OTHER HALF OF THE OWNER'S REPORT.
        check('no tyre smoke exists after the hardest scrubbing available',
              r['smoke'] == 0, 'smoke=%d' % r['smoke'])

        br.close()
    srv.shutdown()

    print()
    print('%d failure(s)%s' % (len(fails), (': ' + ', '.join(fails)) if fails else ''))
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
