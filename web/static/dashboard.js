let externalInteractions = [];
let externalHealth = [];

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

function syncSelect(select, values) {
    const current = select.value;
    select.innerHTML = '<option value="">ทั้งหมด</option>';
    for (const v of values) {
        const opt = document.createElement('option');
        opt.value = v; opt.textContent = v;
        select.appendChild(opt);
    }
    select.value = values.includes(current) ? current : '';
}

async function refresh() {
    const [interactions, health] = await Promise.all([
        fetchLocal('/api/dashboard/interactions'),
        fetchLocal('/api/dashboard/health'),
    ]);
    const allInteractions = interactions.concat(externalInteractions);
    const allHealth = health.concat(externalHealth);

    const eventIds = [...new Set(allInteractions.concat(allHealth).map(r => r.event_id).filter(Boolean))].sort();
    const boothIds = [...new Set(allInteractions.concat(allHealth).map(r => r.booth_id).filter(Boolean))].sort();
    syncSelect(document.getElementById('event-filter'), eventIds);
    syncSelect(document.getElementById('booth-filter'), boothIds);

    const filteredInteractions = applyFilters(allInteractions);
    const filteredHealth = applyFilters(allHealth);

    const booths = new Set([...filteredInteractions, ...filteredHealth].map(r => r.booth_id));
    const openAlerts = filteredHealth.filter(h => h.status === 'error');
    document.getElementById('stat-total').textContent = filteredInteractions.length;
    document.getElementById('stat-products').textContent = new Set(filteredInteractions.map(r => r.product_name)).size;
    document.getElementById('stat-booths').textContent = booths.size;
    document.getElementById('stat-alerts').textContent = openAlerts.length;

    const counts = {};
    for (const r of filteredInteractions) counts[r.product_name] = (counts[r.product_name] || 0) + 1;
    const topProducts = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 10);
    const topBody = document.getElementById('top-products-body');
    topBody.innerHTML = '';
    for (const [name, count] of topProducts) {
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${name}</td><td>${count}</td>`;
        topBody.appendChild(tr);
    }

    const interactionsBody = document.getElementById('interactions-body');
    interactionsBody.innerHTML = '';
    const sortedInteractions = [...filteredInteractions].sort((a, b) => (b.ts || 0) - (a.ts || 0)).slice(0, 200);
    for (const r of sortedInteractions) {
        const tr = document.createElement('tr');
        const conf = typeof r.confidence === 'number' ? (r.confidence * 100).toFixed(0) + '%' : '';
        tr.innerHTML = `<td>${fmtTs(r.ts)}</td><td>${r.booth_id || ''}</td><td>${r.camera_id || ''}</td>` +
            `<td>${r.product_name || ''}</td><td>${conf}</td><td>${r.question || ''}</td><td>${r.answer || ''}</td>`;
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
