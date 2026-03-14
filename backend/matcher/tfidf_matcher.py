import re
import json
from typing import Tuple, List, Dict
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from matcher.resume_skills import RESUME_TEXT, SKILLS, SYNONYMS


def _preprocess(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s+#.]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_matched_missing(job_text: str) -> Tuple[List[str], List[str]]:
    job_lower = job_text.lower()
    for phrase, replacement in SYNONYMS.items():
        job_lower = job_lower.replace(phrase, replacement)

    matched = []
    missing = []
    for skill in SKILLS:
        if skill in job_lower:
            matched.append(skill)
        else:
            missing.append(skill)
    return matched, missing


def score_job(job_description: str) -> Dict:
    job_clean    = _preprocess(job_description)
    resume_clean = _preprocess(RESUME_TEXT)

    vectorizer = TfidfVectorizer(
        ngram_range=(1, 2),
        stop_words="english",
        max_features=5000,
    )
    tfidf_matrix = vectorizer.fit_transform([resume_clean, job_clean])
    base_score   = float(cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0])

    matched, missing = _extract_matched_missing(job_description)
    boost       = min(len(matched) * 0.007, 0.20)
    final_score = min(base_score + boost, 1.0)

    return {
        "score":          round(final_score, 4),
        "matched_skills": matched,
        "missing_skills": missing,
    }


def score_jobs_batch(jobs: List[Dict]) -> List[Dict]:
    for job in jobs:
        result = score_job(job.get("description", ""))
        job["match_score"]    = result["score"]
        job["matched_skills"] = json.dumps(result["matched_skills"])
        job["missing_skills"] = json.dumps(result["missing_skills"])
    return jobs
