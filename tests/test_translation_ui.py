"""Translation workspace exercises the real store using synthetic sources only."""

import json
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest

from isc_helwigii import ui
from isc_helwigii.store import ResearchStore

SOURCE = "𒀭 ša\n𒀭 ša"


def widget(app, kind, label):
    return next(item for item in getattr(app, kind) if item.label == label)


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    store = ResearchStore(tmp_path / "synthetic-translation.db")
    store.initialize()
    store.import_records(
        b"synthetic translation fixture",
        [
            {
                "external_id": "SYNTH-TRANSLATION",
                "language": "akk",
                "text": SOURCE,
                "title": "Fictieve bron",
                "synthetic": True,
            }
        ],
        source="synthetic-ui-fixture",
        license="CC0 synthetic fixture only",
    )
    monkeypatch.setenv("ISC_HELWIGII_PROJECT", str(store.path))
    app = AppTest.from_file(str(Path(ui.__file__))).run()
    return app, store, store.artifacts()[0]["id"]


def open_translation(app):
    assert "Vertalen" in app.sidebar.radio[0].options
    app.sidebar.radio[0].set_value("Vertalen").run()
    assert not app.exception
    assert not app.error


def test_repeat_passage_proposal_stays_pending_until_explicit_review(workspace):
    app, store, artifact_id = workspace
    open_translation(app)
    widget(app, "text_area", "Ongewijzigde bronpassage").set_value("𒀭 ša").run()
    occurrence = widget(app, "selectbox", "Voorkomen in de bron")
    assert len(occurrence.options) == 2
    occurrence.set_value(5).run()
    widget(app, "text_area", "Vertaling").set_value("De god van de tweede regel.")
    widget(app, "text_area", "Bibliografische verwijzing of brontekst").set_value(
        "Fictieve bron, p. 2.\n  Controleer deze lezing."
    )
    widget(app, "selectbox", "Herkomst interpretatie").set_value("imported")
    widget(app, "button", "Vertaling voorstellen").click().run()
    assert not app.exception
    assert not app.error
    dossier = store.dossier(artifact_id)
    assert len(dossier["annotations"]) == 1
    proposal = dossier["annotations"][0]
    edition = dossier["editions"][0]
    assert proposal["payload"] == {
        "edition_id": edition["id"],
        "start": 5,
        "end": 9,
        "target_language": "nl",
        "text": "De god van de tweede regel.",
        "reference": "Fictieve bron, p. 2.\n  Controleer deze lezing.",
    }
    assert proposal["evidence"] == [edition["snapshot_id"], edition["id"]]
    assert proposal["origin"] == "imported"
    assert proposal["status"] == "pending"
    assert widget(app, "metric", "Redactionele dekking").value == "0.0%"
    assert widget(app, "text_area", "Vertaling").value == ""
    assert widget(app, "text_area", "Bibliografische verwijzing of brontekst").value == ""
    assert any(code.value == "De god van de tweede regel." for code in app.code)
    assert any("Fictieve bron, p. 2." in code.value for code in app.code)
    app.run()
    assert len(store.dossier(artifact_id)["annotations"]) == 1

    widget(app, "text_area", "Beoordelingsgrond").set_value("   ")
    widget(app, "button", "Beoordeling vastleggen").click().run()
    assert app.error
    assert store.dossier(artifact_id)["annotations"][0]["reviews"] == []
    widget(app, "text_area", "Beoordelingsgrond").set_value("Tweede voorkomen gecontroleerd.")
    widget(app, "button", "Beoordeling vastleggen").click().run()
    assert not app.exception
    assert not app.error
    reviewed = store.dossier(artifact_id)["annotations"][0]
    assert reviewed["status"] == "accepted"
    assert reviewed["reviews"][0]["reason"] == "Tweede voorkomen gecontroleerd."
    assert widget(app, "metric", "Redactionele dekking").value == "50.0%"
    assert any("lokale onderzoeker" in caption.value for caption in app.caption)
    app.run()
    assert len(store.dossier(artifact_id)["annotations"]) == 1
    assert len(store.dossier(artifact_id)["annotations"][0]["reviews"]) == 1


