// Chat widget: spoken/typed confirmation of a proposed cart change, read-aloud preference, playback failures surfaced
// (text on screen is not speech that was heard), replay, and the language label. No microphone or speaker is used.
import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ChatWidget from '../ChatWidget.jsx';
import { speaker } from '../voice.js';
import { makeApi, makeStore, renderAt } from './helpers.jsx';

const store = vi.hoisted(() => ({ value: null }));
vi.mock('../StoreApp.jsx', () => ({ useStore: () => store.value }));

const reply = (extra = {}) => ({
  reply: 'OK.', products: [], orders: [], requires_login: false, source: 'rules', actions: [], cart: null, language: 'en',
  language_status: 'detected', clarification: false, ...extra,
});
const ADD = { type: 'add_to_cart', slug: 'trailhead-55l-backpack', name: 'Trailhead 55L Backpack', quantity: 1, label: 'Add 1 × Trailhead 55L Backpack to cart' };
const QTY = { type: 'set_cart_quantity', slug: 'trailhead-55l-backpack', name: 'Trailhead 55L Backpack', quantity: 2, label: 'Change Trailhead 55L Backpack to 2' };

function setup(api = {}) {
  const a = makeApi({ speechCapabilities: vi.fn().mockResolvedValue({ server_tts: { available: true, voices: { en: 'Rishi', ta: 'Vani', hi: 'Lekha' } } }), ...api });
  store.value = makeStore({ api: a, session: null });
  renderAt(<ChatWidget open prefill="" onOpen={vi.fn()} onClose={vi.fn()} />);
  return a;
}
const input = () => screen.getByRole('textbox');

afterEach(() => vi.restoreAllMocks());

describe('confirming a proposed cart change by saying or typing "yes"', () => {
  it.each(['yes', 'ஆம்', 'हाँ', 'sari', 'ok'])('"%s" adds the proposed item through the cart API, without another chat turn', async (word) => {
    const user = userEvent.setup();
    const addToCart = vi.fn().mockResolvedValue({ items: [{ slug: ADD.slug, quantity: 1 }] });
    const api = setup({ addToCart, chat: vi.fn().mockResolvedValue(reply({ reply: 'Tap to add.', actions: [ADD] })) });
    await user.type(input(), 'add the trailhead backpack{Enter}');
    await screen.findByRole('button', { name: ADD.label });
    expect(addToCart).not.toHaveBeenCalled();                     // a proposal is not an addition
    await user.type(input(), `${word}{Enter}`);
    expect(addToCart).toHaveBeenCalledWith(ADD.slug, 1);
    expect(await screen.findByText('Added 1 × Trailhead 55L Backpack to your cart.')).toBeInTheDocument();
    expect(api.chat).toHaveBeenCalledTimes(1);
  });

  it('confirms a quantity change and reports it only when the cart shows the new quantity', async () => {
    const user = userEvent.setup();
    const updateCartItem = vi.fn().mockResolvedValue({ items: [{ slug: QTY.slug, quantity: 2 }] });
    setup({ updateCartItem, chat: vi.fn().mockResolvedValue(reply({ reply: 'Tap to change.', actions: [QTY] })) });
    await user.type(input(), 'make it 2{Enter}');
    await user.click(await screen.findByRole('button', { name: QTY.label }));
    expect(updateCartItem).toHaveBeenCalledWith(QTY.slug, 2);
    expect(await screen.findByText('Your cart now has 2 × Trailhead 55L Backpack.')).toBeInTheDocument();
  });

  it('a quantity change the cart did not apply is reported as a failure', async () => {
    const user = userEvent.setup();
    setup({ updateCartItem: vi.fn().mockResolvedValue({ items: [{ slug: QTY.slug, quantity: 1 }] }),
      chat: vi.fn().mockResolvedValue(reply({ reply: 'Tap to change.', actions: [QTY] })) });
    await user.type(input(), 'make it 2{Enter}');
    await user.click(await screen.findByRole('button', { name: QTY.label }));
    expect(await screen.findByText(/That didn’t work/)).toBeInTheDocument();
  });

  it('"yes" never confirms an order cancellation (that needs its own button) and goes to the assistant', async () => {
    const user = userEvent.setup();
    const cancelOrder = vi.fn();
    const chat = vi.fn().mockResolvedValue(reply({ reply: 'Cancel?', actions: [{ type: 'cancel_order', order_number: 'SA-50001', label: 'Cancel order' }] }));
    setup({ cancelOrder, chat });
    await user.type(input(), 'cancel my order{Enter}');
    await screen.findByRole('button', { name: 'Cancel order' });
    await user.type(input(), 'yes{Enter}');
    await waitFor(() => expect(chat).toHaveBeenCalledTimes(2));
    expect(cancelOrder).not.toHaveBeenCalled();
  });

  it('"yes" with two different proposals is not guessed: it goes to the assistant', async () => {
    const user = userEvent.setup();
    const addToCart = vi.fn();
    const chat = vi.fn().mockResolvedValue(reply({ reply: 'Which?', actions: [ADD, { ...ADD, slug: 'daytrip-22l-daypack', label: 'Add daypack' }] }));
    setup({ addToCart, chat });
    await user.type(input(), 'add a backpack{Enter}');
    await screen.findByRole('button', { name: 'Add daypack' });
    await user.type(input(), 'yes{Enter}');
    await waitFor(() => expect(chat).toHaveBeenCalledTimes(2));
    expect(addToCart).not.toHaveBeenCalled();
  });
});

