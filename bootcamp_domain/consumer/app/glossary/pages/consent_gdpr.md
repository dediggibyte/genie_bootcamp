---
title: Consent / GDPR
domain: Consumer
subdomain: Customer Identity
synonyms:
  - consent
  - GDPR
  - marketing consent
  - opt-in
  - opt-out
  - permission to contact
  - contactable
  - samtycke
  - DSGVO
description: "Whether Fjällmark may contact or profile a shopper: the current, granted consent record per shopper and consent type (marketing e-mail, SMS, push, data sharing, profiling, cookies) under GDPR."
owner: Data Protection Officer (role)
related_assets:
  - <catalog>.consumer.consent_record
  - <catalog>.consumer.shopper
  - <catalog>.consumer.loyalty_account
  - <catalog>.consumer.consent_record_metrics
sources:
  - Fjällmark Privacy Policy and Records of Processing (fictional)
  - "Regulation (EU) 2016/679 (GDPR), Articles 6, 7 and 22"
  - "Lakehouse Industry Data Model — Consumer Goods v2 MVM: consumer.consent_record"
---

# Consent / GDPR

## Definition

All Fjällmark shoppers are in the EU/EEA, so **GDPR** applies. Before Fjällmark sends marketing or
profiles a shopper it needs a valid **consent** for that purpose. The system of record is
**`consumer.consent_record`** — one row per shopper, consent type and version (SCD type 2 history).

> A shopper **has consent** for a purpose if their **current** consent record
> (`is_current_record = true`) for that `consent_type` has `consent_status = 'granted'`.

`consent_type` values: `marketing_email`, `sms`, `push_notification`, `data_sharing`,
`profiling`, `cookies`. `consent_status` values: `granted`, `withdrawn`, `pending`, `expired`.

> A shopper is **contactable by e-mail** if they have current granted `marketing_email` consent
> **and** `shopper.lifecycle_status` is not `opted_out` or `suspended`.

## Business rules

1. Only `is_current_record = true` rows describe today's state; older rows are audit history
   (`record_version`, `prior_consent_status`, `withdrawal_timestamp`).
2. Expired consent (`expiry_date` before the reporting date, or `consent_status = 'expired'`) is
   **not** consent.
3. Denormalised flags (`shopper.email_opt_in`, `shopper.sms_opt_in`, `shopper.data_sharing_consent`,
   `loyalty_account.consent_marketing`) are convenience copies — use `consent_record` for compliance
   answers.
4. Legal basis is in `legal_basis` (`consent`, `legitimate_interest`, `contract`, ...);
   `regulatory_jurisdiction` is `GDPR` for all Fjällmark shoppers.
5. **Privacy etiquette:** consent analysis is aggregate (counts, rates). Never output names, e-mail
   addresses, phone numbers or IP addresses — those columns are masked anyway.

## How to calculate (SQL)

```sql
-- Current consent status by consent type
SELECT cr.consent_type,
       cr.consent_status,
       COUNT(DISTINCT cr.shopper_id) AS shoppers
FROM consumer.consent_record cr
WHERE cr.is_current_record = true
GROUP BY ALL
ORDER BY cr.consent_type, shoppers DESC;
```

```sql
-- E-mail contactable shoppers by country
SELECT s.country_code,
       COUNT(DISTINCT s.shopper_id) AS email_contactable_shoppers
FROM consumer.shopper s
JOIN consumer.consent_record cr
  ON cr.shopper_id = s.shopper_id
 AND cr.is_current_record = true
 AND cr.consent_type = 'marketing_email'
 AND cr.consent_status = 'granted'
WHERE s.lifecycle_status NOT IN ('opted_out', 'suspended')
GROUP BY s.country_code
ORDER BY email_contactable_shoppers DESC;
```

Industry metric view: `<catalog>.consumer.consent_record_metrics`.

## Pitfalls and common wrong answers

| Wrong answer | Why it is wrong |
|---|---|
| Counting all `consent_record` rows | Includes history; filter `is_current_record = true`. |
| `WHERE shopper.email_opt_in = true` for a compliance report | Denormalised copy; not the audit trail. |
| Treating `pending` as granted | Double opt-in not completed — not valid consent. |
| Selecting `primary_email` of consenting shoppers | Personal data; masked and not needed for analysis. |

## Example questions

* How many shoppers can we e-mail for marketing, by market?
* What share of shoppers withdrew marketing consent in 2026?
* How many shoppers have consented to profiling?
