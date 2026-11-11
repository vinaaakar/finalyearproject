// The chat conversation survives a page refresh (sessionStorage, last 30 messages + the customer-care draft), per store
// and per account; signing out clears it; another account never sees it; secrets and voice data are never stored.
import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import ChatWidget, { accountKey, chatStorageKey } from '../ChatWidget.jsx';
import { makeApi, makeStore } from './helpers.jsx';

const store = vi.hoisted(() => ({ value: null }));
vi.mock('../StoreApp.jsx', () => ({ useStore: () => store.value }));

const PRIYA = { customer: { name: 'Priya Raman', email: 'priya@example.com', role: 'customer' } };
const ARUN = { customer: { name: 'Arun Kumar', email: 'arun@example.com', role: 'customer' } };
const DRAFT = { kind: 'complaint', step: 'description', order: 'SA-50001', category: 'damaged' };

const reply = (text, extra = {}) => ({
  reply: text, products: [], orders: [], requires_login: false, source: 'rules', actions: [], cart: null,
  language: 'en', language_status: 'detected', clarification: false, ...extra,
});

const tree = () => (
  <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
    <ChatWidget open prefill="" onOpen={() => {}} onClose={() => {}} />
  </MemoryRouter>
);

function mount({ storeId = 'store-a', session = PRIYA, chat } = {}) {
  const api = makeApi({ chat: chat || vi.fn().mockResolvedValue(reply('Here is what I found.')) });
  store.value = makeStore({ storeId, api, session });
  const view = render(tree());
  const switchTo = (next) => { store.value = { ...store.value, session: next }; view.rerender(tree()); };
  return { api, switchTo };
}

async function say(text) {
  const user = userEvent.setup();
  await user.type(screen.getByRole('textbox'), `${text}{Enter}`);
}

const log = () => within(screen.getByRole('dialog'));

describe.each([['store-a'], ['store-b']])('chat persistence (%s)', (storeId) => {
  it('restores the conversation and the language after a refresh', async () => {
    mount({ storeId });
    await say('Do you have a 2-person tent?');
    expect(await screen.findByText('Here is what I found.')).toBeInTheDocument();
    cleanup();                                                                      // the page reloads
    mount({ storeId });
    expect(log().getByText('Do you have a 2-person tent?')).toBeInTheDocument();
    expect(log().getByText('Here is what I found.')).toBeInTheDocument();
    expect(screen.getByTestId('conversation-language')).toHaveValue('en');
    const other = storeId === 'store-a' ? 'store-b' : 'store-a';                   // the other store never sees it
    expect(sessionStorage.getItem(chatStorageKey(other, accountKey(PRIYA)))).toBeNull();
  });

  it('keeps an unfinished customer-care draft through a refresh and sends it back with the next message', async () => {
    mount({ storeId, chat: vi.fn().mockResolvedValue(reply('Please describe the problem.', { care_draft: DRAFT })) });
    await say('I received a damaged product');
    await screen.findByText('Please describe the problem.');
    cleanup();
    const { api } = mount({ storeId });
    await say('The lid is cracked.');
    expect(api.chat.mock.calls[0][3].careDraft).toEqual(DRAFT);
  });
});

describe('chat persistence across accounts', () => {
  it('signing out removes the conversation and the draft, and shows an empty chat', async () => {
    const { switchTo } = mount({ chat: vi.fn().mockResolvedValue(reply('Order SA-50001 is being prepared.', { care_draft: DRAFT })) });
    await say('Where is my order?');
    await screen.findByText('Order SA-50001 is being prepared.');
    const key = chatStorageKey('store-a', accountKey(PRIYA));
    expect(sessionStorage.getItem(key)).not.toBeNull();
    const writes = vi.spyOn(Object.getPrototypeOf(sessionStorage), 'setItem');
    switchTo(null);                                                                  // sign out
    // Not even briefly: the signed-out (guest) key never receives the previous account's messages.
    expect(writes.mock.calls.filter(([k]) => k === chatStorageKey('store-a', 'guest'))).toEqual([]);
    expect(log().queryByText('Order SA-50001 is being prepared.')).not.toBeInTheDocument();
    expect(log().queryByText('Where is my order?')).not.toBeInTheDocument();
    expect(sessionStorage.getItem(key)).toBeNull();
    expect(sessionStorage.getItem(chatStorageKey('store-a', 'guest'))).toBeNull();
  });

  it('another account never sees the previous account’s conversation or draft', async () => {
    const chat = vi.fn().mockResolvedValue(reply('Your complaint draft is ready.', { care_draft: DRAFT }));
    const { api, switchTo } = mount({ chat });
    await say('My item is damaged');
    await screen.findByText('Your complaint draft is ready.');
    switchTo(ARUN);
    expect(log().queryByText('Your complaint draft is ready.')).not.toBeInTheDocument();
    expect(sessionStorage.getItem(chatStorageKey('store-a', accountKey(PRIYA)))).toBeNull();
    chat.mockResolvedValue(reply('Hello Arun.'));
    await say('Hi');
    expect(api.chat.mock.calls[1][3].careDraft).toBeUndefined();                   // Priya's draft is gone
    cleanup();
    mount({ session: PRIYA });                                                        // Priya again: nothing restored
    expect(log().queryByText('Your complaint draft is ready.')).not.toBeInTheDocument();
  });

  it('a guest who signs in keeps the conversation (the assistant promised to remember it)', async () => {
    const { switchTo } = mount({ session: null, chat: vi.fn().mockResolvedValue(reply('Please sign in first — I’ll keep what you told me.', { care_draft: DRAFT, requires_login: true })) });
    await say('I received a damaged product');
    await screen.findByText(/Please sign in first/);
    switchTo(PRIYA);
    expect(log().getByText('I received a damaged product')).toBeInTheDocument();
    expect(sessionStorage.getItem(chatStorageKey('store-a', 'guest'))).toBeNull();
    const saved = JSON.parse(sessionStorage.getItem(chatStorageKey('store-a', accountKey(PRIYA))));
    expect(saved.careDraft).toEqual(DRAFT);
  });

  it('stores at most 30 messages, never secrets, voice data or the e-mail address', async () => {
    let n = 0;
    mount({ chat: vi.fn(async () => reply(`Reply ${++n}`)) });
    await say('My card is 4111 1111 1111 1111');
    await screen.findByText('Reply 1');
    for (let i = 0; i < 16; i += 1) {
      await say(`Question ${i}`);
      await screen.findByText(`Reply ${i + 2}`);
    }
    const key = chatStorageKey('store-a', accountKey(PRIYA));
    expect(key).not.toContain('priya');
    const raw = sessionStorage.getItem(key);
    const saved = JSON.parse(raw);
    expect(saved.messages).toHaveLength(30);
    expect(saved.messages.at(-1).content).toBe('Reply 17');
    expect(raw).not.toContain('4111');
    expect(raw).not.toContain('voiceMeta');
    expect(raw).not.toContain('priya@example.com');
  });

  it('a password typed in the chat is stored only as a mask', async () => {
    mount();
    await say('my password is hunter2');
    await screen.findByText('Here is what I found.');
    const raw = sessionStorage.getItem(chatStorageKey('store-a', accountKey(PRIYA)));
    expect(raw).not.toContain('hunter2');
    expect(JSON.parse(raw).messages[0].content).toBe('•••');
  });
});
