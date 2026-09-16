import json
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
    records = [
        {
            "external_id": f"SYNTH-{index:04d}",
            "language": f"fixture-language-{index:04d}",
            "text": f"invented text {index}",
            "synthetic": True,
        }
        for index in range(1001)
    ]
    store.import_records(
        b"fixture",
        records,
        source="synthetic-ui-fixture",
        license="CC0 synthetic fixture only",
    )
    with store.connection() as con:
        record_after_old_cutoff = json.loads(
            con.execute("SELECT record FROM editions ORDER BY id LIMIT 1 OFFSET 1000").fetchone()[0]
        )
    monkeypatch.setenv("ISC_HELWIGII_PROJECT", str(store.path))
    app = AppTest.from_file(str(Path(ui.__file__))).run()

    app.sidebar.radio[0].set_value("Corpuskwaliteit").run()
    next(button for button in app.button if button.label == "Corpusrapport genereren").click().run()

    assert not app.exception
    language_filter = next(box for box in app.selectbox if box.label == "Taal")
    language_filter.set_value(record_after_old_cutoff["language"]).run()
    assert any(
        "external_id" in frame.value
        and record_after_old_cutoff["external_id"] in set(frame.value["external_id"])
        for frame in app.dataframe
    )
    issue_filter = next(box for box in app.selectbox if box.label == "Probleemtype")
    issue_filter.set_value("synthetic_record").run()
    assert not app.exception
    next(button for button in app.button if button.label == "Referentieset voorbereiden").click().run()
    assert not app.exception
    assert any("geen gecertificeerde benchmark" in warning.value.lower() for warning in app.warning)
