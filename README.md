# Punch-to-Frappe

A production-ready attendance synchronization service that continuously polls Hikvision biometric devices and automatically syncs attendance records to Frappe HRMS.

## Overview

**Punch-to-Frappe** bridges the gap between physical access-control systems and HR management systems. It automates the collection of attendance data from Hikvision devices and pushes them to Frappe HRMS, eliminating manual data entry and ensuring real-time attendance tracking.

### Key Features

- **Continuous Device Polling**: Automatically fetches attendance events from multiple Hikvision devices at configurable intervals
- **Intelligent Deduplication**: Prevents duplicate entries within a configurable time window (default: 30 seconds)
- **Employee Mapping**: Maps device employee IDs to Frappe employee records via a JSON mapping file
- **Automatic Retries**: Implements exponential backoff retry logic for failed API requests
- **Graceful Shutdown**: Handles SIGINT/SIGTERM signals for clean service termination
- **Flexible Logging**: Supports both console and file-based logging with configurable verbosity
- **Event Persistence**: Stores events locally before pushing to HRMS for reliability
- **Timezone Support**: Preserves device local timezone for accurate working hour records

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Attendance Sync Service                   │
└─────────────────────────────────────────────────────────────┘
         │                      │                    │
         ▼                      ▼                    ▼
    ┌─────────┐          ┌──────────┐         ┌────────────┐
    │Hikvision│          │EventStore│         │   Config   │
    │ Devices │          │  (Local) │         │(Env Vars)  │
    └─────────┘          └──────────┘         └────────────┘
         │                      │                    │
         └──────────────────────┼────────────────────┘
                                │
                         ┌──────▼──────┐
                         │EventProcessor│
                         │ (Deduplicate,│
                         │  Map IDs)    │
                         └──────┬───────┘
                                │
                         ┌──────▼───────┐
                         │ Frappe HRMS  │
                         │   (API)      │
                         └──────────────┘
```

## Project Structure

```
attendance_sync/
├── main.py                    # Service entry point with poll loop
├── config/
│   ├── __init__.py
│   └── settings.py            # Environment configuration loader
├── devices/
│   ├── __init__.py
│   └── hikvision_client.py    # Hikvision device ISAPI client
├── hrms/
│   ├── __init__.py
│   └── frappe_client.py       # Frappe HRMS REST API client
├── processors/
│   ├── __init__.py
│   └── event_processor.py     # Event processing & deduplication
└── storage/
    ├── __init__.py
    └── event_store.py         # Local event persistence layer
```

## Requirements

- **Python**: 3.7+ (for f-strings and `datetime.fromisoformat`)
- **Dependencies**:
  - `requests>=2.31.0` - HTTP client for device and API communication
  - `python-dotenv>=1.0.0` - Environment configuration management

## Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/adharshachu/Punch-to-Frappe.git
   cd Punch-to-Frappe
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Create `.env` file** in the project root:
   ```bash
   cp .env.example .env
   ```

4. **Configure environment variables** (see Configuration section below)

5. **Create employee mapping** (see Employee Mapping section below)

## Configuration

All configuration is managed via environment variables in the `.env` file:

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `DEVICES` | Comma-separated list of device IPs and credentials | `10.10.10.131:admin:pass123,10.10.10.132` |
| `HRMS_URL` | Frappe HRMS instance URL | `https://hrms.example.com` |
| `HRMS_API_KEY` | Frappe API key | `your-api-key` |
| `HRMS_API_SECRET` | Frappe API secret | `your-api-secret` |

