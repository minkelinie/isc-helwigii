"""Pinned, offline cuneiform inference; outputs are unreviewed research proposals.

Model: B. Lee Drake, Thalesian/cuneiformBase-400m (Apache-2.0).
Only the explicit download command uses a network connection. Optional ML
libraries are imported on first inference; the base package stays dependency free.
"""

import hashlib
import os
import re
import tempfile
import threading
import time
from functools import lru_cache
from pathlib import Path
from urllib.request import urlopen

from isc_helwigii import __version__
from isc_helwigii.analysis import tokens
from isc_helwigii.store import required

MODEL_ID = "Thalesian/cuneiformBase-400m"
MODEL_REVISION = "5cd996298b654eb60ea3cc0ed30e62ccefb94aef"
MODEL_FILES = {
    "README.md": {
        "size": 19150,
        "sha256": "95e918465bafa986ede56fe93da99c3bbfd594a314488be83178733b75c5b22d",
    },
    "config.json": {
        "size": 858,
        "sha256": "54be853237b1d10ad346fd33d0543bff88dea8f4b3d3df732994e5cb1ef571c7",
    },
    "generation_config.json": {
        "size": 172,
        "sha256": "10f526c167e280f35afe06716d8f224aff05771e048392ad99f432dc26ffc27f",
    },
    "tokenizer_config.json": {
        "size": 6902,
        "sha256": "bd3526cb44452300a3d563113aadaf96df7fe2f7e779fdb8c77af4b90c97279d",
    },
    "tokenizer.json": {
        "size": 16995089,
        "sha256": "56a43fd8b322b043fc6760fc94c1eef191f5fcb7aa0b5a964a708a2313bdbdc8",
    },
    "model.safetensors": {
        "size": 1582752536,
        "sha256": "32afedeb16f1091d3c5c4b26fe3d0a37bd1d9df06db31d625261fa001f615848",
    },
}
LANGUAGES = {"sux": "Sumerian", "akk": "Akkadian"}
FORMATS = {
    "transliteration": "transliteration",
    "complex-transliteration": "complex {language} transliteration",
    "cuneiform": "cuneiform",
}
GENERATION = {"max_new_tokens": 192, "num_beams": 4, "do_sample": False, "early_stopping": True}
WARNINGS = [
    "Experimenteel modelvoorstel; controleer namen, aantallen, ontkenningen en ontbrekende tekens.",
    "De lokale proef bevat fouten in aantallen en Akkadische zinnen; Akkadische uitvoer kan losse woordbetekenissen zijn. Geen nauwkeurigheidsgarantie.",
]


def default_model_dir():
    return Path(
        os.environ.get("ISC_HELWIGII_TRANSLATION_MODEL")
        or Path.home() / ".cache" / "isc-helwigii" / "cuneiformBase-400m"
    ).expanduser()


def canonical_language(value):
    aliases = {
        "sux": "sux",
        "sumerian": "sux",
        "sumerisch": "sux",
        "akk": "akk",
        "akkadian": "akk",
        "akkadisch": "akk",
    }
    result = aliases.get(str(value or "").strip().casefold())
    if result is None:
        raise ValueError("Kies Sumerisch (sux) of Akkadisch (akk); de brontaal wordt niet geraden.")
    return result


def _validate_request(text, source_language, input_format, target_language):
    required(text, "source text")
    if (
        not tokens(text)
        or re.fullmatch(r"[\s.xX…\[\]()\-–—<>⸢⸣⌈⌉?!_+/#*|:;]+", text)
        or text.strip().casefold() in {"n.n.b.", "onbekend", "unknown"}
    ):
        raise ValueError(
            "Deze passage bevat alleen ontbrekende of onbekende tekst; kies leesbare brontekst."
        )
    if len(text) > 16000:
        raise ValueError(
            "Kies een kortere bronpassage; het model ondersteunt maximaal 512 invoertokens."
        )
    language = canonical_language(source_language)
    if target_language != "en":
        raise ValueError("Dit lokale model vertaalt alleen naar Engels (en).")
    if input_format not in FORMATS:
        raise ValueError(
            "Kies transliteration, complex-transliteration of cuneiform als invoervorm."
        )
    return language


