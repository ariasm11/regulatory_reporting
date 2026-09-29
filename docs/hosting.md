# Hosted demonstration

The repository includes a Docker image definition and a Render Free Blueprint for a public HTTPS URL with **invite-only application access**. A public URL does not make datasets or downloads public. The original static Site cannot run the Python backend; publishing only `web/` would not enable uploads or execution.

**Deployment status:** prepared, not provisioned. No public execution URL is available yet. The default Blueprint selects Free compute and no disk. A separate `render.persistent.yaml` selects paid compute and a persistent disk; do not deploy that variant for the free demo.

## Proposed deployment

- One Docker web service, one process and one worker.
- Provider-managed HTTPS reverse proxy; the Python port is not exposed directly to visitors.
- Temporary local state under `/tmp/siter-state`. It is lost on restarts, redeploys and free-instance spin-down.
- Administrator-created accounts, no registration or public default credentials.
- CSV and the included synthetic sample. The public image does not install BigQuery dependencies or configure cloud credentials.
- Existing 100,000-row / 24 MiB request limits, one upload body admitted at a time and private artifacts. Runs expire after at most 24 hours, but may disappear sooner on a restart.

The deployment keeps the current Python pipeline and server. It is a controlled demonstration for invited reviewers using anonymized data, not a general-purpose production banking service. Avoid widely shared credentials. Backups/snapshots at the hosting provider require a separate retention policy and may outlive application-level deletion.

## Render setup

1. Sign in to Render with the account that should own and pay for the service. Connect `ariasm11/regulatory_reporting` and create a Blueprint from `render.yaml`.
2. Confirm the service compute plan is **Free** and no disk is attached. A free workspace alone does not make a paid compute instance free. To keep spending at zero, review bandwidth/build allowances and spend limits; without a payment method, Render suspends affected free services/builds when allowances run out instead of billing overages.
3. Set `SITER_BOOTSTRAP_USER` and `SITER_BOOTSTRAP_PASSWORD` as private environment values. Choose a unique password of at least 12 characters. Do not put credentials in GitHub, screenshots or the README.
4. Deploy. The entrypoint uses Render's `RENDER_EXTERNAL_URL` as its fixed HTTPS origin and `PORT` for its internal listener. The initial account is created only if the local user database is empty.
5. When `/healthz` is healthy, open the assigned URL and sign in. **Keep the bootstrap credentials configured as secrets in Free mode:** after a restart the empty local database needs them to recreate the login. Existing accounts are not reset while the database survives. Sessions and report history are temporary.
6. Run the included sample, inspect/download its TXT and delete the run. The initial account is the only configured hosted account in the default Free setup. Do not share it between people uploading independent datasets; the local/persistent configuration supports separate reviewer accounts.
7. Add the verified public URL to the README only after this hosted check succeeds. Do not reuse the old private static-demo link.

Auto-deploy is disabled. Free instances sleep after 15 minutes without inbound traffic; the next request can take about one minute to start the app. Each restart can erase local state. Render provides 750 free instance hours per workspace/month, shared across free services. Do not add keep-alive jobs or enable paid services for this demo.

The paid `render.persistent.yaml` is an optional future migration requiring separate cost approval. It uses one persistent disk and one instance; it is not deployed automatically.

For a custom domain, set `SITER_PUBLIC_ORIGIN=https://your-domain.example` and use that exact domain; Host and Origin checks intentionally reject alternatives. DNS and TLS must be ready before changing the canonical origin.

## Account management

Render Free does not provide shell access. For this mode, configure the initial username/password in the service's private environment and keep them for recreation after restarts. A different password takes effect when the local user database is replaced; changing the environment alone does not reset an existing account.

For local or paid deployments with an interactive shell:

```bash
python -m siter.server --state /var/data/siter add-user reviewer
```

The command asks for and confirms a password. Repeating it resets that user's password and revokes prior sessions while preserving their runs. Use a separate account for each reviewer and communicate credentials privately. There is no automatic invitation/email delivery.

## Other Docker hosts

The image also runs behind an HTTPS reverse proxy on another compatible host. Persistent operation is optional; supply:

| Variable | Purpose |
| --- | --- |
| `SITER_PUBLIC_ORIGIN` | Exact public HTTPS origin, without a path |
| `SITER_STATE_DIR` | Absolute state path; use a volume only for persistent operation |
| `SITER_EPHEMERAL` | `true` displays the temporary-storage notice |
| `PORT` | Internal port, default `10000` |
| `SITER_BOOTSTRAP_USER` | Initial username, only for an empty installation |
| `SITER_BOOTSTRAP_PASSWORD` | Initial password, only for an empty installation |

The container prepares its state directory and drops root privileges to UID/GID 10001 before starting the service. A persistent configuration must provide a writable volume for that UID. `SIGTERM` triggers graceful server shutdown; interrupted work is marked failed on restart. Files on ephemeral container storage are not durable.

## Deployment validation

GitHub Actions builds the Docker image and runs a container smoke check for startup, health, initial account creation, Secure/HttpOnly cookies and authenticated configuration. The existing HTTP tests cover report generation and user isolation. A successful CI image test does not claim that a hosting account has been provisioned or a public URL tested.

Official references, checked 2026-09-29:

- [Free instance behavior and limits](https://render.com/docs/free)
- [Render pricing](https://render.com/pricing)
- [Docker services](https://render.com/docs/docker)
- [Persistent disks](https://render.com/docs/disks)
- [Environment variables](https://render.com/docs/environment-variables)
- [Blueprint configuration](https://render.com/docs/blueprint-spec)
