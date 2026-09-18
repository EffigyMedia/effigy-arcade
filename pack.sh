#!/usr/bin/env bash
# =====================================================================
# EFFIGY ARCADE — pack.sh
#
#     ./pack.sh                     build and validate effigy-arcade.zip
#     ./pack.sh --standalone <id>   emit ONE self-contained HTML for a game
# `--commercial` is GONE. It omitted the Golden Era shelf, and there is no
# Golden Era shelf here - this arcade is four machines on one floor. The flag
# was also known to be broken: it dropped the shelf from the staging area but
# regenerated the cache lists from the whole catalogue, so the worker asked for
# files the archive did not carry. Rebuild it against this catalogue if a
# commercial split is ever wanted again.
#     ./pack.sh --check             validate only, build nothing
#
# Builds from an explicit WHITELIST rather than from whatever happens to
# be in the folder — four instrumented debug builds once reached the
# public zip because cleanup was tacked onto the end of shell lines that
# sometimes never ran. A whitelist cannot fail that way.
#
# It refuses to build if anything below fails. Every one of these checks
# exists because the fault it catches actually shipped:
#
#   parse gate      two black screens: an unclosed brace, every other
#                   check passing over it. Nothing else asks whether the
#                   browser can READ the file.
#   catalogue       games.js and the games/ folder must agree, both ways,
#                   and `file` must sit under the folder `cat` names
#   scripts resolve every <script src> must exist on disk
#   shell API       Arcade.pad exports six methods; calling anything else
#                   throws the instant a gamepad connects, and no rig here
#                   has one (Girder called pad.onHold)
#   minimum standard meta tags, menus, controls, music bed, sfx, saves,
#                   attract function present in index.html's draw map
#   no scratch      _*, dotfiles and .py never reach the staging area
#   cache agreement sw.js and assets.js must name the same version
#
# What it CANNOT tell you is whether the game works. That is tools/
# drive-test.py and tools/smoke-test.py. Run those too.
#
# © 2026 Effigy Media. All rights reserved.
# =====================================================================
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

ZIP="effigy-arcade.zip"
MODE="build"
STANDALONE=""

while [ $# -gt 0 ]; do
  case "$1" in
    --check)       MODE="check" ;;
    --standalone)  STANDALONE="${2:-}"; shift ;;
    -h|--help)     sed -n '3,8p' "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

fail(){ echo "refusing to pack: $1" >&2; exit 1; }
say(){ printf '  %s\n' "$1"; }

command -v node >/dev/null || fail "node is required (parse gate, catalogue read)"

# ---- the whitelist -------------------------------------------------------
# If a file is added here it must ALSO be added to sw.js CORE_FILES. Two lists,
# one truth; they are cross-checked below. It was three until sync.sh was
# deleted on 2026-09-05 - that script cloned the remote into a temporary folder
# and copied files over the top, from when this working folder was not itself
# the repository (RLG-155).
ROOT_FILES=(
  index.html arcade.js audio.js road.js assets.js games.js sw.js
  manifest.webmanifest icon.png icon-512.png effigy.png
  pack.sh
  LICENSE 404.html
)
# No document ships. Tiny Arcade packed six of them at the root; this project
# keeps every document under docs/, and the archive is the product.
# A doc written after this list was drawn up does not ship, and nothing warns
# you: the whitelist protects against stray files getting IN, and has no
# opinion about wanted files being left OUT. PRIVATEER.md was written, edited
# across five sessions, and packed zero times before anyone noticed. The check
# below closes that: every .md in the folder must be either whitelisted above
# or named here as deliberately excluded.
# CLAUDE.md is the instruction file for an agent working in this repository.
# It describes how the product is BUILT, not the product, so it stays out of
# the archive on purpose.
NOT_SHIPPED=( CLAUDE.md )

# =====================================================================
# 1. THE CATALOGUE
# =====================================================================
CATALOGUE_JSON="$(node -e '
  global.window={};
  eval(require("fs").readFileSync("games.js","utf8"));
  console.log(JSON.stringify(window.EFFIGY_ARCADE));
')" || fail "games.js does not evaluate"

