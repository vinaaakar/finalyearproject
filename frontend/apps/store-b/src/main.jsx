import React from 'react';
import { createRoot } from 'react-dom/client';
import { StoreApp } from '@avc/shared';
import '@avc/shared/styles.css';
import './theme.css';

const config = {
  storeId: 'store-b',
  name: 'Bloom & Brew',
  tagline: 'Coffee, tea & a cozier kitchen',
  logo: '☕',
  assistantName: 'Maple',
  lang: 'en-US',
  heroTitle: 'Slow mornings, better cups.',
  heroText: 'Small-batch coffee, loose-leaf tea and brewing gear. Maple can help you choose, check stock, or track an order — just type or talk.',
  heroEmoji: '🫖',
  demoEmail: 'maria.gomez@example.com',
  demoPassword: 'BrewDemo!2026',
  suggestions: ['Which coffee beans do you have?', 'How much is shipping?', 'Where is my order BB-20001?'],
};

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <StoreApp config={config} />
  </React.StrictMode>,
);
