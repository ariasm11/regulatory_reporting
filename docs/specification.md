# Regulatory specification and implementation decisions

Reviewed: 2026-09-28. Scope: F.943 SITER A v500, ordinary ARS accounts and new ARS term deposits for the configured March-August 2026 periods. This document separates published positions from inferred scenario decisions.

## Source provenance

Manual URL: https://www.afip.gob.ar/operacionesFinancieras/documentos/Manual-F943-SITER-A-Cuentas-y-Operaciones.pdf

Downloaded manual SHA-256: `b34d14d9ac5d514361e6172e1d8a45f2d3fcd44d45887c9bf251d0b5874a9562`.
Embedded last modification: 2025-08-06. Layout interface: 00500. Normative rules: RG 4298 current Title I and Article 16 exclusions, including RG 5814/2026. The source manual is linked rather than redistributed.

## Decisions and limitations

| ID | Evidence / issue | Implementation | Status |
|---|---|---|---|
| D01 | Manual p.11 prose says header 43 characters; table reaches 255; history p.4 adds 212-character filler | Use 255, spaces in positions 38-249 | Positional interpretation; official acceptance unverified |
| D02 | Manual p.13 balance sign lacks listed values; adjacent card signs define 0 positive / 1 negative | Apply 0/1 to balance too | Inference requiring Reporting confirmation |
| D03 | Manual p.10 requires count of record 03 to match record 02 quantity | Quantity counts additional serialized members, excluding primary represented in 02 | Interpretation documented and tested |
| D04 | Rule extends information when any Article 2(b-f) threshold is reached | In a one-primary-account-per-customer scenario, retain all scoped account measures and all new deposits for that owner in the period | Multi-account/joint-owner policy deliberately rejected |
| D05 | Manual p.9 asks for integer numeric amounts, without a universal rounding algorithm | All generated amounts are whole pesos; non-integral aggregated pesos fail | Approved rounding policy needed for fractional inputs |
| D06 | Refunds and error reversals need business classification | CARD_REFUND reduces card consumption and adds to balance; no credit trigger; unknown correction types fail | Scenario mapping, requires Reporting sign-off |
| D07 | Article 2(d) uses last business day | Explicit period cutoff dates; May balance is May 29 while activity covers all May | Calendar covers six stated periods only; not a general Argentine calendar |
| D08 | Fields for FX, special accounts and judicial honoraria require extra models | Reject unsupported input kinds/accounts/currencies; no 06/07, F8103 or F944 generated | Scope restriction, not full bank reporting coverage |

## Business rules

| Rule | Source | Implementation / test |
|---|---|---|
| Monthly credits and absolute cutoff balance: PH 50m / PJ 30m pesos | RG4298 Art.2(b,d) | Inclusive thresholds, signed balance, exact boundary fixture |
| Cash withdrawals 10m pesos | Art.2(c) | Cash only; transfers and card purchases separated |
| New term deposits PH 100m / PJ 30m pesos | Art.2(e) | Sum new principal by primary customer/month |
| Domestic debit-card consumption 50m pesos | Art.2(f) | Signed net consumption under D06 |
| Account opening/block/change/closure events | Art.2(a) | One source event per account per month, report even below monetary thresholds |
| Excluded persons/entities | Art.16 | Explicit source exclusion boolean, not inferred from synthetic names |
| Full replacement | Art.15 | Regenerate all reportable records with new sequence |
| No activity | Art.14; manual p.10 | Header only, no_activity=1; no other records permitted |
| Credits subcategories and exclusions | Annex II | Separate own transfers, loans and term maturity; unsupported error reversals rejected |

Selection and amount rules require both normative text and a domain reviewer. Passing this repository's validation does not demonstrate taxpayer registration, real CBU ownership or official filing acceptance.

## File contract

