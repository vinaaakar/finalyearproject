# Final Demonstration Guide (10–15 minutes)

The demonstration shows the project's actual innovation: **multilingual, voice-first conversational commerce** with
**trustworthy answers** and **customer-care workflows**, across two isolated stores. Payments are sandbox-only,
refunds are simulated, and all people and orders are synthetic. Say this at the start.

> Before the demonstration, the development API must be restarted **with your approval** so the fixes from the final
> audit (cheapest-in-category, "What did I pay?", delivery-time answers, weight answers, PIN-code phone prompt, chat
> persistence) are live. The API that was running when this guide was written was started before those fixes.

---

## 1. Requirements

| Item | Requirement | Check |
|---|---|---|
| Machine | The development Mac (macOS voices Vani / Rishi / Lekha installed) | `say -v '?' \| grep -E 'Vani\|Rishi\|Lekha'` lists all three |
| Browser | Google Chrome, microphone permission **allowed** for `127.0.0.1:5180` and `:5181` | the 🎤 button records |
| Microphone | Built-in mic in a quiet room, ~40–60 cm away; a headset mic is better | speak at a normal pace |
| Speech recognition | `SPEECH_STT=whisper_cpp`, local `whisper-cli`, multilingual `ggml-base.bin` | `curl -s 127.0.0.1:8000/api/speech/capabilities` shows server STT available |
| Language model (optional) | Ollama running with `llama3.2:3b` | `curl -s 127.0.0.1:8000/api/health` → `"llm": {"available": true}` |
| Services | API :8000, Summit Trail Co. :5180, Bloom & Brew :5181, PostgreSQL container `avc_postgres` | see checklist §2 |

Nothing in the demonstration uses the internet.

## 2. Pre-demonstration checklist (the day before, and again 15 minutes before)

1. `curl -s http://127.0.0.1:8000/api/health` → `"status":"ok"`, both databases `true`, both stores `"currency":"INR"`,
   `"prices_complete":true`, `"shipping_configured":true`.
2. `curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/api/health/ready` → `200`.
3. `cd backend && .venv/bin/python -m app.migrate --status` → both stores 0001–0009 applied, checksums match, nothing pending.
4. Open http://127.0.0.1:5180 and http://127.0.0.1:5181: products show ₹ prices; the chat opens in **Tamil**.
5. In each store, open the chat, press 🎤, say "Do you have a two person tent?": the reply is in English.
6. Sign in as each store's staff agent (see §3): the **Customer care** and **Fulfilment** tabs open.
7. **Support hours:** the stores currently show "Mon–Fri 8am–6pm MT" and "Every day 9am–8pm ET" (US time zones left
   from the original data). Decide what to say about them (see §7), or have them confirmed and changed beforehand
   (a database change that needs approval).
8. Close other tabs that use the microphone; set system volume so replies are audible to examiners.
9. Have this guide open on a second screen, and the typed-fallback sentences (§5) ready to paste.

## 3. Demonstration accounts (set up manually before the demonstration)

Passwords are not written in this guide.

* **Staff agents:** the seeded agent of each store (`agent@summittrail.example.com`, `agent@bloomandbrew.example.com`).
  Their synthetic demo credentials are in the README's *Demo accounts* table.
* **Customers:** create one **new** customer per store at `/register` with a password of your choice (for example
  `priya.demo@example.com` in Summit Trail Co. and `arun.demo@example.com` in Bloom & Brew). New accounts get India orders
  in ₹. The seeded customers own the original US-dollar demo orders, which are kept unchanged.
* **Orders for the care workflows** (≈ 5 minutes, before the demonstration):
  1. As the customer, add two items to the cart (e.g. Lumen 300 Headlamp + PocketFlame Stove in Summit Trail;
     Wildflower Honey + Spiced Chai Blend in Bloom & Brew), check out to an Indian address (state, six-digit PIN code,
     Indian mobile number) and pay with the **sandbox** ("Simulate approved payment").
  2. Place a second order the same way (so a return, a refund and a complaint can each use a different order or item —
     only one open request per type per item is allowed).
  3. As the staff agent: **Fulfilment** → the order → *Mark as shipped* (carrier `DemoPost`, any tracking number) →
     *Mark as delivered*. Returns need a delivered order; refunds need a paid one.
* These are records in the development database created through the normal application, by you. Nothing in this
  guide resets or reseeds data.

## 4. Demonstration sequence (≈ 13 minutes)

