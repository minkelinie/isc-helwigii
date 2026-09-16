"""Model plumbing uses synthetic input; these tests do not validate translations."""

import hashlib
import io

import pytest

from isc_helwigii import local_translation as local
from isc_helwigii.store import ResearchStore
from isc_helwigii.translation import build_translation_sheet, render_translation_markdown


@pytest.fixture
def source(tmp_path):
    store = ResearchStore(tmp_path / "synthetic.db")
    store.initialize()
    store.import_records(
        b"synthetic model fixture",
        [
            {
                "external_id": "MODEL-TEST",
                "language": "sumerian",
                "text": "a₂ b\na₂ b",
                "synthetic": True,
            }
        ],
        source="synthetic",
        license="CC0 synthetic test only",
    )
    artifact = store.artifacts()[0]["id"]
    return store, store.dossier(artifact)["editions"][0]["id"]


def test_model_proposal_preserves_exact_span_and_pending_evidence(source, monkeypatch):
    store, edition_id = source
    before = store.edition(edition_id)
    calls = []

    def infer(text, **kwargs):
        calls.append((text, kwargs))
        return {
            "text": "Synthetic output",
            "model": {"id": local.MODEL_ID, "revision": local.MODEL_REVISION},
            "prompt": "synthetic prompt",
            "warnings": ["Requires review"],
        }

    monkeypatch.setattr(local, "translate_text", infer)
    result = local.propose_model_translation(
        store, edition_id, model_dir="unused", actor="tester", start=5, end=9
    )
    assert calls[0][0] == "a₂ b"
    assert calls[0][1]["source_language"] == "sux"
    annotation = store.dossier(before["artifact_id"])["annotations"][0]
    assert annotation["id"] == result["annotation_id"]
    assert annotation["status"] == "pending"
    assert annotation["origin"] == "inferred"
    assert annotation["payload"]["start"] == 5
    assert annotation["payload"]["end"] == 9
    assert annotation["payload"]["target_language"] == "en"
    assert annotation["payload"]["model"]["run_id"] == result["run_id"]
    assert set(annotation["evidence"]) == {before["snapshot_id"], edition_id, result["run_id"]}
    run = store.runs()[0]
    assert run["inputs"]["source_text"] == "a₂ b"
    assert run["inputs"]["declared_language"] == "sumerian"
    assert run["inputs"]["source_language"] == "sux"
    assert run["outputs"]["text"] == "Synthetic output"
    checks = result["quality_checks"]
    assert checks == run["outputs"]["quality_checks"] == annotation["payload"]["quality_checks"]
    assert checks["source_sha256"] == hashlib.sha256("a₂ b".encode()).hexdigest()
    assert checks["quantities"]["status"] == "not_assessed"
    assert build_translation_sheet(store, edition_id, "en")["coverage"]["ratio"] == 0
    for decision in (None, "accepted"):
        if decision:
            store.review(
                annotation["id"], decision, actor="tester", reason="synthetic fixture only"
            )
        sheet = build_translation_sheet(store, edition_id, "en")
        assert "geen nauwkeurigheidsscore" in render_translation_markdown(sheet)
        assert sheet["annotations"][0]["payload"]["quality_checks"] == checks
    assert store.edition(edition_id) == before
    assert build_translation_sheet(store, edition_id, "en")["coverage"]["ratio"] == 0.5


@pytest.mark.parametrize(
    "options",
    [
        {"start": -1},
        {"end": 99},
        {"start": 1, "end": 1},
        {"start": True},
        {"target_language": "nl"},
        {"source_language": "unknown"},
        {"input_format": "photograph"},
        {"actor": " "},
    ],
)
def test_invalid_request_cannot_infer_or_write(source, monkeypatch, options):
    store, edition_id = source

    def unexpected(*args, **kwargs):
        pytest.fail("invalid request reached inference")

    monkeypatch.setattr(local, "translate_text", unexpected)
    with pytest.raises(ValueError):
        local.propose_model_translation(
            store, edition_id, model_dir="unused", **{"actor": "tester", **options}
        )
    assert store.runs() == []
    assert store.dossier(store.edition(edition_id)["artifact_id"])["annotations"] == []


def test_inference_failure_does_not_save_run_or_annotation(source, monkeypatch):
    def fail(*args, **kwargs):
        raise ValueError("model is unavailable")

    monkeypatch.setattr(local, "translate_text", fail)
    store, edition_id = source
    with pytest.raises(ValueError, match="unavailable"):
        local.propose_model_translation(store, edition_id, model_dir="unused", actor="tester")
    assert store.runs() == []