node -e '
const fs=require("fs"), path=require("path");
const games=JSON.parse(process.argv[1]);
let bad=[];
const seen=new Set();
for(const g of games){
  if(!fs.existsSync(g.file)) bad.push("catalogue names a file that is not here: "+g.file);
  if(!g.file.startsWith("games/"+g.cat+"/"))
    bad.push(g.id+": cat is \x27"+g.cat+"\x27 but file is "+g.file);
  if(seen.has(g.id)) bad.push("duplicate id: "+g.id);
  seen.add(g.id);
  if(!g.attract) bad.push(g.id+": no attract field");
}
/* the other direction: a game on disk that the catalogue does not list */
const walk=d=>fs.readdirSync(d,{withFileTypes:true}).flatMap(e=>
  e.isDirectory()?walk(path.join(d,e.name)):[path.join(d,e.name)]);
/* path.join uses the platform separator, and the catalogue is written with
   forward slashes. On Windows every file on disk therefore failed to match
   its own catalogue entry, and the check reported every cabinet as unlisted. */
const onDisk=walk("games").map(f=>f.split(path.sep).join("/")).filter(f=>f.endsWith(".html"));
const listed=new Set(games.map(g=>g.file));
for(const f of onDisk) if(!listed.has(f)) bad.push("shipped but not in the catalogue: "+f);
/* an attract whose draw function does not exist renders a black card and
   throws nothing at all */
const idx=fs.readFileSync("index.html","utf8");
const drawMap=idx.slice(idx.indexOf("draw"));
for(const g of games){
  if(g.attract && g.attract!=="none" && !new RegExp("[\x27\"`]?"+g.attract+"[\x27\"`]?\\s*:").test(drawMap))
    bad.push(g.id+": attract \x27"+g.attract+"\x27 has no entry in the draw map");
}
if(bad.length){ console.error(bad.map(b=>"    "+b).join("\n")); process.exit(1); }
' "$CATALOGUE_JSON" || fail "the catalogue and the folder disagree"
# An unmatched glob stays literal in bash, so a folder with no root document
# used to fail this check against a file named `*.md`. Tiny Arcade always had
# six documents at the root and never hit it; this project ships none.
shopt -s nullglob
for md in *.md; do
  case " ${ROOT_FILES[*]} ${NOT_SHIPPED[*]} " in
    *" $md "*) ;;
    *) fail "$md is in the folder but in no list — add it to ROOT_FILES or NOT_SHIPPED" ;;
  esac
done
shopt -u nullglob
say "docs: every .md is accounted for"

say "catalogue: every game listed is present, every game present is listed"

# =====================================================================
# 2. THE PARSE GATE
#    Extract every inline <script> and run node --check. This is the
#    check that should have existed from the first day.
# =====================================================================
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

PARSE_TARGETS=(arcade.js audio.js road.js games.js assets.js sw.js)
for f in "${PARSE_TARGETS[@]}"; do
  node --check "$f" 2>"$TMP/err" || {
    sed 's/^/        /' "$TMP/err" >&2; fail "$f does not parse"; }
done

node -e '
const fs=require("fs");
const games=JSON.parse(process.argv[1]).map(g=>g.file).concat(["index.html"]);
const out=[];
games.forEach((f,i)=>{
  const html=fs.readFileSync(f,"utf8");
  let body="", m, re=/<script(?![^>]*\ssrc=)[^>]*>([\s\S]*?)<\/script>/gi;
  while((m=re.exec(html))) body += m[1] + "\n;\n";
  fs.writeFileSync(process.argv[2]+"/_syn"+i+".js", body);
  out.push([f, process.argv[2]+"/_syn"+i+".js"]);
});
fs.writeFileSync(process.argv[2]+"/_map.json", JSON.stringify(out));
' "$CATALOGUE_JSON" "$TMP"

node -e '
const {execFileSync}=require("child_process");
const map=JSON.parse(require("fs").readFileSync(process.argv[1]+"/_map.json","utf8"));
let bad=0;
for(const [src,js] of map){
  try { execFileSync("node",["--check",js],{stdio:"pipe"}); }
  catch(e){
    const msg=(e.stderr||"").toString().split("\n").slice(0,3).join(" | ");
    console.error("    "+src+"  "+msg); bad++;
  }
}
process.exit(bad?1:0);
' "$TMP" || fail "a cabinet does not parse"
say "every cabinet parses"

# THE ENGINE'S TEST SURFACE HAS NO NAME ASSIGNED TWICE (RLG-275). The API
# object takes the last assignment silently, and two harnesses went dead that
# way before anyone looked. tools/api-dup-check.js says why the two-stage
# helpers are allowed. It is a tool rather than inline so it can be run alone.
node tools/api-dup-check.js road.js >"$TMP/dup" 2>&1 || {
  sed 's/^/      /' "$TMP/dup" >&2; fail "an API member is assigned twice"; }
