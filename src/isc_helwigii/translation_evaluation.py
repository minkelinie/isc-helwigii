"""Reference comparisons, explicitly separate from expert translation validation."""

import hashlib
import json

from isc_helwigii.local_translation import canonical_language, translate_text
from isc_helwigii.store import required


def evaluate_translation_set(dataset, *, model_dir):
    """Compare every supplied pair; refused inputs remain in metric denominators."""
    if not isinstance(dataset, dict) or not isinstance(dataset.get("dataset"), dict):
        raise ValueError("A dataset provenance object is required.")
    for field in ("name", "source_url", "license", "split", "training_overlap"):
        required(dataset["dataset"].get(field), f"dataset.{field}")
    examples = dataset.get("examples")
    if not isinstance(examples, list) or not 1 <= len(examples) <= 1000:
        raise ValueError("Provide 1–1000 reference examples.")
    ids, sources = set(), set()
    for example in examples:
        if not isinstance(example, dict):
            raise ValueError("Each reference example must be an object.")
        for field in ("id", "text", "reference", "source_url", "license"):
            required(example.get(field), field)
        language = canonical_language(example.get("source_language"))
        key = (language, example["text"])
        if example["id"] in ids or key in sources:
            raise ValueError("Duplicate example ID or source passage in evaluation set.")
        ids.add(example["id"])
        sources.add(key)
    try:
        from sacrebleu.metrics import BLEU, CHRF
    except ImportError as exc:
        raise ValueError(
            "Install reference metrics with pip install 'isc-helwigii[evaluation]'."
        ) from exc
    rows = []
    model = None
    for example in examples:
        row = {**example, "source_language": canonical_language(example["source_language"])}
        try:
            result = translate_text(
                example["text"],
                model_dir=model_dir,
                source_language=example["source_language"],
                input_format=example.get("input_format", "transliteration"),
            )
        except ValueError as exc:
            row.update(prediction="", status="abstained", reason=str(exc))
        else:
            model = result["model"]
            row.update(prediction=result["text"], status="generated", inference=result)
        rows.append(row)
    scores = {}
    for language in sorted({row["source_language"] for row in rows}):
        selected = [row for row in rows if row["source_language"] == language]
        metrics = {}
        for name, metric in (("BLEU", BLEU()), ("chrF", CHRF())):
            score = metric.corpus_score(
                [r["prediction"] for r in selected], [[r["reference"] for r in selected]]
            )
            metrics[name] = {"score": score.score, "signature": str(metric.get_signature())}
        scores[language] = {
            "count": len(selected),
            "generated": sum(r["status"] == "generated" for r in selected),
            "abstained": sum(r["status"] == "abstained" for r in selected),
            "metrics": metrics,
        }
    return {
        "method": "reference-translation-comparison-v1",
        "dataset": dataset["dataset"],
        "dataset_sha256": hashlib.sha256(
            json.dumps(dataset, ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest(),
        "model": model,
        "scores_by_language": scores,
        "examples": rows,
        "limitation": "Text similarity to the supplied references, not expert accuracy. "
        "All examples are scored, with empty predictions for abstentions. "
        "A small convenience sample and unknown training overlap cannot establish generalization.",
    }
