/* =====================================================================
   EFFIGY ARCADE — arcade.js
   Drop this one line into any game's <head> and it gains a title bar,
   a pause menu, and a way back to the launcher:

     <script src="../audio.js"></script>
     <script src="../arcade.js"></script>
     <meta name="arcade-title"  content="Sounding">
     <meta name="arcade-accent" content="#4de0c8">

   The contract a game has to honour is three CSS variables, all of
   which have standalone-friendly defaults so the game still runs fine
   when opened on its own:

     --stage-h    height available to the game        (default 100dvh)
     --safe-top   top safe-area inset to apply        (default env(...))
     #stage       an absolutely-positioned inset:0 root element

   Also provides, to games and to the launcher alike:

     Arcade.pad    Xbox / PlayStation / any standard gamepad
     Arcade.save   namespaced localStorage, one slot per game

   Pausing works by gating requestAnimationFrame, so nothing here needs
   to know anything about how a particular game is built.

   © 2026 Effigy Media. All rights reserved.
   ===================================================================== */
(function(){
"use strict";

var A = window.Arcade = window.Arcade || {};

/* THE VERSION, AND THE ONLY COPY OF IT.
   The shell loads on the launcher and on every cabinet, so a version kept here is
   readable from anywhere in the arcade. There is no package.json to hold it, and a
   second copy in a file that nothing reads is how two answers to one question start.
   The git tag mirrors this string; a tag is a record, not a source.

   IT RESET TO 0.1.0 AT THE FORK, AND THE CODE DID NOT GET YOUNGER. Tiny Arcade
   reached 0.9.11 and its number described a nearly finished arcade of nineteen
   small machines. This product is four machines that are each meant to become a
   full multi-scene game, and almost none of that is built - so carrying 0.9.11
   over would have said "nearly done" about work that has barely started. The
   version tracks THIS product. The maturity of the engine underneath it is
   recorded in the git history, which came across whole. */
A.version = '0.13.39';

/* ---- WHICH BUILD AM I PLAYING? -------------------------------------------
   Asked for by the owner, 2026-08-29, and it is a testing tool rather than
   decoration: a fix cannot be confirmed or ruled out from a device unless the
   device can say which build it is running. Every commit that changes the
   product names this string, and `A.buildTag()` is what the arcade prints, so
   the two can be read side by side.

   IT ALSO CATCHES A STALE HALF, which is the failure this product can actually
   have. `sw.js` serves scripts network-first with a short timeout and a cache
   fallback, so a slow connection can hand a device a FRESH arcade.js beside a
   CACHED road.js and nothing about the picture would say so. road.js stamps
   `window.ROAD_BUILD` with the version it was written for; if the two disagree
   the tag says MIXED, and that is the one case where a second copy of the
   version number earns its place - it is not a second answer to one question,
   it is each file stating which build it came from.
   ------------------------------------------------------------------------ */
A.buildTag = function(){
  var road = window.ROAD_BUILD;
  if (road && road !== A.version) return 'BUILD ' + A.version + ' / ROAD ' + road + ' - MIXED';
  return 'BUILD ' + A.version;
};

/* every cabinet draws its name with the same hand */
A.wordmark = wordmark;

/* ---- Arcade.gesture ----------------------------------------------------
   Page-wide pointer input, shared by every machine. A thumb lands where it
   lands; making someone hit a 360px canvas to steer or to turn a corner is a
   fight with the game rather than with the game's hazards.

   Two ways to listen:
     Arcade.gesture.onSwipe(fn)  fn('up'|'down'|'left'|'right')  — one per flick
     Arcade.gesture.onDrag(fn)   fn({dx, dy, first, last})       — continuous

   Both ignore anything that starts on a control (button, link, field) or on
   an open overlay, so title screens and pause menus keep working, and both
   stop while the shell is paused.
   ------------------------------------------------------------------------ */
(function(){
  var swipeSubs = [], dragSubs = [];
  var id = null, sx = 0, sy = 0, lx = 0, ly = 0, fired = false, dragging = false;
  var THRESH = 16;

  function blocked(target){
    if (A.paused && A.paused()) return true;
    if (!target || !target.closest) return false;
    if (target.closest('button, a, input, select, textarea, [role="button"]')) return true;
    var veil = target.closest('#veil, .ark-veil, .veil');
    if (veil && !veil.classList.contains('hidden')) return true;
    return false;
  }

  function down(e){
    if (id !== null || blocked(e.target)) return;
    id = e.pointerId; sx = lx = e.clientX; sy = ly = e.clientY;
    fired = false; dragging = false;
  }
  function move(e){
    if (id !== e.pointerId) return;
    var dx = e.clientX - lx, dy = e.clientY - ly;
    var tx = e.clientX - sx, ty = e.clientY - sy;

    if (!fired && (Math.abs(tx) >= THRESH || Math.abs(ty) >= THRESH)){
      var dir = Math.abs(tx) > Math.abs(ty) ? (tx > 0 ? 'right' : 'left')
                                            : (ty > 0 ? 'down'  : 'up');
      for (var i=0;i<swipeSubs.length;i++) swipeSubs[i](dir);
      if (swipeSubs.length){ fired = true; if (e.cancelable) e.preventDefault(); }
    }
    if (dragSubs.length){
      for (var j=0;j<dragSubs.length;j++)
        dragSubs[j]({ dx:dx, dy:dy, x:e.clientX, y:e.clientY, first:!dragging, last:false });
      dragging = true;
      if (e.cancelable) e.preventDefault();
    }
    lx = e.clientX; ly = e.clientY;
  }
  function up(e){
    if (id !== e.pointerId) return;
    if (dragging) for (var i=0;i<dragSubs.length;i++)
      dragSubs[i]({ dx:0, dy:0, x:e.clientX, y:e.clientY, first:false, last:true });
    id = null; fired = false; dragging = false;
  }

  window.addEventListener('pointerdown', down, { passive:true });
  window.addEventListener('pointermove', move, { passive:false });
  window.addEventListener('pointerup', up, { passive:true });
  window.addEventListener('pointercancel', up, { passive:true });

  /* Is this a touch device? Decides whether on-screen controls are drawn at
     all — a desktop showing thumb buttons looks broken, and a phone without
     them is unplayable. Coarse pointer rather than user-agent sniffing. */
/* The shell boots on DOMContentLoaded, which is after a game's inline script
   has run — so a game calling Arcade.options.define() at parse time would find
   nothing there. Stand the API up immediately and hold the call until boot. */
A._optQueue = null;
A.options = {
  define: function(defs, onChange){ A._optQueue = { defs: defs, onChange: onChange }; },
  get: function(){ return undefined; },
  set: function(){}
};

  A.touch = (function(){
    try {
      return window.matchMedia('(pointer: coarse)').matches ||
             ('ontouchstart' in window) ||
             (navigator.maxTouchPoints || 0) > 0;
    } catch(e){ return true; }
  })();

  /* ---- cinema --------------------------------------------------------------
   A frame sequence between the title and the run. The shell owns the parts
   every cabinet would otherwise reimplement: the canvas at the right pixel
   ratio, the recovered-footage grade, SKIP, once-per-device memory, and
   handing control back when it is done. A game supplies only the drawings and
   the words.

     Arcade.cinema.play([
       { art: (g,w,h) => {...}, text: 'One line over the frame.' }
     ], { key:'quietus.intro', onDone: start, overlay: myOpenVeil });

   `overlay` is how a game renders a panel — it is handed HTML and a callback,
   because every cabinet already has its own veil and its own typeface, and the
   shell should not impose a look on top of them.
   -------------------------------------------------------------------------- */
/* ---- Arcade.menu: a cursor for every cabinet's own menus -----------------
   EVERY GAME MENU COULD ONLY BE ANSWERED WITH THE FIRST BUTTON. The pattern
   copied into all eighteen cabinets binds Enter (and pad A) to
   `veilBody.querySelector('.btn').click()` - the FIRST one - so PLAY and PLAY
   AGAIN worked and OPTIONS, CONTROLS and QUIT were pointer-only. The page that
   exists to tell a keyboard player which keys to use was the page a keyboard
   could not open.

   This lives in the shell rather than in eighteen files because the fix is
   identical everywhere and the games already agree on the shape: a container
   that becomes visible, holding buttons. Nothing is imposed on their look - the
   cursor is one class, and a cabinet that styles `.ark-cursor` gets its own.

   It takes the keys in the CAPTURE phase and stops them there, because the
   game's own handler is still bound to "Enter clicks the first button" and
   would otherwise fire as well. Arrow keys are only claimed while a menu is
   actually open, so gameplay steering is untouched.
   ------------------------------------------------------------------------ */
A.menu = (function(){
  var BTN = 'button, .btn, .go, .mbtn, .ark-act, [data-act]';
  var cursor = -1;

  function shown(el){
    if (!el) return false;
    var r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  }
  /* the deepest visible panel that holds more than one button */
  function panel(){
    var cands = document.querySelectorAll('#veilBody, #veil, .ark-veil.on, .vw');
    for (var i = cands.length - 1; i >= 0; i--){
      var el = cands[i];
      if (!shown(el)) continue;
      if (el.closest && el.closest('.hidden')) continue;
      if (buttons(el).length > 1) return el;
    }
    return null;
  }
  function buttons(el){
    return [].slice.call(el.querySelectorAll(BTN)).filter(shown);
  }
  function paint(list){
    for (var i = 0; i < list.length; i++)
      list[i].classList.toggle('ark-cursor', i === cursor);
  }
  function move(d){
    var el = panel(); if (!el) return false;
    var list = buttons(el); if (!list.length) return false;
    cursor = cursor < 0 ? 0 : (cursor + d + list.length) % list.length;
    paint(list);
    try { list[cursor].focus({ preventScroll:true }); } catch(e){}
    return true;
  }
  function press(){
    var el = panel(); if (!el) return false;
    var list = buttons(el); if (!list.length) return false;
    var pick = list[cursor >= 0 && cursor < list.length ? cursor : 0];
    cursor = -1;
    pick.click();
    return true;
  }
  /* a fresh panel starts with no cursor, so the first arrow lands on the first
     button rather than the second */
  var seen = null;
  setInterval(function(){
    var el = panel();
    if (el !== seen){ seen = el; cursor = -1; if (el) paint(buttons(el)); }
  }, 140);

  document.addEventListener('keydown', function(e){
    if (!panel()) return;
    var k = e.key;
    if (k === 'ArrowDown' || k === 'ArrowRight'){ if (move(1)){ e.preventDefault(); e.stopPropagation(); } }
    else if (k === 'ArrowUp' || k === 'ArrowLeft'){ if (move(-1)){ e.preventDefault(); e.stopPropagation(); } }
    else if (k === 'Enter' || k === ' '){
      if (cursor >= 0 && press()){ e.preventDefault(); e.stopPropagation(); }
    }
  }, true);

  /* the pad, registered here so it is the FIRST subscriber and can swallow */
  if (A.pad && A.pad.onPress) A.pad.onPress(function(name){
    if (!panel()) return;
    if (name === 'down' || name === 'right'){ return move(1); }
    if (name === 'up'   || name === 'left'){  return move(-1); }
    if ((name === 'a' || name === 'start') && cursor >= 0) return press();
  });

  return { move: move, press: press, open: function(){ return !!panel(); } };
})();

/* Back to the launcher. Every cabinet declares where home is in a meta tag;
   this is the one place that reads it, so QUIT means the same thing everywhere. */
A.home = function(){
  var m = document.querySelector('meta[name="arcade-home"]');
  var href = m && m.content ? m.content : '../../index.html';
  location.href = href;
};

A.cinema = (function(){
  /* ONE BLOB FOR THE WHOLE ARCADE, until this line. Every machine's record of
     which intros it had already shown lived together, which meant erasing one
     game had to reach inside a shared object and prune it, and a game split out
     on its own would have carried its neighbours' flags. Scoped, it is simply
     one of that machine's own keys. */
  var KEY = 'effigyarcade.' + (A.scope || 'launcher') + '.cinema.v1';

  function seenSet(){
    try { return JSON.parse(localStorage.getItem(KEY) || '{}'); } catch(e){ return {}; }
  }
  function seen(k){ return !!seenSet()[k]; }
  function mark(k){
    try { var o = seenSet(); o[k] = 1; localStorage.setItem(KEY, JSON.stringify(o)); } catch(e){}
  }

  /* NO VISUAL TREATMENT LIVES HERE. An earlier pass put grain, scanlines and a
     red recording dot in the shell, which is Quietus's suit-cam look rather
     than a mechanism — Penboy would have inherited horror-film grain over a
     ballpoint drawing. A game passes its own `filter` and gets exactly the
     look it chose. The shell only decides WHEN it runs. */

  function canvasFor(frame, w, h){
    var cv = document.createElement('canvas');
    var dpr = Math.min(2, window.devicePixelRatio || 1);
    cv.width = Math.round(w*dpr); cv.height = Math.round(h*dpr);
    cv.style.width = w+'px'; cv.style.height = h+'px';
    cv.className = 'ark-cine';
    var g = cv.getContext('2d');
    g.scale(dpr,dpr);
    try { frame.art(g, w, h); } catch(e){}
    /* whatever treatment the GAME supplies, applied last */
    if(typeof frame.filter === 'function'){ try { frame.filter(g, w, h); } catch(e){} }
    return cv;
  }

  return { seen: seen, mark: mark, canvasFor: canvasFor };
})();

A.gesture = {
    onSwipe: function(fn){ swipeSubs.push(fn); },
    onDrag:  function(fn){ dragSubs.push(fn); },
    threshold: function(px){ THRESH = px; }
  };
})();

/* ---- 0. offline. Registering here covers the launcher and every game,
   since arcade.js is the one file all of them load. ---- */
if ('serviceWorker' in navigator && location.protocol.slice(0,4) === 'http'){
  window.addEventListener('load', function(){
    /* this file runs from <head>, so the body does not exist yet — the
       launcher/game test has to wait until load or it always says launcher
       and registers games/sw.js, which does not exist. */
    /* Games live TWO levels down (games/<shelf>/x.html), not one — '../sw.js'
       resolved to games/sw.js, which does not exist, so every cabinet 404'd on
       its service worker and silently lost offline support. The launcher is at
       the root. Derive it from the arcade-home meta the game already declares
       rather than counting directories here. */
    var m = document.querySelector('meta[name="arcade-home"]');
    var root = './';
    if (m && m.content) root = m.content.replace(/index\.html(#.*)?$/, '');
    if (!root) root = './';
    /* ---- IT HAS TO UPDATE ITSELF ---------------------------------------
       The worker called skipWaiting and claim, so a NEW worker took over the
       page — but the page it took over was already rendered from the OLD
       files. Nothing reloaded, so you kept looking at the previous build until
       you refreshed by hand. Nobody should have to know that.

       Three parts:
         - check for a new worker on every load, and again every ten minutes
           for a session left open
         - when one installs and something is already controlling the page,
           that is an UPDATE rather than a first install
         - reload once when it takes control. `reloading` guards the loop:
           without it `controllerchange` fires again after the reload and the
           page refreshes forever.
       ------------------------------------------------------------------- */
    navigator.serviceWorker.register(root + 'sw.js').then(function(reg){
      if (!reg) return;
      reg.update();
      setInterval(function(){ reg.update(); }, 10 * 60 * 1000);
      reg.addEventListener('updatefound', function(){
        var w = reg.installing;
        if (!w) return;
        w.addEventListener('statechange', function(){
          if (w.state === 'installed' && navigator.serviceWorker.controller)
            w.postMessage('skipWaiting');
        });
      });
    }, function(err){
      if (window.console && console.warn) console.warn('arcade: offline cache unavailable', err);
    });

    /* ---- A FIRST VISIT IS NOT AN UPDATE ----------------------------------
       `controllerchange` fires TWICE in a page's life: once when the very
       first worker calls `clients.claim()`, and once when a new worker
       replaces an old one. Only the second is an update. Reloading on the
       first meant every cold visit refreshed itself about a second after
       load — long enough to have tapped PLAY, so the garage opened and then
       vanished under you. Found by the drive test, which lost its first
       click to exactly this.

       `hadController` is read BEFORE the reload can happen: if the page was
       already controlled when it loaded, any change from here is a genuine
       swap. */
    var hadController = !!navigator.serviceWorker.controller;
    var reloading = false;
    navigator.serviceWorker.addEventListener('controllerchange', function(){
      if (!hadController) { hadController = true; return; }
      if (reloading) return;
      reloading = true;
      window.location.reload();
    });
  });
}

/* ---- 1. frame gate. Installed immediately, before the game boots ---- */
var paused = false, held = null;
var raf = window.requestAnimationFrame && window.requestAnimationFrame.bind(window);
if (raf) {
  window.requestAnimationFrame = function(cb){
    return raf(function(t){
      if (paused) held = cb;          // only ever one: a paused loop
      else cb(t);                     // cannot schedule its successor
    });
  };
}

/* ---- 2. saving ------------------------------------------------------
   One slot per game id. Anything JSON-serialisable. If a game writes a
   `label`, the launcher prints it on that machine's cabinet card.

   THE NAMESPACE RULE, AND CLEARING DEPENDS ENTIRELY ON IT.
   Everything the arcade stores lives under `effigyarcade.`, and everything
   ONE MACHINE stores lives under one of exactly two shapes:

       effigyarcade.save.v1.<id>          the save slot        (this API)
       effigyarcade.save.v1.<id>-<suffix> a second slot, e.g. `-opts`
       effigyarcade.<id>.<anything>       written by the machine itself

   A machine that stores something outside those shapes is invisible to the
   eraser, and `clear` will report success while leaving it behind. That was
   the state before this comment existed: `clear` removed the save slot only,
   so `-opts` survived, Quietus's own tally and intro flags survived, and the
   cinema's record of which intros had been seen survived. Erasing a game left
   it remembering most of what it knew.

   `save` and `cinema` are therefore reserved and cannot be game ids.
   ---------------------------------------------------------------------- */
var NS   = 'effigyarcade.';
var SKEY = NS + 'save.v1.';
var RESERVED = { save:1, cinema:1, launcher:1 };

/* every stored key that belongs to one machine, and nothing that does not.
   The `-` and `.` in these tests are load-bearing: a bare `indexOf` prefix
   test would let a machine called `inter` claim `interstate`'s keys. */
function ownedBy(id){
  var out = [], exact = SKEY + id, slot = exact + '-', raw = NS + id + '.';
  try {
    Object.keys(localStorage).forEach(function(k){
      if (k === exact || k.indexOf(slot) === 0 || k.indexOf(raw) === 0) out.push(k);
    });
  } catch(e){}
  return out;
}

A.save = {
  get: function(id){
    try { var r = localStorage.getItem(SKEY + id); return r ? JSON.parse(r) : null; }
    catch(e){ return null; }
  },
  set: function(id, obj){
    try { localStorage.setItem(SKEY + id, JSON.stringify(obj)); return true; }
    catch(e){ return false; }
  },
  merge: function(id, obj){
    var cur = A.save.get(id) || {};
    for (var k in obj) cur[k] = obj[k];
    return A.save.set(id, cur);
  },

  /* is there anything to erase? So a menu can say so instead of offering a
     button that does nothing. */
  has: function(id){ return ownedBy(id).length > 0; },

  /* ERASE ONE MACHINE, COMPLETELY. Returns how many keys went, so a caller
     can tell the player something true. */
  clear: function(id){
    if (!id || RESERVED[id]) return 0;
    var keys = ownedBy(id), n = 0;
    for (var i = 0; i < keys.length; i++){
      try { localStorage.removeItem(keys[i]); n++; } catch(e){}
    }
    /* THE PRUNE THAT USED TO LIVE HERE IS GONE, and its absence is the point:
       the cinema is scoped per machine now, so its key is `effigyarcade.<id>.
       cinema.v1` and `ownedBy` above already took it. So are that machine's
       audio preferences and the shell's options for it. Nothing about one
       machine is stored anywhere that erasing it cannot reach. */
    return n;
  },

  /* ERASE THE WHOLE ARCADE. The launcher's own ERASE used to match
     `effigyarcade.save` and so left the cinema blob and every machine's own
     keys in place, under a note promising it cleared runs in progress. */
  clearAll: function(){
    var n = 0;
    try {
      Object.keys(localStorage).forEach(function(k){
        if (k.indexOf(NS) === 0){ localStorage.removeItem(k); n++; }
      });
    } catch(e){}
    return n;
  }
};

/* ---- 3. gamepad -----------------------------------------------------
   Standard mapping, so an Xbox pad and a DualSense land on the same
   names. Directions auto-repeat, which suits both menus and a grid
   crawler. Polled off the raw rAF so Start still works while paused.  */
var NAMES = ['a','b','x','y','lb','rb','lt','rt','back','start','l3','r3','up','down','left','right','home'];
var padState = {}, padPrev = {}, padRepeat = {}, padSubs = [], padAxis = {x:0,y:0};
var padOn = false, DEAD = 0.28;
var REPEAT_DIRS = { up:1, down:1, left:1, right:1 };

function pollPad(){
  var list = navigator.getGamepads ? navigator.getGamepads() : [];
  var gp = null;
  for (var i=0;i<list.length;i++) if (list[i] && list[i].connected){ gp = list[i]; break; }
  padOn = !!gp;
  var now = performance.now();

  for (var n=0;n<NAMES.length;n++) padPrev[NAMES[n]] = padState[NAMES[n]];

  if (gp){
    for (var b=0;b<NAMES.length;b++){
      var btn = gp.buttons[b];
      padState[NAMES[b]] = !!(btn && (btn.pressed || btn.value > 0.5));
    }
    var ax = gp.axes[0] || 0, ay = gp.axes[1] || 0;
    padAxis.x = Math.abs(ax) > DEAD ? ax : 0;
    padAxis.y = Math.abs(ay) > DEAD ? ay : 0;
    /* stick doubles as the d-pad for menus */
    if (padAxis.x < -0.6) padState.left = true;
    if (padAxis.x >  0.6) padState.right = true;
    if (padAxis.y < -0.6) padState.up = true;
    if (padAxis.y >  0.6) padState.down = true;
  } else {
    for (var c=0;c<NAMES.length;c++) padState[NAMES[c]] = false;
    padAxis.x = padAxis.y = 0;
  }

  for (var k=0;k<NAMES.length;k++){
    var name = NAMES[k], is = padState[name], was = padPrev[name];
    var fire = false;
    if (is && !was){ fire = true; padRepeat[name] = now + 380; }
    else if (is && was && REPEAT_DIRS[name] && now > (padRepeat[name] || 0)){
      fire = true; padRepeat[name] = now + 150;
    }
    /* A SUBSCRIBER MAY SWALLOW A PRESS by returning true. The shell's menu
       cursor is registered first and uses this: without it, A would move the
       cursor AND fire the game's own "click the first button" handler, so a
       pad could never choose anything but the first item. Every existing
       subscriber returns undefined, so nothing else changes. */
    if (fire) for (var q=0;q<padSubs.length;q++){
      var swallowed = false;
      try { swallowed = padSubs[q](name) === true; } catch(e){}
      if (swallowed) break;
    }
  }
  if (raf) raf(pollPad);
}

A.paused = function(){ return paused; };

A.pad = {
  connected: function(){ return padOn; },
  axis: function(){ return padAxis; },
  down: function(name){ return !!padState[name]; },
  onPress: function(fn){ padSubs.push(fn); },
  /* the two face buttons everyone means by "confirm" and "back" */
  confirm: function(name){ return name === 'a' || name === 'start'; },
  cancel:  function(name){ return name === 'b'; }
};
if (raf) raf(pollPad);

function meta(name, fallback){
  var el = document.querySelector('meta[name="' + name + '"]');
  return (el && el.getAttribute('content')) || fallback;
}

/* The glass belongs to the whole app, not to a game. It used to be built
   inside boot() AFTER the "no #stage means we are on the launcher" bail, so
   every cabinet had scanlines and the launcher had none. */
/* ---------------------------------------------------------------------------
   UI SCALE. Every cabinet's overlay is laid out in px against a ~390pt phone.
   On a desktop the canvas grows to fill the window but the buttons, gauges and
   readouts stay the size they were, so they shrink into a corner of a 1400px
   window and look like a phone screenshot pasted onto a monitor.

   `--ark-ui` is published on the root element for any game to use. It is 1 on
   a phone and rises with the viewport, capped so a huge monitor does not get
   comically large furniture. Games opt in by scaling their own overlay by it —
   the shell cannot do it for them without knowing what is a control and what
   is the game itself.
   --------------------------------------------------------------------------- */
function uiScale(){
  var w = window.innerWidth, h = window.innerHeight;
  var short = Math.min(w, h);
  /* a phone is ~390 short-edge; grow from there, and stop at 1.8 */
  var s = Math.max(1, Math.min(1.8, short / 390));
  document.documentElement.style.setProperty('--ark-ui', s.toFixed(3));
  return s;
}

/* ===========================================================================
   TITLE WORDMARKS

   Every cabinet draws its own name rather than setting it in a font, because a
   font says "UI" and a marquee does not. The letter skeletons live here so all
   seventeen share one alphabet and one treatment: a heavy shell, then a face
   gradient split at the midline — cool above, hot below — so the horizon runs
   through the word the way it runs through the art behind it.

   A game passes its own two colour ramps, so Redline Interstate is chrome-and-amber and
   Deep is ice-and-abyss, but the construction is common.
   =========================================================================== */
var GLYPH = {
  A:[[[0,14],[5,0],[10,14]],[[2,9],[8,9]]],
  B:[[[0,0],[0,14]],[[0,0],[7,0],[9,2],[9,5],[7,7],[0,7]],[[0,7],[8,7],[10,9],[10,12],[8,14],[0,14]]],
  C:[[[10,3],[7,0],[3,0],[0,3],[0,11],[3,14],[7,14],[10,11]]],
  D:[[[0,0],[0,14]],[[0,0],[6,0],[10,4],[10,10],[6,14],[0,14]]],
  E:[[[0,0],[0,14]],[[0,0],[9,0]],[[0,7],[7,7]],[[0,14],[9,14]]],
  F:[[[0,0],[0,14]],[[0,0],[9,0]],[[0,7],[7,7]]],
  G:[[[10,3],[7,0],[3,0],[0,3],[0,11],[3,14],[7,14],[10,11],[10,8],[5,8]]],
  H:[[[0,0],[0,14]],[[10,0],[10,14]],[[0,7],[10,7]]],
  I:[[[5,0],[5,14]],[[1,0],[9,0]],[[1,14],[9,14]]],
  J:[[[8,0],[8,11],[5,14],[2,14],[0,11]]],
  K:[[[0,0],[0,14]],[[9,0],[0,7]],[[3,5],[10,14]]],
  L:[[[0,0],[0,14],[9,14]]],
  M:[[[0,14],[0,0],[5,6],[10,0],[10,14]]],
  N:[[[0,14],[0,0],[10,14],[10,0]]],
  O:[[[3,0],[7,0],[10,3],[10,11],[7,14],[3,14],[0,11],[0,3],[3,0]]],
  P:[[[0,14],[0,0],[7,0],[10,3],[10,6],[7,9],[0,9]]],
  Q:[[[3,0],[7,0],[10,3],[10,11],[7,14],[3,14],[0,11],[0,3],[3,0]],[[6,10],[10,14]]],
  R:[[[0,14],[0,0],[7,0],[10,3],[10,6],[7,9],[0,9]],[[5,9],[10,14]]],
  S:[[[10,3],[7,0],[3,0],[0,3],[0,5],[3,7],[7,7],[10,9],[10,11],[7,14],[3,14],[0,11]]],
  T:[[[0,0],[10,0]],[[5,0],[5,14]]],
  U:[[[0,0],[0,11],[3,14],[7,14],[10,11],[10,0]]],
  V:[[[0,0],[5,14],[10,0]]],
  W:[[[0,0],[2,14],[5,5],[8,14],[10,0]]],
  X:[[[0,0],[10,14]],[[10,0],[0,14]]],
  Y:[[[0,0],[5,7],[10,0]],[[5,7],[5,14]]],
  Z:[[[0,0],[10,0],[0,14],[10,14]]],
  "0":[[[3,0],[7,0],[10,3],[10,11],[7,14],[3,14],[0,11],[0,3],[3,0]],[[0,12],[10,2]]],
  " ":[]
};

/* ---- THE ALPHABET IS SHARED, THE TREATMENT IS NOT ------------------------
   The letter skeletons are common so every cabinet gets the same construction
   and the same fitting maths. Everything else is the game's own: pass a
   `paint` function and it is called once per stroke with the path already
   laid down, free to stroke it in phosphor, fill it like folded card, cut it
   with a horizon, or anything else.

   Sharing the treatment would have made seventeen marquees that all look like
   Redline Interstate's, which is the exact problem a drawn logo is meant to solve.

   paint(g, pass, i, n)  — pass is 'shell' then 'face'; i is the letter index.

   `glyphs` — the ALPHABET ITSELF. Restyling one skeleton in three colours is
   one typeface three times over, so a cabinet can hand in its own letterforms:
   any map of character to a list of point-lists in a 10-wide, 14-tall box.
   `box` widens or narrows that box, so a condensed or a squat face is possible
   without redrawing anything. What is shared is the LAYOUT — fitting, rake,
   spacing, passes — not the shapes.
   -------------------------------------------------------------------------- */
function wordmark(g, word, cx, cy, size, opt){
  opt = opt || {};
  var rake = opt.rake === undefined ? -0.16 : opt.rake;
  var G    = opt.glyphs || GLYPH;
  var boxW = opt.box || 10;
  var gap  = size * (opt.gap === undefined ? 0.24 : opt.gap);
  /* ---- PROPORTIONAL, if the cabinet asks for it -------------------------
     A fixed slot per letter is a monospace grid, and on a hand-written face it
     shows: an I floats in a gap twice its own width while a D and a C nearly
     touch. `widths` lets a glyph declare its own advance, and the layout steps
     by that instead of by a constant.
     ---------------------------------------------------------------------- */
  var WD = opt.widths || null;
  /* ---- and per-letter BASELINE offsets ---------------------------------
     `rise` lets a cabinet lift or drop individual letters, in the same 14-unit
     glyph space as everything else. A hand-painted sign does not sit on a
     ruled line, and staggering the letters is most of what separates one from
     a typeset word.
     ---------------------------------------------------------------------- */
  var RISE = opt.rise || null;
  var adv = function(ch){ return size * ((WD && WD[ch] !== undefined ? WD[ch] : boxW) / 14); };
  var lw   = size * boxW/14;
  var total = 0;
  for (var q = 0; q < word.length; q++) total += adv(word[q]);
  total += (word.length - 1) * gap;
  var need  = total + Math.abs(rake) * size;
  var k     = Math.min(1, (opt.maxW || 1e9) / need);
  var cool  = opt.cool || ["#f6f8ff", "#9fb2d8", "#e9eefc"];
  var hot   = opt.hot  || ["#ffd27a", "#ff8a2b", "#c93c1f"];

  g.save();
  g.translate(cx, cy);
  g.scale(k, k);
  g.transform(1, 0, rake, 1, 0, 0);
  g.translate(-total/2, -size/2);

  /* ---- A CHARACTER WITH NO GLYPH IS SILENT, AND THAT IS THE PROBLEM -------
     `G[ch] || []` draws nothing and reports nothing, so a word set in a
     cabinet's own alphabet loses whatever letters that alphabet happens not to
     have. Quietus was drawn as `IET` for a whole release: its hand-painted
     blood letters were authored for DERELICT and had no Q, U or S. The build
     passed, and so did the harness - a canvas with three letters on it has
     paint on it exactly like a canvas with seven.

     So the shell says so. Once per word, loudly, naming what is missing. The
     smoke test fails on a console error, which turns a silent art bug into a
     gate for every cabinet. */
  if (opt.glyphs) {
    var gone = '';
    for (var gi = 0; gi < word.length; gi++) {
      var gch = word[gi];
      if (gch !== ' ' && !G[gch] && gone.indexOf(gch) < 0) gone += gch;
    }
    if (gone && typeof console !== 'undefined' && console.error) {
      console.error('Arcade.wordmark: "' + word + '" needs ' + gone.split('').join(', ') +
                    ' and this alphabet has no glyph for ' +
                    (gone.length > 1 ? 'them' : 'it') + ' - they will not draw.');
    }
  }

  var passes = opt.passes || ["shell", "face"];
  passes.forEach(function(pass){
    var x = 0;
    for (var i = 0; i < word.length; i++) {
      var strokes = G[word[i]] || [];
      g.save();
      g.translate(x, (RISE && RISE[i] !== undefined ? RISE[i] : 0) * size/14);
      g.scale(size/14, size/14);
      g.lineJoin = "round"; g.lineCap = "round";
      for (var s2 = 0; s2 < strokes.length; s2++) {
        var st = strokes[s2];
        g.beginPath();
        g.moveTo(st[0][0], st[0][1]);
        for (var j = 1; j < st.length; j++) g.lineTo(st[j][0], st[j][1]);
        /* A cabinet that wants to draw the stroke ITSELF gets the points and
           returns true to say "I have handled it" — the laid path is then
           thrown away. That is what lets a smear vary its width ALONG a
           stroke, which stroking a whole path can never do. */
        if (opt.paint) {
          var handled = opt.paint(g, pass, i, word.length, st, word[i]);
          if (!handled) g.stroke();
          continue;
        }
        if (pass === "shell") { g.strokeStyle = "#0a0710"; g.lineWidth = 5.2; }
        else {
          var grd = g.createLinearGradient(0, 0, 0, 14);
          grd.addColorStop(0.00, cool[0]);
          grd.addColorStop(0.34, cool[1]);
          grd.addColorStop(0.49, cool[2]);
          grd.addColorStop(0.51, hot[0]);
          grd.addColorStop(0.72, hot[1]);
          grd.addColorStop(1.00, hot[2]);
          g.strokeStyle = grd; g.lineWidth = 3.4;
        }
        g.stroke();
      }
      g.restore();
      x += adv(word[i]) + gap;
    }
  });
  g.restore();
}

function glass(){
  if (document.querySelector('.ark-crt')) return;
  /* The launcher has had its own #crt overlay since it was built — full-screen
     scanlines with a hum animation. Adding a second one stacked two sets of
     lines and doubled the darkening. If a page already brought glass, leave it
     alone; the shell only supplies it where there is none. */
  if (document.getElementById('crt')) return;
  /* its own stylesheet: the game stylesheet is built after the launcher bail,
     so rules living there gave the launcher a bare element and no scanlines */
  var gs = document.createElement('style');
  gs.textContent = [
    '.ark-crt{position:fixed;inset:0;z-index:2147483000;pointer-events:none;',
      'background:repeating-linear-gradient(to bottom,',
        'rgba(0,0,0,.26) 0px, rgba(0,0,0,.26) 1px, rgba(255,255,255,.012) 1px,',
        'rgba(255,255,255,.012) 3px)}',
    '@media (min-resolution:2dppx){.ark-crt{background:repeating-linear-gradient(',
      'to bottom, rgba(0,0,0,.22) 0px, rgba(0,0,0,.22) 1.5px,',
      'rgba(255,255,255,.014) 1.5px, rgba(255,255,255,.014) 4px)}}',
    '.ark-crt::after{content:"";position:absolute;inset:0;',
      'background:radial-gradient(ellipse at 50% 50%,',
        'rgba(0,0,0,0) 52%, rgba(0,0,0,.34) 100%)}'
  ].join('');
  document.head.appendChild(gs);
  var crt = document.createElement('div');
  crt.className = 'ark-crt';
  document.body.appendChild(crt);
  A.crt = {
    on: function(v){ crt.style.display = v === false ? 'none' : ''; },
    el: crt
  };
}

function boot(){
  glass();
  uiScale();
  window.addEventListener('resize', uiScale);
  /* no #stage means we are on the launcher: skip the SHELL, keep the rest */
  if (!document.getElementById('stage')) return;

  var title  = meta('arcade-title', document.title || 'Untitled');
  var accent = meta('arcade-accent', '#e9e9f2');
  var home   = meta('arcade-home', '../index.html');
  var root   = home.replace(/index\.html$/, '');

  /* Add to Home Screen from inside a game should still install the arcade,
     under the arcade's name and icon, opening on the launcher. */
  function head(tag, attrs){
    var el = document.createElement(tag);
    for (var k in attrs) el.setAttribute(k, attrs[k]);
    document.head.appendChild(el);
    return el;
  }
  var appName = document.querySelector('meta[name="apple-mobile-web-app-title"]');
  if (appName) appName.setAttribute('content', 'EFFIGY ARCADE');
  else head('meta', { name:'apple-mobile-web-app-title', content:'EFFIGY ARCADE' });
  if (!document.querySelector('meta[name="application-name"]'))
    head('meta', { name:'application-name', content:'EFFIGY ARCADE' });
  if (!document.querySelector('link[rel="manifest"]'))
    head('link', { rel:'manifest', href: root + 'manifest.webmanifest' });
  if (!document.querySelector('link[rel="apple-touch-icon"]')){
    head('link', { rel:'apple-touch-icon', href: root + 'icon.png' });
    head('link', { rel:'icon', href: root + 'icon.png' });
  }

  var css = document.createElement('style');
  css.textContent = [
    ':root{',
    '  --arcade-bar:38px;',
    '  --arcade-h:calc(38px + env(safe-area-inset-top,0px));',
    '  --stage-h:calc(100dvh - var(--arcade-h));',
    '  --safe-top:0px;',
    '  --ark:' + accent + ';',
    '}',
    '#stage{top:var(--arcade-h)!important}',
    '.ark-bar{',
    '  position:fixed;top:0;left:0;right:0;z-index:9000;',
    '  height:var(--arcade-h);padding:env(safe-area-inset-top,0px) 6px 0 14px;',
    '  display:flex;align-items:center;gap:10px;',
    '  background:#0b0b11;border-bottom:1px solid #20212c;',
    '  font-family:ui-monospace,Menlo,monospace;',
    '}',
    '.ark-name{font-size:12px;font-weight:600;letter-spacing:.16em;',
    '  text-transform:uppercase;color:var(--ark)}',
    '.ark-tag{margin-left:auto;font-size:8px;font-weight:600;letter-spacing:.2em;color:#7c7f95}',
    '.ark-btn{flex:none;width:38px;height:26px;margin-left:8px;display:grid;place-items:center;',
    '  background:transparent;border:1px solid #20212c;color:#e9e9f2;cursor:pointer;padding:0}',
    '.ark-btn:active{background:#1a1a24}',
    '.ark-btn:focus-visible{outline:2px solid var(--ark);outline-offset:2px}',
    '.ark-btn i{display:block;width:9px;height:11px;',
    '  border-left:3px solid currentColor;border-right:3px solid currentColor}',
    '.ark-veil{position:fixed;inset:0;z-index:9100;display:none;place-items:center;',
    '  padding:28px 24px;text-align:center;background:rgba(6,6,10,.90);',
    '  -webkit-backdrop-filter:blur(6px);backdrop-filter:blur(6px);',
    '  font-family:ui-monospace,Menlo,monospace;color:#e9e9f2}',
    '.ark-veil.on{display:grid}',
    '.ark-wrap{width:100%;max-width:290px}',
    '.ark-kick{font-size:9px;font-weight:600;letter-spacing:.32em;color:#7c7f95;margin-bottom:10px}',
    '.ark-title{font-size:30px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;',
    '  line-height:1;margin-bottom:26px;color:var(--ark)}',
    '.ark-act{display:block;width:100%;margin-bottom:9px;padding:14px;cursor:pointer;',
    '  font-family:inherit;font-weight:600;font-size:11px;letter-spacing:.24em;',
    '  background:transparent;border:1px solid #20212c;color:#e9e9f2;text-decoration:none}',
    '.ark-act.key{border-color:var(--ark);color:var(--ark);background:rgba(255,255,255,.04)}',
    '.ark-act:active{background:rgba(255,255,255,.08)}',
    '.ark-act:focus-visible{outline:2px solid var(--ark);outline-offset:2px}',
    '.ark-note{margin-top:14px;font-size:9.5px;line-height:1.7;color:#7c7f95}',
    '.ark-build{margin:14px 0 2px;text-align:center;font-size:8px;',
    '  letter-spacing:.28em;color:#5b5e72}',
    '.ark-build.mixed{color:#ff8a6a}',
    '.ark-sep{display:flex;align-items:center;gap:8px;margin:20px 0 12px;',
    '  font-size:8px;letter-spacing:.3em;color:#7c7f95}',
    '.ark-sep::before,.ark-sep::after{content:"";flex:1;height:1px;background:#20212c}',
    '.ark-row{display:flex;gap:8px;margin-bottom:9px}',
    '.ark-row .ark-act{margin-bottom:0}',
    '.ark-act.tog{display:flex;align-items:center;justify-content:space-between;',
    '  padding:12px 13px;letter-spacing:.16em}',
    '.ark-act.tog b{font-weight:600;color:#565a70}',
    '.ark-cine-wrap{margin:12px 0 4px;display:flex;justify-content:center}',
    'canvas.ark-cine{border-radius:4px;display:block;',
      'box-shadow:0 0 0 1px rgba(160,200,225,.16),0 10px 34px -12px #000}',
    '.ark-cine-text{text-align:left;line-height:1.7;margin:12px auto 0;',
      'font-size:clamp(11.5px,3.6vw,15px);max-width:min(34ch,92vw)}',
    '.ark-cine-eyebrow{font-size:9px;letter-spacing:.24em;opacity:.6;text-align:center}',
    '.ark-act.tog.on b{color:var(--ark)}',
    '.ark-act.cursor{border-color:var(--ark);box-shadow:0 0 0 1px var(--ark) inset}',
    '.ark-hint{margin-top:10px;font-size:9px;letter-spacing:.14em;color:#565a70}',
    /* the menu cursor: an outline, so it reads on any cabinet's palette
       without knowing anything about it */
    '.ark-cursor{outline:2px solid var(--ark)!important;outline-offset:2px!important}',
  ].join('\n');
  document.head.appendChild(css);

  var bar = document.createElement('div');
  bar.className = 'ark-bar';
  bar.innerHTML = '<span class="ark-name"></span>' +
                  '<span class="ark-tag">RUNNING</span>' +
                  '<button class="ark-btn" type="button" aria-label="Pause"><i></i></button>';
  bar.querySelector('.ark-name').textContent = title;
  document.body.appendChild(bar);


  var veil = document.createElement('div');
  veil.className = 'ark-veil';
  veil.innerHTML =
    '<div class="ark-wrap">' +
      '<div class="ark-kick">PAUSED</div>' +
      '<div class="ark-title"></div>' +
      '<button class="ark-act key" type="button" data-a="resume">RESUME</button>' +
      '<button class="ark-act" type="button" data-a="restart">RESTART</button>' +
      '<a class="ark-act" href="' + home + '">EXIT TO ARCADE</a>' +
      '<div class="ark-sep">AUDIO</div>' +
      '<div class="ark-row">' +
        '<button class="ark-act tog" type="button" data-a="sfx">SFX<b>ON</b></button>' +
        '<button class="ark-act tog" type="button" data-a="music">MUSIC<b>ON</b></button>' +
      '</div>' +
      '<button class="ark-act" type="button" data-a="all">MUTE ALL</button>' +
      '<div class="ark-opts"></div>' +
      '<div class="ark-note">Restarting throws away the current run.</div>' +
      '<div class="ark-hint" id="ark-pad"></div>' +
    '</div>';
  veil.querySelector('.ark-title').textContent = title;
  document.body.appendChild(veil);

  var tag = bar.querySelector('.ark-tag');
  var AU = (window.Arcade && window.Arcade.audio) || null;

  /* ---- per-game options -------------------------------------------------
     A game registers what it wants to be adjustable and the shell renders it
     into the pause menu, remembers it, and hands back the value. Keeps the
     options in one place rather than each cabinet growing its own menu, and
     means a new game gets the whole apparatus for three lines.

       Arcade.options.define([
         { key:'side',  label:'CONTROLS', type:'toggle', of:['LEFT','RIGHT'], def:'RIGHT' },
         { key:'easy',  label:'EASY MODE', type:'bool', def:false },
         { key:'paint', label:'PAINT', type:'cycle', of:['WHITE','RED','GOLD'], def:'WHITE' }
       ], onChange);
     -------------------------------------------------------------------------- */
  var optDefs = [], optOnChange = null;
  /* ---- KEYED ON THE MACHINE, NOT ON ITS NAME ----------------------------
     This was `effigyarcade.opts.v1.` plus a slug of the cabinet's TITLE, and a
     title is display text. Renaming Highway to Redline Interstate silently
     orphaned every option the player had set, because the key moved with the
     words. Worse, that shape matched none of the patterns `Arcade.save.clear`
     recognises, so erasing a machine left the shell's own settings behind
     while reporting that it had cleared everything.

     `Arcade.scope` is the cabinet's id, declared in its own meta tag. The key
     is now one of the machine's own, so it is erased with the rest of it. */
  var OPT_KEY = 'effigyarcade.' + (A.scope || 'launcher') + '.opts.v1';

  function optAll(){
    try { return JSON.parse(localStorage.getItem(OPT_KEY) || '{}'); } catch(e){ return {}; }
  }
  function optGet(k){
    var v = optAll()[k];
    if (v !== undefined) return v;
    for (var i=0;i<optDefs.length;i++) if (optDefs[i].key === k) return optDefs[i].def;
    return undefined;
  }
  function optSet(k, v){
    var all = optAll(); all[k] = v;
    try { localStorage.setItem(OPT_KEY, JSON.stringify(all)); } catch(e){}
    if (optOnChange) optOnChange(k, v);
  }
  /* ---- the same rows, wherever they are asked for -----------------------
     `paintOpts` only ever looked inside the pause veil, so a game's own title
     OPTIONS screen could not show the same controls and had to say "they are
     in the pause menu" instead. It now paints into ANY `.ark-opts` container
     on the page, which lets a title screen host the identical rows — same
     definitions, same storage, same callback.
     ---------------------------------------------------------------------- */
  function paintOpts(){
    var boxes = document.querySelectorAll('.ark-opts');
    for (var b = 0; b < boxes.length; b++) paintOptsInto(boxes[b]);
  }
  function paintOptsInto(box){
    if (!box) return;
    /* THE BUILD LINE IS PRINTED WHETHER OR NOT THERE ARE OPTIONS. A machine
       with nothing to configure is still a machine somebody is testing, and a
       panel that goes blank takes the build identifier with it. */
    var tag = A.buildTag();
    var foot = '<div class="ark-build' + (tag.indexOf('MIXED') >= 0 ? ' mixed' : '') +
               '">' + tag + '</div>';
    if (!optDefs.length){ box.innerHTML = foot; return; }
    var h = '<div class="ark-sep">OPTIONS</div>';
    for (var i=0;i<optDefs.length;i++){
      var d = optDefs[i], v = optGet(d.key), show;
      /* fall back to the first listed value, not to OFF — a cycle with no
         stored value was rendering as though it were a switch */
      if (d.type === 'bool') show = v ? 'ON' : 'OFF';
      else { if (v === undefined) v = (d.of && d.of[0]) || ''; show = String(v); }
      h += '<button class="ark-act tog' + ((d.type === 'bool' && v) ? ' on' : '') +
           '" type="button" data-opt="' + d.key + '">' + d.label +
           '<b>' + show + '</b></button>';
    }
    box.innerHTML = h + foot;
    var btns = box.querySelectorAll('[data-opt]');
    for (var j=0;j<btns.length;j++){
      btns[j].addEventListener('click', function(){
        var k = this.getAttribute('data-opt'), d = null;
        for (var n=0;n<optDefs.length;n++) if (optDefs[n].key === k) d = optDefs[n];
        if (!d) return;
        var cur = optGet(k);
        if (d.type === 'bool') optSet(k, !cur);
        else {
          var list = d.of || [], at = list.indexOf(cur);
          optSet(k, list[(at + 1) % list.length]);
        }
        paintOpts();
      });
    }
  }

  function paintAudio(){
    if (!AU) return;
    var t = veil.querySelectorAll('.ark-act.tog[data-a]');   /* audio toggles only */
    for (var i=0;i<t.length;i++){
      var k = t[i].getAttribute('data-a'), on = AU.get(k);
      t[i].classList.toggle('on', on);
      t[i].querySelector('b').textContent = on ? 'ON' : 'OFF';
    }
    veil.querySelector('[data-a="all"]').textContent = AU.anyOn() ? 'MUTE ALL' : 'UNMUTE ALL';
  }
  if (AU){ AU.onChange(paintAudio); paintAudio(); }
  paintOpts();

  A.options = {
    define: function(defs, onChange){
      optDefs = defs || [];
      optOnChange = onChange || null;
      /* write the defaults down on first run. Reading them lazily left the
         first paint rendering every control as though it were a switch, and
         only a click put it right. */
      var stored = optAll(), dirty = false;
      for (var d = 0; d < optDefs.length; d++){
        var def = optDefs[d];
        if (stored[def.key] === undefined){
          stored[def.key] = (def.type === 'bool') ? !!def.def
                          : (def.def !== undefined ? def.def : ((def.of && def.of[0]) || ''));
          dirty = true;
        }
      }
      if (dirty){ try { localStorage.setItem(OPT_KEY, JSON.stringify(stored)); } catch(e){} }
      paintOpts();
      /* fire once so the game starts in the state it was left in */
      if (optOnChange) for (var i=0;i<optDefs.length;i++)
        optOnChange(optDefs[i].key, optGet(optDefs[i].key));
    },
    get: optGet,
    set: function(k, v){ optSet(k, v); paintOpts(); },
    /* a game calls this after rendering its own screen containing .ark-opts */
    paint: paintOpts
  };
  /* anything registered before the shell was ready */
  if (A._optQueue){ A.options.define(A._optQueue.defs, A._optQueue.onChange); A._optQueue = null; }

  function setPaused(v){
    if (v === paused) return;
    if (!v) { var cb = held; held = null; if (cb) { try { cb(performance.now()); } catch(e){} } }
    paused = v;
    veil.classList.toggle('on', v);
    tag.textContent = v ? 'PAUSED' : 'RUNNING';
    if (AU){ AU.init(); AU.hush(v); if (v) paintAudio(); }
  }

  bar.querySelector('.ark-btn').addEventListener('click', function(){
    if (AU) AU.init();
    setPaused(!paused);
  });

  /* ---- pad-driven pause menu ---- */
  var acts = [], cursor = 0;
  function refreshActs(){
    acts = [].slice.call(veil.querySelectorAll('.ark-act'));
    paintCursor();
  }
  function paintCursor(){
    for (var i=0;i<acts.length;i++) acts[i].classList.toggle('cursor', i === cursor && A.pad.connected());
  }
  function moveCursor(d){
    if (!acts.length) refreshActs();
    cursor = (cursor + d + acts.length) % acts.length;
    paintCursor();
  }
  refreshActs();

  A.pad.onPress(function(name){
    if (name === 'start'){ if (AU) AU.init(); setPaused(!paused); return; }
    if (!paused){
      if (name === 'back'){ if (AU) AU.init(); setPaused(true); }
      return;
    }
    if (name === 'up')   return moveCursor(-1);
    if (name === 'down') return moveCursor(1);
    if (name === 'b')    return setPaused(false);
    if (name === 'a'){
      if (!acts.length) refreshActs();
      var el = acts[cursor];
      if (el) el.click();
      setTimeout(refreshActs, 0);
    }
  });

  var padHint = document.getElementById('ark-pad');
  function padWatch(){
    var on = A.pad.connected();
    if (padHint) padHint.textContent = on ? 'PAD \u00B7 D-PAD MOVE \u00B7 A SELECT \u00B7 B RESUME \u00B7 START PAUSE' : '';
    if (on) paintCursor();
    setTimeout(padWatch, 700);
  }
  padWatch();
  window.addEventListener('gamepadconnected', function(){
    tag.textContent = 'PAD READY';
    setTimeout(function(){ tag.textContent = paused ? 'PAUSED' : 'RUNNING'; }, 1600);
  });
  /* delegated to the DOCUMENT, not the pause veil: option rows can now live on
     a game's own title screen, and a click there has to work the same way */
  document.addEventListener('click', function(e){
    var el = e.target.closest ? e.target.closest('[data-a]') : e.target;
    var a = el && el.getAttribute('data-a');
    if (a === 'resume') setPaused(false);
    else if (a === 'restart') location.reload();
    else if (a === 'sfx' || a === 'music'){
      if (!AU) return;
      AU.init(); AU.toggle(a);
      (AU.get(a) ? window.Arcade.ui.ok : window.Arcade.ui.off)();
    } else if (a === 'all'){
      if (!AU) return;
      AU.init();
      if (AU.anyOn()){ AU.allOff(); } else { AU.allOn(); window.Arcade.ui.ok(); }
    }
  });
  document.addEventListener('keydown', function(e){
    if (e.key === 'Escape'){ e.preventDefault(); setPaused(!paused); }
  });
  document.addEventListener('visibilitychange', function(){
    if (document.hidden) setPaused(true);
  });

  // the game booted at full height a moment ago — tell it the room shrank
  window.dispatchEvent(new Event('resize'));
  setTimeout(function(){ window.dispatchEvent(new Event('resize')); }, 60);
}

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
else boot();
})();
