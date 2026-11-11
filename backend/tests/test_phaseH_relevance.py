"""Phase H: recommendation relevance (rule-based path, deterministic) — needs map to the right products, party size
matches the product name, occasion words don't block a budget search, and nothing is claimed as a match that isn't."""

from __future__ import annotations

import pytest


def ask(client, store, message, lang="en"):
    r = client.post(f"/api/stores/{store}/chat", json={"message": message, "history": [], "channel": "web_chat", "conversation_language": lang})
    assert r.status_code == 200, r.text
    return r.json()


def test_warmth_finds_sleeping_gear_not_headlamps(client):
    r = ask(client, "store-a", "something to keep me warm at night camping")
    names = [p["name"] for p in r["products"]]
    assert names[0] == "Alpine 20°F Sleeping Bag"
    assert "Lumen 300 Headlamp" not in names and "Basecamp 4-Person Tent" not in names


def test_party_size_ranks_the_right_tent_first_and_stays_honest_about_stock(client):
    r = ask(client, "store-a", "I need a tent for 4 people")
    assert [p["name"] for p in r["products"]][:2] == ["Basecamp 4-Person Tent", "Ridgeline 2-Person Tent"]
    assert r["products"][0]["in_stock"] is False
    assert "currently out of stock" in r["reply"]
    r2 = ask(client, "store-a", "a tent for 2 people")
    assert r2["products"][0]["name"] == "Ridgeline 2-Person Tent"


def test_gift_with_budget_offers_in_stock_items_within_it(client):
    r = ask(client, "store-a", "gift for a hiker under $50")       # who it's for, not what it is
    assert r["products"] and all(p["in_stock"] and float(p["price"].strip("$")) <= 50 for p in r["products"])
    assert r["reply"].startswith("Here's what I found within $50.00")


def test_unmatched_words_with_budget_say_so_before_offering_items(client):
    r = ask(client, "store-a", "a present for a gardener under $50")
    assert r["products"] and all(float(p["price"].strip("$")) <= 50 for p in r["products"])
    assert r["reply"].startswith("I couldn't find a matching product at Summit Trail Co. Here's what I found within $50.00")


def test_existing_product_above_budget_is_not_replaced_by_other_items(client):
    r = ask(client, "store-b", "Do you have a grinder under $100?")
    assert r["products"] == [] and "within $100.00" in r["reply"]


def test_unknown_product_without_budget_is_still_not_found(client):
    r = ask(client, "store-a", "do you sell kayaks?")
    assert r["products"] == [] and "couldn't find a matching product" in r["reply"]


@pytest.mark.parametrize("lang, message, marker", [
    ("ta", "$20-க்குள் ஏதாவது பரிந்துரை செய்யுங்கள்", "$20.00-க்குள் இவை கிடைக்கின்றன"),
    ("hi", "$20 के अंदर कुछ सुझाइए", "$20.00 के अंदर ये मिले"),
])
def test_budget_recommendations_in_tamil_and_hindi(client, lang, message, marker):
    r = ask(client, "store-b", message, lang=lang)
    assert r["products"] and all(float(p["price"].strip("$")) <= 20 for p in r["products"])
    assert marker in r["reply"], r["reply"]
