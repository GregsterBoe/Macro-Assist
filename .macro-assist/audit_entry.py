"""
audit_entry.py — the independent auditor of a register entry (ADR-0022, WP-25.A).

Whoever proposes a hypothesis never judges it (how-we-explore §6). This is the
judge, built so that the proposer has no hand in what it reads or what it
returns. Three parts, kept apart on purpose:

  bundle    What the auditor reads, assembled by code from the committed
            record: the rules page, facts read from code, the entry, the
            entry's git history, the commit list and latest committed content
            of every report the entry names, and the Knowledge Base entries and
            work packages it cites. Never the proposer's conversation, and never
            its summary of its own case. `--bundle-only` prints it, for free.
  auditor   One fresh-context model call. `auditor/instructions.md` is the
            system prompt, and the answer is held to a JSON schema: findings in
            a fixed vocabulary, an answer status for questions 1–11 of §9, and
            the owner's brief with the case against first. **It returns no
            verdict.**
  verdict   Derived here, by code: reject on any blocking finding, or on any of
            questions 1–11 the entry's own text does not answer. An audit that
            did not complete (an API error, a refusal, a truncated or malformed
            answer) is not a pass either. There is no path by which the model's
            prose becomes an approval.

The canaries (`auditor/canaries/`) test the judge. They are a clean fictional
entry (`base/`) and variants of it, each with one planted defect, written as
edits on the base so that the defect is exactly the diff. Each variant is
replayed into a throwaway git repository — `main` for the register, an orphan
`output` for the report, every commit carrying its planted date — and bundled
by the same code that bundles a real entry. The auditor cannot tell a canary
from a real entry by its format.

**What a canary tests.** A canary passes when the auditor reports its planted
defect as blocking **and does not report that category as blocking on the clean
base**. The second half is what an auditor that rejects everything fails:
rejecting is easy; rejecting for the right reason is the test. The clean base's
own verdict is recorded and not graded, because a fictional entry built to be
approvable would be a target to tune the auditor against.

Where a record may be used (ADR-0022, *Scaled to what is at stake*). A run on a
laptop is a *local* audit: good enough for an explore look, never for a
promotion. Every record carries `tier`, but that field is a label; what makes
an audit a promotion-tier one is that CI ran it and CI committed its record.
The proposer running this and relaying the answer is exactly what question 12
does not accept.

The promotion tier (WP-25.C) is `--ci`, run by `audit_entry.yml`. Before any
API call it refuses: outside CI or off main; on a shallow clone, whose bundle
would say the history is unavailable; with a model, effort, instructions or
canary set that no passing CI canary suite certifies; on text CI has already
audited, which would be a retry and not a resubmission; and after two
rejections, unless the owner's decision is pinned (*No grinding*). `--dry-run`
runs all of that and builds the bundle, for free. After CI publishes the record,
`--sync-field` writes the entry's `Audit record` field from CI's records, and
`record_audit.py` holds the field to them — so whoever commits it, nobody
authors it.

Spends API money (ANTHROPIC_API_KEY, or the external provider's key — see
PROVIDERS), except under --bundle-only and --check-canaries. The canary suite is seven calls, and `--max-usd` stops it
before a runaway.

Run:
    python .macro-assist/audit_entry.py H-008 --bundle-only       # what the auditor would read
    python .macro-assist/audit_entry.py --bundle-only --canary thin_evidence
    python .macro-assist/audit_entry.py --check-canaries          # replay every canary, no API call
    python .macro-assist/audit_entry.py H-008                     # a local audit (costs money)
    python .macro-assist/audit_entry.py --canaries                # the suite; exit 1 unless every canary passes
    python .macro-assist/audit_entry.py --canaries --model kimi-k2.6   # the same suite on an external model
    python .macro-assist/audit_entry.py H-008 --ci [--dry-run]    # the promotion tier; audit_entry.yml runs it
    python .macro-assist/audit_entry.py --sync-field              # Audit record fields from CI's records; free
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import decision_packet as dp
import record_audit as ra

MODULE_DIR = Path(".macro-assist")
AUDITOR_DIR = MODULE_DIR / "auditor"
INSTRUCTIONS = AUDITOR_DIR / "instructions.md"
CANARY_DIR = AUDITOR_DIR / "canaries"
BASE = "base"
KNOWLEDGE_BASE = ra.RECORD_DIR / "knowledge-base.md"
ROADMAP = ra.RECORD_DIR / "roadmap.md"
SEAL_SOURCE = MODULE_DIR / "numeric_baseline.py"
OUTPUT_BRANCH = "output"
RESULTS = "results/"
AUDIT_OUT = Path("results") / "audit"

DEFAULT_MODEL = "claude-opus-5-5"
DEFAULT_EFFORT = "high"
MAX_TOKENS = 64000
REPORT_CAP = 120_000        # bytes; a bigger or binary report is listed, not inlined, and the bundle says so
DEFAULT_MAX_USD = 5.0

ANSWERED = tuple(range(1, 12))   # §9 question 12 is this audit; the auditor does not answer it

# The finding vocabulary. `auditor/instructions.md` defines each one for the
# model; the schema below holds it to exactly this list, and every canary's
# expected finding is one of them.
CATEGORIES: tuple[str, ...] = (
    "bar_after_data", "signed_forecast", "sealed_slice", "thin_evidence",
    "uncounted_look", "number_mismatch", "confound_unaddressed",
    "weak_mechanism_clause", "overstated_claim", "ambiguous_term",
    "bar_missing", "other",
)
STATUSES = ("answered", "unanswered", "fails")

# $/MTok (input, output, cache read), for the record and the spend guard — an
# estimate, not a bill. Cache writes (5-minute) are 1.25× input on every model;
# reads are not a fixed fraction, so they are listed.
PRICES: dict[str, tuple[float, float, float]] = {
    "claude-opus-5-5": (4.0, 20.0, 0.20),
    "claude-opus-5": (5.0, 25.0, 0.50),
    "claude-sonnet-5-5": (2.0, 10.0, 0.20),
    "claude-sonnet-5": (2.0, 10.0, 0.20),
    "claude-fable-5-1": (10.0, 50.0, 0.25),
    "claude-opus-4-8": (5.0, 25.0, 0.50),       # the note's main model today (model_compare)
    "claude-haiku-4-5": (1.0, 5.0, 0.10),
    # Moonshot's list prices for K2.5, carried to K2.6 until checked against
    # platform.moonshot.ai — the spend guard needs a number, and an unknown
    # price would let a suite run unguarded.
    "kimi-k2.6": (0.60, 3.00, 0.10),
    "kimi-k2.5": (0.60, 3.00, 0.10),
}



# Where a model id is sent. The auditor's call is the Anthropic Messages API;
# an external provider is reached through its Anthropic-compatible endpoint, so
# the request, the stream and the record are one code path. The model id alone
# picks the provider, so the certified configuration (model, effort,
# instructions, canary set) needs no fifth field, and a canary pass on Kimi
# certifies Kimi and nothing else.
#
# A non-native endpoint does not promise the three things the native call leans
# on — schema-constrained output, `effort`, adaptive thinking — so for one:
# the schema goes into the system prompt and `parse_answer` holds the answer to
# it (it always did); `effort` becomes a thinking budget (`low` turns thinking
# off); and a fenced JSON answer is unwrapped, nothing more lenient.
@dataclass(frozen=True)
class Provider:
    name: str
    prefixes: tuple[str, ...]       # a model id starting with one of these goes here
    key_env: tuple[str, ...]        # the first one set is the key
    base_url_env: str | None = None
    base_url: str | None = None     # None = the SDK's default (Anthropic)
    native: bool = True             # the Anthropic API itself


ANTHROPIC = Provider("anthropic", ("claude-",), ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"))
PROVIDERS: tuple[Provider, ...] = (
    ANTHROPIC,
    # Kimi (Moonshot AI). The same endpoint and key kimi_arm.py uses.
    Provider("moonshot", ("kimi-", "moonshot-"), ("MOONSHOT_API_KEY", "KIMI_API_KEY"),
             base_url_env="KIMI_BASE_URL", base_url="https://api.moonshot.ai/anthropic",
             native=False),
)

# `effort` on a non-native endpoint: a thinking budget in tokens, under MAX_TOKENS.
THINKING_BUDGET = {"low": 0, "medium": 8_000, "high": 16_000, "xhigh": 32_000, "max": 48_000}


def provider_for(model: str) -> Provider:
    """The provider a model id goes to. An id no provider claims is the
    Anthropic API's, which answers for itself whether it knows the model."""
    return next((p for p in PROVIDERS if model.startswith(p.prefixes)), ANTHROPIC)


