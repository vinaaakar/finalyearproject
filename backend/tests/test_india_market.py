"""India-only deployment (this project's configuration), both stores: the academic demonstration INR price list
(config/pricing/demo-inr-prices.json) and demonstration India shipping (config/shipping/*.json), exactly as configured
for the demo. Checks one price source everywhere — catalogue, cart, checkout, orders, staff screens, payments and the
assistants Scout and Maple in Tamil, English and Hindi — never a USD amount, never a converted or invented one."""

from __future__ import annotations

import dataclasses
import json
import re

import pytest

from app import demo_prices
from app.config import PROJECT_ROOT
from app.markets import format_money
from app.seed import AGENT_PASSWORD

from .conftest import AGENT_A, AGENT_B, db_exec, idem, login, make_client, new_customer, set_stock
from .test_multilingual_acceptance import chat, reply_script

LIST = demo_prices.load_list()
LABEL = LIST["approved_by"]
SHIPPING = {s: json.loads((PROJECT_ROOT / "config" / "shipping" / f"{s}.json").read_text())["IN"][0] for s in ("store-a", "store-b")}
CUMBUM = {"full_name": "Priya Raman", "line1": "12 Kambam Main Road", "line2": "Near the bus stand", "city": "Cumbum",
          "region": "TN", "postal_code": "625521", "country": "IN", "phone": "+91 98765 43210"}
INR = lambda paise: format_money(paise, "INR")  # noqa: E731
USD_RE = re.compile(r"\$|\bUSD\b|dollar", re.I)


@pytest.fixture(scope="module")
def india_settings(settings):
    return dataclasses.replace(settings, store_markets={"store-a": "IN", "store-b": "IN"}, checkout_countries=("IN",),
                               shipping_config_dir=PROJECT_ROOT / "config" / "shipping")


@pytest.fixture(scope="module", autouse=True)
def demo_list(settings):
    """The demonstration price list in the TEST databases for this module; removed afterwards."""
    demo_prices.apply(settings.store_database_urls, LIST)
    yield
    for store in ("store-a", "store-b"):
        db_exec(settings, store, "DELETE FROM product_prices WHERE approved_by = %s", [LABEL])


@pytest.fixture
def ic(india_settings):
    with make_client(india_settings) as c:
        yield c


def _customer(c, store, slug, qty=1):
    set_stock(c.app.state.settings, store, slug, 60)
    h, _ = new_customer(c, store)
    r = c.post(f"/api/stores/{store}/cart/items", json={"slug": slug, "quantity": qty}, headers=h)
    assert r.status_code == 200, r.text
    return h, r.json()["cart"]


# ---- configuration -----------------------------------------------------------------------------------------------------
def test_demo_price_list_is_complete_labelled_and_whole_rupees(settings):
    for store in ("store-a", "store-b"):
        slugs = {r[0] for r in db_exec(settings, store, "SELECT slug FROM products")}
        assert set(LIST[store]) == slugs                                           # every product of THIS store, no other
    assert "demonstration" in LABEL and "not commercial" in LABEL
    assert set(LIST["store-a"]).isdisjoint(LIST["store-b"])
    for bad in ({**LIST, "store-a": {**LIST["store-a"], "lumen-300-headlamp": 89950}},     # not whole rupees
                {**LIST, "approved_by": "price list"}):                                  # not labelled as demonstration
        with pytest.raises(ValueError):
            (PROJECT_ROOT / "backend" / "tests" / "fixtures").mkdir(exist_ok=True)
            p = PROJECT_ROOT / "backend" / "tests" / "fixtures" / "_bad_list.json"
            p.write_text(json.dumps(bad))
            try:
                demo_prices.load_list(p)
            finally:
                p.unlink()
    with pytest.raises(ValueError, match="unknown products"):
        demo_prices.apply(settings.store_database_urls, {**LIST, "store-b": {**LIST["store-b"], "lumen-300-headlamp": 89900}}, dry_run=True)


def test_shipping_configuration_is_demonstration_inr_all_india_without_promises():
    for store, z in SHIPPING.items():
        assert z["currency"] == "INR" and len(z["regions"]) == 36 and "demonstration" in z["name"]
        assert "eta_min_days" not in z and z["expedited_cents"] is None


def test_health_reports_india_selling_status(ic):
    selling = ic.get("/api/health").json()["selling"]
    for store in ("store-a", "store-b"):
        assert selling[store] == {"market": "IN", "currency": "INR", "products": 10, "priced": 10, "prices_complete": True,
                                  "shipping_configured": True}


