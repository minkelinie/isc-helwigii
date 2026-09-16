"""Offline adapters. Keep original bytes in the source snapshot alongside mappings."""

import json
import re


def _validate(records):
    if not isinstance(records, list) or not records:
        raise ValueError("expected a non-empty record list")
    seen = set()
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("record must be an object")
        key = record.get("external_id")
        if not isinstance(key, str) or not key.strip() or key in seen:
            raise ValueError("unique non-empty external_id required")
        seen.add(key)
    return records


def parse_native(raw: bytes):
    payload = json.loads(raw.decode("utf-8-sig"))
    return _validate(payload.get("records") if isinstance(payload, dict) else payload)


def parse_atf(raw: bytes):
    records = []
    current = None
    surface = ""
    for line in raw.decode("utf-8-sig").splitlines():
        if line.startswith("&"):
            parts = line[1:].split("=", 1)
            current = {
                "external_id": parts[0].strip(),
                "title": parts[-1].strip(),
                "text": "",
                "language": "unknown",
                "lines": [],
            }
            records.append(current)
            surface = ""
        elif line.startswith("#atf: lang ") and current is not None:
            current["language"] = line[len("#atf: lang ") :].strip()
        elif line.startswith("@"):
            surface = line[1:].strip()
        elif match := re.match(r"^(\d+[a-z']*)\.\s*(.*)$", line):
            if current is None:
                raise ValueError("ATF text line without artifact identifier")
            current["lines"].append({"label": match[1], "text": match[2], "surface": surface})
    for record in records:
        record["text"] = "\n".join(line["text"] for line in record["lines"])
    return _validate(records)


def parse_oracc(raw: bytes):
    payload = json.loads(raw.decode("utf-8-sig"))
    if (
        not isinstance(payload, dict)
        or payload.get("type") not in ("catalogue", "catalog")
        or not isinstance(payload.get("members"), dict)
    ):
        raise ValueError(
            "ORACC catalogue JSON required; corpus manifests and CDL editions are different formats"
        )
    records = []
    for key, fields in payload["members"].items():
        if not isinstance(fields, dict):
            raise ValueError("ORACC catalogue member must be an object")
        records.append(
            {
                **fields,
                "external_id": key,
                "project": payload.get("project", ""),
                "text": "",
                "title": fields.get("designation", key),
                "language": fields.get("language", "unknown"),
            }
        )
    return _validate(records)


PARSERS = {"native": parse_native, "atf": parse_atf, "oracc-catalogue": parse_oracc}
