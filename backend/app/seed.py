"""Seed each store database with SYNTHETIC demonstration data.

Usage: python -m app.seed [--reset]
All people, emails (example.com/.org reserved domains), addresses and orders are fictional.
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta

import psycopg

from .config import load_settings
from .policy_translations import POLICY_TRANSLATIONS
from .security import hash_password
from .stores import StoreId

DEMO_PASSWORDS = {StoreId.STORE_A: "TrailDemo!2026", StoreId.STORE_B: "BrewDemo!2026"}
AGENT_PASSWORD = "AgentDemo!2026"

SEED: dict[StoreId, dict] = {
    StoreId.STORE_A: {
        "profile": ("Summit Trail Co.", "help@summittrail.example.com", "Mon–Fri 8am–6pm MT", "USD"),
        # (standard, free-shipping minimum, expedited) in cents — must match the shipping policy text below.
        "shipping": (695, 7500, 1495),
        "policies": [
            ("shipping", "Free standard shipping over $75; standard delivery takes 3–5 business days.",
             "Standard shipping is $6.95 under $75 and free over $75. Expedited 2-day shipping is $14.95. Orders placed before 1pm MT ship the same business day. We ship to the contiguous US only."),
            ("returns", "Unused gear can be returned within 60 days for a full refund.",
             "Return unused items in original packaging within 60 days of delivery for a full refund to the original payment method. Used gear with a manufacturing defect is covered by warranty instead. Return shipping is free with the prepaid label from your account."),
            ("warranty", "Summit-brand gear has a 2-year defect warranty.",
             "Summit-brand items are covered for manufacturing defects for 2 years. Contact support with your order number and photos of the defect."),
            ("payment", "We accept major cards, PayPal and gift cards.",
             "Visa, Mastercard, American Express, Discover, PayPal and Summit gift cards are accepted."),
        ],
        "products": [
            ("ST-TENT-2P", "ridgeline-2p-tent", "Ridgeline 2-Person Tent", "Tents", "Freestanding 3-season backpacking tent, 1.9 kg, two doors and two vestibules.", 32900, 14, "⛺"),
            ("ST-TENT-4P", "basecamp-4p-tent", "Basecamp 4-Person Tent", "Tents", "Roomy family camping tent with full rainfly and gear loft.", 44900, 0, "🏕️"),
            ("ST-BAG-20", "alpine-20f-sleeping-bag", "Alpine 20°F Sleeping Bag", "Sleeping", "Synthetic-fill mummy bag rated to 20°F, packs to 8 L.", 15900, 22, "🛌"),
            ("ST-PAD-UL", "featherlite-sleeping-pad", "Featherlite Sleeping Pad", "Sleeping", "Ultralight inflatable pad, R-value 4.2, 410 g.", 12900, 31, "🟦"),
            ("ST-PACK-55", "trailhead-55l-backpack", "Trailhead 55L Backpack", "Packs", "Adjustable-torso backpacking pack with rain cover.", 21900, 9, "🎒"),
            ("ST-PACK-22", "daytrip-22l-daypack", "Daytrip 22L Daypack", "Packs", "Lightweight daypack with hydration sleeve and hip belt.", 7900, 48, "🎒"),
            ("ST-BOOT-M", "granite-hiking-boots", "Granite Waterproof Hiking Boots", "Footwear", "Waterproof leather mid boots with Vibram outsole.", 18900, 17, "🥾"),
            ("ST-JKT-RN", "stormshell-rain-jacket", "Stormshell Rain Jacket", "Apparel", "3-layer waterproof breathable shell with pit zips.", 16900, 3, "🧥"),
            ("ST-STOVE", "pocketflame-stove", "PocketFlame Canister Stove", "Cooking", "Compact canister stove, boils 1 L in 3.5 minutes.", 4900, 60, "🔥"),
            ("ST-LAMP", "lumen-300-headlamp", "Lumen 300 Headlamp", "Lighting", "Rechargeable 300-lumen headlamp with red night mode.", 3900, 75, "🔦"),
        ],
        "customers": [
            ("alex.rivera@example.com", "Alex Rivera", "customer"),
            ("jordan.lee@example.com", "Jordan Lee", "customer"),
            ("sam.patel@example.org", "Sam Patel", "customer"),
            ("agent@summittrail.example.com", "Summit Support Agent", "agent"),
        ],
        # (order_number, customer_email, status, postal, carrier, tracking, eta_offset_days, placed_offset_days, [(sku, qty)])
        "orders": [
            ("SA-10001", "alex.rivera@example.com", "shipped", "80302", "UPS", "1ZDEMO0000000001", 2, -3, [("ST-TENT-2P", 1), ("ST-LAMP", 2)]),
            ("SA-10002", "alex.rivera@example.com", "delivered", "80302", "USPS", "9400DEMO000000002", -10, -16, [("ST-BOOT-M", 1)]),
            ("SA-10003", "jordan.lee@example.com", "processing", "97205", None, None, 6, 0, [("ST-PACK-55", 1), ("ST-PAD-UL", 1)]),
            ("SA-10004", "sam.patel@example.org", "out_for_delivery", "02139", "FedEx", "7700DEMO00000004", 0, -4, [("ST-JKT-RN", 1)]),
            ("SA-10005", "jordan.lee@example.com", "cancelled", "97205", None, None, None, -20, [("ST-STOVE", 1)]),
        ],
    },
    StoreId.STORE_B: {
        "profile": ("Bloom & Brew", "care@bloomandbrew.example.com", "Every day 9am–8pm ET", "USD"),
        "shipping": (499, 5000, None),
        "policies": [
            ("shipping", "Flat $4.99 shipping, free over $50; delivery in 2–4 business days.",
             "We charge a flat $4.99 for shipping, free on orders over $50. Most orders arrive in 2–4 business days. Fresh-roasted coffee ships within 48 hours of roasting."),
            ("returns", "Returns accepted within 30 days; opened food items are final sale.",
             "Unused kitchenware can be returned within 30 days for a refund or store credit. Opened coffee, tea and other food items are final sale unless they arrived damaged. Damaged items are replaced free of charge."),
            ("warranty", "Electric appliances carry a 1-year warranty.",
             "Grinders, kettles and other electric items are covered for 1 year against defects. Keep your order number for warranty claims."),
            ("payment", "We accept major cards, Apple Pay and gift cards.",
             "Visa, Mastercard, American Express, Apple Pay, Google Pay and Bloom & Brew gift cards are accepted."),
        ],
        "products": [
            ("BB-COF-ETH", "ethiopia-yirgacheffe-beans", "Ethiopia Yirgacheffe Whole Beans", "Coffee", "Light roast, notes of jasmine and lemon. 340 g bag.", 1900, 40, "☕"),
            ("BB-COF-HSE", "house-blend-beans", "House Blend Whole Beans", "Coffee", "Medium-dark roast with chocolate and caramel notes. 340 g bag.", 1600, 0, "☕"),
            ("BB-TEA-SEN", "sencha-green-tea", "Sencha Green Tea", "Tea", "Loose-leaf Japanese green tea, 100 g tin.", 1400, 55, "🍵"),
            ("BB-TEA-CHA", "spiced-chai-blend", "Spiced Chai Blend", "Tea", "Black tea with cardamom, cinnamon and ginger, 120 g.", 1200, 33, "🫖"),
            ("BB-GRN-BUR", "precision-burr-grinder", "Precision Burr Grinder", "Equipment", "Electric conical burr grinder with 40 grind settings.", 14900, 8, "⚙️"),
            ("BB-KET-GOO", "gooseneck-kettle", "Gooseneck Pour-Over Kettle", "Equipment", "Electric 0.9 L gooseneck kettle with temperature hold.", 8900, 12, "🫖"),
            ("BB-PRS-FRN", "classic-french-press", "Classic French Press", "Brewers", "1 L borosilicate glass French press with steel frame.", 3400, 26, "🫙"),
            ("BB-DRP-V60", "ceramic-pour-over-dripper", "Ceramic Pour-Over Dripper", "Brewers", "Cone dripper in matte glaze, fits size 02 filters.", 2600, 2, "🔻"),
            ("BB-MUG-STN", "stoneware-mug-set", "Stoneware Mug Set (4)", "Kitchen", "Four hand-glazed 350 ml stoneware mugs.", 4800, 19, "🍶"),
            ("BB-HNY-WLD", "wildflower-honey", "Wildflower Honey", "Pantry", "Raw wildflower honey, 450 g jar.", 1100, 64, "🍯"),
        ],
        "customers": [
            # Same email as a Store A customer on purpose: a separate account in a separate database.
            ("alex.rivera@example.com", "Alex Rivera", "customer"),
            ("maria.gomez@example.com", "Maria Gomez", "customer"),
            ("chris.wong@example.org", "Chris Wong", "customer"),
            ("agent@bloomandbrew.example.com", "Bloom Care Agent", "agent"),
        ],
        "orders": [
            ("BB-20001", "maria.gomez@example.com", "shipped", "60614", "USPS", "9400DEMO000020001", 1, -2, [("BB-GRN-BUR", 1), ("BB-COF-ETH", 2)]),
            ("BB-20002", "alex.rivera@example.com", "processing", "80302", None, None, 4, 0, [("BB-TEA-SEN", 1), ("BB-HNY-WLD", 1)]),
            ("BB-20003", "chris.wong@example.org", "delivered", "94110", "UPS", "1ZDEMO0000020003", -5, -9, [("BB-KET-GOO", 1)]),
            ("BB-20004", "maria.gomez@example.com", "returned", "60614", "USPS", "9400DEMO000020004", -20, -30, [("BB-MUG-STN", 1)]),
        ],
    },
}


def seed_store(store: StoreId, url: str, reset: bool) -> None:
    data = SEED[store]
    with psycopg.connect(url) as conn, conn.transaction():
        if reset:
            conn.execute("TRUNCATE sandbox_payment_intents, payments, cart_items, carts, password_reset_tokens, sessions, "
                         "order_items, orders, customers, products, policies, store_profile RESTART IDENTITY CASCADE")
            conn.execute("ALTER SEQUENCE order_number_seq RESTART")
        elif conn.execute("SELECT count(*) FROM products").fetchone()[0] > 0:
            # Non-destructive backfill for databases seeded before shipping prices existed (migration 0002).
            filled = conn.execute(
                "UPDATE store_profile SET standard_shipping_cents = %s, free_shipping_min_cents = %s, expedited_shipping_cents = %s "
                "WHERE id = 1 AND standard_shipping_cents = 0",
                list(data["shipping"]),
            ).rowcount
            translated = _fill_policy_translations(conn, store)
            print(f"{store.value}: already seeded (use --reset to reseed){'; shipping prices backfilled' if filled else ''}"
                  f"{f'; {translated} policy translations backfilled' if translated else ''}")
            return

        conn.execute(
            "INSERT INTO store_profile (id, name, support_email, support_hours, currency, standard_shipping_cents, free_shipping_min_cents, expedited_shipping_cents) "
            "VALUES (1, %s, %s, %s, %s, %s, %s, %s)",
            [*data["profile"], *data["shipping"]],
        )
        for topic, summary, details in data["policies"]:
            conn.execute("INSERT INTO policies (topic, summary, details) VALUES (%s, %s, %s)", [topic, summary, details])
        _fill_policy_translations(conn, store)

        product_ids, prices = {}, {}
        for sku, slug, name, cat, desc, price, stock, emoji in data["products"]:
            pid = conn.execute(
                "INSERT INTO products (sku, slug, name, category, description, price_cents, stock_qty, emoji) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                [sku, slug, name, cat, desc, price, stock, emoji],
            ).fetchone()[0]
            product_ids[sku], prices[sku] = pid, price

        customer_ids = {}
        for email, name, role in data["customers"]:
            pw = AGENT_PASSWORD if role == "agent" else DEMO_PASSWORDS[store]
            customer_ids[email] = conn.execute(
                "INSERT INTO customers (email, full_name, password_hash, role) VALUES (%s,%s,%s,%s) RETURNING id",
                [email, name, hash_password(pw), role],
            ).fetchone()[0]

        today = date.today()
        for number, email, status, postal, carrier, tracking, eta, placed, items in data["orders"]:
            total = sum(prices[sku] * qty for sku, qty in items)
            oid = conn.execute(
                "INSERT INTO orders (order_number, customer_id, status, shipping_postal_code, carrier, tracking_number, estimated_delivery, total_cents, placed_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s, now() + make_interval(days => %s)) RETURNING id",
                [number, customer_ids[email], status, postal, carrier, tracking, today + timedelta(days=eta) if eta is not None else None, total, placed],
            ).fetchone()[0]
            for sku, qty in items:
                conn.execute(
                    "INSERT INTO order_items (order_id, product_id, quantity, unit_price_cents) VALUES (%s,%s,%s,%s)",
                    [oid, product_ids[sku], qty, prices[sku]],
                )
    print(f"{store.value}: seeded {len(data['products'])} products, {len(data['customers'])} accounts, {len(data['orders'])} orders")


def _fill_policy_translations(conn, store: StoreId) -> int:
    """Non-destructive: only fills translations that are still empty."""
    n = 0
    for topic, langs in POLICY_TRANSLATIONS[store].items():
        (sta, dta), (shi, dhi) = langs["ta"], langs["hi"]
        n += conn.execute(
            "UPDATE policies SET summary_ta = %s, details_ta = %s, summary_hi = %s, details_hi = %s WHERE topic = %s AND details_ta IS NULL",
            [sta, dta, shi, dhi, topic],
        ).rowcount
    return n


def seed_all(database_urls: dict[str, str], reset: bool = False) -> None:
    for store in StoreId:
        seed_store(store, database_urls[store.value], reset)


def demo_seeding_refusal(app_env: str, reset: bool, allow_non_development: bool) -> str | None:
    """Why seeding must not run here, or None. The seed creates accounts with PUBLISHED demo passwords
    (DEMO_PASSWORDS, AGENT_PASSWORD) and --reset deletes every customer, order and payment, so outside development
    it is refused unless explicitly allowed — and --reset is never allowed outside development."""
    if app_env == "development":
        return None
    if reset:
        return f"--reset is refused when APP_ENV={app_env}: it deletes all customers, orders and payments."
    if not allow_non_development:
        return (f"Refusing to seed demo data when APP_ENV={app_env}: it creates accounts with published passwords. "
                "Pass --allow-demo-data only for a disposable demo environment.")
    return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="truncate and reseed demo data (development only)")
    parser.add_argument("--allow-demo-data", action="store_true", help="allow demo accounts outside development (disposable demos only)")
    args = parser.parse_args()
    settings = load_settings()
    refusal = demo_seeding_refusal(settings.app_env, args.reset, args.allow_demo_data)
    if refusal:
        raise SystemExit(refusal)
    seed_all(settings.store_database_urls, reset=args.reset)
