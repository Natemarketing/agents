#!/usr/bin/env python3
"""
Configure a client's URL extraction settings from the command line.

Usage:
  python configure_client.py                  # List all clients and their config status
  python configure_client.py "ArmorHQ"        # Configure ArmorHQ interactively
  python configure_client.py "ArmorHQ" test   # Test extraction for ArmorHQ
  python configure_client.py "ArmorHQ" set    # Set config non-interactively:
    --column E --type slug --domain https://armordial.com --mode hyperlink

Examples:
  # ArmorHQ: slugs in column E, hyperlinked, domain is armordial.com
  python configure_client.py "ArmorHQ" set --column E --type slug --domain https://armordial.com --mode hyperlink

  # Caccia: full URLs hyperlinked in auto-detected column
  python configure_client.py "Caccia Home Services" set --column auto --type full_url --mode hyperlink

  # PhoneBurner: full URLs as plain text in column A
  python configure_client.py "PhoneBurner" set --column A --type full_url --mode text
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app
from database import db, Client, ClientConfig
from sheets import test_extraction


def list_clients():
    with app.app_context():
        clients = Client.query.order_by(Client.name).all()
        if not clients:
            print("No clients in database. Run 'Sync Sheet' from the dashboard first.")
            return

        print(f"\n{'ID':<5} {'Client':<40} {'Domain':<30} {'Configured'}")
        print("-" * 85)
        for c in clients:
            cfg = ClientConfig.query.filter_by(client_id=c.id).first()
            status = "YES" if (cfg and cfg.is_configured) else "no"
            detail = ""
            if cfg and cfg.is_configured:
                detail = f"  col={cfg.url_column} type={cfg.url_type} mode={cfg.read_mode}"
                if cfg.base_domain:
                    detail += f" domain={cfg.base_domain}"
            print(f"{c.id:<5} {c.name:<40} {c.domain or '':<30} {status}{detail}")

        unconfigured = sum(
            1 for c in clients
            if not (ClientConfig.query.filter_by(client_id=c.id).first() or ClientConfig()).is_configured
        )
        print(f"\n{len(clients)} clients total, {unconfigured} unconfigured")


def configure_client(name: str):
    with app.app_context():
        client = Client.query.filter_by(name=name).first()
        if not client:
            # Try partial match
            client = Client.query.filter(Client.name.ilike(f"%{name}%")).first()
        if not client:
            print(f"Client '{name}' not found. Run 'python configure_client.py' to see all clients.")
            return

        print(f"\nConfiguring: {client.name} (ID: {client.id}, domain: {client.domain})")

        cfg = ClientConfig.query.filter_by(client_id=client.id).first()
        if cfg and cfg.is_configured:
            print(f"Current config: col={cfg.url_column} type={cfg.url_type} mode={cfg.read_mode} domain={cfg.base_domain}")
            print(f"Notes: {cfg.notes or '(none)'}")

        # Interactive prompts
        print("\nURL column? ('auto' to scan all columns, or a letter like 'A', 'E')")
        url_column = input("  > ").strip() or "auto"

        print("\nURL type? ('full_url' or 'slug')")
        url_type = input("  > ").strip() or "full_url"

        base_domain = ""
        if url_type == "slug":
            print("\nBase domain? (e.g. 'https://armordial.com')")
            base_domain = input("  > ").strip()

        print("\nRead mode? ('hyperlink' = only linked cells, 'text' = plain text, 'both')")
        read_mode = input("  > ").strip() or "hyperlink"

        print("\nNotes? (optional, for your reference)")
        notes = input("  > ").strip()

        if not cfg:
            cfg = ClientConfig(client_id=client.id)
            db.session.add(cfg)

        cfg.url_column = url_column
        cfg.url_type = url_type
        cfg.base_domain = base_domain
        cfg.read_mode = read_mode
        cfg.notes = notes
        cfg.is_configured = True
        db.session.commit()

        print(f"\nSaved. Testing extraction...")
        result = test_extraction(app, client.id)
        if result.get("error"):
            print(f"ERROR: {result['error']}")
        else:
            print(f"Found {result['count']} URLs (showing first 20):")
            for url in result["urls"][:20]:
                print(f"  {url}")
            if result["count"] > 20:
                print(f"  ... and {result['count'] - 20} more")


def set_config(name: str, column: str, url_type: str, domain: str, mode: str, notes: str = ""):
    with app.app_context():
        client = Client.query.filter_by(name=name).first()
        if not client:
            client = Client.query.filter(Client.name.ilike(f"%{name}%")).first()
        if not client:
            print(f"Client '{name}' not found.")
            return

        cfg = ClientConfig.query.filter_by(client_id=client.id).first()
        if not cfg:
            cfg = ClientConfig(client_id=client.id)
            db.session.add(cfg)

        cfg.url_column = column
        cfg.url_type = url_type
        cfg.base_domain = domain
        cfg.read_mode = mode
        cfg.notes = notes
        cfg.is_configured = True
        db.session.commit()
        print(f"Configured {client.name}: col={column} type={url_type} mode={mode} domain={domain}")


def test_client(name: str):
    with app.app_context():
        client = Client.query.filter_by(name=name).first()
        if not client:
            client = Client.query.filter(Client.name.ilike(f"%{name}%")).first()
        if not client:
            print(f"Client '{name}' not found.")
            return

        cfg = ClientConfig.query.filter_by(client_id=client.id).first()
        mode = "configured" if (cfg and cfg.is_configured) else "auto-detect"
        print(f"\nTesting extraction for {client.name} (mode: {mode})...")

        result = test_extraction(app, client.id)
        if result.get("error"):
            print(f"ERROR: {result['error']}")
        else:
            print(f"Found {result['count']} URLs:")
            for url in result["urls"][:50]:
                print(f"  {url}")
            if result["count"] > 50:
                print(f"  ... and {result['count'] - 50} more")


if __name__ == "__main__":
    args = sys.argv[1:]

    if not args:
        list_clients()
    elif len(args) == 1:
        configure_client(args[0])
    elif len(args) == 2 and args[1] == "test":
        test_client(args[0])
    elif len(args) >= 2 and args[1] == "set":
        # Parse --column, --type, --domain, --mode, --notes
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("name")
        parser.add_argument("cmd")
        parser.add_argument("--column", default="auto")
        parser.add_argument("--type", default="full_url", dest="url_type")
        parser.add_argument("--domain", default="")
        parser.add_argument("--mode", default="hyperlink")
        parser.add_argument("--notes", default="")
        parsed = parser.parse_args(args)
        set_config(parsed.name, parsed.column, parsed.url_type, parsed.domain, parsed.mode, parsed.notes)
    else:
        print(__doc__)
