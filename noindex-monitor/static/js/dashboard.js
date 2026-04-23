let clientsData = [];

async function loadClients() {
    const res = await fetch("/api/clients");
    clientsData = await res.json();
    renderStats();
    renderClients();
}

function renderStats() {
    const total = clientsData.length;
    const passing = clientsData.filter(c => c.status === "pass").length;
    const failing = clientsData.filter(c => c.status === "fail").length;
    const pending = clientsData.filter(c => c.status === "pending").length;
    const totalURLs = clientsData.reduce((s, c) => s + c.total_urls, 0);

    document.getElementById("stats-bar").innerHTML = `
        <div class="stat-card"><div class="label">Clients</div><div class="value">${total}</div></div>
        <div class="stat-card"><div class="label">Passing</div><div class="value pass">${passing}</div></div>
        <div class="stat-card"><div class="label">Failing</div><div class="value fail">${failing}</div></div>
        <div class="stat-card"><div class="label">Pending</div><div class="value pending">${pending}</div></div>
        <div class="stat-card"><div class="label">Total URLs</div><div class="value">${totalURLs}</div></div>
    `;
}

function renderClients() {
    const filter = document.getElementById("search").value.toLowerCase();
    const filtered = clientsData.filter(c =>
        c.name.toLowerCase().includes(filter) || c.domain.toLowerCase().includes(filter)
    );

    const grid = document.getElementById("client-grid");
    if (!filtered.length) {
        grid.innerHTML = '<div class="loading">No clients found.</div>';
        return;
    }

    // Sort: fails first, then pass, then pending
    const order = { fail: 0, pass: 1, pending: 2 };
    filtered.sort((a, b) => (order[a.status] ?? 9) - (order[b.status] ?? 9) || a.name.localeCompare(b.name));

    grid.innerHTML = filtered.map(c => {
        const badgeClass = c.status === "pass" ? "badge-pass" : c.status === "fail" ? "badge-fail" : "badge-pending";
        const scanText = c.last_scan ? timeAgo(new Date(c.last_scan)) : "Not scanned";
        const failText = c.fails > 0 ? `<span class="text-fail">${c.fails} fail${c.fails > 1 ? "s" : ""}</span>` : "";
        const cfgText = c.configured ? "" : ' <span style="color:#f59e0b;font-size:0.7rem" title="Not configured - using auto-detect">AUTO</span>';
        return `
        <div class="client-card" onclick="location.href='/client/${c.id}'">
            <div class="card-top">
                <div class="name">${esc(c.name)}</div>
                <span class="badge ${badgeClass}">${c.status}</span>
            </div>
            <div class="domain">${esc(c.domain)}${cfgText}</div>
            <div class="card-bottom">
                <span class="url-count">${c.total_urls} URLs ${failText}</span>
                <span class="scan-time">${scanText}</span>
            </div>
        </div>`;
    }).join("");
}

async function syncSheet() {
    const btn = document.getElementById("btn-sync");
    btn.disabled = true;
    btn.textContent = "Syncing...";
    try {
        const res = await fetch("/api/sync-sheet", { method: "POST" });
        const data = await res.json();
        let msg = `Synced ${data.clients} clients, ${data.urls} URLs`;
        if (data.errors && data.errors.length) msg += ` (${data.errors.length} error${data.errors.length > 1 ? "s" : ""})`;
        toast(msg);
        await loadClients();
    } catch (e) {
        toast("Sync failed: " + e.message);
    }
    btn.disabled = false;
    btn.textContent = "Sync Sheet";
}

async function runFullScan() {
    const btn = document.getElementById("btn-scan");
    btn.disabled = true;
    btn.textContent = "Scanning...";
    try {
        await fetch("/api/scan", { method: "POST" });
        toast("Full scan complete");
        await loadClients();
    } catch (e) {
        toast("Scan failed: " + e.message);
    }
    btn.disabled = false;
    btn.textContent = "Run Full Scan";
}

function toast(msg) {
    const el = document.getElementById("toast");
    el.textContent = msg;
    el.classList.remove("hidden");
    setTimeout(() => el.classList.add("hidden"), 3000);
}

function timeAgo(date) {
    const secs = Math.floor((Date.now() - date.getTime()) / 1000);
    if (secs < 60) return "just now";
    if (secs < 3600) return Math.floor(secs / 60) + "m ago";
    if (secs < 86400) return Math.floor(secs / 3600) + "h ago";
    return Math.floor(secs / 86400) + "d ago";
}

function esc(s) {
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
}

loadClients();