_STRING = {"type": "string"}
RESPONSE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "findings": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "enum": list(CATEGORIES)},
                "blocking": {"type": "boolean"},
                "questions": {"type": "array", "items": {"type": "integer"}},
                "claim": _STRING,
                "evidence": _STRING,
            },
            "required": ["category", "blocking", "questions", "claim", "evidence"],
            "additionalProperties": False,
        }},
        "questions": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "number": {"type": "integer"},
                "status": {"type": "string", "enum": list(STATUSES)},
                "note": _STRING,
            },
            "required": ["number", "status", "note"],
            "additionalProperties": False,
        }},
        "brief": {
            "type": "object",
            "properties": {
                "case_against": _STRING,
                "what_it_claims": _STRING,
                "what_would_change_it": _STRING,
            },
            "required": ["case_against", "what_it_claims", "what_would_change_it"],
            "additionalProperties": False,
        },
    },
    "required": ["findings", "questions", "brief"],
    "additionalProperties": False,
}

_SEAL_RE = re.compile(r"^SEAL_START: date = date\((\d{4}), (\d{1,2}), (\d{1,2})\)", re.M)
_H2_RE = re.compile(r"^## ", re.M)
_WP_HEAD_RE = re.compile(r"^#{2,3} ", re.M)
_TICKS_RE = re.compile(r"`+")


class BundleError(RuntimeError):
    """The bundle cannot be assembled honestly — say so rather than send less."""


class AuditNotRun(RuntimeError):
    """The model call did not produce a complete answer. Never a pass."""


class InvalidAudit(ValueError):
    """The answer came back but does not hold to the contract. Never a pass."""


class CanaryError(ValueError):
    """A canary does not plant what it says it plants."""


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _git_bytes(root: Path, *args: str) -> bytes | None:
    try:
        r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=False)
    except OSError:
        return None
    return r.stdout if r.returncode == 0 else None


def _fence(text: str, lang: str = "") -> list[str]:
    """Fence `text` with more backticks than it contains, so a report's own
    code blocks cannot close the fence early."""
    longest = max((len(m) for m in _TICKS_RE.findall(text)), default=0)
    ticks = "`" * max(5, longest + 1)
    return [f"{ticks}{lang}", text.rstrip("\n"), ticks]


# ---------------------------------------------------------------------------
# the bundle
# ---------------------------------------------------------------------------

@dataclass
class Bundle:
    hid: str
    fingerprint: str        # sha256 of dp.stamped_text(entry) — what an approval is stamped to
    rules: str              # how-we-explore.md as it reads; the system prompt's second block
    material: str           # everything specific to this entry; the user message
    sources: dict[str, str]  # where each part was read from, for the record

    @property
    def sha256(self) -> str:
        return _sha(self.rules + "\0" + self.material)


entry_text = dp.entry_text


def seal_start(root: Path) -> str | None:
    path = root / SEAL_SOURCE
    if not path.is_file():
        return None
    m = _SEAL_RE.search(path.read_text(encoding="utf-8"))
    return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else None


def _shallow(root: Path) -> bool:
    return ra._git(root, "rev-parse", "--is-shallow-repository") == "true"


def entry_history(root: Path, hid: str) -> str:
    """`git log -L` over the entry's line range: every commit that changed it,
    with its commit date and diff."""
    out = ra._git(root, "log", "--no-color", "--format=COMMIT %h  %cI  %s",
                  "-L", f"/^## {hid} /,/^## /:{dp.HYPOTHESES.as_posix()}", "HEAD")
    if out is None:
        return ""
    return out


@dataclass
class ReportView:
    path: str              # as the entry names it, `results/...`
    commits: list[str]     # "sha  date  subject", newest first
    content: str | None    # the latest committed version, if it can be inlined
    note: str              # what the bundle says about it


def report_views(root: Path, entry: str) -> tuple[str | None, list[ReportView]]:
    ref = ra._resolve_ref(root, OUTPUT_BRANCH)
    views: list[ReportView] = []
    for path in sorted(set(dp._REPORT_RE.findall(entry))):
        rel = path[len(RESULTS):] if path.startswith(RESULTS) else path
        if ref is None:
            views.append(ReportView(path, [], None,
                                    f"No `{OUTPUT_BRANCH}` branch is reachable here, so nothing the entry "
                                    "names under results/ could be read."))
            continue
        log = ra._git(root, "log", "--format=%h  %cI  %s", ref, "--", rel) or ""
        commits = [ln for ln in log.splitlines() if ln.strip()]
        kind = ra._git(root, "cat-file", "-t", f"{ref}:{rel}")
        if kind != "blob":
            views.append(ReportView(path, commits, None,
                                    "Not a single committed file on the output branch"
                                    + (" (a directory)." if kind == "tree" else " — no commit holds it.")))
            continue
        raw = _git_bytes(root, "show", f"{ref}:{rel}") or b""
        local = root / path
        if not local.is_file():
            where = "There is no local copy under results/."
        elif local.read_bytes() == raw:
            where = "The local copy under results/ matches the latest committed version."
        else:
            where = ("The local copy under results/ DIFFERS from the latest committed version: "
                     "a run whose report was never committed.")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            views.append(ReportView(path, commits, None, f"{where} Binary; not inlined."))
            continue
        if len(raw) > REPORT_CAP:
            views.append(ReportView(path, commits, None,
                                    f"{where} {len(raw):,} bytes, over the {REPORT_CAP:,}-byte cap; "
                                    "not inlined."))
            continue
        views.append(ReportView(path, commits, text, where))
    return ref, views


def _sections(text: str, heading_re: str, stop: re.Pattern) -> str | None:
    m = re.search(heading_re, text, re.M)
    if m is None:
        return None
    nxt = stop.search(text, m.end())
    return text[m.start(): nxt.start() if nxt else len(text)].rstrip() + "\n"


