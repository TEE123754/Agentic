# Phase 8 quality evaluation and matched comparisons

Phase 8 keeps three questions separate: whether the browser planner reaches a goal, whether evidence-backed detectors find seeded fixture defects, and whether any observed pattern generalizes to people. The frozen gate measures only the first two with a deterministic semantic-control harness on the owned local storefront. It makes no human conversion or churn claim.

## Frozen fixture batch

`configs/phase8-evaluation.json` fixes one impatient-mobile checkout-review journey, two seeds, and a `dead_button`/`healthy` pair for each seed. Pair one runs defective then healthy; pair two reverses the order. The coordinator creates a fresh fixture namespace, browser profile, and synthetic account for each run. Baseline and candidate comparison requires matching configuration hash, profile, journey, seed, model revision, detector policy, environment, and sampled session keys. A mismatch is rejected rather than quietly compared.

The report records raw requested/executed/eligible counts, completion change, resolved/new/persistent findings with confidence, inconclusive sessions, report status, broken evidence references, and both declared isolation and observed sentinel results. Inconclusive agent/protection outcomes never enter the synthetic abandonment denominator. The dashboard's Comparison tab reads only saved API evidence and refuses incompatible runs.

Quality thresholds from the existing implementation plan are 80% healthy fixture completion, 90% high-severity precision against frozen labels, 80% seeded-blocker detection, and 100% valid finding evidence references. They are initial release targets, not a claim about production traffic. The quality JSON/Markdown also reports full ready-report count and zero sentinel traffic. Thresholds are frozen before the gate; do not rerun the same samples until a favorable score appears.

## Mind2Web provenance and split handling

The offline loader pins [osunlp/Mind2Web revision `17ece8eb89862368edc0cc806acee6fca5163474`](https://huggingface.co/datasets/osunlp/Mind2Web/commit/17ece8eb89862368edc0cc806acee6fca5163474). The small training smoke shard `data/train/train_10.json` has SHA-256 `182542d7947b3fa9e90fc57a3d82d4d8f2997ca5a06664217720d7a78a956e33`. The protected `test.zip` archive has SHA-256 `8f5fbe72afab942fe97cdf7fb397e179885d89b5c16862288e9a14bc6d41ca89`. Both values come from the publisher's Hugging Face file and commit pages. The dataset is [CC BY 4.0](https://huggingface.co/datasets/osunlp/Mind2Web); attribute Deng et al., *Mind2Web: Towards a Generalist Agent for the Web* (2023).

The [publisher's repository](https://github.com/OSU-NLP-Group/Mind2Web) separates `train`, `test_task`, `test_website`, and `test_domain`. It asks users not to redistribute the unzipped test data or put it in model training corpora. The loader therefore accepts only an explicitly supplied local JSON shard and declared split, checks its SHA-256, projects action/candidate metadata in memory, and never sends examples to the fixture planner. It does not load pickle scores or fetch a site being evaluated. The remote gate downloads only the 28.4 MB pinned training shard into temporary runner storage, reports candidate/action accuracy for an **untuned lexical reference**, and uploads only aggregate counts. This diagnostic validates the adapter and scoring contract; it is **not** held-out Mind2Web agent accuracy. A later held-out run needs the separately obtained official test archive, an approved prediction producer, and no redistribution of examples.

## Human review rubric

Use the saved masked screenshot and before/after trajectory to score each proposed finding independently:

| Criterion | 0 | 1 | 2 |
|---|---|---|---|
| Observation fidelity | Contradicted or no evidence | Partly supported | Directly supported by linked state/action |
| Explanation plausibility | Invented cause | Plausible but uncertain | Clearly separated observation and inference |
| Recommendation usefulness | Irrelevant/unsafe | Generic but applicable | Concrete change tied to blocker |
| Verification clarity | No check | Vague check | Reproducible fixture criterion |

Record each human disposition and note as a new immutable report revision. Do not convert this rubric into a simulated churn percentage. Review from saved evidence only; do not reopen the tested application.

## Run and limitations

The manual `.github/workflows/phase8-evaluation.yml` performs the one remote fixture/benchmark gate on a free GitHub runner and retains synthetic summaries for seven days. `scripts/review_phase8.py` validates the saved quality report, comparisons, screenshot, and pinned-shard summary without target traffic. If a gate check fails, fix and rerun only the affected checks.

The fixed fixture is still a single controlled website; the semantic-control harness is not the production local Qwen planner. The Mind2Web shard is training data and cannot establish held-out generalization. Wider seeds, true model-driven navigation, external staging replicas with independently proven no-impact isolation, assistive-technology validation, and human behavioral calibration remain outstanding.
