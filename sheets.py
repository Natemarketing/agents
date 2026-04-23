"""
Google Sheets integration with per-client config support.

Master matrix:
- Column A: client names, each hyperlinked to their individual matrix
- Stops at "Retired Clients" row

Client matrices:
- Reads tab 1 only
- Uses ClientConfig if set, otherwise falls back to auto-detect:
  auto-detect = scan all columns for hyperlinked URLs, skip Google Docs/Drive links

ClientConfig options:
  url_column:  "auto" | "A" | "B" | "E" etc.
  url_type:    "full_url" | "slug"
  base_domain: "https://armordial.com" (only needed for slug type)
  read_mode:   "hyperlink" | "text" | "both"
"""

import os
import re
from urllib.parse import urlparse
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from database import db, Client, URL, ClientConfig

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
MASTER_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")
SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SA_FILE", "service_account.json")

RETIRED_MARKER = "retired clients"
MAX_MASTER_ROWS = 200
MAX_CLIENT_ROWS = 10000

# Domains to skip when extracting URLs (internal references, not client pages)
SKIP_DOMAINS = {
    "docs.google.com", "drive.google.com", "sheets.google.com",
    "3.basecamp.com", "basecamp.com",
    "accounts.google.com", "console.cloud.google.com",
}


def _get_service():
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def _extract_sheet_id(url: str) -> str:
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", url or "")
    return m.group(1) if m else ""


def _col_letter_to_index(letter: str) -> int:
    """Convert column letter to 0-based index. A=0, B=1, ..., Z=25, AA=26."""
    letter = letter.upper().strip()
    result = 0
    for ch in letter:
        result = result * 26 + (ord(ch) - ord("A") + 1)
    return result - 1


def _extract_hyperlink(cell: dict) -> str:
    """Get the hyperlink URL from a cell using all known methods."""
    link = cell.get("hyperlink") or ""
    if link:
        return link

    formula = (cell.get("userEnteredValue") or {}).get("formulaValue") or ""
    m = re.search(r'HYPERLINK\s*\(\s*"([^"]+)"', formula)
    if m:
        return m.group(1)

    for run in cell.get("textFormatRuns") or []:
        uri = (run.get("format") or {}).get("link", {}).get("uri")
        if uri:
            return uri

    return ""


def _is_valid_page_url(url: str) -> bool:
    """Check if a URL is a real client page (not an internal doc link)."""
    if not url:
        return False
    if not url.lower().startswith(("http://", "https://")):
        return False
    try:
        domain = urlparse(url).netloc.lower()
        return domain not in SKIP_DOMAINS
    except Exception:
        return False


def _get_master_clients() -> list[dict]:
    """Extract hyperlinked client rows from master matrix column A."""
    service = _get_service()
    result = service.spreadsheets().get(
        spreadsheetId=MASTER_SHEET_ID,
        ranges=[f"A1:A{MAX_MASTER_ROWS}"],
        includeGridData=True,
        fields="sheets.data.rowData.values(formattedValue,hyperlink,userEnteredValue,textFormatRuns)"
    ).execute()

    clients: list[dict] = []
    sheets_data = result.get("sheets", [])
    if not sheets_data:
        return clients

    data = sheets_data[0].get("data", [])
    if not data:
        return clients

    for row in data[0].get("rowData", []):
        cells = row.get("values", [])
        if not cells:
            continue
        cell = cells[0]
        text = (cell.get("formattedValue") or "").strip()

        if text.lower() == RETIRED_MARKER:
            break
        if not text:
            continue

        hyperlink = _extract_hyperlink(cell)
        if not hyperlink:
            continue

        sheet_id = _extract_sheet_id(hyperlink)
        if sheet_id:
            clients.append({"name": text, "sheet_id": sheet_id})

    return clients


def _get_first_tab_data(sheet_id: str) -> tuple[list, str]:
    """
    Fetch full grid data for tab 1 of a client sheet.
    Returns (rows_data, tab_title).
    """
    service = _get_service()

    meta = service.spreadsheets().get(
        spreadsheetId=sheet_id,
        fields="sheets.properties(title,index)"
    ).execute()
    sheets_list = sorted(
        meta.get("sheets", []),
        key=lambda s: s["properties"].get("index", 0)
    )
    if not sheets_list:
        return [], ""
    tab_title = sheets_list[0]["properties"]["title"]

    result = service.spreadsheets().get(
        spreadsheetId=sheet_id,
        ranges=[f"'{tab_title}'!A1:Z{MAX_CLIENT_ROWS}"],
        includeGridData=True,
        fields="sheets.data.rowData.values(formattedValue,hyperlink,userEnteredValue,textFormatRuns)"
    ).execute()

    sheets_data = result.get("sheets", [])
    if not sheets_data:
        return [], tab_title
    data = sheets_data[0].get("data", [])
    if not data:
        return [], tab_title

    return data[0].get("rowData", []), tab_title


