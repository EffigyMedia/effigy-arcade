#!/usr/bin/env python3
"""PRIZE TEST - silver pays a paint set and bronze a livery, once each, to racing cars only.

    .venv/Scripts/python tools/prize-test.py

RLG-071. Signed off by the owner 2026-09-19: silver pays a paint set - production METALLIC, sports
PEARL, super the racing IRIDESCENT set - and bronze a livery: production RALLY stripes, sports a
number ROUNDEL, super TWO-TONE. All nine racing cars wear every livery, and the roundel stacks on a
pattern (owner, 2026-09-19).

WHAT IT ASSERTS, in a fresh save, reading the swatches the garage actually draws:
  . before any silver, a racing car offers the base dozen, and its card names each set and how to win it;
  . each class's silver writes its own flag and adds its own five paints to the racing palette;
  . a second silver in the same class announces nothing new (RLG-202);
  . a formula car's class pays nothing, and a police car's palette gains none of them;
  . once all three are won, the captions are gone;
  . BRONZE: the garage's PATTERN control walks only what is won, ROUNDEL appears only once won, each
    bronze pays once, formula pays nothing, a police car has no livery control;
  . every livery CHANGES THE DRAWN SPRITE of all nine racing cars, and the roundel finds paint on
    every tail;
  . a save from before this build, holding only `stripes: true`, loads as the STRIPES pattern.
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

    def garage(body):
        pg.evaluate("(k) => { const R = window.__probe.road; R.setBody(k); R.showGarage(); }", body)
        pg.wait_for_timeout(300)
        return pg.evaluate("""() => ({
            swatches: [...document.querySelectorAll('[data-act^="paint:"]')].map(b => b.dataset.act.slice(6)),
            notes: [...document.querySelectorAll('#veil .gnote')].map(n => n.textContent),
            pattern: (document.querySelector('[data-act="pattern"] b') || {}).textContent || null,
            roundel: (document.querySelector('[data-act="roundel"] b') || {}).textContent || null })""")

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
    check(g['roundel'] is None, 'and offers no ROUNDEL control', repr(g['roundel']))
    seen = [g['pattern']]
    for _ in range(3):
        seen.append(tap('pattern')['pattern'])
    print('      PATTERN walks %s' % ' -> '.join(map(str, seen)))
    check(set(seen) == {'NONE', 'STRIPES'}, 'and PATTERN walks only NONE and STRIPES', repr(seen))

    for cls, flag in (('production', 'rally'), ('sports', 'roundel'), ('super', 'twotone')):
        got = pg.evaluate("(c) => window.__probe.road.payBronze(c)", cls)
        again = pg.evaluate("(c) => window.__probe.road.payBronze(c)", cls)
        check(got == flag, '%s bronze pays %s' % (cls, flag), repr(got))
        check(again == '', 'and a second %s bronze announces nothing new' % cls, repr(again))
    check(pg.evaluate("() => window.__probe.road.payBronze('formula')") == '',
          "a formula car's class pays no bronze")

    g = garage('COUPE')
    seen = [g['pattern']]
    for _ in range(4):
        seen.append(tap('pattern', 'COUPE')['pattern'])
    print('      PATTERN walks %s' % ' -> '.join(map(str, seen)))
    check(set(seen) == {'NONE', 'STRIPES', 'RALLY', 'TWO-TONE'},
          'once won, PATTERN walks all four patterns', repr(seen))
    check(g['roundel'] == 'OFF', 'and ROUNDEL is offered, OFF', repr(g['roundel']))
    check(tap('roundel', 'COUPE')['roundel'] == 'ON', 'and a tap turns it ON')
    liv = pg.evaluate("() => window.__probe.road.livery()")
    check(bool(liv['roundel']), 'and the car in the garage carries the number', repr(liv))
    check(not any('BRONZE IN A' in n for n in garage('COUPE')['notes']),
          'once all three are won, the bronze captions are gone')
    cop = garage('CRUISER')
    check(cop['pattern'] is None and cop['roundel'] is None,
          'a police car has no livery control', '%r %r' % (cop['pattern'], cop['roundel']))

    # every livery changes the drawn sprite of every racing car, and the roundel lands on every tail
    SPR = """() => {
      const R = window.__probe.road;
      const keys = ['SALOON','COUPE','HATCH','ROADSTER','TUNER','MUSCLE','STALLION','MATADOR','CREST'];
      const ls = [ {}, { stripes:true }, { stripes:'rally' }, { twotone:true }, { roundel:7 } ];
      const rows = R.liverySheet(keys, ls, 'RED');
      const px = c => c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
      const diff = (a, b) => { const A = px(a), B = px(b); let n = 0;
        for (let i = 0; i < A.length; i += 4)
          if (Math.abs(A[i]-B[i]) + Math.abs(A[i+1]-B[i+1]) + Math.abs(A[i+2]-B[i+2]) > 40) n++;
        return n; };
      return keys.map((k, i) => ({ k: k,
        rear:  [1, 2, 3, 4].map(j => diff(rows[i][0], rows[i][2*j])),
        front: [1, 2, 3].map(j => diff(rows[i][1], rows[i][2*j+1])),
        pairVsRally: diff(rows[i][2], rows[i][4]) }));
    }"""
    rows = pg.evaluate(SPR)
    for r in rows:
        print('      %-9s rear px changed  stripes %4d  rally %4d  two-tone %4d  roundel %4d'
              % (r['k'], r['rear'][0], r['rear'][1], r['rear'][2], r['rear'][3]))
    check(all(min(r['rear'][:3]) > 150 and min(r['front']) > 150 for r in rows),
          'every pattern changes the tail and the face of all nine racing cars')
    check(all(r['rear'][3] > 60 for r in rows), 'and the roundel is drawn on all nine tails',
          ', '.join('%s %d' % (r['k'], r['rear'][3]) for r in rows if r['rear'][3] <= 60))
    check(all(r['pairVsRally'] > 100 for r in rows), 'and RALLY is a different drawing from STRIPES')

    errs = pg.evaluate("() => window.__probe.errors")
    check(not errs, 'no page errors', '; '.join(errs[:2]))
    # an older save holds only the stripes switch, and ON was the first pattern
    pg2 = b.new_page(viewport={'width': 480, 'height': 900})
    pg2.add_init_script(INIT)
    boot(pg2, f'http://127.0.0.1:{port}/games/sw/interstate.html')
    until(pg2, '!!window.__probe.road', timeout=10000)
    pg2.evaluate("""() => { const k = 'interstate-opts', s = window.Arcade.save.get(k) || {};
                            delete s.pattern; s.stripes = true; window.Arcade.save.set(k, s); }""")
    boot(pg2, f'http://127.0.0.1:{port}/games/sw/interstate.html')   # boot, not reload: it survives the load wedge
    until(pg2, '!!window.__probe.road', timeout=10000)
    old = pg2.evaluate("() => window.__probe.road.livery().pattern")
    check(old == 'STRIPES', 'a save with only stripes: true loads as the STRIPES pattern', repr(old))
    b.close()
print()
print('  %s' % ('all checks passed' if not fails else '%d check(s) FAILED' % len(fails)))
sys.exit(1 if fails else 0)
