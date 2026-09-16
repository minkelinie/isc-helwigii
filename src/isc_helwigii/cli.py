"""Command-line entrypoint for stable ISC Helwigii operations."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import zipfile
from collections.abc import Sequence
from pathlib import Path

from isc_helwigii import __version__
from isc_helwigii.config import Settings
from isc_helwigii.database import inspect_database


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser without causing side effects."""
    parser = argparse.ArgumentParser(prog="isc-helwigii")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command")
    config_parser = commands.add_parser("config", help="show effective runtime paths")
    config_parser.add_argument("--json", action="store_true", dest="as_json")
    health_parser = commands.add_parser("health", help="inspect the configured database")
    health_parser.add_argument("--database", type=Path)
    health_parser.add_argument("--json", action="store_true", dest="as_json")
    for name in ("init", "demo", "list", "runs"):
        sub = commands.add_parser(name)
        sub.add_argument("project", type=Path)
        if name == "list":
            sub.add_argument("--query", default="")
    sub = commands.add_parser("audit", help="audit corpus metadata and evidence")
    sub.add_argument("project", type=Path)
    sub.add_argument("--output", type=Path, help="new JSON export path")
    sub = commands.add_parser(
        "reference-set", help="prepare an evidence-linked category reference set"
    )
    sub.add_argument("project", type=Path)
    sub.add_argument("--axis", default="genre")
    sub.add_argument("--seed", default="42")
    sub.add_argument("--output", type=Path, help="new JSON export path")
    sub = commands.add_parser("dossier")
    sub.add_argument("project", type=Path)
    sub.add_argument("artifact")
    sub = commands.add_parser("prepare", help="prepare a corpus-wide passage research dossier")
    sub.add_argument("project", type=Path)
    sub.add_argument("edition_id")
    sub.add_argument("--actor", required=True)
    sub.add_argument("--start", type=int, default=0)
    sub.add_argument("--end", type=int)
    sub.add_argument("--limit", type=int, default=10)
    sub.add_argument("--target-language", default="nl")
    sub = commands.add_parser(
        "translation-sheet", help="inspect and export reviewed translations for one source edition"
    )
    sub.add_argument("project", type=Path)
    sub.add_argument("edition_id")
    sub.add_argument("--target-language", default="nl")
    sub.add_argument("--format", choices=["json", "markdown"], default="json")
    sub.add_argument("--output", type=Path, help="new export path (never overwritten)")
    sub = commands.add_parser(
        "download-model", help="download and verify the pinned local translation model (1.6 GB)"
    )
    sub.add_argument("directory", type=Path)
    sub = commands.add_parser(
        "translate", help="generate an unreviewed local model translation for a source passage"
    )
    sub.add_argument("project", type=Path)
    sub.add_argument("edition_id")
    sub.add_argument("--actor", required=True)
    sub.add_argument("--model-dir", type=Path)
    sub.add_argument("--start", type=int, default=0)
    sub.add_argument("--end", type=int)
    sub.add_argument(
        "--source-language",
        help="explicit Sumerian/Akkadian override; recorded with original metadata",
    )
    sub.add_argument("--target-language", default="en")
    sub.add_argument(
        "--input-format",
        choices=["transliteration", "complex-transliteration", "cuneiform"],
        default="transliteration",
    )
    sub = commands.add_parser(
        "recheck-translation", help="append an offline quality check of a saved translation"
    )
    sub.add_argument("project", type=Path)
    sub.add_argument("annotation_id")
    sub.add_argument("--actor", required=True)
    sub.add_argument("--source-language", choices=["sux", "akk"], required=True)
    sub.add_argument(
        "--input-format",
        choices=["transliteration", "complex-transliteration", "cuneiform"],
        required=True,
    )
    sub = commands.add_parser("import")
    sub.add_argument("project", type=Path)
    sub.add_argument("file", type=Path)
    sub.add_argument("--format", choices=["native", "atf", "oracc-catalogue"], default="native")
    sub.add_argument("--source", required=True)
    sub.add_argument("--license", required=True)
    sub = commands.add_parser("import-legacy")
    sub.add_argument("project", type=Path)
    sub.add_argument("file", type=Path)
    sub.add_argument("--source", required=True)
    sub.add_argument("--license", required=True)
    sub.add_argument("--limit", type=int, default=500)
    for name in ("annotate", "run"):
        sub = commands.add_parser(name)
        sub.add_argument("project", type=Path)
        sub.add_argument("file", type=Path, help="JSON request file")
    sub = commands.add_parser("review")
    sub.add_argument("project", type=Path)
    sub.add_argument("annotation")
    sub.add_argument("decision", choices=["accepted", "rejected"])
    sub.add_argument("--actor", required=True)
    sub.add_argument("--reason", required=True)
    for name in ("export", "restore"):
        sub = commands.add_parser(name)
        sub.add_argument("source", type=Path)
        sub.add_argument("destination", type=Path)
    sub = commands.add_parser("start", help="open a locally bound research interface")
    sub.add_argument("project", type=Path)
    sub.add_argument("--port", type=int, default=8501)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Parse command-line arguments and return a process exit code."""
    args = build_parser().parse_args(argv)
    if args.command == "config":
        settings = Settings.from_env()
        if args.as_json:
            sys.stdout.write(json.dumps(settings.to_dict(), indent=2, sort_keys=True) + "\n")
        else:
            for key, value in settings.to_dict().items():
                sys.stdout.write(f"{key}={value}\n")
        return 0
    if args.command == "health":
        path = args.database or Settings.from_env().database_path
        report = inspect_database(path)
        if args.as_json:
            sys.stdout.write(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n")
        else:
            sys.stdout.write(f"status={report.status}\n")
            sys.stdout.write(f"database_path={report.path}\n")
            sys.stdout.write(f"schema={report.schema}\n")
        return {"healthy": 0, "degraded": 1}.get(report.status, 2)
    if args.command:
        try:
            result = research_command(args)
            if (
                args.command == "translation-sheet"
                and args.format == "markdown"
                and args.output is None
            ):
                from isc_helwigii.translation import render_translation_markdown

                sys.stdout.write(render_translation_markdown(result))
            else:
                sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
            return 0
        except (ValueError, OSError, sqlite3.Error, zipfile.BadZipFile) as exc:
            sys.stderr.write(f"error: {exc}\n")
            return 2
    return 0


def research_command(args):
    from isc_helwigii.bundles import export_bundle, restore_bundle
    from isc_helwigii.corpus import audit_corpus, prepare_reference_set, write_json_export
    from isc_helwigii.demo import seed_demo
    from isc_helwigii.ingest import PARSERS
    from isc_helwigii.research import run_method
    from isc_helwigii.store import ResearchStore

    if args.command == "download-model":
        from isc_helwigii.local_translation import download_model

        return download_model(args.directory)
    if args.command == "export":
        return export_bundle(ResearchStore(args.source), args.destination)
    if args.command == "restore":
        return {"project": str(restore_bundle(args.source, args.destination).path)}
    store = ResearchStore(args.project)
    if args.command == "recheck-translation":
        from isc_helwigii.translation_recheck import recheck_translation

        return recheck_translation(
            store,
            args.annotation_id,
            actor=args.actor,
            source_language=args.source_language,
            input_format=args.input_format,
        )
    if args.command == "translate":
        from isc_helwigii.local_translation import propose_model_translation

        return propose_model_translation(
            store,
            args.edition_id,
            model_dir=args.model_dir,
            actor=args.actor,
            start=args.start,
            end=args.end,
            source_language=args.source_language,
            input_format=args.input_format,
            target_language=args.target_language,
        )
    if args.command == "init":
        store.initialize()
        return {"project": str(store.path)}
    if args.command == "demo":
        return {"snapshot_id": seed_demo(store)}
    if args.command == "list":
        return store.artifacts(args.query)
    if args.command == "dossier":
        return store.dossier(args.artifact)
    if args.command == "prepare":
        parameters = {
            "edition_id": args.edition_id,
            "start": args.start,
            "limit": args.limit,
            "target_language": args.target_language,
        }
        if args.end is not None:
            parameters["end"] = args.end
        return run_method(store, "research-dossier", parameters, actor=args.actor)
    if args.command == "runs":
        return store.runs()
    if args.command == "translation-sheet":
        from isc_helwigii.translation import build_translation_sheet, render_translation_markdown

        result = build_translation_sheet(store, args.edition_id, args.target_language)
        if args.output is not None:
            destination = args.output.expanduser().resolve()
            if destination == store.path:
                raise ValueError("export destination must differ from the project")
            content = (
                render_translation_markdown(result)
                if args.format == "markdown"
                else json.dumps(result, ensure_ascii=False, indent=2) + "\n"
            )
            with destination.open("x", encoding="utf-8") as output:
                output.write(content)
        return result
    if args.command in ("audit", "reference-set"):
        if args.output is not None and args.output.expanduser().resolve() == store.path:
            raise ValueError("export destination must differ from the project")
        if args.command == "reference-set":
            try:
                seed = int(args.seed)
            except ValueError as exc:
                raise ValueError("seed must be an integer") from exc
        result = (
            audit_corpus(store)
            if args.command == "audit"
            else prepare_reference_set(store, axis=args.axis, seed=seed)
        )
        if args.output is not None:
            write_json_export(result, args.output)
        return result
    if args.command == "import":
        raw = args.file.read_bytes()
        records = PARSERS[args.format](raw)
        snapshot = store.import_records(
            raw, records, source=args.source, license=args.license, adapter=args.format + "-v1"
        )
        return {"snapshot_id": snapshot, "record_count": len(records)}
    if args.command == "import-legacy":
        from isc_helwigii.legacy import import_legacy

        return import_legacy(
            store, args.file, source=args.source, license=args.license, limit=args.limit
        )
    if args.command == "review":
        store.review(args.annotation, args.decision, actor=args.actor, reason=args.reason)
        return {"annotation_id": args.annotation, "decision": args.decision}
    if args.command in ("annotate", "run"):
        request = json.loads(args.file.read_text(encoding="utf-8"))
        if not isinstance(request, dict):
            raise ValueError("request must be a JSON object")
        try:
            if args.command == "annotate":
                return {"annotation_id": store.annotate(**request)}
            return run_method(store, **request)
        except TypeError as exc:
            raise ValueError(f"invalid request fields: {exc}") from exc
    if args.command == "start":
        import importlib.util
        import subprocess

        if importlib.util.find_spec("streamlit") is None:
            raise ValueError("UI dependency missing: install isc-helwigii[ui]")
        with store.connection():
            pass
        ui = Path(__file__).with_name("ui.py")
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                str(ui),
                "--server.address=127.0.0.1",
                "--server.headless=true",
                f"--server.port={args.port}",
                "--browser.gatherUsageStats=false",
                "--",
                "--project",
                str(store.path),
            ],
            check=False,
        )
        if result.returncode:
            raise ValueError(f"UI exited with status {result.returncode}")
        return {"status": "stopped"}
    raise ValueError("unknown research command")


if __name__ == "__main__":
    raise SystemExit(main())
