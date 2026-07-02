"""
sandbox/app.py — Streamlit evaluation sandbox for the India Runs / Redrob Hackathon
submission (submission_spec.md §10.5).

Imports rank.py directly from the same directory — no separate install needed.
Pure stdlib + streamlit + pandas only. No network calls. No authentication.
"""

import csv
import io
import json
import os
import sys

import pandas as pd
import streamlit as st

# ---------------------------------------------------------------------------
# Ensure sandbox/rank.py is importable regardless of how streamlit is invoked
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import rank  # noqa: E402  (sandbox/rank.py — scoring engine)

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="India Runs — Candidate Ranker Sandbox",
    page_icon="🏃",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.title("🏃 India Runs — Candidate Ranker")
st.caption(
    "Redrob Hackathon · Senior AI Engineer (Founding Team) · "
    "Evaluation sandbox — submission_spec.md §10.5"
)

with st.expander("ℹ️ What this sandbox is for", expanded=False):
    st.markdown(
        """
This is the **evaluation sandbox** for the India Runs / Redrob Hackathon submission.

It runs the **exact same scoring engine** used to produce the final `submission.csv`
— `rank.py` is imported directly from this sandbox folder (byte-for-byte copy of
the production scoring engine).

**What you can do here:**
- Upload a candidate file (`.json` array or `.jsonl`, ≤ 100 candidates)
- Or use the bundled 50-candidate demo sample
- Run the ranker and see the top-N results with scores and reasoning
- Download the ranked output as CSV

**Source code & full submission:**
https://github.com/Srikar-segmentation-fault/Indiaruns-project

**Constraints respected** (matching submission_spec.md):
- CPU-only, no GPU
- No network calls during scoring
- Pure Python stdlib in rank.py — no third-party ML libraries
        """
    )

# ---------------------------------------------------------------------------
# Sidebar — controls
# ---------------------------------------------------------------------------
st.sidebar.header("⚙️ Options")

top_n = st.sidebar.slider(
    "Top-N candidates to show",
    min_value=5,
    max_value=100,
    value=10,
    step=5,
    help="How many top-ranked candidates to display and include in the CSV download.",
)

show_detail = st.sidebar.checkbox(
    "Show score breakdown",
    value=True,
    help="Display per-component scores (must-have, logistics, behavioral multiplier, etc.).",
)

st.sidebar.markdown("---")
# ---------------------------------------------------------------------------
# Compute and display rank.py hash in sidebar (integrity check for evaluators)
# ---------------------------------------------------------------------------
import hashlib as _hashlib

_rank_path = os.path.join(_HERE, "rank.py")
with open(_rank_path, "rb") as _f:
    _rank_hash = _hashlib.sha256(_f.read()).hexdigest()[:16]

st.sidebar.markdown(f"**rank.py** (first 16 of SHA-256)  \n`{_rank_hash}…`")
st.sidebar.caption("Same file used for the production submission.")

# ---------------------------------------------------------------------------
# Input — bundled sample OR upload
# ---------------------------------------------------------------------------
st.subheader("1. Choose a candidate source")

source = st.radio(
    "Candidate source",
    ["Use bundled 50-candidate demo", "Upload my own file"],
    horizontal=True,
    label_visibility="collapsed",
)

candidates = []
load_error = None

if source == "Use bundled 50-candidate demo":
    _sample_path = os.path.join(_HERE, "sample_candidates.json")
    try:
        with open(_sample_path, "r", encoding="utf-8") as _f:
            candidates = json.load(_f)
        st.success(f"✅ Loaded {len(candidates)} candidates from bundled demo sample.")
    except FileNotFoundError:
        load_error = (
            "`sample_candidates.json` not found next to `app.py`. "
            "Re-clone the repo or run from the `sandbox/` directory."
        )

else:
    uploaded = st.file_uploader(
        "Upload a candidate file",
        type=["json", "jsonl"],
        help="JSON array (`.json`) or newline-delimited JSON (`.jsonl`), ≤ 100 candidates.",
    )
    if uploaded is not None:
        try:
            raw = uploaded.read().decode("utf-8")
            if uploaded.name.endswith(".jsonl"):
                candidates = [json.loads(ln) for ln in raw.splitlines() if ln.strip()]
            else:
                candidates = json.loads(raw)
            if not isinstance(candidates, list):
                load_error = "File must contain a JSON array of candidate objects."
            elif len(candidates) > 100:
                load_error = (
                    f"Uploaded file has {len(candidates)} candidates. "
                    "This sandbox is limited to ≤ 100 candidates. "
                    "For the full 100 K run, use `rank.py` from the CLI."
                )
            else:
                st.success(f"✅ Loaded {len(candidates)} candidates from upload.")
        except json.JSONDecodeError as exc:
            load_error = f"JSON parse error: {exc}"

