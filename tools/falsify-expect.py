#!/usr/bin/env python3
"""FALSIFY EXPECT - run a harness falsifier and pass only when exactly the expected checks fail.

    .venv/Scripts/python tools/falsify-expect.py "<label>[|<label>...]" -- <harness command>

A falsifier exits 1 by design, so a step runner records it as a failure even when it proves the
check works. This wrapper inverts that correctly. It passes when every line marked FAIL contains one
of the expected labels, and every expected label appears on a FAIL line. Anything else fails: a
falsifier that fails nothing, fails the wrong check, or crashes proves nothing.
"""
import subprocess
import sys


def main():
    if len(sys.argv) < 4 or sys.argv[2] != '--':
        print(__doc__)
        return 2
    want = [w for w in sys.argv[1].split('|') if w]
    out = subprocess.run(sys.argv[3:], capture_output=True, text=True, encoding='utf-8',
                         errors='replace')
    lines = [l for l in out.stdout.splitlines() if '"GET ' not in l]
    print('\n'.join(lines))
    fails = [l for l in lines if l.strip().startswith('FAIL')]
    stray = [l for l in fails if not any(w in l for w in want)]
    missing = [w for w in want if not any(w in l for l in fails)]
    if out.returncode not in (0, 1):
        print('falsify-expect: the harness crashed with exit %d' % out.returncode)
        print(out.stderr[-1500:])
        return 1
    if stray or missing:
        print('falsify-expect: WRONG. unexpected failures %r, expected but not failed %r'
              % (stray, missing))
        return 1
    print('falsify-expect: exactly the expected check(s) failed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
