from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from PIL import Image, ImageOps
except ImportError:
    print("ERROR: Pillow is required.")
    print(r"Run: .\venv\Scripts\python.exe -m pip install Pillow")
    raise SystemExit(2)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
PRODUCT_WIDTHS = (480, 960)
BLOG_WIDTHS = (480, 960)
HERO_WIDTHS = (768, 1280, 1717)
QUALITY = 82


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_static_path(path: Path, static_root: Path) -> str:
    return path.relative_to(static_root).as_posix()


def classify_source(logical_path: str) -> str:
    if logical_path == "images/onlycards-home-hero.webp":
        return "hero"
    if logical_path.startswith("uploads/products/"):
        return "product"
    if logical_path.startswith("blog/"):
        return "blog"
    return "other"


def source_candidates(static_root: Path) -> list[Path]:
    candidates: list[Path] = []

    product_root = static_root / "uploads" / "products"
    if product_root.exists():
        candidates.extend(
            path for path in product_root.rglob("*")
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
        )

    blog_root = static_root / "blog"
    if blog_root.exists():
        candidates.extend(
            path for path in blog_root.rglob("*")
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
        )

    hero_path = static_root / "images" / "onlycards-home-hero.webp"
    if hero_path.exists():
        candidates.append(hero_path)

    return sorted(set(candidates))


def load_manifest(manifest_path: Path) -> dict[str, Any]:
    if not manifest_path.exists():
        return {"version": 1, "entries": {}}
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "entries": {}}
    if not isinstance(payload.get("entries"), dict):
        payload["entries"] = {}
    payload.setdefault("version", 1)
    return payload


def save_manifest(manifest_path: Path, payload: dict[str, Any]) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = manifest_path.with_suffix(".json.tmp")
    temp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temp_path, manifest_path)


def prepare_image(source: Path) -> Image.Image:
    with Image.open(source) as opened:
        if getattr(opened, "is_animated", False):
            opened.seek(0)

        transposed = ImageOps.exif_transpose(opened)
        if transposed.mode in {"RGBA", "LA"} or (
            transposed.mode == "P" and "transparency" in transposed.info
        ):
            prepared = transposed.convert("RGBA")
        else:
            prepared = transposed.convert("RGB")

        return prepared.copy()


def choose_widths(kind: str, source_width: int) -> list[int]:
    if kind == "hero":
        requested = HERO_WIDTHS
    elif kind == "blog":
        requested = BLOG_WIDTHS
    else:
        requested = PRODUCT_WIDTHS

    widths = [width for width in requested if width <= source_width]
    if not widths:
        widths = [source_width]
    elif widths[-1] != source_width and source_width < max(requested):
        widths.append(source_width)

    return sorted(set(widths))


def render_variant(
    image: Image.Image,
    width: int,
    output_path: Path,
    quality: int = QUALITY,
) -> dict[str, Any]:
    source_width, source_height = image.size
    if width == source_width:
        resized = image.copy()
    else:
        height = max(1, round(source_height * (width / source_width)))
        resized = image.resize((width, height), Image.Resampling.LANCZOS)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    resized.save(
        output_path,
        format="WEBP",
        quality=quality,
        method=6,
        optimize=True,
    )

    with Image.open(output_path) as verification:
        verified_width, verified_height = verification.size

    return {
        "path": output_path.as_posix(),
        "width": verified_width,
        "height": verified_height,
        "size_bytes": output_path.stat().st_size,
    }


def rel_variant_path(hash_prefix: str, width: int) -> Path:
    return Path("optimized") / "assets" / f"{hash_prefix}-{width}.webp"


def ensure_archived(source: Path, project_root: Path, archive_root: Path) -> Path:
    relative = source.relative_to(project_root)
    destination = archive_root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        shutil.copy2(source, destination)
    return destination


