#!/usr/bin/env python3
"""CAR ENDS TEST - every car's front and its own back, measured on the garage card.

    .venv/Scripts/python tools/car-ends-test.py

RLG-182. Owner, 2026-09-09: "The height of the vehicles aren't the same. Every vehicle needs to
have the same height, and we need to show a little bit of the tires on the bottom. Run this check
against every vehicle." And, clarifying: "I mean its front relative to its back, not different
vehicles relative to each other."

SO THE CLAIM IS PER CAR. A MATADOR's face and a MATADOR's tail have to agree with each other; a
MATADOR and a CAB do not. Every garage body is measured, not the three a fresh save can drive -
the silhouettes put seven more cards in front of the player and the complaint came from one of
them.

WHAT IS MEASURED IS WHERE THE PICTURES LAND, not what the sprites contain. `garageFit` picks ONE
scale for both ends and `put` places each with its CONTENT's top on the ceiling line, so two ends
of different ink heights start together and finish apart. The engine reports the ink box, the
shared scale and the resulting top and bottom for each end.

AND THE CODE'S OWN COMMENT SAYS IT SHOULD NOT BE SO: "Both are then drawn at ONE scale... with
their content bottoms on the same line. A car is the same size from both ends and stands on the
same floor, which is the whole of what the owner asked for." The scale half is true. The floor
half is not what the code does.

THIS FILE IS A MEASUREMENT FIRST AND A GATE SECOND. It prints every car either way, because the
owner asked to see the check run against every vehicle.

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
from harness import console_utf8, launch_chromium, boot, until
from playwright.sync_api import sync_playwright

GAME = 'games/sw/interstate.html'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--headed', action='store_true')
    ap.add_argument('--tol', type=float, default=2.0,
                    help='how many CSS pixels the two ends may differ by')
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

    print('car-ends-test  .  every car, its front against its own back')
    with sync_playwright() as p:
        b = launch_chromium(p, headless=not args.headed,
                            args=['--mute-audio', '--autoplay-policy=no-user-gesture-required'])
        ctx = b.new_context(viewport={'width': 480, 'height': 900})
        page = ctx.new_page()
        errs = []
        page.on('pageerror', lambda e: errs.append(str(e)))
        boot(page, '%s/%s' % (base, GAME))
        try:
            until(page, '() => navigator.serviceWorker && navigator.serviceWorker.controller', timeout=5000)
            page.wait_for_timeout(1200)
        except Exception:
            pass
        page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
        page.click('[data-act="play"]')
        page.wait_for_timeout(600)

        ends = page.evaluate('() => window.__road.carEnds()')
        rows, worst, worst_car = [], 0.0, None
        print('  %-14s %9s %9s %8s %8s' %
              ('CAR', 'back WxH', 'front WxH', 'dW', 'dH'))
        for k in sorted(ends):
            e = ends[k]
            if not e or not e['front']:
                print('  %-14s  (one end only)' % k)
                continue
            bh, fh = e['back']['drawnH'], e['front']['drawnH']
            diff = abs(bh - fh)
            rows.append((k, diff))
            if diff > worst:
                worst, worst_car = diff, k
            bw, fw = e['back']['inkW'], e['front']['inkW']
            bih, fih = e['back']['inkH'], e['front']['inkH']
            print('  %-14s %4dx%-4d %4dx%-4d %8d %8d%s'
                  % (k, bw, bih, fw, fih, fw - bw, fih - bih,
                     '' if (fw == bw and fih == bih) else '   <-- differs'))

        # ---- AND THE SILHOUETTE ITSELF (owner, 2026-09-09) -------------------
        # "It's not just the height and the width that need to match, but their
        # silhouettes need to match too, because it's looking at the same vehicle
        # straight on from the front and straight on from the back."
        #
        # A BOUNDING BOX CANNOT ANSWER THAT: two drawings can agree on width and
        # height and still be different shapes. The engine reports each end's ink
        # profile - the top and bottom of the ink in each of 24 columns, as a
        # fraction of the box - with the front MIRRORED, because a face and a tail
        # are the same car seen from opposite ends.
        print('')
        print('  %-14s %9s %9s   %s' % ('CAR', 'meanErr', 'worstCol', 'silhouette'))
        prof_rows = []
        for k in sorted(ends):
            if not ends[k] or not ends[k]['front']:
                continue
            pr = page.evaluate('([k, n]) => window.__road.carProfile(k, n)', [k, 24])
            if not pr or not pr['back'] or not pr['front']:
                print('  %-14s  (profile unavailable)' % k)
                continue
            errs_col = []
            # NOT `b` - that is the browser. Shadowing it here closed nothing at the
            # end of the run and the whole file died after printing its results.
            for ca, cb in zip(pr['back'], pr['front']):
                if ca is None or cb is None:
                    errs_col.append(1.0)
                    continue
                errs_col.append(max(abs(ca['t'] - cb['t']), abs(ca['b'] - cb['b'])))
            mean = sum(errs_col) / len(errs_col)
            # NOT `worst` - that is the height check's own worst, and shadowing
            # it here made the height failure report "worst CREST by 0.0px",
            # which is a number from the profile loop and not a height at all
            worst_col = max(errs_col)
            prof_rows.append((k, mean, worst_col))
            print('  %-14s %8.1f%% %8.1f%%   %s'
                  % (k, mean * 100, worst_col * 100,
                     'match' if worst_col <= 0.04 else 'DIFFERENT SHAPE'))
        bad_shape = [k for k, m, w in prof_rows if w > 0.04]
        ok(bool(prof_rows), 'every car had its outline read',
           '%d profiled' % len(prof_rows))
        ok(not bad_shape,
           "and each car's two ends are the same shape",
           '%d of %d are not' % (len(bad_shape), len(prof_rows)) if bad_shape else '')

        off = [k for k, d in rows if d > args.tol]
        ok(bool(rows), 'every garage car was measured', '%d cars with two ends' % len(rows))
        ok(not off,
           "each car's two ends are drawn the same height",
           '%d of %d disagree, worst %s by %.1fpx'
           % (len(off), len(rows), worst_car, worst) if off else '')
        ok(not errs, 'and the run was clean', '; '.join(errs[:2]))
        ctx.close()
        b.close()

    print('  %s' % ('all checks passed' if not bad else '%d check(s) failed' % bad))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
