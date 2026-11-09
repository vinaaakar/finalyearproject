"""Assistant reply templates in Tamil, English and Hindi.

Only the surrounding words are translated. Product names, prices, order numbers, carriers, tracking
numbers and dates are inserted unchanged, so they are identical in every language (tested).
The Hindi uses gender-neutral phrasing (the assistants Scout and Maple have no grammatical gender here).
"""

from __future__ import annotations

T: dict[str, dict[str, str]] = {
    "greeting": {
        "ta": "வணக்கம்{who}! நான் {assistant}, {store} உதவியாளர். பொருட்கள், ஸ்டாக், உங்கள் ஆர்டர் மற்றும் டெலிவரி, ரிட்டர்ன், ரீஃபண்ட், பணம், உங்கள் கணக்கு பற்றி நான் உதவ முடியும்.",
        "en": "Hi{who}! I'm {assistant}, the {store} assistant. I can help with products and stock, your orders and delivery, returns and refunds, payments and your account.",
        "hi": "नमस्ते{who}! मैं {assistant} हूँ, {store} की ग्राहक सहायता। आप मुझसे प्रोडक्ट और स्टॉक, अपने ऑर्डर और डिलीवरी, रिटर्न और रिफ़ंड, भुगतान और अपने अकाउंट के बारे में पूछ सकते हैं।",
    },
    "order_login": {
        "ta": "உங்கள் பாதுகாப்பிற்காக, ஆர்டர் நிலையைப் பார்க்க முதலில் உங்கள் கணக்கில் உள்நுழையுங்கள்.",
        "en": "For your security, please sign in to your account so I can look up your order status.",
        "hi": "आपकी सुरक्षा के लिए, ऑर्डर की स्थिति देखने से पहले कृपया अपने अकाउंट में साइन इन करें।",
    },
    "order_not_found": {
        "ta": "உங்கள் {store} கணக்கில் {number} என்ற ஆர்டரைக் கண்டுபிடிக்க முடியவில்லை. {store} ஆர்டர் எண்கள் {prefix} என்று தொடங்கும்.",
        "en": "I couldn't find order {number} on your {store} account. {store} order numbers start with {prefix}.",
        "hi": "आपके {store} अकाउंट में ऑर्डर {number} नहीं मिला। {store} के ऑर्डर नंबर {prefix} से शुरू होते हैं।",
    },
    "no_orders": {
        "ta": "உங்கள் கணக்கில் இன்னும் ஆர்டர்கள் எதுவும் இல்லை.",
        "en": "I don't see any orders on your account yet.",
        "hi": "आपके अकाउंट में अभी कोई ऑर्डर नहीं है।",
    },
    "agent_needs_number": {
        "ta": "நீங்கள் பார்க்க விரும்பும் ஆர்டர் எண்ணைச் சொல்லுங்கள்.",
        "en": "Please give me the order number you'd like to look up.",
        "hi": "कृपया वह ऑर्डर नंबर बताइए जिसे आप देखना चाहते हैं।",
    },
    "order_line": {"ta": "ஆர்டர் {number} {status}", "en": "Order {number} is {status}", "hi": "ऑर्डर {number} {status}"},
    "order_via": {"ta": " — {carrier} மூலம் (டிராக்கிங் எண் {tracking})", "en": " via {carrier} (tracking {tracking})",
                  "hi": " — {carrier} से (ट्रैकिंग नंबर {tracking})"},
    "order_eta": {"ta": "; {date}-க்குள் வந்து சேரும் என எதிர்பார்க்கப்படுகிறது", "en": ", expected by {date}", "hi": "; {date} तक पहुँचने की उम्मीद है"},
    "order_on": {"ta": " ({date} அன்று)", "en": " on {date}", "hi": " ({date} को)"},
    "found": {"ta": "இவை கிடைக்கின்றன: ", "en": "Here's what I found: ", "hi": "मुझे ये मिले: "},
    "found_budget": {"ta": "{budget}-க்குள் இவை கிடைக்கின்றன: ", "en": "Here's what I found within {budget}: ", "hi": "{budget} के अंदर ये मिले: "},
    "in_stock": {"ta": "ஸ்டாக்கில் உள்ளது", "en": "in stock", "hi": "स्टॉक में है"},
    "out_of_stock": {"ta": "தற்போது ஸ்டாக்கில் இல்லை", "en": "currently out of stock", "hi": "अभी स्टॉक में नहीं है"},
    "low_stock": {"ta": "{n} மட்டுமே உள்ளன", "en": "only {n} left", "hi": "सिर्फ़ {n} बचे हैं"},
    "not_found": {
        "ta": "{store}-இல் பொருத்தமான பொருள் எதுவும் கிடைக்கவில்லை{within}.",
        "en": "I couldn't find a matching product{within} at {store}.",
        "hi": "{store} में{within} कोई मिलता-जुलता प्रोडक्ट नहीं मिला।",
    },
    "not_found_within": {"ta": " ({budget}-க்குள்)", "en": " within {budget}", "hi": " {budget} के अंदर"},
    "we_carry": {"ta": " எங்களிடம் உள்ள வகைகள்: {cats}.", "en": " We carry: {cats}.", "hi": " हमारे पास ये श्रेणियाँ हैं: {cats}।"},
    "cart_staff": {"ta": "ஸ்டாஃப் கணக்குகளுக்கு ஷாப்பிங் கார்ட் இல்லை.", "en": "Staff accounts don't have a shopping cart.",
                   "hi": "स्टाफ़ अकाउंट के लिए शॉपिंग कार्ट नहीं होता।"},
    "cart_empty": {"ta": "உங்கள் கார்ட் காலியாக உள்ளது.", "en": "Your cart is empty.", "hi": "आपका कार्ट खाली है।"},
    "cart_contents": {
        "ta": "உங்கள் கார்ட்டில்: {lines}. துணைத் தொகை {subtotal}, {shipping}, மொத்தம் {total}.",
        "en": "Your cart has {lines}. Subtotal {subtotal} plus {shipping}, total {total}.",
        "hi": "आपके कार्ट में: {lines}। सबटोटल {subtotal}, {shipping}, कुल {total}।",
    },
    "ship_free": {"ta": "ஷிப்பிங் இலவசம்", "en": "free shipping", "hi": "शिपिंग मुफ़्त"},
    "ship_cost": {"ta": "ஷிப்பிங் {price}", "en": "{price} shipping", "hi": "शिपिंग {price}"},
    "cart_out": {"ta": "{name} ஸ்டாக்கில் இல்லை.", "en": "{name} is out of stock.", "hi": "{name} स्टॉक में नहीं है।"},
    "cart_short": {"ta": "{name} {n} மட்டுமே உள்ளன.", "en": "Only {n} of {name} left.", "hi": "{name} सिर्फ़ {n} बचे हैं।"},
    "contact": {
        "ta": "{store} குழுவை {email} என்ற முகவரியில் தொடர்பு கொள்ளலாம் ({hours}).",
        "en": "You can reach the {store} team at {email} ({hours}).",
        "hi": "आप {store} टीम से {email} पर संपर्क कर सकते हैं ({hours})।",
    },
    "help": {
        "ta": "{store} பொருட்கள், ஸ்டாக், ஆர்டர் மற்றும் டெலிவரி, ரிட்டர்ன், ரீஃபண்ட், பணம், உங்கள் கணக்கு பற்றி நான் உதவ முடியும். உங்களுக்கு என்ன வேண்டும் என்று இன்னும் கொஞ்சம் சொல்ல முடியுமா?",
        "en": "I can help with {store} products and stock, orders and delivery, returns and refunds, payments and your account. Could you tell me a bit more about what you need?",
        "hi": "आप मुझसे {store} के प्रोडक्ट और स्टॉक, ऑर्डर और डिलीवरी, रिटर्न और रिफ़ंड, भुगतान और अपने अकाउंट के बारे में पूछ सकते हैं। क्या आप थोड़ा और बता सकते हैं कि आपको क्या चाहिए?",
    },
    "clarify": {
        "ta": "மன்னிக்கவும், நீங்கள் எந்த மொழியில் பேசினீர்கள் என்று உறுதியாகத் தெரியவில்லை. தமிழ், ஆங்கிலம் அல்லது இந்தியில் மீண்டும் சொல்ல முடியுமா?",
        "en": "Sorry, I couldn't tell which language that was. Could you say it again in Tamil, English or Hindi?",
        "hi": "माफ़ कीजिए, यह साफ़ नहीं हुआ कि आपने किस भाषा में बात की। क्या आप तमिल, अंग्रेज़ी या हिंदी में फिर से कह सकते हैं?",
    },
}

