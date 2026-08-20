"""Download public PDF reports from the MEM investigation-report column.

The crawler starts at the Ministry of Emergency Management investigation report
column and follows same-site links under the column. It records every PDF link
found on listing or article pages and downloads each file once.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from html.parser import HTMLParser
import csv
import gzip
import hashlib
import json
import re
import time
from pathlib import Path
from typing import Iterable
from urllib.parse import urldefrag, urljoin, urlparse, unquote
from urllib.request import Request, urlopen


START_URL = "https://www.mem.gov.cn/gk/sgcc/tbzdsgdcbg/"
OUT_DIR = Path("data/raw/mem_reports")
USER_AGENT = "Mozilla/5.0 (compatible; HongCe research crawler; +https://github.com/ZKD-FDU/hongce)"


@dataclass
class PdfRecord:
    pdf_url: str
    source_url: str
    source_title: str
    link_text: str
    filename: str
    bytes: int
    sha256: str
    status: str


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self.title_parts: list[str] = []
        self._current_href: str | None = None
        self._current_text: list[str] = []
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "a":
            attrs_map = {k.lower(): v for k, v in attrs}
            href = attrs_map.get("href")
            if href:
                self._current_href = href
                self._current_text = []
        elif tag.lower() == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._current_href:
            text = " ".join("".join(self._current_text).split())
            self.links.append((self._current_href, text))
            self._current_href = None
            self._current_text = []
        elif tag.lower() == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._current_href:
            self._current_text.append(data)
        if self._in_title:
            self.title_parts.append(data)

    @property
    def title(self) -> str:
        title = " ".join("".join(self.title_parts).split())
        return title.replace("--中华人民共和国应急管理部", "").strip()


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pages_dir = OUT_DIR / "pages"
    pdfs_dir = OUT_DIR / "pdfs"
    pages_dir.mkdir(exist_ok=True)
    pdfs_dir.mkdir(exist_ok=True)

    seen_pages: set[str] = set()
    queue: list[str] = [START_URL]
    pdf_sources: dict[str, tuple[str, str, str]] = {}
    page_count = 0

    while queue:
        url = queue.pop(0)
        if url in seen_pages:
            continue
        seen_pages.add(url)
        try:
            body, final_url, content_type = fetch(url)
        except Exception as exc:  # noqa: BLE001
            print(f"WARN page fetch failed: {url} -> {exc}")
            continue
        if "pdf" in content_type.lower() or final_url.lower().endswith(".pdf"):
            pdf_sources.setdefault(final_url, (url, "", ""))
            continue

        html = decode_html(body)
        page_count += 1
        (pages_dir / f"page_{page_count:04d}.html").write_text(html, encoding="utf-8")
        parser = LinkParser()
        parser.feed(html)
        title = parser.title
        for href, text in parser.links:
            abs_url = normalize(urljoin(final_url, href))
            if not abs_url:
                continue
            if is_pdf_link(abs_url, text):
                pdf_sources.setdefault(abs_url, (final_url, title, text))
            elif should_follow(abs_url):
                if abs_url not in seen_pages and abs_url not in queue:
                    queue.append(abs_url)
        time.sleep(0.15)

    records: list[PdfRecord] = []
    for i, (pdf_url, source) in enumerate(sorted(pdf_sources.items()), 1):
        source_url, source_title, link_text = source
        filename = make_filename(i, pdf_url, source_title, link_text)
        path = pdfs_dir / filename
        status = "downloaded"
        try:
            if path.exists() and path.stat().st_size > 0:
                data = path.read_bytes()
                status = "exists"
            else:
                data, _, _ = fetch(pdf_url)
                path.write_bytes(data)
            digest = hashlib.sha256(data).hexdigest()
            size = len(data)
        except Exception as exc:  # noqa: BLE001
            print(f"WARN pdf download failed: {pdf_url} -> {exc}")
            digest = ""
            size = 0
            status = f"failed: {exc}"
        records.append(
            PdfRecord(
                pdf_url=pdf_url,
                source_url=source_url,
                source_title=source_title,
                link_text=link_text,
                filename=filename,
                bytes=size,
                sha256=digest,
                status=status,
            )
        )
        time.sleep(0.15)

    write_index(records)
    manifest = {
        "start_url": START_URL,
        "pages_seen": len(seen_pages),
        "pdf_links_found": len(pdf_sources),
        "pdfs_ok": sum(1 for r in records if r.bytes > 0),
        "output_dir": str(OUT_DIR),
    }
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


def fetch(url: str) -> tuple[bytes, str, str]:
    req = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/pdf,*/*",
            "Accept-Encoding": "gzip",
        },
    )
    with urlopen(req, timeout=30) as resp:
        raw = resp.read()
        if resp.headers.get("Content-Encoding", "").lower() == "gzip":
            raw = gzip.decompress(raw)
        return raw, resp.geturl(), resp.headers.get("Content-Type", "")


def decode_html(body: bytes) -> str:
    for enc in ("utf-8", "gb18030", "gbk"):
        try:
            return body.decode(enc)
        except UnicodeDecodeError:
            continue
    return body.decode("utf-8", "replace")


def normalize(url: str) -> str | None:
    url, _ = urldefrag(url)
    if not url or url.startswith(("javascript:", "mailto:", "#")):
        return None
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return None
    return url


def should_follow(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.netloc in {"xxgk.mem.gov.cn"}:
        return parsed.path.startswith("/ezweb/ctrl/news/")
    if parsed.netloc not in {"www.mem.gov.cn", "mem.gov.cn"}:
        return False
    path = parsed.path
    return path.startswith("/gk/sgcc/tbzdsgdcbg/") or path.startswith("/gk/zfxxgkpt/fdzdgknr/")


def is_pdf_link(url: str, text: str = "") -> bool:
    path = urlparse(url).path.lower()
    return (
        path.endswith(".pdf")
        or text.strip().lower().endswith(".pdf")
        or (urlparse(url).netloc == "xxgk.mem.gov.cn" and "/ezweb/ctrl/news/download" in path)
    )


def make_filename(i: int, pdf_url: str, source_title: str, link_text: str) -> str:
    raw = clean_name(link_text) if link_text.strip().lower().endswith(".pdf") else ""
    raw = raw or unquote(Path(urlparse(pdf_url).path).name) or f"report_{i:04d}.pdf"
    if not raw.lower().endswith(".pdf"):
        raw = f"{raw}.pdf"
    stem = Path(raw).stem
    hint = source_title or link_text or stem
    hint = clean_name(hint)[:90].strip("_")
    suffix = hashlib.sha1(pdf_url.encode("utf-8")).hexdigest()[:8]
    return f"{i:04d}_{hint}_{suffix}.pdf" if hint else f"{i:04d}_{stem}_{suffix}.pdf"


def clean_name(value: str) -> str:
    value = re.sub(r"\s+", "_", value.strip())
    value = re.sub(r"[\\\\/:*?\"<>|]+", "_", value)
    value = re.sub(r"_+", "_", value)
    return value.strip("._")


def write_index(records: Iterable[PdfRecord]) -> None:
    rows = [asdict(r) for r in records]
    (OUT_DIR / "index.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    with (OUT_DIR / "index.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(PdfRecord.__annotations__))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    raise SystemExit(main())