describe('read-aloud and real playback', () => {
  it('typed questions are not read aloud by default; turning read-aloud on speaks the next reply', async () => {
    const user = userEvent.setup();
    const speak = vi.spyOn(speaker, 'speak').mockResolvedValue({ mode: 'server', voice: null });
    vi.spyOn(speaker, 'prime').mockImplementation(() => {});
    sessionStorage.setItem('avc:store-a:conversation-language', 'en');
    setup({ chat: vi.fn().mockResolvedValue(reply({ reply: 'Hello there.' })) });
    expect(await screen.findByText('Replies to voice questions are read aloud.')).toBeInTheDocument();
    await user.type(input(), 'hi{Enter}');
    await screen.findByText('Hello there.');
    expect(speak).not.toHaveBeenCalled();
    await user.click(screen.getByRole('checkbox', { name: /Read replies aloud/ }));
    expect(localStorage.getItem('avc:read-aloud')).toBe('on');
    await user.type(input(), 'again{Enter}');
    await waitFor(() => expect(speak).toHaveBeenCalledWith('Hello there.', 'en', expect.objectContaining({ onError: expect.any(Function) })));
  });

  it('a stored legacy "0" (written on every page load before) does not silence voice replies; an explicit "off" does', () => {
    localStorage.setItem('avc:speak-replies', '0');
    setup();
    expect(screen.getByText('பதில்களை உரக்கப் படி').previousSibling).not.toBeChecked();
    expect(screen.getByText('குரல் கேள்விகளுக்கான பதில்கள் உரக்கப் படிக்கப்படும்.')).toBeInTheDocument();
  });

  it('a blocked autoplay is reported (not shown as spoken) and the reply can be played with a tap', async () => {
    const user = userEvent.setup();
    localStorage.setItem('avc:read-aloud', 'on');
    const speak = vi.spyOn(speaker, 'speak').mockResolvedValueOnce({ mode: 'blocked', voice: null }).mockResolvedValue({ mode: 'server', voice: null });
    const prime = vi.spyOn(speaker, 'prime').mockImplementation(() => {});
    setup({ chat: vi.fn().mockResolvedValue(reply({ reply: 'Your order is being prepared.' })) });
    await user.type(input(), 'where is my order{Enter}');
    expect(await screen.findByText('Your browser blocked automatic playback. Tap 🔊 to hear the reply.')).toBeInTheDocument();
    const replay = screen.getByRole('button', { name: 'Read this reply aloud' });
    await waitFor(() => expect(replay).toHaveAttribute('data-tts-mode', 'blocked'));
    await user.click(replay);
    expect(prime).toHaveBeenCalled();
    expect(speak).toHaveBeenLastCalledWith('Your order is being prepared.', 'en', expect.any(Object));
    await waitFor(() => expect(replay).toHaveAttribute('data-tts-mode', 'server'));
  });

  it('a playback error after speech started is surfaced', async () => {
    const user = userEvent.setup();
    localStorage.setItem('avc:read-aloud', 'on');
    vi.spyOn(speaker, 'prime').mockImplementation(() => {});
    vi.spyOn(speaker, 'speak').mockImplementation(async (_t, _l, { onError }) => { setTimeout(() => onError('failed'), 0); return { mode: 'browser', voice: 'Rishi' }; });
    setup({ chat: vi.fn().mockResolvedValue(reply({ reply: 'Shown and spoken.' })) });
    await user.type(input(), 'hi{Enter}');
    expect(await screen.findByText(/couldn’t be played aloud/)).toBeInTheDocument();
  });

  it('with read-aloud off, nothing is spoken', async () => {
    const user = userEvent.setup();
    localStorage.setItem('avc:read-aloud', 'off');
    const speak = vi.spyOn(speaker, 'speak');
    setup({ chat: vi.fn().mockResolvedValue(reply({ reply: 'Silent reply.' })) });
    await user.type(input(), 'hi{Enter}');
    await screen.findByText('Silent reply.');
    expect(speak).not.toHaveBeenCalled();
  });
});

describe('language label', () => {
  it('a message with no language evidence continues the known conversation language (no "not detected")', async () => {
    const user = userEvent.setup();
    setup({ chat: vi.fn().mockResolvedValue(reply({ reply: 'ஆர்டர் SA-50001 தயாராகிறது.', language: 'ta', language_status: 'neutral' })) });
    await user.type(input(), 'SA-50001{Enter}');
    expect(await screen.findByText(/தமிழ் · உரையாடல் மொழியில் தொடர்கிறது/)).toBeInTheDocument();
    expect(screen.queryByText(/கண்டறியப்படவில்லை/)).not.toBeInTheDocument();
  });
});
