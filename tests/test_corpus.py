import json
import unicodedata

import pytest

from isc_helwigii.cli import main
from isc_helwigii.corpus import audit_corpus, prepare_reference_set, write_json_export
from isc_helwigii.store import ResearchStore


def _artifact(store, source, external_id):
    return next(
        row["id"]
        for row in store.artifacts()
        if row["source"] == source and row["external_id"] == external_id
    )


def _accept_category(store, artifact_id, edition_id, axis, label, *, supersedes=None):
    annotation_id = store.annotate(
        artifact_id,
        "category",
        {"axis": axis, "label": label},
        actor="editor",
        origin="observed",
        evidence=[edition_id],
        supersedes=supersedes,
    )
    store.review(annotation_id, "accepted", actor="reviewer", reason="checked")
    return annotation_id


def test_audit_is_complete_read_only_and_deterministic(tmp_path):
    store = ResearchStore(tmp_path / "project.db")
    store.initialize()
    store.import_records(
        b"a-v1",
        [
            {
                "external_id": "A",
                "language": "sux",
                "text": unicodedata.normalize("NFD", "ŠU₂"),
                "legacy_metadata": {"period": "Ur III", "provenience": "Ur"},
            },
            {"external_id": "DIGIT", "language": "sux", "text": "šu₃"},
            {"external_id": "NULL", "language": None, "text": "a-na"},
            {"external_id": "BLANK", "language": " ", "text": ""},
            {"external_id": "PLACEHOLDER", "language": "unknown", "text": "[...]"},
            {
                "external_id": "MALFORMED",
                "language": "akkadian",
                "text": "a-na",
                "period": {"unexpected": "object"},
                "legacy_metadata": "not-an-object",
            },
        ],
        source="source-one",
        license="private/unverified",
    )
    store.import_records(
        b"a-v2",
        [{"external_id": "A", "language": "sumerian", "text": "changed edition"}],
        source="source-one",
        license="private/unverified",
    )
    store.import_records(
        b"other",
        [
            {"external_id": "A", "language": "sux", "text": "šu₂"},
            {"external_id": "OTHER", "language": "akk", "text": "šu2"},
        ],
        source="source-two",
        license="CC0 stated by importer",
        adapter="native-v1",
    )
    before = store.path.read_bytes()

    first = audit_corpus(store)

    assert first == audit_corpus(store)
    assert first["method"] == "corpus-audit-v1"
    assert first["counts"] == {
        "artifacts": 8,
        "editions": 9,
        "snapshots": 3,
        "issues": first["counts"]["issues"],
        "issue_rows": first["counts"]["issue_rows"],
    }
    assert len(first["sources"]) == 3
    assert all("raw" not in source for source in first["sources"])
    assert first["distributions"]["language"]["sumerian"] == 1
    assert first["distributions"]["language"]["[unknown]"] == 3
    by_external = {}
    for row in first["editions"]:
        by_external.setdefault((row["source"], row["external_id"]), []).append(row)
    first_a = by_external[("source-one", "A")][0]
    assert first_a["metadata"]["period"] == "Ur III"
    assert first_a["metadata_paths"]["period"] == "legacy_metadata.period"
    assert "multiple_editions" in first_a["issues"]
    assert "cross_source_external_id_collision" in first_a["issues"]
    assert "exact_normalized_text_duplicate" in first_a["issues"]
    assert "exact_normalized_text_duplicate" not in by_external[("source-two", "OTHER")][0][
        "issues"
    ]
    assert "malformed_metadata" in by_external[("source-one", "MALFORMED")][0]["issues"]
    assert "empty_text" in by_external[("source-one", "BLANK")][0]["issues"]
    assert "unreadable_text" in by_external[("source-one", "PLACEHOLDER")][0]["issues"]
    assert store.path.read_bytes() == before
    assert "does not establish" in first["limitations"][0]


