// Speech adapters (voice.js) with fake browser audio: recorder end-of-speech, no-speech and length limits, cancellation,
// permission errors, transcription timeout; speaker voice choice (local voices only) and interruption.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createServerRecognizer, encodeWav, pickVoice, speaker } from '../voice.js';

// ---- fake microphone + Web Audio --------------------------------------------------------------------------------------
let processor;
class FakeAudioContext {
  constructor() { this.sampleRate = 48000; this.state = 'running'; }
  createMediaStreamSource() { return { connect() {}, disconnect() {} }; }
  createScriptProcessor() { processor = { connect() {}, disconnect() {}, onaudioprocess: null }; return processor; }
  get destination() { return {}; }
  close() { return Promise.resolve(); }
  resume() { return Promise.resolve(); }
}
const frame = (level) => ({ inputBuffer: { getChannelData: () => new Float32Array(4096).fill(level) } });   // 4096 / 48 kHz ≈ 85 ms
const track = { stop: vi.fn() };

function setup({ transcribe = vi.fn().mockResolvedValue({ text: 'வணக்கம்', detected_language: 'ta', language_probability: 0.8 }),
  getUserMedia = vi.fn().mockResolvedValue({ getTracks: () => [track] }), ...opts } = {}) {
  Object.defineProperty(navigator, 'mediaDevices', { value: { getUserMedia }, configurable: true });
  globalThis.AudioContext = FakeAudioContext;
  const cb = { onInterim: vi.fn(), onFinal: vi.fn(), onError: vi.fn(), onEnd: vi.fn() };
  const rec = createServerRecognizer({ transcribe, ...cb, ...opts });
  return { rec, transcribe, cb, getUserMedia };
}
const flush = () => new Promise((r) => setTimeout(r, 0));
// jsdom's Blob has no arrayBuffer(); read it the way a browser page could.
const bytes = (blob) => new Promise((resolve) => { const fr = new FileReader(); fr.onload = () => resolve(fr.result); fr.readAsArrayBuffer(blob); });

