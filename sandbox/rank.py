#!/usr/bin/env python3
"""
Redrob Hackathon — Candidate Ranker for "Senior AI Engineer — Founding Team"

Design summary
---------------
This is a transparent, rule-based hybrid scorer (no LLM calls, no GPU,
no network) built directly against the JD's stated priorities:

  1. Production experience with embeddings/retrieval systems (hard requirement)
  2. Production experience with vector DBs / hybrid search (hard requirement)
  3. Strong Python (hard requirement)
  4. Evaluation-framework experience: NDCG/MRR/MAP/A-B testing (hard requirement)
  5. Nice-to-haves: LoRA/QLoRA/PEFT, learning-to-rank, HR-tech, distributed
     systems, open source
  6. Explicit anti-patterns called out in the JD, each becoming a penalty:
       - title-chasers (short tenures + rapid title escalation)
       - framework enthusiasts / keyword-stuffers (skills without
         production evidence: near-zero duration_months, no matching
         career-history description)
       - career spent entirely at IT-services/consulting firms
       - CV/speech/robotics specialists without NLP/IR exposure
       - pure research background with no production deployment
       - "AI experience" = <12 months of LangChain-calls-OpenAI with no
         pre-LLM-era ML production history
  7. Location / logistics fit (Pune/Noida preferred, Tier-1 India okay,
     outside India = soft penalty, no visa sponsorship)
  8. Notice period preference (<=30 days ideal)
  9. Redrob behavioral signals as a *multiplier* on top of the skill/fit
     score — an unreachable/inactive perfect-on-paper candidate is
     down-weighted, not equally ranked.
 10. Honeypot detection — internally-inconsistent profiles (e.g. "expert"
     proficiency with 0 months used, years_of_experience wildly
     inconsistent with the sum of career_history durations) are flagged
     and excluded from the top 100 rather than special-cased into the
     score.

Everything is feature-engineered from fields that actually exist in
candidate_schema.json — no hallucinated signals, no keyword-only matching
on the skills list in isolation from career-history evidence.

Usage
-----
    python rank.py --candidates ./candidates.jsonl.gz --out ./submission.csv
    python rank.py --candidates ./sample_candidates.json --out ./submission.csv --topn 100

Runs in pure Python + stdlib (json, csv, gzip, re, datetime, math) so there
are no third-party dependencies to install and no risk of exceeding the
5-minute / 16GB / CPU-only / no-network constraints even on the full 100K
candidate pool.
"""

import argparse
import csv
import gzip
import json
import math
import re
from datetime import date, datetime

TODAY = date(2026, 7, 1)  # dataset reference date; override with --today if needed

# ---------------------------------------------------------------------------
# JD-derived vocabulary (Section: "Senior AI Engineer — Founding Team")
# ---------------------------------------------------------------------------

MUST_HAVE_RETRIEVAL_TERMS = [
    "embeddings", "embedding", "sentence-transformers", "sentence transformers",
    "openai embeddings", "bge", "e5", "retrieval", "semantic search",
    "dense retrieval", "vector search",
]
MUST_HAVE_VECTORDB_TERMS = [
    "pinecone", "weaviate", "qdrant", "milvus", "opensearch", "elasticsearch",
    "faiss", "vector database", "vector db", "hybrid search", "bm25",
]
MUST_HAVE_EVAL_TERMS = [
    "ndcg", "mrr", "map", "a/b test", "ab test", "a/b testing",
    "offline evaluation", "online evaluation", "evaluation framework",
    "ranking evaluation", "learning to rank",
]
PYTHON_TERMS = ["python"]

NICE_TO_HAVE_TERMS = [
    "lora", "qlora", "peft", "fine-tuning llms", "fine-tuning", "finetuning",
    "xgboost", "learning to rank", "ltr", "recommendation system",
    "distributed systems", "large-scale inference", "open source",
    "open-source",
]

RANKING_DOMAIN_TERMS = [
    "ranking", "retrieval", "search", "recommendation", "recommender",
    "matching", "embeddings", "vector", "nlp", "information retrieval", "ir",
]

