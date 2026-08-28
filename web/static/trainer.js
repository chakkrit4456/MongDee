let selectedKey = null;
let products = [];
let pollingProgress = false;
let recording = false;

const GUIDE_RECT = { x: 0.25, y: 0.20, w: 0.50, h: 0.60 };  // fraction of natural image size
const RECORD_TICK_MS = 500;
const RECORD_TICKS = 20;  // 20 x 0.5s = 10s

async function fetchProducts() {
    const res = await fetch('/api/products');
    products = await res.json();
    renderProductList();
}

function renderProductList() {
    const list = document.getElementById('product-list');
    list.innerHTML = '';
    for (const p of products) {
        const dotClass = p.sample_count >= RECOMMENDED_SAMPLES ? 'ready' : (p.sample_count > 0 ? 'partial' : 'empty');
        const div = document.createElement('div');
        div.className = 'product-list-item' + (p.key === selectedKey ? ' selected' : '');
        div.innerHTML =
            `<span><span class="sample-dot sample-dot-${dotClass}"></span>${p.name} (${p.sample_count} ภาพ)</span>` +
            `<button type="button" class="btn-danger btn-small product-delete-btn">${iconHtml('trash', { size: 13 })}</button>`;
        div.addEventListener('click', () => selectProduct(p.key));
        div.querySelector('.product-delete-btn').addEventListener('click', (e) => {
            e.stopPropagation();
            deleteProduct(p.key, p.name);
        });
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
    if (n === 0) status = 'ยังไม่มีข้อมูลเทรน — อัปโหลดรูปภาพ วิดีโอ หรือบันทึกจากกล้องเพื่อเริ่มต้น';
    else if (n < RECOMMENDED_SAMPLES) status = `มีข้อมูล ${n} ภาพ — แนะนำให้อัปโหลดเพิ่มอีกอย่างน้อย ${RECOMMENDED_SAMPLES - n} ภาพ เพื่อความแม่นยำ`;
    else status = `มีข้อมูล ${n} ภาพ — พร้อมใช้งานแล้ว (อัปโหลดเพิ่มได้เสมอเพื่อความแม่นยำที่สูงขึ้น)`;
    document.getElementById('detail-status').textContent = status;

    document.getElementById('import-log').textContent = '';
    document.getElementById('import-progress-wrap').classList.add('hidden');
    document.getElementById('record-status').textContent = '';

    document.getElementById('edit-name').value = product.name || '';
    document.getElementById('edit-tagline').value = product.tagline || '';
    document.getElementById('edit-price').value = product.price || '';
    document.getElementById('edit-description').value = product.description || '';
    renderFaqRows('edit-faq-rows', product.faq || []);
}

// ---------------------------------------------------------------- FAQ rows
function renderFaqRows(containerId, faq) {
    const container = document.getElementById(containerId);
    container.innerHTML = '';
    for (const entry of faq) addFaqRow(containerId, entry.q, entry.a);
}

function addFaqRow(containerId, q, a) {
    const container = document.getElementById(containerId);
    const row = document.createElement('div');
    row.className = 'faq-row';
    row.innerHTML =
        '<input type="text" class="faq-q-input" placeholder="คำถาม">' +
        '<input type="text" class="faq-a-input" placeholder="คำตอบ">' +
        '<button type="button" class="faq-remove-btn">' + iconHtml('x', { size: 14 }) + '</button>';
    row.querySelector('.faq-q-input').value = q || '';
    row.querySelector('.faq-a-input').value = a || '';
    row.querySelector('.faq-remove-btn').addEventListener('click', () => row.remove());
    container.appendChild(row);
}

function collectFaqRows(containerId) {
    const rows = document.querySelectorAll(`#${containerId} .faq-row`);
    const faq = [];
    for (const row of rows) {
        const q = row.querySelector('.faq-q-input').value.trim();
        const a = row.querySelector('.faq-a-input').value.trim();
        if (q && a) faq.push({ q, a });
    }
    return faq;
}

document.getElementById('new-add-faq-btn').addEventListener('click', () => addFaqRow('new-faq-rows'));
document.getElementById('edit-add-faq-btn').addEventListener('click', () => addFaqRow('edit-faq-rows'));

// ------------------------------------------------------------- add product
document.getElementById('add-product-btn').addEventListener('click', () => {
    document.getElementById('new-name').value = '';
    document.getElementById('new-tagline').value = '';
    document.getElementById('new-price').value = '';
    document.getElementById('new-description').value = '';
    renderFaqRows('new-faq-rows', []);
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
            price: document.getElementById('new-price').value.trim(),
            description: document.getElementById('new-description').value.trim(),
            faq: collectFaqRows('new-faq-rows'),
        }),
    });
    const data = await res.json();
    document.getElementById('add-modal').classList.add('hidden');
    selectedKey = data.key;
    await fetchProducts();
});

