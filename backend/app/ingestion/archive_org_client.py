"""
Internet Archive client — the source for real Indian Standards, both for
bulk acquisition and for the query-time "nothing matched locally" fallback.

This is a deliberately different situation from BIS's own sales portal
(see app/ingestion/bulk_ingest_cli.py's docstring): Internet Archive's
advancedsearch.php and metadata/download endpoints are public, documented,
unauthenticated APIs with no captcha or login gate — using them is not
circumventing any access control, it is using a service exactly as it is
designed to be used. The ~22,700 Indian Standards indexed here (identifiers
under "gov.in.is.*" and "gov.law.is.*") were uploaded by Public Resource
(public.resource.org) specifically to establish free public access to
Indian technical standards under the Right to Information Act — the same
"Disclosure to Promote the Right To Information" notice already seen on
every real BIS PDF this project has tested against traces back to this
same public-access effort.

No API key, no auth, no rate-limit workaround: DEFAULT_TIMEOUT_SECONDS and
a plain sequential request pattern are deliberately conservative (see
bulk_download_matching() docstring) rather than optimized for throughput,
out of respect for a free, donation-funded nonprofit service.
"""

import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger("bis_sahayak")

SEARCH_URL = "https://archive.org/advancedsearch.php"
METADATA_URL_TEMPLATE = "https://archive.org/metadata/{identifier}"
DOWNLOAD_URL_TEMPLATE = "https://archive.org/download/{identifier}/{filename}"

# Only these two identifier prefixes are real Indian Standards uploads (see
# module docstring) — the query always constrains to them so an unrelated
# archive.org item never gets treated as a BIS standard.
IDENTIFIER_PREFIXES = ("gov.in.is.", "gov.law.is.")

DEFAULT_TIMEOUT_SECONDS = 30.0


class ArchiveOrgError(Exception):
    pass


@dataclass
class ArchiveOrgResult:
    identifier: str
    title: str


def _run_query(title_clause: str, max_results: int) -> list[ArchiveOrgResult]:
    prefix_clause = " OR ".join(f"identifier:{prefix}*" for prefix in IDENTIFIER_PREFIXES)
    query = f"({prefix_clause}) AND {title_clause}"
    params = {
        "q": query,
        "fl[]": ["identifier", "title"],
        "rows": str(max_results),
        "output": "json",
    }
    try:
        response = httpx.get(SEARCH_URL, params=params, timeout=DEFAULT_TIMEOUT_SECONDS)
        response.raise_for_status()
        docs = response.json().get("response", {}).get("docs", [])
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Internet Archive search failed for query %r: %s", query, exc)
        return []

    return [ArchiveOrgResult(identifier=d["identifier"], title=d.get("title", d["identifier"])) for d in docs]


def search_standards(keywords: str, max_results: int = 10) -> list[ArchiveOrgResult]:
    """Searches Internet Archive's real-Indian-Standards index by keyword,
    matched against title. Real BIS standard titles are precise, formal
    phrases (e.g. "Reverse Osmosis Based Point of Use Water Treatment
    System") — a multi-word product description rarely appears in one
    verbatim, but a short, exact sub-phrase from it very often does. So
    this tries progressively shorter/looser queries rather than one rigid
    match, confirmed necessary by testing: searching for the literal
    phrase "reverse osmosis water purifier" (a real product_type value)
    found nothing, while the shorter phrase "reverse osmosis" alone
    correctly found IS 16240. The ladder, stopping at the first query that
    finds anything:
      1. `keywords` as one exact phrase (title:"...") — most precise.
      2. Each 2-word sliding window of `keywords` as an exact phrase, in
         order — still precise, tolerates `keywords` being longer than
         any single real title fragment.
      3. All of `keywords`' significant words OR'd together (title:(a OR
         b OR ...)) — broadest, last resort; results may include
         tangentially-related standards, so this is only reached when
         nothing more precise matched at all.
    Returns [] if every step finds nothing, or on a network/API error — a
    failed search degrades to "nothing found", it never raises into a
    caller expecting a clean fallback path."""
    words = [w for w in keywords.split() if len(w) > 2]  # drop short stopword-like tokens ("of", "in", ...)
    if not words:
        return []

    full_phrase_results = _run_query(f'title:"{keywords}"', max_results)
    if full_phrase_results:
        return full_phrase_results

    for window_size in (3, 2):
        for start in range(len(words) - window_size + 1):
            phrase = " ".join(words[start : start + window_size])
            results = _run_query(f'title:"{phrase}"', max_results)
            if results:
                return results

    or_clause = " OR ".join(words)
    return _run_query(f"title:({or_clause})", max_results)


def fetch_pdf(identifier: str) -> bytes:
    """Downloads the given item's PDF file. Raises ArchiveOrgError if the
    item has no PDF file or the request fails — this is the one function
    in this module allowed to raise, since a caller that already decided
    to ingest a specific identifier needs to know definitively whether
    that succeeded."""
    metadata_url = METADATA_URL_TEMPLATE.format(identifier=identifier)
    try:
        meta_response = httpx.get(metadata_url, timeout=DEFAULT_TIMEOUT_SECONDS)
        meta_response.raise_for_status()
        files = meta_response.json().get("files", [])
    except (httpx.HTTPError, ValueError) as exc:
        raise ArchiveOrgError(f"Could not fetch metadata for {identifier}: {exc}") from exc

    pdf_filenames = [f["name"] for f in files if f.get("name", "").lower().endswith(".pdf")]
    if not pdf_filenames:
        raise ArchiveOrgError(f"Item {identifier} has no PDF file available")

    download_url = DOWNLOAD_URL_TEMPLATE.format(identifier=identifier, filename=pdf_filenames[0])
    try:
        pdf_response = httpx.get(download_url, timeout=DEFAULT_TIMEOUT_SECONDS, follow_redirects=True)
        pdf_response.raise_for_status()
    except httpx.HTTPError as exc:
        raise ArchiveOrgError(f"Could not download PDF for {identifier}: {exc}") from exc

    return pdf_response.content
