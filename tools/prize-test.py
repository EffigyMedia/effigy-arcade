#!/usr/bin/env python3
"""PRIZE TEST - silver pays each racing tournament's paint set, once, to racing cars only.

    .venv/Scripts/python tools/prize-test.py

RLG-071. Signed off by the owner 2026-09-19: silver pays a paint set - production METALLIC, sports
PEARL, super the racing IRIDESCENT set - and bronze a livery (built separately).

WHAT IT ASSERTS, in a fresh save, reading the swatches the garage actually draws:
  . before any silver, a racing car offers the base dozen, and its card names each set and how to win it;
  . each class's silver writes its own flag and adds its own five paints to the racing palette;
  . a second silver in the same class announces nothing new (RLG-202);
  . a formula car's class pays nothing, and a police car's palette gains none of them;
  . once all three are won, the captions are gone.
The payout is called through `API.paySilver`, the same function the finish line calls: finishing a
tournament in second place is a whole race, which measures the race and not the prize.

WHAT IT CANNOT SEE: whether metallic reads as metallic and pearl as pearl on a phone. The owner's call.

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
print('prize-test  .  silver pays a paint set')
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
            notes: [...document.querySelectorAll('#veil .gnote')].map(n => n.textContent) })""")

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
    errs = pg.evaluate("() => window.__probe.errors")
    check(not errs, 'no page errors', '; '.join(errs[:2]))
    b.close()
print()
print('  %s' % ('all checks passed' if not fails else '%d check(s) FAILED' % len(fails)))
sys.exit(1 if fails else 0)
