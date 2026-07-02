# Redrob Hackathon — Intelligent Candidate Ranking

Transparent, rule-based ranker for the **"Senior AI Engineer — Founding Team"** role.
Pure Python stdlib, CPU-only, no network calls, ≤5 min / ≤16 GB RAM on the full
100K-candidate pool.

> **Architecture**: see the module docstring at the top of
> [`rank.py`](./rank.py) for the full design rationale, scoring components,
> and anti-pattern detection logic — it is the authoritative reference and is
> not repeated here.

---

## Quick start

### 1. Requirements

```bash
python --version   # 3.8+ required; no third-party packages needed
```

All code uses the Python standard library only. See [`requirements.txt`](./requirements.txt)
for the explicit declaration and future-extension notes.

---

### 2. Reproduce the submission

#### Option A — Makefile (recommended)

```bash
make submit
```

This runs `rank.py` then `validate_submission.py` in order and stops on the
first failure. Override paths if needed:

```bash
make submit CANDIDATES=./sample_candidates.json   # quick test on sample
```

#### Option B — Shell script (Linux / macOS / WSL)

```bash
bash scripts/run_and_validate.sh
```

#### Option C — Commands verbatim (any platform)

```bash
python rank.py --candidates ./candidates.jsonl.gz --out ./submission.csv --topn 100
python validate_submission.py ./submission.csv
```

Expected output on success:

```
Scored 100000 candidates (N honeypot-flagged).
Wrote top 100 candidates to ./submission.csv
Submission is valid.
```

---

### 3. Quality checks

#### Honeypot audit

```bash
python scripts/audit_honeypots.py \
    --submission ./submission.csv \
    --candidates ./candidates.jsonl.gz
```

Imports `honeypot_flags()` directly from `rank.py`.  
Exit code **1** if the honeypot rate in the top-100 exceeds **10%** (Stage 3
disqualification threshold). Exit code **0** otherwise.

#### Spot check

```bash
python scripts/spot_check.py \
    --submission ./submission.csv \
    --candidates ./candidates.jsonl.gz \
    --n 20
```

Prints a stratified readable table: 7 from top-10, 7 from mid (rank 40–60),
6 from bottom (rank 90–100), 5 random candidates that did NOT make the top-100.
All scores come from `score_candidate()` in `rank.py` — no separate logic.

---

### 4. Timing and memory checks

#### Linux / macOS / WSL

```bash
# Wall-clock time + peak RSS
/usr/bin/time -v python rank.py \
    --candidates ./candidates.jsonl.gz \
    --out ./submission.csv \
    --topn 100 2>&1 | tail -20
```

Key lines to look for:

```
Elapsed (wall clock) time (h:mm:ss or m:ss): 0:02:30
Maximum resident set size (kbytes): 1234567   # ÷ 1024 / 1024 = GB
```

#### Windows PowerShell

```powershell
$t = Measure-Command {
    python rank.py --candidates ./candidates.jsonl.gz `
        --out ./submission.csv --topn 100
}
Write-Host "Wall-clock: $($t.TotalSeconds)s"

# Peak memory (Task Manager, or use:)
Get-Process python | Select-Object WorkingSet64
```

---

## Repository layout

```
india runs/
├── rank.py                        # Scoring engine — do not modify without discussion
├── validate_submission.py         # Official submission validator
├── requirements.txt               # Explicit "no packages needed" declaration
├── Makefile                       # make submit / make audit / make spot
├── submission_metadata.yaml       # Fill in TODOs before final upload
├── README.md                      # This file
├── scripts/
│   ├── run_and_validate.sh        # Bash pipeline (Linux/macOS/WSL)
│   ├── audit_honeypots.py         # Honeypot rate check (exit 1 if >10%)
│   └── spot_check.py              # Stratified quality spot-check
├── sandbox/                       # Hosted demo (Colab — TBD)
└── [PUB] India_runs_data_and_ai_challenge (2)/
    └── …/India_runs_data_and_ai_challenge/
        ├── candidates.jsonl        # Full 100K candidate pool (uncompressed)
        ├── candidate_schema.json
        ├── sample_candidates.json
        ├── sample_submission.csv
        └── submission_metadata_template.yaml
```

---

## Compute constraints (from `submission_spec.md`)

| Constraint                 | Value            | Status |
|---------------------------|------------------|--------|
| CPU-only (no GPU)          | Required         | ✅     |
| No network calls           | Required         | ✅     |
| Wall-clock ≤ 5 min         | Ranking step     | ✅     |
| RAM ≤ 16 GB                | Ranking step     | ✅     |
| Input                      | 100K JSONL(.gz)  | ✅     |
| Output rows                | Exactly 100      | ✅     |
| Ranks                      | 1–100, each once | ✅     |
| Score ordering             | Non-increasing   | ✅     |
| Tie-break                  | `candidate_id` ↑ | ✅     |

---

## Output CSV format

```
candidate_id,rank,score,reasoning
CAND_0001234,1,0.8731,"Senior AI Engineer with 7.0 yrs; strong on retrieval, vectordb; based in Pune; response rate 0.82."
…
```

Validated by `validate_submission.py` against `submission_spec.md` sections 2–3.

---

## Pre-computation note

`rank.py` requires **no pre-computation step**. Embeddings, indexes, and model
downloads are not used. If a sentence-transformers layer is added in a future
iteration, that pre-computation step will be documented here as a separate,
clearly timed phase distinct from the 5-minute ranking budget.

---

## Sandbox (evaluation demo)

A hosted Streamlit sandbox for evaluators is available — see [sandbox/README.md](./sandbox/README.md) for local-run and Streamlit Community Cloud deployment instructions.

---

## Submission checklist

- [ ] `make submit` completes without errors
- [ ] `python scripts/audit_honeypots.py …` exits 0
- [ ] `submission_metadata.yaml` has all TODOs filled in
- [ ] `sandbox/` link is live and working
- [ ] GitHub repo is reachable (or organizer access granted)