| # | Min | What to show | What to do / say |
|---|---|---|---|
| 1 | 1:00 | Introduction and architecture | Show the architecture diagram (`project-report.md` §5): two storefronts, one backend, two databases, local whisper.cpp + optional local LLM. "Everything runs on this laptop; nothing is sent to the cloud." |
| 2 | 0:45 | Summit Trail Co. and Scout | Open :5180. Products in ₹. Open the chat: it opens **in Tamil** by default. |
| 3 | 0:45 | Bloom & Brew and Maple | Open :5181 in a second tab: different brand, catalogue and assistant. Chat also in Tamil. |
| 4 | 1:00 | Tamil voice | Scout: speak **T1**, then **T2** (§5). The language note says "detected from your words". |
| 5 | 0:45 | English voice | Scout: speak **E1** (cheapest sleeping bag → Alpine 20°F Sleeping Bag, ₹4,299.00 — not the pad or a daypack). |
| 6 | 0:45 | Hindi voice | Scout: speak **H1** (shipping → ₹149, free from ₹4,999, no delivery time promised). |
| 7 | 1:00 | Switching mid-conversation, context kept | Type/speak **S1** (Tamil, tent under ₹10,000) then **S2** (Hindi, "how heavy is it?") → Hindi answer about the **same tent**: 1.9 kg. Then **S3** (English "Add it to my cart"). |
| 8 | 1:00 | Discovery and comparison | Maple: **E2** (compare French press and pour-over dripper: both prices, which is cheaper). |
| 9 | 0:30 | INR budget filtering | Maple: **E3** (tea under ₹500) — two teas; then **E4** (a dollar budget) — honestly not converted. |
| 10 | 0:30 | Cart by conversation | Tap the **Add 1 × … to cart** button from step 7; the header cart count changes. "The assistant proposes; the customer confirms." |
| 11 | 1:30 | Complaint | Signed in as the demo customer (Scout): **C1** (Tamil, typed) → choose the order → item → describe → review → **ஆம்**. Read back the reference (`SA-CMP-…`). Show *My requests*. |
| 12 | 1:30 | Return + staff approval | **C2** (Hindi, spoken) on the delivered order → the policy window is stated → confirm with **हाँ**. Staff tab: **Customer care** → Returns → the request → *Start review* → *Approve*. Customer refreshes the request page: "Approved". |
| 13 | 1:15 | Simulated refund lifecycle | **C3** (English, spoken) → confirm. Staff: *Start review* → *Approve* → *Mark refund completed (simulated)*. Customer view: "Refund completed (simulated — no money moved)". |
| 14 | 1:15 | Human escalation + staff response | Maple: **C4** (Tamil, typed) → no order → reason → describe → confirm. Assistant says it is **recorded for staff review — not a live chat**. Staff: assign, send a message, *Mark in progress* → *Mark resolved*. Customer sees the message and "Resolved". Then **Q1** (status question in Hindi or English). |
| 15 | 1:00 | Store isolation and security | In Maple ask **E5** ("Do you sell tents?") → not sold here. Paste a Summit Trail request reference into Bloom & Brew's address bar → "not found". Mention: separate databases and roles, store-bound tokens, no card fields, internal notes never shown. |

Spare time: "What did I pay for my last order?" (**E6**), refresh the page mid-conversation (the chat is restored),
sign out (the chat is cleared).

## 5. Script — exact sentences

**Voice** = recommended to speak (recognised correctly in the measured synthetic tests); **type** = type or paste it.
Synthetic voices are not real speakers, so be ready to type any sentence (§6).

| ID | Store | Lang | Sentence | Mode | Expected answer |
|---|---|---|---|---|---|
| T1 | Scout | ta | உங்களிடம் இரண்டு பேர் தங்கும் கூடாரம் இருக்கிறதா? | voice | Tamil; Ridgeline 2-Person Tent ₹8,999.00 in stock (4-person shown as out of stock) |
| T2 | Scout | ta | என் ஆர்டர் எங்கே இருக்கிறது? | voice | Tamil; signed out → asks to sign in; signed in → the order's status |
| E1 | Scout | en | What's the cheapest sleeping bag? | voice | Alpine 20°F Sleeping Bag — ₹4,299.00 |
| H1 | Scout | hi | शिपिंग कितनी है? | voice | Hindi; ₹149, free from ₹4,999, no delivery time promised |
| S1 | Scout | ta | இரண்டு பேருக்கு ₹10,000க்குள் கூடாரம் இருக்கிறதா? | type (voice possible) | Tamil; Ridgeline 2-Person Tent ₹8,999.00 |
| S2 | Scout | hi | इसका वज़न कितना है? | type | Hindi; the Ridgeline tent weighs 1.9 kg (from the catalogue) |
| S3 | Scout | en | Add it to my cart | voice | English; button "Add 1 × Ridgeline 2-Person Tent to cart" |
| E2 | Maple | en | Compare the French press and the pour-over dripper | voice | both prices; the dripper is ₹400.00 cheaper |
| E3 | Maple | en | Which tea is under ₹500? | voice | Sencha Green Tea ₹449.00, Spiced Chai Blend ₹349.00 |
| E4 | Maple | en | Show me coffee under $10 | type | prices are in ₹; a dollar budget is not converted |
| E5 | Maple | en | Do you sell tents? | voice | not found at Bloom & Brew; lists its own categories |
| E6 | either | en | What did I pay for my last order? | voice | the order number and its recorded ₹ total, payment recorded |
| C1 | Scout | ta | எனக்கு தவறான பொருள் வந்துள்ளது | type | Tamil; asks which order |
| C2 | Scout | hi | मुझे अपना सामान वापस करना है | voice | Hindi; return request on the delivered order, policy window stated |
| C3 | either | en | I want to request a refund | voice | English; refund draft; "no real money is transferred" |
| C4 | Maple | ta | எனக்கு மனித உதவி வேண்டும் | type | Tamil; human-help request; recorded for staff review |
| Q1 | Scout | hi / en | मेरी शिकायत की स्थिति क्या है? / What is the status of my complaint? | type / voice | the reference, status and the staff message |
| — | both | ta / hi | confirm: ஆம் / हाँ / yes — cancel: ரத்து / रद्द / cancel | voice | submits only after this |

