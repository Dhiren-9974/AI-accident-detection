const API_BASE = '';
const state = { user: null, polling: null, charts: {}, map: null, sirenActive: false, activeSection: 'dashboard' };

async function api(path, opts = {}) {
    const res = await fetch(API_BASE + path, { headers: { 'Content-Type': 'application/json', ...opts.headers }, credentials: 'same-origin', ...opts });
    if (res.status === 401) { logout(); throw new Error('Unauthorized'); }
    return res;
}

async function login() {
    const u = document.getElementById('username').value.trim();
    const p = document.getElementById('password').value.trim();
    const res = await api('/api/login', { method: 'POST', body: JSON.stringify({ username: u, password: p }) });
    if (res.ok) { const data = await res.json(); state.user = data; document.getElementById('login-overlay').classList.add('hidden'); init(); }
    else { document.getElementById('login-error').textContent = 'Invalid credentials'; document.getElementById('login-error').classList.remove('hidden'); }
}
async function logout() { await api('/api/logout', { method: 'POST' }); location.reload(); }

document.getElementById('login-form').addEventListener('submit', e => { e.preventDefault(); login(); });
document.getElementById('logout-btn').addEventListener('click', logout);

document.querySelectorAll('.nav-link').forEach(link => {
    if (link.id === 'logout-btn') return;
    link.addEventListener('click', e => {
        e.preventDefault();
        document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
        link.classList.add('active');
        const section = link.dataset.section;
        document.querySelectorAll('.section-content').forEach(s => s.classList.add('hidden'));
        document.getElementById(section).classList.remove('hidden');
        document.getElementById('section-title').textContent = section.charAt(0).toUpperCase() + section.slice(1);
        state.activeSection = section;
        if (section === 'analytics') renderAnalytics();
        if (section === 'map') loadMap();
        if (section === 'queue') fetchQueue();
        if (section === 'gallery') loadGallery();
        if (section === 'vehicles') loadVehicles();
    });
});

document.getElementById('sidebar-toggle').addEventListener('click', () => document.getElementById('sidebar').classList.toggle('-translate-x-full'));

document.getElementById('theme-toggle').addEventListener('click', () => { document.documentElement.classList.toggle('dark'); localStorage.setItem('theme', document.documentElement.classList.contains('dark') ? 'dark' : 'light'); });
if (localStorage.getItem('theme') === 'light') document.documentElement.classList.remove('dark');

document.getElementById('sound-toggle').addEventListener('click', () => { const icon = document.getElementById('sound-icon'); if (icon.classList.contains('fa-volume-mute')) { icon.classList.replace('fa-volume-mute','fa-volume-up'); icon.classList.add('text-primary'); } else { icon.classList.replace('fa-volume-up','fa-volume-mute'); icon.classList.remove('text-primary'); } });

async function init() {
    try {
        const res = await api('/api/user'); if (!res.ok) return; state.user = await res.json();
        document.getElementById('user-info').textContent = state.user.username;
        startPolling();
    } catch (e) { console.error('Init failed', e); }
}

let lastStatusJson = '';
let lastAccidentsJson = '';
let lastPlatesJson = '';
let lastCountsJson = '';
let lastStatusRender = 0;
function startPolling() {
    if (state.polling) clearInterval(state.polling);
    state.polling = setInterval(async () => {
        try {
            const active = state.activeSection;
            const fetches = [api('/api/status'), api('/api/vehicle/counts')];
            if (active === 'history' || active === 'gallery') {
                fetches.push(api('/api/accidents?limit=100'));
            } else {
                fetches.push(api('/api/accidents?dashboard=1'));
            }
            if (active === 'vehicles') {
                fetches.push(api('/api/vehicle-detections?limit=30'));
            }
            const [statusRes, countsRes, accidentsRes, platesRes] = await Promise.all(fetches);
            const now = Date.now();
            if (statusRes.ok) {
                const txt = await statusRes.text();
                if (txt !== lastStatusJson) {
                    lastStatusJson = txt;
                    if (now - lastStatusRender > 1000) { updateDashboard(JSON.parse(txt)); lastStatusRender = now; }
                }
            }
            if (countsRes.ok) {
                const txt = await countsRes.text();
                if (txt !== lastCountsJson) { lastCountsJson = txt; updateVehicleCounts(JSON.parse(txt)); }
            }
            if (accidentsRes.ok) {
                const txt = await accidentsRes.text();
                if (txt !== lastAccidentsJson) {
                    lastAccidentsJson = txt;
                    const data = JSON.parse(txt);
                    if (active === 'history') renderHistory(data);
                    renderGalleryFromAccidents(data);
                }
            }
            if (platesRes && platesRes.ok) {
                const txt = await platesRes.text();
                if (txt !== lastPlatesJson) {
                    lastPlatesJson = txt;
                    const data = JSON.parse(txt);
                    renderPlateReads(data);
                    const pc = document.getElementById('veh-plate-count');
                    if (pc) pc.textContent = data.filter(d => d.plate_number).length;
                }
            }
            if (active === 'vehicles') loadVehicles();
        } catch (e) { console.error('Polling error', e); }
    }, 3000);
}

