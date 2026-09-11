#!/usr/bin/env python3
"""EVENT TEST - a place with a stated length and an authored shape.

    .venv/Scripts/python tools/event-test.py

RLG-112. Owner, 2026-08-31: "The bridge would start with a vertical ramp up, be flat the
entire way and then ramp down at the end transitioning into the next biome."

NOTHING IN THIS ENGINE COULD SAY THAT. Every place lasts six and a half to twelve miles at
random and its terrain is a stream of rolled segments scaled by the place's own relief -
right for a forest, which is a tendency of the land, and wrong for anything somebody built.
RLG-112 says to build the mechanism ONCE, for the bridge and the tunnel together, rather
than scripting one road.

    A LENGTH THE PLACE STATES. A tunnel was six and a half to twelve miles of bore - two and
    a half to four and a half minutes underground against a run clock that starts at sixty
    seconds, so a bore could outlast the run it appeared in.

    AND A SHAPE THE PLACE STATES, WHICH IS A SEPARATE FIELD. A tunnel takes the length and
    NOT the shape: the owner has already ruled on a bore's form and capped both of its axes
    at 0.10. Two fields rather than one is the test of whether this is a mechanism or a
    special case wearing a table entry.

THE ONE THAT MATTERS IS THE LAST, AND IT IS EASY TO GET A FALSE GREEN ON. The rolled
segments are still generated inside an event and the integration overrules them, so
`roadRoughness` - which reads the segment list - stays exactly as it was and would be green
on a build where the profile does nothing at all. This reads the INTEGRATED cache instead,
which is the road the picture draws and the car drives on.

AND A FLAT DECK IS A CLAIM ABOUT THE SLOPE, NOT THE GRADE. The integration is `dy += grade;
y += dy`, so a stated grade of zero holds whatever slope the road arrived with - ask for a
flat bridge that way and you get a straight ramp continuing to the horizon. The profile
replaces the slope, and this checks the slope.

WHAT IT CANNOT DO. It cannot say whether the ramp FEELS like driving onto a bridge, whether
the rise is big enough to read at speed, or whether the crest at each end is comfortable.
`tools/biome-shot.py` takes the picture; the owner judges it.

Exit code 0 if every check passed, 1 otherwise.
"""

import argparse
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
MILE = 1 / 0.00000777

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

# How flat is flat. The integrated slope is in screen pixels per step, and an ordinary
# rolled hill runs to about 0.6 - so 0.01 is two orders of magnitude under the thing being
# excluded, and loose enough that the smoothstep joining the levels does not have to land
# exactly on a sample.
FLAT = 0.01


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def serve(root):
    handler = functools.partial(QuietHandler, directory=str(root))
    httpd = socketserver.TCPServer(('127.0.0.1', 0), handler)
    httpd.allow_reuse_address = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.socket.getsockname()[1]


class Results:
    def __init__(self):
        self.fails = []

    def check(self, ok, label, detail=''):
        print(('  ok    ' if ok else '  FAIL  ') + label + ('' if ok else '   [' + detail + ']'))
        if not ok:
            self.fails.append(label)