say "no API member is assigned twice"

# =====================================================================
# 3. SCRIPTS RESOLVE + THE MINIMUM STANDARD
#    Read the file AND every same-origin script it includes, which is
#    what the browser does — PLAY and OPTIONS now live in road.js, and
#    checking the HTML alone reported a game with no menu at all.
# =====================================================================
node -e '
const fs=require("fs"), path=require("path");
const games=JSON.parse(process.argv[1]);
const PAD_API=["connected","axis","down","onPress","confirm","cancel"];
let bad=[];
for(const g of games){
  const dir=path.dirname(g.file);
  let html=fs.readFileSync(g.file,"utf8"), text=html;
  const srcs=[...html.matchAll(/<script[^>]*\ssrc=["\x27]([^"\x27]+)["\x27]/gi)].map(m=>m[1]);
  let loadsAudio=false, loadsArcade=false;
  for(const s of srcs){
    if(/^https?:/i.test(s)){ bad.push(g.id+": loads a script over the network: "+s); continue; }
    const p=path.normalize(path.join(dir,s));
    if(!fs.existsSync(p)){ bad.push(g.id+": <script src> does not resolve: "+s); continue; }
    if(/audio\.js$/.test(s)) loadsAudio=true;
    if(/arcade\.js$/.test(s)) loadsArcade=true;
    text += "\n" + fs.readFileSync(p,"utf8");
  }
  const need=(re,what)=>{ if(!re.test(text)) bad.push(g.id+": "+what); };
  if(!loadsAudio)  bad.push(g.id+": does not load audio.js");
  if(!loadsArcade) bad.push(g.id+": does not load arcade.js");
  for(const tag of ["arcade-home","arcade-title","arcade-accent"])
    if(!new RegExp("name=[\"\x27]"+tag+"[\"\x27]").test(html)) bad.push(g.id+": no "+tag+" meta tag");
  need(/\bPLAY\b/,          "no PLAY on the title screen");
  need(/\bOPTIONS\b/,       "no OPTIONS on the title screen");
  need(/\bCONTROLS\b/i,     "no controls page");
  need(/Arcade\.touch|AR\s*&&\s*AR\.touch|\.touch\b/, "controls page not detected per device");
  need(/(Arcade|A|AR)\.music\.start/, "no music bed");
  need(/(Arcade|A|AR)\.sfx\.(tone|noise)/, "no sound effects");
  need(/(Arcade|A|AR)\.save\.(merge|set)/, "does not record a best score");
  need(/bus\s*:\s*[\x27"]music[\x27"]/, "music not routed to bus:\x27music\x27");
  /* the shell API: six methods and no others. Qualified calls only —
     matching a bare `pad.` flagged a local `const pad = ...` in Quietus
     that has nothing to do with the gamepad. */
  for(const m of [...text.matchAll(/\b(?:Arcade|AR|A)\.pad\.([a-zA-Z_$][\w$]*)\s*\(/g)]){
    if(!PAD_API.includes(m[1])) bad.push(g.id+": calls Arcade.pad."+m[1]+"(), which does not exist");
  }
}
if(bad.length){ console.error([...new Set(bad)].map(b=>"    "+b).join("\n")); process.exit(1); }
' "$CATALOGUE_JSON" || fail "a cabinet does not meet the minimum standard"
say "every cabinet meets the minimum standard"

# =====================================================================
# 4. THE CACHE LISTS
#    sw.js and assets.js must name the same version, and the file lists
#    they carry are REGENERATED here so they cannot drift from what is
#    actually shipping. CORE went to v20 while RUNTIME stayed at v19
#    once, and a device kept half of a broken build.
# =====================================================================
# ---- REGENERATE, THEN VERIFY (RLG-004) ------------------------------------
# The agreement check used to run BEFORE the regeneration below, which is the
# wrong way round for the one job a build has. `assets.js` is GENERATED, and it
# takes its version from `sw.js` - so in a build the two agree by construction
# the moment the generator has run. Checking first meant a bump to `sw.js`
# failed the build that would have fixed it, and `assets.js` was seeded by hand
# once to get past it.
#
# THE CHECK IS NOT WEAKENED, which matters: the drift it catches is the drift
# that shipped eighteen 404s behind a green build. What changes is WHEN it runs.
# In `--check` mode there is nothing to regenerate, so it stands exactly where
# it was and compares the files as they are. In build mode it runs after
# section 4 and compares what was just written.
SW_CORE="$(grep -o "effigy-arcade-core-v[0-9]*" sw.js | head -1)"
SW_RUN="$(grep -o "effigy-arcade-runtime-v[0-9]*" sw.js | head -1)"
[ -n "$SW_CORE" ] || fail "sw.js has no cache version"
[ "${SW_CORE##*-}" = "${SW_RUN##*-}" ] || fail "sw.js core is ${SW_CORE##*-} but runtime is ${SW_RUN##*-}"

# ---- THE ENGINE'S STAMP AND THE SHELL'S VERSION AGREE (RLG-245) ------------
# `Arcade.buildTag()` prints MIXED when `window.ROAD_BUILD` in road.js differs
# from `A.version` in arcade.js. That tag exists to catch a cached engine beside
# a fresh shell. The two stamps drifted fourteen versions apart once, so every
# device read MIXED and the signal meant nothing. A disagreement in the source
# is always a missed bump, never a stale cache, so it stops the build.
SHELL_V="$(sed -n "s/^A\.version = '\([^']*\)';.*/\1/p" arcade.js | head -1)"
ROAD_V="$(sed -n "s/^window\.ROAD_BUILD = '\([^']*\)';.*/\1/p" road.js | head -1)"
[ -n "$SHELL_V" ] || fail "arcade.js has no A.version line"
[ -n "$ROAD_V" ]  || fail "road.js has no window.ROAD_BUILD line"
[ "$SHELL_V" = "$ROAD_V" ] || fail "road.js stamps ROAD_BUILD $ROAD_V but arcade.js is $SHELL_V - bump both in the same commit"

