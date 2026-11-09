import React, { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useStore } from '../StoreApp.jsx';

// Validation details from the server name the failing field. Whole-request checks (e.g. password strength)
// arrive as field "body" with a message that starts with the field's name.
function detailField(d) {
  const f = d.field.split('.').pop();
  if (f !== 'body') return f;
  const m = /^(password|email|full name)\b/i.exec(d.issue);
  return m ? m[1].toLowerCase().replace(' ', '_') : 'body';
}

// Readable wording for the server's validation messages.
function friendly(d) {
  const f = detailField(d);
  if (/should match pattern/i.test(d.issue)) return f === 'email' ? 'Enter a valid email address, like name@example.com.' : 'Please check this value.';
  if (/at least 1 character/i.test(d.issue)) return 'This field is required.';
  const t = d.issue.charAt(0).toUpperCase() + d.issue.slice(1);
  return /[.!?]$/.test(t) ? t : `${t}.`;
}

function fieldErrors(err, shownInline = []) {
  return err?.details?.filter((d) => !shownInline.includes(detailField(d))).map((d) => {
    const f = detailField(d);
    return f === 'body' ? friendly(d) : `${f.replace('_', ' ')}: ${friendly(d)}`;
  }) || [];
}

// The server's message for one field, or null.
export function fieldError(err, name) {
  const d = err?.details?.find((x) => detailField(x) === name);
  return d ? friendly(d) : null;
}

// Only same-site paths are accepted as a post-sign-in destination.
export const safeNext = (v) => (v && /^\/(?!\/)[\w\-/]*$/.test(v) ? v : null);

// Error summary. Pass the field names shown next to their inputs so they aren't repeated here.
function ErrorNotice({ error, inline = [] }) {
  if (!error) return null;
  const details = fieldErrors(error, inline);
  return (
    <div className="notice notice-error" role="alert">
      {error.message}
      {details.length > 0 && <ul className="error-list">{details.map((d) => <li key={d}>{d}</li>)}</ul>}
    </div>
  );
}

