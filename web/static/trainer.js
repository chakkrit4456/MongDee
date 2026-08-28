let selectedKey = null;
let products = [];
let pollingProgress = false;

async function fetchProducts() {
    const res = await fetch('/api/products');
    products = await res.json();
    renderProductList();
}

function renderProductList() {
    const list = document.getElementById('product-list');
    list.innerHTML = '';
    for (const p of products) {
        const icon = p.sample_count >= RECOMMENDED_SAMPLES ? '🟢' : (p.sample_count > 0 ? '🟡' : '⚪');
        const div = document.createElement('div');
        div.className = 'product-list-item' + (p.key === selectedKey ? ' selected' : '');
        div.textContent = `${icon} ${p.name} (${p.sample_count} ภาพ)`;
        div.addEventListener('click', () => selectProduct(p.key));
        list.appendChild(div);
    }
    if (!selectedKey && products.length > 0) selectProduct(products[0].key);
}

function selectProduct(key) {
    selectedKey = key;
    renderProductList();
    const product = products.find(p => p.key === key);
    if (!product) return;

    document.getElementById('detail-empty').classList.add('hidden');
    document.getElementById('detail-content').classList.remove('hidden');
    document.getElementById('detail-title').textContent = `${product.name} · key: ${product.key}`;

    const n = product.sample_count;
    const pct = Math.min(100, Math.round(100 * n / RECOMMENDED_SAMPLES));
    document.getElementById('sample-progress').style.width = pct + '%';

    let status;
    if (n === 0) status = '⚪ ยังไม่มีข้อมูลเทรน — อัปโหลดรูปภาพหรือวิดีโอเพื่อเริ่มต้น';
    else if (n < RECOMMENDED_SAMPLES) status = `🟡 มีข้อมูล ${n} ภาพ — แนะนำให้อัปโหลดเพิ่มอีกอย่างน้อย ${RECOMMENDED_SAMPLES - n} ภาพ เพื่อความแม่นยำ`;
    else status = `🟢 มีข้อมูล ${n} ภาพ — พร้อมใช้งานแล้ว (อัปโหลดเพิ่มได้เสมอเพื่อความแม่นยำที่สูงขึ้น)`;
    document.getElementById('detail-status').textContent = status;

    document.getElementById('import-log').textContent = '';
    document.getElementById('import-progress-wrap').classList.add('hidden');
}

document.getElementById('add-product-btn').addEventListener('click', () => {
    document.getElementById('new-name').value = '';
    document.getElementById('new-tagline').value = '';
    document.getElementById('new-description').value = '';
    document.getElementById('add-modal').classList.remove('hidden');
});

document.getElementById('add-confirm-btn').addEventListener('click', async () => {
    const name = document.getElementById('new-name').value.trim();
    if (!name) { alert('กรุณากรอกชื่อสินค้า'); return; }
    const res = await fetch('/api/products', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            name,
            tagline: document.getElementById('new-tagline').value.trim(),
            description: document.getElementById('new-description').value.trim(),
        }),
    });
    const data = await res.json();
    document.getElementById('add-modal').classList.add('hidden');
    selectedKey = data.key;
    await fetchProducts();
});

document.getElementById('images-input').addEventListener('change', async (e) => {
    const files = e.target.files;
    if (!files.length || !selectedKey) return;
    const form = new FormData();
    for (const f of files) form.append('files', f);
    await startImport(`/api/products/${selectedKey}/upload_images`, form);
    e.target.value = '';
});

document.getElementById('video-input').addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file || !selectedKey) return;
    const form = new FormData();
    form.append('file', file);
    await startImport(`/api/products/${selectedKey}/upload_video`, form);
    e.target.value = '';
});

async function startImport(url, form) {
    document.getElementById('import-log').textContent = 'กำลังประมวลผล...';
    document.getElementById('import-progress-wrap').classList.remove('hidden');
    document.getElementById('import-progress').style.width = '0%';

    const res = await fetch(url, { method: 'POST', body: form });
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'ล้มเหลว' }));
        document.getElementById('import-log').textContent = `❌ ล้มเหลว: ${err.detail}`;
        document.getElementById('import-progress-wrap').classList.add('hidden');
        return;
    }
    if (!pollingProgress) pollImportProgress();
}

async function pollImportProgress() {
    if (!selectedKey) { pollingProgress = false; return; }
    pollingProgress = true;
    const res = await fetch(`/api/products/${selectedKey}/import_progress`);
    const progress = await res.json();

    if (progress.status === 'running') {
        const pct = progress.total > 0 ? Math.round(100 * progress.done / progress.total) : 0;
        document.getElementById('import-progress').style.width = pct + '%';
        document.getElementById('import-log').textContent = `ประมวลผลแล้ว ${progress.done}/${progress.total}`;
        setTimeout(pollImportProgress, 500);
    } else if (progress.status === 'done') {
        document.getElementById('import-log').textContent = `✅ เพิ่มข้อมูลเทรนสำเร็จ ${progress.done} ภาพ`;
        document.getElementById('import-progress-wrap').classList.add('hidden');
        pollingProgress = false;
        await fetchProducts();
        selectProduct(selectedKey);
    } else if (progress.status === 'error') {
        document.getElementById('import-log').textContent = `❌ ล้มเหลว: ${progress.message || ''}`;
        document.getElementById('import-progress-wrap').classList.add('hidden');
        pollingProgress = false;
    } else {
        pollingProgress = false;
    }
}

document.getElementById('clear-samples-btn').addEventListener('click', async () => {
    if (!selectedKey) return;
    const product = products.find(p => p.key === selectedKey);
    if (!confirm(`ลบข้อมูลเทรนทั้งหมดของ "${product.name}" หรือไม่?`)) return;
    await fetch(`/api/products/${selectedKey}/clear_samples`, { method: 'POST' });
    await fetchProducts();
    selectProduct(selectedKey);
});

function initTestCamera() {
    const select = document.getElementById('test-camera-select');
    for (const camId of CAMERA_IDS) {
        const opt = document.createElement('option');
        opt.value = camId; opt.textContent = camId;
        select.appendChild(opt);
    }
    const updateImg = () => {
        document.getElementById('test-camera-img').src = '/stream/' + select.value + '?t=' + Date.now();
    };
    select.addEventListener('change', updateImg);
    if (CAMERA_IDS.length > 0) updateImg();
}

initTestCamera();
fetchProducts();
setInterval(fetchProducts, 8000);