def cited_kb(root: Path, entry: str) -> dict[str, str | None]:
    path = root / KNOWLEDGE_BASE
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    return {f"KB-{n}": _sections(text, rf"^## KB-{n} — .*$", _H2_RE)
            for n in sorted(set(ra._KB_RE.findall(entry)))}


def cited_wps(root: Path, entry: str) -> dict[str, str | None]:
    path = root / ROADMAP
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    return {f"WP-{w}": _sections(text, rf"^#{{2,3}} WP-{re.escape(w)}\b.*$", _WP_HEAD_RE)
            for w in sorted(set(ra._WP_RE.findall(entry)))}


CLASS_BARS = MODULE_DIR / "class_bars.py"


def class_bar_section(root: Path, entry: str) -> list[str]:
    """What a sealed read would apply to the entry, when it states a
    pre-registration (WP-23.B): the pre-registration as the class bar reads it,
    and the bar itself — code, so the auditor checks questions 7 and 8 against
    the bar that will be applied, not a description of it. Nothing for an entry
    without the field: the seal key refuses it, which code settles, and the
    certified canary bundles stay what they were."""
    if dp.field_block(entry, "Pre-registration") is None:
        return []
    import class_bars as cb
    path = root / CLASS_BARS
    if not path.is_file():
        raise BundleError(f"the entry states a pre-registration and {CLASS_BARS} is not here")
    out = ["### The class bar its `Pre-registration` names", ""]
    try:
        spec = cb.parse_preregistration(entry)
    except cb.PreregError as e:
        return out + [f"**It does not parse:** {e}. The seal key refuses a sealed read until it "
                      "does; code checks that, not this audit.", ""]
    return out + [
        "As `class_bars.validate` normalises it — the class floor filled in where the entry "
        "states none:", "", *_fence(json.dumps(spec, indent=2, ensure_ascii=False), "json"), "",
        "The class bar, as `class_bars.describe` prints it:", "",
        *_fence(cb.describe(cb.BARS[spec["class"]])), "",
        f"The bar is code. `{CLASS_BARS.as_posix()}` as this checkout holds it — the verdict order, "
        "the pass clause and each clause kind are defined here and nowhere else:", "",
        *_fence(path.read_text(encoding="utf-8"), "python"), "",
    ]


def build_bundle(root: Path, hid: str, *, now: datetime | None = None) -> Bundle:
    """The auditor's whole world for one entry. Raises BundleError rather than
    sending a short bundle: an auditor that approves what it was not shown is
    the failure this exists to prevent."""
    now = now or datetime.now(timezone.utc)
    reg_path, rules_path = root / dp.HYPOTHESES, root / dp.HOW_WE_EXPLORE
    for p in (reg_path, rules_path):
        if not p.is_file():
            raise BundleError(f"not found: {p}")
    try:
        entry = entry_text(reg_path.read_text(encoding="utf-8"), hid)
    except KeyError:
        raise BundleError(f"{hid} is not in {dp.HYPOTHESES}") from None
    rules = rules_path.read_text(encoding="utf-8")
    questions = dp.parse_questions(rules)
    if [q.number for q in questions] != list(range(1, 13)):
        raise BundleError("how-we-explore §9 did not parse as twelve questions; "
                          "the audit is held to the page, so it does not run on a guess")
    seal = seal_start(root)
    if seal is None:
        raise BundleError(f"SEAL_START could not be read from {SEAL_SOURCE}")

    arms = dp.harness_arms(root)
    head = ra._git(root, "log", "-1", "--format=%h  %cI", "HEAD") or "(no commit)"
    dirty = bool(ra._git(root, "status", "--porcelain", "--", dp.HYPOTHESES.as_posix()))
    shallow = _shallow(root)
    history = "" if shallow else entry_history(root, hid)
    ref, views = report_views(root, entry)
    kb, wps = cited_kb(root, entry), cited_wps(root, entry)
    fingerprint = _sha(dp.stamped_text(entry))

    register_line = f"- **The register** was read at `HEAD` {head}"
    if dirty:
        register_line += (". It has uncommitted changes, so the entry below is the working-tree "
                          "text and its latest change is not in the history in §3")
    out: list[str] = [
        f"# Audit bundle — {hid}",
        "",
        f"Assembled {now:%Y-%m-%d %H:%M} UTC by `audit_entry.py` from the committed record. "
        "Nothing in it was written for this audit.",
        "",
        "## 1. Facts from code",
        "",
        f"- **Seal date** (`numeric_baseline.SEAL_START`): {seal}. Report dates on or after it "
        "are the sealed holdout; the explore slice ends the day before.",
        (f"- **Explore harness arm vocabulary** ({len(arms)}, `explore_conditioner.py` `ARMS` + "
         f"`OPTIONAL_ARMS`): {', '.join(f'`{a}`' for a in arms)}."
         + (f" `unconditional` is the reference the others are scored against, so a report's "
            f"multiplicity line counts {len(arms) - 1} arms." if "unconditional" in arms else "")
         if arms else "- **Explore harness arm vocabulary:** could not be read."),
        register_line + ".",
        (f"- **Reports** were read from `{ref}`"
         + (" in a shallow clone, so their commit lists may be cut short." if shallow else ".")
         if ref else f"- **Reports:** no `{OUTPUT_BRANCH}` branch is reachable."),
        f"- **Entry fingerprint:** `sha256:{fingerprint}`, over the text in §2 less its Status "
        "line and any Audit record, which a promotion writes itself (`decision_packet.stamped_text`).",
        "",
        "## 2. The entry under audit",
        "",
        *_fence(entry, "markdown"),
        "",
        *class_bar_section(root, entry),
        "## 3. The entry's history",
        "",
    ]
    if shallow:
        out.append("**Unavailable: this is a shallow clone, so git holds no history for the "
                   "entry.** Nothing in this bundle shows when any part of the entry was written.")
    elif not history:
        out.append("**Unavailable: `git log -L` found no history for the entry's line range.** "
                   "Nothing in this bundle shows when any part of the entry was written.")
    else:
        out += ["Every commit that changed the entry, newest first, from `git log -L` on "
                f"`{dp.HYPOTHESES.as_posix()}`. Dates are commit dates.", "", *_fence(history, "diff")]
    out += ["", "## 4. Reports the entry names", ""]
    if not views:
        out.append("The entry names no report under results/.")
    for v in views:
        out += [f"### `{v.path}`", ""]
        if v.commits:
            out.append(f"Commits that touched it on `{OUTPUT_BRANCH}`, newest first:")
            out += [f"- `{c}`" for c in v.commits]
        elif ref:
            out.append(f"No commit on `{OUTPUT_BRANCH}` touched it.")
        out += ["", v.note, ""]
        if v.content is not None:
            out += ["Latest committed content:", "", *_fence(v.content, "markdown"), ""]
    for title, found, source in (
        ("## 5. Knowledge Base entries the entry cites", kb, KNOWLEDGE_BASE),
        ("## 6. Work packages the entry cites", wps, ROADMAP),
    ):
        out += [title, ""]
        if not found:
            out += ["None.", ""]
        for key, text in found.items():
            out += [f"### {key}", ""]
            out += (_fence(text, "markdown") if text is not None
                    else [f"Not found in `{source.as_posix()}`."])
            out.append("")
    out += [
        "## 7. What to return",
        "",
        "Report your findings, answer questions 1–11 of §9 against the entry in §2, and write the "
        "owner's brief. Question 12 is this audit; do not answer it. The questions, as the page "
        "reads today:",
        "",
    ]
    out += [f"{q.number}. *({q.group})* {q.text}" for q in questions]
    material = "\n".join(out).rstrip() + "\n"
    sources = {
        "register": f"HEAD {head}" + (" + uncommitted" if dirty else ""),
        "reports": ref or "(none)",
        "shallow": str(shallow).lower(),
    }
    return Bundle(hid, fingerprint, rules, material, sources)


