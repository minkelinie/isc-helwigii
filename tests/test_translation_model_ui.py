"""Local model UI contract; synthetic generation persists real runs and annotations."""

import os
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

pytest.importorskip("streamlit")

from test_translation_ui import (
    SOURCE,
    open_translation,
    seed_proposal,
    widget,
    workspace as workspace,
)

import isc_helwigii
from isc_helwigii.translation_quality import assess_translation

MODEL_ID = "Thalesian/cuneiformBase-400m"
MODEL_TEXT = "  **Synthetic translation**\n<script>literal</script>\n```text\n  "


@pytest.fixture
def model_core(monkeypatch, tmp_path):
    """Replace only the model boundary, retaining its documented store side effects."""
    core = ModuleType("isc_helwigii.local_translation")
    state = SimpleNamespace(installed=True, error=None, failure=None, calls=[], paths=[])
    monkeypatch.setenv("ISC_HELWIGII_TRANSLATION_MODEL", str(tmp_path / "local model"))
    core.MODEL_ID = MODEL_ID
    core.default_model_dir = lambda: Path(os.environ["ISC_HELWIGII_TRANSLATION_MODEL"])

    def canonical_language(value):
        languages = {"akk": "akk", "Akkadian": "akk", "sux": "sux", "Sumerian": "sux"}
        if value not in languages:
            raise ValueError("Unsupported source language")
        return languages[value]

    def model_status(path):
        state.paths.append(path)
        return {
            "installed": state.installed,
            "error": state.error,
            "model_id": MODEL_ID,
            "revision": "synthetic-revision",
            "path": str(path),
        }

    def propose_model_translation(
        store,
        edition_id,
        *,
        model_dir,
        actor,
        start=0,
        end=None,
        source_language=None,
        input_format="transliteration",
        target_language="en",
    ):
        state.calls.append(edition_id)
        if state.failure:
            raise state.failure
        edition = store.edition(edition_id)
        assert target_language == "en"
        assert source_language in ("sux", "akk")
        assert input_format in ("transliteration", "complex-transliteration", "cuneiform")
        assert 0 <= start < end <= len(edition["text"])
        inputs = {
            "edition_id": edition_id,
            "model_dir": str(model_dir),
            "start": start,
            "end": end,
            "source_text": edition["text"][start:end],
            "source_language": source_language,
            "input_format": input_format,
            "target_language": target_language,
        }
        run_id = store.save_run(
            "synthetic-local-translation", inputs, {"text": MODEL_TEXT}, actor=actor
        )
        annotation_id = store.annotate(
            edition["artifact_id"],
            "translation",
            {
                "edition_id": edition_id,
                "start": start,
                "end": end,
                "target_language": target_language,
                "text": MODEL_TEXT,
                "model": {"id": MODEL_ID, "revision": "synthetic-revision", "run_id": run_id},
            },
            actor=actor,
            evidence=[edition["snapshot_id"], edition_id, run_id],
            origin="inferred",
        )
        return {"annotation_id": annotation_id, "run_id": run_id, "text": MODEL_TEXT}

    core.canonical_language = canonical_language
    core.model_status = model_status
    core.propose_model_translation = propose_model_translation
    monkeypatch.setitem(sys.modules, core.__name__, core)
    monkeypatch.setattr(isc_helwigii, "local_translation", core, raising=False)
    return state


def use_english(app):
    widget(app, "button", "Engels kiezen").click().run()
    assert not app.exception
    assert widget(app, "text_input", "Doeltaal").value == "en"


def generate(app):
    widget(app, "button", "Lokaal vertaalvoorstel maken").click().run()
    assert not app.exception


