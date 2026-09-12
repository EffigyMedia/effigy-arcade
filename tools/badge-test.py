#!/usr/bin/env python3
"""BADGE TEST - the marque sits on paint, and the tailgate glass is unbroken.

    .venv/Scripts/python tools/badge-test.py

RLG-216. The hatchback's tailgate glass runs from the deck line down to about a third of the way
to the floor, and the rear painter drew the marque at the boot-lid height every other body uses -
which on this body is INSIDE that glass. A badge floating on a rear window reads as a sticker, and
the owner read it as one on the fleet sheet.

WHAT IS MEASURED IS THE SPRITE, not the numbers that drew it. Testing my own arithmetic against
itself proves nothing: the whole fault was arithmetic that was right for five bodies and wrong for
the sixth. So this reads pixels out of the built rear sprite and asks two questions of the centre
column, where the badge is:

  1. THE GLASS IS UNBROKEN.  Between the top of the glass and its foot there must be no bright
     pixel. A badge drawn on the glass is a light island in the middle of a dark column, so it
     breaks this and the check fails.

  2. THE BADGE STILL EXISTS, BELOW THE GLASS.  Somewhere under the glass the centre column must
     differ from the plain paint beside it. Without this the first question passes by deleting the
     badge, which is the vacuous way to a green run.

BOTH HALVES MATTER AND NEITHER IS ENOUGH ALONE. Run with `--falsify` to put the defect back - the
engine is served with the badge at the old boot-lid height - and watch question 1 fail. A check
that cannot be made to fail is not evidence.

Exit code 0 if every check passed, 1 otherwise.
"""
import argparse
import functools
import http.server
import importlib.util
import socketserver
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from harness import console_utf8, launch_chromium, boot   # noqa: E402
from playwright.sync_api import sync_playwright            # noqa: E402

# the bodies whose rear glass reaches below the deck line. Only the hatchback has a tailgate
# today; a body added later with the same shape belongs in this list and the check follows it.
GLASS_TAILGATE = ['HATCH']

# a pixel this bright is paint or a badge; a pixel this dark is glass. The gap between the two is
# wide - the tailgate gradient bottoms out near #0a0d13 and white body paint is near #e8ecf1 - so
# the thresholds do not need to be delicate.
DARK = 70
BRIGHT = 120

