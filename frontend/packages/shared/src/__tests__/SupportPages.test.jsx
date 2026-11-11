import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ContactPage, HelpPage, ReturnsPage, ShippingPage } from '../pages/SupportPages.jsx';
import { makeStore, renderAt } from './helpers.jsx';

const store = vi.hoisted(() => ({ value: null }));
vi.mock('../StoreApp.jsx', () => ({ useStore: () => store.value }));

const INFO = {
  name: 'Summit Trail Co.', support_email: 'help@summittrail.example.com', support_hours: 'Mon–Fri 8am–6pm MT', order_number_prefix: 'SA',
  policies: {
    shipping: { summary: 'Free standard shipping over $75.', details: 'Standard shipping is $6.95 under $75.' },
    returns: { summary: 'Unused gear can be returned within 60 days.', details: 'Return unused items within 60 days.' },
    warranty: { summary: '2-year defect warranty.', details: 'Covered for 2 years.' },
  },
};

function setup(element, { info = INFO, infoError = null, storeId = 'store-a' } = {}) {
  store.value = { ...makeStore({ storeId }), info, infoError };
  renderAt(element);
  return store.value;
}

describe.each([['store-a', 'Scout'], ['store-b', 'Maple']])('support pages (%s)', (storeId, assistant) => {
  it('help page links every topic and opens the assistant', async () => {
    const s = setup(<HelpPage />, { storeId });
    expect(screen.getByRole('heading', { level: 1, name: 'Help' })).toBeInTheDocument();
    for (const [name, href] of [['Track your orders', '/account'], ['Shipping', '/shipping'], ['Returns and warranty', '/returns'], ['Contact us', '/contact']]) {
      expect(screen.getByRole('link', { name })).toHaveAttribute('href', href);
    }
    await userEvent.setup().click(screen.getByRole('button', { name: `Ask ${assistant}` }));
    expect(s.openChat).toHaveBeenCalled();
  });
});

describe('support pages', () => {
  it('shipping shows the store policy text', () => {
    setup(<ShippingPage />);
    expect(screen.getByRole('heading', { level: 1, name: 'Shipping' })).toBeInTheDocument();
    expect(screen.getByText('Free standard shipping over $75.')).toBeInTheDocument();
    expect(screen.getByText('Standard shipping is $6.95 under $75.')).toBeInTheDocument();
  });

  it('returns includes the warranty', () => {
    setup(<ReturnsPage />);
    expect(screen.getByText('Unused gear can be returned within 60 days.')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Warranty' })).toBeInTheDocument();
    expect(screen.getByText('Covered for 2 years.')).toBeInTheDocument();
  });

  it('a missing policy is stated, not invented', () => {
    setup(<ShippingPage />, { info: { ...INFO, policies: {} } });
    expect(screen.getByText('Summit Trail Co. hasn’t published a shipping policy yet.')).toBeInTheDocument();
  });

  it('contact shows only published details and says what is not published', () => {
    setup(<ContactPage />);
    expect(screen.getByRole('link', { name: 'help@summittrail.example.com' })).toHaveAttribute('href', 'mailto:help@summittrail.example.com');
    expect(screen.getByText('Mon–Fri 8am–6pm MT')).toBeInTheDocument();
    expect(screen.getByText(/hasn’t published a postal address, phone number or tax registration/)).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/\+?\d[\d\s-]{8,}/);   // no phone-like number appears
  });

  it('shows loading and error states', () => {
    setup(<ContactPage />, { info: null });
    expect(screen.getByText('Loading store information…')).toBeInTheDocument();
  });

  it('shows an error when store information fails', () => {
    setup(<ReturnsPage />, { info: null, infoError: 'down' });
    expect(screen.getByRole('alert')).toHaveTextContent('couldn’t be loaded');
  });
});
