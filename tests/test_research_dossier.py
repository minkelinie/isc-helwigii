import json
import sqlite3
from contextlib import closing

import pytest

from isc_helwigii.cli import main
from isc_helwigii.research import editions, run_method
from isc_helwigii.store import ResearchStore


@pytest.fixture
def corpus(tmp_path):
    store = ResearchStore(tmp_path / "project.db")
    store.initialize()
    records = [
        {"external_id": "A", "text": "prefix a₂ b suffix", "language": "sumerian"},
        {"external_id": "B", "text": "a₂ b", "language": "sumerian"},
        {"external_id": "C", "text": "a₂ c", "language": "sumerian"},
        {"external_id": "D", "text": "a₂ b", "language": "akkadian"},
        {"external_id": "E", "text": "x [...]", "language": "sumerian"},
        {"external_id": "F", "text": "a₂ b", "language": "unknown"},
    ]
    store.import_records(json.dumps(records).encode(), records, source="fixture", license="private")
    return store, {e["external_id"]: e for e in editions(store)}


def test_dossier_searches_corpus_and_freezes_evidence(corpus):
    store, rows = corpus
    e = rows["B"]
    annotation = store.annotate(
        e["artifact_id"],
        "translation",
        {
            "edition_id": e["id"],
            "start": 0,
            "end": 4,
            "text": "illustratieve vertaling",
            "target_language": "nl",
        },
        actor="expert",
        evidence=[e["id"]],
    )
    store.review(annotation, "accepted", actor="expert", reason="software fixture")
    result = run_method(
        store,
        "research-dossier",
        {
            "edition_id": rows["A"]["id"],
            "start": 7,
            "end": 11,
            "limit": 2,
        },
        actor="researcher",
    )
    output = result["outputs"]
    assert output["query"]["text"] == "a₂ b"
    assert [r["external_id"] for r in output["parallels"]] == ["B", "C"]
    assert output["parallels"][0]["jaccard"] == 1
    assert output["parallels"][1]["shared_tokens"] == ["a₂"]
    assert output["parallels"][0]["snapshot_id"] == e["snapshot_id"]
    assert output["translation_memory"]["candidates"][0]["id"] == annotation
    assert output["corpus"]["edition_count"] == 6
    run = store.runs()[0]
    assert run["inputs"]["corpus"]["snapshot_ids"] == [e["snapshot_id"]]
    assert run["inputs"]["implementation"]["sha256"]
    # Later imports cannot silently change the saved run or its search scope.
    store.import_records(
        b"new",
        [{"external_id": "G", "text": "a₂ b", "language": "sumerian"}],
        source="later",
        license="private",
    )
    assert store.runs()[0] == run


def test_search_excludes_other_editions_of_same_artifact(corpus):
    store, rows = corpus
    store.import_records(
        b"alternate",
        [{"external_id": "A", "text": "a₂ b", "language": "sumerian"}],
        source="fixture",
        license="private",
    )
    result = run_method(store, "research-dossier", {"edition_id": rows["A"]["id"]}, actor="r")
    assert all(r["artifact_id"] != rows["A"]["artifact_id"] for r in result["outputs"]["parallels"])


@pytest.mark.parametrize("key", ["E", "F"])
def test_dossier_abstains_without_readable_text_or_language(corpus, key):
    store, rows = corpus
    output = run_method(store, "research-dossier", {"edition_id": rows[key]["id"]}, actor="r")[
        "outputs"
    ]
    assert output["status"] == "abstained"
    assert output["parallels"] == []
    assert output["translation_memory"]["candidates"] == []


@pytest.mark.parametrize(
    "parameters",
    [{"start": -1}, {"end": 1000}, {"end": 0}, {"limit": 0}, {"limit": 101}, {"limit": True}],
)
def test_dossier_rejects_invalid_selection_without_saving(corpus, parameters):
    store, rows = corpus
    with pytest.raises(ValueError):
        run_method(
            store, "research-dossier", {"edition_id": rows["A"]["id"], **parameters}, actor="r"
        )
    assert store.runs() == []


def test_cli_prepares_dossier_without_json_request(corpus, capsys):
    store, rows = corpus
    assert (
        main(
            [
                "prepare",
                str(store.path),
                rows["A"]["id"],
                "--actor",
                "r",
                "--start",
                "7",
                "--end",
                "11",
                "--limit",
                "1",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["outputs"]["parallels"][0]["external_id"] == "B"


def test_translation_candidates_are_bounded_and_rejected_reviews_excluded(corpus):
    store, rows = corpus
    e = rows["B"]
    for i in range(8):
        annotation = store.annotate(
            e["artifact_id"],
            "translation",
            {
                "edition_id": e["id"],
                "start": 0,
                "end": 4,
                "text": f"translation {i}",
                "target_language": "nl",
            },
            actor="author",
            evidence=[e["id"]],
        )
        store.review(annotation, "accepted", actor="reviewer", reason="fixture")
        if i == 7:
            store.review(annotation, "rejected", actor="reviewer", reason="corrected")
    output = run_method(store, "research-dossier", {"edition_id": e["id"], "limit": 2}, actor="r")[
        "outputs"
    ]
    memory = output["translation_memory"]
    assert len(memory["candidates"]) == 2
    assert memory["matched_count"] == 7
    assert memory["truncated"] is True
    assert all(c["review"]["decision"] == "accepted" for c in memory["candidates"])


def test_dossier_translations_share_the_corpus_snapshot(corpus, monkeypatch):
    from isc_helwigii import dossier

    store, rows = corpus
    with closing(sqlite3.connect(store.path)) as con:
        con.execute("PRAGMA journal_mode=WAL")
    original = dossier.collect_translations

    def concurrent_import(con, query, limit):
        store.import_records(
            b"concurrent",
            [{"external_id": "NEW", "text": "a₂ b", "language": "sumerian"}],
            source="new",
            license="private",
        )
        artifact = store.artifacts("NEW")[0]
        e = store.dossier(artifact["id"])["editions"][0]
        a = store.annotate(
            artifact["id"],
            "translation",
            {
                "edition_id": e["id"],
                "start": 0,
                "end": 4,
                "text": "not in frozen scope",
                "target_language": "nl",
            },
            actor="a",
            evidence=[e["id"]],
        )
        store.review(a, "accepted", actor="r", reason="fixture")
        return original(con, query, limit)

    monkeypatch.setattr(dossier, "collect_translations", concurrent_import)
    output = run_method(store, "research-dossier", {"edition_id": rows["B"]["id"]}, actor="r")[
        "outputs"
    ]
    assert output["corpus"]["edition_count"] == 6
    assert output["translation_memory"]["candidates"] == []
    assert store.statistics()["editions"] == 7


def test_ui_prepares_and_retains_result_across_reruns(corpus, monkeypatch):
    pytest.importorskip("streamlit")
    from pathlib import Path

    from streamlit.testing.v1 import AppTest

    from isc_helwigii import ui

    store, rows = corpus
    monkeypatch.setenv("ISC_HELWIGII_PROJECT", str(store.path))
    app = AppTest.from_file(str(Path(ui.__file__))).run()
    app.sidebar.radio[0].set_value("Onderzoeksdossier").run()
    app.text_area(key="dossier_passage_" + rows["A"]["id"]).set_value("a₂ b").run()
    app.button(key="prepare_dossier").click().run()
    assert not app.exception and not app.error
    assert any("B" in str(item.label) for item in app.expander)
    app.run()
    assert len(store.runs()) == 1
    assert any("B" in str(item.label) for item in app.expander)
