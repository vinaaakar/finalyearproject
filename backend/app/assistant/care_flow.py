"""Customer-care requests by conversation (Scout / Maple), in Tamil, English and Hindi, typed or spoken.

A deterministic, rule-based flow — the language model is never used here, and it never decides anything:
  1. recognise the request (complaint, return, simulated refund, human help) or a status question;
  2. ask for what is missing, one thing at a time: order → item → reason → description (nothing is invented; the
     customer's own words are used as the description);
  3. show a review and wait for an explicit "yes" (or the Confirm button) — a draft is never submitted otherwise;
  4. create the request through app/care_requests.py (the same server-side rules as the storefront form) and read
     back the reference THE DATABASE returned; on any refusal, say plainly that nothing was submitted.

The draft travels with the conversation (ChatRequest.care_draft ↔ ChatResponse.care_draft), so switching language
keeps it. Every field in it is re-validated on each turn and again at creation; identity always comes from the session.
"""

from __future__ import annotations

import re
import secrets
from typing import Any

from .. import care_requests as care
from ..commerce import CommerceError
from ..stores import ORDER_PREFIX, STORE_BRANDING, StoreId

# ---- recognition ----------------------------------------------------------------------------------------------------------
_HUMAN = re.compile(r"\b(human|real person|live (agent|person)|(customer )?support (team|agent|person)|speak (to|with) (someone|a person|support|"
                    r"customer support|customer service|an agent|a human)|talk (to|with) (someone|a person|support|customer support|customer service|"
                    r"an agent|a human)|(need|want|get) (customer )?(support|help from (a|an) (person|human|agent))|escalat|(open|raise|create) a ticket|"
                    r"human support|human help|customer care (venum|vendum|chahiye))|மனித உதவி|மனிதர்|வாடிக்கையாளர் சேவை|ஊழியர்|இன்சான்|"
                    r"ஹியூமன்|ஹ்யூமன்|கஸ்டமர் கேர்|கஸ்டமர் சப்போர்ட்|ஏஜென்ட்|ह्यूमन|ह्युमन|कस्टमर केयर|"
                    r"इंसान|मानव सहायता|किसी व्यक्ति|ग्राहक सेवा|सपोर्ट (से|टीम)|कर्मचारी से", re.I)
# "பணத்தைத் திருப்பித் தர" (give the money back) is a refund, although "திருப்பித் தர" alone is a return.
_REFUND = re.compile(r"\b(refund|money back|reimburse)|பணம் திரும்ப|பணத்தைத் திரும்ப|பணத்தை திரும்ப|பணத்தைத் திருப்பி|பணத்தை திருப்பி"
                     r"|பணம் திருப்பி|ரீஃபண்ட்|रिफंड|रिफ़ंड|पैसे वापस|पैसे लौटा|धनवापसी", re.I)
_RETURN = re.compile(r"\b(return (it|this|that|my|the|an?|item|order|product)|send (it |this )?back|want to return|return request)|"
                     r"திருப்பி அனுப்ப|திருப்பித் தர|ரிட்டர்ன்|वापस करना|वापस करनी|लौटाना|रिटर्न", re.I)
_COMPLAINT = re.compile(r"\b(damaged|broken|cracked|defective|wrong (item|product|size|colou?r)|missing|poor quality|bad quality|"
                        r"complain|complaint|arrived (late|damaged|broken)|not as described|"
                        r"report (a|an|the) (problem|issue)|(have|got|there is|there's) (a|an) (problem|issue) with (my|the|this|an?) "
                        r"(order|item|product|delivery)|problem (irukku|iruku|aagudhu)|complaint (pannanum|kudukkanum|kodukkanum|venum))|"
                        r"பிரச்சினையைப் புகார|பிரச்சினை உள்ளது|பிரச்சனை இருக்கு|समस्या (बतानी|दर्ज|की शिकायत)|समस्या है|"
                        r"கம்ப்ளைன்ட்|கம்ப்ளெயின்ட்|கம்ப்ளைண்ட்|कंप्लेंट|कम्प्लेंट|சேதம|உடைந்த|தவறான பொருள்|தவறான|காணவில்லை|"
                        r"புகார்|தரம் (சரியில்லை|மோசம்)|टूटा|टूटी|खराब|ख़राब|गलत सामान|ग़लत|गलत|गायब|शिकायत|क्वालिटी|गुणवत्ता", re.I)
_STATUS_WORD = re.compile(r"\b(status|update|progress|track|where is|what happened|any news)\b|நிலை|என்ன ஆனது|ஸ்டேட்டஸ்|"
                          r"स्थिति|स्टेटस|क्या हुआ|कहाँ तक", re.I)
_REQUEST_WORD = re.compile(r"\b(complaint|return request|return|refund|request|ticket|escalation|human help)\b|புகார்|"
                           r"கோரிக்கை|ரீஃபண்ட்|திருப்பி|शिकायत|अनुरोध|रिफंड|रिफ़ंड|वापसी", re.I)
# A question ABOUT the rules ("what is the return policy?") is answered from the policy, not turned into a request.
# "What do I have to do to return it?" ("ரிட்டர்ன் பண்ண என்ன செய்யணும்?", "return panna enna seiyanum?") is also a how-to question.
_POLICY = re.compile(r"\b(polic(y|ies)|how many days|return window|rules?|allowed to|how (do|can) (i|we)|how to|what (do|should) i do|"
                     r"enna (seiyanum|seyyanum|pannanum|panna)|kya karna|kaise karu?n?)\b|கொள்கை|விதி|எப்படி|என்ன செய்ய|என்ன பண்ண|"
                     r"पॉलिसी|नीति|नियम|कैसे|क्या करना", re.I)
# "Did my refund come through?" — a status question (falls back to the payment-record answer if there's no request).
_REFUND_STATUS = re.compile(r"come through|came through|been refunded|received (my|the|a) refund|got (my|the|a) refund|"
                            r"வரவில்லை|கிடைக்கவில்லை|नहीं मिला|मिला नहीं|आया नहीं|नहीं आया", re.I)
