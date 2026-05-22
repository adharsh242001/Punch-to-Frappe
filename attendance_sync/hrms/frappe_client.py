"""
Frappe HRMS client.

Pushes Employee Checkin records via the Frappe REST API.
Uses token-based authentication (API_KEY:API_SECRET).
"""
import logging
import json
from typing import Any

import requests

logger = logging.getLogger(__name__)


class FrappeClient:
    """
    Thin wrapper around the Frappe REST API for Employee Checkin.

    Parameters
    ----------
    base_url:
        Root URL of the Frappe instance, e.g. "https://hrms.example.com".
    api_key / api_secret:
        Frappe API credentials.
    timeout:
        HTTP request timeout in seconds.
    """

    _ENDPOINT = "/api/resource/Employee Checkin"
    _EMPLOYEE_ENDPOINT = "/api/resource/Employee"
    _ATTENDANCE_ENDPOINT = "/api/resource/Attendance"
    _RESOURCE_PAGE_SIZE = 500
    _ATTENDANCE_FIELDS = [
        "name",
        "employee",
        "employee_name",
        "attendance_date",
        "status",
        "working_hours",
        "in_time",
        "out_time",
        "department",
        "company",
        "shift",
        "late_entry",
        "early_exit",
        "leave_type",
        "half_day_status",
    ]

    def __init__(
        self,
        base_url: str,
        api_key: str,
        api_secret: str,
        timeout: int = 15,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"token {api_key}:{api_secret}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        )

    # ── public interface ──────────────────────────────────────────────────────

    def get_employees(self, employee_ids: list[str]) -> dict[str, dict[str, Any]]:
        """Return Frappe Employee details keyed by employee document name."""
        unique_ids = sorted({str(employee_id).strip() for employee_id in employee_ids if str(employee_id).strip()})
        if not unique_ids:
            return {}

        fields = [
            "name",
            "employee_name",
            "first_name",
            "middle_name",
            "last_name",
            "department",
            "designation",
            "company",
            "branch",
            "status",
            "default_shift",
        ]
        employees: dict[str, dict[str, Any]] = {}
        for index in range(0, len(unique_ids), 100):
            batch = unique_ids[index:index + 100]
            params = {
                "fields": json.dumps(fields),
                "filters": json.dumps([["Employee", "name", "in", batch]]),
                "limit_page_length": len(batch),
            }
            try:
                resp = self._session.get(
                    f"{self._base_url}{self._EMPLOYEE_ENDPOINT}",
                    params=params,
                    timeout=self._timeout,
                )
                resp.raise_for_status()
            except requests.exceptions.HTTPError as exc:
                status = exc.response.status_code
                body = exc.response.text[:500]
                raise FrappeAPIError(
                    f"HTTP {status} from Frappe: {body}", status_code=status, body=body
                ) from exc
            except requests.exceptions.ConnectionError as exc:
                raise FrappeAPIError(f"Connection error: {exc}") from exc
            except requests.exceptions.Timeout as exc:
                raise FrappeAPIError("Request timed out") from exc

            try:
                data = resp.json().get("data") or []
            except ValueError:
                data = []
            for row in data:
                name = str(row.get("name") or "").strip()
                if name:
                    employees[name] = row
        return employees

    def list_attendance(
        self,
        *,
        date_from: str = "",
        date_to: str = "",
        employee: str = "",
    ) -> list[dict[str, Any]]:
        """Return submitted Frappe HRMS Attendance documents for a date range."""
        filters: list[list[Any]] = [["Attendance", "docstatus", "=", 1]]
        if date_from and date_to:
            filters.append(["Attendance", "attendance_date", "between", [date_from, date_to]])
        elif date_from:
            filters.append(["Attendance", "attendance_date", ">=", date_from])
        elif date_to:
            filters.append(["Attendance", "attendance_date", "<=", date_to])
        if employee:
            filters.append(["Attendance", "employee", "=", employee])

        return self._list_resource(
            self._ATTENDANCE_ENDPOINT,
            filters=filters,
            fields=self._ATTENDANCE_FIELDS,
            order_by="attendance_date desc, modified desc",
        )

    def _list_resource(
        self,
        endpoint: str,
        *,
        filters: list[list[Any]],
        fields: list[str],
        order_by: str,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        limit_start = 0
        max_rows = 10000

        while limit_start < max_rows:
            params = {
                "fields": json.dumps(fields),
                "filters": json.dumps(filters),
                "limit_page_length": self._RESOURCE_PAGE_SIZE,
                "limit_start": limit_start,
                "order_by": order_by,
            }
            try:
                resp = self._session.get(
                    f"{self._base_url}{endpoint}",
                    params=params,
                    timeout=self._timeout,
                )
                resp.raise_for_status()
            except requests.exceptions.HTTPError as exc:
                status = exc.response.status_code
                body = exc.response.text[:500]
                raise FrappeAPIError(
                    f"HTTP {status} from Frappe: {body}", status_code=status, body=body
                ) from exc
            except requests.exceptions.ConnectionError as exc:
                raise FrappeAPIError(f"Connection error: {exc}") from exc
            except requests.exceptions.Timeout as exc:
                raise FrappeAPIError("Request timed out") from exc

            try:
                batch = resp.json().get("data") or []
            except ValueError:
                batch = []
            rows.extend(batch)
            if len(batch) < self._RESOURCE_PAGE_SIZE:
                break
            limit_start += self._RESOURCE_PAGE_SIZE

        return rows

    def push_checkin(
        self,
        employee: str,
        event_time: str,
        device_id: str,
        log_type: str | None = None,
        latitude: str | float | None = None,
        longitude: str | float | None = None,
    ) -> dict[str, Any]:
        """
        Create an Employee Checkin record in Frappe HRMS.

        Parameters
        ----------
        employee:
            Frappe employee ID (e.g. "296").
        event_time:
            Formatted timestamp string "YYYY-MM-DD HH:MM:SS".
        device_id:
            Friendly name or IP of the source device.
        log_type:
            Optional Frappe log type, such as "IN" or "OUT".
        latitude / longitude:
            Geographical coordinates.

        Returns
        -------
        dict
            Parsed JSON response from Frappe.

        Raises
        ------
        FrappeAPIError
            If the API returns a non-2xx status.
        """
        payload = self.build_checkin_payload(
            employee=employee,
            event_time=event_time,
            device_id=device_id,
            log_type=log_type,
            latitude=latitude,
            longitude=longitude,
        )
        try:
            resp = self._session.post(
                f"{self._base_url}{self._ENDPOINT}",
                json=payload,
                timeout=self._timeout,
            )
            resp.raise_for_status()
        except requests.exceptions.HTTPError as exc:
            status = exc.response.status_code
            body = exc.response.text[:500]
            raise FrappeAPIError(
                f"HTTP {status} from Frappe: {body}", status_code=status, body=body
            ) from exc
        except requests.exceptions.ConnectionError as exc:
            raise FrappeAPIError(f"Connection error: {exc}") from exc
        except requests.exceptions.Timeout as exc:
            raise FrappeAPIError("Request timed out") from exc

        try:
            return resp.json()
        except ValueError:
            return {"raw": resp.text}

    def build_checkin_payload(
        self,
        *,
        employee: str,
        event_time: str,
        device_id: str,
        log_type: str | None = None,
        latitude: str | float | None = None,
        longitude: str | float | None = None,
    ) -> dict[str, Any]:
        """Build the exact Employee Checkin payload sent to Frappe."""
        payload = {
            "employee": employee,
            "time": event_time,
            "device_id": device_id,
            "skip_auto_attendance": 0,
        }
        if log_type:
            payload["log_type"] = log_type
        if latitude:
            payload["latitude"] = latitude
        if longitude:
            payload["longitude"] = longitude
        return payload

    def close(self) -> None:
        self._session.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class FrappeAPIError(Exception):
    """Raised when the Frappe API returns an error response."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        body: str = "",
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body

    @property
    def is_client_error(self) -> bool:
        """4xx errors are permanent; do not keep retrying."""
        return self.status_code is not None and 400 <= self.status_code < 500

    @property
    def is_duplicate(self) -> bool:
        """Return True only for actual duplicate Employee Checkin responses."""
        if self.status_code == 409:
            return True
        if self.status_code != 417:
            return False

        body = self.body.lower()
        return (
            "duplicateentryerror" in body
            or "duplicate entry" in body
            or "already exists" in body
        )