def test_audit_empty_project_and_fingerprint_tracks_evidence(tmp_path):
    store = ResearchStore(tmp_path / "project.db")
    store.initialize()
    empty = audit_corpus(store)
    assert empty["counts"]["editions"] == 0
    assert empty["editions"] == []

    store.import_records(
        b"one",
        [{"external_id": "A", "language": "sux", "text": "a-na"}],
        source="s",
        license="private",
    )
    before_annotation = audit_corpus(store)["fingerprint"]
    dossier = store.dossier(store.artifacts()[0]["id"])
    annotation = store.annotate(
        dossier["id"],
        "category",
        {"axis": "genre", "label": "letter"},
        actor="local editor",
        evidence=[dossier["editions"][0]["id"]],
    )
    after_annotation = audit_corpus(store)["fingerprint"]
    store.review(annotation, "accepted", actor="local reviewer", reason="checked")
    after_review = audit_corpus(store)["fingerprint"]
    assert len({before_annotation, after_annotation, after_review}) == 3


def test_audit_treats_top_level_and_legacy_placeholder_periods_as_missing(tmp_path):
    store = ResearchStore(tmp_path / "project.db")
    store.initialize()
    store.import_records(
        b"placeholder-periods",
        [
            {
                "external_id": "TOP",
                "language": "sumerian",
                "text": "a",
                "period": "unknown",
                "provenience": "Ur",
            },
            {
                "external_id": "LEGACY",
                "language": "akkadian",
                "text": "b",
                "provenience": "Nippur",
                "legacy_metadata": {"period": "UNKNOWN"},
            },
            {
                "external_id": "NEO-ASSYRIAN",
                "language": "akkadian",
                "text": "c",
                "period": "NA",
                "provenience": "Nineveh",
            },
        ],
        source="legacy",
        license="private/unverified",
    )

    result = audit_corpus(store)

    assert result["distributions"]["issues"]["missing_period"] == 2
    rows = {row["external_id"]: row for row in result["editions"]}
    assert rows["TOP"]["metadata"]["period"] is None
    assert rows["TOP"]["metadata_paths"]["period"] == "period"
    assert rows["LEGACY"]["metadata"]["period"] is None
    assert rows["LEGACY"]["metadata_paths"]["period"] == "legacy_metadata.period"
    assert rows["NEO-ASSYRIAN"]["metadata"]["period"] == "NA"
    assert "missing_period" not in rows["NEO-ASSYRIAN"]["issues"]


def test_audit_retains_issue_rows_beyond_the_first_thousand(tmp_path):
    store = ResearchStore(tmp_path / "project.db")
    store.initialize()
    records = [
        {
            "external_id": f"ROW-{index:04d}",
            "language": f"test-language-{index:04d}",
            "text": f"text {index}",
        }
        for index in range(1001)
    ]
    store.import_records(b"large-fixture", records, source="s", license="private")

    result = audit_corpus(store)

    assert result["counts"]["issue_rows"] == 1001
    assert len(result["editions"]) == 1001
    assert {row["external_id"] for row in result["editions"]} == {
        record["external_id"] for record in records
    }