ISO-8859-1; this implementation emits CRLF (manual also accepts LF). Text fields left aligned with spaces; numeric fields right aligned with zeroes. Width overflow, forbidden control characters and unsupported data fail. Output filename example pattern: `F0943.<11-digit-reporter>.<YYYYMM>00.<4-digit-sequence>.txt`. Header sequence is two digits, 00-99. ZIP contains one TXT; no DGRALES file is invented.

Positions below are inclusive and 1-based, transcribed for the writer. The independent parser has its own explicit slices. Numeric types `n`; alphanumeric `a`. Full field semantics and code lists remain in the linked official manual.

## Record 01: 255 bytes

| Field | Positions | Width | Type |
|---|---:|---:|---|
| record_type | 1-2 | 2 | n |
| reporter_cuit | 3-13 | 11 | n |
| period | 14-19 | 6 | n |
| sequence | 20-21 | 2 | n |
| entity_code | 22-26 | 5 | n |
| tax | 27-30 | 4 | n |
| concept | 31-33 | 3 | n |
| form | 34-37 | 4 | n |
| filler | 38-249 | 212 | a |
| version | 250-254 | 5 | n |
| no_activity | 255-255 | 1 | n |

## Record 02: 236 bytes

| Field | Positions | Width | Type |
|---|---:|---:|---|
| record_type | 1-2 | 2 | n |
| account_type | 3-4 | 2 | n |
| number | 5-26 | 22 | n |
| cbu | 27-48 | 22 | n |
| currency | 49-51 | 3 | a |
| branch | 52-56 | 5 | n |
| document_type | 57-58 | 2 | n |
| document | 59-69 | 11 | n |
| caja_valores | 70-74 | 5 | n |
| role | 75-76 | 2 | n |
| member_count | 77-78 | 2 | n |
| additional_cards | 79-80 | 2 | n |
| credits | 81-98 | 18 | n |
| own_credits | 99-116 | 18 | n |
| loan_credits | 117-134 | 18 | n |
| term_credits | 135-152 | 18 | n |
| cash | 153-170 | 18 | n |
| balance_sign | 171-171 | 1 | n |
| balance | 172-189 | 18 | n |
| card_sign | 190-190 | 1 | n |
| card | 191-208 | 18 | n |
| foreign_card_sign | 209-209 | 1 | n |
| foreign_card | 210-227 | 18 | n |
| event | 228-228 | 1 | a |
| event_date | 229-236 | 8 | n |

## Record 03: 17 bytes

| Field | Positions | Width | Type |
|---|---:|---:|---|
| record_type | 1-2 | 2 | n |
| document_type | 3-4 | 2 | n |
| document | 5-15 | 11 | n |
| role | 16-17 | 2 | n |

## Record 04: 154 bytes

| Field | Positions | Width | Type |
|---|---:|---:|---|
| record_type | 1-2 | 2 | n |
| deposit_type | 3-4 | 2 | n |
| number | 5-26 | 22 | n |
| branch | 27-31 | 5 | n |
| opened | 32-39 | 8 | n |
| foreign_beneficiary | 40-40 | 1 | n |
| maturity | 41-48 | 8 | n |
| document_type | 49-50 | 2 | n |
| document | 51-61 | 11 | n |
| role | 62-63 | 2 | n |
| member_count | 64-65 | 2 | n |
| caja_valores | 66-70 | 5 | n |
| principal | 71-88 | 18 | n |
| interest | 89-106 | 18 | n |
| principal_original | 107-124 | 18 | n |
| interest_original | 125-142 | 18 | n |
| currency | 143-145 | 3 | a |
| event | 146-146 | 1 | a |
| event_date | 147-154 | 8 | n |

## Record 05: 18 bytes

| Field | Positions | Width | Type |
|---|---:|---:|---|
| record_type | 1-2 | 2 | n |
| document_type | 3-4 | 2 | n |
| document | 5-15 | 11 | n |
| foreign_beneficiary | 16-16 | 1 | n |
| role | 17-18 | 2 | n |
