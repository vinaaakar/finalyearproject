// Modular speech adapters for the browser.
//
// Recognizer adapters share one shape: { kind, privacyNote, start(), stop() } and
// report through callbacks { onInterim, onFinal, onError, onEnd }.
//
// - "browser": Web Speech API. Works in Chrome, Edge and Safari. NOTE: Chrome and
//   Edge send microphone audio to the browser vendor's cloud speech service; Safari
//   may process on-device or on Apple servers. This is disclosed in the UI.
// - "server": records the microphone in the page (Web Audio), encodes 16 kHz WAV and sends
//   it to this store's backend, which transcribes it with a LOCAL engine (whisper.cpp).
//   Used automatically when the backend reports `server_stt.available` — see docs/voice.md.
//
// Speech output: `speaker` uses only LOCAL speechSynthesis voices that match the reply language
// (on macOS: Vani ta-IN, Lekha hi-IN, Rishi en-IN). Remote voices (e.g. "Google हिन्दी") are never
// used because they send the text to an external service. Fallback: the store server's local TTS
// (macOS `say`), then text only.
//
// Recognizers report errors as codes ('not-allowed', 'audio-capture', 'no-speech', 'network',
// 'service-not-allowed', 'failed'); the chat widget shows them in the conversation language.

import { LANGUAGES } from './i18n.js';

const BROWSER_ERRORS = new Set(['not-allowed', 'service-not-allowed', 'audio-capture', 'no-speech', 'network']);

function getRecognitionCtor() {
  if (typeof window === 'undefined') return null;
  return window.SpeechRecognition || window.webkitSpeechRecognition || null;
}

export function voiceSupport() {
  return {
    recognition: !!getRecognitionCtor(),
    synthesis: typeof window !== 'undefined' && 'speechSynthesis' in window,
    secureContext: typeof window !== 'undefined' && window.isSecureContext,
  };
}

// NOTE: the Web Speech API needs ONE fixed locale per session; it cannot identify the spoken language.
// Its transcript is still evaluated by the server's text-based language identification.
export function createBrowserRecognizer({ lang = 'ta-IN', onInterim, onFinal, onError, onEnd }) {
  const Ctor = getRecognitionCtor();
  if (!Ctor) return null;
  const rec = new Ctor();
  rec.lang = lang;
  rec.interimResults = true;
  rec.continuous = false;
  rec.maxAlternatives = 1;

  rec.onresult = (event) => {
    let interim = '';
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const r = event.results[i];
      if (r.isFinal) onFinal?.(r[0].transcript.trim(), { engine: 'browser', recognizerLocale: lang });
      else interim += r[0].transcript;
    }
    if (interim) onInterim?.(interim.trim());
  };
  rec.onerror = (event) => {
    if (event.error === 'aborted') return;
    onError?.(BROWSER_ERRORS.has(event.error) ? event.error : 'failed');
  };
  rec.onend = () => onEnd?.();

  return {
    kind: 'browser',
    privacyNote: 'Voice input uses your browser’s speech service, which may send audio to the browser maker (for example Google in Chrome).',
    start() {
      try {
        rec.start();
      } catch {
        onError?.('failed');
      }
    },
    stop: () => rec.stop(),
  };
}

// ---- server (local engine) recognizer -------------------------------------------------------
const TARGET_RATE = 16000;
const SPEECH_RMS = 0.015;      // level treated as speech
const END_SILENCE_MS = 1500;   // stop this long after the speaker goes quiet (natural Tamil/Hindi pauses mid-sentence)
const NO_AUDIO_MS = 2500;      // the microphone delivered no audio frames at all (suspended audio context, muted device)
const NO_SPEECH_MS = 6000;     // give up if nothing is said
const MAX_MS = 15000;          // hard cap per utterance
const TRANSCRIBE_TIMEOUT_MS = 45000; // the server engine has its own 30 s limit; never wait forever on the network

function downsample(samples, fromRate) {
  if (fromRate === TARGET_RATE) return samples;
  const ratio = fromRate / TARGET_RATE;
  const out = new Float32Array(Math.floor(samples.length / ratio));
  for (let i = 0; i < out.length; i++) {
    // Average the source samples that fall into this output sample (simple low-pass).
    const start = Math.floor(i * ratio), end = Math.min(samples.length, Math.floor((i + 1) * ratio));
    let sum = 0;
    for (let j = start; j < end; j++) sum += samples[j];
    out[i] = sum / Math.max(1, end - start);
  }
  return out;
}