def drive_out(page, place, tries=80):
    """Drive a passage the TIMER placed, and sample its slope through the last third.

    It must be the timer: `startBiomeChange` and `setBiomePair` place at the horizon and
    cancel the plan, so neither reproduces a real run's ordering - and neither arms a place
    BEYOND the passage, which is the thing that used to clear the exit ramp.
    """
    page.evaluate("() => window.__probe.road.restart()")
    page.wait_for_timeout(300)
    for _ in range(40):
        st = page.evaluate("() => window.__probe.road.startLine()")
        if st['left'] <= 0 and st['go'] <= 0:
            break
        page.wait_for_timeout(90)
    page.evaluate("""() => { const R = window.__probe.road;
        R.setPhase(0.75); R.setWet(0); R.setSnow(0); R.setPool(0); }""")
    # ---- STAND THE RUN WHERE THE PLACE IS REACHABLE (RLG-142) -----------------------
    # The temperature step means a place may only be followed by one within ten degrees, and
    # forcing the countdown re-plans from the CURRENT instance every time - so rolling over
    # and over from wherever the run opened can never reach a passage that is out of range.
    # A TUNNEL sits at 0.35 to 0.55 and a BRIDGE at 0.30 to 0.80, so 0.45 reaches both.
    page.evaluate("() => window.__probe.road.setInstanceTemp(0.45)")
    got = False
    for _ in range(tries):
        page.evaluate("() => window.__probe.road.biomeCountdown(0)")
        page.evaluate("() => { const R = window.__probe.road;"
                      " R.clearTraffic(); R.setSpd(R.MAX_SPD); }")
        page.wait_for_timeout(40)
        if page.evaluate("() => window.__probe.road.roadPlan()")['key'] == place:
            got = True
            break
    if not got:
        return None
    ev = None
    for _ in range(1400):
        page.evaluate("() => { const R = window.__probe.road;"
                      " R.clearTraffic(); R.setSpd(R.MAX_SPD); }")
        page.wait_for_timeout(40)
        e = page.evaluate("() => window.__probe.road.eventNow()")
        if e['on'] and e['len'] > 0:
            ev = e
            break
    if not ev:
        return None
    z0, ln = ev['z0'], ev['len']
    late, want = [], [0.70, 0.78, 0.86, 0.92, 0.97, 1.00]
    for _ in range(5000):
        page.evaluate("() => { const R = window.__probe.road;"
                      " R.clearTraffic(); R.setSpd(R.MAX_SPD); }")
        page.wait_for_timeout(40)
        t = (page.evaluate("() => window.__probe.road.pos") - z0) / ln
        while want and t >= want[0]:
            want.pop(0)
            late.append(page.evaluate("() => window.__probe.road.roadSlopeAt()"))
        if not want:
            break
    return {'z0': z0, 'len': ln, 'late': late} if len(late) >= 4 else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--headed', action='store_true')
    args = ap.parse_args()
    console_utf8()
    res = Results()
    httpd, port = serve(ROOT)
    print('event-test  .  a stated length and an authored shape')
    with sync_playwright() as p:
        browser = launch_chromium(p, headless=not args.headed)
        page = browser.new_page(viewport={'width': 480, 'height': 900})
        page.add_init_script(INIT)
        boot(page, 'http://127.0.0.1:%d/%s' % (port, GAME))
        try:
            until(page, '() => navigator.serviceWorker && navigator.serviceWorker.controller',
                timeout=5000)
            page.wait_for_timeout(1000)
        except Exception:
            pass
        until(page, '!!window.__probe.road', timeout=10000)
        page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
        page.click('[data-act="play"]')
        page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
        page.click('[data-act="drive"]')
        page.wait_for_timeout(1600)

        keys = page.evaluate("() => window.__probe.road.BIOME_KEYS()")
        spans = page.evaluate("""() => {
          const R = window.__probe.road, out = {};
          for(const k of R.BIOME_KEYS()) out[k] = R.placeSpan(k);
          return out;
        }""")

        # ------------------------------------------------ a length the place states
        print()
        print('  A LENGTH THE PLACE STATES, IN MILES')
        print('      %-10s %8s %8s %8s' % ('place', 'stated', 'armed', 'profile'))
        for k in keys:
            v = spans[k]
            print('      %-10s %8s %8.2f %8s'
                  % (k, '-' if v['stated'] is None else v['stated'], v['armed'],
                     'yes' if v['profile'] else '-'))

        events = [k for k in keys if spans[k]['stated'] is not None]
        ordinary = [k for k in keys if spans[k]['stated'] is None]
        res.check(sorted(events) == ['BRIDGE', 'TUNNEL'],
                  'the tunnel and the bridge are the two places that state a length',
                  'these state one: %s' % sorted(events))
        for k in events:
            res.check(abs(spans[k]['armed'] - spans[k]['stated']) < 0.001,
                      'and %s arms exactly what it states' % k,
                      'states %s, arms %s' % (spans[k]['stated'], spans[k]['armed']))
        res.check(all(6.4 < spans[k]['armed'] < 12.1 for k in ordinary),
                  'and every ordinary place still arms the roll it always did',
                  str({k: spans[k]['armed'] for k in ordinary}))

        # ------------------------------------------------ and the shape is a second field
        print()
        print('  AND THE SHAPE IS A SECOND FIELD, WHICH IS THE TEST OF A MECHANISM')
        # THE TUNNEL HAS A SHAPE NOW, AND THAT IS A RULING RATHER THAN A DRIFT. This
        # check used to assert the opposite - that a tunnel states a length and NO shape -
        # and it was right to, because RLG-112 deliberately withheld one: the owner had
        # already capped a bore's form at 0.10 on both axes, and a single combined field
        # would have overruled that ruling to get a bridge. The owner has since stated the
        # tunnel's shape directly (RLG-143), so the caution was right to WAIT for it rather
        # than guess it, and the check moves with the ruling rather than being deleted.
        res.check(spans['TUNNEL']['profile'] is True and spans['BRIDGE']['profile'] is True,
                  'both events state a shape as well as a length',
                  'tunnel %r, bridge %r'
                  % (spans['TUNNEL']['profile'], spans['BRIDGE']['profile']))
        # AND THE TWO FIELDS ARE STILL SEPARATE, which was the point of the original
        # check. Every ordinary place states neither; nothing acquired a shape by having
        # a length, or the other way round.
        res.check(not any(spans[k]['profile'] for k in ordinary),
                  'and no ordinary place picked one up along the way',
                  str([k for k in ordinary if spans[k]['profile']]))
        # ------------------------------------------------ one shape with a sign
        print()
        print('  ONE SHAPE WITH A SIGN: A BRIDGE RISES, A TUNNEL DROPS')
        # Owner, 2026-09-01: a bridge "starts by going up high above the water and then
        # levels out ... then at the end the roadway goes down to meet the next biome",
        # and "the tunnel does the opposite".
        br = page.evaluate("() => window.__probe.road.riseProfile('BRIDGE', 40)")
        tu = page.evaluate("() => window.__probe.road.riseProfile('TUNNEL', 40)")
        print('      bridge height across the crossing: %s'
              % ' '.join('%+.0f' % v for v in br[::5]))
        print('      tunnel height across the bore:     %s'
              % ' '.join('%+.0f' % v for v in tu[::5]))
        res.check(max(br) > 10 and min(br) > -0.5,
                  'the bridge only ever rises',
                  'it ran from %+.1f to %+.1f' % (min(br), max(br)))
        res.check(min(tu) < -10 and max(tu) < 0.5,
                  'and the tunnel only ever drops, which is the same shape negated',
                  'it ran from %+.1f to %+.1f' % (min(tu), max(tu)))
        # AND THE MOUTHS MEET, which RLG-143 names as where this fails. Zero SLOPE at
        # each end is not zero HEIGHT, and it is the height that has to match the place
        # either side - or a bridge hands over to a desert from thirty feet up.
        for nm, prof in (('bridge', br), ('tunnel', tu)):
            res.check(abs(prof[0]) < 0.5 and abs(prof[-1]) < 0.5,
                      'the %s meets the ground at both mouths' % nm,
                      'it ends at %+.2f and %+.2f' % (prof[0], prof[-1]))

        # ------------------------------------------------ the shape itself
        print()
        print('  RAMP UP, FLAT THE ENTIRE WAY, RAMP DOWN')
        prof = page.evaluate("() => window.__probe.road.profileOf('BRIDGE', 40)")
        res.check(prof is not None, 'the bridge has an authored shape to read')
        if prof:
            n = len(prof) - 1
            up = prof[:n // 5]
            mid = prof[2 * n // 5:3 * n // 5 + 1]
            down = prof[-n // 5:]
            print('      the crossing, in 41 samples of stated slope:')
            print('      %s' % ' '.join('%+.2f' % v for v in prof[::4]))
            res.check(max(up) > 0.1,
                      'it climbs on the way on',
                      'the steepest the first fifth got was %+.3f' % max(up))
            res.check(all(abs(v) < FLAT for v in mid),
                      'the middle is dead flat, which is what the owner asked for',
                      'the worst of the middle was %+.5f' % max(mid, key=abs))
            res.check(min(down) < -0.1,
                      'and it falls on the way off',
                      'the steepest the last fifth got was %+.3f' % min(down))
            # AND IT ENDS WHERE IT STARTED. A ramp that rises and never comes down is a
            # road that walks off the top of the frame, and the next place inherits it.
            res.check(abs(prof[0]) < FLAT and abs(prof[-1]) < FLAT,
                      'and it is level at both ends, so the next place inherits nothing',
                      'ends at %+.4f and %+.4f' % (prof[0], prof[-1]))

        # ------------------------------------------------ the road the car drives on
        print()
        print('  AND THE ROAD ITSELF, NOT THE TABLE THAT DESCRIBES IT')
        # THIS IS THE ONE THAT CAN GO FALSELY GREEN. The rolled segments are still
        # generated inside an event, so anything reading the segment list is unchanged.
        # `roadSlopeAt` reads the INTEGRATED cache - the road the picture draws.
        page.evaluate("() => window.__probe.road.setBiomePair('BRIDGE','BRIDGE')")
        page.wait_for_timeout(500)
        ev = page.evaluate("() => window.__probe.road.eventNow()")
        print('      the event: on=%s, %s of the way across' % (ev['on'], ev['through']))
        res.check(ev['on'],
                  'pinning the pair to a bridge arms the authored profile',
                  str(ev))
        # a quarter of a mile of deck ahead of the car
        bridge = page.evaluate(
            "() => { const R = window.__probe.road, e = R.eventNow();"
            "  return R.roadSlopes(e.z0 + e.len*0.30, e.z0 + e.len*0.60, 24); }")
        print('      the deck, sampled across the middle third:')
        print('      %s' % ' '.join('%+.3f' % v for v in bridge[::3]))
        res.check(all(abs(v) < FLAT for v in bridge),
                  'the road the car drives on is flat across the deck',
                  'the worst sample was %+.5f' % max(bridge, key=abs))

        # AND THE CONTROL. An ordinary place is rolled terrain, so the same measurement
        # over the same length of road must NOT come back flat - otherwise this check
        # would pass on a build with no profile mechanism at all.
        page.evaluate("() => window.__probe.road.setBiomePair('MOUNTAIN','MOUNTAIN')")
        page.wait_for_timeout(500)
        mtn = page.evaluate("() => { const R = window.__probe.road, out = [];"
                            " for(let i = 0; i <= 24; i++) out.push(R.roadSlopeAt(i * 8000));"
                            " return out; }")
        print('      a mountain over the same length of road:')
        print('      %s' % ' '.join('%+.3f' % v for v in mtn[::3]))
        res.check(any(abs(v) > FLAT for v in mtn),
                  'and a rolled place over the same road is not flat, so this measures something',
                  'the mountain was flat everywhere too: %s' % mtn)
        res.check(not page.evaluate("() => window.__probe.road.eventNow().on"),
                  'and an ordinary place arms no profile at all')

        # ------------------------------------------------ driven, not pinned
        print()
        print('  AND THE RAMP IS STILL THERE WHEN YOU DRIVE OUT OF ONE')
        # THIS IS THE CHECK EVERYTHING ABOVE COULD NOT MAKE. `setBiomePair` arms the event
        # itself, so every claim above is about a profile that was installed by the harness
        # and never disturbed. In a real run the NEXT place arms its own event, and a place
        # boundary lands exactly where the current event ends - but the boundary is PLACED
        # at the horizon, a draw distance before the car gets there. So `armEvent` fired
        # with the car still 30,000 units short of the end of the bore, an ordinary place
        # has no profile, and it cleared the one still in force.
        #
        # MEASURED THAT WAY: the road's slope 86 per cent through a real tunnel read -0.09
        # where the profile asks for +0.34. The climb out was simply gone, and every check
        # above stayed green because none of them drove.
        for place, want in (('TUNNEL', +1), ('BRIDGE', -1)):
            r = drive_out(page, place)
            if r is None:
                res.check(False, 'a %s was reached and driven out of' % place,
                          'the timer never planned one in the tries allowed')
                continue
            print('      %s, slope through the last third: %s'
                  % (place, ' '.join('%+.2f' % v for v in r['late'])))
            best = max(r['late']) if want > 0 else min(r['late'])
            res.check(best * want > 0.12,
                      'a %s still %s on its way out, after a real place was placed beyond it'
                      % (place, 'climbs' if want > 0 else 'falls'),
                      'the most it managed was %+.3f' % best)
            res.check(abs(r['late'][-1]) < 0.12,
                      'and it is level again by the far mouth, so the next place inherits '
                      'no slope',
                      'it left the %s at %+.3f' % (place, r['late'][-1]))

        errs = page.evaluate("() => window.__probe.errors")
        res.check(not errs, 'no page errors', '; '.join(errs[:3]))
        browser.close()
    httpd.shutdown()

    print()
    if res.fails:
        print('FAILED: ' + '; '.join(res.fails))
        return 1
    print('all checks passed')
    print('  what the ramp FEELS like is not measured here - see tools/biome-shot.py')
    return 0


sys.exit(main())
