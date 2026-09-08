#!/usr/bin/env python3
"""
HEAT TEST - the wanted level is earned and it cools; it is not a clock.

    .venv/Scripts/python tools/heat-test.py

RLG-030. Owner, 2026-08-30: "I don't think time should increase it at all. It should purely be from
speed traps and taking out cops. I think if you outrun a cop for long enough, your heat would
probably go down so long as you don't pass another speed trap over the speed limit." And: "Super
cruisers should not be dispatched unless you are heat three and above and have gone 170 miles an
hour past a speed trap."

Heat used to rise by one every twenty seconds whatever you did and never fall, so it reached five
inside eighty seconds of any run - a timer wearing a wanted level's costume, and about to become
five stars on the screen.

WHAT IT CANNOT CHECK, stated so nobody reads a green run as more than it is: tripping a real speed
trap and wrecking a real cruiser are not staged here. Both raise heat by one line each, and both
were read rather than driven. What is driven is the part the owner's ruling turns on - that time
does nothing, that clear air cools, and that a super cruiser needs two different things.

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
from harness import console_utf8, launch_chromium

GAME = 'games/sw/interstate.html'

INIT = r"""
window.__probe = { errors: [], road: null };
(function(){
  var real = null, wrapped = null;
  Object.defineProperty(window, 'ROAD', { configurable: true,
    get: function(){ return real ? wrapped : undefined; },
    set: function(fn){ real = fn; wrapped = function(CFG){ var a = real(CFG);
      window.__probe.road = a || (CFG && CFG.api) || null; return a; }; } });
})();
window.addEventListener('error', function(e){ window.__probe.errors.push(String(e.message)); });
"""


class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--headed', action='store_true')
    args = ap.parse_args()
    console_utf8()
    fails = []

    def ok(c, label, detail=''):
        print(('  ok    ' if c else '  FAIL  ') + label + ('' if c else '   [' + str(detail) + ']'))
        if not c:
            fails.append(label)

    httpd = socketserver.TCPServer(('127.0.0.1', 0), functools.partial(Q, directory=str(ROOT)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.socket.getsockname()[1]
    print('heat-test  .  the wanted level is earned, not counted')
    with sync_playwright() as p:
        b = launch_chromium(p, headless=not args.headed)
        pg = b.new_context(viewport={'width': 480, 'height': 900},
                           has_touch=True, is_mobile=True).new_page()
        pg.add_init_script(INIT)
        pg.goto('http://127.0.0.1:%d/%s' % (port, GAME), wait_until='load')
        pg.wait_for_function('!!window.__probe.road', timeout=10000)
        pg.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
        pg.click('[data-act="play"]')
        pg.wait_for_timeout(400)
        # HOT PURSUIT on, or the whole system stands down and every number is zero
        pg.click('[data-act="chase"]')
        pg.wait_for_timeout(200)
        pg.click('[data-act="drive"]')
        pg.wait_for_timeout(1500)
        # AND THE RUN HAS TO OUTLIVE THE CHECKS. This car is parked for most of the
        # harness, so it reaches no checkpoint and buys no seconds; when the sixty the
        # run starts with are gone the update stops, and the cooling clock and the point
        # total freeze exactly where they stood. That reads as a tunable that stopped
        # working - a whole star of cooling went missing that way, with the harness
        # blaming the engine. `setTimed(false)` is the affordance for it (RLG-125), and
        # the clock is nothing this check is asking about.
        pg.evaluate('() => window.__probe.road.setTimed(false)')
        st = pg.evaluate('() => window.__probe.road.pursuit()')
        ok(not st['easy'], 'the pursuit system is running', str(st))

        # STOPPED, AND THE ROAD CLEARED FOR EVERY MEASUREMENT. The first version drove
        # while it watched, and heat went UP: the car wrecked a parked cruiser on the way
        # past, which is one of the two things that now EARNS heat. A check for what time
        # does has to be a check for what time does, so nothing is moving and there is
        # nothing to hit.
        def hold(ms, spd=0.0, clear=True, heat=None):
            for _ in range(max(1, ms // 250)):
                pg.evaluate('([v, c, h]) => { const R = window.__probe.road;'
                            ' R.setSpd(R.MAX_SPD*v); R.parkTraffic(9, 60000);'
                            ' if(c) R.copsClear(); if(h) R.heat(h); }', [spd, clear, heat])
                pg.wait_for_timeout(250)

        # ---- IT IS NOT A CLOCK ------------------------------------------------------
        pg.evaluate('() => window.__probe.road.heat(2)')
        start = pg.evaluate('() => window.__probe.road.pursuit()')['heat']
        hold(11000)
        mid = pg.evaluate('() => window.__probe.road.pursuit()')
        print('      heat %d -> %d over 11s stopped on an empty road (cooling at %.1f of %s)'
              % (start, mid['heat'], mid['cool'], mid['coolNeeds']))
        ok(mid['heat'] <= start, 'time alone never raises the wanted level',
           'went from %d to %d' % (start, mid['heat']))

        # ---- AND IT COOLS WHEN NOBODY IS ON YOU -------------------------------------
        # THE WAIT IS ASKED FOR, NOT ASSUMED. `coolNeeds` is HEAT_COOL - the seconds a
        # star takes to bleed away - and it is a tunable the owner moves. This waited a
        # flat fourteen seconds, which was two clear of the twelve it was written
        # against; the retune to thirty turned that into a red check reporting a working
        # engine. A budget keyed to a tunable has to read the tunable.
        pg.evaluate('() => window.__probe.road.heat(4)')
        needs = pg.evaluate('() => window.__probe.road.pursuit()')['coolNeeds']
        # half a star's worth is enough to cross a boundary: heat(4) lands mid-band, so
        # the level steps down after HALF a star of cooling, plus the grace and slack.
        wait1 = int((needs * 0.5 + 6) * 1000)
        hold(wait1)
        cool = pg.evaluate('() => window.__probe.road.pursuit()')
        print('      heat 4 -> %d after %ds clear of every cruiser (a star is %ds)'
              % (cool['heat'], wait1 // 1000, needs))
        ok(cool['heat'] < 4, 'outrunning them cools the wanted level',
           'still %d after %ds with %d chasing'
           % (cool['heat'], wait1 // 1000, cool['chasing']))

        # ---- AND A CRUISER YOU HAVE LEFT BEHIND IS NOT CHASING YOU ------------------
        # Owner, 2026-09-07: the main way to lose the police and the wanted level is
        # "outrunning them and leaving them behind".
        #
        # IT COULD NOT HAPPEN BEFORE THIS. A cruiser counted as chasing until it was
        # CULLED, 34,000 units back, so a car you had comprehensively lost held the
        # cooling clock at zero the whole way. Measured: thirty seconds of running, half
        # of it flat out in a car forty miles an hour faster than anything behind it, and
        # the wanted level never came down by one level.
        #
        # A cruiser is parked WELL BEHIND, alive and still pointed at the player, and the
        # clock has to run anyway. Without the distance rule this reads zero.
        pg.evaluate('() => window.__probe.road.heat(4)')
        pg.evaluate('() => { const R = window.__probe.road; R.copsClear();'
                    ' R.cops().push({ z: R.pos - 20000, x: 0, spd: 0, wreck:0, ang:0,'
                    '   grace:0, cool:0, side:1, w:0.27, len:400, phase:0, dmg:0,'
                    '   from:"test", onPlayer:true }); }')
        for _ in range(56):
            pg.evaluate('() => { const R = window.__probe.road; R.setSpd(0); R.heat(4);'
                        ' const k = R.cops()[0]; if(k) k.z = R.pos - 20000; }')
            pg.wait_for_timeout(250)
        far = pg.evaluate('() => window.__probe.road.pursuit()')
        print('      a cruiser held 20,000 behind: the cool clock reached %.1f of the %d needed'
              % (far['cool'], far['coolNeeds']))
        ok(far['cool'] > 2 or far['heat'] < 4,
           'a cruiser you have left behind stops holding the wanted level up',
           'the clock read %.2f with one still on the road' % far['cool'])

        # ---- AND IT FALLS ALL THE WAY TO NOTHING ------------------------------------
        # THIS ASSERTED THE OPPOSITE UNTIL 2026-09-07 and it was right to, for the model
        # it was written against: `heat` was an integer that floored at ONE, so there was
        # no such thing as being clean and "it stops at one" was the rule.
        #
        # The owner replaced that model: "cooling off removes these points, so your wanted
        # level can go down to empty as well." The check is inverted because the RULE was
        # inverted, which is the one reason a green assertion may be turned round - and it
        # is written down here rather than quietly edited, because "the check went red and
        # the fix was to change the check" is the shape that hides a real regression.
        #
        # AND THIS BUDGET IS ASKED FOR TOO. heat(1) lands one and a half stars' worth on
        # the clock, so reaching nothing takes one and a half times HEAT_COOL plus the
        # grace. The flat thirty seconds here was sized against a twelve-second star and
        # left 84 points on the board at thirty.
        pg.evaluate('() => window.__probe.road.heat(1)')
        hold(int((needs * 1.5 + 8) * 1000))
        floor = pg.evaluate('() => window.__probe.road.pursuit()')
        ok(floor['heat'] == 0 and floor['pts'] == 0,
           'and it falls all the way to empty, which it could not before',
           '%d stars, %d points' % (floor['heat'], floor['pts']))

        # ---- A SUPER CRUISER IS EARNED TWICE OVER -----------------------------------
        # Heat five at full speed is not enough on its own: the 170 past a trap is an
        # EVENT, and without it no super is dispatched however fast you go.
        # AT 160, NOT 200. Above the 150 the super gate wants, and below the 170 that
        # EARNS one - because a trap caught at full speed sets the flag again and the
        # check would be measuring the game undoing its own setup.
        pg.evaluate("() => { const R = window.__probe.road; R.copsClear();"
                    " R.heat(5); R.earnSupers(false); }")
        # SIXTEEN SECONDS, NOT NINE. An interceptor needs four unbroken seconds above
        # 150mph before the first one is sent, and `spawnSuper` then puts the counter
        # back to 2.2 so they arrive staggered rather than four at once - so nine
        # seconds catches the first one only if the run starts fast, and this check read
        # 0 supers on one run and 4 on the next for that reason alone. Measured with a
        # probe holding 0.82: the first arrives at about eight seconds.
        hold(16000, 0.80, clear=False)
        no_ev = pg.evaluate('() => window.__probe.road.pursuit()')
        print('      heat 5 at 160mph, no trap earned: %d supers' % no_ev['supers'])
        ok(no_ev['supers'] == 0, 'no super cruiser without the 170 past a trap', str(no_ev))

        pg.evaluate("() => { const R = window.__probe.road; R.copsClear();"
                    " R.heat(5); R.earnSupers(true); }")
        hold(16000, 0.80, clear=False)
        yes_ev = pg.evaluate('() => window.__probe.road.pursuit()')
        print('      with the trap earned: %d supers' % yes_ev['supers'])
        ok(yes_ev['supers'] > 0, 'and one is dispatched once it has been', str(yes_ev))

        # ---- AND THE HEAT-THREE HALF CANNOT BE ISOLATED HERE ---------------------
        # It is printed rather than asserted, on the same reasoning as the cull count in
        # RLG-073: the speed a super cruiser needs is above the limit a trap watches, so
        # driving fast enough to trigger one EARNS heat while the check watches. Holding
        # the number down between frames is a race the harness loses - it lost it three
        # times, at 200mph and at 160. The gate is one line, `heat >= 3 && supersEarned`,
        # and an assertion that has to fight the game to stay true is not evidence.
        pg.evaluate("() => { const R = window.__probe.road; R.copsClear();"
                    " R.heat(2); R.earnSupers(true); }")
        hold(6000, 0.80, clear=False, heat=2)
        low = pg.evaluate('() => window.__probe.road.pursuit()')
        print('      heat held at 2 with the trap earned: %d supers, heat now %d'
              '  (printed, not asserted - see the note above)'
              % (low['supers'], low['heat']))

        errs = pg.evaluate('() => window.__probe.errors')
        ok(not errs, 'no page errors', str(errs))
        b.close()
    httpd.shutdown()
    print(('\n%d check(s) failed' % len(fails)) if fails else '\nall checks passed')
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
