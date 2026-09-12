#!/usr/bin/env python3
"""RESORT - the fleet sorts into three groups, and the non-racers are ONE of them.

    .venv/Scripts/python tools/resort-test.py

RLG-213. The owner settled the class ladder on 2026-09-12: production becomes the
LOW END RACE class, and the low-end traffic cars and the utility vehicles merge
into a single class on a single unlock trigger. This checks the resort - the part
everything else reads - and not the ladder, which is separate work.

    production   SALOON, COUPE          open from the start, no unlock
    traffic      CAB, PICKUP, VAN,      one secret unlock, one distance trigger
                 SEMI, AMBULANCE
    racing       sports, super, formula unchanged

THE MIGRATION IS THE POINT OF THE NAME. The merged class is called `traffic`,
which is not a new name: it is the flag from the old hundred-mile rule, and
`carLocked` and `openBy` have honoured it as a fall-through ever since. So a save
that earned it keeps every car, with no migration table to write - and RLG-197
records that a migration is never removed once written, so not needing one is
worth more than it looks. This checks that a save holding ONLY the old flag opens
the whole merged class.

AND IT CHECKS THE TWO OLD FLAGS SEPARATELY, because they are what a real save
holds. `production` and `utility` were granted at 50 and 25 miles, and a player
who earned `utility` alone must not silently gain the cab and the pickup they had
not won - nor lose the van they had.

WHAT IT WOULD CATCH. A body left in a class that no longer exists shows up as a
car that can never be unlocked; the fleet sheet keeping its own copy of the class
map and drifting from the garage's shows up as two answers to what a pickup is;
and production still gating shows up as a starting car the player does not have.

Exit code 0 if every check passes, 1 otherwise.
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
KEY = 'effigyarcade.save.v1.interstate-opts'

PRODUCTION = ['SALOON', 'COUPE']
MERGED = ['CAB', 'PICKUP', 'VAN', 'SEMI', 'AMBULANCE']
SPORTS = ['ROADSTER', 'TUNER', 'MUSCLE']
EXPECT = {'production': ['SALOON', 'COUPE'],
          'sports': ['ROADSTER', 'TUNER', 'MUSCLE'],
          'super': ['STALLION', 'MATADOR', 'CREST']}


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def serve(root):
    handler = functools.partial(QuietHandler, directory=str(root))
    httpd = socketserver.TCPServer(('127.0.0.1', 0), handler)
    httpd.allow_reuse_address = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.socket.getsockname()[1]


class Res:
    def __init__(self):
        self.fails = []

    def ok(self, good, label, detail=''):
        print(('  ok    ' if good else '  FAIL  ') + label
              + ('' if good else '   [' + detail + ']'))
        if not good:
            self.fails.append(label)


def boot_with(browser, port, save):
    """open the game with a given save already written, as a returning player"""
    ctx = browser.new_context(viewport={'width': 480, 'height': 900})
    page = ctx.new_page()
    page.add_init_script(
        "try { localStorage.setItem(%r, %r); } catch (e) {}" % (KEY, save))
    boot(page, 'http://127.0.0.1:%d/%s' % (port, GAME))
    until(page, '!!window.__road', timeout=10000)
    page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
    page.click('[data-act="play"]')
    page.wait_for_timeout(300)
    return ctx, page


def listed(page):
    """the cars that can actually be DRIVEN.

    `garageBodies` is the wrong question and was asked first: it is what the
    garage LISTS, and a locked class that is not secret is listed as a
    SILHOUETTE. So the sports cars read as owned on a fresh save, and the check
    that they are locked passed with them wide open. `playableBodies` filters
    by `carLocked`, which is the question ownership actually is.

    MEMBERSHIP IS THE INSTRUMENT, and the first version of this used the card's
    name instead - it asked each body in turn whether its card read `???`. That
    check was VACUOUS and was watched passing with the migration deleted: a
    SECRET class is ABSENT from the garage when it is locked rather than shown
    as a silhouette, by the owner's own ruling, so `setBody` on a car you have
    not won falls back to a ROADSTER and the card reads ROADSTER. Every arm
    reported "nothing lost" because nothing was there to lose.
    """
    return set(page.evaluate("() => window.__road.playableBodies()"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--headed', action='store_true')
    args = ap.parse_args()
    console_utf8()
    httpd, port = serve(ROOT)
    res = Res()
    print('resort  .  production is a race class and the non-racers are one class')
    with sync_playwright() as p:
        b = launch_chromium(p, headless=not args.headed,
                            args=['--mute-audio',
                                  '--autoplay-policy=no-user-gesture-required'])

        # ---- A BRAND NEW SAVE -------------------------------------------------
        ctx, page = boot_with(b, port, '{}')
        errs = []
        page.on('pageerror', lambda e: errs.append(str(e)))
        have = listed(page)
        missing = [k for k in PRODUCTION if k not in have]
        res.ok(not missing,
               'a new player STARTS in production - both cars, nothing to unlock',
               'not offered: %s' % ', '.join(missing))
        early = [k for k in MERGED if k in have]
        res.ok(not early, 'and has none of the merged class yet',
               'already offered: %s' % ', '.join(early))
        ctx.close()

        # ---- A SAVE THAT EARNED THE OLD HUNDRED-MILE FLAG ----------------------
        ctx, page = boot_with(b, port, '{"traffic":true}')
        have = listed(page)
        shut = [k for k in MERGED if k not in have]
        res.ok(not shut,
               'the old hundred-mile flag still opens the WHOLE merged class',
               'still missing: %s' % ', '.join(shut))
        ctx.close()

        # ---- AND THE TWO FLAGS A REAL SAVE ACTUALLY HOLDS ---------------------
        # These were granted separately at 25 and 50 miles. A player who earned
        # UTILITY alone owned the van, the lorry and the ambulance and had not won
        # the cab or the pickup - so this says what happens to them, rather than
        # leaving it to be discovered by whoever still has that save.
        for flag, had in (('utility', ['VAN', 'SEMI', 'AMBULANCE']),
                          ('production', ['CAB', 'PICKUP'])):
            ctx, page = boot_with(b, port, '{"%s":true}' % flag)
            have = listed(page)
            lost = [k for k in had if k not in have]
            res.ok(not lost,
                   'a save holding only %r keeps every car it had won' % flag,
                   'lost: %s' % ', '.join(lost))
            ctx.close()

        # ---- THE TWO CLASS MAPS MUST AGREE ------------------------------------
        # `API.fleet` keeps its own copy for the fleet sheet, and its own comment
        # records what happens when the two drift: the sheet prints a class the
        # garage disagrees with. Asked of the sheet's own output.
        ctx, page = boot_with(b, port, '{"traffic":true}')
        rows = page.evaluate(
            "() => window.__road.fleet ? window.__road.fleet()"
            " .map(r => [r.key, r.cls]) : null")
        if rows is None:
            print('  BLKD  the engine does not expose the fleet sheet rows')
        else:
            seen = {}
            for key, cls in rows:
                seen.setdefault(key, set()).add(cls)
            split = {k: v for k, v in seen.items() if len(v) > 1}
            res.ok(not split, 'no body is given two classes by the sheet',
                   '; '.join('%s is %s' % (k, '/'.join(sorted(v)))
                             for k, v in split.items()))
            wrong = [k for k in MERGED
                     if k in seen and seen[k] != {'traffic'}]
            res.ok(not wrong,
                   'the sheet agrees with the garage about the merged class',
                   '; '.join('%s is %s' % (k, '/'.join(sorted(seen[k])))
                             for k in wrong))
            wrong2 = [k for k in PRODUCTION
                      if k in seen and seen[k] != {'production'}]
            res.ok(not wrong2, 'and about production',
                   '; '.join('%s is %s' % (k, '/'.join(sorted(seen[k])))
                             for k in wrong2))
        # ---- THE LADDER, AND THAT A FRESH SAVE HAS A ROAD OUT ----------------
        # RLG-213: production -> sports -> super -> formula. The rung that matters
        # most is the FIRST one, because a locked sports class with no way to win
        # it is a new game with two cars and nowhere to go - so this asks the
        # engine what league a production car enters and what a gold in it pays.
        ctx, page = boot_with(b, port, '{}')
        have = listed(page)
        shut = [k for k in SPORTS if k in have]
        res.ok(not shut, 'a fresh save does NOT hold the sports cars',
               'already offered: %s' % ', '.join(shut))
        d = page.evaluate("() => { const R = window.__road;"
                          " R.setBody('SALOON'); return R.duty(); }")
        res.ok(d['cls'] == 'production',
               'a production car enters the PRODUCTION league',
               "it reads %r, so its grid is somebody else's class" % d['cls'])
        res.ok(d['raceLegal'],
               'and it may actually enter a race',
               'RACE_BANNED still holds it, so the league it has cannot be reached')
        print('      with a SALOON the MODE control reads %r' % d['label'])

        # THE RUNG ITSELF. `goldPays` looks the selected car's class up in the same
        # GOLD_PAYS table the finish grants from, so this exercises the ladder
        # rather than a harness's copy of it.
        pays = page.evaluate("() => { const R = window.__road;"
                             " R.setBody('SALOON'); return R.goldPays(); }")
        res.ok(pays == 'sports',
               'a gold in production unlocks the sports class',
               'it pays %r, so a new game has no road out' % pays)
        rungs = page.evaluate(
            "() => { const R = window.__road; const out = {};"
            " for(const k of ['SALOON','TUNER','STALLION','VECTOR']){"
            "   R.setBody(k); out[R.duty().cls] = R.goldPays(); } return out; }")
        res.ok(rungs == {'production': 'sports', 'sports': 'super',
                         'super': 'formula', 'formula': ''},
               'the ladder runs production, sports, super, formula - and STOPS',
               'it reads %r' % rungs)
        # Owner, 2026-09-12: "I don't think the formula car can be used to unlock
        # anything." A win in one used to pay the iridescent paints, which with no
        # formula league meant winning ANY race in it paid the last prize in the
        # game - against a class it outguns by design.
        res.ok(rungs.get('formula') == '',
               'a formula win unlocks nothing at all',
               'it pays %r' % rungs.get('formula'))

        # ---- AND A PRODUCTION CAR CARRIES NO BOTTLE (owner, 2026-09-12) ------
        # "Production cars will not have nitrous bottles." It was already true and
        # true by ACCIDENT - production was not a racing class when `hasNosFor`
        # was written, so it was never a candidate. It is a league now, and the
        # next reader of that list sees three racing classes in it and a fourth
        # missing. This is what stops it being added for symmetry.
        #
        # THE CHECK IS PAIRED, because "no bottle" passes on a build where nobody
        # has one: it asserts the sports cars still DO.
        nos = page.evaluate(
            "() => { const R = window.__road; const out = {};"
            " for(const k of ['SALOON','COUPE','TUNER','ROADSTER','MUSCLE'])"
            "   out[k] = R.hasNosFor ? R.hasNosFor(k) : null; return out; }")
        if nos.get('SALOON') is None:
            print('  BLKD  the engine does not expose which cars carry a bottle')
            res.fails.append('the bottle rule could not be asked')
        else:
            armed = [k for k in PRODUCTION if nos.get(k)]
            res.ok(not armed, 'a production car carries NO nitrous bottle',
                   'these do: %s' % ', '.join(armed))
            bare = [k for k in SPORTS if not nos.get(k)]
            res.ok(not bare, 'and the sports cars still do - so the check is paired',
                   'these do not: %s' % ', '.join(bare))
        ctx.close()

        # ---- THE FORMULA NOVELTY (RLG-213) -----------------------------------
        # "No formula specific races or tournament. You can only race against the
        # first 3 classes." So a formula car's GRID is whatever class it was told
        # to enter, and `classOf` still answers `formula` - which now means "this
        # car has no league" rather than "this car has one of its own".
        #
        # IT IS ASKED OF THE FIELD, not of the setting. A control that cycles a
        # variable while the grid stays formula is the exact failure here.
        ctx, page = boot_with(b, port, '{"sports":true,"super":true,'
                                       '"formula":true,"traffic":true}')
        seen = {}
        for want in ('production', 'sports', 'super'):
            g = page.evaluate(
                "(c) => { const R = window.__road; R.setBody('VECTOR');"
                " let g = R.grid(); let n = 0;"
                " while(g.entry !== c && n++ < 6){ R.cycleEntry(); g = R.grid(); }"
                " return g; }", want)
            seen[want] = g
        for want, g in seen.items():
            res.ok(g['entry'] == want and set(g['field']) == set(EXPECT[want]),
                   'a formula car entering %s races %s cars' % (want, want),
                   'it entered %r against %s' % (g['entry'], ', '.join(g['field'])))
        res.ok(all('VECTOR' not in g['field'] for g in seen.values()),
               'and never races other formula cars - there is no formula league',
               'a formula body turned up on the grid')
        # AND A REAL CLASS STILL FIELDS ITSELF, which is what stops the above
        # passing on a build where every grid is production.
        g = page.evaluate("() => { const R = window.__road;"
                          " R.setBody('TUNER'); return R.grid(); }")
        res.ok(set(g['field']) == set(EXPECT['sports']),
               'a sports car still races sports cars',
               'it faced %s' % ', '.join(g['field']))
        ctx.close()

        if errs:
            res.ok(False, 'the page reported no errors', '; '.join(errs[:3]))
        ctx.close()
        b.close()
    httpd.shutdown()
    print()
    if res.fails:
        print('FAILED: ' + '; '.join(res.fails))
        return 1
    print('the fleet sorts into three groups and both class maps agree')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