CV_SPEECH_ROBOTICS_TERMS = [
    "computer vision", "cv", "image recognition", "object detection",
    "speech recognition", "asr", "robotics", "gans", "cnn",
]
NLP_IR_TERMS = [
    "nlp", "natural language", "retrieval", "search", "ranking",
    "recommendation", "information retrieval", "embeddings", "llm",
]

RECENT_LLM_WRAPPER_TERMS = ["langchain", "openai api", "llamaindex", "llama index"]
PRE_LLM_ML_TERMS = [
    "recommendation", "recommender", "ranking", "search", "retrieval",
    "feature engineering", "xgboost", "click-through", "ctr", "collaborative filtering",
]

CONSULTING_FIRMS = {
    "tcs", "tata consultancy services", "infosys", "wipro", "accenture",
    "cognizant", "capgemini",
}

RESEARCH_ONLY_TITLE_TERMS = [
    "research scientist", "research fellow", "postdoc", "post-doc", "phd researcher",
    "academic researcher",
]
RESEARCH_ORG_TERMS = ["university", "institute", "lab", "academy", "research center", "research centre"]

PRODUCT_COMPANY_SIZE_HINT = None  # not used directly; industry/title used instead

PREFERRED_LOCATIONS = {"pune", "noida"}
ACCEPTABLE_INDIA_LOCATIONS = {"hyderabad", "mumbai", "delhi", "delhi ncr", "gurgaon", "gurugram", "bangalore", "bengaluru"}