STATUS: dict[str, dict[str, str]] = {
    "ta": {"pending_payment": "பணம் செலுத்தக் காத்திருக்கிறது", "processing": "தயாராகிக் கொண்டிருக்கிறது", "shipped": "அனுப்பப்பட்டுவிட்டது",
           "out_for_delivery": "டெலிவரிக்காக வெளியே சென்றுள்ளது", "delivered": "டெலிவரி செய்யப்பட்டுவிட்டது", "cancelled": "ரத்து செய்யப்பட்டது",
           "returned": "திருப்பி அனுப்பப்பட்டு பணம் திருப்பித் தரப்பட்டது"},
    "hi": {"pending_payment": "भुगतान की प्रतीक्षा में है", "processing": "तैयार किया जा रहा है", "shipped": "भेज दिया गया है",
           "out_for_delivery": "डिलीवरी के लिए निकल चुका है", "delivered": "डिलीवर हो चुका है", "cancelled": "रद्द कर दिया गया है",
           "returned": "लौटाया जा चुका है और रिफ़ंड हो गया है"},
}

CATEGORIES: dict[str, dict[str, str]] = {
    "ta": {"Tents": "கூடாரங்கள்", "Sleeping": "தூக்கப் பொருட்கள்", "Packs": "பைகள்", "Footwear": "காலணிகள்", "Apparel": "ஆடைகள்",
           "Cooking": "சமையல்", "Lighting": "விளக்குகள்", "Coffee": "காபி", "Tea": "தேநீர்", "Equipment": "உபகரணங்கள்",
           "Brewers": "ப்ரூவர்கள்", "Kitchen": "சமையலறை", "Pantry": "சரக்கறை"},
    "hi": {"Tents": "टेंट", "Sleeping": "स्लीपिंग", "Packs": "बैग", "Footwear": "जूते", "Apparel": "कपड़े", "Cooking": "कुकिंग",
           "Lighting": "लाइटिंग", "Coffee": "कॉफ़ी", "Tea": "चाय", "Equipment": "उपकरण", "Brewers": "ब्रूअर", "Kitchen": "किचन", "Pantry": "पैंट्री"},
}


# Customer-care templates (deliveries, payments, refunds, returns, accounts, checkout, escalation, actions).
from .care_text import CARE as _CARE  # noqa: E402

T.update(_CARE)


def t(lang: str, key: str, **values) -> str:
    return T[key].get(lang, T[key]["en"]).format(**values)


def status_label(lang: str, status: str, english: str) -> str:
    return STATUS.get(lang, {}).get(status, english)


def category(lang: str, name: str) -> str:
    return CATEGORIES.get(lang, {}).get(name, name)


def end(lang: str) -> str:
    return "।" if lang == "hi" else "."