let lastDashValues = {};
function updateDashboard(data) {
    const set = (id, val) => { const el = document.getElementById(id); if (el && lastDashValues[id] !== val) { el.textContent = val; lastDashValues[id] = val; } };
    set('dash-total-frames', data.total_frames || 0);
    set('dash-processed', data.processed_frames || 0);
    set('dash-accidents', data.total_accidents || 0);
    set('dash-fps', (data.avg_fps || 0).toFixed(1));
    set('dash-video', data.current_video ? data.current_video.substring(0, 28) : 'None');
    set('dash-source', data.current_video ? 'file' : '--');
    set('dash-saved', data.saved_frames_count || 0);
    const progress = data.progress || 0;
    if (lastDashValues['progress'] !== progress) {
        document.getElementById('progress-bar').style.width = progress + '%';
        document.getElementById('progress-text').textContent = progress;
        lastDashValues['progress'] = progress;
    }
    const pt = document.getElementById('processing-time');
    let newPt;
    if (data.start_time && !data.end_time) {
        const sec = Math.floor((Date.now() - new Date(data.start_time).getTime()) / 1000);
        newPt = 'Elapsed: ' + String(Math.floor(sec/60)).padStart(2,'0') + ':' + String(sec%60).padStart(2,'0');
    } else if (data.end_time && data.start_time) {
        const dur = Math.floor((new Date(data.end_time) - new Date(data.start_time)) / 1000);
        newPt = 'Done in ' + String(Math.floor(dur/60)).padStart(2,'0') + ':' + String(dur%60).padStart(2,'0');
    } else {
        newPt = 'Time: --:--';
    }
    if (lastDashValues['pt'] !== newPt) { pt.textContent = newPt; lastDashValues['pt'] = newPt; }
}

function updateVehicleCounts(counts) {
    document.getElementById('count-car').textContent = counts.car || 0;
    document.getElementById('count-bus').textContent = counts.bus || 0;
    document.getElementById('count-truck').textContent = counts.truck || 0;
    document.getElementById('count-bike').textContent = counts.motorcycle || 0;
    const total = (counts.car||0) + (counts.bus||0) + (counts.truck||0) + (counts.motorcycle||0);
    document.getElementById('confidence-bar').style.width = total ? '75%' : '0%';
}

let lastHistoryIds = '';
function renderHistory(data) {
    if (!data || !data.length) { document.getElementById('history-table-body').innerHTML = '<tr><td colspan="8" class="px-4 py-8 text-center text-gray-400 italic">No records found.</td></tr>'; lastHistoryIds = ''; return; }
    const tbody = document.getElementById('history-table-body');
    const ids = data.slice(0, 100).map(h => h.id).join(',');
    if (ids === lastHistoryIds) return;
    lastHistoryIds = ids;
    const sevColors = { critical: 'bg-red-100 text-red-700', moderate: 'bg-orange-100 text-orange-700', minor: 'bg-yellow-100 text-yellow-700' };
    const statColors = { pending: 'bg-gray-100 text-gray-700', confirmed: 'bg-green-100 text-green-700', false_alarm: 'bg-yellow-100 text-yellow-700', emergency_response: 'bg-red-100 text-red-700' };
    const rows = data.slice(0, 100).map(h => `<tr class="border-b border-gray-100 dark:border-gray-700">
        <td class="px-4 py-3">${h.id}</td>
        <td class="px-4 py-3">${new Date(h.timestamp).toLocaleString()}</td>
        <td class="px-4 py-3"><span class="px-2 py-1 rounded-full text-xs font-medium ${sevColors[h.severity] || 'bg-gray-100 text-gray-700'}">${(h.severity || 'moderate').title()}</span></td>
        <td class="px-4 py-3"><span class="px-2 py-1 rounded-full text-xs font-medium ${statColors[h.status] || 'bg-gray-100 text-gray-700'}">${(h.status || 'pending').replace('_', ' ').title()}</span></td>
        <td class="px-4 py-3"><span class="px-2 py-1 rounded-full text-xs font-medium bg-green-100 text-green-700">${Math.round((h.confidence||0)*100)}%</span></td>
        <td class="px-4 py-3">${h.vehicle_type||'--'}</td>
        <td class="px-4 py-3 text-xs">${h.video_name||'--'}</td>
        <td class="px-4 py-3">
            ${h.image_path?`<button onclick="openLightbox('/accident_frames/${h.image_path}')" class="text-primary text-xs hover:underline mr-2">View</button>`:''}
            ${h.status==='pending'?`
                <button onclick="updateAccidentStatus(${h.id}, 'confirm')" class="text-green-600 text-xs hover:underline mr-1">Confirm</button>
                <button onclick="updateAccidentStatus(${h.id}, 'false-alarm')" class="text-yellow-600 text-xs hover:underline mr-1">False</button>
                <button onclick="updateAccidentStatus(${h.id}, 'emergency-response')" class="text-red-600 text-xs hover:underline">Emergency</button>
            `:''}
            ${h.status==='confirmed'?`<span class="text-green-600 text-xs">Confirmed</span>`:''}
            ${h.status==='false_alarm'?`<span class="text-yellow-600 text-xs">False Alarm</span>`:''}
            ${h.status==='emergency_response'?`<span class="text-red-600 text-xs">Emergency</span>`:''}
        </td>
    </tr>`).join('');
    const frag = document.createElement('div');
    frag.innerHTML = '<table><tbody>' + rows + '</tbody></table>';
    tbody.replaceChildren(...frag.querySelector('tbody').children);
}

let galleryCache = [];

function vehicleLabel(type) {
    if (!type) return 'Unknown';
    return type.split('-').map(t => (t || '').charAt(0).toUpperCase() + (t || '').slice(1)).join(' ↔ ');
}

