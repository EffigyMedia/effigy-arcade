#!/usr/bin/env python3
"""
MIND TEST - the car is capable, the driver decides.

    .venv/Scripts/python tools/mind-test.py
    .venv/Scripts/python tools/mind-test.py --headed

RLG-054. Owner, 2026-08-28: every NPC gets a driving personality in three categories - Racer, Speeder
and Civilian. It is one system for rivals and traffic alike, and it is the project's spine applied to
behaviour: RLG-042 gave traffic real stats and made their drivers the limitation, RLG-052 wired every
indicator and left nothing asking them to come on, and this is the same shape a third time.

THE ASSERTION THE RULING ACTUALLY TURNS ON IS THE ONE ABOUT CAPABILITY. "A personality is a set of
DECISIONS. It must not adjust the car's capability." A personality that quietly made a car faster
would reintroduce the exact fault RLG-042's measurement found, under a friendlier name - so the
load-bearing check here is that no driver, of any mind, ever exceeds what their vehicle can do. A
Speeder in a lorry is a speeder in INTENT and drives a lorry.

AND THE MIX IS SAMPLED FROM THE ENGINE'S OWN ROLL, not computed here. Rarity is the specification -
the owner said "very very rare" twice about the supercars and "rarely" about a traffic Racer - and a
rate of one in fifty cannot be measured against the thirty-odd cars the road holds at once. The engine
rolls thousands on request; a check that carried its own copy of the odds would agree with itself
after somebody changed them.

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

SAMPLE = 4000
# RLG-045's split, with a sports car raising the odds. Wide bands: the point is the ORDERING and the
# order of magnitude, not a rate to three places - a check that pinned the exact odds would have to be
# edited by anyone who tuned them, which is how a guard stops meaning anything.
COMMUTER_MIN, COMMUTER_MAX = 0.60, 0.94
RACER_MAX = 0.09          # "rarely", and "very very rare" for the supercars to come
# a sports body must raise the Speeder odds by at least this much, or RLG-045's rule is not in effect
SPORTY_LIFT = 2.0
ORDINARY = ('sedan', 'van', 'truck', 'taxi', 'pickup')
SPORTY = ('coupe', 'tuner', 'muscle')
# the supercars the owner allowed into traffic, and the FORMULA is deliberately not among them
SUPERS = ('stallion', 'matador', 'crest')
# "very very rare", said twice. The old rogue was 2.8% of traffic and this is a different order of
# magnitude, so the ceiling is set an order below it rather than beside it.
SUPER_MAX = 0.012


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
        print(('  ok    ' if ok else '  FAIL  ') + label + ('' if ok else '   [' + str(detail) + ']'))
        if not ok:
            self.fails.append(label)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--headed', action='store_true')
    args = ap.parse_args()
    console_utf8()
    res = Results()
    httpd, port = serve(ROOT)
    print('mind-test  .  the car is capable, the driver decides')
    with sync_playwright() as p:
        browser = launch_chromium(p, headless=not args.headed)
        page = browser.new_page(viewport={'width': 480, 'height': 900})
        page.add_init_script(INIT)
        boot(page, 'http://127.0.0.1:%d/%s' % (port, GAME))
        try:
            until(page, '() => navigator.serviceWorker && navigator.serviceWorker.controller', timeout=5000)
            page.wait_for_timeout(1000)
        except Exception:
            pass
        until(page, '!!window.__probe.road', timeout=10000)
        page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
        page.click('[data-act="play"]')
        page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
        page.click('[data-act="drive"]')
        page.wait_for_timeout(2500)

        limit = page.evaluate("() => window.__probe.road.speedLimit()")
        print('  the limit is %.0f mph of a 200 mph scale' % (limit * 200))
        print()

        # ---- WHO DRIVES WHAT ----------------------------------------------------------------
        print('  the mix, sampled from the engine\'s own roll, %d per type' % SAMPLE)
        mix = {}
        for t in ORDINARY + SPORTY:
            m = page.evaluate('([t, n]) => window.__probe.road.sampleMinds(t, n)', [t, SAMPLE])
            tot = m['commuter'] + m['speeder'] + m['outlaw']
            mix[t] = {'com': m['commuter'] / tot, 'spd': m['speeder'] / tot,
                      'rac': m['outlaw'] / tot, 'cruise': m['cruise'],
                      'vmax': page.evaluate('(t) => window.__probe.road.typeVmax(t)', t)}
            print('      %-7s commuter %4.0f%%   speeder %4.0f%%   outlaw %4.1f%%   can do %3.0f mph'
                  % (t, mix[t]['com'] * 100, mix[t]['spd'] * 100, mix[t]['rac'] * 100,
                     mix[t]['vmax'] * 200))

        worst_com = min(mix[t]['com'] for t in ORDINARY)
        best_com = max(mix[t]['com'] for t in ORDINARY)
        res.check(COMMUTER_MIN <= worst_com and best_com <= COMMUTER_MAX,
                  'most ordinary drivers keep the limit',
                  'commuters run %.0f%% to %.0f%% across ordinary bodies'
                  % (worst_com * 100, best_com * 100))

        worst_rac = max(mix[t]['rac'] for t in ORDINARY + SPORTY)
        res.check(worst_rac <= RACER_MAX,
                  'and a Racer in traffic is rare',
                  'the commonest is %.1f%%, over the %.0f%% this calls rare'
                  % (worst_rac * 100, RACER_MAX * 100))
        res.check(all(mix[t]['rac'] > 0 for t in SPORTY),
                  'but Racers do exist, which rare is not the same as never',
                  'none appeared in %d samples of a sports body' % SAMPLE)

        ord_spd = sum(mix[t]['spd'] for t in ORDINARY) / len(ORDINARY)
        spo_spd = sum(mix[t]['spd'] for t in SPORTY) / len(SPORTY)
        res.check(spo_spd >= ord_spd * SPORTY_LIFT,
                  'and a sports car raises the odds of a Speeder behind the wheel',
                  'sporty %.0f%% against ordinary %.0f%%, wanted at least %.1fx'
                  % (spo_spd * 100, ord_spd * 100, SPORTY_LIFT))
        print('        sporty bodies %.0f%% speeders against %.0f%% for ordinary ones'
              % (spo_spd * 100, ord_spd * 100))
        print()

        # ---- AND NO PERSONALITY MAKES A CAR FASTER THAN IT IS --------------------------------
        # The load-bearing assertion. RLG-042 found a fleet whose stat table said one thing while
        # three comments around it said another; a personality that lifted a car's ceiling would be
        # that fault again with a friendlier name.
        print('  and what the car can actually do')
        over = []
        for t in ORDINARY + SPORTY:
            vmax = mix[t]['vmax']
            worst = max(mix[t]['cruise'])
            if worst > vmax + 1e-6:
                over.append('%s wanted %.3f of a ceiling of %.3f' % (t, worst, vmax))
        res.check(not over,
                  'no driver of any mind exceeds what their vehicle can do',
                  '; '.join(over))

        # A Speeder in a lorry is the case that proves it is a decision rather than a stat: the
        # driver wants to break the limit and the truck cannot.
        truck_top = max(mix['truck']['cruise'])
        res.check(truck_top <= limit,
                  'so a speeding lorry driver still drives a lorry',
                  'the fastest a truck ever wants is %.0f mph, over the %.0f mph limit'
                  % (truck_top * 200, limit * 200))
        print('        a truck tops out at %.0f mph whoever is driving; a tuner reaches %.0f'
              % (truck_top * 200, max(mix['tuner']['cruise']) * 200))
        print()

        # ---- ON THE ROAD, NOT ONLY IN THE ROLL ----------------------------------------------
        # The sampler proves the picker. This proves the picker is actually WIRED - a system that
        # rolled beautifully and assigned nothing would pass everything above.
        print('  and on the road itself')
        # SAMPLED OVER TIME, NOT ONCE. The road holds about thirty cars, so one in ten being a
        # Speeder means a single snapshot has a real chance of containing none - the first version
        # of this check read 14 cars, all commuter, and would have passed on an engine that
        # assigned every driver the same mind. Traffic turns over as you drive, so the run watches
        # and keeps the most it ever saw of each.
        page.keyboard.down('ArrowUp')
        best = {'seen': 0, 'commuter': 0, 'speeder': 0, 'outlaw': 0, 'overLimit': 0}
        mismatched = 0
        for _ in range(24):
            page.wait_for_timeout(900)
            m = page.evaluate("() => window.__probe.road.minds()")
            if m['commuter'] + m['speeder'] + m['outlaw'] != m['seen']:
                mismatched += 1
            for k in best:
                if m[k] > best[k]:
                    best[k] = m[k]
        page.keyboard.up('ArrowUp')
        print('      at their most, over 24 looks: %d cars, %d commuter, %d speeder, %d outlaw, '
              '%d actually over the limit'
              % (best['seen'], best['commuter'], best['speeder'], best['outlaw'],
                 best['overLimit']))
        res.check(best['seen'] > 10, 'there was traffic to look at', '%d cars' % best['seen'])
        res.check(mismatched == 0,
                  'every car on the road has a driver with a mind',
                  'the parts failed to sum to the whole on %d of 24 looks' % mismatched)
        res.check(best['commuter'] > 0,
                  'and most of them are ordinary drivers',
                  'not one commuter in the whole run')
        # THE WIRING, WHICH THE SAMPLER ABOVE CANNOT PROVE. A picker that rolled a perfect mix and
        # assigned nothing would satisfy every check before this one.
        res.check(best['speeder'] > 0,
                  'and the ones who speed actually reach the road',
                  'not one Speeder appeared in 24 looks at the traffic')
        res.check(best['overLimit'] > 0,
                  'and at least one of them is genuinely over the limit',
                  'nothing on the road ever exceeded %.0f mph' % (limit * 200))
        print()

        # ---- THE SUPERCARS IN TRAFFIC (RLG-054) ---------------------------------------------
        # Owner, 2026-08-29: the supercars, not the formula, as very very rare traffic in their
        # muted colours, inheriting the raised Speeder chance. Owner, 2026-08-31: no personality
        # shows on a car other than through its behaviour, and a traffic Racer wears traffic paint.
        print('  the supercars in traffic')
        types = page.evaluate('(n) => window.__probe.road.sampleTypes(n)', 40000)
        tot = sum(types.values())
        supers = sum(types.get(k, 0) for k in SUPERS)
        print('      %d of %d spawns, about one car in %d'
              % (supers, tot, round(tot / supers) if supers else 0))
        res.check(0 < supers / tot <= SUPER_MAX,
                  'a supercar in traffic is very very rare, and does happen',
                  '%.3f%% of spawns, wanted above nothing and under %.1f%%'
                  % (supers / tot * 100, SUPER_MAX * 100))
        res.check('formula' not in types and not any(
                      k in types for k in ('vector', 'apex', 'comet')),
                  'and the formula car is not one of them',
                  'a formula body reached the traffic pool')

        # THE PAINT IS THE ONLY THING THAT SAYS IT IS NOT A RIVAL, so it is the thing to measure.
        # Not "was it handed the right palette" - what the sprite actually came out as.
        for body in SUPERS:
            traf = page.evaluate('([w,k,i]) => window.__probe.road.spriteInk(w,k,i)',
                                 ['traffic', body, 3])
            rival = page.evaluate('([w,k,i]) => window.__probe.road.spriteInk(w,k,i)',
                                  ['rival', body.upper() + '|CYAN', 0])
            if not traf or not rival:
                res.check(False, 'the %s exists in both traffic and rival paint' % body,
                          'traffic %s, rival %s' % (bool(traf), bool(rival)))
                continue
            print('      %-9s traffic saturation %.3f   against the same body as a rival %.3f'
                  % (body, traf['sat'], rival['sat']))
            res.check(traf['sat'] < rival['sat'],
                      'a %s in traffic is muted against the same car as a rival' % body,
                      'traffic %.3f is not below rival %.3f' % (traf['sat'], rival['sat']))
        print()

        # ---- AND THE OTHER END OF THE CLASS SIGNAL (RLG-117) --------------------------------
        # Owner, 2026-08-31: "Actual racers should have a chance to use stripes - not the racer's
        # personality, but race opponents." A striped car is unambiguously an opponent, which is
        # what makes the muted supercar above unambiguously not one. The two are one signal read
        # from both ends, so they are checked in one file.
        print('  stripes on the grid')
        chance = page.evaluate("() => window.__probe.road.stripeChance()")
        print('      the chance is %.0f%%' % (chance * 100))

        # SAMPLED OVER MANY GRIDS, because one grid of a handful of cars says nothing about a
        # chance. `restart` runs the same path a real race start takes.
        # AND IT HAS TO BE A RACE. Racers exist only in race mode - the first version of this
        # section ran in DRIVE, formed no grid at all, and reported "0 of 0" as a failure of the
        # feature rather than of the harness.
        page.evaluate("() => window.__probe.road.setMode('race')")
        grids, striped, seen, bad = 0, 0, 0, []
        bodies = {}
        for _ in range(30):
            page.evaluate("() => window.__probe.road.restart()")
            page.wait_for_timeout(60)
            g = page.evaluate("() => window.__probe.road.gridStripes()")
            if not g['seen']:
                continue
            grids += 1
            striped += g['striped']
            seen += g['seen']
            bad += g['badBody']
            for b, v in g['bodies'].items():
                e = bodies.setdefault(b, [0, 0])
                e[0] += v['seen']
                e[1] += v['striped']
        res.check(grids > 5 and seen > 30,
                  'enough grids were formed to judge a chance',
                  '%d grids, %d cars' % (grids, seen))
        if seen:
            print('      %d cars over %d grids, %d striped (%.0f%%)'
                  % (seen, grids, striped, striped / seen * 100))
            for b in sorted(bodies):
                print('        %-9s %d of %d striped' % (b, bodies[b][1], bodies[b][0]))

        # A CHANCE IS NOT A RULE, in either direction. Both bounds matter: at nothing the signal
        # does not exist, and at everything a grid is a team rather than a field.
        res.check(0 < striped < seen,
                  'some opponents wear stripes and some do not',
                  '%d of %d - a chance should produce both' % (striped, seen))
        res.check(not bad,
                  'and no body wears stripes that is not allowed them',
                  'these did: %s' % ', '.join(sorted(set(bad))))

        # THE ONE THING THAT MUST NOT HAPPEN. A formula car has no stripes - it is not in the
        # allowed list, and the painter refuses them on one anyway. Two guards, and this asserts
        # the effect rather than either guard.
        formula = [b for b in bodies if b in ('VECTOR', 'APEX', 'COMET')]
        res.check(all(bodies[b][1] == 0 for b in formula),
                  'and a formula car never does',
                  'striped formula cars appeared: %s'
                  % ', '.join('%s %d' % (b, bodies[b][1]) for b in formula if bodies[b][1]))
        print()

        errs = page.evaluate("() => window.__probe.errors")
        res.check(not errs, 'no page errors', '; '.join(errs[:3]))
        browser.close()
    httpd.shutdown()

    print()
    if res.fails:
        print('FAILED: ' + ', '.join(res.fails))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
