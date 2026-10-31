#!/usr/bin/env python3
"""Build public chronology JSON from non-rendered <chronology_data> XML nodes.

No AI and no private credentials are involved. The human prose is deliberately
not parsed: only explicit machine-readable records are emitted.
"""
from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

SCHEMAS = {
    "events.json": "chronology-events-v1",
    "claims.json": "chronology-claims-v1",
    "constraints.json": "chronology-constraints-v1",
}
MAX_YEAR = 100000


def required(element: ET.Element, key: str) -> str:
    value = element.get(key)
    if value is None or not value.strip():
        raise ValueError(f"<{element.tag}> needs attribute {key!r}")
    return value.strip()


def integer(element: ET.Element, key: str) -> int:
    raw = required(element, key)
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid integer {key}={raw!r}") from exc
    if not -MAX_YEAR <= value <= MAX_YEAR:
        raise ValueError(f"{key} outside allowed range (+/- {MAX_YEAR}): {value}")
    return value


def bool_field(element: ET.Element, key: str) -> bool:
    raw = required(element, key)
    if raw not in ("true", "false"):
        raise ValueError(f"{key} must be 'true' or 'false', got {raw!r}")
    return raw == "true"


def optional_text(element: ET.Element, tag: str) -> str | None:
    child = element.find(tag)
    return (child.text or "").strip() or None if child is not None else None


def parse_source(node: ET.Element) -> dict[str, str | None]:
    url = required(node, "url")
    if not url.startswith("https://"):
        raise ValueError(f"Source must use an https URL: {url!r}")
    source = {
        "author": required(node, "author"),
        "work": required(node, "work"),
        "location": required(node, "location"),
        "url": url,
        "originalQuote": optional_text(node, "original_quote"),
        "review": optional_text(node, "review"),
    }
    return source


def parse_event(element: ET.Element) -> dict[str, Any]:
    return {
        "id": required(element, "id"),
        "label": required(element, "label"),
        "kind": required(element, "kind"),
        "subject": required(element, "subject"),
    }


def parse_claim(element: ET.Element) -> dict[str, Any]:
    result: dict[str, Any] = {
        "id": required(element, "id"),
        "kind": required(element, "kind"),
        "eventId": required(element, "event_id"),
        "title": required(element, "title"),
        "status": required(element, "status"),
    }
    if "year" in element.attrib:
        result["year"] = integer(element, "year")
    if "year_min" in element.attrib or "year_max" in element.attrib:
        if "year" in result:
            raise ValueError("claim cannot contain exact year and range")
        lower = integer(element, "year_min")
        upper = integer(element, "year_max")
        if lower > upper:
            raise ValueError(f"Backwards year interval in {result['id']}")
        result["year"] = {"min": lower, "max": upper}
    if "metric" in element.attrib:
        result["metric"] = required(element, "metric")
        result["value"] = integer(element, "value")
    if "year" not in result and "metric" not in result:
        raise ValueError(f"Claim {result['id']} must specify a year/range or metric")
    source = element.find("source")
    if source is None:
        raise ValueError(f"Claim {result['id']} must have a <source>")
    result["source"] = parse_source(source)
    return result


def parse_constraint(element: ET.Element) -> dict[str, Any]:
    evidence = element.find("evidence")
    if evidence is None:
        raise ValueError(f"Constraint {element.get('id')} lacks evidence")
    url = required(evidence, "url")
    if not url.startswith("https://"):
        raise ValueError("Constraint evidence needs an https URL")
    return {
        "id": required(element, "id"),
        "kind": required(element, "kind"),
        "lhsEvent": required(element, "lhs_event"),
        "rhsEvent": required(element, "rhs_event"),
        "relation": required(element, "relation"),
        "deltaYears": integer(element, "delta_years"),
        "label": required(element, "label"),
        "defaultActive": bool_field(element, "default_active"),
        "status": required(element, "status"),
        "evidence": {
            "work": required(evidence, "work"),
            "url": url,
            "review": required(evidence, "review"),
        },
    }


def parse_example(element: ET.Element) -> dict[str, Any]:
    return {
        "id": required(element, "id"),
        "kind": required(element, "kind"),
        "baseClaimId": required(element, "base_claim_id"),
        "ageClaimId": required(element, "age_claim_id"),
        "status": required(element, "status"),
    }


