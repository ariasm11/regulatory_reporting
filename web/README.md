# Reporting console

## Authenticated execution workspace

From the repository root, run `python3 -m siter.server add-user analyst`, then `python3 -m siter.server serve`. Open `http://127.0.0.1:8000`. The workspace accepts anonymized CSV datasets, validates them, runs the pipeline and opens results in the existing console. See [execution guide](../docs/execution_console.md) and [CSV contract](../docs/csv_contract.md). A static server cannot execute the pipeline.

## Offline sample console

Static HTML/CSS/JavaScript interface with saved synthetic sample outputs. No API keys, backend or BigQuery queries.

From the repository root:

```bash
python3 -m http.server 8000 --directory web
```

Open http://localhost:8000. Views include overview, searchable accounts, controls, a TXT field inspector and monthly history. Downloadable TXT and ZIP artifacts preserve the exporter bytes.

To regenerate all six sample periods:

```bash
python3 -m scripts.export_ux --out web/data
```

Only August 2026 has documented BigQuery parity; the other months are local references. The recorded cloud execution summary is retained as evidence; downloadable files are local reproductions with matching August hashes. No ARCA acceptance is implied.

This folder can be served by any static web server. A public hosted demo is not available yet; use the local instructions above or the screenshots in the main README.

## Optional development preview

For a live development server, from the repository root:

```bash
npm ci
npm run dev
```

Vite is a development-only dependency. The static console still works with the Python server above and needs no Node.js runtime in production.

Real desktop screenshots are included under `docs/images/` and embedded in the main README.
