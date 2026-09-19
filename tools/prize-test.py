#!/usr/bin/env python3
"""PRIZE TEST - silver pays a paint set and bronze a livery, once each, to racing cars only.

    .venv/Scripts/python tools/prize-test.py

RLG-071. Signed off by the owner 2026-09-19: silver pays a paint set - production METALLIC, sports
PEARL, super the racing IRIDESCENT set - and bronze a livery, as the owner reproposed it the same
day: production STRIPES (locked until then, five patterns), sports TWO-TONE with the second colour
the player's choice, super a static UNDERGLOW in the player's colour. All nine racing cars wear
every livery.

WHAT IT ASSERTS, in a fresh save, reading the swatches the garage actually draws:
  . before any silver, a racing car offers the base dozen, and its card names each set and how to win it;
  . each class's silver writes its own flag and adds its own five paints to the racing palette;
  . a second silver in the same class announces nothing new (RLG-202);
  . a formula car's class pays nothing, and a police car's palette gains none of them;
  . once all three are won, the captions are gone;
  . BRONZE, on the CUSTOMISE screen: before any bronze there is no stripe, two-tone or underglow
    control; each bronze pays once and opens its own; STRIPES walks NONE and five patterns and
    worn stripes take a chosen colour; TWO-TONE is its own switch, worn over the stripes, in a
    chosen tone; UNDERGLOW shows its colours when ON and the ROAD draws the chosen one; formula pays
    nothing; a police car has none of it; DONE returns to a main garage with no paint on it;
  . every pattern CHANGES THE DRAWN SPRITE of all nine racing cars, the five stripe patterns are
    five different drawings, and a chosen second tone differs from the automatic one;
  . a save holding only `stripes: true` loads as the STRIPES pattern.
The payout is called through `API.paySilver`, the same function the finish line calls: finishing a
tournament in second place is a whole race, which measures the race and not the prize.

WHAT IT CANNOT SEE: whether metallic reads as metallic and pearl as pearl on a phone, or whether the
liveries look right at driving size. The owner's call.

Exit code 0 if every check passed, 1 otherwise.
"""
import sys, functools, http.server, socketserver, threading
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
INIT = (ROOT / 'tools' / 'collide-test.py').read_text(encoding='utf-8').split('INIT = r"""')[1].split('"""')[0]
from harness import console_utf8, launch_chromium, boot, until
from playwright.sync_api import sync_playwright
console_utf8()

fails = []


def check(ok, label, detail=''):
    print('  %s  %s%s' % ('ok  ' if ok else 'FAIL', label, '   ' + detail if detail else ''))
    if not ok:
        fails.append(label)


class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


