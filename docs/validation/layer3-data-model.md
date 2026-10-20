# Layer 3 data-model expansion (extraction v4 / schema v3)

Review of `main` Phase 2 (extraction v3), then the v4 extract. No 100-point score. No UI changes.

## Already satisfied on main

- CIK identity; HEI / HEI-A share one issuer file
- Manual Add to Layer 3 + versioned localStorage
- Lazy `layer3/cik/{cik}.json` (index is 881 bytes)
- Company Facts / bulk ZIP; no browser SEC calls
- YTD → standalone Q, Q4 = FY − 9M, TTM from four non-overlapping quarters
- Missing stays `null` (never 0)
- CF/BS labeled `company_facts_only`, never `statement_verified`
- Financial SIC → `modelApplicability: not_applicable`
- Scoring remains `not_implemented`
- Layer 1 / Layer 2 artifacts are only copied, not recomputed

## Changed in this PR

| Area | Before (v3) | After (v4) |
|---|---|---|
| Flow depth | 8Q + TTM for OCF/CapEx/opinc/interest/D&A; FCF/EBITDA TTM only | Same 8Q + current/prior TTM + TTM YoY; **FCF and EBITDA also have 8 derived quarters** |
| New flows | — | Revenue, Net Income, Gross Profit, Cost of Revenue (Company Facts) |
| Margins / conversion | — | Gross / operating / net / FCF margin; cash conversion |
| Balance sheet | Latest aligned snapshot only | **8 aligned quarter-ends + latest**; stale dates are not back-filled |
| New stocks | — | AR, Inventory, AP, Current Assets, Current Liabilities |
| Working capital | — | AR/Inv/AP YoY, current ratio, OWC, DSO, DIO, DPO, CCC |
| Provenance | concept, period, accn, url, verification | Plus `calculationMethod` (`extracted` \| `derived`) separate from verification |
| Versions | schema 2 / extract 3 | schema 3 / extract 4; issuer files add `schemaVersion`, `dataAsOf` |

Existing `metrics.ocf` / `capex` / `fcf` / `cash` / … keys are unchanged. New fields are additive. Old v3 issuer files still parse.

## Compact facts store

Unchanged. It still holds revenue + earnings only. Layer 3 continues to need raw `companyfacts.zip` or a CIK facts directory. A missing source now **fails closed**: `write_layer3` raises `Layer3BuildError` and does not touch existing issuer JSON.

## Safe rebuild

`screener layer3` defaults to `--mode incremental`.

| Flag | Behavior |
|---|---|
| `--ciks` / `--limit` | Update only those issuers. Other `layer3/cik/*.json` files stay on disk. |
| Missing facts for one CIK | Keep the existing extracted file. Never replace it with `pending_analysis`. |
| No zip / facts dir / inline payload | Error. No writes. |
| `--mode full` | Write the complete tree into `--staging-dir` (or `<output>.staging`). Live dest is untouched until `--publish`. |
| `--publish` | Allowed only with `--mode full`. Validates that no live extracted issuer becomes `pending_analysis` or goes missing, copies live → `layer3.rollback-*`, then publishes. A failed publish restores the rollback. |
| `--write-live` | Required before incremental writes or publishes can target `web/public/data/layer3.json`. Refused by default. |

`reset_issuer_dir` refuses the live issuer directory. Production 5,542 v3 files are not rebuilt by this PR.

Sidecar sample (does not publish):

```bash
python pipeline/scripts/layer3_sidecar_sample.py --output /tmp/layer3-sidecar --report /tmp/layer3-sidecar-report.json
```

## Representative tests (no live SEC)

| Case | How covered |
|---|---|
| Software / no inventory | `test_software_without_inventory_is_not_applicable_not_zero` — inventory/DIO N/A, OWC = AR−AP, CCC = DSO−DPO |
| Aerospace / manufacturing | Identity GP + COGS = revenue; OWC = AR+Inv−AP |
| Non-December FY | October year-end; Q4 = FY−9M; cash aligned to 10-31 |
| Missing inventory / AP / CA | `test_working_capital_ratios_do_not_treat_missing_as_zero` |
| Concept conflict | Wrong `CostOfGoodsAndServicesSold` is ignored; `CostOfRevenue` kept |
| Conflicting reported GP + COGS | Both tagged series kept; COGS is **not** replaced with Revenue − GP |
| 52/53-week BS dates | `history_on_end` matches instants within ±10 days (NVDA 07-26 vs 07-31) |
| Incremental / `--ciks` | Other extracted issuer files are not deleted |
| Missing source | `Layer3BuildError`; existing JSON preserved |
| Full publish | Staging + validate + rollback; extracted → `pending_analysis` blocked |
| Share classes | Build test: HEI + HEI-A → one CIK file |
| Financial SIC | JPM / 6021 still `not_applicable`; metrics still extracted |
| Restatement / YTD | Existing YTD derivation + restatement rules reused |

