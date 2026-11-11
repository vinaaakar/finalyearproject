"""Markets: country-specific address rules, currency formatting and shipping configuration (Phase I).

A store's market is configuration (`STORE_A_MARKET`, `STORE_B_MARKET`: `US` | `IN`, default `US`), not code. Both
stores run the `US` market today: their catalogues are priced in USD. Switching a store to `IN` needs owner decisions
that are deliberately NOT made here (docs/business-information.md, docs/india-readiness.md):
- INR prices for every product (no exchange-rate conversion is ever applied) — the API refuses to start a store in the
  `IN` market while its catalogue currency is not INR;
- shipping zones, fees, free-shipping thresholds and delivery times — until configured, an `IN` store reports
  "delivery charges haven't been set" and refuses checkout instead of inventing a fee.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# ISO 3166-2:IN subdivision codes (28 states + 8 union territories) after the 2023 ISO update (CG, OD, TG, UT).
# Codes are internal identifiers; customers see the names. Verify against the current ISO list before launch.
IN_REGIONS: tuple[tuple[str, str, str], ...] = (
    ("AP", "Andhra Pradesh", "state"), ("AR", "Arunachal Pradesh", "state"), ("AS", "Assam", "state"), ("BR", "Bihar", "state"),
    ("CG", "Chhattisgarh", "state"), ("GA", "Goa", "state"), ("GJ", "Gujarat", "state"), ("HR", "Haryana", "state"),
    ("HP", "Himachal Pradesh", "state"), ("JH", "Jharkhand", "state"), ("KA", "Karnataka", "state"), ("KL", "Kerala", "state"),
    ("MP", "Madhya Pradesh", "state"), ("MH", "Maharashtra", "state"), ("MN", "Manipur", "state"), ("ML", "Meghalaya", "state"),
    ("MZ", "Mizoram", "state"), ("NL", "Nagaland", "state"), ("OD", "Odisha", "state"), ("PB", "Punjab", "state"),
    ("RJ", "Rajasthan", "state"), ("SK", "Sikkim", "state"), ("TN", "Tamil Nadu", "state"), ("TG", "Telangana", "state"),
    ("TR", "Tripura", "state"), ("UP", "Uttar Pradesh", "state"), ("UT", "Uttarakhand", "state"), ("WB", "West Bengal", "state"),
    ("AN", "Andaman and Nicobar Islands", "union_territory"), ("CH", "Chandigarh", "union_territory"),
    ("DH", "Dadra and Nagar Haveli and Daman and Diu", "union_territory"), ("DL", "Delhi", "union_territory"),
    ("JK", "Jammu and Kashmir", "union_territory"), ("LA", "Ladakh", "union_territory"), ("LD", "Lakshadweep", "union_territory"),
    ("PY", "Puducherry", "union_territory"),
)

US_REGIONS: tuple[tuple[str, str, str], ...] = tuple((c, n, "state") for c, n in (
    ("AL", "Alabama"), ("AK", "Alaska"), ("AZ", "Arizona"), ("AR", "Arkansas"), ("CA", "California"), ("CO", "Colorado"),
    ("CT", "Connecticut"), ("DE", "Delaware"), ("DC", "District of Columbia"), ("FL", "Florida"), ("GA", "Georgia"),
    ("HI", "Hawaii"), ("ID", "Idaho"), ("IL", "Illinois"), ("IN", "Indiana"), ("IA", "Iowa"), ("KS", "Kansas"),
    ("KY", "Kentucky"), ("LA", "Louisiana"), ("ME", "Maine"), ("MD", "Maryland"), ("MA", "Massachusetts"), ("MI", "Michigan"),
    ("MN", "Minnesota"), ("MS", "Mississippi"), ("MO", "Missouri"), ("MT", "Montana"), ("NE", "Nebraska"), ("NV", "Nevada"),
    ("NH", "New Hampshire"), ("NJ", "New Jersey"), ("NM", "New Mexico"), ("NY", "New York"), ("NC", "North Carolina"),
    ("ND", "North Dakota"), ("OH", "Ohio"), ("OK", "Oklahoma"), ("OR", "Oregon"), ("PA", "Pennsylvania"), ("RI", "Rhode Island"),
    ("SC", "South Carolina"), ("SD", "South Dakota"), ("TN", "Tennessee"), ("TX", "Texas"), ("UT", "Utah"), ("VT", "Vermont"),
    ("VA", "Virginia"), ("WA", "Washington"), ("WV", "West Virginia"), ("WI", "Wisconsin"), ("WY", "Wyoming")))


@dataclass(frozen=True)
class Market:
    code: str
    country: str
    currency: str
    locale: str
    region_label: str
    regions: tuple[tuple[str, str, str], ...]
    postal_label: str
    postal_pattern: str
    postal_example: str
    phone_pattern: str | None = None          # None: no phone field
    phone_example: str | None = None
    landmark: bool = False
    name: str = ""
    dial_code: str = ""
    phone_required: bool = False
    line1_label: str = "Address"
    line2_label: str = "Apartment, suite, etc. (optional)"
    city_label: str = "City"
    # Zones the OWNER configures: [{"name", "regions": [codes] | "pin_prefixes": [..], "standard_minor", "free_over_minor",
    # "eta_min_days", "eta_max_days"}]. Empty = delivery not configured → checkout refused (never an invented fee).
    shipping_zones: tuple[dict[str, Any], ...] = field(default=())

    def public(self) -> dict[str, Any]:
        return {"code": self.code, "country": self.country, "name": self.name, "currency": self.currency, "locale": self.locale,
                "line1_label": self.line1_label, "line2_label": self.line2_label, "city_label": self.city_label,
                "region_label": self.region_label, "regions": [{"code": c, "name": n, "kind": k} for c, n, k in self.regions],
                "postal_label": self.postal_label, "postal_pattern": self.postal_pattern, "postal_example": self.postal_example,
                "phone": {"required": self.phone_required, "pattern": self.phone_pattern, "example": self.phone_example,
                          "dial_code": self.dial_code} if self.phone_pattern else None,
                "landmark": self.landmark,
                "shipping_configured": self.code == "US" or bool(self.shipping_zones)}


MARKETS: dict[str, Market] = {
    # US: today's fields and rules; a phone number is optional (+1), as before it wasn't collected at all.
    "US": Market("US", "US", "USD", "en-US", "State", US_REGIONS, "ZIP code", r"^\d{5}(-\d{4})?$", "80302",
                 phone_pattern=r"^(\+?1)?[2-9]\d{9}$", phone_example="303 555 0100", name="United States", dial_code="+1"),
    # India: couriers need the recipient's mobile number (+91); line 2 doubles as the landmark.
    "IN": Market("IN", "IN", "INR", "en-IN", "State / union territory", IN_REGIONS, "PIN code", r"^[1-9][0-9]{5}$", "625521",
                 phone_pattern=r"^(\+?91)?[6-9]\d{9}$", phone_example="98765 43210", name="India", dial_code="+91",
                 phone_required=True, line1_label="Address line 1", line2_label="Address line 2 / Landmark (optional)",
                 city_label="City / Town"),
}


def get_market(code: str) -> Market:
    if code not in MARKETS:
        raise ValueError(f"unknown market {code!r} (known: {sorted(MARKETS)})")
    return MARKETS[code]


class AddressError(ValueError):
    def __init__(self, problems: list[dict[str, str]]):
        super().__init__("; ".join(f"{p['field']}: {p['issue']}" for p in problems))
        self.problems = problems


def normalise_phone_in(raw: str) -> str:
    """'+91 98765 43210' / '9876543210' → '+919876543210' (E.164)."""
    digits = re.sub(r"\D", "", raw)
    return "+91" + digits[-10:]


def normalise_phone(market: "Market", raw: str) -> str:
    """E.164 for the market's dial code: India '+919876543210', US '+13035550100'."""
    digits = re.sub(r"\D", "", raw)
    return market.dial_code + digits[-10:]


