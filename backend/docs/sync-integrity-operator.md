# Ingest safety and operator review

Imports/repairs require explicit target selection, a verified private backup and
disposable preview before approved live writes. Source guidance is not deployment
or real-broker authorization.

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
  Pair agreement alone does not establish canonical ownership: every paired import
  also requires exactly one trusted operator-enrolled `hl-client-identity` pin in
  `account_aliases` for the resolved owner. No first-use enrollment or automatic
  repinning occurs. See [trusted HL enrollment](#trusted-hl-enrollment) below for the
  fail-closed bootstrap path, including legacy and empty accounts.

## Genuine Trading 212 sale: narrow offline resolution

Automatic sync refuses disappearing securities. Historical sells or `--force` do
not authorize closure. A human must independently verify the genuine sale, account
ownership, completeness of all remaining positions and cash, and the exact source
observation. The CLI below imports **only that snapshot**; it neither logs in nor
imports orders/transactions nor advances provider freshness.

1. Make a consistent SQLite backup/copy using SQLite's backup API (not an unsafe
   copy of a live WAL database). Use the copy for the preview. Identify the canonical
   account and BOTH its latest ingested snapshot (`id DESC`) and latest canonical
   retained valuation (`as_of_date DESC, id DESC`) batch IDs/hashes from that copy.
   Both must be `trading212-api-portfolio.json` observations; they can differ after
   a backdated import. Review missing holdings against the valuation baseline.
2. Stage positions and a successful account summary offline from independently
   reviewed, read-only evidence. Do not place partial exports in the automatic inbox.
3. Create a private JSON review manifest containing exactly these fields:

   | Field | Required evidence |
   |---|---|
   | `account_name` | Exact reviewed canonical name, or an existing alias resolving to it |
   | `expected_batch_id` | Exact latest ingested account snapshot batch ID |
   | `expected_batch_sha256` | That batch's exact stored hash |
   | `expected_valuation_batch_id` | Exact latest canonical retained valuation batch ID |
   | `expected_valuation_batch_sha256` | That valuation batch's exact stored hash |
   | `observation_sha256` | Canonical staged snapshot digest, as defined below |
   | `identifiers` | Nonempty array of exact missing security identifiers approved for closure; never `CASH` |
   | `positions` | Complete staged provider positions array |
   | `account_summary` | Complete successful provider summary with verified GBP cash buckets |
   | `observed_at` | Actual timezone-aware, nonfuture source observation timestamp, not predating either retained baseline |

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
   the user before production. This guide grants no production action.
5. Only after actual operator approval, an operator may run the same command with
   `--apply` against the explicitly selected target. There is no database default,
   broker credential access, network fetch, `--force` or wildcard account option.
   SQLite writer reservation serializes BOTH baseline checks and mutation against
   concurrent writers. Changed account/batch/hash, stale valuation evidence,
   mismatched staged observation, other-provider baseline and cash closures reject.
   Successful apply commits one reviewed snapshot; reusing its old approval fails
   against the new latest batch. Read back that exact target's batch/closure records.
6. Run a separately authorized normal complete sync later to refresh all required
   provider sections. The offline review must not masquerade as a fresh full sync.

## Trusted HL enrollment

A coherent pair proves only that its halves agree. It does **not** prove that the
client owns the retained canonical account. Every paired HL import, including a
first empty-account import and an unchanged repeat, now requires exactly one
operator-enrolled identity pin. Missing, mismatched or ambiguous pins reject before
snapshot/order writes. Neither imported exports nor the importer can enroll or
repin an owner.

The pin uses the existing `account_aliases` table, with:

- `source = 'hl-client-identity'` (reserved for trusted enrollment);
- `source_account_name = hl_client_identity_key(confirmed_client_name,
  confirmed_client_number)`;
- `canonical_account_name =` the independently confirmed resolved account;
- an operator identity and private evidence reference in `created_by` / `notes`.

The key hashes the exact stripped raw name and number, independently of the
historical HL account label. It is private pseudonymous provenance, not an
authentication credential; do not publish it. Legacy economic fingerprints and
legacy account labels are unchanged. Colon-label handling still validates raw
identity separately. A holdings alias is not an owner pin.

### Enrollment review procedure

1. Disable scheduled/manual imports during enrollment. Take a consistent SQLite
   backup and rehearse restoration on a disposable copy. Keep identity evidence
   private; no client names/numbers in tracked files or public reports.
2. Independently establish the client name **and** client number from a trusted
   account statement/authenticated account view, not solely from the incoming pair.
   Confirm the canonical owner and any existing holdings/activity account aliases.
   For legacy data without identity evidence, obtain operator review: do not adopt
   the first newly supplied pair as proof of ownership. For a genuinely new empty
   account, explicitly approve that owner before its first pair import.
3. On the disposable copy, use an offline Python session importing only SQLAlchemy,
   `app.models.AccountAlias` and `app.services.hl_parser.hl_client_identity_key`.
   Bind its engine to the explicit copy path, not application database defaults.
   Start `BEGIN IMMEDIATE`; verify no `AccountAlias` exists with
   `source == 'hl-client-identity'` for the resolved canonical account and no pin
   with the intended key belongs to a different canonical account. **Abort** on
   any existing pin: never update/delete it to make a mismatched export pass.
4. Explicitly insert one `AccountAlias` with the fields above; commit and read back
   that exact row in a fresh reader. `enroll_synthetic_hl_owner` in
   `backend/tests/test_gate_a_hl_pair.py` demonstrates the ORM shape with synthetic
   values only. Enrollment is a trusted operator database edit, not a public API.
5. Exercise a private staged pair against the copy, verify valuation/holdings,
   order deduplication and absent-position effects against trusted sale evidence.
   A new coherent different client name or number must reject without changes.
   Restore the copy to confirm the backup boundary. Only after explicit deployment
   approval repeat the reviewed enrollment on the approved target and read it back.
   Resume imports only after verification; retain the previous backup for rollback.

Identity corrections/owner transfers are a separate reviewed repair operation,
not an automatic repin. If there is insufficient trustworthy identity evidence,
leave the pin absent and HL paired sync blocked. This procedure does not attest real
broker export completeness, validate actual portfolio data, or enroll a live pin.
These remain operator acceptance gates.
