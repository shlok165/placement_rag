# Deploying on one small Linux VM

For a single institute: one VM with 2 vCPUs, 4 GB of RAM and 20 GB of disk is enough for tens of
thousands of postings (see [PERFORMANCE.md](PERFORMANCE.md)). These steps assume Ubuntu 24.04 and
a hostname such as `placements.example.edu` that you control.

Commands marked **checked locally** were run against the production compose file on a developer
machine. DNS, the public certificate and cron were not, because they need a public server.

## 1. Install Docker

```sh
sudo apt-get update && sudo apt-get install -y ca-certificates curl git
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"   # log out and back in afterwards
docker compose version            # needs v2.24 or newer
```

## 2. Point DNS at the VM

Create an `A` record (and `AAAA` for IPv6) from the hostname to the VM's public address. Open ports
80 and 443 in the firewall; nothing else needs to be public.

```sh
sudo ufw allow OpenSSH && sudo ufw allow 80,443/tcp && sudo ufw enable
dig +short placements.example.edu   # must print the VM's address before step 4
```

## 3. Get the code and set `.env`

```sh
git clone https://github.com/shlok165/placement_rag.git && cd placement_rag
cp .env.example .env
chmod 600 .env
```

Edit `.env`:

| Setting | Value |
|---|---|
| `SITE_ADDRESS` | the hostname, for example `placements.example.edu` |
| `POSTGRES_PASSWORD` | a long random string: `openssl rand -base64 32` |
| `ALLOWED_EMAIL_DOMAINS` | the institute's email domain |
| `DEV_EMAIL_DOMAINS` | empty |
| `LLM_MODE` | `mock` to start; `live` with `LLM_API_KEY` and `LLM_MODEL` when ready |

The production file turns off demo data, marks cookies secure and sets `PUBLIC_URL` from
`SITE_ADDRESS`. Keep the key in `.env` only; never in the repository.

## 4. Start with HTTPS (checked locally, with a local hostname)

```sh
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build --wait
```

Caddy asks Let's Encrypt for a certificate on first start; it needs DNS from step 2 and port 80
reachable. Certificates are kept in the `caddydata` volume and renewed by Caddy.

## 5. Create the first coordinator (checked locally)

```sh
docker compose exec backend python -m app.cli create-coordinator admin@example.edu "CAPS Admin"
```

It asks for a password (10 characters or more) without echoing it. Sign in and invite the rest of
the team from **Team**. Students register themselves with an address in `ALLOWED_EMAIL_DOMAINS`.

## 6. Nightly backup (script checked locally; cron not)

`scripts/backup.sh` writes a database dump and the uploaded files to `backups/<time>/` and checks
that the dump can be read.

```sh
crontab -e
# 02:30 every night; keep 14 days
30 2 * * * cd $HOME/placement_rag && sh scripts/backup.sh >> backups/backup.log 2>&1 && find backups -mindepth 1 -maxdepth 1 -type d -mtime +14 -exec rm -rf {} +
```

Copy `backups/` off the machine as well, for example with `rsync` to another host. A backup on the
same disk does not survive the disk.

## 7. Test a restore (checked locally)

A backup is only proven by restoring it. Do this once after setup and after each upgrade:

```sh
sh scripts/backup.sh
sh scripts/restore.sh backups/<the folder it printed>
curl -fsS https://placements.example.edu/readyz
```

The restore stops the app, replaces the database and files, and starts everything again.

## 8. Upgrades

```sh
sh scripts/backup.sh
git pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build --wait
```

Migrations run when the backend starts.

## Smoke test after every deploy

- [ ] `curl -fsS https://<host>/readyz` prints `{"status":"ready"}`
- [ ] The browser shows a valid certificate and no mixed-content warnings
- [ ] `curl -sI https://<host>/ | grep -i content-security-policy` shows the policy
- [ ] The coordinator can sign in and sees the dashboard
- [ ] Adding a posting by pasted text reaches **Live** within a minute
- [ ] A test student can register, search, open the posting and save it
- [ ] The copilot answers (in mock mode it says so)
- [ ] **Download .ics file** on Applications lists the saved posting's deadline
- [ ] `docker compose ps` shows every service healthy
- [ ] Last night's folder exists in `backups/` (from the second day)

## Repository page

The social preview image is `docs/img/social-preview.png`, rendered by `e2e/social-preview.mjs`.
GitHub's API cannot set it: upload it under **Settings > General > Social preview**.

