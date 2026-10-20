let data = { items: [], sync_status: {} };

async function load() {
  try {
    const r = await fetch("inventory.json?t=" + Date.now(), { cache: "no-store" });
    data = await r.json();
  } catch (e) {
    document.getElementById("meta").textContent = "Offline and no cached data yet.";
    return;
  }
  const when = data.generated_at ? new Date(data.generated_at).toLocaleString() : "never";
  document.getElementById("meta").textContent = "Last sync: " + when;
  document.getElementById("status").textContent =
    Object.entries(data.sync_status || {}).map(([k, v]) => `${k}: ${v}`).join("  |  ");
  render();
}

function render() {
  const center = document.getElementById("center").value;
  const q = document.getElementById("search").value.trim().toLowerCase();
  const onlyMismatch = document.getElementById("mismatch").checked;
  const tbody = document.getElementById("rows");
  tbody.replaceChildren();

  const rows = data.items.filter(it =>
    (!center || it.center === center) &&
    (!q || [it.sku, it.barcode, it.description].some(v => (v || "").toLowerCase().includes(q))) &&
    (!onlyMismatch || (it.difference !== null && it.difference !== 0))
  );

  for (const it of rows) {
    const tr = document.createElement("tr");
    const mismatch = it.difference !== null && it.difference !== 0;
    tr.className = it.difference === null ? "" : (mismatch ? "mismatch" : "ok");
    const cells = [
      [it.center], [it.sku], [it.barcode], [it.description],
      [it.ledger_on_hand, "num"],
      [it.platform_available ?? "—", "num"],
      [it.difference ?? "—", "num diff"],
    ];
    for (const [text, cls] of cells) {
      const td = document.createElement("td");
      td.textContent = text;          // textContent avoids HTML injection from product names
      if (cls) td.className = cls;
      tr.appendChild(td);
    }
    tbody.appendChild(tr);
  }
  if (!rows.length) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 7;
    td.textContent = "No matching items.";
    tr.appendChild(td);
    tbody.appendChild(tr);
  }
}

["center", "search", "mismatch"].forEach(id =>
  document.getElementById(id).addEventListener("input", render));
load();

if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js");