# ---- storefront: catalogue, policies, address options --------------------------------------------------------------------
@pytest.mark.parametrize("store", ["store-a", "store-b"])
def test_catalogue_is_in_approved_inr_only(ic, store):
    products = ic.get(f"/api/stores/{store}/products").json()["products"]
    assert {p["slug"]: p["price_cents"] for p in products} == LIST[store]           # exactly the approved list
    for p in products:
        assert p["currency"] == "INR" and p["price"] == INR(LIST[store][p["slug"]]) and p["prices"] == {"INR": {"minor": p["price_cents"], "display": p["price"]}}
    assert not USD_RE.search(json.dumps(products, ensure_ascii=False))
    one = ic.get(f"/api/stores/{store}/products/{products[0]['slug']}").json()["product"]
    assert one["price"] == products[0]["price"]
    assert ic.get(f"/api/stores/{store}").json()["currency"] == "INR"


@pytest.mark.parametrize("store", ["store-a", "store-b"])
def test_policies_are_demonstration_india_text_in_three_languages(ic, store):
    z = SHIPPING[store]
    for lang in ("en", "ta", "hi"):
        pol = ic.get(f"/api/stores/{store}?lang={lang}").json()["policies"]
        ship = pol["shipping"]["details"]
        assert INR(z["standard_cents"]) in ship and INR(z["free_over_cents"]) in ship and not USD_RE.search(json.dumps(pol, ensure_ascii=False))
        assert "US" not in ship and "contiguous" not in ship
        assert {"en": "Demonstration", "ta": "மாதிரி", "hi": "डेमो"}[lang] in ship
        assert pol["returns"]["summary"].startswith({"en": "Demonstration policy", "ta": "மாதிரி கொள்கை", "hi": "डेमो नीति"}[lang])


def test_address_options_offer_india_only(ic):
    h, _ = _customer(ic, "store-a", "lumen-300-headlamp")
    d = ic.get("/api/stores/store-a/checkout/address-options", headers=h).json()
    assert [c["code"] for c in d["countries"]] == ["IN"] and d["default_country"] == "IN"
    assert d["countries"][0]["prices_configured"] and d["countries"][0]["shipping_configured"]


# ---- cart, shipping, checkout, orders, payments ---------------------------------------------------------------------------
@pytest.mark.parametrize("store, slug", [("store-a", "lumen-300-headlamp"), ("store-b", "wildflower-honey")])
def test_cart_and_quote_in_inr_with_the_configured_demo_shipping(ic, store, slug):
    z = SHIPPING[store]
    h, cart = _customer(ic, store, slug)
    paise = LIST[store][slug]
    assert cart["currency"] == "INR" and cart["subtotal_cents"] == paise and cart["shipping"] is None    # shipping at checkout
    assert not USD_RE.search(json.dumps(ic.get(f"/api/stores/{store}/cart", headers=h).json(), ensure_ascii=False))
    q = ic.post(f"/api/stores/{store}/checkout/quote", headers=h, json={"shipping_method": "standard",
                "destination": {"country": "IN", "region": "TN", "postal_code": "625521"}}).json()["cart"]
    fee = 0 if paise >= z["free_over_cents"] else z["standard_cents"]
    assert q["shipping_cents"] == fee and q["total_cents"] == paise + fee and q["can_checkout"]
    assert [o["label"] for o in q["shipping_options"]] == ["Standard delivery"]               # no expedited, no delivery promise
    assert q["shipping_options"][0]["price"] == INR(fee) and not USD_RE.search(json.dumps(q, ensure_ascii=False))


@pytest.mark.parametrize("store, slug, qty", [("store-a", "lumen-300-headlamp", 6), ("store-b", "classic-french-press", 1)])
def test_free_delivery_threshold_comes_from_the_same_configuration(ic, store, slug, qty):
    z = SHIPPING[store]
    h, cart = _customer(ic, store, slug, qty)
    assert cart["subtotal_cents"] >= z["free_over_cents"]
    q = ic.post(f"/api/stores/{store}/checkout/quote", headers=h, json={"shipping_method": "standard",
                "destination": {"country": "IN", "region": "DL", "postal_code": "110001"}}).json()["cart"]
    assert q["shipping_cents"] == 0 and q["total_cents"] == cart["subtotal_cents"]


