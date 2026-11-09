import React from 'react';
import { createRoot } from 'react-dom/client';
import { StoreApp } from '@avc/shared';
import '@avc/shared/styles.css';
import './theme.css';
import { HeroArt, Logo, productArt } from './art.jsx';

const config = {
  storeId: 'store-a',
  name: 'Summit Trail Co.',
  tagline: 'Gear for every trail',
  logo: <Logo />,
  assistantName: 'Scout',
  lang: 'ta-IN', // chat default: Tamil (each utterance's language is still identified automatically)
  heroTitle: 'Built for the long way round.',
  heroText: 'Tents, packs and trail-tested gear. Ask Scout about sizing, stock, shipping or where your order is — by typing or just by speaking.',
  heroArt: <HeroArt />,
  // Product artwork: local SVG illustrations. To use real photos, map a product slug to an image URL in
  // productImages (e.g. a file placed in this app's public/products/ folder); photos take priority.
  art: productArt,
  productImages: {},
  demoEmail: 'alex.rivera@example.com',
  demoPassword: 'TrailDemo!2026',
  suggestions: {
    ta: ['உங்களிடம் இரண்டு பேர் தங்கும் கூடாரம் இருக்கிறதா?', 'திருப்பி அனுப்பும் கொள்கை என்ன?', 'என் ஆர்டர் SA-10001 எங்கே?'],
    en: ['Do you have a 2-person tent?', 'What is your return policy?', 'Where is my order SA-10001?'],
    hi: ['क्या आपके पास दो लोगों का टेंट है?', 'रिटर्न पॉलिसी क्या है?', 'मेरा ऑर्डर SA-10001 कहाँ है?'],
  },
};

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <StoreApp config={config} />
  </React.StrictMode>,
);
