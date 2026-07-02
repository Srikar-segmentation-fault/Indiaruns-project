#!/usr/bin/env python3
"""
scripts/audit_honeypots.py
--------------------------
Audit the top-100 submission for honeypot candidates.

Imports honeypot_flags() directly from rank.py (no reimplementation).
Exit code 1 if honeypot rate > 10% (Stage 3 disqualification threshold).
Exit code 0 otherwise.

Usage
-----
    python scripts/audit_honeypots.py \\
        --submission ./submission.csv \\
        --candidates ./candidates.jsonl.gz

The script also accepts .jsonl and .json candidate files (rank.py's
load_candidates() handles all three formats).
"""

import argparse
import csv
import sys
import os

# ---------------------------------------------------------------------------
# Make rank.py importable when this script is run from repo root OR from
# the scripts/ sub-directory.
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from rank import honeypot_flags, load_candidates  # noqa: E402

DISQUALIFICATION_THRESHOLD = 0.10  # 10%


def load_top100_ids(submission_path):
    """Return an ordered list of candidate_ids from the submission CSV."""
    ids = []
    with open(submission_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ids.append(row["candidate_id"].strip())
    return ids


def main():
    ap = argparse.ArgumentParser(
        description="Audit top-100 submission for honeypot candidates."
    )
    ap.add_argument(
        "--submission",
        required=True,
        metavar="CSV",
        help="Path to submission CSV (e.g. ./submission.csv)",
    )
    ap.add_argument(
        "--candidates",
        required=True,
        metavar="FILE",
        help="Path to candidate pool (.jsonl.gz / .jsonl / .json)",
    )
    args = ap.parse_args()

    # -------------------------------------------------------------------------
    # Load the top-100 candidate IDs from the submission
    # -------------------------------------------------------------------------
    print(f"Loading submission: {args.submission}")
    top100_ids = load_top100_ids(args.submission)
    if len(top100_ids) != 100:
        print(
            f"WARNING: submission contains {len(top100_ids)} rows (expected 100). "
            "Proceeding with whatever is present."
        )
    top100_set = set(top100_ids)
    print(f"  → {len(top100_ids)} candidate IDs loaded.\n")

    # -------------------------------------------------------------------------
    # Stream the candidate pool and evaluate only the top-100 IDs
    # -------------------------------------------------------------------------
    print(f"Scanning candidate pool: {args.candidates}")
    found = {}          # candidate_id -> honeypot flags list
    total_scanned = 0

    for cand in load_candidates(args.candidates):
        cid = cand.get("candidate_id", "")
        if cid in top100_set:
            flags = honeypot_flags(cand)
            found[cid] = flags
        total_scanned += 1
        if total_scanned % 10_000 == 0:
            print(f"  … scanned {total_scanned:,} candidates, found {len(found)}/100 top-100 so far")

    print(f"  → Scanned {total_scanned:,} total candidates.\n")

    # -------------------------------------------------------------------------
    # Report
    # -------------------------------------------------------------------------
    flagged = {cid: flags for cid, flags in found.items() if flags}
    honeypot_count = len(flagged)
    total_found = len(found)
    rate = honeypot_count / total_found if total_found > 0 else 0.0

    print("=" * 60)
    print(f"  Honeypot audit results")
    print("=" * 60)
    print(f"  Top-100 candidates evaluated : {total_found}")
    print(f"  Honeypot-flagged             : {honeypot_count}")
    print(f"  Honeypot rate                : {rate * 100:.1f}%")
    print(f"  Threshold (disqualify > 10%) : 10.0%")
    print("=" * 60)

    if flagged:
        print(f"\nFlagged candidates ({honeypot_count}):\n")
        col_w_id    = 16
        col_w_flags = 60
        header = f"  {'candidate_id':<{col_w_id}}  flags"
        print(header)
        print("  " + "-" * (col_w_id + col_w_flags + 2))
        for cid in top100_ids:  # print in submission rank order
            if cid in flagged:
                flags_str = ", ".join(flagged[cid])
                print(f"  {cid:<{col_w_id}}  {flags_str}")
    else:
        print("\n  No honeypot candidates found in the top 100. ✅")

    print()

    if rate > DISQUALIFICATION_THRESHOLD:
        print(
            f"❌  FAIL — honeypot rate {rate * 100:.1f}% exceeds the 10% "
            "Stage 3 disqualification threshold."
        )
        sys.exit(1)
    else:
        print(f"✅  PASS — honeypot rate {rate * 100:.1f}% is within the allowed limit.")
        sys.exit(0)


if __name__ == "__main__":
    main()