def test_source_target_and_occurrence_changes_isolate_drafts(workspace):
    app, store, artifact_id = workspace
    store.import_records(
        b"synthetic second edition",
        [
            {
                "external_id": "SYNTH-TRANSLATION",
                "language": "akk",
                "text": SOURCE,
                "title": "Tweede fictieve editie",
                "synthetic": True,
            }
        ],
        source="synthetic-ui-fixture",
        license="CC0 synthetic fixture only",
    )
    open_translation(app)
    widget(app, "text_area", "Ongewijzigde bronpassage").set_value("𒀭 ša").run()
    widget(app, "text_area", "Vertaling").set_value("Niet opgeslagen concept").run()
    widget(app, "text_area", "Bibliografische verwijzing of brontekst").set_value(
        "Conceptbron"
    ).run()
    app.run()
    assert widget(app, "text_area", "Vertaling").value == "Niet opgeslagen concept"
    widget(app, "selectbox", "Voorkomen in de bron").set_value(5).run()
    assert widget(app, "text_area", "Vertaling").value == ""
    assert widget(app, "text_area", "Bibliografische verwijzing of brontekst").value == ""
    widget(app, "text_area", "Vertaling").set_value("Tweede voorkomen concept").run()
    widget(app, "text_input", "Doeltaal").set_value("en").run()
    assert widget(app, "text_area", "Vertaling").value == ""
    assert widget(app, "text_area", "Bibliografische verwijzing of brontekst").value == ""
    widget(app, "text_area", "Vertaling").set_value("English draft").run()
    editions = store.dossier(artifact_id)["editions"]
    widget(app, "selectbox", "Broneditie").set_value(editions[1]["id"]).run()
    assert not app.exception
    assert not app.error
    assert widget(app, "text_area", "Vertaling").value == ""
    assert store.dossier(artifact_id)["annotations"] == []


def test_invalid_excerpt_cannot_save_and_empty_source_disables_proposal(workspace):
    app, store, artifact_id = workspace
    open_translation(app)
    widget(app, "text_area", "Ongewijzigde bronpassage").set_value("𒀭  ša").run()
    assert not app.exception
    assert widget(app, "button", "Vertaling voorstellen").disabled
    assert store.dossier(artifact_id)["annotations"] == []
    assert any("ongewijzigde passage" in message.value.lower() for message in app.info)
    store.import_records(
        b"synthetic catalog only",
        [{"external_id": "SYNTH-TRANSLATION", "language": "akk", "text": "", "synthetic": True}],
        source="synthetic-ui-fixture",
        license="CC0 synthetic fixture only",
    )
    app.run()
    empty = store.dossier(artifact_id)["editions"][-1]
    widget(app, "selectbox", "Broneditie").set_value(empty["id"]).run()
    assert not app.exception
    assert not app.error
    assert widget(app, "button", "Vertaling voorstellen").disabled
    assert widget(app, "metric", "Redactionele dekking").value == "—"


def seed_proposal(
    store, artifact_id, *, start=0, end=4, target="nl", text="Fictieve vertaling", edition=None
):
    edition = edition or store.dossier(artifact_id)["editions"][0]
    return store.annotate(
        artifact_id,
        "translation",
        {
            "edition_id": edition["id"],
            "start": start,
            "end": end,
            "target_language": target,
            "text": text,
            "reference": "Fictieve bronverwijzing",
        },
        actor="synthetische vertaler",
        evidence=[edition["snapshot_id"], edition["id"]],
        origin="imported",
    )


