from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest

from isc_helwigii import ui
from isc_helwigii.store import ResearchStore


def test_corpus_workspace_audits_filters_and_prepares_synthetic_abstention(
    tmp_path, monkeypatch
):
    store = ResearchStore(tmp_path / "ui.db")
    store.initialize()
    store.import_records(
        b"fixture",
        [
            {
                "external_id": "SYNTH-A",
                "language": "demo",
                "text": "invented text",
                "synthetic": True,
            }
        ],
        source="synthetic-ui-fixture",
        license="CC0 synthetic fixture only",
    )
    monkeypatch.setenv("ISC_HELWIGII_PROJECT", str(store.path))
    app = AppTest.from_file(str(Path(ui.__file__))).run()

    app.sidebar.radio[0].set_value("Corpuskwaliteit").run()
    next(button for button in app.button if button.label == "Corpusrapport genereren").click().run()

    assert not app.exception
    assert any(frame.value.shape[0] == 1 for frame in app.dataframe)
    issue_filter = next(box for box in app.selectbox if box.label == "Probleemtype")
    issue_filter.set_value("synthetic_record").run()
    assert not app.exception
    next(button for button in app.button if button.label == "Referentieset voorbereiden").click().run()
    assert not app.exception
    assert any("geen gecertificeerde benchmark" in warning.value.lower() for warning in app.warning)
