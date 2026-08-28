// Shared #cam-grid interactions — used by both /booth and /product-view,
// since both pages show a grid of camera panels with the same markup
// (.cam-panel, .cam-icon-btn[data-action=popout|fullscreen]).
//
// "popout" opens the camera in its own window so it can be dragged onto a
// different physical monitor and full-screened there — one browser window
// can only be full-screen on one screen at a time, so showing several
// cameras full-screen across several monitors needs one window per camera.
// "fullscreen" full-screens the panel in place, using whichever screen this
// window currently sits on.
document.getElementById('cam-grid')?.addEventListener('click', (e) => {
    const btn = e.target.closest('.cam-icon-btn');
    if (!btn) return;
    const camId = btn.dataset.cam;

    if (btn.dataset.action === 'popout') {
        window.open(`/booth/camera/${camId}`, `mongdee-cam-${camId}`,
            'width=900,height=680,noopener');
    } else if (btn.dataset.action === 'fullscreen') {
        const panel = document.getElementById(`panel-${camId}`);
        if (!panel) return;
        if (!document.fullscreenElement) {
            (panel.requestFullscreen || panel.webkitRequestFullscreen)?.call(panel);
        } else {
            document.exitFullscreen?.();
        }
    }
});

function updateCamFullscreenIcons() {
    document.querySelectorAll('.cam-icon-btn[data-action="fullscreen"]').forEach((btn) => {
        const camId = btn.dataset.cam;
        const isFs = document.fullscreenElement && document.fullscreenElement.id === `panel-${camId}`;
        btn.innerHTML = iconHtml(isFs ? 'minimize' : 'maximize', { size: 14, className: 'icon-inline' });
        btn.title = isFs ? 'ออกจากโหมดเต็มจอ' : 'ดูกล้องนี้แบบเต็มจอ';
    });
}

document.addEventListener('fullscreenchange', updateCamFullscreenIcons);
document.addEventListener('webkitfullscreenchange', updateCamFullscreenIcons);
