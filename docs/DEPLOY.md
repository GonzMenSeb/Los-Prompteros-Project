# DEPLOY — the hosted instance

DecaBot runs permanently at **https://decabot.web.vespiridion.org**, behind a single
shared password. This is the durable link; `make tunnel` is still the demo-day primary
because it needs no VPS and no DNS.

Infrastructure lives in the **`vps-infrastructure`** repo, Ansible role **`decabot`**.
Nothing about the deployment is configured here beyond the `Dockerfile` and the
pipeline that drives it.

| | |
|---|---|
| URL | `https://decabot.web.vespiridion.org` |
| Password | `vault_decabot_password` in `vps-infrastructure/vault.yml` |
| Image | `zot.web.vespiridion.org/losprompteros/decabot:{latest,<git-sha>}` |
| On the host | `/opt/decabot/{docker-compose.yml,.env,states/}` |
| Ingress | Traefik v3 + Let's Encrypt, router `decabot`, one service on port 8000 |
| Liveness | `GET /ping` — outside the gate, safe to probe |
| CD | Jenkins job `decabot-deploy` · https://jenkins.web.vespiridion.org |
| Pipeline | [`infra/jenkins/Jenkinsfile`](../infra/jenkins/Jenkinsfile) here; job + credential in `vps-infrastructure/roles/jenkins/templates/casc.yml.j2` |
| PR checks | [`.github/workflows/test.yml`](../.github/workflows/test.yml) — offline suite, no secrets |

Read **[`../AGENTS.md`](../AGENTS.md) § Container deployment** before changing anything.
Every line in it was a failed attempt first.

## Ship a change

**Merge to `main`. That is the whole procedure.** The Jenkins job `decabot-deploy`
([`infra/jenkins/Jenkinsfile`](../infra/jenkins/Jenkinsfile), triggered by a GitHub push
webhook) tests, builds, pushes, deploys and health-checks. Pull requests get the offline
suite from GitHub Actions before they land.

A merge that touches only `*.md`, `docs/`, `LICENSE` or `.github/` builds nothing and
leaves the running instance alone. Everything else — `concierge/`, `assets/`,
`reflex.lock/`, `rxconfig.py`, `Dockerfile`, `requirements.txt`, `pytest.ini` — ships.
`tests/`, `fixtures/`, `scripts/`, `infra/jenkins/` and `Makefile` run the suite and stop
there, because the image is not built from them.

**Which commit is live** is a question `docker inspect` answers, because every image
carries its revision:

```bash
ssh ubuntu@148.113.172.15 \
  "docker inspect --format '{{index .Config.Labels \"org.opencontainers.image.revision\"}}' \
   zot.web.vespiridion.org/losprompteros/decabot:latest"
```

Ask it before you believe a bug report. A live turn dying on a storefront `429` on
29 Jul was not a code bug — it was `2d8a591` sitting unbuilt in `main` while the host
ran the 28 Jul image, and the only way to tell was that the traceback named an `httpx`
exception the current code cannot raise. This pipeline exists so that cannot recur.

### By hand, when Jenkins is down

```bash
make check                                    # never push a red suite

# Zot accepts OCI manifests ONLY. A plain `docker push` uploads every layer and then
# fails with `manifest invalid` at the manifest step — these flags are not optional.
docker buildx create --name decabot-builder --driver docker-container --bootstrap  # once
docker buildx build --builder decabot-builder --provenance=false --sbom=false \
  --label org.opencontainers.image.revision=$(git rev-parse --short HEAD) \
  --output type=image,\"name=zot.web.vespiridion.org/losprompteros/decabot:latest\",oci-mediatypes=true,push=true \
  .

cd ../vps-infrastructure          # run ansible from the repo root, see below
ansible-playbook --tags decabot playbook.yml
ansible-playbook tests/health-check.yml
```

Keep the `--label`. Dropping it leaves an unlabelled image on the host, which costs the
pipeline its rollback target on the next deploy.

`ansible.cfg` sets `vault_password_file = .vault_pass` as a **relative** path, so those
commands only find the password from the repo root; from anywhere else they prompt.
Ad-hoc `ansible` runs additionally need `-e @vault.yml` — `vars_files` is play-level, so
an ad-hoc module run never loads the vault and `ansible_host` comes out undefined.

## Roll back

The pipeline rolls itself back when the post-deploy health gate fails: it re-points
`:latest` at the previous revision's tag and brings the stack up again, then fails the
build. To do it by hand for a revision that passed the gate but is wrong anyway:

```bash
ssh ubuntu@148.113.172.15
docker pull zot.web.vespiridion.org/losprompteros/decabot:<sha>
docker tag zot.web.vespiridion.org/losprompteros/decabot:{<sha>,latest}
cd /opt/decabot && docker compose up -d
```

Every build pushes `:<git-short-sha>` alongside `:latest`, so any past revision is
still there to roll back to. Compose stays pinned to `:latest` — the role never changes.

## Change the password

Edit `vault_decabot_password` (`ansible-vault edit vault.yml`), then re-run the role. The
value is templated into `/opt/decabot/.env` as `DECABOT_PASSWORD`; no rebuild is needed.
Every already-admitted browser is logged out, because the cookie holds a digest derived
from the old password and is re-validated server-side on load.

**Unsetting `DECABOT_PASSWORD` disables the gate entirely** — that is deliberate, and it
is what keeps local dev and `make walkthrough` unaffected. Never template it empty on the
public host.

## Verify by hand

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://decabot.web.vespiridion.org/ping   # 200

# --http1.1 is load-bearing: Traefik negotiates h2 with curl, and Connection/Upgrade is
# an HTTP/1.1 mechanism, so over h2 a healthy app answers 400 Invalid websocket upgrade.
curl -s -D - -o /dev/null --http1.1 -N -m 3 \
  -H 'Connection: Upgrade' -H 'Upgrade: websocket' \
  -H 'Sec-WebSocket-Version: 13' -H 'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==' \
  'https://decabot.web.vespiridion.org/_event/?EIO=4&transport=websocket'
# 101 Switching Protocols. curl then times out holding the socket open — that IS the pass.
```

Both are asserted by `vps-infrastructure/tests/health-check.yml`.

**The only end-to-end proof is a message sent from a browser.** A 200 on `/` says the
static bundle is served; it says nothing about whether the page can reach its backend.
Same rule as the RUNBOOK's "prove it from a phone, not the build laptop".

## When it misbehaves

| Symptom | Cause |
|---|---|
| Page renders, nothing responds | The websocket never connected. The gate shows because `unlocked` fails closed — that is the intended tell, not the bug. |
| `manifest invalid` on push | Missing `oci-mediatypes=true`; Zot refuses Docker v2 with `415`. |
| A merge landed and nothing deployed | Either it touched only docs/, or the webhook did not fire. Check the job's build history before assuming the pipeline is broken; `FORCE_DEPLOY=true` re-ships the current `main`. |
| Build says "rolled back" | The health gate failed after deploy and the previous revision was restored. The host is serving the old commit, not a broken one — read the gate's output for which check failed. |
| `PermissionError: '.web/backend'` on boot | `.web/backend/stateful_pages.json` missing from the image. |
| Nothing on the VPS is reachable at all | Check `docker inspect traefik` for empty `Networks` — see that repo's `CLAUDE.md`. |
| `429` from Decathlon | Unchanged from the RUNBOOK: ~48-minute lockout, paced mode latches, keep going. |
