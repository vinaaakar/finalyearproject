"""Deterministic intent detection and search-term extraction.

The backend — not the language model — decides which data to fetch. These rules
pick the intents; the service then calls fixed repository functions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .language import ROMANIZED

ORDER_NUMBER_RE = re.compile(r"\b([A-Za-z]{2})[-\s]?(\d{5})\b")

# ---- budgets ("under $50", "below ₹5,000", "Rs. 5000 க்குள்", "5000 रुपये से कम") ---------------------------
# The currency is kept, never assumed to be the catalogue's: comparing a rupee budget with dollar prices
# would need an exchange rate, and the assistant must not invent one (see Assistant.gather).
_INR = r"₹|\brs\b\.?|\binr\b|\brupees?\b|\brupaye\b|ரூபாய்|ரூ\.|रुपये|रुपए|रुपया|रु\."
_USD = r"\$|\busd\b|\bdollars?\b|டாலர்|डॉलर"
_CUR = rf"(?:{_INR}|{_USD})"
_AMOUNT = r"(?P<whole>\d{1,3}(?:,\d{2,3})+|\d+)(?:\.(?P<frac>\d{1,2}))?(?P<k>\s*k\b)?"
_EN_LIMIT = r"under|below|less than|cheaper than|max(?:imum)?|up to|at most|within|not more than|no more than|budget(?: is| of)?"
_NATIVE_LIMIT = (r"க்குள்|க்குக்?\s*கீழ்|க்குக்?\s*குறைவா|से\s*कम|के\s*अंदर|के\s*भीतर|तक\s*का|तक\s*की|kulla|keezh|se\s*kam|"
                 r"ke\s*andar")
BUDGET_RE = re.compile(rf"\b(?:{_EN_LIMIT})\s*:?\s*(?P<pre>{_CUR})?\s*{_AMOUNT}\s*(?P<post>{_CUR})?", re.I)
_NATIVE_BUDGET_RE = re.compile(rf"(?P<pre>{_CUR})?\s*{_AMOUNT}\s*(?P<post>{_CUR})?\s*-?\s*(?:{_NATIVE_LIMIT})", re.I)
# An amount with an explicit currency and no limit word ("a backpack for ₹5000", "INR 5000 tent") is also a budget.
_PRICED_RE = re.compile(rf"(?P<pre>{_CUR})\s*{_AMOUNT}(?P<post>)|{_AMOUNT.replace('?P<', '?P<b_')}\s*(?P<b_post>{_INR}|\busd\b|\bdollars?\b)", re.I)
# "under 2 kg", "within 3 days", "up to 4 people" are not budgets.
_UNIT_AFTER = re.compile(r"\s*(?:kg|kgs|g|grams?|l|litres?|liters?|ml|oz|lbs?|mm|cm|km|m|days?|hours?|hrs?|minutes?|mins?|weeks?|"
                         r"months?|years?|lumens?|people|persons?|person|°|degrees?|f|c|%|percent|items?|pieces?|pcs)\b", re.I)


@dataclass(frozen=True)
class Budget:
    amount_minor: int          # in hundredths of the stated currency
    currency: str | None       # "INR", "USD" or None (no currency stated)
    span: tuple[int, int]      # where it was found in the message
    limit_word: bool = True    # False for "a backpack for ₹5000" (an amount with a currency but no "under"/"below")


def _currency_of(token: str | None) -> str | None:
    if not token:
        return None
    return "USD" if re.fullmatch(_USD, token.strip(), re.I) else "INR"


def parse_budget(message: str) -> Budget | None:
    """The first spending limit in the message, with its currency if one was stated."""
    for rx in (BUDGET_RE, _NATIVE_BUDGET_RE):
        for m in rx.finditer(message):
            currency = _currency_of(m.group("pre") or m.group("post"))
            if currency is None and _UNIT_AFTER.match(message, m.end()):
                continue
            whole, frac, thousands = m.group("whole"), m.group("frac"), m.group("k")
            units = int(whole.replace(",", "")) * (1000 if thousands else 1)
            if not 0 < units <= 10_000_000:
                continue
            minor = units * 100 + (int(frac.ljust(2, "0")) if frac else 0)
            return Budget(minor, currency, m.span())
    for m in _PRICED_RE.finditer(message):
        g = (lambda k: m.group(k) or m.group("b_" + k)) if m.group("whole") is None else m.group
        token = m.group("pre") if m.group("whole") is not None else m.group("b_post")
        units = int(g("whole").replace(",", "")) * (1000 if g("k") else 1)
        if 0 < units <= 10_000_000:
            return Budget(units * 100 + (int(g("frac").ljust(2, "0")) if g("frac") else 0), _currency_of(token), m.span(), False)
    return None

_KEYWORDS: dict[str, tuple[str, ...]] = {
    "order_status": ("my order", "order status", "track", "tracking", "where is my", "where's my", "package", "parcel",
                     "has it shipped", "when will it arrive", "when will my", "my orders", "order number", "delivery status"),
    "shipping": ("shipping", "ship ", "ships", "delivery", "deliver", "postage", "how long does it take", "expedited"),
    "returns": ("return", "refund", "exchange", "send back", "money back"),
    "warranty": ("warranty", "defect", "broken", "guarantee"),
    "payment": ("payment", "pay with", "pay by", "pay using", "paypal", "apple pay", "google pay", "credit card", "debit card", "gift card",
                " upi", "cash on delivery", " cod ", "net banking", "netbanking", "wallet", "razorpay", "payment method"),
    "stock": ("in stock", "stock", "available", "availability", "sold out", "have any left", "inventory"),
    "price": ("price", "cost", "how much", "cheap", "expensive", "budget", "under $", "$", "₹", " rs ", " rs.", "rupee", " inr "),
    "product": ("recommend", "looking for", "do you have", "do you sell", "need a", "need some", "suggest", "best", "show me", "tell me about"),
    "cart": ("my cart", "in my cart", "my basket", "in my basket", "cart total", "shopping cart"),
    "contact": ("human", "agent", "representative", "real person", "speak to someone", "talk to someone", "contact", "phone number", "email you", "hours"),
    "greeting": (" hello", " hi ", " hi,", " hi!", " hey", "good morning", "good evening"),
}

# Tamil, Hindi and romanized keywords for the same intents (merged into _KEYWORDS below).
_KEYWORDS_I18N: dict[str, tuple[str, ...]] = {
    "order_status": ("ஆர்டர்", "டிராக்", "பார்சல்", "எப்போது வரும்", "வந்து சேரும்", "ऑर्डर", "आर्डर", "और्डर", "ट्रैक", "पार्सल", "कब आएगा",
                     "कब पहुँचेगा", "कब पहुंचेगा", "order enga", "order kahan", "kab aayega", "kab aaega"),
    "shipping": ("ஷிப்பிங்", "டெலிவரி", "அனுப்புவீர்கள்", "அனுப்ப எவ்வளவு", "शिपिंग", "डिलीवरी", "डिलिवरी", "भेजने"),
    "returns": ("ரிட்டர்ன்", "திருப்பி", "பணம் திரும்ப", "ரீஃபண்ட்", "रिटर्न", "वापस", "रिफ़ंड", "रिफंड", "लौटा", "wapas", "vapas", "thirupi"),
    "warranty": ("வாரண்டி", "உத்தரவாதம்", "குறைபாடு", "பழுது", "वारंटी", "गारंटी", "खराब", "दोष"),
    "payment": ("பணம் செலுத்த", "பேமெண்ட்", "கார்டு", "भुगतान", "पेमेंट", "कार्ड"),
    "stock": ("ஸ்டாக்", "கையிருப்பு", "கிடைக்குமா", "இருக்கிறதா", "உள்ளதா", "स्टॉक", "उपलब्ध", "मिलेगा", "है क्या", "irukka", "kidaikkuma",
              "hai kya", "milega"),
    "price": ("விலை", "எவ்வளவு", "மலிவான", "कीमत", "दाम", "कितना", "कितने", "कितनी", "सस्ता", "evvalavu", "evlo", "vilai", "kitna",
              "kitne", "kimat", "keemat", "daam"),
    "product": ("பரிந்துரை", "வேண்டும்", "தேவை", "காட்டுங்கள்", "பற்றி சொல்", "सुझाव", "चाहिए", "दिखाओ", "दिखाइए", "के बारे में", "venum",
                "vendum", "chahiye"),
    "cart": ("கார்ட்", "கூடையில்", "कार्ट", "टोकरी"),
    "contact": ("தொடர்பு", "மனிதர்", "ஏஜென்ட்", "பிரதிநிதி", "संपर्क", "एजेंट", "इंसान", "प्रतिनिधि"),
    "greeting": ("வணக்கம்", "नमस्ते", "नमस्कार", "vanakkam", "namaste"),
}
for _name, _words in _KEYWORDS_I18N.items():
    _KEYWORDS[_name] = _KEYWORDS[_name] + _words

# Tamil / Hindi product words → English catalog search terms (the catalogs are in English).
PRODUCT_LEXICON: dict[str, str] = {
    "இரண்டு பேர்": "2-person", "2 பேர்": "2-person", "இருவர்": "2-person", "நான்கு பேர்": "4-person",
    "दो लोगों": "2-person", "दो लोग": "2-person", "2 लोगों": "2-person", "चार लोगों": "4-person",
    "கூடாரம்": "tent", "டென்ட்": "tent", "टेंट": "tent", "तंबू": "tent",
    "ஸ்லீப்பிங் பேக்": "sleeping", "தூக்கப் பை": "sleeping", "स्लीपिंग बैग": "sleeping",
    "மெத்தை": "pad", "पैड": "pad",
    "பேக்பேக்": "pack", "முதுகுப் பை": "pack", "பை": "pack", "बैकपैक": "pack", "बैग": "pack",
    "பூட்ஸ்": "boot", "காலணி": "boot", "ஷூ": "boot", "जूते": "boot", "बूट": "boot",
    "ஜாக்கெட்": "jacket", "जैकेट": "jacket", "மழை": "rain", "बारिश": "rain",
    "அடுப்பு": "stove", "ஸ்டவ்": "stove", "स्टोव": "stove", "चूल्हा": "stove",
    "விளக்கு": "lamp", "ஹெட்லேம்ப்": "lamp", "டார்ச்": "lamp", "लैंप": "lamp", "टॉर्च": "lamp", "हेडलैंप": "lamp",
    "காபி": "coffee", "कॉफ़ी": "coffee", "कॉफी": "coffee", "பீன்ஸ்": "bean", "बीन्स": "bean",
    "தேநீர்": "tea", "டீ": "tea", "चाय": "tea", "சாய்": "chai",
    "கிரைண்டர்": "grinder", "ग्राइंडर": "grinder", "கெட்டில்": "kettle", "केतली": "kettle",
    "பிரஸ்": "press", "प्रेस": "press", "டிரிப்பர்": "dripper", "ड्रिपर": "dripper",
    "கோப்பை": "mug", "மக்": "mug", "मग": "mug", "தேன்": "honey", "शहद": "honey",
}
_STOPWORDS = set(
    """a an the and or but if of for to in on at by with from about as is are was were be been am do does did
    i me my mine you your we our us it its this that these those what which who whom how when where why can could
    would should will shall may might must have has had any some much many more most less very just also than too
    please thanks thank hello hi hey there here want wanted need looking look show tell know like get got buy
    sell price cost costs stock available availability recommend suggest something good best cheap expensive item
    items product products store shop order orders today now one ones help question under below less dollar dollars
    gift gifts idea ideas around cheaper max maximum most budget spend add put cart basket take compare comparison
    versus difference differences between better which similar alternative alternatives instead else options
    other another cheapest affordable expensive lower within rupee rupees inr usd anything everything""".split()
) | {w for words in ROMANIZED.values() for w in words}


_POLICY_INTENTS = {"shipping", "returns", "warranty", "payment"}
_POLICY_WORDS = {"shipping", "ship", "deliver", "delivery", "postage", "expedited", "return", "refund", "exchange",
                 "warranty", "guarantee", "payment", "pay", "policy", "policie", "long", "take", "fee", "charge"}


_SCRIPTS = {"ta": re.compile(r"[\u0B80-\u0BFF]"), "hi": re.compile(r"[\u0900-\u097F]")}
LANGUAGE_NAMES = {"ta": "Tamil", "hi": "Hindi"}


def script_language(text: str) -> str | None:
    """'ta' / 'hi' when the message is mostly written in Tamil or Devanagari script."""
    letters = [ch for ch in text if ch.isalpha()]
    for code, rx in _SCRIPTS.items():
        if letters and sum(bool(rx.match(ch)) for ch in letters) / len(letters) > 0.5:
            return code
    return None


# ---- customer-care intents ---------------------------------------------------------------------
# Matched on whole words for Latin-script phrases (so "late" does not match "chocolate") and as plain
# substrings for Tamil / Devanagari phrases. English, Tamil, Hindi and common romanized forms.
CARE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "order_late": ("hasn't come", "hasnt come", "has not come", "not come yet", "hasn't arrived", "hasnt arrived", "has not arrived",
                   "not arrived", "not received", "haven't received", "havent received", "didn't receive", "didnt receive",
                   "never arrived", "never came", "still waiting", "late", "delayed", "delay", "taking too long", "lost",
                   "stuck", "not here yet", "where is it",
                   "வரவில்லை", "வந்து சேரவில்லை", "தாமதம்", "இன்னும் வரல", "காணவில்லை", "नहीं आया", "नहीं पहुँचा", "नहीं पहुंचा",
                   "देर", "अभी तक नहीं", "खो गया", "varala", "nahi aaya", "nahin aaya"),
    "delivered_missing": ("says delivered", "marked delivered", "marked as delivered", "shows delivered", "shows as delivered",
                          "delivered but", "status says delivered", "டெலிவரி ஆனதாக", "டெலிவரி செய்யப்பட்டதாக", "डिलीवर दिखा",
                          "डिलीवर बता", "delivered dikha"),
    "damaged": ("damaged", "arrived broken", "came broken", "broken when", "cracked", "smashed", "dented", "torn", "leaking",
                "சேதம்", "சேதமடை", "சேதமாக", "உடைந்து", "உடைந்த", "டேமேஜ்", "टूटा", "टूटी", "टूट", "क्षतिग्रस्त", "डैमेज", "kharab aaya"),
    "defective": ("defective", "faulty", "stopped working", "doesn't work", "does not work", "not working", "won't turn on",
                  "malfunction", "வேலை செய்யவில்லை", "பழுதான", "குறைபாடுள்ள", "काम नहीं कर", "ख़राब है", "खराब है", "डिफेक्ट"),
    "wrong_item": ("wrong item", "wrong product", "wrong size", "wrong colour", "wrong color", "not what i ordered", "different item",
                   "sent the wrong", "received the wrong", "got the wrong", "தவறான பொருள்", "வேறு பொருள்", "गलत सामान", "ग़लत सामान",
                   "गलत प्रोडक्ट", "गलत आइटम"),
    "missing_item": ("missing item", "item missing", "items missing", "missing from my order", "only got", "only received",
                     "part of my order", "partial", "not all items", "not all the items", "missing part", "missing piece",
                     "பொருள் குறைவு", "ஒரு பொருள் இல்லை", "சில பொருட்கள் வரவில்லை", "सामान कम", "एक आइटम नहीं", "कुछ सामान नहीं"),
    "cancel": ("cancel", "cancellation", "don't want it anymore", "dont want it anymore", "call off",
               "ரத்து", "கேன்சல்", "रद्द", "कैंसल", "cancel karna"),
    "modify_order": ("change my order", "modify my order", "edit my order", "change the address", "change my address", "wrong address",
                     "update the address", "update my address", "change delivery address", "change the delivery address",
                     "change shipping address", "change the shipping address", "add to my order", "change the quantity",
                     "முகவரியை மாற்ற", "ஆர்டரை மாற்ற", "पता बदल", "ऑर्डर बदल", "ऑर्डर में बदलाव"),
    "payment_issue": ("payment failed", "payment declined", "declined", "payment didn't", "payment did not", "couldn't pay",
                      "could not pay", "can't pay", "cannot pay", "unable to pay", "paid but", "i paid", "i've paid", "already paid",
                      "charged twice", "double charge", "double charged", "charged two times", "duplicate charge", "charged me twice",
                      "money was taken", "money deducted", "deducted", "payment status", "did my payment", "payment pending",
                      "payment go through", "nothing happened", "பணம் செலுத்தினேன்", "பணம் போச்சு", "பேமெண்ட் தோல்வி", "பணம் கழிக்கப்பட்டது",
                      "இரண்டு முறை", "भुगतान किया", "पैसे कट", "पेमेंट फेल", "भुगतान असफल", "दो बार", "पेमेंट नहीं हुआ", "paise kat"),
    "refund_status": ("refund status", "where is my refund", "where's my refund", "wheres my refund", "my refund", "refund not received",
                      "no refund", "refund yet", "get my refund", "got my refund", "receive my refund", "received my refund",
                      "waiting for my refund", "waiting for a refund", "refund delay", "refund delayed", "when will i get",
                      "ரீஃபண்ட் வரவில்லை", "பணம் திரும்ப வரவில்லை", "ரீஃபண்ட் எப்போது", "रिफंड नहीं मिला", "रिफ़ंड नहीं मिला",
                      "रिफंड कब", "रिफ़ंड कब", "पैसे वापस नहीं", "refund nahi"),
    "return_request": ("want a refund", "get a refund", "need a refund", "request a refund", "return this", "return it", "return my", "return an item", "return the", "want to return", "how do i return",
                       "how to return", "start a return", "make a return", "send it back", "send this back",
                       "திருப்பி அனுப்ப வேண்டும்", "ரிட்டர்ன் செய்ய", "वापस करना", "रिटर्न करना", "लौटाना है"),
    "exchange": ("exchange", "swap it", "swap for", "different size", "replacement", "replace it",
                 "மாற்றித் தர", "எக்ஸ்சேஞ்ச்", "बदलना है", "एक्सचेंज", "बदल दो", "रिप्लेसमेंट"),
    "account": ("sign in", "signin", "sign-in", "log in", "login", "logon", "register", "registration", "create an account",
                "create account", "sign up", "signup", "my account", "account details", "change my email", "change my name",
                "delete my account", "close my account", "password", "forgot", "reset",
                "உள்நுழை", "கணக்கு", "பாஸ்வேர்டு", "கடவுச்சொல்", "லாகின்", "रजिस्टर", "अकाउंट", "खाता", "पासवर्ड", "लॉगिन", "साइन इन"),
    "checkout_help": ("checkout", "check out", "place an order", "place order", "place my order", "how do i buy", "how to buy",
                      "how do i order", "how to order", "guest checkout", "without an account", "as a guest", "zip code", "zip",
                      "doesn't ship", "does not ship", "don't ship", "not ship to", "alaska", "hawaii", "invalid address",
                      "address error", "total changed", "price changed",
                      "செக்அவுட்", "ஆர்டர் செய்வது எப்படி", "வாங்குவது எப்படி", "चेकआउट", "ऑर्डर कैसे करें", "कैसे खरीद"),
    "compare": ("compare", "comparison", "difference between", "differences between", "vs", "versus", "which is better",
                "which one is better", "which one should i", "which should i",
                "ஒப்பிட", "வித்தியாசம்", "எது சிறந்தது", "तुलना", "फ़र्क", "फर्क", "अंतर", "कौन सा बेहतर", "कौन-सा बेहतर"),
    "cheaper": ("cheaper", "less expensive", "lower price", "more affordable", "budget option", "cheapest",
                "மலிவான", "குறைந்த விலை", "सस्ता", "सस्ती", "कम कीमत", "kam daam"),
    "alternative": ("something similar", "similar", "alternative", "alternatives", "instead", "something else", "other options",
                    "வேறு ஏதாவது", "மாற்று", "இதே மாதிரி", "कोई और", "दूसरा विकल्प", "विकल्प", "इसके जैसा"),
    "promotions": ("promo", "promotion", "promotions", "discount", "discounts", "coupon", "coupons", "voucher", "sale", "offers",
                   "special offer", "any offer", "deal", "deals", "தள்ளுபடி", "கூப்பன்", "ஆஃபர்", "छूट", "डिस्काउंट", "कूपन",
                   "ऑफ़र", "ऑफर"),
    "invoice": ("invoice", "receipt", "bill", "billing", "tax invoice", "gst", "ரசீது", "இன்வாய்ஸ்", "பில்", "बिल", "रसीद", "इनवॉइस"),
    "privacy": ("privacy", "personal data", "my data", "personal information", "gdpr", "what do you store", "do you record",
                "recording my", "is my voice", "audio stored", "data stored", "delete my data",
                "தனியுரிமை", "என் தரவு", "தனிப்பட்ட தகவல்", "गोपनीयता", "प्राइवेसी", "मेरा डेटा", "निजी जानकारी"),
    "languages": ("what languages", "which languages", "languages do you", "speak tamil", "speak hindi", "speak english",
                  "language support", "other languages", "which language",
                  "எந்த மொழி", "மொழிகள்", "कौन सी भाषा", "कौन-सी भाषा", "भाषाएँ", "भाषाओं"),
    "accessibility": ("accessibility", "accessible", "screen reader", "blind", "visually impaired", "low vision", "hard to read",
                      "font size", "bigger text", "keyboard only", "keyboard navigation", "deaf", "hard of hearing",
                      "அணுகல்", "பார்வை குறைபாடு", "सुलभता", "दृष्टिबाधित", "स्क्रीन रीडर"),
    "tech_issue": ("website not working", "site not working", "site is down", "website is down", "page not loading", "won't load",
                   "not loading", "blank page", "error message", "something went wrong", "can't add to cart", "cannot add to cart",
                   "can't add it", "add to cart not working", "search not working", "search doesn't work", "button not working",
                   "button doesn't work", "keeps failing", "page is broken", "app is broken",
                   "வெப்சைட் வேலை செய்யவில்லை", "பக்கம் திறக்கவில்லை", "பிழை", "वेबसाइट काम नहीं", "पेज नहीं खुल", "एरर", "त्रुटि"),
    "frustration": ("frustrated", "frustrating", "angry", "annoyed", "upset", "terrible", "horrible", "awful", "worst", "useless",
                    "ridiculous", "unacceptable", "disappointed", "fed up", "not helpful", "not helping", "waste of time",
                    "complaint", "complain",
                    "கோபம்", "ஏமாற்றம்", "மோசம்", "புகார்", "உதவவில்லை", "எரிச்சல்", "गुस्सा", "नाराज़", "नाराज", "बेकार", "शिकायत",
                    "परेशान", "निराश", "बहुत बुरा"),
    # There is no ticket system: these get an honest "not available" plus the real support contact.
    "ticket": ("support ticket", "ticket", "tickets", "raise a complaint", "file a complaint", "register a complaint", "lodge a complaint",
               "support request", "case number", "case id", "ticket number", "complaint number",
               "டிக்கெட்", "புகார் பதிவு", "புகார் எண்", "टिकट", "शिकायत दर्ज", "शिकायत नंबर", "complaint register"),
    "bulk": ("bulk", "wholesale", "business order", "corporate", "large order", "for my company", "for my office", "b2b",
             "resell", "reseller", "மொத்தமாக", "மொத்த ஆர்டர்", "நிறுவனத்துக்கு", "थोक", "बल्क", "कंपनी के लिए"),
    "reorder": ("order again", "reorder", "re-order", "buy again", "same as last time", "repeat my order", "repeat order",
                "last order again", "மீண்டும் ஆர்டர்", "மறுபடியும் ஆர்டர்", "फिर से ऑर्डर", "दोबारा ऑर्डर", "दुबारा ऑर्डर"),
    "care": ("how do i clean", "how to clean", "clean my", "cleaning", "wash", "care for", "take care of", "maintain", "maintenance",
             "store my", "storing", "how do i use", "how to use", "how do i brew", "how to brew", "how should i brew", "brewing tips", "brew ratio",
             "brewing ratio", "ratio",
             "grind size", "steep", "how to make", "set up", "pitch", "dry my", "descale", "crystallised", "crystallized",
             "சுத்தம்", "பராமரிப்பு", "பயன்படுத்துவது எப்படி", "தயாரிப்பது எப்படி", "காய்ச்ச", "எப்படி செய்வது",
             "साफ़ कैसे", "साफ कैसे", "देखभाल", "कैसे इस्तेमाल", "कैसे बनाएँ", "कैसे बनाऊँ", "कैसे बनाते", "बनाने का तरीका"),
    "add_to_cart": ("add to cart", "add to my cart", "add it", "add this", "add that", "add one", "add two", "add the", "put it in",
                    "put in my cart", "i'll take", "i will take", "i want to buy", "i'd like to buy", "buy it", "buy this", "buy the",
                    "கார்ட்டில் சேர்", "சேர்க்கவும்", "சேர்த்து விடு", "வாங்க வேண்டும்", "कार्ट में डाल", "कार्ट में जोड़", "जोड़ दो",
                    "जोड़ें", "खरीदना है", "add kar"),
}
_WEBSITE_WORDS = ("website", "site", "page", "button", "app", "browser", "screen", "checkout page", "search box")
_DIGIT_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
                "ஒன்று": 1, "இரண்டு": 2, "மூன்று": 3, "एक": 1, "दो": 2, "तीन": 3, "चार": 4}
_CARE_RX = {name: [re.compile(rf"(?<![a-z]){re.escape(k)}(?![a-z])") if k.isascii() else k for k in keys]
            for name, keys in CARE_KEYWORDS.items()}

# Things customers must never share in chat (we warn, and keep the text away from the model).
_CARD_RE = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
_SENSITIVE_RE = {
    "cvv": re.compile(r"\b(cvv|cvc|cvv2|security code)\b\D{0,12}\d{3,4}\b", re.I),
    "password": re.compile(r"\b(my )?(password|passcode|pwd)\s*(is|:|=)\s*\S+", re.I),
    "otp": re.compile(r"\b(otp|one[- ]time (pass)?code|verification code|security code|code is)\b\D{0,12}\d{4,8}\b", re.I),
}


def _luhn(digits: str) -> bool:
    total, alt = 0, False
    for d in reversed(digits):
        n = int(d) * (2 if alt else 1)
        total += n - 9 if n > 9 else n
        alt = not alt
    return total % 10 == 0


def sensitive_kind(text: str) -> str | None:
    """'card' / 'cvv' / 'password' / 'otp' if the message seems to contain such a secret, else None."""
    for m in _CARD_RE.finditer(text):
        digits = re.sub(r"\D", "", m.group(0))
        if 13 <= len(digits) <= 19 and _luhn(digits):
            return "card"
    for kind, rx in _SENSITIVE_RE.items():
        if rx.search(text):
            return kind
    return None


# Words that point back at something already discussed ("when will IT arrive?", "இந்த ஆர்டர்", "यह ऑर्डर").
_REFERS_BACK_RE = re.compile(r"(?<![a-z])(it|its|it's|this|that|these|those|same|the order|that one|this one)(?![a-z])"
                             r"|இந்த|அந்த|இது|அது|यह|इसका|इसे|इसकी|वह|वो|उसका|उसे|उसकी")
_MODIFY_RE = re.compile(r"(?<![a-z])(change|update|edit|correct|fix|modify)(?![a-z]).{0,25}(?<![a-z])(address|order)(?![a-z])")
_ADD_TO_CART_RE = re.compile(r"(?<![a-z])(add|put|place)(?![a-z]).{0,50}(?<![a-z])(cart|basket)(?![a-z])"
                             r"|(कार्ट|टोकरी).{0,40}(डाल|जोड़)|(கார்ட்|கூடை).{0,40}சேர்")


def _care_matches(text: str) -> set[str]:
    found = set()
    for name, keys in _CARE_RX.items():
        if any((k.search(text) if hasattr(k, "search") else k in text) for k in keys):
            found.add(name)
    if _ADD_TO_CART_RE.search(text):
        found.add("add_to_cart")
    if _MODIFY_RE.search(text):
        found.add("modify_order")
    if "refund_status" in found:
        found.discard("order_late")    # "my refund hasn't come" is about money, not a late parcel
    return found


def requested_quantity(text: str) -> int:
    """Quantity for an add-to-cart request ("add 2 headlamps", "add two"), defaulting to 1. Prices and order numbers are ignored."""
    budget = parse_budget(text)
    if budget:
        text = text[:budget.span[0]] + " " + text[budget.span[1]:]
    cleaned = ORDER_NUMBER_RE.sub(" ", re.sub(rf"(?:{_CUR})\s*\d[\d,]*(?:\.\d+)?", " ", text.lower(), flags=re.I))
    m = re.search(r"(?<![\w.])(\d{1,2})(?![\w.%-])", cleaned)
    if m:
        return max(1, int(m.group(1)))
    for word, n in _DIGIT_WORDS.items():
        if re.search(rf"(?<![a-z]){re.escape(word)}(?![a-z])", cleaned) if word.isascii() else word in cleaned:
            return n
    return 1


@dataclass
class Intent:
    intents: set[str] = field(default_factory=set)
    order_number: str | None = None
    search_terms: list[str] = field(default_factory=list)
    max_price_cents: int | None = None   # budget amount in hundredths of `budget_currency` (or of the catalogue currency if None)
    budget_currency: str | None = None   # "INR" / "USD" when the customer stated one
    raw: str = ""
    script_language: str | None = None
    quantity: int = 1
    sensitive: str | None = None       # card | cvv | password | otp — the customer typed a secret
    refers_back: bool = False          # the message points at something already discussed ("it", "this order")
    keyword_product: bool = False      # a shopping phrase ("do you have…") triggered the product search


def normalise_order_number(text: str) -> str | None:
    m = ORDER_NUMBER_RE.search(text)
    return f"{m.group(1).upper()}-{m.group(2)}" if m else None


# Everyday words → the words the catalogues actually use ("backpack" must also find the "Daytrip 22L Daypack").
# Expansions are added after the customer's own words; matching is still against real product rows only.
SEARCH_SYNONYMS: dict[str, tuple[str, ...]] = {
    "backpack": ("pack",), "rucksack": ("pack",), "knapsack": ("pack",), "daypack": ("pack",),
    "flashlight": ("lamp",), "torch": ("lamp",), "headlight": ("lamp",), "headtorch": ("lamp",), "light": ("lamp",),
    "shoe": ("boot",), "sneaker": ("boot",), "boots": ("boot",), "footwear": ("boot",),
    "raincoat": ("jacket", "rain"), "coat": ("jacket",), "shell": ("jacket",), "jacket": ("shell",),
    "mat": ("pad",), "mattress": ("pad",), "burner": ("stove",), "cooker": ("stove",), "shelter": ("tent",),
    "cup": ("mug",), "mugs": ("mug",), "pourover": ("dripper", "pour-over"), "pour-over": ("dripper",), "filter": ("dripper",),
    "mill": ("grinder",), "beans": ("bean",), "teapot": ("tea",), "kettle": ("gooseneck",),
}


def extract_search_terms(text: str) -> list[str]:
    words = re.findall(r"[a-zA-Z][a-zA-Z\-]{2,}", text.lower())
    # Tamil / Hindi product words map to English catalog terms (longest phrases first).
    terms: list[str] = []
    for phrase in sorted(PRODUCT_LEXICON, key=len, reverse=True):
        if phrase in text and PRODUCT_LEXICON[phrase] not in terms:
            terms.append(PRODUCT_LEXICON[phrase])
    own: list[str] = []
    for w in words:
        if w in _STOPWORDS:
            continue
        stem = w[:-1] if w.endswith("s") and len(w) > 4 and not w.endswith("ss") else w
        if stem not in terms and stem not in own:
            own.append(stem)
    terms += own
    if "pour" in own and "over" in text.lower():
        terms.append("dripper")
    for w in own:
        for extra in SEARCH_SYNONYMS.get(w, ()):
            if extra not in terms:
                terms.append(extra)
    return terms[:8]


def detect_intent(message: str) -> Intent:
    # Typographic quotes from phones and Macs ("hasn’t") behave like plain ones.
    message = message.replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')
    text = f" {message.lower().strip()} "
    found = {name for name, keys in _KEYWORDS.items() if any(k in text for k in keys)}
    keyword_product = bool(found & {"product", "price", "stock"})
    care = _care_matches(text)
    # "the website isn't working" is a technical problem, not a defective product.
    if "defective" in care and any(w in text for w in _WEBSITE_WORDS):
        care = (care - {"defective"}) | {"tech_issue"}
    if care & {"refund_status", "return_request", "exchange"}:
        found.add("returns")
    if care & {"damaged", "defective"}:
        found.add("warranty")
    if care & {"order_late", "delivered_missing", "wrong_item", "missing_item", "cancel", "modify_order", "reorder"}:
        found.add("order_status")
    if care & {"cheaper", "alternative", "compare", "add_to_cart"}:
        found.add("product")
    if "add_to_cart" in care:
        found.discard("cart")          # an action on the cart, not "what's in my cart"
    # Words about a problem with an order or the site are not product searches.
    if care & {"payment_issue", "refund_status", "account", "checkout_help", "tech_issue", "promotions", "invoice", "privacy",
               "languages", "accessibility", "bulk", "frustration", "ticket"} and not care & {"compare", "cheaper", "alternative", "add_to_cart", "care"}:
        found -= {"product", "price", "stock"} if not keyword_product else set()
    if "payment_issue" in care:
        found.discard("payment")       # a payment problem, not the "which cards do you accept" policy
    script = script_language(message)
    order_number = normalise_order_number(message)
    if order_number:
        found.add("order_status")
    budget = parse_budget(message)
    if budget and not budget.limit_word and found & _POLICY_INTENTS:
        budget = None                  # "is it $5 shipping?" quotes a fee, it is not a spending limit
    max_price_cents = budget.amount_minor if budget else None
    if max_price_cents is not None:
        found.add("product")
    if "cart" in found:
        # "what's in my cart" is about the cart, not a product search or order lookup.
        found -= {"product", "order_status"} if not order_number else set()
    # "delivery" inside an order question is about that order, not the shipping policy.
    if "order_status" in found and not any(k in text for k in ("shipping cost", "shipping policy", "how much is shipping")):
        found.discard("shipping")
    # "cash on delivery" is a payment method, not a shipping question.
    if "cash on delivery" in text and not any(k in text for k in ("shipping", "ship ", "deliver to", "delivery time", "delivery charge")):
        found.discard("shipping")
    if found & {"price", "stock"}:
        found.add("product")
    terms = [] if found <= {"order_status", "greeting", "contact", "cart"} and found else extract_search_terms(message)
    # Words that only describe a policy question ("how much is shipping?") are not product searches.
    if found & _POLICY_INTENTS:
        terms = [t for t in terms if t not in _POLICY_WORDS]
        if not terms and max_price_cents is None:
            found -= {"product", "price", "stock"}
    if not found and not care and terms:
        found.add("product")
    if "add_to_cart" in care and not terms:
        terms = extract_search_terms(message)
    sensitive = sensitive_kind(message)
    if sensitive:
        found -= {"product", "price", "stock"}
        terms = []
    if care & {"payment_issue", "refund_status", "account", "checkout_help", "tech_issue", "promotions", "invoice", "privacy",
               "languages", "accessibility", "bulk", "frustration", "ticket", "order_late", "delivered_missing", "cancel", "modify_order",
               "wrong_item", "missing_item", "reorder", "damaged", "defective"} and not keyword_product \
            and not care & {"compare", "cheaper", "alternative", "add_to_cart", "care"}:
        found.discard("product")
        terms = [] if not care & {"damaged", "defective"} else terms
    found |= care
    return Intent(intents=found, order_number=order_number, search_terms=terms, max_price_cents=max_price_cents,
                  budget_currency=budget.currency if budget else None, raw=message.lower(), script_language=script, quantity=requested_quantity(message),
                  sensitive=sensitive, keyword_product=keyword_product, refers_back=bool(_REFERS_BACK_RE.search(text)))
