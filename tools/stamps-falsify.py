#!/usr/bin/env python3
"""
STAMPS FALSIFY - the stamp checks fail when the stamps disagree (RLG-245).

`window.ROAD_BUILD` in road.js and `A.version` in arcade.js must agree, or
`Arcade.buildTag()` prints MIXED on every device. Three checks guard it:
the `stamps` row in smoke-test.py, the "build tag is not MIXED" check inside
each smoke cabinet, and a gate in `pack.sh --check`. A check that has never
been seen to fail is not evidence, so this builds a throwaway copy of the
product, drifts the stamps in it, and watches each check fail.

    .venv/Scripts/python tools/stamps-falsify.py           static checks only
    .venv/Scripts/python tools/stamps-falsify.py --browser also the page check

Exit 0 when every check passes on agreement AND fails on disagreement.

WHAT THIS CANNOT CHECK: it does not prove a real device shows MIXED for a
real stale cache. That is the service worker's behavior, and no harness
here reproduces a half-cached pair of scripts.
"""

import argparse
import importlib.util
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

fails = []


def check(label, cond, detail=''):
    print(f"{'PASS' if cond else 'FAIL'}  {label}" + (f"  [{detail}]" if detail and not cond else ''))
    if not cond:
        fails.append(label)


def sandbox():
    """Copy the tracked product into a temp root. docs/ is left out: nothing
    under test reads it, and it is most of the tree's weight."""
    sb = Path(tempfile.mkdtemp(prefix='stamps-falsify-'))
    files = subprocess.run(['git', 'ls-files'], cwd=ROOT, capture_output=True,
                           text=True, check=True).stdout.splitlines()
    for f in files:
        if f.startswith('docs/') or not (ROOT / f).is_file():
            continue
        (sb / f).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / f, sb / f)
    return sb


def restamp(sb, file, pattern, value):
    p = sb / file
    text = p.read_text(encoding='utf-8')
    new, n = re.subn(pattern, lambda m: m.group(1) + value + m.group(2), text, count=1, flags=re.M)
    assert n == 1, f'{file}: stamp line not found'
    p.write_text(new, encoding='utf-8')


def stamps_in(sb):
    spec = importlib.util.spec_from_file_location('smoke_' + sb.name, sb / 'tools' / 'smoke-test.py')
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(sb / 'tools'))   # smoke-test imports its sibling harness.py
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.path.pop(0)
    return mod.stamps(sb)


def pack_check(sb):
    bash = shutil.which('bash') or 'bash'
    r = subprocess.run([bash, './pack.sh', '--check'], cwd=sb, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def tree_state(sb):
    return {p.relative_to(sb).as_posix(): p.stat().st_mtime_ns
            for p in sb.rglob('*') if p.is_file() and '__pycache__' not in p.parts}


ROAD = (r"^(window\.ROAD_BUILD = ')[^']*(';)", 'road.js')
SHELL = (r"^(A\.version = ')[^']*(';)", 'arcade.js')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--browser', action='store_true')
    args = ap.parse_args()

    sb = sandbox()
    try:
        # ---- 1. AGREEMENT: every check passes on the real stamps -----------
        bad = [c for c in stamps_in(sb) if not c[0]]
        check('stamps() passes when the stamps agree', not bad, bad)
        before = tree_state(sb)
        code, out = pack_check(sb)
        check('pack.sh --check exits 0 when the stamps agree', code == 0, out[-300:])
        # --check builds nothing; a gate that wrote files would dirty a tree.
        check('pack.sh --check wrote nothing', tree_state(sb) == before)

        # ---- 2. THE ENGINE LAGS: the drift that actually shipped -----------
        restamp(sb, ROAD[1], ROAD[0], '0.13.70')
        res = stamps_in(sb)
        bad = [c for c in res if not c[0]]
        check('stamps() fails when road.js lags', len(bad) == 1 and 'ROAD_BUILD' in bad[0][1],
              res)
        check('stamps() names both versions', bad and '0.13.70' in bad[0][2], bad)
        code, out = pack_check(sb)
        check('pack.sh --check exits non-zero when road.js lags', code != 0, out[-300:])
        # The negative: it must fail ON THE STAMPS, not on some other gate.
        check('pack.sh refuses because of the stamps', 'ROAD_BUILD 0.13.70' in out, out[-300:])

        # ---- 3. THE SHELL LAGS: the other direction ------------------------
        restamp(sb, ROAD[1], ROAD[0], '9.9.9')
        restamp(sb, SHELL[1], SHELL[0], '9.9.8')
        check('stamps() fails when arcade.js lags', any(not c[0] for c in stamps_in(sb)))
        code, out = pack_check(sb)
        check('pack.sh --check fails when arcade.js lags', code != 0 and 'arcade.js is 9.9.8' in out,
              out[-300:])

        # ---- 4. A STAMP LINE REMOVED: a missing line is not agreement ------
        restamp(sb, SHELL[1], SHELL[0], '9.9.9')
        p = sb / 'road.js'
        p.write_text(re.sub(r"^window\.ROAD_BUILD = .*$", '', p.read_text(encoding='utf-8'),
                            count=1, flags=re.M), encoding='utf-8')
        check('stamps() fails when road.js has no stamp', any(not c[0] for c in stamps_in(sb)))
        code, out = pack_check(sb)
        check('pack.sh --check fails when road.js has no stamp',
              code != 0 and 'no window.ROAD_BUILD' in out, out[-300:])

        # ---- 5. THE PAGE: a drifted engine makes smoke report MIXED --------
        if args.browser:
            restamp_line = "window.ROAD_BUILD = '0.13.70';\n"
            text = p.read_text(encoding='utf-8')
            p.write_text(restamp_line + text, encoding='utf-8')
            restamp(sb, SHELL[1], SHELL[0], '0.13.84')
            r = subprocess.run([sys.executable, 'tools/smoke-test.py', 'interstate',
                                '--seconds', '1'], cwd=sb, capture_output=True, text=True)
            out = r.stdout + r.stderr
            check('smoke-test exits non-zero on a drifted page', r.returncode != 0, out[-400:])
            check('smoke flags the stamps row', re.search(r'FAIL\s+stamps', out), out[-400:])
            check('smoke flags the MIXED build tag in the cabinet',
                  'the build tag is not MIXED (BUILD 0.13.84 / ROAD 0.13.70 - MIXED)' in out,
                  out[-400:])
    finally:
        shutil.rmtree(sb, ignore_errors=True)

    print(f"\n{len(fails)} failure(s)" + (': ' + ', '.join(fails) if fails else ''))
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
