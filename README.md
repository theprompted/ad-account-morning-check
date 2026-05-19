# Ad Account Morning Check

**For Prompted Accelerator members.** Access at [skool.com/the-prompted](https://www.skool.com/the-prompted).

A Claude Code skill for media buyers running ~$500-$3K/day on Meta. One command, three answers:

1. **Yesterday's real contribution margin** — Shopify revenue minus COGS, shipping, processing, returns, and ad spend. Not Meta's reported ROAS.
2. **Day-over-day trend** — last 5 days side-by-side so the number has context.
3. **Paused-ads-with-spend audit** — every ad that spent >$50 in the last 7 days and is currently paused. The "good ads stranded" recovery list.

Replaces 10-15 minutes of manual Meta Ads Manager + Shopify Admin clicking every morning.

## How to use it

Tell Claude Code:

> "Go read this repo and install all skills and dependencies: https://github.com/theprompted/ad-account-morning-check"

Claude Code handles the rest.

Then just say: **"morning check"** any morning.

## What you get

Output looks like this:

```
========================================
YESTERDAY (May 18, Mon)
========================================
  Revenue:           $1,338.36
  Ad spend (CAD):    $667.11  (USD ~$486.99)
  Margin before ads: $705.41 (52.7%)
  CM:                $218.42 (16.3%)
  ROAS:              2.75x
  Orders:            27  AOV: $49.57

========================================
LAST 5 DAYS
========================================
  Wed: rev=$1,122  spend=$421  CM=$300 (27%)  ROAS=3.65x
  Fri: rev=$1,452  spend=$1,006 CM=$65 (5%)   ROAS=1.98x
  ...

========================================
PAUSED ADS WITH >$50 LAST 7D
========================================
  ⚠ 1 paused ad with significant spend:
  [PAUSED] $300.52 spent, 6 purch, ROAS 0.92x
    BB2 — I'm Retired V-neck Copy 2
```

## Why contribution margin and not ROAS?

Meta reports ROAS as `purchase_value / spend`. That's the wrong number for deciding whether to scale.

A Meta-reported 2.0x ROAS sounds profitable. But after COGS (~33%), shipping (~9%), payment processing (~4%), returns reserve (~2%), and the spend already in the denominator, you might be at 5% contribution margin — barely above zero. Operators who scale on Meta ROAS alone over-spend on ads that look profitable but barely cover costs.

This skill does the real math: starts from Shopify (cash collected), subtracts your actual unit-economics costs, then subtracts ad spend. The number that comes out is **the money that hit the bank after paying everything ad-related**.

## What's in this repo

- `SKILL.md` — the skill file Claude Code installs
- `scripts/morning_check.py` — the main script that fetches data and prints the report
- `scripts/unit_economics.py` — per-order margin calculator
- `unit-economics.template.json` — cost-structure schema you fill in
- `.env.template` — environment variables template

## Requirements

- [Claude Code](https://claude.ai/code)
- Python 3.9+
- A Meta Marketing API access token (page or System User — System User preferred, non-expiring)
- A Shopify Admin API access token with `read_orders`, `read_products`, `read_inventory` scopes
- Your unit economics in a JSON file (template provided)

## Setup

### 1. Get the skill

```bash
# Option A: Tell Claude Code to install it
# (Just paste the URL above into Claude Code and it does the rest)

# Option B: Clone manually
git clone https://github.com/theprompted/ad-account-morning-check.git
cp -r ad-account-morning-check/.claude/skills/ad-account-morning-check ~/.claude/skills/
```

### 2. Set up tokens

Copy `.env.template` to `.env` at your project root and fill in:

```
META_PAGE_TOKEN=EAA...
META_AD_ACCOUNT_ID=act_1234567890123456
SHOPIFY_STORE=yourstore.myshopify.com
SHOPIFY_ACCESS_TOKEN=shpat_...
```

**Meta token:** Use a System User token from Meta Business Suite (non-expiring). User tokens expire every 60 days and will silently break this skill when they do.

**Shopify token:** Create a custom app in Shopify Admin → Apps → Develop apps. Scopes: `read_orders`, `read_products`, `read_inventory`.

### 3. Set up unit economics

Copy `unit-economics.template.json` to `unit-economics.json` and fill in YOUR cost structure:

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

These percentages are the most important inputs. Don't guess — pull them from your actuals. A 5-point COGS error throws the CM% off by a similar amount.

### 4. Run

```
morning check
```

That's it.

## How it works

1. **Pull yesterday's Shopify orders** via `/admin/api/2024-01/orders.json`.
2. **For each order, compute the real margin** using the unit-economics rates: `total_price - cogs - shipping - processing - returns_reserve`.
3. **Sum across orders** for day-level pre-ad margin.
4. **Pull Meta account-level spend** for the same day.
5. **Compute CM = pre-ad margin - ad spend** (currency-adjusted).
6. **Repeat for the prior 4 days** for the trend table.
7. **Pull ad-level spend** for last 7 days, filter to >$50.
8. **For each, check `effective_status`** — flag any that aren't `ACTIVE`.

## What this skill won't do

- **It doesn't make changes.** Read-only. Decisions stay with you.
- **It doesn't attribute orders to ads.** That's a different problem and Meta's attribution is unreliable enough that it's a separate skill.
- **It doesn't replace daily Shopify ops or customer service work.** It's the morning ad-account check, nothing else.

## Related skills (Accelerator family)

- **cost-cap-walkdown** — $1-at-a-time cost cap adjustment methodology in 2-day cycles. Pair with this skill: morning check identifies candidates, walkdown adjusts them.
- **attribution-adjusted-roas** — calculate the Meta-reported ROAS you need to hit a target CM%, accounting for the gap between Meta-attributed and Shopify-actual revenue.

## Access

This skill ships with the **Prompted Accelerator** at [skool.com/the-prompted](https://www.skool.com/the-prompted). Members get the full operator skill family, support, and live sessions where these skills are used on real ad accounts.

## Built by

[The Prompted](https://theprompted.com) — operators using AI in real DTC media buying, not theorizing about it. Skill bundle distilled from active ~$10K/month Meta spend across multiple Shopify accounts.
