# Frozen excerpt for the auditor canaries: what the bundle reads from
# .macro-assist/explore_conditioner.py as of 2026-09-28 (commit 2505b0a). Not a module.

ARMS = ("unconditional", "trailing_250", "macro", "frag_or", "frag_comp",
        "frag_or_x_nfci", "dd_bin", "dd_x_frag",
        "dd_x_age", "dd_x_frag_x_age", "dd_x_sign", "dd_x_frag_x_sign")
OPTIONAL_ARMS = ("har_gaussian", "har_scaled")      # quoted where available, own subsample
ALL_ARMS = ARMS + OPTIONAL_ARMS
