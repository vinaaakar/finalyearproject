import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import CallPage from '../pages/CallPage.jsx';
import { speaker } from '../voice.js';
import { apiError, makeApi, makeStore, renderAt } from './helpers.jsx';

const store = vi.hoisted(() => ({ value: null }));
vi.mock('../StoreApp.jsx', () => ({ useStore: () => store.value }));

const turn = (say, extra = {}) => ({ simulated: true, call_id: 'call_1234567890', say, language: 'en', expect_input: true,
  hang_up: false, transfer_to_agent: false, ...extra });

function setup(api) {
  store.value = makeStore({ api: makeApi(api) });
  renderAt(<CallPage />);
  return store.value.api;
}

beforeEach(() => {
  vi.spyOn(speaker, 'speak').mockResolvedValue({ mode: 'none' });
});
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe('simulated customer-care call', () => {
  it('is labelled as a simulation with no person on the line, and opens in Tamil by default', async () => {
    const api = setup({ phoneStart: vi.fn().mockResolvedValue(turn('வணக்கம்', { language: 'ta' })) });
    expect(screen.getByText(/no telephone network is involved/)).toBeInTheDocument();
    expect(screen.getByText(/No person is on this line/)).toBeInTheDocument();
    expect(screen.getByTestId('call-language')).toHaveValue('ta');
    await userEvent.setup().click(screen.getByRole('button', { name: 'Start call' }));
    expect(api.phoneStart).toHaveBeenCalledWith('ta');
    expect(await screen.findByText('வணக்கம்')).toBeInTheDocument();
    expect(speaker.speak).toHaveBeenCalledWith('வணக்கம்', 'ta', expect.any(Object));
    expect(screen.getByText('Connected to Scout')).toBeInTheDocument();
  });

  it('sends typed speech and keypad digits as turns, and links a recorded reference', async () => {
    const user = userEvent.setup();
    const api = setup({
      phoneStart: vi.fn().mockResolvedValue(turn('Hello')),
      phoneTurn: vi.fn()
        .mockResolvedValueOnce(turn('Please key in your order number.'))
        .mockResolvedValueOnce(turn('Done. Your reference is SA-CMP-00007.')),
    });
    await user.selectOptions(screen.getByTestId('call-language'), 'en');
    await user.click(screen.getByRole('button', { name: 'Start call' }));
    await screen.findByText('Hello');
    await user.type(screen.getByPlaceholderText('Or type what you would say'), 'My lamp is broken');
    await user.click(screen.getByRole('button', { name: 'Say it' }));
    expect(api.phoneTurn).toHaveBeenCalledWith('call_1234567890', { speech: 'My lamp is broken' });
    await screen.findByText('Please key in your order number.');
    for (const k of ['1', '0', '0', '0', '1']) await user.click(screen.getByRole('button', { name: k }));
    expect(screen.getByText('Keys: 10001')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Send the keys now (#)' }));
    expect(api.phoneTurn).toHaveBeenLastCalledWith('call_1234567890', { digits: '10001' });
    expect(await screen.findByRole('link', { name: 'SA-CMP-00007' })).toHaveAttribute('href', '/support/requests/SA-CMP-00007');
  });

  it('keys pressed together are sent after a pause', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const api = setup({ phoneStart: vi.fn().mockResolvedValue(turn('Hello')), phoneTurn: vi.fn().mockResolvedValue(turn('Thanks.')) });
    await user.click(screen.getByRole('button', { name: 'Start call' }));
    await screen.findByText('Hello');
    await user.click(screen.getByRole('button', { name: '2' }));
    expect(api.phoneTurn).not.toHaveBeenCalled();
    await act(async () => { vi.advanceTimersByTime(1600); });
    expect(api.phoneTurn).toHaveBeenCalledWith('call_1234567890', { digits: '2' });
  });

  it('ends when the assistant hangs up, and can call again', async () => {
    const user = userEvent.setup();
    setup({ phoneStart: vi.fn().mockResolvedValue(turn('Hello')), phoneTurn: vi.fn().mockResolvedValue(turn('Goodbye!', { hang_up: true })) });
    await user.click(screen.getByRole('button', { name: 'Start call' }));
    await screen.findByText('Hello');
    await user.type(screen.getByPlaceholderText('Or type what you would say'), 'bye');
    await user.click(screen.getByRole('button', { name: 'Say it' }));
    await screen.findByText('Goodbye!');
    expect(screen.getByText('Call ended.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Hang up' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Call again' })).toBeInTheDocument();
  });

  it('hang up stops speech and ends the call locally', async () => {
    const user = userEvent.setup();
    const cancel = vi.spyOn(speaker, 'cancel');
    setup({ phoneStart: vi.fn().mockResolvedValue(turn('Hello')) });
    await user.click(screen.getByRole('button', { name: 'Start call' }));
    await screen.findByText('Hello');
    await user.click(screen.getByRole('button', { name: 'Hang up' }));
    expect(cancel).toHaveBeenCalled();
    expect(screen.getByText('Call ended.')).toBeInTheDocument();
  });

  it('explains when the line is unavailable or busy', async () => {
    const user = userEvent.setup();
    setup({ phoneStart: vi.fn().mockRejectedValueOnce(apiError('Not Found', 404)).mockRejectedValueOnce(apiError('Too many', 429)) });
    await user.click(screen.getByRole('button', { name: 'Start call' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('isn’t available on this server');
    await user.click(screen.getByRole('button', { name: 'Start call' }));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Too many calls'));
  });
});