Pipeline tests cover the v4 extract plus rebuild-safety cases. Web tests are unchanged.

## Coverage

Full-universe percents need `screener layer3 --use-cached-facts` after `companyfacts.zip` is present. The index then includes `counts.metrics.<name>.{extracted,missing,notApplicable}`.

This environment has no zip and no `SEC_USER_AGENT`, so the committed 5,542 v3 issuer files were **not** regenerated. A live HEI/MSFT/NVDA v3-vs-v4 sidecar extract is **blocked** until those sources are available.

Synthetic complete manufacturer (unit-test fixture): revenue, GP, COGS, NI, OCF, CapEx, FCF, EBITDA, cash, AR, inventory, AP, CA, CL, current ratio, OWC, DSO/DIO/DPO/CCC all `extracted`.

## Payload size (static deploy)

| Artifact | v3 (committed) | v4 estimate |
|---|---|---|
| `layer3.json` index | 881 B | still an index; plus metric coverage counts (~2–3 KB) |
| Issuer file median | 17 KB | ~45–75 KB if history is populated |
| Dense sample issuer | HEI 21 KB | 74 KB synthetic (3.6×) |
| Full-universe on disk | 75 MB | ~250–400 MB if every CIK is rebuilt |
| Browser download | only saved CIKs | unchanged policy; 20 issuers ≈ 1–1.5 MB |

GitHub Pages still does not fetch the universe. A typical curated list stays small.

## Risks and limits

1. **Layer 3 revenue / NI are Company Facts only.** Layer 1 `layer1` copy remains the statement-verified TTM. Do not treat Layer 3 `metrics.revenue` as face-checked.
2. **Gross Profit is not statement-verified** in this PR (no extra income-statement HTML pass).
3. **CF/BS/AR/inventory/AP/CA/CL stay `company_facts_only`.** No new statement HTML.
4. **GP/COGS identity** uses TTM agreement (`values_agree`). A tag that foots on TTM but not every quarter can still be selected.
5. **Inventory `not_applicable`** means the us-gaap inventory tags are absent. A manufacturer that simply failed to tag inventory looks the same as a software issuer.
6. **DSO/DIO/DPO** use TTM average of the year-ago and latest aligned balances × actual days in the TTM window. Not a quarterly CCC series.
7. **Fiscal labels:** compare companies by `end` / `dataAsOf`, not by “Q3”.
8. **Old v3 files** on Pages keep working; they omit the new keys until the next Layer 3 rebuild with a facts zip.

## Compatibility

- Readers that only use `metrics.ocf.ttm`, `metrics.fcf.ttm`, `metrics.cash.value` need no change.
- `verification: derived` is still emitted on FCF/EBITDA/totalDebt/netDebt so the current detail pane copy stays correct. New code also sets `calculationMethod: derived`.
- `schemaVersion` 2 files are readable as a subset of schema 3.

## Proposed `refresh.yml` Layer 3 step (not enabled)

`refresh.yml` already downloads `companyfacts.zip` into `pipeline/.cache/sec/bulk` and builds Layer 1 compact facts. It does **not** run `screener layer3`. Do not turn this on until a full-universe rebuild is approved.

Recommended add-on after the existing Build step, still without Pages publish:

```yaml
- name: Layer 3 staging refresh (does not publish)
  if: steps.build.outputs.exit_code == '0'
  env:
    SEC_USER_AGENT: ${{ secrets.SEC_USER_AGENT }}
  run: |
    screener layer3 \
      --data-dir "$SCREENER_OUTPUT_DIR" \
      --output "$SCREENER_OUTPUT_DIR/layer3.json" \
      --use-cached-facts \
      --mode full \
      --staging-dir "$SCREENER_OUTPUT_DIR/layer3.staging"
    echo "Layer 3 staging written. Live web/public/data/layer3 was not updated."
```

Notes:

- Reuse the zip the Build step already downloaded (`--use-cached-facts`). Do not download it again.
- Default dest under `$SCREENER_OUTPUT_DIR` is the workflow cache, not `web/public/data`. That is a sidecar as long as `--write-live` is omitted.
- Incremental quarterly updates later: `screener layer3 --use-cached-facts --mode incremental --write-live` only after review, and only for CIKs whose new 10-Q/10-K is in the zip.
- A production cut-over is a separate `--mode full --publish --write-live` against `web/public/data/layer3.json` after staging validation. That step is **not** in the workflow yet.
- Layer 1 / Layer 2 commands stay unchanged.
