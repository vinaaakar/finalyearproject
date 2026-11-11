import React, { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useStore } from './StoreApp.jsx';
import ProductCard from './components/ProductCard.jsx';
import OrderCard from './components/OrderCard.jsx';
import { selectRecognizer, speaker, voiceSupport } from './voice.js';
import { DEFAULT_LANGUAGE, LANGUAGES, SUPPORTED, suggestionsFor, tr } from './i18n.js';

// Read-aloud preference: 'on' (every reply), 'off' (never), or 'auto' (the default: replies to VOICE questions are spoken).
// Saved only when the customer changes it. (The previous key was written on every page load, so a stored "0" did not mean
// the customer turned it off; only its "1" is carried over.)
const READ_ALOUD_KEY = 'avc:read-aloud';
const LEGACY_SPEAK_PREF_KEY = 'avc:speak-replies';

function readPref() {
  try {
    const v = localStorage.getItem(READ_ALOUD_KEY);
    if (v === 'on' || v === 'off') return v;
    return localStorage.getItem(LEGACY_SPEAK_PREF_KEY) === '1' ? 'on' : 'auto';
  } catch {
    return 'auto';
  }
}

// "yes" / "ஆம்" / "हाँ" / "sari" typed or said right after the assistant proposed ONE cart change: the same as tapping it.
const AFFIRM_RE = /^\s*(yes|yeah|yep|yup|ok(ay)?|sure|confirm|go ahead|please do|do it|add it|yes please|ஆம்|ஆமா|ஆமாம்|சரி|ஓகே|சேர்|சேர்த்துவிடு|ஆட் பண்ணுங்க|हाँ|हां|जी हाँ|जी हां|ठीक है|जोड़ दो|haan|han|haa|ji haan|theek hai|aama|aamaa|aam|sari|seri|add pannunga|podunga)[\s.!।]*$/i;
const CONFIRMABLE = new Set(['add_to_cart', 'remove_from_cart', 'set_cart_quantity']);

// The conversation language lives in sessionStorage per store: a new tab (new guest conversation)
// starts in Tamil, and Store A and Store B never share it.
// Below this width the chat panel covers the whole screen (see styles.css), so it behaves as a modal dialog.
const FULL_SCREEN_QUERY = '(max-width: 720px)';

function useFullScreenChat() {
  const query = () => typeof window !== 'undefined' && typeof window.matchMedia === 'function' && window.matchMedia(FULL_SCREEN_QUERY);
  const [full, setFull] = useState(() => !!query()?.matches);
  useEffect(() => {
    const mq = query();
    if (!mq) return undefined;
    const update = () => setFull(mq.matches);
    update();
    mq.addEventListener?.('change', update);
    return () => mq.removeEventListener?.('change', update);
  }, []);
  return full;
}

// The conversation itself (last 30 messages + an unfinished customer-care draft) survives a page refresh in
// sessionStorage, per store AND per account: a guest's chat carries over when that guest signs in ("sign in first —
// I'll keep what you told me"), signing out clears the account's chat, and another account never sees it. Voice
// recordings, speech receipts and anything that looks like a card number or password are never stored.
const MAX_STORED_MESSAGES = 30;
const SECRET_RE = /(?<!\d)(?:\d[ -]?){13,19}(?!\d)|\b(?:password|passcode|passwd|cvv|cvc|otp|upi\s*pin)\b|கடவுச்சொல்|பாஸ்வேர்டு|पासवर्ड/i;

export function accountKey(session) {
  const email = session?.customer?.email;
  if (!email) return 'guest';
  let h = 0x811c9dc5;                               // FNV-1a: the e-mail address itself is not put in the key
  for (const ch of email.toLowerCase()) { h ^= ch.codePointAt(0); h = Math.imul(h, 0x01000193) >>> 0; }
  return `acct-${h.toString(16)}`;
}

export const chatStorageKey = (storeId, account) => `avc:${storeId}:chat:${account}`;

function loadConversation(key) {
  try {
    const v = JSON.parse(sessionStorage.getItem(key));
    return {
      messages: Array.isArray(v?.messages) ? v.messages : [],
      careDraft: v?.careDraft && typeof v.careDraft === 'object' ? v.careDraft : null,
    };
  } catch {
    return { messages: [], careDraft: null };
  }
}

