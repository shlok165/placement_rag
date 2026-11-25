# Evaluation

Run `make eval` for everything that is free. Tables between markers are written by the scripts; the
text around them is written by hand.

## What is measured

The corpus is synthetic. A seeded script builds postings from templates, with invented companies,
and labels come from the generator's hidden attributes (role family, sector, place), never from a
ranker. Real postings are messier, so read these numbers as a way to compare configurations, not as
a forecast of live quality.

- **hit@k**: share of queries with at least one relevant posting in the top k.
- **MRR**: mean of one over the rank of the first relevant posting.
- **nDCG@10**: ranking quality of the first ten, with binary relevance.
- **recall@50**: share of relevant postings among the candidates handed to the re-ranker.

## How the weights were chosen

Every other case went into a development half, and the weights in
`backend/app/search/weights.toml` are the sweep rows with the highest MRR + nDCG@10 on that half.
The held-out half was not used to choose weights, but its scores were visible while the keyword
ranker was being fixed, so treat it as a sanity check and not as a blind test. With about 38 cases
per half, one case moves hit@k by 2.6 points.

## What the numbers say

- **Hybrid does not win everywhere.** Against semantic search alone it finds more of the relevant
  postings (recall@50) and orders the first ten better (nDCG@10), but it puts the first relevant
  posting slightly lower (hit@1, MRR). Most cases are paraphrases, which suits embeddings, and
  keyword matches on shared words add noise at the very top. Hybrid is still the default because
  recall at the candidate stage limits everything after it, and because exact names and skills
  are what keyword search catches.
- **Keyword search alone is the weakest.** Postgres ranking has no inverse document frequency. The
  first version let words such as "internship" decide the order. Weighting each term by rarity
  raised keyword-only nDCG@10 from 0.535 to 0.545 and MRR from 0.627 to 0.649.
- **Personal re-ranking helps most on vague queries**, where the profile carries the meaning. On
  topic and constraint queries it trades a little rank quality for fit, because those labels ignore
  the student.
- **Circularity.** Labels in the personal slice use the same kind of facts as the re-ranker (type,
  place, skills), so its gain there is partly built in. The topic and constraint slices do not have
  this problem.

## Regression guard

CI runs `python -m evals.retrieval --check` and fails when hit@5 of the full pipeline drops below
`evals/baseline.json`.

## Retrieval results

<!-- retrieval:start -->
156 synthetic postings, 77 labelled query and profile pairs. No LLM calls.

### Held-out half (38 cases, not used to choose weights)

| Configuration | hit@1 | hit@3 | hit@5 | MRR | nDCG@10 | recall@50 |
|---|---|---|---|---|---|---|
| Semantic only | 0.711 | 0.921 | 0.921 | 0.806 | 0.669 | 0.888 |
| Keyword only | 0.500 | 0.579 | 0.632 | 0.562 | 0.476 | 0.752 |
| Hybrid | 0.632 | 0.816 | 0.895 | 0.742 | 0.675 | 0.897 |
| Hybrid + personal re-rank | 0.711 | 0.842 | 0.947 | 0.801 | 0.701 | 0.897 |

### All 77 cases

| Configuration | hit@1 | hit@3 | hit@5 | MRR | nDCG@10 | recall@50 |
|---|---|---|---|---|---|---|
| Semantic only | 0.740 | 0.883 | 0.896 | 0.810 | 0.660 | 0.898 |
| Keyword only | 0.584 | 0.662 | 0.740 | 0.649 | 0.545 | 0.768 |
| Hybrid | 0.701 | 0.831 | 0.870 | 0.780 | 0.690 | 0.924 |
| Hybrid + personal re-rank | 0.753 | 0.883 | 0.961 | 0.836 | 0.739 | 0.924 |

### Slice: constraint

| Configuration | hit@1 | hit@3 | hit@5 | MRR | nDCG@10 | recall@50 |
|---|---|---|---|---|---|---|
| Semantic only | 0.800 | 0.950 | 0.950 | 0.883 | 0.754 | 0.917 |
| Keyword only | 0.750 | 0.750 | 0.850 | 0.777 | 0.620 | 0.912 |
| Hybrid | 0.800 | 0.950 | 0.950 | 0.874 | 0.797 | 0.964 |
| Hybrid + personal re-rank | 0.800 | 0.850 | 0.950 | 0.858 | 0.728 | 0.964 |

### Slice: personal

| Configuration | hit@1 | hit@3 | hit@5 | MRR | nDCG@10 | recall@50 |
|---|---|---|---|---|---|---|
| Semantic only | 0.458 | 0.708 | 0.750 | 0.582 | 0.413 | 0.784 |
| Keyword only | 0.208 | 0.417 | 0.542 | 0.359 | 0.290 | 0.537 |
| Hybrid | 0.417 | 0.583 | 0.667 | 0.531 | 0.430 | 0.797 |
| Hybrid + personal re-rank | 0.625 | 0.792 | 0.917 | 0.735 | 0.668 | 0.797 |

### Slice: topic

