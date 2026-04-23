import os
from flask import Flask, render_template, jsonify, request, Response
from database import db, Client, URL, ScanRun, AllowlistEntry, ClientConfig, init_db
from scanner import run_scan_for_client, run_full_scan
from sheets import sync_clients_from_sheet, test_extraction
from slack_notify import send_slack_summary
import csv
import io
from datetime import datetime

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///noindex.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)

with app.app_context():
    init_db(app)


# ---------------------------------------------------------------------------
# Dashboard views
# ---------------------------------------------------------------------------

@app.route("/")
def dashboard():
    return render_template("dashboard.html")


@app.route("/client/<int:client_id>")
def client_detail(client_id):
    return render_template("client_detail.html", client_id=client_id)


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

@app.route("/api/clients")
def api_clients():
    clients = Client.query.order_by(Client.name).all()
    out = []
    for c in clients:
        latest_run = (
            ScanRun.query.filter_by(client_id=c.id)
            .order_by(ScanRun.scanned_at.desc())
            .first()
        )
        total = URL.query.filter_by(client_id=c.id).count()
        fails = 0
        last_scan = None
        if latest_run:
            last_scan = latest_run.scanned_at.isoformat()
            fails = (
                URL.query.filter_by(client_id=c.id, is_noindex=True)
                .filter(~URL.url.in_(
                    db.session.query(AllowlistEntry.url_pattern).filter_by(client_id=c.id)
                ))
                .count()
            )
        out.append({
            "id": c.id,
            "name": c.name,
            "domain": c.domain,
            "total_urls": total,
            "fails": fails,
            "status": "pass" if fails == 0 and latest_run else ("fail" if fails > 0 else "pending"),
            "last_scan": last_scan,
            "configured": bool(c.config and c.config.is_configured),
        })
    return jsonify(out)


@app.route("/api/clients/<int:client_id>/urls")
def api_client_urls(client_id):
    client = Client.query.get_or_404(client_id)
    allowlist = [a.url_pattern for a in AllowlistEntry.query.filter_by(client_id=client_id).all()]
    urls = URL.query.filter_by(client_id=client_id).order_by(URL.url).all()
    out = []
    for u in urls:
        is_allowlisted = u.url in allowlist
        is_new = bool(u.is_noindex and u.first_noindex_detected and not is_allowlisted)
        out.append({
            "id": u.id,
            "url": u.url,
            "is_noindex": u.is_noindex,
            "is_new": is_new,
            "allowlisted": is_allowlisted,
            "status": "allowlisted" if (u.is_noindex and is_allowlisted) else ("fail" if u.is_noindex else "pass"),
            "last_checked": u.last_checked.isoformat() if u.last_checked else None,
            "first_detected": u.first_noindex_detected.isoformat() if u.first_noindex_detected else None,
            "status_code": u.status_code,
            "error": u.error,
        })
    return jsonify({"client": {"id": client.id, "name": client.name, "domain": client.domain}, "urls": out})


@app.route("/api/clients/<int:client_id>/allowlist", methods=["GET", "POST", "DELETE"])
def api_allowlist(client_id):
    if request.method == "GET":
        entries = AllowlistEntry.query.filter_by(client_id=client_id).all()
        return jsonify([{"id": e.id, "url_pattern": e.url_pattern} for e in entries])

    if request.method == "POST":
        data = request.json
        entry = AllowlistEntry(client_id=client_id, url_pattern=data["url_pattern"])
        db.session.add(entry)
        db.session.commit()
        return jsonify({"ok": True})

    if request.method == "DELETE":
        data = request.json
        AllowlistEntry.query.filter_by(id=data["id"]).delete()
        db.session.commit()
        return jsonify({"ok": True})


@app.route("/api/clients/<int:client_id>/config", methods=["GET", "POST"])
def api_client_config(client_id):
    """Get or set per-client extraction config."""
    client = Client.query.get_or_404(client_id)

    if request.method == "GET":
        cfg = ClientConfig.query.filter_by(client_id=client_id).first()
        if not cfg:
            return jsonify({"configured": False})
        return jsonify({
            "configured": cfg.is_configured,
            "url_column": cfg.url_column,
            "url_type": cfg.url_type,
            "base_domain": cfg.base_domain,
            "read_mode": cfg.read_mode,
            "notes": cfg.notes,
        })

    if request.method == "POST":
        data = request.json
        cfg = ClientConfig.query.filter_by(client_id=client_id).first()
        if not cfg:
            cfg = ClientConfig(client_id=client_id)
            db.session.add(cfg)

        cfg.url_column = data.get("url_column", "auto")
        cfg.url_type = data.get("url_type", "full_url")
        cfg.base_domain = data.get("base_domain", "")
        cfg.read_mode = data.get("read_mode", "hyperlink")
        cfg.is_configured = data.get("is_configured", True)
        cfg.notes = data.get("notes", "")
        db.session.commit()
        return jsonify({"ok": True})


@app.route("/api/clients/<int:client_id>/test-extract")
def api_test_extract(client_id):
    """Test URL extraction for a client without modifying data."""
    result = test_extraction(app, client_id)
    return jsonify(result)


@app.route("/api/scan", methods=["POST"])
def api_trigger_scan():
    """Trigger a full scan of all clients."""
    results = run_full_scan(app)
    send_slack_summary(results)
    return jsonify({"ok": True, "results": results})


@app.route("/api/scan/<int:client_id>", methods=["POST"])
def api_trigger_client_scan(client_id):
    """Trigger scan for a single client."""
    result = run_scan_for_client(app, client_id)
    return jsonify({"ok": True, "result": result})


@app.route("/api/sync-sheet", methods=["POST"])
def api_sync_sheet():
    """Pull latest client/URL data from Google Sheets."""
    summary = sync_clients_from_sheet(app)
    return jsonify({"ok": True, **summary})


@app.route("/api/export/<int:client_id>")
def api_export(client_id):
    client = Client.query.get_or_404(client_id)
    urls = URL.query.filter_by(client_id=client_id).order_by(URL.url).all()
    allowlist = [a.url_pattern for a in AllowlistEntry.query.filter_by(client_id=client_id).all()]

    si = io.StringIO()
    writer = csv.writer(si)
    writer.writerow(["URL", "Noindex", "Allowlisted", "Status", "Last Checked", "Error"])
    for u in urls:
        is_al = u.url in allowlist
        status = "allowlisted" if (u.is_noindex and is_al) else ("fail" if u.is_noindex else "pass")
        writer.writerow([
            u.url,
            u.is_noindex,
            is_al,
            status,
            u.last_checked.isoformat() if u.last_checked else "",
            u.error or "",
        ])

    output = si.getvalue()
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={client.name.replace(' ', '_')}_noindex_report.csv"},
    )


if __name__ == "__main__":
    app.run(debug=True, port=5000)
