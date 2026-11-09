import React, { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useStore } from './StoreApp.jsx';
import ProductCard from './components/ProductCard.jsx';
import OrderCard from './components/OrderCard.jsx';
import { selectRecognizer, speaker, voiceSupport } from './voice.js';
import { DEFAULT_LANGUAGE, LANGUAGES, SUPPORTED, suggestionsFor, tr } from './i18n.js';

const SPEAK_PREF_KEY = 'avc:speak-replies';

function readPref() {
  try {
    return localStorage.getItem(SPEAK_PREF_KEY) === '1';
  } catch {
    return false;
  }
}

// The conversation language lives in sessionStorage per store: a new tab (new guest conversation)
// starts in Tamil, and Store A and Store B never share it.
function loadConversationLanguage(key) {
  try {
    const v = sessionStorage.getItem(key);
    return SUPPORTED.includes(v) ? v : DEFAULT_LANGUAGE;
  } catch {
    return DEFAULT_LANGUAGE;
  }
}

export default function ChatWidget({ open, prefill, onOpen, onClose }) {
  const { api, config, session } = useStore();
  const convKey = `avc:${config.storeId}:conversation-language`;
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const [interim, setInterim] = useState('');
  const [voiceNotice, setVoiceNotice] = useState(null);
  const [speakReplies, setSpeakReplies] = useState(readPref);
  const [speechCaps, setSpeechCaps] = useState(null);
  const [lang, setLang] = useState(() => loadConversationLanguage(convKey));
  const recognizerRef = useRef(null);
  // Refs let the speech callbacks (created once per mic press) see current state.
  const messagesRef = useRef(messages);
  const langRef = useRef(lang);
  const busyRef = useRef(false);
  messagesRef.current = messages;
  langRef.current = lang;
  const listRef = useRef(null);
  const inputRef = useRef(null);
  const actionBusy = useRef(false);
  const [confirming, setConfirming] = useState(null); // `${messageId}:${index}` of a cancel awaiting confirmation
  const navigate = useNavigate();
  const support = voiceSupport();
  const t = (key, values) => tr(lang, key, values);

  useEffect(() => {
    try {
      sessionStorage.setItem(convKey, lang);
    } catch {
      /* the language just won't survive a reload */
    }
  }, [convKey, lang]);

  useEffect(() => {
    if (open) {
      if (prefill) setInput(prefill);
      setTimeout(() => inputRef.current?.focus(), 0);
    } else {
      speaker.cancel();
      // Closing the chat discards an unfinished recording instead of sending it.
      const rec = recognizerRef.current;
      if (rec?.cancel) rec.cancel(); else rec?.stop();
    }
  }, [open, prefill]);

  // Ask once whether this store's server offers local speech recognition / synthesis.
  useEffect(() => {
    if (open && speechCaps === null) api.speechCapabilities().then(setSpeechCaps, () => setSpeechCaps({}));
  }, [open, speechCaps, api]);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
  }, [messages, interim, busy, confirming]);

  useEffect(() => {
    try {
      localStorage.setItem(SPEAK_PREF_KEY, speakReplies ? '1' : '0');
    } catch {
      /* preference just won't persist */
    }
    if (!speakReplies) speaker.cancel();
  }, [speakReplies]);

  const serverStt = !!speechCaps?.server_stt?.available;
  const autoDetect = serverStt && !!speechCaps?.server_stt?.language_detection;
  const serverTtsVoices = speechCaps?.server_tts?.available ? speechCaps.server_tts.voices || {} : {};

  async function say(text, replyLang) {
    const serverTts = serverTtsVoices[replyLang] ? (txt, l) => api.synthesize(txt, l) : null;
    const result = await speaker.speak(text, replyLang, { serverTts });
    if (result.mode === 'none') setVoiceNotice(tr(langRef.current, 'noVoice', { lang: LANGUAGES[replyLang].native }));
    return result;
  }

  async function send(text, { viaVoice = false, voiceMeta = null, override = null } = {}) {
    const message = text.trim();
    if (!message || busyRef.current) return;
    const history = messagesRef.current.filter((m) => !m.error).slice(-8).map((m) => ({ role: m.role, content: m.content.slice(0, 2000) }));
    setMessages((m) => [...m, { role: 'user', content: message, viaVoice, voiceMeta }]);
    setInput('');
    setVoiceNotice(null);
    busyRef.current = true;
    setBusy(true);
    try {
      const r = await api.chat(message, history, viaVoice ? 'web_voice' : 'web_chat', {
        conversationLanguage: langRef.current, speechReceipt: voiceMeta?.receipt, languageOverride: override,
      });
      const id = `${Date.now()}-${Math.random()}`;
      const reply = {
        id, role: 'assistant', content: r.reply, products: r.products, orders: r.orders, requiresLogin: r.requires_login, source: r.source,
        actions: r.actions || [], viaVoice,
        cart: r.cart, language: r.language, languageStatus: r.language_status, clarification: r.clarification, retry: { text: message, voiceMeta },
      };
      // The conversation follows the language of each new utterance (not on a clarification).
      if (!r.clarification) setLang(r.language);
      setMessages((m) => [...m, reply]);
      if (viaVoice || speakReplies) {
        say(r.reply, r.language).then((tts) => setMessages((m) => m.map((x) => (x.id === id ? { ...x, tts } : x))));
      }
    } catch (e) {
      setMessages((m) => [...m, { role: 'assistant', content: e.status === 429 ? tr(langRef.current, 'rateLimited') : e.message, error: true }]);
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }

  // After a clarification the customer picks a language explicitly. Voice: re-transcribe the SAME recording
  // in that language. Text: resend. Either way the server labels it as the customer's choice, not detection.
  async function chooseLanguage(code, retry) {
    setLang(code);
    let text = retry.text;
    let voiceMeta = retry.voiceMeta;
    if (retry.voiceMeta?.audio) {
      try {
        const r = await api.transcribe(retry.voiceMeta.audio, code);
        text = r.text || text;
        voiceMeta = { ...retry.voiceMeta, receipt: null, detected: null, chosen: code };
      } catch {
        /* keep the original transcript */
      }
    }
    send(text, { viaVoice: !!retry.voiceMeta, voiceMeta, override: code });
  }

  // Action buttons proposed by the assistant. The existing store API performs and validates every action;
  // the chat says it happened only after that API call succeeds.
  async function runAction(m, a, key) {
    if (actionBusy.current) return;
    if (a.type === 'link') {
      if (a.to.startsWith('mailto:')) { window.location.href = a.to; return; }
      onClose();
      navigate(a.to);
      return;
    }
    if (a.type === 'cancel_order' && confirming !== key) { setConfirming(key); return; }
    actionBusy.current = true;
    setBusy(true);
    const replyLang = m.language || langRef.current;
    let text;
    let ok = false;
    try {
      if (a.type === 'add_to_cart') {
        const cart = await api.addToCart(a.slug, a.quantity);
        ok = cart.items.some((i) => i.slug === a.slug);
        text = ok ? tr(replyLang, 'actionAdded', { qty: a.quantity, name: a.name }) : tr(replyLang, 'actionFailed');
      } else if (a.type === 'cancel_order') {
        const r = await api.cancelOrder(a.order_number);
        ok = r.order?.status === 'cancelled';
        text = ok ? tr(replyLang, 'actionCancelled', { number: a.order_number }) : tr(replyLang, 'actionFailed');
      }
    } catch (e) {
      text = `${tr(replyLang, 'actionFailed')} ${e.message}`;
    } finally {
      actionBusy.current = false;
      setBusy(false);
      setConfirming(null);
    }
    if (!text) return;
    setMessages((ms) => [
      ...ms.map((x) => (x.id === m.id ? { ...x, done: { ...(x.done || {}), [key]: ok } } : x)),
      { id: `${Date.now()}-a`, role: 'assistant', content: text, language: replyLang, system: true, error: !ok },
    ]);
    if (m.viaVoice || speakReplies) say(text, replyLang);
  }

  function actionButtons(m) {
    return (
      <div className="chat-actions">
        {m.actions.map((a, i) => {
          const key = `${m.id}:${i}`;
          if (a.type === 'link') {
            return a.to.startsWith('mailto:')
              ? <a key={key} className="btn btn-small" href={a.to}>{a.label}</a>
              : <button key={key} type="button" className="btn btn-small" onClick={() => runAction(m, a, key)}>{a.label}</button>;
          }
          if (m.done && key in m.done) {
            return <span key={key} className="chat-action-done">{m.done[key] ? '✓ ' : ''}{a.label}</span>;
          }
          if (a.type === 'cancel_order' && confirming === key) {
            return (
              <span key={key} className="chat-confirm" role="group" aria-label={tr(m.language || lang, 'confirmCancelAsk')}>
                <span className="muted">{tr(m.language || lang, 'confirmCancelAsk')}</span>
                <button type="button" className="btn btn-small btn-danger" disabled={busy} onClick={() => runAction(m, a, key)}>
                  {tr(m.language || lang, 'confirmCancel', { number: a.order_number })}
                </button>
                <button type="button" className="btn btn-small" onClick={() => setConfirming(null)}>{tr(m.language || lang, 'keepOrder')}</button>
              </span>
            );
          }
          return (
            <button key={key} type="button" className={`btn btn-small ${a.type === 'add_to_cart' ? 'btn-primary' : ''}`}
              disabled={busy} onClick={() => runAction(m, a, key)}>{a.label}</button>
          );
        })}
      </div>
    );
  }

  function toggleMic() {
    if (listening) {
      recognizerRef.current?.stop();
      return;
    }
    setVoiceNotice(null);
    if (!support.secureContext) {
      setVoiceNotice(t('insecure'));
      return;
    }
    const rec = selectRecognizer(speechCaps, {
      // Server engine: identifies the language from the audio ('auto'). Browser engine: must listen in one locale.
      language: 'auto',
      lang: LANGUAGES[langRef.current].bcp47,
      transcribe: api.transcribe,
      onInterim: (s) => setInterim(s === 'listening' || s === 'transcribing' ? tr(langRef.current, s) : s),
      onFinal: (text, meta) => {
        setInterim('');
        if (text) send(text, { viaVoice: true, voiceMeta: meta });
      },
      onError: (code, detail) => setVoiceNotice(code === 'failed' && detail ? detail : tr(langRef.current, code)),
      onEnd: () => {
        setListening(false);
        setInterim('');
      },
    });
    if (!rec) {
      setVoiceNotice(t('unsupported'));
      return;
    }
    recognizerRef.current = rec;
    speaker.cancel();
    setListening(true);
    rec.start();
  }

  function languageTag(m) {
    const name = LANGUAGES[m.language]?.native;
    if (!name || m.clarification) return null;
    const key = m.languageStatus === 'detected' ? 'langDetected' : m.languageStatus === 'selected' ? 'langSelected' : 'langNeutral';
    return tr(lang, key, { lang: name });
  }

  if (!open) {
    return (
      <button type="button" className="chat-launcher" onClick={onOpen} aria-label={`Open chat with ${config.assistantName}`}>
        <span aria-hidden="true">💬</span> <span className="launcher-label">Ask {config.assistantName}</span>
      </button>
    );
  }

  return (
    <section className="chat-panel" role="dialog" aria-modal="false" aria-labelledby="chat-title" lang={LANGUAGES[lang].bcp47}>
      <header className="chat-header">
        <div>
          <h2 id="chat-title">{config.assistantName}</h2>
          <p>{t('subtitle', { store: config.name })}{session ? t('signedInAs', { name: session.customer.name.split(' ')[0] }) : ''}</p>
        </div>
        <button type="button" className="icon-btn" onClick={onClose} aria-label={t('close')}>✕</button>
      </header>

      <div className="chat-log" ref={listRef} aria-live="polite" aria-relevant="additions">
        {messages.length === 0 && (
          <div className="chat-empty">
            <p>{t('welcome', { assistant: config.assistantName })}</p>
            <div className="chips">
              {suggestionsFor(config, lang).map((s) => (
                <button key={s} type="button" className="chip" onClick={() => send(s)}>{s}</button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`bubble bubble-${m.role} ${m.error ? 'bubble-error' : ''}`}
            lang={m.language ? LANGUAGES[m.language].bcp47 : undefined}
            data-language={m.language} data-tts={m.tts ? `${m.tts.mode}:${m.tts.voice || ''}` : undefined}>
            <span className="sr-only">{m.role === 'user' ? t('youSaid') : t('assistantSaid', { assistant: config.assistantName })}: </span>
            {m.viaVoice && <span className="voice-tag" aria-hidden="true">🎤</span>}
            <p>{m.content}</p>
            {m.products?.length > 0 && (
              <div className="bubble-cards">{m.products.map((p) => <ProductCard key={p.slug} product={p} compact />)}</div>
            )}
            {m.orders?.length > 0 && (
              <div className="bubble-cards">{m.orders.map((o) => <OrderCard key={o.order_number} order={o} />)}</div>
            )}
            {m.clarification && (
              <div className="chips lang-choice" role="group" aria-label={t('chooseLanguage')}>
                <span className="muted">{t('chooseLanguage')}</span>
                {SUPPORTED.map((c) => (
                  <button key={c} type="button" className="chip" lang={LANGUAGES[c].bcp47} disabled={busy}
                    onClick={() => chooseLanguage(c, m.retry)}>{LANGUAGES[c].native}</button>
                ))}
              </div>
            )}
            {m.requiresLogin && <Link className="btn btn-primary btn-small" to="/account" onClick={onClose}>{t('signIn')}</Link>}
            {m.actions?.length > 0 && actionButtons(m)}
            {m.cart?.items?.length > 0 && <Link className="btn btn-small" to="/cart" onClick={onClose}>{t('viewCart')}</Link>}
            {m.role === 'assistant' && !m.error && !m.system && (
              <span className="source-tag">
                {languageTag(m)}{languageTag(m) && m.source === 'rules' ? ' · ' : ''}{m.source === 'rules' ? t('quickAnswer') : ''}
              </span>
            )}
          </div>
        ))}
        {interim && <div className="bubble bubble-user bubble-interim"><p>{interim}…</p></div>}
        {busy && <div className="bubble bubble-assistant typing" aria-label={t('typing')}><span /><span /><span /></div>}
      </div>

      {voiceNotice && <p className="notice notice-warn chat-notice" role="status">{voiceNotice}</p>}

      <form className="chat-input" onSubmit={(e) => { e.preventDefault(); send(input); }}>
        <label htmlFor="chat-message" className="sr-only">{t('typeLabel')}</label>
        <input id="chat-message" ref={inputRef} value={input} maxLength={1000} autoComplete="off"
          placeholder={listening ? `${t('listening')}…` : t('placeholder')} onChange={(e) => setInput(e.target.value)} />
        <button type="button" className={`icon-btn mic ${listening ? 'mic-on' : ''}`} onClick={toggleMic}
          aria-pressed={listening} aria-label={listening ? t('stopVoice') : t('speak')}
          title={support.recognition || serverStt ? t('speak') : t('unsupported')}>
          🎤
        </button>
        <button type="submit" className="btn btn-primary" disabled={busy || !input.trim()}>{t('send')}</button>
      </form>
      <div className="chat-footer">
        <label className="voice-lang">
          {t('conversationLanguage')}
          {/* An explicit choice: sets the language for greetings, prompts, clarifications and language-neutral messages.
              Each new utterance is still identified from its own words. */}
          <select value={lang} onChange={(e) => setLang(e.target.value)} disabled={listening} data-testid="conversation-language">
            {SUPPORTED.map((c) => <option key={c} value={c}>{LANGUAGES[c].native}</option>)}
          </select>
        </label>
        {speechCaps !== null && (
          <span className="lang-note">{autoDetect ? t('autoDetectOn') : t('autoDetectOff', { lang: LANGUAGES[lang].native })}</span>
        )}
        <label className="toggle">
          <input type="checkbox" checked={speakReplies} disabled={!support.synthesis && !Object.keys(serverTtsVoices).length}
            onChange={(e) => setSpeakReplies(e.target.checked)} />
          {t('readAloud')}
        </label>
        {serverStt ? (
          <span className="privacy-note">{t('privacyServer', { store: config.name })}</span>
        ) : support.recognition && <span className="privacy-note">{t('privacyBrowser')}</span>}
      </div>
    </section>
  );
}