def test_reference_requires_current_accepted_label_and_family(tmp_path):
    store = ResearchStore(tmp_path / "project.db")
    store.initialize()
    store.import_records(
        b"records",
        [
            {"external_id": "accepted", "language": "sux", "text": "a-na"},
            {"external_id": "pending", "language": "sux", "text": "i-na"},
            {"external_id": "rejected", "language": "akk", "text": "ša"},
            {
                "external_id": "legacy-only",
                "language": "sux",
                "text": "mu",
                "legacy": True,
                "legacy_metadata": {"genre": "myth", "composition_family": "legacy-family"},
            },
            {"external_id": "synthetic", "language": "demo", "text": "made up", "synthetic": True},
        ],
        source="s",
        license="private/unverified",
    )
    dossiers = {row["external_id"]: store.dossier(row["id"]) for row in store.artifacts()}
    accepted = dossiers["accepted"]
    edition_id = accepted["editions"][0]["id"]
    old = _accept_category(store, accepted["id"], edition_id, "genre", "myth")
    _accept_category(
        store, accepted["id"], edition_id, "genre", "letter", supersedes=old
    )
    family_id = _accept_category(
        store, accepted["id"], edition_id, "composition_family", "family-1"
    )

    pending = dossiers["pending"]
    store.annotate(
        pending["id"],
        "category",
        {"axis": "genre", "label": "letter"},
        actor="editor",
        evidence=[pending["editions"][0]["id"]],
    )
    _accept_category(
        store,
        pending["id"],
        pending["editions"][0]["id"],
        "composition_family",
        "family-2",
    )

    rejected = dossiers["rejected"]
    rejected_label = store.annotate(
        rejected["id"],
        "category",
        {"axis": "genre", "label": "letter"},
        actor="editor",
        evidence=[rejected["editions"][0]["id"]],
    )
    store.review(rejected_label, "rejected", actor="reviewer", reason="wrong")
    _accept_category(
        store,
        rejected["id"],
        rejected["editions"][0]["id"],
        "composition_family",
        "family-3",
    )

    synthetic = dossiers["synthetic"]
    for axis, label in [("genre", "tutorial"), ("composition_family", "demo-family")]:
        _accept_category(store, synthetic["id"], synthetic["editions"][0]["id"], axis, label)

    result = prepare_reference_set(store, axis="genre", seed=42)

    assert result == prepare_reference_set(store, axis="genre", seed=42)
    assert set(result["gold"]) == {item["id"] for item in result["items"]}
    assert list(result["gold"].values()) == ["letter"]
    assert result["items"][0]["family"] == "family-1"
    evidence = result["items"][0]["accepted_evidence"]
    assert evidence["label"]["actor"] == "editor"
    assert evidence["label"]["origin"] == "observed"
    assert evidence["label"]["reviews"][-1]["actor"] == "reviewer"
    assert evidence["family"]["annotation_id"] == family_id
    assert result["items"][0]["source_rights"] == "private/unverified"
    exclusions = {row["external_id"]: row["reasons"] for row in result["exclusions"]}
    assert "missing_accepted_genre" in exclusions["pending"]
    assert "missing_accepted_genre" in exclusions["rejected"]
    assert "missing_accepted_genre" in exclusions["legacy-only"]
    assert "missing_accepted_composition_family" in exclusions["legacy-only"]
    assert "synthetic_record" in exclusions["synthetic"]
    assert result["counts"]["eligible"] == 1
    assert "not authenticated expert status" in " ".join(result["limitations"])


def test_reference_excludes_conflicts_and_keeps_components_together_through_exclusions(
    tmp_path,
):
    store = ResearchStore(tmp_path / "project.db")
    store.initialize()
    store.import_records(
        b"v1",
        [
            {"external_id": "A", "language": "sux", "text": "left duplicate"},
            {"external_id": "BRIDGE", "language": "unknown", "text": "left duplicate"},
            {"external_id": "C", "language": "akk", "text": "right duplicate"},
            {"external_id": "CONFLICT", "language": "sux", "text": "valid"},
        ],
        source="s",
        license="private",
    )
    store.import_records(
        b"v2",
        [{"external_id": "BRIDGE", "language": "unknown", "text": "right duplicate"}],
        source="s",
        license="private",
    )
    dossiers = {row["external_id"]: store.dossier(row["id"]) for row in store.artifacts()}
    for external, family in [("A", "fa"), ("C", "fc")]:
        dossier = dossiers[external]
        edition = dossier["editions"][0]["id"]
        _accept_category(store, dossier["id"], edition, "genre", "letter")
        _accept_category(store, dossier["id"], edition, "composition_family", family)
    bridge = dossiers["BRIDGE"]
    _accept_category(store, bridge["id"], bridge["editions"][0]["id"], "genre", "letter")
    _accept_category(
        store, bridge["id"], bridge["editions"][0]["id"], "composition_family", "bridge"
    )
    conflict = dossiers["CONFLICT"]
    edition = conflict["editions"][0]["id"]
    _accept_category(store, conflict["id"], edition, "genre", "letter")
    _accept_category(store, conflict["id"], edition, "genre", "myth")
    _accept_category(store, conflict["id"], edition, "composition_family", "fa")
    _accept_category(store, conflict["id"], edition, "composition_family", "fc")

    result = prepare_reference_set(store, seed=7)

    by_external = {item["external_id"]: item for item in result["items"]}
    assert set(by_external) == {"A", "C"}
    assert result["assignments"][by_external["A"]["id"]] == result["assignments"][
        by_external["C"]["id"]
    ]
    excluded = {row["external_id"]: row for row in result["exclusions"]}
    assert "unknown_language" in excluded["BRIDGE"]["reasons"]
    assert "conflicting_accepted_genre" in excluded["CONFLICT"]["reasons"]
    assert "conflicting_accepted_composition_family" in excluded["CONFLICT"]["reasons"]
    split = next(iter(result["assignments"].values()))
    assert result["counts"]["splits"][split] == 2
    assert result["counts"]["languages_by_split"][split] == {"akk": 1, "sux": 1}


