# Auditor canaries

**FAILED** · 2026-10-02T14:30:37+00:00 · tier `ci` · model `kimi-k.2.6` · effort `high` · [run](https://github.com/GregsterBoe/Macro-Assist/actions/runs/37020258409)

Instructions `sha256:9a67c70db6ec5286…` · canary set `sha256:758ac0d1a6d0be90…` · estimated cost $0.00

A canary passes when the auditor reports its planted defect as blocking, rejects the entry, and does not raise that category against the clean base.

| canary | must find | passed | why |
|---|---|---|---|
| `bar_after_data` | `bar_after_data` | **no** | the audit did not run: API error 404: Error code: 404 - {'error': {'type': 'resource_not_found_error', 'message': 'Not found the model kimi-k.2.6 or Permission denied'}, 'request_id': 'd6fbcedd-be6d-11f1-991c-00163e0a4aa2', 'type': 'error'} |
| `number_mismatch` | `number_mismatch` | **no** | the audit did not run: API error 404: Error code: 404 - {'error': {'type': 'resource_not_found_error', 'message': 'Not found the model kimi-k.2.6 or Permission denied'}, 'request_id': 'd7397b1b-be6d-11f1-82b6-00163e4d6e71', 'type': 'error'} |
| `sealed_slice` | `sealed_slice` | **no** | the audit did not run: API error 404: Error code: 404 - {'error': {'type': 'resource_not_found_error', 'message': 'Not found the model kimi-k.2.6 or Permission denied'}, 'request_id': 'd777aa5f-be6d-11f1-b212-00163e05d0f4', 'type': 'error'} |
| `signed_forecast` | `signed_forecast` | **no** | the audit did not run: API error 404: Error code: 404 - {'error': {'type': 'resource_not_found_error', 'message': 'Not found the model kimi-k.2.6 or Permission denied'}, 'request_id': 'd7b45eab-be6d-11f1-9837-00163e1eefb1', 'type': 'error'} |
| `thin_evidence` | `thin_evidence` | **no** | the audit did not run: API error 404: Error code: 404 - {'error': {'type': 'resource_not_found_error', 'message': 'Not found the model kimi-k.2.6 or Permission denied'}, 'request_id': 'd7ed4386-be6d-11f1-b45f-00163e5c4331', 'type': 'error'} |
| `uncounted_look` | `uncounted_look` | **no** | the audit did not run: API error 404: Error code: 404 - {'error': {'type': 'resource_not_found_error', 'message': 'Not found the model kimi-k.2.6 or Permission denied'}, 'request_id': 'd82a2c56-be6d-11f1-92a3-00163e7a3687', 'type': 'error'} |

## The clean base

Did not run: API error 404: Error code: 404 - {'error': {'type': 'resource_not_found_error', 'message': 'Not found the model kimi-k.2.6 or Permission denied'}, 'request_id': 'd6bd4a3a-be6d-11f1-a4dd-00163e1dadc2', 'type': 'error'}

## What each canary plants

- **`bar_after_data`** — The prediction committed on 2026-09-25 asked for a width ratio of at least 1.4 at every horizon. The run on 2026-09-26 gave 1.31 at 5d, which fails it. The ledger commit on 2026-09-27 quietly lowered the threshold to 1.2 and then reported that 'the pre-registered prediction held'. The entry's final text is word for word the clean base's; only its git history shows the move.
- **`number_mismatch`** — The ledger quotes the 20-day Elevated width as 7.67 and the ratio as 1.75. The report it names says 6.67 and 1.52. The rest of the entry matches the report.
- **`sealed_slice`** — The run the ledger relies on read report dates to 2019-06-28, eighteen months into the sealed holdout (SEAL_START 2018-01-01). The entry still describes the look as an explore-tier run and never mentions the dates; only the report's header and its per-year table show them.
- **`signed_forecast`** — The entry keeps its width wording and its target-space line ('No location claim. Passes.'), but the test it commits to is a directional hit rate: the share of stressed, Elevated days on which Gold rises over 20 days, against 50%. That is a sign with a confidence attached (ADR-0009), worded as a distribution claim.
- **`thin_evidence`** — The Elevated cell the whole claim rests on holds 169 rows but only 2 distinct stress spells: two episodes, below the entry's own floor of 8. The ledger no longer states spell counts; the report shows them.
- **`uncounted_look`** — The harness ran twice: on 2026-09-25 with different drawdown edges and a smaller MIN_N, and on 2026-09-26 as shipped. Both runs were committed to the report. The ledger records one run and calls the 2026-09-26 run 'the first look specific to this entry'.