def optimize_project(project_root: Path, archive_root: Path, remove_originals: bool) -> dict[str, Any]:
    static_root = project_root / "static"
    manifest_path = static_root / "optimized" / "image-manifest.json"
    manifest = load_manifest(manifest_path)
    entries: dict[str, Any] = dict(manifest.get("entries", {}))

    sources = source_candidates(static_root)
    if not sources:
        raise RuntimeError("No source images were found.")

    before_bytes = 0
    archived_files: list[str] = []
    generated_paths: set[Path] = set()
    source_records: list[dict[str, Any]] = []

    # Archive every source before generating or deleting anything.
    for source in sources:
        logical_path = normalize_static_path(source, static_root)
        archived = ensure_archived(source, project_root, archive_root)
        archived_files.append(archived.relative_to(project_root).as_posix())
        before_bytes += source.stat().st_size

    by_hash: dict[str, dict[str, Any]] = {}

    for source in sources:
        logical_path = normalize_static_path(source, static_root)
        kind = classify_source(logical_path)
        digest = sha256_file(source)
        hash_prefix = digest[:16]

        with prepare_image(source) as image:
            source_width, source_height = image.size
            widths = choose_widths(kind, source_width)

            cache_key = f"{digest}:{','.join(str(width) for width in widths)}"
            cached = by_hash.get(cache_key)

            if cached is None:
                variants: list[dict[str, Any]] = []
                for width in widths:
                    if kind == "hero" and width == source_width:
                        rendered = {
                            "path": logical_path,
                            "width": source_width,
                            "height": source_height,
                            "size_bytes": source.stat().st_size,
                        }
                    else:
                        relative_output = rel_variant_path(hash_prefix, width)
                        output_path = static_root / relative_output
                        rendered = render_variant(image, width, output_path)
                        rendered["path"] = relative_output.as_posix()
                        generated_paths.add(output_path)
                    variants.append(rendered)

                cached = {
                    "variants": variants,
                    "content_sha256": digest,
                }
                by_hash[cache_key] = cached

            entry = {
                "kind": kind,
                "source_width": source_width,
                "source_height": source_height,
                "source_size_bytes": source.stat().st_size,
                "content_sha256": digest,
                "variants": cached["variants"],
            }
            entries[logical_path] = entry
            source_records.append(
                {
                    "logical_path": logical_path,
                    "kind": kind,
                    "source_size_bytes": source.stat().st_size,
                    "variants": cached["variants"],
                }
            )

    manifest = {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "entries": entries,
    }
    save_manifest(manifest_path, manifest)

    removed_sources: list[str] = []
    if remove_originals:
        for source in sources:
            logical_path = normalize_static_path(source, static_root)
            if logical_path == "images/onlycards-home-hero.webp":
                # The current hero is already a small WebP and remains as the largest fallback.
                continue
            source.unlink()
            removed_sources.append(logical_path)

    optimized_unique_files = {
        static_root / variant["path"]
        for entry in entries.values()
        if isinstance(entry, dict)
        for variant in entry.get("variants", [])
        if isinstance(variant, dict) and variant.get("path")
    }
    after_bytes = sum(
        path.stat().st_size
        for path in optimized_unique_files
        if path.exists()
    )
    report = {
        "source_count": len(sources),
        "manifest_entry_count": len(entries),
        "before_bytes": before_bytes,
        "after_bytes": after_bytes,
        "saved_bytes": max(0, before_bytes - after_bytes),
        "saved_percent": round(
            ((before_bytes - after_bytes) / before_bytes) * 100,
            2,
        ) if before_bytes else 0,
        "archive_root": archive_root.relative_to(project_root).as_posix(),
        "archived_files": archived_files,
        "removed_sources": removed_sources,
        "sources": source_records,
    }

    report_dir = project_root / "_onlycards_image_audit"
    report_dir.mkdir(exist_ok=True)
    report_json = report_dir / "optimization-report.json"
    report_txt = report_dir / "optimization-report.txt"

    report_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    report_txt.write_text(
        "\n".join(
            [
                "ONLY CARDS IMAGE OPTIMIZATION",
                f"Source images: {report['source_count']}",
                f"Manifest entries: {report['manifest_entry_count']}",
                f"Before: {report['before_bytes']} bytes",
                f"After: {report['after_bytes']} bytes",
                f"Saved: {report['saved_bytes']} bytes ({report['saved_percent']}%)",
                f"Archive: {report['archive_root']}",
                "",
                "Removed originals:",
                *[f"- {path}" for path in removed_sources],
            ]
        ),
        encoding="utf-8",
    )

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Optimize Only Cards website images.")
    parser.add_argument("--project", default=".", help="Only Cards project root.")
    parser.add_argument(
        "--archive-root",
        default="",
        help="Archive directory relative to the project root.",
    )
    parser.add_argument(
        "--keep-originals",
        action="store_true",
        help="Generate optimized files but keep source files in static.",
    )
    args = parser.parse_args()

    project_root = Path(args.project).resolve()
    if not (project_root / "app.py").exists():
        print(f"ERROR: app.py not found in {project_root}")
        return 1

    archive_root = (
        project_root / args.archive_root
        if args.archive_root
        else project_root
        / "_onlycards_image_originals"
        / datetime.now().strftime("%Y%m%d_%H%M%S")
    )

    try:
        report = optimize_project(
            project_root=project_root,
            archive_root=archive_root,
            remove_originals=not args.keep_originals,
        )
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1

    print("ONLYCARDS_IMAGE_OPTIMIZATION=SUCCESS")
    print(f"Source images: {report['source_count']}")
    print(f"Saved percent: {report['saved_percent']}%")
    print(f"Archive: {report['archive_root']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
