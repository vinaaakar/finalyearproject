"""Phase 1.1 — catalogue verification works for any catalogue size.

A module fixture adds 250 synthetic products to the Store A *test* database whose names sort before every real
product (so a "first 200 products" lookup would miss the real ones) and removes them afterwards.
"""

from __future__ import annotations

import pytest

from app import repositories as repo
from app.assistant.service import ChatResult
from app.stores import StoreId
from tests.conftest import db_exec, make_client
from tests.test_assistant_security import ScriptedLLM
from tests.test_customer_care import ask, turns

BULK = 250


@pytest.fixture(scope="module", autouse=True)
def big_catalogue(settings):
    db_exec(settings, "store-a", "DELETE FROM products WHERE sku LIKE 'ZZ-BULK-%%'")
    db_exec(settings, "store-a",
            "INSERT INTO products (sku, slug, name, category, description, price_cents, stock_qty) "
            "SELECT 'ZZ-BULK-' || n, 'aaa-bulk-item-' || lpad(n::text, 3, '0'), 'AAA Bulk Item ' || lpad(n::text, 3, '0'), "
            "'Bulk', 'Synthetic filler product for catalogue-size tests.', 1000 + n, 5 FROM generate_series(1, %s) n", [BULK])
    yield
    db_exec(settings, "store-a", "DELETE FROM products WHERE sku LIKE 'ZZ-BULK-%%'")


def test_catalogue_really_exceeds_200_and_real_products_sort_last(client):
    first_200 = {p["slug"] for p in repo.list_products(StoreId.STORE_A, limit=200)}
    assert len(repo.list_products(StoreId.STORE_A, limit=1000)) > 200 + 10
    assert "trailhead-55l-backpack" not in first_200   # the old lookup would have missed it


def test_final_check_verifies_products_beyond_the_first_200(client):
    result = ChatResult(reply="ok", intents=["product"], source="rules",
                        products=[{"slug": "trailhead-55l-backpack", "price": "$1.00"}, {"slug": "aaa-bulk-item-249"},
                                  {"slug": "no-such-product"}, {"slug": "gooseneck-kettle"}],
                        actions=[{"type": "add_to_cart", "slug": "trailhead-55l-backpack", "quantity": 1, "label": "Add"},
                                 {"type": "add_to_cart", "slug": "gooseneck-kettle", "quantity": 1, "label": "Add"}])
    out = client.app.state.assistant._finalise(StoreId.STORE_A, result, "en", "Summit Trail Co.")
    assert [p["slug"] for p in out.products] == ["trailhead-55l-backpack", "aaa-bulk-item-249"]
    assert out.products[0]["price"] == "$219.00"                      # server price, not the claimed $1.00
    assert out.products[1]["price"] == "$12.49"
    assert [a["slug"] for a in out.actions] == ["trailhead-55l-backpack"]  # other store's product rejected


def test_lookup_by_slugs_is_store_scoped_and_bounded(client):
    found = repo.get_products_by_slugs(StoreId.STORE_A, ["trailhead-55l-backpack", "gooseneck-kettle", "", None, "x"])
    assert set(found) == {"trailhead-55l-backpack"}
    assert repo.get_products_by_slugs(StoreId.STORE_A, []) == {}


def test_conversation_references_work_beyond_the_first_200(client):
    history = turns(("user", "Tell me about the Trailhead 55L Backpack"),
                    ("assistant", "The Trailhead 55L Backpack is $219.00, in stock."))
    body = ask(client, "store-a", "Do you have anything cheaper?", history=history)
    assert [p["slug"] for p in body["products"]] == ["daytrip-22l-daypack"]   # same category, cheaper, real


def test_model_naming_an_unlisted_real_product_is_still_rejected(settings):
    reply = "Standard delivery takes 3–5 business days. The Trailhead 55L Backpack is great for that."
    with make_client(settings, llm=ScriptedLLM(reply)) as c:
        body = ask(c, "store-a", "How long does shipping take?")
    assert body["source"] == "rules" and "Trailhead" not in body["reply"]


def test_products_mentioned_in_text_uses_the_database(client):
    names = [p["name"] for p in repo.products_mentioned_in(StoreId.STORE_A, "compare AAA Bulk Item 240 and the Lumen 300 Headlamp")]
    assert names == ["AAA Bulk Item 240", "Lumen 300 Headlamp"]
    assert repo.products_mentioned_in(StoreId.STORE_A, "Gooseneck Pour-Over Kettle") == []   # Store B product
