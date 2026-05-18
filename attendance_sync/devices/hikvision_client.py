"""
Hikvision device client.

Fetches access-control events via the ISAPI REST interface using
HTTP Digest authentication (the only auth method the camera supports).

API reference:
  POST /ISAPI/AccessControl/AcsEvent
  Body: AcsEventCond XML (or JSON, depending on firmware)
"""
import logging
from datetime import datetime, timezone
from typing import Any, Generator

import requests
from requests.auth import HTTPDigestAuth
from config import settings

logger = logging.getLogger(__name__)

# How many records to request per page from the device
_PAGE_SIZE = 50
_MAX_AUTH_RETRIES = 1


class HikvisionClient:
    """
    Communicates with a single Hikvision access-control device.

    Parameters
    ----------
    device_ip:
        IP address of the device (e.g. "10.10.10.131").
    username / password:
        Device credentials (HTTP Digest).
    major / minor:
        Event type filter (5 / 75 for face-recognition check-in).
    timeout:
        HTTP request timeout in seconds.
    """

    def __init__(
        self,
        device_ip: str,
        username: str,
        password: str,
        major: int = 5,
        minor: int = 75,
        timeout: int = 10,
    ) -> None:
        self.device_ip = device_ip
        self.major = major
        self.minor = minor
        self.timeout = timeout

        protocol = "https" if settings.HIKVISION_USE_HTTPS else "http"
        self._base_url = f"{protocol}://{device_ip}"
        self._username = username
        self._password = password
        self._auth = HTTPDigestAuth(username, password)
        self._session = self._new_session()
        
        # Suppress insecure request warnings if SSL verification is disabled
        if not settings.HIKVISION_VERIFY_SSL:
            import urllib3  # noqa: PLC0415
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    # ── public interface ──────────────────────────────────────────────────────

    def fetch_events(
        self,
        start_time: datetime,
        end_time: datetime,
    ) -> Generator[dict[str, Any], None, None]:
        """
        Yield all matching events between *start_time* and *end_time*.

        Each yielded dict contains the raw fields returned by the device plus
        an injected ``deviceIP`` key.
        """
        search_id = self._make_search_id()
        position = 0

        while True:
            # Match the working curl's JSON structure
            payload = {
                "AcsEventCond": {
                    "searchID": search_id,
                    "searchResultPosition": position,
                    "maxResults": _PAGE_SIZE,
                    "major": self.major,
                    "minor": self.minor,
                    "startTime": self._fmt_time(start_time),
                    "endTime": self._fmt_time(end_time),
                }
            }

            try:
                # Add ?format=json to the URL as seen in the working curl
                resp = self._post_with_auth_retry(
                    f"{self._base_url}/ISAPI/AccessControl/AcsEvent?format=json",
                    payload,
                )
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
                # If HTTPS failed, try falling back to HTTP (or vice versa)
                alt_protocol = "http" if self._base_url.startswith("https") else "https"
                alt_url = f"{alt_protocol}://{self.device_ip}"
                
                logger.warning(
                    "[%s] %s failing – trying fallback to %s…",
                    self.device_ip,
                    self._base_url.split(":")[0].upper(),
                    alt_protocol.upper(),
                )
                
                try:
                    resp = self._post_with_auth_retry(
                        f"{alt_url}/ISAPI/AccessControl/AcsEvent?format=json",
                        payload,
                    )
                    # Success on fallback! Update base_url for future polls this session
                    self._base_url = alt_url
                except Exception as fallback_exc:
                    logger.error("[%s] Connection failed on both protocols: %s", self.device_ip, fallback_exc)
                    return
            except requests.exceptions.HTTPError as exc:
                logger.error(
                    "[%s] HTTP error %s from device. Check device credentials/session. Response: %s",
                    self.device_ip,
                    exc.response.status_code,
                    " ".join(exc.response.text.split())[:240],
                )
                return

            events, total = self._parse_response(resp)

            if not events:
                logger.debug(
                    "[%s] No events at position %d (total=%d)",
                    self.device_ip,
                    position,
                    total,
                )
                return

            for event in events:
                event["deviceIP"] = self.device_ip
                yield event

            position += len(events)
            if position >= total:
                break

    # ── helpers ───────────────────────────────────────────────────────────────

    def _new_session(self) -> requests.Session:
        session = requests.Session()
        session.auth = HTTPDigestAuth(self._username, self._password)
        session.verify = settings.HIKVISION_VERIFY_SSL
        return session

    def _reset_session(self) -> None:
        self._session.close()
        self._session = self._new_session()

    def _post_with_auth_retry(self, url: str, payload: dict[str, Any]) -> requests.Response:
        last_response: requests.Response | None = None
        for attempt in range(_MAX_AUTH_RETRIES + 1):
            resp = self._session.post(url, json=payload, timeout=self.timeout)
            last_response = resp
            if resp.status_code != 401:
                if attempt:
                    logger.debug("[%s] Digest auth retry succeeded.", self.device_ip)
                resp.raise_for_status()
                return resp

            if attempt < _MAX_AUTH_RETRIES:
                logger.debug("[%s] Refreshing digest auth session after 401.", self.device_ip)
                self._reset_session()

        assert last_response is not None
        logger.warning("[%s] Device still returned 401 after digest auth retry.", self.device_ip)
        last_response.raise_for_status()
        return last_response

    @staticmethod
    def _fmt_time(dt: datetime) -> str:
        """Format datetime as ISO-8601 with UTC offset for the device query."""
        # Convert to local-aware ISO string; device expects e.g. 2026-03-04T00:00:00+05:30
        return dt.astimezone().isoformat(timespec="seconds")

    @staticmethod
    def _make_search_id() -> str:
        return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")

    def _parse_response(
        self, resp: requests.Response
    ) -> tuple[list[dict[str, Any]], int]:
        """
        Parse the ISAPI response.

        The device may return XML or JSON depending on firmware version;
        we try JSON first (most firmware ≥ V2), fall back to XML.
        """
        content_type = resp.headers.get("Content-Type", "")

        if "json" in content_type:
            return self._parse_json(resp.json())

        # Default: XML
        return self._parse_xml(resp.text)

    @staticmethod
    def _parse_json(data: dict) -> tuple[list[dict[str, Any]], int]:
        """Handle JSON-format ISAPI response."""
        result = data.get("AcsEvent", data)
        total = int(result.get("totalMatches", 0))
        info_list = result.get("InfoList", []) or []

        events: list[dict[str, Any]] = []
        for item in info_list:
            event = {
                "employeeNoString": str(item.get("employeeNoString", item.get("cardNo", ""))),
                "name": item.get("name", ""),
                "time": item.get("time", ""),
                "serialNo": str(item.get("serialNo", "")),
            }
            events.append(event)

        return events, total

    @staticmethod
    def _parse_xml(xml_text: str) -> tuple[list[dict[str, Any]], int]:
        """Handle XML-format ISAPI response."""
        # Use stdlib xml.etree — no external dependency needed
        import xml.etree.ElementTree as ET  # noqa: PLC0415

        # Hikvision XML may include namespace prefixes; strip them for simplicity
        xml_text = xml_text.replace(' xmlns="', ' _xmlns="')  # neutralise default NS
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            logger.error("Failed to parse device XML response: %s", exc)
            return [], 0

        def _text(node, tag: str, default: str = "") -> str:
            el = node.find(tag)
            return el.text.strip() if el is not None and el.text else default

        total_el = root.find("totalMatches")
        total = int(total_el.text) if total_el is not None and total_el.text else 0

        events: list[dict[str, Any]] = []
        info_list = root.find("InfoList")
        if info_list is None:
            return events, total

        for item in info_list.findall("AcsEventInfo"):
            event = {
                "employeeNoString": _text(item, "employeeNoString") or _text(item, "cardNo"),
                "name": _text(item, "name"),
                "time": _text(item, "time"),
                "serialNo": _text(item, "serialNo"),
            }
            events.append(event)

        return events, total

    def close(self) -> None:
        self._session.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