# ---------------------------------------------------------------------------
# the auditor: one fresh-context call
# ---------------------------------------------------------------------------

def read_instructions(root: Path) -> str:
    return (root / INSTRUCTIONS).read_text(encoding="utf-8")


def call_auditor(bundle: Bundle, instructions: str, *, client, model: str,
                 effort: str) -> tuple[dict, dict]:
    """(answer, metadata). No conversation, no tools, no memory: the system
    prompt, the rules page and the bundle. The rules block is cached — it is
    the same for every entry — and nothing volatile sits before it."""
    import anthropic

    provider = provider_for(model)
    system = [
        {"type": "text", "text": instructions if provider.native
         else instructions + "\n\n" + external_format_note()},
        {"type": "text", "text": "# The rules: How we explore\n\n" + bundle.rules,
         "cache_control": {"type": "ephemeral"}},
    ]
    if provider.native:
        options = {"thinking": {"type": "adaptive"},
                   "output_config": {"effort": effort,
                                     "format": {"type": "json_schema", "schema": RESPONSE_SCHEMA}}}
    else:
        budget = THINKING_BUDGET[effort]
        options = {"thinking": ({"type": "enabled", "budget_tokens": budget} if budget
                                else {"type": "disabled"})}
    try:
        with client.messages.stream(
            model=model,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": bundle.material}],
            **options,
        ) as stream:
            msg = stream.get_final_message()
    except anthropic.APIConnectionError as e:
        raise AuditNotRun(f"could not reach the API: {e}") from e
    except anthropic.APIStatusError as e:
        raise AuditNotRun(f"API error {e.status_code}: {e.message}") from e

    if msg.stop_reason != "end_turn":
        why = msg.stop_reason
        details = getattr(msg, "stop_details", None)
        if why == "refusal" and details is not None:
            why += f" ({getattr(details, 'category', None)})"
        raise AuditNotRun(f"the answer did not complete: stop_reason {why}")
    text = "".join(b.text for b in msg.content if b.type == "text")
    if not provider.native:
        text = _unfence(text)
    try:
        answer = json.loads(text)
    except json.JSONDecodeError as e:
        raise AuditNotRun(f"the answer is not JSON: {e}") from e
    u = msg.usage
    usage = {
        "input_tokens": u.input_tokens,
        "output_tokens": u.output_tokens,
        "cache_creation_input_tokens": getattr(u, "cache_creation_input_tokens", 0) or 0,
        "cache_read_input_tokens": getattr(u, "cache_read_input_tokens", 0) or 0,
    }
    return answer, {"model": msg.model or model, "provider": provider.name,
                    "request_id": getattr(msg, "_request_id", None), "usage": usage}


def external_format_note() -> str:
    """What the API's schema enforcement says for itself on the native call,
    said in words to an endpoint that does not enforce it."""
    return ("# The answer's format\n\nAnswer with exactly one JSON object and nothing else — "
            "no prose before or after it, no code fence. It must validate against this JSON "
            "Schema:\n\n" + json.dumps(RESPONSE_SCHEMA, indent=1))


_FENCE_RE = re.compile(r"\A\s*```(?:json)?\s*\n(.*)\n\s*```\s*\Z", re.S)


def _unfence(text: str) -> str:
    """A whole answer wrapped in one code fence is the answer. Anything looser —
    JSON fished out of prose — is not: a malformed answer is not a pass."""
    m = _FENCE_RE.match(text)
    return m.group(1) if m else text


def estimate_usd(model: str, usage: dict) -> float | None:
    # exact name first, then the longest prefix — `claude-opus-5-5` also starts
    # with `claude-opus-5-`, and a dated snapshot starts with its family's name
    matches = [m for m in PRICES if model == m or model.startswith(m + "-")]
    if not matches:
        return None
    inp, out, read = PRICES[model if model in PRICES else max(matches, key=len)]
    return round((usage["input_tokens"] * inp
                  + usage["cache_creation_input_tokens"] * inp * 1.25
                  + usage["cache_read_input_tokens"] * read
                  + usage["output_tokens"] * out) / 1e6, 4)


# ---------------------------------------------------------------------------
# the verdict: code, not the model
# ---------------------------------------------------------------------------

@dataclass
class AuditResult:
    findings: list[dict]
    questions: dict[int, dict]
    brief: dict[str, str]


def parse_answer(answer: dict) -> AuditResult:
    """Hold the answer to its contract. The Anthropic API enforces the schema
    (an external endpoint does not, so this checks every field the record
    uses); it also checks what a schema cannot say — every question 1–11 exactly once —
    and anything a test's fake could get wrong."""
    if not isinstance(answer, dict):
        raise InvalidAudit("the answer is not an object")
    findings = answer.get("findings")
    if not isinstance(findings, list):
        raise InvalidAudit("no findings list")
    for f in findings:
        if not isinstance(f, dict) or f.get("category") not in CATEGORIES:
            raise InvalidAudit(f"a finding outside the vocabulary: {f!r}")
        if not isinstance(f.get("blocking"), bool):
            raise InvalidAudit(f"a finding with no blocking flag: {f!r}")
        if not (isinstance(f.get("claim"), str) and isinstance(f.get("evidence"), str)
                and isinstance(f.get("questions"), list)
                and all(isinstance(n, int) for n in f["questions"])):
            raise InvalidAudit(f"a finding missing its claim, evidence or questions: {f!r}")
    qs: dict[int, dict] = {}
    for q in answer.get("questions") or []:
        n = q.get("number") if isinstance(q, dict) else None
        if n == 12:
            continue          # the audit itself; not the auditor's to answer
        if n not in ANSWERED or n in qs:
            raise InvalidAudit(f"question {n!r} is not one of 1–11, or is answered twice")
        if q.get("status") not in STATUSES:
            raise InvalidAudit(f"question {n}: status {q.get('status')!r}")
        if not isinstance(q.get("note"), str):
            raise InvalidAudit(f"question {n}: no note")
        qs[n] = q
    missing = [n for n in ANSWERED if n not in qs]
    if missing:
        raise InvalidAudit(f"questions not answered at all: {missing}")
    brief = answer.get("brief")
    keys = ("case_against", "what_it_claims", "what_would_change_it")
    if not isinstance(brief, dict) or not all(isinstance(brief.get(k), str) and brief[k].strip()
                                              for k in keys):
        raise InvalidAudit("the owner's brief is missing a part")
    return AuditResult(findings, qs, {k: brief[k] for k in keys})


