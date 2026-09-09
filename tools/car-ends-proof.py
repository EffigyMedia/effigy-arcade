#!/usr/bin/env python3
"""CAR ENDS PROOF - proves that `car-ends-test.py` can still fail.

    .venv/Scripts/python tools/car-ends-proof.py

WHY THIS FILE EXISTS. RLG-184 brought all seventeen garage bodies into agreement and, in the same
pass, CHANGED THE CHECK: it used to mirror the front by reversing the column NUMBER, which samples
the two ends one pixel off centre and reported two identical drawings as 78.6 per cent apart. A
green run from a check that was edited in the same commit as the code it checks proves nothing on
its own. Four guards in this project's own constraint list once passed with the bug present.

WHAT IT DOES. It puts a real defect back - the door mirrors declared for both ends of a supercar,
called from the tail only, which is exactly the shape of fault RLG-184 was about - runs the check
and REQUIRES IT TO FAIL. Then it restores the file and requires the check to pass again.

WHY IT CANNOT PASS FALSELY. If the edit does not apply, the run under test passes and this proof
reports failure. If the check has been weakened into something that cannot fail, the first run
passes and this proof reports failure. If the restore is wrong, the second run fails and this proof
reports failure. There is no path through it that reports success without the check having caught a
defect it was blind to a moment earlier.

Exit code 0 if the check is sound, 1 otherwise. It edits `road.js` and puts it back; it refuses to
run if the file is not the committed one, so an interrupted run can never lose work.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROAD = ROOT / 'road.js'
CHECK = ROOT / 'tools' / 'car-ends-test.py'

# the one call that puts a supercar's door mirrors on its tail. Removing it leaves the face drawing
# a pair of mirrors the tail has not got, which is the fault this ruling was about.
DEFECT = """    /* the door mirrors, which the tail never drew - see `carMirrors` */
    if(B) carMirrors(g, w, h, S, o);
"""


def run_check():
    r = subprocess.run([sys.executable, str(CHECK)], cwd=str(ROOT),
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    return r.returncode, (r.stdout or '') + (r.stderr or '')


def main():
    print('car-ends-proof  .  the shape check can still fail')

    # A PROOF THAT EDITS A FILE MUST NOT BE ABLE TO LOSE IT. If the working tree already differs
    # from the commit, an interrupted restore would leave uncommitted work destroyed - so it does
    # not start.
    dirty = subprocess.run(['git', 'diff', '--quiet', '--', 'road.js'], cwd=str(ROOT))
    if dirty.returncode != 0:
        print('  REFUSED  road.js has uncommitted changes; commit or stash them first')
        return 1

    original = ROAD.read_text(encoding='utf-8')
    if original.count(DEFECT) != 1:
        print('  FAIL  the call this proof removes is not in road.js exactly once')
        print('        the proof is stale - find what replaced it before trusting any green run')
        return 1

    bad = 0
    try:
        ROAD.write_text(original.replace(DEFECT, ''), encoding='utf-8', newline='')
        code, out = run_check()
        if code == 0:
            bad += 1
            print('  FAIL  the check PASSED with a one-ended shape in the fleet')
            print('        it is not measuring what it says it measures')
        else:
            hits = [ln.strip() for ln in out.splitlines() if 'DIFFERENT SHAPE' in ln]
            print('  ok    the check fails when a shape is drawn at one end only   %d body(s) caught'
                  % len(hits))
    finally:
        ROAD.write_text(original, encoding='utf-8', newline='')

    code, _ = run_check()
    if code != 0:
        bad += 1
        print('  FAIL  the check does not pass on the restored file')
    else:
        print('  ok    and it passes again once the shape is declared for both ends')

    print('  %s' % ('the check is sound' if not bad else '%d step(s) failed' % bad))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
