#!/usr/bin/env node
/* API-DUP-CHECK - no member of the engine's test surface is assigned twice.

       node tools/api-dup-check.js            check road.js
       node tools/api-dup-check.js FILE ...   check these files

   RLG-275. `road.js` attaches its API surface across thousands of lines, and an
   object literal that is never sealed takes the LAST assignment without a word.
   That happened twice: a second `API.grid` replaced the first and left the
   rolling-start half of launch-test unreachable, and RLG-203's `API.shift()`
   replaced the gearbox's `API.shift(dx, dy)` and broke gate-test with six
   failures that did not name the cause. Both were found by accident. This finds
   the next one the day it lands.

   COMMENTS ARE STRIPPED FIRST, so a name mentioned in prose does not count as
   an assignment. Line numbers survive the strip.

   THE TWO-STAGE MEMBERS ARE ALLOWED, AND ONLY IN THEIR OWN SHAPE. CLAUDE.md
   records that the seam contract fills in two stages: `onReset` fires during
   setup, before `ROAD()` returns, so a few helpers are attached at the top as
   WRAPPERS and replaced by the real functions later. Those names may appear
   exactly twice, and the first must sit above the file's `"use strict"` line,
   which is where the early block ends. A third assignment, or a first one
   anywhere else, is still a failure.

   Exit code 0 if nothing is assigned twice, 1 otherwise.
*/
'use strict';
const fs = require('fs');
const path = require('path');

const STAGED = new Set(['rnd', 'rint', 'rr', 'segAt']);

function check(file) {
  const src = fs.readFileSync(file, 'utf8');
  const keepLines = s => s.replace(/[^\n]/g, '');
  const code = src.replace(/\/\*[\s\S]*?\*\//g, keepLines)
                  .replace(/(^|[^:'"\\])\/\/[^\n]*/g, '$1');
  const strictAt = (() => {
    const i = code.indexOf('"use strict"');
    return i < 0 ? 0 : code.slice(0, i).split('\n').length;
  })();
  const seen = new Map();
  const re = /\bAPI\.([A-Za-z_$][\w$]*)\s*=(?!=)/g;
  let m;
  while ((m = re.exec(code))) {
    const line = code.slice(0, m.index).split('\n').length;
    if (!seen.has(m[1])) seen.set(m[1], []);
    seen.get(m[1]).push(line);
  }
  const bad = [];
  for (const [name, lines] of seen) {
    if (lines.length < 2) continue;
    if (STAGED.has(name) && lines.length === 2 && lines[0] < strictAt) continue;
    bad.push(`API.${name} is assigned ${lines.length} times, at lines ${lines.join(', ')}`);
  }
  return { members: seen.size, bad };
}

const files = process.argv.slice(2);
if (!files.length) files.push(path.join(__dirname, '..', 'road.js'));
let failed = 0;
for (const f of files) {
  const r = check(f);
  for (const b of r.bad) console.log(`  FAIL  ${path.basename(f)}: ${b}`);
  if (!r.bad.length) console.log(`  ok    ${path.basename(f)}: ${r.members} API members, none assigned twice`);
  failed += r.bad.length;
}
process.exit(failed ? 1 : 0);
