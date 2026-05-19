#!/usr/bin/env python3
"""Ad Account Morning Check.

Pulls yesterday's Shopify orders + Meta ad spend, computes real contribution margin
(using your unit-economics JSON), and prints a daily morning report.

Usage:
  python3 morning_check.py [--days 5] [--paused-threshold 50] [--lookback 7]
"""
import argparse, json, os, sys, urllib.request, urllib.parse, re
from datetime import datetime, timedelta
from collections import Counter

# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def load_env():
    """Read .env at project root."""
    env = {}
    for path in ['.env', './.env']:
        if not os.path.exists(path): continue
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line: continue
                k, v = line.split('=', 1)
                env[k.strip()] = v.strip()
        break
    return env

def load_unit_economics():
    for path in ['unit-economics.json', './unit-economics.json']:
        if os.path.exists(path):
            return json.load(open(path))
    print("ERROR: unit-economics.json not found. Copy unit-economics.template.json → unit-economics.json and fill in your cost structure.", file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------------------
# Shopify
# ---------------------------------------------------------------------------

def shopify_orders(store, token, since, until):
    """Pull all orders in window. Returns list of order dicts."""
    orders = []
    url = f"https://{store}/admin/api/2024-01/orders.json?created_at_min={since}T00:00:00-04:00&created_at_max={until}T23:59:59-04:00&status=any&limit=250"
    while url:
        req = urllib.request.Request(url, headers={'X-Shopify-Access-Token': token})
        try:
            resp = urllib.request.urlopen(req)
        except urllib.error.HTTPError as e:
            print(f"Shopify HTTP {e.code}: {e.read().decode()[:300]}", file=sys.stderr)
            return orders
        link_header = resp.headers.get('Link', '')
        data = json.loads(resp.read())
        orders.extend(data.get('orders', []))
        next_url = None
        if 'rel="next"' in link_header:
            m = re.search(r'<([^>]+)>;\s*rel="next"', link_header)
            if m: next_url = m.group(1)
        url = next_url
    return orders

# ---------------------------------------------------------------------------
# Unit economics — per-order margin
# ---------------------------------------------------------------------------

def order_margin(order, ue):
    """Compute pre-ad margin for one order using simple unit-economics rates."""
    total_price = float(order.get('total_price', 0))
    subtotal = float(order.get('subtotal_price', 0))
    # COGS — default to a % of subtotal (after-discount product value)
    cogs = subtotal * ue.get('default_cogs_pct_of_subtotal', 0.33)
    # Shipping cost — flat avg (you charge customer separately; this is YOUR cost)
    n_line_items = sum(int(li.get('quantity', 0)) for li in order.get('line_items', []) if li.get('title', '') != 'Tip')
    shipping_cost = ue.get('shipping_cost_avg', 5.50) * max(1, n_line_items // 3 + 1)  # rough scaling
    # Processing fees — % of total
    processing = total_price * ue.get('processing_pct', 0.041)
    # Returns reserve
    returns = total_price * ue.get('returns_reserve_pct', 0.02)
    margin = total_price - cogs - shipping_cost - processing - returns
    return {
        'total_price': total_price,
        'subtotal': subtotal,
        'cogs': cogs,
        'shipping': shipping_cost,
        'processing': processing,
        'returns': returns,
        'margin': margin,
    }

def day_pnl(store, token, ue, date):
    """Pull orders for a date and compute aggregate pre-ad margin."""
    # ISO 8601 date string YYYY-MM-DD
    orders = shopify_orders(store, token, date, date)
    revenue = 0.0; cogs = 0.0; shipping = 0.0; processing = 0.0; returns = 0.0; margin = 0.0
    units = 0
    for o in orders:
        m = order_margin(o, ue)
        revenue += m['total_price']
        cogs += m['cogs']
        shipping += m['shipping']
        processing += m['processing']
        returns += m['returns']
        margin += m['margin']
        units += sum(int(li.get('quantity', 0)) for li in o.get('line_items', []) if li.get('title', '') != 'Tip')
    n = len(orders)
    return {
        'date': date,
        'orders': n,
        'revenue': revenue,
        'cogs': cogs,
        'shipping': shipping,
        'processing': processing,
        'returns': returns,
        'margin_before_ads': margin,
        'margin_before_ads_pct': (margin/revenue*100) if revenue else 0,
        'aov': (revenue/n) if n else 0,
        'units': units,
        'units_per_order': (units/n) if n else 0,
    }

# ---------------------------------------------------------------------------
# Meta
# ---------------------------------------------------------------------------

def meta_call(path, params, token):
    params['access_token'] = token
    url = f"https://graph.facebook.com/v21.0/{path}?" + urllib.parse.urlencode(params)
    try:
        return json.loads(urllib.request.urlopen(url).read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"Meta HTTP {e.code} on {path}: {body[:300]}", file=sys.stderr)
        return {}

def meta_spend_for_day(account_id, token, date):
    r = meta_call(f"{account_id}/insights", {
        'fields': 'spend,impressions,actions,action_values',
        'time_range': json.dumps({'since': date, 'until': date}),
    }, token)
    if not r.get('data'): return {'spend': 0.0, 'impressions': 0, 'purchases': 0, 'meta_rev': 0.0}
    d = r['data'][0]
    spend = float(d.get('spend', 0))
    purchases = 0; meta_rev = 0.0
    for a in d.get('actions', []):
        if a['action_type'] in ('purchase', 'omni_purchase'):
            purchases = max(purchases, int(a['value']))
    for v in d.get('action_values', []):
        if v['action_type'] in ('purchase', 'omni_purchase'):
            meta_rev = max(meta_rev, float(v['value']))
    return {
        'spend': spend,
        'impressions': int(d.get('impressions', 0) or 0),
        'purchases': purchases,
        'meta_rev': meta_rev,
    }

def meta_paused_ads_with_spend(account_id, token, since, until, threshold):
    """Return list of ads that spent > $threshold and are NOT effective_status=ACTIVE."""
    insights = meta_call(f"{account_id}/insights", {
        'fields': 'ad_id,ad_name,spend,actions,action_values',
        'time_range': json.dumps({'since': since, 'until': until}),
        'level': 'ad',
        'limit': 500,
        'filtering': json.dumps([{'field': 'spend', 'operator': 'GREATER_THAN', 'value': threshold}]),
    }, token)
    records = []
    for d in insights.get('data', []):
        spend = float(d.get('spend', 0))
        if spend < threshold: continue
        p = 0; pv = 0
        for a in d.get('actions', []):
            if a['action_type'] in ('purchase', 'omni_purchase'):
                p = max(p, int(a['value']))
        for v in d.get('action_values', []):
            if v['action_type'] in ('purchase', 'omni_purchase'):
                pv = max(pv, float(v['value']))
        records.append({'id': d['ad_id'], 'name': d.get('ad_name', ''), 'spend': spend, 'purch': p, 'pv': pv})
    # Now fetch status one at a time (the IN filter is unreliable on some account configs)
    paused = []
    for r in records:
        try:
            s = meta_call(r['id'], {'fields': 'id,name,effective_status,adset_id'}, token)
            es = s.get('effective_status', '?')
            if es != 'ACTIVE':
                paused.append({**r, 'effective_status': es, 'adset_id': s.get('adset_id', '')})
        except Exception:
            continue
    return paused

# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def fmt_money(x): return f"${x:,.2f}"
def fmt_pct(x): return f"{x:.1f}%"

def report(yesterday_pnl, yesterday_meta, history, paused_ads, ue, args):
    rate = ue.get('usd_cad_rate', 0.73)
    cur_spend = ue.get('currency_spend', 'CAD')
    cur_rev = ue.get('currency_revenue', 'USD')

    print()
    print("=" * 50)
    print(f"YESTERDAY ({yesterday_pnl['date']})")
    print("=" * 50)
    print(f"  Revenue:           {fmt_money(yesterday_pnl['revenue'])} {cur_rev}")
    spend_cad = yesterday_meta['spend']
    spend_usd = spend_cad * rate if cur_spend != cur_rev else spend_cad
    print(f"  Ad spend ({cur_spend}):    {fmt_money(spend_cad)}  ({cur_rev} ~{fmt_money(spend_usd)})")
    print(f"  Margin before ads: {fmt_money(yesterday_pnl['margin_before_ads'])} ({fmt_pct(yesterday_pnl['margin_before_ads_pct'])})")
    cm = yesterday_pnl['margin_before_ads'] - spend_usd
    cm_pct = (cm / yesterday_pnl['revenue'] * 100) if yesterday_pnl['revenue'] else 0
    print(f"  CM:                {fmt_money(cm)} ({fmt_pct(cm_pct)})")
    roas = (yesterday_pnl['revenue'] / spend_usd) if spend_usd else 0
    print(f"  ROAS:              {roas:.2f}x")
    print(f"  Orders:            {yesterday_pnl['orders']}  AOV: {fmt_money(yesterday_pnl['aov'])}")
    print(f"  Units:             {yesterday_pnl['units']} ({yesterday_pnl['units_per_order']:.1f}/order)")

    print()
    print("=" * 50)
    print(f"LAST {len(history)} DAYS")
    print("=" * 50)
    for h in history:
        d = h['pnl']
        m = h['meta']
        spend_cad_h = m['spend']
        spend_usd_h = spend_cad_h * rate if cur_spend != cur_rev else spend_cad_h
        cm_h = d['margin_before_ads'] - spend_usd_h
        cm_pct_h = (cm_h / d['revenue'] * 100) if d['revenue'] else 0
        roas_h = (d['revenue'] / spend_usd_h) if spend_usd_h else 0
        dow = datetime.fromisoformat(d['date']).strftime('%a')
        print(f"  {d['date']} ({dow}): rev={fmt_money(d['revenue'])}  spend={fmt_money(spend_cad_h)}  CM={fmt_money(cm_h)} ({fmt_pct(cm_pct_h)})  ROAS={roas_h:.2f}x  orders={d['orders']}  AOV={fmt_money(d['aov'])}")

    print()
    print("=" * 50)
    print(f"PAUSED ADS WITH >${args.paused_threshold:.0f} LAST {args.lookback}D")
    print("=" * 50)
    if paused_ads:
        print(f"  ⚠ {len(paused_ads)} paused ad(s) with significant spend:\n")
        for p in paused_ads:
            roas = (p['pv'] * rate) / p['spend'] if p['spend'] > 0 else 0
            print(f"  [{p['effective_status']}] {fmt_money(p['spend'])} spent, {p['purch']} purch, ROAS {roas:.2f}x")
            print(f"    {p['name'][:80]}")
            print(f"    ad_id: {p['id']}")
            print()
    else:
        print(f"  ✓ All ads with >${args.paused_threshold:.0f} spend in last {args.lookback}d are ACTIVE")
    print()

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--days', type=int, default=5, help='Days of trend history to show')
    ap.add_argument('--paused-threshold', type=float, default=50, help='Min spend (in account currency) to flag a paused ad')
    ap.add_argument('--lookback', type=int, default=7, help='Days to look back for paused-ad audit')
    args = ap.parse_args()

    env = load_env()
    ue = load_unit_economics()

    meta_token = env.get('META_PAGE_TOKEN') or env.get('META_ACCESS_TOKEN')
    meta_acct = env.get('META_AD_ACCOUNT_ID', '')
    shop_store = env.get('SHOPIFY_STORE', '')
    shop_token = env.get('SHOPIFY_ACCESS_TOKEN', '')

    missing = []
    if not meta_token: missing.append('META_PAGE_TOKEN')
    if not meta_acct: missing.append('META_AD_ACCOUNT_ID')
    if not shop_store: missing.append('SHOPIFY_STORE')
    if not shop_token: missing.append('SHOPIFY_ACCESS_TOKEN')
    if missing:
        print(f"ERROR: missing in .env: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    # Yesterday in ET (you may want to adjust this for your timezone)
    today = datetime.now().date()
    yesterday = (today - timedelta(days=1)).isoformat()

    # Yesterday's data
    yesterday_pnl = day_pnl(shop_store, shop_token, ue, yesterday)
    yesterday_meta = meta_spend_for_day(meta_acct, meta_token, yesterday)

    # Trend history (4 days before yesterday)
    history = []
    for i in range(2, args.days + 1):
        d = (today - timedelta(days=i)).isoformat()
        history.append({
            'date': d,
            'pnl': day_pnl(shop_store, shop_token, ue, d),
            'meta': meta_spend_for_day(meta_acct, meta_token, d),
        })
    history.reverse()
    # Add yesterday at the end of the trend table
    history.append({'date': yesterday, 'pnl': yesterday_pnl, 'meta': yesterday_meta})

    # Paused-ad audit — last N days
    since = (today - timedelta(days=args.lookback)).isoformat()
    until = yesterday
    paused = meta_paused_ads_with_spend(meta_acct, meta_token, since, until, args.paused_threshold)

    # Report
    report(yesterday_pnl, yesterday_meta, history, paused, ue, args)

if __name__ == '__main__':
    main()