_REF = re.compile(r"\b(SA|BB)-(CMP|RET|RFD|ESC)-(\d{5,})\b", re.I)
_ORDER = re.compile(r"\b(SA|BB)-?(\d{5})\b|\b(\d{5})\b", re.I)

_YES = re.compile(r"^\s*(yes|yeah|yep|y|confirm|submit|ok(ay)?|sure|go ahead|please do|ஆம்|ஆமாம்|சரி|உறுதி|சமர்ப்பி|"
                  r"हाँ|हां|जी हाँ|जी|ठीक है|पुष्टि|भेज दो|सबमिट)(?=$|[\s.,!?।])[\s.!।]*", re.I)
_CANCEL = re.compile(r"^\s*(cancel|stop|never ?mind|forget it|no thanks|don't|do not|ரத்து|வேண்டாம்|நிறுத்து|"
                     r"रद्द|रहने दो|नहीं चाहिए|मत करो)(?=$|[\s.,!?।])", re.I)
_NO = re.compile(r"^\s*(no|none|no order|not about an order|whole order|entire order|all items|இல்லை|எதுவும் இல்லை|முழு ஆர்டர்|"
                 r"नहीं|कोई नहीं|पूरा ऑर्डर)(?=$|[\s.,!?।])", re.I)
_ORDINALS = [r"\b(first|1st|one|1)\b|முதல்|पहला|पहले", r"\b(second|2nd|two|2)\b|இரண்டாவது|दूसरा", r"\b(third|3rd|three|3)\b|மூன்றாவது|तीसरा",
             r"\b(fourth|4th|four|4)\b|நான்காவது|चौथा"]

_CATEGORY_WORDS: dict[str, list[tuple[str, str]]] = {
    "damaged": [("complaint", r"damag|broken|crack|defect|சேத|உடை|टूट|क्षतिग्रस्त|खराब|ख़राब")],
    "wrong_item": [("complaint", r"wrong|தவறான|गलत|ग़लत")],
    "missing_item": [("complaint", r"missing|not in the (box|package)|காணவில்லை|गायब|नहीं मिला")],
    "quality": [("complaint", r"quality|தரம்|क्वालिटी|गुणवत्ता")],
    "delivery": [("complaint", r"late|delivery|courier|டெலிவரி|தாமத|डिलीवरी|देर")],
    "not_as_described": [("return", r"not as described|different from|விவரத்துக்கு மாறாக|जैसा बताया")],
    "no_longer_needed": [("return", r"don'?t need|no longer need|changed my mind|தேவையில்லை|ज़रूरत नहीं|जरूरत नहीं")],
    "not_delivered": [("refund", r"not delivered|never (arrived|came)|didn'?t (arrive|get)|வரவில்லை|नहीं आया|नहीं पहुँचा")],
    "charged_incorrectly": [("refund", r"charged twice|double charg|overcharg|wrong amount|இரண்டு முறை|दो बार")],
    "order_problem": [("escalation", r"order|ஆர்டர்|ऑर्डर")],
    "payment_problem": [("escalation", r"payment|paid|பணம் செலுத்|भुगतान|पेमेंट")],
    "delivery_problem": [("escalation", r"deliver|டெலிவரி|डिलीवरी")],
    "account_problem": [("escalation", r"account|password|login|கணக்கு|अकाउंट|खाता")],
}


def detect(message: str) -> dict[str, Any] | None:
    """{"status": True, "kind"?: …, "reference"?: …} for a status question, {"kind": …} for a new request, else None."""
    m = _REF.search(message)
    if m:
        return {"status": True, "reference": f"{m.group(1)}-{m.group(2)}-{m.group(3)}".upper()}
    if _REFUND.search(message) and _REFUND_STATUS.search(message):
        return {"status": True, "kind": "refund", "fallback": True}
    if _STATUS_WORD.search(message) and _REQUEST_WORD.search(message):
        return {"status": True, "kind": _kind_of(message)}
    kind = _kind_of(message)
    if kind in ("return", "refund") and _POLICY.search(message):
        return None
    return {"kind": kind} if kind else None


def _kind_of(message: str) -> str | None:
    if _HUMAN.search(message):
        return "escalation"
    if _REFUND.search(message):
        return "refund"
    if _RETURN.search(message):
        return "return"
    if _COMPLAINT.search(message):
        return "complaint"
    return None


def infer_category(kind: str, message: str) -> str | None:
    for category, rules in _CATEGORY_WORDS.items():
        for k, rx in rules:
            if k == kind and re.search(rx, message, re.I):
                return category
    if kind == "refund":     # complaint words also explain a refund
        for category in ("damaged", "wrong_item", "missing_item"):
            if re.search(_CATEGORY_WORDS[category][0][1], message, re.I):
                return category
    if kind == "return":
        for category in ("damaged", "wrong_item"):
            if re.search(_CATEGORY_WORDS[category][0][1], message, re.I):
                return category
    return None


