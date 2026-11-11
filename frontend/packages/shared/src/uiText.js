// Storefront interface text in Tamil, English and Hindi (Phase I). English is the default interface language (an owner
// decision; the chat assistant separately starts in Tamil). Tamil and Hindi strings were written for this project and
// still need native-speaker review (docs/india-readiness.md). Store data (policies) comes translated from the server.
export const UI_LANGUAGES = [['en', 'English', 'en'], ['ta', 'தமிழ்', 'ta-IN'], ['hi', 'हिन्दी', 'hi-IN']];

const T = {
  skip: { en: 'Skip to content', ta: 'உள்ளடக்கத்துக்குச் செல்', hi: 'सामग्री पर जाएँ' },
  shop: { en: 'Shop', ta: 'கடை', hi: 'दुकान' },
  signIn: { en: 'Sign in', ta: 'உள்நுழை', hi: 'साइन इन' },
  hi: { en: 'Hi, {name}', ta: 'வணக்கம், {name}', hi: 'नमस्ते, {name}' },
  cart: { en: 'Cart', ta: 'கார்ட்', hi: 'कार्ट' },
  cartLabel: { en: 'Cart, {n} item{s}', ta: 'கார்ட், {n} பொருள்', hi: 'कार्ट, {n} सामान' },
  help: { en: 'Help', ta: 'உதவி', hi: 'मदद' },
  fulfilment: { en: 'Fulfilment', ta: 'ஆர்டர் அனுப்புதல்', hi: 'ऑर्डर भेजना' },
  customerCare: { en: 'Customer care', ta: 'வாடிக்கையாளர் சேவை', hi: 'ग्राहक सेवा' },
  mainNav: { en: 'Main', ta: 'முதன்மை', hi: 'मुख्य' },
  customerService: { en: 'Customer service', ta: 'வாடிக்கையாளர் சேவை', hi: 'ग्राहक सेवा' },
  shipping: { en: 'Shipping', ta: 'ஷிப்பிங்', hi: 'शिपिंग' },
  returns: { en: 'Returns', ta: 'திருப்பி அனுப்புதல்', hi: 'वापसी' },
  returnsWarranty: { en: 'Returns and warranty', ta: 'திருப்பி அனுப்புதல் மற்றும் வாரண்டி', hi: 'वापसी और वारंटी' },
  warranty: { en: 'Warranty', ta: 'வாரண்டி', hi: 'वारंटी' },
  contact: { en: 'Contact us', ta: 'எங்களைத் தொடர்பு கொள்ள', hi: 'संपर्क करें' },
  language: { en: 'Language', ta: 'மொழி', hi: 'भाषा' },
  demoNote: {
    en: 'Demo store with synthetic data. Payments run in sandbox test mode: no real money moves and no card details are collected.',
    ta: 'செயற்கைத் தரவுடன் கூடிய டெமோ ஸ்டோர். பணம் செலுத்துதல் சோதனை (sandbox) முறையில் மட்டும்: உண்மையான பணம் நகராது, கார்டு விவரங்கள் சேகரிக்கப்படுவதில்லை.',
    hi: 'कृत्रिम डेटा वाला डेमो स्टोर। भुगतान सिर्फ़ टेस्ट (sandbox) मोड में: कोई असली पैसा नहीं कटता और कार्ड की जानकारी नहीं ली जाती।',
  },
  loadingInfo: { en: 'Loading store information…', ta: 'ஸ்டோர் தகவல் ஏற்றப்படுகிறது…', hi: 'स्टोर की जानकारी लोड हो रही है…' },
  infoFailed: { en: 'Store information couldn’t be loaded. Please try again later.', ta: 'ஸ்டோர் தகவலை ஏற்ற முடியவில்லை. பிறகு மீண்டும் முயற்சிக்கவும்.',
    hi: 'स्टोर की जानकारी लोड नहीं हो सकी। कृपया बाद में फिर कोशिश करें।' },
  noPolicy: { en: '{store} hasn’t published a {topic} policy yet.', ta: '{store} இன்னும் {topic} கொள்கையை வெளியிடவில்லை.', hi: '{store} ने अभी {topic} नीति प्रकाशित नहीं की है।' },
  stillQuestion: { en: 'Still have a question?', ta: 'இன்னும் கேள்வி உள்ளதா?', hi: 'अब भी कोई सवाल है?' },
  ask: { en: 'Ask {assistant}', ta: '{assistant}-இடம் கேளுங்கள்', hi: '{assistant} से पूछें' },
  or: { en: 'or', ta: 'அல்லது', hi: 'या' },
  contactLower: { en: 'contact us', ta: 'எங்களைத் தொடர்பு கொள்ளுங்கள்', hi: 'हमसे संपर्क करें' },
  moreHelp: { en: 'More help', ta: 'கூடுதல் உதவி', hi: 'और मदद' },
  email: { en: 'E-mail', ta: 'மின்னஞ்சல்', hi: 'ईमेल' },
  hours: { en: 'Hours', ta: 'நேரம்', hi: 'समय' },
  chat: { en: 'Chat', ta: 'அரட்டை', hi: 'चैट' },
  anyTime: { en: 'any time', ta: 'எப்போது வேண்டுமானாலும்', hi: 'कभी भी' },
  notPublished: { en: '{store} hasn’t published a postal address, phone number or tax registration details here yet.',
    ta: '{store} இங்கு இன்னும் அஞ்சல் முகவரி, தொலைபேசி எண் அல்லது வரி பதிவு விவரங்களை வெளியிடவில்லை.',
    hi: '{store} ने यहाँ अभी डाक पता, फ़ोन नंबर या टैक्स पंजीकरण की जानकारी प्रकाशित नहीं की है।' },
  orderHint: { en: 'For an order, include its order number (for example {example}). You can see every order and its status in',
    ta: 'ஆர்டர் பற்றி என்றால், அதன் ஆர்டர் எண்ணைச் சேர்க்கவும் (உதாரணம் {example}). உங்கள் எல்லா ஆர்டர்களையும் அவற்றின் நிலையையும் இங்கே பார்க்கலாம்:',
    hi: 'ऑर्डर के बारे में हो तो उसका ऑर्डर नंबर लिखें (जैसे {example})। अपने सभी ऑर्डर और उनकी स्थिति यहाँ देखें:' },
  yourAccount: { en: 'your account', ta: 'உங்கள் கணக்கு', hi: 'आपका अकाउंट' },
  helpLead: { en: '{assistant} can answer questions about products, orders and our policies in Tamil, English or Hindi.',
    ta: '{assistant} பொருட்கள், ஆர்டர்கள், எங்கள் கொள்கைகள் பற்றிய கேள்விகளுக்குத் தமிழ், ஆங்கிலம் அல்லது இந்தியில் பதில் சொல்லும்.',
    hi: '{assistant} प्रोडक्ट, ऑर्डर और हमारी नीतियों के सवालों के जवाब तमिल, अंग्रेज़ी या हिंदी में दे सकता है।' },
  trackOrders: { en: 'Track your orders', ta: 'உங்கள் ஆர்டர்களைக் கண்காணிக்க', hi: 'अपने ऑर्डर ट्रैक करें' },
  signInTrack: { en: 'Sign in to track your orders', ta: 'ஆர்டர்களைக் கண்காணிக்க உள்நுழையவும்', hi: 'ऑर्डर ट्रैक करने के लिए साइन इन करें' },
  trackText: { en: 'Status, tracking and details of every order.', ta: 'ஒவ்வொரு ஆர்டரின் நிலை, டிராக்கிங் மற்றும் விவரங்கள்.',
    hi: 'हर ऑर्डर की स्थिति, ट्रैकिंग और विवरण।' },
};

export function ui(lang, key, vars = {}) {
  const entry = T[key];
  if (!entry) return key;
  const text = entry[lang] || entry.en;
  return text.replace(/\{(\w+)\}/g, (_, k) => (vars[k] ?? ''));
}

export const UI_KEYS = Object.keys(T);
export const uiTable = T;
