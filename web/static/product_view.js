let lastProductSeq = -1;

function speak(text) {
    try {
        if (!('speechSynthesis' in window)) return;
        const utter = new SpeechSynthesisUtterance(text);
        utter.lang = 'th-TH';
        window.speechSynthesis.cancel();
        window.speechSynthesis.speak(utter);
    } catch (e) { /* TTS is a nice-to-have; ignore if the browser can't do it */ }
}

function addHistoryLine(iconName, text) {
    const list = document.getElementById('history-list');
    const line = document.createElement('div');
    const now = new Date().toLocaleTimeString('th-TH', { hour12: false });
    line.innerHTML = `${iconHtml(iconName, { size: 14, className: 'icon-inline' })}[${now}] ${text}`;
    list.insertBefore(line, list.firstChild);
    while (list.children.length > 100) list.removeChild(list.lastChild);
}

function renderProductInfo(p) {
    document.getElementById('product-name').textContent = p.name;
    document.getElementById('product-tagline').textContent = p.tagline || '';
    document.getElementById('product-price').textContent = p.price ? `ราคา: ${p.price}` : '';
    document.getElementById('product-desc').textContent = p.description || '';
    document.getElementById('product-source').textContent =
        `ตรวจพบโดยกล้อง: ${p.cameras} · ความมั่นใจ ${(p.confidence * 100).toFixed(0)}%`;

    const faqList = document.getElementById('faq-list');
    faqList.innerHTML = '';
    for (const entry of (p.faq || [])) {
        const div = document.createElement('div');
        div.className = 'faq-item';
        div.innerHTML = `<div class="faq-q">${entry.q}</div><div class="faq-a">${entry.a}</div>`;
        faqList.appendChild(div);
    }
}

function renderCameraStatus(cameras) {
    for (const [camId, info] of Object.entries(cameras)) {
        const dot = document.getElementById(`dot-${camId}`);
        const statusText = document.getElementById(`status-${camId}`);
        if (dot) dot.className = 'status-dot status-' + info.status;
        if (statusText) statusText.textContent = info.message || info.status;
    }
}

async function pollState() {
    try {
        const res = await fetch('/api/state');
        const state = await res.json();
        renderCameraStatus(state.cameras);

        if (state.current_product) {
            const p = state.current_product;
            renderProductInfo(p);

            if (state.product_seq !== lastProductSeq) {
                lastProductSeq = state.product_seq;
                addHistoryLine('box', `พบสินค้า: ${p.name} (${p.cameras})`);
                speak(p.speak_text);
            }
        }
    } catch (e) { /* transient network hiccup — next poll will retry */ }
    setTimeout(pollState, 1500);
}

pollState();
