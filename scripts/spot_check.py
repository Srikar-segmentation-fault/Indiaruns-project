#!/usr/bin/env python3
"""
scripts/spot_check.py
---------------------
Spot-check a stratified sample of the submission and the full candidate pool.

Samples ~7 from top 10, ~7 from middle (rank 40-60), ~6 from bottom of top
100 (rank 90-100), plus 5 random candidates from the full pool that did NOT
make the top 100.

For each candidate, prints:
  candidate_id | rank | score | current_title | years_of_experience |
  location | must_have | nice_to_have | anti_penalty | anti_reasons |
  behavioral_mult

Calls score_candidate() from rank.py — no reimplementation of scoring logic.

Usage
-----
    python scripts/spot_check.py \\
        --submission ./submission.csv \\
        --candidates ./candidates.jsonl.gz \\
        --n 20
"""

import argparse
import csv
import random
import sys
import os

# ---------------------------------------------------------------------------
# Make rank.py importable from repo root or scripts/ sub-directory.
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from rank import score_candidate, load_candidates  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_submission(csv_path):
    """
    Returns a dict: candidate_id -> {'rank': int, 'score': float}
    sorted by rank ascending.
    """
    rows = {}
    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cid = row["candidate_id"].strip()
            rows[cid] = {
                "rank": int(row["rank"]),
                "score": float(row["score"]),
            }
    return rows


def stratified_sample(submission_rows, n_total=20):
    """
    Return (top_ids, mid_ids, bot_ids, outside_ids_placeholder)
    outside_ids is filled later after scanning the pool.

    Split: n_top=7, n_mid=7, n_bot=6 from submission; 5 from outside top-100.
    """
    # Adjust proportions if n_total != 20
    n_outside = max(1, round(n_total * 5 / 20))
    remaining = n_total - n_outside
    n_top = round(remaining * 7 / 20)
    n_mid = round(remaining * 7 / 20)
    n_bot = remaining - n_top - n_mid

    by_rank = sorted(submission_rows.items(), key=lambda x: x[1]["rank"])

    top_pool = [cid for cid, r in by_rank if 1 <= r["rank"] <= 10]
    mid_pool = [cid for cid, r in by_rank if 40 <= r["rank"] <= 60]
    bot_pool = [cid for cid, r in by_rank if 90 <= r["rank"] <= 100]

    rng = random.Random(42)  # fixed seed for reproducibility
    top_ids = rng.sample(top_pool, min(n_top, len(top_pool)))
    mid_ids = rng.sample(mid_pool, min(n_mid, len(mid_pool)))
    bot_ids = rng.sample(bot_pool, min(n_bot, len(bot_pool)))

    return set(top_ids), set(mid_ids), set(bot_ids), n_outside


def truncate(s, n):
    s = str(s)
    return s if len(s) <= n else s[: n - 1] + "…"


def fmt_reasons(reasons):
    if not reasons:
        return "—"
    short = {
        "consulting_only_career":              "consulting_only",
        "title_chaser_pattern":                "title_chaser",
        "keyword_stuffed_skills_no_evidence":  "kw_stuffer",
        "cv_speech_robotics_no_nlp_ir":        "cv_no_nlp",
        "pure_research_no_production":         "research_only",
        "langchain_wrapper_only_recent":       "llm_wrapper_only",
    }
    return "; ".join(short.get(r, r) for r in reasons)


