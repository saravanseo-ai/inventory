"""Platform API clients for Amazon FBA and Walmart WFS.
Credentials come from environment variables (GitHub Secrets in CI). Never hard-code them.
"""
import base64
import os
import uuid

import requests

# ---------- Amazon Selling Partner API ----------
AMAZON_LWA_URL = "https://api.amazon.com/auth/o2/token"
AMAZON_HOST = os.environ.get("AMAZON_SP_API_HOST", "https://sellingpartnerapi-na.amazon.com")
AMAZON_MARKETPLACE = os.environ.get("AMAZON_MARKETPLACE_ID", "ATVPDKIKX0DER")  # US


def amazon_configured():
    return all(os.environ.get(k) for k in
               ("AMAZON_REFRESH_TOKEN", "AMAZON_CLIENT_ID", "AMAZON_CLIENT_SECRET"))


def _amazon_token():
    r = requests.post(AMAZON_LWA_URL, data={
        "grant_type": "refresh_token",
        "refresh_token": os.environ["AMAZON_REFRESH_TOKEN"],
        "client_id": os.environ["AMAZON_CLIENT_ID"],
        "client_secret": os.environ["AMAZON_CLIENT_SECRET"],
    }, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]


def amazon_fba_inventory():
    """Returns rows: center, sku, barcode (FNSKU), description, available (fulfillable units)."""
    headers = {"x-amz-access-token": _amazon_token()}
    params = {
        "details": "true",
        "granularityType": "Marketplace",
        "granularityId": AMAZON_MARKETPLACE,
        "marketplaceIds": AMAZON_MARKETPLACE,
    }
    items, next_token = [], None
    while True:
        if next_token:
            params["nextToken"] = next_token
        r = requests.get(f"{AMAZON_HOST}/fba/inventory/v1/summaries",
                         headers=headers, params=params, timeout=30)
        r.raise_for_status()
        body = r.json()
        for s in body.get("payload", {}).get("inventorySummaries", []):
            items.append({
                "center": "amazon",
                "sku": s.get("sellerSku", ""),
                "barcode": s.get("fnSku", ""),
                "description": s.get("productName", ""),
                "available": int(s.get("inventoryDetails", {}).get("fulfillableQuantity", 0)),
            })
        next_token = (body.get("pagination") or {}).get("nextToken")
        if not next_token:
            break
    return items


# ---------- Walmart Marketplace / WFS ----------
WALMART_HOST = "https://marketplace.walmartapis.com"
# TODO: confirm this path and the response shape against Walmart's current WFS inventory docs
WALMART_INVENTORY_PATH = "/v3/fulfillment/inventory"


def walmart_configured():
    return all(os.environ.get(k) for k in ("WALMART_CLIENT_ID", "WALMART_CLIENT_SECRET"))


def _walmart_headers(extra=None):
    h = {"WM_SVC.NAME": "Walmart Marketplace",
         "WM_QOS.CORRELATION_ID": str(uuid.uuid4()),
         "Accept": "application/json"}
    if extra:
        h.update(extra)
    return h


def _walmart_token():
    basic = base64.b64encode(
        f"{os.environ['WALMART_CLIENT_ID']}:{os.environ['WALMART_CLIENT_SECRET']}".encode()
    ).decode()
    r = requests.post(f"{WALMART_HOST}/v3/token",
                      headers=_walmart_headers({"Authorization": f"Basic {basic}",
                                                "Content-Type": "application/x-www-form-urlencoded"}),
                      data={"grant_type": "client_credentials"}, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]


def walmart_wfs_inventory():
    """Returns rows in the same shape as amazon_fba_inventory().
    The parser below assumes a list under 'inventory' with sku/gtin/quantity fields.
    Adjust it once you have a real response from your account.
    """
    token = _walmart_token()
    r = requests.get(f"{WALMART_HOST}{WALMART_INVENTORY_PATH}",
                     headers=_walmart_headers({"WM_SEC.ACCESS_TOKEN": token}), timeout=30)
    r.raise_for_status()
    items = []
    for s in r.json().get("inventory", []):
        items.append({
            "center": "walmart",
            "sku": s.get("sku", ""),
            "barcode": s.get("gtin", ""),
            "description": s.get("productName", ""),
            "available": int(s.get("quantity", {}).get("amount", 0)
                             if isinstance(s.get("quantity"), dict) else s.get("quantity", 0)),
        })
    return items