export function RegisterPage() {
  const { api, config, session } = useStore();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const next = safeNext(params.get('next'));
  const [form, setForm] = useState({ name: '', email: '', password: '' });
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  // Set before the request: the session event fires inside api.register, and the redirect below must not
  // race the success message.
  const registering = useRef(false);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  // Already signed in (e.g. opened /register in a signed-in tab): nothing to do here.
  useEffect(() => {
    if (session && !registering.current) navigate(next || '/account', { replace: true });
  }, [session, next, navigate]);

  async function submit(e) {
    e.preventDefault();
    if (inFlight.current) return; // a ref, so a second click/Enter before re-render is ignored too
    inFlight.current = true;
    setBusy(true);
    setError(null);
    registering.current = true;
    try {
      const customer = await api.register(form.name.trim(), form.email.trim(), form.password);
      // Only reached when the server created the account and issued a session.
      navigate(next || '/account', { replace: true, state: { flash: `Account created. You’re signed in as ${customer.email}.` } });
    } catch (err) {
      registering.current = false;
      setError(err);
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }
  const pwShort = form.password.length > 0 && form.password.length < 10;

  return (
    <form className="card form" onSubmit={submit} noValidate={false}>
      <h1>Create your {config.name} account</h1>
      <p className="muted">This account works for {config.name} only.</p>
      {next === '/checkout' && <p className="notice notice-info">Create an account to continue to checkout. Your cart is kept.</p>}
      <Field id="reg-name" label="Full name" error={fieldError(error, 'full_name')}>
        <input id="reg-name" autoComplete="name" required maxLength={100} value={form.name} onChange={set('name')} />
      </Field>
      <Field id="reg-email" label="Email" error={fieldError(error, 'email')}>
        <input id="reg-email" type="email" autoComplete="email" required maxLength={254} value={form.email} onChange={set('email')} />
      </Field>
      <Field id="reg-password" label="Password" error={fieldError(error, 'password')}
        help={pwShort ? `${form.password.length}/10 characters — at least 10 needed.` : 'At least 10 characters. Avoid common passwords.'}>
        <input id="reg-password" type="password" autoComplete="new-password" required minLength={10} maxLength={200}
          value={form.password} onChange={set('password')} />
      </Field>
      <ErrorNotice error={error} inline={['full_name', 'email', 'password']} />
      <button className="btn btn-primary" type="submit" disabled={busy}>{busy ? 'Creating account…' : 'Create account'}</button>
      <p className="form-links">Already have an account? <Link to={next ? `/account?next=${encodeURIComponent(next)}` : '/account'}>Sign in</Link></p>
    </form>
  );
}

export function ForgotPasswordPage() {
  const { api, config } = useStore();
  const [email, setEmail] = useState('');
  const [done, setDone] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);

  async function submit(e) {
    e.preventDefault();
    if (inFlight.current) return; // a ref, so a second click/Enter before re-render is ignored too
    inFlight.current = true;
    setBusy(true);
    setError(null);
    try {
      setDone((await api.requestPasswordReset(email.trim())).message);
    } catch (err) {
      setError(err);
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  return (
    <form className="card form" onSubmit={submit}>
      <h1>Reset your password</h1>
      <p className="muted">Enter the email for your {config.name} account and we’ll send you a reset link.</p>
      {done ? (
        <>
          <p className="notice notice-ok" role="status">{done}</p>
          <p className="field-help">Demo: no real email is sent. In development the message is written to <code>.run/outbox/</code> on the server.</p>
        </>
      ) : (
        <>
          <label htmlFor="fp-email">Email</label>
          <input id="fp-email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          <ErrorNotice error={error} />
          <button className="btn btn-primary" type="submit" disabled={busy}>{busy ? 'Sending…' : 'Send reset link'}</button>
        </>
      )}
      <p className="form-links"><Link to="/account">Back to sign in</Link></p>
    </form>
  );
}

export function ResetPasswordPage() {
  const { api } = useStore();
  // The token arrives in the URL fragment (never sent to servers). Read it once, then remove it from the address bar.
  const [token] = useState(() => new URLSearchParams(window.location.hash.slice(1)).get('token') || '');
  const [password, setPassword] = useState('');
  const [done, setDone] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);

  useEffect(() => {
    if (window.location.hash) window.history.replaceState(null, '', window.location.pathname);
  }, []);

  async function submit(e) {
    e.preventDefault();
    if (inFlight.current) return; // a ref, so a second click/Enter before re-render is ignored too
    inFlight.current = true;
    setBusy(true);
    setError(null);
    try {
      setDone((await api.confirmPasswordReset(token, password)).message);
    } catch (err) {
      setError(err);
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  if (!token) {
    return (
      <div className="card form">
        <h1>Reset link missing</h1>
        <p>This page needs the link from your reset email. <Link to="/forgot-password">Request a new link</Link>.</p>
      </div>
    );
  }
  return (
    <form className="card form" onSubmit={submit}>
      <h1>Choose a new password</h1>
      {done ? (
        <>
          <p className="notice notice-ok" role="status">{done}</p>
          <Link className="btn btn-primary" to="/account">Sign in</Link>
        </>
      ) : (
        <>
          <label htmlFor="rp-password">New password</label>
          <input id="rp-password" type="password" autoComplete="new-password" required minLength={10} maxLength={200}
            aria-describedby="rp-help" value={password} onChange={(e) => setPassword(e.target.value)} />
          <p id="rp-help" className="field-help">At least 10 characters. You’ll be signed out everywhere after the change.</p>
          <ErrorNotice error={error} />
          <button className="btn btn-primary" type="submit" disabled={busy}>{busy ? 'Saving…' : 'Change password'}</button>
        </>
      )}
    </form>
  );
}

// A labelled input with help text and the server's error for that field, wired up for screen readers.
export function Field({ id, label, help, error, children }) {
  const describedBy = [help && `${id}-help`, error && `${id}-error`].filter(Boolean).join(' ') || undefined;
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      {React.cloneElement(children, { 'aria-describedby': describedBy, 'aria-invalid': error ? true : undefined })}
      {help && <p id={`${id}-help`} className="field-help">{help}</p>}
      {error && <p id={`${id}-error`} className="field-help field-error">{error}</p>}
    </div>
  );
}

export { ErrorNotice };