// ------------------------------------------------------------ edit product
document.getElementById('edit-save-btn').addEventListener('click', async () => {
    if (!selectedKey) return;
    const name = document.getElementById('edit-name').value.trim();
    if (!name) { alert('กรุณากรอกชื่อสินค้า'); return; }
    await fetch(`/api/products/${selectedKey}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            name,
            tagline: document.getElementById('edit-tagline').value.trim(),
            price: document.getElementById('edit-price').value.trim(),
            description: document.getElementById('edit-description').value.trim(),
            faq: collectFaqRows('edit-faq-rows'),
        }),
    });
    await fetchProducts();
    selectProduct(selectedKey);
});

// -------------------------------------------------------------- upload
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
        document.getElementById('import-log').textContent = `ล้มเหลว: ${err.detail}`;
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
        document.getElementById('import-log').textContent = `เพิ่มข้อมูลเทรนสำเร็จ ${progress.done} ภาพ`;
        document.getElementById('import-progress-wrap').classList.add('hidden');
        pollingProgress = false;
        await fetchProducts();
        selectProduct(selectedKey);
    } else if (progress.status === 'error') {
        document.getElementById('import-log').textContent = `ล้มเหลว: ${progress.message || ''}`;
        document.getElementById('import-progress-wrap').classList.add('hidden');
        pollingProgress = false;
    } else {
        pollingProgress = false;
    }
}

async function deleteProduct(key, name) {
    if (!confirm(`ลบสินค้า "${name}" ออกจากระบบทั้งหมด (รวมข้อมูลเทรน) หรือไม่? การกระทำนี้ย้อนกลับไม่ได้`)) return;
    await fetch(`/api/products/${key}`, { method: 'DELETE' });
    if (selectedKey === key) {
        selectedKey = null;
        document.getElementById('detail-empty').classList.remove('hidden');
        document.getElementById('detail-content').classList.add('hidden');
    }
    await fetchProducts();
}

document.getElementById('clear-samples-btn').addEventListener('click', async () => {
    if (!selectedKey) return;
    const product = products.find(p => p.key === selectedKey);
    if (!confirm(`ลบข้อมูลเทรนทั้งหมดของ "${product.name}" หรือไม่?`)) return;
    await fetch(`/api/products/${selectedKey}/clear_samples`, { method: 'POST' });
    await fetchProducts();
    selectProduct(selectedKey);
});

// ---------------------------------------------------------- live test cam
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

// -------------------------------------------------------- record from cam
function initRecordCamera() {
    const select = document.getElementById('record-camera-select');
    for (const camId of CAMERA_IDS) {
        const opt = document.createElement('option');
        opt.value = camId; opt.textContent = camId;
        select.appendChild(opt);
    }
    const updateImg = () => {
        document.getElementById('record-camera-img').src = '/stream/' + select.value + '?t=' + Date.now();
    };
    select.addEventListener('change', updateImg);
    if (CAMERA_IDS.length > 0) updateImg();
}

document.getElementById('record-start-btn').addEventListener('click', startRecording);

async function startRecording() {
    if (recording || !selectedKey) return;
    const img = document.getElementById('record-camera-img');
    if (!img.naturalWidth) {
        document.getElementById('record-status').textContent = 'ยังไม่พบภาพจากกล้อง กรุณารอสักครู่';
        return;
    }
    recording = true;
    const btn = document.getElementById('record-start-btn');
    btn.disabled = true;
    document.getElementById('record-stage').querySelector('.record-guide').classList.add('recording');

    const canvas = document.getElementById('record-canvas');
    const sx = img.naturalWidth * GUIDE_RECT.x;
    const sy = img.naturalHeight * GUIDE_RECT.y;
    const sw = img.naturalWidth * GUIDE_RECT.w;
    const sh = img.naturalHeight * GUIDE_RECT.h;
    canvas.width = sw;
    canvas.height = sh;
    const ctx = canvas.getContext('2d');

    const blobs = [];
    for (let tick = 0; tick < RECORD_TICKS; tick++) {
        ctx.drawImage(img, sx, sy, sw, sh, 0, 0, sw, sh);
        const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.9));
        if (blob) blobs.push(blob);
        document.getElementById('record-status').textContent =
            `กำลังบันทึก... ${tick + 1}/${RECORD_TICKS} ภาพ (${((RECORD_TICKS - tick - 1) * RECORD_TICK_MS / 1000).toFixed(1)} วินาทีที่เหลือ)`;
        if (tick < RECORD_TICKS - 1) await new Promise((r) => setTimeout(r, RECORD_TICK_MS));
    }

    document.getElementById('record-stage').querySelector('.record-guide').classList.remove('recording');
    btn.disabled = false;
    recording = false;

    if (!blobs.length) {
        document.getElementById('record-status').textContent = 'บันทึกภาพไม่สำเร็จ กรุณาลองใหม่';
        return;
    }
    document.getElementById('record-status').textContent = `บันทึกครบ ${blobs.length} ภาพ กำลังส่งประมวลผล...`;
    const form = new FormData();
    blobs.forEach((blob, i) => form.append('files', blob, `record-${i}.jpg`));
    await startImport(`/api/products/${selectedKey}/upload_images`, form);
}

initTestCamera();
initRecordCamera();
fetchProducts();
setInterval(fetchProducts, 8000);