describe('server recognizer (local whisper.cpp path)', () => {
  beforeEach(() => { vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval', 'Date'] }); track.stop.mockClear(); });
  afterEach(() => { vi.useRealTimers(); delete globalThis.AudioContext; });

  it('stops after speech followed by silence and sends one 16 kHz WAV', async () => {
    const { rec, transcribe, cb } = setup();
    await rec.start();
    expect(cb.onInterim).toHaveBeenCalledWith('listening');
    for (let i = 0; i < 5; i++) processor.onaudioprocess(frame(0.2));       // speech
    for (let i = 0; i < 16; i++) processor.onaudioprocess?.(frame(0));       // ≥ 1.2 s of silence (handler detaches when it stops)
    await flush(); await flush();
    expect(transcribe).toHaveBeenCalledTimes(1);
    const [wav, lang] = transcribe.mock.calls[0];
    expect(lang).toBe('auto');
    expect(wav.type).toBe('audio/wav');
    const view = new DataView(await bytes(wav));
    expect(view.getUint32(24, true)).toBe(16000);                            // resampled from 48 kHz
    expect(cb.onFinal).toHaveBeenCalledWith('வணக்கம்', expect.objectContaining({ engine: 'server', detected: 'ta', probability: 0.8 }));
    expect(track.stop).toHaveBeenCalled();                                   // microphone released
    expect(cb.onEnd).toHaveBeenCalledTimes(1);
  });

  it('gives up with no-speech when nothing is said', async () => {
    const { rec, transcribe, cb } = setup();
    await rec.start();
    processor.onaudioprocess(frame(0));
    vi.advanceTimersByTime(6500);
    await flush();
    expect(cb.onError).toHaveBeenCalledWith('no-speech');
    expect(transcribe).not.toHaveBeenCalled();
    expect(track.stop).toHaveBeenCalled();
  });

  it('caps one utterance at 15 seconds', async () => {
    const { rec, transcribe } = setup();
    await rec.start();
    processor.onaudioprocess(frame(0.2));
    vi.advanceTimersByTime(15250);
    await flush(); await flush();
    expect(transcribe).toHaveBeenCalledTimes(1);
  });

  it('cancel discards the recording without transcribing', async () => {
    const { rec, transcribe, cb } = setup();
    await rec.start();
    processor.onaudioprocess(frame(0.2));
    await rec.cancel();
    expect(transcribe).not.toHaveBeenCalled();
    expect(cb.onFinal).not.toHaveBeenCalled();
    expect(cb.onError).not.toHaveBeenCalled();
    expect(track.stop).toHaveBeenCalled();
  });

  it.each([['NotAllowedError', 'not-allowed'], ['NotFoundError', 'audio-capture'], ['AbortError', 'failed']])(
    'reports a microphone %s as %s', async (name, code) => {
      const { rec, cb } = setup({ getUserMedia: vi.fn().mockRejectedValue(Object.assign(new Error('x'), { name })) });
      await rec.start();
      expect(cb.onError).toHaveBeenCalledWith(code);
      expect(cb.onEnd).toHaveBeenCalled();
    });

  it('a transcription that never returns times out as a network problem', async () => {
    vi.useRealTimers();
    const { rec, cb } = setup({ transcribe: () => new Promise(() => {}), transcribeTimeoutMs: 30 });
    await rec.start();
    processor.onaudioprocess(frame(0.2));
    rec.stop();
    await new Promise((r) => setTimeout(r, 60));
    expect(cb.onError).toHaveBeenCalledWith('network');
    expect(cb.onEnd).toHaveBeenCalledTimes(1);
  });

  it('an unreachable server is reported as network (shown in the conversation language)', async () => {
    const { rec, cb } = setup({ transcribe: vi.fn().mockRejectedValue(Object.assign(new Error('Cannot reach the server.'), { code: 'network' })) });
    await rec.start();
    processor.onaudioprocess(frame(0.2));
    await rec.stop();
    expect(cb.onError).toHaveBeenCalledWith('network');
  });
});

describe('encodeWav', () => {
  it('writes a PCM RIFF/WAVE header with clamped samples', async () => {
    const view = new DataView(await bytes(encodeWav(new Float32Array([0, 1, -1, 2]))));
    expect(String.fromCharCode(...[0, 1, 2, 3].map((i) => view.getUint8(i)))).toBe('RIFF');
    expect(view.getUint16(20, true)).toBe(1);            // PCM
    expect(view.getUint16(34, true)).toBe(16);           // 16-bit
    expect(view.getUint32(40, true)).toBe(8);            // 4 samples × 2 bytes
    expect(view.getInt16(50, true)).toBe(32767);         // 2 → clamped to 1
  });
});

describe('pickVoice (local voices only)', () => {
  const V = (name, lang, localService = true) => ({ name, lang, localService });
  const voices = [V('Google हिन्दी', 'hi-IN', false), V('Lekha', 'hi-IN'), V('Vani', 'ta-IN'), V('Samantha', 'en-US'), V('Rishi', 'en-IN')];
  it('never picks a remote voice', () => {
    expect(pickVoice([V('Google हिन्दी', 'hi-IN', false)], 'hi-IN')).toBeNull();
    expect(pickVoice(voices, 'hi-IN').name).toBe('Lekha');
  });
  it('prefers the exact locale, then the same language', () => {
    expect(pickVoice(voices, 'en-IN').name).toBe('Rishi');
    expect(pickVoice(voices, 'ta-IN').name).toBe('Vani');
    expect(pickVoice([V('Samantha', 'en_US')], 'en-IN').name).toBe('Samantha');
    expect(pickVoice(voices, 'te-IN')).toBeNull();      // no Telugu voice → nothing (never a wrong-language voice)
  });
});

describe('speaker interruption', () => {
  let synth;
  beforeEach(() => {
    synth = { getVoices: vi.fn(() => []), speak: vi.fn(), cancel: vi.fn(), addEventListener: vi.fn(), removeEventListener: vi.fn() };
    Object.defineProperty(window, 'speechSynthesis', { value: synth, configurable: true });
    globalThis.SpeechSynthesisUtterance = function U(text) { this.text = text; };
  });
  afterEach(() => { delete window.speechSynthesis; delete globalThis.SpeechSynthesisUtterance; });

  it('speaks with the matching local voice', async () => {
    synth.getVoices.mockReturnValue([{ name: 'Vani', lang: 'ta-IN', localService: true }]);
    expect(await speaker.speak('வணக்கம்', 'ta')).toEqual({ mode: 'browser', voice: 'Vani' });
    expect(synth.speak).toHaveBeenCalledTimes(1);
  });

  it('a reply interrupted while voices are still loading is never spoken', async () => {
    let fire;
    synth.addEventListener.mockImplementation((_, fn) => { fire = fn; });
    const pending = speaker.speak('நீண்ட பதில்', 'ta');
    speaker.cancel();                                                         // customer pressed the mic / closed the chat
    synth.getVoices.mockReturnValue([{ name: 'Vani', lang: 'ta-IN', localService: true }]);
    fire();
    expect(await pending).toEqual({ mode: 'cancelled', voice: null });
    expect(synth.speak).not.toHaveBeenCalled();
  });

  it('server audio that arrives after an interruption is not played', async () => {
    let resolveBlob;
    const serverTts = () => new Promise((r) => { resolveBlob = r; });
    synth.addEventListener.mockImplementation((_, fn) => fn());               // voices list arrives, still no Tamil voice
    const play = vi.fn().mockResolvedValue(undefined);
    globalThis.Audio = vi.fn(() => ({ play, pause: vi.fn(), addEventListener: vi.fn() }));
    const pending = speaker.speak('நீண்ட பதில்', 'ta', { serverTts });
    await flush();
    speaker.cancel();
    resolveBlob(new Blob(['x']));
    expect(await pending).toEqual({ mode: 'cancelled', voice: null });
    expect(play).not.toHaveBeenCalled();
    delete globalThis.Audio;
  });

  it('without any voice the result is text only', async () => {
    synth.addEventListener.mockImplementation((_, fn) => fn());
    expect(await speaker.speak('नमस्ते', 'hi')).toEqual({ mode: 'none', voice: null });
  });
});

describe('speaker speaking state (UI indicator)', () => {
  let synth, utter;
  beforeEach(() => {
    synth = { getVoices: vi.fn(() => [{ name: 'Lekha', lang: 'hi-IN', localService: true }]), speak: vi.fn((u) => { utter = u; }), cancel: vi.fn(),
      addEventListener: vi.fn(), removeEventListener: vi.fn() };
    Object.defineProperty(window, 'speechSynthesis', { value: synth, configurable: true });
    globalThis.SpeechSynthesisUtterance = function U(text) { this.text = text; };
  });
  afterEach(() => { delete window.speechSynthesis; delete globalThis.SpeechSynthesisUtterance; speaker.onChange = null; });

  it('is true from the start of a spoken reply until it ends, and false when interrupted', async () => {
    const seen = [];
    speaker.onChange = (v) => seen.push(v);
    await speaker.speak('नमस्ते', 'hi');
    expect(speaker.speaking).toBe(true);
    utter.onend();
    expect(speaker.speaking).toBe(false);
    await speaker.speak('फिर से', 'hi');
    speaker.cancel();                                   // the customer pressed Stop / the mic
    expect(seen).toEqual([true, false, true, false]);
  });
});
