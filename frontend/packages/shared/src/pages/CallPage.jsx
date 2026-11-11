// "Call us" — the customer-care phone line, SIMULATED in the browser (no telephone network is involved).
// It drives the same call flow a real phone provider would (backend app/phone/session.py): the caller speaks (browser or
// local speech engine, as in the chat), presses keypad digits, or types; Scout / Maple answers in Tamil, English or Hindi
// and the answer is read aloud. Verification, care requests and every rule stay on the server; this page only relays turns.
import React, { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useStore } from '../StoreApp.jsx';
import { ui } from '../uiText.js';
import { DEFAULT_LANGUAGE, LANGUAGES, tr } from '../i18n.js';
import { selectRecognizer, speaker, voiceSupport } from '../voice.js';

const KEYS = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '*', '0', '#'];
const KEY_IDLE_MS = 1500;       // keys pressed together are sent as one entry (an order number, a PIN code)
const REFERENCE = /\b(?:SA|BB)-(?:CMP|RET|RFD|ESC)-\d{5,}\b/g;

export default function CallPage() {
  const store = useStore();
  const { api, config } = store;
  const t = store.t || ((key, vars) => ui('en', key, vars));
  const [lang, setLang] = useState(DEFAULT_LANGUAGE);          // the language the call opens in
  const [call, setCall] = useState(null);                       // { id, ended }
  const [lines, setLines] = useState([]);                       // { who: 'bot' | 'you', text, lang }
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [keys, setKeys] = useState('');
  const [typed, setTyped] = useState('');
  const [listening, setListening] = useState(false);
  const [interim, setInterim] = useState('');
  const [voiceNotice, setVoiceNotice] = useState(null);
  const [caps, setCaps] = useState(null);
  const callRef = useRef(null);
  const callLang = useRef(lang);
  const keysRef = useRef('');
  const keyTimer = useRef(null);
  const recRef = useRef(null);
  const logRef = useRef(null);

  useEffect(() => {
    let live = true;
    api.speechCapabilities?.().then((c) => live && setCaps(c), () => live && setCaps({}));
    return () => {
      live = false;
      speaker.cancel();
      recRef.current?.stop?.();
      clearTimeout(keyTimer.current);
    };
  }, [api]);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [lines, interim]);

  const active = !!call && !call.ended;

  function setCallState(c) {
    callRef.current = c;
    setCall(c);
  }

  function hear(out) {
    callLang.current = out.language || callLang.current;
    setLines((l) => [...l, { who: 'bot', text: out.say, lang: callLang.current }]);
    speaker.speak(out.say, callLang.current, { serverTts: api.synthesize });
    if (out.hang_up) setCallState({ ...callRef.current, ended: true });
  }

  async function start() {
    setError(null);
    setVoiceNotice(null);
    setLines([]);
    setBusy(true);
    try {
      const out = await api.phoneStart(lang);
      setCallState({ id: out.call_id, ended: false });
      hear(out);
    } catch (e) {
      setError(e.status === 404 ? t('callUnavailable') : e.status === 429 ? t('callBusy') : e.message);
    } finally {
      setBusy(false);
    }
  }

  async function turn(body, shown) {
    const c = callRef.current;
    if (!c || c.ended) return;
    speaker.cancel();
    setLines((l) => [...l, { who: 'you', text: shown }]);
    setBusy(true);
    try {
      hear(await api.phoneTurn(c.id, body));
    } catch (e) {
      if (e.status === 404) setCallState({ ...c, ended: true });
      setError(t('callFailed', { reason: e.message }));
    } finally {
      setBusy(false);
    }
  }

  function hangUp() {
    speaker.cancel();
    recRef.current?.stop?.();
    clearTimeout(keyTimer.current);
    keysRef.current = '';
    setKeys('');
    setCallState({ ...callRef.current, ended: true });
  }

  function sendKeys() {
    clearTimeout(keyTimer.current);
    const entry = keysRef.current.replace(/#$/, '');
    keysRef.current = '';
    setKeys('');
    if (entry) turn({ digits: entry }, t('callKeys', { keys: entry }));
  }

  function press(k) {
    if (!active) return;
    speaker.cancel();               // like a phone menu: pressing a key interrupts the prompt
    clearTimeout(keyTimer.current);
    keysRef.current += k;
    setKeys(keysRef.current);
    if (k === '#') sendKeys();
    else keyTimer.current = setTimeout(sendKeys, KEY_IDLE_MS);
  }

  function say(e) {
    e.preventDefault();
    const text = typed.trim();
    if (!text || !active) return;
    setTyped('');
    turn({ speech: text }, text);
  }

  function toggleMic() {
    if (listening) {
      recRef.current?.stop?.();
      return;
    }
    setVoiceNotice(null);
    if (!voiceSupport().secureContext) {
      setVoiceNotice(tr(callLang.current, 'insecure'));
      return;
    }
    const rec = selectRecognizer(caps, {
      language: 'auto',
      lang: LANGUAGES[callLang.current]?.bcp47 || 'ta-IN',
      transcribe: api.transcribe,
      onInterim: (s) => setInterim(s === 'listening' || s === 'transcribing' ? tr(callLang.current, s) : s),
      onFinal: (text) => {
        setInterim('');
        if (text) turn({ speech: text }, text);
      },
      onError: (code, detail) => {
        // On a phone line, saying nothing is silence: the assistant asks again (and never counts it as a wrong answer).
        if (code === 'no-speech') turn({ speech: '' }, t('callSilence'));
        else setVoiceNotice(code === 'failed' && detail ? detail : tr(callLang.current, code));
      },
      onEnd: () => {
        setListening(false);
        setInterim('');
      },
    });
    if (!rec) {
      setVoiceNotice(tr(callLang.current, 'unsupported'));
      return;
    }
    recRef.current = rec;
    speaker.cancel();
    setListening(true);
    rec.start();
  }

  function withReferences(text) {
    const parts = [];
    let last = 0;
    for (const m of text.matchAll(REFERENCE)) {
      parts.push(text.slice(last, m.index));
      parts.push(<Link key={m.index} to={`/support/requests/${m[0]}`}>{m[0]}</Link>);
      last = m.index + m[0].length;
    }
    parts.push(text.slice(last));
    return parts;
  }

  return (
    <section className="support-page call-page" aria-labelledby="call-title">
      <h1 id="call-title">{t('callTitle', { store: config.name })}</h1>
      <p className="notice notice-info">{t('callSimNote', { assistant: config.assistantName })}</p>

      <div className="card call-card">
        <div className="call-status" role="status">
          <span className={`call-dot ${active ? 'call-dot-live' : ''}`} aria-hidden="true" />
          {active ? t('callConnected', { assistant: config.assistantName }) : call ? t('callEnded') : t('callIdle')}
        </div>

        {!active && (
          <div className="call-start">
            <label>
              {t('callLanguage')}{' '}
              <select value={lang} onChange={(e) => setLang(e.target.value)} data-testid="call-language">
                {Object.entries(LANGUAGES).map(([code, l]) => <option key={code} value={code} lang={l.bcp47}>{l.native}</option>)}
              </select>
            </label>
            <button type="button" className="btn btn-primary call-btn" onClick={start} disabled={busy}>
              {call ? t('callAgain') : t('callStart')}
            </button>
          </div>
        )}

        {error && <p className="notice notice-error" role="alert">{error}</p>}

        {lines.length > 0 && (
          <ol className="call-log" ref={logRef} aria-live="polite" aria-label={t('callTranscript')}>
            {lines.map((l, i) => (
              <li key={i} className={`call-line call-${l.who}`} lang={l.who === 'bot' ? LANGUAGES[l.lang]?.bcp47 : undefined}>
                <strong>{l.who === 'bot' ? config.assistantName : t('callYou')}:</strong> {l.who === 'bot' ? withReferences(l.text) : l.text}
              </li>
            ))}
            {interim && <li className="call-line call-you muted">{interim}…</li>}
          </ol>
        )}

        {active && (
          <div className="call-controls">
            <button type="button" className={`btn call-mic ${listening ? 'mic-on' : ''}`} onClick={toggleMic} disabled={busy && !listening}
              aria-pressed={listening}>
              {listening ? t('callStopListening') : t('callSpeak')}
            </button>
            <div className="call-keypad" role="group" aria-label={t('callKeypad')}>
              {KEYS.map((k) => (
                <button key={k} type="button" className="btn call-key" onClick={() => press(k)} disabled={busy}
                  aria-label={k === '#' ? t('callKeysSend') : k}>{k}</button>
              ))}
            </div>
            {keys && <p className="muted" aria-live="polite">{t('callKeys', { keys })}</p>}
            <form className="call-type" onSubmit={say}>
              <label className="sr-only" htmlFor="call-typed">{t('callType')}</label>
              <input id="call-typed" value={typed} onChange={(e) => setTyped(e.target.value)} placeholder={t('callType')}
                disabled={busy} autoComplete="off" />
              <button type="submit" className="btn" disabled={busy || !typed.trim()}>{t('callSend')}</button>
            </form>
            <button type="button" className="btn btn-danger call-btn" onClick={hangUp}>{t('callHangUp')}</button>
          </div>
        )}
        {voiceNotice && <p className="notice notice-warn" role="alert">{voiceNotice}</p>}
      </div>

      <p className="muted">{t('callHint')}</p>
      <p className="muted">{t('callVoiceNote')}</p>
    </section>
  );
}
