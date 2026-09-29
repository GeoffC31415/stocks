# Stocks preproduction preview review

## Open the review candidate

On the Surface, open **http://127.0.0.1:8794/**. This is separate from the production HTTPS site on port5000. It shows labelled synthetic data; it is not your portfolio, a broker session, or production sign-in. Code review is still in progress.

Layout alternatives:
- http://127.0.0.1:8794/demo/chart-first.html — recommended, awaiting your selection.
- http://127.0.0.1:8794/demo/ledger-first.html — alternative.

The listener is loopback-only. `127.0.0.1` on your phone or gaming PC is that device, not the Surface. Do not open firewall/router ports or expose this unauthenticated demo publicly.

From another computer with existing authorized SSH access, forward the Surface loopback port:

```sh
ssh -N -L 8794:127.0.0.1:8794 geoff@<Surface-address>
```

Then open http://127.0.0.1:8794/ on that computer while SSH stays connected. Use your existing hostname/address and authentication; no new SSH configuration is required. Off-LAN reachability/phone access is not verified and may require an existing VPN/remote desktop rather than port forwarding changes.

## What to test

- Overview: portfolio value is prominent, then secondary return/flows, chart, separately dated latest changes and allocation. Confirm the chart/notes make sparse observations and flow estimates obvious.
- Holding returns is lifetime holding analysis, distinct from selected-period Performance.
- Holdings: full-width when unselected; select/close details; check mobile Escape/focus return and shareable inst selection.
- Apply investigation filters, see active filter chips/counts, clear filters without losing account/period. Reset columns/sort should not silently clear investigation filters.
- Switch workspace tabs by mouse and arrow/Home/End keys; legacy URLs should still redirect to the correct view.
- Performance: switch raw snapshot history independently, inspect exact observed drawdown dates/table; unavailable calculations must not appear as zero or a valid-looking curve.
- Data: inspect refresh outcome/check/attempt/valuation/coverage. Synthetic partial/no-op evidence should never become generic green success.
- Resize the browser/mobile simulation. Mobile chart start is in the initial viewport, not the whole plot. Scroll to bottom to check fixed-navigation clearance.
- Review the labelled alternatives and tell Barry which direction to keep, plus any usability problems.

## Intentional restrictions

All mutations, actual import/edit/refresh operations and broker connections are disabled. Unknown API fixture reads return an explicit failure rather than reaching production. Synthetic fixtures demonstrate layout/state handling; they do not establish current-account totals, broker completeness, real passkey login, or production financial reconciliation.

No production deployment has occurred. Trying the preview does not approve live deployment; give that approval separately after remaining actual-data/security/operational gates are reviewed.

## Restart safely if the preview stopped

From the stocks checkout, build into a new scratch directory (not live assets) and start the GET-only preview:

```sh
cd /home/geoff/code/stocks
npm --prefix frontend run build -- --outDir "$TMPDIR/stocks-review-rebuild"
.venv/bin/python frontend/scripts/preview_demo.py --dist "$TMPDIR/stocks-review-rebuild" --port 8794
```

A foreground launch stops with Ctrl+C. If8794 is occupied, identify the existing owned preview instead of killing arbitrary listeners. Scratch files can expire; rebuild rather than using a stale deployment artifact. The currently prepared build is `/home/geoff/.hermes/cache/scratch/stocks-user-review-cba5015`.

For separate real-backend/read-only synthetic-database rehearsal, follow `docs/sync-reliability-operator-notes.md` from an isolated worktree without dotenv files. Never substitute a production database or startup command.
