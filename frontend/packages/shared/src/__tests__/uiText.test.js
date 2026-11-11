import { describe, expect, it } from 'vitest';
import { UI_LANGUAGES, ui, uiTable } from '../uiText.js';

const placeholders = (s) => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();

describe('storefront interface text', () => {
  it('has Tamil, English and Hindi for every key, with the same placeholders', () => {
    expect(UI_LANGUAGES.map(([c]) => c)).toEqual(['en', 'ta', 'hi']);
    for (const [key, entry] of Object.entries(uiTable)) {
      for (const lang of ['en', 'ta', 'hi']) {
        expect(entry[lang], `${key}.${lang}`).toBeTruthy();
        if (lang !== 'en' && key !== 'cartLabel') expect(placeholders(entry[lang]), `${key}.${lang}`).toEqual(placeholders(entry.en));
      }
    }
  });

  it('Tamil and Hindi entries use their own scripts', () => {
    for (const [key, entry] of Object.entries(uiTable)) {
      expect(/[஀-௿]/.test(entry.ta), `${key}.ta`).toBe(true);
      expect(/[ऀ-ॿ]/.test(entry.hi), `${key}.hi`).toBe(true);
    }
  });

  it('fills placeholders and falls back to English', () => {
    expect(ui('ta', 'ask', { assistant: 'Scout' })).toBe('Scout-இடம் கேளுங்கள்');
    expect(ui('fr', 'shop')).toBe('Shop');
    expect(ui('en', 'cartLabel', { n: 2, s: 's' })).toBe('Cart, 2 items');
  });
});
