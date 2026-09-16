#!/usr/bin/env python3
"""EDGE PROOF - that `EDGE_X` is the limit of travel, rather than a number beside it.

    .venv/Scripts/python tools/edge-proof.py

RLG-265 puts a GUARD RAIL at the limit of travel. The limit was written out as the literal
`1.18` at seven separate clamp sites - the player's steering, the drift, the two scripted-steer
paths, the shunt a collision applies, the autopilot's target, and `edgeX()` - and a rail drawn
from one copy would disagree with the car at the other six. So the seven became one constant.

A GREEN SUITE CANNOT TELL YOU THAT WORKED. Every harness passes whether the sites read `EDGE_X`
or still read `1.18`, because the two are the same number today. The refactor is invisible to
every check that exists, which is exactly the shape this project has been caught by before: a
scan that flagged every object-method shorthand, a selector that reported the pause button
missing from every machine, four guards that passed with the bug present.

SO THIS MOVES THE CONSTANT AND ASSERTS THE CAR FOLLOWS IT. `tunnel-wall-test` already measures
how far out the car actually reaches; narrow `EDGE_X` to 0.90 and that measurement must become
0.90. Put it back and it must return. A check that cannot report the other answer is not
evidence of anything.

WHAT IT PROVES AND WHAT IT DOES NOT. Driving the car proves the STEERING clamp and `edgeX()`.
It does not exercise the collision shunt, the two scripted-steer paths or the autopilot target -
nothing in this harness scripts a steer or takes a hit. Those four are covered by the static
half below: no clamp site anywhere in the engine still writes the literal. That is a weaker
claim than the dynamic one and it is stated as such rather than blurred into it.

IT EDITS road.js AND PUTS IT BACK, and it refuses to finish if the file is not restored.
"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROAD = ROOT / 'road.js'
PY = ROOT / '.venv' / 'Scripts' / 'python.exe'

SHIPPED = 'const EDGE_X = 1.18;'
NARROW = 'const EDGE_X = 0.90;'


def reach():
    """how far out tunnel-wall-test measures the car actually getting, on the open road"""
    out = subprocess.run([str(PY), str(ROOT / 'tools' / 'tunnel-wall-test.py')],
                         capture_output=True, text=True, encoding='utf-8',
                         errors='replace', cwd=str(ROOT).replace('/', '\\'))
    for line in (out.stdout + out.stderr).splitlines():
        if 'reaches the old edge' in line:
            m = re.search(r'furthest out ([0-9.]+)', line)
            if m:
                return float(m.group(1))
    raise SystemExit('  the harness did not report a reach - it cannot prove anything\n'
                     + (out.stdout + out.stderr)[-2000:])


def swap(frm, to):
    s = ROAD.read_text(encoding='utf-8')
    if s.count(frm) != 1:
        raise SystemExit('  road.js does not carry `%s` exactly once - refusing to edit' % frm)
    ROAD.write_text(s.replace(frm, to), encoding='utf-8')


def main():
    fails = []
    print('edge-proof  .  that EDGE_X is the limit, not a number beside it')
    print()

    before = reach()
    print('  EDGE_X 1.18, as shipped     the car reaches %.3f' % before)

    swap(SHIPPED, NARROW)
    try:
        narrow = reach()
    finally:
        swap(NARROW, SHIPPED)           # put it back even if the harness threw
    print('  EDGE_X narrowed to 0.90     the car reaches %.3f' % narrow)

    after = reach()
    print('  EDGE_X put back             the car reaches %.3f' % after)
    print()

    if SHIPPED not in ROAD.read_text(encoding='utf-8'):
        fails.append('road.js was NOT restored - fix it by hand before anything else')

    ok = abs(narrow - 0.90) < 0.005
    print('  %s  narrowing the constant moved the car to the new limit   %.3f'
          % ('ok  ' if ok else 'FAIL', narrow))
    if not ok:
        fails.append('the car did not follow the constant - a steering site still reads a literal')

    ok = abs(after - before) < 0.005
    print('  %s  and putting it back restored the old limit   %.3f then %.3f'
          % ('ok  ' if ok else 'FAIL', before, after))
    if not ok:
        fails.append('the limit did not come back')

    # ---- the static half, which is the weaker claim and says so ------------------------
    src = ROAD.read_text(encoding='utf-8')
    strays = [(i + 1, l.strip()) for i, l in enumerate(src.splitlines())
              if re.search(r'-1\.18\s*,\s*1\.18|return 1\.18|Math\.min\(1\.18', l)]
    print('  %s  no clamp site still writes the literal   %d found'
          % ('ok  ' if not strays else 'FAIL', len(strays)))
    for n, l in strays[:5]:
        print('        road.js:%d  %s' % (n, l[:90]))
    if strays:
        fails.append('a clamp site still writes 1.18')

    print()
    print('  the dynamic half proves the STEERING clamp and edgeX. The collision shunt, the two')
    print('  scripted-steer paths and the autopilot target are not driven here - they rest on')
    print('  the static line above, which is the weaker claim.')
    print()
    if fails:
        for f in fails:
            print('  FAIL  ' + f)
        return 1
    print('  EDGE_X is the limit of travel')
    return 0


sys.exit(main())
