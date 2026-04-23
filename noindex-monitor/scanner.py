"""
URL scanner with noindex detection and delta tracking.

For each URL:
1. Fetch the page
2. Check <meta name="robots"> and <meta name="googlebot"> for 'noindex'
3. Check X-Robots-Tag HTTP header for 'noindex'
4. Compare current state to previous_noindex
5. If newly noindexed: set first_noindex_detected timestamp
6. Return results for Slack alerting
"""

import requests
from bs4 import BeautifulSoup
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from database import db, Client, URL, ScanRun, AllowlistEntry

HEADERS = {
    "User-Agent": "MonochromeNoindexMonitor/1.0 (+https://monochromemktg.com)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
TIMEOUT = 15
MAX_WORKERS = 25


def check_noindex(url: str) -> dict:
    """
    Return {is_noindex, status_code, error}.
    Checks meta robots tag AND X-Robots-Tag HTTP header.
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)

        # Check X-Robots-Tag header
        x_robots = (resp.headers.get("X-Robots-Tag", "") or "").lower()
        if "noindex" in x_robots:
            return {"is_noindex": True, "status_code": resp.status_code, "error": None}

        # Must be a successful 2xx to parse HTML
        if resp.status_code >= 400:
            return {
                "is_noindex": False,
                "status_code": resp.status_code,
                "error": f"HTTP {resp.status_code}",
            }

        soup = BeautifulSoup(resp.text, "html.parser")
        for meta in soup.find_all("meta", attrs={"name": True}):
            name = (meta.get("name") or "").lower()
            if name in ("robots", "googlebot"):
                content = (meta.get("content") or "").lower()
                if "noindex" in content:
                    return {"is_noindex": True, "status_code": resp.status_code, "error": None}

        return {"is_noindex": False, "status_code": resp.status_code, "error": None}

    except requests.Timeout:
        return {"is_noindex": False, "status_code": None, "error": "Request timed out"}
    except requests.RequestException as e:
        return {"is_noindex": False, "status_code": None, "error": str(e)[:400]}


def run_scan_for_client(app, client_id: int) -> dict:
    """
    Scan all URLs for a single client. Track newly-detected noindexes.
    Returns {'client', 'total', 'fails', 'new_fails', 'new_urls': [...]}
    """
    with app.app_context():
        client = Client.query.get(client_id)
        if not client:
            return {"error": "Client not found"}

        urls = URL.query.filter_by(client_id=client.id).all()
        if not urls:
            return {
                "client": client.name,
                "total": 0,
                "fails": 0,
                "new_fails": 0,
                "new_urls": [],
            }

        allowlist = {a.url_pattern for a in AllowlistEntry.query.filter_by(client_id=client.id).all()}
        now = datetime.utcnow()
        new_noindex_urls: list[str] = []

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(check_noindex, u.url): u for u in urls}
            for future in as_completed(futures):
                url_obj = futures[future]
                result = future.result()

                was_noindex = url_obj.is_noindex
                current_noindex = result["is_noindex"]

                url_obj.previous_noindex = was_noindex
                url_obj.is_noindex = current_noindex
                url_obj.last_checked = now
                url_obj.error = result["error"]
                url_obj.status_code = result["status_code"]

                # Delta detection: newly noindexed
                if current_noindex and not was_noindex and url_obj.url not in allowlist:
                    url_obj.first_noindex_detected = now
                    new_noindex_urls.append(url_obj.url)
                elif not current_noindex:
                    url_obj.first_noindex_detected = None

        fails = sum(
            1 for u in urls
            if u.is_noindex and u.url not in allowlist
        )

        scan_run = ScanRun(
            client_id=client.id,
            total_urls=len(urls),
            fails=fails,
            new_fails=len(new_noindex_urls),
        )
        db.session.add(scan_run)
        db.session.commit()

        return {
            "client": client.name,
            "total": len(urls),
            "fails": fails,
            "new_fails": len(new_noindex_urls),
            "new_urls": new_noindex_urls,
        }


def run_full_scan(app) -> list:
    """Scan all clients. Returns per-client results."""
    with app.app_context():
        clients = Client.query.all()
        results = []
        for client in clients:
            result = run_scan_for_client(app, client.id)
            results.append(result)
        return results
