import React from 'react';
import { createRoot } from 'react-dom/client';
import { StoreApp } from '@avc/shared';
import '@avc/shared/styles.css';
import './theme.css';

const config = {
  storeId: 'store-a',
  name: 'Summit Trail Co.',
  tagline: 'Gear for every trail',
  logo: '⛰️',
  assistantName: 'Scout',
  lang: 'en-US',
  heroTitle: 'Built for the long way round.',
  heroText: 'Tents, packs and trail-tested gear. Ask Scout about sizing, stock, shipping or where your order is — by typing or just by speaking.',
  heroEmoji: '🏔️',
  demoEmail: 'alex.rivera@example.com',
  demoPassword: 'TrailDemo!2026',
  suggestions: ['Do you have a 2-person tent?', 'What is your return policy?', 'Where is my order SA-10001?'],
};

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <StoreApp config={config} />
  </React.StrictMode>,
);