function storable(m) {
  // Only what is needed to show the conversation again (no audio, speech receipts or retry data).
  const content = m.role === 'user' && SECRET_RE.test(m.content) ? '•••' : m.content;
  const kept = {
    id: m.id, role: m.role, content, viaVoice: !!m.viaVoice, error: !!m.error, language: m.language, languageStatus: m.languageStatus,
    products: m.products, orders: m.orders, actions: m.actions, requiresLogin: m.requiresLogin, source: m.source, cart: m.cart, done: m.done,
  };
  return Object.fromEntries(Object.entries(kept).filter(([, v]) => v !== undefined));
}

function saveConversation(key, messages, draft) {
  try {
    if (!messages.length && !draft) sessionStorage.removeItem(key);
    else sessionStorage.setItem(key, JSON.stringify({ messages: messages.slice(-MAX_STORED_MESSAGES).map(storable), careDraft: draft }));
  } catch {
    /* storage unavailable or full: the conversation just won't survive a reload */
  }
}

function forgetConversation(key) {
  try { sessionStorage.removeItem(key); } catch { /* nothing stored */ }
}

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
  const account = accountKey(session);
  const chatKey = chatStorageKey(config.storeId, account);
  const [restored] = useState(() => loadConversation(chatKey));
  const [messages, setMessages] = useState(restored.messages);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [interim, setInterim] = useState('');
  const [voiceNotice, setVoiceNotice] = useState(null);
  const [readAloud, setReadAloud] = useState(readPref);
  const speakReplies = readAloud === 'on';
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
  const panelRef = useRef(null);
  const launcherRef = useRef(null);
  // What had focus when the chat opened (the header's Help button, "Ask … about this"); null for the launcher,
  // which is replaced by the panel while the chat is open.
  const openerRef = useRef(null);
  const restoreFocus = useRef(false);
  const fullScreen = useFullScreenChat();
  const actionBusy = useRef(false);
  const careDraft = useRef(restored.careDraft);   // customer-care request in progress (see backend app/assistant/care_flow.py)
  const accountRef = useRef(account);
  const skipSave = useRef(false);
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

  // Signing in, signing out or switching accounts in this tab.
  useEffect(() => {
    const before = accountRef.current;
    if (before === account) return;
    accountRef.current = account;
    forgetConversation(chatStorageKey(config.storeId, before));
    // A guest who signs in is the same person: their conversation (and any care request they started) continues.
    if (before === 'guest') return;
    // Signed out, or another account: the previous account's conversation is removed and never shown again.
    speaker.cancel();
    skipSave.current = true;          // this render still holds the previous account's messages
    const next = account === 'guest' ? { messages: [], careDraft: null } : loadConversation(chatKey);
    careDraft.current = next.careDraft;
    setMessages(next.messages);
  }, [account, chatKey, config.storeId]);

  // Saved after every change (the care draft is updated together with the reply that carries it).
  useEffect(() => {
    if (skipSave.current) { skipSave.current = false; return; }
    if (accountRef.current === account) saveConversation(chatKey, messages, careDraft.current);
  }, [chatKey, account, messages]);

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

  useEffect(() => {
    if (open) {
      const active = document.activeElement;   // still the opener: the input is focused on the next tick
      openerRef.current = active && active !== document.body && !panelRef.current?.contains(active) ? active : null;
    } else if (restoreFocus.current) {
      // Closed by the user (close button or Escape): return focus to the opener if it is still on the page,
      // otherwise to the launcher (the launcher that was clicked has been re-created).
      restoreFocus.current = false;
      const opener = openerRef.current;
      const target = opener && opener.isConnected && opener !== document.body ? opener : launcherRef.current;
      target?.focus();
    }
  }, [open]);

  // Full-screen (phone) chat is modal: everything else on the page is made inert (no focus, no clicks, hidden from
  // assistive technology) while it is open, and restored when it closes or the screen gets wider.
  useEffect(() => {
    const panel = panelRef.current;
    if (!open || !fullScreen || !panel?.parentElement) return undefined;
    const others = [...panel.parentElement.children].filter((el) => el !== panel && !el.inert);
    others.forEach((el) => { el.inert = true; });
    return () => others.forEach((el) => { el.inert = false; });
  }, [open, fullScreen]);

  function closeByUser() {
    restoreFocus.current = true;
    onClose();
  }

  function onPanelKeyDown(e) {
    // Escape closes the chat, but not while an input method is composing (Tamil/Hindi keyboards use Escape there).
    if (e.key !== 'Escape' || e.defaultPrevented || e.nativeEvent?.isComposing) return;
    e.stopPropagation();
    closeByUser();
  }

  // Show when a reply is being spoken (and let the customer stop it).
  useEffect(() => {
    speaker.onChange = setSpeaking;
    return () => { if (speaker.onChange === setSpeaking) speaker.onChange = null; };
  }, []);

  // Ask once whether this store's server offers local speech recognition / synthesis.
  useEffect(() => {
    if (open && speechCaps === null) api.speechCapabilities().then(setSpeechCaps, () => setSpeechCaps({}));
  }, [open, speechCaps, api]);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
  }, [messages, interim, busy, confirming]);

  function changeReadAloud(on) {
    const v = on ? 'on' : 'off';
    setReadAloud(v);
    try {
      localStorage.setItem(READ_ALOUD_KEY, v);
    } catch {
      /* preference just won't persist */
    }
    if (on) speaker.prime();       // this tap unlocks audio for the replies that follow (Safari)
    else speaker.cancel();
  }
  const shouldSpeak = (viaVoice) => readAloud === 'on' || (readAloud === 'auto' && viaVoice);

  const serverStt = !!speechCaps?.server_stt?.available;
  const autoDetect = serverStt && !!speechCaps?.server_stt?.language_detection;
  const serverTtsVoices = speechCaps?.server_tts?.available ? speechCaps.server_tts.voices || {} : {};

  // Reads a reply aloud and reports what really happened: a reply shown as text is NOT a reply that was heard.
  async function say(text, replyLang, id = null) {
    const serverTts = serverTtsVoices[replyLang] ? (txt, l) => api.synthesize(txt, l) : null;
    const mark = (tts) => id && setMessages((m) => m.map((x) => (x.id === id ? { ...x, tts } : x)));
    const onError = (code) => {
      setVoiceNotice(tr(langRef.current, code === 'blocked' ? 'playBlocked' : 'playFailed'));
      mark({ mode: code === 'blocked' ? 'blocked' : 'error', voice: null });
    };
    const result = await speaker.speak(text, replyLang, { serverTts, onError });
    if (result.mode === 'none') setVoiceNotice(tr(langRef.current, 'noVoice', { lang: LANGUAGES[replyLang].native }));
    else if (result.mode === 'blocked') setVoiceNotice(tr(langRef.current, 'playBlocked'));
    else if (result.mode === 'error') setVoiceNotice(tr(langRef.current, 'playFailed'));
    mark(result);
    return result;
  }

  function replay(m) {
    speaker.prime();
    setVoiceNotice(null);
    say(m.content, m.language || langRef.current, m.id);
  }

  async function send(text, { viaVoice = false, voiceMeta = null, override = null } = {}) {
    const message = text.trim();
    if (!message || busyRef.current) return;
    speaker.prime();   // the send tap unlocks audio playback for the reply (Safari / autoplay policies)
    // "yes" right after ONE proposed cart change confirms it, exactly like tapping its button (never for a cancellation,
    // and never from an uncertain voice transcript).
    const last = [...messagesRef.current].reverse().find((x) => x.role === 'assistant' && !x.system);
    const pending = (last?.actions || []).map((a, i) => [a, `${last.id}:${i}`])
      .filter(([a, key]) => CONFIRMABLE.has(a.type) && !(last.done && key in last.done));
    if (pending.length === 1 && AFFIRM_RE.test(message) && !voiceMeta?.uncertain) {
      setMessages((m) => [...m, { role: 'user', content: message, viaVoice, voiceMeta }]);
      setInput('');
      await runAction(last, pending[0][0], pending[0][1], { viaVoice });
      return;
    }
    const history = messagesRef.current.filter((m) => !m.error).slice(-8).map((m) => ({ role: m.role, content: m.content.slice(0, 2000) }));
    speaker.cancel();   // a new question interrupts a reply that is still being read aloud
    setMessages((m) => [...m, { role: 'user', content: message, viaVoice, voiceMeta }]);
    setInput('');
    setVoiceNotice(null);
    busyRef.current = true;
    setBusy(true);
    try {
      const r = await api.chat(message, history, viaVoice ? 'web_voice' : 'web_chat', {
        conversationLanguage: langRef.current, speechReceipt: voiceMeta?.receipt, languageOverride: override,
        ...(careDraft.current ? { careDraft: careDraft.current } : {}),
      });
      // A customer-care request being put together (server-validated on every turn; submitted only after a "yes").
      careDraft.current = r.care_draft || null;
      const id = `${Date.now()}-${Math.random()}`;
      const reply = {
        id, role: 'assistant', content: r.reply, products: r.products, orders: r.orders, requiresLogin: r.requires_login, source: r.source,
        actions: r.actions || [], viaVoice,
        cart: r.cart, language: r.language, languageStatus: r.language_status, clarification: r.clarification, retry: { text: message, voiceMeta },
      };
      // The conversation follows the language of each new utterance (not on a clarification).
      if (!r.clarification) setLang(r.language);
      setMessages((m) => [...m, reply]);
      if (shouldSpeak(viaVoice)) say(r.reply, r.language, id);
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
  async function runAction(m, a, key, { viaVoice = false } = {}) {
    if (actionBusy.current) return;
    speaker.prime();
    if (a.type === 'link') {
      if (a.to.startsWith('mailto:')) { window.location.href = a.to; return; }
      onClose();
      navigate(a.to);
      return;
    }
    if (a.type === 'reply') {
      // Sends the button's words as the customer's next message (e.g. "yes" to confirm a reviewed request); the server
      // decides what happens. Only the newest message's choices are active.
      setMessages((ms) => ms.map((x) => (x.id === m.id ? { ...x, done: { ...(x.done || {}), [key]: true } } : x)));
      send(a.text, { viaVoice: !!m.viaVoice });
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
      } else if (a.type === 'set_cart_quantity') {
        const cart = await api.updateCartItem(a.slug, a.quantity);
        ok = cart.items.some((i) => i.slug === a.slug && i.quantity === a.quantity);
        text = ok ? tr(replyLang, 'actionQuantity', { qty: a.quantity, name: a.name }) : tr(replyLang, 'actionFailed');
      } else if (a.type === 'remove_from_cart') {
        const cart = await api.removeCartItem(a.slug);
        ok = !cart.items.some((i) => i.slug === a.slug);
        text = ok ? tr(replyLang, 'actionRemoved', { name: a.name }) : tr(replyLang, 'actionFailed');
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
    if (shouldSpeak(m.viaVoice || viaVoice)) say(text, replyLang);
  }

  const lastAssistantId = [...messages].reverse().find((x) => x.role === 'assistant' && !x.system)?.id;

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
          const stale = a.type === 'reply' && m.id !== lastAssistantId;
          return (
            <button key={key} type="button" className={`btn btn-small ${a.type === 'add_to_cart' || a.type === 'set_cart_quantity' || (a.type === 'reply' && i === 0 && m.actions.length === 2) ? 'btn-primary' : ''}`}
              disabled={busy || stale} onClick={() => runAction(m, a, key)}>{a.label}</button>
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
    speaker.prime();
    const rec = selectRecognizer(speechCaps, {
      // Server engine: identifies the language from the audio ('auto'). Browser engine: must listen in one locale.
      language: 'auto',
      hint: () => langRef.current,
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
      <button type="button" ref={launcherRef} className="chat-launcher" onClick={onOpen} aria-label={`Open chat with ${config.assistantName}`}>
        <span aria-hidden="true">💬</span> <span className="launcher-label">Ask {config.assistantName}</span>
      </button>
    );
  }

  return (
    <section ref={panelRef} className="chat-panel" role="dialog" aria-modal={fullScreen ? 'true' : 'false'} aria-labelledby="chat-title"
      lang={LANGUAGES[lang].bcp47} onKeyDown={onPanelKeyDown}>
      <header className="chat-header">
        <div>
          <h2 id="chat-title">{config.assistantName}</h2>
          <p>{t('subtitle', { store: config.name })}{session ? t('signedInAs', { name: session.customer.name.split(' ')[0] }) : ''}</p>
        </div>
        <button type="button" className="icon-btn" onClick={closeByUser} aria-label={t('close')}>✕</button>
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
            {m.role === 'assistant' && !m.error && (support.synthesis || Object.keys(serverTtsVoices).length > 0) && (
              <button type="button" className="icon-btn replay" onClick={() => replay(m)} aria-label={t('playReply')}
                title={t('playReply')} data-tts-mode={m.tts?.mode || ''}>🔊</button>
            )}
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

      {speaking && (
        <div className="chat-speaking" role="status">
          <span aria-hidden="true">🔊</span> {t('speaking', { assistant: config.assistantName })}
          <button type="button" className="btn btn-small" onClick={() => speaker.cancel()}>{t('stopSpeaking')}</button>
        </div>
      )}
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
            onChange={(e) => changeReadAloud(e.target.checked)} />
          {t('readAloud')}
        </label>
        {readAloud === 'auto' && <span className="lang-note">{t('readAloudAuto')}</span>}
        {serverStt ? (
          <span className="privacy-note">{t('privacyServer', { store: config.name })}</span>
        ) : support.recognition && <span className="privacy-note">{t('privacyBrowser')}</span>}
      </div>
    </section>
  );
}
