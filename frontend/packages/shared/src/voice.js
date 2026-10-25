// Modular speech adapters for the browser.
//
// Recognizer adapters share one shape: { kind, privacyNote, start(), stop() } and
// report through callbacks { onInterim, onFinal, onError, onEnd }.
//
// - "browser": Web Speech API. Works in Chrome, Edge and Safari. NOTE: Chrome and
//   Edge send microphone audio to the browser vendor's cloud speech service; Safari
//   may process on-device or on Apple servers. This is disclosed in the UI.
// - A local server-side adapter (e.g. whisper.cpp behind /api/speech) can be added
//   here once the backend reports `server_stt.available` — see docs/voice.md.
//
// Speech output uses speechSynthesis, which runs locally with the OS voices.

const ERROR_MESSAGES = {
  'not-allowed': 'Microphone access was blocked. You can allow it in your browser’s site settings, or keep typing.',
  'service-not-allowed': 'Speech recognition is not allowed in this browser. You can keep typing instead.',
  'audio-capture': 'No microphone was found. Please connect one or keep typing.',
  'no-speech': 'I didn’t hear anything. Tap the microphone and try again.',
  network: 'The browser’s speech service could not be reached. Please type your question instead.',
  aborted: null,
};

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

export function createBrowserRecognizer({ lang = 'en-US', onInterim, onFinal, onError, onEnd }) {
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
      if (r.isFinal) onFinal?.(r[0].transcript.trim());
      else interim += r[0].transcript;
    }
    if (interim) onInterim?.(interim.trim());
  };
  rec.onerror = (event) => {
    const msg = ERROR_MESSAGES[event.error];
    if (msg !== null) onError?.(msg || 'Voice input stopped unexpectedly. Please try again or type your question.');
  };
  rec.onend = () => onEnd?.();

  return {
    kind: 'browser',
    privacyNote: 'Voice input uses your browser’s speech service, which may send audio to the browser maker (for example Google in Chrome).',
    start() {
      try {
        rec.start();
      } catch {
        onError?.('Voice input is already running.');
      }
    },
    stop: () => rec.stop(),
  };
}

export function selectRecognizer(_capabilities, callbacks) {
  // Prefer a local server engine when one exists (not shipped yet); otherwise use the browser.
  return createBrowserRecognizer(callbacks);
}

export const speaker = {
  get supported() {
    return voiceSupport().synthesis;
  },
  speak(text, { lang = 'en-US', rate = 1 } = {}) {
    if (!this.supported || !text) return;
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = lang;
    u.rate = rate;
    window.speechSynthesis.speak(u);
  },
  cancel() {
    if (this.supported) window.speechSynthesis.cancel();
  },
};
