import json

from isc_helwigii.cli import main
from isc_helwigii.demo import seed_demo
from isc_helwigii.store import ResearchStore


def test_paged_search_and_explicit_edition(tmp_path):
    store = ResearchStore(tmp_path / "p.db")
    store.initialize()
    seed_demo(store)
    assert store.statistics()["artifacts"] == 3
    assert len(store.artifacts(limit=1, offset=1)) == 1
    assert store.artifacts(limit=1, offset=1)[0] != store.artifacts(limit=1)[0]
    found = store.artifacts("mountain", limit=1)
    assert found[0]["external_id"] == "DEMO-B"
    edition = store.dossier(found[0]["id"])["editions"][0]
    assert store.edition(edition["id"])["text"] == "water rises mountain survives"


def test_cli_import_annotation_review_and_experiment(tmp_path, capsys):
    project = tmp_path / "p.db"
    store = ResearchStore(project)
    store.initialize()
    source = tmp_path / "source.json"
    source.write_text(json.dumps([{"external_id": "X", "text": "a b", "language": "akk"}]))
    assert (
        main(["import", str(project), str(source), "--source", "test", "--license", "private"]) == 0
    )
    dossier = store.dossier(store.artifacts()[0]["id"])
    request = tmp_path / "request.json"
    request.write_text(
        json.dumps(
            {
                "artifact_id": dossier["id"],
                "kind": "category",
                "payload": {"label": "letter"},
                "actor": "a",
                "evidence": [dossier["editions"][0]["snapshot_id"]],
            }
        )
    )
    capsys.readouterr()
    assert main(["annotate", str(project), str(request)]) == 0
    annotation = json.loads(capsys.readouterr().out)["annotation_id"]
    assert (
        main(
            ["review", str(project), annotation, "accepted", "--actor", "r", "--reason", "checked"]
        )
        == 0
    )
    request.write_text(
        json.dumps(
            {
                "method": "evaluation",
                "parameters": {"gold": {"X": "letter"}, "predicted": {"X": "letter"}},
                "actor": "a",
            }
        )
    )
    assert main(["run", str(project), str(request)]) == 0
    assert main(["runs", str(project)]) == 0
    assert store.dossier(dossier["id"])["annotations"][0]["status"] == "accepted"
    assert store.runs()[0]["outputs"]["accuracy_all"] == 1
