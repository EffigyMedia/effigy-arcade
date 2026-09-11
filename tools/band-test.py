"""Measure the rubber band in Interstate. It changes nothing.

RLG-029 asks one question: does the rubber band actually work? A rival that falls a long way
behind is supposed to get a tow, and a rival that gets a long way ahead is supposed to get a
governor. The complaint is that neither appears to happen.

THIS HARNESS MEASURES. IT DOES NOT TUNE. A change made on a guess cannot afterwards be told
apart from one made on a fact, so the numbers come first and the fragment records them before
anything in road.js moves.

HOW THE MEASUREMENT AVOIDS BEING VACUOUS
----------------------------------------
Reading `r.spd` while the band is switched on tells you what the rivals are doing. It does NOT
tell you that the band is what makes them do it - the same speeds could come from the skill
spread, from traffic, or from the `AI_TOP` ceiling. Four guards in this project's fix list
already passed with the bug present, so an uncontrolled reading is not evidence.

So the run happens TWICE, against the same scenario:

  band on    road.js exactly as it ships
  band off   road.js with `const band = clamp(...)` rewritten to `const band = 0`, IN THE
             SERVER, in memory. No game file is touched on disk.

If the band does what its comment claims, the two arms must differ. If they do not differ, the
band is inert and the measurement says so with a control behind it. The rewrite is asserted to
hit exactly one line; a control arm that silently patched nothing would be the vacuous proof
this file exists to avoid.

THE EXPERIMENT
--------------
Driving a race and waiting for a gap to open naturally does not reach the interesting part: the
band saturates at 1.27 miles of separation, and a 30-second run does not produce that. So the
initial condition is SET rather than waited for, and then HELD: three rivals are tagged once the
race has settled, and each is pinned to its lead on every tick so the band value it sees is a
constant this harness chose rather than a number that drifts differently in the two arms.

  behind   held two miles back   - the tow should be at full saturation
  ahead    held two miles up     - the governor should be at full saturation
  near     held a tenth back     - the reference, and the only one still inside traffic

Then their speed is sampled for the rest of the run. Speed, not the gap to the player: the
player's car is quicker than `AI_TOP` by twenty miles an hour, so the gap to a rival behind
grows whatever the band does, and reading the gap would report that as the band failing. What
the band controls is `want`, and what `want` controls is speed.
"""

import argparse
import functools
import http.server
import importlib.util
import re
import socketserver
import statistics
import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GAME = 'games/sw/interstate.html'
MPH = 200 / 15333          # MAX_SPD is 200mph, road.js:104


# --- find the interpreter that has Playwright --------------------------------
# Playwright lives in the project's own `.venv`, because it cannot be installed into the
# environment's uv-managed Python (PEP 668 refuses). That is fine when a person runs this from the
# project folder. It is NOT fine under `step.py`, which is how a measurement becomes evidence:
# `step.py` runs its command with the ENVIRONMENT root as cwd, and on Windows `CreateProcess`
# resolves a relative EXECUTABLE against the calling process's directory rather than against `cwd`.
# So `.venv/Scripts/python.exe` cannot be reached by any relative path from there, and an absolute
# one would put a drive letter into the evidence fragment, which `Path_Policy.md` forbids.
#
# The way out is for the harness to find its own interpreter. Run it with whatever Python is on
# PATH; if that Python has no Playwright, it hands over to the venv and gets out of the way.
#
# harness.py documents this same CreateProcess trap for `node`. It is the second time it has bitten.

def _handover():
    try:
        import playwright  # noqa: F401
        return
    except ImportError:
        pass
    for candidate in (ROOT / '.venv' / 'Scripts' / 'python.exe', ROOT / '.venv' / 'bin' / 'python'):
        if candidate.exists() and candidate.resolve() != Path(sys.executable).resolve():
            # stdio is inherited, so the parent's pipe sees the report exactly as it is written
            sys.exit(subprocess.run([str(candidate), str(Path(__file__).resolve())]
                                    + sys.argv[1:]).returncode)
    raise SystemExit(
        '[band-test] playwright is not importable and there is no project .venv to hand over to.\n'
        '            Build one: uv venv .venv, then uv pip install --python .venv playwright')


_handover()

from playwright.sync_api import sync_playwright   # noqa: E402

from harness import console_utf8, launch_chromium, boot, until  # noqa: E402


# --- the engine constants this harness depends on ----------------------------
# Read out of road.js rather than copied into it. A constant that drifted in the engine and not
# here would move every number this file prints, silently and in the same direction, which is
# the failure that looks most like a real result.

