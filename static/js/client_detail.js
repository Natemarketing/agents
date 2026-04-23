let urlsData = [];
let clientInfo = {};

async function loadData() {
    const res = await fetch(`/api/clients/${CLIENT_ID}/urls`);
    const data = await res.json();
    clientInfo = data.client;
    urlsData = data.urls;

    document.getElementById("client-name").textContent = clientInfo.name;
    document.getElementById("client-domain").textContent = clientInfo.domain;
    document.title = clientInfo.name + " - Noindex Monitor";

    renderStats();
    renderURLs();
}

function renderStats() {
    const total = urlsData.length;
    const pass = urlsData.filter(u => u.status === "pass").length;
    const fail = urlsData.filter(u => u.status === "fail").length;
    const al = urlsData.filter(u => u.status === "allowlisted").length;
    const errors = urlsData.filter(u => u.error).length;

    document.getElementById("stats-bar").innerHTML = `
        <div class="stat-card"><div class="label">Total URLs</div><div class="value">${total}</div></div>
        <div class="stat-card"><div class="label">Passing</div><div class="value pass">${pass}</div></div>
        <div class="stat-card"><div class="label">Failing</div><div class="value fail">${fail}</div></div>
        <div class="stat-card"><div class="label">Allowlisted</div><div class="value" style="color:var(--allowlisted)">${al}</div></div>
        <div class="stat-card"><div class="label">Errors</div><div class="value pending">${errors}</div></div>
    `;
}

function renderURLs() {
    const filter = document.getElementById("search").value.toLowerCase();
    const statusFilter = document.getElementById("status-filter").value;

    let filtered = urlsData;
    if (filter) filtered = filtered.filter(u => u.url.toLowerCase().includes(filter));
    if (statusFilter !== "all") filtered = filtered.filter(u => u.status === statusFilter);

    // Sort: fails first
    const order = { fail: 0, allowlisted: 1, pass: 2 };
    filtered.sort((a, b) => (order[a.status] ?? 9) - (order[b.status] ?? 9));

    const tbody = document.getElementById("url-tbody");
    if (!filtered.length) {
        tbody.innerHTML = '<tr><td colspan="4" class="loading">No URLs match.</td></tr>';
        return;
    }

    tbody.innerHTML = filtered.map(u => {
        const badgeClass = u.status === "pass" ? "badge-pass" : u.status === "fail" ? "badge-fail" : "badge-allowlisted";
        const checked = u.last_checked ? new Date(u.last_checked).toLocaleString() : "-";
        const errorTip = u.error ? ` title="${esc(u.error)}"` : "";
        const newBadge = u.is_new ? '<span class="badge badge-new">NEW</span>' : '';
        const actionBtn = u.status === "fail"
            ? `<button class="btn btn-sm btn-secondary" onclick="event.stopPropagation(); addToAllowlist('${esc(u.url)}')">Allowlist</button>`
            : "";
        return `
        <tr${errorTip}>
            <td><span class="badge ${badgeClass}">${u.status}</span>${newBadge}</td>
            <td class="col-url"><a href="${esc(u.url)}" target="_blank">${esc(u.url)}</a>${u.error ? ' <span class="text-fail" title="' + esc(u.error) + '">&#9888;</span>' : ''}</td>
            <td>${checked}</td>
            <td>${actionBtn}</td>
        </tr>`;
    }).join("");
}

async function scanClient() {
    toast("Scanning...");
    try {
        await fetch(`/api/scan/${CLIENT_ID}`, { method: "POST" });
        toast("Scan complete");
        await loadData();
    } catch (e) {
        toast("Scan failed: " + e.message);
    }
}

function exportCSV() {
    window.location.href = `/api/export/${CLIENT_ID}`;
}

// ---- Allowlist ----
function toggleAllowlist() {
    const modal = document.getElementById("allowlist-modal");
    modal.classList.toggle("hidden");
    if (!modal.classList.contains("hidden")) loadAllowlist();
}

async function loadAllowlist() {
    const res = await fetch(`/api/clients/${CLIENT_ID}/allowlist`);
    const entries = await res.json();
    const list = document.getElementById("allowlist-list");
    if (!entries.length) {
        list.innerHTML = "<li>No entries yet.</li>";
        return;
    }
    list.innerHTML = entries.map(e => `
        <li>
            <span>${esc(e.url_pattern)}</span>
            <button class="btn btn-sm btn-secondary" onclick="removeAllowlist(${e.id})">Remove</button>
        </li>
    `).join("");
}

async function addAllowlist() {
    const input = document.getElementById("allowlist-input");
    const url = input.value.trim();
    if (!url) return;
    await fetch(`/api/clients/${CLIENT_ID}/allowlist`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url_pattern: url }),
    });
    input.value = "";
    toast("Added to allowlist");
    await loadAllowlist();
    await loadData();
}

async function addToAllowlist(url) {
    await fetch(`/api/clients/${CLIENT_ID}/allowlist`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url_pattern: url }),
    });
    toast("Added to allowlist");
    await loadData();
}

async function removeAllowlist(id) {
    await fetch(`/api/clients/${CLIENT_ID}/allowlist`, {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id }),
    });
    toast("Removed from allowlist");
    await loadAllowlist();
    await loadData();
}

function toast(msg) {
    const el = document.getElementById("toast");
    el.textContent = msg;
    el.classList.remove("hidden");
    setTimeout(() => el.classList.add("hidden"), 3000);
}

function esc(s) {
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
}

loadData();
