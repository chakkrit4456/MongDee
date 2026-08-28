let externalInteractions = [];
let externalHealth = [];

const STATE_LABELS = { idle: 'นิ่ง (ไม่มีการขยับ)', held: 'มีคนถือ', unsettled: 'กำลังตั้งค่าเริ่มต้น' };

function fmtTs(ts) {
    if (!ts) return '';
    return new Date(ts * 1000).toLocaleString('th-TH', { hour12: false });
}

async function fetchLocal(path) {
    const res = await fetch(path);
    return res.json();
}

function applyFilters(rows) {
    const eventId = document.getElementById('event-filter').value;
    const boothId = document.getElementById('booth-filter').value;
    return rows.filter(r =>
        (!eventId || r.event_id === eventId) && (!boothId || r.booth_id === boothId)
    );
}

function syncSelect(select, values, labels) {
    labels = labels || {};
    const current = select.value;
    select.innerHTML = '<option value="">ทั้งหมด</option>';
    for (const v of values) {
        const opt = document.createElement('option');
        opt.value = v; opt.textContent = labels[v] ? `${labels[v]} (${v})` : v;
        select.appendChild(opt);
    }
    select.value = values.includes(current) ? current : '';
}

function currentQuery() {
    const eventId = document.getElementById('event-filter').value;
    const boothId = document.getElementById('booth-filter').value;
    const params = new URLSearchParams();
    if (eventId) params.set('event_id', eventId);
    if (boothId) params.set('booth_id', boothId);
    return params.toString() ? `?${params.toString()}` : '';
}

