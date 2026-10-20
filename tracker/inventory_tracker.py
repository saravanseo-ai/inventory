#!/usr/bin/env python3
"""
Fulfillment inventory tracker (Walmart / Amazon / any center).

Data is stored as plain CSV files in ./inventory_data (override with INV_DATA_DIR):
  products.csv   one row per product: SKU, description, barcode, units per case
  movements.csv  append-only ledger of every receive / ship / adjust
Stock on hand is always computed from the ledger, so every number is traceable.

Commands
  add-product SKU DESCRIPTION BARCODE [--units-per-case N]
  receive     SKU CENTER QTY [--note TEXT]
  ship        SKU CENTER QTY [--note TEXT] [--force]
  adjust      SKU CENTER QTY_DELTA [--note TEXT]     (use +/- for corrections)
  stock       [--center CENTER]
  label       SKU [--out DIR]                        (Code 128 PNG, needs python-barcode)
  email       [--center CENTER] [--to ADDR ...] [--out FILE.eml] [--send]

Email sending (only with --send) reads these environment variables:
  SMTP_HOST, SMTP_PORT (default 587), SMTP_USER, SMTP_PASS, SMTP_FROM
"""
import argparse
import csv
import datetime as dt
import html
import os
import smtplib
import sys
from collections import defaultdict
from email.message import EmailMessage

DATA_DIR = os.environ.get("INV_DATA_DIR", "inventory_data")
PRODUCTS = os.path.join(DATA_DIR, "products.csv")
MOVES = os.path.join(DATA_DIR, "movements.csv")
PRODUCT_FIELDS = ["sku", "description", "barcode", "units_per_case"]
MOVE_FIELDS = ["timestamp", "sku", "barcode", "center", "qty_change", "type", "note"]


# ---------- storage helpers ----------

def ensure_storage():
    os.makedirs(DATA_DIR, exist_ok=True)
    for path, fields in ((PRODUCTS, PRODUCT_FIELDS), (MOVES, MOVE_FIELDS)):
        if not os.path.exists(path):
            with open(path, "w", newline="") as f:
                csv.DictWriter(f, fieldnames=fields).writeheader()


def read_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def append_csv(path, fields, row):
    with open(path, "a", newline="") as f:
        csv.DictWriter(f, fieldnames=fields).writerow(row)


def load_products():
    return {p["sku"]: p for p in read_csv(PRODUCTS)}


def stock_levels():
    """Return {(sku, center): qty_on_hand} computed from the ledger."""
    totals = defaultdict(int)
    for m in read_csv(MOVES):
        totals[(m["sku"], m["center"].lower())] += int(m["qty_change"])
    return dict(totals)


# ---------- commands ----------

def cmd_add_product(a):
    products = load_products()
    if a.sku in products:
        sys.exit(f"SKU {a.sku} already exists.")
    append_csv(PRODUCTS, PRODUCT_FIELDS, {
        "sku": a.sku,
        "description": a.description,
        "barcode": a.barcode,
        "units_per_case": a.units_per_case,
    })
    print(f"Added {a.sku}: {a.description} (barcode {a.barcode})")


def _record(a, qty_change, kind):
    products = load_products()
    if a.sku not in products:
        sys.exit(f"Unknown SKU {a.sku}. Add it first with add-product.")
    center = a.center.lower()
    append_csv(MOVES, MOVE_FIELDS, {
        "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
        "sku": a.sku,
        "barcode": products[a.sku]["barcode"],
        "center": center,
        "qty_change": qty_change,
        "type": kind,
        "note": a.note or "",
    })
    on_hand = stock_levels().get((a.sku, center), 0)
    print(f"{kind.capitalize()} recorded: {a.sku} @ {center} {qty_change:+d}. On hand now: {on_hand}")


def cmd_receive(a):
    _record(a, a.qty, "receive")


def cmd_ship(a):
    on_hand = stock_levels().get((a.sku, a.center.lower()), 0)
    if on_hand < a.qty and not a.force:
        sys.exit(f"Refusing: only {on_hand} of {a.sku} at {a.center} on hand. Use --force to override.")
    _record(a, -a.qty, "ship")


def cmd_adjust(a):
    _record(a, a.qty_delta, "adjust")


def build_rows(center_filter=None):
    products = load_products()
    rows = []
    for (sku, center), qty in sorted(stock_levels().items()):
        if center_filter and center != center_filter.lower():
            continue
        if qty == 0 and not center_filter:
            continue
        p = products.get(sku, {})
        upc = int(p.get("units_per_case") or 1)
        rows.append({
            "center": center,
            "sku": sku,
            "barcode": p.get("barcode", ""),
            "description": p.get("description", ""),
            "on_hand": qty,
            "cases": round(qty / upc, 2) if upc > 1 else None,
            "warning": "NEGATIVE - check ledger" if qty < 0 else "",
        })
    return rows


def cmd_stock(a):
    rows = build_rows(a.center)
    if not rows:
        print("No stock on record.")
        return
    print(f"{'CENTER':<10}{'SKU':<16}{'BARCODE':<16}{'ON HAND':>9}  DESCRIPTION")
    for r in rows:
        flag = f"  <-- {r['warning']}" if r["warning"] else ""
        print(f"{r['center']:<10}{r['sku']:<16}{r['barcode']:<16}{r['on_hand']:>9}  {r['description']}{flag}")


