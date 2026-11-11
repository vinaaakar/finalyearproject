"""Customer-care reply templates (Tamil, English, Hindi), merged into i18n.T.

Like the rest of i18n, only the surrounding words are translated: product names, prices, order numbers,
dates, carriers, tracking numbers and e-mail addresses are inserted unchanged. Nothing here claims that an
action happened; actions are confirmed separately, by the API, after the customer taps a button.
"""

from __future__ import annotations

CARE: dict[str, dict[str, str]] = {
    # ---- India store (selling in ₹): prices from the approved list only; never converted ----------------------------
    "price_not_set": {
        "ta": "₹ விலை இன்னும் அமைக்கப்படவில்லை",
        "en": "price in ₹ not set yet",
        "hi": "₹ में कीमत अभी तय नहीं",
    },
    "cart_contents_in": {
        "ta": "உங்கள் கார்ட்டில்: {lines}. துணைத் தொகை {subtotal}; டெலிவரி கட்டணம் செக்அவுட்டில் உங்கள் முகவரியைப் பொறுத்து சேர்க்கப்படும்.",
        "en": "Your cart has {lines}. Subtotal {subtotal}; delivery is added at checkout, based on your address.",
        "hi": "आपके कार्ट में: {lines}। सबटोटल {subtotal}; डिलीवरी शुल्क चेकआउट पर आपके पते के आधार पर जोड़ा जाएगा।",
    },
    "cart_unpriced": {
        "ta": "உங்கள் கார்ட்டில்: {lines}. இவற்றுக்கு ₹ விலை இன்னும் அமைக்கப்படவில்லை, எனவே செக்அவுட் செய்ய இயலாது: {names}.",
        "en": "Your cart has {lines}. These items don't have a price in ₹ set yet, so the cart can't be checked out: {names}.",
        "hi": "आपके कार्ट में: {lines}। इनकी ₹ में कीमत अभी तय नहीं है, इसलिए चेकआउट नहीं हो सकता: {names}।",
    },
    "checkout_steps_in": {
        "ta": "செக்அவுட் செய்ய: உங்கள் கார்ட்டைத் திறந்து Checkout-ஐத் தேர்ந்தெடுங்கள், உள்நுழையுங்கள் அல்லது கணக்கு உருவாக்குங்கள் (கார்ட் அப்படியே இருக்கும்), இந்திய டெலிவரி முகவரியை உள்ளிடுங்கள் (மாநிலம் அல்லது யூனியன் பிரதேசம், 6 இலக்க PIN குறியீடு, +91 மொபைல் எண்), ஆர்டரைச் சரிபார்த்து வையுங்கள், பிறகு சோதனைப் பணத்தை முடியுங்கள். பணம் சரிபார்க்கப்பட்ட பிறகே ஆர்டர் உறுதியாகும்.",
        "en": "To check out: open your cart, select Checkout, sign in or create an account (your cart is kept), enter an Indian delivery address (state or union territory, 6-digit PIN code and a +91 mobile number), review and place the order, then complete the test payment. An order is confirmed only after the payment is verified.",
        "hi": "चेकआउट के लिए: अपना कार्ट खोलें, Checkout चुनें, साइन इन करें या अकाउंट बनाएँ (कार्ट बना रहेगा), भारत का डिलीवरी पता डालें (राज्य या केंद्र शासित प्रदेश, 6 अंकों का PIN कोड और +91 मोबाइल नंबर), ऑर्डर देखकर दें, फिर टेस्ट भुगतान पूरा करें। भुगतान की जाँच के बाद ही ऑर्डर पक्का होता है।",
    },
    "checkout_errors_in": {
        "ta": " பொதுவான செய்திகள்: PIN குறியீடு சரியாக 6 இலக்கமாக இருக்க வேண்டும்; மொபைல் எண் 10 இலக்க இந்திய எண்ணாக (+91) இருக்க வேண்டும்; “total changed” என்றால் விலை அல்லது ஸ்டாக் மாறியுள்ளது — ஆர்டரை மீண்டும் சரிபார்த்து முயற்சியுங்கள்.",
        "en": " Common messages: a PIN code needs exactly 6 digits; the mobile number must be a 10-digit Indian number (+91); “the total changed” means a price or stock level changed — review the order and try again.",
        "hi": " आम संदेश: PIN कोड ठीक 6 अंकों का होना चाहिए; मोबाइल नंबर 10 अंकों का भारतीय नंबर (+91) होना चाहिए; “total changed” का मतलब है कीमत या स्टॉक बदल गया — ऑर्डर दोबारा देखकर फिर कोशिश करें।",
    },
    # ---- orders & delivery ---------------------------------------------------------------------
    "late_on_track": {
        "ta": "ஆர்டர் {number} இன்னும் சரியான நேரத்தில் உள்ளது — {date}-க்குள் வந்து சேரும் என எதிர்பார்க்கப்படுகிறது.",
        "en": "Order {number} is still on track — it's expected by {date}.",
        "hi": "ऑर्डर {number} अभी समय पर है — {date} तक पहुँचने की उम्मीद है।",
    },
    "late_overdue": {
        "ta": "ஆர்டர் {number} {date}-க்குள் வர வேண்டியது, அந்தத் தேதி கடந்துவிட்டது.",
        "en": "Order {number} was expected by {date}, and that date has passed.",
        "hi": "ऑर्डर {number} {date} तक पहुँचना था, और वह तारीख निकल चुकी है।",
    },
    "late_carrier": {
        "ta": " {carrier}-இல் டிராக்கிங் எண் {tracking} மூலம் நிலையைப் பார்க்கலாம்.",
        "en": " You can follow it with {carrier} using tracking number {tracking}.",
        "hi": " आप {carrier} पर ट्रैकिंग नंबर {tracking} से इसे देख सकते हैं।",
    },
    "late_processing": {
        "ta": "ஆர்டர் {number} இன்னும் தயாராகிக் கொண்டிருக்கிறது, இன்னும் அனுப்பப்படவில்லை.",
        "en": "Order {number} is still being prepared and hasn't shipped yet.",
        "hi": "ऑर्डर {number} अभी तैयार किया जा रहा है और अभी भेजा नहीं गया है।",
    },
    "late_unpaid": {
        "ta": "ஆர்டர் {number} இன்னும் பணம் செலுத்தப்படாததால் அனுப்பப்படவில்லை.",
        "en": "Order {number} hasn't shipped because it's still waiting for payment.",
        "hi": "ऑर्डर {number} अभी भेजा नहीं गया क्योंकि उसका भुगतान बाकी है।",
    },
    "late_next": {
        "ta": " எதிர்பார்த்த தேதிக்குப் பிறகும் வரவில்லை என்றால், உங்கள் ஆர்டர் எண்ணுடன் {email}-ஐத் தொடர்பு கொள்ளுங்கள்; குழு அதைச் சரிபார்க்கும்.",
        "en": " If it still hasn't arrived after the expected date, email {email} with your order number so the team can look into it.",
        "hi": " अगर उम्मीद की तारीख के बाद भी न पहुँचे, तो अपने ऑर्डर नंबर के साथ {email} पर लिखें ताकि टीम इसकी जाँच कर सके।",
    },
    "delivered_missing": {
        "ta": "ஆர்டர் {number} டெலிவரி செய்யப்பட்டதாகக் குறிக்கப்பட்டுள்ளது{on}. கதவருகில், அக்கம்பக்கத்தினரிடம் அல்லது கட்டட வரவேற்பில் பாருங்கள்; டெலிவரி அறிவிப்பு இருக்கிறதா என்றும் பாருங்கள். இன்னும் கிடைக்கவில்லை என்றால், ஆர்டர் எண்ணுடன் {email}-ஐத் தொடர்பு கொள்ளுங்கள். அரட்டையிலிருந்து நான் விசாரணையைத் தொடங்க முடியாது.",
        "en": "Order {number} is marked as delivered{on}. Please check around your door, with neighbours or building reception, and look for a delivery notice. If you still can't find it, email {email} with your order number so the team can look into it — I can't open an investigation from the chat.",
        "hi": "ऑर्डर {number} डिलीवर दिखाया गया है{on}। कृपया दरवाज़े के आसपास, पड़ोसियों या बिल्डिंग रिसेप्शन पर देखें, और डिलीवरी नोटिस देखें। फिर भी न मिले तो ऑर्डर नंबर के साथ {email} पर लिखें ताकि टीम जाँच कर सके — मैं चैट से जाँच शुरू नहीं कर सकता।",
    },
    "on_date": {"ta": " ({date} அன்று)", "en": " on {date}", "hi": " ({date} को)"},
    "damaged_steps": {
        "ta": "சேதமடைந்து வந்ததற்கு வருந்துகிறோம். பொருளையும் பேக்கிங்கையும் வைத்திருங்கள், சில புகைப்படங்கள் எடுங்கள், பிறகு ஆர்டர் எண், சிறு விளக்கம், புகைப்படங்களுடன் {email}-க்கு மின்னஞ்சல் அனுப்புங்கள். அரட்டையிலிருந்து நான் புகாரைப் பதிவு செய்ய முடியாது; குழு அதைப் பரிசீலிக்கும்.",
        "en": "I'm sorry it arrived damaged. Please keep the item and its packaging, take a few photos, and email {email} with your order number, a short description and the photos. I can't register a claim from the chat, so the team will review it from your email.",
        "hi": "माफ़ कीजिए कि सामान टूटा हुआ पहुँचा। कृपया सामान और पैकिंग संभालकर रखें, कुछ फ़ोटो लें, और ऑर्डर नंबर, छोटा विवरण और फ़ोटो के साथ {email} पर ईमेल करें। मैं चैट से शिकायत दर्ज नहीं कर सकता, इसलिए टीम आपके ईमेल से इसे देखेगी।",
    },
    "defective_steps": {
        "ta": "அது சரியாக வேலை செய்யாததற்கு வருந்துகிறோம். ஆர்டர் எண், என்ன பிரச்சினை என்பது, முடிந்தால் புகைப்படம் அல்லது சிறு வீடியோவுடன் {email}-க்கு எழுதுங்கள். அரட்டையிலிருந்து நான் உத்தரவாதக் கோரிக்கையைப் பதிவு செய்ய முடியாது.",
        "en": "I'm sorry it isn't working properly. Email {email} with your order number, what's wrong, and a photo or short video if you can. I can't register a warranty claim from the chat.",
        "hi": "माफ़ कीजिए कि यह ठीक से काम नहीं कर रहा। अपने ऑर्डर नंबर, समस्या के विवरण और हो सके तो फ़ोटो या छोटे वीडियो के साथ {email} पर लिखें। मैं चैट से वारंटी क्लेम दर्ज नहीं कर सकता।",
    },
    "wrong_item_steps": {
        "ta": "குழப்பத்திற்கு வருந்துகிறோம். அந்தப் பொருளைப் பயன்படுத்த வேண்டாம்; ஆர்டர் எண், நீங்கள் ஆர்டர் செய்தது, வந்தது (ஒரு புகைப்படம் உதவும்) ஆகியவற்றுடன் {email}-க்கு எழுதுங்கள்.",
        "en": "Sorry about the mix-up. Please don't use the item; email {email} with your order number, what you ordered and what arrived (a photo helps).",
        "hi": "इस गड़बड़ी के लिए माफ़ कीजिए। कृपया सामान इस्तेमाल न करें; ऑर्डर नंबर, आपने क्या मँगाया था और क्या आया (फ़ोटो से मदद मिलेगी) लिखकर {email} पर भेजें।",
    },
    "missing_item_steps": {
        "ta": "ஒரு பொருள் குறைவாக வந்ததற்கு வருந்துகிறோம். ஒரு ஆர்டர் பல பார்சல்களில் வருகிறதா என்று என்னால் பார்க்க முடியாது, எனவே ஆர்டர் எண்ணும் எந்தப் பொருள் வரவில்லை என்பதும் சேர்த்து {email}-க்கு எழுதுங்கள்.",
        "en": "Sorry an item is missing. I can't see individual packages for an order, so please email {email} with your order number and which item didn't arrive.",
        "hi": "माफ़ कीजिए कि एक सामान कम आया। मैं किसी ऑर्डर के अलग-अलग पैकेट नहीं देख सकता, इसलिए ऑर्डर नंबर और कौन-सा सामान नहीं आया, यह लिखकर {email} पर भेजें।",
    },
    # ---- cancellations & changes ---------------------------------------------------------------
    "cancel_ok": {
        "ta": "ஆர்டர் {number} இன்னும் பணம் செலுத்தப்படாததால் ரத்து செய்யலாம். உறுதிப்படுத்த கீழே உள்ள “{button}” பொத்தானைத் தட்டுங்கள் — நீங்கள் உறுதிப்படுத்தி, ஸ்டோர் ஒப்புக்கொள்ளும் வரை அது ரத்தாகாது.",
        "en": "Order {number} hasn't been paid yet, so it can be cancelled. Tap “{button}” below to confirm — it isn't cancelled until you confirm and the store confirms it.",
        "hi": "ऑर्डर {number} का अभी भुगतान नहीं हुआ है, इसलिए इसे रद्द किया जा सकता है। पुष्टि के लिए नीचे “{button}” दबाएँ — जब तक आप पुष्टि न करें और स्टोर पुष्टि न करे, यह रद्द नहीं होगा।",
    },
    "cancel_paid": {
        "ta": "ஆர்டர் {number} ஏற்கனவே பணம் செலுத்தப்பட்டு {status}, எனவே இங்கே ரத்து செய்ய முடியாது. அனுப்பப்படும் முன் குழு உதவ முடியுமா என்று பார்க்க உடனே {email}-ஐத் தொடர்பு கொள்ளுங்கள்.",
        "en": "Order {number} is already paid and {status}, so I can't cancel it here. Email {email} as soon as possible to ask whether it can still be stopped before it ships.",
        "hi": "ऑर्डर {number} का भुगतान हो चुका है और यह {status}, इसलिए मैं इसे यहाँ रद्द नहीं कर सकता। भेजे जाने से पहले रोका जा सकता है या नहीं, यह पूछने के लिए तुरंत {email} पर लिखें।",
    },
    "cancel_shipped": {
        "ta": "ஆர்டர் {number} ஏற்கனவே {status}, எனவே இனி ரத்து செய்ய முடியாது. வந்ததும் ரிட்டர்ன் கொள்கைப்படி திருப்பி அனுப்பலாம்.",
        "en": "Order {number} is already {status}, so it can no longer be cancelled. Once it arrives, you can return it under the returns policy.",
        "hi": "ऑर्डर {number} {status}, इसलिए अब इसे रद्द नहीं किया जा सकता। पहुँचने के बाद आप रिटर्न पॉलिसी के अनुसार इसे लौटा सकते हैं।",
    },
    "cancel_closed": {
        "ta": "ஆர்டர் {number} ஏற்கனவே {status}.",
        "en": "Order {number} is already {status}.",
        "hi": "ऑर्डर {number} पहले ही {status}।",
    },
    "cancel_which": {
        "ta": "எந்த ஆர்டரை ரத்து செய்ய வேண்டும்? இன்னும் ரத்து செய்யக்கூடிய பணம் செலுத்தாத ஆர்டர்கள்: {list}.",
        "en": "Which order would you like to cancel? Unpaid orders that can still be cancelled: {list}.",
        "hi": "आप कौन-सा ऑर्डर रद्द करना चाहते हैं? बिना भुगतान वाले ऑर्डर जो अभी रद्द हो सकते हैं: {list}।",
    },
    "cancel_none": {
        "ta": "உங்கள் சமீபத்திய ஆர்டர்கள் எதையும் இங்கே ரத்து செய்ய முடியாது ({list}). பணம் செலுத்தாத ஆர்டர்களை மட்டுமே ஆன்லைனில் ரத்து செய்யலாம்; மற்றவற்றுக்கு {email}-ஐத் தொடர்பு கொள்ளுங்கள்.",
        "en": "None of your recent orders can be cancelled here ({list}). Only unpaid orders can be cancelled online; for anything else, please email {email}.",
        "hi": "आपके हाल के किसी भी ऑर्डर को यहाँ रद्द नहीं किया जा सकता ({list})। सिर्फ़ बिना भुगतान वाले ऑर्डर ऑनलाइन रद्द होते हैं; बाकी के लिए {email} पर लिखें।",
    },
    "cancel_login": {
        "ta": "உங்கள் ஆர்டரை இன்னும் ரத்து செய்ய முடியுமா என்று பார்க்க உள்நுழையுங்கள். பணம் செலுத்தாத ஆர்டர்களை ஆன்லைனில் ரத்து செய்யலாம்; பணம் செலுத்திய ஆர்டர்களுக்கு ஆதரவுக் குழு தேவை.",
        "en": "Please sign in so I can check whether your order can still be cancelled. Unpaid orders can be cancelled online; paid orders need the support team.",
        "hi": "कृपया साइन इन करें ताकि मैं देख सकूँ कि आपका ऑर्डर अभी रद्द हो सकता है या नहीं। बिना भुगतान वाले ऑर्डर ऑनलाइन रद्द होते हैं; भुगतान हो चुके ऑर्डर के लिए सपोर्ट टीम चाहिए।",
    },
    "modify_no": {
        "ta": "ஆர்டர் செய்த பிறகு அதை மாற்ற முடியாது — இந்த ஸ்டோரின் அமைப்பில் பொருட்களையோ டெலிவரி முகவரியையோ திருத்தும் வசதி இல்லை.",
        "en": "Orders can't be changed once they're placed — this store's system doesn't support editing the items or the delivery address.",
        "hi": "ऑर्डर देने के बाद उसे बदला नहीं जा सकता — इस स्टोर के सिस्टम में सामान या डिलीवरी पता बदलने की सुविधा नहीं है।",
    },
    "modify_unpaid": {
        "ta": " ஆர்டர் {number} இன்னும் பணம் செலுத்தப்படவில்லை: அதை ரத்து செய்து சரியான விவரங்களுடன் புதிய ஆர்டர் செய்யலாம்.",
        "en": " Order {number} isn't paid yet: you can cancel it and place a new order with the right details.",
        "hi": " ऑर्डर {number} का अभी भुगतान नहीं हुआ है: आप इसे रद्द करके सही जानकारी के साथ नया ऑर्डर दे सकते हैं।",
    },
    "modify_paid": {
        "ta": " ஆர்டர் {number} {status}; இன்னும் மாற்ற முடியுமா என்று கேட்க சரியான விவரங்களுடன் உடனே {email}-க்கு எழுதுங்கள்.",
        "en": " Order {number} is {status}; email {email} right away with the correct details to ask whether it can still be changed.",
        "hi": " ऑर्डर {number} {status}; सही जानकारी के साथ तुरंत {email} पर लिखकर पूछें कि क्या इसे अभी बदला जा सकता है।",
    },
    "modify_shipped": {
        "ta": " ஆர்டர் {number} ஏற்கனவே {status}, எனவே இங்கிருந்து மாற்ற முடியாது. உதவிக்கு {email}-ஐத் தொடர்பு கொள்ளுங்கள்.",
        "en": " Order {number} is already {status}, so it can't be changed from here. Please email {email} for help.",
        "hi": " ऑर्डर {number} {status}, इसलिए इसे यहाँ से बदला नहीं जा सकता। मदद के लिए {email} पर लिखें।",
    },
    # ---- payments ------------------------------------------------------------------------------
    "pay_failed": {
        "ta": "ஆர்டர் {number}-க்கான கடைசி சோதனைப் பணம் நிராகரிக்கப்பட்டது, எனவே எதுவும் வசூலிக்கப்படவில்லை. பணம் செலுத்தும் பக்கத்தில் மீண்டும் முயற்சிக்கலாம்.",
        "en": "The last test payment for order {number} was declined, so nothing was charged. You can try again on the payment page.",
        "hi": "ऑर्डर {number} का आख़िरी टेस्ट भुगतान अस्वीकार हुआ, इसलिए कुछ भी नहीं कटा। आप भुगतान पेज पर फिर से कोशिश कर सकते हैं।",
    },
    "pay_pending": {
        "ta": "ஆர்டர் {number}-க்கான பணம் தொடங்கப்பட்டது, ஆனால் இன்னும் உறுதிப்படுத்தப்படவில்லை. பணம் செலுத்தும் பக்கத்தில் அதை முடியுங்கள் — பணம் வழங்குநர் உறுதிப்படுத்திய பிறகே ஆர்டர் முன்னேறும்.",
        "en": "A payment for order {number} was started but hasn't been confirmed yet. Please finish it on the payment page — the order only moves forward once the payment provider confirms it.",
        "hi": "ऑर्डर {number} का भुगतान शुरू हुआ था, पर अभी पुष्टि नहीं हुई है। कृपया इसे भुगतान पेज पर पूरा करें — भुगतान प्रदाता की पुष्टि के बाद ही ऑर्डर आगे बढ़ता है।",
    },
    "pay_none": {
        "ta": "ஆர்டர் {number} பணத்திற்காகக் காத்திருக்கிறது; இதுவரை எந்தப் பணமும் பதிவாகவில்லை.",
        "en": "Order {number} is waiting for payment, and no payment has been recorded yet.",
        "hi": "ऑर्डर {number} भुगतान की प्रतीक्षा में है, और अभी तक कोई भुगतान दर्ज नहीं हुआ है।",
    },
    "order_amount": {
        "ta": "ஆர்டர் {number}-இன் மொத்தத் தொகை {total}.",
        "en": "Order {number} came to {total} in total.",
        "hi": "ऑर्डर {number} की कुल राशि {total} है।",
    },
    "order_amount_paid": {
        "ta": " அதற்கு {amount} பணம் செலுத்தப்பட்டதாகப் பதிவாகியுள்ளது.",
        "en": " A payment of {amount} is recorded for it.",
        "hi": " इसके लिए {amount} का भुगतान दर्ज है।",
    },
    "order_amount_unpaid": {
        "ta": " அதற்கு இன்னும் பணம் செலுத்தப்படவில்லை.",
        "en": " It hasn't been paid yet.",
        "hi": " इसका भुगतान अभी नहीं हुआ है।",
    },
    "order_amount_no_record": {
        "ta": " அதற்கான பணம் செலுத்திய பதிவு எதுவும் சேமிக்கப்படவில்லை.",
        "en": " No payment record is stored for it.",
        "hi": " इसके भुगतान का कोई रिकॉर्ड सहेजा नहीं गया है।",
    },
    "pay_ok": {
        "ta": "ஆர்டர் {number}-க்கான பணம் ({amount}) உறுதிப்படுத்தப்பட்டது; ஆர்டர் {status}.",
        "en": "The payment for order {number} ({amount}) is confirmed, and the order is {status}.",
        "hi": "ऑर्डर {number} का भुगतान ({amount}) पक्का हो गया है, और ऑर्डर {status}।",
    },
    "pay_cancelled_paid": {
        "ta": "ஆர்டர் {number}-க்கு {amount} பணம் பதிவான பிறகு அது ரத்து செய்யப்பட்டது. இதற்கான ரீஃபண்ட் பதிவு எதுவும் எனக்குத் தெரியவில்லை; "
              "{email}-க்கு எழுதினால் ஆதரவுக் குழு சரிபார்த்து, உரிய ரீஃபண்டை ஏற்பாடு செய்யும். அரட்டையிலிருந்து என்னால் ரீஃபண்ட் வழங்க முடியாது.",
        "en": "Order {number} was cancelled after a payment of {amount} was recorded. I can't see a refund recorded for it; please email "
              "{email} so the support team can check and arrange any refund that's due. I can't issue refunds from the chat.",
        "hi": "ऑर्डर {number} {amount} का भुगतान दर्ज होने के बाद रद्द हुआ। इसका कोई रिफ़ंड रिकॉर्ड मुझे नहीं दिखता; कृपया {email} पर लिखें "
              "ताकि सपोर्ट टीम जाँच करके देय रिफ़ंड की व्यवस्था करे। मैं चैट से रिफ़ंड जारी नहीं कर सकता।",
    },
    "pay_all_settled": {
        "ta": "உங்கள் எந்த ஆர்டரும் பணத்திற்காகக் காத்திருக்கவில்லை.",
        "en": "None of your orders is waiting for payment.",
        "hi": "आपका कोई भी ऑर्डर भुगतान की प्रतीक्षा में नहीं है।",
    },
    "pay_no_orders": {
        "ta": "இந்த {store} கணக்கில் ஆர்டர்களோ பணப் பதிவுகளோ எதுவும் தெரியவில்லை.",
        "en": "I can't see any orders or payments on this {store} account.",
        "hi": "इस {store} अकाउंट में मुझे कोई ऑर्डर या भुगतान नहीं दिख रहा।",
    },
    "ticket_none": {
        "ta": "இந்த ஸ்டோரில் இன்னும் டிக்கெட் அமைப்பு இல்லை, எனவே என்னால் டிக்கெட் உருவாக்கவோ தேடவோ முடியாது. {store} குழு {email}-இல் உதவும் "
              "({hours}) — ஆர்டர் பற்றியது என்றால் ஆர்டர் எண்ணையும் சேர்க்கவும்.",
        "en": "There's no ticket system in this store yet, so I can't create or look up a ticket. The {store} team can help at {email} "
              "({hours}) — include your order number if it's about an order.",
        "hi": "इस स्टोर में अभी कोई टिकट सिस्टम नहीं है, इसलिए मैं टिकट न बना सकता हूँ, न ढूँढ सकता हूँ। {store} टीम {email} पर मदद कर सकती है "
              "({hours}) — अगर बात किसी ऑर्डर की है तो ऑर्डर नंबर भी लिखें।",
    },
    "budget_currency": {
        "ta": "எங்கள் விலைகள் {currency} ({code})-இல் உள்ளன, எனவே {asked} பட்ஜெட்டை என்னால் பயன்படுத்த முடியாது — நாணய மாற்று விகிதத்தை நான் ஊகிக்க மாட்டேன்.",
        "en": "Our prices are listed in {currency} ({code}), so I can't apply a {asked} budget — I won't guess an exchange rate.",
        "hi": "हमारी कीमतें {currency} ({code}) में हैं, इसलिए मैं {asked} का बजट लागू नहीं कर सकता — मैं विनिमय दर का अंदाज़ा नहीं लगाऊँगा।",
    },
    "pay_sandbox": {
        "ta": " இந்த ஸ்டோரில் பணம் சோதனை முறையில் மட்டுமே இயங்குகிறது: உண்மையான பணம் எதுவும் நகராது, கார்டு விவரங்கள் சேகரிக்கப்படுவதில்லை.",
        "en": " This store runs payments in test mode: no real money moves and no card details are collected.",
        "hi": " यह स्टोर भुगतान टेस्ट मोड में चलाता है: कोई असली पैसा नहीं कटता और कार्ड की जानकारी नहीं ली जाती।",
    },
    "pay_duplicate": {
        "ta": "இந்த அமைப்பில் ஒரு ஆர்டருக்கு ஒரே ஒரு வெற்றிகரமான பணம் மட்டுமே பதிவாக முடியும், எனவே அதே ஆர்டருக்கு இரண்டாவது கட்டணம் பதிவாகாது. உங்கள் வங்கி அறிக்கையில் இரண்டு உண்மையான கட்டணங்கள் தெரிந்தால், ஆர்டர் எண்ணும் தேதிகளும் சேர்த்து {email}-க்கு எழுதுங்கள் — அரட்டையிலிருந்து நான் கட்டணத்தைத் திருப்ப முடியாது.",
        "en": "In this system an order can have only one successful payment, so a second charge for the same order can't be recorded. If you see two real charges on your statement, email {email} with the order number and dates — I can't reverse charges from the chat.",
        "hi": "इस सिस्टम में एक ऑर्डर का सिर्फ़ एक सफल भुगतान दर्ज हो सकता है, इसलिए उसी ऑर्डर का दूसरा चार्ज दर्ज नहीं हो सकता। अगर आपके स्टेटमेंट में दो असली चार्ज दिखें, तो ऑर्डर नंबर और तारीखों के साथ {email} पर लिखें — मैं चैट से चार्ज वापस नहीं कर सकता।",
    },
    "pay_login": {
        "ta": "உங்கள் பணம் மற்றும் ஆர்டர் நிலையைப் பார்க்க உள்நுழையுங்கள். நான் ஒருபோதும் உங்கள் கார்டு எண், CVV அல்லது கடவுச்சொல்லைக் கேட்க மாட்டேன்.",
        "en": "Please sign in so I can check your payment and order status. I'll never ask for your card number, CVV or password.",
        "hi": "कृपया साइन इन करें ताकि मैं आपका भुगतान और ऑर्डर देख सकूँ। मैं कभी आपका कार्ड नंबर, CVV या पासवर्ड नहीं माँगूँगा।",
    },
    # ---- refunds, returns & exchanges ------------------------------------------------------------
    # A returned order does not prove a refund: there are no refund records (see truth.REFUND_STATES), so the
    # assistant must not say a refund was issued, how much, or when.
    "refund_returned": {
        "ta": "ஆர்டர் {number} திருப்பி அனுப்பப்பட்டதாகப் பதிவாகியுள்ளது. அதற்கான ரீஃபண்ட் பதிவு எதுவும் எனக்குத் தெரியவில்லை, எனவே ரீஃபண்ட் "
              "வழங்கப்பட்டதா, எவ்வளவு, எப்போது என்று என்னால் உறுதிப்படுத்த முடியாது. ஆர்டர் எண்ணுடன் {email}-க்கு எழுதினால் குழு சரிபார்க்கும்.",
        "en": "Order {number} is marked as returned. I can't see a refund record for it, so I can't confirm whether a refund has been "
              "issued, how much, or when. Please email {email} with your order number and the team can check.",
        "hi": "ऑर्डर {number} लौटाया गया दर्ज है। इसके लिए मुझे कोई रिफ़ंड रिकॉर्ड नहीं दिखता, इसलिए मैं पक्का नहीं कह सकता कि रिफ़ंड "
              "जारी हुआ या नहीं, कितना या कब। ऑर्डर नंबर के साथ {email} पर लिखें, टीम जाँच करेगी।",
    },
    "refund_none": {
        "ta": "உங்கள் ஆர்டர்களில் எந்த ரீஃபண்டும் பதிவாகியிருப்பதாகத் தெரியவில்லை. ஒரு பொருளைத் திருப்பி அனுப்பியும் பணம் வரவில்லை என்றால், ஆர்டர் எண்ணுடன் {email}-ஐத் தொடர்பு கொள்ளுங்கள் — அரட்டையிலிருந்து நான் ரீஃபண்டை வழங்கவோ விரைவுபடுத்தவோ முடியாது.",
        "en": "I can't see a refund recorded on your orders. If you've sent an item back and haven't been refunded, please email {email} with your order number — I can't issue or speed up refunds from the chat.",
        "hi": "आपके ऑर्डर में मुझे कोई रिफ़ंड दर्ज नहीं दिख रहा। अगर आपने सामान लौटाया है और रिफ़ंड नहीं मिला, तो ऑर्डर नंबर के साथ {email} पर लिखें — मैं चैट से रिफ़ंड जारी या तेज़ नहीं कर सकता।",
    },
    "refund_login": {
        "ta": "உங்கள் ஆர்டர்களைப் பார்க்க உள்நுழையுங்கள்.",
        "en": "Please sign in so I can check your orders.",
        "hi": "कृपया साइन इन करें ताकि मैं आपके ऑर्डर देख सकूँ।",
    },
    "return_how": {
        "ta": " ரிட்டர்னைத் தொடங்க, ஆர்டர் எண்ணும் பொருட்களும் சேர்த்து {email}-க்கு எழுதுங்கள் — இந்த அரட்டையிலோ இணையதளத்திலோ இன்னும் ரிட்டர்னைத் தொடங்க முடியாது.",
        "en": " To start a return, email {email} with your order number and the item(s) — returns can't be started from this chat or the website yet.",
        "hi": " रिटर्न शुरू करने के लिए ऑर्डर नंबर और सामान की जानकारी के साथ {email} पर लिखें — अभी इस चैट या वेबसाइट से रिटर्न शुरू नहीं हो सकता।",
    },
    "return_eligible": {
        "ta": " ஆர்டர் {number} {date} அன்று டெலிவரி செய்யப்பட்டது; {days}-நாள் கொள்கைப்படி {until} வரை பயன்படுத்தாத பொருட்களைத் திருப்பி அனுப்பலாம்.",
        "en": " Order {number} was delivered on {date}; under the {days}-day policy you can return unused items until {until}.",
        "hi": " ऑर्डर {number} {date} को डिलीवर हुआ था; {days} दिन की पॉलिसी के अनुसार आप बिना इस्तेमाल किया सामान {until} तक लौटा सकते हैं।",
    },
    "return_expired": {
        "ta": " ஆர்டர் {number} {date} அன்று டெலிவரி செய்யப்பட்டது, இது {days}-நாள் ரிட்டர்ன் காலத்திற்கு வெளியே ({until} அன்று முடிந்தது). குறைபாடு இருந்தால் உத்தரவாதம் பொருந்தலாம்.",
        "en": " Order {number} was delivered on {date}, which is outside the {days}-day return window (it ended on {until}). If there's a defect, the warranty may still apply.",
        "hi": " ऑर्डर {number} {date} को डिलीवर हुआ था, जो {days} दिन की रिटर्न अवधि से बाहर है ({until} को खत्म हुई)। अगर कोई ख़राबी है, तो वारंटी लागू हो सकती है।",
    },
    "return_not_delivered": {
        "ta": " ஆர்டர் {number} இன்னும் டெலிவரி செய்யப்படவில்லை ({status}); டெலிவரிக்குப் பிறகே ரிட்டர்ன் செய்யலாம்.",
        "en": " Order {number} hasn't been delivered yet ({status}); returns start after delivery.",
        "hi": " ऑर्डर {number} अभी डिलीवर नहीं हुआ है ({status}); रिटर्न डिलीवरी के बाद ही होता है।",
    },
    "return_which": {
        "ta": " எந்த ஆர்டர்? சமீபத்தில் டெலிவரி ஆனவை: {list}.",
        "en": " Which order is it? Recently delivered: {list}.",
        "hi": " कौन-सा ऑर्डर है? हाल में डिलीवर हुए: {list}।",
    },
    "exchange_steps": {
        "ta": " பரிமாற்றங்களை ஆதரவுக் குழு கையாளும்: ஆர்டர் எண்ணும் உங்களுக்கு என்ன வேண்டும் என்பதும் சேர்த்து {email}-க்கு எழுதுங்கள். ரிட்டர்ன் கொள்கைப்படி பொருளைத் திருப்பி அனுப்பி, வேண்டியதை புதிதாக ஆர்டர் செய்யவும் முடியும்.",
        "en": " Exchanges are handled by the support team: email {email} with your order number and what you'd like instead. You can also return the item under the returns policy and order the one you want.",
        "hi": " एक्सचेंज सपोर्ट टीम करती है: ऑर्डर नंबर और आपको बदले में क्या चाहिए, लिखकर {email} पर भेजें। आप रिटर्न पॉलिसी के अनुसार सामान लौटाकर मनचाहा सामान नया ऑर्डर भी कर सकते हैं।",
    },
    # ---- accounts ------------------------------------------------------------------------------
    "acct_signin": {
        "ta": "உள்நுழைய, “உள்நுழைக” பக்கத்தைத் திறந்து உங்கள் {store} கணக்கின் மின்னஞ்சல், கடவுச்சொல்லைப் பயன்படுத்துங்கள் — ஒவ்வொரு ஸ்டோருக்கும் தனிக் கணக்கு. முடியவில்லை என்றால் மின்னஞ்சலையும் Caps Lock-ஐயும் சரிபாருங்கள், அல்லது கடவுச்சொல்லை மீட்டமையுங்கள்.",
        "en": "To sign in, open Sign in and use the email and password for your {store} account — each store has its own accounts. If it fails, check the email address and Caps Lock, or reset your password.",
        "hi": "साइन इन करने के लिए “साइन इन” खोलें और अपने {store} अकाउंट का ईमेल और पासवर्ड डालें — हर स्टोर के अकाउंट अलग होते हैं। न हो पाए तो ईमेल पता और Caps Lock जाँचें, या पासवर्ड रीसेट करें।",
    },
    "acct_register": {
        "ta": "கணக்கு உருவாக்க “கணக்கு உருவாக்கு” பக்கத்தில் உங்கள் பெயர், மின்னஞ்சல், குறைந்தது 10 எழுத்துகள் கொண்ட கடவுச்சொல்லை உள்ளிடுங்கள். உங்கள் கார்ட்டில் உள்ளவை அப்படியே இருக்கும்.",
        "en": "To create an account, open Create an account and enter your name, email and a password of at least 10 characters. Anything already in your cart is kept.",
        "hi": "अकाउंट बनाने के लिए “अकाउंट बनाएँ” खोलें और अपना नाम, ईमेल और कम से कम 10 अक्षरों का पासवर्ड डालें। आपके कार्ट का सामान बना रहेगा।",
    },
    "acct_password": {
        "ta": "உள்நுழையும் பக்கத்தில் “கடவுச்சொல் மறந்துவிட்டதா?” என்பதைப் பயன்படுத்தி உங்கள் மின்னஞ்சலை உள்ளிடுங்கள்; ஒருமுறை மட்டும் வேலை செய்யும், சிறிது நேரத்தில் காலாவதியாகும் இணைப்பு கிடைக்கும். இந்த டெமோ ஸ்டோரில் மின்னஞ்சல்கள் உண்மையில் அனுப்பப்படுவதில்லை. நான் ஒருபோதும் உங்கள் கடவுச்சொல்லைக் கேட்க மாட்டேன்.",
        "en": "Use Forgot password? on the sign-in page and enter your email; you'll get a reset link that works once and expires after a short time. In this demo store, reset emails aren't actually sent. I'll never ask for your password.",
        "hi": "साइन-इन पेज पर “पासवर्ड भूल गए?” से अपना ईमेल डालें; आपको एक रीसेट लिंक मिलेगा जो एक बार चलता है और थोड़ी देर में समाप्त हो जाता है। इस डेमो स्टोर में ईमेल सच में नहीं भेजे जाते। मैं कभी आपका पासवर्ड नहीं माँगूँगा।",
    },
    "acct_update": {
        "ta": "இந்த ஸ்டோரில் பெயர் அல்லது மின்னஞ்சலை ஆன்லைனில் மாற்றும் வசதி இன்னும் இல்லை. {email}-ஐத் தொடர்பு கொள்ளுங்கள்.",
        "en": "This store doesn't support changing your name or email online yet. Please email {email}.",
        "hi": "इस स्टोर में अभी ऑनलाइन नाम या ईमेल बदलने की सुविधा नहीं है। कृपया {email} पर लिखें।",
    },
    "acct_delete": {
        "ta": "கணக்கை நீக்கும் வசதி ஆன்லைனில் இல்லை. உங்கள் கணக்கையும் தரவையும் நீக்கக் கோர {email}-ஐத் தொடர்பு கொள்ளுங்கள்.",
        "en": "Account deletion isn't available online. To ask for your account and data to be deleted, email {email}.",
        "hi": "अकाउंट डिलीट करने की सुविधा ऑनलाइन नहीं है। अपना अकाउंट और डेटा हटवाने के लिए {email} पर लिखें।",
    },
    "acct_history": {
        "ta": "உள்நுழைந்த பிறகு உங்கள் ஆர்டர்கள் “என் ஆர்டர்கள்” பக்கத்தில் இருக்கும்.",
        "en": "Your orders are listed on the My orders page once you're signed in.",
        "hi": "साइन इन करने के बाद आपके ऑर्डर “मेरे ऑर्डर” पेज पर दिखते हैं।",
    },
    # ---- checkout & cart -----------------------------------------------------------------------
    "checkout_steps": {
        "ta": "செக்அவுட் செய்ய: உங்கள் கார்ட்டைத் திறந்து Checkout-ஐத் தேர்ந்தெடுங்கள், உள்நுழையுங்கள் அல்லது கணக்கு உருவாக்குங்கள் (கார்ட் அப்படியே இருக்கும்), அமெரிக்க டெலிவரி முகவரியை உள்ளிடுங்கள், ஆர்டரைச் சரிபார்த்து வையுங்கள், பிறகு சோதனைப் பணத்தை முடியுங்கள். பணம் சரிபார்க்கப்பட்ட பிறகே ஆர்டர் உறுதியாகும்.",
        "en": "To check out: open your cart, select Checkout, sign in or create an account (your cart is kept), enter a US delivery address, review and place the order, then complete the test payment. An order is confirmed only after the payment is verified.",
        "hi": "चेकआउट के लिए: अपना कार्ट खोलें, Checkout चुनें, साइन इन करें या अकाउंट बनाएँ (कार्ट बना रहेगा), अमेरिका का डिलीवरी पता डालें, ऑर्डर देखकर दें, फिर टेस्ट भुगतान पूरा करें। भुगतान की जाँच के बाद ही ऑर्डर पक्का होता है।",
    },
    "checkout_guest": {
        "ta": " செக்அவுட்டுக்குக் கணக்கு தேவை — விருந்தினர் செக்அவுட் இல்லை. ஆனால் உள்நுழையாமலே பொருட்களைக் கார்ட்டில் சேர்க்கலாம்; உள்நுழையும்போது அவை அப்படியே இருக்கும்.",
        "en": " Checkout needs an account — there's no guest checkout. You can still fill your cart as a guest, and it's kept when you sign in or register.",
        "hi": " चेकआउट के लिए अकाउंट ज़रूरी है — गेस्ट चेकआउट नहीं है। फिर भी आप बिना साइन इन के कार्ट भर सकते हैं, और साइन इन या रजिस्टर करने पर वह बना रहता है।",
    },
    "checkout_regions": {
        "ta": " {store} {regions} மாநிலங்களுக்கு அனுப்புவதில்லை.",
        "en": " {store} doesn't ship to {regions}.",
        "hi": " {store} {regions} में डिलीवरी नहीं करता।",
    },
    "checkout_errors": {
        "ta": " பொதுவான செய்திகள்: “does not ship to that state” என்றால் அந்த முகவரி டெலிவரி பகுதிக்கு வெளியே உள்ளது; ZIP குறியீடு 5 இலக்கமாக இருக்க வேண்டும்; “total changed” என்றால் விலை அல்லது ஸ்டாக் மாறியுள்ளது — ஆர்டரை மீண்டும் சரிபார்த்து முயற்சியுங்கள்.",
        "en": " Common messages: “does not ship to that state” means the address is outside the delivery area; a ZIP code needs 5 digits; “the total changed” means a price or stock level changed — review the order and try again.",
        "hi": " आम संदेश: “does not ship to that state” का मतलब है पता डिलीवरी क्षेत्र से बाहर है; ZIP कोड 5 अंकों का होना चाहिए; “total changed” का मतलब है कीमत या स्टॉक बदल गया — ऑर्डर दोबारा देखकर फिर कोशिश करें।",
    },
    "cart_limit": {
        "ta": " ஒவ்வொரு பொருளிலும் அதிகபட்சம் 10 வாங்கலாம், ஸ்டாக்கில் உள்ளதை விட அதிகமாக வாங்க முடியாது.",
        "en": " You can buy up to 10 of each item, and never more than we have in stock.",
        "hi": " आप हर सामान के ज़्यादा से ज़्यादा 10 खरीद सकते हैं, और स्टॉक से ज़्यादा नहीं।",
    },
    # ---- promotions, invoices, privacy, languages, accessibility, technical, bulk ----------------
    "promo_none": {
        "ta": "{store}-இல் தற்போது எந்த ஆஃபரோ தள்ளுபடிக் குறியீடோ அமைக்கப்படவில்லை, எனவே செக்அவுட்டில் குறியீட்டைப் பயன்படுத்த முடியாது. பொருள் பக்கங்களில் உள்ள விலைகளே தற்போதைய விலைகள்.",
        "en": "There are no promotions or discount codes set up for {store} right now, so a code can't be applied at checkout. The prices on the product pages are the current prices.",
        "hi": "{store} में अभी कोई ऑफ़र या डिस्काउंट कोड सेट नहीं है, इसलिए चेकआउट पर कोड लागू नहीं हो सकता। प्रोडक्ट पेज पर दिख रही कीमतें ही अभी की कीमतें हैं।",
    },
    "promo_free_ship": {
        "ta": " {threshold} மற்றும் அதற்கு மேற்பட்ட ஆர்டர்களுக்கு சாதாரண ஷிப்பிங் இலவசம்.",
        "en": " Standard shipping is free on orders from {threshold}.",
        "hi": " {threshold} या उससे ज़्यादा के ऑर्डर पर स्टैंडर्ड शिपिंग मुफ़्त है।",
    },
    "invoice_none": {
        "ta": "இந்த ஸ்டோரின் அமைப்பில் இன்வாய்ஸ்கள் இன்னும் கிடைக்கவில்லை. உங்கள் ஆர்டர் விவரங்கள் — பொருட்கள், துணைத் தொகை, ஷிப்பிங், மொத்தம் — “என் ஆர்டர்கள்” பக்கத்தில் உள்ளன.",
        "en": "Invoices aren't available in this store's system yet. Your order details — items, subtotal, shipping and total — are on the My orders page.",
        "hi": "इस स्टोर के सिस्टम में अभी इनवॉइस उपलब्ध नहीं हैं। आपके ऑर्डर का विवरण — सामान, सबटोटल, शिपिंग और कुल — “मेरे ऑर्डर” पेज पर है।",
    },
    "invoice_order": {
        "ta": " ஆர்டர் {number}: மொத்தம் {total}.",
        "en": " Order {number}: total {total}.",
        "hi": " ऑर्डर {number}: कुल {total}।",
    },
    "invoice_breakdown": {
        "ta": " ஆர்டர் {number}: துணைத் தொகை {subtotal}, ஷிப்பிங் {shipping}, மொத்தம் {total}.",
        "en": " Order {number}: subtotal {subtotal}, shipping {shipping}, total {total}.",
        "hi": " ऑर्डर {number}: सबटोटल {subtotal}, शिपिंग {shipping}, कुल {total}।",
    },
    "privacy": {
        "ta": "{store} உங்கள் கணக்கு (பெயர், மின்னஞ்சல்), ஆர்டர்கள், கார்ட் ஆகியவற்றைத் தன் சொந்த தரவுத்தளத்தில், மற்ற ஸ்டோரிலிருந்து தனியாக வைத்திருக்கிறது. உள்ளூர் பேச்சு இயந்திரம் இயங்கும்போது குரல் ஸ்டோரின் சொந்த சர்வரிலேயே எழுத்தாக்கப்படுகிறது, பதிவுகள் சேமிக்கப்படுவதில்லை. கார்டு விவரங்கள் சேகரிக்கப்படுவதில்லை. உங்கள் தரவின் நகல் அல்லது நீக்கத்திற்கு {email}-ஐத் தொடர்பு கொள்ளுங்கள்.",
        "en": "{store} keeps your account (name and email), orders and cart in its own database, separate from any other store. When the store's local speech engine is on, voice input is transcribed on the store's own server and recordings aren't kept. No card details are collected. For a copy of your data or to have it deleted, email {email}.",
        "hi": "{store} आपका अकाउंट (नाम, ईमेल), ऑर्डर और कार्ट अपने अलग डेटाबेस में रखता है, किसी दूसरे स्टोर से अलग। जब स्टोर का लोकल स्पीच इंजन चालू होता है, आवाज़ स्टोर के अपने सर्वर पर लिखी जाती है और रिकॉर्डिंग नहीं रखी जाती। कार्ड की जानकारी नहीं ली जाती। अपने डेटा की कॉपी या उसे हटवाने के लिए {email} पर लिखें।",
    },
    "languages": {
        "ta": "நான் தமிழ், ஆங்கிலம், இந்தி ஆகிய மொழிகளைப் புரிந்து அதே மொழியில் பதில் சொல்வேன். தட்டச்சு செய்யுங்கள் அல்லது பேசுங்கள் — ஒவ்வொரு செய்தியின் மொழியையும் நான் கண்டறிவதால், எப்போது வேண்டுமானாலும் மொழியை மாற்றலாம்.",
        "en": "I understand and reply in Tamil, English and Hindi. Just type or speak — I detect the language of each message, so you can switch at any time.",
        "hi": "मैं तमिल, अंग्रेज़ी और हिंदी समझता हूँ और उसी भाषा में जवाब देता हूँ। बस टाइप करें या बोलें — मैं हर संदेश की भाषा पहचानता हूँ, इसलिए आप कभी भी भाषा बदल सकते हैं।",
    },
    "accessibility": {
        "ta": "முழு ஸ்டோரையும் கீபோர்டால் பயன்படுத்தலாம் (நகர Tab, தேர்ந்தெடுக்க Enter); பக்கங்கள் ஸ்கிரீன் ரீடர்களுடன் வேலை செய்கின்றன. இந்த அரட்டையில் தட்டச்சுக்குப் பதில் பேசலாம் (🎤), “பதில்களை உரக்கப் படி” என்பதையும் இயக்கலாம். எழுத்தைப் பெரிதாக்க உங்கள் உலாவியின் zoom-ஐப் பயன்படுத்துங்கள் (Ctrl அல்லது Cmd மற்றும் +).",
        "en": "You can use the whole store with a keyboard (Tab to move, Enter to select), and the pages work with screen readers. In this chat you can speak instead of typing (🎤) and turn on “Read replies aloud”. To make text bigger, use your browser's zoom (Ctrl or Cmd and +).",
        "hi": "पूरा स्टोर कीबोर्ड से इस्तेमाल हो सकता है (आगे बढ़ने के लिए Tab, चुनने के लिए Enter), और पेज स्क्रीन रीडर के साथ काम करते हैं। इस चैट में आप टाइप करने के बजाय बोल सकते हैं (🎤) और “जवाब पढ़कर सुनाएँ” चालू कर सकते हैं। अक्षर बड़े करने के लिए ब्राउज़र ज़ूम इस्तेमाल करें (Ctrl या Cmd और +)।",
    },
    "tech_issue": {
        "ta": "சரியாக வேலை செய்யாததற்கு வருந்துகிறோம். இவற்றை முயற்சியுங்கள்: பக்கத்தைப் புதுப்பியுங்கள், இணைய இணைப்பைச் சரிபாருங்கள், வெளியேறி மீண்டும் உள்நுழையுங்கள், அல்லது வேறு உலாவியை முயற்சியுங்கள். ஒரு பொருளைச் சேர்க்க முடியவில்லை என்றால் அது ஸ்டாக்கில் இல்லாமல் இருக்கலாம் அல்லது 10 என்ற வரம்பை அடைந்திருக்கலாம். தொடர்ந்தால், நீங்கள் என்ன கிளிக் செய்தீர்கள், என்ன செய்தி வந்தது என்பதுடன் {email}-க்கு எழுதுங்கள்.",
        "en": "Sorry it isn't working. Please try: refreshing the page, checking your internet connection, signing out and back in, or another browser. If an item won't add, it may be out of stock or at the 10-per-item limit. If it keeps happening, email {email} with what you clicked and the exact message you saw.",
        "hi": "माफ़ कीजिए कि यह काम नहीं कर रहा। कृपया आज़माएँ: पेज रीफ़्रेश करें, इंटरनेट कनेक्शन जाँचें, साइन आउट करके फिर साइन इन करें, या दूसरा ब्राउज़र। अगर कोई सामान नहीं जुड़ रहा, तो वह स्टॉक से बाहर हो सकता है या 10 की सीमा तक पहुँच गया हो। अगर बार-बार हो, तो आपने क्या क्लिक किया और कौन-सा संदेश दिखा, यह लिखकर {email} पर भेजें।",
    },
    # Phase A: never invent an address, phone number, tax ID or legal entity (none is published in this system).
    "business_info": {
        "ta": "{store} இந்த அமைப்பில் கடை முகவரி, தொலைபேசி எண், ஜிஎஸ்டி/வரி பதிவு விவரங்களை இன்னும் வெளியிடவில்லை, எனவே அவற்றை "
              "என்னால் சொல்ல முடியாது. {store} குழுவை {email}-இல் தொடர்பு கொள்ளலாம் ({hours}).",
        "en": "{store} hasn't published a store address, phone number or GST/tax registration details in this system yet, so I "
              "can't give you those. You can reach the {store} team at {email} ({hours}).",
        "hi": "{store} ने इस सिस्टम में अभी दुकान का पता, फ़ोन नंबर या GST/टैक्स पंजीकरण की जानकारी प्रकाशित नहीं की है, इसलिए मैं "
              "वह नहीं बता सकता। {store} टीम से {email} पर संपर्क करें ({hours})।",
    },
    "bulk": {
        "ta": "மொத்த அல்லது நிறுவன ஆர்டர்களுக்கு {email}-ஐத் தொடர்பு கொள்ளுங்கள் ({hours}). ஆன்லைன் ஆர்டர்களில் ஒவ்வொரு பொருளிலும் அதிகபட்சம் 10 மட்டுமே.",
        "en": "For bulk or business orders, please email {email} ({hours}). Online orders are limited to 10 of each item.",
        "hi": "थोक या बिज़नेस ऑर्डर के लिए कृपया {email} पर लिखें ({hours})। ऑनलाइन ऑर्डर में हर सामान के ज़्यादा से ज़्यादा 10 ही होते हैं।",
    },
    # ---- people, frustration, repeated failure -------------------------------------------------
    "frustration": {
        "ta": "இது உங்களுக்கு எரிச்சலூட்டியதற்கு வருந்துகிறேன்.",
        "en": "I'm sorry this has been frustrating.",
        "hi": "माफ़ कीजिए, इससे आपको परेशानी हुई।",
    },
    "human_no_agent": {
        "ta": "அரட்டையிலிருந்து உங்களை நேரடி முகவரிடம் இணைக்கவோ டிக்கெட் உருவாக்கவோ என்னால் முடியாது, ஆனால் {store} குழு {email}-இல் நேரடியாக உதவும் ({hours}).",
        "en": "I can't transfer you to a live agent or create a ticket from the chat, but the {store} team can help directly at {email} ({hours}).",
        "hi": "मैं चैट से आपको किसी लाइव एजेंट से नहीं जोड़ सकता और न ही टिकट बना सकता हूँ, लेकिन {store} टीम {email} पर सीधे मदद कर सकती है ({hours})।",
    },
    "human_summary": {
        "ta": " மின்னஞ்சலில் சேர்க்க சுருக்கம்: {summary}",
        "en": " A summary you can include: {summary}",
        "hi": " ईमेल में जोड़ने के लिए सारांश: {summary}",
    },
    "repeat_failure": {
        "ta": "நான் இதைச் சரியாகப் புரிந்துகொள்ளவில்லை என்று தோன்றுகிறது. {store} குழு {email}-இல் நேரடியாக உதவும் ({hours}).",
        "en": "I don't seem to be getting this right. The {store} team can help directly at {email} ({hours}).",
        "hi": "लगता है मैं इसे ठीक से नहीं समझ पा रहा। {store} टीम {email} पर सीधे मदद कर सकती है ({hours})।",
    },
    # ---- products ------------------------------------------------------------------------------
    "compare_intro": {"ta": "ஒப்பீடு: ", "en": "Here's how they compare: ", "hi": "तुलना: "},
    "compare_cheaper": {
        "ta": " {name} {diff} குறைவான விலை.",
        "en": " {name} is {diff} cheaper.",
        "hi": " {name} {diff} सस्ता है।",
    },
    "compare_need_two": {
        "ta": "எந்தப் பொருட்களை ஒப்பிட வேண்டும்? குறைந்தது இரண்டு பொருள் பெயர்களைச் சொல்லுங்கள்.",
        "en": "Which products would you like me to compare? Tell me at least two product names.",
        "hi": "किन प्रोडक्ट की तुलना करूँ? कम से कम दो प्रोडक्ट के नाम बताइए।",
    },
    "cheaper_found": {
        "ta": "{name} ({price})-ஐ விட மலிவானவை: ",
        "en": "Cheaper than the {name} ({price}): ",
        "hi": "{name} ({price}) से सस्ते: ",
    },
    "cheapest_found": {
        "ta": "ஸ்டாக்கில் உள்ளவற்றில் மிகக் குறைந்த விலை: {name} — {price}.",
        "en": "The lowest-priced one we have in stock is the {name} — {price}.",
        "hi": "स्टॉक में सबसे सस्ता: {name} — {price}।",
    },
    "cheapest_next": {
        "ta": " அடுத்தவை: {list}.",
        "en": " Next: {list}.",
        "hi": " इसके बाद: {list}।",
    },
    "cheapest_sold_out": {
        "ta": " {name} ({price}) இன்னும் மலிவானது, ஆனால் இப்போது ஸ்டாக்கில் இல்லை.",
        "en": " The {name} ({price}) costs less but is out of stock right now.",
        "hi": " {name} ({price}) और सस्ता है, लेकिन अभी स्टॉक में नहीं है।",
    },
    "cheapest_over_budget": {
        "ta": "{budget}-க்குள் அந்த வகையில் எதுவும் இல்லை. ஸ்டாக்கில் உள்ளவற்றில் மிகக் குறைந்த விலை: {name} — {price}.",
        "en": "Nothing of that kind is within {budget}. The lowest-priced one in stock is the {name} — {price}.",
        "hi": "{budget} के अंदर उस तरह का कोई प्रोडक्ट नहीं है। स्टॉक में सबसे सस्ता: {name} — {price}।",
    },
    "cheapest_none": {
        "ta": "அந்த வகையில் இப்போது ஸ்டாக்கில் எதுவும் இல்லை ({name} உட்பட).",
        "en": "Nothing of that kind is in stock right now (including the {name}).",
        "hi": "उस तरह का कोई प्रोडक्ट अभी स्टॉक में नहीं है ({name} भी नहीं)।",
    },
    "cheaper_which": {
        "ta": "எந்தப் பொருளுக்கு மலிவான மாற்று வேண்டும்?",
        "en": "Which product would you like a cheaper option for?",
        "hi": "किस प्रोडक्ट का सस्ता विकल्प चाहिए?",
    },
    "cheaper_none": {
        "ta": "{name} ({price}) தான் எங்களிடம் ஸ்டாக்கில் உள்ள மிகக் குறைந்த விலை {category} பொருள்.",
        "en": "The {name} ({price}) is already the lowest-priced item in {category} that we have in stock.",
        "hi": "{name} ({price}) पहले से ही स्टॉक में मौजूद सबसे सस्ता {category} प्रोडक्ट है।",
    },
    "alternatives": {
        "ta": " ஸ்டாக்கில் உள்ள மாற்றுகள்: {list}.",
        "en": " In-stock alternatives: {list}.",
        "hi": " स्टॉक में मौजूद विकल्प: {list}।",
    },
    "alt_none": {
        "ta": " அந்த வகையில் இப்போது ஸ்டாக்கில் மாற்று எதுவும் இல்லை.",
        "en": " There's no in-stock alternative in that category right now.",
        "hi": " अभी उस श्रेणी में स्टॉक में कोई विकल्प नहीं है।",
    },
    "add_confirm": {
        "ta": "{name} ஸ்டாக்கில் உள்ளது (ஒன்று {price}). சேர்க்க “{button}” பொத்தானைத் தட்டுங்கள் — கார்ட் புதுப்பிக்கப்பட்டதும் உறுதிப்படுத்துகிறேன்.",
        "en": "The {name} is in stock ({price} each). Tap “{button}” to add it — I'll confirm once your cart is updated.",
        "hi": "{name} स्टॉक में है ({price} प्रति)। जोड़ने के लिए “{button}” दबाएँ — कार्ट अपडेट होते ही मैं पुष्टि करूँगा।",
    },
    # Phase H+: attribute questions and conversational cart removal.
    "attr_catalogue": {
        "ta": "{name} பற்றி எங்கள் பட்டியலில் உள்ள விவரம் (ஆங்கிலத்தில்): “{desc}”. இதைத் தவிர {attr} விருப்பங்கள் குறிப்பிடப்படவில்லை, அதனால் நான் ஊகிக்க மாட்டேன்.",
        "en": "Our catalogue describes the {name} as: “{desc}”. It doesn't list other {attr} options, so I won't guess.",
        "hi": "हमारी सूची में {name} के बारे में यह लिखा है (अंग्रेज़ी में): “{desc}”। इसके अलावा कोई {attr} विकल्प नहीं बताए गए हैं, इसलिए मैं अंदाज़ा नहीं लगाऊँगा।",
    },
    "attr_weight": {
        "ta": "எங்கள் பட்டியலின்படி {name}-இன் எடை {weight}.",
        "en": "According to our catalogue, the {name} weighs {weight}.",
        "hi": "हमारी सूची के अनुसार {name} का वज़न {weight} है।",
    },
    "attr_weight_missing": {
        "ta": "எங்கள் பட்டியலில் {name}-இன் எடை குறிப்பிடப்படவில்லை, அதனால் நான் ஊகிக்க மாட்டேன்.",
        "en": "Our catalogue doesn't list the weight of the {name}, so I won't guess.",
        "hi": "हमारी सूची में {name} का वज़न नहीं लिखा है, इसलिए मैं अंदाज़ा नहीं लगाऊँगा।",
    },
    "attr_which": {
        "ta": "எந்தப் பொருளின் {attr} பற்றிக் கேட்கிறீர்கள்? பொருளின் பெயரைச் சொல்லுங்கள்.",
        "en": "Which product's {attr} would you like to know about? Tell me its name.",
        "hi": "किस प्रोडक्ट के {attr} के बारे में जानना है? उसका नाम बताइए।",
    },
    "remove_empty": {
        "ta": "உங்கள் கார்ட் காலியாக உள்ளது — நீக்க எதுவும் இல்லை.",
        "en": "Your cart is empty — there's nothing to remove.",
        "hi": "आपका कार्ट खाली है — हटाने के लिए कुछ नहीं है।",
    },
    "remove_which": {
        "ta": "எதை நீக்க வேண்டும்? உங்கள் கார்ட்டில்: {list}.",
        "en": "Which one should I remove? Your cart has: {list}.",
        "hi": "कौन-सा हटाना है? आपके कार्ट में: {list}।",
    },
    "remove_confirm": {
        "ta": "உங்கள் கார்ட்டில் {name} ({qty}) உள்ளது. நீக்க “{button}” பொத்தானைத் தட்டுங்கள்.",
        "en": "Your cart has the {name} (quantity {qty}). Tap “{button}” to remove it.",
        "hi": "आपके कार्ट में {name} ({qty}) है। हटाने के लिए “{button}” दबाएँ।",
    },
    "btn_remove": {"ta": "{name} நீக்கு", "en": "Remove {name}", "hi": "{name} हटाएँ"},
    "add_which": {
        "ta": "எந்தப் பொருளைச் சேர்க்க வேண்டும்? இவை கிடைத்தன: {list}.",
        "en": "Which one would you like to add? I found: {list}.",
        "hi": "कौन-सा जोड़ना है? मुझे ये मिले: {list}।",
    },
    "add_unknown": {
        "ta": "எந்தப் பொருளை உங்கள் கார்ட்டில் சேர்க்க வேண்டும்?",
        "en": "Which product would you like to add to your cart?",
        "hi": "आप कौन-सा प्रोडक्ट कार्ट में जोड़ना चाहते हैं?",
    },
    "add_out": {
        "ta": "மன்னிக்கவும், {name} ஸ்டாக்கில் இல்லாததால் சேர்க்க முடியாது.",
        "en": "Sorry, the {name} is out of stock, so it can't be added.",
        "hi": "माफ़ कीजिए, {name} स्टॉक में नहीं है, इसलिए जोड़ा नहीं जा सकता।",
    },
    "add_limit": {
        "ta": "{name}-இல் அதிகபட்சம் {max} சேர்க்கலாம் (ஒரு பொருளுக்கு 10 வரம்பு; ஸ்டாக்கில் {stock}).",
        "en": "You can add up to {max} of the {name} (the limit is 10 per item, and we have {stock} in stock).",
        "hi": "आप {name} के ज़्यादा से ज़्यादा {max} जोड़ सकते हैं (हर सामान की सीमा 10 है, और स्टॉक में {stock} हैं)।",
    },
    "add_staff": {
        "ta": "ஸ்டாஃப் கணக்குகளால் பொருட்களை வாங்க முடியாது.",
        "en": "Staff accounts can't shop.",
        "hi": "स्टाफ़ अकाउंट से खरीदारी नहीं हो सकती।",
    },
    "reorder_items": {
        "ta": "உங்கள் கடைசி ஆர்டர் {number}-இல்: {items}. ஒரே தட்டில் மீண்டும் ஆர்டர் செய்யும் வசதி இல்லை, ஆனால் ஸ்டாக்கில் உள்ளவற்றைக் கீழே உள்ள பொத்தான்களால் சேர்க்கலாம்.",
        "en": "Your last order {number} had: {items}. There's no one-tap reorder, but you can add the items that are in stock with the buttons below.",
        "hi": "आपके पिछले ऑर्डर {number} में था: {items}। एक बार में दोबारा ऑर्डर की सुविधा नहीं है, लेकिन स्टॉक में मौजूद सामान नीचे दिए बटनों से जोड़ सकते हैं।",
    },
    "reorder_none": {
        "ta": "மீண்டும் செய்ய முந்தைய ஆர்டர் எதுவும் கிடைக்கவில்லை.",
        "en": "I can't find a previous order to repeat.",
        "hi": "दोहराने के लिए कोई पिछला ऑर्डर नहीं मिला।",
    },
    "reorder_out": {"ta": " {name} தற்போது ஸ்டாக்கில் இல்லை.", "en": " The {name} is currently out of stock.", "hi": " {name} अभी स्टॉक में नहीं है।"},
    "care_intro": {
        "ta": "பொதுவான குறிப்பு (பொருள் விவரத்திலிருந்து அல்ல): ",
        "en": "General tip (not from the product listing): ",
        "hi": "सामान्य सुझाव (प्रोडक्ट विवरण से नहीं): ",
    },
    "care_none": {
        "ta": "அதற்கான நம்பகமான பராமரிப்பு அல்லது பயன்பாட்டுத் தகவல் என்னிடம் இல்லை. பொருள் விவரத்தைப் பாருங்கள் அல்லது {email}-இடம் கேளுங்கள்.",
        "en": "I don't have reliable care or usage information for that. Please check the product description or ask {email}.",
        "hi": "इसके लिए मेरे पास भरोसेमंद देखभाल या इस्तेमाल की जानकारी नहीं है। कृपया प्रोडक्ट का विवरण देखें या {email} से पूछें।",
    },
    "care_safety": {
        "ta": " எப்போதும் பொருளின் லேபிள் அறிவுரைகளைப் பின்பற்றுங்கள்.",
        "en": " Always follow the care label or the maker's instructions.",
        "hi": " हमेशा केयर लेबल या निर्माता के निर्देश मानें।",
    },
    "offtopic": {
        "ta": "நான் {assistant}, {store} உதவியாளர், எனவே அதற்கு என்னால் உதவ முடியாது — ஆனால் {specialty} கண்டுபிடிக்கவும், ஆர்டர், டெலிவரி, ரிட்டர்ன், பணம் பற்றியும் உதவ முடியும்.",
        "en": "I'm {assistant}, the {store} assistant, so I can't help with that — but I can help you find {specialty}, or with an order, delivery, return or payment.",
        "hi": "मैं {assistant} हूँ, {store} का सहायक, इसलिए इसमें मदद नहीं कर सकता — लेकिन {specialty} ढूँढने में, या ऑर्डर, डिलीवरी, रिटर्न और भुगतान में मदद कर सकता हूँ।",
    },
    "sensitive": {
        "ta": "தயவுசெய்து கார்டு எண், பாதுகாப்புக் குறியீடு, கடவுச்சொல் அல்லது ஒருமுறைக் குறியீட்டை இங்கே பகிர வேண்டாம் — நான் அவற்றை ஒருபோதும் கேட்க மாட்டேன், அரட்டையில் பகிர வேண்டிய அவசியமும் இல்லை. உங்கள் செய்தியின் அந்தப் பகுதியை நான் பயன்படுத்தவில்லை.",
        "en": "Please don't share card numbers, security codes, passwords or one-time codes here — I'll never ask for them, and you never need to share them in chat. I haven't used that part of your message.",
        "hi": "कृपया यहाँ कार्ड नंबर, सिक्योरिटी कोड, पासवर्ड या OTP साझा न करें — मैं इन्हें कभी नहीं माँगूँगा, और चैट में इन्हें बताने की ज़रूरत नहीं है। मैंने आपके संदेश का वह हिस्सा इस्तेमाल नहीं किया।",
    },
    # ---- action-button labels ------------------------------------------------------------------
    "btn_cancel": {"ta": "ஆர்டர் {number}-ஐ ரத்து செய்", "en": "Cancel order {number}", "hi": "ऑर्डर {number} रद्द करें"},
    "btn_add": {"ta": "{qty} × {name} கார்ட்டில் சேர்", "en": "Add {qty} × {name} to cart", "hi": "{qty} × {name} कार्ट में जोड़ें"},
    "btn_pay": {"ta": "ஆர்டர் {number}-க்குப் பணம் செலுத்து", "en": "Pay for order {number}", "hi": "ऑर्डर {number} का भुगतान करें"},
    "btn_signin": {"ta": "உள்நுழைக", "en": "Sign in", "hi": "साइन इन करें"},
    "btn_register": {"ta": "கணக்கு உருவாக்கு", "en": "Create an account", "hi": "अकाउंट बनाएँ"},
    "btn_reset": {"ta": "கடவுச்சொல்லை மீட்டமை", "en": "Reset password", "hi": "पासवर्ड रीसेट करें"},
    "btn_cart": {"ta": "கார்ட்டைப் பார்", "en": "View cart", "hi": "कार्ट देखें"},
    "btn_checkout": {"ta": "செக்அவுட்", "en": "Go to checkout", "hi": "चेकआउट करें"},
    "btn_orders": {"ta": "என் ஆர்டர்கள்", "en": "My orders", "hi": "मेरे ऑर्डर"},
    "btn_email": {"ta": "{email}-க்கு மின்னஞ்சல்", "en": "Email {email}", "hi": "{email} पर ईमेल करें"},
}

