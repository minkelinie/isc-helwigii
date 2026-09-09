"""Local, append-only research evidence. No model or network dependencies."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from isc_helwigii.analysis import date_overlap, validate_material
from isc_helwigii.schema import CREATE_SCHEMA, validate_tables

SCHEMA_VERSION = 1
ANNOTATION_KINDS = (
    "transliteration",
    "translation",
    "morphology",
    "category",
    "date",
    "place",
    "motif",
    "material",
    "physical_match",
    "hypothesis",
    "sign",
    "note",
)
TABLES = (
    "source_snapshots",
    "artifacts",
    "editions",
    "annotations",
    "review_events",
    "assets",
    "experiment_runs",
)
SCHEMA_COLUMNS = {
    "source_snapshots": "id source license checksum adapter raw created_at",
    "artifacts": "id source external_id",
    "editions": "id artifact_id snapshot_id record",
    "annotations": "id artifact_id kind payload actor origin evidence supersedes created_at",
    "review_events": "seq annotation_id decision actor reason created_at",
    "assets": "id artifact_id name media_type license actor checksum content created_at",
    "experiment_runs": "id method inputs outputs actor created_at",
}


def integrity_triggers():
    triggers = {}
    for table in TABLES:
        for action in ("UPDATE", "DELETE"):
            name = f"immutable_{table}_{action}"
            triggers[name] = (
                f"CREATE TRIGGER {name} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT, 'immutable evidence'); END"
            )
        key = "seq" if table == "review_events" else "id"
        match = f"{key}=NEW.{key}"
        if table == "artifacts":
            match += " OR (source=NEW.source AND external_id=NEW.external_id)"
        if table == "editions":
            match += " OR (artifact_id=NEW.artifact_id AND snapshot_id=NEW.snapshot_id)"
        name = f"immutable_{table}_INSERT"
        triggers[name] = (
            f"CREATE TRIGGER {name} BEFORE INSERT ON {table} WHEN EXISTS(SELECT 1 FROM {table} WHERE {match}) BEGIN SELECT RAISE(ABORT, 'immutable evidence'); END"
        )
    return triggers


def canonical(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def identifier(*values) -> str:
    return digest(canonical(values).encode())


def required(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value


def now():
    return datetime.now(UTC).isoformat()


class ResearchStore:
    def __init__(self, path):
        self.path = Path(path).expanduser().resolve()

    @contextmanager
    def connection(self, *, write=False):
        if not self.path.is_file():
            raise ValueError("project does not exist; initialize a new project first")
        con = sqlite3.connect(f"{self.path.as_uri()}?mode={'rw' if write else 'ro'}", uri=True)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        try:
            self.validate(con)
            with con:
                yield con
        finally:
            con.close()

    @staticmethod
    def validate(con):
        tables = {
            row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if (
            con.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION
            or not set(TABLES) <= tables
        ):
            raise ValueError("unrelated or unsupported database schema")
        for table, columns in SCHEMA_COLUMNS.items():
            if [row[1] for row in con.execute(f"PRAGMA table_info({table})")] != columns.split():
                raise ValueError("invalid project schema columns")
        validate_tables(con)
        actual = dict(con.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger'"))
        if actual != integrity_triggers():
            raise ValueError("invalid project schema integrity triggers")

    def validate_contents(self):
        with self.connection() as con:
            for table, column in [("source_snapshots", "raw"), ("assets", "content")]:
                for row in con.execute(f"SELECT id,{column},checksum FROM {table}"):
                    if digest(bytes(row[1])) != row[2]:
                        raise ValueError(f"evidence checksum mismatch: {table}/{row[0]}")
            if (
                con.execute("PRAGMA integrity_check").fetchone()[0] != "ok"
                or con.execute("PRAGMA foreign_key_check").fetchone()
            ):
                raise ValueError("database integrity check failed")

    def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(self.path)
        try:
            tables = con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            if tables:
                self.validate(con)
                return
            con.execute("PRAGMA foreign_keys=ON")
            con.executescript(CREATE_SCHEMA)
            for sql in integrity_triggers().values():
                con.execute(sql)
            con.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def import_records(self, raw, records, *, source, license, adapter="native-v1"):
        required(source, "source")
        required(license, "license")
        required(adapter, "adapter")
        if not isinstance(raw, bytes) or not records:
            raise ValueError("raw bytes and at least one record are required")
        seen = set()
        for record in records:
            if not isinstance(record, dict):
                raise ValueError("each record must be an object")
            external = required(record.get("external_id"), "external_id")
            if external in seen:
                raise ValueError(f"duplicate external_id: {external}")
            seen.add(external)
            if not isinstance(record.get("text", ""), str):
                raise ValueError("text must be a string")
        # Include mapped content: a changed parser cannot silently reuse an older mapping.
        snapshot = identifier(source, license, adapter, digest(raw), records)
        with self.connection(write=True) as con:
            con.execute("BEGIN IMMEDIATE")
            if con.execute("SELECT 1 FROM source_snapshots WHERE id=?", (snapshot,)).fetchone():
                return snapshot
            con.execute(
                "INSERT OR IGNORE INTO source_snapshots VALUES(?,?,?,?,?,?,?)",
                (snapshot, source, license, digest(raw), adapter, raw, now()),
            )
            for record in records:
                artifact = identifier(source, record["external_id"])
                if not con.execute("SELECT 1 FROM artifacts WHERE id=?", (artifact,)).fetchone():
                    con.execute(
                        "INSERT INTO artifacts VALUES(?,?,?)",
                        (artifact, source, record["external_id"]),
                    )
                con.execute(
                    "INSERT OR IGNORE INTO editions VALUES(?,?,?,?)",
                    (identifier(artifact, snapshot), artifact, snapshot, canonical(record)),
                )
        return snapshot

    def artifacts(self, query="", limit=None, offset=0):
        if limit is not None and (type(limit) is not int or limit < 1):
            raise ValueError("positive result limit required")
        if type(offset) is not int or offset < 0:
            raise ValueError("non-negative offset required")
        with self.connection() as con:
            con.create_function("casefold", 1, lambda text: text.casefold(), deterministic=True)
            rows = con.execute(
                """SELECT a.*, COUNT(e.id) edition_count FROM artifacts a
                JOIN editions e ON e.artifact_id=a.id
                WHERE ?='' OR instr(casefold(a.external_id),?)>0 OR EXISTS(
                    SELECT 1 FROM editions search WHERE search.artifact_id=a.id AND instr(casefold(search.record),?)>0)
                GROUP BY a.id ORDER BY a.source,a.external_id LIMIT ? OFFSET ?""",
                (
                    query,
                    query.casefold(),
                    query.casefold(),
                    limit if limit is not None else -1,
                    offset,
                ),
            )
            return [dict(row) for row in rows]

    def statistics(self):
        with self.connection() as con:
            return {
                table: con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in TABLES
            }

    def edition(self, edition_id):
        with self.connection() as con:
            row = con.execute(
                "SELECT e.*,a.source FROM editions e JOIN artifacts a ON a.id=e.artifact_id WHERE e.id=?",
                (edition_id,),
            ).fetchone()
            if row is None:
                raise ValueError("edition not found")
            return {
                **json.loads(row["record"]),
                "id": row["id"],
                "artifact_id": row["artifact_id"],
                "snapshot_id": row["snapshot_id"],
                "source": row["source"],
            }

    def dossier(self, artifact_id):
        with self.connection() as con:
            row = con.execute("SELECT * FROM artifacts WHERE id=?", (artifact_id,)).fetchone()
            if row is None:
                raise ValueError("artifact not found")
            result = dict(row)
            result["editions"] = []
            for edition in con.execute(
                "SELECT e.*,s.source,s.license,s.checksum,s.adapter FROM editions e JOIN source_snapshots s ON s.id=e.snapshot_id WHERE artifact_id=? ORDER BY e.rowid",
                (artifact_id,),
            ):
                entry = dict(edition)
                entry["record"] = json.loads(entry["record"])
                result["editions"].append(entry)
            annotations = []
            for row in con.execute(
                "SELECT * FROM annotations WHERE artifact_id=? ORDER BY rowid", (artifact_id,)
            ):
                entry = dict(row)
                for key in ("payload", "evidence"):
                    entry[key] = json.loads(entry[key])
                entry["reviews"] = [
                    dict(r)
                    for r in con.execute(
                        "SELECT * FROM review_events WHERE annotation_id=? ORDER BY seq",
                        (entry["id"],),
                    )
                ]
                entry["status"] = (
                    entry["reviews"][-1]["decision"] if entry["reviews"] else "pending"
                )
                annotations.append(entry)
            superseded = {a["supersedes"] for a in annotations if a["status"] == "accepted"}
            for entry in annotations:
                if entry["id"] in superseded:
                    entry["status"] = "superseded"
            result["annotations"] = annotations
            result["assets"] = [
                dict(r)
                for r in con.execute(
                    "SELECT id,name,media_type,license,actor,checksum,created_at FROM assets WHERE artifact_id=? ORDER BY rowid",
                    (artifact_id,),
                )
            ]
            return result

    def annotate(
        self, artifact_id, kind, payload, *, actor, evidence, origin="observed", supersedes=None
    ):
        required(actor, "actor")
        if kind not in ANNOTATION_KINDS or origin not in ("observed", "imported", "inferred"):
            raise ValueError("unsupported annotation kind or origin")
        if (
            not isinstance(payload, dict)
            or not payload
            or not evidence
            or not isinstance(evidence, list)
        ):
            raise ValueError("payload and evidence identifiers required")
        annotation = uuid.uuid4().hex
        with self.connection(write=True) as con:
            if not con.execute("SELECT 1 FROM artifacts WHERE id=?", (artifact_id,)).fetchone():
                raise ValueError("artifact not found")
            for ref in evidence:
                found = any(
                    con.execute(f"SELECT 1 FROM {table} WHERE id=?", (ref,)).fetchone()
                    for table in (
                        "source_snapshots",
                        "editions",
                        "annotations",
                        "assets",
                        "experiment_runs",
                    )
                )
                if not found:
                    raise ValueError(f"evidence not found: {ref}")
            if supersedes:
                parent = con.execute(
                    "SELECT artifact_id,kind,payload FROM annotations WHERE id=?", (supersedes,)
                ).fetchone()
                if not parent or (parent["artifact_id"], parent["kind"]) != (artifact_id, kind):
                    raise ValueError(
                        "revision must supersede the same artifact and annotation kind"
                    )
                previous = json.loads(parent["payload"])
                scope = []
                if kind in ("translation", "transliteration", "motif", "morphology", "sign"):
                    scope = ["edition_id", "start", "end"]
                if kind == "translation":
                    scope += ["target_language"]
                if kind == "category":
                    scope += ["axis"]
                if kind == "place":
                    scope += ["relation"]
                if any(payload.get(key) != previous.get(key) for key in scope):
                    raise ValueError(
                        "revision cannot change annotation scope; create a separate proposal"
                    )
            if kind in ("translation", "transliteration", "motif", "morphology", "sign"):
                edition = con.execute(
                    "SELECT record FROM editions WHERE id=? AND artifact_id=?",
                    (payload.get("edition_id"), artifact_id),
                ).fetchone()
                start, end = payload.get("start"), payload.get("end")
                if (
                    not edition
                    or type(start) is not int
                    or type(end) is not int
                    or not 0 <= start < end <= len(json.loads(edition[0]).get("text", ""))
                ):
                    raise ValueError(
                        "passage requires this artifact edition and valid character offsets"
                    )
                if kind == "translation":
                    required(payload.get("text"), "translation text")
                    required(payload.get("target_language"), "target_language")
                if kind == "motif":
                    required(payload.get("name"), "motif name")
                    if payload.get("presence", "present") not in ("present", "absent", "uncertain"):
                        raise ValueError("motif presence must be present, absent or uncertain")
            if kind == "material":
                validate_material(payload)
            if kind == "date":
                if payload.get("interval") is None:
                    raise ValueError("date annotation requires an interval")
                date_overlap(payload["interval"], payload["interval"])
            if kind == "category":
                required(payload.get("label"), "category label")
            if kind == "hypothesis":
                for field in ("statement", "test_plan", "counter_evidence"):
                    required(payload.get(field), field)
                if (
                    not isinstance(payload.get("alternatives"), list)
                    or len(payload["alternatives"]) < 2
                ):
                    raise ValueError("hypothesis requires at least two competing explanations")
            if kind == "physical_match":
                target = payload.get("target_artifact")
                if (
                    target == artifact_id
                    or not con.execute("SELECT 1 FROM artifacts WHERE id=?", (target,)).fetchone()
                ):
                    raise ValueError("physical match requires a different existing artifact")
                required(payload.get("basis"), "physical evidence description")
            if kind == "sign" and "bbox" in payload:
                box = payload["bbox"]
                if (
                    not isinstance(box, list)
                    or len(box) != 4
                    or any(type(v) not in (int, float) for v in box)
                    or not (0 <= box[0] < box[2] <= 1 and 0 <= box[1] < box[3] <= 1)
                ):
                    raise ValueError("bbox requires normalized [left,top,right,bottom] coordinates")
                if not con.execute(
                    "SELECT 1 FROM assets WHERE id=? AND artifact_id=?",
                    (payload.get("asset_id"), artifact_id),
                ).fetchone():
                    raise ValueError("sign region requires this artifact media asset")
            con.execute(
                "INSERT INTO annotations VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    annotation,
                    artifact_id,
                    kind,
                    canonical(payload),
                    actor,
                    origin,
                    canonical(evidence),
                    supersedes,
                    now(),
                ),
            )
        return annotation

    def review(self, annotation_id, decision, *, actor, reason):
        required(actor, "actor")
        required(reason, "reason")
        if decision not in ("accepted", "rejected"):
            raise ValueError("decision must be accepted or rejected")
        with self.connection(write=True) as con:
            if not con.execute("SELECT 1 FROM annotations WHERE id=?", (annotation_id,)).fetchone():
                raise ValueError("annotation not found")
            con.execute(
                "INSERT INTO review_events(annotation_id,decision,actor,reason,created_at) VALUES(?,?,?,?,?)",
                (annotation_id, decision, actor, reason, now()),
            )

    def source_bytes(self, snapshot_id):
        return self._bytes("source_snapshots", "raw", snapshot_id)

    def asset_bytes(self, asset_id):
        return self._bytes("assets", "content", asset_id)

    def _bytes(self, table, column, record_id):
        with self.connection() as con:
            row = con.execute(f"SELECT {column} FROM {table} WHERE id=?", (record_id,)).fetchone()
            if row is None:
                raise ValueError("evidence not found")
            return bytes(row[0])

    def add_asset(self, artifact_id, content, *, name, media_type, license, actor):
        for label, value in [
            ("name", name),
            ("media_type", media_type),
            ("license", license),
            ("actor", actor),
        ]:
            required(value, label)
        if not isinstance(content, bytes) or not 0 < len(content) <= 32 * 1024 * 1024:
            raise ValueError("asset must contain 1 byte to 32 MiB")
        asset = identifier(artifact_id, digest(content), name, license, actor)
        with self.connection(write=True) as con:
            con.execute("BEGIN IMMEDIATE")
            if con.execute("SELECT 1 FROM assets WHERE id=?", (asset,)).fetchone():
                return asset
            if not con.execute("SELECT 1 FROM artifacts WHERE id=?", (artifact_id,)).fetchone():
                raise ValueError("artifact not found")
            con.execute(
                "INSERT OR IGNORE INTO assets VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    asset,
                    artifact_id,
                    name,
                    media_type,
                    license,
                    actor,
                    digest(content),
                    content,
                    now(),
                ),
            )
        return asset

    def save_run(self, method, inputs, outputs, *, actor):
        required(method, "method")
        required(actor, "actor")
        run = uuid.uuid4().hex
        with self.connection(write=True) as con:
            con.execute(
                "INSERT INTO experiment_runs VALUES(?,?,?,?,?,?)",
                (run, method, canonical(inputs), canonical(outputs), actor, now()),
            )
        return run

    def runs(self):
        with self.connection() as con:
            results = [
                dict(row)
                for row in con.execute("SELECT * FROM experiment_runs ORDER BY rowid DESC")
            ]
        for result in results:
            result["inputs"] = json.loads(result["inputs"])
            result["outputs"] = json.loads(result["outputs"])
        return results
