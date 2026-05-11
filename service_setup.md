# Running Attendance Sync Service Full-Time on Windows

To ensure the service runs continuously in the background and restarts automatically if the computer reboots, you have three main options.

## Option 1: Windows Task Scheduler (Built-in, Easiest)

This uses the tools already on your computer to start the script when you log in.

1.  **Create a Startup Script**:
    Create a file named `run_sync.bat` in your project folder (`d:\Private\hrms\Punch_to Frappe`) with this content:
    ```batch
    @echo off
    cd /d "d:\Private\hrms\Punch_to Frappe"
    python attendance_sync\main.py
    pause
    ```
2.  **Open Task Scheduler**:
    *   Press `Win + R`, type `taskschd.msc`, and hit Enter.
3.  **Create a New Task**:
    *   Click **Create Task** (not Basic Task).
    *   **General**: Give it a name like "Attendance Sync". Check "Run whether user is logged on or not" and "Run with highest privileges".
    *   **Triggers**: New -> Begin the task: "At startup".
    *   **Actions**: New -> Start a program. 
        *   Program/script: `d:\Private\hrms\Punch_to Frappe\run_sync.bat`
    *   **Settings**: Ensure "If the task fails, restart every: 1 minute" is checked.
4.  **Save**: It will ask for your Windows password.

---

## Option 2: PM2 (Recommended for Monitoring)

PM2 is a professional process manager. It’s great because it keeps logs and automatically restarts the script if it crashes.

1.  **Install Node.js**: Download and install from [nodejs.org](https://nodejs.org/).
2.  **Install PM2**:
    Open PowerShell and run:
    ```powershell
    npm install -g pm2
    npm install -g pm2-windows-startup
    ```
3.  **Start the Service**:
    ```powershell
    cd "d:\Private\hrms\Punch_to Frappe"
    pm2 start attendance_sync\main.py --name "attendance-sync"
    ```
4.  **Save for Reboot**:
    ```powershell
    pm2 save
    pm2-startup install
    ```
5.  **Check Status**:
    *   To see it running: `pm2 status`
    *   To see logs: `pm2 logs attendance-sync`

---

## Option 3: NSSM (Runs as a Native Windows Service)

NSSM (Non-Sucking Service Manager) makes your script look like a real Windows Service (like Windows Update).

1.  **Download NSSM**: Get it from [nssm.cc](https://nssm.cc/download).
2.  **Install**:
    Open PowerShell as Admin and run:
    ```powershell
    .\nssm.exe install AttendanceSync
    ```
3.  **Configuration Window**:
    *   **Path**: Path to your `python.exe` (e.g., `C:\Python311\python.exe`).
    *   **Startup Directory**: `d:\Private\hrms\Punch_to Frappe`.
    *   **Arguments**: `attendance_sync\main.py`.
4.  **Done**: Go to **Services.msc**, find "AttendanceSync", and click **Start**.

---

### Important: Virtual Environments
If you are using a Python Virtual Environment (`venv`), make sure you point to the `python.exe` **inside** that virtual environment folder (e.g., `d:\Private\hrms\Punch_to Frappe\venv\Scripts\python.exe`) instead of the global one.

---

## Distributed Setup Commands

For the central server in the PC A / PC B topology, use this script instead of `attendance_sync\main.py`:

```text
attendance_sync\server.py
```

For each edge PC, use:

```text
attendance_sync\edge_agent.py
```

The same Task Scheduler, PM2, or NSSM steps apply; only the script name changes.