def test_model_uses_selected_occurrence_and_saves_pending_for_explicit_review(
    workspace, model_core, monkeypatch, caplog
):
    from streamlit.elements.lib import policies

    app, store, artifact_id = workspace
    previous = seed_proposal(store, artifact_id, target="en", text="Earlier proposal")
    open_translation(app)
    widget(app, "text_area", "Ongewijzigde bronpassage").set_value("𒀭 ša").run()
    widget(app, "selectbox", "Voorkomen in de bron").set_value(5).run()
    assert widget(app, "button", "Lokaal vertaalvoorstel maken").disabled
    # Streamlit emits this warning only once per process; earlier tests must not hide it.
    monkeypatch.setattr(policies, "_shown_default_value_warning", False)
    caplog.clear()
    use_english(app)
    assert not any("created with a default value" in record.message for record in caplog.records)
    assert not any("created with a default value" in warning.value for warning in app.warning)
    assert widget(app, "text_area", "Ongewijzigde bronpassage").value == "𒀭 ša"
    assert widget(app, "selectbox", "Voorkomen in de bron").value == 5
    assert store.runs() == []
    assert model_core.calls == []
    generate(app)
    assert not app.error
    assert any("in afwachting" in message.value.lower() for message in app.success)
    annotations = store.dossier(artifact_id)["annotations"]
    assert len(annotations) == 2
    proposed = annotations[-1]
    assert proposed["id"] != previous
    assert proposed["status"] == "pending"
    assert proposed["reviews"] == []
    assert proposed["payload"]["start"] == 5
    assert proposed["payload"]["end"] == 9
    assert proposed["payload"]["target_language"] == "en"
    assert proposed["payload"]["text"] == MODEL_TEXT
    assert proposed["origin"] == "inferred"
    assert widget(app, "selectbox", "Voorstel beoordelen").value == proposed["id"]
    assert widget(app, "metric", "Redactionele dekking").value == "0.0%"
    assert sum(code.value == MODEL_TEXT for code in app.code) == 1
    provenance = "\n".join(item.value for item in app.text)
    for value in (MODEL_ID, "synthetic-revision", store.runs()[0]["id"]):
        assert value in provenance
    assert any("experimenteel" in item.value.lower() for item in app.warning)
    assert any("oudere voorstel" in item.value for item in app.caption)
    run = store.runs()[0]
    assert run["inputs"]["source_text"] == "𒀭 ša"
    assert run["inputs"]["source_language"] == "akk"
    assert run["inputs"]["input_format"] == "transliteration"
    assert run["id"] in proposed["evidence"]
    app.run()
    assert len(store.runs()) == 1
    assert len(store.dossier(artifact_id)["annotations"]) == 2
    assert len(model_core.calls) == 1
    widget(app, "text_area", "Beoordelingsgrond").set_value("Checked this synthetic passage.")
    widget(app, "button", "Beoordeling vastleggen").click().run()
    assert not app.error
    assert store.dossier(artifact_id)["annotations"][-1]["status"] == "accepted"
    assert widget(app, "metric", "Redactionele dekking").value == "50.0%"
    assert len(store.runs()) == 1


@pytest.mark.parametrize("language, expected", [("Akkadian", "akk"), ("Sumerian", "sux")])
def test_metadata_language_defaults_and_model_configuration_reach_run(
    workspace, model_core, tmp_path, language, expected
):
    app, store, artifact_id = workspace
    store.import_records(
        language.encode(),
        [{"external_id": "SYNTH-TRANSLATION", "text": SOURCE, "language": language}],
        source="synthetic-ui-fixture",
        license="CC0 synthetic fixture only",
    )
    edition = store.dossier(artifact_id)["editions"][-1]
    open_translation(app)
    widget(app, "selectbox", "Broneditie").set_value(edition["id"]).run()
    use_english(app)
    assert widget(app, "selectbox", "Brontaal voor model").value == expected
    assert widget(app, "text_input", "Lokaal modelpad").value == str(tmp_path / "local model")
    custom_path = tmp_path / "other weights"
    widget(app, "text_input", "Lokaal modelpad").set_value(str(custom_path)).run()
    widget(app, "text_input", "Onderzoeker").set_value("synthetic model researcher").run()
    for index, input_format in enumerate(("complex-transliteration", "cuneiform"), start=1):
        widget(app, "selectbox", "Invoerformaat voor model").set_value(input_format).run()
        generate(app)
        assert not app.error
        run = store.runs()[0]
        assert len(store.runs()) == index
        assert run["actor"] == "synthetic model researcher"
        assert run["inputs"] == {
            "edition_id": edition["id"],
            "model_dir": str(custom_path),
            "start": 0,
            "end": 9,
            "source_text": SOURCE,
            "source_language": expected,
            "input_format": input_format,
            "target_language": "en",
        }
    assert model_core.paths[-1] == custom_path


@pytest.mark.parametrize("language", [None, "unknown", "hit"])
def test_unknown_or_unsupported_metadata_requires_explicit_supported_language(
    workspace, model_core, language
):
    app, store, artifact_id = workspace
    record = {"external_id": "SYNTH-TRANSLATION", "text": SOURCE}
    if language is not None:
        record["language"] = language
    store.import_records(
        b"unknown-language fixture",
        [record],
        source="synthetic-ui-fixture",
        license="CC0 synthetic fixture only",
    )
    edition = store.dossier(artifact_id)["editions"][-1]
    open_translation(app)
    widget(app, "selectbox", "Broneditie").set_value(edition["id"]).run()
    use_english(app)
    language_choice = widget(app, "selectbox", "Brontaal voor model")
    assert language_choice.value is None
    assert widget(app, "button", "Lokaal vertaalvoorstel maken").disabled
    app.run()
    assert store.runs() == []
    assert model_core.calls == []
    language_choice.set_value("sux").run()
    generate(app)
    assert not app.error
    assert store.runs()[0]["inputs"]["source_language"] == "sux"


