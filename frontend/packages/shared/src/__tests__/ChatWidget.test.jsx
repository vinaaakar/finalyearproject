import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ChatWidget from '../ChatWidget.jsx';
import { apiError, deferred, makeApi, makeStore, renderAt } from './helpers.jsx';

const store = vi.hoisted(() => ({ value: null }));
vi.mock('../StoreApp.jsx', () => ({ useStore: () => store.value }));

const reply = (extra = {}) => ({
  reply: 'From our trail gear, these match: Ridgeline 2-Person Tent — $329.00, in stock.', products: [], orders: [],
  requires_login: false, source: 'rules', actions: [], cart: null, language: 'en', language_status: 'detected', clarification: false, ...extra,
});

function setup({ storeId = 'store-a', open = true, prefill = '', api = {}, session = null } = {}) {
  const a = makeApi(api);
  store.value = makeStore({ storeId, api: a, session });
  const onOpen = vi.fn();
  const onClose = vi.fn();
  renderAt(<ChatWidget open={open} prefill={prefill} onOpen={onOpen} onClose={onClose} />);
  return { api: a, onOpen, onClose };
}

const input = () => screen.getByRole('textbox');

describe.each([['store-a', 'Scout', 'Summit Trail Co.'], ['store-b', 'Maple', 'Bloom & Brew']])('ChatWidget (%s)', (storeId, assistant, storeName) => {
  it('shows a launcher while closed and opens on click', async () => {
    const user = userEvent.setup();
    const { onOpen } = setup({ storeId, open: false });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: `Open chat with ${assistant}` }));
    expect(onOpen).toHaveBeenCalledTimes(1);
  });

  it('opens in Tamil by default, with the store assistant and its own suggestions', async () => {
    const { api } = setup({ storeId });
    const dialog = screen.getByRole('dialog', { name: assistant });
    expect(dialog).toHaveAttribute('lang', 'ta-IN');
    expect(within(dialog).getByText(new RegExp(`வணக்கம்! நான் ${assistant}`))).toBeInTheDocument();
    expect(within(dialog).getByText(`${storeName} வாடிக்கையாளர் சேவை`)).toBeInTheDocument();
    expect(screen.getByTestId('conversation-language')).toHaveValue('ta');
    expect(screen.getByRole('button', { name: 'அனுப்பு' })).toBeDisabled();       // nothing typed yet
    expect(screen.getAllByRole('button', { name: /உங்களிடம்/ }).length).toBe(1);   // one Tamil suggestion chip per store config
    await waitFor(() => expect(api.speechCapabilities).toHaveBeenCalledTimes(1));
  });

  it('closes with the close button', async () => {
    const user = userEvent.setup();
    const { onClose } = setup({ storeId });
    await user.click(screen.getByRole('button', { name: 'அரட்டையை மூடு' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('remembers the conversation language per store only', async () => {
    const user = userEvent.setup();
    setup({ storeId });
    await user.selectOptions(screen.getByTestId('conversation-language'), 'hi');
    expect(screen.getByRole('button', { name: 'भेजें' })).toBeInTheDocument();
    expect(sessionStorage.getItem(`avc:${storeId}:conversation-language`)).toBe('hi');
    const other = storeId === 'store-a' ? 'store-b' : 'store-a';
    expect(sessionStorage.getItem(`avc:${other}:conversation-language`)).toBeNull();
  });
});

describe('ChatWidget conversation', () => {
  it('restores a saved language for the same store', () => {
    sessionStorage.setItem('avc:store-b:conversation-language', 'en');
    setup({ storeId: 'store-b' });
    expect(screen.getByTestId('conversation-language')).toHaveValue('en');
    expect(screen.getByRole('button', { name: 'Send' })).toBeInTheDocument();
  });

  it('prefills the input when opened from a product page', () => {
    setup({ prefill: 'Tell me about the Lumen 300 Headlamp' });
    expect(input()).toHaveValue('Tell me about the Lumen 300 Headlamp');
  });

  it('sends a typed message with the conversation language and shows the reply in its detected language', async () => {
    const user = userEvent.setup();
    const { api } = setup({ api: { chat: vi.fn().mockResolvedValue(reply()) } });
    await user.type(input(), 'Do you have a 2-person tent?');
    await user.click(screen.getByRole('button', { name: 'அனுப்பு' }));
    expect(await screen.findByText(/Ridgeline 2-Person Tent — \$329\.00/)).toBeInTheDocument();
    expect(screen.getByText('Do you have a 2-person tent?')).toBeInTheDocument();
    expect(api.chat).toHaveBeenCalledWith('Do you have a 2-person tent?', [], 'web_chat',
      { conversationLanguage: 'ta', speechReceipt: undefined, languageOverride: null });
    // The conversation follows the reply language (English was detected).
    expect(screen.getByTestId('conversation-language')).toHaveValue('en');
    expect(screen.getByRole('button', { name: 'Send' })).toBeInTheDocument();
    expect(input()).toHaveValue('');
  });

  it('sends a suggestion chip', async () => {
    const user = userEvent.setup();
    const { api } = setup({ storeId: 'store-b', api: { chat: vi.fn().mockResolvedValue(reply({ reply: 'From our coffee and tea shelf…' })) } });
    await user.click(screen.getByRole('button', { name: 'உங்களிடம் என்ன காபி பீன்ஸ் உள்ளன?' }));
    expect(api.chat.mock.calls[0][0]).toBe('உங்களிடம் என்ன காபி பீன்ஸ் உள்ளன?');
    expect(await screen.findByText('From our coffee and tea shelf…')).toBeInTheDocument();
  });

  it('sends only one request while a reply is pending', async () => {
    const user = userEvent.setup();
    const pending = deferred();
    const { api } = setup({ api: { chat: vi.fn(() => pending.promise) } });
    await user.type(input(), 'first{Enter}');
    await user.type(input(), 'second{Enter}');
    expect(screen.getByRole('button', { name: 'அனுப்பு' })).toBeDisabled();
    // A submission that bypasses the disabled button (as a voice transcript arriving mid-reply does) must also be ignored.
    fireEvent.submit(input().closest('form'));
    expect(api.chat).toHaveBeenCalledTimes(1);
    expect(screen.getByLabelText('உதவியாளர் தட்டச்சு செய்கிறார்')).toBeInTheDocument();   // typing indicator
    pending.resolve(reply());
    expect(await screen.findByText(/Ridgeline/)).toBeInTheDocument();
  });

  it('shows the server error message as an error bubble', async () => {
    const user = userEvent.setup();
    setup({ api: { chat: vi.fn().mockRejectedValue(apiError('Something went wrong on our side. Please try again.', 500, 'internal_error')) } });
    await user.type(input(), 'hello{Enter}');
    const msg = await screen.findByText('Something went wrong on our side. Please try again.');
    expect(msg.closest('.bubble')).toHaveClass('bubble-error');
    expect(input()).toBeEnabled();
  });

  it('shows a localised message when rate-limited', async () => {
    const user = userEvent.setup();
    setup({ api: { chat: vi.fn().mockRejectedValue(apiError('Too many requests. Please slow down.', 429, 'rate_limited')) } });
    await user.type(input(), 'hello{Enter}');
    expect(await screen.findByText(/நீங்கள் வேகமாகச் செய்திகளை அனுப்புகிறீர்கள்/)).toBeInTheDocument();
  });

  it('offers a language choice on clarification and resends with the explicit choice', async () => {
    const user = userEvent.setup();
    const chat = vi.fn()
      .mockResolvedValueOnce(reply({ reply: 'மன்னிக்கவும், எந்த மொழி?', language: 'ta', language_status: 'uncertain', clarification: true, intents: ['clarify'] }))
      .mockResolvedValueOnce(reply());
    setup({ api: { chat } });
    await user.type(input(), 'ok{Enter}');
    const choice = await screen.findByRole('group', { name: 'மொழியைத் தேர்ந்தெடுங்கள்:' });
    expect(screen.getByTestId('conversation-language')).toHaveValue('ta');   // a clarification does not switch language
    await user.click(within(choice).getByRole('button', { name: 'English' }));
    await waitFor(() => expect(chat).toHaveBeenCalledTimes(2));
    expect(chat.mock.calls[1][0]).toBe('ok');
    expect(chat.mock.calls[1][3]).toMatchObject({ languageOverride: 'en' });
  });

  it('asks for confirmation before cancelling an order and reports success only after the API confirms', async () => {
    const user = userEvent.setup();
    const action = { type: 'cancel_order', order_number: 'SA-50001', label: 'Cancel order SA-50001' };
    const { api } = setup({
      session: { customer: { name: 'Test Shopper', role: 'customer' } },
      api: { chat: vi.fn().mockResolvedValue(reply({ reply: 'Order SA-50001 can be cancelled.', actions: [action] })),
             cancelOrder: vi.fn().mockResolvedValue({ order: { order_number: 'SA-50001', status: 'cancelled' } }) },
    });
    await user.type(input(), 'cancel my order SA-50001{Enter}');
    await user.click(await screen.findByRole('button', { name: 'Cancel order SA-50001' }));
    const confirm = screen.getByRole('group', { name: 'Cancel this order? This can’t be undone.' });
    expect(api.cancelOrder).not.toHaveBeenCalled();
    await user.click(within(confirm).getByRole('button', { name: 'Yes, cancel order SA-50001' }));
    expect(await screen.findByText('Order SA-50001 has been cancelled.')).toBeInTheDocument();
    expect(api.cancelOrder).toHaveBeenCalledTimes(1);
  });

  it('"No, keep the order" dismisses the confirmation without cancelling', async () => {
    const user = userEvent.setup();
    const action = { type: 'cancel_order', order_number: 'SA-50001', label: 'Cancel order SA-50001' };
    const { api } = setup({ api: { chat: vi.fn().mockResolvedValue(reply({ actions: [action] })) } });
    await user.type(input(), 'cancel{Enter}');
    await user.click(await screen.findByRole('button', { name: 'Cancel order SA-50001' }));
    await user.click(screen.getByRole('button', { name: 'No, keep the order' }));
    expect(screen.queryByRole('group', { name: /Cancel this order\?/ })).not.toBeInTheDocument();
    expect(api.cancelOrder).not.toHaveBeenCalled();
  });

  it('does not claim a cancellation the server did not confirm', async () => {
    const user = userEvent.setup();
    const action = { type: 'cancel_order', order_number: 'SA-50001', label: 'Cancel order SA-50001' };
    setup({ api: { chat: vi.fn().mockResolvedValue(reply({ actions: [action] })),
                   cancelOrder: vi.fn().mockResolvedValue({ order: { order_number: 'SA-50001', status: 'pending_payment' } }) } });
    await user.type(input(), 'cancel{Enter}');
    await user.click(await screen.findByRole('button', { name: 'Cancel order SA-50001' }));
    await user.click(screen.getByRole('button', { name: 'Yes, cancel order SA-50001' }));
    expect(await screen.findByText('That didn’t work:')).toBeInTheDocument();
    expect(screen.queryByText('Order SA-50001 has been cancelled.')).not.toBeInTheDocument();
  });

  it('reports an add-to-cart failure with the server message', async () => {
    const user = userEvent.setup();
    const action = { type: 'add_to_cart', slug: 'lumen-300-headlamp', name: 'Lumen 300 Headlamp', quantity: 2, label: 'Add 2 × Lumen 300 Headlamp to cart' };
    setup({ api: { chat: vi.fn().mockResolvedValue(reply({ actions: [action] })),
                   addToCart: vi.fn().mockRejectedValue(apiError('Only 1 of Lumen 300 Headlamp left.', 409, 'insufficient_stock')) } });
    await user.type(input(), 'add two headlamps to my cart{Enter}');
    await user.click(await screen.findByRole('button', { name: 'Add 2 × Lumen 300 Headlamp to cart' }));
    expect(await screen.findByText('That didn’t work: Only 1 of Lumen 300 Headlamp left.')).toBeInTheDocument();
  });

  it('keeps working when the speech service is unavailable', async () => {
    const user = userEvent.setup();
    setup({ api: { speechCapabilities: vi.fn().mockRejectedValue(new Error('offline')), chat: vi.fn().mockResolvedValue(reply()) } });
    expect(await screen.findByText(/தானியங்கி மொழி கண்டறிதலுக்கு/)).toBeInTheDocument();   // explains auto-detect is off
    await user.type(input(), 'tent{Enter}');
    expect(await screen.findByText(/Ridgeline/)).toBeInTheDocument();
  });
});

// Escape, focus restoration and the full-screen modal behaviour (Phase D: K-2, K-3, K-4)
describe('ChatWidget dialog behaviour', () => {
  function Harness() {
    const [open, setOpen] = React.useState(false);
    return (
      <>
        <button type="button" onClick={() => setOpen(true)}>Help</button>
        <ChatWidget open={open} prefill="" onOpen={() => setOpen(true)} onClose={() => setOpen(false)} />
      </>
    );
  }
  const mount = () => {
    store.value = makeStore({ storeId: 'store-a', api: makeApi() });
    renderAt(<Harness />);
  };
  const launcher = () => screen.getByRole('button', { name: 'Open chat with Scout' });

  it('Escape closes the chat and returns focus to the launcher', async () => {
    const user = userEvent.setup();
    mount();
    await user.click(launcher());
    await waitFor(() => expect(input()).toHaveFocus());
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(launcher()).toHaveFocus();
  });

  it('the close button returns focus to the control that opened the chat', async () => {
    const user = userEvent.setup();
    mount();
    const help = screen.getByRole('button', { name: 'Help' });
    help.focus();
    await user.keyboard('{Enter}');
    await waitFor(() => expect(input()).toHaveFocus());
    await user.click(screen.getByRole('button', { name: 'அரட்டையை மூடு' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(help).toHaveFocus();
  });

  it('Escape during input-method composition (Tamil/Hindi keyboards) does not close the chat', async () => {
    const user = userEvent.setup();
    mount();
    await user.click(launcher());
    fireEvent.keyDown(input(), { key: 'Escape', isComposing: true });
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('is non-modal by default and modal (background inert) when full-screen, restoring the page on close', async () => {
    const user = userEvent.setup();
    mount();
    await user.click(launcher());
    expect(screen.getByRole('dialog')).toHaveAttribute('aria-modal', 'false');   // jsdom: no matchMedia → floating
    await user.keyboard('{Escape}');

    const listeners = new Set();
    window.matchMedia = vi.fn(() => ({ matches: true, addEventListener: (_, f) => listeners.add(f), removeEventListener: (_, f) => listeners.delete(f) }));
    try {
      cleanupAndMount();
      await user.click(launcher());
      const dialog = screen.getByRole('dialog');
      expect(dialog).toHaveAttribute('aria-modal', 'true');
      const help = screen.getByRole('button', { name: 'Help' });
      expect(help.inert).toBe(true);
      await user.keyboard('{Escape}');
      expect(help.inert).toBe(false);
    } finally {
      delete window.matchMedia;
    }
  });

  function cleanupAndMount() {
    cleanup();
    mount();
  }
});

// Conversational cart removal: the assistant offers a confirmation button; the cart changes only when it is tapped.
describe('ChatWidget remove-from-cart action', () => {
  it.each([['en', 'Removed Daytrip 22L Daypack from your cart.'], ['ta', 'Daytrip 22L Daypack உங்கள் கார்ட்டிலிருந்து நீக்கப்பட்டது.'],
    ['hi', 'Daytrip 22L Daypack आपके कार्ट से हटा दिया गया।']])('removes only after the button is tapped (%s)', async (language, done) => {
    const user = userEvent.setup();
    const removeCartItem = vi.fn().mockResolvedValue({ items: [] });
    const { api } = setup({ api: { removeCartItem, chat: vi.fn().mockResolvedValue(reply({ reply: 'Tap to remove.', language,
      actions: [{ type: 'remove_from_cart', slug: 'daytrip-22l-daypack', name: 'Daytrip 22L Daypack', label: 'Remove Daytrip 22L Daypack' }] })) } });
    await user.type(input(), 'remove it from my cart{Enter}');
    const btn = await screen.findByRole('button', { name: 'Remove Daytrip 22L Daypack' });
    expect(removeCartItem).not.toHaveBeenCalled();
    await user.click(btn);
    expect(removeCartItem).toHaveBeenCalledWith('daytrip-22l-daypack');
    expect(await screen.findByText(done)).toBeInTheDocument();
    expect(api.chat).toHaveBeenCalledTimes(1);
  });

  it('reports a failed removal instead of claiming success', async () => {
    const user = userEvent.setup();
    setup({ api: { removeCartItem: vi.fn().mockResolvedValue({ items: [{ slug: 'daytrip-22l-daypack' }] }),
      chat: vi.fn().mockResolvedValue(reply({ reply: 'Tap to remove.', actions: [{ type: 'remove_from_cart', slug: 'daytrip-22l-daypack', name: 'Daytrip 22L Daypack', label: 'Remove it' }] })) } });
    await user.type(input(), 'remove it from my cart{Enter}');
    await user.click(await screen.findByRole('button', { name: 'Remove it' }));
    expect(await screen.findByText(/That didn’t work/)).toBeInTheDocument();
  });
});

describe('ChatWidget speaking indicator', () => {
  it('shows who is speaking with a Stop button that stops the speech', async () => {
    const { speaker } = await import('../voice.js');
    const cancel = vi.spyOn(speaker, 'cancel');
    setup({ storeId: 'store-b' });
    const { act } = await import('@testing-library/react');
    act(() => speaker.setSpeaking(true));
    const status = await screen.findByText(/Maple பேசுகிறார்/);
    expect(status.closest('[role="status"]')).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole('button', { name: 'நிறுத்து' }));
    expect(cancel).toHaveBeenCalled();
    expect(screen.queryByText(/Maple பேசுகிறார்/)).not.toBeInTheDocument();
  });
});
