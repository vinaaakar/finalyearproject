// Customer support pages. Everything shown comes from the store's own data (GET /api/stores/{id}), whose policies are
// already filtered to what this system can honour. Nothing here is invented: details the store hasn't published
// (address, phone, tax registration) are stated as not published (docs/business-information.md).
import React from 'react';
import { Link } from 'react-router-dom';
import { useStore } from '../StoreApp.jsx';
import { ui } from '../uiText.js';

// Interface text in the shopper's language (StoreApp provides `t`; English when rendered without it).
const useT = () => useStore().t || ((key, vars) => ui('en', key, vars));

function Loading() {
  return <p className="muted" aria-live="polite">{useT()('loadingInfo')}</p>;
}

function Unavailable() {
  return <p className="notice notice-error" role="alert">{useT()('infoFailed')}</p>;
}

function PolicyPage({ topic, title, related }) {
  const { info, infoError } = useStore();
  const t = useT();
  if (infoError) return <section className="support-page"><h1>{title}</h1><Unavailable /></section>;
  if (!info) return <Loading />;
  const policy = info.policies?.[topic];
  return (
    <section className="support-page" aria-labelledby={`${topic}-title`}>
      <h1 id={`${topic}-title`}>{title}</h1>
      {policy ? (
        <>
          <p className="support-lead">{policy.summary}</p>
          {policy.details && policy.details !== policy.summary && <p>{policy.details}</p>}
        </>
      ) : <p className="muted">{t('noPolicy', { store: info.name, topic: title.toLowerCase() })}</p>}
      {related}
      <SupportFooter />
    </section>
  );
}

function SupportFooter() {
  const { config, openChat } = useStore();
  const t = useT();
  return (
    <aside className="support-more" aria-label={t('moreHelp')}>
      <p>
        {t('stillQuestion')} <button type="button" className="link-btn" onClick={() => openChat()}>{t('ask', { assistant: config.assistantName })}</button>{' '}
        {t('or')} <Link to="/contact">{t('contactLower')}</Link>.
      </p>
    </aside>
  );
}

export function ShippingPage() {
  return <PolicyPage topic="shipping" title={useT()('shipping')} />;
}

export function ReturnsPage() {
  const { info } = useStore();
  const t = useT();
  return (
    <PolicyPage topic="returns" title={t('returns')} related={info?.policies?.warranty && (
      <>
        <h2>{t('warranty')}</h2>
        <p>{info.policies.warranty.details || info.policies.warranty.summary}</p>
      </>
    )} />
  );
}

export function ContactPage() {
  const { info, infoError, config, openChat } = useStore();
  const t = useT();
  if (infoError) return <section className="support-page"><h1>{t('contact')}</h1><Unavailable /></section>;
  if (!info) return <Loading />;
  return (
    <section className="support-page" aria-labelledby="contact-title">
      <h1 id="contact-title">{t('contact')}</h1>
      <dl className="contact-list">
        <div><dt>{t('email')}</dt><dd><a href={`mailto:${info.support_email}`}>{info.support_email}</a></dd></div>
        <div><dt>{t('hours')}</dt><dd>{info.support_hours}</dd></div>
        <div><dt>{t('chat')}</dt><dd><button type="button" className="link-btn" onClick={() => openChat()}>{t('ask', { assistant: config.assistantName })}</button>, {t('anyTime')}</dd></div>
        <div><dt>{t('phone')}</dt><dd><Link to="/support/call">{t('callTry')}</Link></dd></div>
      </dl>
      <p className="muted">{t('notPublished', { store: info.name })}</p>
      <p>{t('orderHint', { example: `${info.order_number_prefix}-50001` })} <Link to="/account">{t('yourAccount')}</Link>.</p>
    </section>
  );
}

export function HelpPage() {
  const { info, config, openChat, session } = useStore();
  const t = useT();
  const topics = [
    ['/account', session ? t('trackOrders') : t('signInTrack'), t('trackText')],
    ['/shipping', t('shipping'), info?.policies?.shipping?.summary],
    ['/returns', t('returnsWarranty'), info?.policies?.returns?.summary],
    ['/contact', t('contact'), info ? `${info.support_email} · ${info.support_hours}` : null],
    ['/support/call', t('callTry'), t('callTryText')],
  ];
  return (
    <section className="support-page" aria-labelledby="help-title">
      <h1 id="help-title">{t('help')}</h1>
      <p className="support-lead">
        {t('helpLead', { assistant: config.assistantName })}{' '}
        <button type="button" className="btn btn-primary btn-small" onClick={() => openChat()}>{t('ask', { assistant: config.assistantName })}</button>
      </p>
      <ul className="help-topics">
        {topics.map(([to, title, text]) => (
          <li key={to} className="card">
            <h2><Link to={to}>{title}</Link></h2>
            {text && <p className="muted">{text}</p>}
          </li>
        ))}
      </ul>
    </section>
  );
}