def read_source_directory(source_dir: Path) -> dict[str, Any]:
    if not source_dir.is_dir():
        raise FileNotFoundError(f"No chronology directory: {source_dir}")

    names = {
        "events": ("events/event", parse_event),
        "claims": ("claims/claim", parse_claim),
        "constraints": ("constraints/constraint", parse_constraint),
        "derivedExamples": ("derived_examples/example", parse_example),
    }
    collected: dict[str, list[dict[str, Any]]] = {key: [] for key in names}
    seen: dict[str, set[str]] = {key: set() for key in names}
    files = sorted(p for p in source_dir.glob("*.xml") if p.name != "info.xml")
    if not files:
        raise ValueError(f"No chronological source XML files in {source_dir}")
    with_metadata = 0
    for file in files:
        raw = file.read_bytes()
        if b"<!DOCTYPE" in raw.upper():
            raise ValueError(f"DOCTYPE not allowed in source XML: {file}")
        try:
            root = ET.fromstring(raw)
        except ET.ParseError as exc:
            raise ValueError(f"Malformed XML: {file}: {exc}") from exc
        if root.tag != "content":
            raise ValueError(f"Expected <content> root in {file}")
        for block in root.findall("./chronology_data"):
            with_metadata += 1
            if required(block, "version") != "1" or required(block, "calendar") != "AM":
                raise ValueError(f"Unsupported chronology_data schema in {file}")
            for key, (selector, parser) in names.items():
                for element in block.findall(selector):
                    try:
                        item = parser(element)
                    except ValueError as exc:
                        raise ValueError(f"{file}: {exc}") from exc
                    if item["id"] in seen[key]:
                        raise ValueError(f"Duplicate {key} id {item['id']} in {file}")
                    seen[key].add(item["id"])
                    collected[key].append(item)
    if not with_metadata:
        raise ValueError("No <chronology_data> blocks found; refuse to overwrite JSON with empty data")

    event_ids = seen["events"]
    claim_ids = seen["claims"]
    for claim in collected["claims"]:
        if claim["eventId"] not in event_ids:
            raise ValueError(f"Unknown claim eventId: {claim['eventId']}")
        if claim["kind"] != "source-claim":
            raise ValueError(f"Only source-claim type currently supported: {claim['id']}")
    for c in collected["constraints"]:
        if c["lhsEvent"] not in event_ids or c["rhsEvent"] not in event_ids:
            raise ValueError(f"Constraint {c['id']} references missing event")
        if c["relation"] != "same-year" or c["deltaYears"] != 0:
            raise ValueError(f"Constraint {c['id']} uses an unsupported relation; extend the solver first")
    for e in collected["derivedExamples"]:
        if e["baseClaimId"] not in claim_ids or e["ageClaimId"] not in claim_ids:
            raise ValueError(f"Example {e['id']} references missing claim")

    for collection in collected.values():
        collection.sort(key=lambda item: item["id"])
    return {
        "events.json": {"schema": SCHEMAS["events.json"], "calendar": "AM", "events": collected["events"]},
        "claims.json": {"schema": SCHEMAS["claims.json"], "calendar": "AM", "claims": collected["claims"]},
        "constraints.json": {
            "schema": SCHEMAS["constraints.json"],
            "constraints": collected["constraints"],
            "derivedExamples": collected["derivedExamples"],
        },
    }


def sync(source_dir: Path, output_dir: Path, check: bool) -> list[str]:
    result = read_source_directory(source_dir)
    changes: list[str] = []
    for filename, data in sorted(result.items()):
        expected = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        output = output_dir / filename
        old = output.read_text(encoding="utf-8") if output.is_file() else None
        if old != expected:
            changes.append(filename)
            if not check:
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(expected, encoding="utf-8")
    return changes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("data"))
    parser.add_argument("--check", action="store_true", help="Fail when generated files differ, without writing")
    opts = parser.parse_args()
    try:
        changes = sync(opts.source_dir, opts.output_dir, opts.check)
    except (ValueError, OSError) as exc:
        print(f"Chronology sync failed: {exc}", file=sys.stderr)
        return 2
    if changes:
        print(("Outdated: " if opts.check else "Updated: ") + ", ".join(changes))
    else:
        print("Chronology JSON is up to date.")
    return int(opts.check and bool(changes))


if __name__ == "__main__":
    raise SystemExit(main())