@pytest.mark.parametrize("store, slug", [("store-a", "pocketflame-stove"), ("store-b", "sencha-green-tea")])
def test_full_india_order_in_inr_and_history_unchanged(ic, store, slug):
    c = ic
    s = c.app.state.settings
    before = db_exec(s, store, "SELECT order_number, currency, total_cents FROM orders WHERE currency = 'USD' ORDER BY order_number")
    h, _ = _customer(c, store, slug)
    q = c.post(f"/api/stores/{store}/checkout/quote", headers=h, json={"shipping_method": "standard",
               "destination": {"country": "IN", "region": "TN", "postal_code": "625521"}}).json()["cart"]
    r = c.post(f"/api/stores/{store}/checkout", headers={**h, **idem()}, json={"shipping": CUMBUM, "expected_total_cents": q["total_cents"]})
    assert r.status_code == 201, r.text
    number = r.json()["order"]["order_number"]
    try:
        o = c.get(f"/api/stores/{store}/orders/{number}", headers=h).json()["order"]
        assert o["currency"] == "INR" and o["total"] == INR(q["total_cents"]) and o["items"][0]["unit_price"] == INR(LIST[store][slug])
        assert o["shipping_address"]["country"] == "IN" and o["shipping_address"]["phone"] == "+919876543210"
        assert not USD_RE.search(json.dumps(o, ensure_ascii=False))
        agent = login(c, store, AGENT_A if store == "store-a" else AGENT_B, AGENT_PASSWORD)
        assert c.get(f"/api/stores/{store}/staff/orders/{number}", headers=agent).json()["order"]["total"] == o["total"]
        pay = c.post(f"/api/stores/{store}/orders/{number}/payments", headers=h).json()["payment"]
        assert pay["amount"] == o["total"]
        other = "store-b" if store == "store-a" else "store-a"
        other_agent = login(c, other, AGENT_B if other == "store-b" else AGENT_A, AGENT_PASSWORD)
        assert c.get(f"/api/stores/{other}/staff/orders/{number}", headers=other_agent).status_code == 404
    finally:
        c.post(f"/api/stores/{store}/orders/{number}/cancel", headers=h)
    after = db_exec(s, store, "SELECT order_number, currency, total_cents FROM orders WHERE currency = 'USD' ORDER BY order_number")
    assert after == before                                          # historical USD orders untouched


def test_every_indian_state_and_union_territory_can_be_ordered_to(ic):
    """All 36 codes are accepted by the API (a US-only schema check once refused e.g. Karnataka "KA"); a US state is not."""
    from app.markets import MARKETS
    store, slug = "store-b", "spiced-chai-blend"
    h, _ = _customer(ic, store, slug)
    codes = [code for code, _, _ in MARKETS["IN"].regions]
    assert len(codes) == 36
    for code in codes:
        q = ic.post(f"/api/stores/{store}/checkout/quote", headers=h, json={"shipping_method": "standard",
                    "destination": {"country": "IN", "region": code, "postal_code": "560001"}}).json()["cart"]
        assert q["can_checkout"], code
    for code in ("KA", "MH", "KL", "UP", "LA"):                              # LA = Ladakh (not Louisiana)
        q = ic.post(f"/api/stores/{store}/checkout/quote", headers=h, json={"shipping_method": "standard",
                    "destination": {"country": "IN", "region": code, "postal_code": "560001"}}).json()["cart"]
        r = ic.post(f"/api/stores/{store}/checkout", headers={**h, **idem()},
                    json={"shipping": {**CUMBUM, "region": code, "postal_code": "560001"}, "expected_total_cents": q["total_cents"]})
        assert r.status_code == 201, (code, r.text)
        number = r.json()["order"]["order_number"]
        assert ic.get(f"/api/stores/{store}/orders/{number}", headers=h).json()["order"]["shipping_address"]["region"] == code
        ic.post(f"/api/stores/{store}/orders/{number}/cancel", headers=h)
        ic.post(f"/api/stores/{store}/cart/items", json={"slug": slug, "quantity": 1}, headers=h)
    r = ic.post(f"/api/stores/{store}/checkout", headers={**h, **idem()},
                json={"shipping": {**CUMBUM, "region": "CO"}, "expected_total_cents": 1})
    assert r.status_code == 422 and "shipping.region" in r.text


def test_missing_inr_price_is_never_invented_and_blocks_checkout(ic, settings):
    store, slug = "store-a", "granite-hiking-boots"
    db_exec(settings, store, "DELETE FROM product_prices WHERE product_id = (SELECT id FROM products WHERE slug = %s)", [slug])
    try:
        p = ic.get(f"/api/stores/{store}/products/{slug}").json()["product"]
        assert p["price"] is None and p["price_cents"] is None and p["prices"] == {"INR": None}
        h, cart = _customer(ic, store, slug)
        assert cart["prices_available"] is False and cart["total"] is None and not USD_RE.search(json.dumps(cart, ensure_ascii=False))
        r = ic.post(f"/api/stores/{store}/checkout", headers={**h, **idem()}, json={"shipping": CUMBUM, "expected_total_cents": 18900})
        assert r.status_code == 409 and r.json()["error"]["code"] == "price_not_configured"
        j = chat(ic, store, "What is the price of the Granite Hiking Boots?", [], "en")
        assert "price in ₹ not set yet" in j["reply"] and not USD_RE.search(j["reply"]) and "189" not in j["reply"]
        assert j["products"][0]["price"] is None
    finally:
        demo_prices.apply(settings.store_database_urls, LIST)


