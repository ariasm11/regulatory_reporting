# Hosted demonstration

The repository includes a Docker image definition and a Render Blueprint for a public HTTPS URL with **invite-only application access**. A public URL does not make datasets or downloads public. The original static Site cannot run the Python backend; publishing only `web/` would not enable uploads or execution.

**Deployment status:** prepared, not provisioned. No public execution URL is available yet. Deploying the Blueprint creates paid resources; review the provider's estimate before confirming it.

## Proposed deployment

- One Docker web service, one process and one worker.
- Provider-managed HTTPS reverse proxy; the Python port is not exposed directly to visitors.
- A 1 GB persistent disk mounted at `/var/data`; state lives in `/var/data/siter`.
- Administrator-created accounts, no registration or public default credentials.
- CSV and the included synthetic sample. The public image does not install BigQuery dependencies or configure cloud credentials.
- Existing 100,000-row / 24 MiB request limits, one upload body admitted at a time, private artifacts and 24-hour run expiry.

The deployment keeps the current Python pipeline and server. It is a controlled demonstration for invited reviewers using anonymized data, not a general-purpose production banking service. Avoid widely shared credentials. Backups/snapshots at the hosting provider require a separate retention policy and may outlive application-level deletion.

## Render setup

1. Sign in to Render with the account that should own and pay for the service. Connect `ariasm11/regulatory_reporting` and create a Blueprint from `render.yaml`.
2. Review the paid 0.5 CPU / 512 MB service and 1 GB disk estimate. Budget approximately USD 7/month for the smallest paid web service, plus the disk; pricing may change. Confirm the current total in the dashboard before deployment. No service is created merely by committing these files.
3. Set `SITER_BOOTSTRAP_USER` and `SITER_BOOTSTRAP_PASSWORD` as private environment values. Choose a unique password of at least 12 characters. Do not put credentials in GitHub, screenshots or the README.
4. Deploy. The entrypoint uses Render's `RENDER_EXTERNAL_URL` as its fixed HTTPS origin and `PORT` for its internal listener. The initial account is created only if the persistent user database is empty.
5. When `/healthz` is healthy, open the assigned URL and sign in. Remove the bootstrap password from the service's environment after confirming the account works; subsequent deployments do not need it and will not reset existing accounts.
6. Run the included sample, inspect/download its TXT and delete the run. Confirm in a second account that the first account's runs are inaccessible before inviting reviewers.
7. Add the verified public URL to the README only after this hosted check succeeds. Do not reuse the old private static-demo link.

Auto-deploy is disabled in the Blueprint. Deploy reviewed changes manually. Persistent disks require a single service instance and can cause a brief interruption during deployment. Do not horizontally scale this SQLite/worker architecture.

For a custom domain, set `SITER_PUBLIC_ORIGIN=https://your-domain.example` and use that exact domain; Host and Origin checks intentionally reject alternatives. DNS and TLS must be ready before changing the canonical origin.

## Account management

From the provider's interactive shell:

```bash
python -m siter.server --state /var/data/siter add-user reviewer
```

The command asks for and confirms a password. Repeating it resets that user's password and revokes prior sessions while preserving their runs. Use a separate account for each reviewer and communicate credentials privately. There is no automatic invitation/email delivery.

## Other Docker hosts

The image also runs behind an HTTPS reverse proxy on another compatible host. Supply:

| Variable | Purpose |
| --- | --- |
| `SITER_PUBLIC_ORIGIN` | Exact public HTTPS origin, without a path |
| `SITER_STATE_DIR` | Absolute path under the mounted persistent volume |
| `PORT` | Internal port, default `10000` |
| `SITER_BOOTSTRAP_USER` | Initial username, only for an empty installation |
| `SITER_BOOTSTRAP_PASSWORD` | Initial password, only for an empty installation |

The container prepares its state directory and drops root privileges to UID/GID 10001 before starting the service. Other hosts must provide a writable persistent volume for that UID. `SIGTERM` triggers graceful server shutdown; interrupted work is marked failed on restart. Files on ephemeral container storage are not durable.

## Deployment validation

GitHub Actions builds the Docker image and runs a container smoke check for startup, health, initial account creation, Secure/HttpOnly cookies and authenticated configuration. The existing HTTP tests cover report generation and user isolation. A successful CI image test does not claim that a hosting account has been provisioned or a public URL tested.

Official references, checked 2026-09-29:

- [Render pricing](https://render.com/pricing)
- [Docker services](https://render.com/docs/docker)
- [Persistent disks](https://render.com/docs/disks)
- [Environment variables](https://render.com/docs/environment-variables)
- [Blueprint configuration](https://render.com/docs/blueprint-spec)