def test_conflict_review_resolves_coverage_and_revision_choices_are_scoped(workspace):
    app, store, artifact_id = workspace
    first = seed_proposal(store, artifact_id, text="Eerste volledige kandidaat")
    overlap = seed_proposal(
        store, artifact_id, start=2, end=9, text="Overlappende volledige kandidaat"
    )
    foreign_target = seed_proposal(store, artifact_id, target="en", text="English only")
    for annotation_id in [first, overlap]:
        store.review(
            annotation_id, "accepted", actor="eerdere beoordelaar", reason="Synthetische proef"
        )
    open_translation(app)
    assert widget(app, "metric", "Redactionele dekking").value == "0.0%"
    assert widget(app, "metric", "Tekens met conflict").value == "6"
    assert any(heading.value == "Conflicterende passages" for heading in app.subheader)
    for translation in ["Eerste volledige kandidaat", "Overlappende volledige kandidaat"]:
        assert sum(code.value == translation for code in app.code) == 1
    selector = widget(app, "selectbox", "Voorstel beoordelen")
    assert all(foreign_target not in option for option in selector.options)
    selector.set_value(overlap).run()
    assert sum(code.value == "Overlappende volledige kandidaat" for code in app.code) == 1
    assert any(code.value == "ša\n𒀭 ša" for code in app.code)
    widget(app, "selectbox", "Besluit").set_value("rejected")
    widget(app, "text_area", "Beoordelingsgrond").set_value("Overlap berust op een andere lezing.")
    widget(app, "button", "Beoordeling vastleggen").click().run()
    assert not app.error
    assert not app.exception
    assert widget(app, "metric", "Redactionele dekking").value == "50.0%"
    assert widget(app, "metric", "Tekens met conflict").value == "0"
    assert any(heading.value == "Nog te vertalen passages" for heading in app.subheader)
    assert any("Afgewezen" in caption.value for caption in app.caption)
    widget(app, "text_area", "Ongewijzigde bronpassage").set_value("𒀭 ša").run()
    revisions = widget(app, "selectbox", "Herziening van")
    assert len(revisions.options) == 2
    revisions.set_value(first)
    widget(app, "text_area", "Vertaling").set_value("Herziene eerste vertaling")
    widget(app, "button", "Vertaling voorstellen").click().run()
    annotations = store.dossier(artifact_id)["annotations"]
    assert annotations[-1]["supersedes"] == first
    assert annotations[-1]["status"] == "pending"
    assert widget(app, "metric", "Redactionele dekking").value == "50.0%"
    widget(app, "text_area", "Beoordelingsgrond").set_value("Herziening gecontroleerd.")
    widget(app, "button", "Beoordeling vastleggen").click().run()
    assert not app.error
    assert store.dossier(artifact_id)["annotations"][0]["status"] == "superseded"
    widget(app, "selectbox", "Voorstel beoordelen").set_value(first).run()
    assert any("Vervangen" in caption.value for caption in app.caption)
    assert len(app.get("download_button")) == 2
    assert {button.proto.label for button in app.get("download_button")} == {
        "Vertaalblad downloaden (Markdown)",
        "Vertaalblad downloaden (JSON)",
    }


def test_failed_proposal_preserves_reference_and_review_follows_selected_annotation(workspace):
    app, store, artifact_id = workspace
    first = seed_proposal(store, artifact_id, text="Eerder voorstel")
    open_translation(app)
    widget(app, "text_area", "Vertaling").set_value(" \n ")
    widget(app, "text_area", "Bibliografische verwijzing of brontekst").set_value(
        "Bewaar deze referentie"
    )
    widget(app, "button", "Vertaling voorstellen").click().run()
    assert app.error
    assert len(store.dossier(artifact_id)["annotations"]) == 1
    assert (
        widget(app, "text_area", "Bibliografische verwijzing of brontekst").value
        == "Bewaar deze referentie"
    )
    widget(app, "text_area", "Vertaling").set_value("  Letterlijke vertaling\nmet regeleinde.  ")
    widget(app, "button", "Vertaling voorstellen").click().run()
    assert not app.error
    proposed = store.dossier(artifact_id)["annotations"][-1]
    assert proposed["payload"]["text"] == "  Letterlijke vertaling\nmet regeleinde.  "
    assert widget(app, "selectbox", "Voorstel beoordelen").value == proposed["id"]
    widget(app, "text_area", "Beoordelingsgrond").set_value("Nog niet bevestigd").run()
    widget(app, "selectbox", "Voorstel beoordelen").set_value(first).run()
    assert widget(app, "text_area", "Beoordelingsgrond").value == ""
    assert any(code.value == "Eerder voorstel" for code in app.code)
    assert not any(code.value == proposed["payload"]["text"] for code in app.code)
    widget(app, "selectbox", "Besluit").set_value("rejected")
    widget(app, "text_area", "Beoordelingsgrond").set_value("Eerdere lezing afgewezen.")
    widget(app, "button", "Beoordeling vastleggen").click().run()
    assert not app.error
    assert not app.exception
    annotations = store.dossier(artifact_id)["annotations"]
    assert annotations[0]["status"] == "rejected"
    assert annotations[1]["status"] == "pending"


