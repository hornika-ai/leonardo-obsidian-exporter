#!/usr/bin/env python3
"""Convert a Leonardo generation payload into an Obsidian Markdown note.

This script accepts either:
- the full SDK response shape from `get_generation_by_id()`, or
- the nested `generations_by_pk` object itself.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import unicodedata
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DEFAULT_STATE_DIR = PROJECT_ROOT / "state"
DEFAULT_BLUEPRINT_CATALOG_PATH = DEFAULT_STATE_DIR / "blueprints_catalog.json"
DEFAULT_MODEL_CATALOG_PATH = DEFAULT_STATE_DIR / "platform_models.json"
LEGACY_MODEL_CATALOG_PATH = DEFAULT_STATE_DIR / "platform_models.md"
BLUEPRINT_CATALOG_SOURCE = "state/blueprints_catalog.json"
_BLUEPRINT_CATALOG_CACHE: dict[str, Any] | None = None
_MODEL_CATALOG_CACHE: dict[str, Any] | None = None


STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "by",
    "for",
    "from",
    "has",
    "have",
    "image",
    "imagery",
    "in",
    "into",
    "is",
    "it",
    "its",
    "of",
    "on",
    "or",
    "that",
    "the",
    "their",
    "this",
    "to",
    "was",
    "were",
    "with",
    "within",
    "featuring",
}


KNOWN_PLATFORM_MODELS = {
    # Leonardo official docs: Commonly Used API Values
    "7b592283-e8a7-4c5a-9ba6-d18c31f258b9": "Lucid Origin",
    "05ce0082-2d80-4a2d-8653-4d1c85e2418e": "Lucid Realism",
    "28aeddf8-bd19-4803-80fc-79602d1a9989": "Flux.1 Kontext",
    "de7d3faf-762f-48e0-b3b7-9d0ac3a3fcf3": "Leonardo Phoenix 1.0",
    "b2614463-296c-462a-9586-aafdb8f00e36": "Flux Dev",
    "1dd50843-d653-4516-a8e3-f0238ee453ff": "Flux Schnell",
    "6b645e3a-d64f-4341-a6d8-7a3690fbf042": "Leonardo Phoenix 0.9",
    "e71a1c2f-4f80-4800-934f-2c68979d8cc8": "Leonardo Anime XL",
    "b24e16ff-06e3-43eb-8d33-4416c2d75876": "Leonardo Lightning XL",
    "16e7060a-803e-4df3-97ee-edcfa5dc9cc8": "SDXL 1.0",
    "aa77f04e-3eec-4034-9c07-d0f619684628": "Leonardo Kino XL",
    "5c232a9e-9061-4777-980a-ddc8e65647c6": "Leonardo Vision XL",
    "1e60896f-3c26-4296-8ecc-53e2afecc132": "Leonardo Diffusion XL",
    "2067ae52-33fd-4a82-bb92-c2c55e7d2786": "AlbedoBase XL",
    "f1929ea3-b169-4c18-a16c-5d58b4292c69": "RPG v5",
    "b63f7119-31dc-4540-969b-2a9df997e173": "SDXL 0.9",
    "d69c8273-6b17-4a30-a13e-d6637ae1c644": "3D Animation Style",
    "ac614f96-1082-45bf-be9d-757f2d31c17": "DreamShaper v7",
}


KNOWN_STYLE_UUIDS = {
    # Leonardo official docs: Commonly Used API Values / StyleUUIDs
    "debdf72a-91a4-467b-bf61-cc02bdeb69c6": "3D Render",
    "9fdc5e8c-4d13-49b4-9ce6-5a74cbb19177": "Bokeh",
    "a5632c7c-ddbb-4e2f-ba34-8456ab3ac436": "Cinematic",
    "33abbb99-03b9-4dd7-9761-ee98650b2c88": "Cinematic Concept",
    "6fedbf1f-4a17-45ec-84fb-92fe524a29ef": "Creative",
    "111dc692-d470-4eec-b791-3475abac4c46": "Dynamic",
    "594c4a08-a522-4e0e-b7ff-e4dac4b6b622": "Fashion",
    "2e74ec31-f3a4-4825-b08b-2894f6d13941": "Graphic Design Pop Art",
    "1fbb6a68-9319-44d2-8d56-2957ca0ece6a": "Graphic Design Vector",
    "97c20e5c-1af6-4d42-b227-54d03d8f0727": "HDR",
    "645e4195-f63d-4715-a3f2-3fb1e6eb8c70": "Illustration",
    "30c1d34f-e3a9-479a-b56f-c018bbc9c02a": "Macro",
    "cadc8cd6-7838-4c99-b645-df76be8ba8d8": "Minimalist",
    "621e1c9a-6319-4bee-a12d-ae40659162fa": "Moody",
    "556c1ee5-ec38-42e8-955a-1e82dad0ffa1": "None",
    "8e2bc543-6ee2-45f9-bcd9-594b6ce84dcd": "Portrait",
    "22a9a7d2-2166-4d86-80ff-22e2643adbcf": "Pro B&W Photography",
    "7c3f932b-a572-47cb-9b9b-f20211e63b5b": "Pro Color Photography",
    "581ba6d6-5aac-4492-bebe-54c424a0d46e": "Pro Film Photography",
    "0d34f8e1-46d4-428f-8ddd-4b11811fa7c9": "Portrait Fashion",
    "b504f83c-3326-4947-82e1-7fe9e839ec0f": "Ray Traced",
    "be8c6b58-739c-4d44-b9c1-b032ed308b61": "Sketch (B&W)",
    "093accc3-7633-4ffd-82da-d34000dfc0d6": "Sketch (Color)",
    "5bdc3f2a-1be6-4d1c-8e77-992a30824a2c": "Stock Photo",
    "dee282d3-891f-4f73-ba02-7f8131e5541b": "Vibrant",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Convert a Leonardo get_generation_by_id payload into an Obsidian note."
        )
    )
    parser.add_argument(
        "--input-json",
        required=True,
        help="Path to a JSON file containing the SDK response or the generation object.",
    )
    parser.add_argument(
        "--output",
        help=(
            "Output Markdown file path. Defaults to "
            "<output-dir>/<created_at>_<generation_id>.md"
        ),
    )
    parser.add_argument(
        "--output-dir",
        default=str(PROJECT_ROOT / "output" / "markdown"),
        help="Directory used when --output is not provided.",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print the rendered Markdown to stdout instead of writing a file.",
    )
    return parser.parse_args()


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def detect_payload_kind(payload: Any) -> str:
    if not isinstance(payload, dict):
        return "invalid"

    obj = payload.get("object")
    if isinstance(obj, dict):
        if isinstance(obj.get("generations_by_pk"), dict):
            return "generation"
        if obj.get("generated_image_variation_generic") is not None:
            return "variation"
        if obj.get("generated_image_variation_motion") is not None:
            return "motion_variation"
        if obj.get("blueprint_execution_generations") is not None:
            return "blueprint_execution_generations"

    one_of = payload.get("one_of")
    if isinstance(one_of, dict) and one_of.get("blueprint_execution") is not None:
        return "blueprint_execution"

    if isinstance(payload.get("generations_by_pk"), dict):
        return "generation"
    if payload.get("generated_image_variation_generic") is not None:
        return "variation"
    if payload.get("generated_image_variation_motion") is not None:
        return "motion_variation"
    if payload.get("blueprint_execution_generations") is not None:
        return "blueprint_execution_generations"
    if payload.get("blueprint_execution") is not None:
        return "blueprint_execution"
    if "id" in payload and ("prompt" in payload or "generated_images" in payload):
        return "generation"

    return "unknown"


def extract_generation(payload: Any) -> dict[str, Any]:
    payload_kind = detect_payload_kind(payload)
    if payload_kind == "invalid":
        raise ValueError("Expected a JSON object at the top level.")

    enrichment = None
    if isinstance(payload, dict):
        enrichment = payload.get("hornika_enrichment")

    if isinstance(payload.get("object"), dict):
        obj = payload["object"]
        if isinstance(obj.get("generations_by_pk"), dict):
            generation = obj["generations_by_pk"]
            if enrichment and isinstance(generation, dict):
                generation["_hornika_enrichment"] = enrichment
            return generation

    if isinstance(payload.get("generations_by_pk"), dict):
        generation = payload["generations_by_pk"]
        if enrichment and isinstance(generation, dict):
            generation["_hornika_enrichment"] = enrichment
        return generation

    if "id" in payload and ("prompt" in payload or "generated_images" in payload):
        return payload

    raise ValueError(
        "Unsupported payload kind "
        f"'{payload_kind}'. Expected a Leonardo generation payload."
    )


def compact_list(values: list[Any]) -> list[Any]:
    return [value for value in values if value not in (None, "", [], {})]


def is_empty_metadata_value(value: Any) -> bool:
    return value in (None, "", [], {})


def compact_metadata(value: Any) -> Any:
    if isinstance(value, dict):
        compacted = {
            key: compact_metadata(item)
            for key, item in value.items()
        }
        return {
            key: item
            for key, item in compacted.items()
            if not is_empty_metadata_value(item)
        }
    if isinstance(value, list):
        compacted_items = [compact_metadata(item) for item in value]
        return [
            item
            for item in compacted_items
            if not is_empty_metadata_value(item)
        ]
    return value


def quote_yaml_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def yaml_string_scalar(value: Any) -> str:
    if value is None or value == "":
        return '" "'
    return quote_yaml_string(str(value))


def yaml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if value is None or value == "":
        return '" "'
    return quote_yaml_string(str(value))


def yaml_block(key: str, value: str | None) -> list[str]:
    if not value:
        return []

    lines = value.splitlines() or [value]
    return [f"{key}: >-"] + [f"  {line}" for line in lines]


def yaml_list(key: str, values: list[Any]) -> list[str]:
    if not values:
        return []
    lines = [f"{key}:"]
    for value in values:
        lines.append(f"  - {yaml_scalar(value)}")
    return lines


def yaml_object_list(key: str, values: list[dict[str, Any]]) -> list[str]:
    if not values:
        return []

    lines = [f"{key}:"]
    for value in values:
        items = list(value.items())
        if not items:
            continue
        first_key, first_value = items[0]
        lines.append(f"  - {first_key}: {yaml_string_scalar(first_value)}")
        for sub_key, sub_value in items[1:]:
            lines.append(f"    {sub_key}: {yaml_string_scalar(sub_value)}")
    return lines


def yaml_field(key: str, value: Any) -> list[str]:
    if value in (None, "", [], {}):
        return []
    return [f"{key}: {yaml_scalar(value)}"]


def yaml_string_field(key: str, value: Any) -> list[str]:
    if value in (None, "", [], {}):
        return []
    return [f"{key}: {yaml_string_scalar(value)}"]


def yaml_raw_field(key: str, value: Any) -> list[str]:
    if value in (None, "", [], {}):
        return []
    return [f"{key}: {value}"]


def slugify(value: str) -> str:
    value = (
        unicodedata.normalize("NFKD", value)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "generation"


def underscore_slug(value: str) -> str:
    return slugify(value).replace("-", "_")


def compact_text(value: str, max_words: int = 8) -> str:
    normalized = (
        unicodedata.normalize("NFKD", value)
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )
    tokens = re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", normalized)
    filtered = []

    for token in tokens:
        parts = token.split("-")
        if all(part in STOP_WORDS for part in parts):
            continue
        if token in STOP_WORDS:
            continue
        filtered.append(token)

    return " ".join(filtered[:max_words]).strip()


def truncate_slug(value: str, max_length: int = 80) -> str:
    if len(value) <= max_length:
        return value
    truncated = value[:max_length].rstrip("-")
    return truncated or "generation"


def extract_created_date(generation: dict[str, Any]) -> str | None:
    created = str(generation.get("createdAt") or "").strip()
    if not created:
        return None
    return created.split("T", 1)[0]


def normalize_created_at(generation: dict[str, Any]) -> str | None:
    created = str(generation.get("createdAt") or "").strip()
    if not created:
        return None

    match = re.match(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})", created)
    if match:
        return f"{match.group(1)}Z"

    if created.endswith("Z"):
        return created

    return created


def compute_aspect_ratio(width: Any, height: Any) -> str | None:
    if not isinstance(width, int) or not isinstance(height, int):
        return None
    if width <= 0 or height <= 0:
        return None
    divisor = math.gcd(width, height)
    return f"{width // divisor}:{height // divisor}"


def compute_generation_hash(generation: dict[str, Any]) -> str:
    prompt = str(generation.get("prompt") or "")
    seed = str(generation.get("seed") or "")
    digest = hashlib.sha1(f"{prompt}|{seed}".encode("utf-8")).hexdigest()
    return digest


def titleize_slug(value: str) -> str:
    return "".join(part.capitalize() for part in value.split("-") if part)


def humanize_identifier(value: str) -> str:
    cleaned = value.strip().replace("_", " ").replace("-", " ")
    if not cleaned:
        return value

    words = re.findall(r"[A-Z]+(?=[A-Z][a-z]|\d|$)|[A-Z]?[a-z]+|\d+", cleaned)
    if words:
        return " ".join(word.capitalize() for word in words)

    return cleaned.title()


def humanize_api_enum(value: str) -> str:
    cleaned = value.strip().replace("-", "_")
    if not cleaned:
        return value

    raw_parts = [part for part in cleaned.split("_") if part]
    if not raw_parts:
        return humanize_identifier(value)

    merged_parts: list[str] = []
    digit_buffer: list[str] = []
    for part in raw_parts:
        if part.isdigit():
            digit_buffer.append(part)
            continue
        if digit_buffer:
            merged_parts.append(".".join(digit_buffer))
            digit_buffer = []
        merged_parts.append(part)
    if digit_buffer:
        merged_parts.append(".".join(digit_buffer))

    human_parts = []
    index = 0
    while index < len(merged_parts):
        part = merged_parts[index]
        next_part = merged_parts[index + 1] if index + 1 < len(merged_parts) else None
        if len(part) == 1 and part.isalpha() and isinstance(next_part, str) and next_part.isdigit():
            human_parts.append(f"{part.upper()}{next_part}")
            index += 2
            continue
        if any(char.isalpha() for char in part):
            human_parts.append(part.capitalize())
        else:
            human_parts.append(part)
        index += 1

    return " ".join(human_parts)


def resolve_model_name(generation: dict[str, Any]) -> str | None:
    return resolve_model_info(generation).get("label")


def build_filename_title(generation: dict[str, Any]) -> str:
    created = extract_created_date(generation) or "unknown-date"
    created_compact = created.replace("-", "")
    seed = str(generation.get("seed") or "no-seed").strip() or "no-seed"
    short_id = str(generation.get("id") or "unknown-id")[:8]

    model_name = resolve_model_name(generation)
    model_part = titleize_slug(slugify(model_name)) if model_name else "UnknownModel"

    prompt_keywords = compact_text(str(generation.get("prompt") or ""), max_words=2)
    prompt_part = (
        titleize_slug(slugify(prompt_keywords)) if prompt_keywords else "Generation"
    )

    return f"{created_compact}_{model_part}_{prompt_part}_{seed}_{short_id}"


def build_human_title(generation: dict[str, Any]) -> str:
    created_prefix = extract_created_date(generation) or "unknown-date"
    prompt = compact_text(str(generation.get("prompt") or ""), max_words=3)

    if prompt:
        human_prompt = " ".join(word.capitalize() for word in prompt.split())
        return f"{human_prompt} - {created_prefix}"
    return f"Leonardo Generation - {created_prefix}"


def build_system_title(generation: dict[str, Any]) -> str:
    return build_filename_title(generation)


def first_present_string(generation: dict[str, Any], keys: list[str]) -> str | None:
    for key in keys:
        value = generation.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def extract_model_key(generation: dict[str, Any]) -> str | None:
    return first_present_string(
        generation,
        [
            "sdVersion",
            "sd_version",
            "motionModel",
            "motion_model",
            "modelKey",
            "model_key",
        ],
    )


def build_tags(generation: dict[str, Any]) -> list[str]:
    tags = ["leonardo", "generation", "ai-image"]

    model_name = resolve_model_name(generation)
    if model_name:
        tags.append(f"model/{slugify(model_name)}")

    preset_style = first_present_string(generation, ["presetStyle", "preset_style"])
    if not preset_style:
        style_uuid = first_present_string(generation, ["styleUUID", "styleUuid", "style_uuid"])
        if style_uuid:
            preset_style = KNOWN_STYLE_UUIDS.get(style_uuid)
    if preset_style:
        tags.append(f"style/{slugify(preset_style)}")

    scheduler = first_present_string(generation, ["scheduler"])
    if scheduler:
        tags.append(f"scheduler/{slugify(scheduler)}")

    engine = first_present_string(generation, ["sdVersion", "sd_version"])
    if engine:
        tags.append(f"engine/{slugify(engine)}")

    # Preserve order while removing duplicates.
    return list(dict.fromkeys(tags))


def build_size(generation: dict[str, Any]) -> str | None:
    width = generation.get("imageWidth")
    height = generation.get("imageHeight")
    if not isinstance(width, int) or not isinstance(height, int):
        return None
    return f"{width}x{height}"


def extract_generated_images(generation: dict[str, Any]) -> list[dict[str, Any]]:
    generated_images = generation.get("generated_images") or []
    return [image for image in generated_images if isinstance(image, dict)]


def first_image_with_url(generation: dict[str, Any]) -> dict[str, Any] | None:
    for image in extract_generated_images(generation):
        if image.get("url"):
            return image
    return None


def extract_image_variations(image: dict[str, Any]) -> list[dict[str, Any]]:
    raw_variations = image.get("generated_image_variation_generics") or []
    variations = []

    for variation in raw_variations:
        if not isinstance(variation, dict):
            continue

        entry = {}
        if variation.get("id"):
            entry["id"] = variation.get("id")
        if variation.get("transformType"):
            entry["transform_type"] = variation.get("transformType")
        elif variation.get("transform_type"):
            entry["transform_type"] = variation.get("transform_type")
        if variation.get("status"):
            entry["status"] = variation.get("status")
        if variation.get("createdAt"):
            entry["created_at"] = variation.get("createdAt")
        elif variation.get("created_at"):
            entry["created_at"] = variation.get("created_at")
        if variation.get("url"):
            entry["url"] = variation.get("url")

        if entry:
            variations.append(entry)

    return variations


def extract_motion_entries(generation: dict[str, Any]) -> list[dict[str, Any]]:
    motion_entries = []
    for index, image in enumerate(extract_generated_images(generation), start=1):
        motion_url = image.get("motionMP4URL")
        if not motion_url:
            continue

        entry = {
            "image_index": index,
            "source_image_id": image.get("id"),
            "motion_mp4_url": motion_url,
            "motion_model": generation.get("motionModel"),
            "motion_strength": generation.get("motionStrength"),
            "image_to_video": generation.get("imageToVideo"),
        }
        motion_entries.append(compact_metadata(entry))

    return motion_entries


def count_variations(generation: dict[str, Any]) -> int:
    return sum(
        len(extract_image_variations(image))
        for image in extract_generated_images(generation)
    )


def count_videos(generation: dict[str, Any]) -> int:
    return len(extract_motion_entries(generation))


def has_reference_hint(generation: dict[str, Any]) -> bool:
    return generation.get("initStrength") not in (None, "")


def get_enrichment(generation: dict[str, Any]) -> dict[str, Any]:
    enrichment = generation.get("_hornika_enrichment") or generation.get("hornika_enrichment")
    if isinstance(enrichment, dict):
        return compact_metadata(enrichment)
    return {}


def load_blueprint_catalog() -> dict[str, Any]:
    global _BLUEPRINT_CATALOG_CACHE
    if _BLUEPRINT_CATALOG_CACHE is not None:
        return _BLUEPRINT_CATALOG_CACHE

    if not DEFAULT_BLUEPRINT_CATALOG_PATH.exists():
        _BLUEPRINT_CATALOG_CACHE = {}
        return _BLUEPRINT_CATALOG_CACHE

    try:
        payload = json.loads(DEFAULT_BLUEPRINT_CATALOG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        _BLUEPRINT_CATALOG_CACHE = {}
        return _BLUEPRINT_CATALOG_CACHE

    if not isinstance(payload, dict):
        _BLUEPRINT_CATALOG_CACHE = {}
        return _BLUEPRINT_CATALOG_CACHE

    _BLUEPRINT_CATALOG_CACHE = payload
    return _BLUEPRINT_CATALOG_CACHE


def extract_json_from_markdown_code_fence(text: str) -> str:
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()


def load_model_catalog() -> dict[str, Any]:
    global _MODEL_CATALOG_CACHE
    if _MODEL_CATALOG_CACHE is not None:
        return _MODEL_CATALOG_CACHE

    catalog_path = DEFAULT_MODEL_CATALOG_PATH
    if not catalog_path.exists():
        catalog_path = LEGACY_MODEL_CATALOG_PATH

    if not catalog_path.exists():
        _MODEL_CATALOG_CACHE = {}
        return _MODEL_CATALOG_CACHE

    try:
        raw_text = catalog_path.read_text(encoding="utf-8")
        payload = json.loads(extract_json_from_markdown_code_fence(raw_text))
    except (OSError, json.JSONDecodeError):
        _MODEL_CATALOG_CACHE = {}
        return _MODEL_CATALOG_CACHE

    models = payload.get("custom_models") or payload.get("models") or []
    if not isinstance(models, list):
        _MODEL_CATALOG_CACHE = {}
        return _MODEL_CATALOG_CACHE

    by_id = {}
    normalized_models = []
    for model in models:
        if not isinstance(model, dict):
            continue
        model_id = model.get("id")
        name = model.get("name")
        if not model_id or not name:
            continue
        entry = compact_metadata(
            {
                "id": model_id,
                "name": name,
                "description": model.get("description"),
                "nsfw": model.get("nsfw"),
                "featured": model.get("featured"),
                "generated_image": model.get("generated_image"),
            }
        )
        normalized_models.append(entry)
        by_id[str(model_id)] = entry

    _MODEL_CATALOG_CACHE = compact_metadata(
        {
            "source": str(catalog_path),
            "count": len(normalized_models),
            "models": normalized_models,
            "indexes": {
                "model_id_to_model": by_id,
            },
        }
    )
    return _MODEL_CATALOG_CACHE


def find_catalog_model_by_id(model_id: str) -> dict[str, Any]:
    catalog = load_model_catalog()
    indexes = catalog.get("indexes") if isinstance(catalog.get("indexes"), dict) else {}
    by_id = indexes.get("model_id_to_model") if isinstance(indexes.get("model_id_to_model"), dict) else {}
    model = by_id.get(model_id)
    return model if isinstance(model, dict) else {}


def first_thumbnail_url(blueprint: dict[str, Any]) -> str | None:
    thumbnails = blueprint.get("thumbnails")
    if isinstance(thumbnails, dict):
        for key in [
            "thumbnailUrl",
            "thumbnailUrlLandscape",
            "thumbnailUrlBanner",
            "thumbnailUrlExtremePortrait",
            "videoUrl",
        ]:
            value = thumbnails.get(key)
            if value:
                return str(value)
    if isinstance(thumbnails, list):
        for item in thumbnails:
            if isinstance(item, dict) and item.get("url"):
                return str(item["url"])
    return None


def find_catalog_blueprint_by_id(catalog: dict[str, Any], blueprint_id: str) -> dict[str, Any]:
    for blueprint in catalog.get("blueprints") or []:
        if not isinstance(blueprint, dict):
            continue
        if blueprint_id in {str(blueprint.get("id") or ""), str(blueprint.get("akUUID") or "")}:
            return blueprint
    return {}


def find_catalog_blueprint_by_version(catalog: dict[str, Any], version_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    indexes = catalog.get("indexes") if isinstance(catalog.get("indexes"), dict) else {}
    version_index = indexes.get("version_id_to_blueprint_id") if isinstance(indexes.get("version_id_to_blueprint_id"), dict) else {}
    blueprint_id = version_index.get(version_id)
    if blueprint_id:
        blueprint = find_catalog_blueprint_by_id(catalog, str(blueprint_id))
        for version in blueprint.get("versions") or []:
            if isinstance(version, dict) and version_id in {
                str(version.get("id") or ""),
                str(version.get("akUUID") or ""),
            }:
                return blueprint, version
        return blueprint, {}

    for blueprint in catalog.get("blueprints") or []:
        if not isinstance(blueprint, dict):
            continue
        for version in blueprint.get("versions") or []:
            if isinstance(version, dict) and version_id in {
                str(version.get("id") or ""),
                str(version.get("akUUID") or ""),
            }:
                return blueprint, version
    return {}, {}


def normalize_blueprint_io_metadata(version: dict[str, Any]) -> dict[str, Any]:
    ui_metadata = version.get("ui_metadata") or version.get("uiMetadata")
    if not isinstance(ui_metadata, dict):
        return {}

    expected_inputs = []
    for item in ui_metadata.get("inputs") or []:
        if not isinstance(item, dict):
            continue
        expected_inputs.append(
            compact_metadata(
                {
                    "type": item.get("type"),
                    "label": item.get("label"),
                    "setting_name": item.get("settingName") or item.get("setting_name"),
                    "node_id": item.get("nodeId") or item.get("node_id"),
                    "required": item.get("required"),
                    "placeholder": item.get("placeholder"),
                }
            )
        )

    expected_outputs = []
    for item in ui_metadata.get("outputs") or []:
        if not isinstance(item, dict):
            continue
        expected_outputs.append(
            compact_metadata(
                {
                    "type": item.get("type"),
                }
            )
        )

    return compact_metadata(
        {
            "expected_inputs": expected_inputs,
            "expected_outputs": expected_outputs,
        }
    )


def blueprint_catalog_metadata(blueprint: dict[str, Any], version: dict[str, Any]) -> dict[str, Any]:
    if not blueprint:
        return {}
    version_io = normalize_blueprint_io_metadata(version)
    blueprint_ak_uuid = blueprint.get("akUUID") or blueprint.get("ak_uuid") or blueprint.get("id")
    version_ak_uuid = version.get("akUUID") or version.get("ak_uuid") or version.get("id")
    return compact_metadata(
        {
            "blueprint_ak_uuid": blueprint_ak_uuid,
            "name": blueprint.get("name"),
            "description": blueprint.get("description"),
            "official": blueprint.get("official"),
            "thumbnail_url": first_thumbnail_url(blueprint),
            "version_ak_uuid": version_ak_uuid,
            "version_id": version_ak_uuid,
            "version_cost": version.get("cost"),
            "version_models": version.get("models"),
            "version_ui_metadata_schema": version.get("ui_metadata_schema_version")
            or version.get("uiMetadataSchemaVersion"),
            **version_io,
            "catalog_source": BLUEPRINT_CATALOG_SOURCE,
        }
    )


def extract_source_images(generation: dict[str, Any]) -> list[dict[str, Any]]:
    enrichment = get_enrichment(generation)
    sources = enrichment.get("source_images") or []
    if not isinstance(sources, list):
        return []
    return [source for source in sources if isinstance(source, dict)]


def extract_blueprint_metadata(generation: dict[str, Any]) -> dict[str, Any]:
    enrichment = get_enrichment(generation)
    blueprint = enrichment.get("blueprint")
    if not isinstance(blueprint, dict):
        return {}

    metadata = dict(blueprint)
    catalog = load_blueprint_catalog()
    if catalog:
        version_id = metadata.get("version_id") or metadata.get("blueprint_version_id")
        blueprint_id = (
            metadata.get("blueprint_ak_uuid")
            or metadata.get("blueprint_id")
            or metadata.get("akUUID")
            or metadata.get("ak_uuid")
            or metadata.get("id")
        )
        catalog_blueprint: dict[str, Any] = {}
        catalog_version: dict[str, Any] = {}

        if version_id:
            catalog_blueprint, catalog_version = find_catalog_blueprint_by_version(
                catalog,
                str(version_id),
            )
        elif blueprint_id:
            catalog_blueprint = find_catalog_blueprint_by_id(catalog, str(blueprint_id))

        catalog_metadata = blueprint_catalog_metadata(catalog_blueprint, catalog_version)
        if catalog_metadata:
            metadata = {**catalog_metadata, **metadata}

    return compact_metadata(metadata)


def blueprint_ak_uuid(generation: dict[str, Any]) -> str | None:
    blueprint = display_blueprint_metadata(generation)
    value = (
        blueprint.get("blueprint_ak_uuid")
        or blueprint.get("akUUID")
        or blueprint.get("ak_uuid")
        or blueprint.get("blueprint_id")
        or blueprint.get("id")
    )
    if value:
        return str(value)
    return None


def blueprint_name(generation: dict[str, Any]) -> str | None:
    blueprint = extract_blueprint_metadata(generation)
    value = blueprint.get("name") or blueprint.get("blueprint_name")
    if value:
        return str(value)
    return None


def iter_media_urls(generation: dict[str, Any]) -> list[str]:
    urls = []
    for image in extract_generated_images(generation):
        for key in ["url", "motionMP4URL"]:
            value = image.get(key)
            if isinstance(value, str) and value:
                urls.append(value)
    return urls


def infer_blueprint_from_media_urls(generation: dict[str, Any]) -> dict[str, Any]:
    catalog = load_blueprint_catalog()
    if not catalog:
        return {}

    media_text = "\n".join(iter_media_urls(generation)).lower()
    if not media_text:
        return {}

    candidates = []
    for blueprint in catalog.get("blueprints") or []:
        if not isinstance(blueprint, dict):
            continue
        name = blueprint.get("name")
        if not name:
            continue
        slug = underscore_slug(str(name))
        if slug and slug in media_text:
            candidates.append((len(slug), blueprint, slug))

    if not candidates:
        return {}

    _, blueprint, slug = sorted(candidates, key=lambda item: item[0], reverse=True)[0]
    blueprint_ak_uuid = blueprint.get("akUUID") or blueprint.get("ak_uuid") or blueprint.get("id")
    return compact_metadata(
        {
            "blueprint_ak_uuid": blueprint_ak_uuid,
            "name": blueprint.get("name"),
            "description": blueprint.get("description"),
            "official": blueprint.get("official"),
            "thumbnail_url": first_thumbnail_url(blueprint),
            "inferred": True,
            "inference_source": "media_url_slug",
            "matched_slug": slug,
            "catalog_source": BLUEPRINT_CATALOG_SOURCE,
        }
    )


def display_blueprint_metadata(generation: dict[str, Any]) -> dict[str, Any]:
    real_blueprint = extract_blueprint_metadata(generation)
    if real_blueprint:
        return real_blueprint
    return infer_blueprint_from_media_urls(generation)


def display_blueprint_name(generation: dict[str, Any]) -> str | None:
    blueprint = display_blueprint_metadata(generation)
    value = blueprint.get("name") or blueprint.get("blueprint_name")
    if value:
        return str(value)
    return None


def has_source_image(generation: dict[str, Any]) -> bool:
    return bool(extract_source_images(generation))


def first_source_image_kind(generation: dict[str, Any]) -> str | None:
    kinds = []
    for source in extract_source_images(generation):
        kind = source.get("kind")
        if kind and str(kind) not in kinds:
            kinds.append(str(kind))
    if len(kinds) > 1:
        return "mixed"
    if kinds:
        return kinds[0]
    return None


def has_blueprint(generation: dict[str, Any]) -> bool:
    return bool(display_blueprint_metadata(generation))


def blueprint_version_id(generation: dict[str, Any]) -> str | None:
    blueprint = extract_blueprint_metadata(generation)
    value = blueprint.get("version_id") or blueprint.get("blueprint_version_id")
    if value:
        return str(value)
    return None


def infer_media_type(generation: dict[str, Any]) -> str | None:
    image_count = len(
        [
            image
            for image in extract_generated_images(generation)
            if image.get("url")
        ]
    )
    video_count = count_videos(generation)

    if image_count and video_count:
        return "mixed"
    if video_count:
        return "video"
    if image_count:
        return "image"
    return None


def build_relation_lines(generation: dict[str, Any]) -> list[str]:
    lines = []
    generation_id = generation.get("id")

    for index, image in enumerate(extract_generated_images(generation), start=1):
        image_id = image.get("id")
        image_label = f"Image {index}"
        if image_id:
            image_label = f"{image_label} `{image_id}`"

        variations = extract_image_variations(image)
        for variation in variations:
            relation_label = "variation"
            transform_type = variation.get("transform_type")
            if transform_type:
                relation_label = humanize_identifier(str(transform_type)).lower()

            detail_parts = []
            if variation.get("id"):
                detail_parts.append(f"id: `{variation['id']}`")
            if variation.get("status"):
                detail_parts.append(f"status: `{variation['status']}`")
            detail_suffix = f" ({', '.join(detail_parts)})" if detail_parts else ""
            lines.append(f"- {image_label} -> {relation_label}{detail_suffix}")

        motion_url = image.get("motionMP4URL")
        if motion_url:
            motion_model = first_present_string(generation, ["motionModel", "motion_model"])
            relation_label = "motion/video"
            if motion_model:
                relation_label = f"{relation_label} `{motion_model}`"
            lines.append(f"- {image_label} -> {relation_label}: {motion_url}")

    if has_reference_hint(generation):
        init_strength = generation.get("initStrength")
        lines.append(
            "- Reference image hint detected"
            + (f" (`initStrength`: `{init_strength}`)" if init_strength not in (None, "") else "")
        )

    for source in extract_source_images(generation):
        label = "Source image"
        kind = source.get("kind")
        if kind:
            label = f"{label} `{kind}`"

        detail_parts = []
        for key, display in [
            ("id", "id"),
            ("source_generation_id", "source_generation_id"),
            ("node_id", "node_id"),
            ("setting_name", "setting_name"),
        ]:
            value = source.get(key)
            if value:
                detail_parts.append(f"{display}: `{value}`")

        detail_suffix = f" ({', '.join(detail_parts)})" if detail_parts else ""
        target = f"generation `{generation_id}`" if generation_id else "generation"
        url = source.get("url")
        if url:
            lines.append(f"- {label} -> {target}: {url}{detail_suffix}")
        else:
            lines.append(f"- {label} -> {target}{detail_suffix}")

    blueprint = display_blueprint_metadata(generation)
    version_id = blueprint.get("version_id") or blueprint.get("blueprint_version_id")
    name = blueprint.get("name") or blueprint.get("blueprint_name")
    target = f"generation `{generation_id}`" if generation_id else "generation"
    if version_id:
        if name:
            lines.append(f"- Blueprint `{name}` version `{version_id}` -> {target}")
        else:
            lines.append(f"- Blueprint version `{version_id}` -> {target}")
    elif name and blueprint.get("inferred"):
        source = blueprint.get("inference_source") or "inferred"
        lines.append(f"- Blueprint `{name}` -> {target} ({source})")

    return lines


def resolve_model_info(generation: dict[str, Any]) -> dict[str, Any]:
    explicit_name = first_present_string(
        generation,
        [
            "modelName",
            "model_name",
            "customModelName",
            "custom_model_name",
            "model",
        ],
    )
    if explicit_name and not explicit_name.isdigit():
        return {
            "label": explicit_name,
            "slug": slugify(explicit_name),
            "resolution": "explicit_name",
        }

    model_id = first_present_string(generation, ["modelId", "model_id"])
    if model_id:
        catalog_model = find_catalog_model_by_id(model_id)
        if catalog_model:
            label = str(catalog_model.get("name"))
            return {
                "label": label,
                "slug": slugify(label),
                "resolution": "platform_model_catalog",
            }

        known_name = KNOWN_PLATFORM_MODELS.get(model_id)
        if known_name:
            return {
                "label": known_name,
                "slug": slugify(known_name),
                "resolution": "known_model_id",
            }

    sd_version = first_present_string(generation, ["sdVersion", "sd_version"])
    if sd_version:
        label = humanize_api_enum(sd_version)
        return {
            "label": label,
            "slug": slugify(label),
            "resolution": "sd_version_fallback",
        }

    motion_model = first_present_string(generation, ["motionModel", "motion_model"])
    if motion_model:
        label = humanize_api_enum(motion_model)
        return {
            "label": label,
            "slug": slugify(label),
            "resolution": "motion_model_fallback",
        }

    return {
        "label": None,
        "slug": None,
        "resolution": "unresolved",
    }


def infer_generation_family(generation: dict[str, Any]) -> str:
    if generation.get("motion") or first_present_string(
        generation, ["motionModel", "motion_model"]
    ):
        return "motion"

    sd_version = first_present_string(generation, ["sdVersion", "sd_version"])
    model_id = first_present_string(generation, ["modelId", "model_id"])
    if model_id in KNOWN_PLATFORM_MODELS or find_catalog_model_by_id(model_id):
        return "standard"

    if model_id:
        return "custom_workflow"

    if sd_version and sd_version not in {"PHOENIX", "FLUX", "FLUX_DEV", "KINO_2_1"}:
        return "custom_workflow"

    return "standard"


def build_audit_flags(generation: dict[str, Any], model_info: dict[str, Any]) -> list[str]:
    flags = []

    model_id = first_present_string(generation, ["modelId", "model_id"])
    if (
        model_id
        and model_id not in KNOWN_PLATFORM_MODELS
        and not find_catalog_model_by_id(model_id)
        and model_info.get("resolution") not in {
            "explicit_name",
            "sd_version_fallback",
            "motion_model_fallback",
        }
    ):
        flags.append("unmapped_model_id")

    if model_info.get("resolution") == "unresolved":
        flags.append("unresolved_model_label")

    if has_reference_hint(generation):
        flags.append("reference_image_hint")

    generated_images = generation.get("generated_images") or []
    if any(
        isinstance(image, dict) and extract_image_variations(image)
        for image in generated_images
    ):
        flags.append("has_linked_variations")

    if infer_generation_family(generation) == "custom_workflow":
        flags.append("custom_workflow_signals")

    return flags


def build_agent_metadata(generation: dict[str, Any], source_json: str) -> dict[str, Any]:
    images = []
    model_info = resolve_model_info(generation)
    variation_count = 0

    for index, image in enumerate(extract_generated_images(generation), start=1):
        image_entry = {}
        image_entry["index"] = index
        if image.get("id"):
            image_entry["id"] = image.get("id")
        if image.get("url"):
            image_entry["url"] = image.get("url")
        if image.get("motionMP4URL"):
            image_entry["motion_mp4_url"] = image.get("motionMP4URL")
        variations = extract_image_variations(image)
        if variations:
            variation_count += len(variations)
            image_entry["variations"] = variations
        if image_entry:
            images.append(image_entry)

    metadata = {
        "source": {
            "system": "leonardo_api",
            "payload_kind": "generation",
            "pipeline": "leonardo_export_v1",
            "source_json": source_json,
            "leonardo_generation_id": generation.get("id"),
            "created_at": normalize_created_at(generation),
        },
        "generation": {
            "model_id": generation.get("modelId"),
            "model_label": model_info.get("label"),
            "model_key": extract_model_key(generation),
            "model_slug": model_info.get("slug"),
            "model_resolution": model_info.get("resolution"),
            "generation_family": infer_generation_family(generation),
            "media_type": infer_media_type(generation),
            "seed": generation.get("seed"),
            "status": generation.get("status"),
            "public": generation.get("public"),
            "image_width": generation.get("imageWidth"),
            "image_height": generation.get("imageHeight"),
            "aspect_ratio": compute_aspect_ratio(
                generation.get("imageWidth"), generation.get("imageHeight")
            ),
        },
        "parameters": {
            "sd_version": generation.get("sdVersion"),
            "scheduler": generation.get("scheduler"),
            "preset_style": generation.get("presetStyle"),
            "negative_prompt": generation.get("negativePrompt"),
            "guidance_scale": generation.get("guidanceScale"),
            "inference_steps": generation.get("inferenceSteps"),
            "prompt_magic": generation.get("promptMagic"),
            "prompt_magic_strength": generation.get("promptMagicStrength"),
            "prompt_magic_version": generation.get("promptMagicVersion"),
            "photo_real": generation.get("photoReal"),
            "photo_real_strength": generation.get("photoRealStrength"),
            "ultra": generation.get("ultra"),
            "init_strength": generation.get("initStrength"),
            "motion": generation.get("motion"),
            "motion_model": generation.get("motionModel"),
            "motion_strength": generation.get("motionStrength"),
            "image_to_video": generation.get("imageToVideo"),
        },
        "relations": {
            "image_count": len(images),
            "variation_count": variation_count or None,
            "video_count": count_videos(generation) or None,
            "has_variations": True if variation_count > 0 else None,
            "has_motion": True if count_videos(generation) > 0 else None,
            "has_elements": True if generation.get("generation_elements") else None,
            "has_reference_hint": True if has_reference_hint(generation) else None,
            "has_source_image": True if has_source_image(generation) else None,
            "has_blueprint": True if has_blueprint(generation) else None,
            "images": images,
            "videos": extract_motion_entries(generation),
            "source_images": extract_source_images(generation),
        },
        "blueprint": display_blueprint_metadata(generation),
        "enrichment": get_enrichment(generation).get("audit"),
        "audit": {
            "flags": build_audit_flags(generation, model_info),
            "raw_fields_of_interest": {
                "model_id": generation.get("modelId"),
                "sd_version": generation.get("sdVersion"),
                "motion_model": generation.get("motionModel"),
                "scheduler": generation.get("scheduler"),
                "preset_style": generation.get("presetStyle"),
                "init_strength": generation.get("initStrength"),
            },
        },
    }

    return compact_metadata(metadata)


def build_frontmatter(generation: dict[str, Any], source_json: str) -> list[str]:
    note_title = build_system_title(generation)
    created_date = extract_created_date(generation)
    model_name = resolve_model_name(generation)
    prompt_short = compact_text(str(generation.get("prompt") or ""), max_words=4)
    tags = build_tags(generation)
    size = build_size(generation)
    generation_id = first_present_string(generation, ["id"])
    generated_images = extract_generated_images(generation)
    cover_image = first_image_with_url(generation)
    aspect_ratio = compute_aspect_ratio(
        generation.get("imageWidth"), generation.get("imageHeight")
    )
    variation_count = count_variations(generation)
    video_count = count_videos(generation)

    lines = ["---"]
    lines.append("type: leonardo_generation")
    lines.extend(yaml_string_field("generation_id", generation_id))
    lines.extend(yaml_string_field("model", model_name))
    lines.extend(yaml_string_field("media_type", infer_media_type(generation)))
    lines.extend(yaml_string_field("blueprint", display_blueprint_name(generation)))
    lines.extend(yaml_string_field("blueprint_ak_uuid", blueprint_ak_uuid(generation)))
    lines.extend(yaml_string_field("blueprint_version_id", blueprint_version_id(generation)))
    lines.extend(yaml_string_field("source_image_kind", first_source_image_kind(generation)))
    lines.extend(yaml_string_field("prompt_short", prompt_short))
    lines.extend(yaml_field("seed", generation.get("seed")))
    lines.extend(yaml_block("prompt", generation.get("prompt")))
    lines.extend(yaml_string_field("size", size))
    lines.extend(yaml_string_field("aspect_ratio", aspect_ratio))
    lines.extend(yaml_string_field("cover_image_url", cover_image.get("url") if cover_image else None))
    lines.extend(yaml_field("image_count", len(generated_images) if generated_images else None))
    lines.extend(yaml_field("variation_count", variation_count if variation_count else None))
    lines.extend(yaml_field("video_count", video_count if video_count else None))
    lines.extend(yaml_field("has_variations", True if variation_count else None))
    lines.extend(yaml_field("has_motion", True if video_count else None))
    lines.extend(yaml_field("has_reference_hint", True if has_reference_hint(generation) else None))
    lines.extend(yaml_list("tags", tags))
    lines.extend(yaml_raw_field("created", created_date))
    lines.extend(yaml_string_field("status", generation.get("status")))
    lines.append("---")
    return lines


def build_metadata_lines(generation: dict[str, Any]) -> list[str]:
    fields = [
        ("Generation ID", generation.get("id")),
        ("Created", normalize_created_at(generation)),
        ("Status", generation.get("status")),
        ("Model ID", generation.get("modelId")),
        ("SD Version", generation.get("sdVersion")),
        ("Style", generation.get("presetStyle")),
        ("Scheduler", generation.get("scheduler")),
        ("Seed", generation.get("seed")),
        (
            "Size",
            (
                f"{generation.get('imageWidth')}x{generation.get('imageHeight')}"
                if generation.get("imageWidth") and generation.get("imageHeight")
                else None
            ),
        ),
        ("Public", generation.get("public")),
    ]
    normalized = []
    for label, value in fields:
        if value in (None, ""):
            continue
        if isinstance(value, bool):
            value = "true" if value else "false"
        normalized.append(f"- {label}: `{value}`")
    return normalized


def build_overview_lines(generation: dict[str, Any]) -> list[str]:
    lines = []
    blueprint = display_blueprint_metadata(generation)
    if blueprint:
        label = "Blueprint"
        value = blueprint.get("name") or blueprint.get("blueprint_name")
        if value:
            lines.append(f"- {label}: `{value}`")

    model_name = resolve_model_name(generation)
    if model_name:
        lines.append(f"- Model: `{model_name}`")

    media_type = infer_media_type(generation)
    if media_type:
        lines.append(f"- Media: `{media_type}`")

    sources = extract_source_images(generation)
    if sources:
        kinds = []
        for source in sources:
            kind = source.get("kind")
            if kind and kind not in kinds:
                kinds.append(kind)
        kind_label = ", ".join(str(kind) for kind in kinds) if kinds else "source image"
        lines.append(f"- Source images: `{len(sources)}` ({kind_label})")

    video_count = count_videos(generation)
    if video_count:
        lines.append(f"- Motion/video: `{video_count}`")

    return lines


def build_markdown(generation: dict[str, Any], source_json: str) -> str:
    generated_images = generation.get("generated_images") or []
    generation_elements = generation.get("generation_elements") or []
    note_title = build_human_title(generation)
    prompt = generation.get("prompt") or ""
    negative_prompt = generation.get("negativePrompt") or ""
    agent_metadata = build_agent_metadata(generation, source_json)

    lines = build_frontmatter(generation, source_json)
    lines.append("")
    lines.append(f"# {note_title}")
    lines.append("")

    overview_lines = build_overview_lines(generation)
    if overview_lines:
        lines.append("## Overview")
        lines.append("")
        lines.extend(overview_lines)
        lines.append("")

    if prompt:
        lines.append("## Prompt")
        lines.append("")
        lines.append("```prompt")
        lines.append(prompt)
        lines.append("```")
        lines.append("")

    if negative_prompt:
        lines.append("## Negative Prompt")
        lines.append("")
        lines.append("```prompt")
        lines.append(negative_prompt)
        lines.append("```")
        lines.append("")

    image_lines = []
    motion_lines = []
    for index, image in enumerate(generated_images, start=1):
        if not isinstance(image, dict):
            continue
        url = image.get("url")
        image_id = image.get("id")
        motion_url = image.get("motionMP4URL")
        variations = extract_image_variations(image)
        if url:
            label = f"Image {index}"
            if image_id:
                label = f"Image {index} ({image_id})"
            image_lines.append(f"- ![{label}]({url})")
            for variation in variations:
                variation_label = "Variation"
                transform_type = variation.get("transform_type")
                if transform_type:
                    variation_label = humanize_identifier(str(transform_type))

                detail_parts = []
                if variation.get("status"):
                    detail_parts.append(f"status: `{variation['status']}`")
                if variation.get("id"):
                    detail_parts.append(f"id: `{variation['id']}`")
                detail_suffix = f" ({', '.join(detail_parts)})" if detail_parts else ""

                variation_url = variation.get("url")
                if variation_url:
                    image_lines.append(
                        f"  - [{variation_label}]({variation_url}){detail_suffix}"
                    )
                else:
                    image_lines.append(f"  - {variation_label}{detail_suffix}")
        if motion_url:
            label = f"Motion {index}"
            if image_id:
                label = f"Motion {index} ({image_id})"
            motion_lines.append(f"- [{{label}}]({motion_url})".format(label=label))

    if image_lines:
        lines.append("## Images")
        lines.append("")
        lines.extend(image_lines)
        lines.append("")

    if motion_lines:
        lines.append("## Motion")
        lines.append("")
        lines.extend(motion_lines)
        lines.append("")

    relation_lines = build_relation_lines(generation)
    if relation_lines:
        lines.append("## Relations")
        lines.append("")
        lines.extend(relation_lines)
        lines.append("")

    element_lines = []
    for element in generation_elements:
        lora = element.get("lora") or {}
        name = lora.get("name") or "Unnamed element"
        weight = element.get("weightApplied")
        if weight not in (None, ""):
            element_lines.append(f"- {name} (`{weight}`)")
        else:
            element_lines.append(f"- {name}")

    if element_lines:
        lines.append("## Elements")
        lines.append("")
        lines.extend(element_lines)
        lines.append("")

    lines.append("## Agent Metadata")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(agent_metadata, indent=2, ensure_ascii=False))
    lines.append("```")
    lines.append("")

    return "\n".join(lines)


def default_output_path(output_dir: Path, generation: dict[str, Any]) -> Path:
    return output_dir / f"{build_filename_title(generation)}.md"


def main() -> None:
    args = parse_args()
    input_path = Path(args.input_json)
    payload = load_json(input_path)
    generation = extract_generation(payload)
    markdown = build_markdown(generation, input_path.as_posix())

    if args.stdout:
        print(markdown)
        return

    output_path = (
        Path(args.output)
        if args.output
        else default_output_path(Path(args.output_dir), generation)
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")
    print(output_path)


if __name__ == "__main__":
    main()
