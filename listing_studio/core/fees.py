"""Per-platform fee calculations.

Used by the UI to show "fee ~$4.70 · net $89.30" next to each platform on
the listing form. Fees are estimates - the actual fee depends on category,
seller account level, and payment processing, none of which we model
exactly. The numbers are accurate enough to be useful for decision-making.

Fee structures (as of conversation date):
  - Reverb:        5% + $0.25 payment processing
  - eBay:          ~13% total (final value + insertion fees vary by category)
  - Etsy:          6.5% transaction + $0.20 listing + 3% payment processing
  - Squarespace:   2.9% + $0.30 (Stripe payment processing only)
  - Facebook:      0% (local pickup) or 5% for shipping orders

These rates change occasionally; if Dad notices the math is off, the
constants are all here in one place.
"""

from __future__ import annotations

from dataclasses import dataclass

from listing_studio.core.models import Platform


@dataclass(frozen=True)
class FeeStructure:
    """How a platform charges for a sale.

    All numbers are in basis points (1 bp = 0.01%) or cents to avoid floats.
    """

    percentage_bps: int      # e.g. 500 = 5.00%
    flat_cents: int          # e.g. 25 = $0.25
    listing_cents: int = 0   # Per-listing fee (Etsy charges $0.20 to list)
    description: str = ""


_FEES: dict[Platform, FeeStructure] = {
    Platform.REVERB: FeeStructure(
        percentage_bps=500,    # 5% selling fee
        flat_cents=25,         # $0.25 payment processing
        description="5% + $0.25",
    ),
    Platform.EBAY: FeeStructure(
        percentage_bps=1300,   # ~13% all-in for musical instruments category
        flat_cents=30,
        description="~13% + $0.30",
    ),
    Platform.ETSY: FeeStructure(
        percentage_bps=950,    # 6.5% transaction + 3% payment
        flat_cents=25,
        listing_cents=20,
        description="6.5% + 3% + $0.20 listing",
    ),
    Platform.SQUARESPACE: FeeStructure(
        # Squarespace itself takes 0% on Commerce Advanced. Payment processing
        # via Stripe is the only fee.
        percentage_bps=290,    # 2.9%
        flat_cents=30,
        description="2.9% + $0.30 (Stripe)",
    ),
    Platform.FACEBOOK: FeeStructure(
        percentage_bps=0,      # Local pickup, no fee
        flat_cents=0,
        description="No fee (local pickup)",
    ),
}


def get_fee_structure(platform: Platform) -> FeeStructure:
    """Return the fee structure for a platform."""
    return _FEES[platform]


def estimate_fee_cents(platform: Platform, sale_price_cents: int) -> int:
    """Estimate the platform's cut on a sale at the given price (cents).

    Includes the percentage cut, the flat per-transaction fee, and any
    per-listing fee amortized over a single sale. Doesn't include shipping
    fees, sales tax, or anything else the buyer pays separately.
    """
    fee = _FEES[platform]
    percentage_cut = sale_price_cents * fee.percentage_bps // 10_000
    return percentage_cut + fee.flat_cents + fee.listing_cents


def estimate_net_cents(platform: Platform, sale_price_cents: int) -> int:
    """Estimate what Dad actually receives after fees."""
    return sale_price_cents - estimate_fee_cents(platform, sale_price_cents)
