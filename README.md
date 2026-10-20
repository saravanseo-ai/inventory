# Fulfillment Inventory

- `tracker/inventory_tracker.py`: CLI ledger (receive, ship, adjust, stock, labels, email)
- `sync/platforms.py`: Amazon FBA and Walmart WFS API clients
- `sync/sync.py`: merges platform stock with the ledger and writes `docs/inventory.json`
- `docs/`: the PWA (GitHub Pages)
- `.github/workflows/sync.yml`: runs every 6 hours, sends the daily email at 13:00 UTC

## Setup

1. **Make the repo private.** It will contain your stock data. GitHub Pages on a private repo needs a paid plan. On a free account, use a public repo only if you accept that the inventory data is visible to anyone.
2. Push this folder to the repo.
3. **Add secrets** (Settings → Secrets and variables → Actions): `AMAZON_CLIENT_ID`, `AMAZON_CLIENT_SECRET`, `AMAZON_REFRESH_TOKEN`, `WALMART_CLIENT_ID`, `WALMART_CLIENT_SECRET`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM`, `EMAIL_TO`. Never commit credentials.
4. **Enable Pages:** Settings → Pages → deploy from branch `main`, folder `/docs`.
5. **Load your ledger:** run the tracker locally to add products and movements, then commit the `inventory_data/` folder. The sync job reads it from the repo.
6. **First run:** Actions tab → "Sync inventory" → Run workflow. Check the log for `sync_status`.
7. **Install on your phone:** open the Pages URL and choose "Add to Home Screen".

## Local testing

```bash
pip install -r requirements.txt
export AMAZON_CLIENT_ID=... AMAZON_CLIENT_SECRET=... AMAZON_REFRESH_TOKEN=...
python3 sync/sync.py
python3 -m http.server -d docs 8000   # open http://localhost:8000
```

## Notes

- Walmart's inventory endpoint and response parsing in `sync/platforms.py` are marked TODO. Check them against your account's real response before relying on Walmart numbers.
- A non-zero "Diff" means the platform count and your ledger disagree. Check for shipments not yet logged, or units still inbound.
