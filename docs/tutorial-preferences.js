/* Optional persistence adapter. Offline/privacy restrictions must never stop a lesson. */
window.AMINATE_TUTORIAL_PREFERENCES = Object.freeze({
  read() {
    try { return localStorage.getItem('aminate-tutorial-theme'); }
    catch (_) { return null; }
  },
  write(theme) {
    if (!['system', 'light', 'dark'].includes(theme)) return;
    try { localStorage.setItem('aminate-tutorial-theme', theme); }
    catch (_) { /* The selected theme remains usable for this page. */ }
  }
});