# What each assistant specialises in (used when steering back from an unrelated question).
SPECIALTY: dict[str, dict[str, str]] = {
    "store-a": {"ta": "கூடாரங்கள், பைகள், ஸ்லீப்பிங் பேக்குகள், காலணிகள், ஆடைகள், அடுப்புகள், விளக்குகள்",
                "en": "outdoor gear — tents, packs, sleeping bags, footwear, clothing, stoves and lights",
                "hi": "आउटडोर सामान — टेंट, बैग, स्लीपिंग बैग, जूते, कपड़े, स्टोव और लाइट"},
    "store-b": {"ta": "காபி, தேநீர், ப்ரூயிங் உபகரணங்கள், சமையலறைப் பொருட்கள்",
                "en": "coffee, tea, brewing gear and kitchen goods",
                "hi": "कॉफ़ी, चाय, ब्रूइंग का सामान और किचन प्रोडक्ट"},
}

# General care / usage tips per store, keyed by the catalogue word they apply to. Widely accepted general
# advice, always labelled as such (care_intro) and followed by "follow the care label" (care_safety).
TIPS: dict[str, dict[str, dict[str, str]]] = {
    "store-a": {
        "tent": {"ta": "பயணத்துக்கு முன் வீட்டிலேயே ஒருமுறை கூடாரத்தை அமைத்துப் பாருங்கள்; பூஞ்சை வராமல் இருக்க, பேக் செய்யும் முன் முழுமையாக உலர வையுங்கள்; குளிர்ந்த, உலர்ந்த இடத்தில் தளர்வாக வையுங்கள்.",
                 "en": "Pitch it once at home before your trip; always let it dry completely before packing it away to prevent mildew; store it loosely in a cool, dry place.",
                 "hi": "यात्रा से पहले एक बार घर पर टेंट लगाकर देखें; फफूंद से बचाने के लिए पैक करने से पहले उसे पूरी तरह सुखाएँ; ठंडी, सूखी जगह पर ढीला रखें।"},
        "sleeping": {"ta": "ஒவ்வொரு பயணத்துக்குப் பிறகும் காற்றாட வையுங்கள்; நீண்ட காலம் அழுத்திய பையில் வைக்காமல், தளர்வாக வையுங்கள்.",
                     "en": "Air it out after each trip, and store it loose rather than squeezed in its stuff sack.",
                     "hi": "हर यात्रा के बाद इसे हवा लगने दें, और लंबे समय तक दबाकर नहीं, ढीला रखें।"},
        "pad": {"ta": "கூர்மையான பொருட்களிலிருந்து தள்ளி தரையை சுத்தம் செய்த பின் விரியுங்கள்; வால்வைத் திறந்தபடி, விரித்து வையுங்கள்.",
                "en": "Clear sharp stones from the ground before laying it out, and store it unrolled with the valve open.",
                "hi": "बिछाने से पहले ज़मीन से नुकीले पत्थर हटाएँ, और इसे वाल्व खुला रखकर फैलाकर रखें।"},
        "boot": {"ta": "சேற்றைச் சுத்தம் செய்து, நேரடி வெப்பத்திலிருந்து தள்ளி இயற்கையாக உலர வையுங்கள்.",
                 "en": "Brush off mud after each hike and let them air-dry away from direct heat.",
                 "hi": "हर हाइक के बाद कीचड़ साफ़ करें और सीधी गर्मी से दूर हवा में सुखाएँ।"},
        "stove": {"ta": "திறந்த வெளியில் மட்டும், நிலையான பரப்பில், கூடாரத்திலிருந்து தள்ளி பயன்படுத்துங்கள்; பேக் செய்யும் முன் குளிர விடுங்கள்.",
                  "en": "Use it outdoors only, on a stable surface and well away from your tent, and let it cool before packing.",
                  "hi": "इसे सिर्फ़ खुले में, स्थिर सतह पर और टेंट से दूर इस्तेमाल करें, और पैक करने से पहले ठंडा होने दें।"},
        "lamp": {"ta": "பயணத்துக்கு முன் முழுமையாக சார்ஜ் செய்யுங்கள்; இரவுப் பார்வையைக் காக்க முகாமில் சிவப்பு விளக்கு முறையைப் பயன்படுத்துங்கள்.",
                 "en": "Charge it fully before a trip, and use red mode around camp to keep your night vision.",
                 "hi": "यात्रा से पहले पूरा चार्ज करें, और रात में देखने की क्षमता बनाए रखने के लिए कैंप में रेड मोड इस्तेमाल करें।"},
    },
    "store-b": {
        "press": {"ta": "தொடக்கத்துக்கு எடைப்படி சுமார் 1:15 காபி–தண்ணீர் விகிதம், கரகரப்பான அரைப்பு, அழுத்தும் முன் சுமார் 4 நிமிடம் ஊற வையுங்கள்.",
                  "en": "A common starting point is about 1:15 coffee to water by weight with a coarse grind, steeped for about 4 minutes before pressing.",
                  "hi": "शुरुआत के लिए वज़न के हिसाब से लगभग 1:15 कॉफ़ी और पानी, मोटी पिसाई, और दबाने से पहले लगभग 4 मिनट भिगोएँ।"},
        "dripper": {"ta": "சுமார் 1:16 விகிதம், நடுத்தர-நுண்ணிய அரைப்புடன் தொடங்கி, வட்டமாக மெதுவாக ஊற்றுங்கள்; மொத்தம் சுமார் 3 நிமிடம்.",
                    "en": "Start around 1:16 with a medium-fine grind and pour slowly in circles; aim for about 3 minutes in total.",
                    "hi": "लगभग 1:16 और मध्यम-बारीक पिसाई से शुरू करें, धीरे-धीरे गोल घुमाकर डालें; कुल लगभग 3 मिनट रखें।"},
        "grinder": {"ta": "பர்களைத் தொடர்ந்து பிரஷ் செய்யுங்கள், தண்ணீரால் கழுவ வேண்டாம்; காய்ச்சும் சற்று முன் அரையுங்கள்.",
                    "en": "Brush the burrs out regularly instead of washing them, and grind just before you brew.",
                    "hi": "बर्र को धोने के बजाय नियमित रूप से ब्रश से साफ़ करें, और ब्रू करने से ठीक पहले पीसें।"},
        "kettle": {"ta": "சிட்ரிக் அமிலம் அல்லது வினிகர் கரைசலால் அவ்வப்போது சுண்ணாம்பை நீக்கி, நன்கு அலசுங்கள்.",
                   "en": "Descale it now and then with a citric-acid or vinegar solution, then rinse it well.",
                   "hi": "कभी-कभी सिट्रिक एसिड या सिरके के घोल से डीस्केल करें, फिर अच्छी तरह धो लें।"},
        "tea": {"ta": "பச்சைத் தேநீருக்கு சுமார் 70–80 °C தண்ணீர், 1–2 நிமிடம் ஊற வையுங்கள்; கொதிநீர் கசப்பாக்கும்.",
                "en": "For green tea, use water around 70–80 °C and steep for 1–2 minutes; boiling water makes it bitter.",
                "hi": "ग्रीन टी के लिए लगभग 70–80 °C पानी लें और 1–2 मिनट भिगोएँ; उबलता पानी इसे कड़वा बनाता है।"},
        "chai": {"ta": "தண்ணீர், பாலுடன் சில நிமிடம் கொதிக்க விட்டு, சுவைக்கேற்ப இனிப்பு சேருங்கள்.",
                 "en": "Simmer it with water and milk for a few minutes, then sweeten to taste.",
                 "hi": "पानी और दूध के साथ कुछ मिनट उबालें, फिर स्वाद अनुसार मीठा डालें।"},
        "bean": {"ta": "காற்றுப்புகாத பாத்திரத்தில், வெளிச்சம், வெப்பத்திலிருந்து தள்ளி வையுங்கள்; காய்ச்சும் முன் அரையுங்கள்.",
                 "en": "Keep beans in an airtight container away from light and heat, and grind just before brewing.",
                 "hi": "बीन्स को एयरटाइट डिब्बे में, रोशनी और गर्मी से दूर रखें, और ब्रू करने से ठीक पहले पीसें।"},
        "honey": {"ta": "பச்சைத் தேன் கெட்டியாகலாம்; ஜாடியை வெதுவெதுப்பான நீரில் மெதுவாக சூடாக்கி மென்மையாக்குங்கள்.",
                  "en": "Raw honey can crystallise; stand the jar in warm water to soften it again.",
                  "hi": "कच्चा शहद जम सकता है; इसे फिर से नरम करने के लिए जार को गुनगुने पानी में रखें।"},
    },
}
# Words that point to a tip (catalogue search terms and slugs map onto these keys).
TIP_ALIASES: dict[str, str] = {
    "tent": "tent", "sleeping": "sleeping", "bag": "sleeping", "pad": "pad", "mat": "pad", "boot": "boot", "shoe": "boot",
    "stove": "stove", "burner": "stove", "lamp": "lamp", "headlamp": "lamp", "torch": "lamp",
    "press": "press", "french": "press", "dripper": "dripper", "pour": "dripper", "pour-over": "dripper", "v60": "dripper",
    "grinder": "grinder", "burr": "grinder", "kettle": "kettle", "tea": "tea", "sencha": "tea", "green": "tea",
    "chai": "chai", "bean": "bean", "coffee": "bean", "honey": "honey",
}