def derive_verdict(result: AuditResult) -> tuple[str, list[str]]:
    """`reject`, or `no_blocking_finding` — never `approve`: the auditor found
    nothing blocking, which is all an audit can say."""
    reasons = [f"blocking finding: {f['category']}" for f in result.findings if f["blocking"]]
    reasons += [f"question {n}: {result.questions[n]['status']}"
                for n in ANSWERED if result.questions[n]["status"] != "answered"]
    return ("reject" if reasons else "no_blocking_finding"), reasons


def blocking_categories(result: AuditResult) -> set[str]:
    return {f["category"] for f in result.findings if f["blocking"]}


def _tier() -> str:
    return "ci" if os.environ.get("GITHUB_ACTIONS") == "true" else "local"


def _run_url() -> str | None:
    """The CI run that made the record — only when the record is CI's, so a
    record never says `local` and links a run in the same breath."""
    env = os.environ
    if _tier() == "ci" and env.get("GITHUB_RUN_ID") and env.get("GITHUB_REPOSITORY"):
        return (f"{env.get('GITHUB_SERVER_URL', 'https://github.com')}/"
                f"{env['GITHUB_REPOSITORY']}/actions/runs/{env['GITHUB_RUN_ID']}")
    return None


def make_record(bundle: Bundle, result: AuditResult, meta: dict, *, requested_model: str,
                effort: str, instructions_sha: str, canary_set_sha: str | None = None,
                certified_by: str | None = None, now: datetime | None = None) -> dict:
    verdict, reasons = derive_verdict(result)
    return {
        "schema": 1,
        "hid": bundle.hid,
        "audited_at": (now or datetime.now(timezone.utc)).isoformat(timespec="seconds"),
        "entry_fingerprint": f"sha256:{bundle.fingerprint}",
        "bundle_sha256": bundle.sha256,
        "instructions_sha256": instructions_sha,
        "canary_set_sha256": canary_set_sha,
        "certified_by": certified_by,
        "tier": _tier(),
        "run": _run_url(),
        "sources": bundle.sources,
        "requested_model": requested_model,
        "provider": meta.get("provider", ANTHROPIC.name),
        "model": meta["model"],
        "effort": effort,
        "request_id": meta.get("request_id"),
        "usage": meta["usage"],
        "est_cost_usd": estimate_usd(meta["model"], meta["usage"]),
        "verdict": verdict,
        "reasons": reasons,
        "findings": result.findings,
        "questions": [result.questions[n] for n in ANSWERED],
        "brief": result.brief,
    }


def render_record(rec: dict) -> str:
    """The record as the owner reads it: the case against first."""
    b = rec["brief"]
    out = [
        f"# Audit — {rec['hid']}",
        "",
        f"**Verdict (derived by code):** `{rec['verdict']}` · tier `{rec['tier']}` · "
        f"model `{rec['model']}` · effort `{rec['effort']}`"
        + (f" · [run]({rec['run']})" if rec.get("run") else ""),
        "",
        f"Entry fingerprint `{rec['entry_fingerprint']}`. Any edit to the entry voids this record.",
        "",
    ]
    if rec["tier"] != "ci":
        out += ["**A local audit.** It can inform an explore look; it does not satisfy §9 "
                "question 12, which needs an audit CI ran and recorded.", ""]
    out += [
        "## The case against", "", b["case_against"], "",
        "## What the entry claims", "", b["what_it_claims"], "",
        "## What would change the verdict", "", b["what_would_change_it"], "",
        "## Why the verdict is what it is", "",
    ]
    out += [f"- {r}" for r in rec["reasons"]] or ["- nothing blocking was found"]
    out += ["", "## Findings", ""]
    if not rec["findings"]:
        out.append("None.")
    for f in rec["findings"]:
        qs = ", ".join(str(n) for n in f["questions"]) or "—"
        out += [f"- **`{f['category']}`** ({'blocking' if f['blocking'] else 'non-blocking'}; "
                f"questions {qs}): {f['claim']}", f"  - *Evidence:* {f['evidence']}"]
    out += ["", "## Questions 1–11", ""]
    out += [f"{q['number']}. `{q['status']}` — {q['note']}" for q in rec["questions"]]
    cost = rec.get("est_cost_usd")
    out += ["", f"*Estimated cost: {'$%.2f' % cost if cost is not None else 'unknown'}.*", ""]
    return "\n".join(out)


def audit(bundle: Bundle, instructions: str, *, client, model: str, effort: str,
          **provenance) -> dict:
    answer, meta = call_auditor(bundle, instructions, client=client, model=model, effort=effort)
    return make_record(bundle, parse_answer(answer), meta, requested_model=model,
                       effort=effort, instructions_sha=_sha(instructions), **provenance)


# ---------------------------------------------------------------------------
# the promotion-tier audit: CI runs it, CI records it (WP-25.C)
# ---------------------------------------------------------------------------

class Refused(RuntimeError):
    """A promotion-tier audit that must not run. Raised before any API call."""


@dataclass
class Preflight:
    hid: str
    status: str
    ref: str
    certified_by: str        # the passing canary suite behind this configuration
    canary_set_sha: str
    prior: list[dict]        # CI's earlier audits of the entry, oldest first
    history_commits: int


def preflight(root: Path, hid: str, *, model: str, effort: str) -> Preflight:
    """Everything that must hold before a promotion-tier audit spends money,
    each a refusal with its reason. The record this audit writes is what
    `record_audit.py` reads, so a record it would hold against the entry is
    never made in the first place."""
    env = os.environ
    if _tier() != "ci" or not _run_url():
        raise Refused("a promotion-tier audit runs in CI, which records it (ADR-0022); "
                      "run it from audit_entry.yml. A run here is a local audit: drop --ci.")
    if env.get("GITHUB_REF") != "refs/heads/main":
        raise Refused(f"dispatched on {env.get('GITHUB_REF')!r}; the register an audit stamps "
                      "is the one on main")
    if _shallow(root):
        raise Refused("this clone is shallow, so the bundle would say the entry's history and "
                      "each report's commits are unavailable — check out with fetch-depth: 0 "
                      "and mount output with its history (OUTPUT_FULL_HISTORY=1)")
    ref = ra._resolve_ref(root, OUTPUT_BRANCH)
    if ref is None:
        raise Refused(f"no `{OUTPUT_BRANCH}` branch here: the canary suites, earlier audits and "
                      "reports are all on it")
    if ra._git(root, "status", "--porcelain", "--", dp.HYPOTHESES.as_posix()):
        raise Refused(f"{dp.HYPOTHESES} has uncommitted changes; an audit stamps committed text")
    register = (root / dp.HYPOTHESES).read_text(encoding="utf-8")
    entry = next((e for e in dp.parse_entries(register) if e.hid == hid), None)
    if entry is None:
        raise Refused(f"{hid} is not in {dp.HYPOTHESES}")
    if entry.status == "closed":
        raise Refused(f"{hid} is closed; a closed entry is not submitted")
    history = entry_history(root, hid)
    if not history:
        raise Refused(f"git holds no history for {hid}'s lines, so nothing would show when "
                      "any part of it was written")

    ins_sha, set_sha = _sha(read_instructions(root)), canary_set_sha(root)
    suite = ra.certified_configs(root, ref).get((model, effort, ins_sha, set_sha))
    if suite is None:
        raise Refused(f"no passing CI canary suite on `{ref}` certifies `{model}` / `{effort}` on "
                      f"instructions sha256:{ins_sha[:12]}… and canary set sha256:{set_sha[:12]}… "
                      "— run auditor_canaries.yml with this configuration first (WP-25.A)")

    prior = ra.ci_audits(root, ref).get(hid, [])
    stamp = f"sha256:{_sha(dp.stamped_text(dp.entry_text(register, hid)))}"
    same = [r for r in prior if r.get("entry_fingerprint") == stamp]
    if same:
        raise Refused(f"CI already audited this exact text (`{same[-1]['_path']}`, "
                      f"`{same[-1].get('verdict')}`); auditing it again is a retry, not a "
                      "resubmission — change the entry, or let the verdict stand")
    rejects = sum(r.get("verdict") == "reject" for r in prior)
    if rejects >= 2 and hid not in ra.OWNER_RESUBMISSIONS:
        raise Refused(f"{hid} has been rejected {rejects} times; it closes or the owner decides "
                      "(ADR-0022, *No grinding*), recorded in resolved.md and pinned in "
                      "record_audit.OWNER_RESUBMISSIONS")
    return Preflight(hid, entry.status, ref, suite, set_sha, prior,
                     sum(ln.startswith("COMMIT ") for ln in history.splitlines()))


