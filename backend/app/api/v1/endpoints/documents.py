"""
API endpoint to fetch and extract legal document content from luatvietnam.vn.

This acts as a backend proxy to avoid CORS issues and to sanitize/clean
the HTML before rendering it on the frontend.
"""

import re
from urllib.parse import urlparse, urljoin
from functools import lru_cache

import httpx
from bs4 import BeautifulSoup
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app.api.deps.auth import get_current_user_id
from app.core.logger import logger

router = APIRouter()

ALLOWED_DOMAINS = ["luatvietnam.vn", "www.luatvietnam.vn"]
BASE_URL = "https://luatvietnam.vn"

_doc_cache: dict[str, dict] = {}
_DOC_CACHE_MAX = 64


class DocumentFetchRequest(BaseModel):
    url: str


class DocumentFetchResponse(BaseModel):
    html: str
    title: str


def _validate_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.hostname not in ALLOWED_DOMAINS:
        raise HTTPException(
            status_code=400,
            detail=f"Chỉ hỗ trợ tải văn bản từ luatvietnam.vn"
        )
    # Ensure https
    if not parsed.scheme:
        url = f"https://{url}"
    return url


def _clean_html(soup: BeautifulSoup) -> str:
    # Remove tooltip/tracking elements
    selectors_to_remove = [
        ".document-tip",
        ".tooltip-button",
        ".tooltip-content-1",
        ".btn-tip-r-more",
        "[data-role='customer-doc-item-follow-button']",
        "[data-role='customer-doc-item-note-button']",
        "script",
        "style",
        "iframe",
    ]
    for selector in selectors_to_remove:
        for el in soup.select(selector):
            el.decompose()

    # Fix relative URLs in <a> tags
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        if href.startswith("/"):
            a_tag["href"] = urljoin(BASE_URL, href)
        # Make all links open in new tab
        a_tag["target"] = "_blank"
        a_tag["rel"] = "noopener noreferrer"

    return str(soup)


def _extract_title(soup: BeautifulSoup) -> str:
    # Try to find the title in common patterns
    # Pattern 1: Bold centered text after the header table (e.g., "NGHỊ ĐỊNH")
    title_candidates = soup.select(".docitem-13 p b, .docitem-13 p strong")
    if title_candidates:
        parts = []
        for el in title_candidates:
            text = el.get_text(strip=True)
            if text:
                parts.append(text)
        if parts:
            title = " - ".join(parts[:2])  # Take first 2 parts max
            return title[:200]  # Limit length

    # Pattern 2: First bold text
    first_bold = soup.find("b")
    if first_bold:
        return first_bold.get_text(strip=True)[:200]

    return "Văn bản pháp luật"


@router.post("/fetch", response_model=DocumentFetchResponse)
async def fetch_document(
    request: DocumentFetchRequest,
    current_user_id: int = Depends(get_current_user_id),
):
    url = _validate_url(request.url)

    # Check cache
    if url in _doc_cache:
        logger.debug(f"📄 Document cache hit: {url}")
        return _doc_cache[url]

    logger.info(f"📄 Fetching legal document: {url}")

    try:
        async with httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
            }
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Không thể kết nối đến luatvietnam.vn (timeout)")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"luatvietnam.vn trả về lỗi: {e.response.status_code}")
    except Exception as e:
        logger.error(f"❌ Error fetching document: {e}")
        raise HTTPException(status_code=502, detail="Không thể tải văn bản từ luatvietnam.vn")

    # Parse HTML
    soup = BeautifulSoup(response.text, "html.parser")

    # Extract the document body
    doc_body = soup.select_one('div.the-document-body[data-role="content-body"]')
    if not doc_body:
        # Fallback: try without data-role
        doc_body = soup.select_one("div.the-document-body")

    if not doc_body:
        raise HTTPException(
            status_code=404,
            detail="Không tìm thấy nội dung văn bản trên trang này"
        )

    # Extract title before cleaning
    title = _extract_title(doc_body)

    # Clean HTML
    cleaned_html = _clean_html(doc_body)

    result = {"html": cleaned_html, "title": title}

    # Cache the result
    if len(_doc_cache) >= _DOC_CACHE_MAX:
        # Remove oldest entry (FIFO)
        oldest_key = next(iter(_doc_cache))
        del _doc_cache[oldest_key]
    _doc_cache[url] = result

    logger.info(f"✅ Document fetched successfully: {title[:80]}")
    return result