| Configuration | hit@1 | hit@3 | hit@5 | MRR | nDCG@10 | recall@50 |
|---|---|---|---|---|---|---|
| Semantic only | 0.909 | 0.970 | 0.970 | 0.932 | 0.782 | 0.969 |
| Keyword only | 0.758 | 0.788 | 0.818 | 0.783 | 0.684 | 0.849 |
| Hybrid | 0.849 | 0.939 | 0.970 | 0.905 | 0.815 | 0.992 |
| Hybrid + personal re-rank | 0.818 | 0.970 | 1.000 | 0.896 | 0.798 | 0.992 |

### Fusion weight sweep (hybrid, no re-rank, development half)

| Configuration | hit@1 | hit@3 | hit@5 | MRR | nDCG@10 | recall@50 |
|---|---|---|---|---|---|---|
| RRF k=10, semantic 1.0, keyword 1.0 | 0.692 | 0.821 | 0.872 | 0.775 | 0.702 | 0.915 |
| RRF k=10, semantic 1.0, keyword 0.5 | 0.769 | 0.846 | 0.846 | 0.818 | 0.705 | 0.951 |
| RRF k=10, semantic 1.0, keyword 0.25 | 0.769 | 0.846 | 0.846 | 0.819 | 0.684 | 0.935 |
| RRF k=10, semantic 0.5, keyword 1.0 | 0.692 | 0.795 | 0.897 | 0.763 | 0.680 | 0.896 |
| RRF k=60, semantic 1.0, keyword 1.0 | 0.692 | 0.795 | 0.872 | 0.773 | 0.684 | 0.915 |
| RRF k=60, semantic 1.0, keyword 0.5 | 0.744 | 0.872 | 0.872 | 0.810 | 0.690 | 0.907 |
| RRF k=60, semantic 1.0, keyword 0.25 | 0.769 | 0.846 | 0.872 | 0.822 | 0.692 | 0.907 |
| RRF k=60, semantic 0.5, keyword 1.0 | 0.692 | 0.795 | 0.897 | 0.762 | 0.678 | 0.869 |
| Weighted sum, semantic 1.0, keyword 1.0 | 0.769 | 0.846 | 0.872 | 0.811 | 0.707 | 0.956 |
| Weighted sum, semantic 1.0, keyword 0.5 | 0.769 | 0.846 | 0.846 | 0.815 | 0.695 | 0.956 |
| Weighted sum, semantic 1.0, keyword 0.25 | 0.744 | 0.846 | 0.872 | 0.807 | 0.676 | 0.953 |
| Weighted sum, semantic 0.5, keyword 1.0 | 0.769 | 0.795 | 0.872 | 0.806 | 0.703 | 0.950 |

### Re-rank weight sweep (hybrid + personal re-rank, development half)

| Configuration | hit@1 | hit@3 | hit@5 | MRR | nDCG@10 | recall@50 |
|---|---|---|---|---|---|---|
| relevance 0.45, skills 0.1, preferences 0.2 | 0.821 | 0.897 | 0.923 | 0.870 | 0.768 | 0.951 |
| relevance 0.45, skills 0.2, preferences 0.2 | 0.795 | 0.897 | 0.949 | 0.863 | 0.776 | 0.951 |
| relevance 0.45, skills 0.2, preferences 0.3 | 0.795 | 0.923 | 0.974 | 0.871 | 0.776 | 0.951 |
| relevance 0.45, skills 0.3, preferences 0.2 | 0.744 | 0.923 | 0.949 | 0.841 | 0.764 | 0.951 |
| relevance 0.7, skills 0.1, preferences 0.2 | 0.795 | 0.872 | 0.923 | 0.849 | 0.754 | 0.951 |
| relevance 0.7, skills 0.2, preferences 0.2 | 0.821 | 0.872 | 0.923 | 0.867 | 0.766 | 0.951 |
| relevance 0.7, skills 0.2, preferences 0.3 | 0.821 | 0.897 | 0.923 | 0.875 | 0.768 | 0.951 |
| relevance 0.7, skills 0.3, preferences 0.2 | 0.795 | 0.897 | 0.923 | 0.858 | 0.774 | 0.951 |
| relevance 1.0, skills 0.1, preferences 0.2 | 0.769 | 0.846 | 0.897 | 0.832 | 0.736 | 0.951 |
| relevance 1.0, skills 0.2, preferences 0.2 | 0.769 | 0.846 | 0.923 | 0.833 | 0.750 | 0.951 |
| relevance 1.0, skills 0.2, preferences 0.3 | 0.795 | 0.872 | 0.923 | 0.854 | 0.758 | 0.951 |
| relevance 1.0, skills 0.3, preferences 0.2 | 0.795 | 0.872 | 0.923 | 0.850 | 0.755 | 0.951 |
| relevance 1.5, skills 0.1, preferences 0.2 | 0.769 | 0.846 | 0.897 | 0.825 | 0.731 | 0.951 |
| relevance 1.5, skills 0.2, preferences 0.2 | 0.769 | 0.846 | 0.897 | 0.827 | 0.739 | 0.951 |
| relevance 1.5, skills 0.2, preferences 0.3 | 0.769 | 0.846 | 0.897 | 0.832 | 0.737 | 0.951 |
| relevance 1.5, skills 0.3, preferences 0.2 | 0.769 | 0.846 | 0.897 | 0.828 | 0.740 | 0.951 |
<!-- retrieval:end -->
