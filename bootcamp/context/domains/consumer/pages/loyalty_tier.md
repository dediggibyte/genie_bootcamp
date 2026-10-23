---
title: Loyalty Tier
domain: Consumer
subdomain: Loyalty Programs
synonyms:
  - tier
  - membership tier
  - membership level
  - Fjällmark Friends tier
  - Bronze
  - Silver
  - Gold
  - Platinum
  - member status
description: "The membership level of a Fjällmark Friends loyalty member — Bronze, Silver, Gold or Platinum (rank 1–4) — which sets the points multiplier, member discount and free shipping."
owner: Loyalty Programme Manager (role)
related_assets:
  - <catalog>.consumer.loyalty_tier
  - <catalog>.consumer.loyalty_account
  - <catalog>.consumer.loyalty_program
  - <catalog>.consumer.dtc_order
  - <catalog>.consumer.dtc_sales_metrics
  - <catalog>.consumer.loyalty_account_metrics
sources:
  - Fjällmark Friends programme terms (fictional)
  - "Lakehouse Industry Data Model — Consumer Goods v2 MVM: consumer.loyalty_tier, consumer.loyalty_account"
---

# Loyalty Tier

## Definition

Fjällmark has one loyalty programme, **Fjällmark Friends** (`loyalty_program.program_name`). A
shopper who enrols gets a `loyalty_account`; the member's **current tier** is on the shopper
(`shopper.loyalty_tier_id` → `loyalty_tier`) and, identically, on the account
(`loyalty_account.loyalty_tier_id`).

| `tier_name` | `tier_code` | `tier_rank` | Points multiplier | Member discount | Free shipping | Share of members |
|---|---|---|---|---|---|---|
| Bronze | BRONZE | 1 | 1.0× | 0 % | no | ~54 % |
| Silver | SILVER | 2 | 1.25× | 2 % | no | ~25 % |
| Gold | GOLD | 3 | 1.5× | 5 % | yes | ~14 % |
| Platinum | PLATINUM | 4 | 2.0× | 8 % | yes | ~6 % |

100 points = 1 EUR. Shoppers **without** a loyalty account are **non-members** (there is no
"None" tier row).

## Business rules

1. Use `loyalty_tier.tier_name` for labels and `tier_rank` for ordering ("Gold or higher" =
   `tier_rank >= 3`).
2. Tier comparisons of buying behaviour use the shopper's **current** tier: `dtc_order.shopper_id` →
   `shopper.loyalty_tier_id` → `loyalty_tier.tier_name`; shoppers without a tier are **Non-member**.
   (`dtc_order.loyalty_account_id` is only filled on orders that earned points, i.e. placed after
   enrolment — joining on it would label a member's earlier orders as non-member.)
3. Count **members** with `loyalty_account.account_status = 'active'` unless the user asks for all
   accounts (statuses: `active`, `suspended`, `closed`, `pending`, `frozen`).
4. Known pattern (2024-01 … 2026-09): Gold/Platinum members place about **3×** as many orders per
   shopper as non-members (≈ 5.3 vs 1.8) and their average order value is about **2.4×** higher
   (order value incl. VAT, EUR; ≈ 2.6× on net merchandise value).

## How to calculate (SQL)

```sql
-- Active members per tier
SELECT t.tier_rank, t.tier_name, COUNT(*) AS active_members
FROM consumer.loyalty_account la
JOIN consumer.loyalty_tier t ON t.loyalty_tier_id = la.loyalty_tier_id
WHERE lower(la.account_status) = 'active'
GROUP BY t.tier_rank, t.tier_name
ORDER BY t.tier_rank;
```

```sql
-- Orders per shopper and AOV (EUR) by current tier, non-members included, all non-cancelled orders
WITH fx AS (
  SELECT jel.company_code_id, je.fiscal_year, je.fiscal_period, AVG(jel.exchange_rate) AS eur_rate
  FROM finance.journal_entry_line jel
  JOIN finance.journal_entry je ON je.journal_entry_id = jel.journal_entry_id
  GROUP BY ALL
)
SELECT coalesce(t.tier_name, 'Non-member')                                                AS loyalty_tier,
       COUNT(DISTINCT s.shopper_id)                                                       AS shoppers,
       COUNT(DISTINCT o.dtc_order_id)                                                     AS orders,
       ROUND(COUNT(DISTINCT o.dtc_order_id) / COUNT(DISTINCT s.shopper_id), 2)            AS orders_per_shopper,
       ROUND(SUM((o.subtotal_amount - o.discount_amount) * fx.eur_rate)
             / COUNT(DISTINCT o.dtc_order_id), 2)                                         AS aov_net_eur
FROM consumer.shopper s
LEFT JOIN consumer.loyalty_tier t ON t.loyalty_tier_id = s.loyalty_tier_id
LEFT JOIN consumer.dtc_order o    ON o.shopper_id = s.shopper_id AND lower(o.order_status) <> 'cancelled'
LEFT JOIN fx                      ON fx.company_code_id = o.company_code_id
                                 AND fx.fiscal_year = year(o.order_date) AND fx.fiscal_period = month(o.order_date)
GROUP BY ALL
ORDER BY aov_net_eur;
```

Governed: `<catalog>.consumer.dtc_sales_metrics` (loyalty tier dimension).

## Pitfalls and common wrong answers

| Wrong answer | Why it is wrong |
|---|---|
| Using `loyalty_account.previous_tier` | It is the tier *before the last change* and uses a different, lower-case vocabulary (`standard`, `silver`, `gold`, `platinum`, `elite`). |
| Using `loyalty_program.tier_level` | Programme-level attribute, not the member's tier. |
| Inner-joining orders to loyalty accounts, or tiering orders via `dtc_order.loyalty_account_id` | Drops non-member orders (the comparison group) and mislabels members' pre-enrolment orders. |
| Comparing AOV across tiers over mixed currencies | Filter one currency or convert to EUR. |

## Example questions

* How many active members are in each loyalty tier?
* Do Gold and Platinum members spend more per order than non-members?
* How many members moved up a tier in 2026?
