---
name: ad-account-morning-check
description: This skill should be used when the user asks to "morning check", "check ads", "how are my ads doing", "yesterday's performance", "ad account check", "morning ad report", "any ads paused", or wants a single-command daily status check on their Meta ad account combining (1) yesterday's contribution margin from real Shopify data and Meta ad spend, (2) day-over-day comparison, (3) audit of any ads that spent >$50 in the last 7 days but are currently paused (the "good ads stranded" recovery list). Replaces 10-15 minutes of manual Meta Ads Manager + Shopify Admin clicking each morning.
---

# Ad Account Morning Check

A single command for media buyers running ~$500-$3K/day on Meta to get the only three things they need to start the day:

1. **Yesterday's real contribution margin** — Shopify revenue minus COGS/shipping/processing/returns minus ad spend, not Meta's reported revenue.
2. **Day-over-day trend** — 5-day side-by-side so today's number has context.
3. **Paused-with-spend audit** — every ad that spent >$50 in the last 7 days that's currently paused. These are the recovery candidates Meta or rules may have auto-killed.

## Why this exists

Most media buyers waste 10-15 minutes every morning bouncing between Meta Ads Manager and Shopify Admin to assemble the same three answers. This skill compresses that into ~30 seconds.

The contribution-margin calculation is the actual differentiator. Meta's reported ROAS is **not** contribution margin — it doesn't subtract COGS, shipping, processing fees, or returns. Operators who run on Meta ROAS alone over-spend on ads that look profitable but aren't.

## Setup (one-time)

### 1. Meta Marketing API token

Generate a **page access token** or a **System User token** (preferred — non-expiring). Save to `.env`:

```
META_PAGE_TOKEN=EAA...your-token...
META_AD_ACCOUNT_ID=act_1234567890123456
```

System User tokens via Meta Business Suite are non-expiring; user tokens expire every 60 days. Always prefer System User.

### 2. Shopify Admin API token

Custom app token from Shopify Admin → Apps → Develop apps → Create app → API credentials. Scopes needed: `read_orders`, `read_products`, `read_inventory`. Save to `.env`:

```
SHOPIFY_STORE=yourstore.myshopify.com
SHOPIFY_ACCESS_TOKEN=shpat_...
```

### 3. Unit economics file

Create `unit-economics.json` at your project root with the cost structure for YOUR products. See `unit-economics.template.json` in this repo for the schema. Example:

```json
{
  "default_cogs_pct_of_subtotal": 0.33,
  "shipping_cost_avg": 5.50,
  "processing_pct": 0.041,
  "returns_reserve_pct": 0.02,
  "usd_cad_rate": 0.73,
  "currency_spend": "CAD",
  "currency_revenue": "USD"
}
```

These percentages are the levers — get them right or the CM number will lie. Hit your accountant for actuals.

## How to use it

Once the env + unit-economics file are in place, invoke the skill:

```
morning check
```

Or any of these triggers:
- `"how are my ads doing"`
- `"yesterday's performance"`
- `"any ads paused"`
- `"ad account check"`

## Output shape

```
========================================
YESTERDAY (May 18, Mon)
========================================
  Revenue:           $1,338.36 USD
  Ad spend (CAD):    $667.11  (USD ~$486.99)
  Margin before ads: $705.41 (52.7%)
  CM:                $218.42 (16.3%)
  ROAS:              2.75x
  Orders:            27  AOV: $49.57
  Units:             44 (1.6/order)

========================================
LAST 5 DAYS
========================================
  Wed 5/13: rev=$1,122  spend=$421  CM=$300 (27%)  ROAS=3.65x  AOV=$51
  Fri 5/15: rev=$1,452  spend=$1,006 CM=$65 (5%)   ROAS=1.98x  AOV=$48
  Sat 5/16: rev=$1,751  spend=$1,145 CM=$127 (7%)  ROAS=2.09x  AOV=$53
  Sun 5/17: rev=$1,561  spend=$747   CM=$323 (21%) ROAS=2.86x  AOV=$56
  Mon 5/18: rev=$1,338  spend=$667   CM=$218 (16%) ROAS=2.75x  AOV=$50

========================================
PAUSED ADS WITH >$50 LAST 7D
========================================
  ⚠ 1 paused ad with significant spend:
  [PAUSED] $300.52 spent, 6 purch, ROAS 0.92x
    BB2 — I'm Retired V-neck Copy 2
    ad_id: 120215629113300199
```

## What the skill does under the hood

See `scripts/morning_check.py` for the full implementation. The core steps:

1. **Fetch yesterday's orders** from Shopify (`/admin/api/2024-01/orders.json` with `created_at_min` / `created_at_max`).
2. **For each order, compute real margin** using the unit-economics rates: `total_price - cogs - shipping - processing - returns_reserve`.
3. **Sum across orders** for the day-level pre-ad margin.
4. **Fetch Meta account-level spend** for the same day window.
5. **CM = pre-ad margin - ad spend** (currency-adjusted).
6. **Repeat for the prior 4 days** for the trend table.
7. **Fetch ad-level spend** for last 7 days, filter to spend > $50.
8. **For each, check current `effective_status`** — flag any that aren't `ACTIVE`.

## Customization

- **Spend threshold** — `$50` is sensible for accounts spending $500-$3K/day. Adjust in `morning_check.py` if your account is larger.
- **Lookback window** — `7 days` for paused-ad audit, `5 days` for trend table. Both configurable.
- **Currency** — defaults assume USD revenue / CAD spend (Shopify USD store + Meta CAD account). Adjust the `usd_cad_rate` and `currency_*` fields in `unit-economics.json` for your setup.

## Related skills in this family

- **`cost-cap-walkdown`** — methodology for adjusting cost caps $1 at a time in 2-day cycles (vs pausing). Pairs with this skill — morning check identifies candidates, walkdown adjusts them.
- **`attribution-adjusted-roas`** — calculate the Meta-reported ROAS goal you need to hit a target CM%, accounting for the gap between Meta-attributed and Shopify-actual revenue.

These are coming as separate skills in the same family.

## Files in this skill

- `scripts/morning_check.py` — the main script the skill executes
- `scripts/unit_economics.py` — per-order margin calculator
- `unit-economics.template.json` — schema for your cost structure
- `.env.template` — environment variables template
