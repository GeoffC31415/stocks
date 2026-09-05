# Reviewed security identity registry

The registry is deliberately small. Unsupported mappings stay as separate positions;
an editable ticker or matching display name is not identity evidence. Original
broker identifiers are not rewritten. Source-value currency remains part of the key.

## EQQQ — checked 2026-09-05

The [London Stock Exchange instrument page](https://www.londonstockexchange.com/stock/EQQQ/invesco/company-page)
was read in a real browser. Its instrument information reports:

- Symbol: `EQQQ`; name: `INVESCO EQQQ NASDAQ 100 UCITS ETF`.
- ISIN: `IE0032077012`; SEDOL: `B0GL4T3`; MIC: `XLON`.
- Traded price currency: `GBX`; income distribution: `Paid`.
- The exchange explains that GBX trade values are displayed in major currency GBP.

The existing provider mapping `EQQQ.L` is accepted only with one of those exact
source identifiers and GBP/GBX/GBp source value currency. The registry key includes
ISIN, exchange, listing symbol and the unchanged source currency. A different
ISIN, unknown identifier, accumulating share class, currency or listing cannot
merge merely because its editable ticker says EQQQ.L. No other listing has been
approved by this change. This is not look-through or provider-history readiness.
