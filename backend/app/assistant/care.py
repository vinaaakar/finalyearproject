"""Customer-care handling: deliveries, cancellations, payments, refunds, returns, accounts, checkout help,
product comparison and alternatives, add-to-cart proposals, escalation to the human team, and more.

Rules (same as the rest of the assistant):
- Data comes only from the existing repository/commerce functions, scoped to the current store and, for
  private data, to the signed-in customer's own orders. Nothing is read from the message text except
  references (order numbers, product names), and every reference is re-checked against the database.
- Nothing here performs an action. Actions are PROPOSED as buttons (add to cart, cancel an unpaid order,
  links); the customer must tap them, and the existing API validates and performs the action, and the
  chat reports success only when that API call succeeds.
- Where the store has no capability (refund initiation, returns, invoices, discount codes, account edits,
  live agents, tickets), the reply says so and gives the real next step (the store's support e-mail).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from .. import commerce
from .. import repositories as repo
from ..commerce import MAX_LINE_QTY, CartOwner
from ..security import Principal
from ..stores import SHIPPING_EXCLUDED_REGIONS, STORE_BRANDING, StoreId
from . import care_text, i18n
from .intent import Intent, normalise_order_number, sensitive_kind

ORDER_CARE = {"order_late", "delivered_missing", "wrong_item", "missing_item", "damaged", "defective", "cancel",
              "modify_order", "payment_issue", "refund_status", "return_request", "exchange", "reorder", "invoice"}
_HUMAN_RE = re.compile(r"human|agent|representative|real person|speak to (someone|a person)|talk to (someone|a person)|"
                       r"மனிதர்|ஏஜென்ட்|பிரதிநிதி|एजेंट|इंसान|प्रतिनिधि|किसी व्यक्ति", re.I)
_DUPLICATE_RE = re.compile(r"twice|double|duplicate|two times|charged again|இரண்டு முறை|दो बार|दोबारा कट", re.I)
_REGION_NAMES = {"AK": "Alaska", "HI": "Hawaii"}
_OPEN = ("pending_payment", "processing", "shipped", "out_for_delivery")


@dataclass
class CareOutcome:
    lead: list[str] = field(default_factory=list)      # empathy, warnings
    body: list[str] = field(default_factory=list)      # the answer
    tail: list[str] = field(default_factory=list)      # escalation / contact
    skip: set[str] = field(default_factory=set)        # generic parts of compose() already covered here
    actions: list[dict[str, Any]] = field(default_factory=list)
    orders: list[dict[str, Any]] | None = None         # order cards to show (None = keep the generic ones)
    products: list[dict[str, Any]] | None = None       # product cards to show (None = keep the generic ones)
    requires_login: bool = False


def _iso(d: Any) -> str | None:
    return d.isoformat() if isinstance(d, date) else d


class CareDesk:
    def __init__(self, payments=None):
        self.payments = payments

    # ---- references from the conversation (re-validated against the database) ----------------------
    @staticmethod
    def history_order(history: list[dict[str, str]]) -> str | None:
        for turn in reversed(history or []):
            numbers = {normalise_order_number(m.group(0)) for m in re.finditer(r"\b[A-Za-z]{2}[-\s]?\d{5}\b", turn["content"])}
            numbers.discard(None)
            if turn["role"] == "user" and numbers:
                return sorted(numbers)[0] if len(numbers) == 1 else None
            if turn["role"] == "assistant" and len(numbers) == 1:
                return numbers.pop()
        return None

    @staticmethod
    def history_products(store: StoreId, history: list[dict[str, str]]) -> list[dict[str, Any]]:
        """Catalogue products named in recent turns, most recent turn first (in mention order within a turn)."""
        found: list[dict[str, Any]] = []
        for turn in reversed((history or [])[-6:]):
            # Matched in the database against this store's products only (no catalogue-size cap).
            for p in repo.products_mentioned_in(store, turn["content"]):
                if p["slug"] not in {f["slug"] for f in found}:
                    found.append(p)
            if found:
                break
        return found

    # ---- main entry ------------------------------------------------------------------------------------
    def handle(self, store: StoreId, message: str, intent: Intent, ctx: dict[str, Any], principal: Principal | None,
               owner: CartOwner | None, lang: str, history: list[dict[str, str]]) -> CareOutcome:
        out = CareOutcome()
        s = ctx["store"]
        email, hours, store_name = s["support_email"], s["support_hours"], s["name"]
        intents = intent.intents
        customer = principal is not None and principal.role == "customer" and principal.store == store
        email_action = {"type": "link", "to": f"mailto:{email}", "label": i18n.t(lang, "btn_email", email=email)}

        if intent.sensitive:
            out.lead.append(i18n.t(lang, "sensitive"))

        # ---- private order / payment care --------------------------------------------------------
        if intents & ORDER_CARE and not (principal is not None and principal.role == "agent"):
            out.skip.add("orders")
            if not customer:
                out.requires_login = True
                key = ("cancel_login" if "cancel" in intents else "pay_login" if "payment_issue" in intents
                       else "refund_login" if "refund_status" in intents else "order_login")
                out.body.append(i18n.t(lang, key))
                if "payment_issue" in intents and self._sandbox():
                    out.body.append(i18n.t(lang, "pay_sandbox").strip())
                if intents & {"damaged", "defective"}:
                    out.body.append(i18n.t(lang, "damaged_steps" if "damaged" in intents else "defective_steps", email=email))
                elif intents & {"wrong_item", "missing_item"}:
                    out.body.append(i18n.t(lang, "wrong_item_steps" if "wrong_item" in intents else "missing_item_steps", email=email))
                if intents & {"return_request", "exchange"}:
                    out.tail.append(i18n.t(lang, "return_how", email=email).strip())
                if "invoice" in intents:
                    out.body.append(i18n.t(lang, "invoice_none"))
                if intents & {"damaged", "defective", "wrong_item", "missing_item", "return_request", "exchange"}:
                    out.actions.append(email_action)
            else:
                self._orders_care(store, intent, ctx, principal, lang, history, out, email)
                if email in " ".join(out.body + out.tail) and email_action not in out.actions:
                    out.actions.append(email_action)  # the reply sends the customer to the team: give them the button

        # ---- products: compare, cheaper, alternatives, add to cart, care tips ---------------------------
        if intents & {"compare", "cheaper", "alternative", "add_to_cart", "care"}:
            self._product_care(store, intent, ctx, principal, owner, lang, history, out, email)

        # ---- accounts, checkout, store information -----------------------------------------------------
        if "account" in intents:
            self._account(intent, principal, store, lang, out, email)
        if "checkout_help" in intents:
            self._checkout(store, intent, ctx, principal, owner, lang, out, store_name)
        if "promotions" in intents:
            out.body.append(i18n.t(lang, "promo_none", store=store_name))
            rates = repo.get_shipping_rates(store)
            if rates["free_shipping_min_cents"] is not None:
                out.body.append(i18n.t(lang, "promo_free_ship", threshold=commerce.money(rates["free_shipping_min_cents"])).strip())
            out.skip |= {"products"}
        for key in ("privacy", "languages", "accessibility"):
            if key in intents:
                out.body.append(i18n.t(lang, key, store=store_name, email=email))
        if "bulk" in intents:
            out.body.append(i18n.t(lang, "bulk", email=email, hours=hours))
            out.actions.append(email_action)
        if "ticket" in intents:
            # There is no ticket system: say so plainly and give the real support route (never a fake ticket number).
            out.skip.add("contact")
            out.body.append(i18n.t(lang, "ticket_none", store=store_name, email=email, hours=hours))
            summary = self._summary(history, message, intent)
            if summary:
                out.tail.append(i18n.t(lang, "human_summary", summary=summary).strip())
            if email_action not in out.actions:
                out.actions.append(email_action)
        if "tech_issue" in intents:
            out.body.append(i18n.t(lang, "tech_issue", email=email))
            out.actions.append(email_action)

        # ---- people: frustration, explicit requests for a human -----------------------------------------
        wants_human = "contact" in intents and _HUMAN_RE.search(intent.raw)
        if "frustration" in intents:
            out.lead.insert(0, i18n.t(lang, "frustration"))
        if (wants_human or "frustration" in intents) and "ticket" not in intents:
            out.skip.add("contact")
            out.tail.append(i18n.t(lang, "human_no_agent", store=store_name, email=email, hours=hours))
            summary = self._summary(history, message, intent)
            if summary:
                out.tail.append(i18n.t(lang, "human_summary", summary=summary).strip())
            if email_action not in out.actions:
                out.actions.append(email_action)
        return out

    # ---- orders --------------------------------------------------------------------------------------
    def _orders_care(self, store: StoreId, intent: Intent, ctx: dict[str, Any], principal: Principal, lang: str,
                     history: list[dict[str, str]], out: CareOutcome, email: str) -> None:
        intents = intent.intents
        orders = repo.list_orders_for_customer(store, principal.customer_id)
        ref = intent.order_number or (self.history_order(history) if intent.refers_back else None)
        target = None
        if ref:
            target = next((o for o in orders if o["order_number"] == ref), None)
            if target is None:
                # Unknown or someone else's order: the same answer either way (no existence leak).
                out.body.append(i18n.t(lang, "order_not_found", number=ref, store=ctx["store"]["name"],
                                       prefix=ctx["store"]["order_number_prefix"]))
                out.orders = []
                return
        status = lambda o: i18n.status_label(lang, o["status"], o["status"].replace("_", " "))  # noqa: E731
        shown: list[dict[str, Any]] = []

        def show(o):
            if o not in shown:
                shown.append(o)

        if not orders:
            out.body.append(i18n.t(lang, "pay_no_orders" if "payment_issue" in intents else "no_orders", store=ctx["store"]["name"]))
            out.orders = []
            return

        if "cancel" in intents:
            pending = [o for o in orders if o["status"] == "pending_payment"]
            cand = target or (pending[0] if len(pending) == 1 else None)
            if cand is None and len(pending) > 1:
                out.body.append(i18n.t(lang, "cancel_which", list=", ".join(f"{o['order_number']} ({commerce.money(o['total_cents'])})" for o in pending)))
                for o in pending:
                    show(o)
            elif cand is None:
                out.body.append(i18n.t(lang, "cancel_none", email=email,
                                       list=", ".join(f"{o['order_number']}: {status(o)}" for o in orders[:3])))
            else:
                show(cand)
                if cand["status"] == "pending_payment":
                    label = i18n.t(lang, "btn_cancel", number=cand["order_number"])
                    out.body.append(i18n.t(lang, "cancel_ok", number=cand["order_number"], button=label))
                    out.actions.append({"type": "cancel_order", "order_number": cand["order_number"], "label": label})
                elif cand["status"] == "processing":
                    out.body.append(i18n.t(lang, "cancel_paid", number=cand["order_number"], status=status(cand), email=email))
                elif cand["status"] in ("shipped", "out_for_delivery", "delivered"):
                    out.body.append(i18n.t(lang, "cancel_shipped", number=cand["order_number"], status=status(cand)))
                else:
                    out.body.append(i18n.t(lang, "cancel_closed", number=cand["order_number"], status=status(cand)))

        if "modify_order" in intents:
            out.body.append(i18n.t(lang, "modify_no"))
            open_orders = [o for o in orders if o["status"] in ("pending_payment", "processing")]
            cand = target or (open_orders[0] if len(open_orders) == 1 else None)
            if cand:
                show(cand)
                key = {"pending_payment": "modify_unpaid", "processing": "modify_paid"}.get(cand["status"], "modify_shipped")
                out.body.append(i18n.t(lang, key, number=cand["order_number"], status=status(cand), email=email).strip())

        if "payment_issue" in intents:
            if _DUPLICATE_RE.search(intent.raw):
                out.body.append(i18n.t(lang, "pay_duplicate", email=email))
            pending = [o for o in orders if o["status"] == "pending_payment"]
            if not target and not pending:
                out.body.append(i18n.t(lang, "pay_all_settled"))
            cands = [target] if target else (pending[:2] or orders[:1])
            for o in cands:
                show(o)
                out.body.append(self._payment_line(store, principal, o, lang, email, out))
            if self._sandbox():
                out.body.append(i18n.t(lang, "pay_sandbox").strip())

        if "refund_status" in intents:
            lines = []
            for o in ([target] if target else orders):
                if o["status"] == "returned":
                    # No refund records exist (truth.refund_evidence): never imply one was issued.
                    lines.append(i18n.t(lang, "refund_returned", number=o["order_number"], email=email))
                    show(o)
                elif o["status"] == "cancelled":
                    p = self._latest_payment(store, principal, o)
                    if p and p["status"] == "succeeded":
                        lines.append(i18n.t(lang, "pay_cancelled_paid", number=o["order_number"], amount=p["amount"], email=email))
                        show(o)
            out.body.extend(lines or [i18n.t(lang, "refund_none", email=email)])

        if intents & {"return_request", "exchange"}:
            delivered = [o for o in orders if o["status"] == "delivered"]
            cand = target or (delivered[0] if len(delivered) == 1 else None)
            days = self._return_days(store)
            if cand:
                show(cand)
                if cand["status"] == "delivered" and days and cand["estimated_delivery"]:
                    until = cand["estimated_delivery"] + timedelta(days=days)
                    key = "return_eligible" if date.today() <= until else "return_expired"
                    out.body.append(i18n.t(lang, key, number=cand["order_number"], date=_iso(cand["estimated_delivery"]),
                                           days=days, until=until.isoformat()).strip())
                elif cand["status"] != "delivered":
                    out.body.append(i18n.t(lang, "return_not_delivered", number=cand["order_number"], status=status(cand)).strip())
            elif len(delivered) > 1:
                out.body.append(i18n.t(lang, "return_which", list=", ".join(
                    f"{o['order_number']} ({_iso(o['estimated_delivery'])})" for o in delivered[:4])).strip())
            if "exchange" in intents:
                out.body.append(i18n.t(lang, "exchange_steps", email=email).strip())
            out.tail.append(i18n.t(lang, "return_how", email=email).strip())

        if intents & {"order_late", "delivered_missing"}:
            if target:
                cands = [target]
            elif "delivered_missing" in intents:
                cands = [o for o in orders if o["status"] == "delivered"][:1]
            else:
                cands = [o for o in orders if o["status"] in _OPEN][:2] or orders[:1]
            late_tail = False
            for o in cands:
                show(o)
                n = o["order_number"]
                eta = o["estimated_delivery"]
                if o["status"] == "delivered":
                    on = i18n.t(lang, "on_date", date=_iso(eta)) if eta else ""
                    out.body.append(i18n.t(lang, "delivered_missing", number=n, on=on, email=email))
                elif o["status"] == "pending_payment":
                    out.body.append(i18n.t(lang, "late_unpaid", number=n))
                    out.actions.append({"type": "link", "to": f"/orders/{n}/pay", "label": i18n.t(lang, "btn_pay", number=n)})
                elif o["status"] == "processing":
                    out.body.append(i18n.t(lang, "late_processing", number=n))
                    late_tail = True
                elif o["status"] in ("shipped", "out_for_delivery"):
                    line = i18n.t(lang, "late_overdue" if eta and eta < date.today() else "late_on_track", number=n, date=_iso(eta)) \
                        if eta else i18n.t(lang, "order_line", number=n, status=status(o)) + i18n.end(lang)
                    if o["carrier"] and o["tracking_number"]:
                        line += i18n.t(lang, "late_carrier", carrier=o["carrier"], tracking=o["tracking_number"])
                    out.body.append(line)
                    late_tail = True
                else:
                    out.body.append(i18n.t(lang, "cancel_closed", number=n, status=status(o)))
            if late_tail:
                out.tail.append(i18n.t(lang, "late_next", email=email).strip())

        if intents & {"damaged", "defective", "wrong_item", "missing_item"}:
            key = ("damaged_steps" if "damaged" in intents else "defective_steps" if "defective" in intents
                   else "wrong_item_steps" if "wrong_item" in intents else "missing_item_steps")
            out.body.append(i18n.t(lang, key, email=email))
            cand = target or next((o for o in orders if o["status"] == "delivered"), None)
            if cand:
                show(cand)

        if "reorder" in intents:
            last = target or next((o for o in orders if o["status"] != "cancelled" and o.get("items")), None)
            if last is None:
                out.body.append(i18n.t(lang, "reorder_none"))
            else:
                show(last)
                out.body.append(i18n.t(lang, "reorder_items", number=last["order_number"],
                                       items=", ".join(f"{i['quantity']} × {i['name']}" for i in last["items"])))
                for item in last["items"][:4]:
                    p = repo.get_product_by_slug(store, item["slug"])
                    if p and p["stock_qty"] > 0:
                        q = max(1, min(item["quantity"], MAX_LINE_QTY, p["stock_qty"]))
                        out.actions.append({"type": "add_to_cart", "slug": p["slug"], "name": p["name"], "quantity": q,
                                            "label": i18n.t(lang, "btn_add", qty=q, name=p["name"])})
                    elif p:
                        out.body.append(i18n.t(lang, "reorder_out", name=p["name"]).strip())

        if "invoice" in intents:
            out.body.append(i18n.t(lang, "invoice_none"))
            o = target or orders[0]
            show(o)
            if o.get("subtotal_cents") is not None and o.get("shipping_cents") is not None:
                out.body.append(i18n.t(lang, "invoice_breakdown", number=o["order_number"], subtotal=commerce.money(o["subtotal_cents"]),
                                       shipping=commerce.money(o["shipping_cents"]), total=commerce.money(o["total_cents"])).strip())
            else:
                out.body.append(i18n.t(lang, "invoice_order", number=o["order_number"], total=commerce.money(o["total_cents"])).strip())
            out.actions.append({"type": "link", "to": "/account", "label": i18n.t(lang, "btn_orders")})

        if not out.body:
            out.skip.discard("orders")   # nothing specific to say: fall back to the normal order lines
        from .service import public_order  # local import: service imports this module
        out.orders = [public_order(o) for o in shown] if shown else out.orders

    def _payment_line(self, store: StoreId, principal: Principal, o: dict[str, Any], lang: str, email: str, out: CareOutcome) -> str:
        n = o["order_number"]
        p = self._latest_payment(store, principal, o)
        status = i18n.status_label(lang, o["status"], o["status"].replace("_", " "))
        if o["status"] == "pending_payment":
            out.actions.append({"type": "link", "to": f"/orders/{n}/pay", "label": i18n.t(lang, "btn_pay", number=n)})
            if p and p["status"] == "failed":
                return i18n.t(lang, "pay_failed", number=n)
            if p and p["status"] == "pending":
                return i18n.t(lang, "pay_pending", number=n)
            return i18n.t(lang, "pay_none", number=n)
        if o["status"] == "cancelled":
            if p and p["status"] == "succeeded":
                return i18n.t(lang, "pay_cancelled_paid", number=n, amount=p["amount"], email=email)
            return i18n.t(lang, "cancel_closed", number=n, status=status)
        if p and p["status"] == "succeeded":
            return i18n.t(lang, "pay_ok", number=n, amount=p["amount"], status=status)
        # Seeded/older orders may have no payment record: report only what is recorded.
        return i18n.t(lang, "order_line", number=n, status=status) + i18n.end(lang)

    def _latest_payment(self, store: StoreId, principal: Principal, o: dict[str, Any]) -> dict[str, Any] | None:
        if self.payments is None:
            return None
        return commerce.latest_payment(store, principal.customer_id, o["order_number"], self.payments)

    def _sandbox(self) -> bool:
        return bool(self.payments is not None and self.payments.sandbox)

    @staticmethod
    def _return_days(store: StoreId) -> int | None:
        text = repo.get_policies(store, "en").get("returns", {}).get("details", "")
        m = re.search(r"within (\d{1,3}) days", text)
        return int(m.group(1)) if m else None

    # ---- products ------------------------------------------------------------------------------------
    def _product_care(self, store: StoreId, intent: Intent, ctx: dict[str, Any], principal: Principal | None,
                      owner: CartOwner | None, lang: str, history: list[dict[str, str]], out: CareOutcome, email: str) -> None:
        from .service import public_product  # local import: service imports this module
        intents = intent.intents
        found = repo.search_products_by_terms(store, intent.search_terms, limit=5) if intent.search_terms else []
        top = [p for p in found if p["score"] == found[0]["score"]] if found else []
        hist = self.history_products(store, history)
        # Same-category lookups go to the database per category (not a capped copy of the whole catalogue).
        def in_category(cat: str) -> list[dict[str, Any]]:
            return repo.list_products(store, category=cat, limit=500)

        def stock(p):
            if p["stock_qty"] <= 0:
                return i18n.t(lang, "out_of_stock")
            return i18n.t(lang, "low_stock", n=p["stock_qty"]) if p["stock_qty"] <= 5 else i18n.t(lang, "in_stock")

        if "compare" in intents:
            out.skip.add("products")
            picks = (found[:3] if len(found) >= 2 else (found + [h for h in hist if h["slug"] not in {f["slug"] for f in found}])[:3])
            if len(picks) < 2:
                out.body.append(i18n.t(lang, "compare_need_two"))
            else:
                lines = []
                for p in picks:
                    desc = f": {p['description'].rstrip('.')}" if lang == "en" else ""
                    lines.append(f"{p['name']} — {commerce.money(p['price_cents'])}, {stock(p)}{desc}")
                text = i18n.t(lang, "compare_intro") + "; ".join(lines) + i18n.end(lang)
                a, b = sorted(picks[:2], key=lambda p: p["price_cents"])
                if a["price_cents"] < b["price_cents"]:
                    text += i18n.t(lang, "compare_cheaper", name=a["name"], diff=commerce.money(b["price_cents"] - a["price_cents"]))
                out.body.append(text)
                out.products = [public_product(p) for p in picks]

        if intents & {"cheaper", "alternative"} and "compare" not in intents:
            out.skip.add("products")
            ref = top[0] if len(top) == 1 else (hist[0] if hist else None)
            if ref is None and found:
                ref = found[0]
            if ref is None:
                out.body.append(i18n.t(lang, "cheaper_which" if "cheaper" in intents else "add_unknown"))
                out.products = []
            else:
                same = [p for p in in_category(ref["category"]) if p["slug"] != ref["slug"] and p["stock_qty"] > 0]
                if "cheaper" in intents:
                    # Same kind of product only: a cheaper backpack is not a cheaper tent.
                    cheaper = sorted((p for p in same if p["price_cents"] < ref["price_cents"]), key=lambda p: -p["price_cents"])
                    if cheaper:
                        out.body.append(i18n.t(lang, "cheaper_found", name=ref["name"], price=commerce.money(ref["price_cents"]))
                                        + "; ".join(f"{p['name']} — {commerce.money(p['price_cents'])}, {stock(p)}" for p in cheaper[:3])
                                        + i18n.end(lang))
                        out.products = [public_product(p) for p in cheaper[:3]]
                    else:
                        out.body.append(i18n.t(lang, "cheaper_none", name=ref["name"], price=commerce.money(ref["price_cents"]),
                                               category=i18n.category(lang, ref["category"])))
                        out.products = [public_product(ref)]
                else:
                    if same:
                        out.body.append(i18n.t(lang, "alternatives", list=", ".join(
                            f"{p['name']} ({commerce.money(p['price_cents'])})" for p in same[:3])).strip())
                        out.products = [public_product(p) for p in same[:3]]
                    else:
                        out.body.append(i18n.t(lang, "alt_none").strip())

        if "add_to_cart" in intents:
            out.skip.add("products")
            if principal is not None and principal.role == "agent":
                out.body.append(i18n.t(lang, "add_staff"))
            else:
                product = top[0] if len(top) == 1 else (None if top else (hist[0] if hist else None))
                if product is None and len(top) > 1:
                    out.body.append(i18n.t(lang, "add_which", list=", ".join(
                        f"{p['name']} ({commerce.money(p['price_cents'])})" for p in top[:3])))
                    out.products = [public_product(p) for p in top[:3]]
                elif product is None:
                    out.body.append(i18n.t(lang, "add_unknown"))
                    out.products = []
                elif product["stock_qty"] <= 0:
                    out.body.append(i18n.t(lang, "add_out", name=product["name"]))
                    alts = [p for p in in_category(product["category"]) if p["stock_qty"] > 0]
                    out.body.append(i18n.t(lang, "alternatives", list=", ".join(
                        f"{p['name']} ({commerce.money(p['price_cents'])})" for p in alts[:3])).strip() if alts
                        else i18n.t(lang, "alt_none").strip())
                    out.products = [public_product(p) for p in [product, *alts[:2]]]
                else:
                    in_cart = 0
                    if owner is not None and (owner.customer_id or owner.guest_hash):
                        cart = commerce.get_cart(store, owner)
                        in_cart = next((i["quantity"] for i in cart["items"] if i["slug"] == product["slug"]), 0)
                    room = min(MAX_LINE_QTY, product["stock_qty"]) - in_cart
                    qty = min(intent.quantity, room)
                    if intent.quantity > room:
                        out.body.append(i18n.t(lang, "add_limit", name=product["name"], max=max(room, 0), stock=product["stock_qty"]))
                    if qty >= 1:
                        label = i18n.t(lang, "btn_add", qty=qty, name=product["name"])
                        out.body.append(i18n.t(lang, "add_confirm", name=product["name"], price=commerce.money(product["price_cents"]), button=label))
                        out.actions.append({"type": "add_to_cart", "slug": product["slug"], "name": product["name"],
                                            "quantity": qty, "label": label})
                    out.products = [public_product(product)]

        if "care" in intents:
            out.skip.add("products")
            tips = care_text.TIPS.get(store.value, {})
            words = list(intent.search_terms) + [w for p in (top[:1] or hist[:1]) for w in re.split(r"[-\s]", p["slug"] + " " + p["name"].lower())]
            key = next((care_text.TIP_ALIASES[w] for w in words if w in care_text.TIP_ALIASES and care_text.TIP_ALIASES[w] in tips), None)
            if key:
                out.body.append(i18n.t(lang, "care_intro") + tips[key][lang] + i18n.t(lang, "care_safety"))
            else:
                out.body.append(i18n.t(lang, "care_none", email=email))

    # ---- accounts & checkout -------------------------------------------------------------------------
    @staticmethod
    def _account(intent: Intent, principal: Principal | None, store: StoreId, lang: str, out: CareOutcome, email: str) -> None:
        raw = intent.raw
        store_name = STORE_BRANDING[store]["name"]
        if re.search(r"delete|close my account|remove my account|நீக்க|डिलीट|हटा", raw):
            out.body.append(i18n.t(lang, "acct_delete", email=email))
        elif re.search(r"change my (email|name)|update my|edit my (details|profile)|account details|மாற்ற|बदल", raw):
            out.body.append(i18n.t(lang, "acct_update", email=email))
        elif re.search(r"password|forgot|reset|கடவுச்சொல்|பாஸ்வேர்டு|पासवर्ड", raw):
            out.body.append(i18n.t(lang, "acct_password"))
            out.actions.append({"type": "link", "to": "/forgot-password", "label": i18n.t(lang, "btn_reset")})
        elif re.search(r"register|sign ?up|create (an )?account|உருவாக்க|रजिस्टर|अकाउंट बना", raw):
            out.body.append(i18n.t(lang, "acct_register"))
            out.actions.append({"type": "link", "to": "/register", "label": i18n.t(lang, "btn_register")})
        else:
            out.body.append(i18n.t(lang, "acct_signin", store=store_name))
            out.actions.append({"type": "link", "to": "/account", "label": i18n.t(lang, "btn_orders" if principal else "btn_signin")})
            if not principal:
                out.actions.append({"type": "link", "to": "/forgot-password", "label": i18n.t(lang, "btn_reset")})
        if principal is not None:
            out.body.append(i18n.t(lang, "acct_history"))

    @staticmethod
    def _checkout(store: StoreId, intent: Intent, ctx: dict[str, Any], principal: Principal | None, owner: CartOwner | None,
                  lang: str, out: CareOutcome, store_name: str) -> None:
        raw = intent.raw
        asks_errors = re.search(r"error|zip|total|address|invalid|changed|wrong|message|பிழை|एरर|ग़लत|गलत", raw)
        asks_region = re.search(r"alaska|hawaii|ship to|deliver to|state|அனுப்ப|डिलीवरी", raw)
        asks_how = re.search(r"how|steps|guest|without an account|place|எப்படி|कैसे|गेस्ट", raw) or not (asks_errors or asks_region)
        if asks_how:
            out.body.append(i18n.t(lang, "checkout_steps"))
        if principal is None and asks_how or re.search(r"guest|without an account|விருந்தினர்|गेस्ट|बिना अकाउंट", raw):
            out.body.append(i18n.t(lang, "checkout_guest").strip())
        excluded = sorted(SHIPPING_EXCLUDED_REGIONS[store])
        if excluded and (asks_region or asks_how):
            out.body.append(i18n.t(lang, "checkout_regions", store=store_name,
                                   regions=" & ".join(_REGION_NAMES.get(r, r) for r in excluded)).strip())
        if asks_errors:
            out.body.append(i18n.t(lang, "checkout_errors").strip())
        if re.search(r"limit|how many|maximum|quantity|எத்தனை|कितने", raw):
            out.body.append(i18n.t(lang, "cart_limit").strip())
        if owner is not None and (owner.customer_id or owner.guest_hash):
            cart = commerce.get_cart(store, owner)
            for i in cart["items"]:
                if i["stock_qty"] <= 0:
                    out.body.append(i18n.t(lang, "cart_out", name=i["name"]))
                elif i["quantity"] > i["stock_qty"]:
                    out.body.append(i18n.t(lang, "cart_short", name=i["name"], n=i["stock_qty"]))
        if not asks_how:
            return
        out.actions.append({"type": "link", "to": "/cart", "label": i18n.t(lang, "btn_cart")})
        if principal is not None and principal.role == "customer":
            out.actions.append({"type": "link", "to": "/checkout", "label": i18n.t(lang, "btn_checkout")})
        elif principal is None:
            out.actions.append({"type": "link", "to": "/account?next=/checkout", "label": i18n.t(lang, "btn_signin")})
            out.actions.append({"type": "link", "to": "/register?next=/checkout", "label": i18n.t(lang, "btn_register")})

    # ---- escalation summary -----------------------------------------------------------------------------
    @staticmethod
    def _summary(history: list[dict[str, str]], message: str, intent: Intent) -> str:
        """The customer's own recent words (never secrets), so they don't have to explain again."""
        said = [t["content"] for t in (history or []) if t["role"] == "user" and not sensitive_kind(t["content"])][-2:]
        if len(message) > 25 and not intent.sensitive:
            said.append(message.strip())
        said = [s[:120] + ("…" if len(s) > 120 else "") for s in said]
        return " / ".join(f"“{s}”" for s in said)