export function encodeWav(samples, rate = TARGET_RATE) {
  const buf = new ArrayBuffer(44 + samples.length * 2);
  const v = new DataView(buf);
  const str = (o, t) => [...t].forEach((c, i) => v.setUint8(o + i, c.charCodeAt(0)));
  str(0, 'RIFF'); v.setUint32(4, 36 + samples.length * 2, true); str(8, 'WAVE');
  str(12, 'fmt '); v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
  v.setUint32(24, rate, true); v.setUint32(28, rate * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true);
  str(36, 'data'); v.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i++) {
    const x = Math.max(-1, Math.min(1, samples[i]));
    v.setInt16(44 + i * 2, x < 0 ? x * 0x8000 : x * 0x7fff, true);
  }
  return new Blob([buf], { type: 'audio/wav' });
}

export function createServerRecognizer({ transcribe, language = 'auto', hint = null, onInterim, onFinal, onError, onEnd,
  transcribeTimeoutMs = TRANSCRIBE_TIMEOUT_MS }) {
  if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia || typeof AudioContext === 'undefined') return null;
  let stream, ctx, node, source, timer;
  let chunks = [], finished = false, heardSpeech = false, quietMs = 0, startedAt = 0, frames = 0;

  function release() {
    clearInterval(timer);
    try { node && (node.onaudioprocess = null); source?.disconnect(); node?.disconnect(); } catch { /* already disconnected */ }
    stream?.getTracks().forEach((t) => t.stop());
    ctx?.close().catch(() => {});
  }

  async function finish(cancelled = false) {
    if (finished) return;
    finished = true;
    const rate = ctx?.sampleRate || TARGET_RATE;
    release();
    try {
      if (cancelled) return;
      if (!heardSpeech) {
        // No frames at all means the audio never reached us (a suspended context or a muted input), not silence.
        onError?.(frames === 0 ? 'no-audio' : 'no-speech');
        return;
      }
      const total = chunks.reduce((n, c) => n + c.length, 0);
      const merged = new Float32Array(total);
      let off = 0;
      for (const c of chunks) { merged.set(c, off); off += c.length; }
      onInterim?.('transcribing');
      const audio = encodeWav(downsample(merged, rate));
      let timeoutId;
      const timedOut = new Promise((_, reject) => { timeoutId = setTimeout(() => reject(Object.assign(new Error('timeout'), { code: 'timeout' })), transcribeTimeoutMs); });
      let result;
      try {
        // The conversation language (hint) only affects how weakly-detected "English" (often Tanglish) is transcribed.
        const h = typeof hint === 'function' ? hint() : hint;
        result = await Promise.race([h ? transcribe(audio, language, h) : transcribe(audio, language), timedOut]);
      } finally {
        clearTimeout(timeoutId);
      }
      const text = (result.text || '').trim();
      onInterim?.('');
      if (text) {
        onFinal?.(text, { engine: 'server', detected: result.detected_language, probability: result.language_probability,
          uncertain: result.uncertain, receipt: result.speech_receipt, audio,
          audioSeconds: result.audio_seconds ?? null, transcribeMs: result.elapsed_ms ?? null });
      } else onError?.('no-speech');
    } catch (e) {
      if (e?.code === 'timeout' || e?.code === 'network') onError?.('network');
      else onError?.('failed', e?.message);
    } finally {
      chunks = [];
      onEnd?.();
    }
  }

  return {
    kind: 'server',
    privacyNote: 'Voice is transcribed by this store’s own server with a local speech engine. Audio is not sent to third parties or stored.',
    async start() {
      // Created synchronously inside the tap, BEFORE awaiting the permission prompt: Safari only lets an AudioContext run
      // when it is created/resumed during a user gesture, and the gesture is gone once getUserMedia resolves.
      ctx = new AudioContext();
      const resumed = ctx.state === 'suspended' ? ctx.resume().catch(() => {}) : null;
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
      } catch (e) {
        finished = true;
        ctx.close().catch(() => {});
        onError?.(e?.name === 'NotAllowedError' || e?.name === 'SecurityError' ? 'not-allowed' : e?.name === 'NotFoundError' ? 'audio-capture' : 'failed');
        onEnd?.();
        return;
      }
      if (resumed) await resumed;
      if (ctx.state === 'suspended') await ctx.resume().catch(() => {});
      source = ctx.createMediaStreamSource(stream);
      // ScriptProcessorNode is deprecated but universally supported and needs no extra module file.
      node = ctx.createScriptProcessor(4096, 1, 1);
      node.onaudioprocess = (e) => {
        if (finished) return;
        frames += 1;
        const data = e.inputBuffer.getChannelData(0);
        chunks.push(new Float32Array(data));
        let sum = 0;
        for (let i = 0; i < data.length; i++) sum += data[i] * data[i];
        const loud = Math.sqrt(sum / data.length) > SPEECH_RMS;
        const ms = (data.length / ctx.sampleRate) * 1000;
        if (loud) { heardSpeech = true; quietMs = 0; } else if (heardSpeech) quietMs += ms;
        if (heardSpeech && quietMs >= END_SILENCE_MS) finish();
      };
      source.connect(node);
      node.connect(ctx.destination); // required for processing to run; the node outputs silence
      startedAt = Date.now();
      timer = setInterval(() => {
        const elapsed = Date.now() - startedAt;
        if (elapsed >= MAX_MS || (!heardSpeech && elapsed >= NO_SPEECH_MS) || (frames === 0 && elapsed >= NO_AUDIO_MS)) finish();
      }, 250);
      onInterim?.('listening');
    },
    stop: () => finish(false),
    cancel: () => finish(true),
  };
}

