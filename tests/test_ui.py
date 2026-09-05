from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest

from isc_helwigii import ui
from isc_helwigii.demo import seed_demo
from isc_helwigii.store import ResearchStore


def test_ui_project_demo_and_pages(tmp_path, monkeypatch):
    path = tmp_path / "ui.db"
    monkeypatch.setenv("ISC_HELWIGII_PROJECT", str(path))
    app = AppTest.from_file(str(Path(ui.__file__))).run()
    assert not app.exception
    app.button(key="init").click().run()
    assert path.exists()
    app.button(key="demo").click().run()
    assert len(ResearchStore(path).artifacts()) == 3
    for page in [
        "Tabletten",
        "Lezen & annoteren",
        "Vergelijken",
        "Materiaal",
        "Mythen & hypothesen",
        "Evaluatie",
        "Experimenten & export",
        "Mogelijkheden",
    ]:
        app.sidebar.radio[0].set_value(page).run()
        assert not app.exception, page
        assert not app.error, page


def test_ui_saves_translation_proposal(tmp_path, monkeypatch):
    store = ResearchStore(tmp_path / "ui.db")
    store.initialize()
    seed_demo(store)
    monkeypatch.setenv("ISC_HELWIGII_PROJECT", str(store.path))
    app = AppTest.from_file(str(Path(ui.__file__))).run()
    app.sidebar.radio[0].set_value("Lezen & annoteren").run()
    next(x for x in app.selectbox if x.label == "Annotatietype").set_value("translation").run()
    next(x for x in app.text_area if x.label == "Vertaling").set_value("Het water stijgt.")
    next(x for x in app.button if x.label == "Annotatie voorstellen").click().run()
    assert not app.error
    dossier = store.dossier(store.artifacts()[0]["id"])
    assert dossier["annotations"][0]["payload"]["text"] == "Het water stijgt."
