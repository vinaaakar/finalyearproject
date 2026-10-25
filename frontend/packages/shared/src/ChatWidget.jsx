import React, { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useStore } from './StoreApp.jsx';
import ProductCard from './components/ProductCard.jsx';
import OrderCard from './components/OrderCard.jsx';
import { selectRecognizer, speaker, voiceSupport } from './voice.js';

const SPEAK_PREF_KEY = 'avc:speak-replies';

function readPref() {
  try {
    return localStorage.getItem(SPEAK_PREF_KEY) === '1';
  } catch {
    return false;
  }
}

export default function ChatWidget({ open, prefill, onOpen, onClose }) {
  const { api, config, session } = useStore();
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const [interim, setInterim] = useState('');
  const [voiceNotice, setVoiceNotice] = useState(null);
  const [speakReplies, setSpeakReplies] = useState(readPref);
  const recognizerRef = useRef(null);
  // Refs let the speech callbacks (created once per mic press) see current state.
  const messagesRef = useRef(messages);
  const busyRef = useRef(false);
  messagesRef.current = messages;
  const listRef = useRef(null);
  const inputRef = useRef(null);
  const support = voiceSupport();

  useEffect(() => {
    if (open) {
      if (prefill) setInput(prefill);
      setTimeout(() => inputRef.current?.focus(), 0);
    } else {
      speaker.cancel();
      recognizerRef.current?.stop();
    }
  }, [open, prefill]);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
  }, [messages, interim, busy]);

  useEffect(() => {
    try {
      localStorage.setItem(SPEAK_PREF_KEY, speakReplies ? '1' : '0');
    } catch {
      /* preference just won't persist */
    }
    if (!speakReplies) speaker.cancel();
  }, [speakReplies]);

  async function send(text, viaVoice = false) {
    const message = text.trim();
    if (!message || busyRef.current) return;
    const history = messagesRef.current.filter((m) => !m.error).slice(-8).map((m) => ({ role: m.role, content: m.content.slice(0, 2000) }));
    setMessages((m) => [...m, { role: 'user', content: message, viaVoice }]);
    setInput('');
    busyRef.current = true;
    setBusy(true);
    try {
      const r = await api.chat(message, history, viaVoice ? 'web_voice' : 'web_chat');
      setMessages((m) => [...m, { role: 'assistant', content: r.reply, products: r.products, orders: r.orders, requiresLogin: r.requires_login, source: r.source }]);
      if (viaVoice || speakReplies) speaker.speak(r.reply, { lang: config.lang });
    } catch (e) {
      setMessages((m) => [...m, { role: 'assistant', content: e.status === 429 ? 'You’re sending messages quickly — please wait a moment and try again.' : e.message, error: true }]);
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }

  function toggleMic() {
    if (listening) {
      recognizerRef.current?.stop();
      return;
    }
    setVoiceNotice(null);
    if (!support.secureContext) {
      setVoiceNotice('Voice input needs a secure (https or localhost) page.');
      return;
    }
    const rec = selectRecognizer(null, {
      lang: config.lang,
      onInterim: setInterim,
      onFinal: (t) => {
        setInterim('');
        if (t) send(t, true);
      },
      onError: (msg) => setVoiceNotice(msg),
      onEnd: () => {
        setListening(false);
        setInterim('');
      },
    });
    if (!rec) {
      setVoiceNotice('Voice input isn’t supported in this browser. Try Chrome, Edge or Safari, or type your question.');
      return;
    }
    recognizerRef.current = rec;
    speaker.cancel();
    setListening(true);
    rec.start();
  }

  if (!open) {
    return (
      <button type="button" className="chat-launcher" onClick={onOpen} aria-label={`Open chat with ${config.assistantName}`}>
        <span aria-hidden="true">💬</span> Ask {config.assistantName}
      </button>
    );
  }

  return (
    <section className="chat-panel" role="dialog" aria-modal="false" aria-labelledby="chat-title">
      <header className="chat-header">
        <div>
          <h2 id="chat-title">{config.assistantName}</h2>
          <p>{config.name} customer service{session ? ` · signed in as ${session.customer.name.split(' ')[0]}` : ''}</p>
        </div>
        <button type="button" className="icon-btn" onClick={onClose} aria-label="Close chat">✕</button>
      </header>

      <div className="chat-log" ref={listRef} aria-live="polite" aria-relevant="additions">
        {messages.length === 0 && (
          <div className="chat-empty">
            <p>Hi! I can help with products, prices, stock, shipping, returns and order status.</p>
            <div className="chips">
              {config.suggestions.map((s) => (
                <button key={s} type="button" className="chip" onClick={() => send(s)}>{s}</button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`bubble bubble-${m.role} ${m.error ? 'bubble-error' : ''}`}>
            <span className="sr-only">{m.role === 'user' ? 'You said' : `${config.assistantName} said`}: </span>
            {m.viaVoice && <span className="voice-tag" aria-label="spoken">🎤</span>}
            <p>{m.content}</p>
            {m.products?.length > 0 && (
              <div className="bubble-cards">{m.products.map((p) => <ProductCard key={p.slug} product={p} compact />)}</div>
            )}
            {m.orders?.length > 0 && (
              <div className="bubble-cards">{m.orders.map((o) => <OrderCard key={o.order_number} order={o} />)}</div>
            )}
            {m.requiresLogin && <Link className="btn btn-primary btn-small" to="/account" onClick={onClose}>Sign in</Link>}
            {m.role === 'assistant' && !m.error && m.source === 'rules' && <span className="source-tag">quick answer</span>}
          </div>
        ))}
        {interim && <div className="bubble bubble-user bubble-interim"><p>{interim}…</p></div>}
        {busy && <div className="bubble bubble-assistant typing" aria-label="Assistant is typing"><span /><span /><span /></div>}
      </div>

      {voiceNotice && <p className="notice notice-warn chat-notice" role="status">{voiceNotice}</p>}

      <form className="chat-input" onSubmit={(e) => { e.preventDefault(); send(input); }}>
        <label htmlFor="chat-message" className="sr-only">Type your message</label>
        <input id="chat-message" ref={inputRef} value={input} maxLength={1000} autoComplete="off"
          placeholder={listening ? 'Listening…' : 'Type or tap the mic'} onChange={(e) => setInput(e.target.value)} />
        <button type="button" className={`icon-btn mic ${listening ? 'mic-on' : ''}`} onClick={toggleMic}
          aria-pressed={listening} aria-label={listening ? 'Stop voice input' : 'Speak your question'}
          title={support.recognition ? 'Voice input' : 'Voice input not supported in this browser'}>
          🎤
        </button>
        <button type="submit" className="btn btn-primary" disabled={busy || !input.trim()}>Send</button>
      </form>
      <div className="chat-footer">
        <label className="toggle">
          <input type="checkbox" checked={speakReplies} disabled={!support.synthesis}
            onChange={(e) => setSpeakReplies(e.target.checked)} />
          Read replies aloud
        </label>
        {support.recognition && <span className="privacy-note">Voice uses your browser’s speech service.</span>}
      </div>
    </section>
  );
}
