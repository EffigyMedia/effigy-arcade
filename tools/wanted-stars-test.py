#!/usr/bin/env python3
"""WANTED STARS TEST - the stars say hot or cold, and the pursuit row is gone.

    .venv/Scripts/python tools/wanted-stars-test.py

RLG-178. Owner, 2026-09-08: "I wanna just remove the pursuit banner. I think there's a better way
we can express being actively engaged or not: if you are actively being engaged then the stars'
fill is golden, if you are on active cooldown the fill is the same colour as the blue edge to
represent being cold instead of hot. I think the outline of the stars should be gold when you're
hot and blue when you're cold, along with the fill."

THE FOUR CLAIMS:

  1. neither cabinet has a pursuit row any more
  2. driving legally past parked traps, the stars are COLD
  3. with a cruiser engaged to the player, they are HOT
  4. and the two states really are different colours on the screen

WHY CLAIM 4 IS SEPARATE FROM CLAIM 3. A class name is not a colour. `hot` could be toggling
perfectly onto an element whose stylesheet says nothing about it - which is exactly what happened
while this was being built: the class was put on the WRAPPER and the rule was written for the
ROW, so the state was correct, the CSS was correct, and nothing changed on the screen. So the
check reads the computed stroke and fill and asserts they move.

AND CLAIM 2 NEEDS TRAPS ON THE ROAD TO MEAN ANYTHING. An empty road is cold trivially. The old
defect was a PARKED car counting as a pursuit, so the check keeps one parked nearby the whole
time it reads cold.

Exit code 0 if every check passed, 1 otherwise.
"""
import argparse
import functools
import http.server
import io
import re
import socketserver
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from harness import console_utf8, launch_chromium, boot, until
from playwright.sync_api import sync_playwright

GAME = 'games/sw/interstate.html'

STATE = """() => {
  const w = document.getElementById('wanted');
  if(!w) return null;
  const on = w.querySelector('b.on') || w.querySelector('b');
  const cs = on ? getComputedStyle(on) : null;
  return {
    hot: w.classList.contains('hot'),
    stroke: cs ? (cs.webkitTextStrokeColor || cs.getPropertyValue('-webkit-text-stroke-color')) : null,
    star: getComputedStyle(w).getPropertyValue('--star').trim(),
    row: !!document.getElementById('pursuit')
  };
}"""

HOT = """() => {
  const R = window.__road;
  R.copsClear();
  R.placeCop(-2600, 0.35);
  window.__hold = setInterval(() => {
    const k = R.cops()[0];
    if(!k) return;
    k.z = R.pos + R.PLAYER_Z - 2600;
    k.onPlayer = true; k.engaged = true; k.tgt = null; k.wreck = 0;
  }, 8);
  return true;
}"""


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

    print('wanted-stars-test  .  gold when hot, blue when cold')

    # ---- 1. THE ROW IS GONE FROM THE SOURCE OF BOTH CABINETS ---------------
    # READ FROM THE FILES, not from a running page: an element can be absent at
    # runtime because a script removed it, which is not the same as it not being
    # in the product. And the styles have to go with it, or a stray rule outlives
    # the thing it styled.
    for name in ('interstate', 'motorsport'):
        p = ROOT / 'games' / 'sw' / ('%s.html' % name)
        src = io.open(str(p), encoding='utf-8').read()
        has_el = 'id="pursuit"' in src
        has_css = re.search(r'#pursuit\s*[{.]', src) is not None
        ok(not has_el and not has_css, 'no pursuit row left in %s' % name,
           'element=%s css=%s' % (has_el, has_css))

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
            page.wait_for_timeout(1000)
        except Exception:
            pass
        page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
        page.click('[data-act="play"]')
        page.wait_for_timeout(300)
        page.click('[data-act="chase"]')
        page.wait_for_timeout(150)
        page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
        page.click('[data-act="drive"]')
        page.wait_for_timeout(2000)

        # ---- 2. LEGAL, WITH A TRAP PARKED NEARBY: COLD ---------------------
        page.evaluate('() => window.__road.copsClear()')
        page.evaluate('() => window.__road.spawnTrap()')
        page.evaluate('() => window.__road.heat(2)')
        hot_frames, traps_seen, cold = 0, 0, None
        for _ in range(60):
            page.evaluate('() => { window.__road.traffic.length = 0; }')
            page.evaluate('() => window.__road.setSpd(0.30 * window.__road.MAX_SPD)')
            page.wait_for_timeout(100)
            if page.evaluate('() => window.__road.cops().filter(k => k.trap).length') > 0:
                traps_seen += 1
            else:
                page.evaluate('() => window.__road.spawnTrap()')
            st = page.evaluate(STATE)
            if st and st['hot']:
                hot_frames += 1
            cold = st
        ok(traps_seen > 30, 'a trap really was parked while this was read',
           '%d of 60 samples had one' % traps_seen)
        ok(hot_frames == 0, 'driving legally past a parked trap leaves the stars cold',
           '%d of 60 samples went hot' % hot_frames)
        ok(bool(cold) and cold['row'] is False,
           'and no pursuit row exists on the page either', str(cold))

        # ---- 3. A CRUISER ENGAGED: HOT ------------------------------------
        page.evaluate(HOT)
        hot = None
        for _ in range(40):
            page.evaluate('() => window.__road.setSpd(0.55 * window.__road.MAX_SPD)')
            page.wait_for_timeout(100)
            st = page.evaluate(STATE)
            if st and st['hot']:
                hot = st
                break
        ok(hot is not None, 'a cruiser engaged to you turns them hot',
           str(hot or page.evaluate(STATE)))

        # ---- 4. AND THE TWO STATES LOOK DIFFERENT --------------------------
        ok(bool(hot) and bool(cold) and hot['star'] != cold['star'],
           'and hot and cold are different colours',
           'cold %s -> hot %s' % (cold and cold['star'], hot and hot['star']))
        ok(bool(hot) and bool(cold) and hot['stroke'] != cold['stroke'],
           'including the outline, which is what was asked for',
           'cold %s -> hot %s' % (cold and cold['stroke'], hot and hot['stroke']))

        ok(not errs, 'and the run was clean', '; '.join(errs[:2]))
        ctx.close()
        b.close()

    print('  %s' % ('all checks passed' if not bad else '%d check(s) failed' % bad))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
