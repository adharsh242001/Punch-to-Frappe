"""
Frappe HRMS client.

Pushes Employee Checkin records via the Frappe REST API.
Uses token-based authentication (API_KEY:API_SECRET).
"""
import logging
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