def engine_constants(src):
    def one(pattern, label):
        found = re.findall(pattern, src)
        if len(found) != 1:
            raise SystemExit('[band-test] expected exactly one %s in road.js, found %d. '
                             'The engine moved; read it before trusting this.'
                             % (label, len(found)))
        return found[0]

    mile = float(one(r'const MILE = 1 / ([0-9.]+);', 'MILE'))
    max_spd = float(one(r'const MAX_SPD = ([0-9]+);', 'MAX_SPD'))
    ai_num, ai_den = one(r'const AI_TOP = MAX_SPD \* \((\d+)/(\d+)\);', 'AI_TOP')
    return 1.0 / mile, max_spd, max_spd * (float(ai_num) / float(ai_den))


# --- the control arm ---------------------------------------------------------

BAND_LINE = 'const band = clamp(-lead * 0.11, -0.14, 0.14);'
BAND_OFF = 'const band = 0;'


def road_without_band(src):
    hits = src.count(BAND_LINE)
    if hits != 1:
        raise SystemExit('[band-test] the band line was found %d times in road.js, not once.\n'
                         '           Looked for: %s\n'
                         '           A control arm that patches nothing proves nothing, so this '
                         'stops rather than reporting two identical runs as a finding.'
                         % (hits, BAND_LINE))
    return src.replace(BAND_LINE, BAND_OFF)


def serve(root, band):
    """The folder, on a free port. With band False, road.js is rewritten on the way out."""
    src = (root / 'road.js').read_text(encoding='utf-8')
    patched = None if band else road_without_band(src).encode('utf-8')

    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            if patched is not None and self.path.split('?')[0].endswith('/road.js'):
                self.send_response(200)
                self.send_header('Content-Type', 'application/javascript')
                self.send_header('Content-Length', str(len(patched)))
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(patched)
                return
            super().do_GET()

    handler = functools.partial(Handler, directory=str(root))
    httpd = socketserver.TCPServer(('127.0.0.1', 0), handler)
    httpd.allow_reuse_address = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.socket.getsockname()[1]


# --- the autopilot, borrowed rather than copied ------------------------------
# drive-test.py owns the engine capture and the centre-seeking driver. Two copies of a driver
# drift apart, and the one that drifts is always the one nobody is reading.