# ---- the assistants: one price source, three languages ----------------------------------------------------------------------
PRODUCT = {"store-a": ("Lumen 300 Headlamp", "lumen-300-headlamp"), "store-b": ("Wildflower Honey", "wildflower-honey")}


@pytest.mark.parametrize("store", ["store-a", "store-b"])
def test_price_answers_quote_the_exact_approved_inr_price_in_three_languages(ic, store):
    name, slug = PRODUCT[store]
    price = INR(LIST[store][slug])
    history: list = []
    en = chat(ic, store, f"What is the price of the {name}?", history, "en")
    assert en["language"] == "en" and price in en["reply"] and not USD_RE.search(en["reply"])
    assert {p["slug"]: p["price"] for p in en["products"]}[slug] == price                 # the chat product card
    ta = chat(ic, store, "இந்த பொருளின் விலை என்ன?", history, "en")
    assert ta["language"] == "ta" and price in ta["reply"] and reply_script(ta["reply"]) == "ta" and not USD_RE.search(ta["reply"])
    hi = chat(ic, store, "इसकी कीमत कितनी है?", history, "ta")
    assert hi["language"] == "hi" and price in hi["reply"] and reply_script(hi["reply"]) == "hi" and not USD_RE.search(hi["reply"])
    assert all(p["price"] == price for p in hi["products"] if p["slug"] == slug)


def test_compare_uses_inr_prices_and_the_difference(ic):
    j = chat(ic, "store-a", "Compare the Ridgeline 2P Tent and the Basecamp 4P Tent", [], "en")
    a, b = LIST["store-a"]["ridgeline-2p-tent"], LIST["store-a"]["basecamp-4p-tent"]
    assert INR(a) in j["reply"] and INR(b) in j["reply"] and INR(b - a) in j["reply"] and not USD_RE.search(j["reply"])


@pytest.mark.parametrize("store", ["store-a", "store-b"])
def test_rupee_budget_filters_on_the_approved_inr_prices(ic, store):
    j = chat(ic, store, "Show me products under ₹2,000", [], "en")
    assert j["products"] and "₹2,000" in j["reply"] and not USD_RE.search(j["reply"])
    for p in j["products"]:
        assert p["price_cents"] is not None and p["price_cents"] <= 200000 and p["price_cents"] == LIST[store][p["slug"]]


def test_dollar_budget_is_not_converted(ic):
    j = chat(ic, "store-b", "Show me coffee beans under 20 dollars", [], "en")
    assert "Indian rupees" in j["reply"] and "exchange rate" in j["reply"]
    for p in j["products"]:
        assert p["price"].startswith("₹")


@pytest.mark.parametrize("store", ["store-a", "store-b"])
def test_four_turn_language_switching_keeps_context_and_inr(ic, store):
    from .test_multilingual_acceptance import EXPECTED_LANGS, SCENARIOS
    turns, about, foreign = SCENARIOS[store]
    history, conv = [], "ta"
    for msg, want in zip(turns, EXPECTED_LANGS):
        j = chat(ic, store, msg, history, conv)
        conv = j["language"]
        assert j["language"] == want, (msg, j["reply"])
        # The only dollar amount allowed is the customer's own budget, repeated while declining to convert it.
        assert not USD_RE.search(re.sub(r"apply an? \$\d+(?:\.\d\d)? budget|\$\d+(?:\.\d\d)? (?:பட்ஜெட்|का बजट)", "", j["reply"])), j["reply"]
        assert foreign not in {p["slug"] for p in j["products"]}                   # never the other store's product
        for p in j["products"]:
            assert p["price"] == INR(LIST[store][p["slug"]])
    assert {p["slug"] for p in j["products"]} & about                               # still about the same products


@pytest.mark.parametrize("store", ["store-a", "store-b"])
def test_cart_and_shipping_answers_use_inr(ic, store):
    name, slug = PRODUCT[store]
    h, _ = _customer(ic, store, slug)
    j = chat(ic, store, "What's in my cart?", [], "en", headers=h)
    assert INR(LIST[store][slug]) in j["reply"] and "checkout" in j["reply"] and not USD_RE.search(j["reply"])
    j = chat(ic, store, "How much is shipping?", [], "en")
    assert INR(SHIPPING[store]["standard_cents"]) in j["reply"] and "emonstration" in j["reply"] and not USD_RE.search(j["reply"])
    j = chat(ic, store, "How do I check out?", [], "en")
    assert "Indian delivery address" in j["reply"] and "US" not in j["reply"]