def sync_field(root: Path, hid: str | None = None) -> list[str]:
    """Rewrite the Audit record field of `hid` (or of every entry) from CI's
    records on the output branch. Returns the entries whose field changed."""
    ref = ra._resolve_ref(root, OUTPUT_BRANCH)
    if ref is None:
        raise SystemExit(f"no `{OUTPUT_BRANCH}` branch here — `git fetch origin {OUTPUT_BRANCH}`")
    audits = ra.ci_audits(root, ref)
    path = root / dp.HYPOTHESES
    text = path.read_text(encoding="utf-8")
    hids = [hid] if hid else [e.hid for e in dp.parse_entries(text)]
    changed = []
    for h in hids:
        new = dp.with_audit_record(text, h, dp.audit_record_paragraph(audits.get(h, [])))
        if new != text:
            changed.append(h)
            text = new
    if changed:
        path.write_text(text, encoding="utf-8")
    return changed


# ---------------------------------------------------------------------------
# the canaries
# ---------------------------------------------------------------------------

@dataclass
class Canary:
    name: str
    expect: str | None      # the finding it must produce; None for the clean base
    planted: str            # what was planted — for the record, never for the auditor
    hid: str
    files: dict[str, str]   # file name → content, after the canary's edits
    commits: list[dict]     # {branch, date, message, files: {path: file name}}


# Copied from the real tree into every canary repository: the rules the auditor
# is held to, and the two code files the bundle's facts are read from.
CANARY_TREE = (dp.HOW_WE_EXPLORE, SEAL_SOURCE, dp.HARNESS)
# The KB entries and work packages the canary entry cites are NOT the live
# pages but frozen excerpts under base/record/. The live ones keep gaining
# dates, and cited text dated after the entry citing it reads as a backdated
# entry — the first paid run (2026-09-28) failed on exactly that.
FROZEN_DIR = "record"
CANARY_FROZEN = {KNOWLEDGE_BASE: "knowledge-base.md", ROADMAP: "roadmap.md"}

_REGISTER_HEAD = """# Hypothesis register

**Conjectures, not findings.** The rules for what goes here and how it leaves
are in How we explore.

---

"""
_REGISTER_TAIL = "\n## Closed\n\nNone yet.\n"


def load_canaries(root: Path) -> tuple[Canary, list[Canary]]:
    """(the clean base, the defective variants), with every edit checked to
    apply exactly once, so no canary silently becomes its own clean twin."""
    cdir = root / CANARY_DIR
    bdir = cdir / BASE
    timeline = json.loads((bdir / "timeline.json").read_text(encoding="utf-8"))
    base_files = {p.name: p.read_text(encoding="utf-8") for p in sorted(bdir.glob("*.md"))}
    base = Canary(BASE, None, "", timeline["hid"], base_files, list(timeline["commits"]))
    _check_files(base)
    variants: list[Canary] = []
    for d in sorted(p for p in cdir.iterdir() if p.is_dir() and p.name != BASE):
        spec = json.loads((d / "canary.json").read_text(encoding="utf-8"))
        if spec.get("expect") not in CATEGORIES:
            raise CanaryError(f"{d.name}: expects {spec.get('expect')!r}, not a finding category")
        if not str(spec.get("planted", "")).strip():
            raise CanaryError(f"{d.name}: says nothing about what it plants")
        files = dict(base_files)
        files.update({p.name: p.read_text(encoding="utf-8") for p in sorted(d.glob("*.md"))})
        for e in spec.get("edits", []):
            if e["file"] not in files:
                raise CanaryError(f"{d.name}: edits {e['file']}, which does not exist")
            n = files[e["file"]].count(e["old"])
            if n != 1:
                raise CanaryError(f"{d.name}: an edit to {e['file']} matches {n} times, not once")
            files[e["file"]] = files[e["file"]].replace(e["old"], e["new"])
        commits = list(timeline["commits"]) + list(spec.get("add_commits", []))
        if files == base_files and commits == base.commits:
            raise CanaryError(f"{d.name}: plants nothing — it is identical to the clean base")
        c = Canary(d.name, spec["expect"], spec["planted"], timeline["hid"], files, commits)
        _check_files(c)
        variants.append(c)
    return base, variants


def _check_files(c: Canary) -> None:
    for commit in c.commits:
        for name in commit["files"].values():
            if name not in c.files:
                raise CanaryError(f"{c.name}: a commit names {name}, which does not exist")


def _content(c: Canary, path: str, name: str) -> str:
    text = c.files[name]
    if path == dp.HYPOTHESES.as_posix():
        return _REGISTER_HEAD + text.rstrip("\n") + "\n" + _REGISTER_TAIL
    return text


