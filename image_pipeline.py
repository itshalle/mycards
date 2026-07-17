from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

from flask import url_for

PROJECT_ROOT = Path(__file__).resolve().parent
STATIC_ROOT = PROJECT_ROOT / "static"
MANIFEST_PATH = STATIC_ROOT / "optimized" / "image-manifest.json"

_manifest_lock = threading.Lock()
_manifest_cache: dict[str, Any] = {
    "mtime_ns": None,
    "entries": {},
}


def normalize_static_image_path(image_path: str | None) -> str:
    path = str(image_path or "").strip().replace("\\", "/").lstrip("/")
    if path.startswith("static/"):
        path = path[len("static/"):]
    if path and "/" not in path:
        path = f"images/{path}"
    return path


def _load_manifest() -> dict[str, Any]:
    try:
        stat = MANIFEST_PATH.stat()
        mtime_ns = stat.st_mtime_ns
    except OSError:
        return {}

    with _manifest_lock:
        if _manifest_cache["mtime_ns"] == mtime_ns:
            return dict(_manifest_cache["entries"])

        try:
            payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

        entries = payload.get("entries", {})
        if not isinstance(entries, dict):
            entries = {}

        _manifest_cache["mtime_ns"] = mtime_ns
        _manifest_cache["entries"] = entries
        return dict(entries)


def _choose_variant(variants: list[dict[str, Any]], preset: str) -> dict[str, Any] | None:
    valid = [
        item for item in variants
        if isinstance(item, dict)
        and item.get("path")
        and isinstance(item.get("width"), int)
        and isinstance(item.get("height"), int)
    ]
    if not valid:
        return None

    valid.sort(key=lambda item: item["width"])

    if preset in {"thumb", "admin"}:
        return valid[0]

    if preset in {"card", "cart"}:
        under_480 = [item for item in valid if item["width"] <= 480]
        return (under_480 or valid)[-1]

    return valid[-1]


def optimized_static_path(image_path: str | None, preset: str = "detail") -> str:
    logical_path = normalize_static_image_path(image_path)
    if not logical_path:
        return ""

    entry = _load_manifest().get(logical_path, {})
    variants = entry.get("variants", []) if isinstance(entry, dict) else []
    selected = _choose_variant(variants, preset)

    if selected:
        return str(selected["path"])

    return logical_path


def get_image_asset(image_path: str | None, preset: str = "card") -> dict[str, Any]:
    logical_path = normalize_static_image_path(image_path)
    if not logical_path:
        return {
            "src": "",
            "srcset": "",
            "width": None,
            "height": None,
            "path": "",
            "logical_path": "",
        }

    entry = _load_manifest().get(logical_path, {})
    variants = entry.get("variants", []) if isinstance(entry, dict) else []
    selected = _choose_variant(variants, preset)

    if not selected:
        return {
            "src": url_for("static", filename=logical_path),
            "srcset": "",
            "width": None,
            "height": None,
            "path": logical_path,
            "logical_path": logical_path,
        }

    sorted_variants = sorted(
        [
            item for item in variants
            if isinstance(item, dict)
            and item.get("path")
            and isinstance(item.get("width"), int)
            and isinstance(item.get("height"), int)
        ],
        key=lambda item: item["width"],
    )

    srcset = ", ".join(
        f'{url_for("static", filename=item["path"])} {item["width"]}w'
        for item in sorted_variants
    )

    return {
        "src": url_for("static", filename=selected["path"]),
        "srcset": srcset,
        "width": selected["width"],
        "height": selected["height"],
        "path": selected["path"],
        "logical_path": logical_path,
    }


def delete_image_variants(image_path: str | None) -> None:
    logical_path = normalize_static_image_path(image_path)
    if not logical_path or not MANIFEST_PATH.exists():
        return

    with _manifest_lock:
        try:
            payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return

        entries = payload.get("entries", {})
        if not isinstance(entries, dict):
            return

        removed_entry = entries.pop(logical_path, None)
        if not removed_entry:
            return

        still_referenced_paths = {
            variant.get("path")
            for entry in entries.values()
            if isinstance(entry, dict)
            for variant in entry.get("variants", [])
            if isinstance(variant, dict) and variant.get("path")
        }

        for variant in removed_entry.get("variants", []):
            if not isinstance(variant, dict):
                continue
            relative_path = variant.get("path")
            if not relative_path or relative_path in still_referenced_paths:
                continue
            full_path = STATIC_ROOT / relative_path
            try:
                full_path.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                pass

        payload["entries"] = entries
        temporary_path = MANIFEST_PATH.with_suffix(".json.tmp")
        temporary_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary_path, MANIFEST_PATH)

        try:
            mtime_ns = MANIFEST_PATH.stat().st_mtime_ns
        except OSError:
            mtime_ns = None

        _manifest_cache["mtime_ns"] = mtime_ns
        _manifest_cache["entries"] = dict(entries)
