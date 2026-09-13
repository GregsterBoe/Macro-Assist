# Archived numeric-baseline runs

`../numeric_baseline.json` and `../numeric_baseline.md` are the **latest** run —
the workflow overwrites them every time. Runs worth keeping re-analysable are
copied here, one self-contained folder per run, with the per-call
`scores.json.gz` the CI artifact carries but the workflow never commits.

| Folder | Work package | KB entry | Actions run | Notes |
|---|---|---|---|---|
| `2026-09-07-wp19e-spf/` | WP-19.E — SPF anchor | KB-026 | `34104184917` | `.json`/`.md` restored from `output` `2780cb4`. **`scores.json.gz` still missing** — artifact `10013945071`, expires 2026-10-07. |
| `2026-09-07-wp21e-vixterm/` | WP-21.E family 1 — VIX term structure | KB-027 | `34150561527` | Complete. The `.md` shows the pre-correction `edge` verdict for `vix_term`; KB-027 carries both columns. |
