let lastProductSeq = -1;
let currentProductKey = null;

function speak(text) {
    try {
        if (!('speechSynthesis' in window)) return;
        const utter = new SpeechSynthesisUtterance(text);
        utter.lang = 'th-TH';
        window.speechSynthesis.cancel();
        window.speechSynthesis.speak(utter);
    } catch (e) { /* TTS is a nice-to-have; ignore if the browser can't do it */ }
}

function addHistoryLine(text) {
    const list = document.getElementById('history-list');
    const line = document.createElement('div');
    const now = new Date().toLocaleTimeString('th-TH', { hour12: false });
    line.textContent = `[${now}] ${text}`;
    list.insertBefore(line, list.firstChild);
    while (list.children.length > 100) list.removeChild(list.lastChild);
}

function renderState(state) {
    for (const [camId, info] of Object.entries(state.cameras)) {
        const dot = document.getElementById(`dot-${camId}`);
        const statusText = document.getElementById(`status-${camId}`);
        if (dot) dot.className = 'status-dot status-' + info.status;
        if (statusText) statusText.textContent = info.message || info.status;
    }

    const pill = document.getElementById('readiness-pill');

    if (state.current_product) {
        const p = state.current_product;
        currentProductKey = p.key;
        document.getElementById('product-name').textContent = p.name;
        document.getElementById('product-tagline').textContent = p.tagline;
        document.getElementById('product-desc').textContent = p.description;
        document.getElementById('product-source').textContent =
            `ตรวจพบโดยกล้อง: ${p.cameras} · ความมั่นใจ ${(p.confidence * 100).toFixed(0)}%`;

        if (state.product_seq !== lastProductSeq) {
            lastProductSeq = state.product_seq;
            document.getElementById('answer-text').textContent = '';
            addHistoryLine(`🟢 พบสินค้า: ${p.name} (${p.cameras})`);
            speak(p.speak_text);
        }
    }

    const alertsList = document.getElementById('alerts-list');
    alertsList.innerHTML = '';
    for (const alert of state.recent_alerts) {
        const div = document.createElement('div');
        const t = new Date(alert.ts * 1000).toLocaleTimeString('th-TH', { hour12: false });
        div.textContent = `[${t}] ${alert.text}`;
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

document.getElementById('ask-btn').addEventListener('click', ask);
document.getElementById('question-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') ask();
});

async function ask() {
    const input = document.getElementById('question-input');
    const question = input.value.trim();
    if (!question) return;
    const res = await fetch('/api/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question }),
    });
    const data = await res.json();
    document.getElementById('answer-text').textContent = data.answer;
    addHistoryLine(`❓ ${question} → ${data.answer}`);
    speak(data.answer);
    input.value = '';
}

document.getElementById('readiness-btn').addEventListener('click', async () => {
    const res = await fetch('/api/readiness', { method: 'POST' });
    const report = await res.json();

    const pill = document.getElementById('readiness-pill');
    pill.textContent = report.overall_ok ? '✅ READY' : '❌ NOT READY';
    pill.className = 'pill ' + (report.overall_ok ? 'ready' : 'not-ready');

    const headline = document.getElementById('readiness-headline');
    headline.textContent = report.overall_ok ? '✅ บูธพร้อมใช้งาน (READY)' : '❌ บูธยังไม่พร้อม (NOT READY)';
    headline.style.color = report.overall_ok ? '#2ecc71' : '#e74c3c';

    const list = document.getElementById('readiness-list');
    list.innerHTML = '';
    for (const c of report.components) {
        const icon = c.ok ? '✅' : (c.critical ? '❌' : '⚠️');
        const line = document.createElement('div');
        line.style.padding = '4px 0';
        line.textContent = `${icon} ${c.component} — ${c.detail}`;
        list.appendChild(line);
    }
    document.getElementById('readiness-modal').classList.remove('hidden');
});

pollState();