def cmd_label(a):
    try:
        import barcode
        from barcode.writer import ImageWriter
    except ImportError:
        sys.exit("Install the label library first: pip install python-barcode pillow")
    products = load_products()
    if a.sku not in products:
        sys.exit(f"Unknown SKU {a.sku}.")
    os.makedirs(a.out, exist_ok=True)
    code = barcode.get("code128", products[a.sku]["barcode"], writer=ImageWriter())
    path = code.save(os.path.join(a.out, f"label_{a.sku}"))
    print(f"Label written to {path}")


def cmd_email(a):
    rows = build_rows(a.center)
    today = dt.date.today().strftime("%b %d, %Y")
    scope = a.center.title() if a.center else "All Centers"
    subject = f"Inventory update: {scope} as of {today}"

    # Plain text version
    lines = [f"Inventory update for {scope} as of {today}", ""]
    if rows:
        lines.append(f"{'Center':<10}{'SKU':<16}{'Barcode':<16}{'On hand':>9}  Description")
        for r in rows:
            lines.append(f"{r['center']:<10}{r['sku']:<16}{r['barcode']:<16}{r['on_hand']:>9}  {r['description']}")
    else:
        lines.append("No stock on record.")
    lines += ["", "Negative counts (if any) need a ledger check before shipping."]
    text_body = "\n".join(lines)

    # HTML version
    def cell(v, align="left"):
        return f'<td style="padding:6px 10px;text-align:{align};border-bottom:1px solid #ddd">{html.escape(str(v))}</td>'

    row_html = "".join(
        "<tr>" + cell(r["center"]) + cell(r["sku"]) + cell(r["barcode"]) +
        cell(r["on_hand"], "right") + cell(r["description"]) + "</tr>"
        for r in rows
    ) or '<tr><td colspan="5">No stock on record.</td></tr>'
    html_body = f"""<html><body style="font-family:Arial,sans-serif;color:#222">
<p>Inventory update for <b>{html.escape(scope)}</b> as of {today}.</p>
<table style="border-collapse:collapse;font-size:14px">
<tr style="background:#f2f2f2">
<th style="padding:6px 10px;text-align:left">Center</th>
<th style="padding:6px 10px;text-align:left">SKU</th>
<th style="padding:6px 10px;text-align:left">Barcode</th>
<th style="padding:6px 10px;text-align:right">On hand</th>
<th style="padding:6px 10px;text-align:left">Description</th></tr>
{row_html}
</table>
<p style="font-size:12px;color:#666">Generated automatically from the inventory ledger.</p>
</body></html>"""

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = os.environ.get("SMTP_FROM", "inventory@example.com")
    msg["To"] = ", ".join(a.to) if a.to else "recipient@example.com"
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")

    out_path = a.out or os.path.join(DATA_DIR, f"update_{dt.date.today().isoformat()}.eml")
    with open(out_path, "wb") as f:
        f.write(bytes(msg))
    print(f"Email saved to {out_path}")

    if a.send:
        if not a.to:
            sys.exit("--send requires at least one --to address.")
        host = os.environ.get("SMTP_HOST")
        if not host:
            sys.exit("Set SMTP_HOST, SMTP_USER, SMTP_PASS (and optionally SMTP_PORT, SMTP_FROM) to send.")
        with smtplib.SMTP(host, int(os.environ.get("SMTP_PORT", "587"))) as s:
            s.starttls()
            s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
            s.send_message(msg)
        print(f"Sent to {', '.join(a.to)}")


# ---------- CLI ----------

def main():
    ensure_storage()
    p = argparse.ArgumentParser(description="Fulfillment inventory tracker")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("add-product")
    s.add_argument("sku")
    s.add_argument("description")
    s.add_argument("barcode")
    s.add_argument("--units-per-case", type=int, default=1)
    s.set_defaults(func=cmd_add_product)

    for name, fn in (("receive", cmd_receive), ("ship", cmd_ship)):
        s = sub.add_parser(name)
        s.add_argument("sku")
        s.add_argument("center")
        s.add_argument("qty", type=int)
        s.add_argument("--note")
        if name == "ship":
            s.add_argument("--force", action="store_true")
        s.set_defaults(func=fn)

    s = sub.add_parser("adjust")
    s.add_argument("sku")
    s.add_argument("center")
    s.add_argument("qty_delta", type=int)
    s.add_argument("--note")
    s.set_defaults(func=cmd_adjust)

    s = sub.add_parser("stock")
    s.add_argument("--center")
    s.set_defaults(func=cmd_stock)

    s = sub.add_parser("label")
    s.add_argument("sku")
    s.add_argument("--out", default="labels")
    s.set_defaults(func=cmd_label)

    s = sub.add_parser("email")
    s.add_argument("--center")
    s.add_argument("--to", nargs="*")
    s.add_argument("--out")
    s.add_argument("--send", action="store_true")
    s.set_defaults(func=cmd_email)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
