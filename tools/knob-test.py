#!/usr/bin/env python3
"""KNOB TEST - a working car has a working gear knob, in both games.

    .venv/Scripts/python tools/knob-test.py
    .venv/Scripts/python tools/knob-test.py --falsify knob
    .venv/Scripts/python tools/knob-test.py --falsify circuit

RLG-069, owner 2026-08-30: *"I also want production and utility vehicles to have a black leather or
plastic shifter with white text on it."* Two things were wrong with that on 2026-09-12 and they are
different faults with the same symptom.

  . `WORK_BODIES` named six bodies and the fleet has eight working ones. The AMBULANCE was added
    after the list was written, the HATCH after that, and neither was ever put in it.
  . ONLY INTERSTATE CARRIED THE STYLE. `road.js` toggles `body.workknob` in both games because it
    does not know which one is running, and Motorsport had no rule for the class. That was harmless
    until RLG-213 made production a RACE class: a SALOON can enter a circuit now, and it arrived
    holding a polished ball while the same car on the interstate held a moulded one.

WHAT IS MEASURED IS THE RENDERED KNOB. Asserting that AMBULANCE is in `WORK_BODIES` would test the
fix against a copy of itself, and asking the page whether `body.workknob` is set would test the
class name rather than the control the player sees. So this sets each body through `API.setBody`
and reads the computed style off `#knob`.

THE ORACLE IS `BODY_CLASS`, WHICH THIS CHECK NEVER WRITES. A body whose class is `production` or
`traffic` is a working vehicle and must show the working knob; everything else keeps the polished
ball. `WORK_BODIES` is a separate hand-written list in the engine, and the day the two disagree this
fails - which is the guard that lets the engine keep its own list while the fleet is classified
properly.

  1. THE TWO FINISHES ARE DIFFERENT, in each game, read off a VAN and a STALLION. Without this
     every other question passes on a cabinet that has no working-knob rule at all, which is exactly
     the state Motorsport was in.
  2. EVERY BODY SHOWS THE FINISH ITS CLASS DEMANDS, in each game, for all of them.

`--falsify knob` serves the engine with the HATCH and the AMBULANCE struck back out of
`WORK_BODIES`; question 2 must fail for those two in both games. `--falsify circuit` deletes the
`body.workknob` rule out of Motorsport's live stylesheet; question 1 must fail there and pass on the
interstate.

Exit code 0 if every check passed, 1 otherwise.
"""
import argparse
import functools
import http.server
import importlib.util
import socketserver
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from harness import console_utf8, launch_chromium, boot   # noqa: E402
from playwright.sync_api import sync_playwright            # noqa: E402

GAMES = [('interstate', 'games/sw/interstate.html'),
         ('motorsport', 'games/sw/motorsport.html')]

# the classes whose cars are driven rather than raced. Named here because this is the ORACLE - the
# owner's ruling in the test's own words - and not because the engine keeps a list of the same shape.
# PRODUCTION IS IN IT ON PURPOSE (owner, 2026-09-12, confirmed): the working wheel and the working
# knob cover production as well as utility, so this pair is not the same set as the `utility` class.
WORK_CLASSES = ('production', 'utility')

PROBE = r"""() => {
  const R = window.__road;
  const knob = document.getElementById('knob');
  if (!knob) return { err: 'no #knob on this cabinet' };
  /* every GARAGE body, taken from the engine rather than from a list in the harness. The traffic
     kinds are lowercase and are not bodies the player is ever sat in, so they are dropped. */
  const keys = [...new Set(R.fleet().map(v => v.key).filter(k => /^[A-Z]+$/.test(k)))].sort();
  const was = R.body();
  const read = (k) => {
    R.setBody(k);
    const cs = getComputedStyle(knob);
    const b = knob.querySelector('b');
    /* the finish is the gradient plus the colour of the number on it - the two things the rule
       changes. Joined into one string so a comparison is one comparison. */
    return cs.backgroundImage + ' | ' + cs.borderColor + ' | ' + (b ? getComputedStyle(b).color : '');
  };
  const out = {};
  for (const k of keys) out[k] = { finish: read(k), cls: R.bodyClass(k) };
  R.setBody(was);
  return { keys: keys, faces: out };
}"""

