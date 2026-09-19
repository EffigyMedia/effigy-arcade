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
ruling. So the table is read off `API.edgeOf` and asserted as numbers.

AND THE DRAWING IS MEASURED DIFFERENTIALLY, in the second half. The same place is rendered
with the rails off and then on, and the difference IS the rail - whatever colour it is, with
no guessing at steel grey against a white shoulder line or a concrete-toned city ground. Then
the same place is rendered again with the hazard forced to the other side, and the rail's mean
position must MOVE. An absolute left-or-right test cannot settle this: a rail converges on the
vanishing point, so its far end crosses the middle of the screen whichever side it stands on,
and that read as 101 pixels of phantom rail on a coast's landward side.

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


# ---- WHERE THE BAR BETWEEN "NO RAIL" AND "A RAIL" SITS, MEASURED ---------------------
# A place with no rail is not a dead-still picture: a few pixels move between the two frames
# whatever is pinned, and FARMLAND has been seen at 0, 2, 6, 8, 14, 15 and 41. A place WITH
# one reports 233 to 1,401. The two are separated by an empty band of more than five to one,
# and this sits in the middle of it rather than against either edge. A first version at 40
# failed one run in three on a farmland reading 41, which is a threshold drawn on the noise.
BARE = 120


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def serve(root):
    handler = functools.partial(QuietHandler, directory=str(root))
    httpd = socketserver.TCPServer(('127.0.0.1', 0), handler)
    httpd.allow_reuse_address = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.socket.getsockname()[1]


