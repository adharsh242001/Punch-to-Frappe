# Distributed Punch Sync Guide

This guide is for the setup where:

- PC A has access to one set of punch devices.
- PC B has access to another set of punch devices.
- One central server receives data from PC A and PC B.
- Only the central server pushes checkins to Frappe every 10 minutes.

## 1. Decide The Machine Roles

Use three roles:

| Machine | Runs | Needs access to |
| --- | --- | --- |
| Central server | `attendance_sync\server.py` | Frappe website, PC A, PC B |
| PC A | `attendance_sync\edge_agent.py` | PC A punch devices, central server |
| PC B | `attendance_sync\edge_agent.py` | PC B punch devices, central server |

The central server does not need direct access to every Hikvision device.

## 2. Copy The Project To All Machines

Copy this full project folder to:

- The central server
- PC A
- PC B

On each machine, install dependencies:

```powershell
pip install -r requirements.txt
```

If you use the included virtual environment, run commands with:

```powershell
venv\Scripts\python.exe
```

instead of:

```powershell
python
```

## 3. Create Shared Secrets

Make one long secret for PC A and one long secret for PC B.

Fast path:

```powershell
python generate_sync_keys.py
```

Or double-click:

```text
generate_sync_keys.bat
```

The output looks like this:

```env
Central server .env:
SERVER_NODE_KEYS=pc-a:secret_for_pc_a,pc-b:secret_for_pc_b

pc-a .env:
EDGE_NODE_ID=pc-a
EDGE_NODE_SECRET=secret_for_pc_a

pc-b .env:
EDGE_NODE_ID=pc-b
EDGE_NODE_SECRET=secret_for_pc_b
```

Put the `SERVER_NODE_KEYS` line only on the central server.

Put the matching `EDGE_NODE_ID` and `EDGE_NODE_SECRET` only on that edge PC.

Example:

```text
pc-a secret: change_this_to_a_long_random_secret_for_pc_a
pc-b secret: change_this_to_a_long_random_secret_for_pc_b
```

Use different secrets for PC A and PC B.

How the key check works:

- PC A signs each upload using `EDGE_NODE_ID=pc-a` and its `EDGE_NODE_SECRET`.
- PC B signs each upload using `EDGE_NODE_ID=pc-b` and its `EDGE_NODE_SECRET`.
- The central server checks the signature against `SERVER_NODE_KEYS`.
- If the node ID is unknown, the secret is wrong, the body was changed, or the timestamp is too old, the server returns `401 Unauthorized`.

## 4. Configure The Central Server

On the central server, create or edit `.env`.

### Option A: Ubuntu Server With Docker

Use this option for a real Ubuntu server.

Install Docker:

```bash
sudo apt update
sudo apt install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

Allow your user to run Docker:

```bash
sudo usermod -aG docker $USER
```

Log out and log back in after running that command.

Create the server env file:

```bash
cp examples/env.server.docker.example .env.server
```

Edit `.env.server`:

```bash
nano .env.server
```

Generate PC keys:

```bash
python3 generate_sync_keys.py
```

Put the generated `SERVER_NODE_KEYS=...` line into `.env.server`.

Create the data folder and give it to the same non-root user used inside the container:

```bash
mkdir -p data
sudo chown -R 10001:10001 data
```

Build and start:

```bash
docker compose up -d --build
```

Check status:

```bash
docker compose ps
docker compose logs -f punch-sync-server
```

Health check:

```bash
curl http://localhost:8080/health
```

Update after pulling new code:

```bash
docker compose up -d --build
```

Stop:

```bash
docker compose down
```

The container runs as UID/GID `10001:10001`, not root.

### Docker Image Build In GitHub Actions

The repository includes:

```text
.github/workflows/docker-image.yml
```

It matches the sample worker style:

- Builds on pushes to `main`.
- Builds on tags like `v1.0.0`.
- Uses Docker Buildx.
- Logs in to Docker Hub with repository secrets.
- Pushes a `linux/amd64` image.
- Publishes branch, tag, SHA, and `latest` tags.

Add these GitHub repository secrets before using it:

```text
DOCKERHUB_USERNAME
DOCKERHUB_TOKEN
```

The image name is currently:

```text
codeaceitsolutionsllp/punch-to-frappe
```

If you want a different Docker Hub image, change it in both:

```text
.github/workflows/docker-image.yml
docker-compose.yml
```

### Option B: Windows Or Direct Python

Fast path:

```powershell
Copy-Item examples\env.central-server.example .env
```

Example central server `.env`:

```env
HRMS_URL=https://your-frappe-site.example.com
HRMS_API_KEY=your_frappe_api_key
HRMS_API_SECRET=your_frappe_api_secret

EMPLOYEE_MAP=employee_map.json
STORE_PATH=data/events.db

SERVER_HOST=0.0.0.0
SERVER_PORT=8080
SERVER_NODE_KEYS=pc-a:change_this_to_a_long_random_secret_for_pc_a,pc-b:change_this_to_a_long_random_secret_for_pc_b