async function refresh() {
    const query = currentQuery();
    const [interactions, health, products, live, movers, presence, holdHistory, presenceHistory,
           knownIds, events, booths] = await Promise.all([
        fetchLocal('/api/dashboard/interactions'),
        fetchLocal('/api/dashboard/health'),
        fetchLocal('/api/products'),
        fetchLocal('/api/dashboard/live'),
        fetchLocal(`/api/dashboard/product_movers${query}`),
        fetchLocal(`/api/dashboard/presence_stats${query}`),
        fetchLocal(`/api/dashboard/product_hold_history${query}`),
        fetchLocal(`/api/dashboard/presence_sessions${query}`),
        fetchLocal('/api/dashboard/known_ids'),
        fetchLocal('/api/registry/events'),
        fetchLocal('/api/registry/booths'),
    ]);
    const allInteractions = interactions.concat(externalInteractions);
    const allHealth = health.concat(externalHealth);

    // The registry (Events/Booths created via /settings) is the primary,
    // curated source — known_ids (scans every log table) is unioned in as a
    // fallback so pre-registry/orphaned log data is still selectable, just
    // without a friendly name.
    const eventLabels = Object.fromEntries(events.map(e => [e.id, e.name]));
    const boothLabels = Object.fromEntries(booths.map(b => [b.id, b.name]));
    const eventIds = [...new Set([
        ...events.map(e => e.id),
        ...knownIds.event_ids,
        ...allInteractions.concat(allHealth).map(r => r.event_id).filter(Boolean),
    ])].sort();
    const boothIds = [...new Set([
        ...booths.map(b => b.id),
        ...knownIds.booth_ids,
        ...allInteractions.concat(allHealth).map(r => r.booth_id).filter(Boolean),
    ])].sort();
    syncSelect(document.getElementById('event-filter'), eventIds, eventLabels);
    syncSelect(document.getElementById('booth-filter'), boothIds, boothLabels);

    const exportLink = document.getElementById('export-link');
    exportLink.href = `/api/dashboard/export.xlsx${query}`;

    const filteredInteractions = applyFilters(allInteractions);
    const filteredHealth = applyFilters(allHealth);

    const activeBoothIds = new Set([...filteredInteractions, ...filteredHealth].map(r => r.booth_id));
    const openAlerts = filteredHealth.filter(h => h.status === 'error');
    document.getElementById('stat-total').textContent = filteredInteractions.length;
    document.getElementById('stat-products').textContent = new Set(filteredInteractions.map(r => r.product_name)).size;
    document.getElementById('stat-booths').textContent = activeBoothIds.size;
    document.getElementById('stat-alerts').textContent = openAlerts.length;
    document.getElementById('stat-people-now').textContent = live.people_now;
    document.getElementById('stat-avg-presence').textContent = presence.avg_sec.toFixed(1);

    const catalogList = document.getElementById('catalog-list');
    catalogList.innerHTML = '';
    for (const p of products) {
        const span = document.createElement('span');
        span.className = 'pill';
        span.textContent = p.name;
        catalogList.appendChild(span);
    }

    const liveBody = document.getElementById('live-states-body');
    liveBody.innerHTML = '';
    for (const p of live.products) {
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${p.camera_id}</td><td>${p.product_name}</td>` +
            `<td>${STATE_LABELS[p.state] || p.state}</td><td>${p.interest_seconds.toFixed(1)}</td>`;
        liveBody.appendChild(tr);
    }

    const topBody = document.getElementById('top-products-body');
    topBody.innerHTML = '';
    for (const m of movers) {
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${m.product_name}</td><td>${m.mover_count}</td><td>${(m.total_interest_sec || 0).toFixed(1)}</td>`;
        topBody.appendChild(tr);
    }

    const holdBody = document.getElementById('hold-history-body');
    holdBody.innerHTML = '';
    for (const h of holdHistory) {
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${fmtTs(h.ts)}</td><td>${h.camera_id}</td><td>${h.product_name}</td><td>${h.duration_sec.toFixed(1)}</td>`;
        holdBody.appendChild(tr);
    }

    const presenceBody = document.getElementById('presence-history-body');
    presenceBody.innerHTML = '';
    for (const p of presenceHistory) {
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${fmtTs(p.ts)}</td><td>${p.camera_id}</td><td>${p.duration_sec.toFixed(1)}</td>`;
        presenceBody.appendChild(tr);
    }

    const interactionsBody = document.getElementById('interactions-body');
    interactionsBody.innerHTML = '';
    const sortedInteractions = [...filteredInteractions].sort((a, b) => (b.ts || 0) - (a.ts || 0)).slice(0, 200);
    for (const r of sortedInteractions) {
        const tr = document.createElement('tr');
        const conf = typeof r.confidence === 'number' ? (r.confidence * 100).toFixed(0) + '%' : '';
        tr.innerHTML = `<td>${fmtTs(r.ts)}</td><td>${r.booth_id || ''}</td><td>${r.camera_id || ''}</td>` +
            `<td>${r.product_name || ''}</td><td>${conf}</td>`;
        interactionsBody.appendChild(tr);
    }

    const healthBody = document.getElementById('health-body');
    healthBody.innerHTML = '';
    const sortedHealth = [...filteredHealth].sort((a, b) => (b.ts || 0) - (a.ts || 0)).slice(0, 100);
    for (const r of sortedHealth) {
        const device = r.component ? `${r.camera_id || ''} (${r.component})` : (r.camera_id || '');
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${fmtTs(r.ts)}</td><td>${r.booth_id || ''}</td><td>${device}</td>` +
            `<td>${r.status || ''}</td><td>${r.message || ''}</td>`;
        healthBody.appendChild(tr);
    }
}

document.getElementById('refresh-btn').addEventListener('click', refresh);
document.getElementById('event-filter').addEventListener('change', refresh);
document.getElementById('booth-filter').addEventListener('change', refresh);

async function deleteRegistryScope(field, label, endpoint) {
    const value = document.getElementById(field).value;
    if (!value) { alert(`กรุณาเลือก ${label} ที่ต้องการลบก่อน`); return; }
    if (!confirm(`ลบ ${label} "${value}" และข้อมูลที่บันทึกไว้ทั้งหมดหรือไม่? การกระทำนี้ย้อนกลับไม่ได้`)) return;
    const res = await fetch(`${endpoint}/${value}`, { method: 'DELETE' });
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'ล้มเหลว' }));
        alert(`ลบไม่สำเร็จ: ${err.detail}`);
        return;
    }
    document.getElementById(field).value = '';
    await refresh();
}

document.getElementById('delete-event-btn').addEventListener('click',
    () => deleteRegistryScope('event-filter', 'Event ID', '/api/registry/events'));
document.getElementById('delete-booth-btn').addEventListener('click',
    () => deleteRegistryScope('booth-filter', 'Booth ID', '/api/registry/booths'));

document.getElementById('import-btn').addEventListener('click', () => {
    document.getElementById('import-file').click();
});
document.getElementById('import-file').addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
        try {
            const data = JSON.parse(reader.result);
            externalInteractions = externalInteractions.concat(data.interactions || []);
            externalHealth = externalHealth.concat(data.health_events || []);
            alert(`นำเข้าข้อมูลจาก ${file.name} สำเร็จ`);
            refresh();
        } catch (err) {
            alert('นำเข้าล้มเหลว: ไฟล์ไม่ใช่ JSON ที่ถูกต้อง');
        }
    };
    reader.readAsText(file);
});

refresh();
setInterval(refresh, 5000);
