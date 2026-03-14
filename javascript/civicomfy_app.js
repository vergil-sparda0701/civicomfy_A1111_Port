/**
 * Civicomfy for Stable Diffusion Automatic1111
 * Self-contained JavaScript - loaded as a regular script
 * v4 - Smart search parsing + rich model cards
 */
(function () {
    'use strict';

    const API = {
        async _post(endpoint, data) {
            const res = await fetch(endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
            const json = await res.json();
            if (!res.ok) throw json;
            return json;
        },
        async _get(endpoint) {
            const res = await fetch(endpoint);
            const json = await res.json();
            if (!res.ok) throw json;
            return json;
        },
        getModelTypes: () => API._get('/civicomfy/model_types'),
        getBaseModels: () => API._get('/civicomfy/base_models'),
        getModelDirs: (modelType) => API._get(`/civicomfy/model_dirs?model_type=${encodeURIComponent(modelType)}`),
        getModelDetails: (params) => API._post('/civicomfy/model_details', params),
        getModelVersions: (modelId, apiKey) => API._get(`/civicomfy/model_versions?model_id=${encodeURIComponent(modelId)}${apiKey ? '&api_key=' + encodeURIComponent(apiKey) : ''}`),
        downloadModel: (params) => API._post('/civicomfy/download', params),
        searchModels: (params) => API._post('/civicomfy/search', params),
        getStatus: () => API._get('/civicomfy/status'),
        cancelDownload: (downloadId) => API._post('/civicomfy/cancel', { download_id: downloadId }),
        retryDownload: (downloadId) => API._post('/civicomfy/retry', { download_id: downloadId }),
        openPath: (downloadId) => API._post('/civicomfy/open_path', { download_id: downloadId }),
        clearHistory: () => API._post('/civicomfy/clear_history', {}),
        loadSettings: () => API._get('/civicomfy/settings'),
        saveSettings: (s) => API._post('/civicomfy/settings', s),
    };

    const Cookies = {
        get(name) { const m = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)')); return m ? decodeURIComponent(m[1]) : null; },
        set(name, value, days = 365) { const exp = new Date(Date.now() + days * 864e5).toUTCString(); document.cookie = `${name}=${encodeURIComponent(value)}; expires=${exp}; path=/; SameSite=Lax`; }
    };

    const SETTINGS_COOKIE = 'civicomfy_settings';
    function getDefaultSettings() { return { apiKey: '', numConnections: 1, defaultModelType: 'checkpoint', autoOpenStatusTab: false, hideMatureInSearch: true, nsfwBlurMinLevel: 4, autoInjectTriggers: true, showNsfwUnblurred: false }; }

    // Load from cookie immediately (fast, available before server responds)
    function loadSettingsFromCookie() {
        try { const r = Cookies.get(SETTINGS_COOKIE); if (r) return { ...getDefaultSettings(), ...JSON.parse(r) }; } catch (_) {}
        return getDefaultSettings();
    }
    function loadSettings() { return loadSettingsFromCookie(); }

    // Save to both server (persistent) and cookie (fast next-load)
    function saveSettings(s) {
        Cookies.set(SETTINGS_COOKIE, JSON.stringify(s));
        API.saveSettings(s).catch(err => console.warn('[Civicomfy] Could not persist settings to server:', err));
    }

    // Load settings from server and merge (called async after init)
    async function syncSettingsFromServer() {
        try {
            const res = await API.loadSettings();
            if (res && res.success && res.settings && Object.keys(res.settings).length > 0) {
                settings = { ...getDefaultSettings(), ...res.settings };
                // Update cookie with server values so next load is fast
                Cookies.set(SETTINGS_COOKIE, JSON.stringify(settings));
                applySettingsToForm();
                console.log('[Civicomfy] Settings loaded from server.');
            }
        } catch (e) { console.warn('[Civicomfy] Could not load settings from server, using cookie/defaults.', e); }
    }

    // ---- Smart Query Parser ----
    // Detects patterns like "morrigan outfit daniel20019" where the last token looks like a username handle
    function parseSearchQuery(raw) {
        const trimmed = raw.trim();
        const result = { query: trimmed, username: null, parsed: false, hint: null };
        if (!trimmed) return result;
        const words = trimmed.split(/\s+/);
        if (words.length < 2) return result;
        const last = words[words.length - 1];
        // Username heuristic: word ending in digits, or word+digits pattern (e.g. daniel20019, artist42, myUser_123)
        const isUsernameToken = /^[a-zA-Z_][a-zA-Z0-9_]{1,}[0-9]{1,}[a-zA-Z0-9_]*$/.test(last) || /^[a-zA-Z0-9_]{2,}[0-9]{3,}$/.test(last);
        if (isUsernameToken) {
            result.query = words.slice(0, -1).join(' ');
            result.username = last;
            result.parsed = true;
            result.hint = `🔍 Buscando <strong>"${escHtml(result.query)}"</strong> del creador <strong>"${escHtml(last)}"</strong>`;
        }
        return result;
    }

    // ---- CSS ----
    const CSS = `
.civicomfy-overlay{position:fixed;z-index:9000;left:0;top:0;width:100%;height:100%;background:rgba(0,0,0,.65);display:flex;justify-content:center;align-items:center;opacity:0;visibility:hidden;transition:opacity .3s,visibility 0s .3s}
.civicomfy-overlay.open{opacity:1;visibility:visible;transition:opacity .3s}
.civicomfy-modal-content{background:var(--background-fill-primary,#1a1a2e);color:var(--body-text-color,#e0e0e0);border-radius:10px;box-shadow:0 8px 32px rgba(0,0,0,.5);width:980px;max-width:96%;height:760px;max-height:93vh;display:flex;flex-direction:column;overflow:hidden}
.civicomfy-header{display:flex;justify-content:space-between;align-items:center;padding:14px 20px;border-bottom:1px solid var(--border-color-primary,#333);flex-shrink:0}
.civicomfy-header h2{margin:0;font-size:1.25em}
.civicomfy-close{background:none;border:none;color:#aaa;font-size:26px;cursor:pointer;padding:0 6px;line-height:1}.civicomfy-close:hover{color:#fff}
.civicomfy-body{display:flex;flex-direction:column;flex:1;overflow:hidden}
.civicomfy-tabs{display:flex;border-bottom:1px solid var(--border-color-primary,#333);padding:0 14px;flex-shrink:0}
.civicomfy-tab{padding:10px 16px;cursor:pointer;border:none;background:none;color:#aaa;opacity:.7;position:relative;top:1px;margin-bottom:-1px}
.civicomfy-tab.active{opacity:1;border-bottom:3px solid #5c8aff;font-weight:bold;color:#fff}
.civicomfy-tab:hover{opacity:1}
.civicomfy-tab-content{display:none;flex:1;overflow-y:auto;padding:18px 20px}
.civicomfy-tab-content.active{display:flex;flex-direction:column}
.civicomfy-form-group{display:flex;flex-direction:column;margin-bottom:14px}
.civicomfy-form-group.inline{flex-direction:row;align-items:center;gap:8px}
.civicomfy-form-group label{font-size:.87em;color:#bbb;margin-bottom:5px}
.civicomfy-form-row{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:14px;margin-bottom:4px}
.civicomfy-input,.civicomfy-select{width:100%;padding:8px 10px;background:var(--input-background-fill,#2a2a3e);color:var(--body-text-color,#e0e0e0);border:1px solid var(--border-color-primary,#444);border-radius:5px;font-size:.9em;box-sizing:border-box}
.civicomfy-select{cursor:pointer}
.civicomfy-input:focus,.civicomfy-select:focus{outline:none;border-color:#5c8aff}
.civicomfy-button{padding:8px 18px;border:none;border-radius:5px;cursor:pointer;font-size:.9em;transition:opacity .2s}
.civicomfy-button.primary{background:#5c8aff;color:#fff}.civicomfy-button.primary:hover{background:#4a78ee}
.civicomfy-button.danger{background:#c44}.civicomfy-button.danger:hover{background:#a33}
.civicomfy-button.small{padding:5px 10px;font-size:.82em}
.civicomfy-button:disabled{opacity:.5;cursor:not-allowed}
.civicomfy-hint{font-size:.82em;color:#888;margin:4px 0 0}
.civicomfy-checkbox{width:16px;height:16px;cursor:pointer}
.civicomfy-search-controls{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:8px}
.civicomfy-search-controls .civicomfy-input{flex:2;min-width:200px}
.civicomfy-search-controls .civicomfy-select{flex:1;min-width:130px}
.civicomfy-parse-hint{font-size:.84em;color:#7eb8ff;background:rgba(92,138,255,.08);border:1px solid rgba(92,138,255,.25);border-radius:6px;padding:7px 13px;margin-bottom:10px;line-height:1.5}

/* ---- Horizontal List Cards ---- */
.civicomfy-search-results{display:flex;flex-direction:column;gap:12px;flex:1;overflow-y:auto;align-content:start;padding-bottom:10px}
.civicomfy-search-results *{box-sizing:border-box}
.civicomfy-search-card{background:var(--input-background-fill,#23233a);border-radius:10px;border:1px solid rgba(255,255,255,.08);display:flex;flex-direction:row;gap:0;overflow:hidden;transition:box-shadow .18s,border-color .18s;min-height:160px;align-items:stretch}
.civicomfy-search-card:hover{box-shadow:0 4px 20px rgba(92,138,255,.28);border-color:rgba(92,138,255,.5)}
/* Thumbnail */
.civicomfy-card-thumb{position:relative;width:160px;min-width:160px;min-height:160px;background:#111;flex-shrink:0;overflow:hidden;align-self:stretch}
.civicomfy-card-thumb img{width:100%;height:100%;object-fit:cover;transition:transform .3s}
.civicomfy-card-thumb img.civicomfy-nsfw-blur{filter:blur(8px)}
.civicomfy-nsfw-show-all .civicomfy-card-thumb img.civicomfy-nsfw-blur{filter:none}
.civicomfy-search-card:hover .civicomfy-card-thumb img{transform:scale(1.04)}
.civicomfy-card-thumb-ph{width:100%;height:100%;display:flex;align-items:center;justify-content:center;font-size:2.5em;color:#333}
.civicomfy-card-badge-type{position:absolute;bottom:6px;left:6px;background:rgba(92,138,255,.9);color:#fff;font-size:.68em;padding:2px 9px;border-radius:10px;font-weight:700;letter-spacing:.3px}
.civicomfy-card-badge-nsfw{position:absolute;top:6px;right:6px;background:rgba(180,0,50,.88);color:#fff;font-size:.66em;padding:2px 7px;border-radius:10px}
/* Main info area */
.civicomfy-card-body{padding:12px 16px;display:flex;flex-direction:column;gap:5px;flex:1;min-width:0;align-self:stretch;justify-content:center}
.civicomfy-card-title{font-size:1em;font-weight:700;line-height:1.3;color:#eee;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.civicomfy-card-meta-line{display:flex;align-items:center;gap:10px;flex-wrap:wrap;font-size:.79em;color:#888}
.civicomfy-card-meta-line span{display:flex;align-items:center;gap:3px}
.civicomfy-card-tags{display:flex;flex-wrap:wrap;gap:5px;margin-top:3px}
.cchip{font-size:.7em;padding:2px 9px;border-radius:10px;white-space:nowrap;font-weight:500}
.cchip-base{background:rgba(92,138,255,.14);color:#8ab4ff;border:1px solid rgba(92,138,255,.28)}
.cchip-tag{background:rgba(255,255,255,.06);color:#aaa;border:1px solid rgba(255,255,255,.1)}
.civicomfy-card-triggers{font-size:.76em;color:#a8c0d8;margin-top:4px;line-height:1.5;display:-webkit-box;-webkit-line-clamp:1;-webkit-box-orient:vertical;overflow:hidden}
.civicomfy-card-triggers b{color:#7eb8ff}
/* Version buttons panel */
.civicomfy-card-versions{display:flex;flex-direction:column;align-items:flex-end;gap:6px;padding:12px 14px;flex-shrink:0;min-width:220px;max-width:260px;justify-content:center;align-self:stretch}
/* Version dropdown row */
.civicomfy-ver-row{display:flex;align-items:center;gap:0;width:100%;border-radius:7px;border:1px solid rgba(92,138,255,.35);overflow:hidden;background:rgba(20,30,60,.5)}
.civicomfy-ver-select-wrap{display:flex;align-items:center;flex:1;min-width:0;overflow:hidden}
.civicomfy-ver-badge-display{background:#2a3a6a;color:#a8c4ff;font-size:.78em;padding:0 9px;font-weight:700;white-space:nowrap;border-right:1px solid rgba(92,138,255,.3);height:100%;display:flex;align-items:center;min-height:30px;flex-shrink:0}
.civicomfy-ver-select{flex:1;min-width:0;background:transparent;color:#e0eaff;border:none;outline:none;font-size:.78em;padding:6px 6px 6px 4px;cursor:pointer;appearance:auto;-webkit-appearance:auto}
.civicomfy-ver-select option{background:#1e2a4a;color:#e0eaff}
.civicomfy-ver-dl-btn{background:rgba(92,138,255,.2);color:#7eb8ff;border:none;border-left:1px solid rgba(92,138,255,.3);padding:0 12px;cursor:pointer;font-size:1.1em;transition:background .18s;display:flex;align-items:center;justify-content:center;min-height:30px;flex-shrink:0}
.civicomfy-ver-dl-btn:hover{background:rgba(92,138,255,.45);color:#fff}
.civicomfy-ver-more-btn{display:flex;align-items:center;justify-content:center;gap:5px;padding:5px 10px;border-radius:7px;border:1px solid rgba(255,255,255,.15);background:rgba(255,255,255,.04);color:#bbb;cursor:pointer;font-size:.76em;transition:background .18s;width:100%}
.civicomfy-ver-more-btn:hover{background:rgba(255,255,255,.09);color:#ddd}
.civicomfy-view-link{display:flex;align-items:center;gap:4px;font-size:.78em;color:#c8d8ff;text-decoration:none;padding:4px 10px;cursor:pointer;background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.15);border-radius:6px;margin-bottom:3px;transition:background .18s}
.civicomfy-view-link:hover{background:rgba(255,255,255,.09);color:#fff}

.civicomfy-status-section{margin-bottom:20px}
.civicomfy-status-section h3{font-size:1em;margin-bottom:10px;color:#ccc;border-bottom:1px solid #333;padding-bottom:5px}
.civicomfy-download-list{display:flex;flex-direction:column;gap:8px}
.civicomfy-download-item{background:var(--input-background-fill,#2a2a3e);border-radius:7px;padding:10px 14px;border:1px solid #333}
.civicomfy-download-item-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}
.civicomfy-download-item-name{font-weight:bold;font-size:.9em;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;max-width:70%}
.civicomfy-download-item-status{font-size:.8em;padding:2px 8px;border-radius:10px}
.civicomfy-status-queued{background:#444;color:#ccc}
.civicomfy-status-downloading{background:#1a4a1a;color:#4caf50}
.civicomfy-status-completed{background:#1a2a4a;color:#5c8aff}
.civicomfy-status-failed{background:#4a1a1a;color:#f44}
.civicomfy-status-cancelled{background:#3a3a1a;color:#aaa}
.civicomfy-progress-bar{height:5px;background:#333;border-radius:3px;overflow:hidden;margin-bottom:6px}
.civicomfy-progress-fill{height:100%;background:#5c8aff;transition:width .3s}
.civicomfy-download-item-actions{display:flex;gap:6px;margin-top:6px}
.civicomfy-download-item-meta{font-size:.78em;color:#888}
.civicomfy-settings-container{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:20px}
.civicomfy-settings-section h4{font-size:.95em;color:#bbb;margin-bottom:10px;border-bottom:1px solid #333;padding-bottom:5px}
.civicomfy-toast{position:absolute;bottom:16px;left:50%;transform:translateX(-50%) translateY(20px);background:#333;color:#fff;padding:10px 20px;border-radius:6px;font-size:.88em;opacity:0;pointer-events:none;transition:opacity .3s,transform .3s;z-index:10;white-space:nowrap}
.civicomfy-toast.show{opacity:1;transform:translateX(-50%) translateY(0)}
.civicomfy-toast.success{background:#1a4a1a;border:1px solid #4caf50}
.civicomfy-toast.error{background:#4a1a1a;border:1px solid #f44}
.civicomfy-toast.info{background:#1a2a4a;border:1px solid #5c8aff}
.civicomfy-preview-box{display:flex;gap:16px;align-items:flex-start;background:var(--input-background-fill,#2a2a3e);border-radius:8px;padding:14px;border:1px solid #333}
.civicomfy-preview-box img{width:120px;height:120px;object-fit:cover;border-radius:6px;flex-shrink:0}
.civicomfy-preview-info{flex:1;min-width:0}
.civicomfy-preview-info h4{margin:0 0 6px;font-size:1em;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}
.civicomfy-preview-info p{margin:2px 0;font-size:.83em;color:#aaa}
.civicomfy-file-select-row{margin-top:10px}
.civicomfy-open-btn{background:#2a3a5a;color:#5c8aff;padding:6px 14px;border:1px solid #5c8aff;border-radius:5px;cursor:pointer;font-size:.82em}
.civicomfy-open-btn:hover{background:#3a4a6a}
#civicomfy-open-btn{position:fixed;bottom:20px;right:20px;z-index:8999;background:#5c8aff;color:#fff;border:none;border-radius:8px;padding:10px 16px;cursor:pointer;font-size:.9em;box-shadow:0 2px 10px rgba(92,138,255,.4)}
#civicomfy-open-btn:hover{background:#4a78ee}
`;

    // ---- State ----
    let settings = loadSettings();
    let modelTypes = {};
    let baseModels = [];
    let searchPagination = { currentPage: 1, totalPages: 1, limit: 20 };
    let statusInterval = null;
    let previewDebounce = null;
    let overlay = null;
    let toastTimeout = null;
    let lastParsed = null;
    // Track download IDs already processed for trigger-word injection (avoid double-injection on re-render)
    const processedTriggerInjections = new Set();

    // ---- Init ----
    function init() {
        injectCSS();
        createOverlay();
        createOpenButton();
        loadModelTypesAndBaseModels();
        // Async: override cookie values with server-persisted settings
        syncSettingsFromServer();
    }

    function injectCSS() {
        if (document.getElementById('civicomfy-styles')) return;
        const s = document.createElement('style');
        s.id = 'civicomfy-styles';
        s.textContent = CSS;
        document.head.appendChild(s);
    }

    function buildModalHTML(s) {
        return `
<div class="civicomfy-modal-content">
  <div class="civicomfy-header"><h2>🎨 Civicomfy</h2><button class="civicomfy-close" id="civicomfy-close">&times;</button></div>
  <div class="civicomfy-body">
    <div class="civicomfy-tabs">
      <button class="civicomfy-tab active" data-tab="download">⬇ Download</button>
      <button class="civicomfy-tab" data-tab="search">🔍 Search</button>
      <button class="civicomfy-tab" data-tab="status">📋 Status <span id="civicomfy-status-indicator" style="display:none">(<span id="civicomfy-active-count">0</span>)</span></button>
      <button class="civicomfy-tab" data-tab="settings">⚙️ Settings</button>
    </div>
    <!-- DOWNLOAD TAB -->
    <div id="civicomfy-tab-download" class="civicomfy-tab-content active">
      <div class="civicomfy-form-group"><label>Model URL or ID</label><input type="text" id="civicomfy-model-url" class="civicomfy-input" placeholder="https://civitai.com/models/12345 or just the ID"></div>
      <p class="civicomfy-hint">You can specify a version with ?modelVersionId=xxxxx in the URL or the field below.</p>
      <div class="civicomfy-form-row">
        <div class="civicomfy-form-group"><label>Model Type (Save Location)</label><select id="civicomfy-model-type" class="civicomfy-select" required></select></div>
        <div class="civicomfy-form-group"><label>Save Subfolder</label><select id="civicomfy-subdir-select" class="civicomfy-select"><option value="">(root)</option></select><p id="civicomfy-save-base-path" class="civicomfy-hint" style="word-break:break-all"></p></div>
        <div class="civicomfy-form-group"><label>Version ID (Optional)</label><input type="number" id="civicomfy-model-version-id" class="civicomfy-input" placeholder="Overrides URL / uses latest"></div>
      </div>
      <div class="civicomfy-form-row"><div class="civicomfy-form-group"><label>Custom Filename (Optional)</label><input type="text" id="civicomfy-custom-filename" class="civicomfy-input" placeholder="Leave blank to use original name"></div></div>
      <div class="civicomfy-form-group inline"><input type="checkbox" id="civicomfy-force-redownload" class="civicomfy-checkbox"><label for="civicomfy-force-redownload">Force Re-download (if exists)</label></div>
      <div id="civicomfy-download-preview-area" style="margin-top:20px;padding-top:15px;border-top:1px solid var(--border-color,#444)"></div>
      <button id="civicomfy-download-submit" class="civicomfy-button primary">Start Download</button>
    </div>
    <!-- SEARCH TAB -->
    <div id="civicomfy-tab-search" class="civicomfy-tab-content">
      <div class="civicomfy-search-controls">
        <input type="text" id="civicomfy-search-query" class="civicomfy-input" placeholder='Ej: "morrigan outfit daniel20019" — detecta creador automáticamente'>
        <select id="civicomfy-search-type" class="civicomfy-select"><option value="any">Any Type</option></select>
        <select id="civicomfy-search-base-model" class="civicomfy-select"><option value="any">Any Base Model</option></select>
        <select id="civicomfy-search-sort" class="civicomfy-select">
          <option value="Most Downloaded">Most Downloaded</option>
          <option value="Highest Rated">Highest Rated</option>
          <option value="Newest">Newest</option>
          <option value="Most Liked">Most Liked</option>
          <option value="Most Discussed">Most Discussed</option>
          <option value="Most Collected">Most Collected</option>
          <option value="Most Buzz">Most Buzz</option>
          <option value="Relevancy">Relevancy</option>
        </select>
        <button id="civicomfy-search-submit" class="civicomfy-button primary">Search</button>
      </div>
      <div id="civicomfy-search-parse-hint" class="civicomfy-parse-hint" style="display:none"></div>
      <div id="civicomfy-search-results" class="civicomfy-search-results"></div>
      <div id="civicomfy-search-pagination" style="text-align:center;margin-top:20px"></div>
    </div>
    <!-- STATUS TAB -->
    <div id="civicomfy-tab-status" class="civicomfy-tab-content">
      <div class="civicomfy-status-section"><h3>Active Downloads</h3><div id="civicomfy-active-list" class="civicomfy-download-list"><p>No active downloads.</p></div></div>
      <div class="civicomfy-status-section"><h3>Queued Downloads</h3><div id="civicomfy-queued-list" class="civicomfy-download-list"><p>Queue is empty.</p></div></div>
      <div class="civicomfy-status-section">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px"><h3>Download History</h3><button id="civicomfy-clear-history-btn" class="civicomfy-button danger small">🗑 Clear History</button></div>
        <div id="civicomfy-history-list" class="civicomfy-download-list"><p>No download history yet.</p></div>
      </div>
    </div>
    <!-- SETTINGS TAB -->
    <div id="civicomfy-tab-settings" class="civicomfy-tab-content">
      <div class="civicomfy-settings-container">
        <div class="civicomfy-settings-section">
          <h4>API &amp; Defaults</h4>
          <div class="civicomfy-form-group"><label>Civitai API Key (Optional)</label><input type="password" id="civicomfy-settings-api-key" class="civicomfy-input" placeholder="For authenticated access" autocomplete="new-password"><p class="civicomfy-hint">Leave blank to use env <code>CIVITAI_API_KEY</code>.</p></div>
          <div class="civicomfy-form-group"><label>Default Model Type</label><select id="civicomfy-settings-default-type" class="civicomfy-select"></select></div>
        </div>
        <div class="civicomfy-settings-section">
          <h4>Interface &amp; Search</h4>
          <div class="civicomfy-form-group inline"><input type="checkbox" id="civicomfy-settings-auto-open" class="civicomfy-checkbox"><label for="civicomfy-settings-auto-open">Switch to Status tab after starting download</label></div>
          <div class="civicomfy-form-group inline"><input type="checkbox" id="civicomfy-settings-hide-mature" class="civicomfy-checkbox" ${s.hideMatureInSearch ? 'checked' : ''}><label for="civicomfy-settings-hide-mature">Hide Mature (R-rated) images in search</label></div>
          <div class="civicomfy-form-group inline"><input type="checkbox" id="civicomfy-settings-auto-inject" class="civicomfy-checkbox" ${s.autoInjectTriggers !== false ? 'checked' : ''}><label for="civicomfy-settings-auto-inject">Auto-add trigger words to the prompt upon completion of download</label></div>
          <div class="civicomfy-form-group inline"><input type="checkbox" id="civicomfy-settings-show-nsfw-unblurred" class="civicomfy-checkbox" ${s.showNsfwUnblurred ? 'checked' : ''}><label for="civicomfy-settings-show-nsfw-unblurred">Show NSFW images without blur (18+)</label></div>
         <div class="civicomfy-form-group"><label>NSFW Blur Threshold</label><input type="number" id="civicomfy-settings-nsfw-threshold" class="civicomfy-input" value="${s.nsfwBlurMinLevel || 4}" min="0" max="128" step="1"><p class="civicomfy-hint">Blur thumbnails when nsfwLevel &ge; this value (ignored if the option above is enabled).</p></div>
        </div>
      </div>
      <button id="civicomfy-settings-save" class="civicomfy-button primary" style="margin-top:20px">Save Settings</button>
    </div>
  </div>
  <div id="civicomfy-toast" class="civicomfy-toast"></div>
</div>`;
    }

    function createOverlay() {
        overlay = document.createElement('div');
        overlay.className = 'civicomfy-overlay';
        overlay.id = 'civicomfy-overlay';
        overlay.innerHTML = buildModalHTML(settings);
        document.body.appendChild(overlay);
        overlay.addEventListener('click', (e) => { if (e.target === overlay) closeModal(); });
        setupEventListeners();
        applySettingsToForm();
    }

    function createOpenButton() {
        const btn = document.createElement('button');
        btn.id = 'civicomfy-open-btn';
        btn.textContent = '🎨 Civicomfy';
        btn.title = 'Open Civicomfy';
        btn.onclick = openModal;
        document.body.appendChild(btn);
        tryAddToA1111Toolbar();
    }

    function tryAddToA1111Toolbar() {
        const tryInsert = () => {
            const tabBar = document.querySelector('#tabs .tab-nav');
            if (tabBar && !document.getElementById('civicomfy-tab-btn')) {
                const b = document.createElement('button');
                b.id = 'civicomfy-tab-btn';
                b.textContent = '🎨 Civicomfy';
                b.className = 'lg svelte-1hnfib2';
                b.style.cssText = 'background:#5c8aff;color:#fff;border-color:#5c8aff';
                b.onclick = openModal;
                tabBar.appendChild(b);
            }
        };
        tryInsert(); setTimeout(tryInsert, 1000); setTimeout(tryInsert, 3000);
    }

    function openModal() { overlay.classList.add('open'); startStatusPolling(); loadAndPopulateSubdirs(); if (settings.showNsfwUnblurred) overlay.classList.add('civicomfy-nsfw-show-all'); else overlay.classList.remove('civicomfy-nsfw-show-all'); }
    function closeModal() { overlay.classList.remove('open'); stopStatusPolling(); }

    function switchTab(t) {
        overlay.querySelectorAll('.civicomfy-tab').forEach(x => x.classList.toggle('active', x.dataset.tab === t));
        overlay.querySelectorAll('.civicomfy-tab-content').forEach(x => x.classList.toggle('active', x.id === `civicomfy-tab-${t}`));
    }

    function showToast(msg, type = 'info', dur = 3500) {
        const toast = overlay.querySelector('#civicomfy-toast');
        if (!toast) return;
        clearTimeout(toastTimeout);
        toast.textContent = msg;
        toast.className = `civicomfy-toast ${type} show`;
        toastTimeout = setTimeout(() => toast.classList.remove('show'), dur);
    }

    async function loadModelTypesAndBaseModels() {
        try {
            const [types, bases] = await Promise.all([API.getModelTypes(), API.getBaseModels()]);
            modelTypes = types; baseModels = bases;
            populateModelTypeSelects(); populateBaseModelSelect();
        } catch (e) { console.error('[Civicomfy] Failed to load types/base models:', e); }
    }

    function populateModelTypeSelects() {
        const sorted = Object.entries(modelTypes).sort((a, b) => a[1].localeCompare(b[1]));
        const dl = overlay.querySelector('#civicomfy-model-type');
        const sr = overlay.querySelector('#civicomfy-search-type');
        const st = overlay.querySelector('#civicomfy-settings-default-type');
        if (dl) dl.innerHTML = '';
        if (st) st.innerHTML = '';
        if (sr) sr.innerHTML = '<option value="any">Any Type</option>';
        sorted.forEach(([key, name]) => {
            const mk = (v, t) => { const o = document.createElement('option'); o.value = v; o.textContent = t; return o; };
            if (dl) dl.appendChild(mk(key, name));
            if (sr) sr.appendChild(mk(key, name));
            if (st) st.appendChild(mk(key, name));
        });
        if (dl && settings.defaultModelType && dl.querySelector(`option[value="${settings.defaultModelType}"]`)) dl.value = settings.defaultModelType;
        if (st && settings.defaultModelType) st.value = settings.defaultModelType;
        loadAndPopulateSubdirs();
    }

    function populateBaseModelSelect() {
        const sel = overlay.querySelector('#civicomfy-search-base-model');
        if (!sel) return;
        sel.innerHTML = '<option value="any">Any Base Model</option>';
        baseModels.forEach(bm => { const o = document.createElement('option'); o.value = bm; o.textContent = bm; sel.appendChild(o); });
    }

    async function loadAndPopulateSubdirs() {
        const ts = overlay.querySelector('#civicomfy-model-type');
        const ss = overlay.querySelector('#civicomfy-subdir-select');
        const bp = overlay.querySelector('#civicomfy-save-base-path');
        if (!ts || !ss) return;
        try {
            const r = await API.getModelDirs(ts.value);
            if (r.success) {
                ss.innerHTML = '<option value="">(root)</option>';
                r.subdirs.forEach(sd => { if (!sd) return; const o = document.createElement('option'); o.value = sd; o.textContent = sd; ss.appendChild(o); });
                if (bp) bp.textContent = r.base_dir || '';
            }
        } catch (e) {}
    }

    function setupEventListeners() {
        const q = id => overlay.querySelector('#' + id);
        q('civicomfy-close').addEventListener('click', closeModal);
        overlay.querySelectorAll('.civicomfy-tab').forEach(t => t.addEventListener('click', () => switchTab(t.dataset.tab)));
        overlay.querySelector('#civicomfy-model-type').addEventListener('change', loadAndPopulateSubdirs);
        const debouncePrev = () => { clearTimeout(previewDebounce); previewDebounce = setTimeout(fetchAndRenderPreview, 600); };
        q('civicomfy-model-url').addEventListener('input', debouncePrev);
        q('civicomfy-model-version-id').addEventListener('input', debouncePrev);
        q('civicomfy-download-submit').addEventListener('click', handleDownloadSubmit);
        q('civicomfy-search-submit').addEventListener('click', () => { searchPagination.currentPage = 1; lastParsed = null; handleSearchSubmit(); });
        q('civicomfy-search-query').addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); searchPagination.currentPage = 1; lastParsed = null; handleSearchSubmit(); } });
        q('civicomfy-settings-save').addEventListener('click', handleSettingsSave);
        q('civicomfy-clear-history-btn').addEventListener('click', handleClearHistory);
    }

    async function fetchAndRenderPreview() {
        const url = overlay.querySelector('#civicomfy-model-url').value.trim();
        const vid = overlay.querySelector('#civicomfy-model-version-id').value.trim();
        const area = overlay.querySelector('#civicomfy-download-preview-area');
        if (!url) { area.innerHTML = ''; return; }
        area.innerHTML = '<p style="color:#888">⏳ Loading model details...</p>';
        try {
            const r = await API.getModelDetails({ model_url_or_id: url, model_version_id: vid ? parseInt(vid, 10) : null, api_key: settings.apiKey });
            if (r && r.success) { renderDownloadPreview(r); autoSelectModelType(r.model_type); }
            else area.innerHTML = `<p style="color:#f66">❌ ${r.error || 'Could not fetch details'}</p>`;
        } catch (e) { area.innerHTML = `<p style="color:#f66">❌ ${e.error || e.message || 'Error'}</p>`; }
    }

    function renderDownloadPreview(r) {
        const area = overlay.querySelector('#civicomfy-download-preview-area');
        const tw = (r.trained_words || []).slice(0, 10).join(', ');
        const tags = (r.tags || []).slice(0, 8).join(', ');
        let filesHtml = '';
        if (r.files && r.files.length > 1) {
            filesHtml = `<div class="civicomfy-file-select-row"><label style="font-size:.83em;color:#aaa">File:</label><select id="civicomfy-file-select" class="civicomfy-select" style="margin-top:5px">${r.files.map(f => `<option value="${f.id || ''}"${f.primary ? ' selected' : ''}>${f.name} (${(f.sizeKB/1024).toFixed(0)}MB)</option>`).join('')}</select></div>`;
        }
        area.innerHTML = `<div class="civicomfy-preview-box">${r.thumbnail ? `<img src="${r.thumbnail}" alt="preview" onerror="this.style.display='none'">` : ''}<div class="civicomfy-preview-info"><h4>${escHtml(r.model_name || 'Unknown')}</h4><p>Version: ${escHtml(r.version_name || '')}</p>${r.model_type ? `<p>Type: ${escHtml(r.model_type)}</p>` : ''}${r.base_model ? `<p>Base: ${escHtml(r.base_model)}</p>` : ''}${tw ? `<p>Trigger words: <em>${escHtml(tw)}</em></p>` : ''}${tags ? `<p>Tags: ${escHtml(tags)}</p>` : ''}${filesHtml}</div></div>`;
    }

    function autoSelectModelType(civitaiType) {
        if (!civitaiType) return;
        const map = { 'Checkpoint': 'checkpoint', 'LORA': 'lora', 'LoCon': 'locon', 'VAE': 'vae', 'TextualInversion': 'embedding', 'Hypernetwork': 'hypernetwork', 'Controlnet': 'controlnet', 'Upscaler': 'upscaler', 'MotionModule': 'motionmodule' };
        const key = map[civitaiType];
        if (!key) return;
        const sel = overlay.querySelector('#civicomfy-model-type');
        if (sel && sel.querySelector(`option[value="${key}"]`)) { sel.value = key; loadAndPopulateSubdirs(); }
    }

    async function handleDownloadSubmit() {
        const btn = overlay.querySelector('#civicomfy-download-submit');
        const url = overlay.querySelector('#civicomfy-model-url').value.trim();
        if (!url) { showToast('Model URL or ID cannot be empty.', 'error'); return; }
        btn.disabled = true; btn.textContent = 'Starting...';
        const fe = overlay.querySelector('#civicomfy-file-select');
        const params = {
            model_url_or_id: url,
            model_type: overlay.querySelector('#civicomfy-model-type').value,
            model_version_id: overlay.querySelector('#civicomfy-model-version-id').value ? parseInt(overlay.querySelector('#civicomfy-model-version-id').value, 10) : null,
            custom_filename: overlay.querySelector('#civicomfy-custom-filename').value.trim(),
            subdir: overlay.querySelector('#civicomfy-subdir-select').value.trim(),
            num_connections: 1,
            force_redownload: overlay.querySelector('#civicomfy-force-redownload').checked,
            api_key: settings.apiKey,
        };
        if (fe && fe.value) { const fid = parseInt(fe.value, 10); if (!isNaN(fid)) params.file_id = fid; }
        try {
            const r = await API.downloadModel(params);
            if (r.status === 'queued') { showToast(`✅ Download queued: ${r.details?.filename || 'Model'}`, 'success'); if (settings.autoOpenStatusTab) switchTab('status'); }
            else if (r.status === 'exists' || r.status === 'exists_size_mismatch') showToast(r.message, 'info', 5000);
            else showToast(`Status: ${r.status}`, 'info');
        } catch (e) { showToast(`❌ ${e.error || e.message || 'Unknown error'}`, 'error', 6000); }
        finally { btn.disabled = false; btn.textContent = 'Start Download'; }
    }

    // ---- Search with smart username detection ----
    async function handleSearchSubmit() {
        const btn = overlay.querySelector('#civicomfy-search-submit');
        const resultsEl = overlay.querySelector('#civicomfy-search-results');
        const paginEl = overlay.querySelector('#civicomfy-search-pagination');
        const hintEl = overlay.querySelector('#civicomfy-search-parse-hint');
        const rawQuery = overlay.querySelector('#civicomfy-search-query').value.trim();

        const parsed = (searchPagination.currentPage === 1 || !lastParsed)
            ? parseSearchQuery(rawQuery)
            : lastParsed;
        if (searchPagination.currentPage === 1) lastParsed = parsed;

        if (hintEl) {
            if (parsed.parsed) { hintEl.innerHTML = parsed.hint; hintEl.style.display = ''; }
            else hintEl.style.display = 'none';
        }

        btn.disabled = true; btn.textContent = 'Searching...';
        resultsEl.innerHTML = '<p style="color:#888;grid-column:1/-1">⏳ Searching...</p>';
        paginEl.innerHTML = '';

        const typeVal = overlay.querySelector('#civicomfy-search-type').value;
        const baseModelVal = overlay.querySelector('#civicomfy-search-base-model').value;

        const params = {
            query: parsed.query || rawQuery,
            model_types: typeVal === 'any' ? [] : [typeVal],
            base_models: baseModelVal === 'any' ? [] : [baseModelVal],
            sort: overlay.querySelector('#civicomfy-search-sort').value,
            limit: searchPagination.limit,
            page: searchPagination.currentPage,
            api_key: settings.apiKey,
            nsfw: settings.hideMatureInSearch ? false : null,
        };
        if (parsed.username) params.username = parsed.username;

        try {
            let response = await API.searchModels(params);
            if (!response || !response.metadata || !Array.isArray(response.items)) throw new Error('Invalid response');

            // Fallback: if creator filter yielded no results, retry without it
            if (response.items.length === 0 && parsed.username) {
                hintEl.innerHTML = `⚠️ Sin resultados para el creador <strong>"${escHtml(parsed.username)}"</strong>. Mostrando resultados generales para <strong>"${escHtml(parsed.query)}"</strong>.`;
                const fallbackParams = { ...params };
                delete fallbackParams.username;
                response = await API.searchModels(fallbackParams);
            }

            renderSearchResults(response.items);
            renderSearchPagination(response.metadata);
        } catch (e) {
            resultsEl.innerHTML = `<p style="color:#f66;grid-column:1/-1">❌ Search failed: ${e.error || e.message || 'Unknown error'}</p>`;
        } finally {
            btn.disabled = false; btn.textContent = 'Search';
        }
    }

    // Max version buttons shown before "All versions" collapse
    const MAX_VER_SHOWN = 3;

    function buildCardHTML(item) {
        const thumb = item.thumbnailUrl || '';
        const name = escHtml(item.name || 'Unknown');
        const type = escHtml(item.type || '');
        const creator = escHtml((item.creator && item.creator.username) || (item.user && item.user.username) || '');
        const dlCount = ((item.metrics && item.metrics.downloadCount) || (item.stats && item.stats.downloadCount) || 0).toLocaleString();
        const likeCount = ((item.metrics && item.metrics.favoriteCount) || (item.stats && (item.stats.favoriteCount || item.stats.thumbsUpCount)) || 0).toLocaleString();
        const commentCount = ((item.metrics && item.metrics.commentCount) || (item.stats && item.stats.commentCount) || 0).toLocaleString();
        const buzzCount = ((item.metrics && item.metrics.tippedAmountCount) || 0).toLocaleString();
        const date = item.publishedAt ? new Date(item.publishedAt).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : '';

        const trainedWords = (
            (item.version && item.version.trainedWords) ||
            (item.modelVersions && item.modelVersions[0] && item.modelVersions[0].trainedWords) ||
            item.trainedWords || []
        );
        const triggerStr = trainedWords.slice(0, 10).join(', ');
        const tags = (item.tags || []).slice(0, 5).map(t => typeof t === 'object' ? (t.name || '') : String(t)).filter(Boolean);

        const nsfwLevel = (item.images && item.images[0] && item.images[0].nsfwLevel) || 1;
        const blur = !settings.showNsfwUnblurred && nsfwLevel >= (settings.nsfwBlurMinLevel || 4);
        const modelId = item.id || '';

        // Build versions list — use modelVersions array if present, else fall back to single version
        const versions = item.modelVersions && item.modelVersions.length
            ? item.modelVersions
            : (item.version ? [item.version] : []);

        // Build version dropdown options
        const verOptionsHTML = versions.map(ver => {
            const vid = ver.id || '';
            const vname = escHtml(ver.name || 'Latest');
            const vbase = escHtml(ver.baseModel || '');
            const label = vbase ? `[${vbase}] ${vname}` : vname;
            return `<option value="${vid}" data-base="${vbase}">${label}</option>`;
        }).join('');

        // First version base model for the badge
        const firstBase = escHtml((versions[0] && versions[0].baseModel) || '');
        const firstVerId = versions[0] ? (versions[0].id || '') : '';

        return `<div class="civicomfy-search-card" data-model-id="${modelId}">
  <div class="civicomfy-card-thumb">
    ${thumb ? `<img src="${escHtml(thumb)}" alt="${name}" ${blur ? 'class="civicomfy-nsfw-blur"' : ''} loading="lazy" onerror="this.style.display='none'">` : `<div class="civicomfy-card-thumb-ph">🎨</div>`}
    ${type ? `<span class="civicomfy-card-badge-type">${type}</span>` : ''}
    ${blur ? `<span class="civicomfy-card-badge-nsfw">NSFW</span>` : ''}
  </div>
  <div class="civicomfy-card-body">
    <div class="civicomfy-card-title" title="${name}">${name}</div>
    <div class="civicomfy-card-meta-line">
      ${creator ? `<span>👤 ${creator}</span>` : ''}
      ${firstBase ? `<span>🗂 ${firstBase}</span>` : ''}
      ${date ? `<span>📅 ${date}</span>` : ''}
    </div>
    <div class="civicomfy-card-meta-line" style="margin-top:2px">
      <span>⬇ ${dlCount}</span>
      <span>👍 ${likeCount}</span>
      <span>💬 ${commentCount}</span>
      ${parseInt(buzzCount) > 0 ? `<span>⚡ ${buzzCount}</span>` : ''}
    </div>
    ${tags.length ? `<div class="civicomfy-card-tags">${tags.map(t => `<span class="cchip cchip-tag">${escHtml(t)}</span>`).join('')}</div>` : ''}
    ${triggerStr ? `<div class="civicomfy-card-triggers"><b>Triggers:</b> ${escHtml(triggerStr)}</div>` : ''}
  </div>
  <div class="civicomfy-card-versions">
    <button class="civicomfy-view-link" data-civitai-url="https://civitai.com/models/${modelId}">View ↗</button>
    ${versions.length > 0 ? `
    <div class="civicomfy-ver-row" data-model-id="${modelId}">
      <div class="civicomfy-ver-select-wrap">
        ${firstBase ? `<span class="ver-base-badge civicomfy-ver-badge-display">${firstBase}</span>` : ''}
        <select class="civicomfy-ver-select" data-model-id="${modelId}">
          ${verOptionsHTML}
        </select>
      </div>
      <button class="civicomfy-ver-dl-btn" data-model-id="${modelId}" data-version-id="${firstVerId}">↓</button>
    </div>` : ''}
  </div>
</div>`;
    }

    function renderSearchResults(items) {
        const el = overlay.querySelector('#civicomfy-search-results');
        if (!items || items.length === 0) { el.innerHTML = '<p style="color:#888">No results found.</p>'; return; }
        el.innerHTML = items.map(buildCardHTML).join('');

        // Version select dropdown — update badge and download button on change
        el.querySelectorAll('.civicomfy-ver-select').forEach(sel => {
            sel.addEventListener('change', (e) => {
                e.stopPropagation();
                const row = sel.closest('.civicomfy-ver-row');
                const selectedOpt = sel.options[sel.selectedIndex];
                const vbase = selectedOpt.dataset.base || '';
                const vid = sel.value;
                // Update badge text
                const badge = row.querySelector('.civicomfy-ver-badge-display');
                if (badge) badge.textContent = vbase || '';
                // Update download button
                const dlBtn = row.querySelector('.civicomfy-ver-dl-btn');
                if (dlBtn) dlBtn.dataset.versionId = vid;
            });
        });

        // Download button
        el.querySelectorAll('.civicomfy-ver-dl-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const row = btn.closest('.civicomfy-ver-row');
                const sel = row.querySelector('.civicomfy-ver-select');
                const modelId = btn.dataset.modelId;
                const versionId = sel ? sel.value : (btn.dataset.versionId || '');
                overlay.querySelector('#civicomfy-model-url').value = modelId;
                overlay.querySelector('#civicomfy-model-version-id').value = versionId || '';
                switchTab('download');
                fetchAndRenderPreview();
                showToast('Model loaded in Download tab.', 'info');
            });
        });

        // View on Civitai link
        el.querySelectorAll('.civicomfy-view-link').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const url = btn.dataset.civitaiUrl;
                if (url) window.open(url, '_blank');
            });
        });

        // ── Async: load all real versions for each card from Civitai API ──
        items.forEach(item => {
            const modelId = item.id;
            if (!modelId) return;
            const card = el.querySelector(`.civicomfy-search-card[data-model-id="${modelId}"]`);
            if (!card) return;
            const verRow = card.querySelector('.civicomfy-ver-row');
            if (!verRow) return;

            API.getModelVersions(modelId, settings.apiKey)
                .then(resp => {
                    if (!resp || !resp.success || !resp.versions || resp.versions.length === 0) return;
                    const versions = resp.versions;
                    const sel = verRow.querySelector('.civicomfy-ver-select');
                    const badge = verRow.querySelector('.civicomfy-ver-badge-display');
                    const dlBtn = verRow.querySelector('.civicomfy-ver-dl-btn');
                    if (!sel) return;

                    // Rebuild options with ALL versions from Civitai
                    sel.innerHTML = versions.map(ver => {
                        const vid = ver.id || '';
                        const vname = escHtml(ver.name || 'Latest');
                        const vbase = escHtml(ver.baseModel || '');
                        const label = vbase ? `[${vbase}] ${vname}` : vname;
                        return `<option value="${vid}" data-base="${vbase}">${label}</option>`;
                    }).join('');

                    // Sync badge and dl button to first (most recent) version
                    const firstOpt = sel.options[0];
                    if (badge) badge.textContent = (firstOpt && firstOpt.dataset.base) || '';
                    if (dlBtn) dlBtn.dataset.versionId = (firstOpt && firstOpt.value) || '';
                })
                .catch(err => { console.warn(`[Civicomfy] Could not load versions for model ${modelId}:`, err); });
        });
    }

    function loadCardIntoDownload(card) {
        overlay.querySelector('#civicomfy-model-url').value = card.dataset.modelId;
        overlay.querySelector('#civicomfy-model-version-id').value = card.dataset.versionId || '';
        switchTab('download');
        fetchAndRenderPreview();
        showToast('Model loaded in Download tab.', 'info');
    }

    function renderSearchPagination(metadata) {
        const el = overlay.querySelector('#civicomfy-search-pagination');
        const { totalPages, currentPage } = metadata;
        searchPagination.totalPages = totalPages;
        if (totalPages <= 1) { el.innerHTML = ''; return; }
        el.innerHTML = `<button class="civicomfy-button small" id="civicomfy-prev-page" ${currentPage <= 1 ? 'disabled' : ''}>◀ Prev</button><span style="margin:0 10px;font-size:.9em;color:#aaa">Page ${currentPage} / ${totalPages}</span><button class="civicomfy-button small" id="civicomfy-next-page" ${currentPage >= totalPages ? 'disabled' : ''}>Next ▶</button>`;
        if (currentPage > 1) el.querySelector('#civicomfy-prev-page').addEventListener('click', () => { searchPagination.currentPage = currentPage - 1; handleSearchSubmit(); });
        if (currentPage < totalPages) el.querySelector('#civicomfy-next-page').addEventListener('click', () => { searchPagination.currentPage = currentPage + 1; handleSearchSubmit(); });
    }

    function startStatusPolling() { stopStatusPolling(); refreshStatus(); statusInterval = setInterval(refreshStatus, 2000); }
    function stopStatusPolling() { if (statusInterval) { clearInterval(statusInterval); statusInterval = null; } }
    async function refreshStatus() { try { renderStatus(await API.getStatus()); } catch (e) {} }

    // ---- Trigger word auto-injection into A1111 positive prompt ----
    function getA1111PromptTextarea() {
        // A1111 positive prompt textarea selectors (txt2img and img2img)
        const selectors = [
            '#txt2img_prompt textarea',
            '#img2img_prompt textarea',
            'textarea[placeholder*="positive"]',
        ];
        for (const sel of selectors) {
            const el = document.querySelector(sel);
            if (el) return el;
        }
        return null;
    }

    function injectTriggerWordsToPrompt(words, modelName) {
        if (!words || words.length === 0) return false;
        const textarea = getA1111PromptTextarea();
        if (!textarea) return false;

        const triggerStr = words.join(', ');
        const current = textarea.value.trim();

        // Don't inject if all trigger words already present
        const alreadyPresent = words.every(w => current.toLowerCase().includes(w.toLowerCase()));
        if (alreadyPresent) return false;

        // Append with separator
        const newValue = current ? `${current}, ${triggerStr}` : triggerStr;
        textarea.value = newValue;

        // Fire React/Gradio synthetic input event so A1111 registers the change
        textarea.dispatchEvent(new Event('input', { bubbles: true }));
        textarea.dispatchEvent(new Event('change', { bubbles: true }));

        return true;
    }

    function renderStatus(data) {
        const { queue = [], active = [], history = [] } = data;
        const total = queue.length + active.length;
        const ind = overlay.querySelector('#civicomfy-status-indicator');
        const cnt = overlay.querySelector('#civicomfy-active-count');
        if (ind) ind.style.display = total > 0 ? '' : 'none';
        if (cnt) cnt.textContent = total;

        // Check history for newly completed downloads with trigger words to inject
        history.forEach(item => {
            if (
                item.status === 'completed' &&
                item.id &&
                !processedTriggerInjections.has(item.id) &&
                Array.isArray(item.trained_words) &&
                item.trained_words.length > 0 &&
                settings.autoInjectTriggers !== false
            ) {
                processedTriggerInjections.add(item.id);
                const injected = injectTriggerWordsToPrompt(item.trained_words, item.model_name);
                if (injected) {
                    showToast(`✨ Triggers de "${item.model_name || 'modelo'}" añadidos al prompt: ${item.trained_words.slice(0, 3).join(', ')}${item.trained_words.length > 3 ? '…' : ''}`, 'success', 5000);
                }
            }
        });

        renderDownloadList('civicomfy-active-list', active, 'active');
        renderDownloadList('civicomfy-queued-list', queue, 'queued');
        renderDownloadList('civicomfy-history-list', history, 'history');
    }

    function renderDownloadList(cid, items, listType) {
        const c = overlay.querySelector('#' + cid);
        if (!c) return;
        if (!items || items.length === 0) { const msgs = { active: 'No active downloads.', queued: 'Queue is empty.', history: 'No download history yet.' }; c.innerHTML = `<p style="color:#888">${msgs[listType] || ''}</p>`; return; }
        c.innerHTML = items.map(i => renderDownloadItem(i, listType)).join('');
        c.querySelectorAll('[data-action]').forEach(b => b.addEventListener('click', () => handleDownloadAction(b.dataset.action, b.dataset.id)));
    }

    function renderDownloadItem(item, listType) {
        const sc = `civicomfy-status-${item.status || 'queued'}`;
        const prog = item.progress || 0;
        const spd = item.speed ? formatBytes(item.speed) + '/s' : '';
        const isActive = item.status === 'downloading' || item.status === 'starting';
        const isFailed = item.status === 'failed' || item.status === 'cancelled';
        const isCompleted = item.status === 'completed';
        const thumb = item.thumbnail ? `<img src="${escHtml(item.thumbnail)}" style="width:40px;height:40px;object-fit:cover;border-radius:4px;flex-shrink:0">` : '';
        let actions = '';
        if (isActive) actions = `<button class="civicomfy-button danger small" data-action="cancel" data-id="${item.id}">✕ Cancel</button>`;
        else if (isFailed && listType === 'history') actions = `<button class="civicomfy-button small" data-action="retry" data-id="${item.id}">↻ Retry</button>`;
        if (isCompleted) actions += ` <button class="civicomfy-open-btn" data-action="open_path" data-id="${item.id}">📁 Open Folder</button>`;
        return `<div class="civicomfy-download-item">
  <div class="civicomfy-download-item-header"><div style="display:flex;gap:8px;align-items:center;min-width:0">${thumb}<div class="civicomfy-download-item-name" title="${escHtml(item.model_name || item.filename || '')}">${escHtml(item.model_name || item.filename || 'Unknown')}</div></div><span class="civicomfy-download-item-status ${sc}">${item.status || 'unknown'}</span></div>
  <div class="civicomfy-download-item-meta">${escHtml(item.filename || '')} ${spd ? `· ${spd}` : ''}</div>
  ${isActive ? `<div class="civicomfy-progress-bar" style="margin-top:6px"><div class="civicomfy-progress-fill" style="width:${prog.toFixed(1)}%"></div></div><div style="font-size:.78em;color:#888;text-align:right">${prog.toFixed(1)}%</div>` : ''}
  ${item.error ? `<div style="font-size:.78em;color:#f66;margin-top:4px">⚠ ${escHtml(item.error)}</div>` : ''}
  ${actions ? `<div class="civicomfy-download-item-actions" style="margin-top:6px">${actions}</div>` : ''}
</div>`;
    }

    async function handleDownloadAction(action, downloadId) {
        try {
            if (action === 'cancel') { await API.cancelDownload(downloadId); showToast('Download cancelled.', 'info'); }
            else if (action === 'retry') { await API.retryDownload(downloadId); showToast('Download re-queued.', 'success'); }
            else if (action === 'open_path') { const r = await API.openPath(downloadId); r.success ? showToast('Folder opened.', 'success') : showToast(r.error || 'Could not open folder.', 'error'); }
            refreshStatus();
        } catch (e) { showToast(`❌ ${e.error || e.message || 'Action failed'}`, 'error'); }
    }

    async function handleClearHistory() {
        if (!confirm('Clear all download history? This cannot be undone.')) return;
        try { const r = await API.clearHistory(); r.success ? (showToast('History cleared.', 'success'), refreshStatus()) : showToast(r.error || 'Failed.', 'error'); }
        catch (e) { showToast('Failed to clear history.', 'error'); }
    }

    function applySettingsToForm() {
        const q = id => overlay.querySelector('#' + id);
        if (q('civicomfy-settings-api-key')) q('civicomfy-settings-api-key').value = settings.apiKey || '';
        if (q('civicomfy-settings-auto-open')) q('civicomfy-settings-auto-open').checked = settings.autoOpenStatusTab || false;
        if (q('civicomfy-settings-hide-mature')) q('civicomfy-settings-hide-mature').checked = settings.hideMatureInSearch !== false;
        if (q('civicomfy-settings-nsfw-threshold')) q('civicomfy-settings-nsfw-threshold').value = settings.nsfwBlurMinLevel || 4;
        if (q('civicomfy-settings-show-nsfw-unblurred')) q('civicomfy-settings-show-nsfw-unblurred').checked = settings.showNsfwUnblurred === true;
        if (q('civicomfy-settings-auto-inject')) q('civicomfy-settings-auto-inject').checked = settings.autoInjectTriggers !== false;
    }

    function handleSettingsSave() {
        const q = id => overlay.querySelector('#' + id);
        settings = { ...settings, apiKey: (q('civicomfy-settings-api-key')?.value || '').trim(), autoOpenStatusTab: q('civicomfy-settings-auto-open')?.checked || false, hideMatureInSearch: q('civicomfy-settings-hide-mature')?.checked !== false, nsfwBlurMinLevel: parseInt(q('civicomfy-settings-nsfw-threshold')?.value || '4', 10), showNsfwUnblurred: q('civicomfy-settings-show-nsfw-unblurred')?.checked === true, defaultModelType: q('civicomfy-settings-default-type')?.value || 'checkpoint', autoInjectTriggers: q('civicomfy-settings-auto-inject')?.checked !== false };
        saveSettings(settings);
        showToast('\u2705 Settings saved.', 'success');
        // Instantly update blur on all currently rendered NSFW thumbnails
        if (settings.showNsfwUnblurred) {
            overlay.classList.add('civicomfy-nsfw-show-all');
        } else {
            overlay.classList.remove('civicomfy-nsfw-show-all');
        }
    }

    function escHtml(s) { return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
    function formatBytes(b) { if (b < 1024) return `${b.toFixed(0)} B`; if (b < 1048576) return `${(b/1024).toFixed(0)} KB`; return `${(b/1048576).toFixed(1)} MB`; }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
})();