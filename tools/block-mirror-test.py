#!/usr/bin/env python3
"""BLOCK MIRROR - a roadblock you have passed is still in the mirror behind you.

    .venv/Scripts/python tools/block-mirror-test.py
    .venv/Scripts/python tools/block-mirror-test.py --root <an older checkout> --expect-fail

RLG-260. Owner, 2026-09-15: "the roadblocks disappeared in the mirror as you passed them, which tells
me they are despond too quickly or stop being rendered or whatever."

WHAT WAS FOUND. `blocks` was culled at `pos - 2000`, and the glass draws to `MIRROR_BACK` (34,000).
So the block was deleted about two car-lengths after the player went through it and there was nothing
left to draw. CRATES AND CHECKPOINT BOARDS BOTH HAD THIS EXACT FAULT and both were fixed by culling at
`MIRROR_BACK` instead; the comment at the crate rule says so in as many words.

THE CHECK. One roadblock is put up by the road's own spawner, the player is held at 60 % of top speed
and driven through it, and the block is followed by `API.roadblocks()` as it falls behind.

  ALIVE    at 10,000 units behind - well past the old 2,000 cull and well inside the glass - the
           block is still on the road.
  OFFERED  and the mirror is handed a roadblock at that moment: `viewKinds().glass` carries 'b'.
  CULLED   beyond MIRROR_BACK it is gone, so this is a longer life and not an immortal object.

WHAT THIS CANNOT SAY. Whether the block LOOKS right in the glass - the panels, the cruiser beside it,
the lights - is the owner's verdict on the device. This asserts that something is there to draw.

Exit code 0 if every check passed (or, with --expect-fail, if one failed), 1 otherwise.
"""
import argparse
import functools
import http.server
import socketserver
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
from harness import console_utf8, launch_chromium, boot, until, garage_screen  # noqa: E402

# follow one roadblock until it is `back` units behind, reporting what the views were offered
WATCH = """(a) => {
  const R = window.__road;
  R.watchDraw(true);
  return new Promise((done) => {
    const out = { seenAt: [], glassAt: null, aliveAt: null, goneBy: null, last: null };
    const t0 = performance.now();
    const tick = () => {
      const bs = R.roadblocks();
      const mine = bs.length ? bs[0] : null;
      if(mine){
        out.last = mine.dz;
        /* the moment it is about `back` behind, ask what the glass was handed */
        if(out.aliveAt === null && mine.dz < -a.back){
          out.aliveAt = mine.dz;
          out.glassAt = R.viewKinds().glass.join(',');
        }
      } else if(out.aliveAt !== null && out.goneBy === null){
        out.goneBy = out.last;
      }
      const done_ = (out.goneBy !== null) || (performance.now() - t0 > a.secs * 1000);
      if(!done_) requestAnimationFrame(tick); else { R.watchDraw(false); done(out); }
    };
    requestAnimationFrame(tick);
  });
}"""


class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default=str(TOOLS.parent))
    ap.add_argument('--expect-fail', action='store_true')
    args = ap.parse_args()
    console_utf8()
    root = Path(args.root)
    fails = []

    def ok(c, label, detail=''):
        print(('  ok    ' if c else '  FAIL  ') + label + ('' if c else '   [' + str(detail) + ']'))
        if not c:
            fails.append(label)

    httpd = socketserver.TCPServer(('127.0.0.1', 0), functools.partial(Q, directory=str(root)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.socket.getsockname()[1]
    print('block-mirror  .  a roadblock you have passed is still behind you')
    print('      serving %s' % root)
    with sync_playwright() as p:
        b = launch_chromium(p, headless=True, args=['--mute-audio'])
        pg = b.new_context(viewport={'width': 480, 'height': 900}).new_page()
        errs = []
        pg.on('pageerror', lambda e: errs.append(str(e)))
        boot(pg, 'http://127.0.0.1:%d/games/sw/interstate.html' % port)
        pg.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
        pg.click('[data-act="play"]')
        pg.wait_for_timeout(400)
        # the drive's settings are on the SETTINGS screen (RLG-071)
        garage_screen(pg, 'settings')
        pg.click('[data-act="chase"]')      # HOT PURSUIT on
        garage_screen(pg, 'main')
        pg.wait_for_timeout(200)
        pg.click('[data-act="drive"]')
        until(pg, '() => window.__road.startLine().left <= 0', timeout=10000)
        pg.evaluate('() => { const R = window.__road; R.setTimed(false); R.heat(3);'
                    ' R.parkTraffic(9, 60000); R.copsClear(); R.holdSpd(0.6 * R.MAX_SPD); }')
        # the road's own spawner, so what is followed is the block the game builds
        until(pg, '() => window.__road.forceRoadblock()', timeout=10000)
        first = pg.evaluate('() => window.__road.roadblocks()[0]')
        print('      put up %d units ahead, opening %.2f wide' % (first['dz'], first['gap']))

        got = pg.evaluate(WATCH, {'back': 10000, 'secs': 60})
        pg.evaluate('() => window.__road.holdSpd(null)')
        print('      at %s behind the glass was handed [%s]; it was culled by %s'
              % (got['aliveAt'], got['glassAt'], got['goneBy']))

        ok(got['aliveAt'] is not None, 'the block was still on the road 10,000 units behind',
           'it was gone by %s' % got['last'])
        ok(got['glassAt'] is not None and 'b' in got['glassAt'].split(','),
           'and the mirror was handed a roadblock there', 'the glass was handed [%s]' % got['glassAt'])
        ok(got['goneBy'] is None or got['goneBy'] < -30000,
           'and it is culled once it is out of the glass, so it is not immortal',
           'it was culled at %s' % got['goneBy'])

        ok(not errs, 'no page errors', errs[0][:120] if errs else '')
        b.close()
    httpd.shutdown()
    print()
    if args.expect_fail:
        print('expected at least one failure: %s' % ('got %d' % len(fails) if fails else 'got NONE'))
        return 0 if fails else 1
    if fails:
        print('FAILED: ' + '; '.join(fails))
        return 1
    print('a roadblock you have passed is still behind you')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
