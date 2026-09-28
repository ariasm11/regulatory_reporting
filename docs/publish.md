# Repository and release guide

Repository: https://github.com/ariasm11/regulatory_reporting

The repository includes the Python pipeline, SQL, configuration, 1,200-row synthetic sample, tests, regulatory mapping, recorded cloud execution evidence, local benchmarks and the full offline console in `web/`.

Large generated batches (`data/portfolio`, `data/trial_100k`) and runtime output stay outside git. Recreate them with the generator when needed. Cloud validation covers the August report on the 1,200-row source sample; larger cloud runs are optional and can incur costs.

## Verification

```bash
python3 -m unittest discover -s tests -v
python3 -m siter.run --data data/sample --period 202608 --out output
python3 -m http.server 8000 --directory web
```

The Actions workflow runs the Python tests and sample pipeline without cloud credentials. The optional BigQuery adapter requires separately configured user credentials. Do not commit credentials.

## Demo access

The GitHub source and interface screenshots are public. A public hosted demo is not available yet. Run the console locally using the command above; publishing the repository does not activate GitHub Pages.
