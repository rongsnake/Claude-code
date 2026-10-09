/* The Long Ledger — music.js
 * Procedural period soundtrack and sound effects for "The Long Ledger".
 * Everything is synthesised with Web Audio; no external files are loaded.
 *
 * TUNES USED
 *  - rialto:   "La Rotta" opening contour (anon., Italy, 14th c., BL Add. 29987), public domain;
 *              continuation and B section original.
 *  - medici:   original basse danse in the Dufay idiom (fauxbourdon-style), original.
 *  - princes:  "Ronde" opening contour (Tielman Susato, Danserye, 1551), public domain;
 *              romanesca / Greensleeves-type bass (anon., c.1580), public domain; galliard original.
 *  - northern: original ground bass (Purcell idiom, descending tetrachord), original.
 *  - country:  original minuet in the Handel idiom, original.
 *  - lombard:  original march, original rag (Joplin idiom), original swing riff.
 *  - basel:    original cool-jazz vibraphone line, original ambient arpeggio (Reich/Eno idiom).
 */
(function () {
  'use strict';
  if (typeof window === 'undefined') return;
  if (window.LedgerSound && window.LedgerSound._v) return;

  // ---------- persistent state ----------
  var KEY = 'ledger-sound';
  var st = { music: false, sfx: true, vol: 0.6 };
  try {
    var raw = localStorage.getItem(KEY);
    if (raw) {
      var o = JSON.parse(raw);
      if (typeof o.music === 'boolean') st.music = o.music;
      if (typeof o.sfx === 'boolean') st.sfx = o.sfx;
      if (typeof o.vol === 'number') st.vol = Math.min(1, Math.max(0, o.vol));
    }
  } catch (e) {}
  function save() { try { localStorage.setItem(KEY, JSON.stringify(st)); } catch (e) {} }

  // ---------- own seeded PRNG (never Math.random) ----------
  function mulberry32(a) {
    return function () {
      a |= 0; a = a + 0x6D2B79F5 | 0;
      var t = Math.imul(a ^ a >>> 15, 1 | a);
      t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
      return ((t ^ t >>> 14) >>> 0) / 4294967296;
    };
  }
  var rnd = mulberry32(0x1ED6E2);
  function rr(a, b) { return a + (b - a) * rnd(); }

  var era = 'rialto', year = 1300, moodK = 'calm', triumphAt = -1;
  var ctx = null, master, musicBus, sfxBus, comp, eraGain = {};
  var noiseBuf = null, MAXV = 32, timer = null, unlocked = false;
  var vStops = []; // stop times of live voices (pruned against ctx.currentTime; no timer leaks)

  function mtof(m) { return 440 * Math.pow(2, (m - 69) / 12); }
  function nyq(f) { return Math.min(f, ctx.sampleRate * 0.45); }

  // ---------- loudness tables ----------
  // Per-theme output gain, measured so every theme sits near 0.07–0.09 RMS at volume 0.8.
  var THEME_GAIN = {
    rialto: 0.45, medici: 0.55, princes: 1.2, northern: 1.1, country: 0.95,
    march: 1.2, rag: 2.4, swing: 1.0, cool: 0.5, ambient: 2.0
  };
  // Per-effect gain so every effect peaks around 0.25–0.4 at volume 0.8.
  var SFX_GAIN = {
    coin: 3, coins: 2.4, quill: 7, seal: 1.1, bell: 1.6, telegraph: 6, crowd: 6,
    gong: 0.9, page: 6, click: 3, storm: 1.2, cannon: 0.9, fanfare: 1.4
  };

  // ---------- audio graph ----------
  function makeImpulse(sec, decay, bright, seed) {
    var r = mulberry32(seed), len = Math.floor(ctx.sampleRate * sec);
    var b = ctx.createBuffer(2, len, ctx.sampleRate);
    for (var c = 0; c < 2; c++) {
      var d = b.getChannelData(c), lp = 0;
      for (var i = 0; i < len; i++) {
        var n = r() * 2 - 1;
        lp += (n - lp) * bright;          // darken the tail
        d[i] = lp * Math.pow(1 - i / len, decay);
      }
    }
    return b;
  }

  var ROOMS = { // seconds, decay exponent, brightness, wet level
    stone: [3.6, 2.2, 0.25, 0.42], hall: [2.4, 2.6, 0.35, 0.32],
    room: [1.1, 3, 0.5, 0.2], dry: [0.7, 3.5, 0.55, 0.12], plate: [2.2, 2.4, 0.7, 0.3]
  };
  var ERA_ROOM = { rialto: 'stone', medici: 'stone', princes: 'hall', northern: 'hall',
    country: 'room', lombard: 'dry', basel: 'plate' };
  var verbIn = {};

  function build() {
    var AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return false;
    try { ctx = new AC(); } catch (e) { ctx = null; return false; }
    master = ctx.createGain(); master.gain.value = st.vol;
    comp = ctx.createDynamicsCompressor();
    comp.threshold.value = -14; comp.ratio.value = 4; comp.attack.value = 0.005; comp.release.value = 0.25;
    musicBus = ctx.createGain(); musicBus.gain.value = st.music ? 0.8 : 0;
    sfxBus = ctx.createGain(); sfxBus.gain.value = st.sfx ? 0.9 : 0;
    var dry = ctx.createGain(); dry.gain.value = 1;
    musicBus.connect(dry); sfxBus.connect(dry);
    dry.connect(comp);
    // one convolver per room; the active era's room gets the send level
    var s = 1;
    for (var k in ROOMS) {
      var R = ROOMS[k], cv = ctx.createConvolver(), g = ctx.createGain();
      cv.buffer = makeImpulse(R[0], R[1], R[2], 77 + s++);
      g.gain.value = 0;
      musicBus.connect(g); sfxBus.connect(g);
      g.connect(cv); cv.connect(comp);
      verbIn[k] = g;
    }
    comp.connect(master); master.connect(ctx.destination);
    // shared 2 s white noise buffer
    var nl = ctx.sampleRate * 2, r = mulberry32(99);
    noiseBuf = ctx.createBuffer(1, nl, ctx.sampleRate);
    var nd = noiseBuf.getChannelData(0);
    for (var i = 0; i < nl; i++) nd[i] = r() * 2 - 1;
    setRoom(era, 0.05);
    return true;
  }

  function setRoom(e, t) {
    if (!ctx) return;
    var now = ctx.currentTime, want = ERA_ROOM[e];
    for (var k in verbIn) {
      var g = verbIn[k].gain;
      g.cancelScheduledValues(now); g.setValueAtTime(g.value, now);
      g.linearRampToValueAtTime(k === want ? ROOMS[k][3] : 0, now + t);
    }
  }

  // per-era output gain, used for crossfades
  function eraOut(e) {
    if (!eraGain[e]) {
      var g = ctx.createGain(); g.gain.value = 0; g.connect(musicBus); eraGain[e] = g;
    }
    return eraGain[e];
  }

  // ---------- voice helpers ----------
  function env(g, t, a, peak, d, sus, rel, end) {
    g.gain.setValueAtTime(0.0001, t);
    g.gain.linearRampToValueAtTime(peak, t + a);
    g.gain.setTargetAtTime(peak * sus, t + a, d / 3);
    g.gain.setTargetAtTime(0.0001, Math.max(end, t + a), rel / 4);
  }
  function osc(type, f, t, stop, det) {
    var o = ctx.createOscillator(); o.type = type; o.frequency.value = f;
    if (det) o.detune.value = det;
    o.start(t); o.stop(stop); return o;
  }
  function noise(t, stop, off) {
    var s = ctx.createBufferSource(); s.buffer = noiseBuf; s.loop = true;
    s.start(t, off == null ? rnd() * 1.5 : off); s.stop(stop); return s;
  }
  function flt(type, f, q) {
    var b = ctx.createBiquadFilter(); b.type = type; b.frequency.value = nyq(f);
    if (q != null) b.Q.value = q; return b;
  }
  function claim(stop) {
    var now = ctx.currentTime;
    if (vStops.length >= MAXV) vStops = vStops.filter(function (s) { return s > now; });
    if (vStops.length >= MAXV) return false;
    vStops.push(stop);
    return true;
  }

  // ---------- instruments: (dest, midi, t, dur, vel) ----------
  var I = {};
  I.pluck = function (out, m, t, d, v, bright) { // lute/harp: filtered detuned saws with a noise attack
    var f = mtof(m), dec = bright ? 0.9 : 1.6, stop = t + Math.min(d + 0.4, dec + 0.3);
    if (!claim(stop)) return;
    var g = ctx.createGain(), lp = flt('lowpass', f * (bright ? 9 : 5), 1.2);
    lp.frequency.setValueAtTime(nyq(f * (bright ? 14 : 7)), t);
    lp.frequency.exponentialRampToValueAtTime(nyq(f * 1.5), t + dec);
    var o1 = osc(bright ? 'sawtooth' : 'triangle', f, t, stop, -4);
    var o2 = osc('sawtooth', f, t, stop, 5);
    var o2g = ctx.createGain(); o2g.gain.value = bright ? 0.5 : 0.25;
    o1.connect(lp); o2.connect(o2g); o2g.connect(lp);
    var n = noise(t, t + 0.03), ng = ctx.createGain(), nb = flt('bandpass', f * 3, 2);
    ng.gain.setValueAtTime(v * 0.5, t); ng.gain.linearRampToValueAtTime(0.0001, t + 0.025);
    n.connect(nb); nb.connect(ng); ng.connect(out);
    g.gain.setValueAtTime(0.0001, t); g.gain.linearRampToValueAtTime(v * 0.5, t + 0.004);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dec);
    g.gain.setTargetAtTime(0.0001, Math.min(t + d + 0.15, t + dec), 0.05);
    lp.connect(g); g.connect(out);
  };
  I.harpsi = function (out, m, t, d, v) { I.pluck(out, m, t, d, v * 0.8, true); };
  I.flute = function (out, m, t, d, v) { // recorder: sine + soft triangle, breath, delayed vibrato
    var f = mtof(m), stop = t + d + 0.3;
    if (!claim(stop)) return;
    var g = ctx.createGain(), o = osc('sine', f, t, stop), o2 = osc('triangle', f * 2, t, stop);
    var g2 = ctx.createGain(); g2.gain.value = 0.12;
    var lfo = osc('sine', 5.2, t, stop), lg = ctx.createGain();
    lg.gain.setValueAtTime(0, t); lg.gain.linearRampToValueAtTime(f * 0.006, t + Math.min(0.5, d));
    lfo.connect(lg); lg.connect(o.frequency); lg.connect(o2.frequency);
    o.connect(g); o2.connect(g2); g2.connect(g);
    var n = noise(t, stop), nb = flt('bandpass', f * 2, 1.5), ng = ctx.createGain();
    ng.gain.setValueAtTime(0.0001, t); ng.gain.linearRampToValueAtTime(v * 0.08, t + 0.03);
    ng.gain.setTargetAtTime(v * 0.02, t + 0.05, 0.05); ng.gain.setTargetAtTime(0.0001, t + Math.max(d, 0.06), 0.04);
    n.connect(nb); nb.connect(ng); ng.connect(out);
    env(g, t, 0.04, v * 0.32, 0.2, 0.8, 0.15, t + d);
    g.connect(out);
  };
  I.strings = function (out, m, t, d, v, organ) { // viol/drone or organ (8', 4', 2 2/3')
    var f = mtof(m), stop = t + d + 0.8;
    if (!claim(stop)) return;
    var g = ctx.createGain();
    if (organ) {
      [[1, 0.5], [2, 0.25], [3, 0.15]].forEach(function (p) {
        var o = osc('sine', f * p[0], t, stop), og = ctx.createGain(); og.gain.value = p[1];
        o.connect(og); og.connect(g);
      });
      env(g, t, 0.06, v * 0.3, 0.1, 1, 0.2, t + d);
    } else {
      var lp = flt('lowpass', Math.min(5000, f * 4), 0.7);
      [-7, 6].forEach(function (dt) { osc('sawtooth', f, t, stop, dt).connect(lp); });
      lp.connect(g);
      env(g, t, Math.min(0.35, d * 0.4), v * 0.14, 0.3, 0.85, 0.5, t + d);
    }
    g.connect(out);
  };
  I.organ = function (out, m, t, d, v) { I.strings(out, m, t, d, v, true); };
  I.shawm = function (out, m, t, d, v) { // reedy square through bandpass
    var f = mtof(m), stop = t + d + 0.2;
    if (!claim(stop)) return;
    var g = ctx.createGain(), bp = flt('bandpass', 1200, 1.1), lp = flt('lowpass', 3500, 0.5);
    var o = osc('square', f, t, stop, 3), o2 = osc('sawtooth', f, t, stop, -3);
    o.connect(bp); o2.connect(bp); bp.connect(lp); lp.connect(g);
    env(g, t, 0.02, v * 0.22, 0.1, 0.75, 0.08, t + d);
    g.connect(out);
  };
  I.brass = function (out, m, t, d, v) { // saw with fast filter envelope
    var f = mtof(m), stop = t + d + 0.25;
    if (!claim(stop)) return;
    var g = ctx.createGain(), lp = flt('lowpass', f, 2);
    lp.frequency.setValueAtTime(nyq(f * 1.2), t);
    lp.frequency.linearRampToValueAtTime(nyq(f * (3 + v * 4)), t + 0.05);
    lp.frequency.setTargetAtTime(nyq(f * 2.4), t + 0.06, 0.15);
    osc('sawtooth', f, t, stop, -5).connect(lp); osc('sawtooth', f, t, stop, 5).connect(lp);
    lp.connect(g);
    env(g, t, 0.03, v * 0.16, 0.15, 0.7, 0.1, t + d);
    g.connect(out);
  };
  I.piano = function (out, m, t, d, v) { // decaying, slightly inharmonic partials
    var f = mtof(m), dec = Math.max(0.8, 3 - (m - 48) / 20), stop = t + Math.min(d + 0.3, dec);
    if (!claim(stop)) return;
    var g = ctx.createGain(), B = 0.0004;
    [1, 2, 3, 4, 5].forEach(function (n, i) {
      var o = osc(i ? 'sine' : 'triangle', nyq(f * n * Math.sqrt(1 + B * n * n)), t, stop);
      var og = ctx.createGain();
      og.gain.setValueAtTime([0.6, 0.3, 0.15, 0.08, 0.05][i], t);
      og.gain.exponentialRampToValueAtTime(0.001, t + dec / (1 + i * 0.7));
      o.connect(og); og.connect(g);
    });
    g.gain.setValueAtTime(0.0001, t); g.gain.linearRampToValueAtTime(v * 0.3, t + 0.004);
    g.gain.setTargetAtTime(0.0001, t + Math.max(d, 0.01), 0.12);
    g.connect(out);
  };
  I.vibe = function (out, m, t, d, v) { // vibraphone-ish sine bells with tremolo
    var f = mtof(m), stop = t + d + 1.2;
    if (!claim(stop)) return;
    var g = ctx.createGain(), o = osc('sine', f, t, stop), o4 = osc('sine', nyq(f * 4), t, stop);
    var g4 = ctx.createGain();
    g4.gain.setValueAtTime(0.15, t); g4.gain.exponentialRampToValueAtTime(0.001, t + 0.3);
    var tr = ctx.createGain(), lfo = osc('sine', 5, t, stop), lg = ctx.createGain(); lg.gain.value = 0.3;
    tr.gain.value = 0.7; lfo.connect(lg); lg.connect(tr.gain);
    o.connect(tr); o4.connect(g4); g4.connect(tr); tr.connect(g);
    g.gain.setValueAtTime(0.0001, t); g.gain.linearRampToValueAtTime(v * 0.28, t + 0.005);
    g.gain.exponentialRampToValueAtTime(0.002, t + d + 1.1);
    g.connect(out);
  };
  I.pad = function (out, m, t, d, v) { // slow detuned saws with a chorused third voice
    var f = mtof(m), stop = t + d + 2.2;
    if (!claim(stop)) return;
    var g = ctx.createGain(), lp = flt('lowpass', 900, 0.4);
    [-12, 0, 11].forEach(function (dt) {
      var o = osc('sawtooth', f, t, stop, dt), l = osc('sine', 0.2 + rnd() * 0.3, t, stop), lg = ctx.createGain();
      lg.gain.value = 6; l.connect(lg); lg.connect(o.detune); o.connect(lp);
    });
    lp.connect(g);
    env(g, t, Math.min(1.5, d * 0.5), v * 0.07, 0.5, 1, 1.8, t + d);
    g.connect(out);
  };
  I.arp = function (out, m, t, d, v) { // soft synth pluck for the ambient arpeggio
    var f = mtof(m), stop = t + 1.4;
    if (!claim(stop)) return;
    var g = ctx.createGain(), lp = flt('lowpass', 2000, 3);
    lp.frequency.setValueAtTime(3000, t); lp.frequency.exponentialRampToValueAtTime(400, t + 0.8);
    osc('triangle', f, t, stop).connect(lp); osc('square', f, t, stop, 7).connect(lp);
    lp.connect(g);
    g.gain.setValueAtTime(0.0001, t); g.gain.linearRampToValueAtTime(v * 0.1, t + 0.01);
    g.gain.exponentialRampToValueAtTime(0.0005, t + 1.3);
    g.connect(out);
  };
  // --- percussion ---
  function drumHit(out, t, f0, f1, dec, v, nAmt, nf, force) {
    var stop = t + dec + 0.1;
    if (!force && !claim(stop)) return;
    var o = osc('sine', f0, t, stop), g = ctx.createGain();
    o.frequency.setValueAtTime(f0, t); o.frequency.exponentialRampToValueAtTime(f1, t + dec * 0.6);
    g.gain.setValueAtTime(0.0001, t); g.gain.linearRampToValueAtTime(v, t + 0.004);
    g.gain.exponentialRampToValueAtTime(0.0005, t + dec);
    o.connect(g); g.connect(out);
    if (nAmt) {
      var n = noise(t, stop), b = flt('bandpass', nf || 900, 0.8), ng = ctx.createGain();
      ng.gain.setValueAtTime(0.0001, t); ng.gain.linearRampToValueAtTime(v * nAmt, t + 0.003);
      ng.gain.exponentialRampToValueAtTime(0.0005, t + dec * 0.5);
      n.connect(b); b.connect(ng); ng.connect(out);
    }
  }
  I.tabor = function (out, m, t, d, v) { drumHit(out, t, 180, 110, 0.18, v * 0.35, 0.6, 1400); };
  I.timp = function (out, m, t, d, v) { drumHit(out, t, mtof(m) * 1.4, mtof(m), 0.9, v * 0.45, 0.15, 300); };
  I.kick = function (out, m, t, d, v) { drumHit(out, t, 110, 45, 0.35, v * 0.4, 0.05, 2000); };
  I.hat = function (out, m, t, d, v, brush) {
    var len = brush ? 0.18 : 0.05, stop = t + len + 0.05;
    if (!claim(stop)) return;
    var n = noise(t, stop), h = flt(brush ? 'bandpass' : 'highpass', brush ? 4000 : 7000, 0.7), g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, t); g.gain.linearRampToValueAtTime(v * (brush ? 0.08 : 0.07), t + (brush ? 0.03 : 0.002));
    g.gain.exponentialRampToValueAtTime(0.0005, t + len);
    n.connect(h); h.connect(g); g.connect(out);
  };
  I.brush = function (out, m, t, d, v) { I.hat(out, m, t, d, v, true); };

  // ---------- compositions ----------
  // Note strings: "pitch:beats" with pitches as semitones above the era root, 'r' rests.
  // Each piece is a set of sections made of parts.
  function P(s) { // parse "0:1 2:.5 r:1" -> [[semi,beats],...]
    return s.trim().split(/\s+/).map(function (x) {
      var a = x.split(':'); return [a[0] === 'r' ? null : +a[0], +a[1]];
    });
  }
  // Each era: root midi, bpm, beats per bar, sections (A, A', B ...) of parts, form order.
  // Parts: {i: instrument, o: octave offset, n: phrase, v: velocity, tag: 'bright'|'low'|'perc'}
  var ERAS = {
    rialto: { id: 'rialto', root: 62, bpm: 96, form: ['A', 'A2', 'B', 'A', 'B2', 'A2'], sec: {
      // La Rotta-like opening (D Dorian/Mixolydian), drone on D-A
      A: [
        { i: 'flute', o: 12, v: .8, tag: 'bright', n: '0:1 2:1 3:1 5:1 7:2 5:1 3:1 2:1 3:1 2:1 0:1 2:3 r:1 7:1 9:1 10:1 9:1 7:1 5:1 3:1 2:1 0:2 -2:1 0:1 2:4' },
        { i: 'pluck', o: 0, v: .6, n: '0:2 7:2 0:2 7:2 5:2 12:2 7:2 2:2 0:2 7:2 3:2 10:2 7:2 5:2 0:4' },
        { i: 'strings', o: -12, v: .7, tag: 'low', n: '0:32' }, { i: 'strings', o: -5, v: .5, tag: 'low', n: '7:32' },
        { i: 'tabor', perc: 1, v: .8, n: '0:1.5 0:.5 0:1 0:1' }],
      A2: [
        { i: 'flute', o: 12, v: .8, tag: 'bright', n: '0:.5 2:.5 3:1 5:1 7:1 9:1 10:.5 9:.5 7:1 5:1 3:1 5:1 2:2 r:1 7:1 5:1 3:1 2:1 0:1 2:1 3:1 5:1 3:1 2:1 -2:1 0:4' },
        { i: 'pluck', o: 0, v: .6, n: '0:1 7:1 12:1 7:1 5:1 12:1 9:1 5:1 3:1 10:1 7:1 3:1 7:2 2:2 0:1 7:1 12:1 7:1 10:2 5:2 7:2 2:2 0:4' },
        { i: 'strings', o: -12, v: .7, tag: 'low', n: '0:32' }, { i: 'strings', o: -5, v: .5, tag: 'low', n: '7:32' },
        { i: 'tabor', perc: 1, v: .8, n: '0:1 0:.5 0:.5 0:1 r:1' }],
      B: [
        { i: 'flute', o: 12, v: .75, tag: 'bright', n: '7:2 10:1 9:1 7:2 5:1 3:1 5:2 7:1 5:1 3:2 2:2 3:1 5:1 7:1 5:1 3:1 2:1 0:1 -2:1 0:2 2:2 0:4' },
        { i: 'pluck', o: 0, v: .55, n: '-2:2 5:2 -2:2 5:2 3:2 10:2 0:2 7:2 3:2 10:2 -2:2 5:2 0:2 7:2 0:4' },
        { i: 'strings', o: -12, v: .7, tag: 'low', n: '0:32' }, { i: 'strings', o: -5, v: .5, tag: 'low', n: '7:32' },
        { i: 'tabor', perc: 1, v: .7, n: '0:2 0:1 0:1' }],
      B2: [
        { i: 'flute', o: 12, v: .75, tag: 'bright', n: '12:1 10:1 9:1 7:1 9:2 7:1 5:1 7:1 5:1 3:1 2:1 3:2 r:2 5:1 7:1 9:1 7:1 5:1 3:1 2:1 3:1 2:2 -2:2 0:4' },
        { i: 'pluck', o: 0, v: .55, n: '0:2 7:2 5:2 12:2 3:2 10:2 7:2 2:2 5:2 0:2 3:2 -2:2 2:2 7:2 0:4' },
        { i: 'strings', o: -12, v: .7, tag: 'low', n: '0:32' }, { i: 'strings', o: -5, v: .5, tag: 'low', n: '7:32' },
        { i: 'tabor', perc: 1, v: .7, n: '0:1.5 0:.5 0:2' }]
    }},
    medici: { id: 'medici', root: 55, bpm: 70, form: ['A', 'B', 'A2', 'B'], sec: {
      // basse danse: tenor in long notes, upper voices in 6ths/3rds, cadences to G with double leading tone
      A: [
        { i: 'flute', o: 12, v: .7, tag: 'bright', n: '7:2 9:1 11:1 12:2 11:1 9:1 7:2 5:1 4:1 2:2 r:1 4:1 5:2 7:1 9:1 7:2 6:1 4:1 7:4' },
        { i: 'flute', o: 7, v: .45, tag: 'bright', n: '4:2 5:1 7:1 9:2 7:1 5:1 4:2 2:1 0:1 -1:2 r:1 0:1 2:2 4:1 5:1 4:2 2:1 1:1 2:4' },
        { i: 'organ', o: -12, v: .5, tag: 'low', n: '0:4 5:4 0:2 -5:2 -1:2 -3:2 -5:4 -3:4 0:4' },
        { i: 'pluck', o: 0, v: .4, n: '0:1 7:1 4:1 7:1 5:1 9:1 0:1 9:1 0:1 7:1 2:1 7:1 4:1 0:1 2:1 -1:1 0:1 7:1 4:1 7:1 2:1 6:1 2:1 9:1 0:4' }],
      A2: [
        { i: 'flute', o: 12, v: .7, tag: 'bright', n: '12:1.5 11:.5 9:1 7:1 9:2 11:1 12:1 14:2 12:1 11:1 9:2 7:2 9:1 11:1 12:1 9:1 11:2 9:1.5 11:.5 12:4' },
        { i: 'flute', o: 7, v: .45, tag: 'bright', n: '9:1.5 7:.5 5:1 4:1 5:2 7:1 9:1 11:2 9:1 7:1 5:2 4:2 5:1 7:1 9:1 5:1 7:2 6:2 7:4' },
        { i: 'organ', o: -12, v: .5, tag: 'low', n: '0:4 5:2 7:2 0:2 5:2 2:4 5:4 2:4 0:4' },
        { i: 'pluck', o: 0, v: .4, n: '0:1 4:1 7:1 4:1 5:1 9:1 2:1 7:1 0:1 4:1 9:1 5:1 2:1 7:1 2:1 9:1 0:4' }],
      B: [
        { i: 'flute', o: 12, v: .7, tag: 'bright', n: '9:2 10:1 9:1 7:2 5:2 7:1 9:1 10:2 9:2 r:1 5:1 7:2 9:1 7:1 5:2 4:2 5:4' },
        { i: 'flute', o: 7, v: .45, tag: 'bright', n: '5:2 7:1 5:1 4:2 2:2 3:1 5:1 7:2 5:2 r:1 2:1 4:2 5:1 4:1 2:2 0:2 0:4' },
        { i: 'organ', o: -12, v: .5, tag: 'low', n: '-7:4 -2:4 3:4 -2:4 -5:4 0:4 -7:4' },
        { i: 'pluck', o: 0, v: .4, n: '5:1 9:1 0:1 9:1 3:1 7:1 10:1 7:1 2:1 5:1 10:1 5:1 0:1 4:1 7:1 4:1 0:1 5:1 9:1 5:1 0:1 4:1 7:1 4:1 5:4' }]
    }},
    princes: { id: 'princes', root: 57, bpm: 112, form: ['A', 'A2', 'B', 'B2', 'A'], sec: {
      // Susato-like Ronde (duple) / romanesca B section
      A: [
        { i: 'shawm', o: 12, v: .7, tag: 'bright', n: '3:1 3:1 5:1 7:1 8:2 7:1 5:1 3:1 5:1 7:1 3:1 2:2 0:2 3:1 3:1 5:1 7:1 8:1 10:1 8:1 7:1 5:1 3:1 2:1 3:1 3:4' },
        { i: 'brass', o: 0, v: .5, n: '0:2 -2:2 3:2 -2:2 0:2 -5:2 -2:4 0:2 -2:2 -4:2 -5:2 -4:2 -5:2 -9:4' },
        { i: 'strings', o: -12, v: .5, tag: 'low', n: '-9:4 -14:4 -9:4 -14:4 -9:4 -7:4 -5:2 -14:2 -9:4' },
        { i: 'tabor', perc: 1, v: .8, n: '0:1 0:.5 0:.5 0:1 0:1' }],
      A2: [
        { i: 'shawm', o: 12, v: .7, tag: 'bright', n: '3:.5 2:.5 3:1 5:.5 3:.5 5:1 7:1 8:.5 7:.5 8:1 7:1 5:1 3:1 2:1 0:2 3:.5 5:.5 7:1 8:.5 10:.5 12:1 10:1 8:1 7:1 5:1 3:1 2:1 3:4' },
        { i: 'brass', o: 0, v: .5, n: '0:2 -2:2 3:2 -2:2 0:2 -5:2 -2:4 0:2 3:2 -4:2 -5:2 -4:2 -5:2 -9:4' },
        { i: 'strings', o: -12, v: .5, tag: 'low', n: '-9:4 -14:4 -9:4 -14:4 -9:4 -7:4 -5:2 -14:2 -9:4' },
        { i: 'tabor', perc: 1, v: .8, n: '0:.5 0:.5 0:1 0:1 0:.5 0:.5' }],
      B: [ // romanesca-type: III VII i V
        { i: 'shawm', o: 12, v: .65, tag: 'bright', n: '7:2 10:1 12:1 10:2 8:1 7:1 5:2 7:1 8:1 7:2 3:2 2:2 3:1 5:1 7:1 5:1 3:1 2:1 0:1 -1:1 0:2 2:2 3:2 2:2 0:4' },
        { i: 'pluck', o: 0, v: .5, n: '3:1 7:1 10:1 7:1 -2:1 2:1 5:1 2:1 0:1 3:1 7:1 3:1 -5:1 -1:1 2:1 -1:1 3:1 7:1 10:1 7:1 -2:1 2:1 5:1 2:1 0:1 3:1 -5:1 -1:1 0:4' },
        { i: 'strings', o: -12, v: .5, tag: 'low', n: '-9:4 -14:4 -12:4 -17:4 -9:4 -14:4 -12:2 -17:2 -12:4' },
        { i: 'tabor', perc: 1, v: .7, n: '0:1.5 0:.5 0:2' }],
      B2: [ // galliard lilt (hemiola in 6 beats feel)
        { i: 'flute', o: 12, v: .65, tag: 'bright', n: '7:1 8:1 10:1 12:1.5 10:.5 8:1 7:2 5:1 3:1 5:1 7:1 5:2 3:1 2:1 3:1 5:1 7:1 5:1 3:1 2:1 0:1 -1:1 0:2 2:2 3:2 2:2 0:4' },
        { i: 'shawm', o: 0, v: .45, n: '3:2 -2:2 0:2 -5:2 3:2 -2:2 0:2 -5:2 3:2 -2:2 0:1 -5:1 0:4' },
        { i: 'strings', o: -12, v: .5, tag: 'low', n: '-9:4 -14:4 -12:4 -17:4 -9:4 -14:4 -12:2 -17:2 -12:4' },
        { i: 'tabor', perc: 1, v: .7, n: '0:1 0:1 0:.5 0:.5 0:1' }]
    }},
    northern: { id: 'northern', root: 55, bpm: 72, form: ['A', 'A2', 'B', 'A3'], sec: {
      // original descending-tetrachord ground in G minor (repeats under each section)
      A: [
        { i: 'strings', o: -12, v: .6, tag: 'low', n: '0:2 -2:2 -4:2 -5:2 -7:2 -9:1 -10:1 -5:4' },
        { i: 'harpsi', o: 0, v: .5, n: '3:.5 7:.5 12:1 2:.5 7:.5 10:1 0:.5 5:.5 8:1 -1:.5 2:.5 7:1 -2:.5 3:.5 7:1 -3:.5 0:.5 5:.5 2:.5 -1:1 2:1 7:2' },
        { i: 'strings', o: 12, v: .45, tag: 'bright', n: 'r:2 10:2 8:2 7:1 8:1 10:2 12:1 10:1 9:2 7:4' }],
      A2: [
        { i: 'strings', o: -12, v: .6, tag: 'low', n: '0:2 -2:2 -4:2 -5:2 -7:2 -9:1 -10:1 -5:4' },
        { i: 'harpsi', o: 0, v: .5, n: '3:.5 7:.5 12:1 2:.5 7:.5 10:1 0:.5 5:.5 8:1 -1:.5 2:.5 7:1 -2:.5 3:.5 7:1 -3:.5 0:.5 5:.5 2:.5 -1:1 2:1 7:2' },
        { i: 'strings', o: 12, v: .45, tag: 'bright', n: '15:1 14:.5 12:.5 14:1 10:1 12:1 11:.5 9:.5 11:1 7:1 8:1.5 10:.5 7:1 5:1 3:1.5 2:.5 2:2 r:2' }],
      B: [
        { i: 'strings', o: -12, v: .6, tag: 'low', n: '0:2 -2:2 -4:2 -5:2 -7:2 -9:1 -10:1 -5:4' },
        { i: 'harpsi', o: 0, v: .5, n: '7:1 3:1 5:1 2:1 3:1 0:1 2:1 -1:1 0:1 -4:1 -3:1 0:1 2:2 -1:2' },
        { i: 'flute', o: 12, v: .5, tag: 'bright', n: '7:2 8:1 7:1 5:2 3:1 2:1 3:2 5:1 3:1 2:1 0:1 -1:2' }],
      A3: [
        { i: 'strings', o: -12, v: .6, tag: 'low', n: '0:2 -2:2 -4:2 -5:2 -7:2 -9:1 -10:1 -5:4' },
        { i: 'harpsi', o: 0, v: .5, n: '12:.5 10:.5 7:.5 3:.5 10:.5 7:.5 2:.5 7:.5 8:.5 5:.5 0:.5 5:.5 7:.5 2:.5 -1:.5 2:.5 3:.5 7:.5 0:.5 3:.5 5:.5 0:.5 2:.5 -1:.5 2:4' },
        { i: 'strings', o: 12, v: .45, tag: 'bright', n: '12:2 10:2 8:2 7:2 5:2 3:1 2:1 2:2 0:2' }]
    }},
    country: { id: 'country', root: 62, bpm: 108, bar: 3, form: ['A', 'A2', 'B', 'A2'], sec: {
      // minuet in D, 3/4; strings + harpsichord (piano after 1790)
      A: [
        { i: 'strings', o: 12, v: .5, tag: 'bright', n: '7:1 4:.5 5:.5 7:1 12:2 11:1 9:1 11:.5 12:.5 14:1 7:3 9:1 7:.5 5:.5 4:1 5:1 4:.5 2:.5 0:1 2:1 4:1 2:2 r:1' },
        { i: 'KEYS', o: 0, v: .45, n: '0:1 4:1 7:1 4:1 7:1 12:1 5:1 9:1 12:1 -1:1 5:1 7:1 5:1 9:1 12:1 0:1 4:1 7:1 -5:1 2:1 5:1 -5:1 -1:1 2:1' },
        { i: 'strings', o: -12, v: .5, tag: 'low', n: '0:3 0:3 5:3 7:3 5:3 0:3 -5:3 -5:3' }],
      A2: [
        { i: 'strings', o: 12, v: .5, tag: 'bright', n: '7:1 9:.5 11:.5 12:1 14:1 12:1 11:1 9:1 7:1 5:1 4:2 r:1 5:1 7:1 9:1 7:1 5:1 4:1 2:1 4:.5 2:.5 -1:1 0:3' },
        { i: 'KEYS', o: 0, v: .45, n: '0:1 4:1 7:1 4:1 7:1 12:1 5:1 9:1 12:1 0:1 4:1 7:1 5:1 9:1 12:1 0:1 4:1 7:1 -5:1 2:1 5:1 0:1 4:1 7:1' },
        { i: 'strings', o: -12, v: .5, tag: 'low', n: '0:3 0:3 5:3 0:3 5:3 0:3 -5:3 0:3' }],
      B: [
        { i: 'strings', o: 12, v: .5, tag: 'bright', n: '9:1 10:1 12:1 10:2 9:1 7:1 9:1 10:1 9:2 7:1 5:1 7:1 9:1 7:1 5:1 4:1 2:1 4:1 6:1 7:3' },
        { i: 'KEYS', o: 0, v: .45, n: '2:1 5:1 9:1 3:1 7:1 10:1 0:1 3:1 7:1 2:1 5:1 9:1 -2:1 2:1 5:1 -3:1 0:1 4:1 2:1 6:1 9:1 -5:1 2:1 7:1' },
        { i: 'strings', o: -12, v: .5, tag: 'low', n: '2:3 3:3 0:3 2:3 -2:3 -3:3 2:3 -5:3' }]
    }},
    lombard: { id: 'march', root: 60, bpm: 104, form: ['A', 'B', 'A2', 'B'], sec: {
      // Victorian march (brass band) in C; replaced by rag/swing variants after 1900/1925
      A: [
        { i: 'brass', o: 12, v: .6, tag: 'bright', n: '7:1.5 7:.5 12:1 11:.5 9:.5 7:2 4:1 5:1 7:1.5 9:.5 7:1 5:1 4:2 2:2 7:1.5 7:.5 12:1 14:1 16:1.5 14:.5 12:1 11:1 9:1 11:1 14:1 11:1 12:4' },
        { i: 'brass', o: 0, v: .4, n: '4:2 4:2 5:2 4:2 5:2 2:2 2:2 -1:2 4:2 4:2 7:2 4:2 5:2 5:2 4:4' },
        { i: 'brass', o: -24, v: .55, tag: 'low', n: '0:1 7:1 0:1 7:1 5:1 0:1 0:1 7:1 2:1 7:1 -5:1 7:1 0:1 7:1 0:1 7:1 5:1 9:1 0:1 7:1 2:1 7:1 -5:1 2:1 0:2 -12:2' },
        { i: 'timp', perc: 1, m: 36, v: .5, n: '0:2 0:2' }, { i: 'hat', perc: 1, v: .5, n: 'r:1 0:1 r:1 0:1' }],
      A2: [
        { i: 'brass', o: 12, v: .6, tag: 'bright', n: '4:1 5:1 7:1 12:1 11:1.5 9:.5 7:2 9:1 11:1 12:1 14:1 12:1 11:1 9:2 7:1 4:1 5:1 7:1 9:1 12:1 11:1 9:1 7:1 5:1 2:1 4:1 0:4' },
        { i: 'brass', o: 0, v: .4, n: '0:2 4:2 4:2 5:2 5:2 7:2 2:2 -1:2 0:2 4:2 5:2 4:2 2:2 -1:2 0:4' },
        { i: 'brass', o: -24, v: .55, tag: 'low', n: '0:1 7:1 0:1 7:1 5:1 0:1 0:1 7:1 2:1 7:1 -5:1 7:1 0:1 7:1 0:1 7:1 5:1 9:1 0:1 7:1 2:1 7:1 -5:1 2:1 0:2 -12:2' },
        { i: 'timp', perc: 1, m: 36, v: .5, n: '0:2 0:2' }, { i: 'hat', perc: 1, v: .5, n: 'r:1 0:1 r:1 0:1' }],
      B: [ // trio in F on parlour piano
        { i: 'piano', o: 12, v: .5, tag: 'bright', n: '9:2 10:1 9:1 7:2 5:2 2:1 4:1 5:1 7:1 9:4 9:2 12:1 10:1 9:1 7:1 5:1 4:1 2:2 4:2 5:4' },
        { i: 'piano', o: 0, v: .35, n: '5:1 9:1 12:1 9:1 5:1 9:1 12:1 9:1 7:1 10:1 14:1 10:1 5:1 9:1 12:1 9:1 2:1 5:1 9:1 5:1 7:1 10:1 14:1 10:1 0:1 4:1 7:1 10:1 5:4' },
        { i: 'brass', o: -24, v: .5, tag: 'low', n: '5:2 0:2 5:2 0:2 -2:2 5:2 5:2 0:2 2:2 9:2 -2:2 5:2 0:2 7:2 5:4' },
        { i: 'timp', perc: 1, m: 41, v: .4, n: '0:4' }]
    }},
    basel: { id: 'cool', root: 53, bpm: 84, form: ['A', 'B', 'A2', 'B'], sec: {
      // 1950s cool jazz: vibe line, walking bass, brushes (F major ii-V-I colour)
      A: [
        { i: 'vibe', o: 12, v: .6, tag: 'bright', n: '9:1.5 7:.5 4:1 2:1 r:1 11:.5 9:.5 7:2 r:1 14:1.5 12:.5 9:1 7:1.5 4:.5 5:3' },
        { i: 'piano', o: 0, v: .25, n: 'r:1 7:1.5 r:1.5 r:1 7:1.5 r:1.5 r:1 4:1.5 r:1.5 r:1 4:3' },
        { i: 'piano', o: 4, v: .22, n: 'r:1 10:1.5 r:1.5 r:1 11:1.5 r:1.5 r:1 9:1.5 r:1.5 r:1 9:3' },
        { i: 'pluck', o: -24, v: .7, tag: 'low', n: '7:1 9:1 10:1 11:1 12:1 11:1 9:1 7:1 5:1 7:1 9:1 10:1 12:1 9:1 7:1 4:1' },
        { i: 'brush', perc: 1, v: .7, n: '0:1 0:.66 0:.34 0:1 0:.66 0:.34' }],
      A2: [
        { i: 'vibe', o: 12, v: .6, tag: 'bright', n: '12:1 9:1 7:.66 9:.34 12:1 14:2 12:1 10:1 9:1.5 7:.5 4:1 2:1 0:2' },
        { i: 'piano', o: 0, v: .25, n: 'r:1 7:1.5 r:1.5 r:1 7:1.5 r:1.5 r:1 4:1.5 r:1.5 r:1 4:3' },
        { i: 'pluck', o: -24, v: .7, tag: 'low', n: '2:1 4:1 5:1 6:1 7:1 5:1 4:1 2:1 0:1 2:1 4:1 5:1 7:1 4:1 2:1 -1:1' },
        { i: 'brush', perc: 1, v: .7, n: '0:1 0:.66 0:.34 0:1 0:.66 0:.34' }],
      B: [
        { i: 'vibe', o: 12, v: .55, tag: 'bright', n: '10:2 8:1 7:1 5:2 r:2 9:2 7:1 5:1 4:4' },
        { i: 'piano', o: 0, v: .25, n: 'r:1 5:1.5 r:1.5 r:1 3:1.5 r:1.5 r:1 7:1.5 r:1.5 r:1 4:3' },
        { i: 'pluck', o: -24, v: .7, tag: 'low', n: '10:1 8:1 7:1 5:1 3:1 5:1 7:1 8:1 9:1 7:1 5:1 4:1 0:1 2:1 4:1 7:1' },
        { i: 'brush', perc: 1, v: .7, n: '0:1 0:.66 0:.34 0:1 0:.66 0:.34' }]
    }}
  };

  // Alternative later-period pieces selected by year
  var RAG = { id: 'rag', root: 60, bpm: 92, form: ['A', 'A', 'B', 'A'], sec: {
    A: [ // syncopated right hand over oom-pah left hand (original, Joplin idiom)
      { i: 'piano', o: 12, v: .5, tag: 'bright', n: '4:.5 7:.25 12:.5 7:.25 12:.5 4:.5 7:.25 12:.5 7:.25 12:.5 5:.5 9:.25 12:.5 9:.25 12:.5 5:.5 9:.25 14:.5 12:.25 9:.5 7:.5 11:.25 14:.5 11:.25 14:.5 7:.5 11:.25 14:.5 11:.25 14:.5 12:.5 16:.25 19:.5 16:.25 12:.5 7:2' },
      { i: 'piano', o: -12, v: .4, tag: 'low', n: '-12:.5 7:.5 -5:.5 7:.5 -12:.5 7:.5 -5:.5 7:.5 -7:.5 9:.5 -3:.5 9:.5 -7:.5 9:.5 -3:.5 9:.5 -5:.5 11:.5 2:.5 11:.5 -5:.5 11:.5 2:.5 11:.5 -12:.5 7:.5 -5:.5 7:.5 -12:1 -5:1' }],
    B: [
      { i: 'piano', o: 12, v: .5, tag: 'bright', n: '9:.5 10:.25 9:.5 5:.25 9:.5 12:1 10:.5 9:.25 7:.5 5:.25 7:.5 9:1.5 r:.5 7:.5 9:.25 7:.5 4:.25 7:.5 11:1 9:.5 7:.25 5:.5 2:.25 4:.5 0:1.5 r:.5' },
      { i: 'piano', o: -12, v: .4, tag: 'low', n: '-7:.5 9:.5 0:.5 9:.5 -7:.5 9:.5 0:.5 9:.5 -5:.5 7:.5 -1:.5 7:.5 -5:.5 7:.5 -1:.5 7:.5 -5:.5 11:.5 2:.5 11:.5 -5:.5 11:.5 2:.5 11:.5 -12:.5 7:.5 -5:.5 7:.5 -12:1 -5:1' }]
  }};
  var SWING = { id: 'swing', root: 58, bpm: 120, swing: 1, form: ['A', 'B', 'A', 'B'], sec: {
    A: [
      { i: 'brass', o: 12, v: .4, tag: 'bright', n: 'r:1 7:.5 9:.5 r:.5 7:1 4:1.5 r:1 7:.5 9:.5 12:.5 9:1 7:1.5 r:1 5:.5 7:.5 r:.5 5:1 2:1.5 0:2 r:2' },
      { i: 'piano', o: 0, v: .25, n: 'r:1 4:1 r:1 4:1 r:1 4:1 r:1 4:1 r:1 5:1 r:1 5:1 r:1 4:1 r:1 4:1' },
      { i: 'pluck', o: -24, v: .7, tag: 'low', n: '0:1 4:1 7:1 9:1 0:1 4:1 7:1 4:1 2:1 5:1 9:1 5:1 7:1 5:1 4:1 2:1' },
      { i: 'brush', perc: 1, v: .7, n: '0:1 0:.66 0:.34 0:1 0:.66 0:.34' }],
    B: [
      { i: 'brass', o: 12, v: .4, tag: 'bright', n: 'r:1 12:.5 10:.5 r:.5 9:1 5:1.5 r:1 9:.5 7:.5 5:.5 4:1 2:1.5 r:1 4:.5 5:.5 7:1 9:1 7:2 r:2' },
      { i: 'piano', o: 0, v: .25, n: 'r:1 5:1 r:1 5:1 r:1 5:1 r:1 5:1 r:1 4:1 r:1 4:1 r:1 7:1 r:1 7:1' },
      { i: 'pluck', o: -24, v: .7, tag: 'low', n: '5:1 9:1 12:1 9:1 5:1 4:1 2:1 0:1 -5:1 -1:1 2:1 5:1 7:1 5:1 2:1 -1:1' },
      { i: 'brush', perc: 1, v: .7, n: '0:1 0:.66 0:.34 0:1 0:.66 0:.34' }]
  }};
  var AMBIENT = { id: 'ambient', root: 57, bpm: 76, form: ['A', 'A2', 'B', 'A2'], sec: {
    A: [ // slow additive arpeggio (Reich/Eno idiom, original)
      { i: 'arp', o: 12, v: .6, tag: 'bright', n: '0:.5 7:.5 12:.5 14:.5 7:.5 12:.5 16:.5 14:.5 0:.5 7:.5 12:.5 14:.5 7:.5 12:.5 19:.5 14:.5' },
      { i: 'pad', o: -12, v: .7, tag: 'low', n: '0:8 -4:8' }, { i: 'pad', o: 0, v: .5, n: '7:8 8:8' },
      { i: 'kick', perc: 1, v: .35, n: '0:4' }],
    A2: [
      { i: 'arp', o: 12, v: .6, tag: 'bright', n: '0:.5 7:.5 12:.5 15:.5 7:.5 12:.5 17:.5 15:.5 3:.5 7:.5 12:.5 15:.5 10:.5 12:.5 19:.5 15:.5' },
      { i: 'pad', o: -12, v: .7, tag: 'low', n: '-4:8 -7:8' }, { i: 'pad', o: 0, v: .5, n: '3:8 5:8' },
      { i: 'kick', perc: 1, v: .35, n: '0:4' }, { i: 'hat', perc: 1, v: .3, n: 'r:.5 0:.5 r:.5 0:.5 r:.5 0:.5 r:.5 0:.5' }],
    B: [
      { i: 'arp', o: 12, v: .55, tag: 'bright', n: '-2:.5 5:.5 10:.5 14:.5 5:.5 10:.5 12:.5 14:.5 -5:.5 2:.5 7:.5 10:.5 2:.5 7:.5 14:.5 10:.5' },
      { i: 'pad', o: -12, v: .7, tag: 'low', n: '-2:8 -5:8' }, { i: 'pad', o: 0, v: .5, n: '5:8 2:8' },
      { i: 'kick', perc: 1, v: .35, n: '0:4' }]
  }};

  // Parse all note strings once. Section length = longest non-percussion part, measured
  // without trailing rests and rounded up to whole bars; any part shorter than the section
  // repeats (truncated) so no section ends in dead air.
  function prep(pc) {
    var bar = pc.bar || 4;
    Object.keys(pc.sec).forEach(function (k) {
      var L = 0;
      pc.sec[k].forEach(function (p) {
        p.N = P(p.n).filter(function (x) { return isFinite(x[1]) && x[1] > 0 && (x[0] === null || isFinite(x[0])); });
        p.len = 0; var sound = 0;
        p.N.forEach(function (x) { p.len += x[1]; if (x[0] !== null) sound = p.len; });
        p.len = Math.round(p.len * 1000) / 1000;
        if (!p.perc) L = Math.max(L, sound);
      });
      pc.sec[k].L = Math.max(bar, Math.ceil(L / bar - 0.01) * bar);
    });
  }
  [RAG, SWING, AMBIENT].forEach(prep);
  Object.keys(ERAS).forEach(function (k) { prep(ERAS[k]); });

  function pieceFor(e) {
    if (e === 'lombard') return year >= 1925 ? SWING : year >= 1900 ? RAG : ERAS.lombard;
    if (e === 'basel') return year >= 1980 ? AMBIENT : ERAS.basel;
    return ERAS[e];
  }

  // ---------- mood transforms ----------
  // tension: lower 3rd/6th/7th degrees (minor/phrygian colour), drop bright voices, add heartbeat
  function moodPitch(s) {
    if (moodK !== 'tension' && moodK !== 'grief') return s;
    var pc = ((s % 12) + 12) % 12;
    if (pc === 4 || pc === 9 || pc === 11) return s - 1;
    if (moodK === 'tension' && pc === 2) return s - 1; // phrygian second
    return s;
  }

  // ---------- scheduler ----------
  // A "player" walks one piece; on era change a new player starts and the old fades out.
  // Each player owns a theme-gain node (THEME_GAIN) feeding the era crossfade gain.
  var player = null, old = [];
  function newPlayer(e, startAt) {
    var pc = pieceFor(e), tg = ctx.createGain();
    tg.gain.value = THEME_GAIN[pc.id] || 1; tg.connect(eraOut(e));
    return { era: e, pc: pc, form: 0, secStart: startAt, out: tg, cyc: 0, queued: false };
  }
  function fadeEra(e, to, t) {
    var g = eraOut(e).gain, now = ctx.currentTime;
    g.cancelScheduledValues(now); g.setValueAtTime(g.value, now);
    g.linearRampToValueAtTime(to, now + t);
  }
  function spbOf(pc) { return 60 / (pc.bpm * (moodK === 'grief' ? 0.7 : 1)); }

  // Schedule whole sections back to back; the next section is always queued as soon as the
  // current one is fully inside the look-ahead, so the loop never waits on a missing bar.
  function scheduleSection(pl, tEnd) {
    var pc = pl.pc, guard = 0;
    while (pl.secStart < tEnd && guard++ < 8) {
      var sec = pc.sec[pc.form[pl.form % pc.form.length]], spb = spbOf(pc), secDur = sec.L * spb;
      if (!(secDur > 0)) { pl.form++; continue; }
      if (!pl.queued) { queueSection(pl, sec, pl.secStart, spb); pl.queued = true; }
      if (pl.secStart + secDur <= tEnd + 0.05) {
        pl.secStart += secDur; pl.form++; pl.queued = false;
        if (pl.form % pc.form.length === 0) pl.cyc++;
      } else break;
    }
  }

  // Notes are pushed into a time-sorted queue, then released into Web Audio just-in-time.
  var queue = [];
  function queueSection(pl, sec, t0, spb) {
    var swing = pl.pc.swing, cycle = pl.cyc;
    sec.forEach(function (p, pi) {
      var bright = p.tag === 'bright', low = p.tag === 'low';
      // variation: on alternate cycles the lute/keys part rests in A sections for breathing room
      if (!bright && !low && !p.perc && cycle % 2 === 1 && pi === 1 && sec.L > 8 && (pl.form % 3 === 1)) return;
      if (!(p.len > 0)) return;
      var reps = Math.max(1, Math.ceil(sec.L / p.len - 0.001));
      var b = 0;
      for (var r = 0; r < reps; r++) {
        for (var j = 0; j < p.N.length; j++) {
          var nt = p.N[j], beat = b; b += nt[1];
          if (nt[0] == null || beat >= sec.L - 0.001) continue;
          var bt = beat, dur = Math.min(nt[1], sec.L - beat);
          if (swing) { var fr = bt % 1; if (Math.abs(fr - 0.5) < 0.01) bt += 0.16; }
          queue.push({ t: t0 + bt * spb, d: dur * spb * 0.95, p: p, s: nt[0], pl: pl, beat: beat });
        }
      }
    });
    queue.sort(function (a, b) { return a.t - b.t; });
  }

  function playNote(n) {
    var p = n.p, pl = n.pl, inst = p.i;
    if (pl !== player && old.indexOf(pl) < 0) return;
    if (moodK === 'tension' && p.tag === 'bright' && !p.perc) return;
    if (moodK === 'grief' && (p.perc || (p.tag !== 'low' && (n.beat % 2) !== 0))) return;
    if (inst === 'KEYS') inst = year >= 1790 ? 'piano' : 'harpsi';
    if (!I[inst]) return;
    var hum = rr(-0.008, 0.008), t = Math.max(ctx.currentTime + 0.005, n.t + hum);
    var vel = p.v * rr(0.85, 1.05) * (n.beat % (pl.pc.bar || 4) === 0 ? 1.1 : 0.95);
    if (moodK === 'grief') vel *= 0.7;
    if (p.perc) { I[inst](pl.out, p.m || 40, t, 0.2, vel); return; }
    var m = pl.pc.root + (p.o || 0) + moodPitch(n.s);
    if (moodK === 'grief') m -= 12 * (p.tag === 'low' ? 0 : 1) - (m < 48 ? 12 : 0);
    var d = Math.max(0.05, n.d);
    if (!isFinite(m) || !isFinite(t) || !isFinite(vel) || !isFinite(d)) return; // never poison the graph
    I[inst](pl.out, m, t, d, vel);
  }

  var heartNext = 0;
  function tick() {
    if (!ctx || document.hidden) return;
    var now = ctx.currentTime, ahead = now + 0.2;
    if (st.music && player) {
      // a player that fell behind (stalled timer, resumed context) restarts at "now"
      if (player.secStart < now - 1 && !player.queued) player.secStart = now + 0.05;
      scheduleSection(player, ahead);
      while (queue.length && queue[0].t < ahead) {
        var n = queue.shift();
        if (n.t > now - 0.05) { try { playNote(n); } catch (e) {} }
      }
      // tension heartbeat: timpani lub-dub + low pulse
      if (moodK === 'tension') {
        if (heartNext < now) heartNext = now + 0.05;
        while (heartNext < ahead) {
          I.timp(player.out, player.pc.root - 24, heartNext, 0.3, 0.8);
          I.timp(player.out, player.pc.root - 24, heartNext + 0.28, 0.3, 0.55);
          heartNext += 1.4;
        }
      }
    } else { queue.length = 0; }
  }

  function startPlayer() {
    if (!ctx) return;
    var t = ctx.currentTime + 0.1;
    if (player) {
      var op = player; old.push(op);
      if (op.era !== era) fadeEra(op.era, 0, 3);
      else ramp(op.out.gain, 0, 2.5);
      setTimeout(function () {
        var i = old.indexOf(op); if (i >= 0) old.splice(i, 1);
        try { op.out.disconnect(); } catch (e) {}
      }, 3500);
    }
    queue = queue.filter(function (n) { return n.t < t + 3 && old.indexOf(n.pl) >= 0; });
    player = newPlayer(era, t + (old.length ? 0.6 : 0));
    fadeEra(era, 1, old.length ? 3 : 0.5);
    setRoom(era, 3);
  }

  function ensureTimer() {
    if (timer || !ctx) return;
    timer = setInterval(tick, 25);
  }

  // ---------- triumph flourish ----------
  function flourish() {
    if (!ctx || !st.music) return;
    var pc = pieceFor(era), r = pc.root, t = ctx.currentTime + 0.05;
    var out = player && player.era === era ? player.out : eraOut(era);
    var inst = { rialto: 'flute', medici: 'flute', princes: 'brass', northern: 'harpsi',
      country: year >= 1790 ? 'piano' : 'harpsi', lombard: 'brass', basel: year >= 1980 ? 'arp' : 'vibe' }[era];
    var line = [[7, .25], [9, .25], [11, .25], [12, .5], [14, .25], [11, .25], [12, 1.2]];
    var s = 60 / pc.bpm, tt = t;
    line.forEach(function (x) { I[inst](out, r + 12 + x[0], tt, x[1] * s * 1.6, 0.7); tt += x[1] * s * 1.6; });
    // V - I cadence underneath
    I.strings(out, r - 5, t, (tt - t) * 0.6, 0.6);
    I.strings(out, r - 12, t + (tt - t) * 0.6, (tt - t) * 0.6, 0.7);
    I.strings(out, r + 4, t + (tt - t) * 0.6, (tt - t) * 0.6, 0.5);
  }

  // ---------- SFX ----------
  // Each call routes through its own gain node (SFX_GAIN) so loudness is set in one table.
  var sfxDest = null;
  function sOut() { return sfxDest || sfxBus; }
  var SFX = {
    coin: function (t, v) { // FM ping + second bounce
      [0, 0.11].forEach(function (dt, k) {
        var tt = t + dt, f = 2350 * (k ? 1.04 : 1), stop = tt + 0.35;
        var c = osc('sine', f, tt, stop), m = osc('sine', f * 1.41, tt, stop), mg = ctx.createGain(), g = ctx.createGain();
        mg.gain.setValueAtTime(f * 1.5, tt); mg.gain.exponentialRampToValueAtTime(10, tt + 0.2);
        m.connect(mg); mg.connect(c.frequency);
        g.gain.setValueAtTime(0.0001, tt); g.gain.linearRampToValueAtTime((v || 1) * (k ? 0.08 : 0.14), tt + 0.002);
        g.gain.exponentialRampToValueAtTime(0.0005, tt + 0.32);
        c.connect(g); g.connect(sOut());
      });
    },
    coins: function (t) { for (var i = 0; i < 5; i++) SFX.coin(t + i * 0.06 + rr(0, 0.03), rr(0.5, 0.9)); },
    quill: function (t) {
      for (var i = 0; i < 4; i++) {
        var tt = t + i * 0.09 + rr(0, 0.02), n = noise(tt, tt + 0.08), b = flt('bandpass', rr(3000, 5000), 1.5), g = ctx.createGain();
        b.frequency.linearRampToValueAtTime(rr(2500, 6000), tt + 0.07);
        g.gain.setValueAtTime(0.0001, tt); g.gain.linearRampToValueAtTime(0.12, tt + 0.015);
        g.gain.linearRampToValueAtTime(0.0001, tt + 0.07);
        n.connect(b); b.connect(g); g.connect(sOut());
      }
    },
    seal: function (t) {
      drumHit(sOut(), t, 140, 60, 0.18, 0.5, 0.3, 500, true);
      var n = noise(t + 0.05, t + 0.35), b = flt('lowpass', 900, 4), g = ctx.createGain();
      b.frequency.setValueAtTime(1200, t + 0.05); b.frequency.exponentialRampToValueAtTime(250, t + 0.3);
      g.gain.setValueAtTime(0.0001, t + 0.05); g.gain.linearRampToValueAtTime(0.12, t + 0.1);
      g.gain.linearRampToValueAtTime(0.0001, t + 0.33);
      n.connect(b); b.connect(g); g.connect(sOut());
    },
    bell: function (t) {
      [[1, .2], [2.76, .08], [5.4, .04], [0.5, .06]].forEach(function (p) {
        var f = 880 * p[0], o = osc('sine', f, t, t + 0.6), g = ctx.createGain();
        g.gain.setValueAtTime(0.0001, t); g.gain.linearRampToValueAtTime(p[1], t + 0.003);
        g.gain.exponentialRampToValueAtTime(0.0005, t + 0.58);
        o.connect(g); g.connect(sOut());
      });
    },
    telegraph: function (t) {
      var pat = [1, 0, 1, 1, 0, 1, 0, 0, 1, 1, 1, 0, 1], tt = t;
      pat.forEach(function (x) {
        var len = x ? 0.045 : 0.018;
        [tt, tt + len].forEach(function (c, k) {
          var n = noise(c, c + 0.012), b = flt('bandpass', k ? 1800 : 2600, 6), g = ctx.createGain();
          g.gain.setValueAtTime(0.0001, c); g.gain.linearRampToValueAtTime(k ? 0.12 : 0.22, c + 0.001);
          g.gain.exponentialRampToValueAtTime(0.0005, c + 0.01);
          n.connect(b); b.connect(g); g.connect(sOut());
        });
        tt += len + 0.03;
      });
    },
    crowd: function (t) {
      var stop = t + 2.6;
      for (var i = 0; i < 3; i++) {
        var n = noise(t, stop), b = flt('bandpass', 400 + i * 350, 3), g = ctx.createGain();
        var l = osc('sine', 3 + i * 1.7, t, stop), lg = ctx.createGain(); lg.gain.value = 180;
        l.connect(lg); lg.connect(b.frequency);
        g.gain.setValueAtTime(0.0001, t); g.gain.linearRampToValueAtTime(0.08, t + 0.6);
        g.gain.setValueAtTime(0.08, t + 1.8); g.gain.linearRampToValueAtTime(0.0001, stop);
        n.connect(b); b.connect(g); g.connect(sOut());
      }
    },
    gong: function (t) {
      var stop = t + 3;
      [[1, .22], [1.48, .1], [2.02, .08], [2.74, .05], [3.3, .03]].forEach(function (p) {
        var f = 98 * p[0], o = osc('sine', f, t, stop), g = ctx.createGain();
        o.frequency.setValueAtTime(f * 1.01, t); o.frequency.exponentialRampToValueAtTime(f, t + 1);
        g.gain.setValueAtTime(0.0001, t); g.gain.linearRampToValueAtTime(p[1], t + 0.02);
        g.gain.exponentialRampToValueAtTime(0.0005, stop - 0.05);
        o.connect(g); g.connect(sOut());
      });
      drumHit(sOut(), t, 90, 50, 0.6, 0.3, 0.3, 300, true);
    },
    page: function (t) {
      var n = noise(t, t + 0.35), b = flt('bandpass', 2000, 0.8), g = ctx.createGain();
      b.frequency.setValueAtTime(1200, t); b.frequency.linearRampToValueAtTime(4500, t + 0.25);
      g.gain.setValueAtTime(0.0001, t); g.gain.linearRampToValueAtTime(0.1, t + 0.08);
      g.gain.linearRampToValueAtTime(0.04, t + 0.18); g.gain.linearRampToValueAtTime(0.0001, t + 0.32);
      n.connect(b); b.connect(g); g.connect(sOut());
    },
    click: function (t) {
      var o = osc('sine', 1800, t, t + 0.05), o2 = osc('triangle', 900, t, t + 0.05), g = ctx.createGain();
      g.gain.setValueAtTime(0.0001, t); g.gain.linearRampToValueAtTime(0.08, t + 0.002);
      g.gain.exponentialRampToValueAtTime(0.0005, t + 0.045);
      o.connect(g); o2.connect(g); g.connect(sOut());
    },
    storm: function (t) {
      var stop = t + 2.8, n = noise(t, stop), b = flt('lowpass', 500, 0.5), g = ctx.createGain();
      b.frequency.linearRampToValueAtTime(1400, t + 1); b.frequency.linearRampToValueAtTime(300, stop);
      g.gain.setValueAtTime(0.0001, t); g.gain.linearRampToValueAtTime(0.25, t + 0.8);
      g.gain.linearRampToValueAtTime(0.0001, stop);
      n.connect(b); b.connect(g); g.connect(sOut());
      drumHit(sOut(), t + 0.9, 60, 30, 1.6, 0.35, 0.6, 150, true); // thunder
    },
    cannon: function (t) {
      drumHit(sOut(), t, 80, 30, 0.55, 0.6, 1, 400, true);
      var n = noise(t, t + 0.6), b = flt('lowpass', 1500, 0.5), g = ctx.createGain();
      b.frequency.exponentialRampToValueAtTime(150, t + 0.5);
      g.gain.setValueAtTime(0.0001, t); g.gain.linearRampToValueAtTime(0.3, t + 0.005);
      g.gain.exponentialRampToValueAtTime(0.0005, t + 0.58);
      n.connect(b); b.connect(g); g.connect(sOut());
    },
    fanfare: function (t) {
      var r = 60, s = 0.11;
      [[0, 1], [4, 1], [7, 1], [12, 3]].forEach(function (x, i) {
        I.brass(sOut(), r + 7 + x[0], t + i * s, x[1] * s + (i === 3 ? 0.2 : 0), 0.8);
        I.brass(sOut(), r + x[0], t + i * s, x[1] * s + (i === 3 ? 0.2 : 0), 0.5);
      });
    }
  };

  // ---------- unlocking ----------
  function unlock() {
    if (unlocked) { if (ctx && ctx.state === 'suspended') ctx.resume().catch(function () {}); return; }
    unlocked = true;
    try {
      if (!build()) return;
      if (ctx.state === 'suspended') ctx.resume().catch(function () {});
      ensureTimer();
      if (st.music) startPlayer();
    } catch (e) { ctx = null; }
  }
  try {
    document.addEventListener('pointerdown', unlock, true);
    document.addEventListener('keydown', unlock, true);
    document.addEventListener('visibilitychange', function () {
      if (!ctx) return;
      if (document.hidden) { queue.length = 0; if (ctx.suspend) ctx.suspend().catch(function () {}); }
      else {
        ctx.resume().catch(function () {});
        if (player) { player.secStart = ctx.currentTime + 0.15; player.queued = false; heartNext = 0; }
      }
    });
  } catch (e) {}

  // ---------- controls ----------
  var ui = {};
  function refreshUI() {
    if (!ui.m) return;
    ui.m.setAttribute('aria-pressed', String(st.music)); ui.m.style.opacity = st.music ? 1 : 0.45;
    ui.s.setAttribute('aria-pressed', String(st.sfx)); ui.s.style.opacity = st.sfx ? 1 : 0.45;
    ui.v.value = String(Math.round(st.vol * 100));
  }
  function init() {
    try {
      if (document.getElementById('ledger-sound-ctl')) return;
      var host = document.getElementById('sound-ctl'), box = document.createElement('div');
      box.id = 'ledger-sound-ctl';
      box.setAttribute('role', 'group'); box.setAttribute('aria-label', 'Sound controls');
      box.style.cssText = 'display:inline-flex;gap:6px;align-items:center;font:14px/1 inherit;color:var(--ink,currentColor);' +
        (host ? '' : 'position:fixed;top:8px;right:8px;z-index:9999;padding:4px 6px;border-radius:6px;' +
          'background:var(--paper,transparent);border:1px solid var(--line,currentColor);');
      function btn(txt, label) {
        var b = document.createElement('button'); b.type = 'button'; b.textContent = txt;
        b.title = label; b.setAttribute('aria-label', label);
        b.style.cssText = 'font:inherit;color:inherit;background:transparent;border:1px solid var(--line,currentColor);' +
          'border-radius:4px;min-width:26px;height:24px;cursor:pointer;padding:0 4px';
        return b;
      }
      ui.m = btn('\u266A', 'Toggle music (M)');
      ui.s = btn('\uD83D\uDD14', 'Toggle sound effects');
      ui.v = document.createElement('input'); ui.v.type = 'range'; ui.v.min = '0'; ui.v.max = '100';
      ui.v.setAttribute('aria-label', 'Volume'); ui.v.style.cssText = 'width:70px;accent-color:currentColor';
      ui.m.addEventListener('click', function () { unlock(); api.setMusic(!st.music); });
      ui.s.addEventListener('click', function () { unlock(); api.setSfx(!st.sfx); });
      ui.v.addEventListener('input', function () { api.setVolume(+ui.v.value / 100); });
      box.appendChild(ui.m); box.appendChild(ui.s); box.appendChild(ui.v);
      (host || document.body).appendChild(box);
      if (!init._k) {
        init._k = 1;
        document.addEventListener('keydown', function (e) {
          if ((e.key !== 'm' && e.key !== 'M') || e.ctrlKey || e.metaKey || e.altKey) return;
          var a = document.activeElement, tg = a && a.tagName;
          if (tg === 'INPUT' || tg === 'TEXTAREA' || tg === 'SELECT' || (a && a.isContentEditable)) return;
          unlock(); api.setMusic(!st.music);
        });
      }
      refreshUI();
    } catch (e) {}
  }

  // ---------- public API ----------
  function ramp(param, v, t) {
    var now = ctx.currentTime; param.cancelScheduledValues(now);
    param.setValueAtTime(param.value, now); param.linearRampToValueAtTime(v, now + t);
  }
  var ERA_IDS = ['rialto', 'medici', 'princes', 'northern', 'country', 'lombard', 'basel'];
  var api = {
    _v: 1,
    init: init,
    setEra: function (id) {
      if (ERA_IDS.indexOf(id) < 0 || id === era) return;
      era = id;
      try { if (ctx && st.music) startPlayer(); else if (ctx) setRoom(era, 1); } catch (e) {}
    },
    setYear: function (y) {
      y = +y; if (!isFinite(y)) return;
      var before = pieceFor(era); year = y;
      try { if (ctx && st.music && player && pieceFor(era) !== before) startPlayer(); } catch (e) {}
    },
    mood: function (k) {
      if (['calm', 'tension', 'triumph', 'grief'].indexOf(k) < 0) return;
      if (k === 'triumph') {
        var prev = moodK === 'triumph' ? 'calm' : moodK; moodK = 'calm';
        try { if (ctx) { var t = ctx.currentTime; if (t - triumphAt > 2) { triumphAt = t; flourish(); } } } catch (e) {}
        moodK = prev === 'tension' ? 'calm' : prev; return;
      }
      moodK = k;
    },
    sfx: function (name) {
      if (!ctx || !st.sfx || !SFX[name] || document.hidden) return;
      try {
        var g = ctx.createGain(); g.gain.value = SFX_GAIN[name] || 1; g.connect(sfxBus);
        sfxDest = g;
        try { SFX[name](ctx.currentTime + 0.01); } finally { sfxDest = null; }
        setTimeout(function () { try { g.disconnect(); } catch (e) {} }, 4000);
      } catch (e) { sfxDest = null; }
    },
    get musicOn() { return st.music; },
    get sfxOn() { return st.sfx; },
    setMusic: function (b) {
      st.music = !!b; save(); refreshUI();
      if (!ctx) return;
      try {
        ramp(musicBus.gain, st.music ? 0.8 : 0, 0.6);
        if (st.music) { if (!player || player.era !== era) startPlayer(); else { player.secStart = ctx.currentTime + 0.1; player.queued = false; fadeEra(era, 1, 0.5); } }
      } catch (e) {}
    },
    setSfx: function (b) {
      st.sfx = !!b; save(); refreshUI();
      try { if (ctx) ramp(sfxBus.gain, st.sfx ? 0.9 : 0, 0.1); } catch (e) {}
    },
    setVolume: function (v) {
      v = Math.min(1, Math.max(0, +v || 0)); st.vol = v; save(); refreshUI();
      try { if (ctx) ramp(master.gain, v, 0.08); } catch (e) {}
    },
    _demo: function () {
      var i = 0, years = [1350, 1450, 1550, 1650, 1780, 1910, 1990];
      if (!st.music) api.setMusic(true);
      clearInterval(api._dt);
      function step() {
        api.setYear(years[i]); api.setEra(ERA_IDS[i]);
        try { console.log('[LedgerSound] demo:', ERA_IDS[i], years[i]); } catch (e) {}
        i = (i + 1) % ERA_IDS.length;
      }
      step(); api._dt = setInterval(step, 8000);
      return 'cycling eras every 8 s; clearInterval(LedgerSound._dt) to stop';
    }
  };
  window.LedgerSound = api;
})();