function renderGalleryFromAccidents(data) {
    if (state.activeSection !== 'gallery') return;
    const grid = document.getElementById('gallery-grid');
    const items = (data || []).filter(h => h.image_path).slice(0, 30);
    const total = (data || []).filter(h => h.image_path).length;
    document.getElementById('gallery-count').textContent = total;
    if (!items.length) { grid.innerHTML = '<p class="text-gray-400 col-span-full text-center py-12 italic">No accident frames captured yet.</p>'; return; }
    const sevColors = { critical: 'border-red-500', moderate: 'border-orange-400', minor: 'border-yellow-400' };
    grid.innerHTML = items.map(h => {
        const clip = h.video_clip_path ? `<a href="/output/${h.video_clip_path}" target="_blank" onclick="event.stopPropagation()" class="text-blue-600 text-xs hover:underline mr-2"><i class="fas fa-film mr-1"></i>Clip</a>` : '';
        const actions = `
            <div class="flex items-center gap-2 pt-1">
                ${clip}
                <a href="/accident_frames/${h.image_path}" download="${h.image_path}" onclick="event.stopPropagation()" class="text-green-600 text-xs hover:underline" title="Save image"><i class="fas fa-download mr-1"></i>Save</a>
                <button onclick="deleteGalleryImage(${h.id})" class="text-red-600 text-xs hover:underline" title="Delete image"><i class="fas fa-trash mr-1"></i>Delete</button>
                <span class="text-gray-400 text-xs ml-auto">ID #${h.id}</span>
            </div>`;
        return `<div class="gallery-item cursor-pointer rounded-xl overflow-hidden border-2 ${sevColors[h.severity] || 'border-gray-200'} bg-white dark:bg-gray-800 shadow-sm hover:shadow-md transition-shadow" onclick="openLightbox('/accident_frames/${h.image_path}')">
            <div class="relative">
                <img src="/accident_frames/${h.image_path}" alt="" loading="lazy" class="w-full h-44 object-cover">
                <span class="absolute top-2 left-2 px-2 py-0.5 rounded-full text-xs font-semibold bg-black/60 text-white">${(h.severity || 'moderate').toUpperCase()}</span>
                <span class="absolute top-2 right-2 px-2 py-0.5 rounded-full text-xs font-semibold bg-primary text-white">${Math.round((h.confidence||0)*100)}%</span>
            </div>
            <div class="p-3 space-y-1">
                <p class="text-sm font-semibold truncate">${vehicleLabel(h.vehicle_type)}</p>
                <p class="text-xs text-gray-500">${h.timestamp ? new Date(h.timestamp).toLocaleString() : ''}</p>
                ${actions}
            </div>
        </div>`;
    }).join('');
}

function updateGalleryCounts() {
    const counts = { all: galleryCache.filter(h => h.image_path).length, car: 0, truck: 0, bus: 0, motorcycle: 0 };
    galleryCache.forEach(h => {
        const t = (h.vehicle_type || '').toLowerCase();
        if (t.includes('car')) counts.car++;
        if (t.includes('truck')) counts.truck++;
        if (t.includes('bus')) counts.bus++;
        if (t.includes('motorcycle')) counts.motorcycle++;
    });
    document.querySelectorAll('.gf-count').forEach(el => { el.textContent = counts[el.dataset.type] || 0; });
}

function loadGallery() {
    api('/api/accidents').then(r => r.ok ? r.json() : []).then(data => { galleryCache = data || []; updateGalleryCounts(); renderGalleryFromAccidents(galleryCache); });
}

function filterGallery(type) {
    document.querySelectorAll('.gallery-filter').forEach(b => {
        const active = b.dataset.type === type;
        b.classList.toggle('bg-primary', active);
        b.classList.toggle('text-white', active);
        b.classList.toggle('bg-gray-100', !active);
        b.classList.toggle('dark:bg-gray-700', !active);
    });
    if (type === 'all') { renderGalleryFromAccidents(galleryCache); return; }
    const filtered = galleryCache.filter(h => (h.vehicle_type || '').toLowerCase().includes(type));
    renderGalleryFromAccidents(filtered);
}

async function deleteGalleryImage(id) {
    if (!confirm('Delete this captured image and its record permanently?')) return;
    const res = await api('/api/accidents/' + id, { method: 'DELETE' });
    if (res.ok) { galleryCache = galleryCache.filter(h => h.id !== id); updateGalleryCounts(); loadGallery(); }
    else { const err = await res.json().catch(() => ({})); alert(err.message || 'Failed to delete'); }
}

function filterHistory(type) {
    const tbody = document.getElementById('history-table-body'); tbody.innerHTML = '<tr><td colspan="8" class="px-4 py-8 text-center text-gray-400 italic">Loading...</td></tr>';
    let url = '/api/accidents';
    if (type === 'today') url += '?today=1';
    else if (type === 'yesterday') url += '?yesterday=1';
    else if (type === 'week') url += '?week=1';
    else if (type === 'vehicle') url += '?vehicle=' + document.getElementById('filter-vehicle').value;
    else if (type === 'search') url += '?search=' + encodeURIComponent(document.getElementById('filter-search').value);
    api(url).then(r => r.ok ? r.json() : []).then(renderHistory);
}

