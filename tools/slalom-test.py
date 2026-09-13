#!/usr/bin/env python3
"""SLALOM TEST - at four stars a roadblock is two or three, to be weaved through.

    .venv/Scripts/python tools/slalom-test.py
    .venv/Scripts/python tools/slalom-test.py --falsify

RLG-242. Owner, 2026-09-13: "I want the roadblocks to become more problematic at 4 stars. What I
mean is I want roadblocks to then be 2-3 roadblocks that need to be slalomed."

  1. BELOW FOUR STARS A ROADBLOCK IS STILL ONE.
  2. AT FOUR STARS IT IS A CHAIN OF TWO OR THREE, and both sizes turn up.
  3. THE OPENINGS ALTERNATE SIDES, measured from the PANELS rather than from `gapX`, which only
     says where the opening was meant to be.
  4. THE BLOCKS ARE SPACED `gapZ` APART.
  5. A DRIVER WHO WEAVES THREADS A THREE-BLOCK CHAIN at 150mph, by the game's own count.
  6. A DRIVER WHO HOLDS THE FIRST OPENING'S LINE STRIKES A LATER BLOCK. Without this, check 5 is
     true of a chain that any line gets through, which is not a slalom.

`--falsify` serves the engine with the chain starting at 99 stars, so a four-star roadblock is one
block: checks 2, 3 and 4 must fail and check 1 must pass.

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

GAME = 'games/sw/interstate.html'
NEED = '  stars: 4,'

# force one roadblock event at a wanted level, then drop the heat so the radio sends nobody
FORCE = r"""(stars) => {
  const R = window.__probe.road;
  R.clearTraffic(); R.heat(stars); R.forceRoadblock(); R.heat(0);
  return R.roadblocks().map(b => b.dz);
}"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--falsify', action='store_true')
    ap.add_argument('--mph', type=float, default=150.0,
                    help='the driving checks'' speed; 150 is the checked default')
    args = ap.parse_args()
    console_utf8()

    spec = importlib.util.spec_from_file_location('dt', ROOT / 'tools' / 'drive-test.py')
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

    print('slalom-test  .  at four stars a roadblock is a slalom')
    if args.falsify:
        print('  FALSIFY: the chain starts at 99 stars.')
    try:
        with sync_playwright() as p:
            b = launch_chromium(p, headless=True, args=['--mute-audio'])
            ctx = b.new_context(viewport={'width': 414, 'height': 896})
            ctx.add_init_script(dt.INIT)
            if args.falsify:
                src = (ROOT / 'road.js').read_text(encoding='utf-8')
                if NEED not in src:
                    raise SystemExit('[slalom] --falsify cannot find %r' % NEED)
                src = src.replace(NEED, '  stars: 99,', 1)

                def serve(route):
                    route.fulfill(status=200, content_type='application/javascript', body=src)
                ctx.route('**/road.js', serve)
            pg = ctx.new_page()
            errs = []
            pg.on('pageerror', lambda e: errs.append(str(e)))
            boot(pg, 'http://127.0.0.1:%d/%s' % (port, GAME))
            pg.wait_for_timeout(1500)
            pg.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
            pg.click('[data-act="play"]')
            pg.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
            pg.click('[data-act="drive"]')
            pg.wait_for_timeout(1800)
            pg.evaluate("() => window.__probe.road.setTimed(false)")
            cfg = pg.evaluate("() => window.__probe.road.slalom()")

            # 1 and 2: the size of a roadblock event, at three stars and at four
            three = [len(pg.evaluate(FORCE, 3)) for _ in range(6)]
            four = [len(pg.evaluate(FORCE, 4)) for _ in range(24)]
            ok(set(three) == {1}, 'below four stars a roadblock is still one block',
               'sizes seen %s' % sorted(set(three)))
            ok(set(four) == {2, 3}, 'at four stars it is a chain of two or three, both sizes seen',
               'sizes seen %s' % sorted(set(four)))

            # 3 and 4: openings measured off the panels, and the spacing, over several chains
            alternate = spaced = True
            detail3 = detail4 = ''
            for _ in range(8):
                pg.evaluate(FORCE, 4)
                opens = pg.evaluate("() => window.__probe.road.roadblockOpenings()")
                if len(opens) < 2:
                    alternate = spaced = False
                    detail3 = detail4 = '%d block(s)' % len(opens)
                    break
                for a, c in zip(opens, opens[1:]):
                    if not (a['open'] * c['open'] < 0 and abs(a['open']) > 0.3 and abs(c['open']) > 0.3):
                        alternate = False
                        detail3 = 'openings %s' % [round(o['open'], 2) for o in opens]
                    if abs((c['dz'] - a['dz']) - cfg['gapZ']) > 5:
                        spaced = False
                        detail4 = 'spacing %s' % [c2['dz'] - a2['dz'] for a2, c2 in zip(opens, opens[1:])]
            ok(alternate, 'the openings alternate sides, measured off the panels', detail3)
            ok(spaced, 'the blocks are %d units apart' % cfg['gapZ'], detail4)

            # 5 and 6: drive a three-block chain two ways
            def drive(weave):
                pg.evaluate("() => { const R = window.__probe.road; R.slalom({min: 3, max: 3}); }")
                before = pg.evaluate("() => window.__probe.road.slalom()")
                n = len(pg.evaluate(FORCE, 4))
                pg.evaluate("() => window.__probe.road.slalom({min: 2, max: 3})")
                if n < 2:
                    return None
                first = pg.evaluate("() => window.__probe.road.roadblockOpenings()")[0]['open']
                for _ in range(600):
                    left = pg.evaluate("""([weave, first, mph]) => {
                      const R = window.__probe.road;
                      R.traffic.length = 0;
                      R.setSpd(R.MAX_SPD * mph / 200);
                      const open = R.roadblockOpenings().filter(o => !o.hit && o.dz > -400);
                      if (!open.length) return 0;
                      R.steerOver(weave ? open[0].open : first, 0.12);
                      return open.length;
                    }""", [weave, first, args.mph])
                    pg.wait_for_timeout(40)
                    if left == 0:
                        break
                after = pg.evaluate("() => window.__probe.road.slalom()")
                return {'blocks': n, 'threaded': after['threaded'] - before['threaded'],
                        'struck': after['struck'] - before['struck']}

            if args.falsify:
                ok(True, '(the driving checks need a chain and are skipped under --falsify)')
            else:
                w = drive(True)
                ok(w is not None and w['blocks'] == 3 and w['threaded'] == 3 and w['struck'] == 0,
                   'a driver who weaves threads a three-block chain at %.0fmph' % args.mph, str(w))
                h = drive(False)
                ok(h is not None and h['blocks'] == 3 and h['struck'] >= 1,
                   'a driver who holds the first opening strikes a later block', str(h))
            if errs:
                ok(False, 'page errors', errs[0][:140])
            b.close()
    finally:
        srv.shutdown()

    print('  %s' % ('all checks passed' if not bad else '%d check(s) FAILED' % bad))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