def model_status(model_dir):
    path = Path(model_dir).expanduser().resolve()
    missing = [
        name
        for name, info in MODEL_FILES.items()
        if not (path / name).is_file() or (path / name).stat().st_size != info["size"]
    ]
    return {
        "installed": not missing,
        "error": (
            f"Modelbestanden ontbreken of hebben een andere grootte: {', '.join(missing)}. "
            f"Installeer met isc-helwigii download-model '{path}'."
            if missing
            else None
        ),
        "model_id": MODEL_ID,
        "revision": MODEL_REVISION,
        "path": str(path),
    }


def _verify_file(path, expected):
    with path.open("rb") as source:
        checksum = hashlib.file_digest(source, "sha256").hexdigest()
    if checksum != expected["sha256"] or path.stat().st_size != expected["size"]:
        raise ValueError(
            f"Modelcontrole mislukt voor {path.name}; bestaand bestand wordt niet overschreven."
        )


def download_model(model_dir):
    """Explicit network operation; pinned URLs and hashes, atomic exclusive files."""
    path = Path(model_dir).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    # Check all existing files before spending bandwidth or creating new files.
    for name, expected in MODEL_FILES.items():
        if (path / name).exists():
            _verify_file(path / name, expected)
    for name, expected in MODEL_FILES.items():
        destination = path / name
        if destination.exists():
            continue
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=path, prefix=".download-", delete=False) as output:
                temporary = Path(output.name)
                url = f"https://huggingface.co/{MODEL_ID}/resolve/{MODEL_REVISION}/{name}"
                with urlopen(url, timeout=60) as response:
                    size = 0
                    while chunk := response.read(4 * 1024 * 1024):
                        size += len(chunk)
                        if size > expected["size"]:
                            raise ValueError(f"Onverwachte downloadgrootte voor {name}.")
                        output.write(chunk)
            _verify_file(temporary, expected)
            # Hard link publishes a complete verified file without overwriting.
            os.link(temporary, destination)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    return model_status(path)


class _Runtime:
    def __init__(self, path):
        for name, expected in MODEL_FILES.items():
            _verify_file(path / name, expected)
        try:
            import torch
            import transformers
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
        except ImportError as exc:
            raise ValueError(
                "Installeer de lokale vertaalbibliotheken met pip install 'isc-helwigii[translation]'."
            ) from exc
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(
                str(path),
                local_files_only=True,
                trust_remote_code=False,
                use_fast=True,
            )
            self.model = (
                AutoModelForSeq2SeqLM.from_pretrained(
                    str(path),
                    local_files_only=True,
                    trust_remote_code=False,
                    use_safetensors=True,
                    dtype=torch.float32,
                )
                .to("cpu")
                .eval()
            )
        except (OSError, ValueError, RuntimeError) as exc:
            raise ValueError(f"Het lokale vertaalmodel kon niet worden geladen: {exc}") from exc
        self.torch = torch
        self.lock = threading.Lock()
        self.versions = {"torch": torch.__version__, "transformers": transformers.__version__}

    def translate(self, prompt):
        with self.lock, self.torch.inference_mode():
            inputs = self.tokenizer(prompt, return_tensors="pt", truncation=False)
            ids = inputs["input_ids"][0].tolist()
            if len(ids) > 512:
                raise ValueError(
                    f"Deze passage gebruikt {len(ids)} invoertokens; kies een kortere passage (maximaal 512)."
                )
            if self.tokenizer.unk_token_id in ids:
                raise ValueError(
                    "De invoer bevat tekens die het model niet kent; controleer de gekozen invoervorm."
                )
            begin = time.monotonic()
            try:
                output = self.model.generate(**inputs, **GENERATION)[0].tolist()
            except (RuntimeError, ValueError) as exc:
                raise ValueError(f"Lokale vertaling mislukt: {exc}") from exc
            if not output or output[-1] != self.tokenizer.eos_token_id:
                raise ValueError(
                    "De uitvoerlimiet is bereikt; kies een kortere passage. Er is geen onvolledig voorstel opgeslagen."
                )
            if self.tokenizer.unk_token_id in output:
                raise ValueError(
                    "Het model produceerde onbekende tekens; er is geen voorstel opgeslagen."
                )
            text = self.tokenizer.decode(output, skip_special_tokens=True).strip()
            required(text, "model output")
            return {
                "text": text,
                "input_tokens": len(ids),
                "output_tokens": len(output) - 1,
                "elapsed_seconds": round(time.monotonic() - begin, 3),
                "runtime": {**self.versions, "device": "cpu", "dtype": "float32"},
            }