function deleteAccident(id) { if (!confirm('Delete this record?')) return; api('/api/accidents/' + id, { method: 'DELETE' }).then(() => startPolling()); }
async function updateAccidentStatus(id, action) {
    const notes = action === 'false-alarm' ? prompt('Reason for false alarm:') : (action === 'emergency-response' ? prompt('Response details:') : prompt('Operator notes (optional):'));
    if (notes === null) return;
    const endpoint = '/api/accidents/' + id + '/' + action;
    const body = { notes: notes };
    if (action === 'emergency-response') body.response_details = notes;
    const res = await api(endpoint, { method: 'PUT', body: JSON.stringify(body) });
    if (res.ok) { lastHistoryIds = ''; startPolling(); addTimelineEvent('Accident ' + id + ' marked as ' + action.replace('-', ' '), action === 'emergency-response' ? 'danger' : 'warning'); }
}

function downloadReport() { window.open('/api/report', '_blank'); }

document.getElementById('start-detection-btn').addEventListener('click', async () => {
    const sourceType = document.querySelector('input[name="source-type"]:checked').value;
    const statusEl = document.getElementById('detection-status');
    try {
        if (sourceType === 'upload') {
            const fileInput = document.getElementById('video-upload');
            if (!fileInput.files[0]) { statusEl.textContent = 'Please select a video file first'; return; }
            const form = new FormData(); form.append('video', fileInput.files[0]);
            statusEl.textContent = 'Uploading and starting detection...';
            const res = await fetch('/api/detect', { method: 'POST', body: form, credentials: 'same-origin' });
            if (res.ok) { statusEl.textContent = 'Detection started'; document.getElementById('start-detection-btn').classList.add('hidden'); document.getElementById('stop-detection-btn').classList.remove('hidden'); }
            else { const err = await res.json(); statusEl.textContent = err.message || 'Failed to start'; }
        } else if (sourceType === 'youtube') {
            const url = document.getElementById('youtube-url').value.trim(); if (!url) { statusEl.textContent = 'Please enter a YouTube URL'; return; }
            statusEl.textContent = 'Downloading YouTube video...';
            const res = await api('/api/detect', { method: 'POST', body: JSON.stringify({ source: url }) });
            if (res.ok) { statusEl.textContent = 'Detection started'; document.getElementById('start-detection-btn').classList.add('hidden'); document.getElementById('stop-detection-btn').classList.remove('hidden'); }
            else { const err = await res.json(); statusEl.textContent = err.message || 'Failed to start'; }
        } else {
            const url = document.getElementById('camera-url').value.trim(); if (!url) { statusEl.textContent = 'Please enter a source URL'; return; }
            statusEl.textContent = 'Starting detection...'; const res = await api('/api/detect', { method: 'POST', body: JSON.stringify({ source: url }) });
            if (res.ok) { statusEl.textContent = 'Detection started'; document.getElementById('start-detection-btn').classList.add('hidden'); document.getElementById('stop-detection-btn').classList.remove('hidden'); }
            else { const err = await res.json(); statusEl.textContent = err.message || 'Failed to start'; }
        }
    } catch (e) { console.error('Detection start failed', e); statusEl.textContent = 'Error starting detection'; }
});

document.getElementById('stop-detection-btn').addEventListener('click', async () => {
    document.getElementById('detection-status').textContent = 'Stop requested...';
    document.getElementById('start-detection-btn').classList.remove('hidden');
    document.getElementById('stop-detection-btn').classList.add('hidden');
    document.getElementById('detection-status').textContent = 'Status: Idle';
});

document.querySelectorAll('input[name="source-type"]').forEach(radio => radio.addEventListener('change', e => {
    const wrap = document.getElementById('upload-input-wrap'), urlWrap = document.getElementById('url-input-wrap'), ytWrap = document.getElementById('youtube-input-wrap');
    if (e.target.value === 'upload') { wrap.classList.remove('hidden'); urlWrap.classList.add('hidden'); ytWrap.classList.add('hidden'); }
    else if (e.target.value === 'youtube') { wrap.classList.add('hidden'); urlWrap.classList.add('hidden'); ytWrap.classList.remove('hidden'); }
    else { wrap.classList.add('hidden'); urlWrap.classList.remove('hidden'); ytWrap.classList.add('hidden'); }
}));

document.getElementById('video-upload').addEventListener('change', function() {
    if (this.files[0]) {
        document.getElementById('detection-status').textContent = 'Selected: ' + this.files[0].name;
        const video = document.getElementById('preview-video');
        video.src = URL.createObjectURL(this.files[0]);
        video.classList.remove('hidden');
        document.getElementById('preview-placeholder').classList.add('hidden');
    }
});

document.getElementById('youtube-url').addEventListener('input', function() {
    const url = this.value.trim();
    const video = document.getElementById('preview-video');
    const placeholder = document.getElementById('preview-placeholder');
    if (url && (url.includes('youtube.com') || url.includes('youtu.be'))) {
        let videoId = '';
        const match = url.match(/(?:v=|youtu\.be\/)([a-zA-Z0-9_-]{11})/);
        if (match) videoId = match[1];
        if (videoId) {
            video.src = `https://www.youtube.com/embed/${videoId}`;
            video.classList.remove('hidden');
            placeholder.classList.add('hidden');
        }
    }
});

document.getElementById('camera-url').addEventListener('input', function() {
    const url = this.value.trim();
    const video = document.getElementById('preview-video');
    const placeholder = document.getElementById('preview-placeholder');
    if (url && !url.startsWith('rtsp://')) {
        video.src = url;
        video.classList.remove('hidden');
        placeholder.classList.add('hidden');
    } else if (url.startsWith('rtsp://')) {
        video.src = '';
        video.classList.add('hidden');
        placeholder.classList.remove('hidden');
        placeholder.innerHTML = '<i class="fas fa-video-slash text-4xl mb-2"></i><p class="text-sm">RTSP stream preview not available in browser</p>';
    }
});

