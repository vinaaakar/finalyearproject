"""Spoken phone prompts in Tamil, English and Hindi.

Everything a caller hears on the phone that is not an answer from the shared assistant comes from here, so the call
never mixes languages within one prompt. Templates are reviewed text; values (store name, order number, product names,
references) are inserted verbatim. The Tamil and Hindi wording has not yet been reviewed by a native speaker (the same
status as the chat templates, see docs/customer-care.md).

Phone wording differs from the chat wording on purpose: there are no buttons or links, so every choice is offered as
"press 1 / say …", references are also spelled out character by character, and nothing says "tap" or "sign in first".
"""

from __future__ import annotations

from datetime import date

LANGS = ("ta", "en", "hi")

P: dict[str, dict[str, str]] = {
    # ---- greeting / general --------------------------------------------------------------------------------------------
    "greeting": {
        "en": "Thanks for calling {store}. This is {assistant}, the store's automated assistant. I can tell you where your order is, "
              "record a complaint, a return, a refund request or a request for our team, and answer questions about products, "
              "shipping and returns. How can I help?",
        "ta": "{store}-ஐ அழைத்ததற்கு நன்றி. நான் {assistant}, கடையின் தானியங்கி உதவியாளர். உங்கள் ஆர்டர் எங்கே உள்ளது என்று சொல்லலாம்; "
              "புகார், திருப்பி அனுப்புதல், பணத்திரும்பக் கோரிக்கை அல்லது எங்கள் குழுவுக்கான கோரிக்கையைப் பதிவு செய்யலாம்; பொருட்கள், டெலிவரி, "
              "ரிட்டர்ன் பற்றிய கேள்விகளுக்கும் பதில் சொல்லலாம். நான் எப்படி உதவலாம்?",
        "hi": "{store} को कॉल करने के लिए धन्यवाद। मैं {assistant} हूँ, स्टोर का ऑटोमेटेड असिस्टेंट। मैं बता सकता हूँ कि आपका ऑर्डर कहाँ है; "
              "शिकायत, वापसी, रिफंड अनुरोध या हमारी टीम के लिए अनुरोध दर्ज कर सकता हूँ; और सामान, डिलीवरी और वापसी के सवालों के जवाब दे "
              "सकता हूँ। मैं कैसे मदद करूँ?",
    },
    "other_languages": {
        "en": " தமிழிலும் பேசலாம். आप हिंदी में भी बात कर सकते हैं।",
        "ta": " You can also speak English. आप हिंदी में भी बात कर सकते हैं।",
        "hi": " You can also speak English. தமிழிலும் பேசலாம்.",
    },
    "language_switched": {"en": "Sure, let's continue in English.", "ta": "சரி, தமிழில் தொடரலாம்.", "hi": "ठीक है, हिंदी में बात करते हैं।"},
    "how_help": {"en": "How can I help you?", "ta": "நான் எப்படி உதவலாம்?", "hi": "मैं आपकी कैसे मदद करूँ?"},
    "anything_else": {"en": "Is there anything else I can help with?", "ta": "வேறு ஏதாவது உதவி வேண்டுமா?",
                      "hi": "क्या मैं किसी और चीज़ में मदद कर सकता हूँ?"},
    "goodbye": {"en": "Thank you for calling {store}. Goodbye!", "ta": "{store}-ஐ அழைத்ததற்கு நன்றி. வணக்கம்!",
                "hi": "{store} को कॉल करने के लिए धन्यवाद। नमस्ते!"},
    "silence": {"en": "Sorry, I didn't hear anything.", "ta": "மன்னிக்கவும், எதுவும் கேட்கவில்லை.", "hi": "माफ़ कीजिए, मुझे कुछ सुनाई नहीं दिया।"},
    "silence_end": {"en": "I still can't hear you, so I'll end this call. Please call again when you're ready. Goodbye.",
                    "ta": "இன்னும் உங்கள் குரல் கேட்கவில்லை, அதனால் இந்த அழைப்பை முடிக்கிறேன். தயாரானதும் மீண்டும் அழையுங்கள். வணக்கம்.",
                    "hi": "मुझे अब भी आपकी आवाज़ नहीं आ रही, इसलिए यह कॉल समाप्त कर रहा हूँ। तैयार होने पर फिर से कॉल करें। नमस्ते।"},
    "back_to_menu": {"en": "OK, let's start again.", "ta": "சரி, மீண்டும் தொடங்கலாம்.", "hi": "ठीक है, फिर से शुरू करते हैं।"},

    # ---- order verification ----------------------------------------------------------------------------------------------
    "ask_order": {"en": "Please say or key in your order number. It starts with {prefix}, followed by five digits.",
                  "ta": "உங்கள் ஆர்டர் எண்ணைச் சொல்லுங்கள் அல்லது டைப் செய்யுங்கள். அது {prefix} என்று தொடங்கி, ஐந்து இலக்கங்கள் கொண்டது.",
                  "hi": "कृपया अपना ऑर्डर नंबर बोलें या कीपैड पर दबाएँ। यह {prefix} से शुरू होता है, फिर पाँच अंक।"},
    "ask_order_care": {"en": "To record it on your account, I first need to check one of your orders. Please say or key in the order "
                             "number. It starts with {prefix}, followed by five digits.",
                       "ta": "இதை உங்கள் கணக்கில் பதிவு செய்ய, முதலில் உங்கள் ஒரு ஆர்டரைச் சரிபார்க்க வேண்டும். ஆர்டர் எண்ணைச் சொல்லுங்கள் "
                             "அல்லது டைப் செய்யுங்கள். அது {prefix} என்று தொடங்கி, ஐந்து இலக்கங்கள் கொண்டது.",
                       "hi": "इसे आपके अकाउंट में दर्ज करने के लिए पहले आपका एक ऑर्डर जाँचना होगा। कृपया ऑर्डर नंबर बोलें या कीपैड पर "
                             "दबाएँ। यह {prefix} से शुरू होता है, फिर पाँच अंक।"},
    "ask_order_no_order": {"en": " If you don't have an order with us, say “no order”.",
                           "ta": " எங்களிடம் ஆர்டர் இல்லையென்றால் “ஆர்டர் இல்லை” என்று சொல்லுங்கள்.",
                           "hi": " अगर आपका हमारे साथ कोई ऑर्डर नहीं है, तो “कोई ऑर्डर नहीं” कहें।"},
    "order_not_caught": {"en": "Sorry, I didn't catch the order number.", "ta": "மன்னிக்கவும், ஆர்டர் எண் புரியவில்லை.",
                         "hi": "माफ़ कीजिए, ऑर्डर नंबर समझ नहीं आया।"},
    "ask_pin": {"en": "To verify it's you, please say or key in the six-digit shipping PIN code for that order. For an older order with "
                      "a US address, use its five-digit ZIP code.",
                "ta": "இது நீங்கள்தான் என்று உறுதிசெய்ய, அந்த ஆர்டரின் ஆறு இலக்க டெலிவரி பின்கோடைச் சொல்லுங்கள் அல்லது டைப் செய்யுங்கள். "
                      "அமெரிக்க முகவரி கொண்ட பழைய ஆர்டருக்கு, அதன் ஐந்து இலக்க ZIP கோடைப் பயன்படுத்துங்கள்.",
                "hi": "यह पुष्टि करने के लिए कि आप ही हैं, उस ऑर्डर का छह अंकों का शिपिंग पिन कोड बोलें या दबाएँ। अमेरिकी पते वाले पुराने "
                      "ऑर्डर के लिए उसका पाँच अंकों का ZIP कोड इस्तेमाल करें।"},
    "ask_zip": {"en": "To verify it's you, please say or key in the five-digit shipping ZIP code for that order.",
                "ta": "இது நீங்கள்தான் என்று உறுதிசெய்ய, அந்த ஆர்டரின் ஐந்து இலக்க டெலிவரி ZIP கோடைச் சொல்லுங்கள் அல்லது டைப் செய்யுங்கள்.",
                "hi": "यह पुष्टि करने के लिए कि आप ही हैं, उस ऑर्डर का पाँच अंकों का शिपिंग ZIP कोड बोलें या दबाएँ।"},
    "pin_not_caught": {"en": "Sorry, I didn't catch the code.", "ta": "மன்னிக்கவும், கோட் புரியவில்லை.", "hi": "माफ़ कीजिए, कोड समझ नहीं आया।"},
    "thanks": {"en": "Thanks.", "ta": "நன்றி.", "hi": "धन्यवाद।"},
    "sure": {"en": "Sure.", "ta": "சரி.", "hi": "ज़रूर।"},
    "no_match_pin": {"en": "That order number and PIN code don't match our records. Let's try again.",
                     "ta": "அந்த ஆர்டர் எண்ணும் பின்கோடும் எங்கள் பதிவுகளுடன் பொருந்தவில்லை. மீண்டும் முயற்சிக்கலாம்.",
                     "hi": "वह ऑर्डर नंबर और पिन कोड हमारे रिकॉर्ड से मेल नहीं खाते। फिर से कोशिश करते हैं।"},
    "no_match_zip": {"en": "That order number and ZIP code don't match our records. Let's try again.",
                     "ta": "அந்த ஆர்டர் எண்ணும் ZIP கோடும் எங்கள் பதிவுகளுடன் பொருந்தவில்லை. மீண்டும் முயற்சிக்கலாம்.",
                     "hi": "वह ऑर्डर नंबर और ZIP कोड हमारे रिकॉर्ड से मेल नहीं खाते। फिर से कोशिश करते हैं।"},
    "verify_failed_end": {"en": "I'm sorry, I wasn't able to verify that order. Please contact our support team by email at {email} for help. Goodbye.",
                          "ta": "மன்னிக்கவும், அந்த ஆர்டரைச் சரிபார்க்க முடியவில்லை. உதவிக்கு எங்கள் குழுவுக்கு {email} என்ற முகவரியில் மின்னஞ்சல் அனுப்புங்கள். வணக்கம்.",
                          "hi": "माफ़ कीजिए, मैं उस ऑर्डर की पुष्टि नहीं कर सका। मदद के लिए हमारी टीम को {email} पर ईमेल करें। नमस्ते।"},
    "locked": {"en": "I'm sorry, I can't verify orders by phone right now. Please sign in on our website to see your orders, or contact "
                     "our support team by email. Goodbye.",
               "ta": "மன்னிக்கவும், இப்போது தொலைபேசியில் ஆர்டர்களைச் சரிபார்க்க முடியாது. உங்கள் ஆர்டர்களைப் பார்க்க எங்கள் இணையதளத்தில் "
                     "உள்நுழையுங்கள், அல்லது எங்கள் குழுவுக்கு மின்னஞ்சல் அனுப்புங்கள். வணக்கம்.",
               "hi": "माफ़ कीजिए, अभी फ़ोन पर ऑर्डर की पुष्टि नहीं हो सकती। अपने ऑर्डर देखने के लिए हमारी वेबसाइट पर साइन इन करें, या "
                     "हमारी टीम को ईमेल करें। नमस्ते।"},
    "order_status": {"en": "Order {n} is {status}.", "ta": "ஆர்டர் {n}: {status}.", "hi": "ऑर्डर {n}: {status}।"},
    "order_eta": {"en": " It's expected by {date}.", "ta": " {date}-க்குள் வந்து சேரும் என்று எதிர்பார்க்கப்படுகிறது.",
                  "hi": " इसके {date} तक पहुँचने की उम्मीद है।"},
    "order_carrier": {"en": " Carrier: {carrier}, tracking number {tracking}.", "ta": " கூரியர்: {carrier}, டிராக்கிங் எண் {tracking}.",
                      "hi": " कूरियर: {carrier}, ट्रैकिंग नंबर {tracking}।"},
    "order_problem_hint": {"en": " If something is wrong with this order, I can record a complaint, a return or a refund request.",
                           "ta": " இந்த ஆர்டரில் ஏதாவது பிரச்சினை இருந்தால், புகார், திருப்பி அனுப்புதல் அல்லது பணத்திரும்பக் கோரிக்கையைப் பதிவு செய்யலாம்.",
                           "hi": " अगर इस ऑर्डर में कोई समस्या है, तो मैं शिकायत, वापसी या रिफंड अनुरोध दर्ज कर सकता हूँ।"},

    # ---- customer-care requests -------------------------------------------------------------------------------------------
    "care_start": {"en": "I can record a {kind} for our team.", "ta": "எங்கள் குழுவுக்காக ஒரு {kind} பதிவு செய்ய முடியும்.",
                   "hi": "मैं हमारी टीम के लिए {kind} दर्ज कर सकता हूँ।"},
    "no_live_agent": {"en": "There's no one available to take calls on this line, so I can't transfer you to a person. I can record a request "
                            "for our team instead; they will reply by email and under My requests on our website.",
                      "ta": "இந்த லைனில் அழைப்புகளை எடுக்க யாரும் இல்லை, அதனால் உங்களை ஒருவரிடம் இணைக்க முடியாது. அதற்குப் பதிலாக எங்கள் "
                            "குழுவுக்கான கோரிக்கையைப் பதிவு செய்யலாம்; அவர்கள் மின்னஞ்சலிலும் இணையதளத்தின் “என் கோரிக்கைகள்” பகுதியிலும் பதில் அளிப்பார்கள்.",
                      "hi": "इस लाइन पर कॉल लेने के लिए कोई व्यक्ति उपलब्ध नहीं है, इसलिए मैं आपको किसी व्यक्ति से नहीं जोड़ सकता। इसके बजाय "
                            "मैं हमारी टीम के लिए अनुरोध दर्ज कर सकता हूँ; वे ईमेल पर और वेबसाइट के “मेरे अनुरोध” में जवाब देंगे।"},
    "contact_only": {"en": "No problem. You can email the {store} team at {email}. Support hours: {hours}.",
                     "ta": "பரவாயில்லை. {store} குழுவுக்கு {email} என்ற முகவரியில் மின்னஞ்சல் அனுப்பலாம். உதவி நேரம்: {hours}.",
                     "hi": "कोई बात नहीं। आप {store} टीम को {email} पर ईमेल कर सकते हैं। सहायता का समय: {hours}।"},
    "not_eligible": {"en": "I can't record a {kind} for order {n}: {reason}",
                     "ta": "ஆர்டர் {n}-க்கு {kind} பதிவு செய்ய இயலாது: {reason}",
                     "hi": "ऑर्डर {n} के लिए {kind} दर्ज नहीं हो सकता: {reason}"},
    "offer_other": {"en": " I can record a complaint or a request for our team instead. For a complaint, press 1 or say “complaint”. "
                          "For a request for our team, press 2 or say “team”. Otherwise, tell me what else I can help with.",
                    "ta": " அதற்குப் பதிலாக புகார் அல்லது எங்கள் குழுவுக்கான கோரிக்கையைப் பதிவு செய்யலாம். புகாருக்கு 1 அழுத்துங்கள் அல்லது “புகார்” "
                          "என்று சொல்லுங்கள். குழுவுக்கான கோரிக்கைக்கு 2 அழுத்துங்கள் அல்லது “குழு” என்று சொல்லுங்கள். இல்லையென்றால், வேறு என்ன "
                          "உதவி வேண்டும் என்று சொல்லுங்கள்.",
                    "hi": " इसके बजाय मैं शिकायत या टीम के लिए अनुरोध दर्ज कर सकता हूँ। शिकायत के लिए 1 दबाएँ या “शिकायत” कहें। टीम के लिए "
                          "अनुरोध के लिए 2 दबाएँ या “टीम” कहें। नहीं तो बताइए कि मैं और किसमें मदद करूँ।"},
    "return_window": {"en": "Order {n} was delivered on {date}; under the store's {days}-day policy a return can be requested until {until}.",
                      "ta": "ஆர்டர் {n} {date} அன்று டெலிவரி ஆனது; கடையின் {days} நாள் கொள்கைப்படி {until} வரை திருப்பி அனுப்பக் கோரலாம்.",
                      "hi": "ऑर्डर {n} {date} को डिलीवर हुआ; स्टोर की {days} दिन की नीति के अनुसार {until} तक वापसी का अनुरोध किया जा सकता है।"},
    "ask_item": {"en": "Which item is it about?", "ta": "இது எந்தப் பொருள் பற்றியது?", "hi": "यह किस सामान के बारे में है?"},
    "ask_category": {"en": "What is the reason?", "ta": "காரணம் என்ன?", "hi": "कारण क्या है?"},
    "option": {"en": "For {name}, press {n}.", "ta": "{name} என்றால் {n} அழுத்துங்கள்.", "hi": "{name} के लिए {n} दबाएँ।"},
    "option_whole": {"en": "For the whole order, press 0.", "ta": "முழு ஆர்டருக்கு 0 அழுத்துங்கள்.", "hi": "पूरे ऑर्डर के लिए 0 दबाएँ।"},
    "choice_not_caught": {"en": "Sorry, I didn't catch your choice.", "ta": "மன்னிக்கவும், உங்கள் தேர்வு புரியவில்லை.",
                          "hi": "माफ़ कीजिए, आपका चुनाव समझ नहीं आया।"},
    "ask_description": {"en": "Please describe the problem in a few words, in your own words.",
                        "ta": "பிரச்சினையைச் சில வார்த்தைகளில், உங்கள் சொந்த வார்த்தைகளில் சொல்லுங்கள்.",
                        "hi": "कृपया समस्या कुछ शब्दों में, अपने शब्दों में बताइए।"},
    "review": {"en": "Let me read it back. {kind}{order}{item}. Reason: {category}. Details: {desc}. To submit it, say “yes” or press 1. "
                     "To cancel, say “no” or press 2.",
               "ta": "நான் படித்துக் காட்டுகிறேன். {kind}{order}{item}. காரணம்: {category}. விவரம்: {desc}. சமர்ப்பிக்க “ஆம்” என்று சொல்லுங்கள் "
                     "அல்லது 1 அழுத்துங்கள். ரத்து செய்ய “இல்லை” என்று சொல்லுங்கள் அல்லது 2 அழுத்துங்கள்.",
               "hi": "मैं पढ़कर सुनाता हूँ। {kind}{order}{item}। कारण: {category}। विवरण: {desc}। भेजने के लिए “हाँ” कहें या 1 दबाएँ। "
                     "रद्द करने के लिए “नहीं” कहें या 2 दबाएँ।"},
    "review_again": {"en": "Please say “yes” or press 1 to submit, or say “no” or press 2 to cancel.",
                     "ta": "சமர்ப்பிக்க “ஆம்” என்று சொல்லுங்கள் அல்லது 1 அழுத்துங்கள்; ரத்து செய்ய “இல்லை” அல்லது 2.",
                     "hi": "भेजने के लिए “हाँ” कहें या 1 दबाएँ; रद्द करने के लिए “नहीं” कहें या 2 दबाएँ।"},
    "about_order": {"en": " for order {n}", "ta": ", ஆர்டர் {n}", "hi": ", ऑर्डर {n}"},
    "about_item": {"en": ", item {name}", "ta": ", பொருள் {name}", "hi": ", सामान {name}"},
    "submitted": {"en": "Done. Your {kind} has been recorded. Your reference is {ref}. That's {spelled}. Status: {status}.",
                  "ta": "முடிந்தது. உங்கள் {kind} பதிவு செய்யப்பட்டது. உங்கள் குறிப்பு எண் {ref}. அதாவது {spelled}. நிலை: {status}.",
                  "hi": "हो गया। आपका {kind} दर्ज कर लिया गया है। आपका संदर्भ नंबर {ref} है, यानी {spelled}। स्थिति: {status}।"},
    "submitted_follow": {"en": " Our team will review it and reply by email; you can also follow it under My requests on our website.",
                         "ta": " எங்கள் குழு இதைப் பரிசீலித்து மின்னஞ்சலில் பதில் அளிக்கும்; இணையதளத்தின் “என் கோரிக்கைகள்” பகுதியிலும் பார்க்கலாம்.",
                         "hi": " हमारी टीम इसकी समीक्षा करके ईमेल पर जवाब देगी; आप इसे हमारी वेबसाइट के “मेरे अनुरोध” में भी देख सकते हैं।"},
    "submitted_escalation": {"en": " This is a recorded request, not a live conversation: a member of the team will look at it.",
                             "ta": " இது பதிவு செய்யப்பட்ட கோரிக்கை, நேரடி உரையாடல் அல்ல: குழுவில் ஒருவர் இதைப் பார்ப்பார்.",
                             "hi": " यह एक दर्ज अनुरोध है, लाइव बातचीत नहीं: टीम का कोई सदस्य इसे देखेगा।"},
    "refund_note": {"en": " Refunds in this demonstration are simulated: no real money is transferred.",
                    "ta": " இந்த மாதிரிச் செயல்முறையில் பணத்திரும்பல் உருவகம் மட்டுமே: உண்மையான பணம் அனுப்பப்படாது.",
                    "hi": " इस प्रदर्शन में रिफंड सिम्युलेटेड है: कोई असली पैसा नहीं भेजा जाता।"},
    "cancelled": {"en": "OK, nothing was recorded.", "ta": "சரி, எதுவும் பதிவு செய்யப்படவில்லை.", "hi": "ठीक है, कुछ भी दर्ज नहीं किया गया।"},
    "not_submitted": {"en": "Nothing was recorded: {reason}", "ta": "எதுவும் பதிவு செய்யப்படவில்லை: {reason}", "hi": "कुछ भी दर्ज नहीं हुआ: {reason}"},
    "duplicate": {"en": "You already have an open request for this: {ref}. That's {spelled}. Nothing new was recorded.",
                  "ta": "இதற்கு ஏற்கனவே ஒரு திறந்த கோரிக்கை உள்ளது: {ref}, அதாவது {spelled}. புதிதாக எதுவும் பதிவு செய்யப்படவில்லை.",
                  "hi": "इसके लिए आपका एक अनुरोध पहले से खुला है: {ref}, यानी {spelled}। कुछ नया दर्ज नहीं किया गया।"},
    "sensitive": {"en": "Please don't say card numbers, CVV, UPI PIN, passwords or one-time codes. They are never needed. Please describe the "
                        "problem again without them.",
                  "ta": "கார்டு எண், CVV, UPI PIN, கடவுச்சொல் அல்லது ஒருமுறை குறியீடுகளைச் சொல்ல வேண்டாம். அவை ஒருபோதும் தேவையில்லை. "
                        "அவை இல்லாமல் பிரச்சினையை மீண்டும் சொல்லுங்கள்.",
                  "hi": "कृपया कार्ड नंबर, CVV, UPI PIN, पासवर्ड या OTP न बोलें। इनकी कभी ज़रूरत नहीं होती। कृपया इनके बिना समस्या फिर से बताइए।"},
    "status_none": {"en": "There are no customer-care requests for order {n}.", "ta": "ஆர்டர் {n}-க்கு வாடிக்கையாளர் சேவைக் கோரிக்கைகள் இல்லை.",
                    "hi": "ऑर्डर {n} के लिए कोई ग्राहक सेवा अनुरोध नहीं है।"},
    "status_line": {"en": "Request {ref}, {kind}: {status}.", "ta": "கோரிக்கை {ref}, {kind}: {status}.", "hi": "अनुरोध {ref}, {kind}: {status}।"},
    "status_reply": {"en": " Latest reply from the team: {msg}", "ta": " குழுவின் சமீபத்திய பதில்: {msg}", "hi": " टीम का ताज़ा जवाब: {msg}"},
}

