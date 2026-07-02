# Sandbox — Streamlit Demo for India Runs / Redrob Hackathon

Interactive browser demo satisfying **submission_spec.md §10.5** — evaluators
can upload a small candidate sample (≤ 100 candidates) or use the bundled
50-candidate demo to run the scoring pipeline end-to-end in the browser.

> **Note**: This sandbox is intentionally limited to ≤ 100 candidates.
> For the full 100 K-candidate production run, use `rank.py` directly from
> the repo root (see the main [README](../README.md)).

---

## Files

```
sandbox/
├── app.py                   ← Streamlit UI (entry point for Streamlit Cloud)
├── rank.py                  ← Scoring engine — byte-for-byte copy of ../rank.py
├── sample_candidates.json   ← Bundled 50-candidate demo set
├── requirements.txt         ← streamlit, pandas
└── README.md                ← This file
```

> **Keeping rank.py in sync**: `sandbox/rank.py` must remain identical to
> `../rank.py`. If you update the main scoring engine, re-copy it:
>
> ```bash
> cp rank.py sandbox/rank.py
> # verify:
> diff rank.py sandbox/rank.py && echo "OK — files are identical"
> ```

---

## Run locally

```bash
cd sandbox
pip install -r requirements.txt
streamlit run app.py
```

Then open http://localhost:8501 in your browser.

To use a non-default port (e.g. for CI / headless checks):

```bash
streamlit run app.py --server.headless true --server.port 8765
# In another terminal:
curl -s -o /dev/null -w "%{http_code}" http://localhost:8765
# Expected: 200
```

---

## Deploy to Streamlit Community Cloud

1. Push this repo to GitHub (already done — see repo root).
2. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with
   your GitHub account.
3. Click **New app** and fill in:
   - **Repository**: `Srikar-segmentation-fault/Indiaruns-project`
   - **Branch**: `main`
   - **Main file path**: `sandbox/app.py`   ← point here
4. Click **Deploy**. No secrets or environment variables are needed.

The app will be live at a URL like:
`https://<your-username>-indiaruns-project-sandbox-app-<hash>.streamlit.app`

Copy that URL into `submission_metadata.yaml` → `sandbox_link`.

---

## What the sandbox does NOT do

- It does **not** handle the full 100 K-candidate pool (upload limit: 100
  candidates; use the CLI for the production run).
- It does **not** make any network calls — scoring is fully local, matching
  the compute constraints in submission_spec.md.
- It does **not** require authentication, rate-limiting, or any other
  production hardening — it is a hackathon evaluation tool only.