def _extract_urls_auto(rows: list) -> list[str]:
    """
    Auto-detect mode: scan all cells in all columns for hyperlinked URLs.
    Falls back to plain text URLs if they start with http(s).
    """
    seen: set[str] = set()
    urls: list[str] = []

    for row in rows:
        for cell in row.get("values", []) or []:
            # Try hyperlink first
            url = _extract_hyperlink(cell)

            # Fallback: plain text http URL
            if not url:
                text = (cell.get("formattedValue") or "").strip()
                if text.lower().startswith(("http://", "https://")):
                    url = text

            if url and _is_valid_page_url(url) and url not in seen:
                seen.add(url)
                urls.append(url)

    return urls


def _extract_urls_configured(rows: list, config: "ClientConfig") -> list[str]:
    """
    Use per-client config to extract URLs from a specific column.
    """
    seen: set[str] = set()
    urls: list[str] = []

    # Determine which column index to read
    target_col = None
    if config.url_column and config.url_column.lower() != "auto":
        target_col = _col_letter_to_index(config.url_column)

    for row in rows:
        cells = row.get("values", []) or []

        if target_col is not None:
            # Only read the specified column
            if target_col < len(cells):
                cells_to_check = [cells[target_col]]
            else:
                continue
        else:
            cells_to_check = cells

        for cell in cells_to_check:
            url = None

            if config.read_mode in ("hyperlink", "both"):
                url = _extract_hyperlink(cell)

            if not url and config.read_mode in ("text", "both"):
                text = (cell.get("formattedValue") or "").strip()
                if text:
                    url = text

            if not url:
                continue

            # Handle slugs: prepend base_domain
            if config.url_type == "slug" and config.base_domain:
                if url.startswith("/"):
                    base = config.base_domain.rstrip("/")
                    url = base + url
                elif not url.lower().startswith(("http://", "https://")):
                    base = config.base_domain.rstrip("/")
                    url = base + "/" + url

            if _is_valid_page_url(url) and url not in seen:
                seen.add(url)
                urls.append(url)

    return urls


def _get_urls_from_client_sheet(sheet_id: str, config: "ClientConfig | None") -> list[str]:
    """Read tab 1 and extract URLs using config or auto-detect."""
    rows, _ = _get_first_tab_data(sheet_id)
    if not rows:
        return []

    if config and config.is_configured:
        return _extract_urls_configured(rows, config)
    else:
        return _extract_urls_auto(rows)


def _derive_domain(urls: list[str]) -> str:
    if not urls:
        return ""
    try:
        return urlparse(urls[0]).netloc.replace("www.", "")
    except Exception:
        return ""


def test_extraction(app, client_id: int) -> dict:
    """
    Test URL extraction for a single client without modifying the database.
    Returns {'urls': [...], 'count': n, 'config_used': 'auto'|'configured', 'error': None}
    """
    with app.app_context():
        client = Client.query.get(client_id)
        if not client:
            return {"error": "Client not found", "urls": [], "count": 0}

        # Find the sheet_id from the master matrix
        try:
            master_clients = _get_master_clients()
        except Exception as e:
            return {"error": f"Master sheet: {str(e)[:200]}", "urls": [], "count": 0}

        mc = next((m for m in master_clients if m["name"] == client.name), None)
        if not mc:
            return {"error": f"Client '{client.name}' not found in master matrix", "urls": [], "count": 0}

        config = ClientConfig.query.filter_by(client_id=client.id).first()
        config_mode = "configured" if (config and config.is_configured) else "auto"

        try:
            urls = _get_urls_from_client_sheet(mc["sheet_id"], config)
        except Exception as e:
            return {"error": str(e)[:200], "urls": [], "count": 0}

        return {
            "urls": urls[:100],  # Cap display at 100 for readability
            "count": len(urls),
            "config_used": config_mode,
            "error": None,
        }


def sync_clients_from_sheet(app) -> dict:
    """Full sync: master matrix -> each client's tab 1 -> database."""
    with app.app_context():
        try:
            master_clients = _get_master_clients()
        except Exception as e:
            return {"clients": 0, "urls": 0, "errors": [f"Master sheet: {str(e)[:200]}"]}

        summary = {"clients": 0, "urls": 0, "errors": []}

        for mc in master_clients:
            name = mc["name"]
            sheet_id = mc["sheet_id"]

            # Upsert client first (so we have an ID for config lookup)
            client = Client.query.filter_by(name=name).first()
            if not client:
                client = Client(name=name, domain="")
                db.session.add(client)
                db.session.flush()

            config = ClientConfig.query.filter_by(client_id=client.id).first()

            try:
                urls = _get_urls_from_client_sheet(sheet_id, config)
            except Exception as e:
                summary["errors"].append(f"{name}: {str(e)[:200]}")
                continue

            if not urls:
                summary["errors"].append(f"{name}: no URLs found in tab 1")
                continue

            domain = _derive_domain(urls)
            if domain:
                client.domain = domain

            existing = {u.url: u for u in URL.query.filter_by(client_id=client.id).all()}
            sheet_urls = set(urls)

            new_rows = [URL(client_id=client.id, url=u) for u in sheet_urls if u not in existing]
            if new_rows:
                db.session.bulk_save_objects(new_rows)

            stale = [existing[u].id for u in existing if u not in sheet_urls]
            if stale:
                URL.query.filter(URL.id.in_(stale)).delete(synchronize_session=False)

            summary["clients"] += 1
            summary["urls"] += len(sheet_urls)
            db.session.commit()

        return summary
