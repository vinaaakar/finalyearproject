import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

// Node 25 defines its own experimental global `localStorage` (without methods unless --localstorage-file is given),
// which shadows jsdom's. Point the globals at jsdom's real Web Storage so components behave as in a browser.
for (const name of ['localStorage', 'sessionStorage']) {
  const domStorage = globalThis.jsdom?.window?.[name];
  if (domStorage && typeof globalThis[name]?.clear !== 'function') {
    Object.defineProperty(globalThis, name, { value: domStorage, configurable: true, writable: true });
  }
}

afterEach(() => {
  cleanup();
  sessionStorage.clear();
  localStorage.clear();
});

// jsdom does not implement element scrolling; the chat log scrolls to the newest message.
if (!Element.prototype.scrollTo) Element.prototype.scrollTo = function scrollTo() {};

// jsdom does not implement media playback (it logs "Not implemented: HTMLMediaElement.prototype.play"). Tests that care
// about playback mock Audio / speechSynthesis themselves; elsewhere playback simply succeeds silently.
if (typeof HTMLMediaElement !== 'undefined') {
  HTMLMediaElement.prototype.play = function play() { return Promise.resolve(); };
  HTMLMediaElement.prototype.pause = function pause() {};
}
