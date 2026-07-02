# =============================================================================
# Makefile — Redrob Hackathon submission pipeline
#
# Primary target:
#   make submit        Run ranker, then validate. Stops on first failure.
#
# Individual targets:
#   make rank          Only run rank.py → submission.csv
#   make validate      Only validate an existing submission.csv
#   make audit         Run honeypot audit on submission.csv
#   make spot          Run spot-check (20 samples) on submission.csv
#   make clean         Remove submission.csv
#
# Usage:
#   make submit
#   make submit CANDIDATES=./sample_candidates.json   # override input file
# =============================================================================

PYTHON     ?= python
CANDIDATES ?= ./candidates.jsonl.gz
OUT        ?= ./submission.csv
TOPN       ?= 100

.PHONY: submit rank validate audit spot clean

## submit: Full pipeline — rank then validate. Stops on first failure.
submit: rank validate
	@echo ""
	@echo "============================================================"
	@echo " PASS — $(OUT) is valid and ready to submit."
	@echo "============================================================"

## rank: Run rank.py and produce submission.csv
rank:
	@echo "[1/2] Running ranker ..."
	$(PYTHON) rank.py --candidates $(CANDIDATES) --out $(OUT) --topn $(TOPN)

## validate: Validate an existing submission.csv
validate:
	@echo "[2/2] Validating $(OUT) ..."
	$(PYTHON) validate_submission.py $(OUT)

## audit: Honeypot audit on submission.csv
audit:
	$(PYTHON) scripts/audit_honeypots.py --submission $(OUT) --candidates $(CANDIDATES)

## spot: Spot-check 20 sampled candidates
spot:
	$(PYTHON) scripts/spot_check.py --submission $(OUT) --candidates $(CANDIDATES) --n 20

## clean: Remove generated output
clean:
	@rm -f $(OUT)
	@echo "Removed $(OUT)"
