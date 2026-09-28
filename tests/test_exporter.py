from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


renderer = load_module(
    "export_generation_to_obsidian",
    SCRIPTS / "export_generation_to_obsidian.py",
)
incremental = load_module(
    "export_new_generations_only",
    SCRIPTS / "export_new_generations_only.py",
)


class ExporterTests(unittest.TestCase):
    def test_synthetic_fixture_matches_renderer(self) -> None:
        source = ROOT / "sample_exports" / "leonardo_json" / "sample_generation.json"
        expected = ROOT / "sample_exports" / "leonardo_md" / "sample_generation.md"
        payload = renderer.load_json(source)
        generation = renderer.extract_generation(payload)

        actual = renderer.build_markdown(
            generation,
            "sample_exports/leonardo_json/sample_generation.json",
        )

        self.assertEqual(expected.read_text(encoding="utf-8"), actual)
        self.assertNotIn("/Users/", actual)

    def test_state_round_trip_uses_an_explicit_temporary_path(self) -> None:
        state = {
            "exported_ids": ["sample-generation-id"],
            "exports_by_id": {"sample-generation-id": {"status": "exported"}},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state" / "exported_ids.json"
            incremental.save_state(path, state)
            self.assertEqual(state, incremental.load_state(path))

    def test_synthetic_payload_contains_no_secret_or_real_media_url(self) -> None:
        source = ROOT / "sample_exports" / "leonardo_json" / "sample_generation.json"
        text = source.read_text(encoding="utf-8")
        payload = json.loads(text)

        self.assertEqual("sample-generation-id", payload["id"])
        self.assertNotIn("cloud.leonardo.ai", text)
        self.assertNotIn("cdn.leonardo.ai", text)
        self.assertNotIn("LEONARDO_API_KEY", text)


if __name__ == "__main__":
    unittest.main()