export function selectRecognizer(capabilities, callbacks) {
  // Prefer the store's local server engine (audio stays on our server); otherwise use the browser's.
  if (capabilities?.server_stt?.available && callbacks.transcribe) {
    const server = createServerRecognizer(callbacks);
    if (server) return server;
  }
  return createBrowserRecognizer(callbacks);
}

// ---- speech output -------------------------------------------------------------------------------
const PREFERRED = ['Vani', 'Lekha', 'Rishi', 'Aman', 'Tara', 'Samantha', 'Daniel', 'Karen'];

/** The best LOCAL voice for a BCP-47 tag: exact locale first, then the same language; null if none. */
export function pickVoice(voices, bcp47) {
  const local = voices.filter((v) => v.localService);
  const norm = (l) => (l || '').replace('_', '-').toLowerCase();
  const rank = (v) => (PREFERRED.indexOf(v.name) + 1 || 99);
  const exact = local.filter((v) => norm(v.lang) === bcp47.toLowerCase()).sort((a, b) => rank(a) - rank(b));
  if (exact.length) return exact[0];
  const same = local.filter((v) => norm(v.lang).startsWith(bcp47.slice(0, 2).toLowerCase())).sort((a, b) => rank(a) - rank(b));
  return same[0] || null;
}

function voicesSoon(timeoutMs) {
  // OS voices can arrive after the first (remote-only) list: wait for one `voiceschanged` or the timeout.
  return new Promise((resolve) => {
    const done = () => {
      window.speechSynthesis.removeEventListener('voiceschanged', done);
      resolve(window.speechSynthesis.getVoices());
    };
    window.speechSynthesis.addEventListener('voiceschanged', done);
    setTimeout(done, timeoutMs);
  });
}

// One reply is read as several short utterances: Chrome stops a single long utterance after ~15 s, and short sentences
// can be interrupted cleanly. Splits at sentence ends (., ?, !, ।) and, for very long sentences, at commas/semicolons.
export function speechChunks(text, max = 220) {
  const sentences = (text || '').replace(/\s+/g, ' ').trim().match(/[^.?!।]+[.?!।]*\s*/g) || [];
  const out = [];
  for (const raw of sentences) {
    let sentence = raw.trim();
    while (sentence.length > max) {
      const cut = Math.max(sentence.lastIndexOf(', ', max - 1), sentence.lastIndexOf('; ', max - 1), sentence.lastIndexOf(' ', max - 1));
      const at = cut > 40 ? cut + 1 : max;
      out.push(sentence.slice(0, at).trim());
      sentence = sentence.slice(at).trim();
    }
    if (sentence) out.push(sentence);
  }
  return out;
}

// A 0.1 s silent WAV: played once inside a tap so Safari (and Chrome's autoplay policy) let later replies play.
const SILENT_WAV = 'data:audio/wav;base64,UklGRigAAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YQQAAAAAAAAA';

