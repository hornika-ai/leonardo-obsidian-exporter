# Security and privacy

Leonardo generation payloads can contain private prompts, account identifiers,
media URLs, and other personal metadata. Do not commit real API responses,
generated notes, state files, or credentials.

The repository ignores `.env`, `output/`, and `state/`. Public tests operate on
synthetic fixtures only.

If you report a vulnerability, remove all real payload content and credentials
from the report before sharing it.