def print_table(rows):
    """Pretty-print as a fixed-width table with a divider after every row."""
    # Column definitions: (header, width, key, fmt)
    cols = [
        ("candidate_id",  14, "candidate_id",  lambda v: str(v)),
        ("rank",           6, "rank",           lambda v: str(v) if v != -1 else "—"),
        ("score",          7, "score",          lambda v: f"{v:.4f}" if isinstance(v, float) else str(v)),
        ("current_title", 26, "current_title",  lambda v: truncate(v, 26)),
        ("yoe",            5, "yoe",            lambda v: f"{v:.1f}"),
        ("location",      14, "location",       lambda v: truncate(v, 14)),
        ("must_have",      9, "must_have",      lambda v: f"{v:.3f}"),
        ("nice_to_hv",     9, "nice_to_have",   lambda v: f"{v:.3f}"),
        ("anti_pen",       8, "anti_penalty",   lambda v: f"{v:.3f}"),
        ("beh_mult",       8, "behavioral_mult",lambda v: f"{v:.3f}"),
        ("anti_reasons",  24, "anti_reasons",   lambda v: truncate(fmt_reasons(v), 24)),
    ]

    sep = "  ".join("-" * w for _, w, _, _ in cols)
    hdr = "  ".join(f"{h:<{w}}" for h, w, _, _ in cols)

    print()
    print(hdr)
    print(sep)

    for r in rows:
        line = "  ".join(
            f"{fmt(r.get(key, '?')):<{w}}"
            for _, w, key, fmt in cols
        )
        print(line)

    print(sep)
    print(f"  {len(rows)} rows shown\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description="Spot-check a stratified sample of submission candidates."
    )
    ap.add_argument("--submission", required=True, metavar="CSV",
                    help="Path to submission.csv")
    ap.add_argument("--candidates", required=True, metavar="FILE",
                    help="Candidate pool (.jsonl.gz / .jsonl / .json)")
    ap.add_argument("--n", type=int, default=20, metavar="N",
                    help="Total number of candidates to sample (default: 20)")
    ap.add_argument("--seed", type=int, default=42,
                    help="Random seed for reproducibility (default: 42)")
    args = ap.parse_args()

    rng = random.Random(args.seed)

    print(f"Loading submission: {args.submission}")
    submission = load_submission(args.submission)
    top100_ids = set(submission.keys())
    print(f"  → {len(submission)} candidates in submission.\n")

    # Determine the stratified IDs we want from the submission
    top_ids, mid_ids, bot_ids, n_outside = stratified_sample(submission, args.n)
    want_from_submission = top_ids | mid_ids | bot_ids

    print(
        f"Sample plan: {len(top_ids)} top-10 | {len(mid_ids)} mid (40-60) | "
        f"{len(bot_ids)} bottom (90-100) | {n_outside} outside top-100"
    )
    print(f"Scanning candidate pool: {args.candidates}\n")

    # Stream the pool once, collecting:
    #   - full records for wanted submission candidates
    #   - non-top-100 candidates reservoir (for the "outside" sample)
    found_submission  = {}   # cid -> cand record
    outside_reservoir = []   # reservoir for non-top-100 candidates

    total_scanned = 0
    for cand in load_candidates(args.candidates):
        cid = cand.get("candidate_id", "")
        total_scanned += 1

        if cid in want_from_submission:
            found_submission[cid] = cand
        elif cid not in top100_ids:
            # Reservoir sampling (Knuth Algorithm R) for non-top-100 pool
            outside_reservoir.append(cid)
            if len(outside_reservoir) > 10_000:
                # Keep reservoir bounded; do a compact replacement pass
                # (simple: just sample n_outside from what we have at the end)
                pass

        if total_scanned % 10_000 == 0:
            print(f"  … {total_scanned:,} scanned, "
                  f"{len(found_submission)}/{len(want_from_submission)} submission targets found")

    print(f"  → Scanned {total_scanned:,} total candidates.\n")

    # Pick the outside sample
    outside_sample_ids = rng.sample(
        outside_reservoir, min(n_outside, len(outside_reservoir))
    )

    # We need to re-scan for the outside candidates' full records
    outside_found = {}
    if outside_sample_ids:
        outside_set = set(outside_sample_ids)
        for cand in load_candidates(args.candidates):
            cid = cand.get("candidate_id", "")
            if cid in outside_set:
                outside_found[cid] = cand
            if len(outside_found) == len(outside_set):
                break  # early exit once we have them all

    # -------------------------------------------------------------------------
    # Build display rows
    # -------------------------------------------------------------------------
    display_rows = []

    def make_row(cand, rank_val, score_val, group_label):
        try:
            result = score_candidate(cand)
        except Exception as exc:
            return None
        prof = cand["profile"]
        return {
            "group":           group_label,
            "candidate_id":    cand["candidate_id"],
            "rank":            rank_val,
            "score":           score_val if score_val is not None else result["score"],
            "current_title":   prof.get("current_title", ""),
            "yoe":             prof.get("years_of_experience", 0),
            "location":        prof.get("location", ""),
            "must_have":       result["must_have"],
            "nice_to_have":    result["nice_to_have"],
            "anti_penalty":    result["anti_penalty"],
            "anti_reasons":    result["anti_reasons"],
            "behavioral_mult": result["behavioral_mult"],
        }

    def add_group(id_set, label):
        for cid in sorted(id_set):
            cand = found_submission.get(cid)
            if cand is None:
                continue
            sub = submission[cid]
            row = make_row(cand, sub["rank"], sub["score"], label)
            if row:
                display_rows.append(row)

    add_group(top_ids, "TOP-10")
    add_group(mid_ids, "MID-40-60")
    add_group(bot_ids, "BOT-90-100")

    for cid in sorted(outside_found.keys()):
        cand = outside_found[cid]
        row = make_row(cand, -1, None, "OUTSIDE")
        if row:
            display_rows.append(row)

    # -------------------------------------------------------------------------
    # Print
    # -------------------------------------------------------------------------
    print("=" * 80)
    print(" SPOT CHECK — Stratified sample")
    print("=" * 80)

    # Print by group
    groups_order = ["TOP-10", "MID-40-60", "BOT-90-100", "OUTSIDE"]
    for g in groups_order:
        g_rows = [r for r in display_rows if r["group"] == g]
        if not g_rows:
            continue
        labels = {
            "TOP-10":      "Top 10 (ranks 1–10)",
            "MID-40-60":   "Middle (ranks 40–60)",
            "BOT-90-100":  "Bottom of top-100 (ranks 90–100)",
            "OUTSIDE":     "Outside top-100 (random from full pool)",
        }
        print(f"\n{'─' * 80}")
        print(f"  {labels[g]}")
        print_table(g_rows)

    print("Done.")


if __name__ == "__main__":
    main()