s = socketserver.TCPServer(('127.0.0.1', 0), functools.partial(Q, directory=str(ROOT)))
port = s.server_address[1]
threading.Thread(target=s.serve_forever, daemon=True).start()
print('prize-test  .  silver pays a paint set, bronze a livery')
with sync_playwright() as p:
    b = launch_chromium(p, headless=True)
    pg = b.new_page(viewport={'width': 480, 'height': 900})
    pg.add_init_script(INIT)
    boot(pg, f'http://127.0.0.1:{port}/games/sw/interstate.html')
    until(pg, '!!window.__probe.road', timeout=10000)
    pg.click('[data-act="play"]')
    pg.wait_for_selector('#veil:not(.hidden) [data-act="drive"]')

    # every look of the car is on the CUSTOMISE screen (owner, 2026-09-19), so this opens it
    def garage(body):
        pg.evaluate("(k) => { const R = window.__probe.road; R.setBody(k); R.showGarage(); }", body)
        pg.wait_for_timeout(300)
        if pg.query_selector('#veil [data-act="custom"]'):
            pg.click('#veil [data-act="custom"]')
            pg.wait_for_timeout(200)
        return pg.evaluate("""() => ({
            swatches: [...document.querySelectorAll('[data-act^="paint:"]')].map(b => b.dataset.act.slice(6)),
            notes: [...document.querySelectorAll('#veil .gnote')].map(n => n.textContent),
            pattern: (document.querySelector('[data-act="pattern"] b') || {}).textContent || null,
            glow: (document.querySelector('[data-act="glow"] b') || {}).textContent || null,
            twotone: (document.querySelector('[data-act="twotone"] b') || {}).textContent || null,
            tones: document.querySelectorAll('[data-act^="tone:"]').length,
            stripeCs: document.querySelectorAll('[data-act^="stripe:"]').length,
            glows: document.querySelectorAll('[data-act^="glowc:"]').length })""")

    g0 = garage('HATCH')
    print('      a fresh HATCH offers %d paints' % len(g0['swatches']))
    check(len(g0['swatches']) == 12, 'before any silver, a racing car offers the base dozen', '%d' % len(g0['swatches']))
    check(sum(1 for n in g0['notes'] if 'SILVER IN A' in n) == 3,
          'and its card names all three sets and how to win them',
          '; '.join(n for n in g0['notes'] if 'SILVER' in n))

    expect = (('production', 'metallic', 'GUNMETAL', 17), ('sports', 'pearl', 'PEARL', 22),
              ('super', 'iridescent', 'ORACLE', 27))
    for cls, flag, sample, total in expect:
        got = pg.evaluate("(c) => window.__probe.road.paySilver(c)", cls)
        again = pg.evaluate("(c) => window.__probe.road.paySilver(c)", cls)
        g = garage('HATCH')
        print('      %-10s silver paid %-10s -> HATCH offers %d paints' % (cls, repr(got), len(g['swatches'])))
        check(got == flag, '%s silver pays %s' % (cls, flag), repr(got))
        check(again == '', 'and a second %s silver announces nothing new' % cls, repr(again))
        check(sample in g['swatches'] and len(g['swatches']) == total,
              'and the racing palette gains its five paints', '%d paints, %s %s' % (
                  len(g['swatches']), sample, 'present' if sample in g['swatches'] else 'MISSING'))

    check(pg.evaluate("() => window.__probe.road.paySilver('formula')") == '',
          'a formula car\'s class pays no silver')
    pg.evaluate("() => window.Arcade.save.merge('interstate-opts', { cruiser:true })")
    cop = garage('CRUISER')
    check(not ({'GUNMETAL', 'PEARL', 'ORACLE'} & set(cop['swatches'])),
          'and a police car gains none of the racing sets', ', '.join(cop['swatches']))
    g9 = garage('HATCH')
    check(not any('SILVER IN A' in n for n in g9['notes']),
          'once all three are won, the captions are gone')
    # ---- BRONZE --------------------------------------------------------------
    print('  bronze')

    def tap(act, body='HATCH'):
        pg.click('#veil [data-act="%s"]' % act)
        pg.wait_for_timeout(150)
        return garage(body)

    g = garage('HATCH')
    check(sum(1 for n in g['notes'] if 'BRONZE IN A' in n) == 3,
          'before any bronze, a racing car names all three liveries and how to win them',
          '; '.join(n for n in g['notes'] if 'BRONZE' in n))
    check(g['pattern'] is None and g['glow'] is None, 'and offers no PATTERN and no UNDERGLOW control',
          '%r %r' % (g['pattern'], g['glow']))

    for cls, flag in (('production', 'stripeset'), ('sports', 'twotone'), ('super', 'underglow')):
        got = pg.evaluate("(c) => window.__probe.road.payBronze(c)", cls)
        again = pg.evaluate("(c) => window.__probe.road.payBronze(c)", cls)
        check(got == flag, '%s bronze pays %s' % (cls, flag), repr(got))
        check(again == '', 'and a second %s bronze announces nothing new' % cls, repr(again))
    check(pg.evaluate("() => window.__probe.road.payBronze('formula')") == '',
          "a formula car's class pays no bronze")

    g = garage('COUPE')
    seen = [g['pattern']]
    for _ in range(6):
        seen.append(tap('pattern', 'COUPE')['pattern'])
    print('      STRIPES walks %s' % ' -> '.join(map(str, seen)))
    check(set(seen) == {'NONE', 'STRIPES', 'RALLY', 'BAND', 'TRIPLE', 'PINSTRIPE'},
          'once won, STRIPES walks NONE and five patterns', repr(seen))
    while g['pattern'] != 'RALLY':
        g = tap('pattern', 'COUPE')
    check(g['stripeCs'] >= 13, 'worn stripes show a row of colours, AUTO and the palette', '%d' % g['stripeCs'])
    pg.click('#veil [data-act="stripe:BLACK"]')
    pg.wait_for_timeout(150)

    # two-tone is its own switch now, and goes on with the stripes still worn
    check(g['twotone'] == 'OFF', 'TWO-TONE is offered once won, OFF', repr(g['twotone']))
    g = tap('twotone', 'COUPE')
    check(g['tones'] >= 13, 'and ON shows a row of second tones, AUTO and the palette', '%d' % g['tones'])
    pg.click('#veil [data-act="tone:GOLD"]')
    pg.wait_for_timeout(150)
    liv = pg.evaluate("() => window.__probe.road.livery()")
    check(liv['toneKey'] == 'GOLD' and liv['twotone'] and liv['tone'] is not None,
          'and a tapped tone is the one worn', '%r %r' % (liv['toneKey'], liv['twotone']))
    check(liv['stripes'] == 'rally' and liv['stripeCol'] is not None,
          'and the stripes are worn with it, in the colour tapped', '%r %r' % (liv['stripes'], liv['stripeCol']))

    g = garage('COUPE')
    check(g['glow'] == 'OFF' and not g['glows'], 'UNDERGLOW is offered once won, OFF, with no colours shown',
          '%r %d' % (g['glow'], g['glows']))
    g = tap('glow', 'COUPE')
    check(g['glow'] == 'ON' and g['glows'] == 7, 'and ON shows its seven colours', '%r %d' % (g['glow'], g['glows']))
    pg.click('#veil [data-act="glowc:MAGENTA"]')
    pg.wait_for_timeout(150)
    check(not any('BRONZE IN A' in n for n in garage('COUPE')['notes']),
          'once all three are won, the bronze captions are gone')
    cop = garage('CRUISER')
    check(cop['pattern'] is None and cop['glow'] is None and cop['twotone'] is None and not cop['tones'],
          'a police car has no livery control', '%r %r %r' % (cop['pattern'], cop['glow'], cop['twotone']))

    # the main garage holds no look of the car: it goes back there with DONE
    garage('COUPE')
    pg.click('#veil [data-act="done"]')
    pg.wait_for_timeout(200)
    main = pg.evaluate("""() => ({ custom: !!document.querySelector('#veil [data-act="custom"]'),
        settings: !!document.querySelector('#veil [data-act="settings"]'),
        box: !!document.querySelector('#veil [data-act="box"]'),
        looks: document.querySelectorAll('#veil [data-act^="paint:"],#veil [data-act="pattern"],#veil [data-act="glow"]').length,
        arrows: document.querySelectorAll('#veil .gbox [data-act]').length })""")
    check(main['custom'] and main['settings'] and not main['box'] and main['looks'] == 0 and main['arrows'] == 2,
          'DONE returns to a main garage with CUSTOMISE, SETTINGS, two arrows, and no paint or gearbox',
          repr(main))

    # the road draws the glow under the car
    pg.click('#veil [data-act="drive"]')
    pg.wait_for_timeout(1500)
    drawn = pg.evaluate("() => window.__probe.road.glowDrawn()")
    check(drawn == '#ff3fd2', 'and the road draws the chosen glow under the car', repr(drawn))

    # every pattern changes the drawn sprite of every racing car
    SPR = """() => {
      const R = window.__probe.road;
      const keys = ['SALOON','COUPE','HATCH','ROADSTER','TUNER','MUSCLE','STALLION','MATADOR','CREST'];
      const ls = [ {}, { stripes:true }, { stripes:'rally' }, { stripes:'band' }, { stripes:'triple' },
                   { stripes:'pin' }, { twotone:true }, { twotone:true, tone:'GOLD' },
                   { stripes:true, stripeCol:'GOLD' } ];
      const rows = R.liverySheet(keys, ls, 'RED');
      const px = c => c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
      const diff = (a, b) => { const A = px(a), B = px(b); let n = 0;
        for (let i = 0; i < A.length; i += 4)
          if (Math.abs(A[i]-B[i]) + Math.abs(A[i+1]-B[i+1]) + Math.abs(A[i+2]-B[i+2]) > 40) n++;
        return n; };
      return keys.map((k, i) => {
        const rear = [1, 2, 3, 4, 5, 6].map(j => diff(rows[i][0], rows[i][2*j]));
        const front = [1, 2, 3, 4, 5, 6].map(j => diff(rows[i][1], rows[i][2*j+1]));
        let apart = 1e9;
        for (let a = 1; a <= 5; a++) for (let b = a + 1; b <= 5; b++)
          apart = Math.min(apart, diff(rows[i][2*a], rows[i][2*b]));
        return { k: k, rear: rear, front: front, apart: apart, tone: diff(rows[i][12], rows[i][14]),
                 stripeC: diff(rows[i][2], rows[i][16]) };
      });
    }"""
    rows = pg.evaluate(SPR)
    for r in rows:
        print('      %-9s rear px changed  %s   least apart %4d   chosen tone %4d'
              % (r['k'], ' '.join('%4d' % n for n in r['rear']), r['apart'], r['tone']))
    check(all(min(r['rear']) > 150 and min(r['front']) > 150 for r in rows),
          'every pattern changes the tail and the face of all nine racing cars')
    check(all(r['apart'] > 100 for r in rows), 'and the five stripe patterns are five different drawings',
          ', '.join('%s %d' % (r['k'], r['apart']) for r in rows if r['apart'] <= 100))
    check(all(r['tone'] > 150 for r in rows), 'and a chosen second tone differs from the automatic one')
    check(all(r['stripeC'] > 150 for r in rows), 'and a chosen stripe colour differs from the automatic one',
          ', '.join('%s %d' % (r['k'], r['stripeC']) for r in rows if r['stripeC'] <= 150))

    errs = pg.evaluate("() => window.__probe.errors")
    check(not errs, 'no page errors', '; '.join(errs[:2]))
    # AN OLDER SAVE HOLDS ONLY THE STRIPES SWITCH. It is read at boot, so each case boots a page on
    # it: ON with nothing won paints no stripes, and ON with stripes won loads as the STRIPES pattern.
    URL = f'http://127.0.0.1:{port}/games/sw/interstate.html'

    def booted_on(extra):
        pg2 = b.new_page(viewport={'width': 480, 'height': 900})
        pg2.add_init_script(INIT)
        boot(pg2, URL)
        until(pg2, '!!window.__probe.road', timeout=10000)
        pg2.evaluate("""(x) => { const k = 'interstate-opts', s = window.Arcade.save.get(k) || {};
                                 delete s.pattern; s.stripes = true; Object.assign(s, x);
                                 window.Arcade.save.set(k, s); }""", extra)
        boot(pg2, URL)   # boot, not reload: it survives the load wedge
        until(pg2, '!!window.__probe.road', timeout=10000)
        pg2.evaluate("() => { const R = window.__probe.road; R.setBody('HATCH'); }")
        out = pg2.evaluate("() => window.__probe.road.livery()")
        pg2.close()
        return out

    liv = booted_on({})
    check(liv['stripes'] is False, 'a save with the old switch ON and nothing won wears no stripes',
          repr(liv['stripes']))
    liv = booted_on({'stripeset': True})
    check(liv['pattern'] == 'STRIPES' and liv['stripes'] is True,
          'and with stripes won it loads as the STRIPES pattern', '%r %r' % (liv['pattern'], liv['stripes']))
    b.close()
print()
print('  %s' % ('all checks passed' if not fails else '%d check(s) FAILED' % len(fails)))
sys.exit(1 if fails else 0)
