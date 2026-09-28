# Repository and release guide

Repository: https://github.com/ariasm11/regulatory_reporting

The repository includes the Python pipeline, SQL, configuration, 1,200-row synthetic sample, tests, regulatory mapping, documented user-supplied cloud evidence, local benchmarks and the full offline console in `web/`.

Large generated batches (`data/portfolio`, `data/trial_100k`) and runtime output stay outside git. Recreate them with the generator when needed. The accepted cloud milestone uses the 1,200-row August sample; larger cloud runs are optional and can incur costs.

## Verification

```bash
python3 -m unittest discover -s tests -v
python3 -m siter.run --data data/sample --period 202608 --out output
python3 -m http.server 8000 --directory web
```

The Actions workflow runs the Python tests and sample pipeline without cloud credentials. The optional BigQuery adapter requires separately configured user credentials. Do not commit credentials.

## Demo access

The GitHub source is public. The separately hosted Sites console remains private: https://siter-reporting-console.ariasmatias91.chatgpt.site. Publishing this repository does not change the Site's audience or activate GitHub Pages.

Before sharing a live demo with recruiters, configure its intended audience or host `web/` on a public static host. Source and local run instructions are sufficient to review the code now.