@lru_cache(maxsize=1)
def _load_runtime(path, stamp):
    # File size and timestamps invalidate the cache after a local file change.
    return _Runtime(Path(path))


def translate_text(
    text, *, model_dir=None, source_language, input_format="transliteration", target_language="en"
):
    language = _validate_request(text, source_language, input_format, target_language)
    status = model_status(model_dir or default_model_dir())
    if not status["installed"]:
        raise ValueError(status["error"])
    path = Path(status["path"])
    stamp = tuple(
        (
            name,
            (path / name).stat().st_size,
            (path / name).stat().st_mtime_ns,
            (path / name).stat().st_ctime_ns,
        )
        for name in MODEL_FILES
    )
    name = LANGUAGES[language]
    form = (
        f"complex {name} transliteration"
        if input_format == "complex-transliteration"
        else f"{name} {FORMATS[input_format]}"
    )
    prompt = f"Translate {form} to English: {text}"
    result = _load_runtime(str(path), stamp).translate(prompt)
    from isc_helwigii.translation_quality import assess_translation

    return {
        **result,
        "quality_checks": assess_translation(
            text, result["text"], source_language=language, input_format=input_format
        ),
        "prompt": prompt,
        "source_language": language,
        "target_language": "en",
        "input_format": input_format,
        "normalization": "none",
        "generation": dict(GENERATION),
        "warnings": list(WARNINGS),
        "model": {
            "id": MODEL_ID,
            "revision": MODEL_REVISION,
            "license": "Apache-2.0",
            "files": MODEL_FILES,
            "source": f"https://huggingface.co/{MODEL_ID}/tree/{MODEL_REVISION}",
        },
    }


def propose_model_translation(
    store,
    edition_id,
    *,
    model_dir=None,
    actor,
    start=0,
    end=None,
    source_language=None,
    input_format="transliteration",
    target_language="en",
):
    """Generate once on explicit request, preserving source and creating no review."""
    required(actor, "actor")
    edition = store.edition(edition_id)
    source = edition.get("text", "")
    end = len(source) if end is None else end
    if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(source):
        raise ValueError("Kies geldige Unicode-posities binnen deze broneditie.")
    text = source[start:end]
    language = _validate_request(
        text, source_language or edition.get("language"), input_format, target_language
    )
    result = translate_text(
        text,
        model_dir=model_dir,
        source_language=language,
        input_format=input_format,
        target_language=target_language,
    )
    required(result["text"], "model output")
    # Keep diagnostics bound to the exact selected passage and literal model output.
    # The fallback also supports inference providers that do not supply diagnostics.
    if "quality_checks" not in result:
        from isc_helwigii.translation_quality import assess_translation

        result["quality_checks"] = assess_translation(
            text,
            result["text"],
            source_language=language,
            input_format=input_format,
            target_language=target_language,
        )
    implementation = Path(__file__).read_bytes()
    inputs = {
        "edition_id": edition_id,
        "snapshot_id": edition["snapshot_id"],
        "source_text": text,
        "start": start,
        "end": end,
        "declared_language": edition.get("language"),
        "source_language": language,
        "input_format": input_format,
        "target_language": target_language,
        "software_version": __version__,
        "implementation_sha256": hashlib.sha256(implementation).hexdigest(),
    }
    run = store.save_run("local-model-translation-v1", inputs, result, actor=actor)
    annotation = store.annotate(
        edition["artifact_id"],
        "translation",
        {
            "edition_id": edition_id,
            "start": start,
            "end": end,
            "target_language": target_language,
            "text": result["text"],
            "quality_checks": result["quality_checks"],
            "model": {"id": MODEL_ID, "revision": MODEL_REVISION, "run_id": run},
            "reference": f"Automatisch modelvoorstel · {MODEL_ID} · {MODEL_REVISION} · experiment {run}",
        },
        actor=actor,
        evidence=[edition["snapshot_id"], edition_id, run],
        origin="inferred",
    )
    return {**result, "annotation_id": annotation, "run_id": run}
