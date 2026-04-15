from __future__ import annotations

from dataclasses import dataclass

from curl_cffi import requests as curl_requests


class FetchError(RuntimeError):
    """Raised when a vendor page cannot be fetched."""


@dataclass(slots=True)
class HttpResponse:
    url: str
    status_code: int
    text: str


class WebClient:
    def __init__(self) -> None:
        self.session = curl_requests.Session(
            headers={
                "Accept-Language": "en-US,en;q=0.9",
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/135.0.0.0 Safari/537.36"
                ),
            }
        )

    def get(self, url: str) -> HttpResponse:
        try:
            response = self.session.get(
                url,
                impersonate="chrome136",
                timeout=30,
                allow_redirects=True,
            )
        except Exception as exc:  # pragma: no cover - network transport errors are environment-specific.
            raise FetchError(f"Failed to fetch {url}: {exc}") from exc

        if response.status_code >= 400:
            raise FetchError(f"Failed to fetch {url}: HTTP {response.status_code}")

        return HttpResponse(
            url=str(response.url),
            status_code=response.status_code,
            text=response.text,
        )