Other tested sentences for questions: Tamil "மிகவும் மலிவான தேநீர் எது?" (cheapest tea, type), Hindi "सबसे सस्ती चाय
कौन सी है?" (type), Hindi "मैंने कितना भुगतान किया?" (what did I pay, type), Tamil "டெலிவரிக்கு எத்தனை நாள் ஆகும்?" (type).

## 6. Staff walkthrough (steps 11–14)

1. Sign in as the store's staff agent in a **second browser window** (or a private window), so the customer stays signed in.
2. **Customer care** tab → choose the type chip (Complaints / Returns / Refunds (simulated) / Human help) → *Open* requests →
   click the reference.
3. The request page shows the customer, order, items, payment (sandbox), the return window, the history, and only
   the status changes allowed now.
4. **Assign to** → the agent → *Assign*. **Internal note** (never shown to the customer) → *Add note*.
5. Choose the next status → *Save*. *Reject* and *Close* require a message to the customer.
6. **Message to the customer** → *Send*. The customer sees it under the request and in the assistant's status answer.
7. Refunds: *Approve* → *Mark refund completed (simulated)*. Point out the notice: no payment provider is called and no
   payment row is created (tested).

## 7. If speech recognition fails (backup plan)

1. **Misheard once:** repeat more slowly, closer to the mic; or tap the language buttons if the assistant asks
   "தமிழ் / English / हिन्दी?" (it re-transcribes the same recording in that language).
2. **Misheard twice:** type or paste the sentence from §5. Everything except the microphone works the same way: the
   language is still identified from the text, and the answer is identical.
3. **No microphone / permission error:** the chat shows the reason; continue typing.
4. **Server speech unavailable** (`/api/speech/capabilities` shows server STT unavailable): continue typing; do not
   switch to the browser's cloud recogniser.
5. **Ollama not running:** no visible change except English policy answers come from the rule-based text (the
   assistant never depends on the model).
6. **Last resort:** show the recorded browser test run (`AVC_E2E_SPEECH=1 npx playwright test e2e/voice.spec.cjs`),
   which feeds synthetic Tamil / English / Hindi audio through the real recorder and whisper.cpp.

## 8. Honest limitations to state to examiners

* **Tamil speech recognition is the weakest part.** With the small `base` model, about half of clean synthetic Tamil
  phrases led to a clarification question rather than an answer (never a wrong-language answer); character error rate
  ≈ 0.3. Some misheard words change the outcome (e.g. "கொள்கை" (policy) heard as "கொள்ளை" starts a return request
  instead of answering — nothing is submitted without confirmation). A larger model was not downloaded; native-speaker
  testing has not been done.
* **Evaluation sets are small and written by the developer**, and some phrases were fixed during testing; the figures
  in `project-report.md` §16 are measured, not general accuracy claims.
* **Tamil and Hindi wording** has not been reviewed by native speakers; forms and staff screens are English.
* **No real payments, refunds, couriers or messages.** Sandbox payment; simulated refunds; notifications are queued and
  written to a local folder only when the background worker runs.
* **Support hours** shown are the original US time-zone values until confirmed; **seeded orders** are the original
  US-dollar demo orders, kept unchanged on purpose.
* **One staff account per store**; the phone channel is a simulator in English.

## 9. After the demonstration

Nothing needs undoing for safety. The demo customers, orders and care requests stay in the development database as
synthetic records; remove them only with a backed-up, approved procedure (`database-safety.md`).
