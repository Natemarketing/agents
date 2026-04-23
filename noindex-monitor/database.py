from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


class Client(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    domain = db.Column(db.String(300), nullable=True)
    urls = db.relationship("URL", backref="client", lazy=True, cascade="all, delete-orphan")
    scans = db.relationship("ScanRun", backref="client", lazy=True, cascade="all, delete-orphan")
    allowlist = db.relationship("AllowlistEntry", backref="client", lazy=True, cascade="all, delete-orphan")


class URL(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey("client.id"), nullable=False)
    url = db.Column(db.String(2000), nullable=False)

    # Current state
    is_noindex = db.Column(db.Boolean, default=False)

    # Previous scan state (for delta detection)
    previous_noindex = db.Column(db.Boolean, default=False)

    # Timestamps
    last_checked = db.Column(db.DateTime, nullable=True)
    first_noindex_detected = db.Column(db.DateTime, nullable=True)

    # Status flags
    error = db.Column(db.String(500), nullable=True)
    status_code = db.Column(db.Integer, nullable=True)


class ScanRun(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey("client.id"), nullable=False)
    scanned_at = db.Column(db.DateTime, default=datetime.utcnow)
    total_urls = db.Column(db.Integer, default=0)
    fails = db.Column(db.Integer, default=0)
    new_fails = db.Column(db.Integer, default=0)


class AllowlistEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey("client.id"), nullable=False)
    url_pattern = db.Column(db.String(2000), nullable=False)


class ClientConfig(db.Model):
    """Per-client extraction settings. If no config exists, auto-detect is used."""
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey("client.id"), nullable=False, unique=True)

    # Which column to read URLs from. "auto" = scan all columns for hyperlinks.
    # Letter like "A", "E", "B" = only look in that column.
    url_column = db.Column(db.String(10), default="auto")

    # "full_url" = cell contains complete URLs (https://domain.com/page)
    # "slug" = cell contains slugs (/page) that need base_domain prepended
    url_type = db.Column(db.String(20), default="full_url")

    # Required when url_type="slug". e.g. "https://armordial.com"
    base_domain = db.Column(db.String(300), nullable=True)

    # "hyperlink" = extract from hyperlinks only (plain text ignored)
    # "text" = read plain text values (for sheets where URLs are typed, not linked)
    # "both" = try hyperlink first, fall back to text
    read_mode = db.Column(db.String(20), default="hyperlink")

    # Whether this client is fully configured and verified
    is_configured = db.Column(db.Boolean, default=False)

    # Notes for you to remember why it's set up this way
    notes = db.Column(db.String(500), nullable=True)

    client = db.relationship("Client", backref=db.backref("config", uselist=False))


def init_db(app):
    with app.app_context():
        db.create_all()
