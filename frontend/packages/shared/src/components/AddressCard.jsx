import React from 'react';

export default function AddressCard({
  address,
  isSelected = false,
  onSelect,
  onEdit,
  onSetDefault,
  onDelete,
  mode = 'manage',
  busy = false,
}) {
  const isDefault = address.is_default;
  const label = address.label || 'Home';

  return (
    <div
      className={`address-card ${isSelected ? 'selected' : ''}`}
      data-testid={`address-card-${address.id}`}
    >
      <div className="address-card-header">
        <span className="address-label-badge">{label}</span>
        {isDefault && <span className="address-default-badge">Default</span>}
      </div>

      <div className="address-card-body">
        <strong className="address-name">{address.full_name}</strong>
        <p className="address-line">{address.line1}</p>
        {address.line2 && <p className="address-line">{address.line2}</p>}
        <p className="address-line">
          {address.city}, {address.region} {address.postal_code}
        </p>
        <p className="address-line">{address.country === 'IN' ? 'India' : address.country}</p>
        {address.phone && (
          <p className="address-phone">
            <span className="muted">Phone:</span> {address.phone}
          </p>
        )}
      </div>

      <div className="address-card-actions">
        {mode === 'checkout' && onSelect && (
          <button
            type="button"
            className={`btn btn-small ${isSelected ? 'btn-primary' : ''}`}
            onClick={() => onSelect(address)}
            disabled={busy}
            aria-pressed={isSelected}
          >
            {isSelected ? '✓ Deliver to this address' : 'Deliver to this address'}
          </button>
        )}

        <div className="address-action-links">
          {onEdit && (
            <button
              type="button"
              className="btn-link"
              onClick={() => onEdit(address)}
              disabled={busy}
              aria-label={`Edit address for ${address.full_name}`}
            >
              Edit
            </button>
          )}

          {!isDefault && onSetDefault && (
            <>
              <span className="action-sep" aria-hidden="true">|</span>
              <button
                type="button"
                className="btn-link"
                onClick={() => onSetDefault(address.id)}
                disabled={busy}
                aria-label={`Set as default address`}
              >
                Set as default
              </button>
            </>
          )}

          {onDelete && (
            <>
              <span className="action-sep" aria-hidden="true">|</span>
              <button
                type="button"
                className="btn-link btn-link-danger"
                onClick={() => onDelete(address.id)}
                disabled={busy}
                aria-label={`Delete address for ${address.full_name}`}
              >
                Delete
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
