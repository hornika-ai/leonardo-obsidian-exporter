# Leonardo to Obsidian Exporter

A small Python toolkit that turns Leonardo.Ai generation metadata into local
JSON snapshots and readable Obsidian Markdown notes.

The repository contains two complementary commands:

- `export_generation_to_obsidian.py` renders an existing Leonardo generation
  payload without making a network request;
- `export_new_generations_only.py` uses authenticated, read-only API requests
  to retrieve generations that are not yet present in the local state file.

The tools do not create images or upload assets. Prompts, account identifiers,
generation metadata, and media URLs may still be private, so real exports stay
inside ignored local directories. The committed examples are synthetic.

## Requirements

- Python 3.11 or newer;
- a Leonardo.Ai API key only for the incremental API exporter.

Create a virtual environment and install the optional `.env` loader:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
```

Copy the environment template and add your own key locally:

```bash
cp .env.example .env
```

Never commit `.env` or paste an API key into an issue, log, or fixture.

## Render one saved payload

The renderer accepts either a complete API response containing
`generations_by_pk` or the generation object itself:

```bash
python3 scripts/export_generation_to_obsidian.py \
  --input-json sample_exports/leonardo_json/sample_generation.json \
  --stdout
```

To write a note instead:

```bash
python3 scripts/export_generation_to_obsidian.py \
  --input-json sample_exports/leonardo_json/sample_generation.json \
  --output output/markdown/sample-generation.md
```

## Export new generations

With `LEONARDO_API_KEY` defined in the shell or local `.env` file:

```bash
python3 scripts/export_new_generations_only.py --max-generations 10
```

By default, private runtime files are written below `output/`:

```text
output/
  json/       # raw API snapshots
  markdown/   # Obsidian notes
  state/      # IDs already exported
```

Use `--output-dir`, `--json-dir`, and `--state-file` to place these files in
your own Obsidian and data directories. Existing environment variables take
precedence over values in `.env`.

## Optional local catalogs

The renderer can enrich labels when these ignored local files exist:

```text
state/blueprints_catalog.json
state/platform_models.json
```

They are optional. Missing catalogs do not prevent rendering, and they are not
included in the public repository.

## Public fixture and tests

`sample_exports/` contains one synthetic generation, its expected Markdown
rendering, and a sample state file. It contains no real prompt, account ID,
generation ID, API key, or Leonardo CDN URL.

Run the public test suite with:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

## API note

The exporter uses Leonardo.Ai's REST base URL and bearer-token authentication.
API behavior can evolve; consult the current official Leonardo.Ai API
documentation before adapting endpoints or response shapes.