# ---- texts (reviewed templates; product names, references and staff messages are inserted verbatim) -----------------------------
KIND_NAMES = {
    "complaint": {"en": "complaint", "ta": "புகார்", "hi": "शिकायत"},
    "return": {"en": "return request", "ta": "திருப்பி அனுப்பும் கோரிக்கை", "hi": "वापसी अनुरोध"},
    "refund": {"en": "refund request (simulated)", "ta": "பணத்திரும்பக் கோரிக்கை (மாதிரி)", "hi": "रिफंड अनुरोध (सिम्युलेटेड)"},
    "escalation": {"en": "request for human help", "ta": "மனித உதவிக் கோரிக்கை", "hi": "मानव सहायता अनुरोध"},
}
CATEGORY_NAMES = {
    "damaged": {"en": "Damaged product", "ta": "சேதமடைந்த பொருள்", "hi": "क्षतिग्रस्त सामान"},
    "wrong_item": {"en": "Wrong product received", "ta": "தவறான பொருள் வந்தது", "hi": "गलत सामान मिला"},
    "missing_item": {"en": "Missing item", "ta": "பொருள் காணவில்லை", "hi": "सामान गायब"},
    "quality": {"en": "Product quality issue", "ta": "தரப் பிரச்சினை", "hi": "गुणवत्ता की समस्या"},
    "delivery": {"en": "Delivery issue", "ta": "டெலிவரி பிரச்சினை", "hi": "डिलीवरी की समस्या"},
    "not_as_described": {"en": "Not as described", "ta": "விவரத்துக்கு மாறாக உள்ளது", "hi": "जैसा बताया था वैसा नहीं"},
    "no_longer_needed": {"en": "No longer needed", "ta": "இனி தேவையில்லை", "hi": "अब ज़रूरत नहीं"},
    "not_delivered": {"en": "Not delivered", "ta": "டெலிவரி ஆகவில்லை", "hi": "डिलीवर नहीं हुआ"},
    "charged_incorrectly": {"en": "Charged incorrectly", "ta": "தவறான கட்டணம்", "hi": "गलत राशि ली गई"},
    "returned_item": {"en": "Item already returned", "ta": "பொருள் ஏற்கனவே திருப்பி அனுப்பப்பட்டது", "hi": "सामान लौटा दिया गया"},
    "order_problem": {"en": "Order problem", "ta": "ஆர்டர் பிரச்சினை", "hi": "ऑर्डर की समस्या"},
    "payment_problem": {"en": "Payment problem", "ta": "பணம் செலுத்துதல் பிரச்சினை", "hi": "भुगतान की समस्या"},
    "delivery_problem": {"en": "Delivery problem", "ta": "டெலிவரி பிரச்சினை", "hi": "डिलीवरी की समस्या"},
    "account_problem": {"en": "Account problem", "ta": "கணக்குப் பிரச்சினை", "hi": "अकाउंट की समस्या"},
    "follow_up": {"en": "Follow-up on an earlier request", "ta": "முந்தைய கோரிக்கையின் தொடர்ச்சி", "hi": "पिछले अनुरोध पर फ़ॉलो-अप"},
    "other": {"en": "Other", "ta": "மற்றவை", "hi": "अन्य"},
}
STATUS_NAMES = {
    "open": {"ta": "திறந்துள்ளது", "hi": "खुला"}, "requested": {"ta": "கோரப்பட்டது", "hi": "अनुरोध किया गया"},
    "under_review": {"ta": "பரிசீலனையில்", "hi": "समीक्षा में"}, "awaiting_customer": {"ta": "உங்கள் பதிலுக்காகக் காத்திருக்கிறது", "hi": "आपके जवाब का इंतज़ार"},
    "assigned": {"ta": "ஊழியரிடம் ஒதுக்கப்பட்டது", "hi": "स्टाफ़ को सौंपा गया"}, "in_progress": {"ta": "நடைபெறுகிறது", "hi": "प्रगति में"},
    "approved": {"ta": "ஏற்கப்பட்டது", "hi": "स्वीकृत"}, "rejected": {"ta": "நிராகரிக்கப்பட்டது", "hi": "अस्वीकृत"},
    "received": {"ta": "பொருள் பெறப்பட்டது", "hi": "सामान मिल गया"}, "inspected": {"ta": "பொருள் சோதிக்கப்பட்டது", "hi": "सामान की जाँच हो गई"},
    "completed": {"ta": "முடிந்தது", "hi": "पूरा हुआ"},
    "simulated_completed": {"ta": "பணத்திரும்பல் முடிந்தது (மாதிரி — உண்மையான பணம் அனுப்பப்படவில்லை)", "hi": "रिफंड पूरा (सिम्युलेटेड — कोई असली पैसा नहीं भेजा गया)"},
    "resolved": {"ta": "தீர்க்கப்பட்டது", "hi": "हल हो गया"}, "closed": {"ta": "மூடப்பட்டது", "hi": "बंद"},
    "withdrawn": {"ta": "திரும்பப் பெறப்பட்டது", "hi": "वापस लिया गया"},
}
T = {
    "signin": {"en": "Please sign in first so I can record your {kind} on your account — I'll keep what you told me.",
               "ta": "உங்கள் கணக்கில் {kind} பதிவு செய்ய முதலில் உள்நுழையுங்கள் — நீங்கள் சொன்னதை நான் நினைவில் வைத்திருப்பேன்.",
               "hi": "आपके अकाउंट में {kind} दर्ज करने के लिए पहले साइन इन करें — आपने जो बताया, मैं याद रखूँगा।"},
    "signin_human_alt": {"en": " You can also email the {store} team at {email} ({hours}). Nobody is live in this chat.",
                         "ta": " {store} குழுவுக்கு {email} என்ற முகவரியிலும் மின்னஞ்சல் அனுப்பலாம் ({hours}). இந்த அரட்டையில் நேரடியாக யாரும் இல்லை.",
                         "hi": " आप {store} टीम को {email} पर ईमेल भी कर सकते हैं ({hours})। इस चैट में अभी कोई व्यक्ति लाइव नहीं है।"},
    "staff": {"en": "Staff accounts can't submit customer requests.", "ta": "ஊழியர் கணக்குகளால் வாடிக்கையாளர் கோரிக்கைகளைச் சமர்ப்பிக்க முடியாது.",
              "hi": "स्टाफ़ अकाउंट से ग्राहक अनुरोध नहीं भेजे जा सकते।"},
    "start": {"en": "I can register a {kind} for you.", "ta": "உங்களுக்காக ஒரு {kind} பதிவு செய்ய முடியும்.", "hi": "मैं आपके लिए {kind} दर्ज कर सकता हूँ।"},
    "ask_order": {"en": "Which order is it about? {list}.", "ta": "இது எந்த ஆர்டரைப் பற்றியது? {list}.", "hi": "यह किस ऑर्डर के बारे में है? {list}।"},
    "ask_order_optional": {"en": " Or say “no order” if it isn't about an order.", "ta": " ஆர்டர் தொடர்பானது இல்லையென்றால் “இல்லை” என்று சொல்லுங்கள்.",
                           "hi": " अगर यह किसी ऑर्डर के बारे में नहीं है तो “नहीं” कहें।"},
    "no_orders": {"en": "You don't have any orders yet.", "ta": "உங்களிடம் இன்னும் ஆர்டர்கள் இல்லை.", "hi": "आपके अभी कोई ऑर्डर नहीं हैं।"},
    "none_eligible": {"en": "None of your orders can have a {kind} right now: {reason}",
                      "ta": "இப்போது உங்கள் எந்த ஆர்டருக்கும் {kind} செய்ய இயலாது: {reason}",
                      "hi": "अभी आपके किसी भी ऑर्डर के लिए {kind} नहीं हो सकता: {reason}"},
    "offer_other": {"en": "I can register a complaint or a request for human help instead.",
                    "ta": "அதற்குப் பதிலாக ஒரு புகார் அல்லது மனித உதவிக் கோரிக்கையைப் பதிவு செய்யலாம்.",
                    "hi": "इसके बजाय मैं शिकायत या मानव सहायता अनुरोध दर्ज कर सकता हूँ।"},
    "ask_item": {"en": "Which item? {list}", "ta": "எந்தப் பொருள்? {list}", "hi": "कौन सा सामान? {list}"},
    "ask_item_optional": {"en": " Or say “whole order”.", "ta": " அல்லது “முழு ஆர்டர்” என்று சொல்லுங்கள்.", "hi": " या “पूरा ऑर्डर” कहें।"},
    "ask_category": {"en": "What is the reason? {list}", "ta": "காரணம் என்ன? {list}", "hi": "कारण क्या है? {list}"},
    "ask_description": {"en": "Please describe it in a few words, in your own words.", "ta": "சில வார்த்தைகளில், உங்கள் சொந்த வார்த்தைகளில் விவரியுங்கள்.",
                        "hi": "कृपया कुछ शब्दों में, अपने शब्दों में बताइए।"},
    "review": {"en": "Please check before I submit: {kind}{order}{item}; reason: {category}; details: “{desc}”. Say “yes” (or tap Confirm) to submit, or “cancel”.",
               "ta": "சமர்ப்பிக்கும் முன் சரிபாருங்கள்: {kind}{order}{item}; காரணம்: {category}; விவரம்: “{desc}”. சமர்ப்பிக்க “ஆம்” என்று சொல்லுங்கள் (அல்லது உறுதிசெய் பொத்தானைத் தட்டுங்கள்), வேண்டாமென்றால் “ரத்து”.",
               "hi": "भेजने से पहले जाँच लें: {kind}{order}{item}; कारण: {category}; विवरण: “{desc}”। भेजने के लिए “हाँ” कहें (या पुष्टि करें दबाएँ), या “रद्द” कहें।"},
    "return_ok": {"en": "Order {n} was delivered on {date}; under the store's {days}-day policy a return can be requested until {until}.",
                  "ta": "ஆர்டர் {n} {date} அன்று டெலிவரி ஆனது; கடையின் {days} நாள் கொள்கைப்படி {until} வரை திருப்பி அனுப்பக் கோரலாம்.",
                  "hi": "ऑर्डर {n} {date} को डिलीवर हुआ; स्टोर की {days} दिन की नीति के अनुसार {until} तक वापसी का अनुरोध किया जा सकता है।"},
    "about_order": {"en": " — order {n}", "ta": " — ஆர்டர் {n}", "hi": " — ऑर्डर {n}"},
    "about_item": {"en": ", item {n}", "ta": ", பொருள் {n}", "hi": ", सामान {n}"},
    "escalation_note": {"en": " This records a request for the {store} team to review — no one is live in this chat right now.",
                        "ta": " இது {store} குழு பரிசீலிக்க ஒரு கோரிக்கையைப் பதிவு செய்கிறது — இப்போது இந்த அரட்டையில் நேரடியாக யாரும் இல்லை.",
                        "hi": " इससे {store} टीम की समीक्षा के लिए अनुरोध दर्ज होता है — इस चैट में अभी कोई व्यक्ति लाइव नहीं है।"},
    "refund_note": {"en": " Refunds here are simulated: no real money is transferred.", "ta": " இங்கே பணத்திரும்பல் மாதிரி மட்டுமே: உண்மையான பணம் அனுப்பப்படாது.",
                    "hi": " यहाँ रिफंड सिम्युलेटेड है: कोई असली पैसा नहीं भेजा जाता।"},
    "submitted": {"en": "Submitted. Your {kind} reference is {ref}. Status: {status}.",
                  "ta": "சமர்ப்பிக்கப்பட்டது. உங்கள் {kind} குறிப்பு எண் {ref}. நிலை: {status}.",
                  "hi": "भेज दिया गया। आपके {kind} का संदर्भ नंबर {ref} है। स्थिति: {status}।"},
    "submitted_escalation": {"en": " It has been recorded for staff review; replies from the team will appear under My requests. This is not a live conversation with a person.",
                             "ta": " இது ஊழியர் பரிசீலனைக்காகப் பதிவு செய்யப்பட்டுள்ளது; குழுவின் பதில்கள் “என் கோரிக்கைகள்” பகுதியில் தெரியும். இது ஒருவருடன் நேரடி உரையாடல் அல்ல.",
                             "hi": " इसे स्टाफ़ की समीक्षा के लिए दर्ज कर लिया गया है; टीम के जवाब “मेरे अनुरोध” में दिखेंगे। यह किसी व्यक्ति से लाइव बातचीत नहीं है।"},
    "not_submitted": {"en": "Nothing was submitted: {reason}", "ta": "எதுவும் சமர்ப்பிக்கப்படவில்லை: {reason}", "hi": "कुछ भी नहीं भेजा गया: {reason}"},
    "duplicate": {"en": "You already have an open request for this: {ref}. Nothing new was submitted.",
                  "ta": "இதற்கு ஏற்கனவே ஒரு திறந்த கோரிக்கை உள்ளது: {ref}. புதிதாக எதுவும் சமர்ப்பிக்கப்படவில்லை.",
                  "hi": "इसके लिए आपका एक अनुरोध पहले से खुला है: {ref}। कुछ नया नहीं भेजा गया।"},
    "cancelled": {"en": "OK — nothing was submitted.", "ta": "சரி — எதுவும் சமர்ப்பிக்கப்படவில்லை.", "hi": "ठीक है — कुछ भी नहीं भेजा गया।"},
    "didnt_get": {"en": "Sorry, I didn't catch which one. ", "ta": "மன்னிக்கவும், எதைச் சொன்னீர்கள் என்று புரியவில்லை. ", "hi": "माफ़ कीजिए, समझ नहीं पाया कि कौन सा। "},
    "status_none": {"en": "You don't have any customer-care requests yet.", "ta": "உங்களிடம் இன்னும் வாடிக்கையாளர் சேவைக் கோரிக்கைகள் இல்லை.",
                    "hi": "आपका अभी कोई ग्राहक सेवा अनुरोध नहीं है।"},
    "status_not_found": {"en": "I couldn't find request {ref} on your account.", "ta": "உங்கள் கணக்கில் {ref} கோரிக்கை இல்லை.",
                         "hi": "आपके अकाउंट में अनुरोध {ref} नहीं मिला।"},
    "status_line": {"en": "{ref} ({kind}{about}): {status}.", "ta": "{ref} ({kind}{about}): {status}.", "hi": "{ref} ({kind}{about}): {status}।"},
    "status_reply": {"en": " Latest reply from the team: “{msg}”", "ta": " குழுவின் சமீபத்திய பதில்: “{msg}”", "hi": " टीम का ताज़ा जवाब: “{msg}”"},
    "status_signin": {"en": "Please sign in so I can look up your requests.", "ta": "உங்கள் கோரிக்கைகளைப் பார்க்க உள்நுழையுங்கள்.",
                      "hi": "अपने अनुरोध देखने के लिए साइन इन करें।"},
    "btn_confirm": {"en": "Confirm and submit", "ta": "உறுதிசெய்து சமர்ப்பி", "hi": "पुष्टि करें और भेजें"},
    "btn_cancel": {"en": "Cancel", "ta": "ரத்து", "hi": "रद्द करें"},
    "btn_no_order": {"en": "No order", "ta": "ஆர்டர் இல்லை", "hi": "कोई ऑर्डर नहीं"},
    "btn_whole": {"en": "Whole order", "ta": "முழு ஆர்டர்", "hi": "पूरा ऑर्डर"},
    "btn_view": {"en": "View {ref}", "ta": "{ref} பார்க்க", "hi": "{ref} देखें"},
    "btn_requests": {"en": "My requests", "ta": "என் கோரிக்கைகள்", "hi": "मेरे अनुरोध"},
    "btn_complaint": {"en": "Report a problem", "ta": "பிரச்சினையைப் புகாரளி", "hi": "समस्या बताएँ"},
    "btn_human": {"en": "Ask for human help", "ta": "மனித உதவி கேள்", "hi": "मानव सहायता माँगें"},
    "say_yes": {"en": "yes", "ta": "ஆம்", "hi": "हाँ"},
    "say_cancel": {"en": "cancel", "ta": "ரத்து", "hi": "रद्द"},
    "say_no_order": {"en": "no order", "ta": "இல்லை", "hi": "नहीं"},
    "say_whole": {"en": "whole order", "ta": "முழு ஆர்டர்", "hi": "पूरा ऑर्डर"},
    "say_complaint": {"en": "I want to report a problem", "ta": "நான் ஒரு புகார் அளிக்க வேண்டும்", "hi": "मुझे शिकायत करनी है"},
    "say_human": {"en": "I need human help", "ta": "எனக்கு மனித உதவி வேண்டும்", "hi": "मुझे मानव सहायता चाहिए"},
}
REASONS = {   # ineligibility reasons, by code (the server's English message is used for English)
    "not_delivered": {"ta": "ஆர்டர் இன்னும் டெலிவரி ஆகவில்லை.", "hi": "ऑर्डर अभी डिलीवर नहीं हुआ है।"},
    "window_passed": {"ta": "கடையின் திருப்பி அனுப்பும் காலம் ({days} நாட்கள்) முடிந்துவிட்டது.", "hi": "स्टोर की वापसी अवधि ({days} दिन) खत्म हो गई है।"},
    "window_unknown": {"ta": "கடையின் கொள்கையில் திருப்பி அனுப்பும் காலம் குறிப்பிடப்படவில்லை.", "hi": "स्टोर की नीति में वापसी अवधि नहीं बताई गई है।"},
    "not_paid": {"ta": "இந்த ஆர்டருக்குப் பணம் செலுத்தியதாகப் பதிவு இல்லை.", "hi": "इस ऑर्डर का कोई पूरा भुगतान दर्ज नहीं है।"},
}
REASONS_EN = {"not_delivered": "the order hasn't been delivered yet.", "window_passed": "the store's {days}-day return window has passed.",
              "window_unknown": "the store's policy doesn't state a return window.", "not_paid": "there is no completed payment recorded for it."}