function initCharts() {
    if (state.charts.daily) return;
    const grid = '#374151'; const txt = '#9ca3af'; const white = '#e5e7eb';
    state.charts.daily = new Chart(document.getElementById('chart-daily'), { type:'line', data:{labels:[],datasets:[{label:'Accidents',data:[],borderColor:'#10b981',tension:.3,fill:true,backgroundColor:'rgba(16,185,129,.15)'}]}, options:{responsive:true,plugins:{legend:{display:false,labels:{color:white}}},scales:{x:{ticks:{color:txt},grid:{color:grid}},y:{ticks:{color:txt},grid:{color:grid}}}} });
    state.charts.hourly = new Chart(document.getElementById('chart-hourly'), { type:'bar', data:{labels:[],datasets:[{label:'Accidents',data:[],backgroundColor:'#3b82f6'}]}, options:{responsive:true,plugins:{legend:{labels:{color:white}}},scales:{x:{ticks:{color:txt},grid:{color:grid}},y:{ticks:{color:txt},grid:{color:grid}}}} });
    state.charts.types = new Chart(document.getElementById('chart-types'), { type:'doughnut', data:{labels:['Cars','Trucks','Buses','Bikes'],datasets:[{data:[0,0,0,0],backgroundColor:['#3b82f6','#f97316','#10b981','#8b5cf6']}]}, options:{responsive:true,plugins:{legend:{labels:{color:white}},title:{display:true,text:'Vehicle Classes Involved',color:white}}} });
    state.charts.severity = new Chart(document.getElementById('chart-severity'), { type:'doughnut', data:{labels:['Minor','Moderate','Critical'],datasets:[{data:[0,0,0],backgroundColor:['#facc15','#f97316','#ef4444']}]}, options:{responsive:true,plugins:{legend:{labels:{color:white}},title:{display:true,text:'Severity Breakdown',color:white}}} });
}

async function renderAnalytics() {
    initCharts();
    try {
        const res = await api('/api/analytics'); if (!res.ok) return; const data = await res.json();
        const days = Object.keys(data.accidents_per_day || {}); const dayCounts = Object.values(data.accidents_per_day || {});
        state.charts.daily.data.labels = days; state.charts.daily.data.datasets[0].data = dayCounts; state.charts.daily.update();
        const hours = Object.keys(data.accidents_per_hour || {}).sort((a,b)=>a-b); const hourCounts = hours.map(h => data.accidents_per_hour[h] || 0);
        state.charts.hourly.data.labels = hours; state.charts.hourly.data.datasets[0].data = hourCounts; state.charts.hourly.update();
        const cls = data.vehicle_class_counts || {}; state.charts.types.data.datasets[0].data = [cls.car||0, cls.truck||0, cls.bus||0, cls.motorcycle||0]; state.charts.types.update();
        const sev = data.severity_counts || {};
        state.charts.severity.data.datasets[0].data = [sev.minor||0, sev.moderate||0, sev.critical||0];
        state.charts.severity.update();
    } catch (e) { console.error('Analytics fetch failed', e); }
}

