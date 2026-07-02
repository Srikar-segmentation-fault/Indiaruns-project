#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# scripts/run_and_validate.sh
#
# Run the full submission pipeline and validate the output in one shot.
# Stops on the first failure (set -e) and prints a clear PASS/FAIL banner.
#
# Usage (from repo root):
#   bash scripts/run_and_validate.sh
#
# Requirements: Python 3.8+ on PATH; no third-party packages needed.
# -----------------------------------------------------------------------------
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "============================================================"
echo " Redrob Hackathon — Run & Validate"
echo "============================================================"
echo ""

# ---------- Step 1: Ranking -------------------------------------------------
echo "[1/2] Running ranker ..."
python rank.py \
    --candidates ./candidates.jsonl.gz \
    --out ./submission.csv \
    --topn 100

echo ""

# ---------- Step 2: Validation ----------------------------------------------
echo "[2/2] Validating submission.csv ..."
python validate_submission.py ./submission.csv

echo ""
echo "============================================================"
echo " ✅  PASS — submission.csv is valid and ready to submit."
echo "============================================================"
