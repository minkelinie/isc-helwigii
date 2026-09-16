"""Explicit rechecks use stored passages and survive ordinary UI reruns."""

import pytest

pytest.importorskip("streamlit")

from test_translation_ui import open_translation, seed_proposal, widget, workspace as workspace


def test_explicit_recheck_uses_selected_saved_proposal_and_preserves_draft(workspace):
    app, store, artifact_id = workspace
    first = seed_proposal(store, artifact_id, start=5, end=9, target="en", text="god")
    second = seed_proposal(store, artifact_id, target="en", text="another god")
    before = store.dossier(artifact_id)
    open_translation(app)
    widget(app, "text_input", "Doeltaal").set_value("en").run()
    widget(app, "selectbox", "Voorstel beoordelen").set_value(first).run()
    widget(app, "text_area", "Ongewijzigde bronpassage").set_value("𒀭 ša").run()
    widget(app, "text_area", "Vertaling").set_value("Unsaved draft").run()
    assert store.runs() == []
    assert widget(app, "button", "Opgeslagen vertaling opnieuw controleren").disabled
    widget(app, "selectbox", "Schrijfwijze voor hercontrole").set_value("cuneiform").run()
    widget(app, "button", "Opgeslagen vertaling opnieuw controleren").click().run()
    assert not app.exception
    assert not app.error
    assert len(store.runs()) == 1
    run = store.runs()[0]
    assert run["inputs"]["annotation_id"] == first
    assert run["inputs"]["start"] == 5
    assert run["inputs"]["end"] == 9
    assert run["inputs"]["translation_text"] == "god"
    assert run["inputs"]["input_format"] == "cuneiform"
    assert run["outputs"]["quantities"]["status"] == "not_assessed"
    assert store.dossier(artifact_id) == before
    assert widget(app, "text_area", "Vertaling").value == "Unsaved draft"
    assert any(run["id"] in text.value for text in app.text)
    app.run()
    assert len(store.runs()) == 1
    widget(app, "selectbox", "Voorstel beoordelen").set_value(second).run()
    assert widget(app, "selectbox", "Schrijfwijze voor hercontrole").value == ""
    assert not any(run["id"] in text.value for text in app.text)
    widget(app, "selectbox", "Voorstel beoordelen").set_value(first).run()
    assert any(run["id"] in text.value for text in app.text)
