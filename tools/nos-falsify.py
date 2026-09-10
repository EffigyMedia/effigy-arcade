"""Break the bottle two ways and prove drive-test says so rather than passing.

The nitrous block had a line reading `nosOn` back to prove the button worked -
after `holdNos(true)` had already set `nosOn` itself. It could not fail, and the
message written under it for the failure case, "the nitrous button did not take,
so nothing below is about the bottle", was printed on the PASS. Four assertions
under it then reported numbers about a bottle nobody had opened.

TWO ARMS, AND BOTH MUST BE CAUGHT.
  BUTTON  the control is unwired, so pressing `#nitro` does nothing. The button
          line must FAIL. Everything under it still measures, because `holdNos`
          opens the bottle for the measurement on purpose.
  BOTTLE  `holdNos` is made to refuse. The three checks that depend on an open
          bottle must come out BLOCKED - not passed, and not silently scored.

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
BACKUP = ROOT / 'road.js.nos-backup'

BUTTON_GOOD = ("nitroBtn.addEventListener('pointerdown',e=>{e.preventDefault(); "
               "if(hasNos() && nos>8){ nosOn=true; snd.nitro(); }});")
BUTTON_BAD = ("nitroBtn.addEventListener('pointerdown',e=>{e.preventDefault(); "
              "if(false && hasNos() && nos>8){ nosOn=true; snd.nitro(); }});")
HOLD_GOOD = "API.holdNos = function(v){ nosOn = !!v && hasNos(); return nosOn; };"
HOLD_BAD = "API.holdNos = function(v){ nosOn = false; return nosOn; };"

BUTTON_LINE = 'the nitrous button opens the bottle'
DEPENDENTS = ('and the bottle is the one thing that lifts the limiter',
              'and it lifts it by a tenth and no more',
              'so the car settles a tenth above its own top end')


def run():
    r = subprocess.run([str(PY_), 'tools/drive-test.py'], cwd=str(ROOT),
                       capture_output=True, text=True)
    return r.returncode, [ln.strip() for ln in (r.stdout + r.stderr).splitlines()]


def arm(name, good, bad, want):
    src = ROAD.read_text(encoding='utf-8')
    if src.count(good) != 1:
        print(f'ABORT [{name}]: the code is not in the shape this proof knows how to break.')
        print('       The proof is stale, not the engine. Read it before trusting either.')
        return 2
    ROAD.write_text(src.replace(good, bad), encoding='utf-8')
    print(f'DEFECT IN [{name}]')
    code, lines = run()
    ok = True
    for state, label in want:
        hit = [ln for ln in lines if ln.startswith(state) and label in ln]
        print(f'   {state:<4} {label}: {"seen" if hit else "NOT SEEN"}')
        if not hit:
            ok = False
    if code == 0:
        print(f'   VACUOUS [{name}]: drive-test exited 0 on a broken bottle.')
        ok = False
    return 0 if ok else 1


def main():
    shutil.copyfile(ROAD, BACKUP)
    try:
        bad = 0
        # ARM ONE - the button. Only the button line may fail: the measurement
        # below it is deliberately taken through `holdNos` and must still run.
        bad |= arm('BUTTON', BUTTON_GOOD, BUTTON_BAD,
                   [('FAIL', BUTTON_LINE)] + [('ok', d) for d in DEPENDENTS])
        shutil.copyfile(BACKUP, ROAD)
        # ARM TWO - the bottle. The BUTTON still works here and must still pass:
        # `holdNos` is what the measurement leans on, and it is a separate thing.
        # Everything that depends on the bottle staying open must come out BLOCKED
        # rather than passed, which is the whole point of the third state.
        bad |= arm('BOTTLE', HOLD_GOOD, HOLD_BAD,
                   [('ok', BUTTON_LINE)] + [('BLKD', d) for d in DEPENDENTS])
        print()
        if bad:
            print('NOT PROVED: read the arms above.')
            return 1
        print('PROVED: an unwired button fails the button line and nothing else, and a')
        print('        bottle that will not open BLOCKS the three checks that need it')
        print('        instead of scoring them.')
        return 0
    finally:
        shutil.copyfile(BACKUP, ROAD)
        os.remove(BACKUP)
        print('RESTORED: road.js is back to the committed build.')


sys.exit(main())