def test_reference_keeps_multiple_editions_together_and_validates_parameters(tmp_path):
    store = ResearchStore(tmp_path / "project.db")
    store.initialize()
    store.import_records(
        b"v1",
        [{"external_id": "A", "language": "sux", "text": "one"}],
        source="s",
        license="private",
    )
    store.import_records(
        b"v2",
        [{"external_id": "A", "language": "sux", "text": "two"}],
        source="s",
        license="private",
    )
    dossier = store.dossier(store.artifacts()[0]["id"])
    edition_id = dossier["editions"][0]["id"]
    _accept_category(store, dossier["id"], edition_id, "genre", "letter")
    _accept_category(store, dossier["id"], edition_id, "composition_family", "family")

    result = prepare_reference_set(store, seed=42)

    assert len(result["items"]) == 2
    assert len({result["assignments"][item["id"]] for item in result["items"]}) == 1
    assert result["counts"]["eligible"] == 2
    for axis, seed in [("", 42), ("made-up", 42), ("genre", True), ("genre", "42")]:
        with pytest.raises(ValueError):
            prepare_reference_set(store, axis=axis, seed=seed)


def test_reference_empty_project_abstains_without_inventing_a_benchmark(tmp_path):
    store = ResearchStore(tmp_path / "project.db")
    store.initialize()
    result = prepare_reference_set(store)
    assert result["items"] == []
    assert result["gold"] == {}
    assert result["assignments"] == {}
    assert result["counts"]["eligible"] == 0
    assert result["status"] == "abstained"


def test_json_export_and_cli_are_create_only(tmp_path, capsys):
    store = ResearchStore(tmp_path / "project.db")
    store.initialize()
    store.import_records(
        b"one",
        [{"external_id": "A", "language": "sux", "text": "a-na"}],
        source="s",
        license="private",
    )
    destination = tmp_path / "audit.json"
    assert main(["audit", str(store.path), "--output", str(destination)]) == 0
    stdout_value = json.loads(capsys.readouterr().out)
    assert json.loads(destination.read_text()) == stdout_value
    original = destination.read_bytes()
    assert main(["audit", str(store.path), "--output", str(destination)]) == 2
    assert "exists" in capsys.readouterr().err
    assert destination.read_bytes() == original
    assert main(["reference-set", str(store.path), "--axis", "bad-axis"]) == 2
    assert "axis" in capsys.readouterr().err
    assert main(["reference-set", str(store.path), "--seed", "not-an-integer"]) == 2
    assert "seed" in capsys.readouterr().err
    assert main(["audit", str(store.path), "--output", str(store.path)]) == 2
    assert "project" in capsys.readouterr().err
    assert store.path.is_file()

    separate = tmp_path / "value.json"
    write_json_export({"b": 1, "a": "Š"}, separate)
    assert json.loads(separate.read_text()) == {"a": "Š", "b": 1}
    with pytest.raises(ValueError, match="exists"):
        write_json_export({}, separate)
