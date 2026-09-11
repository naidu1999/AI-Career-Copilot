# IEEE research roadmap

Karna OS v0.4 is an engineering prototype, not yet a publishable scientific result.
Matching Engine v3 is deterministic and inspectable, but its weights and thresholds
have not yet been validated on a consented labeled dataset.
The defensible research contribution should be an evidence-grounded, constraint-aware
career matching method that reduces ineligible recommendations and unsupported claims.

## Proposed evaluation

- Research question: Does evidence verification plus hard eligibility filtering improve
  job-ranking quality and trust compared with keyword-only and embedding baselines?
- Baselines: TF-IDF/BM25, skill Jaccard, sentence embeddings, and an LLM-only ranker.
- Metrics: Precision@5, NDCG@10, eligibility-violation rate, unsupported-claim rate,
  calibration error, task completion time, and user-rated explanation usefulness.
- Ablations: remove evidence verification, location constraints, seniority/experience,
  and reason generation one at a time.
- Dataset: consented and de-identified resumes/jobs with expert relevance labels;
  document geography, career level, class balance, and labeling agreement.
- Reproducibility: freeze dataset splits, parser/matcher versions, prompts, model IDs,
  seeds, hardware, and dependency lockfile. Report confidence intervals and failures.
- Ethics: minimize personal data, measure geographic and career-level disparities,
  provide human review, and never automate job submission without explicit consent.

Do not invent results. Collect the labeled benchmark and run the preregistered evaluation
before writing claims, tables, or an abstract.