PROBE = r"""(name) => {
  const R = window.__probe.road;
  const v = R.fleet().filter(x => x.name === name)[0];
  if (!v || !v.spr) return null;
  const s = v.spr;
  const c = document.createElement('canvas');
  c.width = s.width; c.height = s.height;
  const g = c.getContext('2d');
  g.drawImage(s, 0, 0);
  const d = g.getImageData(0, 0, c.width, c.height).data;
  /* luminance down two columns: the middle of the car, where the badge is, and a strip of plain
     paint beside it that carries no badge and no lamp. The second is the control. */
  const col = (x) => {
    const out = [];
    for (let y = 0; y < c.height; y++) {
      const i = (y*c.width + x)*4;
      const a = d[i+3] / 255;
      /* an unpainted pixel is not a dark one - the sprite is transparent outside the car, and
         treating that as glass would put the top of the glass at the top of the canvas */
      out.push(a < 0.5 ? null : (0.2126*d[i] + 0.7152*d[i+1] + 0.0722*d[i+2]));
    }
    return out;
  };
  return { w: c.width, h: c.height, mid: col(Math.round(c.width*0.5)),
           ref: col(Math.round(c.width*0.42)) };
}"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--falsify', action='store_true',
                    help='serve the engine with the badge at the old boot-lid height; check 1 must fail')
    args = ap.parse_args()
    console_utf8()

    dt_path = ROOT / 'tools' / 'drive-test.py'
    spec = importlib.util.spec_from_file_location('dt', dt_path)
    dt = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dt)

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
    srv = socketserver.TCPServer(('127.0.0.1', 0), handler)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    bad = 0

    def ok(cond, label, detail=''):
        nonlocal bad
        if not cond:
            bad += 1
        print('  %s  %s%s' % ('ok  ' if cond else 'FAIL', label,
                              ('   ' + detail) if detail else ''))

    print('badge-test  .  the marque is on paint and the glass is unbroken')
    if args.falsify:
        print('  FALSIFY: the badge is served at the boot-lid height. Check 1 must fail.')
    try:
        with sync_playwright() as p:
            b = launch_chromium(p, headless=True, args=['--mute-audio'])
            ctx = b.new_context(viewport={'width': 480, 'height': 900})
            ctx.add_init_script(dt.INIT)
            if args.falsify:
                # the defect, put back from the outside: the marque at the height the fault used.
                # It is injected into the PAINTER rather than into this file's own numbers, so the
                # check meets the drawing it would have met before the fix.
                src = (ROOT / 'road.js').read_text(encoding='utf-8').replace(
                    'const mqY = isHatch ? ly + lh*0.5 : deckY + h*0.088;',
                    'const mqY = deckY + h*0.088;')
                ctx.route('**/road.js', lambda route: route.fulfill(
                    status=200, content_type='application/javascript', body=src))
            pg = ctx.new_page()
            errs = []
            pg.on('pageerror', lambda e: errs.append(str(e)))
            boot(pg, 'http://127.0.0.1:%d/games/sw/interstate.html' % port)
            pg.wait_for_timeout(1600)
            pg.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
            pg.click('[data-act="play"]')
            pg.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
            pg.click('[data-act="drive"]')
            pg.wait_for_timeout(1500)

            for name in GLASS_TAILGATE:
                r = pg.evaluate(PROBE, name)
                if not r:
                    ok(False, '%-8s sprite not found' % name)
                    continue
                mid, ref = r['mid'], r['ref']
                ink = [y for y, v in enumerate(mid) if v is not None]
                if not ink:
                    ok(False, '%-8s no ink on the centre column' % name)
                    continue
                # ---- THE GLASS IS MEASURED ON THE COLUMN THE BADGE CANNOT REACH --------------
                # Two earlier builds of this check were vacuous, and the second passed its own
                # falsifier.
                #
                #   (a) taking the LAST dark row of the centre column put the foot of the "glass"
                #       at row 161 of 164, because the tyre and the shadow under the car are dark
                #       as well. The badge was never inside the range being examined.
                #   (b) taking the CONTIGUOUS dark run from the top fixed that and broke the
                #       check: a badge sitting on the glass is bright, so the run simply STOPS
                #       where the badge starts and the range is unbroken by construction. With
                #       the defect served back in, it reported "glass unbroken rows 28-92" and
                #       passed.
                #
                # So the extent of the glass is read off the REFERENCE column instead. The pane is
                # wider than the badge at every height, the reference column is inside it, and
                # nothing is ever drawn on that column between the roof and the rubber - so its
                # dark run is the glass whether the badge is misplaced or not. The centre column
                # is then judged against a range it did not help to define.
                dark = [y for y, v in enumerate(ref) if v is not None and v < DARK]
                if not dark:
                    ok(False, '%-8s no glass on the reference column' % name)
                    continue
                g0 = dark[0]
                g1 = g0
                while g1 + 1 < len(ref) and ref[g1 + 1] is not None and ref[g1 + 1] < DARK:
                    g1 += 1
                # 1. the glass is unbroken between its own top and its own foot
                breaks = [y for y in range(g0, g1 + 1)
                          if mid[y] is not None and mid[y] > BRIGHT]
                ok(not breaks,
                   '%-8s glass unbroken  rows %d-%d' % (name, g0, g1),
                   '' if not breaks
                   else '%d bright row(s), first at %d' % (len(breaks), breaks[0]))
                # 2. and the badge is still drawn, below the glass, on the paint
                marks = [y for y in range(g1 + 1, len(mid))
                         if mid[y] is not None and ref[y] is not None
                         and abs(mid[y] - ref[y]) > 20]
                ok(bool(marks),
                   '%-8s badge below the glass' % name,
                   'rows %d-%d' % (marks[0], marks[-1]) if marks
                   else 'nothing differs from the paint beside it')

            if errs:
                ok(False, 'page errors', errs[0][:140])
            b.close()
    finally:
        srv.shutdown()

    print('  %s' % ('all checks passed' if not bad else '%d check(s) FAILED' % bad))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