# ---- per-store voice for catalogue answers ----------------------------------------------------------------
# Same catalogue rows, different introduction: Scout is practical trail gear, Maple is the coffee & tea shelf.
FOUND_INTRO: dict[str, dict[str, str]] = {
    "store-a": {"ta": "எங்கள் மலையேற்றப் பொருட்களில் இவை பொருந்துகின்றன: ", "en": "From our trail gear, these match: ",
                "hi": "हमारे ट्रेल गियर में ये मेल खाते हैं: "},
    "store-b": {"ta": "எங்கள் காபி, தேநீர் வரிசையில் இவை பொருந்துகின்றன: ", "en": "From our coffee and tea shelf, these match: ",
                "hi": "हमारी कॉफ़ी और चाय की शेल्फ़ से ये मेल खाते हैं: "},
}

CURRENCY_NAMES: dict[str, dict[str, str]] = {
    "USD": {"ta": "அமெரிக்க டாலர்", "en": "US dollars", "hi": "अमेरिकी डॉलर"},
    "INR": {"ta": "இந்திய ரூபாய்", "en": "Indian rupees", "hi": "भारतीय रुपये"},
}

# When a shopping question asks about conditions or properties the catalogue doesn't describe, each assistant
# says plainly that it can only go by the product descriptions (Scout: safety; Maple: caffeine/health/taste).
import re as _re  # noqa: E402