def materialize(root: Path, c: Canary, dest: Path) -> Path:
    """Replay a canary into a fresh git repository at `dest`: the real rules,
    KB, roadmap and code facts as a first commit on `main`, then the canary's
    commits in date order — each with its own date, on `main` or on an orphan
    `output` — built with plumbing so no checkout juggling can mix branches."""
    dest.mkdir(parents=True, exist_ok=False)

    def git(*args: str, env: dict | None = None, data: str | None = None) -> str:
        r = subprocess.run(["git", "-C", str(dest), *args], input=data, capture_output=True,
                           text=True, check=False, env=env)
        if r.returncode != 0:
            raise CanaryError(f"{c.name}: git {' '.join(args[:2])} failed: {r.stderr.strip()}")
        return r.stdout.strip()

    git("init", "-q", "-b", "main")
    commits = sorted(c.commits, key=lambda k: datetime.fromisoformat(k["date"]))
    first = datetime.fromisoformat(commits[0]["date"]) - timedelta(days=1)
    tree_files = [(rel.as_posix(), (root / rel).read_text(encoding="utf-8"))
                  for rel in CANARY_TREE if (root / rel).is_file()]
    frozen = root / CANARY_DIR / BASE / FROZEN_DIR
    tree_files += [(rel.as_posix(), (frozen / name).read_text(encoding="utf-8"))
                   for rel, name in CANARY_FROZEN.items()]
    steps = [("main", first.isoformat(), "record: the rules, the KB, the roadmap", tree_files)]
    steps += [(k["branch"], k["date"], k["message"],
               [(p, _content(c, p, n)) for p, n in k["files"].items()]) for k in commits]

    heads: dict[str, str] = {}
    base_env = {**os.environ, "GIT_AUTHOR_NAME": "macro-assist",
                "GIT_AUTHOR_EMAIL": "macro-assist@localhost",
                "GIT_COMMITTER_NAME": "macro-assist", "GIT_COMMITTER_EMAIL": "macro-assist@localhost"}
    for branch, when, message, files in steps:
        env = {**base_env, "GIT_INDEX_FILE": str(dest / ".git" / f"index-{branch}"),
               "GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when}
        for path, text in files:
            blob = git("hash-object", "-w", "--stdin", data=text)
            git("update-index", "--add", "--cacheinfo", f"100644,{blob},{path}", env=env)
        tree = git("write-tree", env=env)
        parent = ["-p", heads[branch]] if branch in heads else []
        heads[branch] = git("commit-tree", tree, *parent, "-m", message, env=env)
        git("update-ref", f"refs/heads/{branch}", heads[branch])
    git("checkout", "-q", "-f", "main")
    # mount the latest output the way a real checkout has it, so the bundle's
    # "local copy" line reads as it would for a real entry
    if "output" in heads:
        for rel in (git("ls-tree", "-r", "--name-only", "output") or "").splitlines():
            local = dest / RESULTS / rel
            local.parent.mkdir(parents=True, exist_ok=True)
            local.write_bytes(_git_bytes(dest, "show", f"output:{rel}") or b"")
    return dest


def canary_bundle(root: Path, c: Canary, workdir: Path, *, now: datetime | None = None) -> Bundle:
    return build_bundle(materialize(root, c, workdir / c.name), c.hid, now=now)


def score_canaries(variants: list[Canary], results: dict[str, dict]) -> tuple[bool, list[dict]]:
    """results: name → {"status": "ran", "record": …} or {"status": "not_run", "why": …}.
    Passed only if every variant was caught for its own defect, was rejected,
    and the clean base did not carry that category as blocking. A base that did
    not run fails every canary: without it nothing is discriminated."""
    base = results.get(BASE, {})
    base_blocking = ({f["category"] for f in base["record"]["findings"] if f["blocking"]}
                     if base.get("status") == "ran" else None)
    rows: list[dict] = []
    for c in variants:
        r = results.get(c.name, {"status": "not_run", "why": "no result"})
        row = {"canary": c.name, "expect": c.expect, "passed": False}
        if r.get("status") != "ran":
            row["why"] = f"the audit did not run: {r.get('why')}"
        elif base_blocking is None:
            row["why"] = f"the clean base did not run ({base.get('why')}), so nothing is discriminated"
        else:
            rec = r["record"]
            caught = c.expect in {f["category"] for f in rec["findings"] if f["blocking"]}
            rejected = rec["verdict"] == "reject"
            clean = c.expect not in base_blocking
            row.update(caught=caught, rejected=rejected, clean_base_clear=clean,
                       found=sorted({f["category"] for f in rec["findings"] if f["blocking"]}))
            row["passed"] = caught and rejected and clean
            row["why"] = ("caught, and not raised against the clean base" if row["passed"] else
                          "; ".join(w for w, bad in (
                              (f"{c.expect} not reported as blocking", not caught),
                              ("not rejected", not rejected),
                              (f"{c.expect} is also raised against the clean base", not clean),
                          ) if bad))
        rows.append(row)
    return bool(rows) and all(r["passed"] for r in rows), rows


def run_canaries(root: Path, *, client, model: str, effort: str,
                 max_usd: float = DEFAULT_MAX_USD, now: datetime | None = None) -> dict:
    base, variants = load_canaries(root)
    instructions = read_instructions(root)
    results: dict[str, dict] = {}
    spent = 0.0
    with tempfile.TemporaryDirectory(prefix="audit-canaries-") as tmp:
        for c in (base, *variants):
            if spent >= max_usd:
                results[c.name] = {"status": "not_run",
                                   "why": f"spend guard: ${spent:.2f} of ${max_usd:.2f} used"}
                continue
            bundle = canary_bundle(root, c, Path(tmp), now=now)
            try:
                rec = audit(bundle, instructions, client=client, model=model, effort=effort)
            except (AuditNotRun, InvalidAudit) as e:
                results[c.name] = {"status": "not_run", "why": str(e)}
                continue
            spent += rec["est_cost_usd"] or 0.0
            results[c.name] = {"status": "ran", "record": rec}
    passed, rows = score_canaries(variants, results)
    base_rec = results.get(BASE, {}).get("record")
    return {
        "schema": 1,
        "suite": "auditor canaries (WP-25.A)",
        "passed": passed,
        "ran_at": (now or datetime.now(timezone.utc)).isoformat(timespec="seconds"),
        "tier": _tier(),
        "run": _run_url(),
        "requested_model": model,
        "provider": provider_for(model).name,
        "effort": effort,
        "instructions_sha256": _sha(instructions),
        "canary_set_sha256": canary_set_sha(root),
        "est_cost_usd": round(spent, 4),
        "clean_base_verdict": base_rec["verdict"] if base_rec else None,
        "canaries": rows,
        "planted": {c.name: c.planted for c in variants},
        "results": results,
    }


def canary_set_sha(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted((root / CANARY_DIR).rglob("*")):
        if p.is_file():
            h.update(p.relative_to(root / CANARY_DIR).as_posix().encode() + b"\0")
            h.update(p.read_bytes() + b"\0")
    return h.hexdigest()


def render_suite(s: dict) -> str:
    out = [
        "# Auditor canaries",
        "",
        f"**{'PASSED' if s['passed'] else 'FAILED'}** · {s['ran_at']} · tier `{s['tier']}` · "
        f"model `{s['requested_model']}` · effort `{s['effort']}`"
        + (f" · [run]({s['run']})" if s.get("run") else ""),
        "",
        f"Instructions `sha256:{s['instructions_sha256'][:16]}…` · canary set "
        f"`sha256:{s['canary_set_sha256'][:16]}…` · estimated cost ${s['est_cost_usd']:.2f}",
        "",
        "A canary passes when the auditor reports its planted defect as blocking, rejects the "
        "entry, and does not raise that category against the clean base.",
        "",
        "| canary | must find | passed | why |",
        "|---|---|---|---|",
    ]
    out += [f"| `{r['canary']}` | `{r['expect']}` | {'yes' if r['passed'] else '**no**'} | {r['why']} |"
            for r in s["canaries"]]
    base = s["results"].get(BASE, {})
    out += ["", "## The clean base", ""]
    if base.get("status") == "ran":
        rec = base["record"]
        out.append(f"Verdict `{rec['verdict']}` — recorded, not graded.")
        out += [f"- {r}" for r in rec["reasons"]] or ["- nothing blocking"]
    else:
        out.append(f"Did not run: {base.get('why')}")
    out += ["", "## What each canary plants", ""]
    out += [f"- **`{k}`** — {v}" for k, v in s["planted"].items()]
    return "\n".join(out) + "\n"


def render_dry_run(pf: Preflight, bundle: Bundle, *, model: str, effort: str) -> str:
    rejects = sum(r.get("verdict") == "reject" for r in pf.prior)
    out = [
        f"# Dry run — {pf.hid}",
        "",
        f"Every refusal check passed and the bundle was built. **No API call was made and nothing "
        f"was recorded.** A real run would audit with `{model}` / `{effort}`.",
        "",
        f"- **Entry:** `{pf.status}`, stamped text `sha256:{bundle.fingerprint[:16]}…`",
        f"- **History:** a full clone; {pf.history_commits} commit(s) changed the entry",
        f"- **Certified by:** `{pf.ref}:{pf.certified_by}`",
        f"- **Earlier CI audits:** {len(pf.prior)} ({rejects} rejection{'s' * (rejects != 1)})",
        f"- **Bundle:** {len(bundle.rules) + len(bundle.material):,} characters, "
        f"sha256 `{bundle.sha256[:16]}…`; reports read from `{bundle.sources['reports']}`",
        "",
    ]
    return "\n".join(out)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _client(model: str = DEFAULT_MODEL):
    import anthropic
    p = provider_for(model)
    key = next((os.environ[k] for k in p.key_env if os.environ.get(k)), None)
    if not key:
        raise SystemExit(f"{p.key_env[0]} is not set (the key for `{model}`, provider "
                         f"{p.name}). --bundle-only and --check-canaries need none; the canary "
                         f"suite runs in CI (auditor_canaries.yml).")
    if p.native:
        return anthropic.Anthropic()
    base_url = (os.environ.get(p.base_url_env) if p.base_url_env else None) or p.base_url
    return anthropic.Anthropic(base_url=base_url, api_key=key)


def _stamp(now: datetime) -> str:
    return now.strftime("%Y-%m-%dT%H%MZ")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="The independent auditor of a register entry (ADR-0022). "
                    "--bundle-only and --check-canaries make no API call.")
    ap.add_argument("hid", nargs="?", help="register entry, e.g. H-008")
    ap.add_argument("--bundle-only", action="store_true",
                    help="print what the auditor would read, and stop")
    ap.add_argument("--canary", help="with --bundle-only: a canary's bundle instead ('base' or a name)")
    ap.add_argument("--canaries", action="store_true", help="run the canary suite")
    ap.add_argument("--check-canaries", action="store_true",
                    help="replay and bundle every canary without calling the model")
    ap.add_argument("--ci", action="store_true",
                    help="a promotion-tier audit (audit_entry.yml): refuse unless in CI, full "
                         "history, a certified configuration and no grinding")
    ap.add_argument("--dry-run", action="store_true",
                    help="with --ci: run every refusal check and build the bundle, then stop "
                         "before the API call")
    ap.add_argument("--sync-field", action="store_true",
                    help="rewrite the entry's Audit record field (every entry's, with no id) "
                         "from CI's records on the output branch; no API call")
    ap.add_argument("--model", default=os.environ.get("AUDITOR_MODEL") or DEFAULT_MODEL,
                    help="auditor model; `kimi-…` goes to Moonshot (MOONSHOT_API_KEY), "
                         "`claude-…` to Anthropic")
    ap.add_argument("--effort", default=DEFAULT_EFFORT,
                    choices=("low", "medium", "high", "xhigh", "max"))
    ap.add_argument("--max-usd", type=float, default=DEFAULT_MAX_USD,
                    help="stop the canary suite once its estimated spend reaches this")
    ap.add_argument("--out-dir", type=Path, help=f"where records go (default <root>/{AUDIT_OUT})")
    ap.add_argument("--root", type=Path, default=ra._repo_root(), help="repo root")
    args = ap.parse_args(argv)
    root = args.root.resolve()
    out_dir = args.out_dir or root / AUDIT_OUT
    now = datetime.now(timezone.utc)

    if args.check_canaries or (args.bundle_only and args.canary):
        base, variants = load_canaries(root)
        with tempfile.TemporaryDirectory(prefix="audit-canaries-") as tmp:
            if args.canary:
                pick = next((c for c in (base, *variants) if c.name == args.canary), None)
                if pick is None:
                    ap.error(f"no canary {args.canary!r}; there are: "
                             f"{', '.join(c.name for c in (base, *variants))}")
                sys.stdout.write(canary_bundle(root, pick, Path(tmp), now=now).material)
                return 0
            for c in (base, *variants):
                b = canary_bundle(root, c, Path(tmp), now=now)
                print(f"{c.name:<16} {c.expect or '(clean base)':<16} "
                      f"{len(b.material) + len(b.rules):>7,} chars  entry sha256:{b.fingerprint[:12]}")
        print(f"{len(variants)} canaries and a clean base replay and bundle; no API call made.")
        return 0

    if args.canaries:
        suite = run_canaries(root, client=_client(args.model), model=args.model, effort=args.effort,
                             max_usd=args.max_usd, now=now)
        dest = out_dir / "canaries"
        dest.mkdir(parents=True, exist_ok=True)
        name = f"{_stamp(now)}-{suite['instructions_sha256'][:8]}"
        (dest / f"{name}.json").write_text(json.dumps(suite, indent=2, ensure_ascii=False) + "\n",
                                           encoding="utf-8")
        text = render_suite(suite)
        (dest / "latest.md").write_text(text, encoding="utf-8")
        sys.stdout.write(text)
        return 0 if suite["passed"] else 1

    if args.sync_field:
        changed = sync_field(root, args.hid.upper() if args.hid else None)
        print(f"Audit record rewritten from CI's records: {', '.join(changed)}." if changed
              else "Every Audit record already matches CI's records.")
        return 0

    if not args.hid:
        ap.error("give an entry id, or --canaries / --check-canaries")
    if args.dry_run and not args.ci:
        ap.error("--dry-run goes with --ci")
    hid = args.hid.upper()
    pf = None
    if args.ci:
        try:
            pf = preflight(root, hid, model=args.model, effort=args.effort)
        except Refused as e:
            print(f"Refused, and nothing was spent: {e}", file=sys.stderr)
            return 2
    try:
        bundle = build_bundle(root, hid, now=now)
    except BundleError as e:
        ap.error(str(e))
    if args.bundle_only:
        sys.stdout.write(bundle.material)
        return 0
    if pf is not None and args.dry_run:
        sys.stdout.write(render_dry_run(pf, bundle, model=args.model, effort=args.effort))
        return 0

    provenance = ({"canary_set_sha": pf.canary_set_sha, "certified_by": pf.certified_by}
                  if pf is not None else {"canary_set_sha": canary_set_sha(root)})
    try:
        rec = audit(bundle, read_instructions(root), client=_client(args.model), model=args.model,
                    effort=args.effort, now=now, **provenance)
    except (AuditNotRun, InvalidAudit) as e:
        print(f"The audit did not complete, and that is not a pass: {e}", file=sys.stderr)
        return 1
    dest = out_dir / "entries" / hid
    dest.mkdir(parents=True, exist_ok=True)
    name = f"{_stamp(now)}-{rec['tier']}"
    (dest / f"{name}.json").write_text(json.dumps(rec, indent=2, ensure_ascii=False) + "\n",
                                       encoding="utf-8")
    text = render_record(rec)
    (dest / f"{name}.md").write_text(text, encoding="utf-8")
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