def validate_address(market: Market, a: dict[str, Any]) -> dict[str, Any]:
    """Market rules on top of the schema's generic checks. Returns the normalised address; raises AddressError."""
    problems = []
    if a.get("country", market.country) != market.country:
        problems.append({"field": "shipping.country", "issue": f"this store delivers to {market.country} only"})
    region = (a.get("region") or "").upper()
    if region not in {c for c, _, _ in market.regions}:
        problems.append({"field": "shipping.region", "issue": f"choose a {market.region_label.lower()} from the list"})
    postal = (a.get("postal_code") or "").strip()
    if not re.fullmatch(market.postal_pattern, postal):
        problems.append({"field": "shipping.postal_code", "issue": f"enter a valid {market.postal_label} (e.g. {market.postal_example})"})
    out = {**a, "region": region, "postal_code": postal, "country": market.country}
    phone = re.sub(r"[\s\-().]", "", a.get("phone") or "")         # people type "+91 98765-43210"
    if market.phone_pattern and (phone or market.phone_required):
        if not re.fullmatch(market.phone_pattern, phone):
            problems.append({"field": "shipping.phone", "issue": f"enter a 10-digit {'mobile' if market.phone_required else 'phone'} "
                                                                  f"number (e.g. {market.dial_code} {market.phone_example})"})
        else:
            out["phone"] = normalise_phone(market, phone)
    else:
        out["phone"] = None
    if problems:
        raise AddressError(problems)
    return out


def shipping_zone(market: Market, region: str, postal_code: str) -> dict[str, Any] | None:
    """Longest matching PIN prefix wins, then the state/UT; None = not deliverable (or not configured)."""
    best = None
    for z in market.shipping_zones:
        for prefix in z.get("pin_prefixes", ()):
            if postal_code.startswith(prefix) and (best is None or len(prefix) > best[0]):
                best = (len(prefix), z)
    if best:
        return best[1]
    return next((z for z in market.shipping_zones if region in z.get("regions", ())), None)


# ---- money ------------------------------------------------------------------------------------------------------------
_SYMBOLS = {"USD": "$", "INR": "₹"}


def _group_indian(n: int) -> str:
    s = str(n)
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return ",".join(groups) + "," + tail


def format_money(minor: int, currency: str) -> str:
    """Integer minor units → display string. USD '$1,249.99' (unchanged from before); INR '₹1,24,999.00' (Indian grouping)."""
    sign = "-" if minor < 0 else ""
    whole, frac = divmod(abs(int(minor)), 100)
    if currency == "INR":
        return f"{sign}₹{_group_indian(whole)}.{frac:02d}"
    symbol = _SYMBOLS.get(currency)
    body = f"{whole:,}.{frac:02d}"
    return f"{sign}{symbol}{body}" if symbol else f"{sign}{body} {currency}"