@pytest.mark.parametrize("target", ["nl", "de"])
def test_non_english_target_blocks_model_but_preserves_manual_proposals(
    workspace, model_core, target
):
    app, store, artifact_id = workspace
    open_translation(app)
    widget(app, "text_input", "Doeltaal").set_value(target).run()
    assert widget(app, "button", "Lokaal vertaalvoorstel maken").disabled
    assert model_core.calls == []
    widget(app, "text_area", "Vertaling").set_value("Manual translation")
    widget(app, "button", "Vertaling voorstellen").click().run()
    assert not app.error
    assert not app.exception
    proposal = store.dossier(artifact_id)["annotations"][0]
    assert proposal["payload"]["target_language"] == target
    assert proposal["status"] == "pending"
    assert store.runs() == []


@pytest.mark.parametrize("error", [None, "Local model config is invalid"])
def test_missing_model_shows_install_command_and_keeps_manual_route(
    workspace, model_core, tmp_path, error
):
    app, store, _ = workspace
    model_core.installed = False
    model_core.error = error
    open_translation(app)
    use_english(app)
    assert widget(app, "button", "Lokaal vertaalvoorstel maken").disabled
    assert not widget(app, "button", "Vertaling voorstellen").disabled
    assert any(
        "isc-helwigii download-model" in code.value and str(tmp_path / "local model") in code.value
        for code in app.code
    )
    if error:
        assert any(error in item.value for item in app.warning)
    app.run()
    assert store.runs() == []
    assert model_core.calls == []


@pytest.mark.parametrize("passage", ["", "𒀭  ša", "ša\r\n𒀭"])
def test_invalid_passage_never_generates(workspace, model_core, passage):
    app, store, artifact_id = workspace
    open_translation(app)
    use_english(app)
    widget(app, "text_area", "Ongewijzigde bronpassage").set_value(passage).run()
    assert widget(app, "button", "Lokaal vertaalvoorstel maken").disabled
    assert store.runs() == []
    assert store.dossier(artifact_id)["annotations"] == []
    assert model_core.calls == []


@pytest.mark.parametrize(
    "failure",
    [ValueError("Weights failed verification"), OSError("Model dependencies unavailable")],
)
def test_generation_errors_preserve_manual_draft_and_do_not_retry_on_rerun(
    workspace, model_core, failure
):
    app, store, artifact_id = workspace
    model_core.failure = failure
    open_translation(app)
    use_english(app)
    widget(app, "text_area", "Vertaling").set_value("Keep my manual draft").run()
    widget(app, "text_area", "Bibliografische verwijzing of brontekst").set_value(
        "Keep my reference"
    ).run()
    generate(app)
    assert any(str(failure) in item.value for item in app.error)
    assert widget(app, "text_area", "Vertaling").value == "Keep my manual draft"
    assert (
        widget(app, "text_area", "Bibliografische verwijzing of brontekst").value
        == "Keep my reference"
    )
    app.run()
    assert len(model_core.calls) == 1
    assert store.runs() == []
    assert store.dossier(artifact_id)["annotations"] == []


@pytest.mark.parametrize(
    "prediction,missing",
    [
        ("132 ewes, Ur-Namma", True),
        ("one thousand two hundred and thirty-two ewes, Ur-Namma", False),
    ],
)
def test_quantity_evidence_remains_visible_after_review(workspace, model_core, prediction, missing):
    app, store, artifact_id = workspace
    source = "𒀭 2(gesz'u) 3(u) 2(disz) u8 ur-{d}namma"
    store.import_records(
        b"synthetic quantity UI regression",
        [
            {
                "external_id": "SYNTH-TRANSLATION",
                "text": source,
                "language": "sux",
                "synthetic": True,
            }
        ],
        source="synthetic-ui-fixture",
        license="CC0 synthetic fixture only",
    )
    edition = store.dossier(artifact_id)["editions"][-1]
    checks = assess_translation(source, prediction, source_language="sux")
    annotation = store.annotate(
        artifact_id,
        "translation",
        {
            "edition_id": edition["id"],
            "start": 0,
            "end": len(source),
            "text": prediction,
            "target_language": "en",
            "model": {"id": MODEL_ID, "revision": "synthetic"},
            "quality_checks": checks,
        },
        actor="synthetic tester",
        evidence=[edition["id"]],
        origin="inferred",
    )
    before = store.edition(edition["id"])
    open_translation(app)
    widget(app, "selectbox", "Broneditie").set_value(edition["id"]).run()
    use_english(app)
    assert any("Controleer de aantallen" in item.value for item in app.warning) == missing
    detail = "\n".join(item.value for item in app.text)
    for literal in ("1232", "2(gesz'u) 3(u) 2(disz)", "ur-{d}namma", "geen nauwkeurigheidsscore"):
        assert literal in detail
    assert widget(app, "metric", "Redactionele dekking").value == "0.0%"
    widget(app, "text_area", "Beoordelingsgrond").set_value(
        "Synthetic review; warning must persist."
    )
    widget(app, "button", "Beoordeling vastleggen").click().run()
    assert not app.exception
    assert any("Controleer de aantallen" in item.value for item in app.warning) == missing
    assert store.dossier(artifact_id)["annotations"][-1]["id"] == annotation
    assert store.edition(edition["id"]) == before
    assert model_core.calls == []
    assert store.runs() == []