TITLE_SENIORITY_RANK = {
    "intern": 0, "junior": 1, "associate": 1, "engineer": 2, "senior": 3,
    "staff": 4, "principal": 5, "lead": 4, "director": 6, "vp": 7, "head": 6,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_date(s):
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def text_contains_any(text, terms):
    text = (text or "").lower()
    return any(t in text for t in terms)


def count_matches(text, terms):
    text = (text or "").lower()
    return sum(1 for t in terms if t in text)


def full_candidate_text(cand):
    """All free text on the profile, concatenated, for phrase search."""
    parts = [
        cand["profile"].get("headline", ""),
        cand["profile"].get("summary", ""),
        cand["profile"].get("current_title", ""),
    ]
    for job in cand.get("career_history", []):
        parts.append(job.get("title", ""))
        parts.append(job.get("description", ""))
    return " . ".join(parts).lower()


def skill_lookup(cand):
    """dict skill_name_lower -> skill record"""
    return {s["name"].strip().lower(): s for s in cand.get("skills", [])}


# ---------------------------------------------------------------------------
# Honeypot / integrity checks
# ---------------------------------------------------------------------------

def honeypot_flags(cand):
    flags = []

    # 1. "expert" proficiency with ~0 months used, repeated across several skills
    zero_duration_experts = [
        s for s in cand.get("skills", [])
        if s.get("proficiency") == "expert" and s.get("duration_months", 0) <= 1
    ]
    if len(zero_duration_experts) >= 3:
        flags.append("expert_zero_duration_skills")

    # 2. years_of_experience wildly inconsistent with sum of career_history durations
    total_months = sum(j.get("duration_months", 0) for j in cand.get("career_history", []))
    total_years = total_months / 12.0
    yoe = cand["profile"].get("years_of_experience", 0)
    if yoe > 0:
        ratio = total_years / yoe if yoe else 0
        if ratio > 2.0 or ratio < 0.35:
            flags.append("experience_years_inconsistent")

    # 3. Overlapping full-time roles (more than one is_current, or overlapping date ranges
    #    beyond a small buffer, across >=2 non-trivial roles)
    intervals = []
    for j in cand.get("career_history", []):
        sd = parse_date(j.get("start_date"))
        ed = parse_date(j.get("end_date")) or TODAY
        if sd:
            intervals.append((sd, ed))
    intervals.sort()
    overlap_months = 0
    for i in range(len(intervals) - 1):
        end_i = intervals[i][1]
        start_next = intervals[i + 1][0]
        if start_next < end_i:
            overlap_months += (end_i - start_next).days / 30.0
    if overlap_months > 6:
        flags.append("overlapping_roles")

    current_flags = [j for j in cand.get("career_history", []) if j.get("is_current")]
    if len(current_flags) > 1:
        flags.append("multiple_current_roles")

    # NOTE: we deliberately do NOT flag "education finished after career started"
    # as a honeypot signal — part-time MBAs / executive education / further
    # degrees taken years into a career are common and legitimate. Flagging
    # that pattern produces false positives on real candidates, not honeypots.

    return flags


# ---------------------------------------------------------------------------
# Feature scoring
# ---------------------------------------------------------------------------

def score_must_haves(cand, text, skills):
    """Returns (score 0-1, evidence dict) for the four hard requirements."""
    evidence = {}

    # Retrieval/embeddings: needs BOTH a skill entry with real duration AND
    # corroborating career-history language (guards against keyword stuffing)
    retrieval_skill_months = max(
        [skills[k].get("duration_months", 0) for k in skills if any(t in k for t in MUST_HAVE_RETRIEVAL_TERMS)],
        default=0,
    )
    retrieval_in_history = count_matches(text, MUST_HAVE_RETRIEVAL_TERMS)
    retrieval_score = min(1.0, (retrieval_skill_months / 24.0)) * 0.6 + min(1.0, retrieval_in_history / 3.0) * 0.4
    evidence["retrieval"] = round(retrieval_score, 3)

    vectordb_skill_months = max(
        [skills[k].get("duration_months", 0) for k in skills if any(t in k for t in MUST_HAVE_VECTORDB_TERMS)],
        default=0,
    )
    vectordb_in_history = count_matches(text, MUST_HAVE_VECTORDB_TERMS)
    vectordb_score = min(1.0, (vectordb_skill_months / 18.0)) * 0.6 + min(1.0, vectordb_in_history / 2.0) * 0.4
    evidence["vectordb"] = round(vectordb_score, 3)

    python_skill = skills.get("python")
    python_score = 0.0
    if python_skill:
        prof_weight = {"beginner": 0.3, "intermediate": 0.6, "advanced": 0.85, "expert": 1.0}.get(
            python_skill.get("proficiency"), 0.4
        )
        dur_weight = min(1.0, python_skill.get("duration_months", 0) / 36.0)
        python_score = 0.5 * prof_weight + 0.5 * dur_weight
    evidence["python"] = round(python_score, 3)

    eval_in_history = count_matches(text, MUST_HAVE_EVAL_TERMS)
    eval_skill_present = any(any(t in k for t in ["ndcg", "mrr", "map", "evaluation", "a/b"]) for k in skills)
    eval_score = min(1.0, eval_in_history / 2.0) * 0.7 + (0.3 if eval_skill_present else 0.0)
    evidence["eval_framework"] = round(eval_score, 3)

    must_have_score = (retrieval_score + vectordb_score + python_score + eval_score) / 4.0
    return must_have_score, evidence


def score_nice_to_haves(text, skills):
    hits = count_matches(text, NICE_TO_HAVE_TERMS)
    return min(1.0, hits / 4.0)


def score_anti_patterns(cand, text, skills):
    """Returns a multiplicative penalty factor in (0, 1]. 1.0 = no penalty."""
    penalty = 1.0
    reasons = []
    history = cand.get("career_history", [])

    # Consulting-only career (unless prior product-company experience exists)
    companies = [j.get("company", "").strip().lower() for j in history]
    industries = [j.get("industry", "").strip().lower() for j in history]
    all_consulting = bool(companies) and all(
        any(cf in c for cf in CONSULTING_FIRMS) or "it services" in ind
        for c, ind in zip(companies, industries)
    )
    if all_consulting:
        penalty *= 0.35
        reasons.append("consulting_only_career")

    # Title-chasers: >=3 roles, avg tenure < 18 months, AND seniority escalates
    if len(history) >= 3:
        avg_tenure = sum(j.get("duration_months", 0) for j in history) / len(history)
        seniority_seq = []
        for j in sorted(history, key=lambda x: parse_date(x.get("start_date")) or date.min):
            t = j.get("title", "").lower()
            rank = max([v for k, v in TITLE_SENIORITY_RANK.items() if k in t], default=2)
            seniority_seq.append(rank)
        escalating = all(b >= a for a, b in zip(seniority_seq, seniority_seq[1:])) and seniority_seq[-1] > seniority_seq[0]
        if avg_tenure < 18 and escalating:
            penalty *= 0.6
            reasons.append("title_chaser_pattern")

    # Framework enthusiast / keyword stuffer: many AI-sounding skills but near-zero
    # duration_months on most of them and no corroborating production evidence
    ai_skill_names = [k for k in skills if any(t in k for t in RANKING_DOMAIN_TERMS + NICE_TO_HAVE_TERMS)]
    if len(ai_skill_names) >= 5:
        shallow = sum(1 for k in ai_skill_names if skills[k].get("duration_months", 0) <= 3)
        production_evidence = count_matches(text, RANKING_DOMAIN_TERMS)
        if shallow / len(ai_skill_names) > 0.7 and production_evidence < 2:
            penalty *= 0.25
            reasons.append("keyword_stuffed_skills_no_evidence")

    # CV / speech / robotics specialist without NLP/IR exposure
    cv_hits = count_matches(text, CV_SPEECH_ROBOTICS_TERMS)
    nlp_hits = count_matches(text, NLP_IR_TERMS)
    if cv_hits >= 3 and nlp_hits == 0:
        penalty *= 0.45
        reasons.append("cv_speech_robotics_no_nlp_ir")

    # Pure research, no production deployment
    titles_lower = [j.get("title", "").lower() for j in history]
    orgs_lower = [j.get("company", "").lower() + " " + j.get("industry", "").lower() for j in history]
    research_titles = sum(1 for t in titles_lower if any(rt in t for rt in RESEARCH_ONLY_TITLE_TERMS))
    research_orgs = sum(1 for o in orgs_lower if any(ro in o for ro in RESEARCH_ORG_TERMS))
    if history and (research_titles + research_orgs) >= len(history):
        penalty *= 0.15
        reasons.append("pure_research_no_production")

    # Recent LangChain/OpenAI-wrapper-only AI experience, no pre-LLM ML depth
    wrapper_months = max(
        [skills[k].get("duration_months", 0) for k in skills if any(t in k for t in RECENT_LLM_WRAPPER_TERMS)],
        default=0,
    )
    deeper_ml_months = max(
        [skills[k].get("duration_months", 0) for k in skills if any(t in k for t in PRE_LLM_ML_TERMS)],
        default=0,
    )
    if wrapper_months > 0 and wrapper_months <= 12 and deeper_ml_months < 24 and count_matches(text, PRE_LLM_ML_TERMS) < 2:
        penalty *= 0.5
        reasons.append("langchain_wrapper_only_recent")

    return penalty, reasons


def score_location(cand):
    loc = (cand["profile"].get("location") or "").lower()
    country = (cand["profile"].get("country") or "").lower()
    willing = cand["redrob_signals"].get("willing_to_relocate", False)

    if any(p in loc for p in PREFERRED_LOCATIONS):
        return 1.0
    if country == "india":
        if any(a in loc for a in ACCEPTABLE_INDIA_LOCATIONS):
            return 0.85 if willing else 0.75
        return 0.6 if willing else 0.45
    # Outside India: the JD explicitly states no visa sponsorship.
    # willing_to_relocate=True does not solve a visa-sponsorship constraint,
    # so it earns no bonus here — the penalty is the same regardless.
    return 0.08


def score_experience_band(yoe):
    """Soft triangular preference for 5-9 years, not a hard cutoff."""
    if 5 <= yoe <= 9:
        return 1.0
    if yoe < 5:
        return max(0.0, 1.0 - (5 - yoe) * 0.18)
    return max(0.0, 1.0 - (yoe - 9) * 0.10)


def score_notice_period(days):
    if days <= 30:
        return 1.0
    if days <= 60:
        return 0.75
    if days <= 90:
        return 0.5
    return 0.3


def score_behavioral_multiplier(sig):
    """Multiplier in roughly [0.5, 1.15]. Rewards availability/engagement,
    penalizes inactive or unreachable candidates."""
    m = 1.0

    if not sig.get("open_to_work_flag", False):
        m *= 0.85

    last_active = parse_date(sig.get("last_active_date"))
    if last_active:
        days_inactive = (TODAY - last_active).days
        if days_inactive > 180:
            m *= 0.6
        elif days_inactive > 90:
            m *= 0.8
        elif days_inactive <= 14:
            m *= 1.05

    rrr = sig.get("recruiter_response_rate", 0)
    m *= 0.7 + 0.5 * rrr  # 0 -> 0.7x, 1 -> 1.2x

    icr = sig.get("interview_completion_rate", None)
    if icr is not None:
        m *= 0.85 + 0.25 * icr

    oar = sig.get("offer_acceptance_rate", -1)
    if oar is not None and oar >= 0:
        m *= 0.9 + 0.2 * oar

    verified_bonus = sum([
        sig.get("verified_email", False),
        sig.get("verified_phone", False),
        sig.get("linkedin_connected", False),
    ])
    m *= 1.0 + 0.02 * verified_bonus

    return max(0.4, min(1.2, m))


# ---------------------------------------------------------------------------
# Composite scoring
# ---------------------------------------------------------------------------

def score_candidate(cand):
    text = full_candidate_text(cand)
    skills = skill_lookup(cand)
    sig = cand["redrob_signals"]
    prof = cand["profile"]

    hp_flags = honeypot_flags(cand)

    must_have, mh_evidence = score_must_haves(cand, text, skills)
    nice_to_have = score_nice_to_haves(text, skills)
    anti_penalty, anti_reasons = score_anti_patterns(cand, text, skills)
    location = score_location(cand)
    exp_band = score_experience_band(prof.get("years_of_experience", 0))
    notice = score_notice_period(sig.get("notice_period_days", 60))

    # Capability must GATE the score, not just add to it — otherwise a
    # candidate with zero AI/ranking evidence can still rank highly on
    # location + notice period + behavioral activity alone. Logistics only
    # scales a capability score up or down within a bounded band; it can
    # never manufacture fit out of nothing.
    capability = 0.78 * must_have + 0.22 * nice_to_have
    logistics = 0.65 * location + 0.20 * exp_band + 0.15 * notice  # 0-1  (location raised: JD no-visa-sponsorship is near-disqualifying)
    logistics_multiplier = 0.55 + 0.45 * logistics  # bounded to [0.55, 1.0]

    fit_score = capability * logistics_multiplier
    fit_score *= anti_penalty

    behavioral_mult = score_behavioral_multiplier(sig)
    final_score = fit_score * behavioral_mult

    if hp_flags:
        final_score *= 0.02  # effectively removes honeypots from top 100

    return {
        "candidate_id": cand["candidate_id"],
        "score": final_score,
        "must_have": must_have,
        "nice_to_have": nice_to_have,
        "anti_penalty": anti_penalty,
        "anti_reasons": anti_reasons,
        "location": location,
        "exp_band": exp_band,
        "notice": notice,
        "behavioral_mult": behavioral_mult,
        "honeypot_flags": hp_flags,
        "mh_evidence": mh_evidence,
    }


# ---------------------------------------------------------------------------
# Reasoning generation (grounded strictly in candidate fields)
# ---------------------------------------------------------------------------

def build_reasoning(cand, result):
    """Build a reasoning string that varies structure based on the candidate's
    dominant signal so reviewers don't see 100 near-identical templates."""
    prof = cand["profile"]
    sig = cand["redrob_signals"]
    country = (prof.get("country") or "").lower()
    loc = prof.get("location", "")
    title = prof["current_title"]
    yoe = prof["years_of_experience"]
    rrr = sig.get("recruiter_response_rate")
    open_to_work = sig.get("open_to_work_flag", True)

    ev = result["mh_evidence"]
    strong_bits = [k for k, v in ev.items() if v >= 0.6]
    weak_bits = [k for k, v in ev.items() if v < 0.3]
    anti = result["anti_reasons"]

    anti_labels = {
        "consulting_only_career":             "consulting-only career (IT-services firms throughout)",
        "title_chaser_pattern":               "title-chaser pattern (short tenures, rapid escalation)",
        "keyword_stuffed_skills_no_evidence": "keyword-stuffed skills without career-history evidence",
        "cv_speech_robotics_no_nlp_ir":       "CV/speech background with no NLP or IR exposure",
        "pure_research_no_production":        "research-only track record, no production deployment",
        "langchain_wrapper_only_recent":      "LangChain/OpenAI-wrapper AI experience only, no pre-LLM ML depth",
    }

    profile_str = f"{title}, {yoe:.1f} yrs exp"
    skills_str  = ("covers " + ", ".join(strong_bits)) if strong_bits else "limited JD skill coverage"
    gap_str     = ("gaps: " + ", ".join(weak_bits)) if weak_bits and len(weak_bits) < 4 else ""

    # ---- Lead with the most disqualifying signal first ----

    # Anti-pattern disqualifier
    if anti:
        label = anti_labels.get(anti[0], anti[0])
        parts = [f"Penalised — {label}",
                 profile_str, skills_str]
        if gap_str:
            parts.append(gap_str)
        parts.append(f"location: {loc}")
        if rrr is not None:
            parts.append(f"responsiveness {rrr:.2f}")

    # Overseas candidate — lead with the visa constraint
    elif country != "india":
        parts = [f"Outside India ({loc}) — no visa sponsorship per JD",
                 profile_str, skills_str]
        if gap_str:
            parts.append(gap_str)
        if rrr is not None:
            parts.append(f"response rate {rrr:.2f}")

    # Strong all-round JD fit — lead with the match
    elif len(strong_bits) >= 3:
        parts = [f"Strong JD fit: {profile_str}",
                 "production evidence on " + ", ".join(strong_bits),
                 f"based in {loc}"]
        if gap_str:
            parts.append(gap_str)
        if rrr is not None:
            parts.append(f"response rate {rrr:.2f}")
        if not open_to_work:
            parts.append("not currently open to work")

    # Partial fit — standard order but field-first
    else:
        parts = [profile_str, skills_str]
        if gap_str:
            parts.append(gap_str)
        parts.append(f"location: {loc}")
        if rrr is not None:
            parts.append(f"response rate {rrr:.2f}")
        if not open_to_work:
            parts.append("not open to work")

    reasoning = "; ".join(parts) + "."
    return reasoning[:400]


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------

def load_candidates(path):
    if path.endswith(".jsonl.gz"):
        with gzip.open(path, "rt", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield json.loads(line)
    elif path.endswith(".jsonl"):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield json.loads(line)
    elif path.endswith(".json"):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            for c in data:
                yield c
    else:
        raise ValueError(f"Unsupported file extension for {path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates", required=True, help="Path to candidates.jsonl / .jsonl.gz / .json")
    ap.add_argument("--out", required=True, help="Output CSV path")
    ap.add_argument("--topn", type=int, default=100)
    args = ap.parse_args()

    results = []
    honeypot_count = 0
    total = 0
    for cand in load_candidates(args.candidates):
        total += 1
        try:
            r = score_candidate(cand)
        except Exception as e:
            # never let one malformed record crash the whole run
            continue
        if r["honeypot_flags"]:
            honeypot_count += 1
        r["_cand"] = cand
        results.append(r)

    print(f"Scored {total} candidates ({honeypot_count} honeypot-flagged).")

    results.sort(key=lambda r: (-r["score"], r["candidate_id"]))
    top = results[: args.topn]

    # BUG FIX: round(score, 4) can collapse genuinely near-equal full-float scores
    # into the same displayed value, creating an apparent tie that fails the
    # validator's tie-break check even though the internal sort was correct.
    # Fix: round to 6 decimal places, then re-sort by the *rounded* score so
    # the displayed order is guaranteed consistent with what the validator checks.
    # If two candidates are truly identical at 6 dp, candidate_id asc wins.
    for r in top:
        r["_score_out"] = round(r["score"], 6)
    top.sort(key=lambda r: (-r["_score_out"], r["candidate_id"]))

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["candidate_id", "rank", "score", "reasoning"])
        for i, r in enumerate(top, start=1):
            reasoning = build_reasoning(r["_cand"], r)
            writer.writerow([r["candidate_id"], i, r["_score_out"], reasoning])

    print(f"Wrote top {len(top)} candidates to {args.out}")


if __name__ == "__main__":
    main()
