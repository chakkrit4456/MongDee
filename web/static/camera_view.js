const stage = document.getElementById('cam-stage');
const fsBtn = document.getElementById('fullscreen-btn');

function updateFullscreenBtn() {
    const isFs = !!(document.fullscreenElement || document.webkitFullscreenElement);
    fsBtn.innerHTML = iconHtml(isFs ? 'minimize' : 'maximize', { size: 16 }) +
        (isFs ? 'ออกจากเต็มจอ' : 'เต็มจอ');
}

fsBtn.addEventListener('click', () => {
    if (!(document.fullscreenElement || document.webkitFullscreenElement)) {
        (stage.requestFullscreen || stage.webkitRequestFullscreen)?.call(stage);
    } else {
        (document.exitFullscreen || document.webkitExitFullscreen)?.call(document);
    }
});

document.addEventListener('fullscreenchange', updateFullscreenBtn);
document.addEventListener('webkitfullscreenchange', updateFullscreenBtn);
updateFullscreenBtn();

async function pollStatus() {
    try {
        const res = await fetch('/api/state');
        const state = await res.json();
        const info = state.cameras[CAMERA_ID];
        if (info) {
            const dot = document.getElementById(`dot-${CAMERA_ID}`);
            const statusText = document.getElementById(`status-${CAMERA_ID}`);
            if (dot) dot.className = 'status-dot status-' + info.status;
            if (statusText) statusText.textContent = info.message || info.status;
        }
    } catch (e) { /* transient network hiccup — next poll will retry */ }
    setTimeout(pollStatus, 2000);
}

pollStatus();