def test_project_switch_isolates_identical_edition_ids(workspace, tmp_path):
    app, store, artifact_id = workspace
    other = ResearchStore(tmp_path / "other-synthetic-project.db")
    other.initialize()
    other.import_records(
        b"synthetic translation fixture",
        [
            {
                "external_id": "SYNTH-TRANSLATION",
                "language": "akk",
                "text": SOURCE,
                "title": "Fictieve bron",
                "synthetic": True,
            }
        ],
        source="synthetic-ui-fixture",
        license="CC0 synthetic fixture only",
    )
    assert (
        other.dossier(artifact_id)["editions"][0]["id"]
        == store.dossier(artifact_id)["editions"][0]["id"]
    )
    open_translation(app)
    widget(app, "text_area", "Vertaling").set_value("Concept in eerste project").run()
    widget(app, "text_area", "Bibliografische verwijzing of brontekst").set_value(
        "Eerste projectbron"
    ).run()
    widget(app, "text_input", "Projectbestand").set_value(str(other.path)).run()
    assert not app.error
    assert not app.exception
    assert widget(app, "text_area", "Vertaling").value == ""
    assert widget(app, "text_area", "Bibliografische verwijzing of brontekst").value == ""
    assert store.dossier(artifact_id)["annotations"] == []
    assert other.dossier(artifact_id)["annotations"] == []


def test_downloads_contain_fresh_reviewed_sheet_and_optional_metadata_is_not_required(workspace):
    _, store, artifact_id = workspace
    store.import_records(
        b"synthetic edition without optional fields",
        [{"external_id": "SYNTH-TRANSLATION", "text": SOURCE}],
        source="synthetic-ui-fixture",
        license="CC0 synthetic fixture only",
    )
    edition = store.dossier(artifact_id)["editions"][-1]
    proposal = seed_proposal(store, artifact_id, edition=edition, text="Exporteer deze vertaling")
    # Keep the actual AppTest download storage after the script run. This wrapper
    # neither replaces the UI nor mocks a store, worksheet, renderer or download.
    app = AppTest.from_string("""
from isc_helwigii.ui import main
import streamlit as st
from streamlit.runtime import get_instance
main()
st.session_state["test_download_storage"] = get_instance().media_file_mgr._storage
""").run()
    open_translation(app)
    widget(app, "selectbox", "Broneditie").set_value(edition["id"]).run()
    assert not app.error
    assert not app.exception
    widget(app, "text_area", "Beoordelingsgrond").set_value("Exportcontrole van de bronpassage.")
    widget(app, "button", "Beoordeling vastleggen").click().run()
    assert not app.error
    storage = app.session_state["test_download_storage"]
    downloads = {
        button.proto.label: storage.get_file(button.proto.url.rsplit("/", 1)[-1])
        for button in app.get("download_button")
    }
    sheet = json.loads(downloads["Vertaalblad downloaden (JSON)"].content)
    assert sheet["edition"]["id"] == edition["id"]
    assert sheet["edition"]["text"] == SOURCE
    assert sheet["target_language"] == "nl"
    assert sheet["coverage"]["ratio"] == 0.5
    assert sheet["annotations"][0]["id"] == proposal
    assert sheet["annotations"][0]["status"] == "accepted"
    assert sheet["annotations"][0]["review"]["reason"] == "Exportcontrole van de bronpassage."
    markdown = downloads["Vertaalblad downloaden (Markdown)"].content.decode()
    assert markdown.count("Exporteer deze vertaling") == 1
    assert "50.0%" in markdown
    assert "NIET VERTAALD" in markdown
    assert "Exportcontrole van de bronpassage." in markdown
