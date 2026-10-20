"""Pull platform inventory, compare with the local ledger, write docs/inventory.json for the PWA."""
import datetime as dt
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tracker"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("INV_DATA_DIR", os.path.join(ROOT, "inventory_data"))

import inventory_tracker as inv  # noqa: E402
import platforms as p  # noqa: E402

OUT = os.path.join(ROOT, "docs", "inventory.json")


def main():
    inv.ensure_storage()
    status, platform_rows = {}, []

    for name, configured, fetch in (
        ("amazon", p.amazon_configured, p.amazon_fba_inventory),
        ("walmart", p.walmart_configured, p.walmart_wfs_inventory),
    ):
        if not configured():
            status[name] = "not configured"
            continue
        try:
            rows = fetch()
            platform_rows.extend(rows)
            status[name] = f"ok ({len(rows)} items)"
        except Exception as e:  # keep going so one platform failing doesn't block the other
            status[name] = f"error: {e}"

    platform = {(r["sku"], r["center"]): r for r in platform_rows}
    ledger = inv.stock_levels()
    products = inv.load_products()

    keys = set(platform) | {k for k in ledger if k[1] in ("amazon", "walmart")}
    items = []
    for sku, center in sorted(keys):
        plat = platform.get((sku, center))
        prod = products.get(sku, {})
        ledger_qty = ledger.get((sku, center), 0)
        plat_qty = plat["available"] if plat else None
        items.append({
            "center": center,
            "sku": sku,
            "barcode": (plat or {}).get("barcode") or prod.get("barcode", ""),
            "description": (plat or {}).get("description") or prod.get("description", ""),
            "ledger_on_hand": ledger_qty,
            "platform_available": plat_qty,
            # Differences are flags to investigate, not proof of error:
            # platforms count their own warehouse units, which may lag your shipments.
            "difference": None if plat_qty is None else plat_qty - ledger_qty,
        })

    out = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "sync_status": status,
        "items": items,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(out, f, indent=2)
    print(json.dumps(status, indent=2))
    print(f"Wrote {len(items)} rows to {OUT}")


if __name__ == "__main__":
    main()