def rail_pixels(a, b, band='road'):
    """where the pixels that changed between two frames sit, and how many there are.

    Returns (count, mean x). ABSOLUTE POSITION CANNOT SETTLE WHICH SIDE A RAIL IS ON: a rail
    converging on the vanishing point crosses the middle of the screen whichever side of the
    road it stands on, and the first version of this check read that as 101 pixels of rail on
    a coast's landward side, where there is none. So the caller renders the SAME place with
    the hazard forced to each side and compares the two means. Every other term - the road,
    the light, the scenery, the vanishing point's own offset - is shared and cancels.
    """
    import io
    from PIL import Image
    ia = Image.open(io.BytesIO(a)).convert('RGB')
    ib = Image.open(io.BytesIO(b)).convert('RGB')
    w, h = ia.size
    pa, pb = ia.load(), ib.load()
    n = 0
    sx = 0
    # `band` picks WHICH VIEW is being measured. The road pass owns the lower half; the
    # mirror is its own pane near the top and has to be asked for separately, because a
    # change up there is the GLASS agreeing rather than a second rail on the road.
    # RLG-280 is the reason it is asked at all: everything RLG-265 drew was invisible
    # behind you, and this check passed the whole time by only ever looking forward.
    y0, y1 = ((int(h * 0.42), h) if band == 'road'
              else (int(h * 0.045), int(h * 0.125)))
    for y in range(y0, y1, 2):
        for x in range(0, w, 2):
            ca, cb = pa[x, y], pb[x, y]
            if abs(ca[0]-cb[0]) + abs(ca[1]-cb[1]) + abs(ca[2]-cb[2]) > 24:
                n += 1
                sx += x
    return n, (sx / n if n else w / 2.0)


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

        # ---- AND THE RAIL IS ACTUALLY DRAWN, ON THAT SIDE --------------------------
        # NOT BY HUNTING FOR ITS COLOUR. Steel grey has to be told from a white shoulder
        # line, from wet tarmac and from a city's concrete-toned ground, and every one of
        # those guesses is a way to report a rail that is not there. The same frame is
        # rendered with the rails OFF and the two are differenced: whatever changed IS the
        # rail, whatever colour it happens to be.
        #
        # AND THE SIDE IS MEASURED DIFFERENTIALLY. The same place is rendered with the
        # hazard forced left and then forced right, and the rail's mean position must MOVE
        # between them. An absolute left-or-right test cannot work: the rail converges on
        # the vanishing point, so its far end crosses the middle of the screen whichever
        # side it is on, and that read as a phantom rail on a coast's landward side.
        print()
        print('  AND IT IS DRAWN, ON THE SIDE THE TABLE NAMES')
        page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
        page.click('[data-act="play"]')
        page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=8000)
        page.click('[data-act="drive"]')
        page.wait_for_timeout(1600)
        for _ in range(40):
            st = page.evaluate("() => window.__probe.road.startLine()")
            if st['left'] <= 0 and st['go'] <= 0:
                break
            page.wait_for_timeout(90)

        def settle(k, side):
            """pin the place, the light, the curve and the car, with the hazard on `side`"""
            page.evaluate("([k, s]) => { const R = window.__probe.road;"
                          " R.setTimed(false); R.holdCurve(0); R.holdSpd(null);"
                          " R.setBiomePair(k, k); R.setPhase(0.75);"
                          " R.setWet(0); R.setSnow(0); R.setPool(0); R.clearTraffic();"
                          " R.setHazardSide(s); R.setSeaSide(s);"
                          " R.setSpd(R.MAX_SPD * 0.35); }", [k, side])
            for _ in range(14):
                page.evaluate("() => { const R = window.__probe.road;"
                              " R.clearTraffic(); R.setSpd(R.MAX_SPD * 0.35); }")
                page.wait_for_timeout(40)
            for _ in range(12):
                page.evaluate("() => { const R = window.__probe.road;"
                              " R.clearTraffic(); R.holdSpd(0); R.setPhase(0.75); }")
                page.wait_for_timeout(40)

        def rail_of(k, side):
            settle(k, side)
            page.evaluate("() => { const R = window.__probe.road;"
                          " R.holdSpd(0); R.railsOff(true); }")
            page.wait_for_timeout(90)
            off = page.screenshot()
            page.evaluate("() => { const R = window.__probe.road;"
                          " R.holdSpd(0); R.railsOff(false); }")
            page.wait_for_timeout(90)
            on = page.screenshot()
            return rail_pixels(on, off)

        for k in ('COASTAL', 'MOUNTAIN', 'CITY', 'FARMLAND'):
            nL, xL = rail_of(k, -1)
            nR, xR = rail_of(k, 1)
            print('      %-9s hazard left: %4d px at x=%5.1f    hazard right: %4d px at x=%5.1f'
                  % (k, nL, xL, nR, xR))
            want = WANT.get(k)
            if want is None:
                check(nL < BARE and nR < BARE, '%s draws no rail at all' % k,
                      '%d and %d pixels changed' % (nL, nR))
            elif want == 'barrier':
                # A CITY IGNORES THE COIN, so its two renders must be the SAME picture.
                check(nL > BARE and nR > BARE,
                      '%s draws its barrier down both sides' % k,
                      '%d and %d pixels' % (nL, nR))
                check(abs(xL - xR) < 30,
                      '%s does not move when the coin turns - a barrier is not a hazard' % k,
                      'x=%.1f against x=%.1f' % (xL, xR))
            else:
                check(nL > BARE and nR > BARE, '%s draws a rail whichever side the hazard is' % k,
                      '%d and %d pixels' % (nL, nR))
                # THE RULING IS THE SIDE. The rail must sit further left when the hazard is
                # left than when it is right, by more than any noise in the picture.
                check(xR - xL > 60, '%s puts the rail on the side the hazard is' % k,
                      'x=%.1f with the hazard left, x=%.1f with it right' % (xL, xR))

        # ---- AND A CLIFF IS A DROP, SO NOTHING STANDS ON IT (RLG-265) --------------
        # Owner, 2026-09-15: "The side with the mountainous stuff does not have a guard
        # rail and hitting the mountainous stuff is the physical stuff you can bang up
        # against." The other side is air, and a rock face standing in mid-air beside a
        # guard rail is the picture this forbids.
        #
        # COUNTED, NOT LOOKED AT. `scenerySides` counts the objects the engine actually
        # drew, per side, so this cannot be satisfied by scenery that is merely hidden -
        # and the count is taken with the hazard forced BOTH ways, because a mountain that
        # always emptied the left would pass a check that only ever looked left.
        print()
        print('  AND NOTHING STANDS ON A CLIFF')
        for side in (-1, 1):
            settle('MOUNTAIN', side)
            page.evaluate("() => { const R = window.__probe.road;"
                          " R.resetScenerySides(); R.setSpd(R.MAX_SPD * 0.10); }")
            page.wait_for_timeout(700)
            sc = page.evaluate("() => window.__probe.road.scenerySides()")
            drop, solid = ((sc['left'], sc['right']) if side < 0
                           else (sc['right'], sc['left']))
            print('      hazard %s:  the drop side drew %4d,  the solid side drew %4d'
                  % ('left ' if side < 0 else 'right', drop, solid))
            check(solid > 20, 'the solid side of a mountain still carries its rock',
                  '%d objects' % solid)
            check(drop == 0, 'and the cliff side carries nothing at all',
                  '%d objects on the drop' % drop)
            # AND IN THE MIRROR (owner, 2026-09-19): "if you look in the rearview of a
            # mountain biome ... it's still rocks on both sides." The glass has its own
            # scenery loop, and it had never learned to skip the drop.
            mdrop, msolid = ((sc['mLeft'], sc['mRight']) if side < 0
                             else (sc['mRight'], sc['mLeft']))
            print('      in the mirror:  the drop side drew %4d,  the solid side drew %4d'
                  % (mdrop, msolid))
            check(msolid > 0 and mdrop == 0,
                  'and the mirror carries rock on the solid side and nothing on the drop',
                  '%d on the drop, %d on the solid side' % (mdrop, msolid))

        # ---- AND THE GROUND STOPS AT THE RIM (RLG-278) -----------------------------
        # Owner, 2026-09-16: "that sheer cliff face on the mountain biome does not read
        # as a cliff down." Emptying the side left ORDINARY GROUND running away to the
        # horizon, so the rail said there was a fall and the ground said there was a
        # field.
        #
        # SAMPLING THE VERGE WAS TRIED AND IT MEASURED THE SCENERY. A strip at a fixed
        # row read 69.0 over the drop against 68.7 over the solid side, and the FARMLAND
        # control - which has no drop at all - swung 19 levels between its own two sides.
        # So the drop is found the way the rail is: render it away, and diff.
        print()
        print('  AND THE GROUND STOPS AT THE RIM')

        def drop_of(k, side):
            settle(k, side)
            page.evaluate("() => { const R = window.__probe.road;"
                          " R.holdSpd(0); R.dropOff(true); }")
            page.wait_for_timeout(90)
            off = page.screenshot()
            page.evaluate("() => { const R = window.__probe.road;"
                          " R.holdSpd(0); R.dropOff(false); }")
            page.wait_for_timeout(90)
            on = page.screenshot()
            return rail_pixels(on, off)

        for k in ('MOUNTAIN', 'FARMLAND'):
            nL, xL = drop_of(k, -1)
            nR, xR = drop_of(k, 1)
            print('      %-9s hazard left: %5d px at x=%5.1f    hazard right: %5d px at x=%5.1f'
                  % (k, nL, xL, nR, xR))
            if WANT.get(k) is None:
                check(nL < BARE and nR < BARE, '%s has no drop to draw' % k,
                      '%d and %d pixels changed' % (nL, nR))
            else:
                check(nL > BARE and nR > BARE, '%s paints a drop beside the road' % k,
                      '%d and %d pixels' % (nL, nR))
                # AND ON THE SIDE THE HAZARD IS. Same differential as the rail: the drop's
                # mean position must move when the coin turns.
                check(xR - xL > 60, '%s puts the drop on the side the hazard is' % k,
                      'x=%.1f with the hazard left, x=%.1f with it right' % (xL, xR))
                # AND IT IS A FLOOR FAR BELOW, NOT DARK GROUND BESIDE THE ROAD (owner,
                # 2026-09-19): "Couldn't we actually just not do a plane equal to the road and
                # have an actual drop off?" The dark face of 2026-09-16 was a colour on a
                # surface at the road's own level, and every check above passed on it. What
                # separates a fall is SCALE: at the row where a rim is drawn, the floor seen
                # past it must be a slice much further away. A plane at road level answers
                # the rim's own slice; a missing floor answers nothing.
                settle(k, -1)
                page.evaluate("() => { const R = window.__probe.road; R.holdSpd(0); R.dropOff(false); }")
                page.wait_for_timeout(90)
                at = page.evaluate("() => window.__probe.road.dropFloorAt(40)")
                print('      %-9s at the rim of slice 40 (row %s) the floor seen is slice %s, of %s drawn'
                      % (k, at and at['rimY'], at and at['floorN'], at and at['floors']))
                check(bool(at) and at['floorN'] is not None and at['floorN'] >= 2 * at['rimN'],
                      '%s: past the rim lies a floor far below, not ground at the road level' % k,
                      repr(at))

        # ---- AND ALL OF IT IS BEHIND YOU TOO (RLG-280) -----------------------------
        # Owner, 2026-09-16: "all the new boundaries items you just added, are invisible
        # in the mirror." They were, and this check could not see it: the diff above
        # reads the lower half of the frame only, so it proved the windscreen and said
        # nothing about the glass. The mirror is a second road pass with its own walk and
        # its own scale - anything beside the road has to be drawn twice or it does not
        # exist behind you, which is why bridge-test asserts its ironwork in both views.
        print()
        print('  AND IT IS IN THE MIRROR')
        for k in ('MOUNTAIN', 'CITY', 'FARMLAND'):
            settle(k, 1)
            page.evaluate("() => { const R = window.__probe.road;"
                          " R.holdSpd(0); R.railsOff(true); R.dropOff(true); }")
            page.wait_for_timeout(110)
            off = page.screenshot()
            page.evaluate("() => { const R = window.__probe.road;"
                          " R.holdSpd(0); R.railsOff(false); R.dropOff(false); }")
            page.wait_for_timeout(110)
            on = page.screenshot()
            nRoad, _ = rail_pixels(on, off, 'road')
            nGlass, _ = rail_pixels(on, off, 'mirror')
            print('      %-9s windscreen %5d px   mirror %5d px' % (k, nRoad, nGlass))
            if WANT.get(k) is None:
                check(nGlass < 30, '%s draws nothing in the glass either' % k,
                      '%d pixels' % nGlass)
            else:
                check(nGlass > 30, '%s carries its boundary into the glass' % k,
                      '%d pixels in the mirror against %d on the road' % (nGlass, nRoad))

        errs = page.evaluate("() => window.__probe.errors")
        check(not errs, 'no page errors', '; '.join(errs[:2]))
        browser.close()
    httpd.shutdown()

    print()
    if fails:
        print('  %d check(s) FAILED' % len(fails))
        return 1
    print('  the table holds and the rail follows it')
    print('  it says nothing about whether the rail is drawn WELL - whether it reads as')
    print('  steel at speed, and whether it stands at the right height - which is the')
    print('  owner call on a device.')
    return 0


sys.exit(main())