def drive_test_module():
    path = Path(__file__).resolve().parent / 'drive-test.py'
    spec = importlib.util.spec_from_file_location('drive_test', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --- the sampler -------------------------------------------------------------

SAMPLER = r"""
(function(mile){
  var P = window.__probe, R = P.road;
  P.band = { rows: [], mile: mile, tagged: null };
  /* ---- THE GAP IS HELD, NOT WATCHED --------------------------------------
     Displacing a rival once and then reading its speed measures the band at a lead that drifts
     the whole time, and it drifts by different amounts in the two arms - which puts the
     independent variable on both sides of the comparison. So each tagged rival is PINNED to
     its lead on every tick. The band value it sees is then a constant that this harness chose,
     and its speed is the only thing left free to move.

     Pinning has a second effect worth stating, because it is doing real work: a rival held two
     miles from the player is in clean air, since traffic spawns around the player. That takes
     the `want = min(want, blocking car)` clamp out of the reading. The rival held at -0.10 is
     NOT in clean air, and it is kept for exactly that contrast.
     --------------------------------------------------------------------- */
  var PINS = { behind: -2.0, near: -0.10, ahead: +2.0 };
  /* The middle of the field by pace, so no tagged car sits at an end of the skill spread. */
  var live = R.racers.filter(function(r){ return !r.wreck; });
  if(live.length < 3) return false;
  live.sort(function(a, b){ return a.base - b.base; });
  var m = (live.length / 2) | 0;
  live[m - 1].__tag = 'behind';
  live[m].__tag     = 'near';
  live[m + 1].__tag = 'ahead';
  P.band.tagged = [live[m - 1], live[m], live[m + 1]].map(function(r){
    return { tag: r.__tag, base: r.base, vmax: r.vmax, body: r.body };
  });
  P.band.timer = setInterval(function(){
    R.racers.forEach(function(r){
      if(!r.__tag) return;
      P.band.rows.push({ tag: r.__tag, lead: (r.z - R.pos) / mile, spd: r.spd, base: r.base,
                         wreck: r.wreck > 0 ? 1 : 0, pspd: R.spd });
      r.z = R.pos + PINS[r.__tag] * mile;     /* pinned AFTER the reading, never before */
    });
  }, 100);
  return true;
})
"""


# ---- the same race twice -----------------------------------------------------
# The first version of this harness compared two DIFFERENT races: the grid, the paints and the
# traffic are all drawn from Math.random, so the arms differed by more than the band and the
# report said the tow made a rival ELEVEN MPH SLOWER. That was two grids, not an effect.
#
# Seeding Math.random before any game script runs makes the two arms the same race. The seed is
# the harness's, not the engine's, so nothing in road.js knows it is being measured.

SEED_RNG = r"""
(function(){
  var s = 0x9E3779B9;
  Math.random = function(){
    s |= 0; s = (s + 0x6D2B79F5) | 0;
    var t = Math.imul(s ^ (s >>> 15), 1 | s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
})();
"""


def run_arm(browser, base_url, seconds, settle, mile, label):
    dt = drive_test_module()
    ctx = browser.new_context(viewport={'width': 480, 'height': 900})
    ctx.add_init_script(SEED_RNG)
    ctx.add_init_script(dt.INIT)
    page = ctx.new_page()
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    try:
        boot(page, base_url + '/' + GAME)
        # the first visit reloads itself when the service worker claims the page; wait it out
        try:
            until(page, '() => navigator.serviceWorker && navigator.serviceWorker.controller',
                timeout=5_000)
            page.wait_for_timeout(1_200)
        except Exception:
            pass
        until(page, '!!window.__probe.road', timeout=10_000)

        page.click('[data-act="play"]')
        page.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=5_000)
        # one press of the three-state control turns TEST DRIVE into SINGLE RACE
        page.click('[data-act="mode"]')
        page.wait_for_timeout(150)
        page.click('[data-act="drive"]')
        page.wait_for_timeout(400)
        page.evaluate('() => window.__probe.drive()')

        # let the field find its pace before the initial condition is set
        page.wait_for_timeout(int(settle * 1000))
        if page.evaluate('() => window.__probe.road.racers.length') == 0:
            raise SystemExit('[band-test] no rivals - the race did not start, so there is '
                             'nothing to measure. The garage control may have moved.')
        if not page.evaluate(SAMPLER + '(%r)' % mile):
            raise SystemExit('[band-test] fewer than three rivals were healthy at the settle '
                             'point; the run is not comparable and is not reported.')
        page.wait_for_timeout(int(seconds * 1000))

        rows = page.evaluate('() => window.__probe.band.rows')
        tagged = page.evaluate('() => window.__probe.band.tagged')
        page.evaluate('() => { clearInterval(window.__probe.band.timer); '
                      'window.__probe.stop(); }')
        errors += page.evaluate('() => window.__probe.errors')
        return {'label': label, 'rows': rows, 'tagged': tagged, 'errors': errors}
    finally:
        ctx.close()


# --- the arithmetic ----------------------------------------------------------

def summarise(arm, ai_top):
    """Per tag: how fast it ran, against its own base and against the ceiling."""
    out = {}
    for tag in ('behind', 'near', 'ahead'):
        rows = [r for r in arm['rows'] if r['tag'] == tag and not r['wreck']]
        if not rows:
            out[tag] = None
            continue
        base = statistics.fmean(r['base'] for r in rows)
        # ---- these two columns are OBSERVATIONS, not interpretations ---------
        # An earlier version reported "at cap" against a flat AI_TOP and a "headroom" that
        # assumed the engine caps `want` at AI_TOP after the band. Both were true of the engine
        # on the day they were written, and both went false the moment the cap was changed - so
        # the report kept printing a confident explanation of a mechanism that had gone. What a
        # harness may state is what it saw: how fast the car went, against its own `base` and
        # against the flat 180mph figure. Why it went that fast belongs to whoever reads it.
        out[tag] = {
            'n': len(rows),
            'spd': statistics.fmean(r['spd'] for r in rows),
            'base': base,
            'ratio': statistics.fmean(r['spd'] / r['base'] for r in rows),
            'lead': statistics.fmean(r['lead'] for r in rows),
            'over_top': sum(1 for r in rows if r['spd'] > ai_top * 1.005) / len(rows),
            'base_top': base / ai_top,
        }
    out['player'] = statistics.fmean(r['pspd'] for r in arm['rows']) if arm['rows'] else 0.0
    return out


ROW = '    {:<9} {:>7} {:>10} {:>9} {:>10} {:>9} {:>10}'