function initMap() {
    const mapEl = document.getElementById('map-canvas');
    if (!mapEl) return;
    if (!state.map) {
        state.map = L.map('map-canvas').setView([20.5937, 78.9629], 5);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution:'© OpenStreetMap', maxZoom:19 }).addTo(state.map);
    }
    setTimeout(() => state.map.invalidateSize(), 200);
    setTimeout(() => state.map.invalidateSize(), 500);
}
function loadMap() {
    initMap();
}
function saveLocation() { 
    const lat = document.getElementById('map-lat').value; 
    const lng = document.getElementById('map-lng').value; 
    if (!lat || !lng || !state.map) return; 
    L.marker([lat,lng]).addTo(state.map).bindPopup(document.getElementById('map-loc-name').value || 'Location').openPopup(); 
    state.map.setView([lat,lng], 12); 
}
async function findHospitals() {
    const lat = parseFloat(document.getElementById('map-lat').value);
    const lng = parseFloat(document.getElementById('map-lng').value);
    if (isNaN(lat) || isNaN(lng)) { alert('Please enter a valid latitude and longitude first'); return; }
    if (!state.map) { alert('Map not ready yet'); return; }
    if (!state.hospitalMarkers) state.hospitalMarkers = [];
    state.hospitalMarkers.forEach(m => state.map.removeLayer(m));
    state.hospitalMarkers = [];
    try {
        const res = await api(`/api/hospitals/nearby?lat=${lat}&lng=${lng}&radius=5000`);
        if (!res.ok) { const err = await res.json(); alert(err.message || 'Failed to find hospitals'); return; }
        const data = await res.json();
        const hospitals = (data.hospitals || []).filter(h => h.lat && h.lng && h.name);
        if (!hospitals.length) { alert('No verified hospitals found near this location'); state.map.setView([lat, lng], 13); return; }
        const center = L.marker([lat, lng], { icon: L.icon({ iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-red.png', iconSize: [25, 41], iconAnchor: [12, 41] }) })
            .addTo(state.map).bindPopup(`<b>Incident Location</b><br>${document.getElementById('map-loc-name').value || 'Accident site'}`);
        state.hospitalMarkers.push(center);
        const bounds = L.latLngBounds([[lat, lng]]);
        hospitals.forEach(h => {
            const marker = L.marker([h.lat, h.lng]).addTo(state.map)
                .bindPopup(`<b>${h.name}</b><br><span class="text-xs text-gray-500">${h.type}</span><br>${h.phone ? 'Phone: ' + h.phone + '<br>' : ''}${h.address || ''}`);
            state.hospitalMarkers.push(marker);
            bounds.extend([h.lat, h.lng]);
        });
        state.map.fitBounds(bounds, { padding: [60, 60], maxZoom: 15 });
    } catch (e) { console.error('Hospital search failed', e); alert('Error searching for hospitals'); }
}

async function addToQueue() { const path = document.getElementById('queue-path').value.trim(); const type = document.getElementById('queue-type').value; if (!path) return; await api('/api/video/queue', { method:'POST', body: JSON.stringify({ video_path: path, source_type: type }) }); document.getElementById('queue-path').value = ''; fetchQueue(); }
async function fetchQueue() { try { const res = await api('/api/video/queue'); const queue = await res.json(); document.getElementById('queue-table-body').innerHTML = queue.map((q,i) => `<tr class="border-b border-gray-100 dark:border-gray-700"><td class="px-4 py-3">${i+1}</td><td class="px-4 py-3 text-xs">${q.video_path}</td><td class="px-4 py-3"><span class="px-2 py-1 rounded-full text-xs font-medium ${q.status==='queued'?'bg-gray-100 dark:bg-gray-700':q.status==='processing'?'bg-blue-100 text-blue-700':'bg-green-100 text-green-700'}">${q.status}</span></td><td class="px-4 py-3"><button onclick="removeQueue(${q.id})" class="text-red-600 text-xs hover:underline">Remove</button></td></tr>`).join('') || '<tr><td colspan="4" class="px-4 py-8 text-center text-gray-400 italic">No videos in queue.</td></tr>'; } catch (e) { console.error('Queue fetch failed', e); } }
async function removeQueue(id) { try { await api('/api/video/queue/' + id, { method:'DELETE' }); fetchQueue(); } catch (e) { console.error('Queue delete failed', e); } }

async function saveSettings() {
    const settings = { confidence_threshold: document.getElementById('set-confidence').value, process_every_n_frames: document.getElementById('set-process-n').value, notification_cooldown: document.getElementById('set-cooldown').value, detection_speed: document.getElementById('set-speed').value, camera_location: document.getElementById('set-camera-location').value, telegram_bot_token: document.getElementById('set-telegram-token').value, telegram_chat_id: document.getElementById('set-telegram-chat').value, smtp_host: document.getElementById('set-smtp-host').value, smtp_port: document.getElementById('set-smtp-port').value, smtp_user: document.getElementById('set-smtp-user').value, smtp_password: document.getElementById('set-smtp-pass').value, from_email: document.getElementById('set-from-email').value, alert_recipient_emails: document.getElementById('set-alert-emails').value, twilio_account_sid: document.getElementById('set-twilio-sid').value, twilio_auth_token: document.getElementById('set-twilio-token').value, twilio_from_phone: document.getElementById('set-twilio-phone').value, twilio_from_whatsapp: document.getElementById('set-whatsapp-from').value };
    const res = await api('/api/settings', { method:'PUT', body: JSON.stringify(settings) });
    if (res.ok) alert('Settings saved successfully');
}

async function testNotification(channel) {
    const payload = { telegram: false, email: false, sms: false, whatsapp: false };
    payload[channel] = true;
    const res = await api('/api/notifications/test', { method:'POST', body: JSON.stringify(payload) });
    const data = await res.json(); alert('Test ' + channel + ' result: ' + JSON.stringify(data.results));
}

function openLightbox(src) { document.getElementById('lightbox-img').src = src; document.getElementById('lightbox').classList.remove('hidden'); document.getElementById('lightbox').classList.add('flex'); }
document.getElementById('lightbox-close').addEventListener('click', () => { document.getElementById('lightbox').classList.add('hidden'); document.getElementById('lightbox').classList.remove('flex'); });
document.getElementById('lightbox').addEventListener('click', e => { if (e.target.id === 'lightbox') { document.getElementById('lightbox').classList.add('hidden'); document.getElementById('lightbox').classList.remove('flex'); } });

function addTimelineEvent(title, type = 'info') { const timeline = document.getElementById('timeline'); const item = document.createElement('div'); item.className = `timeline-item ${type} animate-slide-in`; item.innerHTML = `<div class="font-semibold text-sm">${title}</div><div class="text-xs text-gray-400">${new Date().toLocaleTimeString()}</div>`; if (timeline.querySelector('.italic')) timeline.innerHTML = ''; timeline.prepend(item); }
function addNotification(message, type = 'info') { const panel = document.getElementById('notifications-panel'); const item = document.createElement('div'); item.className = `notification-item notification-${type} animate-fade-in`; item.innerHTML = `<div class="flex items-center justify-between"><span class="text-sm font-medium">${message}</span><span class="text-xs text-gray-400">${new Date().toLocaleTimeString()}</span></div>`; if (panel.querySelector('.italic')) panel.innerHTML = ''; panel.prepend(item); }

function playSiren() { if (state.sirenActive) return; state.sirenActive = true; try { const ctx = new (window.AudioContext || window.webkitAudioContext)(); const osc = ctx.createOscillator(); const gain = ctx.createGain(); osc.connect(gain); gain.connect(ctx.destination); osc.type = 'sine'; osc.frequency.value = 780; gain.gain.value = .15; osc.start(); let up = true; const t = setInterval(() => { if (up && osc.frequency.value < 1560) osc.frequency.value += 60; else if (!up && osc.frequency.value > 220) osc.frequency.value -= 60; else up = !up; }, 200); setTimeout(() => { clearInterval(t); osc.stop(); ctx.close(); state.sirenActive = false; }, 5000); } catch (e) { console.error('Audio error', e); } }

async function loadSettings() { try { const res = await api('/api/settings'); if (res.ok) { const s = await res.json(); const map = { 'set-confidence':'confidence_threshold','set-process-n':'process_every_n_frames','set-cooldown':'notification_cooldown','set-speed':'detection_speed','set-camera-location':'camera_location','set-telegram-token':'telegram_bot_token','set-telegram-chat':'telegram_chat_id','set-smtp-host':'smtp_host','set-smtp-port':'smtp_port','set-smtp-user':'smtp_user','set-smtp-pass':'smtp_password','set-from-email':'from_email','set-alert-emails':'alert_recipient_emails','set-twilio-sid':'twilio_account_sid','set-twilio-token':'twilio_auth_token','set-twilio-phone':'twilio_from_phone','set-whatsapp-from':'twilio_from_whatsapp' }; for (const [id, key] of Object.entries(map)) { const el = document.getElementById(id); if (el && s[key]) el.value = s[key]; } } } catch (e) { console.error('Settings load failed', e); } }

setTimeout(() => { api('/api/user').then(r => r.ok ? init() : document.getElementById('login-overlay').classList.remove('hidden')).catch(() => document.getElementById('login-overlay').classList.remove('hidden')); }, 200);
setTimeout(loadSettings, 1200);
setInterval(fetchQueue, 5000); fetchQueue();

window.filterHistory = filterHistory; window.filterGallery = filterGallery; window.deleteGalleryImage = deleteGalleryImage; window.loadMap = loadMap; window.deleteAccident = deleteAccident; window.updateAccidentStatus = updateAccidentStatus; window.downloadReport = downloadReport; window.saveLocation = saveLocation; window.findHospitals = findHospitals; window.addToQueue = addToQueue; window.removeQueue = removeQueue; window.saveSettings = saveSettings; window.testNotification = testNotification; window.openLightbox = openLightbox;

function renderPlateReads(data) {
    const el = document.getElementById('plate-reads'); if (!el) return;
    if (!data || !data.length) { el.innerHTML = '<p class="text-gray-400 text-sm italic">No plates captured yet.</p>'; return; }
    el.innerHTML = data.slice(0, 30).map(d => {
        const matched = d.owner_name ? '<span class="text-green-600 text-xs font-medium">Owner known</span>' : '<span class="text-gray-400 text-xs">Unregistered</span>';
        const img = d.image_path ? `<img src="/plate_frames/${d.image_path}" class="w-16 h-10 object-cover rounded border border-gray-200 dark:border-gray-600" onerror="this.style.display='none'">` : '';
        return `<div class="flex items-center gap-3 p-2 bg-gray-50 dark:bg-gray-700 rounded-lg">
            ${img}
            <div class="min-w-0 flex-1">
                <div class="font-semibold text-sm">${d.plate_number ? d.plate_number : '— (pending OCR)'}</div>
                <div class="text-xs text-gray-500">${d.vehicle_type || ''} • ${new Date(d.timestamp).toLocaleTimeString()}</div>
            </div>
            <div class="text-right">${matched}</div>
        </div>`;
    }).join('');
}

async function loadVehicles() {
    try { const r = await api('/api/vehicles'); if (r.ok) renderRegistry(await r.json()); } catch (e) { console.error('Registry load failed', e); }
    try { const r = await api('/api/vehicle-detections?limit=100'); if (r.ok) renderDetections(await r.json()); } catch (e) { console.error('Detections load failed', e); }
}

function renderRegistry(data) {
    const tbody = document.getElementById('registry-table-body'); if (!tbody) return;
    const q = (document.getElementById('registry-search')?.value || '').toLowerCase();
    const rows = (data || []).filter(v => !q || (v.plate_number + ' ' + (v.owner_name||'') + ' ' + (v.make||'')).toLowerCase().includes(q));
    if (!rows.length) { tbody.innerHTML = '<tr><td colspan="7" class="px-4 py-8 text-center text-gray-400 italic">No vehicles registered.</td></tr>'; return; }
    tbody.innerHTML = rows.map(v => `<tr class="border-b border-gray-100 dark:border-gray-700">
        <td class="px-4 py-3 font-medium">${v.plate_number}</td>
        <td class="px-4 py-3">${v.vehicle_type || '--'}</td>
        <td class="px-4 py-3">${[v.make, v.model].filter(Boolean).join(' ') || '--'}</td>
        <td class="px-4 py-3">${v.owner_name || '--'}</td>
        <td class="px-4 py-3">${v.owner_phone || '--'}</td>
        <td class="px-4 py-3">${v.insurance_expiry || '--'}</td>
        <td class="px-4 py-3">
            <button onclick="lookupPlate('${v.plate_number}')" class="text-primary text-xs hover:underline mr-2">View</button>
            ${current_user_is_admin ? `<button onclick="deleteVehicle('${v.plate_number}')" class="text-red-600 text-xs hover:underline">Delete</button>` : ''}
        </td>
    </tr>`).join('');
}

function renderDetections(data) {
    const tbody = document.getElementById('detections-table-body'); if (!tbody) return;
    if (!data || !data.length) { tbody.innerHTML = '<tr><td colspan="7" class="px-4 py-8 text-center text-gray-400 italic">No captures yet.</td></tr>'; return; }
    const statColors = { recognized: 'bg-green-100 text-green-700', pending: 'bg-gray-100 text-gray-700', manual: 'bg-blue-100 text-blue-700' };
    tbody.innerHTML = data.slice(0, 100).map(d => `<tr class="border-b border-gray-100 dark:border-gray-700">
        <td class="px-4 py-3">${d.id}</td>
        <td class="px-4 py-3 font-medium">${d.plate_number || '—'}</td>
        <td class="px-4 py-3">${d.vehicle_type || '--'}</td>
        <td class="px-4 py-3">${d.owner_name || '<span class="text-gray-400">Unknown</span>'}</td>
        <td class="px-4 py-3 text-xs">${new Date(d.timestamp).toLocaleString()}</td>
        <td class="px-4 py-3"><span class="px-2 py-1 rounded-full text-xs font-medium ${statColors[d.status] || 'bg-gray-100 text-gray-700'}">${(d.status || 'pending').title()}</span></td>
        <td class="px-4 py-3">
            ${d.status !== 'recognized' ? `<button onclick="confirmDetection(${d.id})" class="text-blue-600 text-xs hover:underline mr-2">Confirm</button>` : ''}
            ${current_user_is_admin ? `<button onclick="deleteDetection(${d.id})" class="text-red-600 text-xs hover:underline">Delete</button>` : ''}
        </td>
    </tr>`).join('');
}

function filterRegistry() { api('/api/vehicles').then(r => r.ok ? r.json() : []).then(renderRegistry); }

async function lookupPlate(preset) {
    const plate = (preset || document.getElementById('plate-search').value).trim().toUpperCase();
    const el = document.getElementById('owner-detail'); if (!el) return;
    if (!plate) { el.innerHTML = '<span class="text-gray-500">Enter a plate number to view full owner details.</span>'; return; }
    try {
        const r = await api('/api/vehicles/' + encodeURIComponent(plate));
        const v = r.ok ? await r.json() : null;
        if (!v) { el.innerHTML = `<div class="p-3 bg-yellow-50 dark:bg-yellow-900/30 rounded-lg text-yellow-700 dark:text-yellow-300">No owner found for plate <b>${plate}</b>. Register it in the Vehicle Registry below.</div>`; return; }
        el.innerHTML = `<div class="p-4 bg-gray-50 dark:bg-gray-700 rounded-lg space-y-2">
            <div class="flex items-center gap-2"><i class="fas fa-id-card text-primary"></i><span class="text-lg font-bold">${v.plate_number}</span><span class="px-2 py-0.5 rounded-full text-xs bg-primary-100 text-primary-700">${(v.vehicle_type||'').title()}</span></div>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1 text-sm">
                <div><span class="text-gray-500">Vehicle:</span> ${[v.make, v.model, v.color, v.year].filter(Boolean).join(' ') || '--'}</div>
                <div><span class="text-gray-500">Owner:</span> ${v.owner_name || '--'}</div>
                <div><span class="text-gray-500">Phone:</span> ${v.owner_phone || '--'}</div>
                <div><span class="text-gray-500">Email:</span> ${v.owner_email || '--'}</div>
                <div class="sm:col-span-2"><span class="text-gray-500">Address:</span> ${v.address || '--'}</div>
                <div><span class="text-gray-500">Registered:</span> ${v.registration_date || '--'}</div>
                <div><span class="text-gray-500">Insurance Exp:</span> ${v.insurance_expiry || '--'}</div>
                ${v.notes ? `<div class="sm:col-span-2"><span class="text-gray-500">Notes:</span> ${v.notes}</div>` : ''}
            </div>
        </div>`;
    } catch (e) { console.error('Lookup failed', e); }
}

document.getElementById('vehicle-form').addEventListener('submit', async e => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const payload = Object.fromEntries(fd.entries());
    const res = await api('/api/vehicles', { method: 'POST', body: JSON.stringify(payload) });
    if (res.ok) { e.target.reset(); loadVehicles(); alert('Vehicle saved to registry'); }
    else { const err = await res.json().catch(() => ({})); alert(err.message || 'Failed to save'); }
});

async function deleteVehicle(plate) { if (!confirm('Delete vehicle ' + plate + '?')) return; await api('/api/vehicles/' + encodeURIComponent(plate), { method: 'DELETE' }); loadVehicles(); }
async function deleteDetection(id) { if (!confirm('Delete capture record?')) return; await api('/api/vehicle-detections/' + id, { method: 'DELETE' }); loadVehicles(); }
async function confirmDetection(id) {
    const plate = prompt('Enter the correct plate number for this capture:');
    if (!plate) return;
    const res = await api('/api/vehicle-detections/' + id + '/confirm', { method: 'PUT', body: JSON.stringify({ plate_number: plate }) });
    if (res.ok) loadVehicles();
}

let current_user_is_admin = false;
async function refreshUserRole() { try { const r = await api('/api/user'); if (r.ok) { const u = await r.json(); current_user_is_admin = u.role === 'admin'; } } catch (e) {} }
refreshUserRole();

window.loadVehicles = loadVehicles; window.lookupPlate = lookupPlate; window.filterRegistry = filterRegistry; window.deleteVehicle = deleteVehicle; window.deleteDetection = deleteDetection; window.confirmDetection = confirmDetection;