### Optional Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DEVICE_USER` | (none) | Global device username (overridden by per-device config) |
| `DEVICE_PASS` | (none) | Global device password (overridden by per-device config) |
| `HIKVISION_USE_HTTPS` | `true` | Use HTTPS for device communication |
| `HIKVISION_VERIFY_SSL` | `false` | Verify SSL certificates (useful for self-signed certs) |
| `DEVICE_NAMES` | (none) | Friendly names mapping (e.g., `10.10.10.131:GATE-01`) |
| `POLL_INTERVAL` | `600` | Seconds between polling cycles |
| `DEDUP_WINDOW` | `30` | Seconds for duplicate detection window |
| `FIRST_RUN_LOOKBACK_HOURS` | `24` | Hours to look back on first run |
| `EVENT_MAJOR` | `5` | Hikvision event major type (5 = access control) |
| `EVENT_MINOR` | `75` | Hikvision event minor type (75 = face recognition) |
| `DEFAULT_LOG_TYPE` | `IN` | Default check-in type (`IN` or `OUT`) |
| `LATITUDE` | (none) | Default latitude for geolocation tagging |
| `LONGITUDE` | (none) | Default longitude for geolocation tagging |
| `EMPLOYEE_MAP` | `employee_map.json` | Path to employee ID mapping file |
| `STORE_PATH` | `data/events.db` | Path to local event store |
| `RETRY_MAX_ATTEMPTS` | `5` | Maximum retry attempts for failed API calls |
| `RETRY_BACKOFF_BASE` | `2.0` | Exponential backoff base in seconds |
| `LOG_LEVEL` | `INFO` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `LOG_FILE` | (none) | Optional log file path (stdout if not set) |

### Device Configuration Examples

**Single device with default credentials**:
```
DEVICES=10.10.10.131
DEVICE_USER=admin
DEVICE_PASS=password123
```

**Multiple devices with mixed credentials**:
```
DEVICES=10.10.10.131:admin:pass1,10.10.10.132,10.10.10.133:root:pass3
DEVICE_USER=admin
DEVICE_PASS=pass2
```

## Employee Mapping

Create an `employee_map.json` file to map device employee IDs to Frappe employee IDs:

```json
{
  "0001": "EMP-001",
  "0002": "EMP-002",
  "1234": "john.doe",
  "prefix_1001": "MGR-001"
}
```

The mapping supports:
- Numeric IDs (with optional leading zeros)
- Alphanumeric prefixed IDs
- Case-insensitive matching (keys are normalized to lowercase)

## Usage

### Start the Service

```bash
python attendance_sync/main.py
```

The service will:
1. Load configuration from `.env` and employee mapping
2. Set up logging to console and/or file
3. Register graceful shutdown handlers (SIGINT, SIGTERM)
4. Enter the polling loop:
   - Query each device for events since the last cycle
   - Process and deduplicate events
   - Push to Frappe HRMS
   - Sleep for `POLL_INTERVAL` seconds
5. On shutdown signal: Complete current cycle and exit cleanly

### Running as a System Service

#### Windows Task Scheduler (Recommended)

1. Create `run_sync.bat`:
   ```batch
   @echo off
   cd /d "d:\Private\hrms\Punch_to_Frappe"
   python attendance_sync\main.py
   pause
   ```

2. Open Task Scheduler (`Win + R` → `taskschd.msc`)
3. Create New Task:
   - **General**: Enable "Run whether user is logged on or not"
   - **Triggers**: Set to "At startup"
   - **Actions**: Run `run_sync.bat`
   - **Settings**: Enable auto-restart on failure

#### PM2 (Professional Process Manager)

```bash
# Install PM2
npm install -g pm2

# Start service
pm2 start attendance_sync/main.py --name "attendance-sync"

# Save for reboot
pm2 save
pm2-startup
```

#### NSSM (Windows Native Service)

See `service_setup.md` for detailed instructions.

## Logging

Logs follow this format:
```
2026-04-07 14:25:30  INFO     root             === Attendance Sync Service starting ===
2026-04-07 14:25:30  INFO     root             Devices: 10.10.10.131 | Poll interval: 600s | Dedup window: 30s
2026-04-07 14:25:31  DEBUG    devices          [10.10.10.131] Fetched 3 event(s) in this cycle.
```

### Log Levels