def t(lang: str, key: str, **values) -> str:
    return T[key].get(lang, T[key]["en"]).format(**values)


def _status_name(lang: str, status: str) -> str:
    return care.STATUS_LABELS[status] if lang == "en" else STATUS_NAMES.get(status, {}).get(lang, care.STATUS_LABELS[status])


def _reason(lang: str, elig: dict[str, Any]) -> str:
    code = elig.get("reason") or "not_paid"
    if lang == "en":
        return REASONS_EN.get(code, "").format(days=elig.get("days", ""))
    return REASONS.get(code, {}).get(lang, REASONS_EN.get(code, "")).format(days=elig.get("days", ""))


def _reply(label: str, text: str) -> dict[str, str]:
    """A button that sends `text` as the customer's next message (nothing happens until the server handles it)."""
    return {"type": "reply", "label": label, "text": text}


# ---- the flow ---------------------------------------------------------------------------------------------------------------------
class CareFlow:
    def handle(self, store: StoreId, message: str, principal, lang: str, draft: dict[str, Any] | None,
               history: list[dict[str, str]]) -> dict[str, Any] | None:
        """None = not a customer-care request turn (the normal assistant answers; any draft is kept by the caller)."""
        draft = self._clean_draft(draft)
        found = detect(message)
        # A cancel while a draft is waiting.
        if draft and _CANCEL.search(message):
            return self._out(t(lang, "cancelled"), None, ["care_cancelled"])
        # A status question (never starts a draft).
        if found and found.get("status") and not (draft and draft.get("step") == "description"):
            return self._status(store, principal, lang, found, draft)
        if draft is None:
            if not found or not found.get("kind"):
                return None
            draft = {"kind": found["kind"], "order": None, "no_order": False, "item_id": None, "whole_order": False,
                     "category": infer_category(found["kind"], message), "description": None, "step": None, "key": None}
            m = _ORDER.search(message)
            if m:
                draft["order"] = self._order_number(store, m)
            if len(message.split()) >= 10:   # a real explanation, in the customer's own words, is the description (shown at review)
                draft["description"] = care._clean(message, 1000)
            starting = True
        else:
            # Mid-request, only an explicit ask for a person switches the request type (an answer such as "Damaged product"
            # to a refund's reason question must not turn the refund into a complaint).
            if found and found.get("kind") == "escalation" and draft["kind"] != "escalation" and draft.get("step") != "description":
                draft = {"kind": found["kind"], "order": draft.get("order"), "no_order": False, "item_id": None, "whole_order": False,
                         "category": infer_category(found["kind"], message), "description": None, "step": None, "key": None}
                starting = True
            else:
                starting = False
        kind_name = KIND_NAMES[draft["kind"]][lang]
        if principal is None and not starting and not found:
            # A signed-out customer with a request waiting for sign-in asked something else ("Trailhead 55L Backpack",
            # "what are your hours?"): answer that normally and keep the request for after sign-in.
            return None
        if principal is None:
            text = t(lang, "signin", kind=kind_name)
            if draft["kind"] == "escalation":
                from .. import repositories as repo
                prof = repo.get_store_profile(store) or {}
                text += t(lang, "signin_human_alt", store=STORE_BRANDING[store]["name"], email=prof.get("support_email", ""),
                          hours=prof.get("support_hours", ""))
            return self._out(text, draft, ["care_" + draft["kind"]], requires_login=True,
                             actions=[{"type": "link", "to": "/account", "label": {"en": "Sign in", "ta": "உள்நுழைக", "hi": "साइन इन"}[lang]}])
        if principal.role != "customer":
            return self._out(t(lang, "staff"), None, ["care_" + draft["kind"]])
        if not starting:
            # None = not an answer to the pending question (a different question): the normal assistant answers it and
            # the draft is kept for the next turn.
            return self._apply_answer(store, principal, lang, draft, message)
        return self._next(store, principal, lang, draft, lead=t(lang, "start", kind=kind_name) if starting else "")

    # -- draft handling ------------------------------------------------------------------------------------------------
    @staticmethod
    def _clean_draft(d: Any) -> dict[str, Any] | None:
        if not isinstance(d, dict) or d.get("kind") not in care.KINDS:
            return None
        out = {"kind": d["kind"], "step": d.get("step") if d.get("step") in ("order", "item", "category", "description", "confirm") else None,
               "order": d["order"].upper() if isinstance(d.get("order"), str) and re.fullmatch(r"[A-Za-z]{2}-\d{5}", d["order"]) else None,
               "no_order": d.get("no_order") is True, "whole_order": d.get("whole_order") is True, "noted": d.get("noted") is True,
               "item_id": d["item_id"] if isinstance(d.get("item_id"), int) and not isinstance(d.get("item_id"), bool) else None,
               "category": d["category"] if d.get("category") in care.CATEGORIES[d["kind"]] else None,
               "description": care._clean(d["description"], 1000) if isinstance(d.get("description"), str) and d["description"].strip() else None,
               "key": d["key"] if isinstance(d.get("key"), str) and re.fullmatch(r"chat_[A-Za-z0-9_-]{16,40}", d["key"]) else None,
               "choices": [c for c in d.get("choices", []) if isinstance(c, (str, int)) and not isinstance(c, bool)][:6]
               if isinstance(d.get("choices"), list) else []}
        return out

    @staticmethod
    def _order_number(store: StoreId, m: re.Match) -> str:
        digits = m.group(2) or m.group(3)
        return f"{ORDER_PREFIX[store]}{digits}"

    def _pick(self, message: str, choices: list) -> Any:
        for i, rx in enumerate(_ORDINALS):
            if i < len(choices) and re.search(rx, message, re.I):
                return choices[i]
        return None

    def _apply_answer(self, store, principal, lang, draft, message) -> dict[str, Any] | None:
        step = draft.get("step")
        if step == "confirm":
            if _YES.search(message):
                return self._submit(store, principal, lang, draft)
            if _NO.search(message):
                return self._out(t(lang, "cancelled"), None, ["care_cancelled"])
            return None                                  # something else: the normal assistant answers; draft kept
        if step == "order":
            m = _ORDER.search(message)
            if m:
                draft["order"] = self._order_number(store, m)
            elif draft["kind"] in ("complaint", "escalation") and _NO.search(message):
                draft["no_order"] = True
            else:
                picked = self._pick(message, draft["choices"])
                if picked is None:
                    return None if self._unrelated(message) else self._next(store, principal, lang, draft, lead=t(lang, "didnt_get"))
                draft["order"] = picked
        elif step == "item":
            if draft["kind"] != "return" and _NO.search(message):
                draft["whole_order"] = True
            else:
                picked = self._pick(message, draft["choices"])
                if picked is None:
                    names = self._item_names(store, principal, draft)
                    picked = next((i for i, n in names.items() if n.lower() in message.lower()), None)
                if picked is None:
                    return None if self._unrelated(message) else self._next(store, principal, lang, draft, lead=t(lang, "didnt_get"))
                draft["item_id"] = int(picked)
        elif step == "category":
            cats = care.CATEGORIES[draft["kind"]]
            picked = self._pick(message, draft["choices"]) or infer_category(draft["kind"], message)
            if picked is None:
                picked = next((c for c in cats if any(n.lower() == message.strip().lower().rstrip(".") for n in CATEGORY_NAMES[c].values())), None)
            if picked is None:
                return None if self._unrelated(message) else self._next(store, principal, lang, draft, lead=t(lang, "didnt_get"))
            draft["category"] = picked
        elif step == "description":
            draft["description"] = care._clean(message, 1000)
        return self._next(store, principal, lang, draft)

    @staticmethod
    def _unrelated(message: str) -> bool:
        """A different question asked in the middle of a request ("what tents do you have?"): answered normally, draft kept."""
        from .intent import detect_intent
        return bool(detect_intent(message).intents - {"complaint", "damaged", "defective", "return_request", "refund", "human",
                                                     "frustration", "exchange", "ticket"})

    def _item_names(self, store, principal, draft) -> dict[int, str]:
        try:
            opts = care.options(store, principal.customer_id, draft["kind"], draft["order"])
        except CommerceError:
            return {}
        return {i["id"]: i["name"] for i in opts["items"]}

    def _next(self, store, principal, lang, draft, lead: str = "") -> dict[str, Any]:
        """Ask for the next missing piece, or show the review."""
        kind = draft["kind"]
        kind_name = KIND_NAMES[kind][lang]
        lead = (lead + " ") if lead and not lead.endswith(" ") else lead
        # 1. order
        if draft["order"] is None and not draft["no_order"]:
            opts = care.options(store, principal.customer_id, kind)
            eligible = [o for o in opts["orders"] if o["eligible"]]
            if not opts["orders"] and kind in ("complaint", "escalation"):
                draft["no_order"] = True
            elif not eligible:
                if not opts["orders"]:
                    return self._out(lead + t(lang, "no_orders") + " " + t(lang, "offer_other"), None, ["care_" + kind],
                                     actions=self._other_routes(lang))
                return self._out(lead + t(lang, "none_eligible", kind=kind_name, reason=_reason(lang, opts["orders"][0])) + " "
                                 + t(lang, "offer_other"), None, ["care_" + kind], actions=self._other_routes(lang))
            elif kind in ("return", "refund") and len(eligible) == 1:
                draft["order"] = eligible[0]["order_number"]
            else:
                shown = eligible[:4]
                draft["step"], draft["choices"] = "order", [o["order_number"] for o in shown]
                text = lead + t(lang, "ask_order", list=", ".join(f"{i + 1}) {o['order_number']}" for i, o in enumerate(shown)))
                actions = [_reply(o["order_number"], o["order_number"]) for o in shown]
                if kind in ("complaint", "escalation"):
                    text += t(lang, "ask_order_optional")
                    actions.append(_reply(t(lang, "btn_no_order"), t(lang, "say_no_order")))
                return self._out(text, draft, ["care_" + kind], actions=actions + [_reply(t(lang, "btn_cancel"), t(lang, "say_cancel"))])
        # the order must still be the customer's own and eligible (re-checked on every turn)
        if draft["order"]:
            try:
                opts = care.options(store, principal.customer_id, kind, draft["order"])
            except CommerceError as e:
                draft["order"], draft["step"] = None, None
                return self._next(store, principal, lang, draft, lead=lead + (e.message if lang == "en" else t(lang, "didnt_get")))
            if not opts["order"]["eligible"]:
                return self._out(lead + t(lang, "none_eligible", kind=kind_name, reason=_reason(lang, opts["order"])) + " "
                                 + t(lang, "offer_other"), None, ["care_" + kind], actions=self._other_routes(lang))
            if kind == "return" and not draft.get("noted") and opts["order"].get("until"):
                # Say once what the eligibility is based on: the delivery date on record and the store's own policy window.
                from datetime import date, timedelta
                until = date.fromisoformat(opts["order"]["until"])
                lead += t(lang, "return_ok", n=draft["order"], date=(until - timedelta(days=opts["order"]["days"])).isoformat(),
                          days=opts["order"]["days"], until=until.isoformat()) + " "
                draft["noted"] = True
            items = opts["items"]
            # 2. item (returns need one; complaints may be about the whole order; refunds and escalations are per order)
            if draft["item_id"] is None and not draft["whole_order"] and kind in ("return", "complaint"):
                if len(items) == 1:
                    draft["item_id"] = items[0]["id"]
                elif items:
                    draft["step"], draft["choices"] = "item", [i["id"] for i in items[:4]]
                    text = lead + t(lang, "ask_item", list=", ".join(f"{n + 1}) {i['name']}" for n, i in enumerate(items[:4])))
                    actions = [_reply(i["name"], i["name"]) for i in items[:4]]
                    if kind == "complaint":
                        text += t(lang, "ask_item_optional")
                        actions.append(_reply(t(lang, "btn_whole"), t(lang, "say_whole")))
                    return self._out(text, draft, ["care_" + kind], actions=actions)
            if draft["item_id"] is not None and draft["item_id"] not in {i["id"] for i in items}:
                draft["item_id"], draft["step"] = None, None
                return self._next(store, principal, lang, draft)
        # 3. reason
        if draft["category"] is None:
            cats = list(care.CATEGORIES[kind])
            draft["step"], draft["choices"] = "category", cats
            return self._out(lead + t(lang, "ask_category", list=", ".join(f"{n + 1}) {CATEGORY_NAMES[c][lang]}" for n, c in enumerate(cats))),
                             draft, ["care_" + kind], actions=[_reply(CATEGORY_NAMES[c][lang], CATEGORY_NAMES[c][lang]) for c in cats])
        # 4. description
        if not draft["description"]:
            draft["step"], draft["choices"] = "description", []
            return self._out(lead + t(lang, "ask_description"), draft, ["care_" + kind],
                             actions=[_reply(t(lang, "btn_cancel"), t(lang, "say_cancel"))])
        # 5. review → explicit confirmation
        draft["step"], draft["choices"] = "confirm", []
        draft["key"] = draft["key"] or f"chat_{secrets.token_urlsafe(18)}"
        item_name = self._item_names(store, principal, draft).get(draft["item_id"]) if draft["item_id"] else None
        text = lead + t(lang, "review", kind=kind_name[:1].upper() + kind_name[1:],
                        order=t(lang, "about_order", n=draft["order"]) if draft["order"] else "",
                        item=t(lang, "about_item", n=item_name) if item_name else "",
                        category=CATEGORY_NAMES[draft["category"]][lang], desc=draft["description"])
        if kind == "escalation":
            text += t(lang, "escalation_note", store=STORE_BRANDING[store]["name"])
        if kind == "refund":
            text += t(lang, "refund_note")
        return self._out(text, draft, ["care_" + kind, "care_review"],
                         actions=[_reply(t(lang, "btn_confirm"), t(lang, "say_yes")), _reply(t(lang, "btn_cancel"), t(lang, "say_cancel"))])

    def _submit(self, store, principal, lang, draft) -> dict[str, Any]:
        """Only after an explicit yes. Success is reported ONLY with the reference the database returned."""
        kind = draft["kind"]
        try:
            view, _created = care.create(store, principal.customer_id, kind=kind, category=draft["category"],
                                         description=draft["description"] or "", order_number=draft["order"],
                                         item_id=draft["item_id"], idempotency_key=draft["key"])
        except CommerceError as e:
            if e.code == "duplicate_request":
                ref = (e.details or [{}])[0].get("issue", "")
                return self._out(t(lang, "duplicate", ref=ref), None, ["care_" + kind, "care_not_submitted"],
                                 actions=[{"type": "link", "to": f"/support/requests/{ref}", "label": t(lang, "btn_view", ref=ref)}])
            reason = e.message if lang == "en" else _reason(lang, {"reason": (e.details or [{}])[0].get("issue")}) or t(lang, "didnt_get")
            return self._out(t(lang, "not_submitted", reason=reason), None, ["care_" + kind, "care_not_submitted"],
                             actions=self._other_routes(lang))
        ref = view["reference"]
        text = t(lang, "submitted", kind=KIND_NAMES[kind][lang], ref=ref, status=_status_name(lang, view["status"]))
        if kind == "escalation":
            text += t(lang, "submitted_escalation")
        if kind == "refund":
            text += t(lang, "refund_note")
        return self._out(text, None, ["care_" + kind, "care_submitted"], reference=ref,
                         actions=[{"type": "link", "to": f"/support/requests/{ref}", "label": t(lang, "btn_view", ref=ref)}])

    def _status(self, store, principal, lang, found, draft) -> dict[str, Any]:
        if principal is None or principal.role != "customer":
            return self._out(t(lang, "status_signin"), draft, ["care_status"], requires_login=principal is None)
        if found.get("reference"):
            try:
                rows = [care.get_for_customer(store, principal.customer_id, found["reference"])]
            except CommerceError:
                return self._out(t(lang, "status_not_found", ref=found["reference"]), draft, ["care_status"])
        else:
            rows = care.list_for_customer(store, principal.customer_id, found.get("kind"))[:3]
            rows = [care.get_for_customer(store, principal.customer_id, r["reference"]) for r in rows]
        if not rows:
            if found.get("fallback"):
                return None          # no refund request: the assistant's payment-record answer applies
            return self._out(t(lang, "status_none"), draft, ["care_status"], actions=self._other_routes(lang))
        lines = []
        for r in rows:
            about = t(lang, "about_order", n=r["order_number"]) if r["order_number"] else ""
            line = t(lang, "status_line", ref=r["reference"], kind=KIND_NAMES[r["kind"]][lang], about=about,
                     status=_status_name(lang, r["status"]))
            staff = [u for u in r["updates"] if u["by"] == "staff" and u["message"]]
            if staff:
                line += t(lang, "status_reply", msg=staff[-1]["message"])
            lines.append(line)
        return self._out(" ".join(lines), draft, ["care_status"],
                         actions=[{"type": "link", "to": f"/support/requests/{r['reference']}", "label": t(lang, "btn_view", ref=r["reference"])} for r in rows]
                         + [{"type": "link", "to": "/support/requests", "label": t(lang, "btn_requests")}])

    @staticmethod
    def _other_routes(lang: str) -> list[dict[str, str]]:
        return [_reply(t(lang, "btn_complaint"), t(lang, "say_complaint")), _reply(t(lang, "btn_human"), t(lang, "say_human"))]

    @staticmethod
    def _out(reply: str, draft, intents: list[str], *, actions=None, requires_login: bool = False, reference: str | None = None) -> dict[str, Any]:
        public = None
        if draft:   # only what the next turn needs; validated again when it comes back
            public = {k: draft.get(k) for k in ("kind", "step", "order", "no_order", "item_id", "whole_order", "noted", "category",
                                                "description", "key", "choices")}
        return {"reply": reply.strip(), "care_draft": public, "intents": intents, "actions": actions or [],
                "requires_login": requires_login, "care_reference": reference}