export const speaker = {
  audio: null,
  element: null,      // one reusable <audio> element, unlocked by prime() during a tap
  primed: false,
  // Incremented by every cancel(): a speak() still waiting for voices or server audio checks it before making a sound,
  // so a reply never starts after the customer interrupted it (pressed the mic, closed the chat, sent a new message).
  generation: 0,
  // Speaking state for the UI ("Scout is speaking — Stop"): set from the real start/end of playback.
  speaking: false,
  onChange: null,
  setSpeaking(v) {
    if (this.speaking === v) return;
    this.speaking = v;
    this.onChange?.(v);
  },
  get supported() {
    return voiceSupport().synthesis;
  },
  /**
   * Call synchronously from a tap/click (send, mic, "play" buttons). Browsers — Safari in particular — refuse to start
   * speech or audio that is not tied to a user gesture; a reply arrives seconds later, after the gesture has ended.
   * Priming once (a silent utterance and a silent clip on a reusable audio element) lets those later replies play.
   */
  prime() {
    if (this.primed || typeof window === 'undefined') return;
    this.primed = true;
    try {
      if (this.supported && typeof SpeechSynthesisUtterance !== 'undefined') {
        const u = new SpeechSynthesisUtterance(' ');
        u.volume = 0;
        window.speechSynthesis.speak(u);
      }
    } catch { /* speech synthesis unavailable: server audio may still work */ }
    try {
      if (typeof Audio !== 'undefined') {
        this.element = this.element || new Audio();
        this.element.src = SILENT_WAV;
        const p = this.element.play?.();
        if (p && typeof p.catch === 'function') p.catch(() => {});
      }
    } catch { /* no audio element support */ }
  },
  /**
   * Speak `text` in `lang` ('ta' | 'en' | 'hi'). Resolves to { mode, voice, error? }:
   *   'browser' — a local voice is speaking it; later failures are reported through `onError(code)`
   *   'server'  — the store's local TTS audio is playing
   *   'blocked' — the browser refused to start playback without a tap (autoplay policy): offer a "play" button
   *   'error'   — speech was attempted but failed (server TTS error, empty audio, playback error)
   *   'none'    — no voice for this language on this device and no server TTS: text only
   *   'cancelled' — interrupted before it started
   * `serverTts(text, lang)` (optional) returns a WAV Blob from the store's local TTS.
   */
  async speak(text, lang, { serverTts, rate = 1, onError } = {}) {
    this.cancel();
    const gen = this.generation;
    const interrupted = () => gen !== this.generation;
    if (!text) return { mode: 'none', voice: null };
    const bcp47 = LANGUAGES[lang]?.bcp47 || lang;
    if (this.supported) {
      let voice = pickVoice(window.speechSynthesis.getVoices(), bcp47);
      if (!voice) voice = pickVoice(await voicesSoon(1500), bcp47);
      if (interrupted()) return { mode: 'cancelled', voice: null };
      if (voice) {
        const chunks = speechChunks(text);
        const done = () => { if (gen === this.generation) this.setSpeaking(false); };
        chunks.forEach((chunk, i) => {
          const u = new SpeechSynthesisUtterance(chunk);
          u.voice = voice;
          u.lang = voice.lang;
          u.rate = rate;
          if (i === chunks.length - 1) u.onend = done;
          u.onerror = (e) => {
            // 'interrupted' / 'canceled' are our own cancel(); anything else means the reply was NOT heard.
            if (e?.error === 'interrupted' || e?.error === 'canceled') return;
            if (gen !== this.generation) return;
            done();
            window.speechSynthesis.cancel();
            onError?.(e?.error === 'not-allowed' ? 'blocked' : 'failed');
          };
          window.speechSynthesis.speak(u);
        });
        this.setSpeaking(true);
        return { mode: 'browser', voice: voice.name };
      }
    }
    if (serverTts) {
      let blob;
      try {
        blob = await serverTts(text, lang);
      } catch (e) {
        return interrupted() ? { mode: 'cancelled', voice: null } : { mode: 'error', voice: null, error: e?.message || 'server' };
      }
      if (interrupted()) return { mode: 'cancelled', voice: null };
      if (!blob || blob.size === 0) return { mode: 'error', voice: null, error: 'empty' };
      const url = URL.createObjectURL(blob);
      const audio = this.element || new Audio();
      audio.src = url;
      audio.objectUrl = url;
      this.audio = audio;
      const finished = () => {
        if (audio.objectUrl === url) { URL.revokeObjectURL(url); audio.objectUrl = null; }
        if (gen === this.generation) this.setSpeaking(false);
      };
      audio.onended = finished;
      audio.onerror = () => { finished(); if (gen === this.generation) onError?.('failed'); };
      this.setSpeaking(true);
      try {
        await audio.play();
        return { mode: 'server', voice: null };
      } catch (e) {
        finished();
        return e?.name === 'NotAllowedError' ? { mode: 'blocked', voice: null } : { mode: 'error', voice: null, error: e?.message || 'play' };
      }
    }
    return { mode: 'none', voice: null };
  },
  cancel() {
    this.generation += 1;
    this.setSpeaking(false);
    if (this.supported) window.speechSynthesis.cancel();
    if (this.audio) {
      this.audio.pause?.();
      if (this.audio.objectUrl) URL.revokeObjectURL(this.audio.objectUrl);
      this.audio.objectUrl = null;
      this.audio = null;
    }
  },
};