- **DEBUG**: Detailed operation info (event counts, processing steps)
- **INFO**: High-level service status and configuration
- **WARNING**: Issues that don't stop execution (malformed timestamps)
- **ERROR**: Failures requiring investigation (device connection errors, API failures)

## How It Works

### Poll Cycle

1. **Fetch Events**: Query each device for events in time window `[last_poll_time, now]`
2. **Parse Events**: Convert device timestamps (ISO-8601) to UTC
3. **Process**:
   - Map device employee IDs to Frappe employee IDs
   - Check deduplication window (ignore duplicate serial numbers within 30 seconds)
   - Format timestamp for Frappe format (`YYYY-MM-DD HH:MM:SS`)
4. **Push to HRMS**: Call Frappe API to create Employee Checkin records
5. **Retry on Failure**: Exponential backoff (2^attempt * backoff_base seconds)
6. **Store Locally**: Persist events for audit trail and recovery

### Deduplication

Events are uniquely identified by `(serial_number, time_window)`. If the same serial number appears twice within 30 seconds, the second occurrence is ignored.

### Retry Logic

Failed API calls use exponential backoff:
- Attempt 1: Immediate
- Attempt 2: 2 seconds
- Attempt 3: 4 seconds
- Attempt 4: 8 seconds
- Attempt 5: 16 seconds

After 5 failed attempts, the event is logged and dropped.

## Troubleshooting

### Service Won't Start

1. **Check environment variables**: Ensure all required vars are set in `.env`
2. **Verify employee mapping**: Confirm `employee_map.json` exists and is valid JSON
3. **Test device connectivity**: 
   ```bash
   python -c "from devices.hikvision_client import HikvisionClient; HikvisionClient('10.10.10.131', 'admin', 'pass')"
   ```
4. **Test Frappe connectivity**:
   ```bash
   curl -H "Authorization: token KEY:SECRET" https://hrms.example.com/api/resource/Employee
   ```

### Events Not Syncing

1. **Check logs**: Enable `LOG_LEVEL=DEBUG` for detailed output
2. **Verify employee mapping**: Ensure device IDs in mapping match actual device IDs
3. **Check Frappe permissions**: API user must have write access to Employee Checkin doctype
4. **Verify timestamps**: Ensure device time is synchronized

### High CPU/Memory Usage

1. Reduce `POLL_INTERVAL` (currently defaults to 600s)
2. Check device logs for event storms
3. Review `DEDUP_WINDOW` settings

## API Reference

### Hikvision ISAPI

- **Endpoint**: `POST /ISAPI/AccessControl/AcsEvent`
- **Auth**: HTTP Digest
- **Body**: XML or JSON (AcsEventCond format)
- **Response**: Paginated event records with timestamps, device IDs, serial numbers

### Frappe REST API

- **Endpoint**: `POST /api/resource/Employee Checkin`
- **Auth**: Token-based (`Authorization: token KEY:SECRET`)
- **Payload**:
  ```json
  {
    "doctype": "Employee Checkin",
    "employee": "EMP-001",
    "log_type": "IN",
    "time": "2026-04-07 14:25:30",
    "device_id": "10.10.10.131",
    "latitude": "12.9716",
    "longitude": "77.5946"
  }
  ```

## Development

### Testing

```bash
# Install dev dependencies
pip install -r requirements-dev.txt

# Run tests
python -m pytest tests/
```

### Code Structure

- **Dependency Injection**: Each component receives dependencies via constructor
- **Type Hints**: Full type annotations for IDE support and static checking
- **Logging**: Structured logging with `logging` module
- **Error Handling**: Graceful degradation with retry logic

## License

[Add your license here]

## Support

For issues, feature requests, or contributions, please visit the [GitHub repository](https://github.com/adharshachu/Punch-to-Frappe).

## Changelog

### v1.0.0 (2026-04-07)
- Initial release with Hikvision polling and Frappe HRMS integration
- Deduplication, retry logic, and employee mapping support
- Graceful shutdown handling
