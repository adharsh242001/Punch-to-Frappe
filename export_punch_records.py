"""
Export Hikvision punch records to CSV.

Defaults to exporting records from 2026-01-01 through 2026-03-31 inclusive.

Examples
--------
    python export_punch_records.py
    python export_punch_records.py --start 2026-01-01 --end 2026-03-31
    python export_punch_records.py --output data\\q1_2026_punch_records.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from requests.auth import HTTPDigestAuth
import os


PAGE_SIZE = 50
ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env.server")


def normalize_id(emp_id: str) -> str:
    if not emp_id:
        return ""
    value = emp_id.strip().lower()
    if value.isdigit():
        return value.lstrip("0") or "0"
    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export Hikvision punch records to CSV.")
    parser.add_argument("--start", default="2026-01-01", help="Start date in YYYY-MM-DD format.")
    parser.add_argument("--end", default="2026-03-31", help="End date in YYYY-MM-DD format.")
    parser.add_argument(
        "--output",
        default=str(ROOT / "data" / "punch_records_2026-01-01_to_2026-03-31.csv"),
        help="Output CSV file path.",
    )
    return parser.parse_args()


def parse_day_start(value: str) -> datetime:
    return datetime.fromisoformat(f"{value}T00:00:00")


def parse_day_end(value: str) -> datetime:
    return datetime.fromisoformat(f"{value}T23:59:59")


def load_device_configs() -> list[dict[str, str]]:
    raw_devices = os.getenv("DEVICES", "").split(",")
    default_user = os.getenv("DEVICE_USER", "")
    default_pass = os.getenv("DEVICE_PASS", "")
    configs: list[dict[str, str]] = []

    for entry in raw_devices:
        parts = [part.strip() for part in entry.split(":") if part.strip()]
        if not parts:
            continue

        config = {"ip": parts[0]}
        if len(parts) >= 3:
            config["user"] = parts[1]
            config["pass"] = parts[2]
        else:
            config["user"] = default_user
            config["pass"] = default_pass

        configs.append(config)

    if not configs:
        raise EnvironmentError("No devices found. Set DEVICES in .env.")

    return configs


def load_device_names() -> dict[str, str]:
    raw = os.getenv("DEVICE_NAMES", "")
    result: dict[str, str] = {}
    for entry in raw.split(","):
        if ":" in entry:
            ip, name = entry.split(":", 1)
            result[ip.strip()] = name.strip()
    return result


def load_employee_map() -> dict[str, str]:
    map_path = Path(os.getenv("EMPLOYEE_MAP", str(ROOT / "employee_map.json")))
    if not map_path.exists():
        return {}
    with map_path.open(encoding="utf-8") as file_handle:
        raw_map = json.load(file_handle)
    return {normalize_id(key): value for key, value in raw_map.items()}


class HikvisionExporterClient:
    def __init__(self, ip: str, username: str, password: str) -> None:
        use_https = os.getenv("HIKVISION_USE_HTTPS", "true").lower() == "true"
        verify_ssl = os.getenv("HIKVISION_VERIFY_SSL", "false").lower() == "true"

        self.ip = ip
        self.verify_ssl = verify_ssl
        self.base_url = f"{'https' if use_https else 'http'}://{ip}"
        self.session = requests.Session()
        self.session.auth = HTTPDigestAuth(username, password)
        self.session.verify = verify_ssl

        if not verify_ssl:
            import urllib3  # noqa: PLC0415

            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def fetch_events(self, start_time: datetime, end_time: datetime) -> list[dict[str, Any]]:
        major = int(os.getenv("EVENT_MAJOR", "5"))
        minor = int(os.getenv("EVENT_MINOR", "75"))
        position = 0
        search_id = datetime.now().strftime("%Y%m%d%H%M%S%f")
        rows: list[dict[str, Any]] = []

        while True:
            payload = {
                "AcsEventCond": {
                    "searchID": search_id,
                    "searchResultPosition": position,
                    "maxResults": PAGE_SIZE,
                    "major": major,
                    "minor": minor,
                    "startTime": start_time.astimezone().isoformat(timespec="seconds"),
                    "endTime": end_time.astimezone().isoformat(timespec="seconds"),
                }
            }

            response = self._post_with_fallback(payload)
            events, total = self._parse_response(response)
            if not events:
                break

            for event in events:
                event["deviceIP"] = self.ip
                rows.append(event)

            position += len(events)
            if position >= total:
                break

        return rows

    def _post_with_fallback(self, payload: dict[str, Any]) -> requests.Response:
        url = f"{self.base_url}/ISAPI/AccessControl/AcsEvent?format=json"
        headers = {"Content-Type": "application/json"}
        try:
            response = self.session.post(url, json=payload, headers=headers, timeout=30)
            if response.status_code == 401:
                return self._post_with_curl(url, payload)
            response.raise_for_status()
            return response
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            alt_base = (
                f"http://{self.ip}" if self.base_url.startswith("https://") else f"https://{self.ip}"
            )
            alt_url = f"{alt_base}/ISAPI/AccessControl/AcsEvent?format=json"
            response = self.session.post(
                alt_url,
                json=payload,
                headers=headers,
                timeout=30,
            )
            if response.status_code == 401:
                self.base_url = alt_base
                return self._post_with_curl(alt_url, payload)
            response.raise_for_status()
            self.base_url = alt_base
            return response

    def _post_with_curl(self, url: str, payload: dict[str, Any]) -> requests.Response:
        curl_path = shutil.which("curl.exe") or shutil.which("curl")
        if not curl_path:
            response = requests.Response()
            response.status_code = 401
            response.url = url
            response._content = b"Authentication failed and curl is not available for fallback."
            raise requests.exceptions.HTTPError(
                "401 Client Error: Unauthorized and curl fallback not available",
                response=response,
            )

        username = self.session.auth.username  # type: ignore[attr-defined]
        password = self.session.auth.password  # type: ignore[attr-defined]
        command = [
            curl_path,
            "--silent",
            "--show-error",
            "--digest",
            "--user",
            f"{username}:{password}",
            "--request",
            "POST",
            "--url",
            url,
            "--header",
            "content-type: application/json",
            "--data",
            json.dumps(payload),
        ]
        if not self.verify_ssl and url.startswith("https://"):
            command.insert(1, "--insecure")

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            response = requests.Response()
            response.status_code = 500
            response.url = url
            response._content = result.stderr.encode("utf-8", errors="replace")
            raise requests.exceptions.HTTPError(
                f"curl fallback failed with exit code {result.returncode}",
                response=response,
            )

        response = requests.Response()
        response.status_code = 200
        response.url = url
        response.headers["Content-Type"] = "application/json"
        response._content = result.stdout.encode("utf-8", errors="replace")
        return response

    @staticmethod
    def _parse_response(response: requests.Response) -> tuple[list[dict[str, Any]], int]:
        content_type = response.headers.get("Content-Type", "")
        if "json" in content_type.lower():
            return HikvisionExporterClient._parse_json(response.json())
        return HikvisionExporterClient._parse_xml(response.text)

    @staticmethod
    def _parse_json(data: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
        result = data.get("AcsEvent", data)
        total = int(result.get("totalMatches", 0))
        info_list = result.get("InfoList", []) or []

        events: list[dict[str, Any]] = []
        for item in info_list:
            events.append(
                {
                    "employeeNoString": str(item.get("employeeNoString", item.get("cardNo", ""))),
                    "name": item.get("name", ""),
                    "time": item.get("time", ""),
                    "serialNo": str(item.get("serialNo", "")),
                }
            )

        return events, total

    @staticmethod
    def _parse_xml(xml_text: str) -> tuple[list[dict[str, Any]], int]:
        import xml.etree.ElementTree as ET  # noqa: PLC0415

        xml_text = xml_text.replace(' xmlns="', ' _xmlns="')
        root = ET.fromstring(xml_text)

        total_el = root.find("totalMatches")
        total = int(total_el.text) if total_el is not None and total_el.text else 0

        info_list = root.find("InfoList")
        if info_list is None:
            return [], total

        events: list[dict[str, Any]] = []
        for item in info_list.findall("AcsEventInfo"):
            events.append(
                {
                    "employeeNoString": (item.findtext("employeeNoString") or item.findtext("cardNo") or "").strip(),
                    "name": (item.findtext("name") or "").strip(),
                    "time": (item.findtext("time") or "").strip(),
                    "serialNo": (item.findtext("serialNo") or "").strip(),
                }
            )

        return events, total


def export_to_csv(
    start_time: datetime,
    end_time: datetime,
    output_path: Path,
) -> tuple[Path, int]:
    device_names = load_device_names()
    employee_map = load_employee_map()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "device_ip",
        "device_name",
        "employee_no",
        "mapped_employee_id",
        "employee_name",
        "event_time",
        "serial_no",
    ]

    total_rows = 0
    with output_path.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        for device in load_device_configs():
            client = HikvisionExporterClient(device["ip"], device["user"], device["pass"])
            events = client.fetch_events(start_time, end_time)
            for event in events:
                employee_no = str(event.get("employeeNoString", "")).strip()
                writer.writerow(
                    {
                        "device_ip": device["ip"],
                        "device_name": device_names.get(device["ip"], device["ip"]),
                        "employee_no": employee_no,
                        "mapped_employee_id": employee_map.get(normalize_id(employee_no), ""),
                        "employee_name": event.get("name", ""),
                        "event_time": event.get("time", ""),
                        "serial_no": str(event.get("serialNo", "")).strip(),
                    }
                )
                total_rows += 1

    return output_path, total_rows


def main() -> None:
    args = parse_args()
    start_time = parse_day_start(args.start)
    end_time = parse_day_end(args.end)
    if start_time > end_time:
        raise ValueError("Start date must be earlier than or equal to end date.")

    output_path, row_count = export_to_csv(start_time, end_time, Path(args.output))
    print(f"Exported {row_count} punch record(s) to {output_path}")


if __name__ == "__main__":
    main()
