"""AN AMBULANCE DOES NOT WAIL LIKE A POLICE CAR.

    .venv/Scripts/python tools/siren-test.py

Owner, 2026-09-05: "I think the ambulance should have a different sounding siren to the
police." There is ONE siren voice in the engine and two things can ask for it - the bar on
your own roof, and police closing on you - so this checks both that the two vehicles sound
different and that the right one wins when both are sounding.

A SOUND CHECK CANNOT LISTEN, BUT IT CAN READ THE GRAPH. RLG-065 is the standing lesson here
and it cost three attempts: counting rebuild calls read zero on a FIXED build, and reading a
held layer's gain read a healthy 0.13 on a BROKEN one. What works is asking the live node
what it is set to. So this samples `snd.siren.osc.frequency.value` and
`snd.siren.filter.frequency.value` - the oscillator and the filter themselves, after
`setTargetAtTime` has ramped them - rather than reading the table those values were set
from. A check that reads the table agrees with the table and proves nothing.

THE ONE THING THAT CHANGES BETWEEN THE TWO SAMPLES IS THE BODY. Nothing else is touched -
same road, same run, same bar switched on the same way - so a difference in the sound can
only have come from the vehicle. That is the owner's actual requirement: "the ambulance just
has to have a different sounding siren no matter what", and "it has nothing to do with the
player driving or not". A siren belongs to the vehicle sounding it, the same way a class
describes the vehicle rather than who is holding the wheel.

WHAT IT CANNOT EXERCISE, and says so rather than implying otherwise: there is no NPC
ambulance today, so "no matter who drives it" cannot be tested by driving it two ways. What
IS tested is that the voice is looked up FROM THE BODY, which is what makes an NPC ambulance
sound right for free on the day one exists.

WHAT IT ASSERTS:
  1. The two vehicles occupy different pitch bands. A police wail runs 560-760; an
     ambulance yelp runs 700-980, so the ambulance's LOWEST tone is above the police
     car's lowest and its highest is above the police car's highest.
  2. The filter is brighter on the ambulance - 3200 against 2600. That one is a single
     settled number rather than an alternation, so it is the least ambiguous evidence
     that the vehicle changed the voice at all.
  3. The ambulance alternates FASTER. Sampling at a fixed interval, the yelp crosses
     between its two tones more often than the wail does.

Exit code 0 if every check passed, 1 otherwise.
"""
import sys, threading, http.server, socketserver, functools

from pathlib import Path as _P
ROOT = _P(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from harness import launch_chromium, console_utf8
from playwright.sync_api import sync_playwright
console_utf8()

h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
srv = socketserver.TCPServer(('127.0.0.1', 0), h)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()

bad = [0]


def check(ok, label, detail):
    print(f'  {"ok  " if ok else "FAIL"}  {label:<46} {detail}')
    if not ok:
        bad[0] += 1


SAMPLE = """async (body) => {
  const R = window.__road;
  R.setBody(body);
  R.setBar(true);
  const out = [];
  for (let i = 0; i < 90; i++) {
    await new Promise(r => setTimeout(r, 30));
    const s = R.sirenNow();
    if (s && s.freq) out.push({ f: +s.freq.toFixed(1), c: +s.cutoff.toFixed(0) });
  }
  R.setBar(false);
  return out;
}"""

with sync_playwright() as p:
    b = launch_chromium(p, headless=True,
                        args=['--mute-audio', '--autoplay-policy=no-user-gesture-required'])
    pg = b.new_context(viewport={'width': 480, 'height': 900}).new_page()
    errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.goto(f'http://127.0.0.1:{PORT}/games/sw/interstate.html', wait_until='load')
    pg.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
    pg.click('[data-act="play"]')
    pg.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
    # the siren only sounds on the road, and the audio graph only exists once a
    # gesture has started it - the click above is that gesture
    pg.click('[data-act="drive"]')
    pg.wait_for_timeout(1800)

    got = {}
    for k in ('CRUISER', 'AMBULANCE'):
        got[k] = pg.evaluate(SAMPLE, k)

    print()
    if not got['CRUISER'] or not got['AMBULANCE']:
        check(False, 'the siren sounds at all',
              f"cruiser {len(got['CRUISER'])} samples, "
              f"ambulance {len(got['AMBULANCE'])} - a silent graph proves nothing")
    else:
        def band(rows):
            fs = [r['f'] for r in rows]
            return min(fs), max(fs)

        def flips(rows):
            fs = [r['f'] for r in rows]
            mid = (min(fs) + max(fs)) / 2
            side = [f > mid for f in fs]
            return sum(1 for i in range(1, len(side)) if side[i] != side[i-1])

        clo, chi = band(got['CRUISER'])
        alo, ahi = band(got['AMBULANCE'])
        check(alo > clo and ahi > chi,
              'the ambulance sits in a higher band',
              f'police {clo:.0f}-{chi:.0f} Hz, ambulance {alo:.0f}-{ahi:.0f} Hz')

        cc = max(r['c'] for r in got['CRUISER'])
        ac = max(r['c'] for r in got['AMBULANCE'])
        check(ac > cc + 200,
              'and is brighter through the filter',
              f'police {cc:.0f} Hz cutoff, ambulance {ac:.0f}')

        cf, af = flips(got['CRUISER']), flips(got['AMBULANCE'])
        check(af > cf,
              'and alternates faster',
              f'police {cf} tone changes, ambulance {af}, over the same window')

    check(not errs, 'no page errors', errs[0] if errs else 'clean')
    pg.close()
    b.close()
srv.shutdown()
print()
print('  ' + ('an ambulance does not wail like a police car'
              if not bad[0] else f'{bad[0]} FAILURES'))
sys.exit(1 if bad[0] else 0)
