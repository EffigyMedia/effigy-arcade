"""Unwire the indicator and prove traffic-test notices.

RLG-052's whole history is that `c.blink` was set on every merge decision for
months and no renderer ever read it, so the feature was invisible while every
check about it passed. The check that catches that has to watch the SCREEN, and
it has to be shown failing when the screen stops showing it.

THIS SCRIPT EXITS 0 ONLY IF THE GUARD FIRES. It deletes the one line that paints
a traffic car's indicator - putting the engine back in exactly the state RLG-052
was raised about - runs traffic-test, and requires that the amber line FAILS.

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
BACKUP = ROOT / 'road.js.amber-backup'

GOOD = ("      if(it.o.blink > 0 && box && box.w >= 10 && Math.sin(blinkPhase) > 0)\n"
        "        lampsLit(box, img, [it.o.blinkDir < 0 ? 'turn.l' : 'turn.r'], 1, 2);\n")
BAD = ("      if(false && it.o.blink > 0 && box && box.w >= 10 && Math.sin(blinkPhase) > 0)\n"
       "        lampsLit(box, img, [it.o.blinkDir < 0 ? 'turn.l' : 'turn.r'], 1, 2);\n")
# the one check that must catch it, named so a rename cannot silently pass this
GUARD = 'an indicating car puts amber on the screen'
# and the two lines that say the measurement was taken in a scene worth taking it
# in. If either of those fails instead, the amber line failed for the wrong reason.
SETUP = ('four cars could be put across the road for the shot',
         'and the scene held still while the shot was taken')


def main():
    src = ROAD.read_text(encoding='utf-8')
    if src.count(GOOD) != 1:
        print('ABORT: the indicator painter is not in the shape this proof knows how to break.')
        print('       The proof is stale, not the engine. Read it before trusting either.')
        return 2
    shutil.copyfile(ROAD, BACKUP)
    try:
        ROAD.write_text(src.replace(GOOD, BAD), encoding='utf-8')
        print('DEFECT IN: nothing paints a traffic indicator, which is RLG-052 before it was fixed.')
        r = subprocess.run([str(PY_), 'tools/traffic-test.py'], cwd=str(ROOT),
                           capture_output=True, text=True)
        out = r.stdout + r.stderr
        lines = [ln.strip() for ln in out.splitlines()]
        failed = [ln for ln in lines if ln.startswith('FAIL')]
        print('traffic-test exit %d, %d check(s) failed' % (r.returncode, len(failed)))
        for ln in failed:
            print('   ' + ln)
        if not any(GUARD in ln for ln in failed):
            print()
            print('VACUOUS: the amber line did not fail on an engine that draws no indicator.')
            print('         Whatever it is measuring, it is not the indicator.')
            return 1
        for s in SETUP:
            if not any(ln.startswith('ok') and s in ln for ln in lines):
                print()
                print('WRONG REASON: the shot itself did not set up, so the amber line failing')
                print('              proves nothing about the indicator. Missing: ' + s)
                return 1
        print()
        print('PROVED: the amber line fires when nothing paints the indicator, and the')
        print('        scene it measures in was still and staged while it did.')
        return 0
    finally:
        shutil.copyfile(BACKUP, ROAD)
        os.remove(BACKUP)
        print('RESTORED: road.js is back to the committed build.')


sys.exit(main())