if load_error:
    st.error(load_error)

# ---------------------------------------------------------------------------
# Run ranker
# ---------------------------------------------------------------------------
st.subheader("2. Run the ranker")

run_btn = st.button(
    "▶ Rank candidates",
    type="primary",
    disabled=(len(candidates) == 0 or load_error is not None),
)

if run_btn and candidates:
    with st.spinner(f"Scoring {len(candidates)} candidates…"):
        results = []
        honeypot_count = 0
        errors = []

        for cand in candidates:
            try:
                r = rank.score_candidate(cand)
                r["_cand"] = cand
                if r["honeypot_flags"]:
                    honeypot_count += 1
                results.append(r)
            except Exception as exc:
                errors.append(f"{cand.get('candidate_id', '?')}: {exc}")

        # Sort: score desc, candidate_id asc (tie-break)
        results.sort(key=lambda r: (-r["score"], r["candidate_id"]))
        # Round to 6 dp then re-sort on rounded value (matches production behaviour)
        for r in results:
            r["_score_out"] = round(r["score"], 6)
        results.sort(key=lambda r: (-r["_score_out"], r["candidate_id"]))

        top = results[: top_n]

    # ---- Summary metrics ----
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Candidates scored", len(results))
    col2.metric("Honeypot-flagged", honeypot_count)
    col3.metric("Showing top", len(top))
    col4.metric("Score errors", len(errors))

    if errors:
        with st.expander(f"⚠️ {len(errors)} scoring error(s)"):
            for e in errors:
                st.code(e)

    st.markdown("---")
    st.subheader(f"3. Top-{len(top)} ranked candidates")

    # ---- Build display dataframe ----
    rows = []
    for i, r in enumerate(top, start=1):
        cand = r["_cand"]
        prof = cand["profile"]
        ev = r["mh_evidence"]
        reasoning = rank.build_reasoning(cand, r)

        row = {
            "Rank": i,
            "Candidate ID": r["candidate_id"],
            "Score": f"{r['_score_out']:.6f}",
            "Title": prof.get("current_title", ""),
            "Location": prof.get("location", ""),
            "YoE": prof.get("years_of_experience", ""),
            "Reasoning": reasoning,
        }
        if show_detail:
            row.update(
                {
                    "Must-have": f"{r['must_have']:.3f}",
                    "Nice-to-have": f"{r['nice_to_have']:.3f}",
                    "Anti-penalty": f"{r['anti_penalty']:.3f}",
                    "Behavioral ×": f"{r['behavioral_mult']:.3f}",
                    "retrieval": f"{ev.get('retrieval', 0):.3f}",
                    "vectordb": f"{ev.get('vectordb', 0):.3f}",
                    "python": f"{ev.get('python', 0):.3f}",
                    "eval_fw": f"{ev.get('eval_framework', 0):.3f}",
                    "Honeypot?": ", ".join(r["honeypot_flags"]) or "—",
                }
            )
        rows.append(row)

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    # ---- CSV download ----
    st.markdown("---")
    st.subheader("4. Download ranked output")

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["candidate_id", "rank", "score", "reasoning"])
    for i, r in enumerate(top, start=1):
        reasoning = rank.build_reasoning(r["_cand"], r)
        writer.writerow([r["candidate_id"], i, r["_score_out"], reasoning])

    st.download_button(
        label="⬇️ Download submission.csv",
        data=buf.getvalue().encode("utf-8"),
        file_name="submission.csv",
        mime="text/csv",
        help="CSV format matches the submission spec: candidate_id, rank, score, reasoning.",
    )

    st.caption(
        "The CSV format (candidate_id, rank, score, reasoning) matches "
        "submission_spec.md §2–3 and can be validated with `validate_submission.py`."
    )

elif not run_btn and not candidates and source == "Upload my own file":
    st.info("Upload a `.json` or `.jsonl` file above, then click **▶ Rank candidates**.")

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.markdown("---")
st.caption(
    "India Runs · Redrob Hackathon · "
    "[GitHub repo](https://github.com/Srikar-segmentation-fault/Indiaruns-project) · "
    "Scoring: pure Python stdlib, CPU-only, no network calls."
)
