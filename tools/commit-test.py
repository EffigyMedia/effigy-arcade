#!/usr/bin/env python3
"""COMMIT TEST - one engagement, one target, and a trap that stays parked.

    .venv/Scripts/python tools/commit-test.py

RLG-173. Owner, 2026-09-08: "whenever a cop engages a target it continues to engage that
target until that target either pulls over voluntarily, is forced to stop due to entrapment,
or fails to keep up with its target and it disengages and pulls back over to make a new trap.
Having it retarget something else because it is slightly faster while cool I think will just
break this illusion. So that means one engagement to one target permanently."

THE FOUR CLAIMS, AND THE FIRST IS THE ONE THE FRAGMENT GOT WRONG:

  1. a parked, armed trap does not move and does not take a target - at all
  2. a cruiser engaged to somebody else never switches to the player, however fast you go
  3. a cruiser that is left far enough behind for long enough gives up
  4. and when it gives up it becomes a trap again rather than vanishing

WHY THE FIRST NEEDS MEASURING RATHER THAN READING. `trapWatch` sweeps `traffic` only, so
reading that function alone says the traps already survive a field of rivals - which is what
RLG-173 concluded, and it is wrong. A trap lives in the `cops` array and the main cruiser
update had no guard for it: an armed trap ran the retarget sweep every 1.4 seconds, and the
floor under a cruiser's speed is 2,000 units, so it crept off its post whether it found
anybody or not. This file therefore watches the CAR and not the function.

WHY THE SECOND IS STAGED RATHER THAN WAITED FOR. Catching a cruiser mid-pursuit on the open
road is luck. `placeCop` puts one where it is needed and the engine decides everything after
that, so what is under test is the rule rather than the placement.

AND WHY THE PLAYER IS HELD LEGAL THROUGHOUT THE FIRST CHECK. A trap that leaves its post for
a speeding player is RLG-046 working exactly as ruled, so a check that speeds cannot tell the
defect from the design.

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
from harness import console_utf8, launch_chromium
from playwright.sync_api import sync_playwright

GAME = 'games/sw/interstate.html'

# a speeding traffic car, built the way the road builds one, for a cruiser to commit to
STAGE_NPC = """([dz, frac]) => {
    const R = window.__road, M = R.MAX_SPD;
    R.traffic.length = 0;
    R.placeCop(dz, 0.2);
    const k = R.cops()[0];
    k.from = 'test';
    /* TAGGED, so the check can follow THIS car. `cops[0]` is not an identity: the
       road keeps laying traps into the same array, and a cruiser left behind is
       culled 34,000 units back - so the slot quietly becomes a different car, and
       ITS first commitment reads as the tagged one switching. That produced a
       confident nine-frame failure against an engine doing nothing wrong. */
    k.probe = true;
    R.traffic.push({ z: k.z + 900, lane: 1, x: 0.2, spd: M * frac, cruise: M * frac,
                     mind: 1, type: 'sedan', w: 0.27, len: 400,
                     near: false, drift: 0, paintN: 0 });
    return R.traffic.length;
}"""


def boot(b, base):
    ctx = b.new_context(viewport={'width': 480, 'height': 900})
    page = ctx.new_page()
    errs = []
    page.on('pageerror', lambda e: errs.append(str(e)))
    page.goto('%s/%s' % (base, GAME), wait_until='load')
    try:
        page.wait_for_function(
            '() => navigator.serviceWorker && navigator.serviceWorker.controller', timeout=5000)
        page.wait_for_timeout(1000)
    except Exception:
        pass
    page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
    page.click('[data-act="play"]')
    page.wait_for_timeout(400)
    # HOT PURSUIT ON, or no trap is ever laid: the spawner is gated on it.
    page.click('[data-act="chase"]')
    page.wait_for_timeout(150)
    page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
    page.click('[data-act="drive"]')
    page.wait_for_timeout(1500)
    return ctx, page, errs


def hold(page, frac, ms=100):
    """Hold a speed. Setting it once lets the car coast, and a coasting car proves nothing."""
    page.evaluate('(f) => window.__road.setSpd(f * window.__road.MAX_SPD)', frac)
    page.wait_for_timeout(ms)


def cop0(page):
    """The tagged cruiser, or None once it has left the road.

    NOT `cops[0]`. See the note in STAGE_NPC: that slot changes hands.
    """
    return page.evaluate("""() => {
        const k = window.__road.cops().filter(c => c.probe)[0];
        return k ? { onPlayer: k.onPlayer, engaged: !!k.engaged,
                     trap: !!k.trap, armed: !!k.armed,
                     commits: k.commits || 0,
                     spd: Math.round(k.spd || 0) } : null;
    }""")


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

    print('commit-test  .  one engagement, one target')
    with sync_playwright() as p:
        b = launch_chromium(p, headless=not args.headed,
                            args=['--mute-audio', '--autoplay-policy=no-user-gesture-required'])
        ctx, page, errs = boot(b, base)

        # ============ 1. A PARKED TRAP IS SCENERY UNTIL trapWatch TRIPS IT =========
        page.evaluate('() => window.__road.copsClear()')
        page.evaluate('() => window.__road.spawnTrap()')
        laid = page.evaluate('() => window.__road.trapWatchState().length')
        # WHERE IT WAS PUT, in absolute road units. `dz` is measured from the player and
        # changes every frame because the PLAYER moves, so a drift check reading it is
        # reading the driver rather than the trap.
        posts = {}
        for k in page.evaluate('() => window.__road.trapWatchState()'):
            posts[k['z']] = k['z']
        moved, took, top, drift = 0, 0, 0, 0
        for _ in range(120):
            # THE TRAFFIC IS EMPTIED, and that is what makes the reading mean anything:
            # a trap tripped by a speeding traffic car has left its post CORRECTLY, and
            # leaving the road populated makes the two indistinguishable.
            page.evaluate('() => { window.__road.traffic.length = 0; }')
            hold(page, 0.30)          # legal - the limit is 0.40 of top speed
            for k in page.evaluate('() => window.__road.trapWatchState()'):
                if not (k['trap'] and k['armed']):
                    continue
                top = max(top, abs(k['spd']))
                if abs(k['spd']) > 1:
                    moved += 1
                if k['tz'] is not None:
                    took += 1
                # a trap first seen this tick is one the spawner has just laid, and its
                # own post is wherever it was put
                near = min(posts, key=lambda z: abs(z - k['z'])) if posts else None
                if near is None or abs(near - k['z']) > 4000:
                    posts[k['z']] = k['z']
                    continue
                # ---- AND BEING HIT IS NOT LEAVING (measured, not assumed) ------
                # A parked trap is a solid object and the player can drive into one;
                # the collision knocks it back exactly 500 units, which is the engine
                # treating it like any other car and is not it creeping off its post.
                # A first version of this check called that a failure. What the claim
                # is really about is a trap moving UNDER ITS OWN POWER, so samples
                # taken while the player is close enough to touch it are not evidence
                # either way and are left out.
                if abs(k['dz']) < 2000:
                    posts[k['z']] = k['z']
                    continue
                drift = max(drift, abs(near - k['z']))
        end = page.evaluate('() => window.__road.trapWatchState()')
        ok(laid > 0, 'a trap is on the road to measure at all', '%d laid' % laid)
        ok(drift == 0, 'a parked trap never moves under its own power',
           'furthest any drifted clear of the player: %d units over 12s' % drift)
        ok(moved == 0, 'and its engine is never turning either',
           '%d frames with a speed on it, fastest %d units/s' % (moved, top))
        ok(took == 0, 'and it never takes a target', '%d frames holding one' % took)
        ok(bool(end) and end[0]['trap'] and end[0]['armed'],
           'so it is still a trap, still armed, twelve seconds later', str(end[:1]))

        # ============ 2. A COMMITTED CRUISER DOES NOT SWITCH TO YOU ================
        # THE EXACT CASE THAT DID TAKE THE PURSUIT YESTERDAY. The rule that shipped on
        # 2026-09-08 released a cruiser to the player when the player went past it ten
        # miles an hour quicker than the car it had, so this check fails on that build
        # and passes on this one - which is what makes it worth running.
        page.evaluate('() => window.__road.copsClear()')
        page.evaluate(STAGE_NPC, [6000, 0.62])
        for _ in range(20):
            hold(page, 0.55, 60)
        got = cop0(page)
        ok(bool(got) and got['engaged'] and got['onPlayer'] is False,
           'the cruiser commits to the traffic car beside it', str(got))
        # ---- WHAT COUNTS AS A SWITCH, AND WHAT DOES NOT ----------------------
        # A first version of this counted every frame the cruiser was on the player and
        # called 19 of them a failure. They were legitimate: the cruiser lost its car off
        # the back of the road, gave up, parked as a trap, and then caught a player doing
        # 196 - three rules working in sequence. A second version watched for the trap
        # state in between and still failed once, because giving up and being tripped
        # again can both happen inside one 60ms sample.
        #
        # SO THE CAR IS ASKED HOW MANY TIMES IT HAS CHOSEN. A cruiser that reaches the
        # player on the SAME commitment it took the NPC with has been switched, which is
        # the defect; one that reaches the player on a LATER commitment gave up first,
        # which is the design. The counter cannot be outrun by the sample rate.
        first = cop0(page)
        base_commits = first['commits'] if first else 0
        switched, gone = 0, 0
        for _ in range(60):
            hold(page, 0.98, 60)
            st = cop0(page)
            if st is None:
                gone += 1          # left behind and culled, which ends the experiment
                continue
            if st['onPlayer'] is True and st['commits'] <= base_commits:
                switched += 1
        end2 = cop0(page)
        ok(switched == 0, 'and blasting past it does not take it off them',
           '%d frames on the player without a fresh commitment; commits %d -> %s'
           % (switched, base_commits, end2['commits'] if end2 else 'car culled'))
        # AND IT HAS TO HAVE BEEN THERE TO PROVE ANYTHING. A cruiser culled on the first
        # tick would pass the check above by being absent, which is the vacuity this
        # project has been caught by before.
        ok(gone < 55, 'and the cruiser was actually on the road while this was asked',
           '%d of 60 samples had it culled' % gone)

        # ============ 3 & 4. IT GIVES UP, AND WHAT IT BECOMES ======================
        # LOSING GROUND, not a bare distance. The condition is five seconds of the gap
        # opening, so the target is pushed up the road every tick and kept at speed -
        # a target parked twenty thousand units away is a different situation.
        page.evaluate('() => window.__road.copsClear()')
        page.evaluate(STAGE_NPC, [2000, 0.62])
        for _ in range(16):
            hold(page, 0.55, 60)
        engaged = cop0(page)
        ok(bool(engaged) and engaged['engaged'], 'a second cruiser commits to its car',
           str(engaged))
        parked_again, waited = False, 0
        for i in range(140):
            page.evaluate("""() => { const R = window.__road;
                for(const c of R.traffic){ c.z += 900; c.spd = R.MAX_SPD * 0.62; } }""")
            hold(page, 0.30, 100)
            waited = i
            st = cop0(page)
            if st and st['trap'] and st['armed']:
                parked_again = True
                break
        ok(parked_again,
           'a cruiser that cannot keep up gives up and becomes a trap again',
           'after %.1fs; %s' % (waited * 0.1, str(cop0(page))))
        ok(parked_again and cop0(page)['spd'] == 0,
           'and it is stopped on the verge rather than still rolling', str(cop0(page)))

        ok(not errs, 'and the whole run was clean', '; '.join(errs[:2]))
        ctx.close()
        b.close()

    print('  %s' % ('all checks passed' if not bad else '%d check(s) failed' % bad))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
