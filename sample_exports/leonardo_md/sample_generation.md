---
type: leonardo_generation
generation_id: "sample-generation-id"
media_type: "image"
prompt_short: "sanitized sample prompt documentation"
prompt: >-
  Sanitized sample prompt for documentation and tests.
cover_image_url: "https://example.invalid/leonardo/sample-image.png"
image_count: 1
tags:
  - "leonardo"
  - "generation"
  - "ai-image"
created: 2026-01-01
---

# Sanitized Sample Prompt - 2026-01-01

## Overview

- Media: `image`

## Prompt

```prompt
Sanitized sample prompt for documentation and tests.
```

## Images

- ![Image 1 (sample-image-id)](https://example.invalid/leonardo/sample-image.png)

## Agent Metadata

```json
{
  "source": {
    "system": "leonardo_api",
    "payload_kind": "generation",
    "pipeline": "leonardo_export_v1",
    "source_json": "sample_exports/leonardo_json/sample_generation.json",
    "leonardo_generation_id": "sample-generation-id",
    "created_at": "2026-01-01T00:00:00Z"
  },
  "generation": {
    "model_id": "sample-model-id",
    "model_resolution": "unresolved",
    "generation_family": "custom_workflow",
    "media_type": "image"
  },
  "relations": {
    "image_count": 1,
    "images": [
      {
        "index": 1,
        "id": "sample-image-id",
        "url": "https://example.invalid/leonardo/sample-image.png"
      }
    ]
  },
  "audit": {
    "flags": [
      "unmapped_model_id",
      "unresolved_model_label",
      "custom_workflow_signals"
    ],
    "raw_fields_of_interest": {
      "model_id": "sample-model-id"
    }
  }
}
```