# What the caller says to choose a language explicitly (whole utterance).
LANGUAGE_WORDS = {
    "en": ("english", "inglish", "ஆங்கிலம்", "इंग्लिश", "अंग्रेज़ी", "अंग्रेजी"),
    "ta": ("tamil", "தமிழ்", "தமிழில்", "तमिल"),
    "hi": ("hindi", "हिंदी", "हिन्दी", "ஹிந்தி", "இந்தி"),
}

_MONTHS = {
    "en": ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"),
    "ta": ("ஜனவரி", "பிப்ரவரி", "மார்ச்", "ஏப்ரல்", "மே", "ஜூன்", "ஜூலை", "ஆகஸ்ட்", "செப்டம்பர்", "அக்டோபர்", "நவம்பர்", "டிசம்பர்"),
    "hi": ("जनवरी", "फ़रवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर"),
}
_WEEKDAYS_EN = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def p(lang: str, key: str, **values) -> str:
    return P[key].get(lang, P[key]["en"]).format(**values)


def spoken_date(lang: str, value) -> str:
    """A date as people say it ("Friday, 13 November"), not as an ISO string a speech engine would read digit by digit."""
    d = value if isinstance(value, date) else date.fromisoformat(str(value)[:10])
    month = _MONTHS.get(lang, _MONTHS["en"])[d.month - 1]
    if lang == "en":
        return f"{_WEEKDAYS_EN[d.weekday()]}, {d.day} {month}"
    return f"{d.day} {month}"


def spelled(reference: str) -> str:
    """'SA-CMP-00001' → 'S A, C M P, 0 0 0 0 1' so a caller can write it down."""
    return ", ".join(" ".join(part) for part in reference.split("-"))
