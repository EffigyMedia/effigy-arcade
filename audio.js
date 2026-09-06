/* =====================================================================
   EFFIGY ARCADE — audio.js

   Every sound in this arcade is generated at runtime. No samples, no
   files, nothing to download. One shared engine so the mute settings
   follow you from the launcher into a game and back.

     <script src="../audio.js"></script>     (before arcade.js)

   Buses:  sfx  · music  · ui        each mutable independently
   Prefs persist in localStorage under 'effigyarcade.audio.v1'.

   Browsers will not make a sound until the user has touched something,
   so call Arcade.audio.init() from a real gesture handler.

   © 2026 Effigy Media. All rights reserved.
   ===================================================================== */
(function(){
"use strict";

var A = window.Arcade = window.Arcade || {};

/* ---- THE STORAGE SCOPE, AND EVERY PERSISTED THING HANGS OFF IT ------------
   These four machines are standalone games that share a launcher for the
   owner's convenience while they are built. Anything they share in storage is
   a thing that breaks, or silently goes missing, on the day one of them is
   split out. Audio preferences were shared: one mute switch, one set of levels,
   for all four. So was the shell's option store and the cinema's record of
   which intros had been seen.

   `Arcade.scope` is the answer, and it is defined HERE rather than in the shell
   because audio.js loads first and needs it immediately.

     <meta name="arcade-id" content="hardpoint">   the cabinet says who it is
     the file name                                 a standalone build renamed
     'launcher'                                    index.html, which is no game

   Every key becomes `effigyarcade.<scope>.<what>.v1`, which is exactly the
   shape `Arcade.save.clear` already treats as belonging to one machine - so
   erasing a game now takes its audio settings and its seen-intros with it,
   which it did not before.
   ------------------------------------------------------------------------ */
A.scope = (function(){
  function slug(v){ return String(v || '').toLowerCase().replace(/[^a-z0-9]+/g, ''); }
  try {
    var m = document.querySelector('meta[name="arcade-id"]');
    if (m && m.content) return slug(m.content);
    var f = slug((location.pathname.split('/').pop() || '').replace(/\.html?$/i, ''));
    return (!f || f === 'index') ? 'launcher' : f;
  } catch(e){ return 'launcher'; }
})();

var KEY = 'effigyarcade.' + A.scope + '.audio.v1';
var SEED_KEY = 'effigyarcade.launcher.audio.v1';

var ctx = null, master = null, sfxBus = null, musBus = null, uiBus = null;
/* ---- A REVERB PER BUS, NOT ONE FOR THE WHOLE ARCADE (RLG-078) -----------
   Owner, 2026-08-29: "if I was to mute the music, the reverb bus still plays
   so we want to make sure muting the music also mutes that bus."

   There was one convolver and its return went straight to `master`, so a voice
   was connected twice and only one of the two copies rode the mute: the dry
   went to its bus and the wet went round it. Muting the music silenced the
   music and left its tail ringing.

   ONE RETURN COULD NOT HAVE FIXED IT. Muting the single return when MUSIC is
   muted would take the sound effects' reverb with it, because one return
   carries both. The tail has to ride the same gain its dry copy rides, and
   that means a convolver per bus - each returning INTO its own bus rather than
   into master, so `applyGains` mutes the tail without having to know it exists.

   THEY ARE BUILT ON DEMAND. A convolution is not free and the arcade does not
   use reverb on every bus; a bus gets one the first time a voice sends to it,
   and buses that never do pay nothing.
   ----------------------------------------------------------------------- */
var verbs = {}, noiseBuf = null, hushed = false, outTap = null;
/* Leaving the page has to silence us. A backgrounded tab still runs its
   scheduler, throttled to about a tick a second, so the bed keeps playing —
   late, dragging and out of time — long after you think you have closed it.
   The game shell pauses itself, but the launcher has no shell, so this lives
   down here where every page gets it. */
var bgHidden = false;
function quiet(){ return hushed || bgHidden; }
var listeners = [], resetSubs = [];
/* How many audio engines this page has built. It matters because the SECOND one
   is not the same event as the first: a game builds its held voices itself when
   it starts, but after a teardown those voices belong to a context that no
   longer exists and nobody is going to ask for them again. See `rebuilt()`. */
var builds = 0;
var gestured = false;      // a context built before a real gesture starts
var pending = null;        // suspended and never recovers cleanly on iOS

/* sfx/music are the mute switches; the three levels are continuous 0..1.
   All five live in the same persisted record, so everything the player sets in
   the launcher is already in force inside a cabinet. */
var pref = { sfx:true, music:true, vMaster:1, vMusic:1, vSfx:1 };
var musicTrim = 1.00;
try {
  var raw = localStorage.getItem(KEY);
  /* ---- THE LAUNCHER SEEDS A CABINET THAT HAS NO SETTINGS OF ITS OWN -------
     Splitting the stores would otherwise cost a real convenience: turning the
     music down in the launcher and having a cabinet ignore you. A machine with
     nothing saved reads the launcher's settings ONCE, as its starting point,
     and owns them from then on. Independent, without being deaf. */
  var seeded = false;
  if (!raw && A.scope !== 'launcher'){
    try { raw = localStorage.getItem(SEED_KEY); seeded = !!raw; } catch(e){}
  }
  if (raw){
    var o = JSON.parse(raw);
    pref.sfx   = o.sfx   !== false;
    pref.music = o.music !== false;
    /* the levels have to be read back too, or they are written in the launcher
       and silently discarded on the way into a cabinet */
    ['vMaster','vMusic','vSfx'].forEach(function(k){
      if (typeof o[k] === 'number' && isFinite(o[k]))
        pref[k] = Math.max(0, Math.min(1, o[k]));
    });
  }
} catch(e){}

function save(){ try { localStorage.setItem(KEY, JSON.stringify(pref)); } catch(e){} }

/* WRITE THE SEED DOWN IMMEDIATELY, or the machine has not taken ownership of
   anything - it is just reading the launcher's settings on every load, and a
   later change in the launcher would move it again. Persisting on the first
   visit is what makes "its own settings" true rather than a description of
   what happens until somebody touches a slider. */
if (seeded) save();
function fire(){ for (var i=0;i<listeners.length;i++) try { listeners[i](pref); } catch(e){} }

/* a stored level, clamped, defaulting to full if it was never set */
function lvl(key){
  var v = pref[key];
  return (typeof v === 'number' && isFinite(v)) ? Math.max(0, Math.min(1, v)) : 1;
}

function applyGains(t){
  if (!ctx || !sfxBus) return;
  var now = ctx.currentTime, k = Math.max(0.004, (t === undefined ? 0.09 : t) / 3);
  sfxBus.gain.setTargetAtTime((pref.sfx   && !quiet()) ? 0.62 * lvl('vSfx') : 0, now, k);
  /* musicTrim lets a page sit its bed under the interface without touching the
     player's MUSIC toggle. Setting musBus.gain directly does not work — this
     runs on every change and puts it straight back. */
  musBus.gain.setTargetAtTime((pref.music && !quiet()) ? musicTrim * lvl('vMusic') : 0, now, k);
  uiBus.gain.setTargetAtTime(pref.sfx ? 0.55 * lvl('vSfx') : 0, now, 0.01);
  /* master rides everything, including the UI bus */
  if (master) master.gain.setTargetAtTime(lvl('vMaster'), now, k);
}

/* iOS will hand back a context that claims to be running but stays mute
   until something has actually been played inside the gesture itself. */
function unlockTap(){
  try {
    var b = ctx.createBuffer(1, 1, 22050);
    var src = ctx.createBufferSource();
    src.buffer = b;
    src.connect(ctx.destination);
    src.start(0);
  } catch(e){}
}

/* called whenever the context might have come alive */
function flush(){
  if (!ctx || ctx.state !== 'running') return;
  A.audio.ready = true;
  applyGains(0.05);
  if (pending && !M.timer && M.on) runMusic(pending);
}

function buildVerb(){
  var len = Math.floor(ctx.sampleRate * 1.9);
  var buf = ctx.createBuffer(2, len, ctx.sampleRate);
  for (var c=0;c<2;c++){
    var d = buf.getChannelData(c);
    for (var i=0;i<len;i++){
      var x = i/len;
      d[i] = (Math.random()*2-1) * Math.pow(1-x, 3.1) * (1 - x*0.25);
    }
  }
  var cv = ctx.createConvolver(); cv.buffer = buf;
  return cv;
}

/* The reverb for one bus, built the first time something asks for it. The
   return lands on the BUS, which is the whole point: a tail rides the gain that
   mutes its own dry signal, and nothing else has to know a reverb is there. */
/* ---- ONE SEND THAT WASHES EVERY VOICE ON A BUS (RLG-105) ----------------
   Owner, 2026-09-01: "engine sounds, tyre screeching, and horns need to have a
   bunch of reverb while in a tunnel."

   A PER-VOICE `verb` COULD NOT DO IT. That send is fixed when the voice is
   built, so it can colour a horn that is about to sound and can do nothing at
   all about an ENGINE - a held voice, built once at the start of the run and
   driven for the whole of it. Driving into a tunnel has to change a sound that
   is already playing.

   So every voice also connects to a single send per bus whose gain starts at
   zero. Moving that one parameter moves the whole mix into a space, held voices
   included, and moving it back takes them out. The place ramps it; nothing else
   has to know.
   ------------------------------------------------------------------------- */
var spaceSends = {};
function spaceSendFor(which){
  var name = which === 'music' ? 'music' : which === 'ui' ? 'ui' : 'sfx';
  if (spaceSends[name]) return spaceSends[name];
  var s = ctx.createGain(); s.gain.value = 0;
  s.connect(verbFor(name));
  spaceSends[name] = s;
  return s;
}
function verbFor(which){
  var name = which === 'music' ? 'music' : which === 'ui' ? 'ui' : 'sfx';
  if (verbs[name]) return verbs[name].conv;
  var conv = buildVerb();
  var ret = ctx.createGain(); ret.gain.value = 0.85;
  conv.connect(ret); ret.connect(A.audio.bus(name));
  verbs[name] = { conv: conv, ret: ret };
  return conv;
}

/* ------------------------------------------------------------------ */
A.audio = {
  ready:false,
  /* ---- HOW MUCH SPACE THE SOUNDS ARE IN (RLG-105) ---------------------
     0 is the open road and 1 is a bore. It ramps rather than steps, because a
     mix that snaps into a reverb reads as a bug and because the tunnel's mouth
     is a ramp for the eye already. Only the sfx bus: music and the interface do
     not live in the world and should not follow the car into a tunnel. */
  space: function(v, secs){
    if (!ctx) return 0;
    var amt = Math.max(0, Math.min(1, v || 0));
    var s = spaceSendFor('sfx');
    s.gain.setTargetAtTime(amt, ctx.currentTime, Math.max(0.02, (secs === undefined ? 0.45 : secs)));
    return amt;
  },
  ctx:null,

  init: function(){
    /* Returns "there is an engine to talk to", NOT "it is making sound yet".
       iOS builds the context inside the gesture but resumes it a moment
       later, so demanding 'running' here made every caller bail out before
       queueing its music, and nothing ever queued it again. */
    if (ctx){
      if (ctx.state !== 'running' && gestured) ctx.resume().then(flush, function(){});
      return true;
    }
    /* ---- TRY ANYWAY -------------------------------------------------------
       This returned early without a gesture, so on a fresh page load the
       context was never even ATTEMPTED — and a game opened from the launcher is
       always a fresh page load, because the launcher navigates rather than
       swapping views. Music could not start until you touched something, and
       if that touch was PLAY you never heard the title at all.

       There is no way to force audio without permission, but there IS a case
       the old code threw away: a browser that has already granted autoplay for
       this origin — desktop, an installed PWA, or one with enough media
       engagement — will happily build a RUNNING context on load.

       So: build it optimistically. If it comes up running, the music starts by
       itself. If it comes up suspended, nothing is lost — `gestured` still
       gates the resume and the first tap flushes the queue exactly as before.
       ---------------------------------------------------------------------- */
    var C = window.AudioContext || window.webkitAudioContext;
    if (!C) return false;
    try { ctx = new C(); } catch(e){ return false; }

    master = ctx.createGain(); master.gain.value = 0.85; master.connect(ctx.destination);
    sfxBus = ctx.createGain(); sfxBus.connect(master);
    musBus = ctx.createGain(); musBus.connect(master);
    uiBus  = ctx.createGain(); uiBus.connect(master);

    /* the reverbs are built on demand, one per bus - see verbFor */
    verbs = {}; spaceSends = {};

    var n = Math.floor(ctx.sampleRate * 2);
    noiseBuf = ctx.createBuffer(1, n, ctx.sampleRate);
    var d = noiseBuf.getChannelData(0);
    for (var i=0;i<n;i++) d[i] = Math.random()*2-1;

    builds++;
    A.audio.ctx = ctx; A.audio.ready = true;
    applyGains(0);
    ctx.onstatechange = flush;
    unlockTap();
    /* a context that comes up running on its own means autoplay was allowed:
       treat that as the gesture, so queued music flushes immediately */
    if (ctx.state === 'running'){ gestured = true; flush(); }
    else ctx.resume().then(function(){ gestured = true; flush(); }, function(){});
    startWatchdog();
    /* ---- A REBUILT ENGINE HAS NO HELD VOICES -----------------------------
       Reported from the device: after the app has been in the background,
       looping sounds never come back while one-shots still work.

       Backgrounding for four seconds calls `teardown`, which CLOSES the context
       to release the hardware - deliberately, because a merely suspended iOS
       session can wake up after a force-quit. Everything the games are holding -
       the engine note, the wind, the siren, the horn - dies with it. A one-shot
       builds fresh nodes every time it plays, so those survive; a held voice is
       created once and never again, which is exactly the split the owner
       described.

       The watchdog DID have a rebuild path, and it could never run: `teardown`
       clears the watchdog's own interval, and the path is behind `if (!ctx)
       return` in any case. So the subscribers were only ever fired by a branch
       that was unreachable after the only thing that closes a context.

       Firing them here instead - on any engine after the first - puts the
       rebuild where the rebuild actually happens. The first build is left
       alone, because a game builds its own voices when it starts and firing
       them here as well would create two of everything.
       ------------------------------------------------------------------- */
    if (builds > 1) rebuilt();
    return true;
  },

  get: function(k){ return pref[k]; },
  set: function(k, v){ pref[k] = !!v; save(); applyGains(); flush(); fire(); },

  /* Continuous levels, 0..1, kept in the same persisted record as the mutes —
     so anything the player sets in the launcher is already in force inside a
     cabinet without either side knowing about the other.
        vMaster  rides everything, including the interface
        vMusic   the bed only
        vSfx     effects and the interface                                    */
  level: function(k){ return lvl(k); },
  setLevel: function(k, v){
    if (k !== 'vMaster' && k !== 'vMusic' && k !== 'vSfx') return;
    pref[k] = Math.max(0, Math.min(1, +v || 0));
    save(); applyGains(0.05); fire();
    return pref[k];
  },
  toggle: function(k){ A.audio.set(k, !pref[k]); },
  allOn:  function(){ pref.sfx = true;  pref.music = true;  save(); applyGains(); flush(); fire(); },
  allOff: function(){ pref.sfx = false; pref.music = false; save(); applyGains(); fire(); },
  anyOn:  function(){ return pref.sfx || pref.music; },
  onChange: function(fn){ listeners.push(fn); },

  /* If the OS throws the context away entirely — a long spell in the
     background — held voices like engines and drones die with it. Games
     register here to rebuild them. */
  onReset: function(fn){ resetSubs.push(fn); },

  /* silence everything without touching the user's preferences */
  hush: function(v){
    hushed = !!v;
    applyGains(0.16);
    if (hushed) A.music.pause(); else A.music.resume();
  },

  bus: function(which){
    return which === 'music' ? musBus : which === 'ui' ? uiBus : sfxBus;
  },
  /* ---- A TAP ON THE OUTPUT, FOR A CHECK THAT HAS TO HEAR (RLG-078) -----
     A check that reads a gain value off the Web Audio graph is not reading the
     graph, and this project has paid three attempts to learn it (RLG-065): a
     GainNode on a closed context reports a healthy value quite happily. A
     ROUTING fault is worse than that - it changes no gain anywhere, so there is
     no value to read that would be wrong.

     What settles a routing question is the signal. This hangs an analyser off
     `master` and hands it back, so a harness can mute a bus, play something on
     it, and measure whether anything came out. The analyser is a sink and does
     not connect onward, so it changes nothing about what is heard.
     ------------------------------------------------------------------- */
  tap: function(){
    if (!ctx || !master) return null;
    if (!outTap){ outTap = ctx.createAnalyser(); outTap.fftSize = 2048; master.connect(outTap); }
    return outTap;
  },
  /* which buses have a reverb built, for a report that says what was measured */
  verbBuses: function(){ var o = []; for (var k in verbs) o.push(k); return o.sort(); },
  now: function(){ return ctx ? ctx.currentTime : 0; }
};

/* ------------------------------------------------------------------
   voices
   ------------------------------------------------------------------ */
function env(g, t0, peak, attack, dur, hold){
  g.gain.setValueAtTime(0.0001, t0);
  g.gain.exponentialRampToValueAtTime(Math.max(0.0002, peak), t0 + attack);
  if (hold) g.gain.setValueAtTime(Math.max(0.0002, peak), t0 + attack + hold);
  g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
}

A.sfx = {
  /* a pitched blip, optionally sliding */
  tone: function(o){
    if (!ctx) return null;
    o = o || {};
    if (!ctx) return;
    var t0 = o.t || ctx.currentTime;
    var dur = o.dur || 0.18;
    var osc = ctx.createOscillator();
    osc.type = o.type || 'square';
    var f0 = o.freq || 440, f1 = o.to || f0;
    osc.frequency.setValueAtTime(f0, t0);
    if (f1 !== f0) osc.frequency.exponentialRampToValueAtTime(Math.max(1, f1), t0 + dur);
    if (o.detune) osc.detune.value = o.detune;

    var g = ctx.createGain();
    env(g, t0, o.gain === undefined ? 0.22 : o.gain, o.attack === undefined ? 0.006 : o.attack, dur, o.hold);

    var tail = osc;
    if (o.cutoff){
      var f = ctx.createBiquadFilter();
      f.type = o.filter || 'lowpass';
      f.frequency.setValueAtTime(o.cutoff, t0);
      if (o.cutoffTo) f.frequency.exponentialRampToValueAtTime(Math.max(30, o.cutoffTo), t0 + dur);
      if (o.q) f.Q.value = o.q;
      tail.connect(f); tail = f;
    }
    tail.connect(g);
    g.connect(A.audio.bus(o.bus || 'sfx'));
    if (o.verb){ var vs = ctx.createGain(); vs.gain.value = o.verb; g.connect(vs); vs.connect(verbFor(o.bus || 'sfx')); }
    /* and the space, for the voices that live in the world (RLG-105). Owner,
       2026-09-01: "Not on every sound effect, only the engines, the brakings,
       tire squeals, sirens, and horns." A crate chime and a menu blip are not
       in the tunnel with you, so a voice opts IN with `space:true` rather than
       everything being washed and a list of exceptions kept. */
    if (o.space) g.connect(spaceSendFor(o.bus || 'sfx'));
    osc.start(t0); osc.stop(t0 + dur + 0.06);
    return osc;
  },

  /* filtered noise: impacts, wind, hats, splashes */
  noise: function(o){
    if (!ctx) return null;
    o = o || {};
    if (!ctx) return;
    var t0 = o.t || ctx.currentTime;
    var dur = o.dur || 0.2;
    var src = ctx.createBufferSource();
    src.buffer = noiseBuf; src.loop = true;
    src.playbackRate.value = o.rate || 1;

    var f = ctx.createBiquadFilter();
    f.type = o.filter || 'bandpass';
    f.frequency.setValueAtTime(o.freq || 1200, t0);
    if (o.to) f.frequency.exponentialRampToValueAtTime(Math.max(30, o.to), t0 + dur);
    f.Q.value = o.q === undefined ? 1 : o.q;

    var g = ctx.createGain();
    env(g, t0, o.gain === undefined ? 0.2 : o.gain, o.attack === undefined ? 0.004 : o.attack, dur, o.hold);

    src.connect(f); f.connect(g);
    g.connect(A.audio.bus(o.bus || 'sfx'));
    if (o.verb){ var vs = ctx.createGain(); vs.gain.value = o.verb; g.connect(vs); vs.connect(verbFor(o.bus || 'sfx')); }
    /* and the space, for the voices that live in the world (RLG-105). Owner,
       2026-09-01: "Not on every sound effect, only the engines, the brakings,
       tire squeals, sirens, and horns." A crate chime and a menu blip are not
       in the tunnel with you, so a voice opts IN with `space:true` rather than
       everything being washed and a list of exceptions kept. */
    if (o.space) g.connect(spaceSendFor(o.bus || 'sfx'));
    src.start(t0); src.stop(t0 + dur + 0.06);
    return src;
  },

  /* several tones at once */
  chord: function(freqs, o){
    o = o || {};
    for (var i=0;i<freqs.length;i++){
      var c = {}; for (var k in o) c[k] = o[k];
      c.freq = freqs[i];
      c.t = (o.t || (ctx ? ctx.currentTime : 0)) + (o.spread || 0) * i;
      A.sfx.tone(c);
    }
  },

  drum: function(kind, t, gain, bus){
    if (!ctx) return;
    if (!ctx) return;
    t = t || ctx.currentTime;
    gain = gain === undefined ? 0.5 : gain;
    bus = bus || 'music';
    if (kind === 'kick'){
      A.sfx.tone({ t:t, freq:150, to:44, dur:0.19, type:'sine', gain:gain, attack:0.004, bus:bus });
      A.sfx.noise({ t:t, freq:90, dur:0.04, gain:gain*0.35, filter:'lowpass', bus:bus });
    } else if (kind === 'snare'){
      A.sfx.noise({ t:t, freq:1800, to:900, dur:0.15, gain:gain*0.55, filter:'bandpass', q:0.8, bus:bus });
      A.sfx.tone({ t:t, freq:210, to:150, dur:0.1, type:'triangle', gain:gain*0.28, bus:bus });
    } else if (kind === 'hat'){
      A.sfx.noise({ t:t, freq:8200, dur:0.038, gain:gain*0.22, filter:'highpass', q:0.6, bus:bus });
    } else if (kind === 'open'){
      A.sfx.noise({ t:t, freq:7200, dur:0.20, gain:gain*0.16, filter:'highpass', q:0.6, bus:bus });
    } else if (kind === 'tom'){
      A.sfx.tone({ t:t, freq:190, to:90, dur:0.22, type:'sine', gain:gain*0.5, bus:bus });
    } else if (kind === 'clap'){
      for (var i=0;i<3;i++)
        A.sfx.noise({ t:t+i*0.012, freq:1500, dur:0.09, gain:gain*0.3, filter:'bandpass', q:1.4, bus:bus });
    }
  },

  /* a held voice you drive yourself — engines, sirens, drones */
  hold: function(o){
    if (!ctx) return null;
    o = o || {};
    var osc = ctx.createOscillator();
    osc.type = o.type || 'sawtooth';
    osc.frequency.value = o.freq || 110;
    if (o.detune) osc.detune.value = o.detune;
    var f = ctx.createBiquadFilter();
    f.type = o.filter || 'lowpass';
    f.frequency.value = o.cutoff || 900;
    f.Q.value = o.q === undefined ? 0.8 : o.q;
    var g = ctx.createGain(); g.gain.value = 0;
    /* Optional stereo placement. Anything that exists at a POSITION in the
       world — another car passing, a siren going by — needs to move across
       the ears, not just get louder. */
    var pan = null;
    if (o.pan !== undefined && ctx.createStereoPanner){
      pan = ctx.createStereoPanner();
      pan.pan.value = o.pan;
      osc.connect(f); f.connect(g); g.connect(pan);
      pan.connect(A.audio.bus(o.bus || 'sfx'));
    } else {
      osc.connect(f); f.connect(g); g.connect(A.audio.bus(o.bus || 'sfx'));
    }
    if (o.verb){ var vs = ctx.createGain(); vs.gain.value = o.verb; g.connect(vs); vs.connect(verbFor(o.bus || 'sfx')); }
    /* and the space, for the voices that live in the world (RLG-105). Owner,
       2026-09-01: "Not on every sound effect, only the engines, the brakings,
       tire squeals, sirens, and horns." A crate chime and a menu blip are not
       in the tunnel with you, so a voice opts IN with `space:true` rather than
       everything being washed and a list of exceptions kept. */
    if (o.space) g.connect(spaceSendFor(o.bus || 'sfx'));
    osc.start();
    return {
      osc:osc, filter:f, gain:g,
      set: function(freq, level, cutoff, glide){
        if (!ctx) return;
        var n = ctx.currentTime, k = glide || 0.05;
        if (freq !== undefined)   osc.frequency.setTargetAtTime(Math.max(8, freq), n, k);
        if (level !== undefined)  g.gain.setTargetAtTime(level, n, k);
        if (cutoff !== undefined) f.frequency.setTargetAtTime(Math.max(40, cutoff), n, k);
      },
      /* -1 hard left, 0 centre, +1 hard right */
      place: function(x, glide){
        if (!ctx || !pan) return;
        pan.pan.setTargetAtTime(Math.max(-1, Math.min(1, x)),
                                ctx.currentTime, glide || 0.06);
      },
      stop: function(){ if (!ctx) return; try { g.gain.setTargetAtTime(0, ctx.currentTime, 0.05); osc.stop(ctx.currentTime + 0.4); } catch(e){} }
    };
  },

  /* same idea but noise-based — wind, tyre roar, water */
  holdNoise: function(o){
    if (!ctx) return null;
    o = o || {};
    var src = ctx.createBufferSource();
    src.buffer = noiseBuf; src.loop = true;
    var f = ctx.createBiquadFilter();
    f.type = o.filter || 'bandpass';
    f.frequency.value = o.freq || 800;
    f.Q.value = o.q === undefined ? 0.7 : o.q;
    var g = ctx.createGain(); g.gain.value = 0;
    /* ---- A NOISE VOICE CAN BE PLACED TOO --------------------------------
       `hold` has had a stereo panner since sounds needed to exist at a
       POSITION in the world; `holdNoise` never did, so anything noise-based
       was always dead centre however far to the side it was happening. That
       was invisible while noise was only used for wind and tyre roar, which
       are not anywhere in particular - and it became a real gap the moment a
       nitrous hiss had to come from the car that was using it.

       Same option and same shape as `hold`: opt in with `pan`, and get a
       `place()` that moves it. A voice that does not ask for one is wired
       exactly as before. */
    var pan = null;
    if (o.pan !== undefined && ctx.createStereoPanner){
      pan = ctx.createStereoPanner();
      pan.pan.value = o.pan;
      src.connect(f); f.connect(g); g.connect(pan);
      pan.connect(A.audio.bus(o.bus || 'sfx'));
    } else {
      src.connect(f); f.connect(g); g.connect(A.audio.bus(o.bus || 'sfx'));
    }
    src.start();
    return {
      gain:g, filter:f,
      set: function(freq, level, glide){
        if (!ctx) return;
        var n = ctx.currentTime, k = glide || 0.08;
        if (freq !== undefined)  f.frequency.setTargetAtTime(Math.max(40, freq), n, k);
        if (level !== undefined) g.gain.setTargetAtTime(level, n, k);
      },
      /* -1 hard left, 0 centre, +1 hard right - the same contract `hold` has */
      place: function(x, glide){
        if (!ctx || !pan) return;
        pan.pan.setTargetAtTime(Math.max(-1, Math.min(1, x)),
                                ctx.currentTime, glide || 0.06);
      },
      stop: function(){ if (!ctx) return; try { g.gain.setTargetAtTime(0, ctx.currentTime, 0.05); src.stop(ctx.currentTime + 0.4); } catch(e){} }
    };
  }
};

/* small interface clicks, on their own bus so a paused game stays audible */
A.ui = {
  tick: function(){ A.sfx.tone({ freq:900, to:1300, dur:0.05, type:'square', gain:0.10, bus:'ui' }); },
  ok:   function(){ A.sfx.tone({ freq:660, to:990, dur:0.10, type:'square', gain:0.11, bus:'ui' }); },
  off:  function(){ A.sfx.tone({ freq:520, to:300, dur:0.10, type:'square', gain:0.11, bus:'ui' }); }
};

/* ------------------------------------------------------------------
   music: a lookahead step sequencer. A game hands over a tick(step, t)
   and schedules whatever it likes at the times it is given.
   ------------------------------------------------------------------ */
var M = { bpm:120, div:4, step:0, next:0, tickFn:null, timer:null, on:false, paused:false };

function runMusic(spec){
  if (M.timer){ clearInterval(M.timer); M.timer = null; }
  if (!ctx) return;
  M.bpm = spec.bpm; M.div = spec.div; M.tickFn = spec.tickFn;
  M.step = 0; M.next = ctx.currentTime + 0.05; M.on = true; M.paused = false;
  M.timer = setInterval(function(){
    if (!M.on || M.paused || !ctx || ctx.state !== 'running') return;
    var spb = 60 / M.bpm / M.div;
    /* if the clock jumped — tab restored, context resumed — do not try to
       replay the gap, just pick up from now */
    if (M.next < ctx.currentTime - 0.3) M.next = ctx.currentTime + 0.05;
    var horizon = ctx.currentTime + 0.14, guard = 0;
    while (M.next < horizon && guard++ < 32){
      try { M.tickFn(M.step, M.next); } catch(e){}
      M.step++; M.next += spb;
    }
  }, 25);
}

A.music = {
  /* 0..1, how loud this page's bed sits under its interface. Applied through
     applyGains, because setting musBus.gain directly does not survive — that
     function runs on every change and puts it straight back. */
  trim: function(v){
    musicTrim = Math.max(0, Math.min(1, v));
    applyGains(0.15);
    return musicTrim;
  },
  start: function(bpm, div, tickFn){
    pending = { bpm:bpm, div:div, tickFn:tickFn };
    M.on = true;
    /* Run it now even if the context is still waking. The tick loop skips
       scheduling while the clock is dead and resyncs the moment it starts,
       so the bed comes in within one 25ms tick instead of waiting for a
       watchdog sweep or a state-change event that may never fire. */
    if (ctx) runMusic(pending);
  },
  stop: function(){
    M.on = false; M.tickFn = null; pending = null;
    if (M.timer){ clearInterval(M.timer); M.timer = null; }
  },
  pause:  function(){ M.paused = true; },
  resume: function(){
    if (!M.on || !ctx) return;
    if (M.paused && ctx){ M.next = ctx.currentTime + 0.06; M.paused = false; }
  },
  playing: function(){ return M.on; },
  bpm: function(){ return M.bpm; }
};

/* a handful of note names so game code reads musically */
var NAMES = {C:0,'C#':1,D:2,'D#':3,E:4,F:5,'F#':6,G:7,'G#':8,A:9,'A#':10,B:11};
A.note = function(name, oct){
  var n = NAMES[name];
  if (n === undefined) return 440;
  return 440 * Math.pow(2, (n - 9) / 12 + ((oct === undefined ? 4 : oct) - 4));
};

/* Everything above assumes the browser behaves. This is the net underneath:
   twice a second, check that what should be audible actually is, and repair
   it. It fixes a stalled start without the player having to touch the mute
   toggle, which is the manual version of exactly this. */
var wdTimer = null, wdFast = 0;
/* tell every game to build its held voices again on the engine that exists now */
function rebuilt(){
  for (var i = 0; i < resetSubs.length; i++) try { resetSubs[i](); } catch(e){}
}

function startWatchdog(){
  if (wdTimer){ wdFast = Date.now() + 6000; return; }
  wdFast = Date.now() + 6000;
  wdTimer = setInterval(function(){
    if (!ctx) return;
    if (bgHidden) return;          /* deliberately asleep; leave it alone */
    /* after the opening scramble, back off so we are not polling forever */
    if (Date.now() > wdFast && ctx.state === 'running' && M.timer && !pending) return;
    if (ctx.state === 'closed'){
      ctx = null; master = sfxBus = musBus = uiBus = noiseBuf = null; verbs = {}; spaceSends = {}; outTap = null;
      A.audio.ctx = null; A.audio.ready = false;
      if (M.timer){ clearInterval(M.timer); M.timer = null; }
      /* `init` fires the subscribers itself now, for every engine after the
         first, so this branch no longer has to - and it was never the only path
         that needed it, which is the bug it hid. */
      if (gestured) A.audio.init();
      return;
    }
    if (ctx.state !== 'running'){
      if (gestured) ctx.resume().then(flush, function(){});
      return;
    }
    /* music was asked for but never actually got going */
    if (pending && M.on && !M.paused && !M.timer) runMusic(pending);
    /* a bus that should be open but is sitting at zero */
    var wantMus = (pref.music && !quiet()) ? 1.00 : 0;
    var wantSfx = (pref.sfx   && !quiet()) ? 0.62 : 0;
    if (Math.abs(musBus.gain.value - wantMus) > 0.4 ||
        Math.abs(sfxBus.gain.value - wantSfx) > 0.4) applyGains(0.05);
  }, 120);
}

/* Any real gesture is our cue: build the context if we have not yet, resume
   it if the browser parked it, and release any music that was queued while
   we were not allowed to make a sound. Stays subscribed, because a tab can
   be suspended again at any time. */
function wake(){
  gestured = true;
  /* If a page loads while the browser thinks it is hidden — which iOS does
     when a home-screen app is launched from cold — the background silencer
     can latch on and never let go. A real gesture on a visible page is proof
     enough that we are back. */
  if (bgHidden && !document.hidden) background(false);
  if (killTimer){ clearTimeout(killTimer); killTimer = null; }
  A.audio.init();
  if (!ctx) return;
  unlockTap();
  if (ctx.state !== 'running') ctx.resume().then(flush, function(){});
  else flush();
  /* re-assert every time: if a bus is sitting at zero when the player has
     not asked for silence, open it now rather than waiting on the watchdog */
  if (!hushed){
    if (pref.music && musBus.gain.value < 0.05) applyGains(0);
    if (pref.sfx   && sfxBus.gain.value < 0.05) applyGains(0);
  }
  if (pending && M.on && !M.timer && ctx.state === 'running') runMusic(pending);
  startWatchdog();
}
/* ---- TRY ONCE ON LOAD, BEFORE ANY GESTURE --------------------------------
   Nothing called `init()` until the first tap, so on a fresh page load the
   engine did not exist and the music had nowhere to go. A game opened from the
   launcher is ALWAYS a fresh page load, because the launcher navigates rather
   than swapping views — which is why games started silent.

   Attempting it costs one suspended context if permission is refused, and
   wins outright wherever autoplay is already allowed for the origin: desktop,
   an installed PWA, or a site the browser has enough engagement with. The
   gesture path below is untouched and still catches every other case.
   -------------------------------------------------------------------------- */
try { A.audio.init(); } catch(e){}

/* capture phase: a game's own pointerdown handler on its canvas would
   otherwise run first and find the engine still asleep */
document.addEventListener('pointerdown', wake, { capture:true, passive:true });
document.addEventListener('touchstart',  wake, { capture:true, passive:true });
document.addEventListener('keydown',     wake, { capture:true, passive:true });
document.addEventListener('click',       wake, { capture:true, passive:true });
/* Tear the engine down completely. suspend() only parks the audio session —
   iOS can and does resume a parked session after the app is gone, which is
   how a backgrounded page carried on blipping through a force-quit. close()
   releases the hardware for good; the next real gesture builds a fresh
   context and the games rebuild their held voices through onReset. */
var killTimer = null;
function teardown(){
  if (killTimer){ clearTimeout(killTimer); killTimer = null; }
  if (M.timer){ clearInterval(M.timer); M.timer = null; }
  M.paused = true;
  if (wdTimer){ clearInterval(wdTimer); wdTimer = null; }
  if (!ctx) return;
  try { if (master) master.disconnect(); } catch(e){}
  var dying = ctx;
  ctx = null; master = sfxBus = musBus = uiBus = noiseBuf = null; verbs = {}; spaceSends = {}; outTap = null;
  A.audio.ctx = null; A.audio.ready = false;
  try { if (dying.state !== 'closed') dying.close(); } catch(e){}
}

function background(on){
  if (bgHidden === on) return;
  bgHidden = on;
  if (on){
    M.paused = true;
    applyGains(0.03);
    if (ctx && ctx.state === 'running') ctx.suspend().catch(function(){});
    /* If we are still hidden a few seconds later the app is not coming back
       soon — stop being a live audio session at all. Covers the case where
       pagehide never fires, which is how it escaped a force-quit. */
    if (killTimer) clearTimeout(killTimer);
    killTimer = setTimeout(teardown, 4000);
  } else {
    if (killTimer){ clearTimeout(killTimer); killTimer = null; }
    if (!hushed) M.paused = false;
    if (ctx && gestured) ctx.resume().then(flush, function(){});
    applyGains(0.05);
  }
}

document.addEventListener('visibilitychange', function(){
  background(document.hidden);
  if (!document.hidden && gestured) wake();
});
/* pagehide fires where visibilitychange sometimes does not — closing a tab,
   swiping a home-screen app away, the back/forward cache */
/* closing, swiping the app away, or being frozen: destroy it outright */
window.addEventListener('pagehide', teardown);
window.addEventListener('freeze',   teardown);
window.addEventListener('beforeunload', teardown);
window.addEventListener('blur',     function(){ if (document.hidden) background(true); });
window.addEventListener('pageshow', function(){ if (!document.hidden) background(false); });
})();
