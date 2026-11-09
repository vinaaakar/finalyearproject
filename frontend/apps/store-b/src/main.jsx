import React from 'react';
import { createRoot } from 'react-dom/client';
import { StoreApp } from '@avc/shared';
import '@avc/shared/styles.css';
import './theme.css';
import { HeroArt, Logo, productArt } from './art.jsx';

const config = {
  storeId: 'store-b',
  name: 'Bloom & Brew',
  tagline: 'Coffee, tea & a cozier kitchen',
  logo: <Logo />,
  assistantName: 'Maple',
  lang: 'ta-IN', // chat default: Tamil (each utterance's language is still identified automatically)
  heroTitle: 'Slow mornings, better cups.',
  heroText: 'Small-batch coffee, loose-leaf tea and brewing gear. Maple can help you choose, check stock, or track an order — just type or talk.',
  heroArt: <HeroArt />,
  // Product artwork: local SVG illustrations. To use real photos, map a product slug to an image URL in
  // productImages (e.g. a file placed in this app's public/products/ folder); photos take priority.
  art: productArt,
  productImages: {},
  demoEmail: 'maria.gomez@example.com',
  demoPassword: 'BrewDemo!2026',
  suggestions: {
    ta: ['உங்களிடம் என்ன காபி பீன்ஸ் உள்ளன?', 'ஷிப்பிங் கட்டணம் எவ்வளவு?', 'என் ஆர்டர் BB-20001 எங்கே?'],
    en: ['Which coffee beans do you have?', 'How much is shipping?', 'Where is my order BB-20001?'],
    hi: ['आपके पास कौन-सी कॉफ़ी बीन्स हैं?', 'शिपिंग कितनी है?', 'मेरा ऑर्डर BB-20001 कहाँ है?'],
  },
};

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <StoreApp config={config} />
  </React.StrictMode>,
);
