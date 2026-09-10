#!/usr/bin/env python3
"""INTERCEPTOR TEST - the supercar gold pays a car you can actually drive.

    .venv/Scripts/python tools/interceptor-test.py

RLG-181. Four things in the code agreed that the SUPER CRUISER was a prize: `tourScore` wrote
`supercruiser:true` into the save on a supercar gold taken under pursuit, the reward screen counted
it, the garage card named the gold that pays it, and `UNLOCK_HOW` carried its condition. The fifth
made it impossible - `BODY.SUPERCRUISER` carried `npc:true`, and `garageBodies` filters NPC bodies
out before it asks anything else. So the hardest prize in the game opened nothing at all, and no
check anywhere noticed, because every check asked whether the CRUISER worked.

THE OWNER CHOSE TO MAKE IT DRIVABLE, 2026-09-10, over the other answer on the table - removing the
award. So what this file asserts is the whole path a prize has to walk: it is advertised while it is
still to be won, it opens when it is won, and the car that opens is a real one.

AND THE LAST ARM IS THE POINT OF THE FILE. A garage listing check passes trivially - the car is
there or it is not - so this puts `npc:true` BACK on the live record and requires the listing to
fail. The defect is reintroduced and watched, rather than assumed to be gone.

WHAT THIS CANNOT SAY. It reads the garage, not a device. Whether the interceptor is any GOOD to
drive, whether 190mph with a cage in it feels like the floor of the supercar class, and whether the
silhouette reads as a police car before it is won are the owner's verdict on a phone.

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
CAR = 'SUPERCRUISER'
HOW = 'WIN A SUPERCAR TOURNAMENT · HOT PURSUIT ON'


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

    print('interceptor-test  .  the supercar gold pays a car you can drive')
    with sync_playwright() as p:
        b = launch_chromium(p, headless=not args.headed,
                            args=['--mute-audio', '--autoplay-policy=no-user-gesture-required'])
        ctx = b.new_context(viewport={'width': 480, 'height': 900})
        page = ctx.new_page()
        errs = []
        page.on('pageerror', lambda e: errs.append(str(e)))

        def open_garage():
            page.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
            page.click('[data-act="play"]')
            page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)

        def bodies():
            return page.evaluate('() => window.__road.garageBodies()')

        def stand_in_front_of(k):
            page.evaluate('(k) => { window.__road.setBody(k); window.__road.showGarage(); }', k)
            page.wait_for_timeout(150)

        def card():
            return page.evaluate("""() => {
                const w = document.querySelector('#veilBody .gwrap');
                const btn = document.querySelector('#veilBody [data-act="drive"]');
                const cv = document.querySelector('#veilBody #gcar');
                let ink = 0;
                if(cv){
                    const d = cv.getContext('2d').getImageData(0, 0, cv.width, cv.height).data;
                    for(let i = 3; i < d.length; i += 4) if(d[i] > 8) ink++;
                }
                return {
                    locked: !!(w && w.classList.contains('locked')),
                    name: (document.querySelector('#veilBody .gname') || {}).textContent || '',
                    notes: Array.from(document.querySelectorAll('#veilBody .gnote'))
                                .map(e => e.textContent.trim()),
                    stats: Array.from(document.querySelectorAll('#veilBody .gstat'))
                                .map(e => e.textContent.trim()),
                    drive: btn ? btn.textContent.trim() : null,
                    shut: btn ? btn.hasAttribute('disabled') : null,
                    ink: ink
                };
            }""")

        # ---- ARM 1 - IT IS ADVERTISED BEFORE IT IS WON --------------------
        print('  -- a save that has not won it')
        page.goto('%s/%s' % (base, GAME), wait_until='load')
        page.wait_for_timeout(600)
        open_garage()
        listed = bodies()
        ok(CAR in listed, 'the interceptor is listed in the garage',
           '%d cars listed' % len(listed))
        stand_in_front_of(CAR)
        c = card()
        ok(c['locked'], 'and it stands there as a silhouette')
        ok(c['name'] == '???', 'its name is withheld', 'reads %r' % c['name'])
        ok(HOW in c['notes'], 'with the condition written under it',
           'reads %r' % (c['notes'][-1] if c['notes'] else ''))
        ok(c['drive'] == 'LOCKED' and c['shut'] is True,
           'and DRIVE refuses', 'button reads %r, disabled=%s' % (c['drive'], c['shut']))
        ok(c['ink'] > 200, 'the shape is drawn, which is what makes it an invitation',
           '%d lit pixels' % c['ink'])

        # ---- ARM 2 - WIN IT, the way tourScore does ----------------------
        print('  -- and then the supercar gold is taken under pursuit')
        page.evaluate("""() => {
            window.Arcade.save.merge('interstate-opts', { supercruiser:true });
        }""")
        page.reload(wait_until='load')
        page.wait_for_timeout(600)
        del errs[:]
        open_garage()
        won = bodies()
        ok(CAR in won, 'the interceptor is still listed')
        stand_in_front_of(CAR)
        c = card()
        ok(not c['locked'], 'and it is open')
        ok(c['name'] == CAR, 'the card names it', 'reads %r' % c['name'])
        ok(c['drive'] == 'DRIVE' and c['shut'] is False,
           'DRIVE is offered', 'button reads %r' % c['drive'])
        note = c['notes'][0] if c['notes'] else ''
        ok('INTERCEPTOR' in note, 'it reads its own record rather than a blank',
           'note %r' % note)
        ok(any('190 MPH' in s for s in c['stats']),
           'and its own top speed', '; '.join(c['stats']))
        ok(c['ink'] > 200, 'the painter ran', '%d lit pixels' % c['ink'])
        # THE HISTORICAL FAILURE. `cycleBody` still carries the note saying this car
        # once threw a non-finite gradient and took the whole screen down with it.
        ok(not errs, 'and it did not throw - the crash the npc flag was hiding',
           '; '.join(errs[:2]))
        fits = page.evaluate('() => window.__road.garageFits().each[%r]' % CAR)
        ok(isinstance(fits, (int, float)), 'the card has a real height for it',
           'height %s' % fits)

        # ---- ARM 3 - WHAT THE CLASS BUYS ---------------------------------
        print('  -- what the class buys')
        cls = page.evaluate('() => window.__road.bodyClass(%r)' % CAR)
        ok(cls == 'supercruiser', "it is its own class, not the cruiser's",
           'reads %r' % cls)
        ok(page.evaluate('() => window.__road.raceLegal(%r)' % CAR),
           'and it may enter a race, as the floor of its class should')
        ok(page.evaluate('() => window.__road.inCruiser()'),
           'sitting in it, the light bar is yours')

        # ---- ARM 4 - THE FALSIFICATION -----------------------------------
        # A listing check passes for free. Put the defect back on the live record
        # and require this file to see it.
        print('  -- with npc:true put back on the record')
        page.evaluate('() => { window.__road.BODY.%s.npc = true; }' % CAR)
        gone = bodies()
        ok(CAR not in gone,
           'the garage drops it again - the check is not vacuous',
           '%d cars listed' % len(gone))
        page.evaluate('() => { delete window.__road.BODY.%s.npc; }' % CAR)
        back = bodies()
        ok(CAR in back, 'and taking the flag off returns it')

        ctx.close()
        b.close()

    print('  %s' % ('all checks passed' if not bad else '%d check(s) failed' % bad))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