POLL_INTERVAL=600
DEDUP_WINDOW=30
DEFAULT_LOG_TYPE=IN
LOG_LEVEL=INFO
LOG_FILE=data/server.log
```

Important:

- `SERVER_NODE_KEYS` must contain both PC A and PC B.
- The secret for `pc-a` must match PC A's `EDGE_NODE_SECRET`.
- The secret for `pc-b` must match PC B's `EDGE_NODE_SECRET`.
- Keep `.env` private.

Start the server:

```powershell
python attendance_sync\server.py
```

Or double-click:

```text
run_central_server.bat
```

Check if it is alive from the central server:

```powershell
Invoke-RestMethod http://localhost:8080/health
```

Expected result:

```json
{
  "ok": true,
  "pending_events": 0
}
```

## 5. Configure PC A

On PC A, create or edit `.env`.

Use only the devices PC A can reach.

Fast path:

```powershell
Copy-Item examples\env.pc-a.example .env
```

Example PC A `.env`:

```env
DEVICES=10.10.10.166,10.10.10.128
DEVICE_USER=admin
DEVICE_PASS=your_device_password

SYNC_SERVER_URL=http://central-server-ip:8080
EDGE_NODE_ID=pc-a
EDGE_NODE_SECRET=change_this_to_a_long_random_secret_for_pc_a

POLL_INTERVAL=600
FIRST_RUN_LOOKBACK_HOURS=24
LOG_LEVEL=INFO
LOG_FILE=data/edge-agent.log
```

Replace:

- `central-server-ip` with the real IP address or hostname of the central server.
- `DEVICES` with PC A's actual device IPs.
- `DEVICE_PASS` with the real Hikvision password.

Start PC A:

```powershell
python attendance_sync\edge_agent.py
```

Or double-click:

```text
run_edge_agent.bat
```

## 6. Configure PC B

On PC B, create or edit `.env`.

Use only the devices PC B can reach.

Fast path:

```powershell
Copy-Item examples\env.pc-b.example .env
```

Example PC B `.env`:

```env
DEVICES=10.10.20.50,10.10.20.51
DEVICE_USER=admin
DEVICE_PASS=your_device_password

SYNC_SERVER_URL=http://central-server-ip:8080
EDGE_NODE_ID=pc-b
EDGE_NODE_SECRET=change_this_to_a_long_random_secret_for_pc_b

POLL_INTERVAL=600
FIRST_RUN_LOOKBACK_HOURS=24
LOG_LEVEL=INFO
LOG_FILE=data/edge-agent.log
```

Start PC B:

```powershell
python attendance_sync\edge_agent.py
```

Or double-click:

```text
run_edge_agent.bat
```

## 7. Test The Flow

Test in this order.

### Central Server Test

From PC A or PC B, run:

```powershell
Invoke-RestMethod http://central-server-ip:8080/health
```

If this fails, check:

- Central server is running.
- Windows Firewall allows inbound port `8080`.
- PC A and PC B can reach the central server IP.

### Edge Device Test

On PC A, run a CSV export for a small date:

```powershell
python export_punch_records.py --start 2026-05-01 --end 2026-05-01 --output data\pc_a_test.csv
```

On PC B, run:

```powershell
python export_punch_records.py --start 2026-05-01 --end 2026-05-01 --output data\pc_b_test.csv
```

If CSV export is empty, check:

- Device IPs
- Device username/password
- Device date/time
- `HIKVISION_USE_HTTPS`

### Full Sync Test

1. Start the central server.
2. Start PC A edge agent.
3. Start PC B edge agent.
4. Watch central server logs.
5. Confirm new `Employee Checkin` records appear in Frappe.

## 8. Run Full-Time

After testing, run each script using one of:

- Windows Task Scheduler
- PM2
- NSSM

Use these scripts:

| Machine | Script |
| --- | --- |
| Central server | `attendance_sync\server.py` |
| PC A | `attendance_sync\edge_agent.py` |
| PC B | `attendance_sync\edge_agent.py` |

More Windows service setup notes are in `service_setup.md`.

## 9. Safety Notes

- Use a private LAN, VPN, Tailscale, ZeroTier, or HTTPS if possible.
- The upload is signed, so the server rejects fake or modified requests.
- Plain HTTP does not encrypt punch data.
- Do not share `.env`.
- Do not delete `data/events.db` unless you intentionally want to reset sync memory.

## 10. What Happens If Something Fails

If PC A or PC B cannot reach the central server:

- The edge agent logs an error.
- It does not advance its polling window.
- On the next cycle, it tries the same time range again.
- The central server de-duplicates repeated uploads.

If Frappe is down:

- The central server keeps events in SQLite.
- Failed pushes go into the retry queue.
- The server retries later.

If the same punch is sent twice:

- Duplicate `serialNo` records are ignored.
- Punches inside `DEDUP_WINDOW` are skipped.

## Quick Start Summary

Central server:

```powershell
python attendance_sync\server.py
```

PC A:

```powershell
python attendance_sync\edge_agent.py
```

PC B:

```powershell
python attendance_sync\edge_agent.py
```

Default push interval:

```env
POLL_INTERVAL=600
```