@pytest.mark.parametrize("text", ["[x]", "[x x]", "x-x", "[... …]", "⸢x⸣", "n.n.b."])
def test_damage_only_source_cannot_reach_model_or_create_proposal(tmp_path, monkeypatch, text):
    store = ResearchStore(tmp_path / "damage.db")
    store.initialize()
    store.import_records(
        b"synthetic damage only",
        [
            {"external_id": "DAMAGE", "language": "sux", "text": text, "synthetic": True},
        ],
        source="synthetic",
        license="CC0 synthetic only",
    )
    artifact = store.artifacts()[0]["id"]
    edition_id = store.dossier(artifact)["editions"][0]["id"]
    monkeypatch.setattr(local, "translate_text", lambda *a, **kw: pytest.fail("no readable source"))
    with pytest.raises(ValueError, match="leesbare brontekst"):
        local.propose_model_translation(store, edition_id, actor="tester")
    assert store.runs() == []
    assert store.dossier(artifact)["annotations"] == []


def test_download_verifies_bytes_and_never_overwrites(tmp_path, monkeypatch):
    content = b"synthetic model bytes"
    monkeypatch.setattr(
        local,
        "MODEL_FILES",
        {"config.json": {"size": len(content), "sha256": hashlib.sha256(content).hexdigest()}},
    )
    urls = []

    def fetch(url, **kwargs):
        urls.append(url)
        return io.BytesIO(content)

    monkeypatch.setattr(local, "urlopen", fetch)
    result = local.download_model(tmp_path)
    assert result["installed"]
    assert local.MODEL_REVISION in urls[0]
    local.download_model(tmp_path)
    assert len(urls) == 1
    (tmp_path / "config.json").write_bytes(b"user file")
    with pytest.raises(ValueError, match="config.json"):
        local.download_model(tmp_path)
    assert (tmp_path / "config.json").read_bytes() == b"user file"


def test_corrupt_download_leaves_no_loadable_file(tmp_path, monkeypatch):
    monkeypatch.setattr(
        local,
        "MODEL_FILES",
        {"config.json": {"size": 4, "sha256": hashlib.sha256(b"good").hexdigest()}},
    )
    monkeypatch.setattr(local, "urlopen", lambda *a, **kw: io.BytesIO(b"bad!"))
    with pytest.raises(ValueError):
        local.download_model(tmp_path)
    assert not list(tmp_path.iterdir())


def test_offline_status_does_not_import_ml_or_download(tmp_path, monkeypatch):
    monkeypatch.setattr(local, "urlopen", lambda *a, **kw: pytest.fail("network used"))
    assert not local.model_status(tmp_path)["installed"]
    with pytest.raises(ValueError, match="download-model"):
        local.translate_text("lugal", model_dir=tmp_path, source_language="sux")


def test_cli_download_and_translate_routes(source, tmp_path, monkeypatch, capsys):
    from isc_helwigii.cli import main

    monkeypatch.setattr(
        local, "download_model", lambda path: {"path": str(path), "installed": True}
    )
    assert main(["download-model", str(tmp_path)]) == 0
    assert '"installed": true' in capsys.readouterr().out
    store, edition_id = source
    monkeypatch.setattr(
        local,
        "translate_text",
        lambda *a, **kw: {
            "text": "Synthetic output",
            "model": {"id": local.MODEL_ID, "revision": local.MODEL_REVISION},
        },
    )
    assert (
        main(
            [
                "translate",
                str(store.path),
                edition_id,
                "--actor",
                "tester",
                "--model-dir",
                str(tmp_path),
                "--start",
                "5",
                "--end",
                "9",
            ]
        )
        == 0
    )
    assert '"annotation_id"' in capsys.readouterr().out
    assert (
        main(
            [
                "translate",
                str(store.path),
                edition_id,
                "--actor",
                "tester",
                "--target-language",
                "nl",
            ]
        )
        == 2
    )
    assert "Engels" in capsys.readouterr().err


@pytest.mark.parametrize(
    "input_ids,output,reason",
    [
        ([3] * 513, [0, 4, 1], "512"),
        ([3, 2, 1], [0, 4, 1], "invoer"),
        ([3, 1], [0, 4, 4], "uitvoerlimiet"),
        ([3, 1], [0, 2, 1], "onbekende"),
    ],
)
def test_runtime_refuses_truncation_and_unknown_tokens(input_ids, output, reason):
    import threading
    from contextlib import nullcontext
    from types import SimpleNamespace

    class Row(list):
        def tolist(self):
            return list(self)

    class Tokenizer:
        unk_token_id = 2
        eos_token_id = 1

        def __call__(self, prompt, **kwargs):
            assert kwargs["truncation"] is False
            return {"input_ids": [Row(input_ids)]}

        def decode(self, *args, **kwargs):
            pytest.fail("unsafe model output was decoded")

    runtime = local._Runtime.__new__(local._Runtime)
    runtime.tokenizer = Tokenizer()
    runtime.model = SimpleNamespace(generate=lambda **kwargs: [Row(output)])
    runtime.torch = SimpleNamespace(inference_mode=nullcontext)
    runtime.lock = threading.Lock()
    with pytest.raises(ValueError, match=reason):
        runtime.translate("synthetic prompt")
