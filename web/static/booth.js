const ALERT_ICONS = {
    camera_offline: 'alertTriangle',
    camera_online: 'check',
    camera_connected: 'plug',
    product_found: 'box',
};

function renderState(state) {
    for (const [camId, info] of Object.entries(state.cameras)) {
        const dot = document.getElementById(`dot-${camId}`);
        const statusText = document.getElementById(`status-${camId}`);
        if (dot) dot.className = 'status-dot status-' + info.status;
        if (statusText) statusText.textContent = info.message || info.status;
    }

    const peoplePill = document.getElementById('people-now-pill');
    peoplePill.innerHTML = iconHtml('users', { size: 14, className: 'icon-inline' }) + `คนในกล้อง: ${state.people_now}`;

    const alertsList = document.getElementById('alerts-list');
    alertsList.innerHTML = '';
    for (const alert of state.recent_alerts) {
        const div = document.createElement('div');
        const t = new Date(alert.ts * 1000).toLocaleTimeString('th-TH', { hour12: false });
        const icon = ALERT_ICONS[alert.type] || 'info';
        div.innerHTML = `${iconHtml(icon, { size: 14, className: 'icon-inline' })}[${t}] ${alert.text}`;
        alertsList.appendChild(div);
    }
}

async function pollState() {
    try {
        const res = await fetch('/api/state');
        const state = await res.json();
        renderState(state);
    } catch (e) { /* transient network hiccup — next poll will retry */ }
    setTimeout(pollState, 1500);
}

document.getElementById('open-dashboard-btn').addEventListener('click', () => {
    window.open('/dashboard', '_blank', 'noopener');
});

document.getElementById('open-product-btn').addEventListener('click', () => {
    window.open('/product-view', '_blank', 'noopener');
});

document.getElementById('readiness-btn').addEventListener('click', async () => {
    const res = await fetch('/api/readiness', { method: 'POST' });
    const report = await res.json();

    const pill = document.getElementById('readiness-pill');
    pill.innerHTML = report.overall_ok
        ? iconHtml('check', { size: 14, className: 'icon-inline' }) + 'READY'
        : iconHtml('x', { size: 14, className: 'icon-inline' }) + 'NOT READY';
    pill.className = 'pill ' + (report.overall_ok ? 'ready' : 'not-ready');

    const headline = document.getElementById('readiness-headline');
    headline.textContent = report.overall_ok ? 'บูธพร้อมใช้งาน (READY)' : 'บูธยังไม่พร้อม (NOT READY)';
    headline.style.color = report.overall_ok ? '#2ecc71' : '#e74c3c';

    const list = document.getElementById('readiness-list');
    list.innerHTML = '';
    for (const c of report.components) {
        const icon = c.ok ? 'check' : (c.critical ? 'x' : 'alertTriangle');
        const block = document.createElement('div');
        block.className = 'readiness-component';
        let html = `<div class="readiness-summary">${iconHtml(icon, { size: 14, className: 'icon-inline' })}${c.component} — ${c.detail}</div>`;
        const advanced = c.advanced || {};
        const keys = Object.keys(advanced);
        if (keys.length) {
            html += '<dl class="readiness-advanced">';
            for (const key of keys) {
                html += `<dt>${key}</dt><dd>${advanced[key]}</dd>`;
            }
            html += '</dl>';
        }
        block.innerHTML = html;
        list.appendChild(block);
    }
    document.getElementById('readiness-modal').classList.remove('hidden');
});

pollState();