# the one comparison, in a function, so there is one definition of what
# agreement MEANS and two places that ask for it
cache_agrees(){
  local as_core
  as_core="$(grep -o "effigy-arcade-core-v[0-9]*" assets.js | head -1)"
  [ "$SW_CORE" = "$as_core" ] || fail "assets.js says $as_core, sw.js says $SW_CORE"
  say "cache version: ${SW_CORE##*-} (sw.js and assets.js agree)"
}

if [ "$MODE" != "build" ] || [ -n "$STANDALONE" ]; then cache_agrees; fi

if [ "$MODE" = "build" ] && [ -z "$STANDALONE" ]; then
  node -e '
    const fs=require("fs"), path=require("path");
    const games=JSON.parse(process.argv[1]).map(g=>"./"+g.file);
    /* dotfiles are excluded here for the same reason the staging area refuses
       them. `fonts/.gitkeep` reached both cache lists on the first run of this
       recreation, and the staging copy `cp fonts/*` does not carry it - so the
       service worker asked for a file the archive did not hold, and one 404
       fails the whole precache. */
    /* .woff2 ONLY. The glob used to take everything in the folder, so
       fonts/LICENSES.md was precached on every first visit - a document that
       no running game ever asks for. Dotfiles are excluded for the same reason
       the staging area refuses them: `fonts/.gitkeep` reached both cache lists
       once, the staging copy does not carry it, and one 404 fails the whole
       precache. */
    const fonts=fs.readdirSync("fonts").filter(f=>f[0]!=="."&&f.endsWith(".woff2"))
                  .sort().map(f=>"./fonts/"+f);
    const list=games.sort().concat(fonts);
    const body=JSON.stringify(list,null,2).replace(/^/gm,"").replace(/\[\n/,"[\n").slice(0,-1)+"];";
    /* assets.js */
    const core=fs.readFileSync("sw.js","utf8").match(/effigy-arcade-core-v\d+/)[0];
    fs.writeFileSync("assets.js",
      "/* generated by pack.sh — do not edit */\n"+
      "window.CACHE_NAME = \x27"+core+"\x27;\n"+
      "window.ARCADE_ASSETS = "+JSON.stringify(list,null,2)+";\n");
    /* sw.js ALL_FILES, rewritten in place between its markers */
    let sw=fs.readFileSync("sw.js","utf8");
    sw=sw.replace(/const ALL_FILES = \[[\s\S]*?\n\];/,
      "const ALL_FILES = "+JSON.stringify(list,null,2)+";");
    fs.writeFileSync("sw.js",sw);
  ' "$CATALOGUE_JSON"
  node --check assets.js && node --check sw.js || fail "regenerated cache lists do not parse"
  say "regenerated assets.js and sw.js ALL_FILES from what is shipping"
  # and NOW they must agree, on what was just written rather than on what was there
  cache_agrees
fi

# =====================================================================
# 5. STANDALONE — one self-contained HTML, every <script src> folded in
# =====================================================================
if [ -n "$STANDALONE" ]; then
  OUT="$(node -e '
    const fs=require("fs"), path=require("path");
    const games=JSON.parse(process.argv[1]);
    const g=games.find(x=>x.id===process.argv[2]);
    if(!g){ console.error("no such game: "+process.argv[2]); process.exit(1); }
    const dir=path.dirname(g.file);
    let html=fs.readFileSync(g.file,"utf8"), n=0, bytes=0;
    html=html.replace(/<script[^>]*\ssrc=["\x27]([^"\x27]+)["\x27][^>]*><\/script>/gi,(m,src)=>{
      if(/^https?:/i.test(src)) return m;
      const raw=fs.readFileSync(path.normalize(path.join(dir,src)),"utf8");
      /* arcade.js and audio.js each contain a literal closing script tag
         inside a string. Inlined as-is it ends the block early and the rest
         of the engine is parsed as HTML — the standalone booted to a canvas
         and an "Invalid or unexpected token". */
      const code=raw.replace(/<\/script/gi,"<\\/script");
      n++; bytes+=code.length;
      return "<script>\n/* inlined by pack.sh --standalone: "+src+" */\n"+code+"\n<\/script>";
    });
    const out=g.id+"-standalone.html";
    fs.writeFileSync(out,html);
    console.log(out+"\t"+n+"\t"+Math.round(fs.statSync(out).size/1024));
  ' "$CATALOGUE_JSON" "$STANDALONE")" || fail "standalone build failed"
  set -- $OUT
  say "standalone: $STANDALONE  ($2 shared scripts inlined, ${3}K)  →  $1"
  exit 0
