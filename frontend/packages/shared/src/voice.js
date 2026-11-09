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
const END_SILENCE_MS = 1200;   // stop this long after the speaker goes quiet
const NO_SPEECH_MS = 6000;     // give up if nothing is said
const MAX_MS = 15000;          // hard cap per utterance

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

export function createServerRecognizer({ transcribe, language = 'auto', onInterim, onFinal, onError, onEnd }) {
  if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia || typeof AudioContext === 'undefined') return null;
  let stream, ctx, node, source, timer;
  let chunks = [], finished = false, heardSpeech = false, quietMs = 0, startedAt = 0;

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
        onError?.('no-speech');
        return;
      }
      const total = chunks.reduce((n, c) => n + c.length, 0);
      const merged = new Float32Array(total);
      let off = 0;
      for (const c of chunks) { merged.set(c, off); off += c.length; }
      onInterim?.('transcribing');
      const audio = encodeWav(downsample(merged, rate));
      const result = await transcribe(audio, language);
      const text = (result.text || '').trim();
      onInterim?.('');
      if (text) {
        onFinal?.(text, { engine: 'server', detected: result.detected_language, probability: result.language_probability,
          uncertain: result.uncertain, receipt: result.speech_receipt, audio });
      } else onError?.('no-speech');
    } catch (e) {
      onError?.('failed', e?.message);
    } finally {
      chunks = [];
      onEnd?.();
    }
  }

  return {
    kind: 'server',
    privacyNote: 'Voice is transcribed by this store’s own server with a local speech engine. Audio is not sent to third parties or stored.',
    async start() {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
      } catch (e) {
        finished = true;
        onError?.(e?.name === 'NotAllowedError' || e?.name === 'SecurityError' ? 'not-allowed' : e?.name === 'NotFoundError' ? 'audio-capture' : 'failed');
        onEnd?.();
        return;
      }
      ctx = new AudioContext();
      if (ctx.state === 'suspended') await ctx.resume().catch(() => {});
      source = ctx.createMediaStreamSource(stream);
      // ScriptProcessorNode is deprecated but universally supported and needs no extra module file.
      node = ctx.createScriptProcessor(4096, 1, 1);
      node.onaudioprocess = (e) => {
        if (finished) return;
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
        if (elapsed >= MAX_MS || (!heardSpeech && elapsed >= NO_SPEECH_MS)) finish();
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

export const speaker = {
  audio: null,
  get supported() {
    return voiceSupport().synthesis;
  },
  /**
   * Speak `text` in `lang` ('ta' | 'en' | 'hi'). Returns { mode: 'browser' | 'server' | 'none', voice }.
   * `serverTts(text, lang)` (optional) returns a WAV Blob from the store's local TTS.
   */
  async speak(text, lang, { serverTts, rate = 1 } = {}) {
    this.cancel();
    if (!text) return { mode: 'none', voice: null };
    const bcp47 = LANGUAGES[lang]?.bcp47 || lang;
    if (this.supported) {
      let voice = pickVoice(window.speechSynthesis.getVoices(), bcp47);
      if (!voice) voice = pickVoice(await voicesSoon(1500), bcp47);
      if (voice) {
        const u = new SpeechSynthesisUtterance(text);
        u.voice = voice;
        u.lang = voice.lang;
        u.rate = rate;
        window.speechSynthesis.speak(u);
        return { mode: 'browser', voice: voice.name };
      }
    }
    if (serverTts) {
      try {
        const blob = await serverTts(text, lang);
        this.audio = new Audio(URL.createObjectURL(blob));
        await this.audio.play();
        return { mode: 'server', voice: null };
      } catch {
        /* fall through to text only */
      }
    }
    return { mode: 'none', voice: null };
  },
  cancel() {
    if (this.supported) window.speechSynthesis.cancel();
    if (this.audio) {
      this.audio.pause();
      this.audio = null;
    }
  },
};