def main():
    console_utf8()
    ap = argparse.ArgumentParser()
    ap.add_argument('--seconds', type=float, default=25.0, help='sampling window per arm')
    ap.add_argument('--settle', type=float, default=6.0, help='racing before the gap is set')
    ap.add_argument('--repeats', type=int, default=3, help='paired runs; one is not a result')
    ap.add_argument('--headed', action='store_true')
    args = ap.parse_args()

    src = (ROOT / 'road.js').read_text(encoding='utf-8')
    mile, max_spd, ai_top = engine_constants(src)
    # fail before a browser is launched if the control arm cannot be built
    road_without_band(src)

    print('band-test  -  RLG-029  -  %gs per arm after a %gs settle' % (args.seconds, args.settle))
    print(f'  MILE {mile:,.0f} units  -  MAX_SPD {max_spd:,.0f} ({max_spd * MPH:.0f}mph)'
          f'  -  AI_TOP {ai_top:,.0f} ({ai_top * MPH:.0f}mph)')

    # ---- paired runs --------------------------------------------------------
    # ONE PAIR IS NOT A RESULT. The rival held at -0.10 is inside traffic, and traffic is the
    # loudest thing on this road: the first pair this harness ever ran reported that tag at
    # -23%, which no 1.1% tow can produce. Repeats separate the effect from the weather.
    pairs = []
    with sync_playwright() as p:
        browser = launch_chromium(
            p, headless=not args.headed,
            args=['--autoplay-policy=no-user-gesture-required', '--mute-audio'])
        for i in range(args.repeats):
            pair = {}
            for band, label in ((True, 'band on'), (False, 'band off')):
                httpd, port = serve(ROOT, band)
                try:
                    arm = run_arm(browser, 'http://127.0.0.1:%d' % port,
                                  args.seconds, args.settle, mile, label)
                finally:
                    httpd.shutdown()
                arm['summary'] = summarise(arm, ai_top)
                pair[label] = arm
            pairs.append(pair)
            print('  pair %d of %d done' % (i + 1, args.repeats))
        browser.close()

    print()
    for label in ('band on', 'band off'):
        print('  ' + label.upper() + '   (mean of %d runs)' % len(pairs))
        errs = [e for pr in pairs for e in pr[label]['errors']]
        if errs:
            print('    page errors: ' + errs[0][:110])
        print('    player averaged %.1f mph'
              % (statistics.fmean(pr[label]['summary']['player'] for pr in pairs) * MPH))
        print(ROW.format('tag', 'samples', 'lead(mi)', 'mph', 'spd/base', 'over 180', 'base/180'))
        for tag in ('behind', 'near', 'ahead'):
            vs = [pr[label]['summary'][tag] for pr in pairs if pr[label]['summary'][tag]]
            if not vs:
                print(ROW.format(tag, 0, '-', '-', '-', '-', '-'))
                continue
            avg = lambda k: statistics.fmean(v[k] for v in vs)
            print(ROW.format(tag, sum(v['n'] for v in vs), '%+.2f' % avg('lead'),
                             '%.1f' % (avg('spd') * MPH), '%.3f' % avg('ratio'),
                             '%.0f%%' % (avg('over_top') * 100), '%.3f' % avg('base_top')))
        print()

    print('  THE ANSWER  -  what the band changes, band on minus band off')
    print('    %-9s %10s   %s' % ('tag', 'mean', 'per-run spread'))
    for tag in ('behind', 'near', 'ahead'):
        deltas = []
        for pr in pairs:
            on, off = pr['band on']['summary'][tag], pr['band off']['summary'][tag]
            if on and off:
                deltas.append((on['spd'] / off['spd'] - 1) * 100)
        if not deltas:
            print('    %-9s not measured' % tag)
            continue
        print('    %-9s %+9.2f%%   %s' % (tag, statistics.fmean(deltas),
                                          ', '.join('%+.2f%%' % d for d in deltas)))
    print()
    print('  The band claims up to 14 percent either way. A difference near zero means it is')
    print('  inert, and the control arm above proves the measurement can see a difference.')
    print()
    print('  OVER 180 is the share of samples above AI_TOP, the flat ceiling a rival used to be')
    print('  held to whatever the band said. BASE/180 is the pace the car would ask for with no')
    print('  band at all, against that same figure - above 1.000 means the flat ceiling binds')
    print('  the car before the band is even considered. Both are readings, not explanations:')
    print('  what the engine does with them is for the reader of this report to say.')
    print()
    print('  The middle row is held inside traffic, where the blocking-car clamp sets the speed')
    print('  rather than the band. Read its spread before reading its mean.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
