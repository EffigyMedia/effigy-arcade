# Backlog reconciliation — 2026-09-08, against v0.13.38

The `requested` list had grown to **83 rulings** and was not usable as a queue. This pass
sorts each one into *implemented* or *genuinely not started*, against the engine.

**It never marks anything `built`.** [RLG-116](../fragments/RLG-116.md) rules that built means
implemented AND signed off working, and that the second condition is the owner's alone. So a
ruling whose work is in the code moves to **`in-flight`** — begun, not signed off — which is
exactly what those two conditions make it.

**Result: 83 requested became 27.** Fifty-six rulings were already implemented and had simply
never been moved off `requested`.

---

## Why the earlier attempt failed, and what was different

The thread records this reconciliation being tried and abandoned, with two signals rejected:

- **the changelog** — an entry CITES the ruling it serves rather than completing it;
- **the fragment's own prose** — it resolved 15 of 67 and left 52 unclear.

**Neither looks at the engine.** The question "is this implemented" is answerable from the
code, and this codebase answers it unusually well: its comments cite ruling ids by number,
because every mechanism is written up beside itself. A tally over `road.js`, `arcade.js`,
`index.html`, `games.js`, `audio.js`, `sw.js`, the cabinets, `tools/` and `pack.sh` found
**57 of the 83 cited in the source**, some very heavily — RLG-112 sixty-nine times, RLG-059
sixty, RLG-105 forty-four.

**A citation is triage, not proof, and the distinction that matters is what KIND of ruling it
is.** For a *build X* ruling, a citation is strong evidence X was built. For a *X is wrong, fix
it* ruling, a citation only proves X exists — the complaint may still stand. RLG-153 is cited
eighteen times and says the tunnel looks terrible: the tunnel is plainly built and the
complaint is plainly open. Every ruling of that shape was held back and checked by hand.

**Three signals were used together**, and where they disagreed the code won: the citation
count, the ruling's own kind, and a targeted read of the mechanism it names.

---

## What moved, and on what evidence

**Fifty-six moved to `in-flight`.** The heavily-cited build rulings — the bridge, the tunnel,
the canyon, farmland, the jungle, the climate model, the biome sweep, the lamp declaration, the
scenery, the wider road, the count-in, the four-speed gate — plus the ones whose mechanism was
read directly. A sample of what was checked by hand rather than by citation:

| Ruling | Evidence |
|---|---|
| RLG-004 pack.sh order | `pack.sh` carries a section headed *REGENERATE, THEN VERIFY (RLG-004)* |
| RLG-023 two weather layers | the ground layer and the far field carry the cover, as the owner asked |
| RLG-046 police engage any speeder | `if(!(c.mind >= SPEEDER)) continue;` — the gate is on the driver, not on the player |
| RLG-047 non-racers pull over | `yielding` is set, read and cleared through the traffic step |
| RLG-050 debug jump to a finish | the finish line can be placed behind the car from the API |
| RLG-076 damage is the impact's magnitude | `hurt(13 * sev …)` where `sev` is what `impactWith` returns |
| RLG-066 push cadence | a policy ruling, now stated in `CLAUDE.md` |
| RLG-084 radar detector | **superseded by [RLG-164](../fragments/RLG-164.md)**, built 2026-09-08 |
| RLG-098 screech pitch | `var r = spd / top` — the pitch already climbs with SPEED, not with revs |
| RLG-124 / RLG-135 mirror rain | `mirror-rain-test` carries the dry control the rulings asked for |
| RLG-141 nitrous flake | `drive-test` reads `nosOn` rather than assuming the button took |

**Twenty-seven stayed `requested`.** They are listed below with why.

---

## And one of them is not what the owner believed

`tools/verify-097-100.py` exists because of this, owner 2026-08-31: *"ruling 100 is probably
unnecessary now because adding earning +10 seconds to each pick up solved that issue. Also,
RLG-097 has been fixed. Let's move both of these to the end and just do a quick analysis to
verify these facts."*

**It was run. RLG-100 does not survive it.** At full throttle, on a road with checkpoints two
miles apart paying twenty seconds:

| Car | clock | distance | crates |
|---|---|---|---|
| TUNER | 60.0 → 0.0 | 3.46 miles | 1 |
| ROADSTER | 60.0 → 0.0 | 1.89 miles | 0 |
| MUSCLE | 60.0 → 0.0 | 3.94 miles | 0 |

**All three run the clock out, and the ROADSTER runs out at 1.89 miles — before it ever reaches
the first checkpoint.** The crate award did not close the margin; the roadster never gets far
enough to collect one. That is the unfairness across classes the ruling names, still present.
RLG-100 stays open and it is now measured rather than asserted.

RLG-097, the pop on GO, is a device report and stays open on the same grounds the harness gives:
a harness cannot see the pop, only whether anything still steps across the count-in boundary.

---

## What is genuinely left, and what each one needs

**Needs nothing but a session — start any of these:**

- **RLG-100** the checkpoint budget, now with the measurement above to work from
- **RLG-081** turbo and supercharger upgrades — one mention of "turbo" in the engine, in an unrelated comment
- **RLG-156** one-mile drag races, forced manual, one on one
- **RLG-099** the tyres screech when the car slides — the screech is gated on `decel` only, and lateral scrub is computed a few lines away and never reaches it
- **RLG-139** nothing reads `ROAD_BUILD` outside the engine, so the stamp can go stale again
- **RLG-043** lower the production and sports stats — `stat-test` says in its own words that this is not built
- **RLG-071** what silver and bronze pay — the code says it "is being explored; nothing is" settled
- **RLG-137** the optimisation sweep, which today's survey now points at scenery
- **RLG-063** the arcade says which build it is running, and the commit says the same string

**Needs one decision from the owner first:**

- **RLG-171** should a cruiser behind you take traffic damage — taste, not correctness
- **RLG-027** the menu polish, whose scope has never been agreed
- **RLG-149** whether Godot with rasterized art answers the older iPad
- **RLG-134** the centre-screen messages, deliberately deferred once already

**Needs the owner's eye on a device:**

- **RLG-097** the pop on GO, **RLG-082** anchored spacing, **RLG-153** the tunnel's look,
  **RLG-145** the eight-item device report, **RLG-146** the desert skyline's detail

**Investigations nobody has run:**

- **RLG-029** verify the rubber banding — measure, do not tune
- **RLG-037** scatter against the corridor guarantee — measured failing again today at 0.234,
  0.209 and 0.283 against a 0.34 limit, on both arms, so it is a live flake
- **RLG-033** racers need more intelligence, four parts the owner chose
- **RLG-122** whether traffic and rival engine sounds are pinned rather than derived

**Uncertain — a grep could not settle these and each needs a session's reading:**

- **RLG-026** whether a stale tournament rewards system still fires
- **RLG-068** whether vehicles close to the player are still clipped by road slices
- **RLG-147** whether returning from pause still gets a fresh countdown
- **RLG-061** whether vehicles should be drawn further down the road
- **RLG-083** an environment-level ruling about the fragment tools, not this project's code

---

## What this pass does NOT claim

- **Nothing here is `built`.** Fifty-six rulings are now `in-flight`, which says the work is in
  the engine and says nothing about whether it works on a device. Only the owner closes them.
- **The `in-flight` set was not individually device-tested**, and several of its members are
  today's unseen builds.
- **Citation counts were a triage signal**, and the four uncertain rulings above are exactly the
  cases where that signal ran out. They are named rather than guessed at.
