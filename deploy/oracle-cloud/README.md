# Oracle Cloud Always Free VM deployment

This deploys the Python MusicMaid bot and its built-in web server as one systemd service. It does not deploy the separate Next.js dashboard in `src/`.

## Free-tier caveats

Oracle offers Always Free compute, but signup requires a payment card for identity verification, and free VM capacity may be unavailable in some regions. Oracle can reclaim an Always Free compute instance if CPU, network, and (for A1 Arm instances) memory utilization all stay below 20% over a seven-day period. This is not a guaranteed production 24/7 host; a paid always-on VM is the reliable option.

Create an Ubuntu 24.04 VM in your tenancy's home region. The A1 Flex shape can use up to 2 OCPUs and 12 GB memory within the published Always Free allowance. If Oracle reports no host capacity, retry later or choose another availability domain in the home region.

## Network and domain setup

1. Assign the VM a public IPv4 address and create a DNS `A` record for a domain you control.
2. In the OCI network security list or network security group, allow inbound TCP `22` only from your own IP, and inbound TCP `80` and `443` for the website. Do not expose port `8080` publicly.
3. Allow outbound traffic, including UDP, so the bot can connect to Discord voice servers.
4. Install Caddy using its official Ubuntu instructions. Replace `musicmaid.example.com` in `deploy/oracle-cloud/Caddyfile` with your domain; Caddy will proxy HTTPS traffic to the local web server on port `8080`.

## Install the application

Connect to the VM over SSH, then run:

```sh
sudo apt update
sudo apt install -y git python3 python3-venv python3-dev build-essential ffmpeg libopus0 libopus-dev nodejs
sudo useradd --system --create-home --home-dir /opt/musicmaid --shell /usr/sbin/nologin musicmaid
sudo -u musicmaid git clone --branch main --single-branch https://github.com/kishorerai390/Rai-discord-bot.git /opt/musicmaid
sudo -u musicmaid python3 -m venv /opt/musicmaid/.venv
sudo -u musicmaid /opt/musicmaid/.venv/bin/pip install --upgrade pip
sudo -u musicmaid /opt/musicmaid/.venv/bin/pip install -r /opt/musicmaid/requirements.txt
sudo -u musicmaid mkdir -p /opt/musicmaid/data /opt/musicmaid/logs
```

Create a protected environment file for secrets and host-specific settings:

```sh
sudo install -d -o root -g musicmaid -m 0750 /etc/musicmaid
sudo install -o root -g musicmaid -m 0640 /dev/null /etc/musicmaid/musicmaid.env
sudoedit /etc/musicmaid/musicmaid.env
```

Set these values in `/etc/musicmaid/musicmaid.env` (replace every placeholder; never commit this file):

```dotenv
MUSIC_BOT_TOKEN=REPLACE_WITH_DISCORD_BOT_TOKEN
DISCORD_CLIENT_ID=REPLACE_WITH_DISCORD_APPLICATION_ID
DISCORD_CLIENT_SECRET=REPLACE_WITH_DISCORD_CLIENT_SECRET
SESSION_SECRET=REPLACE_WITH_A_LONG_RANDOM_SECRET
MUSIC_DATABASE_PATH=/opt/musicmaid/data/music.db
DATABASE_PATH=/opt/musicmaid/data/bot.db
PORT=8080
PUBLIC_BASE_URL=https://musicmaid.example.com
MUSICMAID_WEBSITE_URL=https://musicmaid.example.com
DISCORD_REDIRECT_URI=https://musicmaid.example.com/api/auth/callback
COMMAND_SYNC_MODE=global
LOG_LEVEL=INFO
```

`MUSICMAID_WEBSITE_URL` points the built-in health heartbeat at this deployment instead of the old Render URL. Configure the same redirect URI in the Discord Developer Portal under the OAuth2 application's redirect URLs.

Install and start the systemd service:

```sh
sudo cp /opt/musicmaid/deploy/oracle-cloud/musicmaid.service /etc/systemd/system/musicmaid.service
sudo systemctl daemon-reload
sudo systemctl enable --now musicmaid
sudo systemctl status musicmaid
sudo journalctl -u musicmaid -f
```

Copy the Caddy configuration to the VM, then configure and start it:

```sh
sudo cp /opt/musicmaid/deploy/oracle-cloud/Caddyfile /etc/caddy/Caddyfile
sudoedit /etc/caddy/Caddyfile
sudo systemctl enable --now caddy
sudo systemctl reload caddy
```

## Verify and update

- Open `https://musicmaid.example.com/api/health` and confirm the bot is healthy.
- In Discord, run `/247 status`, then `/247 enable` while in the desired voice channel.
- Check `sudo journalctl -u musicmaid -f` if the bot fails to connect or restart.
- For updates, run `sudo -u musicmaid git -C /opt/musicmaid pull --ff-only`, reinstall requirements if they changed, and run `sudo systemctl restart musicmaid`.

SQLite data and the 24/7 channel settings are stored under `/opt/musicmaid/data`. Back up this directory outside the VM; Always Free does not replace an independent backup.
