// Chat-widget text in the three supported prototype languages. Tamil is the default.
// Only the chat widget is localised; the rest of each storefront stays in English.

export const LANGUAGES = {
  ta: { native: 'தமிழ்', bcp47: 'ta-IN' },
  en: { native: 'English', bcp47: 'en-IN' },
  hi: { native: 'हिन्दी', bcp47: 'hi-IN' },
};
export const SUPPORTED = Object.keys(LANGUAGES);
export const DEFAULT_LANGUAGE = 'ta';

const STRINGS = {
  welcome: {
    ta: 'வணக்கம்! நான் {assistant}. பொருட்கள், ஆர்டர் மற்றும் டெலிவரி, ரிட்டர்ன் மற்றும் ரீஃபண்ட், பணம் அல்லது உங்கள் கணக்கு பற்றி தமிழ், English அல்லது हिन्दी-யில் கேளுங்கள்.',
    en: 'Hi! I’m {assistant}. Ask about products, orders and delivery, returns and refunds, payments or your account — in Tamil, English or Hindi.',
    hi: 'नमस्ते! मैं {assistant} हूँ। प्रोडक्ट, ऑर्डर और डिलीवरी, रिटर्न और रिफ़ंड, भुगतान या अपने अकाउंट के बारे में तमिल, अंग्रेज़ी या हिंदी में पूछिए।',
  },
  subtitle: { ta: '{store} வாடிக்கையாளர் சேவை', en: '{store} customer service', hi: '{store} ग्राहक सेवा' },
  signedInAs: { ta: ' · {name} ஆக உள்நுழைந்துள்ளீர்கள்', en: ' · signed in as {name}', hi: ' · {name} के रूप में साइन इन' },
  placeholder: { ta: 'தட்டச்சு செய்யுங்கள் அல்லது மைக்கைத் தட்டுங்கள்', en: 'Type or tap the mic', hi: 'टाइप करें या माइक दबाएँ' },
  typeLabel: { ta: 'உங்கள் செய்தியைத் தட்டச்சு செய்யுங்கள்', en: 'Type your message', hi: 'अपना संदेश टाइप करें' },
  listening: { ta: 'கேட்கிறேன்', en: 'Listening', hi: 'सुन रहे हैं' },
  speaking: { ta: '{assistant} பேசுகிறார்', en: '{assistant} is speaking', hi: '{assistant} बोल रहा है' },
  stopSpeaking: { ta: 'நிறுத்து', en: 'Stop', hi: 'रोकें' },
  transcribing: { ta: 'எழுத்தாக்குகிறேன்', en: 'Transcribing', hi: 'लिख रहे हैं' },
  send: { ta: 'அனுப்பு', en: 'Send', hi: 'भेजें' },
  speak: { ta: 'உங்கள் கேள்வியைப் பேசுங்கள்', en: 'Speak your question', hi: 'अपना सवाल बोलिए' },
  stopVoice: { ta: 'குரல் உள்ளீட்டை நிறுத்து', en: 'Stop voice input', hi: 'आवाज़ इनपुट रोकें' },
  close: { ta: 'அரட்டையை மூடு', en: 'Close chat', hi: 'चैट बंद करें' },
  signIn: { ta: 'உள்நுழைக', en: 'Sign in', hi: 'साइन इन करें' },
  viewCart: { ta: 'கார்ட்டைப் பார்', en: 'View cart', hi: 'कार्ट देखें' },
  // Results of the chat's action buttons. Shown only after the store's API confirms the action.
  actionAdded: { ta: '{qty} × {name} உங்கள் கார்ட்டில் சேர்க்கப்பட்டது.', en: 'Added {qty} × {name} to your cart.', hi: '{qty} × {name} आपके कार्ट में जोड़ दिया गया।' },
  actionRemoved: { ta: '{name} உங்கள் கார்ட்டிலிருந்து நீக்கப்பட்டது.', en: 'Removed {name} from your cart.', hi: '{name} आपके कार्ट से हटा दिया गया।' },
  actionCancelled: { ta: 'ஆர்டர் {number} ரத்து செய்யப்பட்டது.', en: 'Order {number} has been cancelled.', hi: 'ऑर्डर {number} रद्द कर दिया गया है।' },
  actionFailed: { ta: 'அதைச் செய்ய முடியவில்லை:', en: 'That didn’t work:', hi: 'यह नहीं हो पाया:' },
  confirmCancel: { ta: 'ஆம், ஆர்டர் {number}-ஐ ரத்து செய்', en: 'Yes, cancel order {number}', hi: 'हाँ, ऑर्डर {number} रद्द करें' },
  keepOrder: { ta: 'வேண்டாம், ஆர்டரை வைத்திரு', en: 'No, keep the order', hi: 'नहीं, ऑर्डर रहने दें' },
  confirmCancelAsk: { ta: 'உறுதியாக ரத்து செய்ய வேண்டுமா? இதை மீண்டும் மாற்ற முடியாது.', en: 'Cancel this order? This can’t be undone.', hi: 'क्या यह ऑर्डर रद्द करें? इसे वापस नहीं किया जा सकता।' },
  quickAnswer: { ta: 'விரைவு பதில்', en: 'quick answer', hi: 'त्वरित जवाब' },
  youSaid: { ta: 'நீங்கள் சொன்னது', en: 'You said', hi: 'आपने कहा' },
  assistantSaid: { ta: '{assistant} சொன்னது', en: '{assistant} said', hi: '{assistant} ने कहा' },
  typing: { ta: 'உதவியாளர் தட்டச்சு செய்கிறார்', en: 'Assistant is typing', hi: 'सहायक लिख रहा है' },
  conversationLanguage: { ta: 'உரையாடல் மொழி', en: 'Conversation language', hi: 'बातचीत की भाषा' },
  readAloud: { ta: 'பதில்களை உரக்கப் படி', en: 'Read replies aloud', hi: 'जवाब बोलकर सुनाएँ' },
  // How a reply's language was chosen (never claims detection unless the server detected it).
  langDetected: { ta: '{lang} · உங்கள் வார்த்தைகளிலிருந்து கண்டறியப்பட்டது', en: '{lang} · detected from your words', hi: '{lang} · आपके शब्दों से पहचानी गई' },
  langNeutral: { ta: '{lang} · மொழி கண்டறியப்படவில்லை, உரையாடல் மொழியில் பதில்', en: '{lang} · language not detected, replying in the conversation language',
    hi: '{lang} · भाषा नहीं पहचानी गई, बातचीत की भाषा में जवाब' },
  langSelected: { ta: '{lang} · நீங்கள் தேர்ந்தெடுத்தது', en: '{lang} · your choice', hi: '{lang} · आपकी पसंद' },
  chooseLanguage: { ta: 'மொழியைத் தேர்ந்தெடுங்கள்:', en: 'Choose a language:', hi: 'भाषा चुनें:' },
  autoDetectOn: {
    ta: 'பேசும் மொழி (தமிழ், English, हिन्दी) ஒவ்வொரு முறையும் தானாகக் கண்டறியப்படும்.',
    en: 'The spoken language (Tamil, English, Hindi) is detected automatically each time.',
    hi: 'बोली गई भाषा (तमिल, अंग्रेज़ी, हिंदी) हर बार अपने-आप पहचानी जाती है।',
  },
  autoDetectOff: {
    ta: 'தானியங்கி மொழி கண்டறிதலுக்கு ஸ்டோரின் உள்ளூர் பேச்சு இயந்திரம் தேவை. உங்கள் உலாவி {lang}-இல் கேட்கும்; பதிலின் மொழி அது புரிந்துகொண்ட வார்த்தைகளைப் பொறுத்தது.',
    en: 'Automatic spoken-language detection needs the store’s local speech engine. Your browser will listen in {lang}; the reply language follows the words it recognises.',
    hi: 'अपने-आप भाषा पहचानने के लिए स्टोर का लोकल स्पीच इंजन चाहिए। आपका ब्राउज़र {lang} में सुनेगा; जवाब की भाषा पहचाने गए शब्दों पर निर्भर करेगी।',
  },
  privacyServer: { ta: 'குரல் {store}-இன் சொந்த சர்வரில் (உள்ளூர் இயந்திரம்) எழுத்தாக்கப்படுகிறது.', en: 'Voice is transcribed on {store}’s own server (local engine).',
    hi: 'आवाज़ {store} के अपने सर्वर पर (लोकल इंजन से) लिखी जाती है।' },
  privacyBrowser: { ta: 'குரல் உங்கள் உலாவியின் பேச்சு சேவையைப் பயன்படுத்துகிறது.', en: 'Voice uses your browser’s speech service.',
    hi: 'आवाज़ आपके ब्राउज़र की स्पीच सेवा का उपयोग करती है।' },
  noVoice: { ta: 'இந்தச் சாதனத்தில் {lang} குரல் இல்லை — பதில் எழுத்தில் மட்டும் காட்டப்படுகிறது.', en: 'No {lang} voice is available on this device — the reply is shown as text only.',
    hi: 'इस डिवाइस पर {lang} आवाज़ उपलब्ध नहीं है — जवाब सिर्फ़ टेक्स्ट में दिखाया गया है।' },
  rateLimited: { ta: 'நீங்கள் வேகமாகச் செய்திகளை அனுப்புகிறீர்கள் — சிறிது நேரம் கழித்து முயற்சி செய்யுங்கள்.', en: 'You’re sending messages quickly — please wait a moment and try again.',
    hi: 'आप बहुत जल्दी संदेश भेज रहे हैं — कृपया थोड़ी देर बाद कोशिश करें।' },
  // Voice-input messages
  'not-allowed': { ta: 'மைக்ரோஃபோன் அனுமதி மறுக்கப்பட்டது. உலாவியின் தள அமைப்புகளில் அனுமதிக்கலாம், அல்லது தட்டச்சு செய்யுங்கள்.',
    en: 'Microphone access was blocked. You can allow it in your browser’s site settings, or keep typing.',
    hi: 'माइक्रोफ़ोन की अनुमति नहीं मिली। आप ब्राउज़र की साइट सेटिंग में अनुमति दे सकते हैं, या टाइप करते रहें।' },
  'audio-capture': { ta: 'மைக்ரோஃபோன் கிடைக்கவில்லை. ஒன்றை இணைக்கவும் அல்லது தட்டச்சு செய்யுங்கள்.', en: 'No microphone was found. Please connect one or keep typing.',
    hi: 'कोई माइक्रोफ़ोन नहीं मिला। कृपया एक जोड़ें या टाइप करें।' },
  'no-speech': { ta: 'எதுவும் கேட்கவில்லை. மைக்கைத் தட்டி மீண்டும் பேசுங்கள்.', en: 'I didn’t hear anything. Tap the microphone and try again.',
    hi: 'कुछ सुनाई नहीं दिया। माइक दबाकर फिर से बोलिए।' },
  'service-not-allowed': { ta: 'இந்த உலாவியில் பேச்சு அங்கீகாரம் அனுமதிக்கப்படவில்லை. தட்டச்சு செய்யுங்கள்.', en: 'Speech recognition is not allowed in this browser. You can keep typing instead.',
    hi: 'इस ब्राउज़र में स्पीच रिकग्निशन की अनुमति नहीं है। आप टाइप कर सकते हैं।' },
  network: { ta: 'பேச்சு சேவையை அணுக முடியவில்லை. உங்கள் கேள்வியைத் தட்டச்சு செய்யுங்கள்.', en: 'The speech service could not be reached. Please type your question instead.',
    hi: 'स्पीच सेवा तक नहीं पहुँच पाए। कृपया अपना सवाल टाइप करें।' },
  failed: { ta: 'குரல் உள்ளீடு தோல்வியடைந்தது. மீண்டும் முயற்சி செய்யுங்கள் அல்லது தட்டச்சு செய்யுங்கள்.', en: 'Voice input failed. Please try again or type your question.',
    hi: 'आवाज़ इनपुट विफल रहा। फिर से कोशिश करें या अपना सवाल टाइप करें।' },
  unsupported: { ta: 'இந்த உலாவியில் குரல் உள்ளீடு ஆதரிக்கப்படவில்லை. Chrome, Edge அல்லது Safari-ஐ முயற்சிக்கவும், அல்லது தட்டச்சு செய்யுங்கள்.',
    en: 'Voice input isn’t supported in this browser. Try Chrome, Edge or Safari, or type your question.',
    hi: 'इस ब्राउज़र में आवाज़ इनपुट समर्थित नहीं है। Chrome, Edge या Safari आज़माएँ, या टाइप करें।' },
  insecure: { ta: 'குரல் உள்ளீட்டிற்கு பாதுகாப்பான (https அல்லது localhost) பக்கம் தேவை.', en: 'Voice input needs a secure (https or localhost) page.',
    hi: 'आवाज़ इनपुट के लिए सुरक्षित (https या localhost) पेज चाहिए।' },
};

export function tr(lang, key, values = {}) {
  const entry = STRINGS[key];
  if (!entry) return key;
  return (entry[lang] || entry.en).replace(/\{(\w+)\}/g, (_, k) => values[k] ?? '');
}

export function suggestionsFor(config, lang) {
  const s = config.suggestions;
  return Array.isArray(s) ? s : s[lang] || s[DEFAULT_LANGUAGE] || [];
}