ADVICE_LIMITS: dict[str, dict] = {
    "store-a": {
        "rx": _re.compile(r"winter|snow|cold|freez|sub-?zero|below zero|altitude|alpine climb|mountaineer|storm|monsoon|heavy rain|desert|"
                          r"extreme|expedition|-\d+\s*°|பனி|குளிர்|மழைக்காலம்|உயரமான|बर्फ|ठंड|सर्दी|मानसून|ऊँचाई|ऊंचाई", _re.I),
        "ta": "தயாரிப்பு விளக்கங்களில் உள்ளதை மட்டுமே என்னால் சொல்ல முடியும். நீங்கள் எதிர்பார்க்கும் சூழலுக்கு ஒவ்வொரு பொருளின் "
              "மதிப்பீட்டையும் சரிபாருங்கள்; கடுமையான சூழல்களுக்கு அனுபவமுள்ளவர்களின் ஆலோசனையைப் பெறுங்கள்.",
        "en": "I can only go by the product descriptions above. Check each item's rating against the conditions you expect, and get "
              "experienced advice before heading into harsh conditions.",
        "hi": "मैं सिर्फ़ प्रोडक्ट विवरण के आधार पर बता सकता हूँ। जिन हालात की आप उम्मीद करते हैं, उनके हिसाब से हर सामान की रेटिंग जाँचें, "
              "और कठिन हालात में जाने से पहले अनुभवी लोगों की सलाह लें।",
    },
    "store-b": {
        "rx": _re.compile(r"caffeine|decaf|health|healthy|pregnan|allerg|calorie|sugar|gluten|vegan|organic|acidity|stomach|"
                          r"காஃபின்|ஆரோக்கிய|ஒவ்வாமை|कैफीन|कैफ़ीन|सेहत|स्वास्थ्य|एलर्जी", _re.I),
        "ta": "தயாரிப்பு விளக்கங்களில் உள்ளதை மட்டுமே என்னால் சொல்ல முடியும் — காஃபின் அளவு, ஒவ்வாமை அல்லது ஆரோக்கியத் தகவல்கள் "
              "எங்கள் பட்டியலில் இல்லை.",
        "en": "I can only go by the product descriptions above — caffeine levels, allergen and health details aren't part of our "
              "listings.",
        "hi": "मैं सिर्फ़ प्रोडक्ट विवरण के आधार पर बता सकता हूँ — कैफ़ीन की मात्रा, एलर्जी या सेहत से जुड़ी जानकारी हमारी लिस्टिंग में नहीं है।",
    },
}


ATTRIBUTE_NAMES: dict[str, dict[str, str]] = {
    "colour": {"ta": "நிற", "en": "colour", "hi": "रंग"},
    "size": {"ta": "அளவு", "en": "size", "hi": "साइज़"},
    "flavour": {"ta": "சுவை", "en": "flavour", "hi": "स्वाद"},
    "material": {"ta": "பொருள்", "en": "material", "hi": "सामग्री"},
    "weight": {"ta": "எடை", "en": "weight", "hi": "वज़न"},
}
