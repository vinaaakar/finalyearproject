import React, { useEffect, useState } from 'react';
import { useStore } from '../StoreApp.jsx';
import { ErrorNotice } from '../pages/AuthPages.jsx';

const EMPTY = {
  label: 'Home',
  full_name: '',
  line1: '',
  line2: '',
  city: '',
  region: '',
  postal_code: '',
  phone: '',
  country: 'IN',
  is_default: false,
};

const htmlPattern = (p) => (p ? p.replace(/^\^/, '').replace(/\$$/, '') : '');

export default function AddressForm({
  initial = null,
  countries: externalCountries = null,
  onSave,
  onCancel,
  submitLabel = 'Save address',
  busy = false,
}) {
  const { api, session } = useStore();
  const [address, setAddress] = useState(() => ({
    ...EMPTY,
    full_name: session?.customer?.name || '',
    ...(initial || {}),
  }));
  const [countries, setCountries] = useState(externalCountries);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (externalCountries?.length) {
      setCountries(externalCountries);
      return;
    }
    let live = true;
    api.addressOptions().then(
      (d) => {
        if (live && d?.countries?.length) {
          setCountries(d.countries);
          if (!initial?.country) {
            setAddress((a) => ({ ...a, country: d.default_country || d.countries[0].code }));
          }
        }
      },
      (e) => live && setError(e)
    );
    return () => {
      live = false;
    };
  }, [api, externalCountries, initial]);

  const set = (k) => (e) => setAddress((a) => ({ ...a, [k]: e.target.value }));
  const country = countries?.find((c) => c.code === address.country) || null;

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    try {
      const payload = {
        label: address.label.trim() || 'Home',
        full_name: address.full_name.trim(),
        line1: address.line1.trim(),
        line2: address.line2?.trim() || null,
        city: address.city.trim(),
        region: address.region,
        postal_code: address.postal_code.trim(),
        country: address.country,
        phone: address.phone?.trim() || null,
        is_default: Boolean(address.is_default),
      };
      await onSave(payload);
    } catch (err) {
      setError(err);
    }
  }

  if (!country) {
    return error ? <ErrorNotice error={error} /> : <p className="muted">Loading address options…</p>;
  }

  return (
    <form className="card address-form" onSubmit={handleSubmit} data-testid="address-form">
      <h3>{initial?.id ? 'Edit address' : 'Add a new address'}</h3>

      <div className="form-row-2">
        <div>
          <label htmlFor="addr-label">Address type / nickname</label>
          <select id="addr-label" value={address.label} onChange={set('label')}>
            <option value="Home">Home</option>
            <option value="Work">Work</option>
            <option value="Other">Other</option>
          </select>
        </div>
        {countries.length > 1 && (
          <div>
            <label htmlFor="addr-country">Country / Region</label>
            <select
              id="addr-country"
              value={address.country}
              onChange={(e) => setAddress((a) => ({ ...a, country: e.target.value, region: '', postal_code: '' }))}
            >
              {countries.map((c) => (
                <option key={c.code} value={c.code}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      <label htmlFor="addr-name">Full name</label>
      <input
        id="addr-name"
        autoComplete="shipping name"
        required
        maxLength={100}
        value={address.full_name}
        onChange={set('full_name')}
      />

      <label htmlFor="addr-line1">{country.line1_label || 'Address line 1'}</label>
      <input
        id="addr-line1"
        autoComplete="shipping address-line1"
        required
        maxLength={120}
        value={address.line1}
        onChange={set('line1')}
      />

      <label htmlFor="addr-line2">{country.line2_label || 'Address line 2 / Landmark (optional)'}</label>
      <input
        id="addr-line2"
        autoComplete="shipping address-line2"
        maxLength={120}
        value={address.line2 || ''}
        onChange={set('line2')}
      />

      <div className="form-row">
        <div>
          <label htmlFor="addr-city">{country.city_label || 'City / Town'}</label>
          <input
            id="addr-city"
            autoComplete="shipping address-level2"
            required
            maxLength={80}
            value={address.city}
            onChange={set('city')}
          />
        </div>
        <div>
          <label htmlFor="addr-region">{country.region_label || 'State / Union territory'}</label>
          <select
            id="addr-region"
            autoComplete="shipping address-level1"
            required
            value={address.region}
            onChange={set('region')}
          >
            <option value="">Select…</option>
            {country.regions.map((r) => (
              <option key={r.code} value={r.code}>
                {r.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="addr-postal">{country.postal_label || 'PIN code'}</label>
          <input
            id="addr-postal"
            autoComplete="shipping postal-code"
            inputMode="numeric"
            required
            pattern={htmlPattern(country.postal_pattern)}
            maxLength={country.code === 'IN' ? 6 : 10}
            value={address.postal_code}
            onChange={set('postal_code')}
          />
        </div>
      </div>

      {country.phone && (
        <>
          <label htmlFor="addr-phone">
            {country.phone.required ? 'Mobile number' : 'Phone number (optional)'}
          </label>
          <div className="phone-field">
            <span className="phone-prefix" aria-hidden="true">
              {country.phone.dial_code}
            </span>
            <input
              id="addr-phone"
              type="tel"
              autoComplete="shipping tel-national"
              inputMode="tel"
              required={country.phone.required}
              maxLength={20}
              pattern="[+0-9 ().\-]{10,20}"
              title={`10-digit number, for example ${country.phone.example}`}
              value={address.phone || ''}
              onChange={set('phone')}
            />
          </div>
        </>
      )}

      <label className="checkbox-label">
        <input
          type="checkbox"
          checked={Boolean(address.is_default)}
          onChange={(e) => setAddress((a) => ({ ...a, is_default: e.target.checked }))}
        />
        <span>Make this my default address</span>
      </label>

      <ErrorNotice error={error} />

      <div className="detail-actions">
        {onCancel && (
          <button type="button" className="btn" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
        )}
        <button type="submit" className="btn btn-primary" disabled={busy}>
          {busy ? 'Saving…' : submitLabel}
        </button>
      </div>
    </form>
  );
}
