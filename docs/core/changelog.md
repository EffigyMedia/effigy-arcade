# Changelog

The append-only index of what shipped and when, keyed to version. One short dated entry per feature
commit. Newest on top. **An entry is never edited after the fact.**

Each entry links to the fragment that holds the full record. This project keeps no `tracker.md`, so
a link points at the fragment file itself: `[RLG-001](../fragments/RLG-001.md)`. Both directions
must resolve, and that is verified at every audit.

**The history before this file begins is Tiny Arcade's**, and it came across whole rather than being
squashed. That project's own changelog stops at 0.9.11 and stays in its own repository. The version
here reset to 0.1.0 at the fork: the engine did not get younger, but this product's own work had
barely started, and 0.9.x would have claimed otherwise.

---

<a id="v0-13-45"></a>
## [0.13.45] - 2026-09-08
- Removed: **the PURSUIT row, from both driving cabinets.** Owner, 2026-09-08: "I wanna just
  remove the pursuit banner. I think there's a better way we can express being actively engaged or
  not." It said in words, in its own box, what the stars above it could say in a colour.
- Changed: **the wanted stars are gold while a cruiser is engaged to you and blue while you are
  cooling.** Owner: "the outline of the stars should be gold when you're hot and blue when you're
  cold, along with the fill." Outline and fill move together, so the row answers *how wanted* and
  *right now?* in one glance. See [RLG-178](../fragments/RLG-178.md).
- Changed: **the stars have a real outline.** They were solid glyphs, so an unfilled star was the
  same shape in a paler colour and there was no outline to give a colour to. The edge is a
  `-webkit-text-stroke` now and the fill is painted through `background-clip:text`, which is how
  the part-filled star already worked. `--gold` is finally a named variable: `#rotate b` has been
  asking for it with a literal fallback since it was written.
- Added: **`tools/stars-shot.py`**, which captures the row in each state at four times device
  pixels, and **`tools/wanted-stars-test.py`**, which replaces `pursuit-row-test.py`. The check
  reads the computed stroke and fill rather than trusting the class name - while this was being
  built the class was toggled onto the WRAPPER while the rule was written for the ROW, so the
  state was right, the stylesheet was right, and nothing changed on the screen.

<a id="v0-13-44"></a>
## [0.13.44] - 2026-09-08
- Fixed: **the thing that looked like a health bar over police cruisers in the mirror was a second
  light bar.** Owner, 2026-09-08, from the device. The glass painted its own `fillRect` on top of
  every cruiser - **the whole width of the car, one bar-height above the roof** - over the bar the
  front sprite already draws. The comment beside it claimed the bar "is the one part of a police
  car that is not in the sprite, because it flashes", and that stopped being true when
  [RLG-053](../fragments/RLG-053.md) converted the cruiser: the front sprite declares `bar.fl` and
  `bar.fr` as lamps. The mirror now lights those, so there is one bar and the sprite owns it. See
  [RLG-177](../fragments/RLG-177.md).
- Added: **`tools/mirror-bar-test.py` and `tools/cop-mirror-shot.py`.** The capture tool is what
  found this - the two candidate explanations, a real bar and the light bar misread at 44-pixel
  scale, could not be told apart by reading code, and one picture settled it. The check asserts
  that nothing belonging to a police car is painted above its own sprite.

<a id="v0-13-43"></a>
## [0.13.43] - 2026-09-08
- Fixed: **every run opened with a blinking PURSUIT ×1 and nothing was chasing you.** Owner,
  2026-09-08: "Every run starts with a banner that says pursuit x1. What is that and why do we
  need it?" The row is a live count of the cruisers on you and is worth having, but it counted
  `onPlayer !== false` - and a car that has never chosen a target has `onPlayer` **undefined**,
  which passes that test. A speed trap is laid in the first seconds of every run, so the row
  reported a parked car that had not looked at anybody. **This is the same mistake in the same
  shape as the box in 0.13.42**, found the same day: `!== false` was written to mean "is on the
  player" and quietly also means "has never decided". Measured on the old predicate: lit, at
  ×1, on 90 of 90 samples of a legal drive. See [RLG-178](../fragments/RLG-178.md).
- Removed: **the dead combo suffix on that row.** `combo` is zeroed at every reset and nothing
  raises it - the score system it belonged to is gone, and the near-miss handler already carries
  a note about the same variable printing "+0" over the road. The text it guarded could never
  appear.

<a id="v0-13-42"></a>
## [0.13.42] - 2026-09-08
- Changed: **one engagement, one target, permanently.** Owner, 2026-09-08: "whenever a cop engages a
  target it continues to engage that target until that target either pulls over voluntarily, is
  forced to stop due to entrapment, or fails to keep up with its target and it disengages and pulls
  back over to make a new trap. Having it retarget something else because it is slightly faster while
  cool I think will just break this illusion." A cruiser now searches ONCE, at the start of a
  pursuit, and holds that car until one of those three endings. The event switch that shipped the
  day before is gone, and so are `COP_PASS_BY` and `COP_SWITCH_MPH`. See
  [RLG-173](../fragments/RLG-173.md).
- Added: **a cruiser that cannot keep up gives up and parks as a new speed trap.** Twenty thousand
  units of ground lost, held for five seconds, and it pulls onto the verge and re-arms. This is what
  makes the trap population self-sustaining: a trap that leaves comes back as a trap somewhere else,
  so the field cannot empty the road of them.
- Fixed: **a speed trap was not parked.** The owner reported cruisers driving along the side of the
  road rather than sitting on it, and the cause was that nothing kept a trap out of the main cruiser
  update: an armed trap ran the pursuit search every 1.4 seconds, took whatever speeder it found, and
  the 2,000-unit floor under every cruiser's speed moved it off its post even when it found nobody.
  It joined the box as well, because a car that has never chosen a target has `onPlayer` undefined
  and the box test asked whether it was *not* the player. Measured at 93mph while parked; now zero
  drift over twelve seconds.
- Fixed: **a dispatched car is dispatched for you.** With the first choice now the only choice, an
  interceptor that opened on a passing NPC was spent - measured, heat five with the 170-past-a-trap
  condition earned put FOUR interceptors on the road before and NONE after. A radio car and a super
  cruiser take the player without searching, and a pursuit of a driver who is still wanted is never
  given up on: it is dropped the old way, left behind and culled.

<a id="v0-13-41"></a>
## [0.13.41] - 2026-09-08
- Changed: **a cruiser keeps the car it is chasing unless you go past it faster.** Owner,
  2026-09-08: "I don't think every cruiser should just inherently switch its targeting to you just
  because you exist and you are also speeding half a mile behind them." The switch is an EVENT now,
  not a comparison: it must be alongside you, and you must be doing more than the car it already has
  by ten miles an hour. Measured - half a mile up the road with you 40mph faster, it keeps the NPC.
  See [RLG-172](../fragments/RLG-172.md).
- Fixed: **three fallbacks that quietly meant "the player".** A fruitless search wrote its empty
  result through and set the speed being compared against to zero, which makes "faster than its
  current car" true of any speed. Keeping the old target instead broke the opposite case: a cruiser
  that never had a target kept an undefined one, and the line that reads it treats undefined as YOU -
  it busted a clean stopped driver in the check written to forbid that. And the bust counted any
  cruiser standing near a stopped car, so a driver wanted for nothing could be arrested for pulling
  up beside a parked police car. **A bust is the end of a pursuit**, so it needs a cruiser actually
  on you, and a parked trap counts for nothing.

<a id="v0-13-40"></a>
## [0.13.40] - 2026-09-08
- Fixed: **a clean driver is not a target.** Owner, 2026-09-08: "there's STILL an overwhelming amount
  of cops just coming back at me one after the other engaged to me... and why do I start hot pursuit
  with heat at all?" One root cause answered both. The player was the DEFAULT target of every
  cruiser's search, unconditionally and weighted toward - right for a cruiser already on you, wrong
  for every other one. So a trap that left its post for a speeding NPC re-targeted within 1.4 seconds
  and adopted you however you were driving, and they accumulated.
- **Measured at 76mph against a limit of 80**, with no heat and not one radio dispatch: four cruisers
  engaged to a driver who had done nothing, every one trap-born. After the fix the same run holds at
  zero engaged, and the only cruiser on the road is a trap pulling over an NPC.
- **And that is where the heat came from.** RLG-170 charges two points a mile WHILE PURSUED, so a
  clean driver was billed for a pursuit that should never have started. Nothing was wrong with the
  reset - `heatPts` is zeroed every run. See [RLG-172](../fragments/RLG-172.md).
- **A cop already on you still keeps you**, which is the half the old comment claimed and the code
  did not make. Without it, braking to a stop made every cruiser lose interest and the BUSTED rule
  became unreachable.
- Fixed: **the bust check was holding the defect in place.** It staged a cruiser beside a driver with
  NO heat and expected an arrest - a case that only passed because every cruiser adopted the player
  whatever they had done. The scene now carries a real pursuit, and the owner's complaint is a check
  of its own: a driver wanted for nothing cannot be busted.

<a id="v0-13-39"></a>
## [0.13.39] - 2026-09-08
- Fixed: **no police arrive from up the road.** Owner, 2026-09-08: "there are still police coming
  from up ahead." It was two rulings meeting rather than either being wrong. A speed trap is parked
  35,000 to 52,000 units AHEAD by its nature, and [RLG-046](../fragments/RLG-046.md) says the police
  engage any car breaking the limit and not only the player - so a trap far up the road that spotted
  a speeding NPC left its post and became a MOVING police car in front of you, chasing somebody
  else, having never come from behind. Measured: three of fourteen cruisers in one run were
  trap-born and first seen about 36,000 units ahead, already out of trap state.
- **The gate is the one the player's own case already uses**: a trap acts when it is behind you,
  which is exactly when you have passed it. That keeps RLG-046 whole and keeps the arrival behind
  you. It costs the sight of somebody else being pulled over up ahead. See
  [RLG-157](../fragments/RLG-157.md).
- Fixed: **a cruiser could exceed its own top speed**, which shipped this morning with the box at
  speed. The station is built from the PLAYER'S speed, harmless while the box only formed at a
  standstill and a way round the car's ceiling once it formed at any speed - measured at 16,393
  against a ceiling of 10,886, a patrol car keeping station with a supercar it cannot catch. Both
  police cars are back under their own ceilings.
- `patrol-test.py` now asserts it. **RLG-157 had no harness**, which is why it could go wrong
  silently after being proved once by hand - and the two ways it happens are separated, because a
  cruiser born ahead and one that drives in front need different fixes.

<a id="v0-13-38"></a>
## [0.13.38] - 2026-09-08
- Changed: **a deer you hit is killed, and it costs the car properly.** Owner, 2026-09-08: "the deer
  should explode in a bloody mess and it should do appropriate damage to your car." That is the tone
  question [RLG-152](../fragments/RLG-152.md) left open and said was not a session's to make.
- **The mess is not the debris burst in a different colour.** Forty particles in three reds on two
  velocity budgets - a fast bright spray gone in a fifth of a second, and slow dark chunks still
  tumbling most of a second later. And it comes up over the BONNET: the impact point projects to the
  very bottom of the screen, behind the player's own car, where almost none of it could be seen.
- **Two numbers, because they answer different questions.** 90kg decides what the animal does to the
  car's motion - you barely slow, and it does not push you off your line. A separate strike factor
  decides what it does to the bodywork, and is deliberately more than the mass suggests: a deer comes
  over the bonnet rather than being pushed aside. **Measured nose-on at four fifths of top speed:
  20.3 damage against 10.2 for clipping a saloon at the same speed**, a quarter of an 81-point panel.
  Before this an animal cost 8.1 - hitting a deer was cheaper than clipping a car.
- Fixed: **every particle burst in the game rose in a straight vertical line.** `fx` carries floating
  messages and particles, and the driving stepper branched on the wrong axis - it tested `vy` where
  it meant `vx`, and a particle has both, so every burst took the message path: no horizontal spread
  and no gravity. It has been flattening the orange debris off a car and the yellow off a roadblock
  since both were written, and the wrecked stepper has always had it right. Found while trying to
  photograph the gore.

<a id="v0-13-37"></a>
## [0.13.37] - 2026-09-08
- Added: **the road runs to the horizon as one body of tarmac.** Owner, 2026-08-31: "another thing
  that would be really cool is if we did the same thing for the highway, so that the highway is
  interpreted and drawn to the horizon." The road stopped short of the skyline and the band above it
  was filled with the far verge's colour, so the tarmac ended and the land carried on.
- **The tarmac and not the markings**, which the ruling worked out in advance. Carrying the surface
  is a polygon; carrying the lane markings is a strobing pattern that has to keep its phase, and
  past this distance a marking is under a pixel wide anyway. One construction, not two: the band
  walks on in the same steps the road walks in and closes to a point at the vanishing point. See
  [RLG-101](../fragments/RLG-101.md).
- **The steps had to grow rather than be even.** Beyond the draw distance the projection compresses
  hard, so an even stride put the first point inside a quarter-pixel of the horizon and every point
  was rejected - the band came out as one straight cone, which is the thing it was built not to be.
- **And it belongs on the road's side of the haze.** The sea's band is painted before the haze and
  takes the wash as paint; the road cannot be, because the drawn road is painted after it - a band
  on the sky's side arrived a different colour and the seam was a tone step of 46. The ruling
  predicted that seam and gave the reason.
- **The tone step across the join is printed rather than asserted, and the harness says why.** Four
  sampling schemes were tried and each measured something other than the seam - the lane markings,
  the rumble strip, the verge, and the band on both sides - and the last one still swung 34, 84 and
  39 across three runs of one unchanged build. `tools/farroad-test.py` asserts what is stable and
  falsifies on it. **The join needs judging on a device.**

<a id="v0-13-36"></a>
## [0.13.36] - 2026-09-08
- Fixed: **stars belong to a clear night.** Owner, 2026-09-01: "can the clear night sky have stars?"
  It already did, so the ruling said to MEASURE which of three candidates was wrong before changing
  any of them. Measured: 2,499 bright points on a clear sky and 2,580 under nine tenths cover - the
  same sky twice, because the star alpha never mentioned the cover at all. It does now.
- **The third candidate was already fixed and the ruling did not know it**: the horizon bloom is
  driven purely by the golden hour now and reaches zero at night, so nothing washes them. And forty
  single pixels on a regular lattice read as dither, so there are 110 at three brightnesses with the
  lattice broken up. A clear sky also has no cloud in it now - the puff count had a floor of three.
- Added: **a tundra sometimes has an aurora.** One place in four, rolled once when the place opens
  and held for it. Three bands, each a wave with its own height and phase, hanging DOWN from a
  ragged edge and fading before they reach anything - green low, violet above. Night only, and it
  wants a clear sky for the same reason the stars do, which makes both halves one mechanism. See
  [RLG-151](../fragments/RLG-151.md).
- **The first placement could not be seen**: the curtain hung a tenth of the way down the sky, which
  on a phone is directly behind the rear-view mirror. Drawn correctly, and invisible.
- `tools/aurora-test.py` is new. It asserts the aurora and falsifies on it, and it PRINTS the star
  numbers rather than asserting them - with the gate taken back out the ordering still held, because
  cloud covers a star as well as dimming it, and a check that cannot fail is worse than none.

<a id="v0-13-35"></a>
## [0.13.35] - 2026-09-08
- Changed: **clouds read as clouds.** Owner, 2026-09-07: "clouds don't read as clouds - fluffy white
  in clear skies, light snow storms, and dark thunder storms." The cover had a NUMBER and no FORM,
  so a sky with more cloud in it read as a flatter colour rather than as more cloud.
- **The three the owner named are one thing seen three ways**, driven by two values that already
  existed - how stormy it is and whether the precipitation is snow. Clear is piled and white, snow
  is a low flat pale lid, thunder is dark and heavy. See [RLG-167](../fragments/RLG-167.md).
- **A cumulus is a cluster, not an ellipse.** One ellipse is a smudge at any size; four overlapping
  circles along a flat base is a cloud at any size, and the underside is drawn darker because a
  cloud is lit from above. The wash is squared against the cover now, so a light day is shapes on
  open sky rather than a grey film with shapes on it.
- **Three statistics were needed before one measured cloud.** Contrast across a row scored an EMPTY
  sky at 85, because the horizon glow is radial; neighbour-to-neighbour scored an empty sky at 1.39
  and an overcast one at 1.43, because the sun is a small disc with hard edges. What works is
  comparing two skies, where the sun and the gradient subtract away exactly, and measuring how
  patchy the difference is WITHIN each row. `tools/cloud-test.py` is new and it falsifies: with the
  shapes removed the score drops from 0.61-0.95 to 0.30-0.39.

<a id="v0-13-34"></a>
## [0.13.34] - 2026-09-08
- Added: **a deer crosses a forest road, very rarely.** Owner, 2026-09-01: "in the forest biome I'd
  like a very very small chance for deer to sprint across the road from one tree line to the other."
  It is the first thing in this game that moves ACROSS the road.
- **It is a mind, not a vehicle class.** `CROSSING` sits beside CIVILIAN, SPEEDER and RACER, so the
  spawner, the culler, the mirror, the crest occlusion and the collision all go on working without
  knowing what a deer is. See [RLG-152](../fragments/RLG-152.md).
- **The ruling's three open questions are answered and recorded as decided-for-now**, each a single
  tunable: about one forest in ten, rolled once when the place opens rather than tested per second,
  measured at 10.8%, 10.5% and 9.5% over 400 openings; 2.5 lane units a second, which clears the
  tarmac in about eight tenths of a second; and hitting one costs what any collision costs, which is
  what makes a forest a place to slow down for. **The animal is not killed and nothing depicts one
  being killed** - the ruling calls that a tone decision and not a session's to make.
- **It wants two tree lines**, so a forest with water down one side plans none - measured at 0 of 400.
- **It is kept out of the lane sweeps deliberately.** A thing on the road for under a second is
  nobody's lane, and treating it as an obstacle would set every car near it braking for something
  already gone. The hazard is the player's. `tools/deer-test.py` is new and it falsifies.

<a id="v0-13-33"></a>
## [0.13.33] - 2026-09-08
- Fixed: **every car is as wide as its own picture.** Owner, 2026-08-28: "we have to make the
  vehicle colliders true to their sprite size. It's hard to tell." The half of that ruling left for
  later was that all six player cars collided at ONE width while traffic and rivals each carried
  their own - a lorry and a roadster the same width in your hands.
- **The numbers are derived, not invented.** `PLAYER_W` sizes the canvas a car is drawn into; the
  painter draws the body across a fraction of that canvas, and the fraction is the body's own
  `wide`. So the width you can SEE has been per-car all along and only the hit test was not. It is
  the rear silhouette, because that is the only view you have of your own car.
- **Every car gets narrower, which is the point.** The fleet runs from 0.225 for the roadster to
  0.300 for a formula car against a flat 0.265, so a roadster was being struck fifteen per cent
  wider than it looks. See [RLG-058](../fragments/RLG-058.md).
- Fixed: **two checks in the collider harness were red on main and nobody had said so**, and four
  faults in it are gone - all the same shape, a measurement not measuring what it named. The run
  clock froze the world mid-search and made a body read zero damage at a full overlap; the count-in
  froze it during the FIRST search, which is why only that one was unstable at 0.0012, 0.0750 and
  0.0375 on one build; a contact shoved the player out of the offset being tested, so the answer
  depended on how long the harness waited; and the declared sum was read against whichever car was
  first in the array rather than the one parked in front of the player.

<a id="v0-13-32"></a>
## [0.13.32] - 2026-09-08
- Changed: **the police navigate the traffic, and surround you before you stop.** Owner, 2026-09-07:
  they "need to be just as interested in navigating the traffic as they are stopping and arresting
  you... their main method of attack should be to surround you and slow you down so that you get
  arrested/busted." See [RLG-158](../fragments/RLG-158.md).
- **The dodge steered and never lifted.** A cruiser read the road ahead and picked a LINE around it;
  its speed came from the chase and nothing else, so a lorry with cars either side was driven into
  at full chase speed. It now eases for what it cannot go round - closer than a civilian would,
  because a police car in a pursuit tailgates. **The reach is a time, not a distance**: 2,400 units
  sounds a long way and is under half a second at 150mph.
- **The box no longer waits for you to stop.** It asked whether the player was under a tenth of top
  speed, which made being surrounded the consequence of stopping rather than the method of causing
  it. A cruiser that has caught up takes its station at any speed, and the one in front runs at nine
  tenths of your speed rather than matching it, so staying on the throttle means going through it.
- **The proof is two controlled scenes, because the statistic could not settle it.** Damage taken
  from traffic ran 6.0, 5.3 and 8.7 a minute before and 2.7, 7.3 and 5.3 after - the means move the
  right way and the ranges overlap, so three runs an arm say nothing. Against three cars abreast,
  where no line exists, the cruiser slowed from 7,000 to 5,037 against a wall running at 4,622 and
  took no damage; the old engine held 10,886 and went through.
- **The owner's original report still does not reproduce**, and the reason is now known: a cruiser
  only takes traffic damage while level with the player or ahead, so every one chasing from behind
  passes through traffic untouched. Tracked as [RLG-171](../fragments/RLG-171.md) - it needs the
  owner's judgment, not a fix.

<a id="v0-13-31"></a>
## [0.13.31] - 2026-09-08
- Fixed: **the traffic can see the police.** Owner, 2026-09-07: "seems like traffic doesn't avoid
  crashing into the police either, so it's two-sided." Every avoidance sweep read `traffic`, then
  the PLAYER as a named special case, and `cops` not at all - so a cruiser was invisible to every
  civilian on the road, and a pursuit ploughed a furrow through the traffic instead of parting it.
  Four sweeps now read the police too: is this lane clear, would moving there close the road, how
  fast is that lane, and what am I about to drive into the back of.
- **A cruiser is a third list, not a third behaviour.** Nothing about how civilians drive changed -
  same margins, same urgency, same corridor guarantee. Only what they can see. See
  [RLG-159](../fragments/RLG-159.md).
- **The proof is a controlled approach**, because two statistics measured nothing first. A cruiser
  is parked in one lane, one car is put behind it closing, and the road is swept of everything
  else: the car moved 0.78 of a lane to go round and never occupied the same road, where the engine
  before the change moved 0.00 and drove straight on.
- **The police crashing into traffic does not reproduce here**, and that is recorded rather than
  claimed either way: zero cruisers put out by traffic over ninety seconds of pursuit, and zero
  again across five conditions from one star at half speed to five at nine tenths. That is a fact
  about the harness, not evidence about the device. `tools/twoway-test.py` is new.

<a id="v0-13-30"></a>
## [0.13.30] - 2026-09-08
- Added: **a radar detector for what is ahead.** Owner, 2026-09-07: a detector "for upcoming speed
  traps and traffic cops, just like it was done in the original Need for Speed games". Four bars
  under the mirror fill toward the nearest thing that can catch you, and they cover BOTH kinds the
  ruling names - a parked trap and a patrol still driving in traffic - which live in two different
  lists, so a detector that swept one would look finished while being half built.
- **It answers a measured problem rather than adding an ornament.** Losing a pursuit takes a long
  clean run, and at speed you meet the next trap before that run is finished, so the escape is hard
  to complete by driving alone. A warning turns that from a surprise into a choice: lift, or risk it.
- **The range is the spawn horizon**, written as such rather than as a number of its own. Police are
  placed no nearer, so every contact enters the cone from the far edge and closes - a longer reach
  would let one appear inside it with no approach. About a quarter of a mile: six and a half seconds
  of warning at 150mph. See [RLG-164](../fragments/RLG-164.md).
- **The beep rate is the reading.** The game is played with both thumbs on the road, so the interval
  carries the same number to the ears - nearly a second apart at the far edge, a chatter on arrival -
  and the pitch rises with it. It is a clean pip, deliberately not the loud-hailer bark, because a
  warning that sounds like a consequence teaches the wrong thing.
- It is **always fitted**. Whether it should be earned was left open in the ruling and is recorded as
  decided-for-now: an unlock needs a garage card, a price and a save field, none of which were asked
  for, and this is an aid to reading the road rather than a performance part.

<a id="v0-13-29"></a>
## [0.13.29] - 2026-09-08
- Added: **a pursuit you stay in earns heat by the mile.** Owner, 2026-09-08: "we can also
  increment 2 heat per mile while actively pursued." The other three earners are EVENTS - being
  seen, running a roadblock, putting a cruiser out - and a driver good enough to hold a chase open
  without any of them happening again was in a pursuit that could not get worse. This is the floor
  under that. It is charged against the road travelled rather than the clock, because a distance
  cannot be farmed by sitting still, and only while a live cruiser is actually on you.
- **It is slow on purpose.** At 150mph two points a mile is one point every twelve seconds, so a
  star costs fifty miles. Over a chase of a minute or two it adds a few points to what the events
  earn - pressure rather than a source. See [RLG-170](../fragments/RLG-170.md).
- Fixed: **the new check passed with the feature switched off**, and it was caught by falsifying it
  rather than by reading it. Its expected value came from the rate the engine reports, so at a rate
  of zero it expected nothing, got nothing, and called that agreement. It now asserts that the
  pursued arm earns heat the clean arm did not - the mechanism existing - before asserting the rate.

<a id="v0-13-28"></a>
## [0.13.28] - 2026-09-08
- Changed: **an incident is worth less, and cooling is slower by the same measure.** Owner,
  2026-09-08: incidents should be worth fewer points, so the stars climb more slowly and a hot
  pursuit lasts longer. Being seen by a new cop falls from 50 points to **20**, running a roadblock
  from 70 to **30**, and putting a cruiser out from 80 to **35**. A star is still 100 points, so a
  star is now **five sightings instead of two**.
- **The decay moved with them, and it had to.** At the old 8.33 points a second a 20-point sighting
  was undone in under three seconds of clean road, so cutting the earners alone would have stopped
  the level climbing at all. The lever is `HEAT_COOL`, which is stated in seconds to shed a star:
  **12 becomes 30**, so the total bleeds at 3.33 a second and five stars take two and a half minutes
  of clean road rather than one.
- **What an incident is WORTH in seconds of running is almost unchanged** - a sighting cost 6.0
  seconds of cooling before and costs 6.0 now, a roadblock 8.4 against 9.0, a takedown 9.6 against
  10.5. The economy keeps its shape; only its grain changed. See [RLG-169](../fragments/RLG-169.md).
- Fixed: **two pursuit harnesses were being killed by the run clock.** A car parked for a
  measurement reaches no checkpoint, so the sixty seconds a run starts with expire and the update
  stops - freezing the point total and the cooling clock mid-fall. It read as a broken tunable: 350
  points fell to 162 and sat there for two more minutes. `heat-test.py` and `heatpoints-test.py` now
  turn the clock off, and their cooling waits are computed from the tunable instead of hardcoded
  against the old one. That also cleared a super-cruiser check which was already red before this
  work.

<a id="v0-13-27"></a>
## [0.13.27] - 2026-09-08
- Added: **the wanted level is a point total, and it can fall to empty.** Owner, 2026-09-07:
  "instead of a single instance of something raising it one star, we could do heat POINTS... cooling
  off removes these points, so your wanted level can go down to empty as well." A star is 100 points.
  Being caught by a new cop is 50, running a roadblock 70, putting a cruiser out 80 - so **two
  sightings make a star** and a level is something you can be part-way through.
- **The old level could not reach empty.** It was an integer that moved in whole steps and floored at
  one, so there was no such thing as being clean. Zero stars is a real state now, and cooling bleeds
  the total away continuously - a star's worth every twelve seconds, after a three-second grace -
  rather than dropping a whole star at a time.
- **`heat` is still the star count and everything goes on reading it.** Trap density, when a roadblock
  may go up, when an interceptor is dispatched, how well a cruiser drives: a dozen readers, all
  untouched. Only its source moved. That is what made this a small change rather than a wide one.
- Changed: **the wanted-level stars are a flex row of five that fill by points** (RLG-163, arriving
  with the points because a gradient needs something continuous to draw). The star you are part-way
  through clips an orange gradient to the glyph, so it fills **left to right** and moves with every
  point. Every star is always present, which is what stops the row reading as vertical at one star
  and horizontal after.
- `heat-test`'s "and it stops at one" is **inverted, and deliberately so** - it asserted the rule the
  owner has replaced. Written up rather than quietly edited, because "the check went red and the fix
  was to change the check" is the shape that hides a regression.
- Added `tools/heatpoints-test.py`, watched failing with the old whole-star model restored.
  See [UNT-199](../fragments/UNT-199.md).
- **Known red and unexplained:** `heat-test`'s interceptor-dispatch check reads 0 supers. A direct
  probe shows interceptors dispatching normally - two of them, the first at about eight seconds - and
  the point decay works in its own harness, so both halves of the mechanism are demonstrably fine.
  Something in that section of that harness is specific to it. Written up rather than papered over.

<a id="v0-13-26"></a>
## [0.13.26] - 2026-09-07
- **Both halves of the owner's ruling were already true, and are now proved rather than assumed.**
  "They should only come from behind. The exception to this is when you pass a speed trap or the cop
  sitting at a roadblock. And the cop at a roadblock never chases you - that's just set dressing."
  Nothing in the engine changed; what changed is that it can no longer stop being true silently.
- Every cruiser records **where it came in relative to the player** and which source made it, logged
  from one place in the step rather than at the four spawn sites - so a fifth source cannot be added
  without appearing in the ledger. `patrol-test` asserts the **rule**, not a reading of the three
  spawners that exist today: a check naming them would go on passing the day a fourth is added in
  front of the car, which is the shape being ruled out. Watched failing with the radio dispatching
  ahead: two cruisers at +2,944 and +2,857.
- The roadblock's cruiser is a **part of the block** and never enters the pursuit array at all - every
  AI and collision loop skips it. Asserted now, so it stays set dressing.
- Fixed a check that was measuring luck: "a patrol car turns up in ordinary traffic" counted patrols
  **on the road at that instant**, and with a 4% share and usually one out that read 128 sightings on
  one run and **zero on the next**, on an engine spawning them perfectly well. It counts how many the
  road has *made*. Same mistake `ladder-test` made with the radio and the same answer - count the
  events, not the state. See [UNT-198](../fragments/UNT-198.md).

<a id="v0-13-25"></a>
## [0.13.25] - 2026-09-07
- Fixed: **a roadblock is in the mirror** - and the sweep the owner asked for found it was not
  alone. "Do a sweep of all things that should be in the mirror and make sure they are visible in
  it." The forward pass hands its painter **eight** kinds of thing; the mirror's list carried
  **five**. A roadblock you had just threaded, a **sign** you had just passed and a **repair crate**
  you had just missed all vanished the moment they were behind you.
- **The crate needed more than a place in the list.** It was deleted 1,500 units behind the camera
  and the glass sees 34,000, so it did not exist by the time the mirror could draw it - adding it
  changed nothing until the retention moved. The checkpoint boards had exactly this problem and were
  given exactly this fix; both read `MIRROR_BACK` now, so they cannot drift apart. A crate behind you
  is still not collectable, because that test is a proximity one.
- Each roadblock panel is projected at **its own lateral position** rather than the block's centre,
  because a roadblock *is* its spread across the road - drawn on the centre line a wall becomes a
  post. The cruiser standing at it takes its front sprite, which is the glass's rule for every
  vehicle.
- Added `tools/mirror-test.py`, and it **compares the two lists rather than holding its own.** A
  check naming the kinds it expects would be a second place to update and would go on passing the day
  a ninth thing is added to the road and forgotten in the glass - which is the fault being fixed. It
  asserts on what each view is *offered*, because that is where this went wrong: everything after
  the list was working perfectly. Watched failing with the roadblock removed again.
  See [UNT-197](../fragments/UNT-197.md).
- Known red and not caused by this: `bridge-test`'s water-symmetry check, unchanged since before this
  queue began.

<a id="v0-13-24"></a>
## [0.13.24] - 2026-09-07
- Fixed: **a destroyed car keeps its smoke and fire.** Owner, 2026-09-07: "when a car is destroyed -
  police, traffic, doesn't matter - the damage VFX go away. They need to keep their smoking fire,
  cause that is the state of things." It was true of all three kinds for **two different reasons**:
  taking a cruiser or a rival out clears its damage counter so it can be put back in play, so the
  plume stopped at the exact moment it was most earned - and **traffic never had the effect at all.**
  A lorry you had put into the barrier rolled to the shoulder looking showroom fresh.
- One helper answers "how hurt does this car look", and it reads the **wreck** rather than the
  counter. Both zeroings are correct for what they were written for and are untouched.
- Fixed: **the plume sat half a car too high on everything except the player.** Owner: "the fire and
  smoke don't look the same on other cars than it does on mine. Like layers are missing or its drawn
  location is wrong?" Both, from one mistake - the painter takes the car's centre and its *bottom*,
  and every caller but the player passed half a car height above that. It moves the origin **and**
  raises the clip that keeps smoke above the bonnet, so the bottom of the column was cut away too.
- Fixed: **the plume was drawn in front of the car.** Owner: "that's getting rendered in front of the
  car. We need it to be rendered behind it." The player has always drawn its smoke *before* its body,
  so the source is hidden - it is coming from an engine bay. `drawSprite` now takes a `beneath` hook
  called with the box at the moment it is known, rather than re-deriving the geometry or drawing each
  car twice.
- Added `tools/wreck-fx-test.py`. See [UNT-196](../fragments/UNT-196.md).
- Known flaky, re-run clean and **not caused by this**: `occlusion-test`'s lamp-clip check reported
  0 of 34,538 on one run and 399 of 38,415 on the next, unchanged. It needs a road with a brow under
  a lamp, and that is the road rather than the code.

<a id="v0-13-23"></a>
## [0.13.23] - 2026-09-07
- Fixed: **traffic behind you resolves out of the distance instead of appearing.** Owner,
  2026-09-07: "if you just stop the car and look at your rearview mirror you just constantly see
  traffic just popping into existence." The mirror draws 34,000 units back and the rear spawner was
  dropping cars **2,600 to 4,200 behind** - a third of the way up the glass, at a size you cannot
  miss.
- **Both halves, and neither works alone.** They go in at 7,000 to 11,000 now, and they **fade up
  over their first stretch of travel.** Simply spawning past the mirror's reach would have deleted
  the feature: a car has to *close* on you to arrive, and at road speed the closing rate is a few
  hundred units a second, so one dropped at the far edge would take the better part of a minute.
  This spawner exists to stop a stopped car sitting on an empty road.
- **The fade is measured in the car's own travel, not the gap to you.** The gap is the obvious
  quantity and the wrong one - when you are moving quickly it barely closes, so a fade keyed on it
  would still be half transparent a minute later.
- Added `tools/arrive-test.py`. It asserts cars go in well back, arrive transparent, become fully
  solid - **and still arrive**, which is the check that keeps the other three honest: spawning at
  the far edge of the glass would satisfy them perfectly and quietly remove the feature. Watched
  failing with the old distance and no fade: nearest drop 2,607 units, and **0 of 2,680 readings**
  caught a car mid-fade. See [UNT-195](../fragments/UNT-195.md).

<a id="v0-13-22"></a>
## [0.13.22] - 2026-09-07
- Fixed: **getting onto a bridge is a sharp ramp, a flat deck, and a sharp ramp.** Owner,
  2026-09-07: "a sharp ramp up for maybe a quarter of a mile, then absolutely flat for the duration
  of the bridge, and then for the quarter mile before transitioning into the next biome, the sharp
  ramp down." The tunnel is that shape inverted and moves with it.
- **The arrangement was already right and it was still wrong**, which is worth saying because the
  old comment here claimed exactly what the owner asked for. Measured on the shipping build: the
  climb took 0.34 of a mile, the deck *was* properly flat for 60% of the crossing, and the descent
  took another 0.34. Two things were off, and neither was the arrangement.
- **The ramp was a share of the crossing, not a length.** Sixteen per cent of however long the
  bridge happened to be - so a longer bridge got a longer climb, and "a quarter of a mile" could not
  be expressed at all. It is a distance now; a longer bridge gets more deck instead.
- **And the ramp was almost entirely easing.** The smoothing width was 0.55 of the ramp itself, so
  the slope spent the whole climb rising to a peak and falling away and was never steady - a soft
  hump rather than a ramp. Height gained per step ran **0.50, 7.26, 9.12, 4.17**; a bell. With the
  corners taken off a constant slope instead, **5 of 6 ramp steps now sit within 15% of the
  steepest, against 3 of 8 before.**
- **The deck height is deliberately unchanged** - 42.4 against the old 42.3, and the bore at -23.3
  against -23.7. A constant ramp gains more over the same ground, so `rise` came down to hold the
  summit where it was; raising the bridge was not what was asked for.
- `bridge-test` gained the profile checks and they were watched failing on the old build, on both
  places at once. Two earlier versions of the shape check were discarded first: trimming a fixed
  number of corner steps reads the tunnel and the bridge as different shapes, because where the
  rounding falls on a 40-step grid is arbitrary. See [UNT-194](../fragments/UNT-194.md).
- Known red and **not caused by this**: `bridge-test`'s "water to left AND right in comparable
  amounts" fails identically with this change stashed.

<a id="v0-13-21"></a>
## [0.13.21] - 2026-09-07
- Removed: **the PIT manoeuvre.** Owner, 2026-09-07: "I don't think there is enough collision
  granularity to really do the PIT justice reliably... just have the main mechanism for losing the
  police and your heat level outrunning them and leaving them behind." It was decided on the single
  frame two bodies overlapped, and a contact that lasts a frame cannot tell a deliberate move from a
  lucky one. Writing its check made that plain rather than proving it. A cruiser is now just a car
  you can hit, which is what [RLG-131](../fragments/RLG-131.md) asked for in the first place - the
  PIT was its one exception.
- **You can still take one out.** Owner: "the police can still be taken out of the chase if their
  health is reduced to zero, so you can still lead them into collisions or hit them yourself... the
  dirty alternative to simply outrunning them." Barrier and traffic damage are untouched.
- Fixed: **a cruiser you have left behind no longer holds your wanted level up.** One counted as
  chasing you until it was *culled*, 34,000 units back - so a car five seconds off your tail and
  falling further away every second held the cooling clock at zero. Measured: thirty seconds of
  running, half flat out in a car 40mph faster than anything behind it, and **the wanted level never
  came down one level.** A cruiser more than `LOST_AT` away has lost you, and the radio does not
  reinforce a pursuit you have already broken.
- **Escapes still need you to avoid meeting new police.** With traps and patrols on the road ahead,
  running flat out trips fresh ones faster than the clock can run. The cooling now *starts* where it
  never did; finishing it is a matter of the road. That is what a radar detector would answer.
- `ladder-test` had to give ground, and it is written up rather than quietly relaxed: the cap is a
  pure function of the wanted level and is asserted; how many cars come out of it in a window is not,
  because the population is at most three and the level keeps being re-earned while driving fast.
  Three attempts to assert the observed numbers rung by rung all produced a gate that went red on the
  road. **Revisit it when the wanted level becomes granular points.** See
  [UNT-193](../fragments/UNT-193.md).
- `tools/pit-test.py` is deleted with the feature it covered.

<a id="v0-13-20"></a>
## [0.13.20] - 2026-09-07
- Added `tools/pit-test.py`, the last of the three rows the police audit left uncovered. The PIT
  needs three conditions together - alongside, steering into it, and above 0.62 of top speed - and
  this asserts that a takedown happens on **exactly** the contacts where all three hold.
- **Staging the manoeuvre was tried first and abandoned, and that is the finding.** A harness can
  place a cruiser and drive at it, but the decision is made on the single frame two bodies overlap, a
  staged cruiser is a *real* one whose chase AI moves it between anything the harness sets, and one
  glancing contact locks out the next second with the mercy window. **Three runs of one unchanged
  build gave three different answers**, including one where the manoeuvre and its opposite came back
  inverted. A gate that flaky is worse than no gate.
- So the engine records the three conditions **as it evaluated them** on every contact with a
  cruiser, and the check asserts the rule over all of them. Individual contacts land where the timing
  puts them; the implication holds either way.
- **The ledger records what happened, not what should have.** `pit` was first written as the
  predicate copied out of the line below it - which would have made this a test of the harness's own
  arithmetic, green whatever the branch did. It is set inside the branch instead. Watched failing
  with the speed and steering conditions removed: **61 PITs against 15 contacts that qualified.**
- A run that produces no qualifying contact is reported rather than failed - about one in three does,
  and a gate that goes red on the traffic is the failure mode this project guards against - but it
  says plainly that only the negative direction was tested. See [UNT-192](../fragments/UNT-192.md).
- With this, the police audit's Finding 3 is closed: the bust, roadblocks, the PIT and the escalation
  ladder all have checks.

<a id="v0-13-19"></a>
## [0.13.19] - 2026-09-07
- Added `tools/roadblock-test.py`, and **something that can see a roadblock in the first place.**
  Nothing exposed the array, so the police audit could only infer one existed from a boolean about
  the road immediately ahead - a stage of the pursuit nobody could count was a stage nobody could
  test.
- It asserts that a roadblock goes up on its own at heat 3, that it spans the road rather than being
  a chicane, that a cruiser is parked at it, that it appears well ahead rather than on top of you,
  and that **the opening is wider than the car**.
- **The opening is measured off the panels, not off the field that says where it should be.** `gapX`
  records where the gap was meant to go; the panels are where it actually is. A tiling bug that
  closed the opening would leave `gapX` perfectly correct and the game unplayable, and a check
  reading `gapX` would never see it. Watched failing with the opening tiled shut: the measured gap
  read **0.02 against the car's 0.265**, while every other assertion stayed green. See
  [UNT-191](../fragments/UNT-191.md).

<a id="v0-13-18"></a>
## [0.13.18] - 2026-09-07
- Added `tools/bust-test.py`, closing the first of the three uncovered rows in the police audit's
  Finding 3. Stopping with a cruiser alongside ends the run, and **nothing else does**: it asserts
  the bust on a stopped car beside a cruiser, no bust on an empty road, and no bust with HOT PURSUIT
  off. The middle case is the one that matters - a bust that fired on stopping alone would pass the
  first check and ruin the game.
- The engine records **why** the last wreck happened. During a run the flash says WRECKED whatever
  caused it, so from the outside a bust and a head-on collision are the same event - fine for a
  player, impossible for a check. Recorded, not shown: whether the flash should say BUSTED is the
  owner's call and is not made here.
- Watched failing with the bust disabled. See [UNT-190](../fragments/UNT-190.md).

<a id="v0-13-17"></a>
## [0.13.17] - 2026-09-07
- Fixed: **a car parked on the shoulder no longer judders.** Owner, 2026-09-07: "When parked
  (stopped) on the shoulder of the road, the car still shutters like I'm driving offroad but I'm
  stopped. It shouldn't do that." The off-road shake was a **constant** - being off the tarmac was
  the whole test - so a parked car shook exactly as hard as one crossing the verge at 90mph. With
  nothing on screen moving, that reads as a fault in the picture rather than as rough ground.
- It scales with speed now: full strength by about 20mph, **nothing at a standstill**. The same
  factor applies to the barrier scrape, because resting against a wall is not scraping along one.
- **What the verge costs is untouched.** The off-road speed ceiling and the scrub are unchanged;
  this is only about what it looks like.
- Added `tools/verge-test.py`, watched failing with the constant restored. **Two of its own checks
  were wrong first and are worth recording:** it sampled before the car had finished slowing from the
  launch, and reported the fix broken on a build where it worked; and it tried to assert the off-road
  speed ceiling using the harness's own speed setter, which writes straight past the acceleration
  model the ceiling lives in - it read 13,280 against a 4,200 limit that was working perfectly. That
  assertion measured the harness, not the game, and has been removed rather than tuned. See
  [UNT-189](../fragments/UNT-189.md).

<a id="v0-13-16"></a>
## [0.13.16] - 2026-09-07
- Added: **the third source of police, and it is the one a wanted level actually buys.** Owner,
  2026-09-07: "Police are generated from 3 sources. Traffic cruisers engaging after pass, speed traps
  raising heat, and random timers from rear spawner." The first two were built; the third,
  `spawnCop`, **had existed for a long time and was never called from anywhere.** So nothing ever
  arrived because your wanted level was high, and heat four summoned exactly what heat two did.
- Heat now decides **how many** the radio will keep on you - nobody at heat 1, one more per level to
  a ceiling of three - and **how often** it sends them.
- **It reinforces a pursuit; it does not start one.** The first build dispatched on heat alone and
  `heat-test` caught what that costs: "outrunning them cools the wanted level" went red, still at 4
  after fourteen seconds. Cooling needs a stretch with nothing chasing you, and a fresh car every few
  seconds resets that clock forever - **heat could never come down and a bad run had no way out but
  the wall.** Something must already have eyes on you before the radio adds to it, which is also what
  a radio *is*: a dispatch goes to a pursuit in progress.
- The radio has **its own quota**, and that mattered: counting every chasing cruiser against the cap
  killed this source a second time, because at speed a trap catches you every few seconds and two or
  three trap cars sit on you almost permanently. Measured - radio cars peaked at **zero on every rung
  of the ladder** while the cap said three. A separate hard ceiling of four keeps all three sources
  from piling up.
- Every cruiser now records **which of the three sources made it**. A count that lumps them together
  cannot see a wanted level doing its job, which is precisely how the rear spawner went missing.
- Added `tools/ladder-test.py` — **the check whose absence let this happen.** Nothing had ever asked
  whether heat *does* anything. It reads cars actually on the road rather than the cap they are drawn
  from, and it was watched failing with the spawner un-wired again: 0 at every level, against 0-1-2-2
  now. This closes the fourth row of the audit's Finding 3; the bust, roadblocks and the PIT are
  still uncovered. See [UNT-188](../fragments/UNT-188.md).
- Known flaky, not caused by this: `heat-test`'s super-cruiser dispatch depends on four unbroken
  seconds above 150mph and reported 0 supers on one run and 4 on the next, unchanged.

<a id="v0-13-15"></a>
## [0.13.15] - 2026-09-07
- Fixed: **a police car is only as fast as the same car in your hands.** Owner, 2026-09-07: "I want
  the police cruiser to have the same stats - the fact that a supercar can outrun it is the point,
  and why the super cruiser exists." The chase clamped every cruiser to `AI_TOP`, a flat 180 of the
  player's 200, and never asked the car what it could do. **Measured before: a chasing cruiser
  reached 169mph while the CRUISER in the garage tops out at 142.** That is an NPC in a better
  version of the same car, against the standing one-physics ruling.
- **It cuts both ways, and that is the part worth reading.** The patrol car loses 38mph and can no
  longer stay with a supercar - the owner's point rather than a regression. But the flat ceiling was
  also **holding the interceptor back**: a SUPERCRUISER is a 190mph car and was being run at 180. It
  gets its ten back. The gap between the two police cars is now the reason the second one exists:
  **142 against 190**, where before it was 180 against 180.
- Only the two force cars changed. `AI_TOP` still governs every other AI car on the road, and the
  rubber band remains the one named exception to one physics for every car.
- `patrol-test` gained the check, and it asserts the **invariant** rather than the ceiling: no
  cruiser ever exceeds its own body's `vmax` over a whole pursuit. Coaxing one car up to its limit
  means fighting a chase AI that backs off, boxes and peels away - three attempts measured 64, 89 and
  102mph and proved nothing. Watched failing with the flat ceiling restored: the patrol car ran to
  **173mph against its 142**, and the interceptor was pinned at exactly 180 against its 190.
- Findings 1 and 3 of the police audit are untouched and still open. See
  [UNT-187](../fragments/UNT-187.md).

<a id="v0-13-14"></a>
## [0.13.14] - 2026-09-07
- Added: **police patrol in ordinary traffic.** Owner, 2026-09-07: "We should put police into the
  traffic as standard vehicles. They just don't engage you if hot pursuit has turned off. If hot
  pursuit is turned on then these random police in the traffic will engage you if you pass them going
  beyond the speed limit." Four per cent of the cars ahead of you, with a Civilian at the wheel, the
  bar dark, cruising at the limit like anything else.
- **It drives as traffic and then stops being traffic.** While patrolling it is an ordinary car in
  the traffic array - it sits in a lane, merges round slow cars, takes no interest in you. When it
  engages it is moved into the `cops` array, where the chase, the lunge, the siren, the scatter and
  the lights already live. **Nothing about chasing was written twice.** It is the same shape the
  speed trap already uses: a dormant cruiser that wakes.
- **Passing it is the trigger, not being near it.** The engagement fires on the frame you go from
  behind it to ahead of it, so a patrol you never catch never looks at you.
- **Four per cent and not two, which is what "standard" means.** At two, a thirty-second drive turned
  up either one patrol car or none - a vehicle you meet once every couple of minutes is an event, not
  ordinary traffic. The ambulance stays at two *because* it is meant to be rarer than that.
- **The super cruiser is not in this and must not be.** Owner, same day: "the super cruiser is still
  omitted from regular traffic, it only comes out when you are triggering its conditions."
- **Patrols spawn ahead only**, which is the one body deliberately not in both spawn tables. A car
  spawned behind you must be quicker than you or it never arrives, and a police car doing 130 to
  catch up is either already chasing you or breaking the law it is there to enforce. It would also
  trip the speed trap, which would then be pulling over the police.
- A patrol is exempt from the speed trap and from a cruiser's retargeting, the same way an ambulance
  on a call is - or the force spends the run arresting itself.
- Added `tools/patrol-test.py`, and **both guards were watched failing**: with the pursuit switch
  ignored, blasting past with HOT PURSUIT off starts a chase; with the limit ignored, a legal pass
  starts one. Two of its own checks were also caught proving nothing and fixed - one read the drivers
  at a moment when no patrol was on the road, and one "passed legally" case never actually overtook,
  because the patrol was faster than the player. See [UNT-186](../fragments/UNT-186.md).

<a id="v0-13-13"></a>
## [0.13.13] - 2026-09-07
- Fixed: **a car that signals a lane change can now finish it.** The merge decision re-ran on every
  frame a car was held up - *including* the frames where it had already announced a move and was
  waiting out its own indicator - and rewrote the wait with a fresh 1.1 to 1.8 seconds. The countdown
  then took one frame off a number that had just been reset, so **it could never reach zero.** Only
  the roughly one driver in five who does not signal ever merged at all. This is why the road silted
  up behind slow cars in a way [RLG-032](../fragments/RLG-032.md) was supposed to have ended: the
  merge logic was right and could not run.
- Fixed: **the commit-time re-check was given a lane index where it wanted a road position.**
  `laneClear` and `wouldBlock` compare against `o.x` and `playerX`; this passed `want`, a lane number
  from 0 to 3. It is the same confusion `scatter` carries two long notes about, and it survived
  because the branch it sits in could not be reached - **one defect was hiding the other.**
- Changed: **a Racer does not queue.** Owner, 2026-09-07: "it shouldn't queue up behind anybody, it
  should always work to get around obstacles and continue as fast as it can." Three numbers, all the
  same impatience: how far below its own pace it tolerates before looking for a lane (99% against
  86%), how much faster that lane must be to be worth taking (40 against 200), and how soon it looks
  again after being turned down (under a second against several). **Nothing makes a Racer's car
  quicker** - the vehicle still caps the driver, which is the rule the whole fleet is built on.
- **The check that would have caught this could not have.** `merge-test` passed the entire time: both
  kinds of merge landed in one counter, so the total merely fell from 30 completed moves to 18,
  comfortably over the 12 it asks for. It now counts **indicators started** against **moves
  completed**, and the two states are three orders of magnitude apart - 42 started with 26 completed
  after the fix, against **13,786 started with 5 completed** with the defect put back.
- The ambulance's siren check is an assertion again, and it now also asserts that it works its way
  **past** you. See [UNT-185](../fragments/UNT-185.md).
- Known flaky, measured on both sides and **not caused by this**: `traffic-test`'s corridor check
  fails about one run in three on the unchanged engine too (1/180 samples, 0.332 against this
  change's 0.327), its amber count varies with the hour and the place, and `drive-test`'s nitrous
  check passes vacuously whenever the button does not take. Written up separately.

<a id="v0-13-12"></a>
## [0.13.12] - 2026-09-07
- Added: **an ambulance comes through on a call.** Owner, 2026-09-07: "there's a chance for it to
  spawn behind you in emergency mode. It's given the racer personality so it wants to go as fast as
  possible and the siren works just like the police version as far as moving people out of the way."
  It arrives behind you on its own clock - one every ninety seconds to three minutes, never two at
  once - with the bar lit, the siren sounding and a Racer driving.
- **It could not use the spawner that puts cars behind you.** That one only runs after you have been
  slower than the flow of traffic for two seconds, because it exists to stop a stopped car sitting on
  an empty road. An ambulance on a call does not wait for you to dawdle, so it is an event on its own
  clock rather than a type in a table.
- **Nothing was made faster to let it hurry.** `RACER` chooses a target and the vehicle caps it, so
  the ambulance gets its own 0.55 and no more - the rule the whole fleet is built on
  ([RLG-042](../fragments/RLG-042.md)), and an emergency is not an exemption from it.
- The siren is **literally the police call**: `scatter` at 90% from where the ambulance is. It has
  taken an origin and a lateral position since the NPC cruisers were given sirens, so there was
  nothing to build beyond asking it. The authority to move traffic comes from the **bar**, and this
  has one; it has no `force`, so it is not police and never becomes a pursuit.
- Fixed: **the bloom under a light bar took its colours from the vehicle instead of from the police.**
  It was hardcoded blue-and-red, which painted one side of an ambulance police blue. A medical scheme
  is red at both ends and now says so. The wash below it had been fixed for exactly this and this
  half was missed.
- Fixed: **the police no longer engage an ambulance.** Owner: "it should go without saying." It did
  not - a trap arms on anything over the limit, and a cruiser retargets onto the nearest thing over
  0.44 of top speed, and an emergency ambulance is faster than both **by design**. A patrol would have
  dropped a real pursuit to chase the ambulance it was making way for. The test is the **bar**, not
  the body, so it stays true for whatever carries one next.
- **Known limitation, and it is a defect this exposed rather than one it caused:** the ambulance often
  queues behind the player instead of going round. A car that signals a lane change never completes
  it, because the merge decision re-runs every frame and resets the signalling wait before it can
  elapse. That is every signalling car in the game, not this one. It is fixed in the next unit. See
  [UNT-184](../fragments/UNT-184.md).

<a id="v0-13-11"></a>
## [0.13.11] - 2026-09-07
- Added: **the ambulance is ordinary traffic now, and you can finally meet one.** Owner,
  2026-09-07: "It's a standard traffic vehicle in nonemergency mode." It had a body record, a rig,
  a light bar, a siren and a place in the garage, and **neither traffic table listed it** - so the
  only way to see an ambulance was to drive one. It takes two per cent out of the van's share in
  both tables, because it *is* a van; the road gets a more varied set of big slab-sided vehicles
  rather than more of them. No bar, no siren, no hurry: this one is going back to the station.
- Changed: **it is a little quicker than the van**, on the owner's word - 0.55 against 0.50 as
  traffic, 0.47 against 0.43 in your hands. **Both tables moved together.** `TYPE_VMAX` says what a
  vehicle does as traffic and `BODY.vmax` says what it does when you are driving it, and a vehicle
  that disagrees with itself about its own top end is the fault [RLG-042](../fragments/RLG-042.md)
  exists to stop. `API.topOf` now returns both at once so a check can assert the pair.
- Cleanup: **how big a vehicle is, stated once.** The width and length chains were written out in
  full in three places - both spawners and `API.parkTraffic`, whose own comment claims it builds a
  car "with the same fields the spawner gives it". A body added to only one of them would have been
  the right vehicle ahead of you and a saloon-sized one behind, and nothing in this engine would
  ever have printed the difference.
- Added `tools/ambulance-test.py`. See [UNT-183](../fragments/UNT-183.md).
- Known red, and **not caused by this**: `collide-test.py` fails two of its checks on `main`, and it
  fails them identically with this change stashed. It is written up rather than folded in here.

<a id="v0-13-10"></a>
## [0.13.10] - 2026-09-07
- Changed: **the barrier holds you against it, and it no longer steers for you.** Owner,
  2026-09-07: "I don't want the player car to bounce back into the roadway. If you hit the playable
  edge right now it pushes you back in." One line inside the off-road block, `targetX = playerX*0.7`,
  parked the steering target three tenths of the way back toward the middle - so the car drove itself
  off the barrier. Worse, it wrote that target on **every frame the wall was touched**, which threw
  away whatever the thumb had just asked for: against the edge, the player was not the one steering.
  Measured, it kept the car from ever reaching the wall at all (it pinned at 0.94 of the 1.13) and
  then carried it 0.16 back toward the middle once the wheel was released.
- The aim now follows the car - `targetX = playerX`, the same idiom this engine already uses after a
  shunt. You rest against the barrier until you steer off it yourself.
- **Nothing was relaxed about what the verge costs.** `offRoad` still caps the whole thing at
  OFF_SPD for as long as you are outside the tarmac, and the hard scrub still runs for every frame
  you press *into* the wall rather than along it. What went is the shove, not the punishment - and
  the new check asserts the ceiling as well as the hold, because deleting the off-road block would
  otherwise satisfy the first two assertions while giving the verge away for free.
- Added `tools/wall-test.py`, watched failing against the old line. See
  [UNT-182](../fragments/UNT-182.md).

<a id="v0-13-9"></a>
## [0.13.9] - 2026-09-07
- Fixed: **the scenery half of the report, and the traffic was never the thing painted wrongly.**
  Owner, 2026-09-07: "in the jungle and the road curving up and away hard so that the incoming
  traffic were behind the scenery, but rendered on top." The trees were not painted over. **They
  were never painted at all.** Three guards at the top of the road walk drop a slice whose geometry
  is degenerate, and each one also skipped that slice's roadside while still emitting the CARS
  standing on it - so a distant car appeared in a gap where the jungle should have stood in front
  of it.
- Measured before it was believed: on three fresh jungle roads the inversion guard took **70 to 94
  slices of 151 in a single frame**, the whole far half of the draw, and **every one of them was
  inverted by less than one pixel** (median 0.28 to 0.42, largest 0.71). That is the road flattening
  toward the horizon, not a hill. It is the same sub-pixel failure [RLG-041](../fragments/RLG-041.md)
  found for the cars, still live for the scenery because only the emit was moved out of the guards.
- The roadside now leaves those guards with the cars, and `crestGate` - which `drawScenery` already
  calls, once per object - is the only thing that hides it behind terrain. Slices drawing their
  roadside went from about 55 of 151 to **149 of 151**; the two that draw none are under the camera
  and have no valid projection to place anything with.
- **It costs frames, and that is the owner's call rather than this unit's.** The picture now holds
  scenery it was dropping, and drawing it is real work: the swamp fell from 60.0-60.4 fps to
  48.0-55.2, ranges that do not overlap, and the forest sits at or below its old floor. Measured in
  headless desktop Chromium, so **a phone will be worse.** Nothing is tuned here to claw it back -
  what to cull at distance is [RLG-073](../fragments/RLG-073.md), which is still open.
- `occlusion-test` gained the check that would have caught this, and it was watched failing with the
  defect put back: **331 of 331 inverted slices drew no roadside.** It prints how many frames
  actually inverted, and says plainly when a run proved nothing, because about half of the roads
  generated here never invert at all. See [UNT-181](../fragments/UNT-181.md).

<a id="v0-13-8"></a>
## [0.13.8] - 2026-09-07
- Fixed: **everything on one segment is painted far to near, not in the order the arrays were
  built.** Owner, 2026-09-07: "cars are rendering through scenery and the checkpoint signs." A bucket
  is one segment of road, and traffic, police, gantries and roadblocks went into it in whatever order
  `items` happened to be assembled - nothing sorted it. So a car two hundred units BEHIND a checkpoint
  gantry could paint straight over the front of it. The road pass already walks far to near, which is
  what makes the order between buckets right; the inside of a bucket now follows the same rule.
- Note: **only half the report is confirmed fixed.** The gantry half has a found and understood cause
  above. **The scenery half is NOT reproduced**: scenery is drawn per segment right after that
  segment's bucket, which makes it paint OVER a car at the same depth rather than under it - the
  opposite of the symptom. It may share the cause and be fixed by the same sort, or it may be a
  second fault. It is not claimed as fixed.

<a id="v0-13-7"></a>
## [0.13.7] - 2026-09-07
- Changed: **hardiness is the material; health is what comes out of it.** Owner, 2026-09-07: "I can't
  imagine a standard sedan having less hardiness than a supercar. There might have to be a second
  variable other than mass." Then: "instead of hardiness being health itself, we just have the final
  output of that formula being health, and hardiness could be that variable that represents light
  shell versus steel box." **`health = 100 * sqrt(mass / 1400) * hardy`**
  ([RLG-131](../fragments/RLG-131.md)).
- Note: **the old table proved the point.** On mass alone a SALOON came out at 103 and a STALLION at
  104 - a family saloon out-toughed by a supercar because the supercar weighs forty kilos more. Mass
  says how much car there is; it cannot say what the car is made of.
- Note: **the values.** Carbon formula tub 0.70, supercar shell 0.85, roadster 0.95, ordinary car
  1.00, coupe 1.10, saloon and cab 1.15, muscle car and vans 1.20, pickup on its ladder frame 1.25,
  artic 1.30. Resulting health runs formula 49-52, supercars 87-90, saloon 118, muscle 133, cruiser
  177, lorry 411 - and a saloon now sits comfortably above every supercar, which is what the owner
  said it should.
- Note: **both numbers stay hidden.** Neither is drawn, and neither is in the fleet sheet.

<a id="v0-13-6"></a>
## [0.13.6] - 2026-09-07
- Fixed: **a police car wore two badges on the nose.** Owner, from the saved fleet renders,
  2026-09-07: "there's two badges on the front." The `else if` correctly kept the GENERIC badge off a
  cruiser, but the branch above it fires for any car declaring a `marque` - and the cop branch at the
  foot of the same painter draws the star as well. `cop` is excluded from both branches now, so that
  branch owns the star wherever the sprite was built.
- Note: **it only ever appeared in the fleet sheet, which is why it survived.** The game builds
  `FRONT_SP.cop` with no `marque` at all, so the first branch never fired there. The sheet builds
  every front with `marque: rs.rear`, and a cruiser's `rear` is CRUISER - so the sheet, and only the
  sheet, drew it twice. **A defect that lives only in a generated document is invisible to every
  harness that drives the game.**

<a id="v0-13-5"></a>
## [0.13.5] - 2026-09-07
- Fixed: **police hardiness follows the car they are a variant OF, not their own mass.** Owner,
  2026-09-07: "I always saw the cab and cruiser as a variant of the saloon." The ruling was 1.5x
  "their standard car counterpart" and the counterpart is now declared rather than guessed:
  **cruiser 155** from the saloon's 103, **super cruiser 159** from the Matador's 106, where taking
  1.5x their own mass had given 171 and 169 ([RLG-131](../fragments/RLG-131.md)).
- Added: **`kin` on the BODY record - what a car is a variant of.** The codebase already half-said
  this: `rigBody` maps `sedan2` onto the saloon's numbers with the note "the variant borrows the
  saloon's numbers", and the super cruiser's own comment has called it a MATADOR the force took since
  it was built. `kin` writes it down instead of leaving it implied by a rig name. CAB declares SALOON
  too, though its own hardiness is still mass-derived - it is not police, so the 1.5x does not apply.

<a id="v0-13-4"></a>
## [0.13.4] - 2026-09-07
- Added: **wrecked traffic slides aside and stays as a hazard until it is culled.** Owner, 2026-09-07,
  answering their own question: "hazard until culled", and "they can't spin out because we can't
  render that - we only have the rear and the front. So they just slide to the side and come to the
  rest with the rear view as normal." No respawn: a two-second penalty is a RACING idea and traffic
  has no position to lose, and a car that vanished and reappeared is the complaint RLG-041 took
  eleven versions to fix ([RLG-131](../fragments/RLG-131.md)).
- Note: **the no-spin constraint was already true and never enforced.** `ang` is written on wrecked
  rivals and cruisers and is **read by nothing** - three writers, no reader - so the spin those two
  were supposedly doing has never been visible. Nothing here adds a fourth writer.
- Added: **hardiness, a hidden per-vehicle stat.** Owner: health "possibly based on mass", with the
  cruiser and super cruiser at 1.5x, and "this hardiness stat should never be exposed to the player."
  Nothing draws it and it is deliberately absent from the fleet sheet.
- Note: **mass drives it, but not linearly.** The fleet runs 690kg to 14,000kg - twenty to one -
  so a straight mapping would make an artic unkillable and a formula car paper. The square root
  compresses that to about four and a half to one: formula 70, saloon 103, van 131, lorry 316,
  cruiser 171.
- Fixed: **a check that hard-coded the old 100-point threshold.** It hit a cruiser three times for 45
  and expected it down; with 171 health that stopped being true on working code. It asks the engine
  for the car's own hardiness now.

<a id="v0-13-3"></a>
## [0.13.3] - 2026-09-07
- Added: **police are taken out by the damage system, not by one hit.** Owner, 2026-09-07: "this
  damage system should apply to taking out police as well." A cruiser used to go down on a single
  call to `wreckCop`, whatever hit it and however hard - a barrier, a traffic car and a PIT were all
  identical. It carries `dmg` now, is taken out at a hundred, and serves `WRECK_SECS`
  ([RLG-131](../fragments/RLG-131.md)).
- Note: **the reward still belongs to the takedown, not to the hit.** Heat, the nitrous and the
  CRUISER DOWN flash fire when the car actually goes down, so leaning on a cruiser four times pays
  once. **The PIT still puts one out outright** - it is a deliberate manoeuvre at speed, and that is
  the point of it being harder than a shunt.
- Added: **every car wears its own damage.** Owner: "the visual effects of damage/health should apply
  to every car now." The smoke and flames were written inside `drawPlayer` reading the global `dmg`,
  so only the player could show them - the same shape the NOS flame had. Lifted into one `damageFx`
  that rivals and cruisers also call, with the drawing unchanged.
- Fixed: **the extraction leaked a local and threw on every frame.** `lean` is the player's roll into
  a corner and only the player has one; it went out as a parameter defaulting to zero, because an
  upright sprite's plume leaving its nose is correct rather than a compromise. Caught by a page error
  in a probe, not by the eye.

<a id="v0-13-2"></a>
## [0.13.2] - 2026-09-06
- Added: **damage is a factor of which end took the hit.** Owner, 2026-09-06: "if you have a front
  impact it's the worst, followed by side impacts. Then finally impact to your rear is the least
  damaging." Front 1.00, side 0.55, rear 0.30, blended by how square the hit was so a car sliding
  from alongside to in line never steps ([RLG-131](../fragments/RLG-131.md)).
- Note: **the geometry was already being measured and then thrown away.** `impactWith` computes
  `square` (how nose-to-tail) and `dz` (which side of you the other car is on) for the shove, so
  front and rear were always distinguishable - the severity just never asked. It read
  `0.25 + square*0.75`, which made a car running into your back exactly as costly as you running
  into its back ([RLG-131](../fragments/RLG-131.md)).
- Changed: **one collision now scores the two cars differently.** Running into the back of a rival is
  YOUR front and THEIR rear, so the same impact costs you the most it can and them the least.
  Measured through the real function: a car rear-ending you at speed takes 0.91 while you take 0.35
  ([RLG-131](../fragments/RLG-131.md)).
- Note: **the three numbers are tunables with committed defaults, not constants.** The ORDER is the
  ruling; the balance is the owner's to judge on a device, and `impact-test` asserts the order rather
  than pinning the values.
- Added: **`tools/impact-test.py`**, which goes through the real `impactWith` rather than
  reimplementing it - the function MOVES BOTH CARS as well as scoring the hit, so it cannot be called
  twice and compared. Watched failing on all four checks with the ordering inverted.
- Note: **`collide-test` fails two checks and did so before this change.** "A car in the same place
  as you is a hit" returns an empty result, and the half-width check measures 0.0094 against an
  expected 0.2230. Confirmed pre-existing by running it on the previous build. Not diagnosed here -
  it is either a stale harness or a real collider defect, and it wants its own unit.

<a id="v0-13-1"></a>
## [0.13.1] - 2026-09-06
- Fixed: **a wreck penalty no longer freezes the world.** Owner, 2026-09-06: "when the player gets
  the 2 seconds penalty, the world shouldn't freeze. The world should continue." The step used to
  `return` early, skipping the biome, the weather, the traffic, the police and `stepRacers` - and its
  own comment said so: *"the world stops, the clock does not"*. **So two seconds of penalty cost the
  clock and nothing else: the field sat frozen exactly where it was and you lost no ground at all**,
  which is the opposite of a penalty. Measured after: rivals cover about 7,700 units while the player
  covers zero.
- Added: **a rival keeps a health bar and serves the same two seconds.** Owner: "we need it so they
  can get damaged too and incite the same 2sec penalty." Damage accumulates on a rival as it does on
  the player, and at a hundred it wrecks for `WRECK_SECS` - the same constant, so the two penalties
  cannot drift apart.
- Changed: **a rival gets an invulnerability window, because the player has one.** The collision
  tests run every frame while two cars overlap, so damage taken straight from them would wreck a
  rival in a handful of frames of contact. `r.iframe` mirrors the player's.
- Changed: **leaning on you is no longer free.** The note beside the player-versus-rival contact said
  *"only you take damage, because you are the only one keeping a health bar"* - a rival now takes the
  same severity from the same impact. It is still the lightest hit on the road, because a rub between
  two racing cars is the sport.
- Note: **the clock has one owner again.** It was decremented inside the penalty branch precisely
  because the early return skipped the clock's own code. With the frame running to the end, both
  would have ticked it and the countdown would have run at DOUBLE SPEED for exactly two seconds.
  Measured at 1.00/s through a penalty against 1.00/s driving normally.
- Added: **`tools/penalty-test.py`**, which asks whether the FIELD MOVED while the player did not,
  rather than whether time passed. Watched failing with the freeze restored: rivals move 0 units.

<a id="v0-13-0"></a>
## [0.13.0] - 2026-09-06

**Slice checkpoint. The rivals slice closes.** 0.12 ran nine patches and they divide cleanly in
two: the ambulance and the class gate that made it coherent, then the rivals gaining a gearbox and a
bottle. The queue now turns to the tyre screech, so the minor moves and the patch count resets.

- Added: **rival sports, super and formula cars carry nitrous.** Owner, 2026-09-06: "rival sports
  cars, supercars, a formula cars should all have nitrous too. So they need to have the AI behavior
  to use it appropriately. They will also compete with you over the pickups, which will award NOS to
  them the same way it does you. They should also get the trickle fill of NOS as well." All four
  parts are built ([RLG-038](../fragments/RLG-038.md)).
- Changed: **`hasNos()` stopped being a question about the player.** It read `optBody` throughout, so
  it could only answer for whoever held the wheel. It is `hasNosFor(body)` now, and the class list is
  unchanged - a rival and a player in the same model can never disagree about whether that car has a
  bottle.
- Changed: **the bottle's three numbers are named and shared.** The drain, the trickle and the
  minimum to open were inline constants inside the player's own step. A rival refilling at its own
  rate would have been a second bottle, and the ruling is one physics for every car
  ([RLG-038](../fragments/RLG-038.md)).
- Added: **the AI decides when to spend it, and each driver decides differently.** A boost is only
  taken when there is something to chase or hold off, when the car is already near its ceiling, and
  while keeping a reserve. `nerve` is set per DRIVER at the grid, never per body - **measured at 7.7%
  of the time with the bottle open, max 9% across the field**.
- Added: **a crate is first come, first served.** The rival test runs BEFORE the player's, because a
  crate the player has taken is already marked and skipped - checking rivals second would mean the
  player always won a tie. It pays only what that car can use, exactly as it does for you.
- Added: **the blue flame is on rivals too, and it is the same flame.** It already existed but was
  written inside the player's own painter, so only the player could ever wear it. Lifted into one
  `nosFlame` both call, with the geometry byte-identical.
- Added: **you hear a rival's bottle, from where the car is.** Owner: "with sound location and
  Doppler just like engines." It is a second layer on the SAME voice slot as that car's engine, so it
  inherits that slot's panning and Doppler rather than reimplementing them, and can never drift out
  of step with the engine it belongs to.
- Changed: **`holdNoise` can be placed.** `hold` has had a stereo panner since sounds needed to exist
  at a position; the noise voice never did, so anything noise-based was dead centre however far to the
  side it was happening. Same option and same contract as `hold`.
- Note: **rivals are about 6% faster overall** - mean speed 6612 before against 7023 after. That is a
  real balance change and it is the owner's to judge on a device: the field is harder to beat than it
  was, and the lever is the reserve and the trigger rather than the boost itself.

<a id="v0-12-9"></a>
## [0.12.9] - 2026-09-06
- Added: **a rival holds a gear, and you hear it shift.** Owner, 2026-09-06: "the AI racers should
  have shift events all the same no matter what... I should hear them hit the red line and shift up
  or shift down if they slam on the brakes next to me", and clarifying: "I don't mean I actually hear
  the shifter. I just hear what their engine does as an effect." **Nothing new is played.** A rival's
  revs simply stop being a smooth function of its speed - they climb to the redline, the gear
  changes, and they drop into the new band ([RLG-038](../fragments/RLG-038.md)).
- Fixed: **a rival was voiced as a generic engine, not as its own car.** The traffic mixer resolved a
  body through `rigBody()[c.type]` - a TRAFFIC TYPE. A racer has no `type`; it carries `body`, a BODY
  key. So every rival fell through to a null body and was played at pitch 1.0 against a shared 0.9
  ceiling: eleven cars of three different models all sounding like one engine. It reads `c.body`
  first now.
- Changed: **a shift costs time, so it is an event rather than a relabelling.** `AI_SHIFT_TIME` is
  0.11s during which the car is between gears and makes no torque. **Measured: rivals are about 1.2%
  slower** - 6694 units of mean speed before against 6612 after, two trials each on one seed - which
  is the price of gearchanges they never used to pay.
- Note: **the gear bands already overlapped "so a shift has somewhere to happen".** That hysteresis
  was built long before anything needed it, so shifting up past the band top and down below its floor
  cannot chatter.
- Note: **what a rival always had, against what it lacked.** It already used this car's ratio table,
  this car's redline and the SAME torque curve as the player - RLG-038 enforced one physics for every
  car. What it had not got was a HELD gear: the band was recomputed from speed every frame, so it was
  always in exactly the right gear, instantly, and there was no shift to hear
  ([RLG-038](../fragments/RLG-038.md)).
- Added: **`tools/shift-test.py`**, which checks the mechanism and then the consequence - that revs
  BREAK while the car is still accelerating, which a gearbox-less car can never do. It waits for the
  grid to be released rather than measuring the count-in, where all eleven cars sit at one speed with
  no gear picked and the answer is a meaningless "0 of 11".

<a id="v0-12-8"></a>
## [0.12.8] - 2026-09-05
- Added: **an ambulance does not wail like a police car.** Owner, 2026-09-05: "the ambulance should
  have a different sounding siren to the police." A police wail is 760 over 560 at rate 0.055 through
  a 2600 filter and is **unchanged**; the ambulance yelps at 980 over 700, rate 0.098, through 3200.
  Three differences rather than one, because changing pitch alone reads as the same siren on a
  different car ([RLG-114](../fragments/RLG-114.md)).
- Changed: **the siren lives in `BAR_SCHEME` beside the colours.** "What kind of emergency vehicle is
  this" is one question, so one record answers it - the lens colours, the wash, and now the voice
  ([RLG-114](../fragments/RLG-114.md)).
- Fixed: **a siren belongs to the vehicle sounding it, not to who is driving.** Owner, 2026-09-05,
  correcting the first build: "it has nothing to do with the player driving or not. The ambulance
  just has to have a different sounding siren no matter what." The lookup was framed around the
  player and is keyed on the BODY now, which is the same rule three earlier rulings set for stats,
  colour and class. An NPC ambulance would get the right voice for free the day one exists
  ([RLG-114](../fragments/RLG-114.md)).
- Note: **there is one siren oscillator, so when two sirens sound at once the louder one is heard.**
  That is a mixing limit and not a rule about the player - every car in `cops` is a cruiser by
  construction, so a pursuit sounds like police because of what is chasing you rather than because of
  what you are in ([RLG-114](../fragments/RLG-114.md)).
- Added: **`tools/siren-test.py`**, which reads the live oscillator and filter rather than the table
  they were set from - RLG-065's lesson, which cost three attempts before. It changes ONLY the body
  between samples, so a difference in sound can only have come from the vehicle. Watched failing on
  all three checks with the ambulance given the police siren
  ([RLG-065](../fragments/RLG-065.md), [RLG-114](../fragments/RLG-114.md)).

<a id="v0-12-7"></a>
## [0.12.7] - 2026-09-05
- Changed: **the cross on the rear doors is centred on the handles.** Owner, 2026-09-05: "lower the
  cross on the rear doors slightly more, the handles of the doors should sit centered in the cross."
  It takes the handles' own centre line now, which drops it from 0.508 of the sprite to 0.548
  ([RLG-114](../fragments/RLG-114.md)).
- Note: **that is a better landmark than the one it replaces, not just a lower number.** Splitting
  the clear panel between the glass and the lamps was a reasonable rule that happened to look wrong.
  "The handles sit in the middle of the cross" is a thing the eye can check directly - it is either
  true or it is not ([RLG-114](../fragments/RLG-114.md)).
- Note: **the lamps do not collide with it, and that was checked rather than assumed.** The cross's
  lower arm does reach the lamp row in Y, but the lamps sit at x 0.07 and 0.855 while the cross
  spans 0.32 to 0.68, so the two never meet ([RLG-114](../fragments/RLG-114.md)).
- Fixed: **`bar-row.py` was under-counting the cross it was checking.** Its sample window stopped at
  0.55 of the sprite, so lowering the cross put a third of it outside and the count fell from 1808 to
  1302 while the paint was unchanged. The window is the PANEL now, bounded in X to exclude the lamps
  outright so that Y can cover the whole body - it reads 2658, and a plain van still reads zero,
  which is what proves the X bound is doing the excluding. **A check whose window must be re-tuned
  every time the thing it measures moves is a check that will one day be re-tuned wrongly**
  ([RLG-114](../fragments/RLG-114.md)).

<a id="v0-12-6"></a>
## [0.12.6] - 2026-09-05
- Removed: **the bus, before it was built.** Owner, 2026-09-05: "I don't think we should make the
  bus. It's just extra work for not much payoff so we can just retire that idea." No code changes;
  [RLG-114](../fragments/RLG-114.md) asked for the pickup reclassified, an ambulance and a bus, and
  it closes as **built** with the third withdrawn rather than left open forever.
- Note: **why the bus was not cheap the way the ambulance was.** The ambulance already had a body
  the painters knew how to draw - `rig:'van'`, front and rear - so the only new drawing was a light
  bar. A bus shares none of that: a new branch in both rig painters, its own `rigBox` entry, sprite
  registration, stat row and traffic decision. And every rig branch in those painters returns early,
  so nothing already written at the foot of them would have applied to it
  ([RLG-114](../fragments/RLG-114.md)).
- Note: **RLG-115 is part of why the payoff was small.** A bus is a utility vehicle, so the rule the
  owner set the same day would have confined it to TEST DRIVE in Interstate and kept it out of
  Motorsport's garage entirely. What made a driveable bus sensible rather than a novelty also caps
  how much of the game it could appear in ([RLG-115](../fragments/RLG-115.md)).

<a id="v0-12-5"></a>
## [0.12.5] - 2026-09-05
- Fixed: **the cross on the back doors sat too high.** Owner, 2026-09-05: "it's way too high. He
  needs to be centered on the doors below the windows." The size was right and is unchanged; it is
  centred on the clear door panel now ([RLG-114](../fragments/RLG-114.md)).
- Changed: **the cross on the nose is half the size and centred under the windscreen.** Owner: "half
  its size and centered in the front under the windows between the windows and the grill." Span
  0.30 of the body width down to 0.15 ([RLG-114](../fragments/RLG-114.md)).
- Note: **both are placed from LANDMARKS rather than from a fraction of the body.** The rear takes
  the middle of what lies between the door glass ending at `top+0.165` and the lamps beginning at
  `bot-0.150`; the nose takes the middle between the screen ending at `top+0.200` and the grille
  beginning at `bot-0.215`. Written that way they stay centred if any of those ever move, which a
  tuned constant would not - and the first placement was exactly such a constant
  ([RLG-114](../fragments/RLG-114.md)).
- Note: **the door handles are drawn over the rear cross, and that is right.** Handles are hardware
  bolted over paint ([RLG-114](../fragments/RLG-114.md)).

<a id="v0-12-4"></a>
## [0.12.4] - 2026-09-05
- Added: **the ambulance wears a red cross, in three places.** Owner, 2026-09-05: one on the front,
  one on the back "split down the middle as if it's printed at the seam of the double doors that
  swing out", and "that same Red Cross to be the badge that goes on the steering wheel"
  ([RLG-114](../fragments/RLG-114.md)).
- Note: **the back one is one piece of paint, not two halves.** The cross is drawn as a single shape
  centred on the door seam, and the seam is then stroked back over it - which is how a real one
  behaves, because the paint went on a closed van and the doors were cut through it afterwards.
  Drawing two half-crosses either side of the line would have been the same picture built from the
  wrong idea, and it would have drifted the moment either half moved
  ([RLG-114](../fragments/RLG-114.md)).
- Note: **the body cross and the wheel badge are deliberately different drawings.** On the bodywork
  it is livery - a bare cross, large, no disc. On the wheel boss it is a BADGE and takes the white
  disc and thin rim every other marque has, because a bare red cross on a black boss reads as a
  smear at twenty pixels across. One `drawCross` serves the nose and the doors so those two cannot
  drift ([RLG-114](../fragments/RLG-114.md)).
- Fixed: **giving the ambulance its own marque would have changed its steering wheel.** The rim
  shape is chosen from the MARQUE, so `MEDICAL` had to join the round-rim list or a van would have
  quietly acquired a flat-bottomed wheel ([RLG-114](../fragments/RLG-114.md)).
- Changed: **`tools/bar-row.py` now checks the cross in all three places, against a plain van.**
  Counting red pixels on the ambulance alone would pass on any vehicle with a tail light in frame;
  the van is the same vehicle without the livery, which is what makes the count mean "cross". Watched
  failing with the door cross removed ([RLG-114](../fragments/RLG-114.md)).

<a id="v0-12-3"></a>
## [0.12.3] - 2026-09-05
- Added: **the AMBULANCE.** Owner, 2026-08-31: "in utility we add an ambulance and a bus. The
  ambulance is essentially going to be the van with a red only light bar. Its light bar and siren
  would function the same as with police in terms of getting cars to move out of the way." It is a
  white van with a red bar, it latches and wails from the horn button like a cruiser, and traffic
  gets out of its way ([RLG-114](../fragments/RLG-114.md)).
- Changed: **`force` means police, and a new `bar` means there is a light bar.** One field was
  answering two questions - "is this police" and "has this a bar, a siren and the right to move
  traffic" - and an ambulance is the second without the first. `bar` carries the colour scheme with
  it, so a bar is declared rather than assumed blue and red. `inCruiser()` was really asking the
  second question, so it is `hasBar()` now, with `inForce()` beside it for the first
  ([RLG-114](../fragments/RLG-114.md)).
- Note: **the siren and the scatter cost nothing; the drawing cost everything.** `barOn` already
  drove `scatter(0.90)` and the wail already rode on it, so both followed the new gate untouched.
  But a light bar was drawn in FOUR painters, and in the two rig painters it sat inside a branch
  gated on the car being a cop - so a bar was something only police could have, twice over
  ([RLG-114](../fragments/RLG-114.md)).
- Fixed: **the van branch returns early, which is why the first fix did not work.** Moving the bar
  to the foot of the rig painter was not enough: `if(kind === 'van')` draws its slab and returns, so
  the shared block was never reached and the ambulance came back carrying a plain van's three lamps.
  No error, no warning - the code simply never got there. The bar is drawn inside that branch now,
  on its own roof line ([RLG-114](../fragments/RLG-114.md)).
- Changed: **an ambulance has its own rig, and only so that it can own a sprite.** `SP` is keyed by
  rig and `SP.van` is the one sprite every traffic van shares, so a bar bolted to it would have put
  one on the traffic. Both rig painters remap `ambulance` to `van` on entry with the medical bar
  implied ([RLG-114](../fragments/RLG-114.md)).
- Added: **`tools/bar-row.py`**, which measures where a bar actually sits on a sprite, because the
  note beside `barY` says the existing values were sampled and that any new one must be too. The
  guess was 0.070 and the measurement is 0.074. **It carries the two known cars as a control and
  refuses to report numbers unless they come back right** - and that control caught two faults in
  its own first draft, since the sprite table is empty on the title screen and a check that hunts
  for blue and red pixels cannot find a bar that is neither ([RLG-114](../fragments/RLG-114.md)).
- Fixed: **the fleet sheet's own copy of the class map gained the ambulance.** RLG-114's note warns
  that a class moving in one copy and not the other makes the sheet print something the garage
  disagrees with ([RLG-114](../fragments/RLG-114.md)).
- Note: **an ambulance is a utility vehicle, so RLG-115 applies to it without a new decision** -
  Test Drive only in Interstate, and not listed at all in Motorsport. That follows from the owner's
  own rule, and it is worth their eye: an emergency vehicle missing from a circuit garage may read
  as a bug rather than as the rule working ([RLG-115](../fragments/RLG-115.md)).
- Note: **what a harness cannot judge.** Whether a white van with a red bar reads as an ambulance at
  speed, whether red at both ends still reads as a flash rather than a steady lamp, and whether the
  scatter feels like traffic yielding rather than traffic behaving oddly.

<a id="v0-12-2"></a>
## [0.12.2] - 2026-09-05
- Changed: **the repository is `effigy-arcade`.** Owner, 2026-09-05: "we are supposed to use the
  standard GitHub nomenclature of - instead of _ and development repos -dev while production repos
  drop the -dev." The account bore the standard out - ten private repositories carry a `-dev` suffix
  and the one other public one does not, so the correlation with visibility is exact. This
  repository is public and Pages serves `main`, which makes it the production repository, so
  dropping `-dev` was already right and only the underscore was wrong. **The Pages URL is now
  `effigymedia.github.io/effigy-arcade/`** ([RLG-155](../fragments/RLG-155.md)).
- Note: **the project folder is unchanged and the two rules are different.** `Effigy_Arcade` keeps
  `Pascal_Snake_Case` with underscores and never takes a `-dev` suffix. A repository name is derived
  from the project name rather than equal to it: lowercase it, turn the underscores into hyphens,
  then add `-dev` if it is a development repository ([RLG-155](../fragments/RLG-155.md)).
- Note: **nothing in the product had to change for the rename.** The manifest uses
  `start_url: "./index.html"` and `scope: "./"` and every asset path is relative, so no shipped file
  carries the repository name. Saves survive because `localStorage` is scoped to the origin
  `effigymedia.github.io`, which a rename does not touch. **The installed web app on a phone points
  at the old path and needs adding to the home screen once more**
  ([RLG-155](../fragments/RLG-155.md)).
- Removed: **`sync.sh`.** It cloned the remote into a temporary folder and copied files over the
  top, which is from when this working folder was not itself the repository. It has been carried as
  obsolete for some time and the rename was the occasion to finish it. `pack.sh` cross-checked three
  lists against each other and now cross-checks two ([RLG-155](../fragments/RLG-155.md)).
- Fixed: **three stale references to the old repository name** - `CLAUDE.md`, a path comment in
  `404.html`, and the site link in `docs/README.md` ([RLG-155](../fragments/RLG-155.md)).
- Fixed: **the process corpus now carries the standard, which is why this drifted in the first
  place.** `Development_Process.md` said only that the repository name matches the project name - and
  a project folder uses underscores, so a session following the written rule correctly produced
  `effigy_arcade`. It now reads that the repository name is DERIVED from the project name, with
  visibility as the discriminator so that a repository which is both developed in and shipped from
  counts as the production one. **Project folder naming is untouched.** The owner granted explicit
  authority for a project session to make that edit, which it normally may not, and a note carrying
  a plan for its own removal was left at the environment root
  ([RLG-155](../fragments/RLG-155.md)).

<a id="v0-12-1"></a>
## [0.12.1] - 2026-09-05
- Added: **the events are for the cars built to enter them.** Owner, 2026-08-31: "if you have a
  production or utility vehicle selected, the only mode available is test drive." The garage classes
  stop being only a schedule of when a car unlocks and start describing what a car is FOR - the
  ordinary cars are for driving around in, and a saloon on a starting grid against three supercars
  is a race nobody wrote ([RLG-115](../fragments/RLG-115.md)).
- Changed: **the race modes grey out and say why, rather than vanishing.** Owner, 2026-09-05, given
  three shapes to choose between. MODE keeps its place, dims, carries `disabled`, and a line under it
  reads the car's own class followed by TEST DRIVE ONLY. A control that disappears teaches nothing,
  and a player who never picks a race car would never learn the classes mean anything
  ([RLG-115](../fragments/RLG-115.md)).
- Changed: **a circuit garage does not list a van at all.** Owner, 2026-09-05, choosing the strongest
  of four options for Motorsport. Interstate lists production and utility cars and greys the race
  modes out, because it HAS a mode they are legal in; a circuit does not, so a greyed-out control
  there would explain a rule about a screen the player cannot reach. It is a `CFG.raceOnlyGarage`
  flag set by the cabinet - this is the first thing that makes the two games' garages hold different
  cars, and the engine must never ask which game it is ([RLG-115](../fragments/RLG-115.md)).
- Changed: **a save can no longer hold a car and a mode that disagree.** The owner rejected both
  resolve-it-at-launch answers in favour of never letting the disagreement exist, so the rule is
  applied as the garage opens and again whenever a car is chosen. **The tournament is switched off,
  not erased** - the round, the points and the standings are untouched, and picking a race car back
  up resumes it. Taking a van out for a drive must not cost somebody their ladder
  ([RLG-115](../fragments/RLG-115.md)).
- Changed: **the class table answers one question in one place.** It was a local `const LOCK` inside
  `cycleBody`, where only the arrows could ask it; it is `BODY_CLASS` at module scope now, with the
  unlock gate and `raceLegal()` both reading it. The list of cars the garage shows became
  `garageBodies()` for the same reason ([RLG-115](../fragments/RLG-115.md)).
- Added: **`tools/class-test.py`**, which drives the real controls rather than asking `raceLegal` and
  agreeing with itself, and which was watched failing with each lock removed and with both. **One of
  its checks was vacuous in draft and the fragment records it**: "pressing it anyway does nothing"
  read the button's LABEL, which is hardcoded to TEST DRIVE on the banned branch and cannot move
  whatever happens underneath - so it passed with both locks gone. It reads the engine's `mode` now
  ([RLG-115](../fragments/RLG-115.md)).
- Note: **RLG-115's own premise was stale and the fragment now says so.** It describes the mode
  buttons as being on the title screen and the car as chosen in the garage, "two separate screens".
  MODE and HOT PURSUIT were moved into the garage; the title holds only PLAY, OPTIONS and QUIT. The
  car and the mode are adjacent controls on one screen, which is what makes greying out read clearly
  ([RLG-115](../fragments/RLG-115.md)).
- Note: **whether a dimmed control reads as switched-off rather than broken is the owner's eye.**
  0.42 opacity on a phone in daylight, and a 9px reason under it, are not things a harness can judge.

<a id="v0-12-0"></a>
## [0.12.0] - 2026-09-05

**Slice checkpoint. The world slice closes.** Thirty of the thirty-one patches in 0.11 changed what
is OUTSIDE the car - the places on the board, the weather over them, and the structures the road runs
through. The queue now turns to the vehicles, so the minor moves and the patch count resets. The rule
is that a minor bump marks a slice completing, and [0.11.0](#v0-11-0) was cut for the same reason
after 0.10 ran to forty-six patches with several slices closing unmarked inside it.

The one patch that was not world work is named below rather than left out, because a checkpoint that
quietly drops what does not fit the theme is a summary and not a record.

WHAT THE SLICE CONTAINED, grouped by what it built rather than in patch order:

**Four new places on the board.** FARMLAND, a cornfield down one side and houses and barns down the
other ([0.11.1](#v0-11-1)); TUNNEL, the only place that is dark by day ([0.11.2](#v0-11-2)); CANYON,
whose distance is a wall ([0.11.5](#v0-11-5)); and JUNGLE ([0.11.29](#v0-11-29)), whose canopy cost
almost nothing because the tunnel had already built the mechanism it needed. The crop side also
learned to alternate corn with pasture, and a pasture holds horses or cows ([0.11.23](#v0-11-23)).

**A place can now be an EVENT rather than a place** ([0.11.7](#v0-11-7)) - a stated length and an
authored profile, instead of a rolled stretch of terrain. That is the structural change of the
slice, and both the bridge and the tunnel are built on it.

**The bridge became a bridge.** Water on both sides all the way to the skyline
([0.11.8](#v0-11-8)), its red truss ([0.11.10](#v0-11-10)), suspended above the water rather than
floating on it ([0.11.11](#v0-11-11)), no longer ending in mid-water ([0.11.12](#v0-11-12)), and
finally a deck under the car with expansion joints across it ([0.11.28](#v0-11-28)).

**The tunnel took nine patches and three of them were one defect wearing three faces.** Walls tight
to the roadway ([0.11.3](#v0-11-3)), a run can never open inside one ([0.11.6](#v0-11-6)), it does
the opposite of the bridge ([0.11.14](#v0-11-14)), it is not transparent ([0.11.15](#v0-11-15)), and
it is not painted over the traffic ([0.11.16](#v0-11-16)). Then the three the owner reported from
the device together: the inside goes past you now ([0.11.24](#v0-11-24)), it climbs back out of
itself ([0.11.25](#v0-11-25)), and the bore exists where the tunnel is rather than where the light is
([0.11.26](#v0-11-26)).

**The coast and the sky.** A fleet rather than one boat ([0.11.13](#v0-11-13)), open water on the
horizon with no headlands standing on it ([0.11.17](#v0-11-17)), less relief ([0.11.18](#v0-11-18)),
a canyon skyline no higher than the canyon walls ([0.11.9](#v0-11-9)), and far more lit windows on
the city ([0.11.21](#v0-11-21)).

**The climate model, and the defect under it.** A place's own bend and hill are in force from its
first unit ([0.11.20](#v0-11-20)) - a generation-order fault that had been quietly making every
biome transition read wrong. A tundra's ground is white before anything falls
([0.11.22](#v0-11-22)); the farmland yards are sparse ([0.11.19](#v0-11-19)); and the drops on the
glass stop when the fall does, with a temperature step over the board
([0.11.27](#v0-11-27)).

**And one patch that belongs to none of the above.** Traffic engines are heard at six car lengths
and rivals at twelve ([0.11.4](#v0-11-4)) - a change to the audio mix, written as a ROLE carried on
the vehicle rather than a branch naming a class, and measured in car lengths so that it survives the
road ever being widened.

**One fleet change, which is the hinge into the next slice.** The pickup is a production vehicle
([0.11.30](#v0-11-30)), and the traffic pickup with it ([0.11.31](#v0-11-31)) - because a class
describes the vehicle, not who is holding the wheel.

WHAT IS STILL THE OWNER'S EYE AND NOT A MEASUREMENT. The tunnel's portal fills the frame from five
thousand units out and reads as a cliff rather than a portal, and near the exit the next place floods
in around the tube. Both are geometrically honest and neither is obviously right. 0.11.20 also
changes how EVERY biome transition feels, because the tables were tuned by feel while the fault was
present, and 0.11.22 takes the mountain's ground cover from a flat 0.10 to a median 0.39.

<a id="v0-11-31"></a>
## [0.11.31] - 2026-09-02
- Fixed: **the traffic pickup is production too.** [0.11.30](#v0-11-30) moved the driveable
  PICKUP and deliberately left the traffic `pickup` in utility. Owner, 2026-09-02: "no the
  traffic version is also production - why would we create inconsistencies?"
- Note: **they are right and the reasoning was wrong.** A CLASS DESCRIBES THE VEHICLE, NOT WHO
  IS HOLDING THE WHEEL. The same body in someone else's hands is the same body, so splitting it
  gave the game two answers to what a pickup is - which is precisely the fault the note written
  beside it claimed to be preventing. It was introduced in the same commit that congratulated
  itself for avoiding it.
- Note: **measured rather than assumed this time.** Reading the fleet back from the engine:
  production holds 9 - COUPE, SALOON, CAB, PICKUP, sedan, sedan2, coupe, pickup, taxi - and
  utility holds 4: VAN, LORRY, van, truck. The sheets in `docs/fleet/` are regenerated with it.
- Note: **the file size was a red herring and nearly went unchecked.** `utility.png` shrank and
  `production.png` came back byte-identical, which read as the pickup leaving one class without
  arriving in the other. A PNG's size is not a measurement of what is in it; the fleet had to be
  asked.

<a id="v0-11-30"></a>
## [0.11.30] - 2026-09-02
- Changed: **the pickup is a production vehicle.** Owner, 2026-08-31: "we move pickup to
  production" ([RLG-114](../fragments/RLG-114.md), the first half of queue item 7).
- Note: **it is one line and it is also a balance change**, which is the part worth a moment.
  Production unlocks at 50 miles and utility at 25, so this makes the pickup unlock LATER rather
  than sooner - and it leaves utility with two entries where it had three, so both classes
  change size at once. A player who has just earned utility now finds two vehicles in it.
- Note: **and it is the classification catching up with the drawing.** The wheel work already
  splits the fleet into a sporty group and the ones the owner named production and utility, and
  the pickup already sits with a four-speed gearbox and a production-shaped wheel. Nothing about
  the vehicle itself changes.
- Note: **the class map exists twice and both copies moved.** The garage's unlock map and the
  fleet sheet's own map are separate tables, and a sheet printing a class the garage disagreed
  with would be the value-typed-beside-a-value fault again. The TRAFFIC pickup stays utility: it
  is a working vehicle in someone else's hands, and only the DRIVEABLE one was reclassified.
- Note: **the sheets in `docs/fleet/` are regenerated**, so production and utility both show
  their new membership.

<a id="v0-11-29"></a>
## [0.11.29] - 2026-09-02
- Added: **the jungle.** Owner, 2026-08-31: "let's add a jungle biome"
  ([RLG-113](../fragments/RLG-113.md)). Twelfth place on the board.
- Note: **its climate is already taken and that is not a problem.** On the two axes the model
  runs on, a jungle is hot and very wet, and so is the swamp. Climate is not what separates two
  places: four things make one - climate, TERRAIN, scenery and light - and this differs from the
  swamp on three of the four. A swamp is flat and half water at 0.15 of relief; a jungle is
  hilly and closed at 0.55. That gap is larger than the difference between most pairs on the
  board and it is felt through the wheel rather than seen.
- Note: **and it is the wettest place there is**, 0.78 against the swamp's 0.64. That is the one
  climate claim worth making about it.
- Added: **a `canopy` form for the skyline**, the third caller of the continuous mechanism after
  the canyon's ridge. `buildSkyline` draws SWAMP and FOREST with narrow trunks and holes punched
  through the line; a jungle horizon has no gaps and no individual tree readable in it, which is
  nearer the canyon's wall than the forest's comb. Lower and gentler than a ridge, because rock
  is cut and vegetation is not.
- Note: **the gloom cost nothing, because the tunnel went first.** RLG-113 said to build them in
  that order for exactly this reason: `lampsOn` already reads the PLACE as well as the hour, so
  a canopy asks the same function for a smaller number. 0.35 is a road under closed vegetation.
  Built the other way round the jungle would have grown its own darkening and the tunnel would
  have arrived to find two answers to one question.
- Changed: **`bore` is the structure and `dark` is the light**, which were one field until now.
  A canopy is darker by day than anywhere else and is emphatically not a tunnel - reading `dark`
  as "there is a tube here" would have cut a rock face across a jungle road and drawn walls down
  it. `boreSpan` and `drawPortal` ask `bore`; `dark` goes on saying only how dark it is.
- Added: **`setInstanceTemp`, because the temperature step broke two harnesses and they were
  right to break.** [0.11.27](#v0-11-27) means a place may only be followed by one within ten
  degrees, and forcing the countdown re-plans from the CURRENT instance every time - so a
  harness rolling over and over from wherever the run opened can never reach a passage that is
  out of range. It stands the run at a chosen climate first.
- Note: **`place-shape-test` is marginal and the number was NOT moved.** One drive is one roll of
  the generator, which its own notes say. Three runs: two comfortably inside the ceiling, one at
  0.87 against 0.86. [RLG-056](../fragments/RLG-056.md) is the standing rule that a threshold is
  not fixed by moving it - the measurement would have to average a longer baseline, and that is
  work rather than a number.

<a id="v0-11-28"></a>
## [0.11.28] - 2026-09-02
- Added: **a bridge has a deck under the car, and expansion joints across it.**
  [RLG-112](../fragments/RLG-112.md) says a span reads as a bridge because of its deck, its
  joints and the rail down each side. The rail was built and the other two were not, so a
  crossing was ironwork standing over ordinary tarmac.
- Added: **the deck.** A bridge carries its running surface on a structure, and that reads paler
  and greyer than a road laid on the ground - steel and concrete rather than bitumen. The lift
  is applied to the BASE colour before the weather and the hour, so a wet deck at night is still
  a deck and the snow, the rain and the sheen all go on reading through one expression.
- Note: **it is not a second painter, which is the point.** A deck with its own tone function
  would be a second answer to what colour a road is, and it would stop agreeing with the first
  the day anyone tuned the wet wash - the fault this file has been caught by four times.
- Added: **the joints, on the world cycle the stanchions already use.** `postIn` asks the WORLD
  rather than a segment index, so they keep their spacing whichever view walks over them and
  however big its steps are. Nine segments is 1,800 units, about twenty-one metres on the anchor
  the fleet uses, and about three a second at the speed the interstate is driven - a rhythm
  rather than a texture.
- Note: **a joint is a gap with a plate either side of it.** The dark band is the gap and the
  pale line on its near lip is the steel catching the light, which is what stops it reading as a
  painted stripe. It runs kerb to kerb because a joint is structural.
- Changed: **and the mirror shows the same deck.** The glass keeps its own tone expression - it
  is a 44-pixel pane and its base greys are lifted for legibility - so it cannot simply call
  `tarmacTone`. What it must not do is disagree about what surface is under the car, so it takes
  the same lift at the same point in its own expression.

<a id="v0-11-27"></a>
## [0.11.27] - 2026-09-01
- Fixed: **the drops on the glass stop when the fall does**, which they did not. Owner,
  2026-09-01, from the device: "the snow eventually subsided and the wet drops on the screen
  kept going" ([RLG-142](../fragments/RLG-142.md)).
- Note: **it is a type error, not a lifetime one.** The fragment guessed at a scheduled effect
  outliving the state that armed it, in the family of
  [RLG-111](../fragments/RLG-111.md)'s thunder, and said explicitly not to diagnose it from
  that guess. It is simpler and it is one line: `stepLens` took `Math.max(wet, snowy)` as the
  amount on the glass, and `snowy` is a KIND - set to 1 or 0 when the weather is rolled and
  cleared by nothing but the NEXT roll - while `wet` is the amount and eases to zero when the
  fall ends. So it was pinned at 1 from the first flake until the next roll, whatever the sky
  was doing.
- Note: **and it answers the owner's other question at the same time.** They asked what the
  drops were drops OF. They were rain drops at the maximum rate for the whole of the mountain
  as well, because the amount never read the amount - so they were wrong before the transition
  too, and the transition is only where it became obvious. That is exactly what the fragment
  predicted would turn out to be the case.
- Added: **the temperature step - a place may not be more than ten degrees from the one before
  it.** Owner: "I'd say 10 to 20 degrees, leaning more towards 10."
- Added: **and the scale, stated once**, because the model had no degrees in it. 0 is -10F and
  1 is 120F, in Fahrenheit because everything else the player sees here is imperial. Against it
  the board reads TUNDRA -3F, MOUNTAIN 10F, FOREST 49F, COASTAL 62F, FARMLAND 68F, SWAMP 94F,
  CANYON 101F, DESERT 114F.
- Note: **it is a constraint on the ROLL, not a filter on the pick.** Rejecting candidates until
  one is close enough biases the board toward whatever is near and deadlocks at the ends of the
  scale. The place's own range is intersected with the window the previous instance allows and
  the roll happens inside what is left; a place that cannot reach is picked again.
- Changed: **the place and its temperature are chosen together.** The instance used to be rolled
  at the placement, seconds after the pick, and the pick knew nothing about it - but it is the
  instance that says whether a place may follow this one.
- Note: **measured over 400 places from three starts**, running the real `pickNext` rather than a
  copy: the worst step is 10.0F in every walk, and the board still travels - from TUNDRA it
  reaches all eleven places and spans -9.5F to 105.3F. So it is a walk rather than a cage, which
  is the thing worth knowing before the owner sees it.
- Note: **what a run will feel like, said plainly.** A run is sixty seconds plus checkpoints and
  a place lasts six and a half to twelve miles, so a run sees one to three places. Under this
  rule a run stays inside a narrow climate band and the variety comes from returning rather than
  from one drive.

<a id="v0-11-26"></a>
## [0.11.26] - 2026-09-01
- Fixed: **a bore exists where the tunnel is, not where the light is.** Owner, 2026-09-01: "the
  way biomes transition into the tunnel and out of the tunnel is also very jarring"
  ([RLG-153](../fragments/RLG-153.md) item 3).
- Note: **measured through both mouths before anything was changed.** `drawBore` began with
  `if(placeDark() <= 0.01) return`, so whether a tunnel EXISTED was decided by how dark it was -
  and the darkness ramps. GOING IN, the darkness was still 0.000 a hundred units past the mouth
  and 0.056 three hundred after that: nothing was drawn while you approached a hole in a cliff,
  and then the whole tube arrived SOLID in one frame, because the walls are painted at full
  opacity by [RLG-144](../fragments/RLG-144.md) and rightly so. You were already inside it when
  it appeared. COMING OUT, the darkness eases over the full crossing for the photosensitivity
  reason [RLG-060](../fragments/RLG-060.md) gives, so the walls went on being drawn for
  thousands of units over the next place.
- Changed: **existence is geometry now.** `boreSpan` gives the stretch of road the tunnel
  occupies, and the tube is drawn from its own mouth - or from the camera once that is behind -
  to its own far end, and not at all past it. Nothing fades in and nothing springs out.
  `placeDark` keeps the one job RLG-144 gave it back: how dark it is in there.
- Changed: **the far end is dark because it is far.** The depth fade and the ceiling lamps were
  both scaled by `placeDark`, which is the same mistake the walls made. Approaching a mouth the
  darkness is zero, so the bore had no black far end and no lamps in it - a pale, endless
  corridor seen through a hole in a cliff. Neither consults `placeDark` any more.
- Changed: **and the bore runs to the portal.** The profile's span and the place's boundary are
  meant to be the same point and are only nearly it, because the boundary is placed at the
  generator's frontier which overshoots by a segment. Measured at an exit, the walls stopped
  about three thousand units before the rock face - so you drove out of a tunnel into open
  tunnel-coloured ground and then through a cliff.
- Fixed: **a pending nothing is still pending**, which was a defect introduced at
  [0.11.25](#v0-11-25) and caught by this measurement. A place with no profile waiting to take
  over left `pendLen` at 0 and `pendProfile` at null, which the handover read as "nothing is
  waiting" - so a tunnel's event stayed armed for the rest of the run. Eight thousand units past
  the exit, `eventNow().on` was still true. It is a flag now, not an inference.
- Note: **what is still open is the owner's call and cannot be measured here.** The portal fills
  the frame from five thousand units out, and near the exit the tube is short enough that the
  next place floods in around it. Both are geometrically honest and neither is obviously right.

<a id="v0-11-25"></a>
## [0.11.25] - 2026-09-01
- Fixed: **a tunnel climbs back out of itself, and a bridge comes down off its deck.** Neither
  did. Owner, 2026-09-01: "the shapes of the entrances and exits as far as their relief are
  wrong for both the tunnel and the bridge" ([RLG-153](../fragments/RLG-153.md) item 2,
  [RLG-148](../fragments/RLG-148.md)).
- Note: **measured before anything was touched, which is what RLG-148 asked for.** Driving a
  real bore and sampling the road's own integrated slope, 86 per cent of the way through read
  `-0.09` where the profile asks for `+0.34`. The climb out was not there. A bridge lost the
  same ramp and showed it less, because its span is longer.
- Note: **the next place was arming its event over the top of the one still in force.** A
  place's boundary lands exactly where the current event ends, which is right - but a boundary
  is PLACED at the horizon, a draw distance before the car reaches it. So `armEvent` fired with
  the car still 30,000 units short of the end of the bore, and an ordinary place has no
  profile, so it cleared the bore's. Every event lost its last 30,000 units.
- Changed: **a new event waits until the car has driven out of the old one.** They are adjacent
  rather than overlapping - the new one begins exactly where the old ends - so nothing is lost
  by waiting and no stretch of road is ever owned by two profiles.
- Fixed: **and the shape is handed over rather than switched on.** The profile REPLACES the
  terrain's slope, which is right and is why it could not be another entry in the relief table.
  But a replacement is a switch, and it was thrown 30,000 units before the mouth - a whole
  drawn road's worth, every visible slice changing its slope in one frame. Over the first and
  last 4 per cent of an event the two are now MIXED. The profile is already flat at both ends
  by construction, so the shape is unchanged; only the handover is.
- Changed: **`setBiomePair` and `startBiomeChange` arm outright.** They stand in for a placement
  AND for the miles of driving after it, so a place they pin has to take effect at once. Left
  to wait, pinning a MOUNTAIN after a BRIDGE held the bridge's deck in force.
- Added: **`event-test` drives a passage the TIMER placed and samples its exit.** Every claim
  that file made before this was about a profile the harness installed and nothing ever
  disturbed, which is exactly why a green run said nothing about the defect. A tunnel now reads
  `+0.28 +0.33` through its last third and `+0.01` at the mouth; a bridge `-0.40 -0.49` and
  `-0.02`.

<a id="v0-11-24"></a>
## [0.11.24] - 2026-09-01
- Fixed: **the inside of a tunnel goes past you now.** Owner, 2026-09-01, from the device: "the
  main offender is that the walls and ceiling of the tunnel are static. They don't move. They
  should obviously be moving based on your speed" ([RLG-153](../fragments/RLG-153.md), item 1).
- Note: **they could not move, and the reason is one line.** `borePoints` samples the tube at
  `z0 + t*t*reach`, and once you are inside, `z0` IS THE CAMERA - so every rib, joint and lamp
  sat at a fixed distance ahead of you for ever. The shape was right and the picture never
  changed: a painted backdrop with a road running into it.
- Added: **a RING, at a world position.** The transverse joints, the wall panels and the lamps
  are drawn at fixed multiples of `BORE.ring` in world units, so they come at you and pass
  overhead. 1,050 units is about twelve and a half metres on the anchor the fleet uses, which
  is a real segment length and about five a second at the speed the interstate is driven. The
  lamps take every second ring, so they sit ON the joints rather than wandering between them.
- Note: **the surfaces keep the camera-relative walk, and that is deliberate.** A wall and a
  vault are continuous, their silhouette is the same however they are sampled, and the squared
  spacing puts the samples where the shape actually bends. Only the DETAIL needed anchoring,
  because detail is the only thing that can be seen to move.
- Changed: **one description of the bore's cross-section, not two.** `borePointAt` was inline
  in `borePoints`; with a second walk over the same tube it becomes a function. Two
  descriptions of one shape is what this file has been caught by three times.
- Note: **measured in the pixels, because the sample list was never wrong.** `tunnel-test` now
  diffs the CEILING band - below the mirror, above the horizon, so the road's own stripes
  cannot answer for it - between two frames 180ms apart at seven tenths of top speed. Before:
  2.2 per cent of the band changed, and that much is the tube swinging on a bend. After: 20.9
  per cent. The parked control reads 0 both ways, which is what says the figure is motion.

<a id="v0-11-23"></a>
## [0.11.23] - 2026-09-01
- Added: **the crop side alternates corn with pasture, and a pasture holds horses OR cows.**
  Owner, 2026-09-01: "can we also alternate the cornfields with pastures? In these pastures
  should either be horses or cows never at the same time" ([RLG-145](../fragments/RLG-145.md),
  item 8). This closes the eighth and last item of that report.
- Note: **it is the `crop` mechanism again and nothing new.** A place names the spec its rolled
  side draws; farmland names two now, and `fieldSpecFor` alternates them field by field.
  Nothing in the painter learned what a pasture is.
- Added: **a FIELD, which is 90 segments** - about 18,000 units, a bit over two hundred metres
  on the anchor the fleet uses. The road is drawn 150 segments ahead, so a field and its
  neighbour are both in the picture and the boundary between them is visible, which is what
  "alternate" has to look like.
- Note: **the alternation is strict rather than rolled.** A coin gives two pastures in a row
  about a quarter of the time, and two adjacent pastures are one big pasture - which is exactly
  what stops reading as alternation. Fields really are laid out in a grid.
- Added: **`herd`, which is the whole of "never at the same time".** Every other spec picks its
  kind from a per-segment roll, so two kinds means a horse beside a cow beside a horse. A
  `herd` spec reads the FIELD's roll instead. That is the same one-roll-read-by-many rule the
  sea's side and the crop's side already follow.
- Changed: **the mirror reads both answers too**, for the same reason it already shares the
  side: the glass must not show a pasture where the road ahead has corn.
- Note: **sparse, and not a lattice.** A cornfield is planted and its regularity is the point;
  livestock stand about a field in no order, so the pasture keeps the density roll and the
  jitter the crop spec deliberately drops.
- Changed: **`farmland-test` reads the CORN rather than the crop side** for its planted-not-
  scattered claim. Without that it counted a pasture's jitter as a cornfield's and reported
  eleven distances in a rank that should hold one.
- Added: **and it drives to check the alternation**, because a field is 90 segments and one
  frame holds two at best. Over 33 pastures: both kinds appear across fields, no field holds
  both specs, and no pasture holds two kinds. With the per-field roll reverted to a per-segment
  one, that last check fails on fields 1, 3, 5 and 7.

<a id="v0-11-22"></a>
## [0.11.22] - 2026-09-01
- Changed: **a tundra's ground is white before anything falls, and only the tarmac
  accumulates.** Owner, 2026-09-01, from the device: "the ground and far ground in tundra should
  be white as if covered in snow. Only the tarmac should increment and decrement snow (though
  keep in mind that the tarmac has a capped minimum baseline of .247 I believe it was)"
  ([RLG-145](../fragments/RLG-145.md), item 1).
- Note: **the owner's 0.247 is exact.** It is what `climateAt` derives for a tundra at its
  stated 0.05. The note above the table said 0.48, from before `SNOW_FLOOR_K` moved, and that
  figure is corrected.
- Changed: **a ground cover is not a floor, and they are two quantities now.** `snowFloor` is
  where the TARMAC's accumulation starts and where melting stops - it keeps that job and its
  number. The ground takes the greater of its permanent cover and whatever has settled, because
  driving through a blizzard or a thaw does not make a frozen plain more or less frozen.
- Note: **and it is still derived, which [RLG-109](../fragments/RLG-109.md) requires.** Nothing
  new is stated in the table. The cover is the place's own floor read against the coldest floor
  the model produces, so a cold-rolled city lies under snow for the same reason a tundra does.
  Measured over 400 rolls each: TUNDRA 0.77-1.00 cover, median 0.99. MOUNTAIN 0.00-1.00, median
  0.39 - a mountain is sometimes bare and sometimes buried, which is what a mountain is. FOREST
  and DESERT are 0.00 throughout and unchanged. A CITY is 0.00 at its median and 1.00 at its
  cold end.
- Changed: **TUNDRA's `vary` from 0.10 to 0.04**, which is what makes the first claim true. At
  0.10 an instance could roll to 0.15, where a tundra derives the same floor a mountain does
  and its ground came out half bare. A tundra is defined by being reliably frozen rather than
  by being cold on average, and `vary` is the field that says so.
- Changed: **the mirror's ground takes the same quantity**, or the glass shows a different
  winter from the road.
- Note: **the mountain is the visible side effect and it was not asked for.** Its ground cover
  goes from a flat 0.10 to a median 0.39 that varies run to run. It follows from the owner's own
  model rather than from a decision made here, and it is the owner's call on the device.

<a id="v0-11-21"></a>
## [0.11.21] - 2026-09-01
- Changed: **the city carries far more lit windows.** Owner, 2026-09-01, from the device: "the
  illuminated windows in the skyline buildings of the city biome need to have a higher
  quantity" ([RLG-145](../fragments/RLG-145.md), item 6).
- Note: **two numbers, and neither of them is a brightness.** How many windows a building HAS
  was 0.42 of its grid, and how much of its own cycle each one spends lit was 0.45 to 0.87.
  What the eye counts is the product, so both moved: 0.58 of the grid, lit 0.58 to 0.94 of the
  time. Turning up a colour would have made the same windows brighter, not more of them.
- Note: **the spread is kept, which is the whole point of the habit.** A duty of 1 for every
  window is a city that never changes and one narrow band of duties is a city that switches
  together - the fault [RLG-095](../fragments/RLG-095.md) exists to prevent. The band is still
  a third of the range wide.
- Note: **measured over fifty samples of the window clock**, with the clock held so each
  reading is taken at the time it was set to. Lit pixels in the near band went from 192-348,
  median 264, to 457-559, median 489 - up 85 per cent. The swing did NOT grow: it fell from 156
  to 102, and from 0.59 of the median to 0.21, so nothing about this makes the city read as
  switching as one. The capture is `_shots/biome-city.png`, taken at midnight.

<a id="v0-11-20"></a>
## [0.11.20] - 2026-09-01
- Fixed: **a place's own `bend` and `hill` are in force from its first unit.** They were not.
  The owner reported that the bridge and the tunnel both turn too hard, and those two hold the
  lowest numbers on the board ([RLG-150](../fragments/RLG-150.md), from
  [RLG-145](../fragments/RLG-145.md) item 5).
- Note: **WHERE a place begins and WHEN it was chosen were one variable, and they are two
  questions.** The road is generated to `pos + 100000`; a place was decided at
  `biomeEdge = here + DRAW`, which is 30,000 ahead. `pushCurve` scales a segment by its place
  AT GENERATION - correctly, because a bend that changed magnitude as you approached it would
  be the road moving under you - so the 70,000 units between the two were made under the
  PREVIOUS place's factor and nothing ever went back for them.
- Changed: **the timer now PLANS a place instead of placing one.** It chooses the place and its
  edge at the generator's own frontier, past every segment that exists, and only `shapeAt`
  is told. The picture is told later, when the car is a draw distance short of that same edge -
  so the colour still enters at the horizon and travels in, which is
  [RLG-022](../fragments/RLG-022.md), and the shape of the road and the colour of it change at
  one place because it is one number.
- Fixed: **and no segment straddles the boundary.** A first build planned correctly and still
  measured an entry at 0.88 of the ordinary road where it wanted 0.23. A bend runs 4,000 to
  15,000 units and the two segment lists do not end together, so the shorter one always had one
  segment left that began before the boundary and carried the old factor for its whole tail.
  `clipToPlan` cuts it at the boundary, and the next one starts exactly on it.
- Note: **measured by driving, and falsified before it was believed.** A bridge wants 0.23 as
  bent as ordinary road throughout and read `1.29 1.39 0.28 0.27 0.11 0.30 0.09 0.24` by
  eighths before; it reads `0.04 0.11 0.08 0.10 0.20 0.06 0.00 0.08` now. A tunnel wants 0.29,
  read `2.24 0.72 0.82 0.55 0.43 0.15 0.35 0.36` and now reads
  `0.38 0.51 0.14 0.26 0.19 0.35 0.25 0.37`. With the one line of the fix reverted and the
  instrument left in place, the check fails again at 0.87 and 3.08.
- Added: **`tools/place-shape-test.py`.** It drives a passage placed by the TIMER, because
  `startBiomeChange` and `setBiomePair` both place at the horizon - a harness cannot drive
  70,000 units before it starts - so they cancel the plan and do not reproduce the corrected
  order. A check using either would measure the old behaviour and report a pass.
- Changed: **`biome-test`'s last claim, because the behaviour it described has legitimately
  changed.** The countdown running out and the pair changing are now two events with a drive
  between them. It asserts both, plus that the planned edge is still beyond the horizon while
  the plan is pending. Its first form asserted that the edge is past every generated segment,
  which is only true at the instant of planning - nine tenths of a second later the generator
  has properly run on past it, into the new place, with the new factor.
- Note: **this was never only a passage problem.** Every place was entered through 70,000 units
  of the previous place's shape; a bridge and a tunnel merely made it obvious because they are
  the two calmest things in the game. So every transition in the game is affected, the tables
  were tuned by feel with the fault present, and **the owner has to judge the result on the
  device.** The numbers now do what the table says they do, which is not the same as being the
  right numbers.

<a id="v0-11-19"></a>
## [0.11.19] - 2026-09-01
- Changed: **the farmland yards are sparse now** - scenery density 0.30 to 0.14. Owner,
  2026-09-01, from the device: "the houses and barns in the farmland biome need to be more
  sparse" ([RLG-145](../fragments/RLG-145.md), item 7).
- Note: **0.30 stood ABOVE the coast's 0.24, which is the wrong way round.** A beach strip is a
  row of houses; a farmstead is a yard with fields either side of it. The capture showed the
  consequence exactly - an unbroken run of roofs from the vanishing point to the near verge
  with no field between any two of them.
- Note: **the gap is the subject**, which is the same thing the coast's own horizon spec says
  about its islands. 0.14 leaves the yards clearly further apart than the beach houses and
  stays well above the desert's 0.055, which is a thing every few hundred yards.
- Note: **the look is the owner's call and the capture is in `_shots/biome-farmland.png`.**
  A density is a number a harness can read back; whether a farm reads as a farm is not.

<a id="v0-11-18"></a>
## [0.11.18] - 2026-09-01
- Changed: **the coast barely rises and falls now** - relief 0.18 to 0.10. Owner, 2026-09-01:
  "we should minimize the verticality significantly in coastal because when we go up and down
  in this biome the ocean follows and that's not how that works"
  ([RLG-145](../fragments/RLG-145.md), item 3).
- Note: **this is the cheap half and the owner asked for it; it is not the fix.** THE OCEAN
  FOLLOWING IS THE REAL FAULT. The sea is drawn from the ROAD's own line, so a crest lifts the
  water with it, and a lower relief only makes the crest smaller. Water drawn at the LAND's
  level is the honest answer, which is what [RLG-143](../fragments/RLG-143.md) is building for
  the bridge - a coast is its second customer.
- Note: **measured, because a relief number is otherwise chosen by eye.** `farSea().y` is where
  the water meets the near shore on the screen, so its peak-to-peak over a drive IS the
  movement being complained about. Six runs at each value, trimmed: 0.18 gave 21 to 39 pixels
  on an 862-pixel screen, 0.10 gave 12 to 20. The ranges do not overlap, which is the bar
  `fps-test` sets for a change being real, and the medians are 25 against 17.
- Note: **0.10 is the board's floor and that is why it stops there.** FARMLAND sits at 0.10 and
  its own note claims that as the thing it is, the flattest place there is. Going below takes
  that identity off it, and that is the owner's call rather than one to make while tuning a
  coast. So the water still moves about 17 pixels, and only RLG-143 takes it to zero.

<a id="v0-11-17"></a>
## [0.11.17] - 2026-09-01
- Changed: **the coast's horizon is open water now, with no headlands standing on it.** Owner,
  2026-09-01, from the device: the islands are masked wrong at the shoreline, "it might just be
  simpler to remove them" ([RLG-145](../fragments/RLG-145.md), item 2). COASTAL states
  `skyForm:'none'`.
- Note: **the mask was measured before it was believed wrong, and it is not wrong.** The clip
  added at [0.11.13](#v0-11-13) splits the skyline at the road's vanishing point. The water's
  own far band records where it reaches the horizon, and over fourteen frames the two agreed to
  0.0 of a pixel. Sampled down the pixel column, the sea begins on the horizon row itself, so
  an island's base meets the water with no gap under it.
- Note: **so there was nothing better to clip to.** Above the horizon the shoreline IS a
  vertical line at the vanishing point - that is what a vanishing point means. What is left is
  a headland cut in half by that line, and no repositioning of a mask fixes a hard vertical cut.
  The ruling was to take the owner's simpler option unless the mask could follow the shoreline
  itself; it cannot, so this takes it.
- Note: **the clip is left standing and is now unused.** `seaOnly` in the skyline painter has no
  customer, because the only place with water on one side draws no band. It stays because the
  measurement said it was right, so restoring the headlands is one word in the COASTAL row -
  and it should only go back with an answer to the vertical cut.
- Note: **`coast-test` passed six runs out of six after the change.** It had been failing about
  three runs in thirteen with the clip live and about one in twelve without it, and the note at
  0.11.13 said plainly that the cause was never isolated. Six is not a rate and this does not
  claim the flake is gone - it is recorded so a later session has the before and the after.

<a id="v0-11-16"></a>
## [0.11.16] - 2026-09-01
- Fixed: **the tunnel wall is not painted over the traffic any more.** Owner, 2026-09-01, from
  the device, with a capture: cars inside the bore had the wall and the floor drawn straight
  across them ([RLG-145](../fragments/RLG-145.md), item 4).
- Note: **both halves of the draw order were already right and they contradicted each other.**
  `drawRoad` paints the ground out to the frame edge, so the bore has to come after it or the
  verge buries the foot of the wall - that is [RLG-105](../fragments/RLG-105.md) and it was
  measured. But `drawRoad` also EMITS THE SPRITES as it walks, so the one call that must
  precede the bore also puts every car underneath it.
- Changed: **so the cars leave the road pass.** While a bore is on the screen the sprite pass
  records the buckets it was asked to paint instead of painting them, and they are painted
  after the walls. The EMISSION DECISION does not move, and that decision is the occlusion: a
  bucket the road never reached is still never painted, which is how a car behind a brow stays
  hidden. The partial crest clip reads `hillClip` and does not care when it is called.
- Changed: **and only what stands on the road is held back.** The first build held back every
  sprite and a capture showed why that is wrong - a bridge tower came up through the tunnel
  ceiling in red lattice. A sign, a gantry and a tower are OUTSIDE the tube and the wall is
  correctly in front of them. Traffic, police, rivals, roadblocks and crates are on the
  carriageway with you, and only those go over the wall.
- Changed: **the far end still goes black, over the cars as well as the road.** The depth fade
  moved into its own pass after the traffic, so a car deep in the bore is swallowed by the same
  darkness the tarmac is instead of hanging in it as a lit sprite. The fade and the ceiling
  lamps keep the order they had with respect to each other.
- Added: **`tools/bore-order-test.py`**, which settles a draw order in pixels. The road is
  frozen, one car is parked at a stated distance and offset, and the canvas is differenced with
  and without it. The control is that same car moved back to the middle of the road: the walls
  converge on the vanishing point, so they close over the EDGES long before the middle, and the
  centred car is an identical sprite at an identical size under identical light.
- Note: **the first version of that check passed with the defect present.** It compared a
  tunnel against FARMLAND, which has moving scenery and so differs from itself by hundreds of
  pixels, and it measured a car at the centre of the road where the bore never covered it. The
  defect was put back and watched failing before the rewrite was believed: a car at the road
  edge keeps 15 to 75 per cent of itself with the bore over it and 82 to 99 with the bore under
  it, and the check reads the worst of twelve placements.

<a id="v0-11-15"></a>
## [0.11.15] - 2026-09-01
- Fixed: **the tunnel is not transparent any more.** Owner, 2026-09-01, on a capture of the
  mouth: "why is that tunnel transparent?" Its opacity WAS the crossing ramp - the bore was
  laid over the ordinary world with the place's own darkness as its alpha, so halfway through
  a transition the whole thing was at half opacity and the farmland behind it showed straight
  through ([RLG-144](../fragments/RLG-144.md)).
- Note: **two things were fused and they are not the same.** How dark it is inside a bore is a
  property of the place and should ramp. Whether the WALLS EXIST is not a matter of degree.
  That is the same split [RLG-094](../fragments/RLG-094.md) had to make between what a city
  looks like and what colour it is at this hour.
- Changed: **so the crossing decides the EXTENT rather than the opacity.** The tube is built
  from the tunnel's own mouth inward, which the event record already holds to the world unit,
  and stops at the far portal. Measured across an approach: the mouth stands 27,564 units
  ahead, closes to 9,741, then reaches the camera - while the darkness ramps 0 to 1 over the
  same stretch. Two numbers moving independently.
- Note: **and the darkness kept its real job**, so the mouth is still a ramp rather than a cut
  and [RLG-060](../fragments/RLG-060.md)'s comfort argument still holds. The check asserts
  both halves: a build that made the walls solid by freezing the ramp would have passed a
  check that only looked at the walls.
- Fixed: **the debug biome setter now arms the event too.** It placed a tunnel without one, so
  a harness driving into it measured a bore beginning at the camera - a state the real game
  never produces, and it read as a fault in the engine. The setter already rolled the side and
  the climate for exactly this reason.

<a id="v0-11-14"></a>
## [0.11.14] - 2026-09-01
- Added: **the tunnel does the opposite of the bridge.** Owner, 2026-09-01: "the tunnel does
  the opposite - when you enter it goes down and then its verticality is capped to 0, and at
  the end of the tunnel it moves back up to meet the ground of the next biome." It is the
  bridge's own profile with the sign turned over, through the same machinery, and nothing new
  was built for it - which is the test of whether the event mechanism was a mechanism
  ([RLG-143](../fragments/RLG-143.md)).
- Note: **[RLG-112](../fragments/RLG-112.md) deliberately withheld this and was right to.** It
  gave the bridge a profile and not the tunnel, because the owner had already capped a bore's
  form at 0.10 on both axes and one combined field would have overruled that ruling. The owner
  has now stated the tunnel's shape directly, so the caution was waiting for a ruling rather
  than avoiding work. The 0.10 cap stays: the profile governs the vertical inside the event
  and the cap governs what little the bore does outside it.
- Note: **and the mouths meet, which RLG-143 named as where it would fail.** Zero SLOPE at
  each end is not zero HEIGHT, and it is the height that has to match the place either side.
  The two ramps are equal and opposite so the integral is exactly zero - checked at 0.000000
  before any of it was wired up. Measured across the crossings: the bridge runs 0 to +42 and
  back, the tunnel 0 to -24 and back.
- Added: **a second accumulator that runs the ordinary terrain straight through an event**, as
  though no profile were in force. It is the level the land would have been at, and the
  difference between it and the road is the crossing's own height.
- Note: **the water is NOT yet drawn at it, and the obstacle is a units one.** Both
  accumulators are read through functions that subtract the player's own value - which is what
  makes the road drawn relative to the camera, and is correct for the road. It is wrong for
  the water: at the car's own position the subtraction makes the difference zero, so the sea
  rose to meet the deck exactly where it should have been furthest below it. The rise has to
  enter the projection as a WORLD height, the way the tunnel's ceiling does, rather than as a
  screen offset added afterwards. That is the same mistake the bore's roof made and it cost
  three builds there. `WATER_DROP` stands until then, and it is still a constant picked by
  eye.

<a id="v0-11-13"></a>
## [0.11.13] - 2026-09-01
- Added: **a fleet rather than one boat** - sailboats, speedboats, fishing boats, ocean
  liners and tankers. Owner, 2026-09-01: "not just some sailboats. Some speedboats and ocean
  liner or tanker" ([RLG-112](../fragments/RLG-112.md),
  [RLG-059](../fragments/RLG-059.md)).
- Added: **coastal carries them too, as scenery on the seaward side.** Owner: "the boat gonna
  be painted on the ocean as scenery details." A first attempt placed them by distance the way
  the bridge does and the owner read them as skyline detail - correctly, because a coast's sea
  is at the ground's own level and converges on the horizon, so every boat came out in a
  three-pixel band beside the headlands. The scenery system already knows how to size, cull,
  fade and mirror a thing, and the seaward side has drawn nothing since the coast was built.
- Fixed: **a tanker is 330 metres, not 117.** Owner: "had a small tanker - see in that picture
  tankers are huge." It had been sized by eye against the small craft beside it rather than
  against the thing it is.
- Fixed: **and the fleet is ONE table now, which is the real fix.** Owner: "please make sure
  these sizes are carried over to the bridge biome." They could not have been - the bridge and
  the coast had two independent size tables, so correcting one left the other. That is the
  same shape this project has been caught by three times. Every vessel is stated once in
  METRES and KNOTS and both waters convert through the car's own known length.
- Added: **and they move, against a clock of their own.** Owner: "can we have them moving from
  one side to the other?" Against `seaClock` and never against the camera - a lateral position
  derived from `pos` is not a position in the world. Not the day clock either: a harness has
  to be able to move the sun, and moving the sun must not teleport the shipping.
- Note: **the real knots give the owner's ordering for free.** "Tankers will barely be moving,
  sailboats will be a little bit faster and speedboats will be ripping." In absolute terms a
  tanker at fifteen knots is faster than a sailboat at six - so that ordering is about the
  angular rate, and a tanker is a mile out where a sailboat is a few hundred metres. Measured:
  tanker 0.88 pixels a second, sailboat 3.89, speedboat 35. Nothing is tuned to imitate it.
- Changed: **the coastal islands are clipped to the water.** Owner: "I don't mind keeping the
  island looking skyline over the water, but we need to remove it from the land side." The
  skyline has never known which side the sea is on - one band tiled across the whole horizon,
  right for every place with the same thing all the way round and wrong for the one that has
  not. Clipped at the road's own vanishing point, which is where the shoreline reaches the
  horizon.
- Changed: **the seaward check was rewritten rather than deleted.** `coast-test` asked that
  NOTHING be drawn on the seaward side, which the boats violate by design. The invariant it
  was protecting was never "the sea is empty" but "no palm stands in the water", so it asks
  that now, by spec key.
- Note: **not clean, and it should not be read as clean.** With the island clip in, coast-test
  failed about three runs in thirteen; without it, one in twelve. The failures are spread
  across three different checks and one is the shoreline-join flake the audit already records
  at one run in four. The mechanism argues against the clip - it paints only above the horizon
  and the failing check samples below it - but the cause was not isolated.

<a id="v0-11-12"></a>
## [0.11.12] - 2026-09-01
- Fixed: **the bridge no longer ends in mid-water.** Owner, 2026-09-01: "the end of the
  rendered bridge ends under the horizon, which wouldn't happen." The road is drawn for DRAW
  segments and stops short of the vanishing point - on land the far field fills that gap with
  more ground and nobody reads it as an end, but on a bridge the STRUCTURE stops in the middle
  of a stretch of water ([RLG-112](../fragments/RLG-112.md)).
- Note: **the technique is [RLG-093](../fragments/RLG-093.md)'s and it is not an
  extrapolation.** The note on the sea's far band records that estimating the angle from the
  last two slices measured WORSE - at the far end of the draw two neighbouring slices are a
  fraction of a pixel apart vertically, so the slope is a small number over a smaller one, and
  it put the crease at thirteen times the edge's own curvature. So the deck's walk asks `proj`
  the same questions the drawn slices ask, in the same steps, until the horizon. A shorter
  walk is its failure mode, never a wrong one.
- Note: **the lane markings are the one part not carried**, and RLG-101 already says why: a
  dashed line is a strobing pattern that has to keep its phase, and past a certain distance a
  marking is under a pixel wide anyway. The tarmac, the kerb and both rails are carried.
- Changed: **the tarmac's colour has one definition and two callers now**, so the far stretch
  cannot disagree with the slices below it - which is exactly where a join shows.
- Note: **the check reads the walk, not the pixels, and that was decided after trying the
  other way.** Two things sit exactly where the deck's tip is and cannot be told from it by
  colour: the skyline's own headlands, which are dark silhouettes on the horizon line, and the
  ironwork's stanchions. Scanning the road's vanishing column is worse - near the horizon the
  road is at a finite distance and the bend puts it well off that column, so one unchanged
  build read 353, 356, 358 and 397 on four runs.
- Note: **it closes 8.4 px of a 12.6 px gap by sampling and the rest by construction.** The
  polygon ends on the vanishing point itself, which is a value rather than a trend. A road
  converging on a vanishing point is a POINT there, so reaching the skyline exactly is not
  something to ask a picture for.

<a id="v0-11-11"></a>
## [0.11.11] - 2026-09-01
- Fixed: **the bridge is suspended above the water rather than floating on it.** Owner,
  2026-09-01, correcting the first cut: draw "only the tarmac and the bridge structure and
  leaving the water to be just the far edge rendered blue so the bridge looks suspended
  hundreds of feet above water" ([RLG-112](../fragments/RLG-112.md)).
- Note: **the fault was a perspective one.** Every slice painted water from the ROAD'S OWN
  LINE downward, so the sea met the kerb and converged at exactly the rate the tarmac did.
  That is what a surface at the road's level does, and it is why the crossing read as a
  causeway.
- Note: **the suspension is drawn as DISTANCE, because it cannot be drawn as geometry.**
  Every surface this engine draws sits on one ground plane. But a plane far below the eye is
  a plane a long way AWAY - water thirteen camera heights under the deck reads 0.34 of the
  draw distant at the foot of the frame, against 0.02 for the tarmac at the same screen row,
  seventeen times further. "Far off" is something this engine already paints.
- Added: **little boats scattered on the water below.** Owner: "the same as intended to be
  used on coastal but smaller since they are 'further away'." The smallness is not a setting
  - a boat sits on the water plane, so the nearest one that can appear is already ten
  thousand units off and the painter comes out tiny without being told to. They are also
  what gives the drop its scale: a flat colour has no size in it, and a boat is a known one.
- Note: **these boats are not blocked by the culling question the coastal ones are.**
  [RLG-059](../fragments/RLG-059.md) deferred the coast's boats because they stand outboard
  of the lamp posts, so [RLG-073](../fragments/RLG-073.md)'s rule governs them. A boat on the
  water below a bridge stands on no ground plane at all.
- Fixed: **two wrong scatters before the right one, and the second is the instructive one.**
  A fixed lateral spread put all but one boat off the sides, because the offset that lands
  in frame runs from 14,000 units at the foot to 357,000 at the skyline. An ANGULAR spread
  fixed that and was worse: it makes a boat's position in the world depend on where the CAR
  is, so the boats swim sideways to stay on screen. Both looked fine in a still picture. It
  is a fixed world offset now, sized for the band boats are actually seen in.
- Note: **and the harness checks the fault that was actually made.** It reads each boat's
  world place, drives on, and reads again - nothing may have moved. On the angular build ten
  of ten moved.
- Added: **all of it in the mirror**, through the same painter with the glass's own scale and
  horizon - and walking the water BEHIND the car, which the first cut did not: it would have
  shown the boats in front of you, and looked perfectly plausible doing it.

<a id="v0-11-10"></a>
## [0.11.10] - 2026-09-01
- Added: **the bridge wears its red truss.** Owner, 2026-09-01: "the bridge needs its red
  truss, like Golden Gate Bridge." International Orange, which is the colour the Golden Gate
  is actually painted and is not pillar-box red - a railing down both sides of the deck on a
  concrete kerb, suspender ropes, the main cable, and towers that pass overhead
  ([RLG-112](../fragments/RLG-112.md)).
- Note: **not the towers - the RAILING is what a driver sees.** RLG-112 says the deck is the
  part a player sees at speed, and it is right: what runs past for the length of the crossing
  is the rail with the ropes rising off it, and a tower passes occasionally. So the rail, the
  ropes and the cable are drawn per slice in the road pass, where they inherit the crest
  occlusion and the far-to-near ordering for nothing.
- Note: **the tower is a gantry built tall**, which is the machinery RLG-112 named. Nothing
  about it is a skyline problem.
- Fixed: **the red-and-white rumble strip had to go on a deck.** It is the single strongest
  thing in the frame saying ORDINARY ROADWAY and it runs the whole crossing. A first attempt
  painted the kerb the ironwork's own colour and merged the two into one solid orange ribbon
  lying on the deck - a railing needs something to stand up from. Grey concrete, which is
  also what is there.
- Fixed: **seven towers, not the Golden Gate's two, and the constraint is geometric.** A
  tower is culled at the draw distance like everything else, and the cable rises to tower
  height wherever a tower stands - so towers further apart than the draw leave the cable
  climbing to a peak with nothing at the top of it. Measured at four towers: a probe of the
  live game found no tower inside the draw at all, one 1,600 units behind and the next 42,000
  ahead. Seven puts the bays at 27,349 against a draw of 30,000.
- Fixed: **the towers were drawn past the end of the road.** Every tower on the crossing was
  painted at once and they stacked up at the vanishing point, which read as a ladder standing
  in the sea. They are culled and faded at the draw distance now, the way
  [RLG-073](../fragments/RLG-073.md) settled for the scenery.
- Fixed: **a tower has a portal, not a ladder.** Five evenly spaced braces starting above the
  deck came out as a gate across the road. A suspension tower has a large open opening at
  deck level and two or three braces well above it, and the opening you drive through is most
  of what says the thing is a tower.
- Added: **and all of it is in the mirror.** Owner: it "needs to be properly visible in the
  mirror". One painter, two callers - it takes the view's own vertical scale as an argument,
  so the glass gets the same railing, cable, ropes and towers from one definition. The posts
  and ropes are spaced by world position rather than by segment index, because the mirror
  walks in 900-unit steps against the road's 200 and an index cycle would put the rail on a
  different pitch in each view.

<a id="v0-11-9"></a>
## [0.11.9] - 2026-09-01
- Fixed: **the canyon skyline stands no higher than the canyon walls.** Owner, from the
  device: "The skyline should only be as high as the canyon walls (scenery)." It was six
  times higher - a stated 281 pixels of band against a tallest wall of 47 - so the horizon
  read as a mountain range standing behind a canyon rather than as the canyon closing
  ([RLG-104](../fragments/RLG-104.md)).
- Note: **the cap is not a matter of taste.** The skyline is painted AT the horizon, which is
  further away than any scenery in the game, so nothing there may be taller on screen than
  the last thing the road pass draws. A place asks for the cap now instead of stating a
  height, and it is derived from that place's own roadside scenery through the same
  expression the scenery is sized with. Measured after: 47.3 pixels against 47.3.
- Fixed: **the canyon floor is the same stone as its walls.** Owner: "Same colour AS the
  canyon walls themselves." The walls were painted from the rock table and the ground from
  the biome's own grass pair, which was a brown chosen to sit beside the rock rather than to
  be it. The sandstone is stated once now and read by three - the ground, the wall art and
  the silhouette - so a canyon is one stone at every distance.
- Note: **both faults had one shape, and it is worth naming.** A constant chosen to match
  something derived is a constant that drifts, and both of these had drifted before they ever
  shipped. It is the same shape as the three name branches this place has already had
  removed.
- Note: **the first version of the check passed on the build the owner rejected.** It
  asserted the canyon's band was TALLER than an ordinary horizon - which was true, and was
  the fault. A ratio cannot answer a question about two things on screen, so the two heights
  are compared in pixels now, with a second assertion in the other direction so that a cap
  satisfied by drawing no horizon at all fails too.

<a id="v0-11-8"></a>
## [0.11.8] - 2026-09-01
- Added: **the bridge is over water, on both sides, all the way to the skyline.** Owner,
  2026-08-31: the water "would be drawn as a complete surface underneath the bridge". Every
  surface this engine draws sits on one ground plane, so a second altitude is not something
  the projection can express - and [RLG-112](../fragments/RLG-112.md) says to try the CHEAP
  answer first and let the picture decide, because the far sea was built twice and the
  version that measured better made no estimate at all.
- Note: **the cheat is that the place's GROUND is water.** The whole width of every slice,
  both sides, out to the frame edges, with the road painted over it exactly as it is painted
  over grass anywhere else. Every hard part of the coast is absent - no side to roll, no
  beach to converge, no shoreline, no join. What is kept is the distance recession, because
  water at one flat colour reads as a painted floor.
- Fixed: **a far-field rectangle written for it was dead code, and the harness is what
  proved it.** `groundBase` serves the far field ahead and the band under the mirror's own
  horizon, so answering the water question there covers both - the band was being painted
  twice in two slightly different tones. Removing it changed the row under the skyline by
  nothing at all: 480 of 480 pixels either way.
- Fixed: **the bridge's unused ground colour was water-coloured, which made the check
  unfalsifiable.** It was written as a second sea tone on the reasoning that a place with no
  ground colour reads as an omission - and then removing the water left a ground that was
  still blue and still passed every pixel test. A FALLBACK THAT LOOKS LIKE SUCCESS HIDES THE
  FAULT. It is the headland the bridge springs from now, so with the water taken out the
  road runs over grass and all four water checks read 0 of 480.
- Note: **one control is printed rather than asserted on.** The coast's row under the
  skyline came back 238, 183 and 340 of 480 on three runs of one unchanged build - its shore
  converges on the road's own vanishing point, which the bend moves across the frame. An
  assertion on it would fail at random, which is the failure mode `occlusion-test.py` was
  written against.
- Note: **it is a causeway, not yet a bridge.** The towers, the cables and the deck - its
  surface, its expansion joints and the rail down each side - are the next two pieces of
  work, and RLG-112 says the deck is the part a player sees at speed rather than the towers.

<a id="v0-11-7"></a>
## [0.11.7] - 2026-09-01
- Added: **a place can be an EVENT rather than a place - a stated length and an authored
  shape.** Owner, 2026-08-31, describing a bridge: "start with a vertical ramp up, be flat
  the entire way and then ramp down at the end." Nothing in the engine could say that. Every
  place lasts six and a half to twelve miles at random and its terrain is rolled segments
  scaled by the place's own relief - right for a forest, which is a tendency of the land, and
  wrong for anything somebody built ([RLG-112](../fragments/RLG-112.md)).
- Note: **two fields, and that they are separate is the test of a mechanism.** A tunnel takes
  the length and NOT the shape, because the owner has already ruled on a bore's form and
  capped both of its axes at 0.10. One field would have overruled that ruling to get a
  bridge.
- Fixed: **a tunnel is a tunnel's length again.** It was the ordinary roll - at the speed the
  interstate is actually driven, two and a half to four and a half MINUTES underground
  against a run clock that starts at sixty seconds, so a bore could outlast the run it
  appeared in. 1.4 miles now, which is about eleven seconds.
- Added: **BRIDGE, the first place that is an event** - 1.7 miles, the Golden Gate's own
  length, with a ramp at each end and a dead flat deck between them. The water under it is
  the next piece of work; today the road runs over a fill.
- Note: **an authored profile states a SLOPE, not a grade, and that is the whole design.**
  The integration is `dy += grade; y += dy`, so a grade is the rate of change of the slope.
  Ask for a flat deck by stating a grade of zero and you get a straight ramp continuing to
  the horizon - measured, at a constant +0.017 forever. The profile replaces the slope.
- Note: **the check reads the road, not the table.** The rolled segments are still generated
  inside an event and the integration overrules them, so anything reading the segment list
  is unchanged and would be green on a build where the profile does nothing at all.
  `tools/event-test.py` reads the integrated cache - the road the picture draws and the car
  drives on - and both ways of getting it wrong were put back and watched going red.
- Note: **the bridge became a passage by stating one field**, so a run cannot open on it
  and nothing else had to change. That is [RLG-140](../fragments/RLG-140.md)'s own claim
  paying for itself one version after it was made: `tools/tunnel-test.py` asserts both
  places rather than being loosened to let the new one through.
- Note: **the vertical shape needed a mechanism and the horizontal one did not.** Nothing
  authors curvature: a suspension bridge is straight because it is built straight, so it
  says so with a low sinuosity the ordinary generator already reads.

<a id="v0-11-6"></a>
## [0.11.6] - 2026-09-01
- Fixed: **a run can never open in a tunnel.** Owner, 2026-09-01: "runs can never start in
  a tunnel or on a bridge." A run picked its first place with a flat roll over every entry
  in the table, so about one in eleven began already inside the bore, with the mouth behind
  the camera and no approach to it - measured at 35 of 400 rolls on the engine before this
  ([RLG-140](../fragments/RLG-140.md)).
- Note: **it is a stated property, not a name the picker knows.** A tunnel and a bridge are
  not places at all - they are events with a mouth, a length and an exit, where every other
  entry is a place that lasts six to twelve miles at random. A place states `passage`, so
  the bridge of [RLG-112](../fragments/RLG-112.md) needs no second edit the day it lands.
  This is the fourth name branch removed from this file in two versions.
- Note: **the way this fix goes wrong is by deleting the tunnel from the game.** There is
  one list of places and the running game picks the NEXT one from it while you drive, so
  filtering that list would make a tunnel unreachable - and no check on the opening draw
  alone would notice. The second list is read by the opening and by nothing else, and
  `tools/tunnel-test.py` asserts both halves. Both failure modes were put back and watched
  going red.
- Changed: **the version and the engine's own build stamp move together again**, which is
  what [RLG-139](../fragments/RLG-139.md) is about.

<a id="v0-11-5"></a>
## [0.11.5] - 2026-09-01
- Added: **CANYON - the place whose distance is a wall.** Owner, 2026-08-31: of the four
  gaps offered, canyon and tunnel are the two to build. **It is the tunnel's opposite.** A
  tunnel has no distance in it at all, so the far field is painted over; a canyon has
  plenty of distance and every bit of it is rock
  ([RLG-104](../fragments/RLG-104.md)).
- Added: **a horizon that is one mass rather than a row of objects, and it is built once.**
  Three places asked the skyline generator for the same missing thing before any of them
  was built - this wall, the bridge towers and the jungle canopy - so it is a table
  (`SKY_CONTINUOUS`) and a planner (`contPlan`) rather than three special cases. The crest
  is a bounded random walk and each segment carries the height at both of its ends, so the
  silhouette is connected by construction instead of by the gaps happening to be zero.
- Fixed: **and the crest closes on itself, because the skyline sprite tiles.** A walk that
  ended where it liked would put a cliff at the seam and then repeat that cliff across the
  whole horizon. The last fifth of the walk is bent back onto its own first sample.
- Note: **the seam is the only rule that separates a wall from a row of objects, and that
  was measured.** The first version of the check asserted that a continuous crest never
  jumps, and it went red on the controls - a peak line overlaps its own neighbours, so
  MOUNTAIN and TUNDRA have no gaps AND a small step and are still rows of peaks. Nothing
  but a closed walk plans the two ends of a tile together; MOUNTAIN misses the seam by 60
  pixels. `tools/canyon-test.py` runs all three rules on every place on the board, which is
  what makes it a measurement rather than a restatement.
- Added: **a place says how tall it stands its skyline.** The band was a fixed eighth of the
  frame everywhere, which is right for a horizon miles off and wrong for a wall a few
  hundred feet away. The canyon states 2.4, the mirror takes the same multiple, and nothing
  else on the board changes.
- Fixed: **the wall's shading is continuous too, and the first capture is why it had to be.**
  Each falling face was shaded by its own drop, so the shading ended where the segment did
  and the wall came out as a row of upright panels - the row of objects the form exists to
  stop, painted back over a continuous silhouette. One cap depth everywhere makes
  neighbours share an edge exactly.
- Changed: **two name branches went with it.** `buildSkyline` chose its silhouette colour by
  testing for TUNDRA; a place states `skyBase` now. `ROCKFACE` took a `snow` boolean and
  could only ever be grey rock or white rock; it takes a named tone, and the canyon walls
  are the mountain's own ranks in sandstone rather than a sixth set of art
  ([RLG-102](../fragments/RLG-102.md) removed the same shape from the horizon forms).
- Changed: **the walls are the scenery system, not a second one.** RLG-104 calls them the
  largest possible instance of the far-scenery question, so they are built from the ranks
  MOUNTAIN already uses - tight to the kerb, packed until the silhouettes overlap into one
  mass, and reaching back until the rock has no visible far edge. They inherit whatever
  [RLG-073](../fragments/RLG-073.md) decides about culling instead of needing it now.
- Fixed: **the engine stamps its own build again.** `window.ROAD_BUILD` sat at 0.9.15 while
  the shell moved 22 versions past it, so the BUILD row in SETTINGS has been reporting a
  half-updated cache on every build since - the one instrument for the fault that once
  black-screened the game was crying wolf
  ([RLG-139](../fragments/RLG-139.md)).
- Note: **not judged on a device.** Whether the strip of sky between the masses reads as a
  canyon at speed, whether the far bands recede or merely go pale, and whether a road at
  0.90 of bend between walls is comfortable on a phone are the owner's call.

<a id="v0-11-4"></a>
## [0.11.4] - 2026-09-01
- Changed: **traffic engines carry six car lengths, rivals twelve.** Owner, having driven the first
  cut: "Let's make it about six car length", and "Make opponent racers 12 car length." It was 36,000
  units before this work - over a quarter of a mile, further than the drawn world - and 6,000 after
  the first pass, which was still sixteen lengths.
- Note: **it is a ROLE, not a body.** Three standing rulings forbid a branch naming a vehicle class to
  get a behaviour, and this does not: a supercar in traffic is heard at six lengths and a roadster in
  the race at twelve, because what differs is whether it is racing you. The distance rides on the
  vehicle as `earshot`, so the mix reads a property rather than asking what something is. And the
  numbers are written in car lengths rather than units, which stays true if the road ever gets wider
  ([RLG-105](../fragments/RLG-105.md)).

<a id="v0-11-3"></a>
## [0.11.3] - 2026-09-01
- Fixed: **the tunnel walls are tight to the roadway, and the fault was draw order.** Owner: "the
  walls just aren't tight to the roadway. There's like 100 or 200 feet outside of the roadway to the
  wall." I moved the width four times and sent a capture each time; the owner was right that they
  looked identical. TWO real faults: a UNIT ERROR - the cornfield's offset is in roadside units and
  mine multiplied the road half-width, an order of magnitude larger - and then, after that was fixed
  and the wall measured TIGHTER than the corn, the verge was still being painted over its foot
  because `drawRoad` ran after the bore. The bore draws after the road now
  ([RLG-105](../fragments/RLG-105.md)).
- Fixed: **the ceiling is a plane above the camera.** It was placed as an offset from the road's own
  projected height, which is how a roadside object is placed and not how a roof works - so the near
  section fell below the frame and nothing converged where the player was looking.
- Changed: **the wall sits outside the drivable shoulder.** Owner: "the car is clipping through the
  wall when I pull over to the side." The player reaches 1.18 of a half-width and the tarmac ends at
  1.00, so the shoulder is driven on - the wall was at 1.083 and the car went through it. It is at
  about 1.25 now, with crates untouched at 0.86 to 1.02.
- Changed: **a road tunnel is brightly lit.** Two reference photographs from the owner settled it -
  pale tiled walls, a lit vault, a bright road. The darkness of a tunnel is the sky being gone, not
  the scene going dark. Two rows of intermittent overhead lamps, at the owner's choice over the
  continuous runs the photographs also show.
- Changed: **the far end fades to black**, as a run of quads rather than a hard cap - a cap read as a
  black rectangle beside the tunnel on any climb or bend. And the outward wall fill is a receding
  SURFACE rather than a rectangle to the frame edge, which covered half the frame on a hard corner.
- Changed: **both of the tunnel's shape axes are capped at 0.10.** Owner: a bore that climbs and
  swings reads wrong.
- Added: **a wash of reverb on the car's own voices in a tunnel.** Owner: the engines, brakings, tyre
  squeals, sirens and horns. All of those are HELD voices built once at the start of a run, so a
  per-voice send could not reach them - there is one send per bus now, opt-in so a crate chime stays
  dry, driven by the same ramp the eye follows.
- Changed: **another car's engine is heard at sixteen car lengths, not a quarter of a mile.** Owner:
  "I don't really hear a car engine unless I'm pulled up on it." It was 36,000 units, so every car in
  a stretch longer than the drawn world was in the mix. 6,000 now. This one is general and not about
  tunnels.

<a id="v0-11-2"></a>
## [0.11.2] - 2026-09-01
- Added: **TUNNEL - the one place on the board that is dark by day.** Owner: nothing else is, and that
  is the whole point. The place is a third term in the SAME `lampsOn` expression that already took the
  hour and the weather, so every lamp in the game - the beams, the street lighting, all 178 declared
  lamps across 59 vehicles - lights inside it without a second route. Measured: at midday the lamps
  read 1.00 while the day clock still reads 0.00, so the sun did not move
  ([RLG-105](../fragments/RLG-105.md)).
- Added: **a real bore, with walls and a ceiling over the camera.** Owner: "The tunnel needs 3D walls
  and a ceiling above the camera." The first build filled the sky with a dark gradient, which is a
  hole cut in the picture rather than an enclosure. It is sampled off the road's own projection at
  sixteen distances, so the walls converge and bend with the road, and the near samples project above
  the top of the frame.
- Added: **a hillside with the bore cut through it.** Owner: "Entering it also requires a forward wall
  or cliff face or mountain side something." Without one the entrance was a dimmer rather than a
  place. One piece of geometry serves both ends: entering, the arch is dark and the rock is in
  daylight; leaving, the same arch is bright, which is the light at the end of a tunnel.
- Changed: **entering is abrupt and leaving is not.** A straight blend darkened the world 36 segments
  BEFORE the mouth, so the car dimmed while still in the open. Going in runs over 18 segments once the
  mouth is reached because a portal is sudden; coming out eases over the full 36, because the
  brightening is the photosensitivity hazard and the eye adapts to light more slowly than to dark.
- Fixed: **a latent snap in every weather-band quantity.** The darkness faded smoothly to 0.47 and then
  CUT to 0.00 in one frame: the ground pair collapses after 18 segments while the weather band is 72
  wide, so the blend was thrown away three quarters of the way through. **The snow floor had the same
  discontinuity and nobody had looked.** There is a separate pair now.
- Fixed: **the horizon form was a list of names.** `skylinePlanFor` branched on the biome's name and
  fell through to TOWERS for anything unrecognised, so farmland was given a city skyline - found by
  photographing it. A place states its form now, the way it states its rain
  ([RLG-102](../fragments/RLG-102.md)).
- Changed: **the cornfield runs off the edge of the screen.** Owner: "The corn needs to extend beyond
  the side of the screen. You can make the field less dense to accomplish this." The reach triples and
  the rank spacing pays for it, which is the owner's own trade.
- Removed: **the turn cautionary boards.** Owner: "We can completely remove the turn cautionary
  signs." The spawn goes and the painter stays, so they return by restoring five lines
  ([RLG-138](../fragments/RLG-138.md)).
- Added: **`tools/tunnel-test.py`** and **`tools/biome-shot.py`**, which photographs a place from the
  road and a mouth from the approach. It asserts nothing.

<a id="v0-11-1"></a>
## [0.11.1] - 2026-09-01
- Added: **FARMLAND - a cornfield down one side, houses and barns down the other.** Owner: "one side
  with a cornfield and the other side flat with houses and barns. Just like the ocean, the sides would
  be randomly decided at generation. The skyline would just be open sky just like ocean." The flattest
  place on the board at a relief of 0.10, which is the gap it was argued to fill
  ([RLG-102](../fragments/RLG-102.md)).
- Changed: **the coast's side roll is generalised rather than copied.** `seaSide` is `sideRoll` across
  all twenty-two sites that read it. A place says what it does with the side it rolled: the coast
  draws NOTHING there because it is water, farmland draws a different spec. One roll read by two
  places, so a place can never disagree with itself about which side it is - which is what a second
  roll would eventually produce.
- Added: **a cornfield is a texture with rows, not a scatter.** This is the part with no precedent.
  Every roadside in the engine jitters, and the eye reads woodland precisely because it is irregular;
  a planted field is the opposite. `lattice` skips the density roll and drops the jitter, and the
  perspective does the rest. Measured: the crop uses ONE distinct distance from the road per rank,
  the yards on the other side use sixteen.
- Verified: **both views agree which side is which** - 4,810 placements on the rolled side out of the
  windscreen against 250 on the other, and 2,758 against 68 in the mirror. And **the open sky cost
  nothing**: farmland states the coast's own cloud bias and needed no new code, which was the stated
  test of whether the coastal work was a tendency or a special case.
- Corrected: **a loose claim in [RLG-109](../fragments/RLG-109.md).** It said the weather swing gives
  farmland snow on "roughly three precipitation events in ten". Thirty per cent is the fraction of
  MOMENTS cold enough to snow at all, not the fraction of falls that come down as snow - the model
  gives 4.5% and the engine measures 3.8%. The model is right and the sentence overstated it.
- Added: **`tools/farmland-test.py`**.

<a id="v0-11-0"></a>
## [0.11.0] - 2026-08-31

**Slice checkpoint.** The owner played through every tournament, unlocking everything, and reported
five things; all five are built, and four further rulings arrived while they were being built. That
is a completed slice, so the minor version moves and the patch count resets - the rule is that a
minor bump marks a slice completing, and 0.10 ran to forty-six patches without one while several
slices closed inside it.

WHAT THE SLICE CONTAINED, in the order it was built:

- **0.10.40** the checkpoint boards stay in the mirror, and the finish banner joins them - two faults
  behind one sentence ([RLG-133](../fragments/RLG-133.md))
- **0.10.41** the transient messages sit under the mirror rather than across the road ahead, anchored
  to a measured band instead of a percentage ([RLG-134](../fragments/RLG-134.md))
- **0.10.42** a wet road carries you further than you asked, and you can aim with it
  ([RLG-048](../fragments/RLG-048.md), [RLG-132](../fragments/RLG-132.md))
- **0.10.43** a collision answers where it happened, and moves both cars
  ([RLG-131](../fragments/RLG-131.md))
- **0.10.44** a slick road runs you wide in a bend, measured rather than assumed
- **0.10.45** it precipitates about half as often, by one lever over the whole board
  ([RLG-136](../fragments/RLG-136.md))
- **0.10.46** the mirror carries the roadside the windscreen carries
  ([RLG-130](../fragments/RLG-130.md))

Earlier in the same day, 0.10.38 and 0.10.39 built the biome and climate model and then took the
owner's snow floors ([RLG-109](../fragments/RLG-109.md)).

**NOT ONE OF THESE HAS BEEN JUDGED ON A DEVICE.** Nine builds. Every one is verified by harness and
by measurement, and the things a harness cannot judge - whether the slip reads as a skill, whether
being shoved forward by a rival is satisfying, whether five ranks of mirror scenery is denser or
merely cluttered, whether a forest still holds 60fps on a phone - are all still open. The tunables
behind them are live so a device report can be answered without a rebuild.

<a id="v0-10-46"></a>
## [0.10.46] - 2026-08-31
- Changed: **the mirror draws the same ranks of roadside the windscreen does.** Owner: "The scenery in
  the rearview mirror is much more sparse than what it actually is in the front view. It should be
  the same or at least closely comparable." It drew ONE rank where a forest has five, and then thinned
  that rank with the per-rank density on top. Measured through the engine's own scenery trace: the
  glass drew 6% of the windscreen's objects and now draws 27%
  ([RLG-130](../fragments/RLG-130.md)).
- Changed: **the far-end cutoff is 2.2 pixels, not 1.5.** An object under two pixels in a pane 44 tall
  is a smudge that still costs a full draw, and the far end of a fifth rank is where the ranks cost
  their frames and contribute least.
- Note: **the frame-rate cost could not be measured here, and that is the finding.** Nine samples per
  arm in a forest, the heaviest place on the board: one rank ran 52.4-60.4, two ran 49.2-60.4, five
  ran 46.4-60.8. One rank with a TIGHTER cutoff - strictly less work than the shipped baseline -
  scored a LOWER minimum, so the minimum is noise. Two ranks and five are indistinguishable. The
  device is the judge, and `API.mirrorRows`, `API.mirrorNear` and `API.mirrorMin` are all live so a
  report from the phone can be answered without a rebuild.
- Unchanged, deliberately: **the near cull stays at a fifth of the pane.** It is the one of the three
  culls with a known fault behind it - the nearest trees filled the glass and buried the road and the
  cars on it. It is a lever now rather than a constant.

<a id="v0-10-45"></a>
## [0.10.45] - 2026-08-31
- Changed: **it precipitates about half as often.** Owner, after twenty to thirty minutes of play:
  "it seemed to precipitate a lot. Maybe we should reduce the overall chances of precipitation." The
  table averaged 0.366 and the weather rolls every 35 to 80 seconds, which is nine or ten events in a
  twenty-five minute session - a dry road was the exception. One multiplier at 0.55 over the whole
  board, so the places keep their relationship to each other
  ([RLG-136](../fragments/RLG-136.md)).
- Changed: **the scale is applied at the roll, not to the table.** Scaling the stated precipitation
  would have dragged everything derived from it down too: a tundra's snow chance would have fallen
  under the taper threshold, so snow carried into a tundra would have started tapering and silently
  reversed an owner ruling, and the cloud would have thinned with the rain. Applied at the roll, only
  the frequency moves - and an overcast day with no rain in it becomes commoner, which the sky model
  already calls the commonest sky there is.
- Measured through the engine's own roll: a forest has weather on 31% of rolls against 52% unscaled,
  and a swamp still has it on 37% against a desert's 2% - so the board was scaled rather than
  flattened. `API.precipScale` is live, because how much weather a session carries is judged by
  playing rather than by reading.

<a id="v0-10-44"></a>
## [0.10.44] - 2026-08-31
- Verified: **a slick road runs you wide in a bend, and by two mechanisms that compound.** Owner: "I
  want to make sure that it still plays into roadway turns, e.g. You are more greatly pulled to the
  outside curve due to slippage." It does. The cornering force already divides by grip, so a wet road
  pushes harder toward the outside on its own - and that push moves the wheel, which the slip model
  reads as a movement and adds its own overshoot to. Neither was written for the other, so whether
  they stack was a question rather than a certainty ([RLG-048](../fragments/RLG-048.md)).
- Measured: at a pinned curvature and a fixed speed over one second, a dry road runs the car to
  -0.038 and a snowy one to -0.089 - two and a third times as wide, to the same side, with the slip
  offset carrying a measurable part of it rather than the cornering force being the whole story.
- Added: **`API.holdCurve`**, which pins the curvature the cornering force reads. Finding a bend of a
  stated severity by driving is a search, and it would measure the road generator rather than the
  physics. The first version of this check used a hard bend for two and a half seconds and put BOTH
  arms against the edge of the road at -1.08, where the difference it exists to measure cannot exist.

<a id="v0-10-43"></a>
## [0.10.43] - 2026-08-31
- Changed: **a collision answers where it happened, and moves both cars.** Owner: "if I cut off an
  opponent and they hit me, I lose all my speed and they drive by me which kind of defeats the entire
  purpose of defensive maneuvering." The geometry was already being computed and then thrown away -
  both collision sites worked out how far apart the cars were and used it only inside `Math.abs()`,
  so the SIGN, which is who is in front, was discarded ([RLG-131](../fragments/RLG-131.md)).
- Changed: **the three cases are one expression, not three branches.** The relative speed already
  says who ran into whom: catching a slower car makes it positive, being caught by a faster one makes
  it negative, and the same subtraction moves speed the right way in both. Measured: rear-ending
  costs you 2,736 and gives them 2,303; being rear-ended gives you 2,736 and costs them 2,303. Exact
  opposites, which is the whole ruling in one line.
- Changed: **a sideswipe bumps both cars apart and costs almost no speed.** How square the hit is
  decides what it exchanges - along the road for a rear-ending, across it for a rub. One number
  separates the two.
- Changed: **mass comes off the vehicle's own width and length.** Three standing rulings forbid a
  branch that names a vehicle class to get a behaviour, so a lorry shrugs off a hatchback because it
  is a bigger object. Measured: hitting a lorry costs 2,837 and moves it only 1,418.
- Changed: **traffic, rivals and cruisers now share one collision.** Leaving the cruiser on its own
  path would have recreated the inconsistency this ruling removes. The PIT manoeuvre is untouched.
  Rivals keep their smaller damage and lose their unfair split - it was 0.80 against 0.86, so a rival
  who rear-ended the player lost less than the player did.
- Added: **`tools/impact-test.py`**, which stages a collision at a chosen geometry instead of driving
  into one and hoping. It also asserts that nothing is conjured: what one car gains the other loses,
  so a collision cannot become a speed source.
- Note: drive-test's nitrous assertion failed on two of three runs of this build and one of three of
  the previous one. Both arms fail it, the samples are too small to separate them, and this change is
  neither shown innocent nor guilty. Recorded rather than dismissed.

<a id="v0-10-42"></a>
## [0.10.42] - 2026-08-31
- Changed: **a wet road carries you further than you asked, instead of making the steering wiggle.**
  Owner: "when you turn the vehicle, it moves further than you intend based off of the Delta that
  you've moved so if you steer discreetly, there will be less slip, but if you make larger movements
  than the slip is larger too. The function of the slip is the wetness/iciness." The wiggle was the
  SHAPE of the equation and not a bad coefficient - a proportional term feeding a carried velocity is
  an underdamped oscillator, so tuning changed how long it wiggled and never whether it did
  ([RLG-048](../fragments/RLG-048.md)).
- Added: **the slip can be aimed at, which is the point of it.** Owner: "with practice, you can
  understeer to get the amount of steering you need given the environmental state of the ground.
  Instead of it being a pure hindrance, it's something you can learn to work with." That requires the
  overshoot to be proportional and NOT to fade, so it is bounded by the surface rather than by a
  timer - a fading slip means aiming short lands you short and there is nothing to learn. Measured on
  snow: aiming at 0.5596 to arrive at 0.700 landed at 0.7000 exactly.
- Changed: **the grip numbers are the ORIGINAL ones, deliberately.** They were halved for one build of
  this work, on a diagnosis that the size of the loss was the problem. Owner: "The original numbers
  may not actually necessarily need to be dialed back. It's just that the implementation we were using
  before was very unwieldy." Reverted, and the whole struct is live through `API.wetModel` and
  `API.slipModel` so it can be dialled in on a device without a rebuild
  ([RLG-132](../fragments/RLG-132.md)).
- Unchanged, by ruling: **braking stays a plain multiplier.** Owner: "it also directly affects
  braking, but that should be modelled more simply such that your braking grip is just reduced based
  on the wetness/iciness." It already was, and it is now checked as one.
- Added: **`tools/slip-test.py`**, which measures the model rather than the tuning: the overshoot is
  proportional to the movement, it survives three seconds, snow is a different curve from rain, a dry
  road produces none, and understeering by the predicted amount lands on the mark. Snow overshoots
  0.1978 of the movement, rain 0.0612 against a predicted 0.060, dry 0.0000. Two measurement faults
  were found and recorded rather than papered over: the first version measured collisions, and the
  second was reading a slip residue the previous surface had left behind.

<a id="v0-10-41"></a>
## [0.10.41] - 2026-08-31
- Changed: **transient messages sit under the mirror instead of across the road ahead.** Owner: "the
  UI elements that pop up in the dead center of the screen block my view of the upcoming road, so I
  think we should move that to just under the other information that's below the rearview mirror."
  TWO mechanisms were printing in the middle - the DOM banner and the canvas labels - and moving one
  would have left half the messages where they were, which no single screenshot would show
  ([RLG-134](../fragments/RLG-134.md)).
- Changed: **the band is measured from the information row rather than set as a percentage.**
  `top:38%` is why it landed on the road on one phone and not another. The row already anchors itself
  under the glass, so its own bottom is the honest answer to "just under the other information": the
  engine reads that rect and publishes `--msg-top`, and the canvas labels ask for the same number. A
  distance follows the thing it is a distance from.
- Changed: **the floating labels stop climbing back over the road.** They drifted 75 pixels upward,
  which was fine from the middle of an empty windscreen and would carry them into the mirror from the
  new band. And the banner is smaller - it was sized to be read across an empty windscreen and now
  shares the busiest band on the screen.
- Added: **`tools/message-band-test.py`**, which checks both cabinets and both mechanisms. Its first
  version compared the labels with the published variable, which is the engine agreeing with itself;
  it compares them with the banner's own rect. Falsified by putting `top:38%` back: the banner sat at
  328 against labels at 136, and every other check still passed - "below the row", "in the top half"
  and "clears the horizon" are all true of 328 on a 900-tall screen.
- Note: this answers the question [RLG-082](../fragments/RLG-082.md) was blocked on. It asked for
  anchored relative spacing without knowing which elements on which screen; playing the game named
  them.

<a id="v0-10-40"></a>
## [0.10.40] - 2026-08-31
- Fixed: **the checkpoint boards stay in the mirror instead of vanishing a second after you pass
  them.** Owner: "I still don't think I see the back of the checkpoints or the finish line in the
  rearview mirror." The mirror pass added in 0.10.36 was right; a board was being deleted 8,000 units
  after it was passed while the glass draws to 34,000, so it survived 0.06 of a mile - about a second
  and a half at 150mph, shrinking the whole time. The cull reads the mirror's own constant now, so the
  two cannot drift apart again ([RLG-133](../fragments/RLG-133.md)).
- Added: **the finish banner is in the mirror, which it never was on any build.** A second fault
  behind the same sentence, and naming the finish line separately is what separated them: RLG-108 was
  scoped to the checkpoint array, and the banner is a different object with a different painter that
  stops 600 units past the line. The chequered line on the tarmac is drawn as it is out of the
  windscreen, because paint on a road reads the same from either side; the board is not, so from
  behind you get its backing, its rails and the structure. Crossing the finish is the one moment in a
  race when what is behind you is the story.
- Fixed: **a harness probe whose default sat inside the bug it was meant to catch.** `parkGantry`
  parked a board 4,000 units back - inside the 8,000 that survived - so a check asking "is a board in
  the mirror" got yes on a build where a real one had already gone. It parks at 20,000 now, past the
  old cull and well inside the glass. Measured with the world held still: a board changes 1.84% of the
  pane against 0.03% for an unchanged world, and the finish line 1.35% against 0.00%.

<a id="v0-10-39"></a>
## [0.10.39] - 2026-08-31
- Changed: **the mountain lies under a tenth of snow and the tundra under a quarter.** Owner, having
  driven 0.10.38: "The mountains base snow floor should be .1 snowiness. The tundra base snow floor
  should be .25 snowiness." The model derived 0.24 and 0.48 and both were about twice too white. This
  is the model being tuned rather than corrected, and it is the move [RLG-109](../fragments/RLG-109.md)
  said to make: a number that falls out of a model changes in one place, and a number typed into one
  biome cannot.
- Changed: **the freezing pivot moved with it, because one coefficient could not give both numbers.**
  The two places sit at 0.40 and 0.80 of full cover against a pivot of 0.25 - a ratio of 1 to 2 - and
  the owner asked for 1 to 2.5. So ground snow now starts to lie at 0.22 rather than 0.25 and the
  coefficient is 0.32, which puts the mountain on 0.102 and the tundra on 0.247. Two constants fixed
  by two stated points is an exact fit with no freedom left in it, and that is said plainly rather
  than dressed up as a derivation - what it buys is that every other place still derives, so a city
  that rolls freezing lies under snow with no line naming it.
- Unchanged, and verified rather than assumed: **falling snow adds to the floor up to 1.0.** The
  second half of the ruling was already the behaviour - accumulation builds FROM the floor and is
  clamped at 1 - so nothing was changed for it.
- Changed: **three biome checks carried the old numbers and now carry the new ones.** The tundra and
  the mountain are asserted against the owner's figures rather than against whatever the engine
  reports, so a build that deleted the floor cannot satisfy them by agreeing with itself. The unwind
  check also had to move its starting level: its design is to begin JUST above the floor, where only
  the floor can stop the descent, and 0.58 stopped being just above anything when the floor halved -
  it failed by measuring the length of the run instead. Falsified by putting the old coefficient
  back: three checks fail. biome-test is 82 of 82.

<a id="v0-10-38"></a>
## [0.10.38] - 2026-08-31
- Changed: **a place states a climate and a day states its weather.** The biome table stated `rain`
  and `snow` as two separate chances, and MOUNTAIN declared 0.30 and 0.34 - two independent rolls
  summing to 0.64, so the place was asked twice whether it had any weather at all. A place now states
  a temperature and one precipitation chance, and rain, snow and the settled ground floor all derive
  from the two. The impossible state is not fixed, it is unrepresentable ([RLG-109](../fragments/RLG-109.md)).
- Changed: **the temperature is rolled once per visit, so one recipe is many places.** A city has no
  climate of its own and rolls the widest range on the board: drive into one and it is under snow,
  into the next and it is warm rain, with nothing in the code naming either. This is what replaced a
  `neutral` flag - neutrality stated by degrees rather than as a boolean, so a narrow-ranged place can
  only sit among places of its own temperature and a wide-ranged one fits wherever it lands.
- Added: **a second temperature, so a temperate place has snowy days without being a cold place.**
  Owner: "farmland can be snowy, but you have snow chance at zero." Computing the rain-or-snow split
  from the PLACE's temperature dry-locks everything above 0.50 out of snow for ever. A weather event
  now rolls its own temperature within `CLIMATE_SWING` of the instance's, so snow is an EVENT rather
  than a property - a place where it always snows is scenery. Measured: the forest snows on 20% of
  what falls on it, the tundra on 81%, the desert and the swamp on none of 1,200 events each. ONE
  global swing gives all four, which is the test of a model rather than of a tuning.
- Changed: **the snow on the ground derives from the cold, so it is no longer the tundra's property.**
  `snowFloor` was typed into one recipe. It comes off the instance temperature now: the tundra derives
  0.48 against the 0.50 that was typed in, the mountain gains 0.24, and a city that rolls cold lies
  under snow for the same reason a tundra does.
- Changed: **`cover` becomes `bias`, and the cloud calculation gets shorter rather than longer.** It
  was `(rain + snow) * 1.6`, and `rain + snow` was always exactly `precip` - the two were a split of
  one quantity, and how the water falls has no bearing on how much cloud is overhead. The field was
  also renamed because `cover` read as ground cover next to `snowFloor` and a multiplier where 0.45
  means CLEARER is backwards on a first reading.
- Added: **any sky can be clear and no sky is ever total.** Owner: "we should probably always allow
  for some clear sky, no matter what." The roll's low end was 0.35 - a proportion of the place's
  tendency rather than a floor under it - so a wet place could never roll a clear day. It reaches
  zero now, and `CLOUD_MAX` at 0.88 is the ceiling. Lowering the roll cannot produce rain from a blue
  sky, because the floor while it is raining is set by the rain and not by the roll.
- Changed: **the two taper thresholds moved with the model, so the owner's three cases still behave.**
  `WEATHER_KEEP` and `WEATHER_THIN` read odds that are now on a different scale - tundra snow was 0.62
  and is 0.135. Leaving them would have silently reversed the ruling they exist to serve. One case
  genuinely changes and cannot be avoided: rain into a desert thins over the whole crossing rather
  than a third of it, because desert rain at 0.04 and city snow at 0.038 cannot be separated by any
  threshold, and the city is the one the owner ruled on by name.
- Changed: **the harness reads the instance, and one check proves the engine does too.** Every biome
  probe read the RECIPE, which is the exact shape this refactor could hide: a check on the recipe stays
  green while the game reads something else. `biomeOdds()` with no argument returns the running
  instance; `sampleWeatherRolls` calls the engine's own `rollWeather` and counts what came out.
  Falsified by putting the half-migration back - with `rollWeather` on the recipe, both a cold city and
  a warm one give the recipe's answer, that one check fails, AND EVERY OTHER CHECK STAYS GREEN.
  biome-test is 81 of 81, up from 64.

<a id="v0-10-26"></a>
## [0.10.26] - 2026-08-31
- Added: **race opponents have a chance of wearing stripes.** Owner, correcting what the request could
  have meant before it could be built wrong: race opponents, not cars with the Racer personality -
  stripes on those would be the exact failure RLG-054 spent two paragraphs warning against. It is the
  class signal read from the other end: a striped car is unambiguously an opponent, which is what
  makes the muted supercar in traffic unambiguously not. A chance rather than a rule, and both bounds
  matter - at nothing the signal does not exist, at everything a grid is a team. Measured over 30
  grids and 330 cars: 121 striped, 37% against a 35% chance, spread across all three bodies. Rolled
  with the paint and the body, because it is part of what the car is for the whole race. A formula car
  never wears them, guarded twice, and the check asserts the effect rather than either guard
  ([RLG-117](../fragments/RLG-117.md)).
- Changed: **`rivalFront` takes the stripe flag, because a car striped from behind and plain from the
  front is two cars.** The rear cache is eager and the front one lazy, so the striped variants are
  built in the boot loop and the flag joins the lazy key - each cache keeps the policy it already had.
  The fault this avoids only shows in the mirror ([RLG-117](../fragments/RLG-117.md)).

<a id="v0-10-25"></a>
## [0.10.25] - 2026-08-31
- Added: **supercars appear as very rare traffic, in traffic paint.** Owner, 2026-08-29, extending the
  personalities ruling; and owner, 2026-08-31, settling the question it had left open on its first
  day - no personality shows on a car other than through its behaviour, and a traffic Racer wears
  traffic paint. A traffic supercar is built exactly as a rival is, with the colour coming from the
  muted list instead of the saturated one, and that is deliberately the whole difference. Measured off
  the sprites' own pixels, saturation runs 0.113 to 0.162 as traffic against 0.532 to 0.634 as a
  rival - a four-fold difference, which is the thing the ruling said had to be right. The gate sits
  before the type table in BOTH spawners rather than as a slice of one, so its rarity is a number a
  reader can find: 230 of 40,000 spawns, about one car in 174 against the old rogue's one in 36. Not
  the FORMULA, and the check asserts its absence. They inherit the raised Speeder chance, which is the
  sentence that could not be built until the personalities existed, and they get the supercar's
  stats - slow because the driver is going to work ([RLG-054](../fragments/RLG-054.md)).

<a id="v0-10-24"></a>
## [0.10.24] - 2026-08-31
- Added: **every NPC driver has a personality - Civilian, Speeder or Racer.** One system for traffic
  and rivals alike, and the project's spine applied to behaviour: the car is capable, the driver
  decides. A personality picks a TARGET speed and nothing else; what the vehicle can do is its own
  ceiling, and the cruise is the smaller of the two. So a Speeder in a lorry drives a lorry - 68mph,
  under the 80mph limit - and trips no trap, while the same mind in a tuner reaches 140. Nothing names
  a body to decide a personality; the body only caps the outcome. Sampled 4,000 per type, ordinary
  bodies run 88-90% civilian against RLG-045's 90/10, and a sports car lifts the Speeder odds 2.8
  times. A Racer is about one car in fifty ([RLG-054](../fragments/RLG-054.md)).
- Changed: **the rogue is superseded, at deliberately the same rarity.** One in five tuners and muscle
  cars used to cruise at 100-124mph under a separate flag - about 2.8% of traffic against a Racer's
  2%. The speed trap and the cruiser's target search asked "is this a rogue" and now ask "is this a
  driver who chooses to exceed the limit"; both already had a speed test after that question, which is
  why a capped lorry correctly trips neither ([RLG-054](../fragments/RLG-054.md)).
- Fixed: **a lorry could come up behind the player at 92mph.** The behind-spawner capped every body at
  a flat 0.46 of top speed. It takes the vehicle's own ceiling now, like everything else - and because
  its speed is decided before its driver is, the personality is read OFF the speed rather than rolled,
  so nothing carries a mind that contradicts what it is doing
  ([RLG-054](../fragments/RLG-054.md)).
- Added: **`tools/mind-test.py`.** Its road check had to be rewritten to be worth anything: the first
  version took one snapshot, saw 14 cars all civilian, and would have passed on an engine that gave
  every driver the same mind - at one in ten, a fourteen-car sample is empty of speeders about a
  quarter of the time. It watches 24 times across a drive now. `traffic-test`'s corridor guarantee was
  measured on both arms - 0.288/0.347/0.441 before, 0.295/0.409/0.372 after - so RLG-037's known
  one-in-three flake did not move ([RLG-054](../fragments/RLG-054.md)).

<a id="v0-10-23"></a>
## [0.10.23] - 2026-08-31
- Fixed: **standing water survived a reset, and took a quarter of the grip with it.** `freshWorld`
  reset settled snow and not standing water - the same idea, read by the same two functions, two lines
  apart in the source. A run that ended in a downpour handed the next one a soaked road: `worldState`
  reported wet 0 and settle 0 while `wetGrip()` read 0.740 against 1.000 on a genuinely dry start.
  That is RLG-090's own complaint in a variable it did not name. The deposition rates go with them, or
  a new run melts its snow at the previous run's speed ([RLG-111](../fragments/RLG-111.md)).
- Fixed: **a clap of thunder could outlive its own run.** `thunderIn` is a scheduled sound - a strike
  sets it to between 250ms and 5 seconds and the stepper plays the clap when it runs out - and nothing
  reset it, so a bolt in the last second of a run made its noise in the next one, over a road that may
  have no weather at all. `boltNext` is armed to a full interval rather than zero, because a run that
  has just started is not one that is due to be struck ([RLG-111](../fragments/RLG-111.md)).
- Changed: **`worldState` now reports more than `freshWorld` resets.** That is the finding behind both
  fixes. `retry-test` asserts a fresh run inherits nothing by reading `worldState`, which reported
  exactly the fields the reset owned - so the field list was both the reset AND the definition of
  clean, and anything missing from one was invisible to the other by construction. `pool`, `grip`,
  `thunderIn` and `boltIn` are published whether or not they are reset, and each new assertion is its
  own line rather than folded into an existing one ([RLG-111](../fragments/RLG-111.md)).

<a id="tooling-260831"></a>
## [tooling, on 0.10.22] - 2026-08-31
*No product file changed, so there is no version and no cache bump: a device running 0.10.22 is
running exactly what this entry was tested against. Bumping for a harness-only change would make
every installed device re-download a build whose bytes it already has.*
- Fixed: **a missing selector aborted every Interstate run of `drive-test`.** Reported for weeks as
  "18/19 passed", it was not one failing check - it was six that never ran. `eval_on_selector` throws
  when a selector misses, and the throw left the function, taking speed, the rev limiter, distance
  travelled, staying on the road and damage with it. `#score` exists in Motorsport and not in the
  Interstate, whose live figures are `#clock`, `#dist` and `#place`, so one game passed and the other
  died on the same line. It reads `#hud` now - the container both machines have, whose text changes
  when anything inside it does - through a helper that returns nothing rather than throwing. The
  Interstate reports peak 152mph, revs never past the limiter, 192,332 units travelled, on the road
  for 100% of samples and worst damage 13%, none of which had ever been read. 27 of 27
  ([RLG-103](../fragments/RLG-103.md)).

<a id="v0-10-22"></a>
## [0.10.22] - 2026-08-31
- Changed: **OCEAN is COASTAL.** Five places in `road.js` and fifteen across four harnesses. Nothing
  persists a biome name, so no save key had to migrate ([RLG-059](../fragments/RLG-059.md)).
- Added: **the coast has an open sky.** Cloud cover comes from a place's own rain and snow, so a coast
  that rains a third of the time was as grey as a forest that rains 42 per cent of the time. `cover`
  is a multiplier on that tendency, defaulting to 1 for every place that does not state one, so the
  coast is the only entry carrying a number and a place added later gets the ordinary sky for nothing.
  Over 400 rolls each: coast median 0.233 and clear 56% of the time, against forest 0.727, swamp 0.706
  and city 0.710, all unchanged. The rain is deliberately untouched - lowering it would change how the
  place DRIVES through `wetGrip`, and nobody asked for that - and the check asserts the coast still
  clouds over sometimes, because a `cover` of zero would pass every other assertion and be wrong
  ([RLG-059](../fragments/RLG-059.md)).
- Fixed: **a field named `sky` silently overwrote the biome's sky colour.** The open-sky multiplier was
  called `sky` for one edit. `sky` is already the biome record's hex colour for the sky above the
  place, so the number replaced the colour and the cover calculation multiplied by a string: EVERY
  biome's cloud went to NaN, on the title screen, with nothing logged anywhere. `node --check` passes
  on it and so does every syntax gate. It is called `cover` now, and the scar is written into the code
  at both ends ([RLG-059](../fragments/RLG-059.md)).

<a id="v0-10-21"></a>
## [0.10.21] - 2026-08-31
- Fixed: **the sea runs to the horizon as one body of water.** Owner: the ocean drawn into the
  background should run to the horizon seamlessly. The ruling supposed the background met the horizon
  at the wrong ANGLE; measured, the angle was never what could be seen - across 13 bands in 40 places
  the straight line it replaces creased by at most 2.0 times the edge's own curvature, which is the
  quantisation of the reading. The fault was a COLOUR. The band above the furthest drawn slice is
  painted before `drawHaze()` so the distance wash falls on it; the road's own sea is painted after
  and gets none, and `seaTone` had no distance term at all where the land has receded properly since
  RLG-059. So the water changed colour at the join by up to 45 in summed RGB - a pale blue meeting a
  dark green-grey. The sea recedes toward the haze's own colour now, from the same function
  `drawHaze` asks. Median step across the join 21.94 without it, 1.57 with
  ([RLG-093](../fragments/RLG-093.md)).
- Changed: **the background shoreline is the drawn shoreline carried on, not a straight line.** It
  walks in the same steps the road walks in, asking `proj` and `roadsideAt` the same questions the
  drawn slices ask, so there is no second construction for a first one to disagree with. Kept because
  it is the right construction and it is what was asked for; the record says plainly that it changed
  nothing measurable. A first attempt estimated the tangent from the last two slices and measured
  WORSE - at the far end of the draw two slices are a fraction of a pixel apart vertically, so the
  slope is a small number over a smaller one, and on a 13-pixel band it bent 13x where the straight
  line sat at 2 ([RLG-093](../fragments/RLG-093.md)).
- Added: **`tools/seajoin-test.py`.** It sweeps the recession inside single frames rather than across
  runs, because the road is generated per load and the day is always turning - two runs differ in the
  road, the hour and the sea's colour at once, which is RLG-062's lesson. The value 0.25 is a clean
  minimum with the curve rising on both sides. It reports the crease measurement and gates on
  neither construction's shape, because where the band is shallow there is no unbroken edge to read
  and a check that cannot fail is not a check ([RLG-093](../fragments/RLG-093.md)).

<a id="v0-10-20"></a>
## [0.10.20] - 2026-08-31
- Fixed: **the skyline's parallax is chased in seconds, not in frames.** This is the other half of the
  owner's report - RLG-094 was the popping, this is the jitter, and it was found by measuring rather
  than by reading. The chase was a fixed fraction per FRAME: a time constant of about 22 frames, so
  0.37 seconds at 60fps and 0.18 at 120. How fast the city answered a corner was decided by the
  refresh rate of the device. Worse, the frame rate is not constant within one run - fps-test measures
  FOREST between 45 and 60 on one unchanged build - so the chase sped up and slowed down as the
  scenery thickened, which is a horizon that surges for no reason on screen and cannot be reproduced
  without the reporter's frame rate. Displaced by 100 pixels and given a second and a half of wall
  clock, the old form left 1.45 at 61fps and 33.12 at 16; the new one leaves 1.42 and 1.23. The tuned
  number did not move - `chase()` restates the same 0.045 as a per-second rate, so at 60fps it is
  exactly what it always was. The step is measured in `drawSky` because the title draws a skyline
  without running a step loop, and clamped at an eighth of a second so a backgrounded tab cannot snap
  the city across the glass on the frame the player returns ([RLG-096](../fragments/RLG-096.md)).
- Added: **`tools/skychase-test.py`.** It parks the car so the chase has a fixed target, displaces
  the value, and compares how far it comes back in equal wall-clock time at full speed and with the
  CPU throttled. It refuses to measure below the engine's own step clamp, which it reads rather than
  copies - its first version throttled past the clamp and failed a build that was already correct.
  Falsified by putting the fixed per-frame fraction back, which makes the two residuals differ by 96
  per cent ([RLG-096](../fragments/RLG-096.md)).
- Fixed: **`skyline-test.py`'s frozen-clock control was flaky, about one run in three.** Setting the
  window clock did not stop it, so each sample landed at the time it was set to plus however long the
  read took, and a window on the edge of its cycle flipped between two samples meant to be identical.
  The clock can be held now and the whole window section is sampled at exact times
  ([RLG-095](../fragments/RLG-095.md)).
- Fixed: **`skyTrace` published the raw bend rather than what the chase converges on.** The chase
  targets `-bendPx * 0.55`; a check measuring its residual against `bendPx` compares the value with a
  number it never approaches, which is how the first run of the chase test read 34 left of 100 and
  passed ([RLG-096](../fragments/RLG-096.md)).

<a id="v0-10-19"></a>
## [0.10.19] - 2026-08-31
- Added: **the city's windows switch on and off on their own clocks.** Owner: the skyline does not
  have dynamic window lights like it used to. It never had them by design - one window sheet at one
  global alpha following the clock, which is all `DESIGN.md` ever described. What was moving was
  RLG-094's defect regenerating the sheet every six seconds with new positions and new colours, seen
  from the side where it looked good. The habit is on the window now: each carries a phase, a period
  between 26 and 190 seconds and a duty, and is lit when its own cycle says so. Spreading the periods
  is the point rather than decoration - a city where every window shares one clock is a pulse, not a
  place, which is the lesson RLG-012 already recorded about a thruster on a single sine. The sheet is
  repainted when the pattern changes and not every frame, at most once every 0.35 seconds; the
  buildings sheet is never touched. Driven from `drawSky` on a fixed frame step rather than the step
  loop, because the loop returns early on the results screen and the title draws a skyline without
  stepping at all. `lampsOn()` is untouched, so at midday the city is dark whatever any window thinks
  ([RLG-095](../fragments/RLG-095.md)).
- Changed: **`skyline-test.py` reads the lit sheet as well as the silhouette,** because the two
  assertions have to hold at once. The pattern must move - 65 of 1024 columns change across six
  minutes of window clock - and the buildings must not, which is what stops this being satisfied by
  putting RLG-094's defect back. Both are watched failing: with the window clock held still, zero
  columns change; with the plan re-rolled, 1,021 do. No measurable frame-rate cost across two pairs
  of runs, with overlapping ranges and the direction flipping between them
  ([RLG-095](../fragments/RLG-095.md)).

<a id="v0-10-18"></a>
## [0.10.18] - 2026-08-31
- Fixed: **the skyline was a different city every six seconds.** Owner: the skyline jitters and pops,
  in the forward view and the rear-view. It was not a parallax fault, which is why two rounds of
  smoothing the offset never touched it - the city was not moving wrongly, it was being rebuilt as a
  different city. `buildSkyline()` generated the plan from `Math.random()` inline, and RLG-080 makes
  that function run whenever the hour bucket moves: one fortieth of a 240-second day. Ten times a
  minute the entire horizon was replaced, in both views at once because both draw from one cache.
  What a place looks like belongs to the biome and what colour it is belongs to the hour; they were
  fused in one function, so the only way to get a new colour was to get a new city. The plan is
  cached per biome and built once, the painter paints it in the current hour's light, and RLG-080 is
  untouched - the tint is still baked, with no wash over the frame. A lit window's amber-or-blue roll
  moved into the plan with it, so a city no longer recolours every window it has ten times a minute
  ([RLG-094](../fragments/RLG-094.md)).
- Added: **`tools/skyline-test.py`.** It walks ten hours of one pinned biome and reads the silhouette
  as a profile - the topmost opaque row in each of the sprite's 1024 columns - rather than as a pixel
  count two different cities could share. Zero of 1024 columns move across the day. It also asserts
  the colour still travels, because "never rebuild the sprite" would pass every shape check and is
  the fault RLG-080 was raised to remove; and it asserts the run crossed several hour buckets,
  because the defect does not exist inside one and a check sampling twice in six seconds would have
  gone green on it. Falsified by reintroducing the fault rather than by reverting the engine, which
  cannot be done here - the instrument does not exist on the broken build
  ([RLG-094](../fragments/RLG-094.md)).

<a id="v0-10-17"></a>
## [0.10.17] - 2026-08-31
- Added: **the weather falls in the rear-view as well.** Owner: rain and snow should be shown in the
  rear view - the precipitation itself, not the drops on the glass, which belong to the windscreen.
  The mirror is a picture of the world behind the car, so weather in the AIR belongs in it and water
  on a LENS does not. This finishes the job RLG-079 started, and it finishes it the same way: the
  particles moved out of `drawRain` into one painter that takes a rectangle, so the windscreen and
  the glass ask the same function rather than two copies of it. Each pane keeps its own particles,
  because both advance them once a frame and one shared field would be stepped twice. The lean flips
  in the mirror - rain falls straight down and it is the car that moves through it, so the streaks
  lean the other way when you look the other way. Three numbers are the mirror's own and are named
  tunables: the pane is 60 pixels tall against a 900-pixel screen, so the forward view's ninety
  particles and its streak of 3.5% of the screen would give either a blizzard or nothing
  ([RLG-092](../fragments/RLG-092.md)).
- Added: **`tools/mirror-rain-test.py`, which measures the weather in the glass without measuring
  the weather on the road.** "The mirror looks different when it rains" was already true before this
  was built, because RLG-079 wired the wet tarmac and the settled snow into the same surface code, so
  a check written that way would have passed on the old engine. It compares particles against no
  particles in one and the same wet scene: `API.mirrorRain({n: 0})` removes the feature through the
  public interface, and the harness runs the identical assertion with it off and requires that to go
  red. The instrument caught two of its own faults on the way - a road still filling with standing
  water gets brighter on its own, and parking the car is precisely what makes the engine feed traffic
  in behind it ([RLG-092](../fragments/RLG-092.md)).
- Added: **`API.mirrorRect()` publishes where the glass is.** `tools/mirror-shot.py` carries its own
  copy of the layout formula and the copy is three changes out of date - it still reads 0.62 of the
  width capped at 250 with a fixed height of 44, against 0.80 capped at 340. Anything that wants to
  read the pane now asks the code that draws it ([RLG-092](../fragments/RLG-092.md)).

<a id="v0-10-16"></a>
## [0.10.16] - 2026-08-31
- Fixed: **the world settles before the count, not on GO.** Owner: there is still a pop on GO - can
  the state not be started on load and persisted through the countdown and the drive start. It can,
  and that was the fix. A counter left at zero means **a roll is due**, and the count-in returns from
  the frame update before the world runs - so the first frame after GO rolled the weather and the
  cloud in front of the player. The biome had exactly this fault and was fixed in 0.10.11; these are
  the same bug twice more, in the two counters sitting beside it. The rolls happen at the reset now,
  the run starts at what it rolled rather than easing toward it, and both counters are armed to a
  full interval ([RLG-090](../fragments/RLG-090.md)).
- Changed: **`retry-test` no longer asserts a fresh run is dry.** That was right while the reset
  zeroed everything and left the first roll to the drive, and it is wrong now that a run rolls its
  own weather up front - a new run may legitimately start in snow. It asks the questions that
  actually mean "a new run": nothing accumulated survives, what is falling is what this run rolled,
  nothing is left due, and the previous run's values did not come across
  ([RLG-090](../fragments/RLG-090.md)).

<a id="v0-10-15"></a>
## [0.10.15] - 2026-08-30
- Fixed: **the mirror walks the world, not the car.** Owner: scenery in the rear-view absolutely
  ZOOMS away at many times the speed it approaches in the forward view. It was not receding at all.
  The glass walked fixed distances BEHIND THE CAR, and the mirror's projection takes distance as
  `pos - worldZ`, so every slice sat at a constant distance back for ever. The mirror was a ladder
  of rungs that never moved; what changed as you drove was which object got drawn on each rung. A
  tree did not glide away - it sat still and was replaced by the next tree every time the world
  index ticked over. **Measured, the frame-to-frame size change of a mirror object was exactly
  0.00%**, against a median of 0.55% out of the windscreen. It is 0.52% now. This is the fault
  `hillClip` had, and the note there says the same thing: anything pinned to the segment behind the
  player shifts by one every time the player crosses one ([RLG-073](../fragments/RLG-073.md)).
- Added: **scenery eases into the mirror instead of appearing.** Anything over a fifth of the pane
  is left out, which is a cut rather than a fade, so an object arrived abruptly at its largest
  allowed size. It fades in over the largest fifth of what is allowed, the way the forward view has
  always done ([RLG-073](../fragments/RLG-073.md)).

<a id="v0-10-14"></a>
## [0.10.14] - 2026-08-30
- Measured, and **nothing about the road changed**: the scenery's approach obeys perspective
  exactly. Owner: scenery moves away far faster than it approaches. Following one tree in from
  30,000 units to 12,500 on a flattened road, apparent width times distance holds at 275,141 with a
  drift of 0.00% - which is the one law perspective cannot argue with. So the size and the position
  are right, and whatever the eye is reacting to is the FADE or the draw distance, not the geometry.
  `scenery-test.py` keeps that as a regression check; a deliberate distance-dependent scale error
  drifts it 14.7% ([RLG-073](../fragments/RLG-073.md)).
- Added: debug-only hooks the measurement needed and nothing in the game calls - a trace of where
  each object was drawn (with the road position stamped **at draw time**, because reading it after
  the frame put a couple of per cent of skew in and read as the geometry drifting), the road
  position, and a dead flat, dead straight road. On the shipped road an object near the horizon
  moves mostly because the terrain under it does: the first run of this measurement reported a
  50-pixel jump that was a hill ([RLG-073](../fragments/RLG-073.md)).

<a id="v0-10-13"></a>
## [0.10.13] - 2026-08-30
- Fixed: **the hour is a blend, not a branch.** Owner: going from night to day, and day to night, is
  a gigantic snap. It was, and only the GROUND was snapping - `nightFall` and `goldenHour` have
  always returned smooth ramps, and every sky stop already mixes against them. Three places took the
  same smooth numbers and thresholded them at `> 0.5` and `> 0.25`, so the ground, the sea and the
  mirror's snow each flipped between three fixed looks in a single frame while the sky above went on
  crossfading. That is why it read as the whole world jumping rather than as a colour being off.
  The fractions are used as fractions now, night applied after gold so full night still wins.
  Measured across a whole day: the worst single frame carried **100% of the ground's colour travel**
  before, and 3% after ([RLG-091](../fragments/RLG-091.md)).
- Added: **`hour-test.py`**, which walks the day in 360 steps and compares the biggest single step
  with the day's whole range. Sampling four times a day would have found three plausible colours and
  no snap at all - the fault only existed between the samples. The share is measured against the
  day's own travel rather than a threshold in brightness levels, which would need re-tuning the day
  anybody changed a biome palette ([RLG-091](../fragments/RLG-091.md)).

<a id="v0-10-12"></a>
## [0.10.12] - 2026-08-30
- Fixed: **the device was serving a half-updated cache, which is a black screen.** Owner: pressing
  DRIVE gives an all-black screen with the mirror still drawing. That is the exact symptom `sw.js`
  predicts in its own note - the previous game HTML running beside the current shared scripts. Eight
  versions shipped in one evening and the cache names were not touched once. The rule written there
  says to bump them whenever a file MOVES or is RENAMED, and nothing had; that turned out to be the
  wrong question, because what matters is whether the files still agree with each other, and after a
  change the size of `road.js` they do not. Caches are v27, and `pack.sh` refused the build until
  `assets.js` agreed - which is the check that would have caught this on any of the seven builds
  before it, had it been run ([RLG-090](../fragments/RLG-090.md)).
- Fixed: **a run owns its weather, and a retry starts it clean.** Owner: on a time-over, RETRY
  carries state over - a dry biome with snow slipperiness still applied. Two pieces of state
  disagreeing is worse than either being wrong: the road looks like one thing and drives like
  another. Rain, snow, what has settled, the cloud and the storm now live in one `freshWorld` list
  with the place, rather than as lines scattered through the reset - **three of these have been
  found one after another**, and a fourth line would have fixed one and left the next
  ([RLG-090](../fragments/RLG-090.md)).
- Fixed: **the horizon no longer snaps to the next biome at GO.** Owner, on the previous build: the
  ground holds still now but the far end changes the instant the count ends. `biomeNext` was left at
  zero, which means a change is DUE, so the first frame after the count placed a new place at the
  horizon. A place you have just arrived in is not also one you are leaving, so the distance to the
  next is armed when the opening place is chosen ([RLG-088](../fragments/RLG-088.md)).

<a id="v0-10-11"></a>
## [0.10.11] - 2026-08-30
- Fixed: **the world does not change when the countdown ends.** Owner: when the countdown finishes
  the entire world changes, and you arrive in a brand new biome on GO. Two correct changes met
  badly - the reset was made to clear the opening-place flag so each run picks its own place
  (0.10.4), and the count-in was made to return from the frame update before the biome runs so the
  car is held (0.10.9). Together, the opening place was chosen on the first frame AFTER the count:
  at GO, in front of the player, as a snap. The pick is its own function now and the reset calls it,
  so the world you look at for three seconds is the world you drive into
  ([RLG-088](../fragments/RLG-088.md)).
- Changed: **the count-in holds one note instead of climbing.** Owner: the pitch going up while
  counting down is wrong. It is, and this file already said so - the note on the run-out `tick`
  argues that a rising pitch reads as a fanfare and a countdown holds ONE note and gets more
  insistent. Same 392 Hz each time; what changes is how hard it is struck, how long it rings and
  how much low weight sits under it, which leaves GO as the only different note in the sequence
  ([RLG-088](../fragments/RLG-088.md)).

<a id="v0-10-10"></a>
## [0.10.10] - 2026-08-30
- Fixed: **a race has checkpoints, whatever the timed toggle says.** Owner: turn TIMED off under
  TEST DRIVE and a race started afterwards has no checkpoints in it. The loop that places the boards
  already sat inside `clockRuns()`, which is `mode === 'race' || timedRun` and is the correct test -
  and then asked `timedRun` again on the next line, getting a different answer. Worse, it still
  counted past each checkpoint, so they were thrown away rather than deferred and turning the toggle
  back on mid-run could not have recovered them. There is no condition there now: being inside
  `clockRuns()` is the condition, and TIMED is a choice about a test drive rather than something a
  race consults ([RLG-089](../fragments/RLG-089.md)).
- **The countdown was mis-numbered as 0.11.0 and is renumbered 0.10.9 above.** One feature is one
  patch, and a new mechanic is not a reason for a minor bump; the entry heading and its anchor are
  corrected rather than a second entry added, because two numbers for one release is worse than an
  edited heading. Version numbers only climb, so this release is 0.10.10.

<a id="v0-10-9"></a>
## [0.10.9] - 2026-08-30
- Added: **three, two, one, GO before the car moves.** Owner: hitting DRIVE should give a countdown,
  with some flare. The car is **held**, not merely covered - the throttle is ignored, the run clock
  does not start and nothing is scored until GO, because a countdown drawn over a car that is
  already accelerating is a lie the first frame gives away. The world runs behind it, so you see the
  road you are about to take. Each number arrives at 1.35 of its size and settles back, with a ring
  leaving it as it lands; GO is bigger, green, lifts as it goes and stays up while the car is
  already moving. Three pips a whole tone apart and a major chord on GO - the opposite of the
  run-out `tick`, which deliberately holds one note because a clock running out should be ominous
  and a start should not. **After the first run of a session, the throttle shortens the count to a
  third of a second** rather than cancelling it, so a player who has just crashed is not paying a
  toll ([RLG-088](../fragments/RLG-088.md)).
- Added: **`start-test.py`.** It holds the pedal down from before the count begins, because a car
  nobody is asking to move sits still whether it is held or not - the first version of the check
  passed on a build with no countdown in it at all ([RLG-088](../fragments/RLG-088.md)).

<a id="v0-10-8"></a>
## [0.10.8] - 2026-08-30
- Changed: **the garage card has two sizes: the regular cars, and the big ones.** Owner, on seeing
  the single card: the lorry and the van are a bummer, so standardize it for the regular cars and
  expand it only for the extra large vehicles. One reservation made every car pay for the lorry -
  the fleet runs LORRY 150, VAN 115, then PICKUP 112 down to ROADSTER 78, so a roadster sat above
  72 px of air to accommodate one vehicle most players never choose. Ordinary cars now reserve 112
  and the two oversized ones reserve 150, so a card never changes size between two ordinary cars -
  which was the complaint - and does change when you scroll onto something the size of a lorry,
  which reads as the vehicle being different. `big` is declared on the body rather than inferred
  from a height, because a rule like "anything over 120 px" would silently re-tier a car the day
  somebody adjusted a sprite ([RLG-087](../fragments/RLG-087.md)).

<a id="v0-10-7"></a>
## [0.10.7] - 2026-08-30
- Fixed: **the garage card holds one height, whichever car is in it.** Owner: switching cars
  collapsed and expanded the layout by a small amount, which is annoying. It moved between 78 and
  90 px across the cars a player starts with. The card is now the tallest card any body in the game
  produces - measured by loading each in turn and putting the player's own car back, rather than
  typed in, so a taller car added later cannot silently overflow it. The car still hangs from the
  ceiling line, so the spare falls underneath it where a floor would be. **This reverses a
  deliberate decision**: the height was made per-car precisely to avoid a band of nothing under a
  low one, and the owner has now weighed the two with the thing in front of them
  ([RLG-087](../fragments/RLG-087.md)).

<a id="v0-10-6"></a>
## [0.10.6] - 2026-08-30
- Fixed: **a short gearbox is designed, not a six-speed with the top gears cut off.** Owner: the
  muscle car's first three gears are good and its fourth is one long tedious grind. The table was
  the six-speed's first n gears with the last one's ceiling forced to the top of the range, so a
  four-speed's fourth ran from 0.41 of top speed to 1.00 - fifty-nine per cent of everything the car
  can do, in one gear, while the three below it kept their original short bands. The six-speed's own
  shift points are read as a curve now and a shorter box samples that curve at its own spacing, so
  four gears take it in four steps rather than in four sixths of one. The muscle car's top gear
  carries 34% of the range instead of 59%, and a five-speed's carries 28% instead of 42%. **A
  six-speed is returned untouched and drives exactly as it did**
  ([RLG-069](../fragments/RLG-069.md)).

<a id="v0-10-5"></a>
## [0.10.5] - 2026-08-30
- Fixed: **the garage answers a tap at once.** Owner, from the device: choosing a colour takes about
  half a second before the selection changes, and toggling is the same, and it is probably having to
  rebuild the vehicle. It was rebuilding all of them. One sprite build painted the two player
  sprites, then the ENTIRE rival cache - every rival body in every paint - and then every traffic
  sprite, the patrol car and the super cruiser, none of which depend on the colour you tapped, on
  the stripes, or on which car you are sitting in. The build is split at the seam that was already
  there: the player's car, and everything the road brings with it. Measured on this desktop, a
  colour tap went from 215-335 ms to 3.9-6.2 ms and the stripes toggle from 209-405 ms to 3.8-4.2 ms
  ([RLG-086](../fragments/RLG-086.md)).

<a id="v0-10-4"></a>
## [0.10.4] - 2026-08-30
- Fixed: **a biome is a distance you drive, not a wait you sit through.** Owner, from the device:
  park at the side of the road and the biome changes anyway, without the car having moved. It did -
  the countdown ran in SECONDS, so a place lasted seventy to a hundred and thirty seconds of sitting
  still as readily as of driving. The comment above it has said "changes biome every few miles"
  since the day it was written, so the intent was distance all along and only the arithmetic was
  time. It counts down in world units now, spent by the same quantity the road position advances
  by, so it stops when you do. The range is the old one converted rather than replaced: seventy to
  a hundred and thirty seconds at the speed the interstate is actually driven is six and a half to
  twelve miles, so the pacing at a normal pace is unchanged
  ([RLG-022](../fragments/RLG-022.md)).
- Fixed: **a new run starts a new map.** Neither the countdown nor the flag that says a run has
  chosen its opening place was ever cleared, so only the FIRST run of a page load chose one
  outright. A second run inherited the last one and whatever was left of its countdown, which could
  be a few hundred units - a place that ended before the car had left the starting line
  ([RLG-022](../fragments/RLG-022.md)).

<a id="v0-10-3"></a>
## [0.10.3] - 2026-08-30
- Added: **every other vehicle throws its own headlight beam.** Owner: would it be too much if all
  the other vehicles also had headlight beams. It is not, given a cap. A traffic car, a rival or a
  cruiser gets ONE cone rather than the player's three shells and pool, so the cost is set by how
  many are allowed a beam rather than by how many are on the road, and the light fades with
  distance so the far ones thin out instead of switching off at the cap and popping. Only vehicles
  ahead of the camera get one: in the forward view they are all seen from behind, so their lamps
  point down the road and the light lands on tarmac you can see. A wreck has no lamps left and a
  speed trap parked on the verge is waiting rather than driving, so neither throws anything
  ([RLG-085](../fragments/RLG-085.md)).
- Changed: **one painter draws every beam in the game.** The player's throw, the pool at its
  bumper and a delivery van's are now the same function at different sizes, so a fix to how a beam
  rides a crest reaches all of them at once ([RLG-085](../fragments/RLG-085.md)).
- Changed: **`fps-test.py` takes the hour as an argument.** It started at the dusk default and let
  the clock run, so a two-second sample landed somewhere between no street lighting and all of it
  and the headlights switched on partway through. Neither is a thing to average over when the
  change being measured is a light ([RLG-085](../fragments/RLG-085.md)).

<a id="v0-10-2"></a>
## [0.10.2] - 2026-08-30
- Fixed: **the headlights lay light on the road instead of standing two grey slabs on it.** The
  owner reported that the beams did not look right, and two of the three causes were geometry
  rather than taste. The throw began 485 world units ahead of the car, which projects ABOVE the
  car's own roofline, so the tarmac beside the bumper - the road a dipped beam lights most
  brightly - had nothing on it and the light appeared to start in mid-air. And a cone whose
  world half-width grows linearly with distance projects to a CONSTANT width on screen, which is
  what made it read as two parallel-sided stripes on a road that converges away behind them. The
  throw now starts at the car, the near width carries the shape, and three nested cones summed
  under `lighter` give a bright core with a soft shoulder in place of one hard-edged polygon. The
  hot spot at the bumper is a short wide cone rather than an ellipse on the glass: the old one was
  spread over most of the screen and had never once been visible
  ([RLG-060](../fragments/RLG-060.md)).
- Added: **`beam-test.py`, which photographs the same road with the beam and without it.** It asks
  whether the light reaches the road at the car, stays below the horizon, dies out before the
  horizon rather than stopping at a line, and is held off at midday by the CLOCK rather than by
  luck. The old geometry fails its first check. Two debug hooks serve it and nothing in the game
  calls either: one turns the beam off, and one clears the road, because a car driving up the
  picture lifts a long run of rows in exactly the way a beam does and three statistical dodges
  were tried against that before the obvious answer ([RLG-060](../fragments/RLG-060.md)).

<a id="v0-10-1"></a>
## [0.10.1] - 2026-08-30
- Fixed: **the bottle is centred by its ink, and the nozzle is part of the ink.** The owner saw that
  the NOS bottle still sat left of centre over the pedals, and named the cause: the measurement did
  not include the NOZZLE. The valve and the tapered outlet are drawn outside the button's own box
  and hang 20 px off its left, so a button centred on the pads drew a picture 12.5 px left of them.
  How far the ink reaches past the button is now written once, and both the outlet and the button's
  offset are measured from it, so the two cannot disagree. `hud-test.py` photographs the strip the
  bottle occupies and reads the leftmost and rightmost painted column, because a check that measured
  the box would have agreed with the build the owner was complaining about
  ([RLG-082](../fragments/RLG-082.md)).

<a id="v0-10-0"></a>
## [0.10.0] - 2026-08-30
- Fixed: **the gap the eye sees, not the gap the boxes have.** The owner saw more space above the
  bottle than below it on a build whose numbers said 7.4 and 7.4, and named the cause: the gauges
  have their own padding. They do - the two faces are drawn into a canvas that reaches 2.5 px lower
  than anything painted in it. Both gaps are 9.8 to the INK now
  ([RLG-082](../fragments/RLG-082.md)).
- Changed: **heat is earned and it cools; it is not a clock.** Owner: "I don't think time should
  increase it at all. It should purely be from speed traps and taking out cops. I think if you outrun
  a cop for long enough, your heat would probably go down." It used to rise by one every twenty
  seconds whatever you did and never fall, reaching five inside eighty seconds of any run - a timer
  wearing a wanted level's costume, and about to be five stars on the screen. Up on a trap and on
  taking a cruiser out; down after twelve seconds with nobody on you; the cooling clock resets the
  moment a trap catches you again ([RLG-030](../fragments/RLG-030.md)).
- Fixed: **a parked trap is not chasing you.** There are always two to four cruisers parked on the
  verge, and they counted as pursuit - so the cooling clock reset every frame and heat could never
  come down at all. Found by the check for cooling failing with nobody behind the car
  ([RLG-030](../fragments/RLG-030.md)).
- Changed: **a super cruiser is earned twice over.** Owner: "not dispatched unless you are heat three
  and above and have gone 170 miles an hour past a speed trap." Two conditions of different kinds - a
  standing state and an event. The old rule asked for heat one and four seconds above 150, which any
  fast car does by accident ([RLG-030](../fragments/RLG-030.md)).
- Added: **`tools/heat-test.py`**, which says plainly what it cannot isolate: the speed a super needs
  is above the limit a trap watches, so driving fast enough to trigger one earns heat while the check
  watches ([RLG-030](../fragments/RLG-030.md)).

<a id="v0-9-99"></a>
## [0.9.99] - 2026-08-30
- Removed: **DISTANCE from the top row, permanently.** Owner: "it's already currently displayed in
  the odometer." Interstate's markup no longer has the panel, and the engine writes to it only if a
  cabinet still has one - Motorsport does, and its HUD is a separate conversation
  ([RLG-082](../fragments/RLG-082.md)).
- Added: **the wanted level is five stars, centred under the glass.** `heat` runs 1 to 5, so it maps
  to five stars with nothing to scale or round. Shown whenever the pursuit system is on rather than
  only while a cruiser is behind you - the level is a thing you carry, and it is what decides how
  thickly the traps ahead are laid. The banner below still says how many are chasing you right now,
  and no longer repeats the heat ([RLG-082](../fragments/RLG-082.md)).
- Changed: **the top row is centred rather than spread.** The countdown centres itself when it is
  alone; with the stars it becomes one group, clock left and stars right with a gap between - which
  is what a flex row does for nothing ([RLG-082](../fragments/RLG-082.md)).
- Fixed: **the NOS bottle is centred over the pads and evenly spaced.** Owner: it should be centred
  above the brake and accelerator with equal padding between them and the gauges. It was 16 px right
  of the pads' own centre and sat ON them - 0 px below, 6 above
  ([RLG-082](../fragments/RLG-082.md)).
- Fixed: **the pedal box's own offset is in the scaled space too.** Everything inside it scales with
  the UI and the offset did not, so the gap below the bottle grew with the scale while the gap above
  it did not: 7.4 and 10.2 where both were meant to be 7.4. Two distances in one stack have to be in
  the same units ([RLG-082](../fragments/RLG-082.md)).

<a id="v0-9-98"></a>
## [0.9.98] - 2026-08-30
- Changed: **the rear-view mirror is larger and actually centred.** Owner: "make the rearview mirror
  larger and centered on the top of the screen." It was not centred, and the reason looked
  deliberate: `viewShift` moves the whole forward view left to make room for the thumb cluster, and
  the mirror was carried along with it - so the glass hung 8.5% of the screen left of the middle of a
  symmetrical windscreen. A mirror is mounted on the screen, not in the world. 0.62 of the width
  capped at 250 becomes 0.80 capped at 340, and the height follows the 5.7:1 the glass already had
  ([RLG-082](../fragments/RLG-082.md)).
- Changed: **the HUD measures itself against the glass.** The row under the mirror cleared it with a
  hardcoded 58 - six of margin, a 44-pixel mirror and eight of gap, three numbers collapsed into one,
  in a different file from the two that decide them. The engine publishes `--mirror-h` and
  `--mirror-top`, so the row moves when the glass does. Both driving games
  ([RLG-082](../fragments/RLG-082.md)).
- Changed: **the HUD's top padding is the safe area only**, so the row below the mirror owns the
  whole distance from the top of the stage and can be measured against the glass rather than against
  whatever the padding happened to be. Measured: the gap is 9.8 px where 9.8 is designed, and the old
  hardcode reads -8 - an overlap ([RLG-082](../fragments/RLG-082.md)).

<a id="v0-9-97"></a>
## [0.9.97] - 2026-08-30
- Fixed: **a slope measured over half a pixel is not a slope.** The sea's fill carries its edge down
  to the bottom of the screen so the nearest slice ends on the shoreline's own angle rather than
  dropping vertically - and that angle came from the slice's own two ends. A slice at the far end of
  the draw is a third of a pixel tall, so dividing by its height turned a rounding error into a line
  across the frame, wherever a nearer slice then failed to paint over the tail. A slice must be
  taller than two pixels to have an angle worth reading ([RLG-059](../fragments/RLG-059.md)).
- Fixed: **the audit's AUD-002 was four faults in the check and one in the game.** The check took
  the largest change in x between neighbouring rows, which is only meaningful while the edge is
  steeper than 45 degrees - a straight shoreline running shallow reported a 121 px "staircase". It
  compared across rows that do not touch, so an edge leaving the screen and returning read as a
  119 px kink. A second difference is large on a real bend. And a local line fit cannot tell a
  staircase from a CREST, where the brow legitimately hides the slices between two shorelines and
  the edge steps once. What a staircase is, without reference to angle, is an edge whose steps are
  mostly nothing and occasionally a jump - so the test is now outliers against the edge's OWN median
  step ([AUD-001](../fragments/AUD-001.md), [RLG-059](../fragments/RLG-059.md)).
- Changed: **the horizon check counts water rather than a fraction of the band.** How much of the
  strip is sea depends on where the shoreline crosses it: 23, 40, 45 and 67 per cent were all
  correct pictures ([RLG-059](../fragments/RLG-059.md)).

<a id="v0-9-96"></a>
## [0.9.96] - 2026-08-30
- Fixed: **the driving HUD's readouts are anchored in the same space as its controls.** Owner: "fix
  the anchored relative spacing of UI elements", on the driving HUD. The shell publishes a UI scale
  that runs from 1 on a phone to 1.8 on a big screen, and its own note says a game opts in by scaling
  its overlay - this cabinet opted its CONTROLS in and left its READOUTS behind. At 1.8 the wheel,
  pedals, bottle and dials were half as big again while TIME and DISTANCE were the same 26px they are
  on a phone, stranded in corners 200 pixels further out. Nothing was resized: every number is what
  it was, times the scale everything beside it already used, so a phone is unchanged to the pixel
  ([RLG-082](../fragments/RLG-082.md)).
- Note: **the mirror clearance is deliberately NOT scaled.** The glass is drawn on the canvas at a
  fixed 44px and does not grow, so the row below it is measured against the glass rather than against
  the scale ([RLG-082](../fragments/RLG-082.md)).
- Added: **`hud-test.py` measures a readout at two viewports** and asserts it grew by the factor the
  scale did: 26.0px at scale 1 and 46.8px at 1.8, against 26.0 and 26.0 before
  ([RLG-082](../fragments/RLG-082.md)).

<a id="v0-9-95"></a>
## [0.9.95] - 2026-08-30
- Fixed: **a car with no bottle leaves no hole.** Owner: cars without NOS did not have the gauges
  collapse down to the pedals. Hiding the bottle left the space it stood in, so the shifter and the
  dials went on measuring their height from where a bottle would have been. The cluster stacks
  bottom-up and `--bottle` is how much room the bottle takes in that stack; setting it to zero closes
  the gap and nothing else has to know why. The dials come down 46.8 px, landing exactly where the
  bottle's own floor was ([RLG-028](../fragments/RLG-028.md)).
- Added: **`tools/hud-test.py` measures the cluster as boxes.** Whether the stack closed up is a
  question about `getBoundingClientRect`, not about pixels, and it does not care what the road behind
  it is doing ([RLG-028](../fragments/RLG-028.md)).

<a id="v0-9-94"></a>
## [0.9.94] - 2026-08-30
- Fixed: **the player collides at the width it is drawn at.** Owner: "We have to make the vehicle
  colliders true to their sprite size. It's hard to tell." The car was drawn at 0.265 of the road and
  struck at 0.26, in three separate hard-coded places - about two per cent narrower than it looks,
  which is exactly the gap between what you can see and what you can predict. One number now, and
  the tyre marks it lays follow it too ([RLG-058](../fragments/RLG-058.md)).
- Added: **`tools/collide-test.py` measures where the hit actually happens.** It parks a car on the
  real traffic array, walks the player out sideways, and binary-searches the offset at which the hit
  stops firing. Two cars of different widths separate the sum into its parts, so the player's own
  half-width is MEASURED rather than read back: 0.2648 against a drawn 0.2650. With the old constant
  restored it measures 0.2597 and fails ([RLG-058](../fragments/RLG-058.md)).
- Note: **per-car widths and length are not in this.** Every player car is still drawn at one width,
  so a lorry and a roadster are the same in your hands - that is twenty-six numbers in the fleet
  table and the owner's to rule on. And a billboard sprite has no depth, so "true to the sprite"
  cannot be read literally for length ([RLG-058](../fragments/RLG-058.md),
  [RLG-055](../fragments/RLG-055.md)).

<a id="v0-9-93"></a>
## [0.9.93] - 2026-08-30
- Fixed: **the packer regenerates before it verifies.** `assets.js` is generated and takes its
  version from `sw.js`, so in a build the two agree by construction the moment the generator has run
  - but the agreement check ran BEFORE it, so bumping `sw.js` failed the very build that would have
  fixed it, and `assets.js` was seeded by hand once to get past it. The check is not weakened, which
  matters: the drift it catches is what shipped eighteen 404s behind a green build. What changed is
  when it runs ([RLG-004](../fragments/RLG-004.md)).
- Changed: **one definition of what agreement means, two callers.** `--check` has nothing to
  regenerate, so it compares the files as they are; a build compares what it just wrote
  ([RLG-004](../fragments/RLG-004.md)).

<a id="v0-9-92"></a>
## [0.9.92] - 2026-08-30
- Fixed: **the cars behind you have their headlights on after dark.** Every front sprite declared a
  `head` lamp and nothing in the game ever asked for one, so the mirror showed a road of cars driving
  at midnight with their lights off. The declaration was there; the wiring was not, which is the half
  of RLG-053 the rears finished and the fronts never did. Same clock as the street lamps
  ([RLG-053](../fragments/RLG-053.md)).
- Fixed: **a front lamp declared its own glow, so three of them baked one into the UNLIT sprite** - a
  parked car with a lit headlight. Every rear declares its LENS and lets the sprite builder blur the
  lit drawing into a halo behind it; the fronts do the same now. Measured: front headlights spilled
  860 to 1,983 lit pixels outside their own bulb, and 178 lamps across 59 sprites now stay inside
  ([RLG-053](../fragments/RLG-053.md)).
- Added: **`lamp-test.py` checks both faces of every car**, where it only ever checked the back. 29
  fronts, the formula class excepted by the same ruling that excuses it from indicators - a
  single-seater runs in daylight on a closed circuit and has never had headlights
  ([RLG-053](../fragments/RLG-053.md)).

<a id="v0-9-91"></a>
## [0.9.91] - 2026-08-30
- Fixed: **every harness finds its own root, so any of them can be run as evidence.** Seven served
  the folder from `.` and imported from `tools`, which only works from the project directory - and
  `step.py` runs a command with the environment's root as its working directory. So each one 404'd or
  raised there and recorded a FALSE FAILURE, twice in one session before it was worth fixing
  ([RLG-039](../fragments/RLG-039.md)).
- Fixed: **`scene-test.py` waited thirty seconds for a screen that must never exist.** It clicked
  CONTROLS to check the attract animation stops when a menu takes over, and this project ruled a
  controls page out of existence - `menu-test.py` asserts its absence. It uses OPTIONS, which every
  title has ([RLG-039](../fragments/RLG-039.md), [RLG-002](../fragments/RLG-002.md)).
- Fixed: **`scene-test.py` needed its output directory as an argument**, so running it the way every
  other harness is run raised before it opened a browser ([RLG-039](../fragments/RLG-039.md)).

<a id="v0-9-90"></a>
## [0.9.90] - 2026-08-30
- Fixed: **the title card wears the car's own tail lights.** Owner: the title menu shows the wrong
  tail lights, and it may be that the title is not using the right renderer. It was using the right
  renderer and then painting over it - two red rectangles at hand-written coordinates and a halo at
  two more, on a sprite that already knew where its lamps were and what they look like. The lamps run
  from the same declaration the road uses, inside the same transform the car is drawn in, so they
  lean with it and a reskin moves both ([RLG-077](../fragments/RLG-077.md)).
- Changed: **the lamp declaration can paint onto any canvas.** It painted into the road's own context
  and had no way to be told otherwise, which is why the title grew its own rectangles in the first
  place. One argument, and every surface that draws a car can light it the same way
  ([RLG-077](../fragments/RLG-077.md), [RLG-053](../fragments/RLG-053.md)).
- Added: **`tools/title-test.py` strips the declaration and looks again.** If the lamps come from the
  declaration they go out; if the title paints its own, nothing changes - which is what the old code
  did. Measured: 550 red pixels lit, 0 stripped; with the rectangles put back, 1,253 stripped against
  1,331 lit ([RLG-077](../fragments/RLG-077.md)).

<a id="v0-9-89"></a>
## [0.9.89] - 2026-08-30
- Fixed: **the pattern is centred in the plate.** Owner: "The 4-speed needs to be centered in its
  housing." It was not, and neither was the six-speed - the rails began at 13 and the plate ran on
  past the last one. The knob was 4px out as well, which is the same fault from the other side. One
  number does both: a rail centred under its knob starts 9px right of it, and the cross rail then
  ends the same distance from each edge on every plate ([RLG-069](../fragments/RLG-069.md)).
- Fixed: **a five-speed shows five positions.** Owner: "We need to make sure that the 5-speed only
  shows the 5 positions." It showed six with the sixth reading neutral, which is a gearbox fact
  dressed up as a picture. Its third rail stops at the cross rail, and the knob will not go down it
  ([RLG-069](../fragments/RLG-069.md)).
- Added: **a black knob for the production and utility cars.** Owner: "I also want production and
  utility vehicles to have a black leather or plastic shifter with white text on it." The saloon, the
  cab, the coupe, the pickup, the van and the lorry get a moulded black one with the number in white;
  the sports, super and formula classes keep the polished ball. The police cars are NOT in it, which
  is a decision rather than an oversight - a cruiser is a production saloon underneath, but this game
  treats the police as a class of their own ([RLG-069](../fragments/RLG-069.md)).

<a id="v0-9-88"></a>
## [0.9.88] - 2026-08-30
- Fixed: **muting a bus mutes its reverb.** Owner: "if I was to mute the music, the reverb bus still
  plays so we want to make sure muting the music also mutes that bus." There was one convolver and
  its return went straight to master, so a voice was connected twice and only the dry copy rode the
  mute - the music went quiet and its tail kept ringing. Each bus has its own reverb now, returning
  into the bus, so a tail rides the same gain its dry copy rides
  ([RLG-078](../fragments/RLG-078.md)).
- Changed: **the reverbs are built on demand.** A convolution is not free and no bus needs one until
  a voice sends to it. Measured in play: two get built, music and effects
  ([RLG-078](../fragments/RLG-078.md)).
- Added: **`tools/verb-test.py` listens rather than reads.** A routing fault changes no gain
  anywhere, so there is no value on the graph that could be wrong - the only thing that answers it is
  the signal. It taps the output through a new `Arcade.audio.tap()` and measures the tail. Falsified
  by putting the shared return back: a muted bus then leaves its tail at 88% of full
  ([RLG-078](../fragments/RLG-078.md)).

<a id="v0-9-87"></a>
## [0.9.87] - 2026-08-30
- Fixed: **the gate is the gears the car has.** A four-speed could be dragged onto a third rail it
  has no gears for, because the knob's travel was clamped to the length of the rail table rather than
  to the car - and `gearFactor` returns zero past the end of the ratio table, so the car stopped
  pulling in a gear it does not have. Two rails for a four-speed, three above it, and the knob cannot
  leave them ([RLG-069](../fragments/RLG-069.md)).
- Fixed: **a five-speed no longer engages a sixth.** The slot below fifth is where reverse lives in a
  road car and this game has no reverse, so it reads NEUTRAL rather than a gear the engine does not
  have ([RLG-069](../fragments/RLG-069.md)).
- Fixed: **a five-speed's plate was wider than a six-speed's**, which is the one thing it cannot be.
  Three hand-set widths that followed from nothing - 86, 92 and 74 - are now the last rail's knob
  position plus the padding it has on the left, so the plate is the gate it holds. On a phone the
  size of a control is the control ([RLG-069](../fragments/RLG-069.md)).
- Fixed: **the knob came back inside the gate when the car changed.** Leaving a six-speed in sixth
  and taking out a four-speed left it standing on a rail that car does not have
  ([RLG-069](../fragments/RLG-069.md)).
- Added: **`tools/gate-test.py` walks the gate with the game's own `shiftStep`**, and
  **`tools/gate-shot.py`** photographs the plate for a car of each gear count. Both run in a TOUCH
  context: the shell hides the whole thumb cluster on a device that reports no touch, so a desktop
  harness measures a plate zero pixels wide and reports success
  ([RLG-069](../fragments/RLG-069.md)).

<a id="v0-9-86"></a>
## [0.9.86] - 2026-08-30
- Fixed: **the shoreline is a line, not a staircase.** The sea was filled as a rectangle at the near
  shore for the whole height of a slice, so the coast came out as a hard step per segment beside a
  road drawn as a smooth quad - the most visible thing about the coast in every capture taken. The
  water's edge is a quad now, from the far shore to the near one, out of the same numbers
  ([RLG-059](../fragments/RLG-059.md)).
- Fixed: **a pale hairline every eight pixels, all the way out to sea.** Each slice paints the ground
  full width and paints its water back over it, so the top row of every fill was antialiased against
  sand rather than against the water already there. Each fill starts a pixel higher, which puts that
  row under the fill in front of it ([RLG-059](../fragments/RLG-059.md)).
- Added: **`coast-test.py` measures the edge row by row.** A line moves by its slope every row; a
  staircase does not move for the height of a slice and then jumps by the slope times that height.
  Measured: largest step 4-5 px against a mean of 2-3, where the rectangle gave 11, 12 and 63
  ([RLG-059](../fragments/RLG-059.md)).
- Added: **`fps-test.py` covers the two new places.** The coast reads 60.4 fps across three samples,
  the ceiling, so the quad costs nothing measurable. Swamp is 57.2 to 60.4 and forest is still the
  heaviest at 47.2 to 48.8 ([RLG-059](../fragments/RLG-059.md)).

<a id="v0-9-85"></a>
## [0.9.85] - 2026-08-30
- Changed: **the sea reaches the horizon.** Owner: "maintaining the ocean sided render into the
  background up to the horizon?" The road is drawn for a fixed number of segments and stops short of
  the skyline; the band above it is the far field, which was land. So a coast faded into sand at the
  horizon and a limit of the renderer showed through as a fact about the world. The band takes the
  water now, on the same side, behind the same shoreline, in the windscreen and in the mirror
  ([RLG-059](../fragments/RLG-059.md)).
- Fixed: **the horizon's shoreline is a value, not a trend.** The first version read the shore at two
  depths and carried the line between them upward, which needed the nearer slice to sit lower on the
  screen - not true on a road that climbs, so the band was skipped about a third of the time. At
  infinite distance the shore arrives where the road does, which is exact and costs nothing
  ([RLG-059](../fragments/RLG-059.md)).
- Added: **`tools/coast-test.py` measures the strip the road never paints.** Sampling wider passed
  two runs in three with the feature removed, because below that strip the road paints its own sea.
  The engine now reports where the road pass stopped, and the check reads only above it
  ([RLG-059](../fragments/RLG-059.md)).

<a id="v0-9-84"></a>
## [0.9.84] - 2026-08-30
- Fixed: **nothing stands in the sea.** Owner: "we need to make sure that scenery objects aren't
  generated in the side with the ocean." The roadside pass placed from one spec on both sides,
  because until the coast arrived no place had a reason to differ left from right - so palms and
  rocks stood in the water on whichever side the coast had rolled onto. The side the water is on is
  skipped, using the segment's own biome rather than the car's, so the shore empties where the ground
  colour changes ([RLG-059](../fragments/RLG-059.md)).
- Added: **palms and beach houses on the landward side.** Owner: "we might want random palm trees and
  beach houses on the opposing side." Four palms, two rocks and two houses, picked flat from the
  placement hash, so a shoreline has more trees on it than buildings. One house stands on piles with
  a deck, the other is low and long on the sand ([RLG-059](../fragments/RLG-059.md)).
- Added: **a beach house lights up at night**, on the same clock as the city's windows and the street
  lamps, with a light left on over the door. A house with dark windows in a place where everything
  else has lit up reads as abandoned. The spec now carries its own `buildLit` beside `build`, the
  same shape the lamps on the cars use - the thing that knows how an object is drawn is the thing
  that says where its light comes out ([RLG-059](../fragments/RLG-059.md)).
- Changed: **a palm has a crown.** Seen beside the houses at close range the first one read as a few
  leaves on a telephone pole. Longer fronds, nine of them, drooping at the tips
  ([RLG-059](../fragments/RLG-059.md)).
- Added: **the water is behind you as well.** The mirror's ground is one flat fill, so the glass
  showed a coast with no coast in it. Same shoreline, same side, same tone as the windscreen
  ([RLG-059](../fragments/RLG-059.md)).
- Fixed: **the BUILD row has been saying MIXED since 0.9.56.** `road.js` stamps the version it was
  written for so a device can tell a fresh shell from a cached engine, and that stamp had not moved
  in twenty-seven versions - so the one diagnostic for a half-stale install cried wolf on every
  install ([RLG-059](../fragments/RLG-059.md)).

<a id="v0-9-83"></a>
## [0.9.83] - 2026-08-30
- Changed: **the sea runs alongside the road, on one side, with beach between.** Owner: "I was kind
  of wanting the ocean to be either on the left side or right side (randomly rolled each time the
  biome is generated) of the road, with some beach between it and the road." The first version put it
  across the whole horizon, which reads as a road running INTO the sea rather than along it. The
  shoreline is a fixed distance out from the tarmac in the same units the roadside uses, so it
  converges with the road and rides the crests ([RLG-059](../fragments/RLG-059.md)).
- Added: **the side is rolled when the place is generated**, not when it is drawn - a value rolled
  per frame would put the water on alternating sides sixty times a second. Measured over 40
  placements: 17 left, 23 right ([RLG-059](../fragments/RLG-059.md)).
- Changed: **swamp and coast are the flattest of all.** Owner: "swamp and beach are the flattest of
  all biomes I suspect." They are, and for a reason a player feels without being told - both are
  places at sea level, where a city is graded flat by people and still runs over whatever hills were
  there. 0.15 and 0.18 against the city's 0.30, and still never zero
  ([RLG-059](../fragments/RLG-059.md)).
- Fixed: **a test hook took a different path from the game.** `startBiomeChange` set the biome pair
  directly and never rolled the sea's side, so the check for "the side is rolled" came back 40 out of
  40 on one side while the game was rolling it correctly. One function rolls it now and both callers
  use it ([RLG-059](../fragments/RLG-059.md)).

<a id="v0-9-82"></a>
## [0.9.82] - 2026-08-30
- Added: **two more places, an OCEAN coast and a SWAMP.** Seven biomes now. They are a table entry
  and some art, which is the point of the last two days: the ground at every hour, the weather odds,
  the taper a place imposes on weather arriving from elsewhere, the skyline, the roadside scenery and
  how much the road climbs and turns all read from that one record. Neither needed a new branch
  anywhere to be accepted ([RLG-059](../fragments/RLG-059.md)).
- Added: **an ocean has sea under its horizon.** Without it a coast is just a beach - pale sand
  either side, palms, no water anywhere. `farGround` is what the land BECOMES at the far end of the
  draw, and it goes through the same hour, weather and haze the land does. Every other biome leaves
  it out and the band stays the ground's own colour ([RLG-059](../fragments/RLG-059.md)).
- OCEAN rains 0.34 and never snows, nearly flat but winding along the water - the only place besides
  forest that bends more than it climbs. SWAMP is the wettest on the board at 0.62, the same figure
  tundra snows at, and turns a lot because a road through standing water goes round what it cannot
  cross ([RLG-059](../fragments/RLG-059.md)).

<a id="v0-9-81"></a>
## [0.9.81] - 2026-08-30
- Added: **the biome shapes the road - how much it climbs and how much it turns.** Owner: "the biome
  should probably also drive the magnitude of the road's vertical curvature - mountains on one
  extreme and desert > city on the other. Never completely flat but much less so", and "the
  verticality and bendiness of the road is also dictated by the biome." Each segment is scaled as it
  is GENERATED, by the biome at the place that segment will be - not at draw, because a bend that
  changed magnitude as you approached it would be the road moving under you
  ([RLG-059](../fragments/RLG-059.md)).
- Mountain is 1.00 on both, so **the road as it has always been IS the mountain road** and everywhere
  else is calmer. Nothing gets steeper or tighter than the renderer has always handled, which matters
  because the corner cap is a renderer limit rather than a taste one. City is 0.30, never 0
  ([RLG-059](../fragments/RLG-059.md)).
- Measured over 4,000 generated segments each: mountain turns 2.42 and climbs 2.16; city turns 0.69
  and climbs 0.67. A short drive could NOT show this - the roll's own variance is larger than the
  difference between two biomes, and a desert out-bent a mountain in one ten-segment sample. The
  chevron boards count for the corner as scaled, so a calmed city bend is not signed as the hairpin
  it was rolled as ([RLG-059](../fragments/RLG-059.md)).

<a id="v0-9-80"></a>
## [0.9.80] - 2026-08-30
- Changed: **the place you are entering decides how fast its weather ends.** Owner: "the speed of the
  taper should be dictated by the new biome... a snowy forest transitioning to tundra should more
  than likely not even taper off at all, a snowy forest transitioning to city could have a chance of
  tapering it off at a normal rate, and a snowy forest transitioning to desert should quickly taper
  off." The engine asked only whether the destination could produce the weather AT ALL, so a tundra
  and a city were treated identically and a desert like both - snow carried into a tundra only by
  accident of the test rather than because the place wants it
  ([RLG-022](../fragments/RLG-022.md)).
- Measured, snow leaving a forest: into TUNDRA support 0.62 and **no taper at all**; into CITY
  support 0.10 and the ordinary crossing; into DESERT support 0.00 and gone over a third of it -
  quick, but still a taper rather than the snap it used to be. Settled snow melts only in the last
  case: a city that snows one time in ten does not melt what is already lying
  ([RLG-057](../fragments/RLG-057.md)).

<a id="v0-9-79"></a>
## [0.9.79] - 2026-08-30
- Fixed: **a run starts in one place, with that place's weather.** Owner: "my first test run started
  with a raining desert." `biomeNext` began at 0, so the biome timer fired on the very first frame -
  and the guard for "first call" tested whether that frame had been longer than a SECOND. A real
  first frame is about sixteen milliseconds, so it took the CHANGE branch instead: the car started in
  the declared default of FOREST with a transition placed at the horizon, and the weather rolled
  against FOREST, which rains 42% of the time. Seconds later the car drove into whatever had been
  placed ahead ([RLG-022](../fragments/RLG-022.md)).
- Added: **a check read before anything else touches the state** - that a run does not begin part-way
  through a biome change, and that whatever is falling is weather the starting place can produce. It
  was watched failing on the old code, reproducing the report exactly: started in FOREST, changing to
  TUNDRA ([RLG-022](../fragments/RLG-022.md)).

<a id="v0-9-78"></a>
## [0.9.78] - 2026-08-30
- Fixed: **headlight beams follow the clock, not the weather.** Owner: "my headlights were on midday.
  The headlights need to follow the time of day like all other lights. It might have been because it
  was raining." It was. `lampsOn()` treats weather as night by the owner's own earlier ruling, so a
  shower at noon switched the beams on. Both rulings stand and they are about different things: a
  LAMP comes on in rain, and a BEAM is the light you can see lying on the road, which is invisible in
  daylight however wet it is. The lamps keep `lampsOn()`; the beam takes the day cycle alone
  ([RLG-060](../fragments/RLG-060.md)).
- Added: **a check that keeps the two apart.** Measured in heavy rain: at midday the lamps read 1.00
  and the beam 0.00; at midnight both read 1.00 ([RLG-060](../fragments/RLG-060.md)).

<a id="v0-9-77"></a>
## [0.9.77] - 2026-08-30
- Fixed: **the road widens and the cars do not.** Owner: "the road was supposed to get wider while
  everything else stayed the same size... I want the cars to be the same size they used to be just
  the road widening so cars at their original dimensions fit in the lanes better." Every vehicle's
  width was a fraction of `ROAD`, so widening grew every car by the same fifth and nothing fit any
  better. Widths read against `CAR_UNIT` now - the road half-width as it was before the widening -
  while POSITIONS still use `ROAD`, because a car's lateral place is a lane
  ([RLG-024](../fragments/RLG-024.md)).
- Fixed: **the collision widths went with them.** Left in road units while the sprites shrank, a car
  would have collided wider than it looked - you clip something you can see you have missed, which is
  worse than the fault being fixed and invisible to any check that does not drive into something on
  purpose ([RLG-024](../fragments/RLG-024.md)).
- Added: **a check that the car does not grow with the road.** Measured: the player is 230.17 pixels
  wide at ROAD 1900, 2300 and 3000, while the road edge goes 31.9, 38.6, 50.4
  ([RLG-024](../fragments/RLG-024.md)).

<a id="v0-9-76"></a>
## [0.9.76] - 2026-08-30
- Changed: **the road is a fifth wider, and the lanes with it.** `ROAD` goes from 1900 to 2300. The
  lanes come for nothing because `LANE_X` is normalised, and everything that moves sideways is
  already written in lane units. Chosen by capturing 1900, 2300 and 2700 and comparing: at 2700 the
  near tarmac swallows the frame, the car looks small on it and the verge is pushed out of the near
  view ([RLG-024](../fragments/RLG-024.md)).
- Fixed: **a roadside sign is roadside, not road.** It stood at 1.34 road widths from the centre and
  was sized by the road's width, so widening would have walked the chevron boards away from the kerb
  and grown them. A sign is the size of a car door whatever the carriageway behind it is doing
  ([RLG-024](../fragments/RLG-024.md)).
- Fixed: **the signs had no occlusion either.** Their guard was `overBrow`, the same dead call the
  lamps were found behind - it returns false on its first line. They go through the cars' crest gate
  now, like everything else beside the road ([RLG-073](../fragments/RLG-073.md)).

<a id="v0-9-75"></a>
## [0.9.75] - 2026-08-30
- Added: **the mirror shows the skyline and the roadside behind you.** The same sprites, from the
  same cache, placed by the same hash of the same world segment index - so a tree you have just
  driven past is in the glass at the size and place it was. It shows `biomeFrom`, because behind you
  is where you have been: during a crossing the windscreen shows the place arriving and the glass
  shows the place leaving ([RLG-079](../fragments/RLG-079.md)).
- Added: **nothing looms in a pane 44 pixels tall.** The sizes are proportionally right, but the
  windscreen is 900 pixels and the mirror is 44, so the nearest trees buried the road and the cars on
  it - the one thing the mirror is for. Anything over a fifth of the glass is left out
  ([RLG-079](../fragments/RLG-079.md)).
- Added: **`tools/fps-test.py`, which reports its SPREAD.** On one unchanged build a forest measured
  54.5, 60.2 and 57.0 fps in three consecutive runs, and over more samples 48.0 to 60.4. Two rounds
  of scenery tuning had already been done against single readings inside that spread. A change is
  only real if two ranges do not overlap ([RLG-059](../fragments/RLG-059.md)).
- Corrected: **the frame-rate claim in v0.9.71 was noise.** "Mountain measured 54.5 fps against 60
  everywhere else" is a single reading inside a 12-fps spread and it did not support the conclusion
  drawn from it. The mountain row count stays at three because it still reads as a valley, which was
  confirmed by looking - not because of the number ([RLG-059](../fragments/RLG-059.md)).

<a id="v0-9-74"></a>
## [0.9.74] - 2026-08-30
- Fixed: **the roadside takes the hour's light, not only the horizon.** The scenery sprites baked
  fixed colours, so a tree was a daylight tree at midnight while the skyline behind it had gone dark.
  Same treatment as the skyline: the tint is mixed in at build time and the cache is keyed by the
  hour bucket, so nothing passes over the frame ([RLG-080](../fragments/RLG-080.md)).
- Fixed: **the night colour has to be DARKER than what it lights.** `source-atop` is a mix toward the
  colour given, so the colour decides the direction - anything darker than the target gets brighter.
  The first version used a mid blue-grey and a forest tree went from 45.6 by day to 63.5 at night:
  the night tint was lighting the trees up. A picture would not have shown it either, because against
  a near-black sky a slightly brighter tree still reads as dark
  ([RLG-080](../fragments/RLG-080.md)).
- Added: **a check that the roadside darkens after dark**, and `API.setPhase` so it can ask the
  question in a second rather than waiting out a four-minute day. Measured: rock 74.3 to 44.1, forest
  45.6 to 33.0, skyline 68.9 to 25.8 ([RLG-080](../fragments/RLG-080.md)).

<a id="v0-9-73"></a>
## [0.9.73] - 2026-08-30
- Added: **the player's headlights beam down the road at night.** The cone is walked in WORLD space
  and its edges projected like anything else, so it follows the bend, rides the crests and narrows
  over a brow exactly as the tarmac does - a fixed triangle on the glass would sit dead straight
  while the road bent away underneath it. It is a bounded shape clipped to the ground plane, not an
  overlay: it cannot touch the sky and it does not light the player's own paintwork
  ([RLG-060](../fragments/RLG-060.md)).
- Added: **a hot pool just ahead of the bumper.** Two cones alone read as searchlights, because the
  gradient runs down the road rather than across it and they are therefore brightest where they are
  widest. A dipped beam puts most of its light in a short pool at the front of the car, and that pool
  is what makes the light read as coming from the car rather than from the camera
  ([RLG-060](../fragments/RLG-060.md)).
- Note: **the comfort option does not apply and that is deliberate.** RLG-060's setting exists for
  the lightning FLASH, which is a photosensitivity hazard. A headlight beam is steady light with no
  transient. If oncoming traffic is ever added to the forward view its beams point at the camera and
  that judgement has to be made again ([RLG-060](../fragments/RLG-060.md)).

<a id="v0-9-72"></a>
## [0.9.72] - 2026-08-30
- Added: **the skylines have depth.** Three bands are painted back to front into one strip, the far
  one small and pale and the near one large and dark, each mixed toward the sky AT THE HORIZON by its
  own amount. A ridge behind a ridge in the same colour is a wall, not a range
  ([RLG-080](../fragments/RLG-080.md)).
- Added: **every shape has an inside.** Towers get setbacks and masts, peaks a snow line and a
  sunward shoulder, mesas a talus skirt, treelines holes in them. Each is the thing that says what
  kind of object it is from a mile away, rather than detail for its own sake
  ([RLG-080](../fragments/RLG-080.md)).
- Added: **the silhouettes take the hour's own light.** A tint pass was tried before and removed
  because `source-atop` washed the sky as well as the buildings - the sky is opaque, so painting over
  every opaque pixel paints the sky. The colours are mixed in at BUILD time from the same `skyStops`
  the windscreen uses, so nothing passes over the frame at all
  ([RLG-080](../fragments/RLG-080.md)).
- Fixed: **the skyline cache is keyed by the hour as well as the biome.** A cached sprite is now a
  sprite of one hour, so without the bucket it would hold the colour of whatever moment it was first
  drawn at, through dusk and midnight - which would have looked like the tint not working rather than
  like a stale cache. One entry per biome, replaced when the bucket moves: keeping all forty would be
  180MB of canvas for a horizon ([RLG-080](../fragments/RLG-080.md)).

<a id="v0-9-71"></a>
## [0.9.71] - 2026-08-30
- Fixed: **a thick biome fills from the road edge out past the side of the screen.** One object per
  segment per side is a hedge - a single row at one distance - which is why the first version read as
  a band near the horizon with nothing close. Forest, mountain and tundra now walk several rows
  outward from the tarmac edge to beyond the frame, drawn outside in so a near trunk stands in front
  of what is behind it. The sparse places keep one row, because sparseness is the point of them
  ([RLG-059](../fragments/RLG-059.md)).
- Fixed: **an object's inner edge sits at its placement point**, so a tree at the kerb stands beside
  the tarmac rather than half over it ([RLG-059](../fragments/RLG-059.md)).
- Changed: **the mountain rows were cut from four to three**, and the row density with them. Filling
  cost frames where the objects are largest: measured 54.5 fps against 60 everywhere else, on a
  desktop, which is a warning rather than a verdict for a phone. At three rows it is 60 and it still
  reads as a valley ([RLG-059](../fragments/RLG-059.md)).

<a id="v0-9-70"></a>
## [0.9.70] - 2026-08-30
- Added: **mountain draws rock faces in three layers, and the road cuts through them.** "Various
  layers" was the one thing the owner described structurally rather than by subject, so there are
  three bands at three distances out, each paler and taller than the one in front, with slopes that
  lean OUT of the frame rather than standing square to it. The layer rises with how far out the rock
  stands, because the palette is what makes depth read ([RLG-059](../fragments/RLG-059.md)).
- Added: **tundra is mountain, painted white** - the same shapes with a different palette rather than
  a sixth set of art, which is what makes the two places read as one landscape under different
  weather. Its skyline is pale now too: against white cliffs and snow-covered ground the near-black
  silhouette read as a hole cut in the picture ([RLG-059](../fragments/RLG-059.md)).
- Note: **every other skyline is still one flat near-black at one depth**, and beside the new rock it
  now looks it. That is [RLG-080](../fragments/RLG-080.md), which the owner has already asked for and
  which follows this.

<a id="v0-9-69"></a>
## [0.9.69] - 2026-08-29
- Changed: **the roadside is measured from the road EDGE, in its own unit, so widening the road
  cannot move it.** Everything beside the road was written in multiples of `ROAD` - the lamps at 1.15
  of it, the trees at 1.35 - so the coming wider road would have pushed the whole roadside outward
  and grown it, thinning the forest at exactly the moment the tarmac got closer to it. Measured: with
  `ROAD` at 1900, 2600 and 3400 the road edge moves 31.9, 43.6, 57.1 pixels while the lamp and tree
  gaps hold at 41.5 and 54.2 ([RLG-024](../fragments/RLG-024.md), [RLG-059](../fragments/RLG-059.md)).
- Changed: **`ROAD` is a tunable rather than a constant.** RLG-024 is going to change it, the lanes
  are normalised fractions of it and so widen with it automatically, and making it settable turns
  that change into a runtime experiment instead of a rebuild - which is also what makes the
  independence above measurable at all ([RLG-024](../fragments/RLG-024.md)).

<a id="v0-9-68"></a>
## [0.9.68] - 2026-08-29
- Added: **the city has buildings, and their windows light up at night.** Four heights with setbacks
  on the taller ones, a window grid that reads as texture by day, and a second sheet carrying only
  the glass, drawn over the top with an alpha that follows the same clock the street lamps use. The
  two sheets come from one description of where the windows are, so a lit window cannot drift away
  from the hole it shines out of ([RLG-059](../fragments/RLG-059.md)).
- Changed: **the street lamps are city scenery, and nowhere else has them.** They were drawn on every
  eighth segment of everywhere, so a desert at midnight was lit by street lighting. The segment's
  biome decides, so the lighting ends where the city ends rather than under the car
  ([RLG-059](../fragments/RLG-059.md)).
- Consequence, stated because nobody asked for it in those words: **four biomes are now dark at
  night.** A forest at midnight has no light in it but the moon. That follows from the ruling rather
  than being a separate decision, and it is the kind of thing to look at rather than read about
  ([RLG-059](../fragments/RLG-059.md)).

<a id="v0-9-67"></a>
## [0.9.67] - 2026-08-29
- Added: **roadside scenery, per biome, drawn toward the camera like the lamps.** FOREST puts thick
  conifer on both sides; DESERT puts a sparse scatter of saguaro, and its emptiness is what makes the
  other places read as full. CITY, MOUNTAIN and TUNDRA declare nothing yet and so draw nothing, with
  no branch anywhere to say so ([RLG-059](../fragments/RLG-059.md)).
- Added: **placement is a hash of the segment index, not a random number.** The segment index IS the
  world position, so hashing it puts an object somewhere and leaves it there for as long as that
  segment exists, without storing anything. `Math.random()` per frame would reshuffle the whole
  roadside every frame and the forest would boil ([RLG-059](../fragments/RLG-059.md)).
- Added: **the scenery goes through the cars' crest gate**, which is the whole of RLG-073 - a tree
  behind a hill is hidden and one coming over a brow is cut off at the silhouette. Measured over
  three roads: 5,763 clipped of 386,607 asked ([RLG-073](../fragments/RLG-073.md)).
- Added: **an object belongs to its segment's biome, not to the car's**, so a transition changes the
  roadside at the same place on the road where it changes the ground rather than switching under you
  ([RLG-022](../fragments/RLG-022.md)).

<a id="v0-9-66"></a>
## [0.9.66] - 2026-08-29
- Fixed: **the mirror is framed like a mirror, and the eye height was never the fault.** It was
  raised three times from written descriptions - 1.55x, 2.15x, 3.00x - and reported still wrong after
  every one. The horizon sat at 0.16 of the glass, near the TOP, so 84% of the pane was road surface
  and the view read as looking DOWN at the tarmac. No eye height fixes that, because the eye only
  decides how fast the road falls away below that line: raising it three times made it worse each
  time. The horizon is at 0.45 now and the eye came back down to 2.20x
  ([RLG-079](../fragments/RLG-079.md)).
- Added: **`tools/mirror-shot.py`** - it renders the mirror pane on its own, enlarged, at any eye
  height, horizon, weather and hour. One look at it settled in seconds what three rounds of reasoning
  from the projection had got backwards. It asserts nothing; it is an instrument, not a gate
  ([RLG-079](../fragments/RLG-079.md)).

<a id="v0-9-65"></a>
## [0.9.65] - 2026-08-29
- Fixed: **the mirror shows the world it is in.** It never had. The sky was two fixed blues, the
  ground one fixed near-black and the tarmac two more, so the glass read as dusk in a forest at every
  hour, in every biome, in every weather - snow could cover the world and the mirror stayed dry. It
  asks the same `skyStops`, `groundBase` and `groundTone` the windscreen asks, each with one
  definition and two callers ([RLG-079](../fragments/RLG-079.md)).
- Added: **the mirror looks at the place behind you.** Its ground reads the segment index at the far
  end of what it can see, which is BEHIND the car - so during a biome change the glass still shows the
  place you are leaving while the windscreen shows the one you are entering. That falls out of asking
  the right index rather than being arranged, which is the point of the biome living on the road
  ([RLG-022](../fragments/RLG-022.md)).
- Added: **the road behind takes the same weather as the road ahead** - snow whitens it and covers the
  markings, rain soaks it. The grazing reflection is left out, because it is scaled by distance ahead
  and there is no equivalent looking back ([RLG-079](../fragments/RLG-079.md)).

<a id="v0-9-64"></a>
## [0.9.64] - 2026-08-29
- Changed: **the mirror looks down from higher up.** The owner reported from the device that it still
  shows too low to the ground. The eye rises from 2.15x the driving height to 3.00x, which spreads
  the road down the glass instead of leaving it flat along the bottom - a car 6,000 units behind moves
  from 0.158 of the pane below its horizon to 0.242.
- Changed: **the mirror height is a named tunable rather than a number inside an expression.** It has
  moved three times now - 1.55x, 2.15x, 3.00x - so `MIRROR_EYE` is the one thing about this view that
  keeps needing to move and it is findable. `API.mirrorEye()` sets it live and `API.mirrorAt()` says
  where a car at a given distance lands, so the next adjustment can be measured rather than guessed.
- Known limit, stated rather than discovered later: **the eye height and the vertical zoom are the
  same knob** in this projection, so looking further down also pushes near things off the bottom edge.
  A follower closer than about 1,300 units is now below the glass, where the limit used to be 950.
  Clamping such a car to the bottom edge - which is what a real mirror shows - would fix it and is not
  built.

<a id="v0-9-63"></a>
## [0.9.63] - 2026-08-29
- Added: **the tundra lies under snow before anything falls.** `snowFloor` is 50% there and absent
  everywhere else, and it is a floor rather than a level: a fall builds from it in the ordinary way
  and every path that takes snow away stops at it. It crosses on the WEATHER band rather than the
  ground's, because it is weather - the white should arrive with the cold, not with the colour of the
  verge ([RLG-059](../fragments/RLG-059.md)).
- Added: **arriving somewhere that lies under snow whitens the ground over seconds, not in a frame.**
  Clamping the level up to the floor would have snapped it white the instant the floor rose, which is
  the switch this run of work exists to remove. The decay stops at the floor when it is already above
  it, and a separate gentle climb handles arriving below it - about four seconds from bare to a
  tundra's half cover ([RLG-057](../fragments/RLG-057.md)).
- Changed: **the tundra is permanently slipperier, and nothing was added to say so.** `wetGrip`
  already costs `settle * 0.30`, so a floor of 0.5 takes about 15% of dry grip before a flake falls.
  That is a consequence of the ruling rather than a separate decision
  ([RLG-057](../fragments/RLG-057.md)).

<a id="v0-9-62"></a>
## [0.9.62] - 2026-08-29
- Fixed: **the skyline belongs to the horizon, not to the car.** The far-field ground already showed
  the new biome the moment a boundary was placed, while the skyline was still rebuilt on ARRIVAL - so
  for the whole transition you would have seen the new biome's ground sitting under the old biome's
  sky. The horizon is the furthest segments and those are already the next place, so the skyline
  inherits from them ([RLG-022](../fragments/RLG-022.md)).
- Added: **both skyline swap mechanisms, switchable.** A crossfade is a degenerate case of the layer
  move - two skylines drawn at once, blended by opacity instead of by position - so building the
  layers gives both for one branch. `SKY_SWAP` defaults to `move`: the outgoing skyline sinks and
  shrinks behind the horizon while the incoming one rises from it. The owner rules on which reads
  better after seeing them ([RLG-022](../fragments/RLG-022.md)).
- Added: **the weather transitions as you cross, over a longer run than the ground.** Weather the new
  place cannot produce thins out in proportion to how far in you are, instead of being switched off
  at a line, and settled snow starts melting at a rate that comes on with the crossing. The weather
  band is 72 segments against the colour band's 18, because the ground underfoot changes at a line
  and the sky above it does not - measured, the weather ramps 0.00, 0.35, 0.69, 1.00 while the ground
  steps across its own ([RLG-022](../fragments/RLG-022.md)).
- Fixed: **the weather harness pins the biome as well as the hour.** The verge check went red on runs
  that landed in FOREST and green on runs that landed in DESERT, on one unchanged build, because a
  dark ground leaves the rain darkening least room to show. It is pinned to the darkest biome, so a
  pass is a pass everywhere - which a random biome could never promise
  ([RLG-057](../fragments/RLG-057.md)).

<a id="v0-9-61"></a>
## [0.9.61] - 2026-08-29
- Added: **a biome change is a place you drive into.** The new biome's colour is taken by the road
  slices at the furthest point being drawn and travels toward the camera as you approach it, with an
  18-segment blend band so the join is a ramp rather than a line. The mechanism is the segment index:
  it is an absolute world position, so a boundary placed at one arrives on its own and nothing has to
  animate it. The weather, the skyline and the name flash still fire when the CAR crosses, because
  that is when you have arrived ([RLG-022](../fragments/RLG-022.md)).
- Fixed: **each biome is strict about its ground at every hour.** The night and golden-hour ground
  colours were flat hex constants shared by all five biomes, so a desert at night was the same
  green-black as a forest at night - and the sweep would have been invisible for most of the day
  cycle. They are derived from the biome's own grass now, dimmed and cooled after dark and warmed at
  golden hour, so a biome added later gets both for nothing
  ([RLG-059](../fragments/RLG-059.md)).
- Fixed: **the band under the horizon is the same ground, seen further off.** It asked `bio()` - where
  the CAR is - while showing what is at the far end of the road, so a transition would have reached
  the horizon last instead of first. It reads the same `groundTone` call the furthest drawn slice
  makes. Its brightness is now normalised to a fixed fraction of the foreground rather than hoped for:
  the haze wash mixes toward a light grey, so on a dark biome it made the band BRIGHTER - a forest
  verge at 48 came out at 79 ([RLG-022](../fragments/RLG-022.md)).
- Added: **`tools/biome-test.py`** - it reads the sweep as numbers over time, because one frame cannot
  show travel. A flip shows the same mix at the car and at the horizon at every instant; a sweep shows
  the horizon leading. The harness puts the flip back and checks that the distinction fails
  ([RLG-022](../fragments/RLG-022.md)).

<a id="v0-9-60"></a>
## [0.9.60] - 2026-08-29
- Fixed: **the street lamps had no occlusion at all, and now they use the cars'.** The test guarding
  them was `!overBrow(...)`, and `overBrow` returns false on its first line - dead since `crestY` was
  re-enabled. So a post behind a hill drew straight through it and one coming over a brow arrived
  whole, which is the pop reported from the device. The crest rules are lifted out of `drawSprite`
  into one `crestGate` and both callers use it, because a second implementation that behaves
  similarly is a thing that drifts ([RLG-073](../fragments/RLG-073.md)).
- Added: **the crest gate keeps a ledger of what each kind of thing DID about its answer**, and the
  distinction is the whole value of it. Counting the outcome inside the gate records what the gate
  decided, and a caller that asks and then ignores the answer - which is exactly the fault being
  fixed - produces an identical ledger. The first version of the check passed with the defect
  deliberately put back. The count moved to the branch that acts, and it then failed at 0 clipped
  against 47 ([RLG-073](../fragments/RLG-073.md)).

<a id="v0-9-59"></a>
## [0.9.59] - 2026-08-29
- Changed: **thunder is a crack and a rumble, and distance eats the crack.** High frequencies are
  absorbed and scattered over distance and low ones are not, so a strike overhead is a crack with a
  rumble under it and the same strike a mile off is the rumble alone. The crack falls away as the
  nearness squared - it keeps 22% of its level at half distance and is gone entirely past two thirds
  - while the rumble falls in a straight line and never below 0.20. The far rumble also runs longer,
  2.8s overhead against 4.6s across the valley, because what reaches you has come by several paths
  ([RLG-060](../fragments/RLG-060.md)).
- Fixed: **the weather harness pins the time of day.** A run started at DUSK drifted into the night
  branch part way through, where the ground is already dark and the rain darkening has almost no room
  to show, and the verge check went red on one run in six at a margin of about three. Loosening the
  threshold would have hidden a real thing about the effect; measuring in daylight is what makes the
  number mean anything ([RLG-057](../fragments/RLG-057.md)).

<a id="v0-9-58"></a>
## [0.9.58] - 2026-08-29
- Changed: **thunder is loud enough to be thunder.** It was mixed as a background texture, under
  `dead` and `copDown`, which are ordinary event sounds. Thunder is the loudest thing in a storm and
  it should make you look up. The three beds now peak at 0.46, 0.37 and 0.20 - about 1.8x - and the
  headroom was counted rather than guessed: the master bus is 0.85 with no compressor after it, the
  beds do not peak together, and the worst case through the master is 0.71
  ([RLG-060](../fragments/RLG-060.md)).
- Changed: **the gap between the flash and the sound is how far away the strike was.** The delay
  runs from 250ms to 5s, and the distance is rolled once so the delay, the loudness and the
  brightness of the flash all follow from it. They used to be rolled separately, so a strike could
  arrive at full volume five seconds after its flash or barely register a quarter of a second later
  ([RLG-060](../fragments/RLG-060.md)).
- Added: **the weather harness measures the sound as well as the paint.** It records the gains
  thunder hands the synthesizer, rather than reading a value back off the Web Audio graph - RLG-065
  cost three attempts on that distinction, because a GainNode on a closed context reports a healthy
  value quite happily. The old levels were put back and both loudness checks were watched going red
  ([RLG-060](../fragments/RLG-060.md)).

<a id="v0-9-57"></a>
## [0.9.57] - 2026-08-29
- Fixed: **the weather is painted on the ground, not washed over the frame.** Snow cover and the rain
  darkening were screen-wide rectangles drawn after the road and after the player, so the car got as
  snowed on as the ground it stood on and a hill a quarter of a mile away got as wet as the tarmac
  underfoot. The owner rejected the snow half on sight. Both now mix into each surface's own colour,
  per segment: the ground layer that follows the road over every crest, and the band between it and
  the horizon ([RLG-057](../fragments/RLG-057.md)).
- Fixed: **settled snow shows at every hour.** The night and golden-hour ground colours were flat
  hex values that ignored the cover, so snow vanished at sunset and returned at dawn. That is what
  the full-screen overlay had been quietly compensating for. Snow now takes the colour of the light
  on it - near white at noon, warm at golden hour, a dim blue-grey under a moon
  ([RLG-057](../fragments/RLG-057.md)).
- Added: **the road itself covers over, and that is the slippery part.** The tarmac whitens as snow
  accumulates, less than the land beside it so the corridor stays readable, and the markings go under
  the cover before the surface does ([RLG-057](../fragments/RLG-057.md)).
- Changed: **snow unwinds at the rate it arrived.** It was a one-way build with a slow leak under it.
  When the fall stops and the biome still allows snow, the cover runs back down the slope it climbed
  and the grip returns at the pace it went - a blizzard that covers the ground in forty seconds
  clears it in forty. A biome that cannot hold snow still takes it away outright
  ([RLG-057](../fragments/RLG-057.md)).
- Added: **rain accumulates too, by the same model.** Standing water builds while it rains, unwinds
  at twice that rate when it stops because water runs off a camber, and clears outright in a biome
  that cannot rain. Rain used to be a level: a shower was at its worst the second it arrived and no
  worse ten minutes later. The falling term drops from 0.38 to 0.22 to pay for it, so a shower
  arriving is gentler and a rain that has set in is worse ([RLG-057](../fragments/RLG-057.md)).
- Fixed: **the wet sheen was a third full-screen wash, and it reversed the other two.** It added more
  light than the darkening removed - measured, the tarmac came out 5.4 brighter in the rain than it
  was dry. A wet road is bright in the distance because of reflection at a grazing angle, so that is
  where it is painted now: on the road, per segment, scaled by distance, absent at your feet
  ([RLG-057](../fragments/RLG-057.md)).
- Added: **`tools/weather-test.py`** - it stops the world, then reads pixels off the frozen frame
  with only the weather changed between samples. The assertion that carries it is that the player's
  car does not change colour when the weather does, and the harness proves that check is real by
  putting the old full-screen wash back through `CFG.afterDraw` and watching the same check go red
  ([RLG-057](../fragments/RLG-057.md)).

<a id="v0-9-56"></a>
## [0.9.56] - 2026-08-29
- Changed: **snow accumulates instead of settling to a level.** It used to chase the fall and stop
  there, so a flurry could never whiten the ground however long it lasted and a blizzard reached its
  ceiling in seconds. It integrates now - about forty seconds of heavy snow to cover the ground,
  three or four minutes for a flurry - and melt is a twentieth of the rate it arrived
  ([RLG-057](../fragments/RLG-057.md)).
- Changed: **deep snow is slicker than snow.** Settled cover costs more grip than the fall does: a
  road with an inch on it is the hazard and the flakes are only how it got there. Measured, grip fell
  from 0.578 to 0.340 as the ground whitened, and the floor is deliberate - below a third of dry grip
  a car feels broken rather than slippery ([RLG-057](../fragments/RLG-057.md)).

<a id="v0-9-55"></a>
## [0.9.55] - 2026-08-29
- Fixed: **settled snow is two layers rather than one slab.** It was a single overlay filling
  everything from the horizon down at one strength. There is a bright far field under the horizon
  that fades downward, and a wash on the ground in front of you that fades upward, and the two
  overlap across most of the plane so there is nowhere for a seam to be
  ([RLG-057](../fragments/RLG-057.md)).

<a id="v0-9-54"></a>
## [0.9.54] - 2026-08-29
- Added: **cloud cover as a range from clear to overcast.** It is a weather variable rather than a
  consequence of rain - an overcast day with no rain in it is the commonest sky there is - and rain
  or snow raise it. `storm` is how black the cover is and follows the rain, so heavy rain is dark and
  heavy snow is bright ([RLG-057](../fragments/RLG-057.md)).
- Added: **the sun and moon bleed through the cloud**, because the cover is drawn after them
  ([RLG-057](../fragments/RLG-057.md)).
- Added: **lightning and thunder.** A strike belongs to a heavy storm and never to snow; the flash is
  two or three strikes in quick succession and lights the cloud rather than the ground, and thunder
  follows at a distance. **Not verified by ear** ([RLG-060](../fragments/RLG-060.md)).

<a id="v0-9-53"></a>
## [0.9.53] - 2026-08-29
- Added: **the wipers move, and the lens gets wet.** Every vehicle has carried a wiper since the
  fronts were drawn and the only caller was the fleet sheet - the mirror drew them parked in all
  weathers. One sweep clock for the whole road, at a rate set by how hard it is raining, because at
  sprite size a road of blades each keeping its own time reads as noise and one rhythm reads as
  weather ([RLG-060](../fragments/RLG-060.md)).
- Added: **drops on the camera lens** that arrive with the rain and the speed, crawl, and clear
  completely when the wiper passes - the same clock, so the lens clears on the stroke you can see on
  the car in front ([RLG-060](../fragments/RLG-060.md)).

<a id="v0-9-52"></a>
## [0.9.52] - 2026-08-29
- Added: **traffic signals before it merges.** A car announces the move, waits between 1.1 and 1.8
  seconds, re-checks the gap and only then crosses - and one driver in five never bothers, decided
  once per car because it is a habit rather than a coin toss. The indicator flag had been set on
  every merge decision since the merge logic was written and **no renderer had ever read it**
  ([RLG-052](../fragments/RLG-052.md)).
- Added: **`traffic-test` checks the screen, not the engine.** It forces every car to blink and
  counts amber pixels - 11 with the blinks off, 57 with them on. A check that read only the engine
  state would have passed the whole time the feature was invisible
  ([RLG-052](../fragments/RLG-052.md)).

<a id="v0-9-51"></a>
## [0.9.51] - 2026-08-29
- Changed: **the fleet sheets live in `docs/fleet/`.** Six pictures beside the prose is a folder you
  have to read past to find a document. Nothing was left behind to move: every render has overwritten
  the same six paths since the class split ([RLG-053](../fragments/RLG-053.md)).

<a id="v0-9-50"></a>
## [0.9.50] - 2026-08-29
- Changed: **the dim state splits the difference between off and bright**, and carries a third of the
  glow. A running light does glow a little, and a lamp that lights with no bloom reads as a painted
  shape rather than as a light ([RLG-053](../fragments/RLG-053.md)).

<a id="v0-9-49"></a>
## [0.9.49] - 2026-08-29
- Changed: **the whole lamp ladder moves down a rung.** The red that was the unlit lens is the
  running light now, and unlit is a lens with almost nothing in it - which is what an unlit red lamp
  looks like in daylight ([RLG-053](../fragments/RLG-053.md)).
- Changed: **a headlight is dark when it is off.** It was a pale grey lens whether lit or not, so the
  lit state had nothing to arrive from ([RLG-053](../fragments/RLG-053.md)).
- Added: **weather turns the lights on as if it were night.** `lampsOn()` takes the stronger of the
  clock and the weather, so a storm at noon lights the road - street lamps, tail lights, headlights
  and the mirror all read that one function ([RLG-053](../fragments/RLG-053.md)).

<a id="v0-9-48"></a>
## [0.9.48] - 2026-08-29
- Added: **a little tyre under every vehicle**, drawn before the body so the sill overlaps it and
  only the bottom shows ([RLG-053](../fragments/RLG-053.md)).
- Fixed: **the front bumper is the same colour as the rear one** ([RLG-053](../fragments/RLG-053.md)).
- Changed: **the van is a size smaller.** It was 85% of an articulated lorry; it is about 70% now
  ([RLG-053](../fragments/RLG-053.md)).
- Changed: **the muscle car's front indicators sit behind its headlights**
  ([RLG-053](../fragments/RLG-053.md)).
- Changed: **the MATADOR and SUPER CRUISER tail is a full bank of chevrons** - eight brake blades a
  side and a two-blade indicator outboard of them ([RLG-053](../fragments/RLG-053.md)).

<a id="v0-9-47"></a>
## [0.9.47] - 2026-08-29
- Fixed: **brake lights are red, and they have three states.** They were drawn additively over the
  picture underneath, which turns red into white, and their inner highlight was nearly white before
  anything was added to it. A lamp paints its own lens opaquely now, and its highlight is a lighter
  RED. Off is daylight idle, dim is the night-time running light, bright is the brake - and the level
  is driven where the car is drawn rather than faked with alpha
  ([RLG-053](../fragments/RLG-053.md)).
- Added: **a lit lamp carries a baked glow.** Rendered once at build time and blurred, drawn
  additively behind the lens. `lamp-test` gained a check that a lit lamp covers more than its own
  lens, which found four vehicles whose glow was being thrown off the canvas
  ([RLG-053](../fragments/RLG-053.md)).

<a id="v0-9-46"></a>
## [0.9.46] - 2026-08-29
- Fixed: **a car's front now has the same silhouette as its back.** The rear body is a path with a
  waist - shoulders curving out to 0.955 and a sill tucking back in - and the front was a rounded
  rectangle under a comment claiming it was "exactly as the back". It was exactly as the back at the
  two edges it named and a different shape everywhere between them. The front draws the rear's own
  path now, with the rear's arch blisters ([RLG-053](../fragments/RLG-053.md)).

<a id="v0-9-45"></a>
## [0.9.45] - 2026-08-29
- Changed: **the garage's two views hang from the roof line.** A shared floor line is the physical
  way to think about it and is not what reads as aligned: the two ends carry different amounts of car
  below the body, so a common floor pushes the front's roof up. Owner's instruction - align the tops.
  The card is also sized to the cars in it rather than to a constant
  ([RLG-072](../fragments/RLG-072.md)).

<a id="v0-9-44"></a>
## [0.9.44] - 2026-08-29
- Fixed: **the player's front sprite is built in the same box as its rear.** The garage's two views
  were not misaligned, they were different shapes: a road car's tail is painted into that shape's own
  canvas and its face was being painted into a flat 220x168, so the same car came out with different
  proportions. The same hardcoded box was in three other places, including the rival caches - so
  every sports-class rival on the road was drawn at the wrong aspect ratio. One `rigBox()` now, read
  by all of them ([RLG-072](../fragments/RLG-072.md)).
- Fixed: **drive-test knows about the ladder.** It expected the supercars in the garage and asserted
  150mph in a car that now tops out at 153 - so a garage change reported itself as a slow engine. It
  expects the sports class and asserts nine tenths of whatever car it is sitting in
  ([RLG-070](../fragments/RLG-070.md)).

<a id="v0-9-43"></a>
## [0.9.43] - 2026-08-29
- Fixed: **an old save no longer starts with the supercars.** The migration that protects a returning
  player's cars counted the SAVED CAR as evidence of a career, and the old default body was a
  MATADOR - so every save ever written held a supercar key and every returning player was handed the
  class for nothing. Only a tournament prize counts now
  ([RLG-070](../fragments/RLG-070.md)).

<a id="v0-9-42"></a>
## [0.9.42] - 2026-08-29
- Fixed: **the garage's two views are the same car.** Aligning their sprite boxes was not enough and
  neither was one shared scale: the two painters draw the car at different sizes inside their own
  canvases, so the front came out about nine per cent bigger. Each end is now scaled so their solid
  bodywork is the same WIDTH - the one dimension both views share - and the floor line is read from
  the tyres rather than from the soft shadow under them ([RLG-072](../fragments/RLG-072.md)).

<a id="v0-9-41"></a>
## [0.9.41] - 2026-08-29
- Fixed: **every vehicle in the mirror is the real car.** The police were still drawn as the
  placeholder block, and no car fades to a simplified render any more: the level of detail, the
  cross-fade and the MIRROR setting are all gone, and the mirror is always the full one. The two
  police cars gained the fronts they never had ([RLG-074](../fragments/RLG-074.md)).
- Added: **`tools/face-test.py`** - asks the engine what the mirror would draw for every vehicle in
  the game, and fails if any of them has no face or a blank one. Three vehicles have been found in
  this state by eye, on a phone, weeks after shipping ([RLG-074](../fragments/RLG-074.md)).

<a id="v0-9-40"></a>
## [0.9.40] - 2026-08-29
- Changed: **the whole fleet's stat table, and acceleration and braking are derived rather than
  declared.** Every class below the supercars comes down and the gaps between classes are equal:
  formula 248-276, super 190-206, sports 142-160, production 100-120, utility 80-94. Acceleration is
  `1.56 * sqrt(hp/mass) * launch` and braking is `grip * mech`, so horsepower, mass and grip are now
  what a car IS and the two old multipliers are gone. Mass is deliberately absent from braking: in a
  tyre-limited stop it cancels, and what makes a heavy vehicle stop badly already lives in its grip
  ([RLG-055](../fragments/RLG-055.md)).
- Changed: **each police car is the slowest of the class it polices, and the best-braked.** The super
  cruiser sits 4mph under the slowest supercar, which makes its own note about the cage costing it
  4mph true; the cruiser sits 4mph under the slowest sports car ([RLG-055](../fragments/RLG-055.md)).
- Fixed: **the three stat comments that described numbers this change moved** - the 200mph ceiling,
  the sports-class rungs, and the super cruiser's note ([RLG-055](../fragments/RLG-055.md)).

<a id="v0-9-39"></a>
## [0.9.39] - 2026-08-29
- Fixed: **the formula cars reach their own top speed.** A safety clamp at 260mph and a speedometer
  face fixed at 260 were both written when the quickest car did 206 - so COMET, declared at 276, was
  held at 260 with a pegged needle. Both are derived from the fleet now, and the dial's red band is
  the car's own ceiling rather than a fixed 200. Measured: 248, 260 and 276 of 248, 260 and 276; with
  the old clamp restored, COMET reaches 260 ([RLG-075](../fragments/RLG-075.md)).

<a id="v0-9-38"></a>
## [0.9.38] - 2026-08-29
- Fixed: **the garage's two views stand on one floor at one scale.** They were bottom-aligned by
  their sprite boxes, which are different shapes with the car in a different place inside each - so
  one end floated and the two were different sizes. The painted content of each sprite is measured
  and the pair is placed by that ([RLG-072](../fragments/RLG-072.md)).

<a id="v0-9-37"></a>
## [0.9.37] - 2026-08-29
- Fixed: **the racers have faces in the mirror.** The mirror fades a painted nose in over a
  simplified block as a car closes, but it looked the nose up by traffic TYPE - and a racer carries a
  body and a paint instead, so every rival stayed a coloured lozenge while the van beside it had a
  face. Rival fronts are built on demand, about eight in a race, rather than doubling a hundred
  cached canvases on a phone ([RLG-074](../fragments/RLG-074.md)).

<a id="v0-9-36"></a>
## [0.9.36] - 2026-08-29
- Added: **`stat-test` measures braking and cornering.** RLG-055 was blocked on it: every body
  declares a `brake` and a `grip` and nothing had ever checked what they do. Braking is a stopping
  distance from 140 to 40mph; cornering is the drift through one bend with **no steering input at
  all**, divided by the push the engine applied. Both stats turn out honest - braking spreads four to
  one, and the measured `cornerG` times the declared grip is 0.420 with a standard deviation of 0.006
  across sixteen bodies. Both halves were watched failing with the stats removed
  ([RLG-055](../fragments/RLG-055.md)).
- Added: **five probe instruments** the measurement needed - `setBrake`, `pushK`, `targetX`,
  `curvatureAt` and `setLane` ([RLG-055](../fragments/RLG-055.md)).

<a id="v0-9-35"></a>
## [0.9.35] - 2026-08-29
- Added: **the garage shows both ends of the car.** Only the tail was ever built for the player, and
  the garage is the one screen where you look at the car instead of following it. Each end is about
  half the size the single picture was, and the card is fifty pixels shorter with it - two cars side
  by side are limited by their width, so the taller card was a band of nothing
  ([RLG-072](../fragments/RLG-072.md)).

<a id="v0-9-34"></a>
## [0.9.34] - 2026-08-29
- Removed: **the silver and bronze prizes.** They paid the TUNER and the MUSCLE car, and both are in
  the starting class since the ladder was built - so second and third place were handing over cars
  the player already owned. What those places should pay instead is being explored
  ([RLG-071](../fragments/RLG-071.md)).

<a id="v0-9-33"></a>
## [0.9.33] - 2026-08-29
- Added: **the formula class - VECTOR, APEX and COMET.** One formula car became three, each at least
  twenty per cent above the *best* supercar in every stat: 248, 260 and 276mph, biased to
  acceleration, balance and top end. They share one design and are told apart by name, badge and
  numbers - VECTOR wears blue chevrons, APEX the gold bolt, COMET a comet
  ([RLG-070](../fragments/RLG-070.md)).
- Changed: **`classOf` knows a third class.** A formula car used to fall through into 'super' and race
  road cars. The grid, the ladder, the yoke, the missing indicators and the missing wipers all follow
  the class now, so nothing names these three cars again ([RLG-070](../fragments/RLG-070.md)).
- Changed: **the ladder of classes.** A fresh install holds the sports class alone. A sports gold
  opens the supercars, a supercar gold opens the formula class, and a formula gold opens the
  iridescent paints. An existing save that shows a career keeps the supercars it already had
  ([RLG-070](../fragments/RLG-070.md)).
- Added: **a third debug switch.** All racers, police, all traffic - the patrol car used to ride on
  the racers' switch, so testing a pursuit opened the whole ladder with it
  ([RLG-070](../fragments/RLG-070.md)).

<a id="v0-9-32"></a>
## [0.9.32] - 2026-08-29
- Added: **a plain steering wheel for the production and utility cars.** They were being given the
  sports wheel with its flat bottom rounded off - carbon weave, chrome spoke inserts, a bezel round
  the switchgear and a racing tick at twelve o'clock. The plain wheel is its own object: a moulded
  rim, plain arms, no weave and no tick, and a wide horn pad in place of the machined hub. The lorry
  takes a thinner rim than the rest ([RLG-053](../fragments/RLG-053.md)).

<a id="v0-9-31"></a>
## [0.9.31] - 2026-08-29
- Changed: **racing stripes belong to the supercars and the sports cars.** The rule was an exclusion
  of the two cars that already wear a livery, which left every van and saloon free to wear a pair of
  Le Mans stripes. It is a list now - the formula car stays out because its livery is its bodywork -
  and the STRIPES button no longer appears in the garage for the six production and utility cars
  ([RLG-053](../fragments/RLG-053.md)).

<a id="v0-9-30"></a>
## [0.9.30] - 2026-08-29
- Changed: **each vehicle is drawn in the paint it is allowed to wear.** The fleet sheet built every
  body in white, so the cab was white and both patrol cars were white. The cab takes its forced
  yellow, and each patrol car appears twice - once in each of the force's two liveries, built from
  `COP_PAINT` rather than the garage palette. Everything else stays white
  ([RLG-053](../fragments/RLG-053.md)).
- Added: **a stripes frame on every row.** Stripes are paint rather than a body, so any car can wear
  them except one already wearing a livery of its own - the formula car and both cruisers, whose
  cells are empty ([RLG-053](../fragments/RLG-053.md)).

<a id="v0-9-29"></a>
## [0.9.29] - 2026-08-29
- Fixed: **the utility vehicles have windscreen wipers.** The pickup, the van and the lorry were the
  only things on the road without a pair. Each has its own branch in the front painter, because a
  lorry's face is mostly glass and a pickup's cab sits back behind its bed, and every one of those
  branches returns before the shared registration at the bottom of the painter - so the wipers were
  never handed back for those three. Each branch registers its own now, and the lorry's takes the
  cab's paint rather than the trailer's ([RLG-053](../fragments/RLG-053.md)).

<a id="v0-9-28"></a>
## [0.9.28] - 2026-08-29
- Changed: **the road cars are earned by distance on the clock.** The old rule was a hundred miles on
  TEST DRIVE with any settings, opening every road car at once. Now **25 miles unlocks UTILITY** and
  **50 miles unlocks PRODUCTION**, and both need the timer running. A save holding the retired
  `traffic` flag keeps both ([RLG-067](../fragments/RLG-067.md)).
- Changed: **the lorry's trailer takes a much darker shade of the chosen colour** instead of a fixed
  beige, and the cab still wears the colour itself. It exposed a fault the rear view had hidden - the
  FRONT painter drew the cab out of the trailer's shade, so the whole face was the colour of the box
  ([RLG-053](../fragments/RLG-053.md)).
- Added: **a hint of the trailer above the lorry's cab.** Head on, a lorry is a cab with a box behind
  and above it; without that the front view was a tall van ([RLG-053](../fragments/RLG-053.md)).
- Fixed: **the wipers are no longer baked into the sprite.** They were drawn parked into the canvas
  AND handed back for animation, so anything sweeping them painted a second pair over the first -
  both poses at once ([RLG-053](../fragments/RLG-053.md)).
- Fixed: **the blower floated above the bonnet**, and it is anchored to the bonnet line now rather
  than to a number chosen beside it ([RLG-053](../fragments/RLG-053.md)).
- Changed: **the blower is a bug catcher** - three round trumpets with red mouths on a narrow
  injector hat, a polished ribbed case, and the drive pulley at the bottom, the whole unit about a
  fifth of the car's width and standing through the bonnet. Two earlier attempts were wide flat
  scoops, which is bodywork rather than an engine ([RLG-053](../fragments/RLG-053.md)).
- Verified, not assumed: a cab is always yellow, the two force cars are black-and-white only, and the
  lorry's cab is what carries the paint ([RLG-053](../fragments/RLG-053.md)).

<a id="v0-9-27"></a>
## [0.9.27] - 2026-08-29
- Added: **every FRONT declares its lamps** - `head`, `turn.l`, `turn.r`, and the front pair of the
  police bar. 84 lamps became 130 across the same 26 vehicles
  ([RLG-053](../fragments/RLG-053.md)).
- Fixed: **every car's headlights were on at noon.** `headGlow` painted a bloom straight into the
  sprite, so a parked car glowed in the garage. A headlight is a lamp like any other now
  ([RLG-053](../fragments/RLG-053.md)).
- Added: **wipers.** A wiper is not a lamp - it has a POSITION, not an on and off - so a sprite
  carries `wipers(g, t)` beside its lamps, 0 parked and 1 at full sweep, and bakes the parked pose.
  They wear the car's own paint and a lighter shade of it ([RLG-060](../fragments/RLG-060.md),
  [RLG-053](../fragments/RLG-053.md)).
- Changed: **the muscle car loses its forced stripes and gains an exposed blower** standing out of
  the bonnet and cutting into the screen, drawn in front of the wipers. Its outer headlight is a
  bigger bulb than its inner one ([RLG-053](../fragments/RLG-053.md)).
- Fixed: **every supercar wore MATADOR's face.** `paintFront` takes its body under `bodyType` and the
  fleet accessor was passing `kind` - five cars, one nose
  ([RLG-053](../fragments/RLG-053.md)).
- Changed: **a front indicator is its own lamp, never a headlight.** At the rear a cluster is a row
  of repeated elements and the outermost can be the amber; at the front there are two lamps and
  taking one removes a headlight. STALLION and MATADOR stack theirs under the lamp at the lamp's own
  rake; CREST's banded bar gives up its outermost segment, which is the rear's answer for the rear's
  reason ([RLG-053](../fragments/RLG-053.md)).
- Changed: **one sheet per class** - `docs/fleet-super.png`, `-sport`, `-police`, `-production`,
  `-utility`. One picture of everything was unreadable at any size that fits on a screen. Two rows
  per vehicle, back then front, and the steering wheels at the end
  ([RLG-053](../fragments/RLG-053.md)).

<a id="v0-9-26"></a>
## [0.9.26] - 2026-08-29
- Fixed: **the van has one brake light and one indicator above it, per side.** It was a single tall
  red lamp with an amber band across its top - one object that read as two - and two earlier attempts
  each adjusted the wrong part of it ([RLG-053](../fragments/RLG-053.md)).
- Changed: **on every laterally-clustered car the indicator is OUTBOARD** - roadster, tuner, cruiser,
  coupe, saloon, cab. Inboard put the two ambers together in the middle of the car, where they read
  as one central lamp rather than as a side being signalled. Carved out of the cluster, so the tail
  is the width it always was ([RLG-053](../fragments/RLG-053.md)).
- Changed: the fleet sheet names each vehicle once. **There is no garage version and traffic version
  - it is one car** ([RLG-053](../fragments/RLG-053.md)).

<a id="v0-9-25"></a>
## [0.9.25] - 2026-08-29
- Fixed: **the van had two indicators.** Its cluster has always carried an amber band across the top
  of each red lamp; the conversion added a bulb above it. The band is declared as the indicator now
  and the added bulb is gone - the art was already right and nothing was reading it
  ([RLG-053](../fragments/RLG-053.md)).
- Fixed: **the lorry's roof row lit pale yellow when asked to light red.** A lit lamp composites with
  `lighter`, which adds, and amber plus red is yellow. The row is dark red when off and bright red
  when braking, which is what a lorry's rear roof markers are
  ([RLG-053](../fragments/RLG-053.md)).

<a id="v0-9-24"></a>
## [0.9.24] - 2026-08-29
- Changed: **STALLION keeps all four rings as brake lights**, and the indicator is the dot inside the
  outer two - the first attempt made the outer rings themselves amber, which changed what the brake
  light is ([RLG-053](../fragments/RLG-053.md)).
- Changed: **MUSCLE has four boxes a side**, the outermost one the indicator, matching MATADOR's
  outermost chevron ([RLG-053](../fragments/RLG-053.md)).
- Changed: **the VAN indicates above its brake lights**, and only there
  ([RLG-053](../fragments/RLG-053.md)).
- Changed: **the LORRY's roof running lights brake as well** - they are part of the tail declaration
  now, which is what you actually see of a lorry slowing at night
  ([RLG-053](../fragments/RLG-053.md)).
- Changed: `fleet-sheet` prints each row's painter, so two rows that look alike in white can be told
  apart rather than read as duplicates ([RLG-053](../fragments/RLG-053.md)).

<a id="v0-9-23"></a>
## [0.9.23] - 2026-08-29
- Added: **the whole fleet declares its lamps** - 84 lamps across 26 vehicles, each a single drawing
  run unlit into the sprite and again lit on top of it. Every rear sprite in the game is converted
  ([RLG-053](../fragments/RLG-053.md)).
- Added: **every vehicle but the FORMULA has indicators**, wired and working, with the blink phase
  running whether or not anything is signalling so a lamp that comes on is in step with the road.
  **The FORMULA has none by the owner's ruling** - a single-seater does not carry them, and that is
  what the car is rather than something unfinished
  ([RLG-052](../fragments/RLG-052.md), [RLG-053](../fragments/RLG-053.md)).
- Added: **the police bar is four addressable lamps**, on the cruiser and the super cruiser alike,
  so a bar can run a pattern instead of pulsing as one blob. `drawCopLights` no longer paints its
  own bar over the sprite's - and the two never agreed: the lit bar sat at 0.19 of the car's width
  against the sprite's 0.235 ([RLG-053](../fragments/RLG-053.md)).
- Changed: the unlit bulb is a **dark amber** and the lit one a **bright amber**; on MATADOR the
  indicator **is** the outermost chevron of the tail cluster, and on STALLION it is the outer two of
  the four rings - so a signal is the same design as the brake light beside it
  ([RLG-053](../fragments/RLG-053.md)).
- Added: `tools/fleet-sheet.py` and `docs/fleet.png` - the fleet drawn dark, braking, indicating
  each way, and with the bar. One row per painter, so the garage SALOON and the traffic sedan are
  one car in two liveries rather than two rows ([RLG-053](../fragments/RLG-053.md)).
- Added: `lamp-test` checks all 84 lamps with no colour knowledge - it runs each declaration lit and
  unlit and compares **pixels**. Its first version compared bounding boxes and could not see one
  lamp of a pair sliding inside the box; a deliberate 3% drift passed. It now fails at 50 stray
  pixels of 1,156 ([RLG-053](../fragments/RLG-053.md)).

<a id="v0-9-22"></a>
## [0.9.22] - 2026-08-29
- Added: **a lamp is one drawing, run twice.** A painter declares its lamps as functions that draw
  themselves and take one argument - lit or not. The sprite runs each unlit as it bakes; the screen
  runs the same function again through a transform that maps the sprite onto the car. One
  description, executed twice, so a reskin moves the bulb and its light together
  ([RLG-053](../fragments/RLG-053.md)).
- Fixed: **there were three descriptions of the player's tail lamps.** The sprite's own art,
  `playerBrakes` (which **nothing ever called**), and a third inline in `drawPlayer` - the one you
  actually saw. `playerBrakes` is deleted rather than converted; the inline copy remains only for
  bodies not yet converted ([RLG-053](../fragments/RLG-053.md)).
- Fixed: the player's tail glow was drawn **outside the transform that draws the car**, so it did not
  lean with it ([RLG-053](../fragments/RLG-053.md)).
- Added: **the MATADOR has indicators, wired and unasked.** An unlit amber bulb at each blade
  housing, lit through the same declaration, with the blink phase running at ~1.5Hz whether or not
  anything is signalling - so a lamp that comes on is in step with every other one on the road.
  Nothing in the game asks for it, which is the ruling and not an omission
  ([RLG-052](../fragments/RLG-052.md), [RLG-053](../fragments/RLG-053.md)).
- Added: `tools/lamp-test.py` - runs the declaration lit into a blank canvas and checks those pixels
  sit where the **baked sprite's** own unlit bulb sits. Shifting only the lit pass by 5% fails it.
  Two earlier versions diffed live frames and were reporting weather: 800-1,300 pixels of the car
  change between two frames with the lamp off ([RLG-053](../fragments/RLG-053.md)).
- **Not converted:** CREST, STALLION, FORMULA, the cruiser, the super cruiser, every traffic body,
  the front sprites and the rear-view. `lamp-test` skips rather than passes on those, so a
  half-converted engine cannot read as a finished one ([RLG-053](../fragments/RLG-053.md)).

<a id="v0-9-21"></a>
## [0.9.21] - 2026-08-29
- Fixed: **fully visible cars vanished beyond the bottom of a valley.** `horizon` is a fixed line at
  40% of the canvas - where sky meets ground on *flat* road - and the sprite pass culled anything
  standing above it as "off screen". Beyond a dip the far side rises, the road is painted well above
  that line, and a car standing on it was thrown away while in plain sight. The screen is the bound
  now ([RLG-041](../fragments/RLG-041.md)).
- Measured, splitting the two cases before changing either: **2,083 and 3,469 vehicle-frames per run
  were culled as "off screen" while on the screen; genuinely off the top, 3 and 5.** Total pops fell
  from 53-56 per minute to 9-20 ([RLG-041](../fragments/RLG-041.md)).
- Not kept: fading small sprites at a crest instead of clipping them. The reasoning was sound - at
  25,000 units a car is six pixels tall and the crest line legitimately moves several pixels a frame
  - but it **did not move any measured number**, so it was removed rather than shipped beside the
  fix that works ([RLG-041](../fragments/RLG-041.md)).

<a id="v0-9-20"></a>
## [0.9.20] - 2026-08-29
- Fixed: **cars flickered in a valley below you**, reported from the device on v0.9.19 once the brow
  flicker was gone. Three faults in the near end of the crest table, found by recording the
  *distance* of every step over ten pixels: 618 of 632 were within 4,000 units of the player
  ([RLG-041](../fragments/RLG-041.md)).
- Fixed: **the crest table started at `pos`, and the camera is `PLAYER_Z` ahead of it.** Its first
  five entries projected points *behind the camera*, where a sample flickering between refused and
  accepted poisons the running minimum for everything after it. The `n < 2` guard in `crestAt` was a
  patch over exactly that and is gone ([RLG-041](../fragments/RLG-041.md)).
- Fixed: **"no crest yet" was written as `H`, a screen coordinate.** Harmless while entries were read
  whole; not harmless once v0.9.17 interpolated between them, where a blend from `H` to a real road
  height is a brow sweeping the whole screen in one segment. The sentinel is `Infinity` now
  ([RLG-041](../fragments/RLG-041.md)).
- Fixed: **the cull was a cliff four pixels wide.** A car under the brow draws nothing through the
  clip anyway, so culling it is an optimisation, not a decision - and its threshold sat one sliver
  from visible. It is `H*0.05` now, so the flip happens where the car is already clipped away
  ([RLG-041](../fragments/RLG-041.md)).
- Measured: **flickers per minute 8-24 → 0.0, 0.0, 1.3, 0.0** across four runs, and the surviving
  silhouette steps are confined to the first two segments past the camera
  ([RLG-041](../fragments/RLG-041.md)).

<a id="v0-9-19"></a>
## [0.9.19] - 2026-08-29
- Fixed: **cars appeared at the draw edge instead of arriving.** A sprite in the last sixth of the
  drawn road fades in now. Measured: a car at the edge is **6.7 px wide on a 480 px screen**, not
  the one pixel the record twice claimed - that figure had been inferred from the painter refusing
  sprites under 1.2 px, which is where a sprite stops being drawn rather than where one arrives. It
  reaches full opacity by 25,200 units, so a car comes in over about 4,800
  ([RLG-061](../fragments/RLG-061.md)).
- Still open: **how far the road should be drawn.** The fade changes the basis for deciding it - the
  draw distance can now be judged on how far you can see rather than on how badly things arrive
  ([RLG-061](../fragments/RLG-061.md)).

<a id="v0-9-18"></a>
## [0.9.18] - 2026-08-29
- Fixed: **looping sounds never came back after the app was backgrounded**, reported from the
  device. Four seconds hidden closes the audio context on purpose - a suspended iOS session can wake
  after a force-quit - and every held voice dies with it, while one-shots keep working because they
  build fresh nodes each time. The rebuild path existed and **could never run**: it lived in the
  watchdog's `closed` branch, and teardown clears the watchdog and nulls the context the branch
  tests. `A.audio.init()` fires the rebuild itself now, for every engine after the first
  ([RLG-065](../fragments/RLG-065.md)).
- Fixed: **Hardpoint never subscribed to the rebuild at all.** Quietus and `road.js` did; Hardpoint's
  four held layers could not come back even once the shell started asking
  ([RLG-065](../fragments/RLG-065.md)).
- Added: `audio-test` backgrounds the app and asks **which context a held layer belongs to**. Two
  weaker checks were written first and both were worthless - counting rebuild calls read zero on a
  fixed build, and reading the layer's gain read a healthy 0.13 on a broken one, because a GainNode
  on a closed context reports its value quite happily ([RLG-065](../fragments/RLG-065.md)).

<a id="v0-9-17"></a>
## [0.9.17] - 2026-08-29
- Fixed: **cars still popped at the brow of a hill**, reported from the device after v0.9.13. Two
  more faults in the same silhouette. The crest table holds one value per road segment and was read
  as a **staircase** - the brow did not move while a car crossed a segment, then jumped when it left
  one. It is interpolated now; the table is a running minimum, so a straight blend between entries
  *is* the silhouette ([RLG-041](../fragments/RLG-041.md)).
- Fixed: **the crest table was pinned to the segment behind the player.** It walked
  `(base + n) * SEG`, so every entry shifted by one whenever the player crossed a boundary, and the
  segment just passed - at a crest, the highest point on the road - left the running minimum in one
  step. It walks `pos + n * SEG` now and slides with the camera
  ([RLG-041](../fragments/RLG-041.md)).
- Measured: the largest single jump in the silhouette fell from **355 px to 80 px** on a 900 px
  screen, and the median move from 0.60 px to 0.40 px. Flicker rates moved too, but two runs apiece
  cannot separate that from the road being different, so **no claim is made on them**
  ([RLG-041](../fragments/RLG-041.md), [RLG-062](../fragments/RLG-062.md)).
- Removed: the skew counter that compared the two crest-index conventions. They agree by
  construction now, and a check that can only read zero is not a check
  ([RLG-041](../fragments/RLG-041.md)).

<a id="v0-9-16"></a>
## [0.9.16] — 2026-08-29
- Fixed: **nothing came up behind you when you stopped**, reported from the device. Traffic was
  culled only once it had fallen 34,000 units *behind*, so anything quicker than the player drove
  away and stayed in the array forever. Measured at a standstill: the array pinned at **30 cars, all
  ahead, and within fifteen seconds all thirty were past the draw distance** — an empty road with
  thirty invisible cars on it. `spawnBehind` is gated on `traffic.length < 26` and so could never
  fire. Cars are now culled past `pos + 64000`, beyond the furthest road the run has built
  ([RLG-064](../fragments/RLG-064.md)).
- Added: `traffic-test` tags every car present when you stop and asserts that an **untagged** one
  arrives behind you. A car that was already there proves nothing
  ([RLG-064](../fragments/RLG-064.md)).

<a id="v0-9-15"></a>
## [0.9.15] — 2026-08-29
- Added: **the arcade says which build it is running.** A BUILD row in the launcher's SETTINGS
  sheet, directly above FORCE UPDATE — the two are the same question — and a build line in every
  `.ark-opts` panel, printed even when a machine has no options. The identifier is
  `Arcade.version`, the same string every commit names, so there is no second number to maintain
  ([RLG-063](../fragments/RLG-063.md)).
- Added: **a MIXED warning.** `sw.js` serves scripts network-first with a cache fallback, so a slow
  connection can hand a device a fresh `arcade.js` beside a cached `road.js`. The engine stamps
  `window.ROAD_BUILD`, and the tag reads `BUILD 0.9.15 / ROAD 0.9.14 - MIXED` in orange when the two
  disagree ([RLG-063](../fragments/RLG-063.md)).

<a id="v0-9-14"></a>
## [0.9.14] — 2026-08-29
- Changed: `occlusion-test` drives **three shorter stints on three fresh roads** and sums them,
  instead of one stint on one road. The terrain is generated per load, so its numbers swung
  `culled` 0 → 40 → 147 on a single unchanged build and one of those runs failed its own
  `drawn > 200` assertion. The per-stint figures are printed and the report says plainly that one
  run cannot be compared with another ([RLG-062](../fragments/RLG-062.md)).
- **No product file changed in this version.** It is a harness fix, found by quoting that harness
  wrongly in v0.9.12 ([RLG-041](../fragments/RLG-041.md)).

<a id="v0-9-13"></a>
## [0.9.13] — 2026-08-29
- Fixed: **cars flickered at the lip of a crest**, reported from the device after v0.9.12.
  `buildHillClip` fills its table by absolute segment; `crestY` looked it up by *segments ahead of
  the player*, which is one lower whenever the car sits earlier in its segment than the player does
  — and which of the two it is flips **every time the road crosses a segment boundary, ~57 times a
  second at speed**. On flat road the two entries agree; at a crest they differ sharply, so a car
  near the brow flipped between hidden and drawn. Measured: the two conventions disagreed on 24
  vehicle-frames in 45 seconds, twice over, and only ever on cars at a crest
  ([RLG-041](../fragments/RLG-041.md)).
- Measured after: flickers 14.7 and 1.3 per minute, **all of them at the draw edge**, none mid-road
  ([RLG-041](../fragments/RLG-041.md)).
- Corrected: v0.9.12 cited `occlusion-test` going from `culled 0` to `culled 167` as proof. **That
  is withdrawn** — three runs on one unchanged build gave 0, 40 and 147. The terrain is generated
  fresh each run and that figure measures how hilly the road happened to be. The change stands on
  its own reasoning and on the sub-pixel measurement; the occlusion numbers were not evidence for it
  ([RLG-041](../fragments/RLG-041.md)).

<a id="v0-9-12"></a>
## [0.9.12] — 2026-08-28
- Fixed: **cars winked out for three or four frames at mid-distance.** The engine had two occlusion
  tests for terrain: `crestY`, a real silhouette built from the hill clip every frame, and a coarse
  one that dropped a whole sprite bucket whenever its road slice was skipped. Measured, every
  flickering car sat on a slice that missed being painted by a **median of under one pixel** — a
  crest tangent, not a hill. The bucket is always emitted now and `crestY` is the only thing that
  hides a car behind terrain ([RLG-041](../fragments/RLG-041.md)).
- Changed: `occlusion-test` now reports **culled 0 → 167, clipped 14 → 160**. Cars fully behind a
  crest were being lost by the bucket gate before the real test ever saw them, which is why the
  engine reported zero culls while occlusion visibly worked
  ([RLG-041](../fragments/RLG-041.md)).
- Measured: flickers fell from 16–28 per minute to 8–12, and every survivor is at the draw-distance
  edge rather than on the road. Zero cull faults, before and after
  ([RLG-041](../fragments/RLG-041.md)).
- Known: the second mechanism is characterized and not fixed — the sprite bucket range runs to
  `DRAW+1` and the road pass walks to `DRAW`, so a car at ~30,000 units flickers for a median of one
  frame at about a pixel wide. Changing anything at the draw edge risks a worse pop-in
  ([RLG-041](../fragments/RLG-041.md)).

<a id="v0-9-11"></a>
## [0.9.11] — 2026-08-28
- Added: **the engine can say why a vehicle was not drawn.** A ledger behind `API.watchDraw()`
  records the painter's own exit for every vehicle offered to it — `drawn`, `clipped`, `crest`,
  `offscreen`, `behind`, `tiny`, `huge`, `unbucketed`, `unemitted`, `nosprite`. Off in the product,
  where it costs one boolean test per sprite ([RLG-041](../fragments/RLG-041.md)).
- Added: `tools/pop-test.py` — the measurement RLG-041 asks for before any fix. It answers the
  ruling's question: **every disappearance was an object still in `traffic` or `racers` that the
  painter declined to paint. Zero cull faults in four runs.** Two mechanisms account for the
  flickers — a bucket alternating between emitted and not at ~11,000 units, and the draw-distance
  edge at ~30,300 ([RLG-041](../fragments/RLG-041.md)).
- Known: the run is a headless desktop browser at 480x900 and the owner's report is from a phone.
  **A clean run here is not evidence the reported fault is absent**
  ([RLG-041](../fragments/RLG-041.md)).

<a id="v0-9-10"></a>
## [0.9.10] — 2026-08-28
- Fixed: **traffic that gave way was never given back.** `keepLaneOpen` leans the car furthest ahead
  toward the verge to hold a corridor open and set a flag that **nothing ever cleared** — so a car
  that once made room was slowed for life, barred from merging again, and left standing between two
  lanes. It was 42–46% of every lateral move on the road, and it is what the owner reported as a car
  merging a fraction of a lane. Giving way is a timed state now: it ends, the car pulls fully into
  the nearest lane, and it recovers its cruising speed. Cars at rest between two lanes fell from
  **7.8% to 1.3%** of at-rest samples ([RLG-040](../fragments/RLG-040.md)).
- Fixed: a merge aimed at `c.x + 0.50` clamped to `0.86`, which from the outermost lane is a fifth of
  a lane onto the verge. It targets a **lane index**, one lane at a time, from the lane the car is in
  ([RLG-040](../fragments/RLG-040.md)).
- Changed: **every lateral number in the engine is now in lane widths** — merge rate, arrival,
  idle drift, spawn jitter, and the verge a yielding car leans onto. `LANE_W` sits beside `LANE_X`,
  shared by traffic and rivals, so full merging survives the road getting wider
  ([RLG-040](../fragments/RLG-040.md), [RLG-024](../fragments/RLG-024.md)).
- Changed: `cruiseFloor` was set on rogue cars every frame and read by nothing. It is the pace a car
  returns to after it has been made to slow down, which is the job it was created for
  ([RLG-040](../fragments/RLG-040.md)).
- Added: `tools/merge-test.py` — does traffic change a whole lane? It reads lateral position over
  time and no engine state, so a merge that is recorded and never carried out cannot pass it. Run
  against the engine as it was, it fails ([RLG-040](../fragments/RLG-040.md)).
- Known: the Interstate is slower for the player, because the lanes are genuinely fuller now —
  `drive-test` peak speed over eight runs 126–182mph (mean 156) against 150–188 (mean 175) before.
  **The threshold was not lowered** ([RLG-056](../fragments/RLG-056.md)).

<a id="v0-9-9"></a>
## [0.9.9] — 2026-08-28
- Fixed: **rivals never finished an overtake.** Steering was a per-frame lateral pressure that lasted
  only while something was in front, then pulled the car back to a lane index nothing ever updated —
  so a rival leaned out, unblocked its own scan, and drifted home. A lane change is a decision now:
  pick a target, commit, arrive, one lane at a time. Measured, time off a lane centre fell from
  **59–61% to 10–11%** with overtakes unchanged at ~30/min ([RLG-033](../fragments/RLG-033.md)).
- Fixed: **rivals could not see the player.** They scanned traffic, each other and the police and
  were blind to the one car you are sitting in — the same omission that once let them drive through
  you ([RLG-033](../fragments/RLG-033.md)).
- Changed: roadblocks are aimed at by **lane** rather than by coordinate, and every lane figure is in
  lane widths, so full merging survives the road getting wider
  ([RLG-040](../fragments/RLG-040.md), [RLG-024](../fragments/RLG-024.md)).
- Fixed: `drive-test`'s autopilot was blind to racers and drove into them once the rivals stopped
  wandering — 91% damage and a 127mph peak, which read as the engine failing
  ([RLG-033](../fragments/RLG-033.md)).
- Known: `speed rises above 150mph` now fails about one run in four at 146–148mph, because the road
  is genuinely busier. **The threshold was deliberately not lowered**
  ([RLG-056](../fragments/RLG-056.md)).

<a id="v0-9-8"></a>
## [0.9.8] — 2026-08-28
- Fixed: **every AI car accelerated through the PLAYER's gearbox.** `aiGearFactor` read `gearTable()`
  and `redline()`, both scoped to `optBody`, so the same rival recovered in 3.82s with the player in
  a four-speed and 4.75s in a six-speed — a 24% swing caused by a car it never met. Rivals and police
  now use their own gearbox, redline and top speed. Measured after: **−0.4%**
  ([RLG-042](../fragments/RLG-042.md)).
- Fixed: **`r.pull` was assigned to every rival and never read.** AI acceleration was a flat `2850`
  with no torque term, against the player's `1000 × gearFactor × pull`. Both now use the same
  expression ([RLG-042](../fragments/RLG-042.md)).
- Changed: **rivals accelerate about 3.5× less hard than they did**, because they had been pulling
  that much harder than any car the player can buy. Recovery from 40% to 90% of pace: 3.82s → 13.5s.
  The rubber band weakens with it — the governor from −7.80% to −3.21%, and a towed rival no longer
  reaches the raised ceiling. **Awaiting the owner's ruling** on whether `pull` is raised in the
  fleet table ([RLG-055](../fragments/RLG-055.md)).
- Changed: gear tables are cached by gear count rather than rebuilt per call — eleven rivals a frame
  made the old allocation matter ([RLG-042](../fragments/RLG-042.md)).

<a id="v0-9-7"></a>
## [0.9.7] — 2026-08-28
- Added: **a TIME control in the garage** — DUSK, MIDNIGHT, DAWN, MIDDAY. It sets where the day
  cycle *starts*; the four minutes then run on as before, so dusk still becomes night. The four are
  the four phase points the cycle already named, so no new lighting was written
  ([RLG-051](../fragments/RLG-051.md)).
- Changed: **a run no longer inherits the sky from the last one.** `dayClock` was deliberately never
  reset so the light carried across runs. A setting the player picks that the game then ignores is
  not a setting, so the choice now wins ([RLG-051](../fragments/RLG-051.md)).
- Added: `API.phase()` on the fork seam, beside `wet`, `snowy`, `settle` and `biome` — and the only
  way to test the TIME control by its effect rather than by its label
  ([RLG-051](../fragments/RLG-051.md)).
- Added: `drive-test` asserts that the run starts at the time the garage was set to. With the
  feature disabled the label check still passed and this one failed, which is why it exists
  ([RLG-051](../fragments/RLG-051.md)).

<a id="v0-9-6"></a>
## [0.9.6] — 2026-08-28
- Changed: **the police cars are won in the tournament now, under pursuit.** A gold in a sports car
  with HOT PURSUIT on also unlocks the CRUISER; a gold in a supercar unlocks the SUPERCRUISER. The
  old TEST DRIVE triggers — 20 miles on the clock, and the same 20 at a 180mph average — are removed
  completely rather than kept alongside ([RLG-049](../fragments/RLG-049.md)).
- Fixed: **the trophy screen announced "FORMULA UNLOCKED" for every gold**, and its button offered a
  FORMULA, even for a sports gold that actually pays the iridescent paint. The prize is computed
  from the class now, and a gold with pursuit off is told what it missed
  ([RLG-049](../fragments/RLG-049.md)).
- Fixed: the CRUISER's unlock card still described the TEST DRIVE trigger that no longer exists, and
  the SUPERCRUISER's card described nothing at all ([RLG-049](../fragments/RLG-049.md)).
- Known: **the new unlock branch is not executed by any harness.** A tournament is four races of 10,
  12, 16 and 24 miles with no debug route to a finish, so this shipped on a static parse plus the
  standing regression suite. A debug jump to a tournament finish is tracked
  ([RLG-050](../fragments/RLG-050.md)).

<a id="v0-9-5"></a>
## [0.9.5] — 2026-08-28
- Fixed: **the rubber band's tow did nothing at all.** A rival held two miles behind ran 179.0mph
  with the band and 178.7mph without it. `want` was multiplied by the band and capped at `AI_TOP` on
  the very next line, and every rival's base pace already exceeds that cap, so the tow was discarded
  before it could take effect. The ceiling now rises with the tow and only with the tow: measured
  **+13.21%** of a claimed 14%, with the governor unchanged at −7.80%
  ([RLG-038](../fragments/RLG-038.md)).
- Changed: a rival at full tow may now reach 205mph, above the player's 200. It only saturates past
  1.27 miles of separation, which is off the back of the screen, so the player stays the quickest
  thing they can see ([RLG-038](../fragments/RLG-038.md)).
- Added: `tools/band-test.py`, which measures the band against a band-off control arm served from
  memory, pins each rival to a fixed gap, and seeds `Math.random` so both arms race the same grid.
  It found the fault and then proved the fix ([RLG-029](../fragments/RLG-029.md)).
- Known: the other four harnesses cannot be run as step evidence. On Windows `CreateProcess`
  resolves a relative executable against the calling process's directory, so nothing can reach the
  project `.venv` from the environment root. `band-test.py` finds its own interpreter; the rest do
  not ([RLG-039](../fragments/RLG-039.md)).

<a id="v0-9-4"></a>
## [0.9.4] — 2026-08-25
- Fixed: **things spawned inside the drawn road.** Traps and cruisers were placed as close as 26,000
  into a 30,000 draw, so they appeared out of nothing in front of the player — which is what a
  rendering pop looks like. Every spawner measures from the draw distance now; nearest spawn 35,000
  ([RLG-031](../fragments/RLG-031.md)).
- Changed: a merge is judged by every corridor window that will later judge it, not just the one
  centred on it — measurably better, **not yet a guarantee**
  ([RLG-037](../fragments/RLG-037.md)).
- Changed: `traffic-test` reports the horn's effect rather than asserting it. Whether a car is in
  front of you is stochastic, and a check that fails one run in three teaches people to ignore it
  ([RLG-035](../fragments/RLG-035.md)).

<a id="v0-9-3"></a>
## [0.9.3] — 2026-08-25
- Fixed: **the horn and siren had no effect on traffic**, from three separate faults — a lane INDEX
  compared against a road position, a car that agreed to move only having its lane LABEL changed, and
  a search that started at the camera rather than the car. The sound itself was always working
  ([RLG-035](../fragments/RLG-035.md)).
- Changed: **no horn and no siren on the circuit, control included.** A closed track has neither
  traffic nor police, and a button that is present but does nothing costs the player a lap of
  wondering what they are missing ([RLG-035](../fragments/RLG-035.md)).
- Known: scatter and the lane-open guarantee pull against each other; the corridor measurement varies
  between runs and goes under the limit in some ([RLG-037](../fragments/RLG-037.md)).

<a id="v0-9-2"></a>
## [0.9.2] — 2026-08-25
- Fixed: **the revs could pass the limiter, from three separate causes.** The slipstream scaled the
  GEAR ceiling as well as the aero one; `gearRpm` clamped to `redline() + 300`; and the engine note
  was computed against a slip-reduced divisor, so a tow raised the PITCH while the revs sat pinned
  ([RLG-034](../fragments/RLG-034.md)).
- Changed: a tow now quiets and dulls the **wind** — which was the original intent — and leaves the
  engine note alone ([RLG-034](../fragments/RLG-034.md)).
- Added: a limiter check in `drive-test.py` that puts the car ON the ceiling rather than driving
  toward it; three earlier versions passed with the bug present
  ([RLG-034](../fragments/RLG-034.md)).

<a id="v0-9-1"></a>
## [0.9.1] — 2026-08-25
- Fixed: **slowing down on the Motorsport circuit conjured civilian traffic behind you.**
  `CFG.circuitOnly` gates four of the five spawners; the fifth lives with the speed logic rather than
  with the others and was outside it ([RLG-036](../fragments/RLG-036.md)).
- Added: `tools/circuit-test.py` — no existing harness could catch this, because `drive-test` holds
  the throttle down and this only happens when you stop
  ([RLG-036](../fragments/RLG-036.md)).

<a id="v0-9-0"></a>
## [0.9.0] — 2026-08-25
- Added: **traffic goes round slower cars.** Civilians could only ever slow for what was ahead of
  them, so the road silted up into rolling walls. They now decide, commit to and carry out a lane
  change — checking a lateral position rather than a lane index, refusing to pull out unless the
  other lane is actually faster, and never taking the last gap through
  ([RLG-032](../fragments/RLG-032.md)).
- Added: a car indicates for the beat before it moves across
  ([RLG-032](../fragments/RLG-032.md)).

<a id="v0-8-1"></a>
## [0.8.1] — 2026-08-25
- Fixed: **traffic could still pile up into a wall.** The guarantee counted lane indices rather than
  occupied width, and bucketed by `round(z/1500)` — so a wall straddling a bucket boundary looked
  passable from both sides. It measures the real corridor in a sliding window now, and starts opening
  the road before it closes rather than after ([RLG-025](../fragments/RLG-025.md)).
- Added: `tightestAhead` reports the narrowest corridor seen, and `tools/traffic-test.py` asserts it
  never goes under a car width — measured 0.452 against a 0.34 limit
  ([RLG-025](../fragments/RLG-025.md)).

<a id="v0-8-0"></a>
## [0.8.0] — 2026-08-25
- Fixed: **a car partly hidden by a crest vanished entirely.** The partial-clip path existed but was
  unreachable, and it clipped the wrong half — in this projection a crest covers a car from the
  bottom up, so the visible band is ABOVE the silhouette ([RLG-021](../fragments/RLG-021.md)).
- Added: `spriteStats` counts drawn, clipped and culled per frame; `ROAD()` publishes its API as
  `window.__road`; `tools/occlusion-test.py` proves cars are hidden rather than missing
  ([RLG-021](../fragments/RLG-021.md)).

<a id="v0-7-5"></a>
## [0.7.5] — 2026-08-25
- Fixed: **cars popped to a different texture in the rearview.** The mirror switched from a drawn
  block to a painted sprite at exactly 26px wide, and every car crossed that line in the same place
  on screen. The sprite fades in across a band now ([RLG-020](../fragments/RLG-020.md)).

<a id="v0-7-4"></a>
## [0.7.4] — 2026-08-25
- Fixed: **racers drove through the player.** They collided with traffic, cruisers, roadblocks and
  each other, and never once looked at the player. It is a rub rather than a wreck, scaled by closing
  speed ([RLG-019](../fragments/RLG-019.md)).

<a id="v0-7-3"></a>
## [0.7.3] — 2026-08-25
- Changed: **the damage smoke and fire are smaller.** At high damage the plume filled the middle of
  the frame and hid the traffic you were about to hit ([RLG-018](../fragments/RLG-018.md)).

<a id="v0-7-2"></a>
## [0.7.2] — 2026-08-25
- Fixed: **snow followed you into the desert.** The biome's odds were used to START weather and never
  to end it, so a front kept falling for the rest of its own timer wherever the road went — and
  settled snow took a minute and a half to fade ([RLG-017](../fragments/RLG-017.md)).

<a id="v0-7-1"></a>
## [0.7.1] — 2026-08-25
- Changed: **Interstate's verge costs speed, not health.** The barrier took 9 health on a repeating
  cooldown, so sliding along a wall was as expensive as hitting a truck. It scrubs speed
  continuously instead ([RLG-016](../fragments/RLG-016.md)).

<a id="v0-7-0"></a>
## [0.7.0] — 2026-08-25
- Added: **Hardpoint's full sound pass.** Four held layers that follow the ship every frame — engine
  (pitch on speed, level on throttle), afterburn, hull air, and separate alarms for heat and hull.
  Every sound before this was a one-shot, so the ship had no engine
  ([RLG-015](../fragments/RLG-015.md)).
- Added: **the engine mechanic is audible.** Engines dark spins the engine down to silence and leaves
  the air louder than it was under power — measured 0.128 to 0.002, air 0.035 to 0.055
  ([RLG-015](../fragments/RLG-015.md)).
- Added: a three-tier bed — bridge, hunted (a heartbeat on the off-beat), and boarding — plus its own
  slower bed on the title ([RLG-015](../fragments/RLG-015.md)).
- Added: nine events that were silent — the hunter arriving, losing him, the hull breach, being
  repelled, dying, the relight, the airlock, and footsteps paced by distance walked
  ([RLG-015](../fragments/RLG-015.md)).
- Added: `tools/audio-test.py`, which reads the Web Audio graph because a sound test cannot listen
  ([RLG-015](../fragments/RLG-015.md)).

<a id="v0-6-0"></a>
## [0.6.0] — 2026-08-25
- Removed: **every controls screen.** These are touch games, and a page listing gestures describes
  what the interface already shows one tap away ([RLG-014](../fragments/RLG-014.md)).
- Changed: Quietus's emergency light is **bolted over the hatch and pulses** instead of swinging
  across the frame. Nothing else in that room moves, so a drifting light read as a floating
  rectangle. It is drawn as a fitting now — housing, lens, wire guard, brackets and a throw on the
  plating ([RLG-014](../fragments/RLG-014.md)).
- Added: `tools/menu-test.py`, which asserts every title has the same set and that OPTIONS returns
  to it ([RLG-014](../fragments/RLG-014.md)).

<a id="v0-5-1"></a>
## [0.5.1] — 2026-08-25
- Fixed: **Quietus drew its title as `IET`.** Its hand-painted blood alphabet was authored for
  DERELICT and had no Q, U or S, and an unknown character draws nothing and reports nothing. The
  three letters are drawn ([RLG-013](../fragments/RLG-013.md)).
- Added: `Arcade.wordmark` reports a missing glyph on the console, once per word, naming the
  characters — and `smoke-test.py` now fails a cabinet on console errors, so a machine that quietly
  fails to draw its own name is a failing gate ([RLG-013](../fragments/RLG-013.md)).

<a id="v0-5-0"></a>
## [0.5.0] — 2026-08-25
- Added: **Hardpoint's title is an animated chase** — two ships, the hunter firing on the runner,
  lit thrusters, three parallax star layers, a sun off frame and a planet turning under it. Drawn
  every frame, nothing downloaded ([RLG-012](../fragments/RLG-012.md)).
- Changed: the veil turns to glass while the title is up, so the scene is visible rather than painted
  and covered ([RLG-012](../fragments/RLG-012.md)).
- Added: `tools/scene-test.py`, which asserts the scene paints, runs on the title, and **stops** when
  another screen takes over ([RLG-012](../fragments/RLG-012.md)).

<a id="v0-4-1"></a>
## [0.4.1] — 2026-08-25
- Changed: the driving wordmark is a **marque lockup** — REDLINE small above, INTERSTATE or
  MOTORSPORT large beneath. Set as one line it read as a single long name and shrank the half that
  actually names the game ([RLG-011](../fragments/RLG-011.md)).
- Changed: **HARDPOINT is cut from hull plate** — brushed steel, panel seams with rivets, scuffs, a
  rim light and a warm engine bounce, clipped to the letters so the material runs across the whole
  word ([RLG-011](../fragments/RLG-011.md)).

<a id="v0-4-0"></a>
## [0.4.0] — 2026-08-25
- Changed: **every machine owns everything it stores.** The shell's options, the audio settings and
  the record of seen intros were shared between all four; they are now scoped per machine under
  `Arcade.scope`, read from a new `<meta name="arcade-id">` ([RLG-010](../fragments/RLG-010.md)).
- Fixed: the shell's options were keyed on a slug of the cabinet's **title**, so the rename orphaned
  them — and that shape was invisible to `Arcade.save.clear`, **so erasing a machine had been
  leaving its settings behind while reporting success** ([RLG-010](../fragments/RLG-010.md)).
- Added: the launcher seeds a cabinet's audio settings once, on first visit, and the cabinet writes
  them down and owns them from then on ([RLG-010](../fragments/RLG-010.md)).
- Added: `tools/isolation-test.py`, and the `saves()` check now covers all six stores
  ([RLG-010](../fragments/RLG-010.md)).

<a id="v0-3-1"></a>
## [0.3.1] — 2026-08-25
- Added: **Hardpoint has a proper title** — a drawn wordmark, the career read back as STANDING,
  CREDITS and BEST RUN, and a first button that says `BEGIN` or `CONTINUE` rather than a `PLAY` that
  opened a station screen ([RLG-009](../fragments/RLG-009.md)).
- Fixed: Hardpoint's QUIT hardcoded `../../index.html#em`, naming a shelf that no longer exists. It
  uses `Arcade.home()` like every other machine ([RLG-009](../fragments/RLG-009.md)).

<a id="v0-3-0"></a>
## [0.3.0] — 2026-08-25
- Added: **every machine can erase its own save from its own options**, behind a two-press confirm.
  The label reads `NO SAVED DATA` when there is nothing to erase
  ([RLG-008](../fragments/RLG-008.md)).
- Fixed: `road.js` hardcoded `HIGHWAY` on its Options and Debug screens — and it serves both driving
  games, so Motorsport had been showing the other game's name above its own options
  ([RLG-008](../fragments/RLG-008.md)).
- Added: `smoke-test.py` now drives the erase path on every machine — arm, confirm, and check the
  store after the reload ([RLG-008](../fragments/RLG-008.md)).

<a id="v0-2-1"></a>
## [0.2.1] — 2026-08-25
- Fixed: **erasing a machine did not erase it.** `Arcade.save.clear` removed the save slot only, so
  options, a machine's own stored keys, and the record of which intros it had shown all survived —
  and the call reported success. The launcher's ERASE left even more behind
  ([RLG-007](../fragments/RLG-007.md)).
- Added: `Arcade.save.has(id)` and `Arcade.save.clearAll()`, and a namespace rule in the shell that
  says what belongs to a machine ([RLG-007](../fragments/RLG-007.md)).
- Added: a `saves` check in `smoke-test.py`, run against the old implementation first to prove it
  is not vacuous ([RLG-007](../fragments/RLG-007.md)).

<a id="v0-2-0"></a>
## [0.2.0] — 2026-08-25
- Changed: **the four machines are renamed**, in one unit — Derelict to **Quietus**, Privateer to
  **Hardpoint**, Highway to **Redline Interstate**, Raceway to **Redline Motorsport**. Ids, file
  paths, the catalogue, the engine's default, the drive harness and the save keys all moved together
  ([RLG-006](../fragments/RLG-006.md)).
- Changed: the cache generation is v26. Every cabinet filename changed, so a worker holding the old
  list would ask the server for four files that no longer exist
  ([RLG-006](../fragments/RLG-006.md)).
- Removed: the `#em` / `#sw` shelf hash from each cabinet's `arcade-home`, which addressed a picker
  that no longer exists ([RLG-006](../fragments/RLG-006.md)).

<a id="v0-1-2"></a>
## [0.1.2] — 2026-08-25
- Added: the icon is built from the **Effigy Media symbol** in the arcade's palette, pixelated, and
  generated by a committed script rather than being a binary nobody can regenerate. All six slats
  come from one thickness and one gap, so an uneven slat is not possible
  ([RLG-003](../fragments/RLG-003.md)).
- Fixed: **the loading counter reported files checked, not files fetched**, so it climbed to 18/18
  on every visit and a returning player saw what looked like a full download each time. Measured
  before the fix: cold 26 requests, warm reload 8 ([RLG-003](../fragments/RLG-003.md)).
- Fixed: `fonts/LICENSES.md` was precached — a document no running game asks for. The generator now
  takes `.woff2` only ([RLG-003](../fragments/RLG-003.md)).
- Changed: the cache generation is v25. `icon.png` is a core file, so without the bump every
  returning visitor would have kept serving the old icon out of cache
  ([RLG-003](../fragments/RLG-003.md)).
- Changed: the manifest `name` is `EFFIGY ARCADE`, so every install surface agrees with the
  `apple-mobile-web-app-title` that iOS pre-fills on Add to Home Screen
  ([RLG-003](../fragments/RLG-003.md)).

<a id="v0-1-1"></a>
## [0.1.1] — 2026-08-25
- Changed: **mobile only.** Touch is the input; keyboard, mouse and gamepad are out of scope. Owner
  ruling, recorded with what it makes redundant and what it does not delete
  ([RLG-002](../fragments/RLG-002.md)).
- Documented: a game leaves this arcade by one of two routes — a binary wrapper around the web
  build, or a conversion to Godot. Under the Godot route this codebase is the playable design
  document rather than the shipping artifact, so web-only plumbing is not worth investing in
  ([RLG-002](../fragments/RLG-002.md)).

<a id="v0-1-0"></a>
## [0.1.0] — 2026-08-25
- Added: **Effigy Arcade** — Derelict, Privateer, Highway and Raceway on one floor, forked from Tiny
  Arcade at v0.9.11 ([RLG-001](../fragments/RLG-001.md)).
- Changed: the launcher opens straight onto the rack. The three-shelf picker is gone; the shelf
  mechanism is kept whole behind a single shelf whose id `all` matches every cabinet, so a fifth
  machine or a real second shelf is one entry away ([RLG-001](../fragments/RLG-001.md)).
- Removed: fifteen machines, and the fourteen fonts that belonged only to them — 324KB off the
  offline precache ([RLG-001](../fragments/RLG-001.md)).
- Fixed: the `every .md is accounted for` gate tested a file called `*.md` in a folder with no root
  document, because an unmatched glob stays literal in bash. Latent in the parent, which always had
  six documents at its root ([RLG-001](../fragments/RLG-001.md)).
- Fixed: the archive step assumed `zip` is on PATH, so a build passed every gate and then died on
  its last line. It falls back to PowerShell's `Compress-Archive`
  ([RLG-001](../fragments/RLG-001.md)).
