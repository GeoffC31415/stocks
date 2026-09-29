# Offline owner and closure review gates

This is a source-only change. No live database, credentials, broker sessions or
production services were accessed. No schema migration is needed.

## Trading 212 closure review

A private closure manifest now requires **both** pairs of fields:

- `expected_batch_id`, `expected_batch_sha256`: latest ingestion for the resolved
  canonical account (`ImportBatch.id DESC`).
- `expected_valuation_batch_id`, `expected_valuation_batch_sha256`: exact latest
  retained valuation (`as_of_date DESC, id DESC`) for that same account.

Both baselines must be Trading 212 API snapshots. They can differ when a backdated
observation was ingested later. Do not copy the ingestion fields into valuation
fields without independently checking the retained state. Old manifests lacking
valuation fields are rejected. Review identifiers against the valuation baseline,
not the latest ingestion. Keep the staged observation hash and reviewed missing
security allowlist exact; cash cannot be approved as a missing security.

`observed_at` must not precede either retained date. Validation and the canonical
mutation hold one SQLite writer reservation, including direct service callers.
Invalid reviews reject before staging holdings, even with `--apply`. Valid preview
stages then rolls back; only explicit apply commits. The CLI takes an explicit
existing database path and does not read broker credentials:

```sh
PYTHONPATH=backend .venv/bin/python -m app.closure_review_cli \
  --database /explicit/disposable/portfolio-copy.db --review /private/review.json
# Recheck evidence and both baselines before adding --apply on an approved copy.
```

## HL trusted owner pin: explicit enrollment required

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

### Bootstrap review procedure (not performed by this change)

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
leave the pin absent and HL paired sync blocked. This patch does not attest real
broker export completeness, validate actual portfolio data, or enroll a live pin.
These remain operator acceptance gates.

## Public status report resilience

Malformed list/dict status, coverage, name, reason/action and outcome values are
reduced to public allowlisted defaults; non-list steps/files are ignored. Arbitrary
payload detail, client identity and file names are not echoed.