fi

[ "$MODE" = "check" ] && { echo "  all checks pass — nothing built (--check)"; exit 0; }

# =====================================================================
# 6. STAGE FROM THE WHITELIST, AND REFUSE SCRATCH
# =====================================================================
STAGE="$TMP/effigy-arcade"
mkdir -p "$STAGE"
for f in "${ROOT_FILES[@]}"; do
  [ -f "$f" ] && cp "$f" "$STAGE/$f"
done
mkdir -p "$STAGE/fonts"; cp fonts/* "$STAGE/fonts/"
while IFS= read -r g; do
  mkdir -p "$STAGE/$(dirname "$g")"
  cp "$g" "$STAGE/$g"
done < <(node -e 'JSON.parse(process.argv[1]).forEach(g=>console.log(g.file))' "$CATALOGUE_JSON")
[ -d tools ] && { mkdir -p "$STAGE/tools"; cp tools/*.py "$STAGE/tools/" 2>/dev/null || true; }

SCRATCH="$(find "$STAGE" \( -name '_*' -o -name '.*' -o -name '*.py' \) \
           -not -path "$STAGE/tools/*" -not -name '.' | head -5)"
[ -z "$SCRATCH" ] || { echo "$SCRATCH" | sed 's/^/    /' >&2; fail "scratch files reached the staging area"; }

rm -f "$ZIP"
# `zip` is not on a stock Windows box and is not always in Git Bash either, so
# the build used to get all the way through every gate and then die on the last
# line. PowerShell's Compress-Archive is always there, produces a normal zip,
# and is only reached when `zip` is genuinely absent.
if command -v zip >/dev/null; then
  ( cd "$TMP" && zip -qr "$HERE/$ZIP" effigy-arcade )
elif command -v powershell >/dev/null; then
  powershell -NoProfile -Command     "Compress-Archive -Path '$(cygpath -w "$STAGE" 2>/dev/null || echo "$STAGE")'                       -DestinationPath '$(cygpath -w "$HERE/$ZIP" 2>/dev/null || echo "$HERE/$ZIP")' -Force"     || fail "Compress-Archive could not write $ZIP"
else
  fail "no archiver: install zip, or run where powershell is available"
fi
[ -f "$ZIP" ] || fail "the archive step reported success and produced no $ZIP"
COUNT="$(command -v unzip >/dev/null && unzip -l "$ZIP" | tail -1 | awk '{print $2}' || echo '?')"
say "packed $COUNT files → $ZIP ($(du -h "$ZIP" | cut -f1))"

echo
echo "  pack.sh cannot tell you the game works. Next:"
echo "      python3 tools/smoke-test.py      all four machines boot"
echo "      python3 tools/drive-test.py      both driving games play"
