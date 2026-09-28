#!/usr/bin/env python3
"""Incrementally export Leonardo generations to Obsidian Markdown notes."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
from typing import Any
import urllib.error
import urllib.parse
import urllib.request


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import export_generation_to_obsidian as renderer


BASE_URL = "https://cloud.leonardo.ai/api/rest/v1"


def load_project_env() -> None:
    """Load local .env values when python-dotenv is installed."""
    try:
        from dotenv import load_dotenv
    except ModuleNotFoundError:
        return
    load_dotenv(SCRIPT_DIR.parent / ".env", override=False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Export new Leonardo generations to JSON snapshots and Obsidian notes."
        )
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("LEONARDO_API_KEY"),
        help="Leonardo API key. Defaults to LEONARDO_API_KEY.",
    )
    parser.add_argument(
        "--user-id",
        help="Leonardo user ID. If omitted, it is resolved via /me.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(SCRIPT_DIR.parent / "output" / "markdown"),
        help="Directory where Markdown notes are written.",
    )
    parser.add_argument(
        "--json-dir",
        default=str(SCRIPT_DIR.parent / "output" / "json"),
        help="Directory where raw generation JSON snapshots are stored.",
    )
    parser.add_argument(
        "--state-file",
        default=str(SCRIPT_DIR.parent / "output" / "state" / "exported_ids.json"),
        help="State file used to avoid exporting the same generation twice.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Page size used for /generations/user/{userId}.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=50,
        help="Maximum number of pages to scan per run.",
    )
    parser.add_argument(
        "--max-generations",
        type=int,
        help="Optional hard cap on the number of new generations to export.",
    )
    parser.add_argument(
        "--order",
        choices=["newest", "oldest"],
        default="newest",
        help="Processing order for matched generations. Defaults to newest.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Export generations even if their IDs are already present in the state file.",
    )
    parser.add_argument(
        "--enrich-sources",
        action="store_true",
        help=(
            "Try to enrich exported snapshots with source image and blueprint "
            "relations exposed by the Leonardo API."
        ),
    )
    return parser.parse_args()


def request_json(url: str, api_key: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} for {url}\n{body}") from exc


def try_request_json(url: str, api_key: str, warnings: list[str]) -> dict[str, Any] | None:
    try:
        return request_json(url, api_key)
    except Exception as exc:
        warnings.append(f"{url}: {exc}")
        return None


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exported_ids": [], "exports_by_id": {}}
    with path.open("r", encoding="utf-8") as handle:
        state = json.load(handle)
    state.setdefault("exported_ids", [])
    state.setdefault("exports_by_id", {})
    return state


def save_state(path: Path, state: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def resolve_user_id(api_key: str, user_id: str | None) -> str:
    if user_id:
        return user_id
    me = request_json(f"{BASE_URL}/me", api_key)
    return me["user_details"][0]["user"]["id"]


def fetch_generation_summaries(
    api_key: str,
    user_id: str,
    limit: int,
    max_pages: int,
) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    offset = 0

    for _ in range(max_pages):
        query = urllib.parse.urlencode({"limit": limit, "offset": offset})
        payload = request_json(f"{BASE_URL}/generations/user/{user_id}?{query}", api_key)
        page_items = payload.get("generations") or []
        if not page_items:
            break
        summaries.extend(item for item in page_items if isinstance(item, dict))
        offset += limit

    return summaries


def sort_summaries_oldest_first(summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        summaries,
        key=lambda item: (
            str(item.get("createdAt") or ""),
            str(item.get("id") or ""),
        ),
    )


def sort_summaries(
    summaries: list[dict[str, Any]],
    order: str,
) -> list[dict[str, Any]]:
    sorted_items = sort_summaries_oldest_first(summaries)
    if order == "newest":
        sorted_items.reverse()
    return sorted_items


def expected_paths_for_summary(
    output_dir: Path,
    json_dir: Path,
    summary: dict[str, Any],
) -> tuple[Path | None, Path | None]:
    generation_id = str(summary.get("id") or "").strip()
    if not generation_id:
        return None, None

    markdown_path = renderer.default_output_path(output_dir, summary)
    json_path = json_dir / f"{markdown_path.stem}.json"
    return markdown_path, json_path


def first_present(mapping: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def classify_source_url(url: str) -> tuple[str, str | None]:
    if "/initImages/" in url:
        return "init_image", None

    match = re.search(r"/generations/([^/]+)/", url)
    if match:
        return "generated_image", match.group(1)

    if "cdn.leonardo.ai" in url or "leonardo.ai" in url:
        return "unknown_url", None

    return "external_url", None


def extract_init_image(payload: dict[str, Any]) -> dict[str, Any]:
    obj = payload.get("object") if isinstance(payload.get("object"), dict) else {}
    candidates = [
        obj.get("init_images_by_pk"),
        payload.get("init_images_by_pk"),
        payload.get("init_image"),
    ]
    for candidate in candidates:
        if isinstance(candidate, dict):
            return candidate
    return {}


def add_source_image(
    source_images: list[dict[str, Any]],
    *,
    kind: str,
    source_field: str,
    id: str | None = None,
    url: str | None = None,
    source_generation_id: str | None = None,
    node_id: str | None = None,
    setting_name: str | None = None,
    init_image_type: str | None = None,
) -> None:
    entry = renderer.compact_metadata(
        {
            "kind": kind,
            "source_field": source_field,
            "id": id,
            "url": url,
            "source_generation_id": source_generation_id,
            "node_id": node_id,
            "setting_name": setting_name,
            "init_image_type": init_image_type,
        }
    )
    if entry and entry not in source_images:
        source_images.append(entry)


def enrich_from_init_image_id(
    *,
    api_key: str,
    init_image_id: str,
    source_field: str,
    source_images: list[dict[str, Any]],
    warnings: list[str],
    init_image_type: str | None = None,
) -> None:
    payload = try_request_json(f"{BASE_URL}/init-image/{init_image_id}", api_key, warnings)
    init_image = extract_init_image(payload or {})
    add_source_image(
        source_images,
        kind="init_image",
        source_field=source_field,
        id=init_image_id,
        url=init_image.get("url"),
        init_image_type=init_image_type,
    )


def normalize_node_input(node_input: dict[str, Any]) -> dict[str, Any]:
    setting_name = first_present(node_input, ["settingName", "setting_name"])
    node_id = first_present(node_input, ["nodeId", "node_id"])
    value = node_input.get("value")
    return renderer.compact_metadata(
        {
            "node_id": node_id,
            "setting_name": setting_name,
            "value": value,
        }
    )


def extract_blueprint_execution(payload: dict[str, Any]) -> dict[str, Any]:
    one_of = payload.get("one_of") if isinstance(payload.get("one_of"), dict) else {}
    obj = payload.get("object") if isinstance(payload.get("object"), dict) else {}
    candidates = [
        one_of.get("blueprintExecution"),
        one_of.get("blueprint_execution"),
        obj.get("blueprintExecution"),
        obj.get("blueprint_execution"),
        payload.get("blueprintExecution"),
        payload.get("blueprint_execution"),
    ]
    for candidate in candidates:
        if isinstance(candidate, dict):
            return candidate
    return {}


def enrich_from_blueprint_execution(
    *,
    api_key: str,
    execution_id: str,
    source_images: list[dict[str, Any]],
    warnings: list[str],
) -> dict[str, Any]:
    payload = try_request_json(
        f"{BASE_URL}/blueprint-executions/{execution_id}",
        api_key,
        warnings,
    )
    execution = extract_blueprint_execution(payload or {})
    inputs = execution.get("inputs") or []
    normalized_inputs = []

    for node_input in inputs:
        if not isinstance(node_input, dict):
            continue
        normalized = normalize_node_input(node_input)
        if normalized:
            normalized_inputs.append(normalized)

        setting_name = normalized.get("setting_name")
        value = normalized.get("value")
        if setting_name == "imageUrl" and isinstance(value, str):
            kind, source_generation_id = classify_source_url(value)
            add_source_image(
                source_images,
                kind=kind,
                source_field="blueprint.inputs.imageUrl",
                url=value,
                source_generation_id=source_generation_id,
                node_id=normalized.get("node_id"),
                setting_name=setting_name,
            )

    return renderer.compact_metadata(
        {
            "execution_id": execution_id,
            "created_at": execution.get("createdAt") or execution.get("created_at"),
            "status": execution.get("status"),
            "public": execution.get("public"),
            "inputs": normalized_inputs,
        }
    )


def build_generation_enrichment(api_key: str, generation: dict[str, Any]) -> dict[str, Any]:
    source_images: list[dict[str, Any]] = []
    warnings: list[str] = []

    init_image_id = first_present(generation, ["initImageId", "init_image_id"])
    if init_image_id:
        enrich_from_init_image_id(
            api_key=api_key,
            init_image_id=str(init_image_id),
            source_field="generation.initImageId",
            source_images=source_images,
            warnings=warnings,
        )

    init_generation_image_id = first_present(
        generation,
        ["initGenerationImageId", "init_generation_image_id"],
    )
    if init_generation_image_id:
        add_source_image(
            source_images,
            kind="generated_image",
            source_field="generation.initGenerationImageId",
            id=str(init_generation_image_id),
        )

    image_prompts = first_present(generation, ["imagePrompts", "image_prompts"])
    if isinstance(image_prompts, list):
        for item in image_prompts:
            if not item:
                continue
            if isinstance(item, str) and item.startswith("http"):
                kind, source_generation_id = classify_source_url(item)
                add_source_image(
                    source_images,
                    kind=kind,
                    source_field="generation.imagePrompts",
                    url=item,
                    source_generation_id=source_generation_id,
                )
            else:
                add_source_image(
                    source_images,
                    kind="image_prompt",
                    source_field="generation.imagePrompts",
                    id=str(item),
                )

    controlnets = first_present(generation, ["controlnets"])
    if isinstance(controlnets, list):
        for index, controlnet in enumerate(controlnets):
            if not isinstance(controlnet, dict):
                continue
            controlnet_init_id = first_present(controlnet, ["initImageId", "init_image_id"])
            init_image_type = first_present(controlnet, ["initImageType", "init_image_type"])
            if controlnet_init_id:
                enrich_from_init_image_id(
                    api_key=api_key,
                    init_image_id=str(controlnet_init_id),
                    source_field=f"generation.controlnets[{index}].initImageId",
                    source_images=source_images,
                    warnings=warnings,
                    init_image_type=str(init_image_type) if init_image_type else None,
                )

    blueprint_version_id = first_present(
        generation,
        ["blueprintVersionId", "blueprint_version_id"],
    )
    blueprint_execution_id = first_present(
        generation,
        [
            "blueprintExecutionId",
            "blueprint_execution_id",
            "blueprintExecutionAkUUID",
            "blueprint_execution_ak_uuid",
        ],
    )

    blueprint = renderer.compact_metadata(
        {
            "version_id": blueprint_version_id,
            "execution_id": blueprint_execution_id,
        }
    )
    if blueprint_execution_id:
        execution_metadata = enrich_from_blueprint_execution(
            api_key=api_key,
            execution_id=str(blueprint_execution_id),
            source_images=source_images,
            warnings=warnings,
        )
        blueprint.update(execution_metadata)

    enrichment = {
        "version": 1,
        "source": "leonardo_export_enrichment_v1",
        "source_images": source_images,
        "blueprint": blueprint,
        "audit": {
            "warnings": warnings,
            "checked_fields": [
                "initImageId",
                "initGenerationImageId",
                "imagePrompts",
                "controlnets",
                "blueprintVersionId",
                "blueprintExecutionId",
            ],
        },
    }
    if not source_images and not blueprint and not warnings:
        return {}
    return renderer.compact_metadata(enrichment)


def export_generation(
    api_key: str,
    generation_id: str,
    json_dir: Path,
    output_dir: Path,
    enrich_sources: bool = False,
) -> tuple[str, Path, Path] | tuple[str, str]:
    payload = request_json(f"{BASE_URL}/generations/{generation_id}", api_key)
    payload_kind = renderer.detect_payload_kind(payload)
    if payload_kind != "generation":
        return ("skip", payload_kind)

    generation = renderer.extract_generation(payload)
    if enrich_sources:
        enrichment = build_generation_enrichment(api_key, generation)
        if enrichment:
            payload["hornika_enrichment"] = enrichment
            generation["_hornika_enrichment"] = enrichment

    markdown_path = renderer.default_output_path(output_dir, generation)
    json_path = json_dir / f"{markdown_path.stem}.json"

    ensure_parent(json_path)
    json_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    markdown = renderer.build_markdown(generation, json_path.as_posix())
    ensure_parent(markdown_path)
    markdown_path.write_text(markdown, encoding="utf-8")
    return ("exported", json_path, markdown_path)


def main() -> None:
    load_project_env()
    args = parse_args()
    if not args.api_key:
        raise SystemExit(
            "Missing API key. Set LEONARDO_API_KEY or pass --api-key explicitly."
        )

    output_dir = Path(args.output_dir)
    json_dir = Path(args.json_dir)
    state_file = Path(args.state_file)

    state = load_state(state_file)
    exported_ids = set(state.get("exported_ids") or [])
    exports_by_id = state.get("exports_by_id") or {}

    user_id = resolve_user_id(args.api_key, args.user_id)
    summaries = fetch_generation_summaries(
        api_key=args.api_key,
        user_id=user_id,
        limit=args.limit,
        max_pages=args.max_pages,
    )

    if not args.force:
        filtered_summaries = []
        for summary in summaries:
            generation_id = str(summary.get("id") or "").strip()
            if not generation_id:
                continue

            markdown_path, json_path = expected_paths_for_summary(
                output_dir=output_dir,
                json_dir=json_dir,
                summary=summary,
            )
            state_entry = exports_by_id.get(generation_id) or {}

            known_markdown = Path(state_entry["markdown_path"]) if state_entry.get("markdown_path") else markdown_path
            known_json = Path(state_entry["json_path"]) if state_entry.get("json_path") else json_path

            already_exported = generation_id in exported_ids
            files_present = bool(
                known_markdown
                and known_json
                and known_markdown.exists()
                and known_json.exists()
            )

            if already_exported and files_present:
                continue

            filtered_summaries.append(summary)

        summaries = filtered_summaries

    summaries = sort_summaries(summaries, args.order)
    if args.max_generations is not None:
        summaries = summaries[: args.max_generations]

    exported_now: list[dict[str, str]] = []
    skipped_now: list[dict[str, str]] = []
    for summary in summaries:
        generation_id = str(summary.get("id") or "").strip()
        if not generation_id:
            continue

        result = export_generation(
            api_key=args.api_key,
            generation_id=generation_id,
            json_dir=json_dir,
            output_dir=output_dir,
            enrich_sources=args.enrich_sources,
        )
        if result[0] == "skip":
            payload_kind = result[1]
            skipped_now.append(
                {
                    "generation_id": generation_id,
                    "payload_kind": payload_kind,
                }
            )
            print(
                f"SKIP {generation_id}: unsupported payload kind '{payload_kind}'",
                file=sys.stderr,
            )
            continue

        _, json_path, markdown_path = result
        exported_ids.add(generation_id)
        exported_now.append(
            {
                "generation_id": generation_id,
                "file_name": markdown_path.stem,
                "json_path": json_path.as_posix(),
                "markdown_path": markdown_path.as_posix(),
            }
        )
        exports_by_id[generation_id] = {
            "file_name": markdown_path.stem,
            "json_path": json_path.as_posix(),
            "markdown_path": markdown_path.as_posix(),
        }
        print(markdown_path)

    state["user_id"] = user_id
    state["exported_ids"] = sorted(exported_ids)
    state["exports_by_id"] = exports_by_id
    state["last_run_exported_count"] = len(exported_now)
    state["last_run_exports"] = exported_now
    state["last_run_skipped_count"] = len(skipped_now)
    state["last_run_skipped"] = skipped_now
    save_state(state_file, state)

    print(
        json.dumps(
            {
                "user_id": user_id,
                "exported_count": len(exported_now),
                "skipped_count": len(skipped_now),
                "state_file": state_file.as_posix(),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
