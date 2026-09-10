"""Close the road on purpose and prove traffic-test says so, and says WHERE.

The corridor line is stochastic: measured over twenty-four runs, the road closes
on about one run in three, so watching the real harness come out green proves
nothing at all about the check. It has to be forced.

THIS SCRIPT EXITS 0 ONLY IF THE GUARD FIRES. It raises the engine's car-width
limit from 0.34 lane units to 0.90 - wider than any corridor ordinary traffic
leaves - so every road counts as closed, runs traffic-test, and requires that
the run FAILS on the corridor line and that the failure names a distance up the
road. A closure reported without a distance cannot be told from a transient
twenty thousand units away, which is the whole reason the distance is carried.

It restores road.js on every path, including on its own failure.
"""
import shutil, subprocess, sys, os
from pathlib import Path

# the project root is two levels up from this file, the way every other harness
# here finds it. An absolute path written into a tracked file breaks the next
# time the environment moves - see Path_Policy.md.
ROOT = Path(__file__).resolve().parent.parent
ROAD = ROOT / 'road.js'
PY_ = ROOT / '.venv' / 'Scripts' / 'python.exe'
if not PY_.exists():
    PY_ = ROOT / '.venv' / 'bin' / 'python'
BACKUP = ROOT / 'road.js.corridor-backup'

GOOD = 'const NEED = 0.34;'
BAD = 'const NEED = 0.90;'
# the one check that must catch it, named so a rename cannot silently pass this
GUARD = 'this road never closed to a car in front of the player'


def main():
    src = ROAD.read_text(encoding='utf-8')
    if src.count(GOOD) != 1:
        print('ABORT: the car-width limit is not written the way this proof expects.')
        print('       The proof is stale, not the engine. Read it before trusting either.')
        return 2
    shutil.copyfile(ROAD, BACKUP)
    try:
        ROAD.write_text(src.replace(GOOD, BAD), encoding='utf-8')
        print('DEFECT IN: a car now needs 0.90 lane units to pass, which no road gives it.')
        r = subprocess.run([str(PY_), 'tools/traffic-test.py'], cwd=str(ROOT),
                           capture_output=True, text=True)
        out = r.stdout + r.stderr
        failed = [ln.strip() for ln in out.splitlines() if ln.strip().startswith('FAIL')]
        print('traffic-test exit %d, %d check(s) failed' % (r.returncode, len(failed)))
        for ln in failed:
            print('   ' + ln)
        if r.returncode == 0:
            print()
            print('VACUOUS: traffic-test PASSED on a road no car could get through.')
            return 1
        line = next((ln for ln in failed if GUARD in ln), None)
        if line is None:
            print()
            print('WRONG GUARD: traffic-test failed, but not on the corridor line.')
            print('             Something else broke; that is not proof of this one.')
            return 1
        # AND IT HAS TO SAY WHERE. A distance up the road is what separates a wall
        # the player is about to hit from a corridor that has two seconds to open,
        # and the old line carried neither.
        if 'nearest closure' not in line or 'units ahead' not in line:
            print()
            print('NO DISTANCE: the corridor line failed without saying where the road')
            print('             closed, which is half of what the failure has to report.')
            return 1
        print()
        print('PROVED: the corridor line fires on a closed road, and it names the distance.')
        return 0
    finally:
        shutil.copyfile(BACKUP, ROAD)
        os.remove(BACKUP)
        print('RESTORED: road.js is back to the committed build.')


sys.exit(main())
