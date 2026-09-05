"""Application operations shared by the CLI and UI, with frozen experiment inputs."""

from pathlib import Path

from isc_helwigii import __version__, analysis, evaluation
from isc_helwigii.store import digest

METHODS = (
    "text",
    "material",
    "motif-network",
    "translation-memory",
    "chronology",
    "evaluation",
    "ranking-evaluation",
    "reading-evaluation",
    "split",
)


def editions(store, query="", limit=None):
    result = []
    for artifact in store.artifacts(query, limit=limit):
        for edition in store.dossier(artifact["id"])["editions"]:
            result.append(
                {
                    **edition["record"],
                    "id": edition["id"],
                    "artifact_id": artifact["id"],
                    "snapshot_id": edition["snapshot_id"],
                    "source": artifact["source"],
                }
            )
    return result


def reviewed_translations(store):
    entries = []
    with store.connection() as con:
        artifacts = [
            r[0]
            for r in con.execute(
                "SELECT DISTINCT artifact_id FROM annotations WHERE kind='translation'"
            )
        ]
    for artifact_id in artifacts:
        dossier = store.dossier(artifact_id)
        edition_map = {e["id"]: e for e in dossier["editions"]}
        for annotation in dossier["annotations"]:
            if annotation["kind"] != "translation":
                continue
            payload = annotation["payload"]
            edition = edition_map[payload["edition_id"]]
            entries.append(
                {
                    **payload,
                    "id": annotation["id"],
                    "artifact_id": artifact_id,
                    "status": annotation["status"],
                    "language": edition["record"].get("language", "unknown"),
                    "source_text": edition["record"]["text"][payload["start"] : payload["end"]],
                    "evidence": annotation["evidence"],
                }
            )
    return entries


def run_method(store, method, parameters, *, actor):
    if method not in METHODS or not isinstance(parameters, dict):
        raise ValueError("unsupported method or parameters")
    inputs = {"parameters": parameters, "software_version": __version__}
    if method == "text":
        selected = [store.edition(parameters.get(k)) for k in ("left", "right")]
        inputs["editions"] = selected
        a, b = selected
        if a.get("language", "unknown") != b.get(
            "language", "unknown"
        ) or not analysis.valid_language(a.get("language")):
            outputs = {"status": "abstained", "reason": "language unknown or mismatched"}
        else:
            outputs = analysis.text_similarity(a.get("text", ""), b.get("text", ""))
    elif method == "translation-memory":
        inputs["translation_entries"] = reviewed_translations(store)
        outputs = analysis.translation_memory(
            parameters.get("query", ""),
            inputs["translation_entries"],
            parameters.get("language", "unknown"),
            parameters.get("target_language", "en"),
        )
    elif method in ("material", "motif-network", "chronology"):
        chosen = parameters.get("artifacts", [])
        if not isinstance(chosen, list) or not chosen or len(set(chosen)) != len(chosen):
            raise ValueError("select distinct artifacts")
        dossiers = [store.dossier(a) for a in chosen]
        inputs["dossiers"] = dossiers
        kind = {"material": "material", "motif-network": "motif", "chronology": "date"}[method]
        accepted = [
            [a for a in d["annotations"] if a["kind"] == kind and a["status"] == "accepted"]
            for d in dossiers
        ]
        if method == "motif-network":
            witnesses = [
                {
                    "id": d["id"],
                    "motifs": sorted(
                        {
                            a["payload"]["name"]
                            for a in aa
                            if a["payload"].get("presence", "present") == "present"
                        }
                    )
                    if any(a["payload"].get("presence", "present") != "uncertain" for a in aa)
                    else None,
                }
                for d, aa in zip(dossiers, accepted, strict=True)
            ]
            outputs = analysis.motif_network(witnesses)
        else:
            if len(dossiers) != 2:
                raise ValueError("select exactly two artifacts")
            if any(len(aa) > 1 for aa in accepted):
                outputs = {
                    "status": "abstained",
                    "reason": "conflicting accepted annotations; resolve or supersede explicitly",
                }
            elif method == "material":
                outputs = analysis.compare_materials(
                    *[aa[0]["payload"] if aa else None for aa in accepted]
                )
            else:
                outputs = analysis.date_overlap(
                    *[aa[0]["payload"].get("interval") if aa else None for aa in accepted]
                )
    elif method == "evaluation":
        outputs = evaluation.evaluate_labels(
            parameters.get("gold", {}), parameters.get("predicted", {})
        )
    elif method == "ranking-evaluation":
        outputs = evaluation.evaluate_rankings(
            parameters.get("gold", {}), parameters.get("predicted", {}), parameters.get("k", 10)
        )
    elif method == "reading-evaluation":
        outputs = evaluation.evaluate_readings(
            parameters.get("gold", {}), parameters.get("predicted", {})
        )
    else:
        outputs = evaluation.grouped_split(parameters.get("records", []), parameters.get("seed", 0))
    # Save the actual implementation text as well as its digest, without executing it on restore.
    module = (
        evaluation
        if method in ("evaluation", "split", "ranking-evaluation", "reading-evaluation")
        else analysis
    )
    source = Path(module.__file__).read_text(encoding="utf-8")
    inputs["implementation"] = {
        "filename": Path(module.__file__).name,
        "sha256": digest(source.encode()),
        "source": source,
    }
    run_id = store.save_run(outputs.get("method", method + "-v1"), inputs, outputs, actor=actor)
    return {"run_id": run_id, "outputs": outputs}
