#!/usr/bin/env python3
"""HAZARD TEST - each side of the road is a hazard or a solid, and the table says which.

    .venv/Scripts/python tools/hazard-test.py

RLG-265. Owner, 2026-09-15, on the biomes: "the side with the mountainous stuff does not have
a guard rail and hitting the mountainous stuff is the physical stuff you can bang up against
just like coastal and farmland."

A RAIL GOES WHERE NOTHING IS. A hazard side is a drop or open water - the rail is the only
thing that can stop you there, so it earns its place. A solid side is rock, trees, a fence
line or a bank, and a rail in front of one is the road furniture RLG-264 deleted.

WHY THIS IS A NUMBER CHECK AND NOT A SCREENSHOT. A rail drawn on the landward side of a coast
is a rail correctly drawn as far as any picture is concerned: it is the right object, the right
colour, in the right place on the screen. Only the SIDE is wrong, and the side is the whole
ruling. So the table is read off `API.edgeOf` and asserted, and the drawing is checked
elsewhere.

AND IT ASSERTS THE COIN IS NOT STUCK. A mountain's cliff falls on either side per stretch. One
stretch cannot tell a working coin from a jammed one, and `rollSide`'s own note records exactly
that fault being missed - 40 out of 40 on one side while the game was rolling correctly. So
this rolls many times and requires both answers, and it requires the mountain's coin to
DISAGREE with the sea's often enough to prove they are two coins rather than one read twice.
"""

import functools
import http.server
import socketserver
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from harness import console_utf8, launch_chromium, boot, until

GAME = 'games/sw/interstate.html'

INIT = r"""
window.__probe = { errors: [], road: null };
(function(){
  var real = null, wrapped = null;
  Object.defineProperty(window, 'ROAD', {
    configurable: true,
    get: function(){ return real ? wrapped : undefined; },
    set: function(fn){
      real = fn;
      wrapped = function(CFG){
        var api = real(CFG);
        window.__probe.road = api || (CFG && CFG.api) || null;
        return api;
      };
    }
  });
})();
window.addEventListener('error', function(e){ window.__probe.errors.push(String(e.message)); });
"""

# THE SETTLED TABLE, from the ruling. `rail` means a railed hazard side exists and which coin
# decides it; `barrier` means a drawn limit on BOTH sides; None means solid both sides and
# nothing drawn. Written out here rather than read from the engine, because a check that asks
# the code what it does and then agrees with the answer proves nothing.
WANT = {
    'COASTAL':  'water',     # the sea
    'SWAMP':    'water',     # the standing water
    'MOUNTAIN': 'roll',      # the cliff, either side, per stretch
    'CITY':     'barrier',   # concrete, both sides
    'FARMLAND': None, 'DESERT': None, 'TUNDRA': None, 'FOREST': None,
    'JUNGLE':   None, 'CANYON': None, 'BRIDGE': None, 'TUNNEL': None,
}


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def serve(root):
    handler = functools.partial(QuietHandler, directory=str(root))
    httpd = socketserver.TCPServer(('127.0.0.1', 0), handler)
    httpd.allow_reuse_address = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.socket.getsockname()[1]


def main():
    console_utf8()
    fails = []

    def check(ok, label, detail=''):
        print('  %s  %s%s' % ('ok  ' if ok else 'FAIL', label,
                              '   ' + detail if detail else ''))
        if not ok:
            fails.append(label)

    httpd, port = serve(ROOT)
    print('hazard-test  .  a hazard side is railed, a solid side is not')
    print()
    with sync_playwright() as p:
        browser = launch_chromium(p, headless=True)
        page = browser.new_page(viewport={'width': 480, 'height': 900})
        page.add_init_script(INIT)
        boot(page, 'http://127.0.0.1:%d/%s' % (port, GAME))
        until(page, '!!window.__probe.road', timeout=15000)

        keys = page.evaluate("() => window.__probe.road.BIOME_KEYS()")
        check(sorted(keys) == sorted(WANT), 'the board is the twelve places this table covers',
              '%d on the board, %d in the table' % (len(keys), len(WANT)))
        if sorted(keys) != sorted(WANT):
            print('     on the board and not in the table: %s'
                  % sorted(set(keys) - set(WANT)))
            print('     in the table and not on the board: %s'
                  % sorted(set(WANT) - set(keys)))

        print()
        print('  WHAT STANDS AT EACH LIMIT')
        for k in keys:
            want = WANT.get(k)
            left = page.evaluate("(k) => window.__probe.road.edgeOf(k, -1)", k)
            right = page.evaluate("(k) => window.__probe.road.edgeOf(k, 1)", k)
            haz = page.evaluate("(k) => window.__probe.road.hazardSideOf(k)", k)
            print('      %-9s left %-8s right %-8s hazard side %+d'
                  % (k, str(left), str(right), haz))
            if want == 'barrier':
                check(left == 'barrier' and right == 'barrier',
                      '%s has a drawn limit on both sides' % k)
            elif want is None:
                check(left is None and right is None,
                      '%s is solid on both sides - nothing drawn' % k)
            else:
                # EXACTLY ONE SIDE. A hazard place railed on both sides would be a corridor,
                # which is what the ruling explicitly is not.
                one = (left == 'rail') != (right == 'rail')
                check(one and (left in ('rail', None)) and (right in ('rail', None)),
                      '%s is railed on exactly one side' % k,
                      'the hazard is on %s' % ('the left' if haz < 0 else 'the right'))
                check(haz in (-1, 1), '%s names a side rather than neither' % k)

        # ---- THE TWO COINS, AND THAT THEY ARE TWO ------------------------------------------
        print()
        print('  THE COINS, OVER 200 ROLLS')
        rolls = page.evaluate("""() => {
          const R = window.__probe.road, out = [];
          for(let i = 0; i < 200; i++){ R.rollSide(); out.push([R.sideRoll(), R.hazardRoll()]); }
          return out;
        }""")
        sea = [r[0] for r in rolls]
        cliff = [r[1] for r in rolls]
        agree = sum(1 for a, b in rolls if a == b)
        print('      the sea coin    left %3d   right %3d' % (sea.count(-1), sea.count(1)))
        print('      the cliff coin  left %3d   right %3d' % (cliff.count(-1), cliff.count(1)))
        print('      they agreed on %d of %d rolls' % (agree, len(rolls)))
        check(cliff.count(-1) > 0 and cliff.count(1) > 0,
              "a mountain's cliff falls on both sides across stretches",
              'left %d, right %d' % (cliff.count(-1), cliff.count(1)))
        # TWO COINS, NOT ONE READ TWICE. One coin read twice agrees 200 times out of 200. Two
        # fair coins agree about half the time; anything past 90% of rolls is a welded pair.
        check(0.10 < agree / len(rolls) < 0.90,
              'the cliff coin is a SECOND coin rather than the sea coin read twice',
              '%.0f%% agreement - one coin read twice would be 100%%'
              % (100.0 * agree / len(rolls)))

        errs = page.evaluate("() => window.__probe.errors")
        check(not errs, 'no page errors', '; '.join(errs[:2]))
        browser.close()
    httpd.shutdown()

    print()
    if fails:
        print('  %d check(s) FAILED' % len(fails))
        return 1
    print('  the table holds')
    print('  it says nothing about whether a rail is DRAWN, or drawn well - that is')
    print('  the next part of RLG-265 and it is settled by looking.')
    return 0


sys.exit(main())
