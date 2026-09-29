# Sync integrity and operator closure review

## Deployment gate

This change has been exercised only against synthetic exports and disposable SQLite
files. Do not apply it to production, invoke a live broker, change credentials or
migrate a live database without operator approval after the requested preview.

## Status semantics

- A Trading 212 observation requires holdings, cash, order history and transaction
  history. Missing account-summary/cash permission rejects the entire observation,
  including the first import. Cancellation/timeout rolls back the owning transaction.
- Live snapshot hashes are compared with the latest **ingested account observation**
  (batch ID), not every historical hash or the latest-dated valuation. A → B → A
  imports three observations; only the fourth consecutive A is unchanged. Local
  inbox duplicate detection remains historical. No old batches/fingerprints are
  deleted or rewritten.
- `verified_at` is the provider check time. `valuation_at` is retained snapshot
  evidence, not the current check date. HL's `Valuation as at` takes precedence over
  `Spreadsheet created at`; a pair without date evidence is rejected.
- `complete` requires every explicit required section to have successful verified
  coverage. Committing rows alone does not prove coverage. Duplicate-only inbox
  runs are `no_op`, not new provider observations.
- HL's browser fetch requests a bounded 90-day activity interval. The report exposes
  `coverage_start`/`coverage_end` and `coverage=partial`, never universal history.
  Staged pairs without attested fetch ranges report order coverage `unknown`.
  Range bounds and all imported trade dates are checked before writes. Barclays
  order-export history currently has no universal-coverage attestation and remains
  `unknown`. These runs can commit safely but aggregate as `partial` and need review;
  do not turn missing evidence into `complete` to make a timer exit successfully.
- Both HL halves must independently contain matching, nonempty `Client Name` and
  `Client Number`. Legacy account labels/fingerprints are unchanged. Missing or
  different raw identity is rejected even when old hardcoded account names agree.

## Genuine Trading 212 sale: narrow offline resolution

Automatic sync refuses disappearing securities. Historical sells or `--force` do
not authorize closure. A human must independently verify the genuine sale, account
ownership, completeness of all remaining positions and cash, and the exact source
observation. The CLI below imports **only that snapshot**; it neither logs in nor
imports orders/transactions nor advances provider freshness.

1. Make a consistent SQLite backup/copy using SQLite's backup API (not an unsafe
   copy of a live WAL database). Use the copy for the preview. Identify the canonical
   account and its latest Trading 212 snapshot batch ID and `file_sha256` from that
   copy. The latest batch must be a `trading212-api-portfolio.json` observation.
2. Stage positions and a successful account summary offline from independently
   reviewed, read-only evidence. Do not place partial exports in the automatic inbox.
3. Create a private JSON review manifest containing exactly these fields:

   | Field | Required evidence |
   |---|---|
   | `account_name` | Exact reviewed canonical name, or an existing alias resolving to it |
   | `expected_batch_id` | Exact latest account snapshot batch ID |
   | `expected_batch_sha256` | That batch's exact stored hash |
   | `observation_sha256` | Canonical staged snapshot digest, as defined below |
   | `identifiers` | Nonempty array of exact missing security identifiers approved for closure; never `CASH` |
   | `positions` | Complete staged provider positions array |
   | `account_summary` | Complete successful provider summary with verified GBP cash buckets |
   | `observed_at` | Actual timezone-aware, nonfuture source observation timestamp |

   Digest algorithm (same bytes as the existing snapshot fingerprint):
   `sha256(json.dumps({"account_name": CANONICAL_ACCOUNT, "account": SUMMARY,
   "positions": sorted(POSITIONS, key=lambda row: json.dumps(row, sort_keys=True))},
   sort_keys=True, separators=(",", ":")).encode()).hexdigest()`.
   Use the **resolved canonical** account, not an alias, in this digest. Preserve
   identifiers/hashes exactly; do not normalise or invent source values. Treat the
   manifest as private financial data and restrict it to the operator.
4. Preview against the explicit backup copy (default rolls back all staged writes):

   ```sh
   PYTHONPATH=backend .venv/bin/python -m app.closure_review_cli \
     --database /explicit/path/to/preview-copy.sqlite \
     --review /explicit/path/to/private-reviewed-observation.json
   ```

   Confirm `applied=false`, account and closed identifiers. Review the preview with
   the user before production. No production action has been approved or executed
   by this change.
5. Only after actual operator approval, an operator may run the same command with
   `--apply` against the explicitly selected target. There is no database default,
   broker credential access, network fetch, `--force` or wildcard account option.
   SQLite `BEGIN IMMEDIATE` serializes the baseline check and mutation against
   concurrent writers. Changed account/batch/hash, stale valuation evidence,
   mismatched staged observation, other-provider baseline and cash closures reject.
   Successful apply commits one reviewed snapshot; reusing its old approval fails
   against the new latest batch. Read back that exact target's batch/closure records.
6. Run a separately authorized normal complete sync later to refresh all required
   provider sections. The offline review must not masquerade as a fresh full sync.

## Regression gates

`backend/tests/test_independent_backend_regressions.py` covers owner-commit-after-
cancellation and real runner timeout on file SQLite; both providers' A → B → A → A;
required coverage/skipped orders/duplicate-only inbox; retained Trading 212 and HL
valuation evidence; first-import denied cash; missing paginator termination and
oversized pages; account/alias/stale/provider/cash/exact-observation closure checks;
CLI preview/apply on disposable SQLite; raw HL identity and date rejection; bounded
activity and privacy-safe public ranges. Existing parser/pair/API/reliability tests
use labelled synthetic fixtures and preserve historical fingerprint expectations.