# `--falsify circuit` only. Deletes every rule that carries the working-knob class out of the live
# document, which is the state Motorsport was in before this unit. Returns how many it removed, so
# a falsifier that quietly matched nothing cannot be mistaken for a defect that failed to reproduce.
DROP_RULE = r"""() => {
  let n = 0;
  for (const sh of Array.from(document.styleSheets)) {
    let rules;
    try { rules = sh.cssRules; } catch (e) { continue; }
    if (!rules) continue;
    for (let i = rules.length - 1; i >= 0; i--) {
      const sel = rules[i].selectorText || '';
      if (sel.indexOf('.workknob') >= 0) { sh.deleteRule(i); n++; }
    }
  }
  return n;
}"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--falsify', choices=['knob', 'circuit'],
                    help='put one of the two defects back and watch the matching question fail')
    args = ap.parse_args()
    console_utf8()

    dt_path = ROOT / 'tools' / 'drive-test.py'
    spec = importlib.util.spec_from_file_location('dt', dt_path)
    dt = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dt)

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
    srv = socketserver.TCPServer(('127.0.0.1', 0), handler)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    bad = 0

    def ok(cond, label, detail=''):
        nonlocal bad
        if not cond:
            bad += 1
        print('  %s  %s%s' % ('ok  ' if cond else 'FAIL', label,
                              ('   ' + detail) if detail else ''))

    print('knob-test  .  a working car has a working knob, in both games')
    if args.falsify == 'knob':
        print('  FALSIFY: HATCH and AMBULANCE are served out of WORK_BODIES. Question 2 must fail.')
    if args.falsify == 'circuit':
        print('  FALSIFY: the workknob rule is deleted from Motorsport. Question 1 must fail there.')
    try:
        with sync_playwright() as p:
            b = launch_chromium(p, headless=True, args=['--mute-audio'])
            for gid, path in GAMES:
                ctx = b.new_context(viewport={'width': 480, 'height': 900})
                ctx.add_init_script(dt.INIT)
                if args.falsify == 'knob':
                    # the defect, struck out of the ENGINE's list rather than out of this file's
                    # idea of one, so the check meets the build it would have met before the fix.
                    src = (ROOT / 'road.js').read_text(encoding='utf-8')
                    need = "const WORK_BODIES = ['COUPE','SALOON','HATCH','CAB','PICKUP','VAN','SEMI','AMBULANCE'];"
                    if need not in src:
                        raise SystemExit('[knob-test] --falsify knob cannot find the line it rewrites')
                    src = src.replace(need, "const WORK_BODIES = ['COUPE','SALOON','CAB','PICKUP','VAN','SEMI'];", 1)
                    ctx.route('**/road.js', lambda route: route.fulfill(
                        status=200, content_type='application/javascript', body=src))
                pg = ctx.new_page()
                errs = []
                pg.on('pageerror', lambda e: errs.append(str(e)))
                boot(pg, 'http://127.0.0.1:%d/%s' % (port, path))
                pg.wait_for_timeout(1600)
                if args.falsify == 'circuit' and gid == 'motorsport':
                    # THE RULE IS DELETED FROM THE LIVE DOCUMENT rather than served out of the
                    # file. Rewriting the cabinet over the network was the first attempt and the
                    # navigation hung: a cabinet registers a service worker, so the page HTML is
                    # not reliably a request Playwright gets to answer. Deleting the real rule out
                    # of the real stylesheet needs no network and puts the page in exactly the
                    # state it was in before the fix.
                    gone = pg.evaluate(DROP_RULE)
                    if not gone:
                        raise SystemExit('[knob-test] --falsify circuit found no workknob rule to remove')
                pg.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=10000)
                pg.click('[data-act="play"]')
                pg.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5000)
                pg.click('[data-act="drive"]')
                pg.wait_for_timeout(1500)

                r = pg.evaluate(PROBE)
                print('  %s' % gid)
                if r.get('err') or not r.get('keys'):
                    ok(False, '  %-10s no knob to read' % gid, r.get('err', ''))
                    ctx.close()
                    continue
                faces = r['faces']
                work = faces.get('VAN', {}).get('finish')
                play = faces.get('STALLION', {}).get('finish')
                # 1. the cabinet has two finishes at all
                ok(bool(work) and bool(play) and work != play,
                   '  the working finish and the polished one differ',
                   '' if work != play
                   else 'both read the same - this cabinet has no working-knob rule')
                # 2. every body wears the finish its class demands
                wrong = []
                for k in r['keys']:
                    f = faces[k]
                    want = work if f['cls'] in WORK_CLASSES else play
                    if f['finish'] != want:
                        wrong.append('%s(%s)' % (k, f['cls']))
                ok(not wrong,
                   '  all %d bodies match their class  [oracle: BODY_CLASS]' % len(r['keys']),
                   '' if not wrong else 'wrong finish on ' + ', '.join(wrong))
                if errs:
                    ok(False, '  %s page errors' % gid, errs[0][:140])
                ctx.close()
            b.close()
    finally:
        srv.shutdown()

    print('  %s' % ('all checks passed' if not bad else '%d check(s) FAILED' % bad))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
