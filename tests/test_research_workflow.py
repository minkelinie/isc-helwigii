import pytest

from isc_helwigii.demo import seed_demo
from isc_helwigii.research import editions, run_method
from isc_helwigii.store import ResearchStore


def test_evidence_to_hypothesis_workflow(tmp_path):
    store = ResearchStore(tmp_path / "research.db")
    store.initialize()
    seed_demo(store)
    rows = editions(store)
    selected = rows[:2]
    for e in selected:
        for kind, payload in [
            ("motif", {"name": "flood", "edition_id": e["id"], "start": 0, "end": 5}),
            ("date", {"interval": [-2000, -1900]}),
            (
                "material",
                {
                    "method": "pXRF",
                    "laboratory": "L",
                    "calibration": "C",
                    "reference_group": "G",
                    "measurements": {"Fe": {"value": 1, "unit": "ppm", "uncertainty": 0.1}},
                },
            ),
            (
                "translation",
                {
                    "edition_id": e["id"],
                    "start": 0,
                    "end": len(e["text"]),
                    "text": "illustrative translation",
                    "target_language": "nl",
                },
            ),
        ]:
            a = store.annotate(
                e["artifact_id"], kind, payload, actor="author", evidence=[e["snapshot_id"]]
            )
            store.review(a, "accepted", actor="reviewer", reason="synthetic test")
    text = run_method(
        store, "text", {"left": selected[0]["id"], "right": selected[1]["id"]}, actor="a"
    )
    assert text["outputs"]["jaccard"] > 0
    ids = [e["artifact_id"] for e in selected]
    for method in ("material", "motif-network", "chronology"):
        assert (
            run_method(store, method, {"artifacts": ids}, actor="a")["outputs"]["status"]
            == "exploratory"
        )
    assert run_method(
        store,
        "translation-memory",
        {"query": selected[0]["text"], "language": "demo", "target_language": "nl"},
        actor="a",
    )["outputs"]["candidates"]
    assert (
        run_method(
            store, "evaluation", {"gold": {"a": "myth"}, "predicted": {"a": "myth"}}, actor="a"
        )["outputs"]["accuracy_all"]
        == 1
    )
    assert run_method(
        store, "split", {"records": [{"id": "a", "family": "f", "text": "t"}]}, actor="a"
    )["outputs"]["assignments"]
    assert len(store.runs()) == 7
    assert all(r["inputs"]["implementation"]["sha256"] for r in store.runs())
    with pytest.raises(ValueError):
        run_method(store, "text", {"left": "missing", "right": "missing"}, actor="a")


def test_material_and_hypothesis_validation(tmp_path):
    store = ResearchStore(tmp_path / "research.db")
    store.initialize()
    source = seed_demo(store)
    artifact = store.artifacts()[0]["id"]
    with pytest.raises(ValueError, match="method"):
        store.annotate(artifact, "material", {"measurements": {}}, actor="a", evidence=[source])
    with pytest.raises(ValueError):
        store.annotate(
            artifact, "hypothesis", {"statement": "ancestry"}, actor="a", evidence=[source]
        )
