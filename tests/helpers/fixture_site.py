from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


FIXTURE_ROOT = Path(__file__).resolve().parent.parent / "fixtures" / "sites"


@dataclass
class FixtureResponse:
    url: str
    status_code: int
    text: str
    headers: dict[str, str]


class FixtureSession:
    def __init__(self, site_name: str):
        self.site_name = site_name
        self.site_root = FIXTURE_ROOT / site_name

    def get(self, url, headers=None, timeout=None, allow_redirects=True, params=None):
        parsed = urlparse(url)
        path = parsed.path or "/"
        if path == "/":
            filename = "homepage.html"
        else:
            filename = path.strip("/").replace("/", "__")
            if "." not in filename:
                filename += ".html"

        file_path = self.site_root / filename
        if not file_path.exists():
            return FixtureResponse(url=url, status_code=404, text="", headers={"Content-Type": "text/html"})

        content_type = "application/xml" if file_path.suffix == ".xml" else "text/html"
        return FixtureResponse(
            url=url,
            status_code=200,
            text=file_path.read_text(),
            headers={"Content-Type": content_type},
        )

