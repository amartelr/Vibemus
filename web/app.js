/**
 * VIBEMUS — MODERN MUSIC HARMONY DASHBOARD ENGINE
 * Dual-Sync architecture (LocalStorage + Google Sheets Cloud)
 * Web Audio API synthesizer for chords
 * SVG Circle of Fifths interactive visualizer
 */

// Global Application State
const state = {
    songs: [],
    filteredSongs: [],
    selectedSong: null,
    currentSuggestion: null,
    activeFilters: {
        search: '',
        tonality: null, // selected key on Circle of Fifths
        complexity: 'all',
        harmonyStatus: 'all', // 'all', 'with', 'without'
        scanStatus: 'all',    // 'all', 'scanned', 'never'
        styles: new Set(), // empty Set = show all (no filter)
        progressionLength: 'all',
        progression: 'all',
        playlist: 'all',
        justFound: false,
        likedOnly: false
    },
    sortRule: 'title-asc', // 'title-asc' or 'scrobble-desc'
    selectedSource: 'Ultimate Guitar', // selected search source
    selectedSongScanTime: null, // scan time at the moment of song selection
    lastActiveTonality: null, // tracked tonality for smart transposition
    justFoundRows: [], // row IDs of songs successfully found in the last playlist autocomplete run
    availableStyles: new Set(),
    availablePlaylists: new Set(),
    availableProgressionLengths: new Set(),
    availableProgressions: new Set(),
    audioContext: null,
    synths: [],
    selectedLyrics: null,   // lyrics_with_chords from last successful autodetect
    chordViewMode: 'diagrams' // 'diagrams' | 'lyrics'
};

// MIDI note helper mapping
const NOTE_FREQS = {
    'C': 261.63, 'C#': 277.18, 'Db': 277.18, 'D': 293.66, 'D#': 311.13, 'Eb': 311.13,
    'E': 329.63, 'F': 349.23, 'F#': 369.99, 'Gb': 369.99, 'G': 392.00, 'G#': 415.30,
    'Ab': 415.30, 'A': 440.00, 'A#': 466.16, 'Bb': 466.16, 'B': 493.88
};

// Circle of Fifths Key Configuration
const CIRCLE_KEYS = {
    outer: [
        { name: 'C Major', note: 'C', key: 'C Major' },
        { name: 'G Major', note: 'G', key: 'G Major' },
        { name: 'D Major', note: 'D', key: 'D Major' },
        { name: 'A Major', note: 'A', key: 'A Major' },
        { name: 'E Major', note: 'E', key: 'E Major' },
        { name: 'B Major', note: 'B', key: 'B Major' },
        { name: 'F# Major', note: 'F#', key: 'F# Major' },
        { name: 'C# Major', note: 'C#', key: 'C# Major' },
        { name: 'Ab Major', note: 'Ab', key: 'Ab Major' },
        { name: 'Eb Major', note: 'Eb', key: 'Eb Major' },
        { name: 'Bb Major', note: 'Bb', key: 'Bb Major' },
        { name: 'F Major', note: 'F', key: 'F Major' }
    ],
    inner: [
        { name: 'A Minor', note: 'A', key: 'A Minor' },
        { name: 'E Minor', note: 'E', key: 'E Minor' },
        { name: 'B Minor', note: 'B', key: 'B Minor' },
        { name: 'F# Minor', note: 'F#', key: 'F# Minor' },
        { name: 'C# Minor', note: 'C#', key: 'C# Minor' },
        { name: 'G# Minor', note: 'G#', key: 'G# Minor' },
        { name: 'D# Minor', note: 'D#', key: 'D# Minor' },
        { name: 'A# Minor', note: 'A#', key: 'A# Minor' },
        { name: 'F Minor', note: 'F', key: 'F Minor' },
        { name: 'C Minor', note: 'C', key: 'C Minor' },
        { name: 'G Minor', note: 'G', key: 'G Minor' },
        { name: 'D Minor', note: 'D', key: 'D Minor' }
    ]
};

// Vibe-based dynamic accent profile matching
const STYLE_ACCENTS = {
    'alegre': '245, 158, 11',    // Amber / Yellow
    'oscura': '244, 63, 94',     // Rose / Pink
    'moderna': '16, 185, 129',   // Emerald / Green
    'simple': '140, 140, 140',   // Gray / Neutral
    'default': '6, 182, 212'     // Cyan / Teal
};

// Document Elements
const els = {
    songsList: document.getElementById('songs-list'),
    globalSearch: document.getElementById('global-search'),
    syncBtn: document.getElementById('sync-btn'),
    clearTonalityBtn: document.getElementById('clear-tonality-filter'),
    
    // Stats
    statTotalSongs: document.getElementById('stat-total-songs'),
    statTotalArtists: document.getElementById('stat-total-artists'),
    statHarmonyPct: document.getElementById('stat-harmony-pct'),
    statLikedSongs: document.getElementById('stat-liked-songs'),
    filterLikedCard: document.getElementById('filter-liked-card'),
    
    // Filters
    filterComplexity: document.getElementById('filter-complexity'),
    filterHarmonyStatus: document.getElementById('filter-harmony-status'),
    filterScanStatus: document.getElementById('filter-scan-status'),
    filterStyle: document.getElementById('filter-style'),
    filterProgressionLength: document.getElementById('filter-progression-length'),
    filterProgression: document.getElementById('filter-progression'),
    filterPlaylist: document.getElementById('filter-playlist'),
    explorerCount: document.getElementById('explorer-count'),
    countFiltered: document.getElementById('count-filtered'),
    countTotal: document.getElementById('count-total'),
    filterActiveBadge: document.getElementById('filter-active-badge'),
    bulkRestyleBtn: document.getElementById('bulk-restyle-btn'),
    
    // Sorters
    sortTitleBtn: document.getElementById('sort-title'),
    sortScrobbleBtn: document.getElementById('sort-scrobble'),
    sortScanDateBtn: document.getElementById('sort-scan-date'),
    
    // Focus Panel
    harmonyFocusPanel: document.getElementById('harmony-focus-panel'),
    harmonyEmptyPanel: document.getElementById('harmony-empty-panel'),
    focusSongTitle: document.getElementById('focus-song-title'),
    focusSongArtist: document.getElementById('focus-song-artist'),
    focusSongAlbumYear: document.getElementById('focus-song-album-year'),
    focusLastfmScrobble: document.getElementById('focus-lastfm-scrobble'),
    focusLocalScrobble: document.getElementById('focus-local-scrobble'),
    focusChordsContainer: document.getElementById('focus-chords-container'),
    focusProgressionText: document.getElementById('focus-progression-text'),
    focusProgressionChords: document.getElementById('focus-progression-chords'),
    focusBadgeComplexity: document.getElementById('focus-badge-complexity'),
    focusBadgeStyle: document.getElementById('focus-badge-style'),
    
    // Video
    videoPlaceholder: document.getElementById('video-placeholder'),
    videoWrapper: document.getElementById('video-wrapper'),
    youtubePlayer: document.getElementById('youtube-player'),
    youtubeActionsContainer: document.getElementById('youtube-actions-container'),
    youtubeDirectLink: document.getElementById('youtube-direct-link'),
    closeFocusBtn: document.getElementById('close-focus-panel'),
    
    // Form
    editForm: document.getElementById('edit-harmony-form'),
    editRow: document.getElementById('edit-row'),
    editTonality: document.getElementById('edit-tonality'),
    btnTransposeDown: document.getElementById('btn-transpose-down'),
    btnTransposeUp: document.getElementById('btn-transpose-up'),
    editComplex: document.getElementById('edit-complex'),
    editStyle: document.getElementById('edit-style'),
    editProgression: document.getElementById('edit-progression'),
    editChord: document.getElementById('edit-chord'),
    saveBtn: document.getElementById('save-harmony-btn'),
    
    // HUDs
    audioHud: document.getElementById('audio-hud'),
    audioHudText: document.getElementById('audio-hud-text'),
    toast: document.getElementById('toast'),
    toastMessage: document.getElementById('toast-message'),
    
    // Autodetect & Modal controls
    autodetectBtn: document.getElementById('autodetect-btn'),
    generateImprovBtn: document.getElementById('generate-improvisation-btn'),
    expandImprovModal: document.getElementById('expand-improvisation-modal'),
    closeExpandImprovBtn: document.getElementById('close-expand-improv-btn'),
    expandedImprovTitle: document.getElementById('expanded-improv-song-title'),
    expandedImprovTonality: document.getElementById('expanded-improv-tonality'),
    expandedImprovProgression: document.getElementById('expanded-improv-progression'),
    expandedImprovStyle: document.getElementById('expanded-improv-style'),
    expandedImprovContent: document.getElementById('expanded-improv-content'),
    sourceTabs: document.querySelectorAll('.source-tab'),
    confirmModal: document.getElementById('confirm-modal'),
    suggestConfidence: document.getElementById('suggest-confidence'),
    suggestSource: document.getElementById('suggest-source'),
    modalRegisteredSong: document.getElementById('modal-registered-song'),
    modalSuggestedSong: document.getElementById('modal-suggested-song'),
    currentChordsPreview: document.getElementById('current-chords-preview'),
    suggestedChordsPreview: document.getElementById('suggested-chords-preview'),
    modalRejectBtn: document.getElementById('modal-reject-btn'),
    modalAcceptBtn: document.getElementById('modal-accept-btn'),
    autocompletePlaylistBtn: document.getElementById('autocomplete-playlist-btn'),
    playlistCacheInfo: document.getElementById('playlist-cache-info'),
    cacheTimeLabel: document.getElementById('cache-time-label'),
    resetPlaylistCacheBtn: document.getElementById('reset-playlist-cache-btn'),
    songCacheContainer: document.getElementById('song-cache-container'),
    songCacheLabel: document.getElementById('song-cache-label'),
    resetSongCacheBtn: document.getElementById('reset-song-cache-btn'),
    deleteHarmonyBtn: document.getElementById('delete-harmony-btn'),
    justFoundBanner: document.getElementById('just-found-banner'),
    justFoundCount: document.getElementById('just-found-count'),
    clearJustFoundBtn: document.getElementById('clear-just-found-btn')
};

// Initial Setup on DOM Load
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        initApp();
        setupEventListeners();
    });
} else {
    initApp();
    setupEventListeners();
}

// Primary Initialization
function initApp() {
    // Purge legacy browser scan cache so Google Sheets LastScanned column is always the single source of truth
    localStorage.removeItem('vibemus_song_scan_cache');
    
    // 1. Check local storage cache for instant rendering
    const cachedData = localStorage.getItem('vibemus_songs_data');
    if (cachedData) {
        console.log("Cargando catálogo musical desde LocalStorage...");
        try {
            const parsed = JSON.parse(cachedData);
            // Only use cache if it has valid songs (not empty or corrupted)
            if (Array.isArray(parsed) && parsed.length > 0) {
                // Purge corrupted lyrics from cached data
                let cleanedAny = false;
                parsed.forEach(s => {
                    if (s.lyrics && !_filterAndValidateLyrics(s.lyrics)) {
                        s.lyrics = null;
                        cleanedAny = true;
                    }
                });
                state.songs = parsed;
                if (cleanedAny) {
                    try { localStorage.setItem('vibemus_songs_data', JSON.stringify(state.songs)); } catch(e) { console.warn('Cache quota exceeded'); }
                }
                processSongsMetadata();
                applyFiltersAndRender();
                recoverRecentlyFoundSongs();
            } else {
                console.warn("Caché local vacío o inválido, limpiando...");
                localStorage.removeItem('vibemus_songs_data');
                renderSkeletons();
            }
        } catch (e) {
            console.error("Error al parsear cache local:", e);
            localStorage.removeItem('vibemus_songs_data');
            renderSkeletons();
        }
    } else {
        renderSkeletons();
    }
    
    // 2. Fetch fresh catalog from Cloud Server (Google Sheets API through Python)
    fetchSongsFromServer();
    
    // 3. Render Circle of Fifths skeleton
    drawCircleOfFifths();
}

// Fetch data from server
async function fetchSongsFromServer() {
    setSyncingStatus(true);
    try {
        const response = await fetch('/api/songs?_t=' + new Date().getTime());
        if (!response.ok) throw new Error(`La API del servidor falló: ${response.status}`);
        
        const data = await response.json();
        
        // Check for server-side error responses (e.g., {"error": "..."})
        if (data && data.error) {
            throw new Error(`Error del servidor: ${data.error}`);
        }
        
        if (Array.isArray(data) && data.length > 0) {
            console.log(`¡Catálogo sincronizado desde Google Sheets! ${data.length} canciones.`);
            state.songs = data;
            
            // Update cache only with valid non-empty data
            try { localStorage.setItem('vibemus_songs_data', JSON.stringify(state.songs)); } catch(e) { console.warn('Cache quota exceeded'); }
            
            processSongsMetadata();
            applyFiltersAndRender();
            recoverRecentlyFoundSongs();
        } else {
            console.warn("El servidor devolvió datos vacíos o inválidos", data);
            // Don't overwrite existing local cache with empty data
            if (state.songs.length === 0) {
                showToast("El servidor no devolvió canciones. Revisa la conexión.", true);
            }
        }
    } catch (error) {
        console.warn("Error al sincronizar con el servidor:", error);
        showToast("Modo Offline: Datos leídos del navegador", true);
    } finally {
        setSyncingStatus(false);
    }
}

// Clear all local caches and force a fresh reload from server
function clearAllCacheAndReload() {
    localStorage.removeItem('vibemus_songs_data');
    localStorage.removeItem('vibemus_song_scan_cache');
    // Clear all vibemus_ prefixed keys
    Object.keys(localStorage).filter(k => k.startsWith('vibemus_')).forEach(k => localStorage.removeItem(k));
    state.songs = [];
    state.filteredSongs = [];
    state.selectedSong = null;
    renderSkeletons();
    fetchSongsFromServer();
    showToast("Caché limpiado. Recargando catálogo...");
}

// Poll the server: warn while a CLI command (playlist sync…) may be rewriting the sheet
let cliBusyShown = false;
async function pollSheetStatus() {
    try {
        const info = await (await fetch('/api/sheet-status')).json();
        const label = document.querySelector('.status-label');
        const dot = document.querySelector('.status-dot');
        if (info.busy && !cliBusyShown) {
            showToast(`Hay un comando de Vibemus en curso (${info.command}). Evita escanear armonías hasta que termine.`);
        }
        if (label && dot && !document.querySelector('.status-dot.syncing')) {
            dot.className = info.busy ? "status-dot syncing" : "status-dot online";
            label.textContent = info.busy ? `CLI en curso: ${info.command}` : "Online";
        }
        cliBusyShown = info.busy;
    } catch (e) { /* server restarting */ }
}
setInterval(pollSheetStatus, 15000);

// Set status indicator syncing state
function setSyncingStatus(isSyncing) {
    const dot = document.querySelector('.status-dot');
    const label = document.querySelector('.status-label');
    
    if (isSyncing) {
        dot.className = "status-dot syncing";
        label.textContent = "Sincronizando...";
    } else {
        dot.className = "status-dot online";
        label.textContent = "Online";
    }
}

// Process data to extract stats, genres, playlists and styles
function processSongsMetadata() {
    state.availableStyles.clear();
    state.availablePlaylists.clear();
    state.availableProgressions.clear();
    state.availableProgressionLengths.clear();
    
    let withChords = 0;
    let likedCount = 0;
    const artists = new Set();
    
    state.songs.forEach(song => {
        if (song.chord && song.chord.trim() !== '') withChords++;
        if (song.liked) likedCount++;
        if (song.artist) artists.add(song.artist);
        
        // Extract style (normalize to lowercase first-letter capitalized, splitting by commas)
        if ((song.emotional || song.style) && (song.emotional || song.style).trim() !== '') {
            const styles = (song.emotional || song.style).split(',').map(s => s.trim().toLowerCase());
            styles.forEach(s => {
                if (s !== '') {
                    state.availableStyles.add(s.charAt(0).toUpperCase() + s.slice(1));
                }
            });
        }
        
        // Extract playlist
        if (song.playlist && song.playlist.trim() !== '') {
            state.availablePlaylists.add(song.playlist.trim());
        }
        
        // Extract progression and its length
        if (song.progression && song.progression.trim() !== '') {
            state.availableProgressions.add(song.progression.trim());
            const chordCount = getProgressionLength(song.progression);
            if (chordCount >= 2) state.availableProgressionLengths.add(chordCount);
        }
    });
    
    // Stats update
    els.statTotalSongs.textContent = state.songs.length;
    els.statTotalArtists.textContent = artists.size;
    els.statLikedSongs.textContent = likedCount;
    
    const harmonyPct = state.songs.length > 0 ? Math.round((withChords / state.songs.length) * 100) : 0;
    els.statHarmonyPct.textContent = `${harmonyPct}%`;
    
    // Update dropdown lists
    populateFilters();
    
    // Re-draw Circle of Fifths to update segment glows based on song frequency
    drawCircleOfFifths();

    // Auto-initialize cache from existing data
    initializeCacheFromExistingData();
    
    // Update active playlist cache UI if selected
    if (state.activeFilters.playlist && state.activeFilters.playlist !== 'all') {
        updatePlaylistCacheUI(state.activeFilters.playlist);
    }
}

// Populate Filter elements dynamically
function populateFilters() {
    // 1. Playlists Select
    const currentPlaylistVal = els.filterPlaylist.value;
    els.filterPlaylist.innerHTML = '<option value="all">Todas las Playlists</option>';
    state.availablePlaylists.forEach(playlist => {
        const opt = document.createElement('option');
        opt.value = playlist;
        opt.textContent = playlist;
        els.filterPlaylist.appendChild(opt);
    });
    els.filterPlaylist.value = currentPlaylistVal;

    // 1b. Progression Length Select (minimum 2, shown as plain number)
    const currentProgressionLengthVal = els.filterProgressionLength.value;
    els.filterProgressionLength.innerHTML = '<option value="all">Cualquier Longitud</option>';
    Array.from(state.availableProgressionLengths).sort((a, b) => a - b).forEach(len => {
        if (len < 2) return; // skip single-chord entries
        const opt = document.createElement('option');
        opt.value = String(len); // always string for reliable e.target.value comparison
        opt.textContent = String(len);
        els.filterProgressionLength.appendChild(opt);
    });
    els.filterProgressionLength.value = currentProgressionLengthVal;

    // 1c. Progressions Select (filtered by active length if set)
    populateProgressionOptions();
    
    // 2. Style Badges
    const styleContainer = els.filterStyle;
    const allActive = state.activeFilters.styles.size === 0;
    styleContainer.innerHTML = `<button class="tag-btn${allActive ? ' active' : ''}" data-style="all">Todos</button>`;
    state.availableStyles.forEach(styleName => {
        const btn = document.createElement('button');
        btn.className = "tag-btn";
        if (state.activeFilters.styles.has(styleName)) btn.classList.add('active');
        btn.setAttribute('data-style', styleName);
        btn.textContent = styleName;
        styleContainer.appendChild(btn);
    });
}

// Populate Progresión Numérica options based on active progression length filter
function populateProgressionOptions() {
    if (!els.filterProgression) return;
    const currentProgressionVal = state.activeFilters.progression || 'all';
    const activeLen = state.activeFilters.progressionLength;
    els.filterProgression.innerHTML = '<option value="all">Todas las Progresiones</option>';
    
    Array.from(state.availableProgressions).sort().forEach(progression => {
        // If a length filter is active, only show progressions that match that length
        if (activeLen !== 'all') {
            const len = getProgressionLength(progression);
            if (String(len) !== activeLen) return;
        }
        const opt = document.createElement('option');
        opt.value = progression;
        opt.textContent = progression;
        els.filterProgression.appendChild(opt);
    });
    
    // Restore value if option still exists, otherwise reset to 'all'
    const exists = Array.from(els.filterProgression.options).some(opt => opt.value === currentProgressionVal);
    els.filterProgression.value = exists ? currentProgressionVal : 'all';
    state.activeFilters.progression = els.filterProgression.value;
}

// Draw Interactive Circle of Fifths Visualizer
function drawCircleOfFifths() {
    const svg = els.circleFifthsSVG || document.getElementById('circle-fifths-svg');
    if (!svg) return;
    svg.innerHTML = '';
    
    // Calculate song counts per tonality to define glow/opacity
    const tonalityCounts = {};
    state.songs.forEach(song => {
        if (song.tonality) {
            const key = song.tonality.trim().toLowerCase();
            tonalityCounts[key] = (tonalityCounts[key] || 0) + 1;
        }
    });
    
    const maxCount = Math.max(...Object.values(tonalityCounts), 1);
    
    const size = 400;
    const cx = size / 2;
    const cy = size / 2;
    
    // Add central circle structure
    const centralRing = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    centralRing.setAttribute('cx', cx);
    centralRing.setAttribute('cy', cy);
    centralRing.setAttribute('r', '75');
    centralRing.setAttribute('class', 'circle-inner-ring');
    svg.appendChild(centralRing);
    
    // Draw sector bands: Major (Outer) and Minor (Inner)
    const drawRingSectors = (ringType, keys, innerR, outerR) => {
        const sectorAngle = 360 / 12;
        
        keys.forEach((k, idx) => {
            const startAngle = (idx * sectorAngle - 90 - sectorAngle / 2);
            const endAngle = (startAngle + sectorAngle);
            
            // Calculate Path coordinates for concentric sector
            const rad = Math.PI / 180;
            const x1_in = cx + innerR * Math.cos(startAngle * rad);
            const y1_in = cy + innerR * Math.sin(startAngle * rad);
            const x2_in = cx + innerR * Math.cos(endAngle * rad);
            const y2_in = cy + innerR * Math.sin(endAngle * rad);
            
            const x1_out = cx + outerR * Math.cos(startAngle * rad);
            const y1_out = cy + outerR * Math.sin(startAngle * rad);
            const x2_out = cx + outerR * Math.cos(endAngle * rad);
            const y2_out = cy + outerR * Math.sin(endAngle * rad);
            
            const pathData = `
                M ${x1_out} ${y1_out}
                A ${outerR} ${outerR} 0 0 1 ${x2_out} ${y2_out}
                L ${x2_in} ${y2_in}
                A ${innerR} ${innerR} 0 0 0 ${x1_in} ${y1_in}
                Z
            `;
            
            // Render sector path
            const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
            path.setAttribute('d', pathData);
            path.setAttribute('class', 'circle-key-sector');
            
            // Calculate density glow color
            const songCount = tonalityCounts[k.key.toLowerCase()] || 0;
            const densityRatio = maxCount > 0 ? songCount / maxCount : 0;
            
            // Custom sector styles
            let strokeColor = 'rgba(255,255,255,0.06)';
            let fill = 'rgba(10, 10, 10, 0.4)';
            
            if (state.activeFilters.tonality === k.key) {
                // Highly active glowing filter accent
                fill = `rgba(var(--accent-rgb), 0.35)`;
                strokeColor = `rgb(var(--accent-rgb))`;
            } else if (songCount > 0) {
                // Gentle glow relative to song frequency
                fill = `rgba(var(--accent-rgb), ${0.05 + densityRatio * 0.2})`;
                strokeColor = `rgba(var(--accent-rgb), ${0.15 + densityRatio * 0.3})`;
            }
            
            path.setAttribute('fill', fill);
            path.setAttribute('stroke', strokeColor);
            path.setAttribute('stroke-width', '1');
            
            // Interaction click
            path.addEventListener('click', () => {
                setTonalityFilter(k.key);
            });
            
            svg.appendChild(path);
            
            // Place text labels dynamically
            const textAngle = startAngle + sectorAngle / 2;
            const textRadius = (innerR + outerR) / 2;
            const tx = cx + textRadius * Math.cos(textAngle * rad);
            const ty = cy + textRadius * Math.sin(textAngle * rad) + 4; // micro-offset
            
            const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
            text.setAttribute('x', tx);
            text.setAttribute('y', ty);
            text.setAttribute('text-anchor', 'middle');
            text.setAttribute('class', 'circle-key-text');
            
            // Text visual styling
            if (songCount > 0) {
                text.setAttribute('fill', 'var(--text-primary)');
                text.setAttribute('font-weight', '700');
            } else {
                text.setAttribute('fill', 'var(--text-tertiary)');
            }
            
            text.textContent = k.note + (ringType === 'inner' ? 'm' : '');
            svg.appendChild(text);
        });
    };
    
    // Draw rings: Outer Major (140px to 190px radius), Inner Minor (90px to 140px radius)
    drawRingSectors('outer', CIRCLE_KEYS.outer, 135, 185);
    drawRingSectors('inner', CIRCLE_KEYS.inner, 85, 135);
    
    // Add central circle text detailing selection
    const textLabel = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    textLabel.setAttribute('x', cx);
    textLabel.setAttribute('y', cy);
    textLabel.setAttribute('text-anchor', 'middle');
    textLabel.setAttribute('fill', 'var(--text-secondary)');
    textLabel.setAttribute('font-size', '10px');
    textLabel.setAttribute('font-weight', '700');
    textLabel.setAttribute('letter-spacing', '0.1em');
    textLabel.textContent = state.activeFilters.tonality ? 'TONALIDAD ACTIVA' : 'SELECCIÓN';
    svg.appendChild(textLabel);
    
    const textValue = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    textValue.setAttribute('x', cx);
    textValue.setAttribute('y', cy + 18);
    textValue.setAttribute('text-anchor', 'middle');
    textValue.setAttribute('fill', state.activeFilters.tonality ? 'var(--accent-color)' : 'var(--text-tertiary)');
    textValue.setAttribute('font-size', '14px');
    textValue.setAttribute('font-weight', '800');
    textValue.textContent = state.activeFilters.tonality ? state.activeFilters.tonality : 'Ninguna';
    svg.appendChild(textValue);
}

// Handle key filtration
function setTonalityFilter(key) {
    if (state.activeFilters.tonality === key) {
        state.activeFilters.tonality = null;
        els.clearTonalityBtn.classList.add('hide');
    } else {
        state.activeFilters.tonality = key;
        els.clearTonalityBtn.classList.remove('hide');
    }
    drawCircleOfFifths();
    applyFiltersAndRender();
}

// Clear Circle of Fifths filter
els.clearTonalityBtn.addEventListener('click', () => {
    state.activeFilters.tonality = null;
    els.clearTonalityBtn.classList.add('hide');
    drawCircleOfFifths();
    applyFiltersAndRender();
});

// Render Skeleton loading containers
function renderSkeletons() {
    els.songsList.innerHTML = '';
    for (let i = 0; i < 6; i++) {
        const skel = document.createElement('div');
        skel.className = "skeleton-row animate-pulse";
        els.songsList.appendChild(skel);
    }
}

// Helper: count chords in a progression string (e.g. "I - V - vi" → 3)
function getProgressionLength(progression) {
    if (!progression || progression.trim() === '') return 0;
    const trimmed = progression.trim();
    // Count occurrences of ' - ' and add 1 to get the number of chords
    const separators = (trimmed.match(/ - /g) || []).length;
    return separators + 1;
}

// Core Filter Engine
function applyFiltersAndRender() {
    const filters = state.activeFilters;
    
    let songCache = {};
    try {
        songCache = JSON.parse(localStorage.getItem('vibemus_song_scan_cache') || '{}');
    } catch (e) {}
    
    state.filteredSongs = state.songs.filter(song => {
        // If "Just Found" verification filter is active, bypass all other filters to show exactly these songs
        if (filters.justFound) {
            return state.justFoundRows && state.justFoundRows.includes(song.row);
        }

        // 1. Text Search (title, artist)
        const query = filters.search.toLowerCase();
        const matchesSearch = query === '' || 
            (song.title && song.title.toLowerCase().includes(query)) ||
            (song.artist && song.artist.toLowerCase().includes(query));
            
        // 2. Tonality / Key signature filter
        const matchesTonality = !filters.tonality || 
            (song.tonality && song.tonality.trim().toLowerCase() === filters.tonality.toLowerCase());
            
        // 3. Complexity filter
        const currentSkill = song.skill || song.complex;
        const matchesComplexity = filters.complexity === 'all' || 
            (currentSkill && currentSkill.toLowerCase() === filters.complexity.toLowerCase());
            
        // 4. Style filter — multi-select AND: song must have ALL selected styles
        const currentStyle = song.emotional || song.style;
        const songStyles = currentStyle
            ? currentStyle.split(',').map(s => { const t = s.trim().toLowerCase(); return t.charAt(0).toUpperCase() + t.slice(1); })
            : [];
        const matchesStyle = filters.styles.size === 0 ||
            [...filters.styles].every(sel => songStyles.includes(sel));
            
        // 5. Playlist filter
        const matchesPlaylist = filters.playlist === 'all' || 
            (song.playlist && song.playlist === filters.playlist);
            
        // 5b. Progression length filter
        const songProgressionLength = getProgressionLength(song.progression);
        const matchesProgressionLength = filters.progressionLength === 'all' ||
            String(songProgressionLength) === filters.progressionLength;

        // 5c. Progression filter
        const matchesProgression = filters.progression === 'all' || 
            (song.progression && song.progression === filters.progression);
            
        // 6. Harmony Status filter
        const hasHarmony = song.chord && song.chord.trim() !== '';
        const isSelected = state.selectedSong && 
            (state.selectedSong.row === song.row || 
             (state.selectedSong.title === song.title && state.selectedSong.artist === song.artist));
        const matchesHarmonyStatus = filters.harmonyStatus === 'all' || 
            (filters.harmonyStatus === 'with' && (hasHarmony || isSelected)) ||
            (filters.harmonyStatus === 'without' && (!hasHarmony || isSelected));
 
        // 7. Scan Status filter
        const key = `${song.artist} - ${song.title}`;
        const hasScanDate = !!(song.lastScanDate || songCache[key]);
        const matchesScanStatus = filters.scanStatus === 'all' ||
            (filters.scanStatus === 'scanned' && (hasScanDate || isSelected)) ||
            (filters.scanStatus === 'never' && (!hasScanDate || isSelected));
        // 8. Liked Status filter
        const matchesLiked = !filters.likedOnly || song.liked;
            
        return matchesSearch && matchesTonality && matchesComplexity && matchesStyle && matchesPlaylist && matchesProgressionLength && matchesProgression && matchesHarmonyStatus && matchesScanStatus && matchesLiked;
    });
    
    // Sort songs
    sortSongs();
    
    // Render list
    renderSongsExplorer();
}

// Sorting logic
function sortSongs() {
    if (state.sortRule === 'title-asc') {
        state.filteredSongs.sort((a, b) => {
            const titleA = (a.title || '').toLowerCase();
            const titleB = (b.title || '').toLowerCase();
            return titleA.localeCompare(titleB);
        });
    } else if (state.sortRule === 'scrobble-desc') {
        state.filteredSongs.sort((a, b) => {
            const scrobbleA = parseInt(a.scrobble) || 0;
            const scrobbleB = parseInt(b.scrobble) || 0;
            return scrobbleB - scrobbleA;
        });
    } else if (state.sortRule === 'scan-desc') {
        let songCache = {};
        try {
            songCache = JSON.parse(localStorage.getItem('vibemus_song_scan_cache') || '{}');
        } catch (e) {}
        
        state.filteredSongs.sort((a, b) => {
            const getScanTime = (song) => {
                if (state.selectedSong && state.selectedSong.row === song.row) {
                    return state.selectedSongScanTime ? new Date(state.selectedSongScanTime).getTime() : 0;
                }
                const key = `${song.artist} - ${song.title}`;
                const t = song.lastScanDate || songCache[key];
                return t ? new Date(t).getTime() : 0;
            };
            
            const timeA = getScanTime(a);
            const timeB = getScanTime(b);
            return timeB - timeA; // newest first
        });
    }
}

// Render Song List into GUI
function renderSongsExplorer() {
    const container = els.songsList;
    container.innerHTML = '';
    
    // Update the rich filter counter
    const filtered = state.filteredSongs.length;
    const total = state.songs.length;
    els.countFiltered.textContent = filtered;
    els.countTotal.textContent = total;

    // Detect if any filter is active
    const f = state.activeFilters;
    const isFiltered = f.justFound ||
        f.search !== '' ||
        f.tonality !== null ||
        f.complexity !== 'all' ||
        f.styles.size > 0 ||
        f.playlist !== 'all' ||
        f.progressionLength !== 'all' ||
        f.progression !== 'all' ||
        f.harmonyStatus !== 'all' ||
        f.scanStatus !== 'all';

    els.explorerCount.classList.toggle('is-filtered', isFiltered);
    els.filterActiveBadge.classList.toggle('hide', !isFiltered);
    
    if (state.filteredSongs.length === 0) {
        container.innerHTML = `
            <div class="songs-empty-state">
                <i class="ph ph-mask-sad"></i>
                <h4 class="empty-title">Sin Resultados</h4>
                <p class="empty-description">Prueba a limpiar los filtros o cambia la consulta de búsqueda.</p>
            </div>
        `;
        return;
    }
    
    let songCache = {};
    try {
        songCache = JSON.parse(localStorage.getItem('vibemus_song_scan_cache') || '{}');
    } catch (e) {}
    
    state.filteredSongs.forEach((song, idx) => {
        const card = document.createElement('div');
        card.className = "song-row";
        card.setAttribute('data-row-num', song.row);
        if (state.selectedSong && state.selectedSong.row === song.row) {
            card.classList.add('selected');
        }
        
        // Define complexity complexity badge
        const hasHarmony = song.chord && song.chord.trim() !== '';
        let compBadgeClass = 'badge-none';
        let compText = '—';
        if (hasHarmony) {
            compText = song.skill || song.complex || 'Baja';
            if (compText === 'Media') compBadgeClass = 'badge-mid';
            else if (compText === 'Media-Alta' || compText === 'Alta') compBadgeClass = 'badge-high';
            else compBadgeClass = 'badge-low';
        }
        
        const key = `${song.artist} - ${song.title}`;
        const scanTime = song.lastScanDate || songCache[key];
        let scanDisplay = '';
        if (scanTime) {
            const formatted = formatCacheDate(scanTime);
            scanDisplay = `<div class="song-row-scan-date" style="font-size: 10px; color: var(--text-tertiary); margin-top: 4px; display: flex; align-items: center; gap: 4px;"><i class="ph ph-calendar"></i> Escaneado: ${formatted}</div>`;
        } else {
            scanDisplay = `<div class="song-row-scan-date" style="font-size: 10px; color: var(--text-tertiary); margin-top: 4px; display: flex; align-items: center; gap: 4px; opacity: 0.5;"><i class="ph ph-calendar-blank"></i> Nunca escaneado</div>`;
        }
        
        card.innerHTML = `
            <div class="song-row-index font-mono">#${idx + 1}</div>
            <div class="song-row-info">
                <div class="song-row-title">${song.title || 'Desconocido'}</div>
                <div class="song-row-artist">${song.artist || 'Desconocido'}</div>
                ${scanDisplay}
            </div>
            <div class="song-row-album">${song.album || '—'}</div>
            <div class="song-row-tonality font-mono">${song.tonality || '—'}</div>
            <div class="song-row-badge ${compBadgeClass}">${compText}</div>
            <div class="song-row-like ${song.liked ? 'liked' : ''}"><i class="${song.liked ? 'ph-fill' : 'ph'} ph-heart"></i></div>
        `;
        
        card.addEventListener('click', (e) => {
            if (e.target.closest('.song-row-like')) {
                toggleLikeSong(song);
                return;
            }
            selectSong(song);
        });
        
        container.appendChild(card);
    });
}

// Filter and validate lyrics data quality.
// Rejects tab-type tablature notation (e|---, B|---, etc.) and editorial prose.
// Removes sections with no chords and strips long unchorded prose lines.
// Returns filtered sections array, or null if invalid or poor quality.
function _filterAndValidateLyrics(lyricsData) {
    if (!lyricsData || !Array.isArray(lyricsData) || !lyricsData.length) return null;

    const TAB_PATTERN = /(^[eBGDAE]\s*\|.*[-—]{2,})|(\|[-—]{3,}\|)|([-—]{5,})|(\b[eBGDAE]\|[-—])/i;
    const PROSE_TRIGGER_WORDS = /\b(preface|fretboard|first guitar|second guitar|bump up that reverb|usable chords)\b/i;

    // Step 1: Filter sections and lines
    const filtered = lyricsData.map(sec => {
        if (!sec.lines || !sec.lines.length) return null;

        // Strip bad lines (tabs, prose, long unchorded text)
        const cleanedLines = sec.lines.filter(l => {
            const text = (l.lyric || '').trim();
            if (text && (TAB_PATTERN.test(text) || PROSE_TRIGGER_WORDS.test(text))) {
                return false;
            }
            
            const hasChords = l.chords && l.chords.length > 0;
            if (hasChords) return true;
            if (!text) return false;
            if (text.length > 45) return false;
            return true;
        });
        
        if (!cleanedLines.length) return null;
        const hasAnyChord = cleanedLines.some(l => l.chords && l.chords.length > 0);
        if (!hasAnyChord) return null; // Entire section has zero chords

        return { ...sec, lines: cleanedLines };
    }).filter(Boolean);

    if (!filtered.length) return null;

    // Step 2: Global density check on what remains — at least 25% of lyric lines need chords
    const lyricLines = filtered.flatMap(sec => sec.lines).filter(l => l.lyric && l.lyric.trim());
    if (!lyricLines.length) return null;
    const withChords = lyricLines.filter(l => l.chords && l.chords.length > 0).length;
    if (withChords / lyricLines.length < 0.25) return null;

    return filtered;
}

// Backward-compat shim used by the selectSong guard
function _lyricsHasValidChordDensity(lyricsData) {
    return !!_filterAndValidateLyrics(lyricsData);
}

// Select Song and Focus Dashboard Details Panel

async function toggleLikeSong(song) {
    const prevLiked = song.liked;
    song.liked = !song.liked;
    
    // Update UI immediately
    updateSongCardInDOM(song);
    let currentLikedCount = parseInt(els.statLikedSongs.textContent) || 0;
    els.statLikedSongs.textContent = song.liked ? currentLikedCount + 1 : currentLikedCount - 1;
    
    try {
        const response = await apiUpdateFetch('/api/update', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                row: song.row,
                artist: song.artist,
                title: song.title,
                liked: song.liked
            })
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        showToast(song.liked ? 'Añadida a Liked ❤️' : 'Eliminada de Liked 💔');
        
        // Update local cache
        try { localStorage.setItem('vibemus_songs_data', JSON.stringify(state.songs)); } catch(e) { console.warn('Cache quota exceeded'); }
    } catch (err) {
        console.error("Error updating Like status:", err);
        showToast("Error al guardar en la nube", true);
        
        // Revert on error
        song.liked = prevLiked;
        updateSongCardInDOM(song);
        let revertCount = parseInt(els.statLikedSongs.textContent) || 0;
        els.statLikedSongs.textContent = song.liked ? revertCount + 1 : revertCount - 1;
    }
}

function selectSong(song, shouldRedrawList = true) {
    // Capture the original scan time for this song if newly selected, to prevent sudden re-sorting in list
    if (!state.selectedSong || state.selectedSong.row !== song.row) {
        let songCache = {};
        try {
            songCache = JSON.parse(localStorage.getItem('vibemus_song_scan_cache') || '{}');
        } catch (e) {}
        const key = `${song.artist} - ${song.title}`;
        state.selectedSongScanTime = song.lastScanDate || songCache[key] || null;
    }
    
    state.selectedSong = song;
    
    // Highlight active selected row directly in the DOM
    document.querySelectorAll('.song-row').forEach(row => {
        if (parseInt(row.getAttribute('data-row-num')) === song.row) {
            row.classList.add('selected');
        } else {
            row.classList.remove('selected');
        }
    });
    
    if (shouldRedrawList) {
        applyFiltersAndRender(); // Redraws and maintains selection class
    }
    
    // Shift layout to show details
    document.querySelector('.workspace-grid').classList.add('focus-active');
    els.harmonyFocusPanel.classList.remove('hide');
    els.harmonyEmptyPanel.classList.add('hide');
    
    // Update Details Text
    els.focusSongTitle.textContent = song.title;
    els.focusSongArtist.textContent = song.artist;
    
    const albumDetails = [song.album, song.year].filter(x => x && x.trim() !== '').join(' — ');
    els.focusSongAlbumYear.textContent = albumDetails || 'Álbum Desconocido';
    els.focusProgressionText.textContent = song.progression || '— Sin Progresión Numérica';
    els.focusProgressionChords.textContent = romanProgressionToChords(song.progression, song.tonality) || '';
    renderProgressionDiagrams(document.getElementById('focus-progression-diagrams'), song.progression, song.tonality);
    
    // Set Scrobbles
    els.focusLastfmScrobble.textContent = parseInt(song.lastfmScrobble || 0).toLocaleString();
    els.focusLocalScrobble.textContent = parseInt(song.scrobble || 0).toLocaleString();
    
    // Set Badges
    const hasHarmony = song.chord && song.chord.trim() !== '';

    // When switching songs, reset lyrics state & view mode
    // Restore persisted lyrics from Google Sheets column Q if available,
    // filtering out prose-only sections and validating chord density.
    const cleanedLyrics = _filterAndValidateLyrics(song.lyrics);
    if (cleanedLyrics) {
        state.selectedLyrics = cleanedLyrics;
        state.chordViewMode = 'lyrics';
    } else {
        state.selectedLyrics = null;
        state.chordViewMode = 'diagrams';
        // If song had corrupted/invalid lyrics in cache, sanitize it
        if (song.lyrics) {
            song.lyrics = null;
            try {
                try { localStorage.setItem('vibemus_songs_data', JSON.stringify(state.songs)); } catch(e) { console.warn('Cache quota exceeded'); }
            } catch (e) {}
        }
    }

    els.focusBadgeComplexity.textContent = hasHarmony ? (song.skill || song.complex || 'Baja') : '—';
    els.focusBadgeStyle.textContent = song.emotional || song.style || 'Sin Estilo';
    
    // Update individual song cache UI
    updateSongCacheUI(song);
    
    // Set Accent Vibe Palette (Dynamic Visual Response)
    shiftVibeAccentColor(song.emotional || song.style);
    
    // Render Chords Structure (with persisted lyrics if available)
    renderChordSheet(song.chord, state.selectedLyrics);
    renderImprovisationGuide(song);

    
    // Load YouTube Video Embed safely
    loadYouTubeEmbed(song.videoId);
    
    // Fill Edit Form Values
    els.editRow.value = song.row;
    setSelectTonalityValue(song.tonality || '');
    state.lastActiveTonality = els.editTonality.value || song.tonality || '';
    els.editComplex.value = song.skill || song.complex || 'Baja';
    els.editStyle.value = song.emotional || song.style || '';
    els.editProgression.value = song.progression || '';
    els.editChord.value = song.chord || '';
    
    // Smooth scroll down to details if mobile viewport
    if (window.innerWidth <= 1024) {
        els.harmonyFocusPanel.scrollIntoView({ behavior: 'smooth' });
    }
}

// Shift UI Theme Accents dynamically based on song style vibe
function shiftVibeAccentColor(style) {
    if (!style) {
        setCSSAccent('default');
        return;
    }
    
    const cleanStyle = style.trim().toLowerCase();
    
    // Matching vibe classes
    if (cleanStyle.includes('alegre') || cleanStyle.includes('folk') || cleanStyle.includes('pop')) {
        setCSSAccent('alegre');
    } else if (cleanStyle.includes('oscura') || cleanStyle.includes('sad') || cleanStyle.includes('emo') || cleanStyle.includes('slowcore') || cleanStyle.includes('melancólica') || cleanStyle.includes('soñadora')) {
        setCSSAccent('oscura');
    } else if (cleanStyle.includes('moderna') || cleanStyle.includes('complex') || cleanStyle.includes('indie') || cleanStyle.includes('shoegaze')) {
        setCSSAccent('moderna');
    } else if (cleanStyle.includes('simple') || cleanStyle.includes('acoustic')) {
        setCSSAccent('simple');
    } else {
        setCSSAccent('default');
    }
}

function setCSSAccent(profileKey) {
    const rgbStr = STYLE_ACCENTS[profileKey] || STYLE_ACCENTS['default'];
    document.documentElement.style.setProperty('--accent-rgb', rgbStr);
    
    // Force redraw of Circle of Fifths to change color palette
    drawCircleOfFifths();
}

// ==========================================
// GUITAR CHORD DIAGRAM ENGINE & DATABASE
// ==========================================

// Movable (no open strings) chord shapes, low E → high e. Offsets are relative to the root fret;
// null = muted string. E-shape holds the root on the 6th string, A-shape on the 5th.
const X = null;
const CHORD_SHAPE_TEMPLATES = {
    E: {
        rootString: 0,
        shapes: {
            maj:   { o: [0, 2, 2, 1, 0, 0],   f: [1, 3, 4, 2, 1, 1] },
            m:     { o: [0, 2, 2, 0, 0, 0],   f: [1, 3, 4, 1, 1, 1] },
            7:     { o: [0, 2, 0, 1, 0, 0],   f: [1, 3, 1, 2, 1, 1] },
            maj7:  { o: [0, X, 1, 1, 0, X],   f: [2, 0, 3, 4, 1, 0] },
            m7:    { o: [0, 2, 0, 0, 0, 0],   f: [1, 3, 1, 1, 1, 1] },
            m9:    { o: [0, 2, 0, 0, 0, 2],   f: [1, 3, 1, 1, 1, 4] },
            maj9:  { o: [0, X, 1, 1, 0, 2],   f: [1, 0, 2, 3, 1, 4] },
            9:     { o: [0, 2, 0, 1, 0, 2],   f: [1, 3, 1, 2, 1, 4] },
            13:    { o: [0, X, 0, 1, 2, X],   f: [1, 0, 2, 3, 4, 0] },
            sus4:  { o: [0, 2, 2, 2, 0, 0],   f: [1, 2, 3, 4, 1, 1] },
            '7sus4': { o: [0, 2, 0, 2, 0, 0], f: [1, 3, 1, 4, 1, 1] },
            6:     { o: [0, X, -1, 1, 0, X],  f: [2, 0, 1, 4, 3, 0] },
            m6:    { o: [0, X, -1, 0, 0, X],  f: [2, 0, 1, 3, 4, 0] },
            m7b5:  { o: [0, X, 0, 0, -1, X],  f: [2, 0, 3, 4, 1, 0] },
            dim7:  { o: [0, X, -1, 0, -1, X], f: [2, 0, 1, 3, 1, 0] },
            5:     { o: [0, 2, 2, X, X, X],   f: [1, 3, 4, 0, 0, 0] }
        }
    },
    A: {
        rootString: 1,
        shapes: {
            maj:   { o: [X, 0, 2, 2, 2, 0],   f: [0, 1, 2, 3, 4, 1] },
            m:     { o: [X, 0, 2, 2, 1, 0],   f: [0, 1, 3, 4, 2, 1] },
            7:     { o: [X, 0, 2, 0, 2, 0],   f: [0, 1, 3, 1, 4, 1] },
            maj7:  { o: [X, 0, 2, 1, 2, 0],   f: [0, 1, 3, 2, 4, 1] },
            m7:    { o: [X, 0, 2, 0, 1, 0],   f: [0, 1, 3, 1, 2, 1] },
            m9:    { o: [X, 0, -2, 0, 0, X],  f: [0, 2, 1, 3, 3, 0] },
            maj9:  { o: [X, 0, -1, 1, 0, X],  f: [0, 2, 1, 4, 3, 0] },
            9:     { o: [X, 0, -1, 0, 0, 0],  f: [0, 2, 1, 3, 3, 3] },
            13:    { o: [X, 0, -1, 0, 2, 2],  f: [0, 2, 1, 3, 4, 4] },
            sus4:  { o: [X, 0, 2, 2, 3, 0],   f: [0, 1, 2, 3, 4, 1] },
            sus2:  { o: [X, 0, 2, 2, 0, 0],   f: [0, 1, 3, 4, 1, 1] },
            '7sus4': { o: [X, 0, 2, 0, 3, 0], f: [0, 1, 3, 1, 4, 1] },
            6:     { o: [X, 0, 2, 2, 2, 2],   f: [0, 1, 3, 3, 3, 3] },
            m6:    { o: [X, 0, 2, -1, 1, X],  f: [0, 2, 4, 1, 3, 0] },
            m7b5:  { o: [X, 0, 1, 0, 1, X],   f: [0, 1, 3, 2, 4, 0] },
            dim7:  { o: [X, 0, 1, -1, 1, X],  f: [0, 2, 3, 1, 4, 0] },
            dim:   { o: [X, 0, 1, 2, 1, X],   f: [0, 1, 2, 4, 3, 0] },
            aug:   { o: [X, 0, -1, -2, -2, X], f: [0, 4, 3, 1, 2, 0] },
            5:     { o: [X, 0, 2, 2, X, X],   f: [0, 1, 3, 4, 0, 0] }
        }
    },
    D: {
        rootString: 2,
        shapes: {
            maj:   { o: [X, X, 0, 2, 3, 2],   f: [0, 0, 1, 2, 4, 3] },
            m:     { o: [X, X, 0, 2, 3, 1],   f: [0, 0, 1, 3, 4, 2] },
            7:     { o: [X, X, 0, 2, 1, 2],   f: [0, 0, 1, 3, 2, 4] },
            maj7:  { o: [X, X, 0, 2, 2, 2],   f: [0, 0, 1, 3, 3, 3] },
            m7:    { o: [X, X, 0, 2, 1, 1],   f: [0, 0, 1, 3, 2, 2] },
            sus4:  { o: [X, X, 0, 2, 3, 3],   f: [0, 0, 1, 2, 3, 4] },
            sus2:  { o: [X, X, 0, 2, 3, 0],   f: [0, 0, 1, 2, 4, 1] },
            '7sus4': { o: [X, X, 0, 2, 1, 3], f: [0, 0, 1, 3, 2, 4] },
            6:     { o: [X, X, 0, 2, 0, 2],   f: [0, 0, 1, 3, 1, 4] },
            m6:    { o: [X, X, 0, 2, 0, 1],   f: [0, 0, 1, 3, 1, 2] },
            m7b5:  { o: [X, X, 0, 1, 1, 1],   f: [0, 0, 1, 2, 3, 4] },
            dim7:  { o: [X, X, 0, 1, 0, 1],   f: [0, 0, 1, 3, 2, 4] },
            dim:   { o: [X, X, 0, 1, 3, 1],   f: [0, 0, 1, 2, 4, 3] },
            aug:   { o: [X, X, 0, 3, 3, 2],   f: [0, 0, 1, 3, 4, 2] }
        }
    }
};

// When a shape family has no template for a quality, try the next simpler one
const CHORD_QUALITY_FALLBACK = {
    maj9: 'maj7', m9: 'm7', 13: '7', 9: '7', '7sus4': '7', m6: 'm', 6: 'maj', sus2: 'maj',
    sus4: 'maj', dim: 'm7b5', dim7: 'm7b5', m7b5: 'm', aug: 'maj', 5: 'maj', maj7: 'maj', m7: 'm', 7: 'maj'
};

// Only extensions can be dropped when a shape family lacks the exact quality
const CHORD_EXTENSION_FALLBACK = { maj9: 'maj7', m9: 'm7', 9: '7', 13: '7' };

const OPEN_STRING_SEMITONES = [4, 9, 2, 7, 11, 4]; // E A D G B e

function chordQualityFromSuffix(suffix) {
    const s = (suffix || '').trim().replace(/^(Maj|MAJ)/, 'maj').replace(/^(Min|MIN)/, 'min');
    if (/^(maj|M|Δ)(9|11|13)/.test(s)) return 'maj9';
    if (/^(maj|M|Δ)7?/.test(s) && /7|maj7|M7|Δ/.test(s)) return 'maj7';
    if (/^(m|min|-)7?b5|^ø/.test(s)) return 'm7b5';
    if (/^(dim|°|o)7/.test(s)) return 'dim7';
    if (/^(dim|°|o)/.test(s)) return 'dim';
    if (/^(aug|\+)/.test(s)) return 'aug';
    if (/^(m|min|-)(?!aj)(9|11|13)/.test(s)) return 'm9';
    if (/^(m|min|-)(?!aj)6/.test(s)) return 'm6';
    if (/^(m|min|-)(?!aj)7/.test(s)) return 'm7';
    if (/^(m|min|-)(?!aj)/.test(s)) return 'm';
    if (/^7sus/.test(s)) return '7sus4';
    if (/^sus2/.test(s)) return 'sus2';
    if (/^sus/.test(s)) return 'sus4';
    if (/^13/.test(s)) return '13';
    if (/^(9|11)/.test(s)) return '9';
    if (/^7/.test(s)) return '7';
    if (/^6/.test(s)) return '6';
    if (/^5/.test(s)) return '5';
    return 'maj';
}

// All playable movable voicings for a chord: [{ frets, fingers, barres, center }]
function getTemplateVoicings(chordName) {
    const norm = normalizeChordName(chordName).split('/')[0];
    const match = norm.match(/^([A-G][#b]?)(.*)$/);
    if (!match || NOTE_PITCH_MAP[match[1]] === undefined) return [];
    const rootSemi = NOTE_PITCH_MAP[match[1]];
    const quality = chordQualityFromSuffix(match[2]);

    // A shape of another quality (a sus2 drawn as a major chord) would be a different chord, so only
    // extensions may be dropped (maj9 → maj7, 13 → 7...). Looser fallbacks are a last resort.
    const collect = (loose) => {
    const out = [];
    Object.entries(CHORD_SHAPE_TEMPLATES).forEach(([familyName, family]) => {
        let q = quality;
        while (q && !family.shapes[q]) q = (loose ? CHORD_QUALITY_FALLBACK : CHORD_EXTENSION_FALLBACK)[q];
        if (!q && !loose) return;
        const tpl = family.shapes[q || 'maj'];
        const simplified = (q || 'maj') !== quality; // e.g. a maj9 drawn as maj7 in a family without maj9
        const baseRoot = (rootSemi - OPEN_STRING_SEMITONES[family.rootString] + 12) % 12;
        [baseRoot, baseRoot + 12].forEach(rootFret => {
            const frets = tpl.o.map(o => (o === null ? -1 : rootFret + o));
            const played = frets.filter(f => f >= 0);
            // Movable shapes only: skip any octave that would need an open string or run off the neck
            if (played.some(f => f < 1) || Math.max(...played) > 15) return;
            const zeroStrings = tpl.o.map((o, i) => (o === 0 ? i : -1)).filter(i => i >= 0);
            const barres = zeroStrings.length >= 3
                ? [{ fret: rootFret, start: zeroStrings[0], end: zeroStrings[zeroStrings.length - 1] }]
                : [];
            out.push({
                key: frets.join(','),
                family: familyName,
                frets,
                fingers: tpl.f,
                barres,
                center: played.reduce((a, b) => a + b, 0) / played.length,
                penalty: simplified ? 3 : 0
            });
        });
    });
    return out;
    };
    const exact = collect(false);
    return exact.length ? exact : collect(true);
}

// Voicings built from the chord's own notes: every playable grip (≤5 fret stretch, ≤4 fingers counting a barre,
// at most one muted string inside the grip) that contains the notes the chord is made of and has the right
// note in the bass (the root, or the note after the slash). The best few per neck position are kept, ordered
// from the nut up. Open strings are allowed in low positions (automatic defaults still avoid them).
// Falls back to the shape templates for exotic chords.
const voicingCache = new Map();
function getChordVoicings(chordName) {
    const key = normalizeChordName(chordName);
    if (!voicingCache.has(key)) {
        const found = searchVoicings(key);
        voicingCache.set(key, found.length ? found : getTemplateVoicings(key));
    }
    const generated = voicingCache.get(key);
    const mine = (getCustomVoicings()[chordPrefKey(chordName)] || [])
        .filter(k => !generated.some(v => v.key === k))
        .map(k => buildVoicingFromFrets(k.split(',').map(Number), 'custom'));
    return [...generated, ...mine].sort((a, b) => a.position - b.position || b.score - a.score);
}

// Fingers a grip needs: one for a barre on the lowest fret (when nothing open sits under it), one per other note
function fingersNeeded(frets) {
    const fretted = frets.map((f, s) => ({ f, s })).filter(n => n.f > 0);
    if (!fretted.length) return 0;
    const minFret = Math.min(...fretted.map(n => n.f));
    const atMin = fretted.filter(n => n.f === minFret);
    let barre = false;
    if (atMin.length >= 2) {
        const lo = atMin[0].s, hi = atMin[atMin.length - 1].s;
        barre = frets.slice(lo, hi + 1).every(f => f !== 0); // an open string can't ring under a barre
    }
    return (barre ? 1 : atMin.length) + fretted.length - atMin.length;
}

function searchVoicings(chordName) {
    const info = getChordTones(chordName);
    if (!info) return [];
    const [base, bass] = chordName.split('/');
    const m = base.match(/^([A-G][#b]?)(.*)$/);
    const quality = chordQualityFromSuffix(m[2]);
    const bassPc = bass && NOTE_PITCH_MAP[bass] !== undefined ? NOTE_PITCH_MAP[bass] : info.rootPc;
    const tonePcs = new Set(info.tones.map(t => t.pc));
    // notes a grip must contain: everything but the plain fifth (and the 9th of a 13th chord)
    const essential = info.tones
        .filter(t => !(t.interval === 7 && info.tones.length > 2) && !(quality === '13' && t.interval === 2))
        .map(t => t.pc);
    const fifthPc = (info.rootPc + 7) % 12;
    const minStrings = info.tones.length <= 2 ? 3 : 4;
    const byPosition = new Map(); // lowest fretted fret -> [{score, frets}]
    const pcOf = (s, f) => (OPEN_STRING_SEMITONES[s] + f) % 12;

    for (let w = 1; w <= 12; w++) {
        const options = [];
        for (let s = 0; s < 6; s++) {
            const opts = [-1];
            if (w <= 5 && tonePcs.has(pcOf(s, 0))) opts.push(0); // open strings only near the nut
            for (let f = w; f <= Math.min(w + 4, 15); f++) if (tonePcs.has(pcOf(s, f))) opts.push(f); // up to a 5-fret stretch
            options.push(opts);
        }
        const cur = [];
        const rec = (s) => {
            if (s < 6) {
                for (const f of options[s]) { cur[s] = f; rec(s + 1); }
                return;
            }
            const played = cur.map((f, i) => (f >= 0 ? i : -1)).filter(i => i >= 0);
            if (played.length < minStrings) return;
            const fretted = cur.filter(f => f > 0);
            if (!fretted.length || Math.min(...fretted) !== w) return; // each grip belongs to one position
            if (cur.includes(0) && Math.max(...fretted) > 4) return; // open strings only in first-position grips
            const innerMutes = played[played.length - 1] - played[0] + 1 - played.length;
            if (innerMutes > 1) return;
            if (pcOf(played[0], cur[played[0]]) !== bassPc) return;
            const pcs = played.map(i => pcOf(i, cur[i]));
            if (!essential.every(pc => pcs.includes(pc))) return;
            if (fingersNeeded(cur) > 4) return;
            const span = Math.max(...fretted) - w;
            const rootCount = pcs.filter(pc => pc === info.rootPc).length;
            const score = played.length * 1.6 + (pcs.includes(fifthPc) ? 1 : 0) + (rootCount >= 2 ? 0.5 : 0)
                - span * 0.7 - (span >= 4 ? 1 : 0) - innerMutes * 1.2;
            const group = cur.includes(0) ? 0 : w; // open-string grips form their own "first position" group
            const list = byPosition.get(group) || [];
            list.push({ score, frets: cur.slice() });
            byPosition.set(group, list);
        };
        rec(0);
    }

    const out = [];
    [...byPosition.entries()].sort((a, b) => a[0] - b[0]).forEach(([group, list]) => {
        list.sort((a, b) => b.score - a.score).slice(0, group === 0 ? 4 : 3)
            .forEach(c => out.push(buildVoicingFromFrets(c.frets, 'pos', c.score)));
    });
    return out;
}

// Full voicing object (fingers, barre, centre) from six frets (-1 muted, 0 open)
function buildVoicingFromFrets(frets, family, score = 0) {
    const fretted = frets.map((f, s) => ({ f, s })).filter(n => n.f > 0);
    const played = frets.filter(f => f >= 0);
    const minFret = fretted.length ? Math.min(...fretted.map(n => n.f)) : 0;
    const atMin = fretted.filter(n => n.f === minFret);
    const lo = atMin.length ? atMin[0].s : 0, hi = atMin.length ? atMin[atMin.length - 1].s : 0;
    const barre = atMin.length >= 2 && frets.slice(lo, hi + 1).every(f => f !== 0);
    // finger numbers: index on the lowest fret (as a barre when possible), then 2-3-4 going up the neck
    const fingers = frets.map(() => 0);
    let next = 1;
    if (barre) { atMin.forEach(n => { fingers[n.s] = 1; }); next = 2; }
    fretted.filter(n => !(barre && n.f === minFret))
        .sort((a, b) => a.f - b.f || a.s - b.s)
        .forEach(n => { fingers[n.s] = Math.min(4, next++); });
    const span = fretted.length ? Math.max(...fretted.map(n => n.f)) - minFret : 0;
    return {
        key: frets.join(','),
        family,
        frets,
        fingers,
        barres: barre && atMin.length >= 3 ? [{ fret: minFret, start: lo, end: hi }] : [],
        position: frets.includes(0) ? 0 : minFret,
        score,
        center: played.length ? played.reduce((a, b) => a + b, 0) / played.length : 0,
        // when picking a default automatically: prefer compact, full, closed grips (the user's own are never penalised)
        penalty: family === 'custom' ? 0
            : 0.7 * span + (played.length < 5 ? 1 : 0) + (frets.includes(0) ? 3 : 0) + (fingersNeeded(frets) >= 4 ? 0.3 : 0)
    };
}

// Default voicing per chord, chosen by the user in the chord practice panel (shared by every diagram)
const VOICING_PREF_KEY = 'vibemus_chord_voicing_pref';
// Preferences are keyed by the chord with sharp spelling, so A#maj7 and Bbmaj7 share the same choice
function canonChordKey(name) {
    const n = normalizeChordName(name);
    const m = n.match(/^([A-G][#b]?)([^/]*)(?:\/([A-G][#b]?))?$/);
    if (!m || NOTE_PITCH_MAP[m[1]] === undefined) return n;
    const bass = m[3] && NOTE_PITCH_MAP[m[3]] !== undefined ? '/' + CHROMATIC_SHARPS[NOTE_PITCH_MAP[m[3]]] : '';
    return CHROMATIC_SHARPS[NOTE_PITCH_MAP[m[1]]] + m[2] + bass;
}
function chordPrefKey(chordName) {
    return canonChordKey(chordName);
}
// Entries saved under an older spelling are folded into the canonical key when read
function canonKeys(obj, merge) {
    const out = {};
    Object.entries(obj || {}).forEach(([k, v]) => {
        const ck = canonChordKey(k);
        out[ck] = merge && out[ck] ? [...new Set([...out[ck], ...v])] : v;
    });
    return out;
}
function getVoicingPrefs() {
    try { return canonKeys(JSON.parse(localStorage.getItem(VOICING_PREF_KEY) || '{}')); } catch (e) { return {}; }
}

// Grips the user draws themselves, per chord
const CUSTOM_VOICING_KEY = 'vibemus_chord_custom_voicings';
function getCustomVoicings() {
    try { return canonKeys(JSON.parse(localStorage.getItem(CUSTOM_VOICING_KEY) || '{}'), true); } catch (e) { return {}; }
}
function saveCustomVoicing(chordName, frets) {
    const all = getCustomVoicings();
    const k = chordPrefKey(chordName);
    const key = frets.join(',');
    all[k] = [...new Set([...(all[k] || []), key])];
    try { localStorage.setItem(CUSTOM_VOICING_KEY, JSON.stringify(all)); } catch (e) { console.warn('No se pudo guardar la posición'); }
    return key;
}
function deleteCustomVoicing(chordName, key) {
    const all = getCustomVoicings();
    const k = chordPrefKey(chordName);
    all[k] = (all[k] || []).filter(x => x !== key);
    if (!all[k].length) delete all[k];
    try { localStorage.setItem(CUSTOM_VOICING_KEY, JSON.stringify(all)); } catch (e) {}
}
function setVoicingPref(chordName, voicingKey) {
    const prefs = getVoicingPrefs();
    if (voicingKey) prefs[chordPrefKey(chordName)] = voicingKey; else delete prefs[chordPrefKey(chordName)];
    try { localStorage.setItem(VOICING_PREF_KEY, JSON.stringify(prefs)); } catch (e) { console.warn('No se pudo guardar la preferencia'); }
}

const VOICING_HOME_FRET = 5; // comfortable mid-neck zone the voicings gravitate to

// Spelling by key: each pitch gets the letter its scale degree calls for (G major: Bb for the b3, F# for the 7th),
// so a chord is written the same way everywhere instead of mixing A#maj7 and Bbmaj7
const SPELL_LETTERS = ['C', 'D', 'E', 'F', 'G', 'A', 'B'];
const SPELL_LETTER_PC = { C: 0, D: 2, E: 4, F: 5, G: 7, A: 9, B: 11 };
const SPELL_STEPS = [0, 1, 1, 2, 2, 3, 3, 4, 5, 5, 6, 6]; // letters above the tonic for each semitone offset
function spellPitchForKey(pc, keyRoot, mode) {
    const keyPc = NOTE_PITCH_MAP[keyRoot];
    if (keyPc === undefined) return CHROMATIC_SHARPS[pc];
    const offset = (pc - keyPc + 12) % 12;
    let steps = SPELL_STEPS[offset];
    if (offset === 6 && String(mode).toLowerCase() === 'minor') steps = 4; // b5 rather than #4 in a minor key
    const letter = SPELL_LETTERS[(SPELL_LETTERS.indexOf(keyRoot[0]) + steps) % 7];
    const diff = ((pc - SPELL_LETTER_PC[letter] + 18) % 12) - 6;
    const name = diff === 0 ? letter : diff === 1 ? letter + '#' : diff === -1 ? letter + 'b' : null;
    if (!name) return isFlatKey(`${keyRoot} ${mode}`) ? CHROMATIC_FLATS[pc] : CHROMATIC_SHARPS[pc]; // double accidentals
    return { 'E#': 'F', 'B#': 'C', 'Cb': 'B', 'Fb': 'E' }[name] || name;
}

// Re-spell the root (and slash bass) of a chord name for the song's key
function spellChordForKey(chordName, tonality) {
    if (!tonality) return chordName;
    const key = parseTonalityString(tonality);
    const m = normalizeChordName(chordName).match(/^([A-G][#b]?)([^/]*)(?:\/([A-G][#b]?))?$/);
    if (!m || NOTE_PITCH_MAP[m[1]] === undefined) return chordName;
    const sp = n => spellPitchForKey(NOTE_PITCH_MAP[n], key.root, key.mode);
    return sp(m[1]) + m[2] + (m[3] && NOTE_PITCH_MAP[m[3]] !== undefined ? '/' + sp(m[3]) : '');
}

// Intervals (semitones above the root) each chord quality contains
const CHORD_QUALITY_TONES = {
    maj: [0, 4, 7], m: [0, 3, 7], 7: [0, 4, 7, 10], maj7: [0, 4, 7, 11], m7: [0, 3, 7, 10],
    maj9: [0, 4, 7, 11, 2], m9: [0, 3, 7, 10, 2], 9: [0, 4, 7, 10, 2], 13: [0, 4, 7, 10, 2, 9],
    sus4: [0, 5, 7], sus2: [0, 2, 7], '7sus4': [0, 5, 7, 10], 6: [0, 4, 7, 9], m6: [0, 3, 7, 9],
    m7b5: [0, 3, 6, 10], dim: [0, 3, 6], dim7: [0, 3, 6, 9], aug: [0, 4, 8], 5: [0, 7]
};

// Pitch classes of a chord: [{ pc, interval }] (root first); `add9`/`add11`/`add6` are added on top
function getChordTones(chordName) {
    const [base, bass] = normalizeChordName(chordName).split('/');
    const m = base.match(/^([A-G][#b]?)(.*)$/);
    if (!m || NOTE_PITCH_MAP[m[1]] === undefined) return null;
    const rootPc = NOTE_PITCH_MAP[m[1]];
    const intervals = new Set(CHORD_QUALITY_TONES[chordQualityFromSuffix(m[2])] || CHORD_QUALITY_TONES.maj);
    (m[2].match(/add(\d+)/g) || []).forEach(a => {
        const n = parseInt(a.slice(3), 10);
        intervals.add({ 2: 2, 9: 2, 4: 5, 11: 5, 6: 9, 13: 9 }[n] ?? 2);
    });
    const tones = [...intervals].map(interval => ({ pc: (rootPc + interval) % 12, interval }));
    if (bass && NOTE_PITCH_MAP[bass] !== undefined && !tones.some(t => t.pc === NOTE_PITCH_MAP[bass])) {
        tones.push({ pc: NOTE_PITCH_MAP[bass], interval: (NOTE_PITCH_MAP[bass] - rootPc + 12) % 12 });
    }
    return { rootPc, tones };
}

const GUITAR_OPEN_MIDI = [40, 45, 50, 55, 59, 64]; // E A D G B e (low → high)
const CHORD_DEGREE_NAMES = ['1', 'b2', '2', 'b3', '3', '4', 'b5', '5', 'b6', '6', 'b7', '7'];
// Interval name as chord symbols use it: 9/11/13 when there is a 7th or a third, 2/4 in sus chords, 6 without a 7th
function chordDegreeLabel(interval, tones) {
    const has = i => tones.some(t => t.interval === i);
    const third = has(3) || has(4), seventh = has(10) || has(11);
    if (interval === 2) return third ? '9' : '2';
    if (interval === 5) return third ? '11' : '4';
    if (interval === 9) return seventh ? '13' : '6';
    if (interval === 1) return 'b9';
    return CHORD_DEGREE_NAMES[interval];
}

// Names the chord a set of frets spells (root, quality and slash bass), or null when it isn't a known chord
const IDENT_QUALITIES = [
    ['', CHORD_QUALITY_TONES.maj], ['m', CHORD_QUALITY_TONES.m], ['7', CHORD_QUALITY_TONES[7]],
    ['maj7', CHORD_QUALITY_TONES.maj7], ['m7', CHORD_QUALITY_TONES.m7], ['maj9', CHORD_QUALITY_TONES.maj9],
    ['m9', CHORD_QUALITY_TONES.m9], ['9', CHORD_QUALITY_TONES[9]], ['13', CHORD_QUALITY_TONES[13]],
    ['sus4', CHORD_QUALITY_TONES.sus4], ['sus2', CHORD_QUALITY_TONES.sus2], ['7sus4', CHORD_QUALITY_TONES['7sus4']],
    ['6', CHORD_QUALITY_TONES[6]], ['m6', CHORD_QUALITY_TONES.m6], ['m7b5', CHORD_QUALITY_TONES.m7b5],
    ['dim', CHORD_QUALITY_TONES.dim], ['dim7', CHORD_QUALITY_TONES.dim7], ['aug', CHORD_QUALITY_TONES.aug],
    ['5', CHORD_QUALITY_TONES[5]], ['add9', [0, 4, 7, 2]], ['madd9', [0, 3, 7, 2]],
    ['add11', [0, 4, 7, 5]], ['madd11', [0, 3, 7, 5]]
];
function identifyChord(frets, spell) {
    const pcs = [];
    let bassPc = null;
    frets.forEach((f, s) => {
        if (f < 0) return;
        const pc = (OPEN_STRING_SEMITONES[s] + f) % 12;
        if (bassPc === null) bassPc = pc;
        if (!pcs.includes(pc)) pcs.push(pc);
    });
    if (pcs.length < 2) return null;
    let best = null;
    pcs.forEach(root => IDENT_QUALITIES.forEach(([suffix, tones]) => {
        const rel = pcs.map(pc => (pc - root + 12) % 12);
        if (!rel.every(i => tones.includes(i))) return;
        const needed = tones.filter(i => !(i === 7 && tones.length > 2) && !(suffix === '13' && i === 2));
        if (!needed.every(i => rel.includes(i))) return;
        const score = (rel.length === tones.length ? 2 : 0) + (root === bassPc ? 4 : 0) - tones.length * 0.2;
        if (!best || score > best.score) {
            best = { score, name: spell(root) + suffix + (root !== bassPc ? '/' + spell(bassPc) : '') };
        }
    }));
    return best ? { name: best.name, notes: pcs.map(pc => spell(pc)) } : null;
}

// Fretboard with every position of the chord's notes; the chosen voicing is outlined, the rest dimmed.
// With `edit` (six frets) the neck becomes clickable and shows the grip being drawn.
function chordFretboardSVG(chordName, voicing, labelMode, spell, edit) {
    const info = getChordTones(chordName);
    if (!info) return '';
    const nutX = 50, endX = 1010, frets = 15, fw = (endX - nutX) / frets;
    const yOf = s => 30 + (5 - s) * 24;
    const xOf = f => (f === 0 ? nutX - 20 : nutX + (f - 0.5) * fw);
    let svg = `<svg viewBox="0 0 1045 190" style="width: 100%; height: auto; display: block; user-select: none;">
        <rect x="${nutX}" y="18" width="${endX - nutX}" height="144" rx="4" fill="#141519" stroke="#27272a" stroke-width="1.5"/>`;
    [3, 5, 7, 9, 15].forEach(f => { svg += `<circle cx="${nutX + (f - 0.5) * fw}" cy="90" r="7" fill="rgba(255,255,255,0.12)"/>`; });
    svg += `<circle cx="${nutX + 11.5 * fw}" cy="66" r="6" fill="rgba(255,255,255,0.15)"/><circle cx="${nutX + 11.5 * fw}" cy="114" r="6" fill="rgba(255,255,255,0.15)"/>`;
    for (let f = 1; f <= frets; f++) svg += `<line x1="${nutX + f * fw}" y1="18" x2="${nutX + f * fw}" y2="162" stroke="#475569" stroke-width="2.2"/>`;
    svg += `<rect x="${nutX - 5}" y="16" width="6" height="148" rx="2" fill="#e2e8f0"/>`;
    const grip = edit || (voicing ? voicing.frets : null);
    // strings that sound in the grip are drawn brighter; muted ones fade (like a chord chart)
    for (let s = 0; s < 6; s++) {
        const muted = grip && grip[s] < 0;
        svg += `<line x1="20" y1="${yOf(s)}" x2="${endX}" y2="${yOf(s)}" stroke="#94a3b8" stroke-width="${1 + (5 - s) * 0.45}" ${muted ? 'stroke-dasharray="4 4" opacity="0.45"' : ''}/>`;
    }
    [0, 1, 3, 5, 7, 9, 12, 15].forEach(f => { svg += `<text x="${f === 0 ? nutX - 20 : nutX + (f - 0.5) * fw}" y="182" fill="#94a3b8" font-family="'Geist Mono', monospace" font-size="12" text-anchor="middle">${f}</text>`; });

    for (let s = 0; s < 6; s++) {
        if (grip && grip[s] < 0) {
            svg += `<text x="${nutX - 34}" y="${yOf(s) + 4}" fill="#ef4444" font-size="13" font-weight="700" text-anchor="middle">×</text>`;
        }
        for (let f = 0; f <= frets; f++) {
            const pc = (OPEN_STRING_SEMITONES[s] + f) % 12;
            const tone = info.tones.find(t => t.pc === pc);
            if (!tone) continue;
            const isRoot = tone.interval === 0;
            const label = labelMode === 'notes' ? spell(pc) : chordDegreeLabel(tone.interval, info.tones);
            const chosen = !edit && grip && grip[s] === f;
            const opacity = edit ? 0.3 : (!grip || chosen ? 1 : 0.22);
            svg += `<g class="chord-practice-dot" data-midi="${GUITAR_OPEN_MIDI[s] + f}" opacity="${opacity}" style="cursor: pointer;">
                ${chosen ? `<circle cx="${xOf(f)}" cy="${yOf(s)}" r="16.5" fill="none" stroke="#ffffff" stroke-width="2.5"/>` : ''}
                <circle cx="${xOf(f)}" cy="${yOf(s)}" r="12" fill="${isRoot ? '#ef4444' : '#059669'}" stroke="${isRoot ? '#b91c1c' : '#047857'}" stroke-width="2"/>
                <text x="${xOf(f)}" y="${yOf(s) + 4}" fill="#fff" font-family="'Geist Mono', monospace" font-size="${label.length > 2 ? 9.5 : 11.5}" font-weight="700" text-anchor="middle" pointer-events="none">${label}</text>
            </g>`;
        }
    }
    if (edit) {
        // the user's grip, any note allowed; every fret position is a click target
        edit.forEach((f, s) => {
            if (f < 0) return;
            const pc = (OPEN_STRING_SEMITONES[s] + f) % 12;
            svg += `<circle cx="${xOf(f)}" cy="${yOf(s)}" r="14" fill="#2563eb" stroke="#ffffff" stroke-width="2.5" pointer-events="none"/>
                <text x="${xOf(f)}" y="${yOf(s) + 4}" fill="#fff" font-family="'Geist Mono', monospace" font-size="11" font-weight="700" text-anchor="middle" pointer-events="none">${spell(pc)}</text>`;
        });
        for (let s = 0; s < 6; s++) for (let f = 0; f <= frets; f++) {
            svg += `<circle class="chord-edit-hit" data-s="${s}" data-f="${f}" cx="${xOf(f)}" cy="${yOf(s)}" r="11" fill="transparent" style="cursor: pointer;"/>`;
        }
    }
    if (grip) {
        // chord-chart style column on the right: what each string plays in this grip
        grip.forEach((f, s) => {
            const pc = (OPEN_STRING_SEMITONES[s] + f) % 12;
            const txt = f < 0 ? '×' : chordDegreeLabel((pc - info.rootPc + 12) % 12, info.tones);
            const color = f < 0 ? '#ef4444' : (pc === info.rootPc ? '#f87171' : '#f59e0b');
            svg += `<text x="1028" y="${yOf(s) + 4}" fill="${color}" font-family="'Geist Mono', monospace" font-size="11" font-weight="700" text-anchor="middle">${txt}</text>`;
        });
    }
    return svg + '</svg>';
}

// Redraw every visible copy of the chord sheet (panel, expanded modal, floating window) and the practice panel
function redrawChordViews() {
    refreshChordDiagrams();
    const panel = document.getElementById('chord-practice-panel');
    if (panel && state.selectedSong) renderChordPracticePanel(panel, state.selectedSong);
}

// Where does each chord of the lyrics view live in the chord text? Sections are paired by name (in order); inside a
// pair the chords are matched by order, or by sequence alignment when the counts differ (the text often has chords the
// lyrics lack). Without any section in common the whole song is aligned. Slots with no counterpart are unmapped.
function mapLyricsToText(lyrics, text) {
    const tokens = [];
    const tsecs = [];
    let cur = null;
    text.replace(/(<[^>]+>)|(\S+)/g, (m, tag, tok, offset) => {
        if (tag) { cur = { name: tag.slice(1, -1), toks: [] }; tsecs.push(cur); }
        else if (/^[A-G][#b]?[a-zA-Z0-9#b\-+\/()]*$/.test(tok)) {
            if (!cur) { cur = { name: '', toks: [] }; tsecs.push(cur); }
            const t = { text: tok, start: offset, end: offset + tok.length };
            tokens.push(t);
            cur.toks.push(tokens.length - 1);
        }
        return m;
    });
    const slotChords = [];
    const lsecs = lyrics.map(sec => {
        const first = slotChords.length;
        sec.lines.forEach(l => l.chords.forEach(c => slotChords.push(c.chord)));
        return { name: sec.section || '', first, count: slotChords.length - first };
    });
    const map = new Map();
    const pair = (slotIdxs, tokIdxs) => {
        if (slotIdxs.length === tokIdxs.length) { slotIdxs.forEach((si, k) => map.set(si, tokIdxs[k])); return; }
        const al = alignChordSequences(slotIdxs.map(i => slotChords[i]), tokIdxs.map(i => tokens[i].text));
        if (al) al.ops.forEach(o => { if (o.i !== undefined && o.j !== undefined) map.set(slotIdxs[o.i], tokIdxs[o.j]); });
    };
    const norm = n => String(n).toLowerCase().replace(/[_\s]+/g, '');
    const base = n => norm(n).replace(/\d+$/, '');
    let ptr = 0, paired = 0;
    lsecs.forEach(ls => {
        const cands = tsecs.map((t, i) => i).filter(i => i >= ptr && (norm(tsecs[i].name) === norm(ls.name) || base(tsecs[i].name) === base(ls.name)));
        const idx = cands.find(i => tsecs[i].toks.length === ls.count) ?? cands[0];
        if (idx === undefined) return;
        ptr = idx + 1;
        paired++;
        pair(Array.from({ length: ls.count }, (_, k) => ls.first + k), tsecs[idx].toks);
    });
    if (!paired) pair(slotChords.map((_, i) => i), tokens.map((_, i) => i));
    return { tokens, slotChords, tokOf: i => map.get(i) };
}

// Change (newName) or delete (newName === null) one chord of the lyrics view, mirror it in the chord text that
// feeds the diagrams view, then re-analyse and save. ref = { si, li, ci } position inside state.selectedLyrics.
async function editLyricsChord(ref, newName) {
    const song = state.selectedSong;
    const lyrics = state.selectedLyrics;
    if (!song || !Array.isArray(lyrics)) return;
    const slotChords = [];
    let flat = -1;
    lyrics.forEach((sec, si) => sec.lines.forEach((l, li) => l.chords.forEach((c, ci) => {
        slotChords.push(c.chord);
        if (si === ref.si && li === ref.li && ci === ref.ci) flat = slotChords.length - 1;
    })));
    if (flat === -1) return;

    const text = (els.editChord ? els.editChord.value : song.chord) || '';
    const { tokens, tokOf } = mapLyricsToText(lyrics, text);
    const tokIdx = tokOf(flat);
    let newText = text;
    if (tokIdx !== undefined) {
        const t = tokens[tokIdx];
        newText = newName === null
            ? text.slice(0, t.start) + text.slice(t.end).replace(/^[ \t]/, '')
            : text.slice(0, t.start) + newName + text.slice(t.end);
    }

    state.selectedLyrics = lyrics.map((sec, si) => ({
        ...sec,
        lines: sec.lines
            .map((l, li) => (si !== ref.si || li !== ref.li ? l : {
                ...l,
                chords: newName === null ? l.chords.filter((_, ci) => ci !== ref.ci) : l.chords.map((c, ci) => (ci === ref.ci ? { ...c, chord: newName } : c))
            }))
            .filter(l => l.lyric || l.chords.length)
    }));
    if (els.editChord) els.editChord.value = newText;
    song.chord = newText;
    redrawChordViews(); // instant feedback: analysing and saving to the sheet take a few seconds
    await handleFormSubmission({ preventDefault() {} });
}

// Add a chord to the lyrics view at line (si, li), on word `wordIdx`, as chord number `at` of that line, and mirror it
// in the chord text right after the chord that precedes it. Then re-analyse and save.
async function addLyricsChord(si, li, wordIdx, at, name) {
    const song = state.selectedSong;
    const lyrics = state.selectedLyrics;
    if (!song || !Array.isArray(lyrics) || !lyrics[si] || !lyrics[si].lines[li]) return;
    let total = 0;
    let flat = 0; // slot number the new chord will take
    const slotSection = [];
    lyrics.forEach((sec, a) => sec.lines.forEach((l, b) => {
        if (a === si && b === li) flat = total + at;
        total += l.chords.length;
        l.chords.forEach(() => slotSection.push(a));
    }));

    const text = (els.editChord ? els.editChord.value : song.chord) || '';
    const { tokens, tokOf } = mapLyricsToText(lyrics, text);
    let newText;
    let prev = flat - 1;
    while (prev >= 0 && tokOf(prev) === undefined) prev--;
    // first chord of a section: it goes before the chord that follows it, not at the end of the previous section
    const startsSection = prev >= 0 && slotSection[prev] < si;
    if (prev >= 0 && !startsSection) {
        const t = tokens[tokOf(prev)];
        newText = text.slice(0, t.end) + ' ' + name + text.slice(t.end);
    } else {
        let next = flat;
        while (next < total && tokOf(next) === undefined) next++;
        if (next < total) {
            const t = tokens[tokOf(next)];
            newText = text.slice(0, t.start) + name + ' ' + text.slice(t.start);
        } else {
            newText = text.replace(/\s+$/, '') + (text.trim() ? ' ' : '') + name;
        }
    }

    state.selectedLyrics = lyrics.map((sec, a) => (a !== si ? sec : {
        ...sec,
        lines: sec.lines.map((l, b) => {
            if (b !== li) return l;
            const chords = l.chords.slice();
            chords.splice(at, 0, { chord: name, word_idx: wordIdx });
            return { ...l, chords };
        })
    }));
    if (els.editChord) els.editChord.value = newText;
    song.chord = newText;
    redrawChordViews();
    await handleFormSubmission({ preventDefault() {} });
}

// Inline input that asks for a chord name; calls onSubmit(name) with a valid, normalised name
function promptChordInline(anchor, onSubmit, onCancel) {
    const input = document.createElement('input');
    input.className = 'lyrics-chord-input';
    input.placeholder = 'Acorde';
    input.size = 7;
    anchor.appendChild(input);
    input.focus();
    let done = false;
    const finish = async (commit) => {
        if (done) return;
        done = true;
        const value = input.value.trim();
        input.remove();
        if (!commit || !value) { if (onCancel) onCancel(); return; }
        const name = normalizeChordName(value);
        if (!getChordTones(name)) {
            showToast(`"${value}" no es un acorde reconocido`, true);
            if (onCancel) onCancel();
            return;
        }
        await onSubmit(name);
    };
    input.addEventListener('keydown', (ev) => {
        if (ev.key === 'Enter') finish(true);
        else if (ev.key === 'Escape') finish(false);
    });
    input.addEventListener('blur', () => finish(true));
    input.addEventListener('click', ev => ev.stopPropagation());
}

// Swap a chord name for another everywhere in the open song (chord text and lyrics), then re-analyse and save
async function renameChordInSong(oldName, newName) {
    const song = state.selectedSong;
    if (!song) return 0;
    const same = c => canonChordKey(c) === canonChordKey(oldName);
    let count = 0;
    const text = (els.editChord ? els.editChord.value : song.chord) || '';
    const newText = text.replace(/(<[^>]+>)|(\S+)/g, (m, tag, tok) => (tag || !same(tok) ? m : (count++, newName)));
    if (Array.isArray(state.selectedLyrics)) {
        state.selectedLyrics = state.selectedLyrics.map(sec => ({
            ...sec,
            lines: sec.lines.map(l => ({ ...l, chords: l.chords.map(c => (same(c.chord) ? { ...c, chord: newName } : c)) }))
        }));
    }
    if (els.editChord) els.editChord.value = newText;
    song.chord = newText;
    await handleFormSubmission({ preventDefault() {} });
    return count;
}

// Chord practice panel (above the lyrics): pick a chord, see all its positions on the neck, choose or draw the default shape
function renderChordPracticePanel(container, song) {
    if (!container) return;
    const chords = songUniqueChords(song.chord, state.selectedLyrics, song.tonality);
    if (!chords.length) { container.innerHTML = ''; return; }

    const songKey = parseTonalityString(song.tonality || 'C Major');
    const spell = pc => spellPitchForKey(pc, songKey.root, songKey.mode);
    const view = { chord: chords[0], voicingKey: null, labelMode: 'degrees', edit: null };
    const chip = 'padding: 4px 10px; font-size: 12px; border-radius: 8px; border: 1px solid var(--border-hairline-light); cursor: pointer; font-weight: 600; font-family: inherit;';
    const accent = 'var(--theme-accent, #6366f1)';
    const fretsText = f => f.map(x => (x < 0 ? 'x' : x)).join(' ');

    // Previous / next grip along the neck (wraps around); from "Todas" it starts at either end
    const step = (dir) => {
        const list = getChordVoicings(view.chord);
        if (!list.length) return;
        const idx = list.findIndex(v => v.key === view.voicingKey);
        const next = idx === -1 ? (dir > 0 ? 0 : list.length - 1) : (idx + dir + list.length) % list.length;
        view.voicingKey = list[next].key;
        draw();
        container.focus({ preventScroll: true }); // keep ← → working after the buttons are redrawn
        strumVoicing(list[next]);
    };
    container.tabIndex = 0;
    container.style.outline = 'none';
    container.onkeydown = (e) => {
        if (view.edit || (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight')) return;
        e.preventDefault();
        step(e.key === 'ArrowRight' ? 1 : -1);
    };

    const draw = () => {
        const voicings = getChordVoicings(view.chord);
        const prefKey = getVoicingPrefs()[chordPrefKey(view.chord)];
        if (view.voicingKey !== '__all__' && !voicings.some(v => v.key === view.voicingKey)) {
            view.voicingKey = (voicings.find(v => v.key === prefKey) || getChordShape(view.chord) || voicings[0] || {}).key || null;
        }
        const current = voicings.find(v => v.key === view.voicingKey) || null;
        const typeBtns = `
            <div style="display: inline-flex; border: 1px solid var(--border-hairline-light); border-radius: 8px; overflow: hidden;">
                <button type="button" data-label="degrees" style="${chip} border: 0; border-radius: 0; background: ${view.labelMode === 'degrees' ? accent : 'transparent'}; color: ${view.labelMode === 'degrees' ? '#fff' : 'var(--text-secondary)'};">Grados</button>
                <button type="button" data-label="notes" style="${chip} border: 0; border-radius: 0; background: ${view.labelMode === 'notes' ? accent : 'transparent'}; color: ${view.labelMode === 'notes' ? '#fff' : 'var(--text-secondary)'};">Notas</button>
            </div>`;
        const header = `
            <div style="display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; margin-bottom: 10px;">
                <span style="font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-tertiary); font-weight: 700;"><i class="ph ph-guitar"></i> Practicar acordes · todas las posiciones</span>
                ${typeBtns}
            </div>
            <div style="display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 10px;">
                ${chords.map(c => `<button type="button" data-chord="${c}" style="${chip} background: ${c === view.chord ? accent : 'rgba(255,255,255,0.04)'}; color: ${c === view.chord ? '#fff' : 'var(--text-primary)'};">${c}${getVoicingPrefs()[chordPrefKey(c)] ? ' ★' : ''}</button>`).join('')}
            </div>`;

        let body;
        if (view.edit) {
            const found = identifyChord(view.edit, spell);
            const sameChord = found && normalizeChordName(found.name) === normalizeChordName(view.chord);
            const played = view.edit.some(f => f >= 0);
            body = `
                <div style="font-size: 12px; color: var(--text-secondary); margin-bottom: 8px;">
                    <strong style="color: var(--text-primary);">Crea tu posición:</strong> haz clic en el mástil para poner una nota en una cuerda (una por cuerda). Un clic sobre una nota la quita; el 0 es cuerda al aire.
                </div>
                <div style="display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin-bottom: 8px; font-family: 'Geist Mono', monospace; font-size: 12px;">
                    <span style="color: var(--text-tertiary);">Cuerdas (6→1): <span style="color: var(--text-primary);">${fretsText(view.edit)}</span></span>
                    <span style="color: var(--text-tertiary);">Notas: <span style="color: var(--text-primary);">${found ? found.notes.join(' ') : '—'}</span></span>
                    <span style="color: var(--text-tertiary);">Acorde: ${found
                        ? `<strong style="color: ${sameChord ? '#34d399' : '#f59e0b'};">${found.name}</strong>${sameChord ? '' : ` <span style="color: #f59e0b;">(distinto de ${view.chord})</span>`}`
                        : (played ? '<span style="color: #ef4444;">no reconocido</span>' : '—')}</span>
                </div>
                <div style="display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 8px;">
                    <button type="button" data-edit-play style="${chip} background: rgba(255,255,255,0.04); color: var(--text-primary);"><i class="ph-fill ph-play"></i> Tocar</button>
                    <button type="button" data-edit-clear style="${chip} background: rgba(255,255,255,0.04); color: var(--text-secondary);">Vaciar</button>
                    <button type="button" data-edit-save ${played ? '' : 'disabled'} style="${chip} background: rgba(255,255,255,0.04); color: var(--text-primary);">Guardar posición${found && !sameChord ? ` como ${found.name}` : ''}</button>
                    <button type="button" data-edit-default ${played ? '' : 'disabled'} style="${chip} background: rgba(245,158,11,0.18); color: #f59e0b; border-color: rgba(245,158,11,0.5);">★ Guardar y usar por defecto${found && !sameChord ? ` (y renombrar ${view.chord} → ${found.name})` : ''}</button>
                    <button type="button" data-edit-cancel style="${chip} margin-left: auto; background: transparent; color: var(--text-secondary);">Cancelar</button>
                </div>
                ${chordFretboardSVG(found ? found.name : view.chord, null, view.labelMode, spell, view.edit)}`;
        } else {
            body = `
                <div style="display: flex; gap: 6px; flex-wrap: wrap; align-items: center; margin-bottom: 8px;">
                    <button type="button" data-nav="-1" ${voicings.length ? '' : 'disabled'} style="${chip} background: rgba(255,255,255,0.04); color: var(--text-primary);" title="Posición anterior (←)"><i class="ph ph-caret-left"></i> Anterior</button>
                    <div style="min-width: 210px; text-align: center; font-size: 12px; line-height: 1.35;">
                        ${current
                            ? `<div style="color: var(--text-primary); font-weight: 700;">Posición ${voicings.indexOf(current) + 1} de ${voicings.length} · ${current.position ? 'traste ' + current.position : 'primera posición'}${current.family === 'custom' ? ' · mía' : ''}${current.key === prefKey ? ' · ★' : ''}</div>
                               <div style="font-family: 'Geist Mono', monospace; color: var(--text-tertiary); font-size: 11px;">${fretsText(current.frets)}</div>`
                            : `<div style="color: var(--text-primary); font-weight: 700;">Todas las notas</div><div style="color: var(--text-tertiary); font-size: 11px;">${voicings.length} posiciones disponibles</div>`}
                    </div>
                    <button type="button" data-nav="1" ${voicings.length ? '' : 'disabled'} style="${chip} background: rgba(255,255,255,0.04); color: var(--text-primary);" title="Posición siguiente (→)">Siguiente <i class="ph ph-caret-right"></i></button>
                    <button type="button" data-voicing="" style="${chip} background: ${!current ? accent : 'rgba(255,255,255,0.04)'}; color: ${!current ? '#fff' : 'var(--text-secondary)'};">Todas</button>
                    <button type="button" data-edit-start style="${chip} background: transparent; color: var(--text-primary); border-style: dashed;"><i class="ph ph-pencil-simple"></i> Crear la mía</button>
                    ${current ? `
                        <button type="button" data-play style="${chip} margin-left: auto; background: rgba(255,255,255,0.04); color: var(--text-primary);"><i class="ph-fill ph-play"></i> Tocar</button>
                        <button type="button" data-arpeggio style="${chip} background: rgba(255,255,255,0.04); color: var(--text-primary);"><i class="ph ph-wave-sine"></i> Arpegio</button>
                        ${current.family === 'custom' ? `<button type="button" data-edit-existing style="${chip} background: rgba(255,255,255,0.04); color: var(--text-primary);"><i class="ph ph-pencil-simple"></i> Editar</button><button type="button" data-delete style="${chip} background: rgba(255,255,255,0.04); color: #ef4444;"><i class="ph ph-trash"></i></button>` : ''}
                        <button type="button" data-default style="${chip} background: ${current.key === prefKey ? 'rgba(245,158,11,0.18)' : 'rgba(255,255,255,0.04)'}; color: ${current.key === prefKey ? '#f59e0b' : 'var(--text-primary)'}; border-color: ${current.key === prefKey ? 'rgba(245,158,11,0.5)' : 'var(--border-hairline-light)'};">${current.key === prefKey ? '★ Predeterminada (quitar)' : '☆ Usar como predeterminada'}</button>` : ''}
                </div>
                ${voicings.length ? chordFretboardSVG(view.chord, current, view.labelMode, spell) : '<div style="color: var(--text-tertiary); font-size: 12px;">No hay formas disponibles para este acorde.</div>'}
                <div style="font-size: 11.5px; color: var(--text-tertiary); margin-top: 6px;">Haz clic en una nota para escucharla. La forma predeterminada es la que se dibuja en todos los diagramas de ${view.chord}.</div>`;
        }
        container.innerHTML = `<div style="background: rgba(0,0,0,0.25); border: 1px solid rgba(255,255,255,0.06); border-radius: 10px; padding: 14px 16px; margin-bottom: 22px;">${header}${body}</div>`;

        const $ = sel => container.querySelector(sel);
        container.querySelectorAll('[data-chord]').forEach(b => b.addEventListener('click', () => { view.chord = b.dataset.chord; view.voicingKey = null; view.edit = null; draw(); }));
        container.querySelectorAll('[data-label]').forEach(b => b.addEventListener('click', () => { view.labelMode = b.dataset.label; draw(); }));

        if (view.edit) {
            container.querySelectorAll('.chord-edit-hit').forEach(h => h.addEventListener('click', () => {
                const s = parseInt(h.dataset.s, 10), f = parseInt(h.dataset.f, 10);
                if (view.edit[s] === f) view.edit[s] = -1; else { view.edit[s] = f; if (window.GuitarFretboard) window.GuitarFretboard.playNote(GUITAR_OPEN_MIDI[s] + f); }
                draw();
            }));
            $('[data-edit-play]').addEventListener('click', () => strumVoicing({ frets: view.edit }));
            $('[data-edit-clear]').addEventListener('click', () => { view.edit = [-1, -1, -1, -1, -1, -1]; draw(); });
            $('[data-edit-cancel]').addEventListener('click', () => { view.edit = null; draw(); });
            const commit = async (makeDefault) => {
                const found = identifyChord(view.edit, spell);
                const target = found ? found.name : view.chord;
                const renaming = found && normalizeChordName(found.name) !== normalizeChordName(view.chord);
                if (renaming && !confirm(`Las notas que has puesto forman ${found.name}, no ${view.chord}.\n\n¿Cambiar ${view.chord} por ${found.name} en toda la canción (acordes y letra) y guardar?`)) return;
                const key = saveCustomVoicing(target, view.edit);
                if (makeDefault) setVoicingPref(target, key);
                if (renaming) {
                    await renameChordInSong(view.chord, found.name);
                    showToast(`${view.chord} → ${found.name} en toda la canción ✨`);
                    renderChordPracticePanel(container, state.selectedSong);
                    const sheet = document.getElementById('expanded-chord-sheet');
                    if (sheet) renderExpandedChordSheet(sheet, state.selectedSong);
                    return;
                }
                view.edit = null;
                view.voicingKey = key;
                refreshChordDiagrams();
                draw();
                showToast(makeDefault ? `Posición de ${target} guardada como predeterminada ★` : `Posición de ${target} guardada`);
            };
            $('[data-edit-save]').addEventListener('click', () => commit(false));
            $('[data-edit-default]').addEventListener('click', () => commit(true));
            return;
        }

        container.querySelectorAll('[data-voicing]').forEach(b => b.addEventListener('click', () => {
            view.voicingKey = '__all__';
            draw();
        }));
        container.querySelectorAll('[data-nav]').forEach(b => b.addEventListener('click', () => step(parseInt(b.dataset.nav, 10))));
        const arp = $('[data-arpeggio]');
        if (arp && current) arp.addEventListener('click', () => strumVoicing(current, 260));
        $('[data-edit-start]').addEventListener('click', () => { view.edit = current ? current.frets.slice() : [-1, -1, -1, -1, -1, -1]; draw(); });
        const play = $('[data-play]');
        if (play && current) play.addEventListener('click', () => strumVoicing(current));
        const editExisting = $('[data-edit-existing]');
        if (editExisting && current) editExisting.addEventListener('click', () => { view.edit = current.frets.slice(); draw(); });
        const del = $('[data-delete]');
        if (del && current) del.addEventListener('click', () => {
            deleteCustomVoicing(view.chord, current.key);
            if (getVoicingPrefs()[chordPrefKey(view.chord)] === current.key) setVoicingPref(view.chord, null);
            view.voicingKey = null;
            refreshChordDiagrams();
            draw();
        });
        const def = $('[data-default]');
        if (def && current) def.addEventListener('click', () => {
            setVoicingPref(view.chord, current.key === prefKey ? null : current.key);
            refreshChordDiagrams();
            draw();
            showToast(current.key === prefKey ? `Forma de ${view.chord} restablecida` : `Forma predeterminada de ${view.chord} guardada ★`);
        });
        container.querySelectorAll('.chord-practice-dot').forEach(g => g.addEventListener('click', () => {
            if (window.GuitarFretboard) window.GuitarFretboard.playNote(parseInt(g.dataset.midi, 10));
        }));
    };
    draw();
}

function strumVoicing(voicing, gapMs = 45) {
    if (!window.GuitarFretboard) return;
    let n = 0;
    voicing.frets.forEach((f, s) => {
        if (f >= 0) setTimeout(() => window.GuitarFretboard.playNote(GUITAR_OPEN_MIDI[s] + f), n++ * gapMs);
    });
}

// Redraw every visible chord diagram after the default voicing of a chord changes
function refreshChordDiagrams() {
    const song = state.selectedSong;
    if (!song) return;
    ['focus-progression-diagrams', 'expanded-progression-diagrams', 'expanded-improv-progression-diagrams', 'chord-float-diagrams'].forEach(id => {
        const el = document.getElementById(id);
        if (el && el.children.length) renderProgressionDiagrams(el, song.progression, song.tonality);
    });
    renderChordSheet((els.editChord && els.editChord.value.trim()) || song.chord, state.selectedLyrics);
    ['expanded-chord-sheet', 'chord-float-content'].forEach(id => {
        const el = document.getElementById(id);
        if (el && el.children.length) renderExpandedChordSheet(el, song);
    });
}

// Single chord with no context: the voicing nearest the home zone
function getChordShape(chordName) {
    return voiceChordSequence([chordName])[0];
}

// Picks one voicing per chord so the whole sequence moves as little as possible along the neck
// (Viterbi over the candidates), with a light pull towards the home zone so it doesn't drift.
// Returns an array aligned with chordNames (null where no shape exists).
function voiceChordSequence(chordNames) {
    const prefs = getVoicingPrefs();
    const cands = chordNames.map(name => {
        const list = getChordVoicings(name);
        const chosen = prefs[chordPrefKey(name)] && list.find(v => v.key === prefs[chordPrefKey(name)]);
        return chosen ? [chosen] : list; // a voicing picked as default is the only candidate
    });
    const home = v => 0.25 * Math.abs(v.center - VOICING_HOME_FRET) + v.penalty;
    let prev = null; // [{ cost, path }] for the last chord that had candidates
    cands.forEach((list, i) => {
        if (!list.length) return;
        prev = list.map(v => {
            if (!prev) return { cost: home(v), path: [[i, v]] };
            const best = prev.reduce((b, p) => {
                const c = p.cost + Math.abs(v.center - p.path[p.path.length - 1][1].center);
                return c < b.c ? { c, p } : b;
            }, { c: Infinity, p: null });
            return { cost: best.c + home(v), path: [...best.p.path, [i, v]] };
        });
    });
    const result = chordNames.map(() => null);
    if (prev) prev.reduce((a, b) => (b.cost < a.cost ? b : a)).path.forEach(([i, v]) => { result[i] = v; });
    return result;
}

// ============================================================================
// MUSIC THEORY & HARMONIC TRANSPOSITION ENGINE
// ============================================================================

const CHROMATIC_SHARPS = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];
const CHROMATIC_FLATS  = ['C', 'Db', 'D', 'Eb', 'E', 'F', 'Gb', 'G', 'Ab', 'A', 'Bb', 'B'];

const NOTE_PITCH_MAP = {
    'C': 0, 'B#': 0,
    'C#': 1, 'Db': 1,
    'D': 2,
    'D#': 3, 'Eb': 3,
    'E': 4, 'Fb': 4,
    'F': 5, 'E#': 5,
    'F#': 6, 'Gb': 6,
    'G': 7,
    'G#': 8, 'Ab': 8,
    'A': 9,
    'A#': 10, 'Bb': 10,
    'B': 11, 'Cb': 11
};

// Keys that naturally use flats in standard music notation
const FLAT_KEY_PREFERENCES = new Set([
    'F Major', 'Bb Major', 'Eb Major', 'Ab Major', 'Db Major', 'Gb Major', 'Cb Major',
    'D Minor', 'G Minor', 'C Minor', 'F Minor', 'Bb Minor', 'Eb Minor', 'Ab Minor',
    'F', 'Bb', 'Eb', 'Ab', 'Db', 'Gb',
    'Dm', 'Gm', 'Cm', 'Fm', 'Bbm', 'Ebm', 'Abm'
]);

function parseTonalityString(tonalityStr) {
    if (!tonalityStr || typeof tonalityStr !== 'string') {
        return { root: 'C', mode: 'Major', canonical: 'C Major' };
    }
    const clean = tonalityStr.trim();
    // Normalize Spanish note names if present
    const spMap = { 'do': 'C', 're': 'D', 'mi': 'E', 'fa': 'F', 'sol': 'G', 'la': 'A', 'si': 'B' };
    let normStr = clean;
    for (const [sp, en] of Object.entries(spMap)) {
        if (normStr.toLowerCase().startsWith(sp)) {
            normStr = en + normStr.slice(sp.length);
            break;
        }
    }
    
    const match = normStr.match(/^([A-G][#b]?)(.*)$/i);
    if (!match) {
        return { root: 'C', mode: 'Major', canonical: 'C Major' };
    }
    let rawRoot = match[1];
    let root = rawRoot.charAt(0).toUpperCase() + (rawRoot.length > 1 ? rawRoot.charAt(1).toLowerCase() : '');
    if (root.endsWith('S') || root.endsWith('s')) root = root.charAt(0) + '#';

    const remainder = (match[2] || '').toLowerCase().trim();
    const isMinor = remainder.includes('min') || remainder.includes('menor') || remainder === 'm' || remainder.startsWith('m ') || remainder.startsWith('m-');
    const mode = isMinor ? 'Minor' : 'Major';
    return {
        root: root,
        mode: mode,
        canonical: `${root} ${mode}`
    };
}

function isFlatKey(tonality) {
    if (!tonality) return false;
    const parsed = typeof tonality === 'string' ? parseTonalityString(tonality) : tonality;
    if (FLAT_KEY_PREFERENCES.has(parsed.canonical) || FLAT_KEY_PREFERENCES.has(parsed.root)) {
        return true;
    }
    return parsed.root.includes('b');
}

function getSemitoneOffset(fromKey, toKey) {
    if (!fromKey || !toKey) return 0;
    const from = parseTonalityString(fromKey);
    const to = parseTonalityString(toKey);
    const pitchFrom = NOTE_PITCH_MAP[from.root];
    const pitchTo = NOTE_PITCH_MAP[to.root];
    if (pitchFrom === undefined || pitchTo === undefined) return 0;
    let diff = (pitchTo - pitchFrom) % 12;
    if (diff < 0) diff += 12;
    return diff;
}

function transposeSingleNote(note, semitones, preferFlats) {
    if (!note) return note;
    let clean = note.trim();
    let root = clean.charAt(0).toUpperCase() + (clean.length > 1 ? clean.charAt(1).toLowerCase() : '');
    if (root.endsWith('s') || root.endsWith('S')) root = root.charAt(0) + '#';
    const pitch = NOTE_PITCH_MAP[root];
    if (pitch === undefined) return note;
    let newPitch = (pitch + semitones) % 12;
    if (newPitch < 0) newPitch += 12;
    return preferFlats ? CHROMATIC_FLATS[newPitch] : CHROMATIC_SHARPS[newPitch];
}

function transposeChordName(chordName, semitones, targetKey) {
    if (!chordName || semitones === 0) return chordName;
    const preferFlats = isFlatKey(targetKey);

    // Handle slash chords like C/E, D/F#, Am/G
    if (chordName.includes('/')) {
        const parts = chordName.split('/');
        const mainChord = transposeChordName(parts[0], semitones, targetKey);
        const bassNote = transposeSingleNote(parts[1], semitones, preferFlats);
        return `${mainChord}/${bassNote}`;
    }

    // Match root note and chord quality/extensions (e.g., F#m7, Bbadd9, Gsus4, Cmaj7)
    const match = chordName.match(/^([A-G][#b]?)(.*)$/);
    if (!match) return chordName;

    const root = match[1];
    const suffix = match[2];
    const newRoot = transposeSingleNote(root, semitones, preferFlats);
    return `${newRoot}${suffix}`;
}

// Determines the roman numeral, quality and tonic relationship of a chord to the song's key
function getChordAnalysis(chordName, tonalityString) {
    if (!chordName || !tonalityString) return { roman: '', isTonic: false, quality: 'major', degree: 0 };

    const tonalityMatch = tonalityString.match(/^([A-G][#b]?)\s+(Major|Minor)$/i);
    if (!tonalityMatch) return { roman: '', isTonic: false, quality: 'major', degree: 0 };

    const keyRoot = tonalityMatch[1];
    const keyMode = tonalityMatch[2].toLowerCase();

    const chordBase = chordName.split('/')[0];
    const chordMatch = chordBase.match(/^([A-G][#b]?)(.*)$/);
    if (!chordMatch) return { roman: '', isTonic: false, quality: 'major', degree: 0 };

    const chordRoot = chordMatch[1];
    const suffix = chordMatch[2];

    if (NOTE_PITCH_MAP[keyRoot] === undefined || NOTE_PITCH_MAP[chordRoot] === undefined) {
        return { roman: '', isTonic: false, quality: 'major', degree: 0 };
    }

    const diff = (NOTE_PITCH_MAP[chordRoot] - NOTE_PITCH_MAP[keyRoot] + 12) % 12;

    let quality = 'major';
    if (suffix.startsWith('m') && !suffix.startsWith('maj')) {
        quality = 'minor';
    } else if (suffix.startsWith('dim') || suffix.includes('°')) {
        quality = 'diminished';
    } else if (suffix.startsWith('aug') || suffix.includes('+')) {
        quality = 'augmented';
    }

    const isMinorQuality = quality === 'minor' || quality === 'diminished';
    const isTonic = (diff === 0);

    let roman = '';
    let degree = 0;
    if (keyMode === 'major') {
        const majorNumerals = {
            0: 'I', 1: 'bII', 2: 'II', 3: 'bIII', 4: 'III',
            5: 'IV', 6: '#IV', 7: 'V', 8: 'bVI', 9: 'VI', 10: 'bVII', 11: 'VII'
        };
        const majorDegrees = {
            0: 1, 1: 2, 2: 2, 3: 3, 4: 3,
            5: 4, 6: 4, 7: 5, 8: 6, 9: 6, 10: 7, 11: 7
        };
        roman = majorNumerals[diff];
        degree = majorDegrees[diff];
    } else {
        const minorNumeralsScale = {
            0: 'I', 1: 'bII', 2: 'II', 3: 'III', 4: '#III',
            5: 'IV', 6: '#IV', 7: 'V', 8: 'VI', 9: '#VI', 10: 'VII', 11: '#VII'
        };
        const minorDegrees = {
            0: 1, 1: 2, 2: 2, 3: 3, 4: 3,
            5: 4, 6: 4, 7: 5, 8: 6, 9: 6, 10: 7, 11: 7
        };
        roman = minorNumeralsScale[diff];
        degree = minorDegrees[diff];
    }

    if (roman) {
        if (isMinorQuality) {
            roman = roman.toLowerCase();
        }
        if (quality === 'diminished') {
            roman += '°';
        } else if (quality === 'augmented') {
            roman += '+';
        }
    }

    return { roman, isTonic, quality, degree };
}

/**
 * Convert a Roman numeral progression string (e.g. "i7 - VIImaj7 - III")
 * into actual chord names (e.g. "Am7 - Gmaj7 - C") given a tonality string.
 */
function romanProgressionToChords(progressionStr, tonalityStr) {
    if (!progressionStr || !tonalityStr) return '';

    const tonalityMatch = tonalityStr.match(/^([A-G][#b]?)\s+(Major|Minor)$/i);
    if (!tonalityMatch) return '';

    const keyRoot = tonalityMatch[1];
    const keyMode = tonalityMatch[2].toLowerCase();
    const keyPitch = NOTE_PITCH_MAP[keyRoot];
    if (keyPitch === undefined) return '';

    const preferFlats = isFlatKey(tonalityStr);
    const chromatic = preferFlats ? CHROMATIC_FLATS : CHROMATIC_SHARPS;

    // Semitone intervals for each Roman degree in major vs minor
    const majorIntervals = { 'I': 0, 'II': 2, 'III': 4, 'IV': 5, 'V': 7, 'VI': 9, 'VII': 11 };
    const minorIntervals = { 'I': 0, 'II': 2, 'III': 3, 'IV': 5, 'V': 7, 'VI': 8, 'VII': 10 };
    const intervals = keyMode === 'minor' ? minorIntervals : majorIntervals;

    // Split by " - " separator (standard progression format)
    const parts = progressionStr.split(/\s*-\s*/);

    const chordNames = parts.map(part => {
        const trimmed = part.trim();
        if (!trimmed) return '';

        // Parse Roman numeral: optional accidental prefix (b/#), Roman numeral, optional suffix
        const romanMatch = trimmed.match(/^([b#]?)(i{1,3}v?|v?i{0,3}|IV|V|I{1,3})(.*?)$/i);
        if (!romanMatch) return trimmed;

        const accidental = romanMatch[1]; // b or #
        const romanPart = romanMatch[2];
        const suffix = romanMatch[3];     // e.g. "7", "maj7", "sus4", "dim", etc.

        // Normalize Roman numeral to uppercase for lookup
        const upperRoman = romanPart.toUpperCase();
        // Determine quality from case: lowercase = minor
        const isLowerCase = romanPart === romanPart.toLowerCase() && romanPart !== romanPart.toUpperCase();

        // Map Roman to standard degree
        const romanToDegree = {
            'I': 'I', 'II': 'II', 'III': 'III', 'IV': 'IV', 'V': 'V', 'VI': 'VI', 'VII': 'VII'
        };
        const degree = romanToDegree[upperRoman];
        if (!degree) return trimmed;

        let semitones = intervals[degree] || 0;

        // Apply accidental
        if (accidental === 'b') semitones = (semitones - 1 + 12) % 12;
        if (accidental === '#') semitones = (semitones + 1) % 12;

        const notePitch = (keyPitch + semitones) % 12;
        const noteName = spellPitchForKey(notePitch, keyRoot, keyMode);

        // Build suffix: if lowercase and suffix doesn't already start with "m", add "m"
        let chordSuffix = suffix;
        if (isLowerCase) {
            // Don't double-add "m" if suffix already starts with "m" (but not "maj")
            if (!chordSuffix.match(/^m(?!aj)/i)) {
                chordSuffix = 'm' + chordSuffix;
            }
        }

        // Handle diminished (°) in suffix
        chordSuffix = chordSuffix.replace('°', 'dim');

        return noteName + chordSuffix;
    });

    return chordNames.join(' - ');
}

/**
 * Render mini fretboard diagram cards into a container for each chord in the progression.
 * Tonic chords (degree I) get yellow highlighting via the .is-tonic class.
 */
// Every different chord of the song in order of appearance (slash chords and extensions included), spelled for the key
function songUniqueChords(chordText, lyrics, tonality) {
    const seen = new Set();
    const out = [];
    const add = c => {
        const n = normalizeChordName(c);
        if (!n || !getChordTones(n) || seen.has(canonChordKey(n))) return;
        seen.add(canonChordKey(n));
        out.push(spellChordForKey(n, tonality));
    };
    parseChordSections(chordText || '').forEach(sec => sec.chords.forEach(add));
    if (!out.length && Array.isArray(lyrics)) lyrics.forEach(sec => sec.lines.forEach(l => l.chords.forEach(c => add(c.chord))));
    return out;
}

function renderProgressionDiagrams(container, progressionStr, tonalityStr) {
    if (!container) return;
    container.innerHTML = '';
    container.style.flexWrap = 'wrap';

    // The roman-numeral string keeps only a few chords and folds slash chords away, so the cards come from the
    // chord text itself (the same list as the practice panel); the string is the fallback when there is no text.
    const editorChord = els.editChord && els.editChord.value.trim();
    const chordText = editorChord || (state.selectedSong && state.selectedSong.chord) || '';
    // Chords and key must come from the same place: an unsaved transposition lives in the editor, so its key
    // does too (otherwise Bbm9 is spelled A#m9 against the key saved in the sheet).
    const editorTonality = els.editTonality && els.editTonality.value.trim();
    if (editorChord && editorTonality) tonalityStr = editorTonality;
    const allChords = tonalityStr ? songUniqueChords(chordText, state.selectedLyrics, tonalityStr) : [];

    if ((!progressionStr && !allChords.length) || !tonalityStr) return;

    const tonalityMatch = tonalityStr.match(/^([A-G][#b]?)\s+(Major|Minor)$/i);
    if (!tonalityMatch) return;

    const keyRoot = tonalityMatch[1];
    const keyMode = tonalityMatch[2].toLowerCase();
    const keyPitch = NOTE_PITCH_MAP[keyRoot];
    if (keyPitch === undefined) return;

    const preferFlats = isFlatKey(tonalityStr);
    const chromatic = preferFlats ? CHROMATIC_FLATS : CHROMATIC_SHARPS;

    const majorIntervals = { 'I': 0, 'II': 2, 'III': 4, 'IV': 5, 'V': 7, 'VI': 9, 'VII': 11 };
    const minorIntervals = { 'I': 0, 'II': 2, 'III': 3, 'IV': 5, 'V': 7, 'VI': 8, 'VII': 10 };
    const intervals = keyMode === 'minor' ? minorIntervals : majorIntervals;

    const cards = [];

    allChords.forEach(chordName => {
        const analysis = getChordAnalysis(chordName, tonalityStr);
        const card = document.createElement('div');
        card.className = 'progression-diagram-card' + (analysis.degree >= 1 ? ' chord-degree-' + analysis.degree : '');
        const romanLabel = document.createElement('span');
        romanLabel.className = 'prog-card-roman';
        romanLabel.textContent = analysis.roman;
        card.appendChild(romanLabel);
        const nameLabel = document.createElement('span');
        nameLabel.className = 'prog-card-name';
        nameLabel.textContent = chordName;
        card.appendChild(nameLabel);
        cards.push({ card, chordName });
        card.addEventListener('click', (e) => {
            e.stopPropagation();
            playChordNotes(chordName, card);
        });
        container.appendChild(card);
    });

    const parts = allChords.length ? [] : progressionStr.split(/\s*-\s*/);

    parts.forEach(part => {
        const trimmed = part.trim();
        if (!trimmed) return;

        const romanMatch = trimmed.match(/^([b#]?)(i{1,3}v?|v?i{0,3}|IV|V|I{1,3})(.*?)$/i);
        if (!romanMatch) return;

        const accidental = romanMatch[1];
        const romanPart = romanMatch[2];
        const suffix = romanMatch[3];
        const upperRoman = romanPart.toUpperCase();
        const isLowerCase = romanPart === romanPart.toLowerCase() && romanPart !== romanPart.toUpperCase();

        const romanToDegree = { 'I': 'I', 'II': 'II', 'III': 'III', 'IV': 'IV', 'V': 'V', 'VI': 'VI', 'VII': 'VII' };
        const degreeStr = romanToDegree[upperRoman];
        if (!degreeStr) return;

        // Map to numeric degree (1-7)
        const degreeNumMap = { 'I': 1, 'II': 2, 'III': 3, 'IV': 4, 'V': 5, 'VI': 6, 'VII': 7 };
        const degreeNum = degreeNumMap[degreeStr] || 0;

        let semitones = intervals[degreeStr] || 0;
        if (accidental === 'b') semitones = (semitones - 1 + 12) % 12;
        if (accidental === '#') semitones = (semitones + 1) % 12;

        const notePitch = (keyPitch + semitones) % 12;
        const noteName = spellPitchForKey(notePitch, keyRoot, keyMode);

        let chordSuffix = suffix;
        if (isLowerCase) {
            if (!chordSuffix.match(/^m(?!aj)/i)) {
                chordSuffix = 'm' + chordSuffix;
            }
        }
        chordSuffix = chordSuffix.replace('°', 'dim');
        const chordName = noteName + chordSuffix;

        // Build the card with degree-based color class
        const card = document.createElement('div');
        card.className = 'progression-diagram-card' + (degreeNum >= 1 ? ' chord-degree-' + degreeNum : '');

        // Roman numeral label
        const romanLabel = document.createElement('span');
        romanLabel.className = 'prog-card-roman';
        romanLabel.textContent = trimmed;
        card.appendChild(romanLabel);

        // Chord name label
        const nameLabel = document.createElement('span');
        nameLabel.className = 'prog-card-name';
        nameLabel.textContent = chordName;
        card.appendChild(nameLabel);

        cards.push({ card, chordName });

        // Click to play
        card.addEventListener('click', (e) => {
            e.stopPropagation();
            playChordNotes(chordName, card);
        });

        container.appendChild(card);
    });

    // Mini SVG diagrams, voiced together so the shapes stay close on the neck
    const shapes = voiceChordSequence(cards.map(c => c.chordName));
    cards.forEach(({ card, chordName }, i) => {
        const svg = createGuitarChordDiagram(chordName, shapes[i]);
        if (svg) {
            svg.setAttribute('width', '68');
            svg.setAttribute('height', '78');
            card.appendChild(svg);
        }
    });
}

function transposeChordStructure(chordText, semitones, targetKey) {
    if (!chordText || semitones === 0) return chordText;

    // Split keeping section headers (<intro>, [verse], etc.) intact
    const sectionTagRegex = /(<[^>]+>|\[[^\]]+\]|\([^)]+\))/g;
    const nonChordWords = new Set([
        'intro', 'verse', 'chorus', 'bridge', 'outro', 'solo', 'pre', 'interlude',
        'instrumental', 'tab', 'ch', 'verso', 'estribillo', 'puente', 'guitar', 'riff'
    ]);

    const parts = chordText.split(sectionTagRegex);
    return parts.map(part => {
        if (!part) return '';
        // If it's a section tag like <intro> or [Verse], leave it intact
        if (part.match(sectionTagRegex)) {
            return part;
        }
        // Split by whitespace while preserving delimiters
        const tokens = part.split(/(\s+)/);
        return tokens.map(token => {
            if (!token || /^\s+$/.test(token)) return token;
            const cleanToken = token.trim();
            if (nonChordWords.has(cleanToken.toLowerCase())) return token;
            // Test if token resembles a valid chord
            if (/^[A-G][#b]?(?:[a-zA-Z0-9#b\-\+\/\(\)]*)$/.test(cleanToken)) {
                return transposeChordName(cleanToken, semitones, targetKey);
            }
            return token;
        }).join('');
    }).join('');
}

function transposeLyricsData(lyricsData, semitones, targetKey) {
    if (!lyricsData || !Array.isArray(lyricsData) || semitones === 0) return lyricsData;
    return lyricsData.map(section => {
        return {
            ...section,
            lines: section.lines.map(line => {
                return {
                    ...line,
                    chords: line.chords.map(c => {
                        return {
                            ...c,
                            chord: transposeChordName(c.chord, semitones, targetKey)
                        };
                    })
                };
            })
        };
    });
}

// Splits the structured chord text ("<intro> Gm Ab ... <verse_1> ...") into sections with their chord list
function parseChordSections(chordText) {
    const sections = [];
    let current = null;
    (chordText || '').split(/(<[^>]+>)/).forEach(part => {
        if (!part) return;
        const tag = part.match(/^<([^>]+)>$/);
        if (tag) {
            current = { name: tag[1], chords: [] };
            sections.push(current);
        } else if (current) {
            part.split(/\s+/).filter(t => /^[A-G][#b]?[a-zA-Z0-9#b\-+\/()]*$/.test(t)).forEach(t => current.chords.push(t));
        }
    });
    return sections;
}

// After the chord text is edited, copy the new chord names into the lyrics view. Sections are matched in
// order by name and by number of chords, so a text section that doesn't line up is skipped.
// Returns { lyrics, updated, total } (lyrics is the original array when nothing could be aligned).
function resyncLyricsChords(lyricsData, chordText) {
    if (!Array.isArray(lyricsData) || !lyricsData.length) return { lyrics: lyricsData, updated: 0, total: 0 };
    const norm = n => String(n).toLowerCase().replace(/[_\s]+/g, '');
    const base = n => norm(n).replace(/\d+$/, '');
    const textSections = parseChordSections(chordText);
    let ptr = 0;
    let updated = 0;
    const result = lyricsData.map(section => {
        const slots = section.lines.reduce((n, l) => n + l.chords.length, 0);
        const name = section.section || '';
        const idx = textSections.findIndex((t, i) =>
            i >= ptr && t.chords.length === slots && (norm(t.name) === norm(name) || base(t.name) === base(name)));
        if (idx === -1) return section;
        ptr = idx + 1;
        const chords = textSections[idx].chords;
        let k = 0;
        updated++;
        return {
            ...section,
            lines: section.lines.map(line => ({
                ...line,
                chords: line.chords.map(c => ({ ...c, chord: chords[k++] }))
            }))
        };
    });
    if (updated < lyricsData.length) {
        const aligned = alignLyricsToChordText(lyricsData, textSections.flatMap(t => t.chords));
        if (aligned) return { lyrics: aligned.lyrics, updated: lyricsData.length, total: lyricsData.length, removed: aligned.removed, added: aligned.added };
    }
    return { lyrics: result, updated, total: lyricsData.length };
}

// Whole-song alignment of the chords shown in the lyrics against the edited chord text (sequence alignment:
// same chord = match, same root = cheap substitution, otherwise gap). Chords that only exist in the lyrics are
// dropped, ones that only exist in the text are inserted after the previous chord. Returns null when the two
// sequences are too different to be the same song.
function alignChordSequences(oldChords, newChords) {
    const n = oldChords.length, m = newChords.length;
    if (!n || !m) return null;
    const root = c => (String(c).match(/^[A-G][#b]?/) || [''])[0];
    const sub = (a, b) => (a === b ? 0 : root(a) === root(b) ? 0.4 : 1);
    const GAP = 1;
    const D = Array.from({ length: n + 1 }, () => new Float32Array(m + 1));
    for (let i = 1; i <= n; i++) D[i][0] = i * GAP;
    for (let j = 1; j <= m; j++) D[0][j] = j * GAP;
    for (let i = 1; i <= n; i++) {
        for (let j = 1; j <= m; j++) {
            D[i][j] = Math.min(D[i - 1][j - 1] + sub(oldChords[i - 1], newChords[j - 1]), D[i - 1][j] + GAP, D[i][j - 1] + GAP);
        }
    }
    const ops = [];
    let i = n, j = m;
    while (i > 0 || j > 0) {
        if (i > 0 && j > 0 && D[i][j] === D[i - 1][j - 1] + sub(oldChords[i - 1], newChords[j - 1])) { ops.push({ i: i - 1, j: j - 1 }); i--; j--; }
        else if (i > 0 && D[i][j] === D[i - 1][j] + GAP) { ops.push({ i: i - 1 }); i--; }
        else { ops.push({ j: j - 1 }); j--; }
    }
    ops.reverse();
    const kept = ops.filter(o => o.i !== undefined && o.j !== undefined && root(oldChords[o.i]) === root(newChords[o.j])).length;
    return { ops, kept };
}

function alignLyricsToChordText(lyricsData, textChords) {
    const slots = [];
    lyricsData.forEach((sec, si) => sec.lines.forEach((l, li) => l.chords.forEach((c, ci) => slots.push({ si, li, ci, chord: c.chord }))));
    const n = slots.length, m = textChords.length;
    const al = alignChordSequences(slots.map(x => x.chord), textChords);
    if (!al || al.kept < 0.6 * Math.min(n, m)) return null;
    const { ops } = al;
    // the text often holds chords the lyrics never had (intro, solos...): only remove / replace, never inject them
    if (ops.some(o => o.i === undefined)) return null;

    const replacement = new Array(n).fill(null); // chord to show in each slot (null = remove)
    const after = Array.from({ length: n + 1 }, () => []); // chords to add after slot k-1 (index 0 = before the first)
    let slotPos = 0, removed = 0, added = 0;
    ops.forEach(o => {
        if (o.i !== undefined && o.j !== undefined) { replacement[o.i] = textChords[o.j]; slotPos = o.i + 1; }
        else if (o.i !== undefined) { removed++; slotPos = o.i + 1; }
        else { after[slotPos].push(textChords[o.j]); added++; }
    });

    const lyrics = lyricsData.map(sec => ({ ...sec, lines: sec.lines.map(l => ({ ...l, chords: [] })) }));
    const push = (si, li, chord, word_idx) => lyrics[si].lines[li].chords.push({ chord, word_idx });
    after[0].forEach(c => push(slots[0].si, slots[0].li, c, 0));
    slots.forEach((slot, idx) => {
        const orig = lyricsData[slot.si].lines[slot.li].chords[slot.ci];
        if (replacement[idx] !== null) lyrics[slot.si].lines[slot.li].chords.push({ ...orig, chord: replacement[idx] });
        after[idx + 1].forEach(c => push(slot.si, slot.li, c, orig.word_idx));
    });
    // a chord-only line that lost all its chords has nothing left to show
    lyrics.forEach(sec => { sec.lines = sec.lines.filter(l => l.lyric || l.chords.length); });
    return { lyrics, removed, added };
}

function shiftTonalityKey(currentTonalityStr, semitoneDelta) {
    const parsed = parseTonalityString(currentTonalityStr || 'C Major');
    const pitch = NOTE_PITCH_MAP[parsed.root] !== undefined ? NOTE_PITCH_MAP[parsed.root] : 0;
    let newPitch = (pitch + semitoneDelta) % 12;
    if (newPitch < 0) newPitch += 12;

    const majorKeyNames = ['C', 'C#', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'Ab', 'A', 'Bb', 'B'];
    const minorKeyNames = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'Bb', 'B'];

    const newRoot = parsed.mode === 'Minor' ? minorKeyNames[newPitch] : majorKeyNames[newPitch];
    return `${newRoot} ${parsed.mode}`;
}

function setSelectTonalityValue(val) {
    if (!els.editTonality) return;
    if (!val || val.trim() === '') {
        els.editTonality.value = "";
        return;
    }
    const cleanVal = val.trim();
    // Try exact match first
    for (let opt of els.editTonality.options) {
        if (opt.value.toLowerCase() === cleanVal.toLowerCase()) {
            els.editTonality.value = opt.value;
            return;
        }
    }
    // Try matching parsed canonical format (e.g. "Am" -> "A Minor")
    const parsed = parseTonalityString(cleanVal);
    for (let opt of els.editTonality.options) {
        if (opt.value.toLowerCase() === parsed.canonical.toLowerCase()) {
            els.editTonality.value = opt.value;
            return;
        }
    }
    // If not found in standard options, append custom option dynamically
    const opt = document.createElement('option');
    opt.value = cleanVal;
    opt.textContent = cleanVal;
    els.editTonality.appendChild(opt);
    els.editTonality.value = cleanVal;
}

// Normalization function to clean and map chord names
function normalizeChordName(name) {
    if (!name) return '';
    let normalized = name.trim();
    // Replace 's' representing sharp next to a note letter (e.g. Fs -> F#, Cs -> C#)
    normalized = normalized.replace(/^([A-G])s(?!us)/, '$1#'); // but not the s of sus: Dsus2 stays Dsus2
    // Also normalize the slash note (e.g. D/Fs -> D/F#)
    normalized = normalized.replace(/\/([A-G])s/, '/$1#');
    // Replace 'min' with 'm' (e.g. Amin -> Am, Bmin7 -> Bm7)
    normalized = normalized.replace(/min/, 'm');
    // Normalize spaces
    normalized = normalized.replace(/\s+/g, '');
    return normalized;
}


// Helper to create namespaced SVG elements
function createSVGElement(tag, attrs = {}) {
    const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (const [key, val] of Object.entries(attrs)) {
        el.setAttribute(key, val);
    }
    return el;
}

// Draw a beautiful, modern guitar chord diagram in SVG format
function createGuitarChordDiagram(chordName, shape = getChordShape(chordName)) {
    if (!shape) {
        return null;
    }
    
    const svg = createSVGElement("svg", {
        viewBox: "0 0 80 90",
        width: "80",
        height: "90"
    });
    
    // Auto-calculate base fret to support high-fret chords
    const positiveFrets = shape.frets.filter(f => f > 0);
    let baseFret = 1;
    // Start the diagram at the lowest fretted note so a shape at fret 2 isn't mistaken for an open chord
    if (positiveFrets.length > 0 && !shape.frets.includes(0)) {
        baseFret = Math.min(...positiveFrets);
    }
    
    // 1. Draw Frets (5 horizontal lines for 4 fret slots)
    for (let j = 0; j <= 4; j++) {
        const y = 20 + j * 12;
        const line = createSVGElement("line", {
            x1: "15",
            y1: y,
            x2: "65",
            y2: y,
            class: j === 0 && baseFret === 1 ? "chord-nut" : "chord-fret-line"
        });
        svg.appendChild(line);
    }
    
    // 2. Draw Strings (6 vertical lines)
    for (let i = 0; i <= 5; i++) {
        const x = 15 + i * 10;
        const line = createSVGElement("line", {
            x1: x,
            y1: "20",
            x2: x,
            y2: "68",
            class: "chord-string-line"
        });
        svg.appendChild(line);
    }
    
    // 3. Draw Fret Number on the left if baseFret > 1
    if (baseFret > 1) {
        const txt = createSVGElement("text", {
            x: "9.5",
            y: "26",
            "text-anchor": "end",
            class: "fret-label"
        });
        txt.textContent = `${baseFret}`;
        svg.appendChild(txt);
    }
    
    // 4. Draw Cejilla (Barre) if defined
    if (shape.barres && shape.barres.length > 0) {
        shape.barres.forEach(barre => {
            const relFret = barre.fret - baseFret + 1;
            if (relFret >= 1 && relFret <= 4) {
                const y = 20 + (relFret - 0.5) * 12;
                const x1 = 15 + barre.start * 10;
                const x2 = 15 + barre.end * 10;
                const line = createSVGElement("line", {
                    x1: x1,
                    y1: y,
                    x2: x2,
                    y2: y,
                    class: "chord-barre"
                });
                svg.appendChild(line);
            }
        });
    }
    
    // 5. Draw Open/Muted indicators and Fretted dots
    for (let i = 0; i <= 5; i++) {
        const fret = shape.frets[i];
        const finger = shape.fingers ? shape.fingers[i] : 0;
        const x = 15 + i * 10;
        
        if (fret === -1) {
            // Muted string 'X'
            const text = createSVGElement("text", {
                x: x,
                y: "12",
                class: "string-marker muted"
            });
            text.textContent = "×";
            svg.appendChild(text);
        } else if (fret === 0) {
            // Open string 'O'
            const text = createSVGElement("text", {
                x: x,
                y: "12",
                class: "string-marker open"
            });
            text.textContent = "○";
            svg.appendChild(text);
        } else {
            // Fretted dot
            const relFret = fret - baseFret + 1;
            if (relFret >= 1 && relFret <= 4) {
                const y = 20 + (relFret - 0.5) * 12;
                
                const dot = createSVGElement("circle", {
                    cx: x,
                    cy: y,
                    r: "4.5",
                    class: "chord-dot"
                });
                svg.appendChild(dot);
                
                // Finger number label
                if (finger > 0) {
                    const text = createSVGElement("text", {
                        x: x,
                        y: y,
                        class: "chord-dot-text"
                    });
                    text.textContent = finger;
                    svg.appendChild(text);
                }
            }
        }
    }
    
    return svg;
}

// Parse Google Sheet Chords and render them as interactive boxes
function renderChordSheet(chordString, lyricsData) {
    const container = els.focusChordsContainer;
    container.innerHTML = '';

    const hasLyrics = !!(lyricsData && lyricsData.length > 0);
    const hasChords = !!(chordString && chordString.trim() !== '');

    const expandBtn = document.getElementById('expand-chords-btn');
    if (!hasChords && !hasLyrics) {
        container.innerHTML = `<div class="empty-state font-sans" style="color: var(--text-tertiary); text-align: center;">Sin acordes estructurados cargados. Añádelos abajo para verlos y reproducirlos.</div>`;
        _updateLyricsToggle(false);
        if (expandBtn) expandBtn.classList.add('hide');
        return;
    }

    _updateLyricsToggle(hasLyrics);
    if (expandBtn) expandBtn.classList.remove('hide');

    // Si no hay acordes pero SÍ hay letras, forzamos la vista de letras
    if (hasLyrics && (!hasChords || state.chordViewMode === 'lyrics')) {
        _renderLyricsSheet(container, lyricsData);
    } else {
        _renderDiagramSheet(container, chordString);
    }
}

// ── Diagram Sheet (existing behavior) ────────────────────────────────────────
function _renderDiagramSheet(container, chordString) {
    // Parse chords with section headers like <intro_1> or [verse_1]
    const regex = /(<[^>]+>|\[[^\]]+\])/g;
    const parts = chordString.split(regex);

    let activeSectionName = "Canción";
    let activeChords = [];

    const renderActiveSection = () => {
        if (activeChords.length > 0) {
            const block = document.createElement('div');
            block.className = "chord-section-block";

            const title = document.createElement('div');
            title.className = "chord-section-title";
            title.textContent = activeSectionName;
            block.appendChild(title);

            const grid = document.createElement('div');
            grid.className = "chord-grid";

            // Voice the whole section together so the shapes stay close on the neck
            const sectionShapes = voiceChordSequence(activeChords.map(c => c.trim()));
            activeChords.forEach((ch, chIdx) => {
                if (ch.trim() === '') return;

                const box = document.createElement('div');
                box.className = "chord-box font-mono";
                
                const tonalityString = (els.editTonality ? els.editTonality.value : null) || (state.selectedSong ? state.selectedSong.tonality : null);
                const analysis = getChordAnalysis(ch, tonalityString);

                if (analysis.degree >= 1 && analysis.degree <= 7) {
                    box.classList.add('chord-degree-' + analysis.degree);
                }

                if (analysis.roman) {
                    const romanEl = document.createElement('span');
                    romanEl.className = 'chord-box-roman';
                    romanEl.textContent = analysis.roman;
                    box.appendChild(romanEl);
                }

                // Chord Name label
                const nameEl = document.createElement('span');
                nameEl.className = 'chord-name';
                nameEl.textContent = spellChordForKey(ch, tonalityString);
                box.appendChild(nameEl);

                // Guitar Diagram
                const svg = createGuitarChordDiagram(ch, sectionShapes[chIdx]);
                if (svg) {
                    box.appendChild(svg);
                } else {
                    const fallbackEl = document.createElement('div');
                    fallbackEl.className = 'chord-fallback';
                    fallbackEl.style.fontSize = '10px';
                    fallbackEl.style.color = 'var(--text-tertiary)';
                    fallbackEl.style.marginTop = '24px';
                    fallbackEl.textContent = 'N/A';
                    box.appendChild(fallbackEl);
                }

                // Play chords in Synthesizer on click
                box.addEventListener('click', (e) => {
                    e.stopPropagation();
                    playChordNotes(ch, box);
                });

                grid.appendChild(box);
            });

            block.appendChild(grid);
            container.appendChild(block);
        }
    };

    parts.forEach(part => {
        if (part.match(regex)) {
            // Found section header tag. Render previous section first.
            renderActiveSection();

            // Set new section name (remove brackets/carats and capitalize)
            const rawName = part.replace(/[<>[\]]/g, '').replace(/_/g, ' ');
            activeSectionName = rawName.charAt(0).toUpperCase() + rawName.slice(1);
            activeChords = [];
        } else {
            // Accumulate chords
            const chords = part.trim().split(/\s+/);
            activeChords = activeChords.concat(chords);
        }
    });

    // Render last remaining section
    renderActiveSection();
}

// ── Lyrics Sheet (new mode) ───────────────────────────────────────────────────
function _renderLyricsSheet(container, lyricsData) {
    const sheet = document.createElement('div');
    sheet.className = 'lyrics-chord-sheet';

    // Helper: create a chord chip with an SVG diagram tooltip
    function _makeChordChip(chordName, extraClass = '', ref = null) {
        const wrap = document.createElement('span');
        wrap.className = 'lyrics-chord-chip-wrap' + (extraClass ? ' ' + extraClass : '');

        const tonalityString = (els.editTonality ? els.editTonality.value : null) || (state.selectedSong ? state.selectedSong.tonality : null);
        const analysis = getChordAnalysis(chordName, tonalityString);

        if (analysis.roman) {
            const romanEl = document.createElement('span');
            romanEl.className = 'lyrics-chord-roman';
            romanEl.textContent = analysis.roman;
            wrap.appendChild(romanEl);
        }

        const chip = document.createElement('span');
        chip.className = 'lyrics-chord-chip';
        
        if (analysis.degree >= 1 && analysis.degree <= 7) {
            chip.classList.add('chord-degree-' + analysis.degree);
        }
        
        chip.textContent = spellChordForKey(chordName, tonalityString);
        chip.addEventListener('click', (e) => { e.stopPropagation(); playChordNotes(chordName, chip); });
        wrap.appendChild(chip);

        if (ref) {
            const actions = document.createElement('span');
            actions.className = 'chord-edit-actions';
            const mk = (icon, title, cls) => {
                const b = document.createElement('button');
                b.type = 'button';
                b.className = 'chord-edit-btn ' + cls;
                b.title = title;
                b.innerHTML = `<i class="ph ph-${icon}"></i>`;
                return b;
            };
            const editBtn = mk('pencil-simple', 'Cambiar acorde', 'edit');
            const delBtn = mk('x', 'Quitar acorde', 'del');
            const addBtn = mk('plus', 'Añadir un acorde después de este', 'add');
            actions.append(addBtn, editBtn, delBtn);
            addBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                actions.remove();
                promptChordInline(wrap, name => addLyricsChord(ref.si, ref.li, ref.word_idx, ref.ci + 1, name), () => wrap.appendChild(actions));
            });
            wrap.appendChild(actions);

            editBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                const input = document.createElement('input');
                input.className = 'lyrics-chord-input';
                input.value = chip.textContent;
                input.size = Math.max(4, chip.textContent.length + 1);
                chip.replaceWith(input);
                actions.remove();
                input.focus();
                input.select();
                let done = false;
                const finish = async (commit) => {
                    if (done) return;
                    done = true;
                    const value = input.value.trim();
                    if (!commit || !value || value === chip.textContent) { input.replaceWith(chip); return; }
                    const name = normalizeChordName(value);
                    if (!getChordTones(name)) {
                        showToast(`"${value}" no es un acorde reconocido`, true);
                        input.replaceWith(chip);
                        return;
                    }
                    await editLyricsChord(ref, name);
                };
                input.addEventListener('keydown', (ev) => {
                    if (ev.key === 'Enter') finish(true);
                    else if (ev.key === 'Escape') finish(false);
                });
                input.addEventListener('blur', () => finish(true));
                input.addEventListener('click', ev => ev.stopPropagation());
            });
            delBtn.addEventListener('click', async (e) => {
                e.stopPropagation();
                await editLyricsChord(ref, null);
            });
        }

        // Build the diagram tooltip
        const tooltip = document.createElement('span');
        tooltip.className = 'chord-diagram-tooltip';
        const diag = createGuitarChordDiagram(chordName);
        if (diag) {
            // Resize diagram to fit tooltip
            diag.setAttribute('width', '72');
            diag.setAttribute('height', '82');
            tooltip.appendChild(diag);
        } else {
            tooltip.textContent = chordName;
        }
        wrap.appendChild(tooltip);

        return wrap;
    }

    lyricsData.forEach((section, si) => {
        const block = document.createElement('div');
        block.className = 'lyrics-section-block';

        const title = document.createElement('div');
        title.className = 'lyrics-section-title';
        title.textContent = section.section;
        block.appendChild(title);

        section.lines.forEach((lineData, li) => {
            const lineEl = document.createElement('div');
            lineEl.className = 'lyrics-line';

            const { lyric, chords } = lineData;

            if (!lyric && chords.length > 0) {
                // Chord-only line: show chips with diagrams
                const chordRow = document.createElement('div');
                chordRow.className = 'lyrics-chord-row chord-only-row';
                chords.forEach((c, ci) => {
                    chordRow.appendChild(_makeChordChip(c.chord, '', { si, li, ci, word_idx: c.word_idx }));
                });
                const addEnd = document.createElement('button');
                addEnd.type = 'button';
                addEnd.className = 'chord-add-btn chord-add-end';
                addEnd.title = 'Añadir un acorde al final de la línea';
                addEnd.innerHTML = '<i class="ph ph-plus"></i>';
                addEnd.addEventListener('click', (e) => {
                    e.stopPropagation();
                    addEnd.style.display = 'none';
                    promptChordInline(chordRow, name => addLyricsChord(si, li, 0, chords.length, name), () => { addEnd.style.display = ''; });
                });
                chordRow.appendChild(addEnd);
                lineEl.appendChild(chordRow);
                block.appendChild(lineEl);
                return;
            }

            if (!lyric) return; // skip truly empty lines

            // Build a chord-position map: word_idx → chord name(s)
            const chordMap = {};
            chords.forEach((c, ci) => {
                const widx = Math.max(0, c.word_idx);
                if (!chordMap[widx]) chordMap[widx] = [];
                chordMap[widx].push({ name: c.chord, ref: { si, li, ci, word_idx: c.word_idx } });
            });

            // Render words with chord chips above (each chip has a diagram tooltip)
            const words = lyric.split(/\s+/).filter(Boolean);
            const wordContainer = document.createElement('div');
            wordContainer.className = 'lyrics-words';

            words.forEach((word, wi) => {
                const wordEl = document.createElement('span');
                wordEl.className = 'lyrics-word';

                if (chordMap[wi]) {
                    // One chip per chord at this word position
                    const chordAboveWrap = document.createElement('span');
                    chordAboveWrap.className = 'lyrics-chord-above-group';
                    chordMap[wi].forEach(ch => {
                        chordAboveWrap.appendChild(_makeChordChip(ch.name, 'above', ch.ref));
                    });
                    wordEl.appendChild(chordAboveWrap);
                } else {
                    // Spacer so all words align vertically
                    const spacer = document.createElement('span');
                    spacer.className = 'lyrics-chord-spacer';
                    wordEl.appendChild(spacer);
                }
                if (!chordMap[wi]) {
                    const add = document.createElement('button');
                    add.type = 'button';
                    add.className = 'chord-add-btn';
                    add.title = 'Añadir un acorde sobre esta palabra';
                    add.innerHTML = '<i class="ph ph-plus"></i>';
                    add.addEventListener('click', (e) => {
                        e.stopPropagation();
                        add.style.display = 'none';
                        // keep the chords of the line ordered by word: go after every chord placed on or before this word
                        let at = chords.findIndex(c => Math.max(0, c.word_idx) > wi);
                        if (at === -1) at = chords.length;
                        promptChordInline(wordEl, name => addLyricsChord(si, li, wi, at, name), () => { add.style.display = ''; });
                    });
                    wordEl.appendChild(add);
                }

                const textNode = document.createElement('span');
                textNode.className = 'lyrics-word-text';
                textNode.textContent = word;
                wordEl.appendChild(textNode);

                wordContainer.appendChild(wordEl);
            });

            lineEl.appendChild(wordContainer);
            block.appendChild(lineEl);
        });

        sheet.appendChild(block);
    });

    container.appendChild(sheet);
}

// ── Toggle visibility & state ─────────────────────────────────────────────────
function _updateLyricsToggle(hasLyrics) {
    const btn = document.getElementById('lyrics-view-toggle');
    if (!btn) return;
    if (hasLyrics) {
        btn.classList.remove('hide');
        btn.querySelector('.toggle-label').textContent =
            state.chordViewMode === 'lyrics' ? 'Ver Diagramas' : 'Ver con Letra';
        const icon = btn.querySelector('i');
        if (icon) {
            icon.className = state.chordViewMode === 'lyrics'
                ? 'ph ph-guitar'
                : 'ph ph-text-aa';
        }
    } else {
        btn.classList.add('hide');
    }
}


// YouTube Player loader
function loadYouTubeEmbed(videoId) {
    if (!videoId || videoId.trim() === '') {
        els.videoPlaceholder.innerHTML = `<i class="ph ph-video-camera-slash"></i><span>Sin video disponible de YouTube</span>`;
        els.videoPlaceholder.classList.remove('hide');
        els.videoWrapper.classList.add('hide');
        els.youtubePlayer.src = '';
        // Keep the actions row so a video can still be searched for; only the direct link needs a video
        if (els.youtubeActionsContainer) els.youtubeActionsContainer.classList.remove('hide');
        if (els.youtubeDirectLink) els.youtubeDirectLink.classList.add('hide');
    } else {
        els.videoPlaceholder.classList.add('hide');
        els.videoWrapper.classList.remove('hide');
        // Load YouTube embed safely (music.youtube.com blocks iframe embeds via CSP)
        els.youtubePlayer.src = `https://www.youtube.com/embed/${videoId.trim()}?enablejsapi=1`;
        if (els.youtubeActionsContainer && els.youtubeDirectLink) {
            els.youtubeDirectLink.classList.remove('hide');
            els.youtubeDirectLink.href = `https://music.youtube.com/watch?v=${videoId.trim()}`;
            els.youtubeActionsContainer.classList.remove('hide');
        }
    }
}

// 8. WEB AUDIO SYNTHESIZER ENGINE (Premium Rhodes & Warm Ambient Synth)
function playChordNotes(chordName, buttonEl) {
    initAudioContext();
    
    // Visual playing highlight
    buttonEl.classList.add('playing');
    setTimeout(() => buttonEl.classList.remove('playing'), 800);
    
    // Stop currently active notes to prevent overlapping chaos
    stopCurrentNotes();
    
    // Parse chord details
    const parsed = parseChord(chordName);
    if (!parsed) return;
    
    const freqs = parsed.notes.map(note => NOTE_FREQS[note]).filter(x => x);
    if (freqs.length === 0) return;
    
    const now = state.audioContext.currentTime;

    // Alternative instrument chosen in the header: a gentle strum through the shared sound bank
    const instrumentId = window.VibemusSound ? window.VibemusSound.getId() : 'original';
    if (instrumentId !== 'original') {
        freqs.forEach((freq, idx) => {
            const oscs = window.VibemusSound.playNote(state.audioContext, state.audioContext.destination, freq, now + idx * 0.018, 1.6, instrumentId, Math.min(1, 2.4 / freqs.length));
            state.synths.push(...oscs);
        });
        return;
    }
    
    // Create master chord gain node
    const chordGainNode = state.audioContext.createGain();
    chordGainNode.gain.setValueAtTime(0.7, now);
    
    // 1. Classic Tremolo (LFO)
    const lfo = state.audioContext.createOscillator();
    lfo.type = 'sine';
    lfo.frequency.setValueAtTime(4.8, now); // 4.8 Hz tremolo speed
    
    const lfoGain = state.audioContext.createGain();
    lfoGain.gain.setValueAtTime(0.18, now); // 18% depth
    
    lfo.connect(lfoGain);
    lfoGain.connect(chordGainNode.gain);
    
    lfo.start(now);
    lfo.stop(now + 2.5);
    state.synths.push(lfo);
    
    // 2. Main Filter (lowpass to make it warm and analog)
    const mainFilter = state.audioContext.createBiquadFilter();
    mainFilter.type = 'lowpass';
    mainFilter.frequency.setValueAtTime(1400, now);
    
    // 3. Stereo Spatial Delay Line (for premium ambient space)
    const delayNode = state.audioContext.createDelay(1.0);
    delayNode.delayTime.setValueAtTime(0.24, now); // 240ms delay
    
    const delayFeedback = state.audioContext.createGain();
    delayFeedback.gain.setValueAtTime(0.25, now); // 25% feedback
    
    const delayFilter = state.audioContext.createBiquadFilter();
    delayFilter.type = 'lowpass';
    delayFilter.frequency.setValueAtTime(700, now); // Darken the echoes
    
    // Connect feedback loop
    delayNode.connect(delayFilter);
    delayFilter.connect(delayFeedback);
    delayFeedback.connect(delayNode);
    
    // Delay Wet mix node
    const delayWet = state.audioContext.createGain();
    delayWet.gain.setValueAtTime(0.15, now); // 15% wet mix
    delayNode.connect(delayWet);
    
    // Connect Main paths to destination
    chordGainNode.connect(mainFilter);
    mainFilter.connect(state.audioContext.destination);
    
    // Connect delay input and wet output
    mainFilter.connect(delayNode);
    delayWet.connect(state.audioContext.destination);
    
    // 4. Generate voices for each chord note
    freqs.forEach((freq, idx) => {
        // Base note panning
        let panner = null;
        let noteDest = chordGainNode;
        
        if (state.audioContext.createStereoPanner) {
            panner = state.audioContext.createStereoPanner();
            const panVal = freqs.length > 1 ? ((idx / (freqs.length - 1)) * 0.6 - 0.3) : 0;
            panner.pan.setValueAtTime(panVal, now);
            panner.connect(chordGainNode);
            noteDest = panner;
        }
        
        // --- VOICE A: Triangle Fundamental ---
        const oscTri = state.audioContext.createOscillator();
        oscTri.type = 'triangle';
        oscTri.frequency.setValueAtTime(freq, now);
        oscTri.detune.setValueAtTime(-4, now); // slightly detuned down
        
        const gainTri = state.audioContext.createGain();
        gainTri.gain.setValueAtTime(0, now);
        gainTri.gain.linearRampToValueAtTime(0.12, now + 0.02); // attack
        gainTri.gain.exponentialRampToValueAtTime(0.001, now + 1.8); // long warm decay
        
        oscTri.connect(gainTri);
        gainTri.connect(noteDest);
        
        oscTri.start(now);
        oscTri.stop(now + 2.0);
        state.synths.push(oscTri);
        
        // --- VOICE B: Sine Fundamental (Warmth) ---
        const oscSine = state.audioContext.createOscillator();
        oscSine.type = 'sine';
        oscSine.frequency.setValueAtTime(freq, now);
        oscSine.detune.setValueAtTime(4, now); // slightly detuned up
        
        const gainSine = state.audioContext.createGain();
        gainSine.gain.setValueAtTime(0, now);
        gainSine.gain.linearRampToValueAtTime(0.12, now + 0.02);
        gainSine.gain.exponentialRampToValueAtTime(0.001, now + 1.8);
        
        oscSine.connect(gainSine);
        gainSine.connect(noteDest);
        
        oscSine.start(now);
        oscSine.stop(now + 2.0);
        state.synths.push(oscSine);

        // --- VOICE C: Bright Rhodes Tine Strike (transient) ---
        const oscTine = state.audioContext.createOscillator();
        oscTine.type = 'sine';
        // Rhodes tines ring at high harmonics or integer multiples + slight offset
        const tineFreq = freq * 4.5;
        oscTine.frequency.setValueAtTime(tineFreq, now);
        
        const gainTine = state.audioContext.createGain();
        gainTine.gain.setValueAtTime(0, now);
        gainTine.gain.linearRampToValueAtTime(0.08, now + 0.002); // instant strike attack
        gainTine.gain.exponentialRampToValueAtTime(0.0001, now + 0.08); // extremely rapid decay
        
        // Highpass filter specifically for the tine to keep it clear and bell-like
        const tineFilter = state.audioContext.createBiquadFilter();
        tineFilter.type = 'highpass';
        tineFilter.frequency.setValueAtTime(1200, now);
        
        oscTine.connect(tineFilter);
        tineFilter.connect(gainTine);
        gainTine.connect(noteDest);
        
        oscTine.start(now);
        oscTine.stop(now + 0.15);
        state.synths.push(oscTine);
        
        // --- VOICE D: Sub-octave Bass Weight (Roots only) ---
        if (idx === 0) {
            const oscBass = state.audioContext.createOscillator();
            oscBass.type = 'sine';
            oscBass.frequency.setValueAtTime(freq / 2, now); // One octave lower
            
            const gainBass = state.audioContext.createGain();
            gainBass.gain.setValueAtTime(0, now);
            gainBass.gain.linearRampToValueAtTime(0.22, now + 0.03); // slightly slower attack
            gainBass.gain.exponentialRampToValueAtTime(0.001, now + 2.2); // extra long tail
            
            // Separate warm bass filter to keep low-end clean
            const bassFilter = state.audioContext.createBiquadFilter();
            bassFilter.type = 'lowpass';
            bassFilter.frequency.setValueAtTime(250, now);
            
            oscBass.connect(bassFilter);
            bassFilter.connect(gainBass);
            gainBass.connect(chordGainNode); // directly to main gain, bypass panning for center bass weight
            
            oscBass.start(now);
            oscBass.stop(now + 2.4);
            state.synths.push(oscBass);
        }
    });
}

// Header selector: sound used by chords and scale playback everywhere in the app
(function setupInstrumentSelect() {
    const sel = document.getElementById('instrument-select');
    if (!sel || !window.VibemusSound) return;
    const { instruments, getId, setId } = window.VibemusSound;
    sel.innerHTML = Object.entries(instruments).map(([id, i]) => `<option value="${id}">${i.label}</option>`).join('');
    sel.value = getId();
    sel.addEventListener('change', () => setId(sel.value));
})();

function initAudioContext() {
    if (!state.audioContext) {
        state.audioContext = new (window.AudioContext || window.webkitAudioContext)();
        els.audioHud.classList.remove('hide');
        els.audioHudText.textContent = "Sintetizador Web Audio Inicializado 🎹";
        setTimeout(() => els.audioHud.classList.add('hide'), 3000);
    }
    if (state.audioContext && state.audioContext.state === 'suspended') {
        state.audioContext.resume();
    }
}

function stopCurrentNotes() {
    state.synths.forEach(osc => {
        try { osc.stop(); } catch (e) {}
    });
    state.synths = [];
}

// Chord notes translator logic (Circle of Fifths integration)
function parseChord(chordName) {
    // Strip section codes or complex slashes e.g. C/G becomes C
    const baseChord = chordName.split('/')[0].trim();
    if (baseChord === '') return null;
    
    // Parse root note and modifier suffix
    const regex = /^([A-G][#b]?)(.*)$/;
    const match = baseChord.match(regex);
    if (!match) return null;
    
    const root = match[1];
    const suffix = match[2].toLowerCase();
    
    // Key scale indexes (semitones)
    const semitones = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];
    const rootIdx = semitones.indexOf(normalizeNote(root));
    if (rootIdx === -1) return null;
    
    // Define chord formulas by intervals (semitone distances from root)
    let intervals = [0, 4, 7]; // Major triad default
    
    if (suffix.includes('min') || suffix.includes('m') && !suffix.includes('maj')) {
        intervals = [0, 3, 7]; // Minor triad
    }
    
    if (suffix.includes('7')) {
        if (suffix.includes('maj') || suffix.includes('maj7')) {
            intervals = [0, 4, 7, 11]; // Major 7th
        } else if (suffix.includes('min') || suffix.includes('m7')) {
            intervals = [0, 3, 7, 10]; // Minor 7th
        } else {
            intervals = [0, 4, 7, 10]; // Dominant 7th
        }
    } else if (suffix.includes('dim')) {
        intervals = [0, 3, 6]; // Diminished
    } else if (suffix.includes('aug')) {
        intervals = [0, 4, 8]; // Augmented
    } else if (suffix.includes('sus4')) {
        intervals = [0, 5, 7]; // Suspended 4th
    }
    
    // Translate intervals to actual notes
    const notes = intervals.map(interval => {
        const idx = (rootIdx + interval) % 12;
        return semitones[idx];
    });
    
    return { root, suffix, notes };
}

// Convert Bb to A#, Db to C#, etc. for strict mapping
function normalizeNote(note) {
    const flatToSharp = { 'Db': 'C#', 'Eb': 'D#', 'Gb': 'F#', 'Ab': 'G#', 'Bb': 'A#' };
    return flatToSharp[note] || note;
}

// Setup Dashboard User Events
function setupEventListeners() {
    // 1. Text Search Input
    els.globalSearch.addEventListener('input', (e) => {
        state.activeFilters.search = e.target.value;
        applyFiltersAndRender();
        
        // Reset scroll position to top when searching
        const scrollContainer = document.querySelector('.songs-list-container');
        if (scrollContainer) {
            scrollContainer.scrollTop = 0;
        }
    });
    
    // Global keyboard shortcut focus search
    window.addEventListener('keydown', (e) => {
        if (e.key === '/' && document.activeElement !== els.globalSearch) {
            e.preventDefault();
            els.globalSearch.focus();
            els.globalSearch.select();
        }
    });

    // 1a. Liked filter card
    if (els.filterLikedCard) {
        els.filterLikedCard.addEventListener('click', () => {
            state.activeFilters.likedOnly = !state.activeFilters.likedOnly;
            els.filterLikedCard.classList.toggle('active', state.activeFilters.likedOnly);
            applyFiltersAndRender();
        });
    }

    // 1b. Progression Length Filter Selector
    els.filterProgressionLength.addEventListener('change', (e) => {
        state.activeFilters.progressionLength = e.target.value;
        // When length changes, reset specific progression filter and update available options
        state.activeFilters.progression = 'all';
        populateProgressionOptions();
        applyFiltersAndRender();
    });

    // 1c. Progression Filter Selector
    els.filterProgression.addEventListener('change', (e) => {
        state.activeFilters.progression = e.target.value;
        applyFiltersAndRender();
    });

    // 2. Playlists Filter Selector
    els.filterPlaylist.addEventListener('change', (e) => {
        state.activeFilters.playlist = e.target.value;
        
        // Reset just found filter on playlist change to avoid confusion
        state.activeFilters.justFound = false;
        state.justFoundRows = [];
        if (els.justFoundBanner) {
            els.justFoundBanner.classList.add('hide');
        }
        
        applyFiltersAndRender();
        
        // Show/hide autocomplete playlist button
        if (e.target.value !== 'all') {
            els.autocompletePlaylistBtn.classList.remove('hide');
            updatePlaylistCacheUI(e.target.value);
        } else {
            els.autocompletePlaylistBtn.classList.add('hide');
            els.playlistCacheInfo.classList.add('hide');
        }
    });

    // 3. Complexity Filter Badges
    els.filterComplexity.addEventListener('click', (e) => {
        const btn = e.target.closest('.tag-btn');
        if (!btn) return;
        
        document.querySelectorAll('#filter-complexity .tag-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        
        state.activeFilters.complexity = btn.getAttribute('data-complexity');
        applyFiltersAndRender();
    });

    // 3b. Harmony Status Filter Badges
    if (els.filterHarmonyStatus) {
        els.filterHarmonyStatus.addEventListener('click', (e) => {
            const btn = e.target.closest('.tag-btn');
            if (!btn) return;
            
            document.querySelectorAll('#filter-harmony-status .tag-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            
            state.activeFilters.harmonyStatus = btn.getAttribute('data-harmony');
            applyFiltersAndRender();
        });
    }

    // 3c. Scan Status Filter Badges
    if (els.filterScanStatus) {
        els.filterScanStatus.addEventListener('click', (e) => {
            const btn = e.target.closest('.tag-btn');
            if (!btn) return;
            
            document.querySelectorAll('#filter-scan-status .tag-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            
            state.activeFilters.scanStatus = btn.getAttribute('data-scan');
            applyFiltersAndRender();
        });
    }

    // 4. Style Filter Badges — multi-select toggle (Delegated dynamically)
    els.filterStyle.addEventListener('click', (e) => {
        const btn = e.target.closest('.tag-btn');
        if (!btn) return;

        const val = btn.getAttribute('data-style');

        if (val === 'all') {
            // Reset: clear all selected styles
            state.activeFilters.styles.clear();
        } else {
            // Toggle the clicked style in the Set
            if (state.activeFilters.styles.has(val)) {
                state.activeFilters.styles.delete(val);
            } else {
                state.activeFilters.styles.add(val);
            }
        }

        // Sync visual active states
        const allActive = state.activeFilters.styles.size === 0;
        document.querySelector('#filter-style [data-style="all"]')?.classList.toggle('active', allActive);
        document.querySelectorAll('#filter-style .tag-btn:not([data-style="all"])').forEach(b => {
            b.classList.toggle('active', state.activeFilters.styles.has(b.getAttribute('data-style')));
        });

        applyFiltersAndRender();
    });

    // 5. Cloud Sync Button Click
    els.syncBtn.addEventListener('click', () => {
        fetchSongsFromServer();
    });

    // 5b. Bulk Restyle — recalcula estilos emocionales de todas las canciones
    els.bulkRestyleBtn.addEventListener('click', async () => {
        const btn = els.bulkRestyleBtn;
        const originalHTML = btn.innerHTML;

        // Estado de carga
        btn.disabled = true;
        btn.innerHTML = '<i class="ph ph-spinner" style="animation: spin 0.8s linear infinite;"></i><span>Recalculando...</span>';
        showToast('Recalculando estilos emocionales… esto puede tardar unos segundos.', false);

        try {
            const res  = await fetch('/api/bulk-restyle', { method: 'POST' });
            const data = await res.json();

            if (data.success) {
                showToast(`✓ ${data.updated} canciones actualizadas. Sincronizando...`);
                // Resincronizar para reflejar los nuevos estilos en la UI
                await fetchSongsFromServer();
            } else {
                showToast(`Error: ${data.error || 'Fallo desconocido'}`, true);
            }
        } catch (err) {
            showToast('Error de red al recalcular estilos.', true);
            console.error(err);
        } finally {
            btn.disabled = false;
            btn.innerHTML = originalHTML;
        }
    });

    // 6. Closures
    els.closeFocusBtn.addEventListener('click', () => {
        state.selectedSong = null;
        document.querySelector('.workspace-grid').classList.remove('focus-active');
        els.harmonyFocusPanel.classList.add('hide');
        els.harmonyEmptyPanel.classList.remove('hide');
        setCSSAccent('default');
        
        // Stop YouTube video
        els.youtubePlayer.src = '';
        applyFiltersAndRender();
    });

    // 7. Sorters
    els.sortTitleBtn.addEventListener('click', () => {
        els.sortScrobbleBtn.classList.remove('active');
        if (els.sortScanDateBtn) els.sortScanDateBtn.classList.remove('active');
        els.sortTitleBtn.classList.add('active');
        state.sortRule = 'title-asc';
        applyFiltersAndRender();
    });
    
    els.sortScrobbleBtn.addEventListener('click', () => {
        els.sortTitleBtn.classList.remove('active');
        if (els.sortScanDateBtn) els.sortScanDateBtn.classList.remove('active');
        els.sortScrobbleBtn.classList.add('active');
        state.sortRule = 'scrobble-desc';
        applyFiltersAndRender();
    });

    if (els.sortScanDateBtn) {
        els.sortScanDateBtn.addEventListener('click', () => {
            els.sortTitleBtn.classList.remove('active');
            els.sortScrobbleBtn.classList.remove('active');
            els.sortScanDateBtn.classList.add('active');
            state.sortRule = 'scan-desc';
            applyFiltersAndRender();
        });
    }

    // 8. Edit & Form Updates Submission
    els.editForm.addEventListener('submit', handleFormSubmission);

    // 9. Autodetect / Autocomplete Trigger
    els.autodetectBtn.addEventListener('click', handleAutodetect);
    els.modalRejectBtn.addEventListener('click', () => {
        els.confirmModal.classList.add('hide');
    });
    els.modalAcceptBtn.addEventListener('click', handleAcceptSuggestion);

    // 10. Source Tab Switching (if present)
    if (els.sourceTabs) {
        els.sourceTabs.forEach(tab => {
            tab.addEventListener('click', () => {
                els.sourceTabs.forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                state.selectedSource = tab.getAttribute('data-source');
            });
        });
    }

    // 11. Autocomplete Playlist Harmony
    els.autocompletePlaylistBtn.addEventListener('click', handleAutocompletePlaylist);

    // 12. Reset Playlist Cache
    if (els.resetPlaylistCacheBtn) {
        els.resetPlaylistCacheBtn.addEventListener('click', () => {
            const selectedPlaylist = state.activeFilters.playlist;
            if (selectedPlaylist && selectedPlaylist !== 'all') {
                if (confirm(`¿Estás seguro de que deseas reiniciar la caché de la playlist "${selectedPlaylist}"?\nEsto permitirá volver a escanear todas las canciones sin armonía.`)) {
                    resetPlaylistCache(selectedPlaylist);
                }
            }
        });
    }

    // 13. Reset Song Cache
    if (els.resetSongCacheBtn) {
        els.resetSongCacheBtn.addEventListener('click', () => {
            if (state.selectedSong) {
                resetSongCache(state.selectedSong);
            }
        });
    }

    // 14. Delete Song Harmony
    if (els.deleteHarmonyBtn) {
        els.deleteHarmonyBtn.addEventListener('click', handleDeleteHarmony);
    }

    // 14b. Lyrics / Diagrams view toggle
    const lyricsToggleBtn = document.getElementById('lyrics-view-toggle');
    if (lyricsToggleBtn) {
        lyricsToggleBtn.addEventListener('click', () => {
            state.chordViewMode = state.chordViewMode === 'lyrics' ? 'diagrams' : 'lyrics';
            renderChordSheet(
                state.selectedSong ? state.selectedSong.chord : '',
                state.selectedLyrics
            );
        });
    }

    // 14c. Expand Chords Modal
    const expandChordsBtn = document.getElementById('expand-chords-btn');
    const expandChordsModal = document.getElementById('expand-chords-modal');
    const closeExpandModalBtn = document.getElementById('close-expand-modal-btn');
    const expandedChordsContent = document.getElementById('expanded-chords-content');
    const expandedSongTitleLabel = document.getElementById('expanded-song-title-label');
    const expandedTonality = document.getElementById('expanded-tonality');
    const expandedProgression = document.getElementById('expanded-progression');
    const expandedProgressionChords = document.getElementById('expanded-progression-chords');
    const expandedStyle = document.getElementById('expanded-style');
    const expandedPlayer = document.getElementById('expanded-youtube-player');
    const expandedVideoEmpty = document.getElementById('expanded-video-empty');
    const ytCommand = (frame, func, args = '') => {
        if (frame && frame.contentWindow && frame.getAttribute('src')) {
            frame.contentWindow.postMessage(JSON.stringify({ event: 'command', func, args }), '*');
        }
    };
    // Same song volume as the mixer in the improvisation guide
    if (expandedPlayer) expandedPlayer.addEventListener('load', () => {
        const v = parseInt(localStorage.getItem('vibemus_vol_song'), 10);
        if (Number.isFinite(v)) ytCommand(expandedPlayer, 'setVolume', [v]);
    });

    if (expandChordsBtn && expandChordsModal) {
        expandChordsBtn.addEventListener('click', () => {
            if (!state.selectedSong) return;
            
            // Set song title in modal
            expandedSongTitleLabel.textContent = `${state.selectedSong.artist} - ${state.selectedSong.title}`;
            
            // Set song meta in modal
            if (expandedTonality) expandedTonality.textContent = state.selectedSong.tonality || '—';
            if (expandedProgression) expandedProgression.textContent = state.selectedSong.progression || '—';
            if (expandedProgressionChords) {
                const chordNames = romanProgressionToChords(state.selectedSong.progression, state.selectedSong.tonality);
                expandedProgressionChords.textContent = chordNames || '—';
            }
            if (expandedStyle) expandedStyle.textContent = state.selectedSong.emotional || state.selectedSong.style || '—';
            
            // Render mini fretboard diagrams for each chord in the progression
            const diagramsContainer = document.getElementById('expanded-progression-diagrams');
            renderProgressionDiagrams(diagramsContainer, state.selectedSong.progression, state.selectedSong.tonality);
            
            // Visible YouTube player in the header; the one on the main page is paused so only one plays
            const videoId = (state.selectedSong.videoId || '').trim();
            ytCommand(els.youtubePlayer, 'pauseVideo');
            if (expandedPlayer) {
                expandedPlayer.style.display = videoId ? 'block' : 'none';
                if (expandedVideoEmpty) expandedVideoEmpty.style.display = videoId ? 'none' : 'inline';
                expandedPlayer.src = videoId ? `https://www.youtube.com/embed/${videoId}?enablejsapi=1` : '';
            }
            
            expandedChordsContent.innerHTML = '<div id="chord-practice-panel"></div><div id="expanded-chord-sheet"></div>';
            renderChordPracticePanel(document.getElementById('chord-practice-panel'), state.selectedSong);
            renderExpandedChordSheet(document.getElementById('expanded-chord-sheet'), state.selectedSong);
            
            expandChordsModal.classList.remove('hide');
        });
        
        closeExpandModalBtn.addEventListener('click', () => {
            expandChordsModal.classList.add('hide');
            expandedChordsContent.innerHTML = ''; // Clean up memory and prevent double audio play events
            if (expandedPlayer) expandedPlayer.src = ''; // stops the video
        });
    }

    // 15. Real-time auto-analysis and interactive transposition
    if (els.editTonality) {
        els.editTonality.addEventListener('change', (e) => {
            handleTonalityChange(e.target.value);
        });
    }

    if (els.btnTransposeDown) {
        els.btnTransposeDown.addEventListener('click', (e) => {
            e.preventDefault();
            handleQuickTranspose(-1);
        });
    }

    if (els.btnTransposeUp) {
        els.btnTransposeUp.addEventListener('click', (e) => {
            e.preventDefault();
            handleQuickTranspose(1);
        });
    }

    // 16. Real-time auto-analysis when typing chords
    let chordAnalyzeTimeout = null;
    if (els.editChord) {
        els.editChord.addEventListener('blur', () => triggerLiveHarmonicAnalysis());
        els.editChord.addEventListener('input', () => {
            clearTimeout(chordAnalyzeTimeout);
            chordAnalyzeTimeout = setTimeout(() => triggerLiveHarmonicAnalysis(), 800);
        });
    }
}

// Re-analyze harmony in real-time and update all focus panel visuals
async function triggerLiveHarmonicAnalysis() {
    const chordText = els.editChord ? els.editChord.value.trim() : '';
    const tonalityText = els.editTonality ? els.editTonality.value.trim() : '';
    if (!chordText) return;
    
    try {
        const res = await fetch('/api/analyze-chords', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                chord: chordText,
                tonality: tonalityText
            })
        });
        if (res.ok) {
            const data = await res.json();
            if (data) {
                if (data.progression) els.editProgression.value = data.progression;
                if (data.skill || data.complex) els.editComplex.value = data.skill || data.complex;
                if (data.emotional || data.style) els.editStyle.value = data.emotional || data.style;
                if (!tonalityText && data.tonality) {
                    setSelectTonalityValue(data.tonality);
                    state.lastActiveTonality = data.tonality;
                }
                
                // Live update the visual Chord Map & Progression in Focus Panel
                renderChordSheet(chordText, state.selectedLyrics);
                els.focusProgressionText.textContent = data.progression || '— Sin Progresión Numérica';
                els.focusProgressionChords.textContent = romanProgressionToChords(data.progression, data.tonality || state.selectedSong?.tonality) || '';
                renderProgressionDiagrams(document.getElementById('focus-progression-diagrams'), data.progression, data.tonality || state.selectedSong?.tonality);
                els.focusBadgeComplexity.textContent = data.complex || 'Baja';
                els.focusBadgeStyle.textContent = data.style || 'Sin Estilo';
                shiftVibeAccentColor(data.style);
            }
        }
    } catch (err) {
        console.warn("Auto-análisis en tiempo real no disponible:", err);
    }
}

// Handle Tonality Dropdown Change and transpose chords accordingly
function handleTonalityChange(newTonality) {
    if (!newTonality) return;
    const currentChordText = els.editChord ? els.editChord.value : '';
    const oldTonality = state.lastActiveTonality || (state.selectedSong ? state.selectedSong.tonality : '');
    
    const hasChords = currentChordText.trim() !== '';
    const hasLyrics = state.selectedLyrics && Array.isArray(state.selectedLyrics);
    
    if (oldTonality && oldTonality.toLowerCase() !== newTonality.toLowerCase() && (hasChords || hasLyrics)) {
        const offset = getSemitoneOffset(oldTonality, newTonality);
        if (offset !== 0) {
            if (hasChords) {
                const transposedText = transposeChordStructure(currentChordText, offset, newTonality);
                if (els.editChord) {
                    els.editChord.value = transposedText;
                }
            }
            if (hasLyrics) {
                state.selectedLyrics = transposeLyricsData(state.selectedLyrics, offset, newTonality);
            }
            const semitoneLabel = offset > 6 ? (offset - 12) : (offset > 0 ? `+${offset}` : offset);
            showToast(`Armonía transpuesta a ${newTonality} (${semitoneLabel} st) 🎵`);
        }
    }
    
    state.lastActiveTonality = newTonality;
    // Redraw cards and sheet now with the new key (the analysis below returns early without chord text)
    refreshChordDiagrams();
    triggerLiveHarmonicAnalysis();
}

// Handle Quick Transpose Buttons (+1 / -1 semitone)
function handleQuickTranspose(deltaSemitones) {
    const currentTonality = (els.editTonality && els.editTonality.value) || state.lastActiveTonality || (state.selectedSong ? state.selectedSong.tonality : 'C Major');
    const newTonality = shiftTonalityKey(currentTonality, deltaSemitones);
    setSelectTonalityValue(newTonality);
    
    const currentChordText = els.editChord ? els.editChord.value : '';
    if (currentChordText.trim() !== '') {
        const transposedText = transposeChordStructure(currentChordText, deltaSemitones, newTonality);
        if (els.editChord) {
            els.editChord.value = transposedText;
        }
    }
    
    if (state.selectedLyrics && Array.isArray(state.selectedLyrics)) {
        state.selectedLyrics = transposeLyricsData(state.selectedLyrics, deltaSemitones, newTonality);
    }
    
    state.lastActiveTonality = newTonality;
    showToast(`Transpuesto ${deltaSemitones > 0 ? '+1' : '-1'} semitono a ${newTonality} 🎵`);
    refreshChordDiagrams();
    triggerLiveHarmonicAnalysis();
}

// Submit Edits back to LocalStorage cache and Google Sheets API through Flask
async function handleFormSubmission(e) {
    e.preventDefault();
    
    const rowNum = parseInt(els.editRow.value);
    if (!rowNum) return;
    
    const chordInput = els.editChord.value.trim();
    let tonalityInput = els.editTonality.value.trim();
    let progressionInput = els.editProgression.value.trim();
    let complexInput = els.editComplex.value;
    let styleInput = els.editStyle.value.trim();
    
    // Tactile Active Saving feedback Animation
    els.saveBtn.classList.add('active');
    els.saveBtn.disabled = true;
    els.saveBtn.querySelector('span').textContent = "Analizando y Guardando...";
    
    // If chords are provided, auto-generate all harmonic metadata (Tonalidad, Progresión, Complejidad, Estilo)
    if (chordInput) {
        try {
            const analyzeRes = await fetch('/api/analyze-chords', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    chord: chordInput,
                    tonality: tonalityInput
                })
            });
            if (analyzeRes.ok) {
                const analyzed = await analyzeRes.json();
                if (analyzed) {
                    tonalityInput = analyzed.tonality || tonalityInput;
                    progressionInput = analyzed.progression || progressionInput;
                    complexInput = analyzed.complex || complexInput;
                    styleInput = analyzed.style || styleInput;
                    
                    // Reflect in form inputs
                    setSelectTonalityValue(tonalityInput);
                    state.lastActiveTonality = tonalityInput;
                    els.editProgression.value = progressionInput;
                    els.editComplex.value = complexInput;
                    els.editStyle.value = styleInput;
                }
            }
        } catch (err) {
            console.warn("Error en auto-análisis de acordes:", err);
        }
    }
    
    // Keep the lyrics view in step with edited chords (only sections whose chord count lines up)
    if (chordInput && Array.isArray(state.selectedLyrics) && state.selectedLyrics.length) {
        const synced = resyncLyricsChords(state.selectedLyrics, chordInput);
        if (synced.updated > 0) state.selectedLyrics = synced.lyrics;
        if (synced.removed || synced.added) {
            showToast(`Letra sincronizada: ${synced.removed} acordes quitados, ${synced.added} añadidos`);
        } else if (synced.updated < synced.total) {
            showToast(`Letra: ${synced.updated} de ${synced.total} secciones actualizadas (el resto no coincide en nº de acordes)`, true);
        }
    }

    // Update scan timestamp to current moment
    const scanTime = state.pendingScanTime || new Date().toISOString();
    
    const updatedValues = {
        row: rowNum, artist: state.selectedSong?.artist, title: state.selectedSong?.title,
        chord: chordInput,
        tonality: tonalityInput,
        progression: progressionInput,
        complex: complexInput,
        style: styleInput,
        emotional: styleInput,
        skill: complexInput,
        lastScanDate: scanTime,
        lyricsWithChords: state.selectedLyrics || null
    };
    
    const songIndex = state.songs.findIndex(s => s.row === rowNum);
    
    // 1. Instantly update local client memory & UI (Optimistic UI update)
    if (songIndex !== -1) {
        state.songs[songIndex] = {
            ...state.songs[songIndex],
            ...updatedValues,
            // selectSong reads song.lyrics, so keep it in sync with the (possibly transposed) lyrics being saved
            lyrics: state.selectedLyrics || state.songs[songIndex].lyrics,
            liked: state.songs[songIndex].liked
        };
        
        // Cache immediately in LocalStorage
        try { localStorage.setItem('vibemus_songs_data', JSON.stringify(state.songs)); } catch(e) { console.warn('Cache quota exceeded'); }
        
        // Re-process metadata to update stats dynamically
        processSongsMetadata();
        
        // Update the DOM card in list
        updateSongCardInDOM(state.songs[songIndex]);
        
        // Update Focus Panel Visuals: Map, Progression, Badges, Color
        // Preserve lyrics when called from autodetect flow
        renderChordSheet(chordInput, state.selectedLyrics);
        els.focusProgressionText.textContent = progressionInput || '— Sin Progresión Numérica';
        els.focusProgressionChords.textContent = romanProgressionToChords(progressionInput, tonalityInput || state.selectedSong?.tonality) || '';
        renderProgressionDiagrams(document.getElementById('focus-progression-diagrams'), progressionInput, tonalityInput || state.selectedSong?.tonality);
        els.focusBadgeComplexity.textContent = chordInput ? (complexInput || 'Baja') : '—';
        els.focusBadgeStyle.textContent = styleInput || 'Sin Estilo';
        shiftVibeAccentColor(styleInput);
        updateSongCacheUI(state.songs[songIndex]);
        
        // Highlight active details view — use a flag to avoid resetting lyrics state
        const savedLyrics = state.selectedLyrics;
        const savedViewMode = state.chordViewMode;
        selectSong(state.songs[songIndex], false);
        // Restore lyrics that selectSong would have wiped
        state.selectedLyrics = savedLyrics;
        state.chordViewMode = savedViewMode;
        redrawChordViews(); // expanded modal / floating window, before waiting for the cloud
    }
    
    // 2. Async Cloud Sync via Flask
    try {
        setSyncingStatus(true);
        const response = await apiUpdateFetch('/api/update', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(updatedValues)
        });
        
        if (!response.ok) throw new Error("No se pudo guardar en la nube");
        
        showToast("¡Armonía analizada y guardada en Google Sheets! ✨");
    } catch (err) {
        console.warn("Cambios guardados localmente, pero falló la sincronización en la nube.", err);
        showToast("Guardado local (Fallo de red en la nube)", true);
    } finally {
        setSyncingStatus(false);
        els.saveBtn.classList.remove('active');
        els.saveBtn.disabled = false;
        els.saveBtn.querySelector('span').textContent = "Guardar Cambios en Google Sheets";
    }
}

// Delete all harmony details for the selected song in LocalStorage and Google Sheets, and update the scan cache date
async function handleDeleteHarmony() {
    if (!state.selectedSong) return;
    
    const song = state.selectedSong;
    const confirmMsg = `¿Estás seguro de que deseas borrar toda la armonía de la canción "${song.title}"?\n\nEsta acción limpiará los acordes, tonalidad y progresión tanto en local como en la nube de Google Sheets y actualizará la fecha del escaneo a la hora actual.`;
    if (!confirm(confirmMsg)) return;
    
    const scanTime = new Date().toISOString();
    const rowNum = song.row;
    const updatedValues = {
        row: rowNum, artist: state.selectedSong?.artist, title: state.selectedSong?.title,
        chord: '',
        tonality: '',
        progression: '',
        complex: '',
        style: '',
        lastScanDate: scanTime
    };
    
    // Animate delete button loading
    els.deleteHarmonyBtn.disabled = true;
    els.deleteHarmonyBtn.querySelector('span').textContent = "Borrando...";
    
    // 1. Update local client state
    const songIndex = state.songs.findIndex(s => s.row === rowNum);
    if (songIndex !== -1) {
        state.songs[songIndex] = {
            ...state.songs[songIndex],
            ...updatedValues,
            liked: state.songs[songIndex].liked
        };
        
        // Cache in LocalStorage
        try { localStorage.setItem('vibemus_songs_data', JSON.stringify(state.songs)); } catch(e) { console.warn('Cache quota exceeded'); }
        
        // Update song-level scan cache date to the current date/time
        let songCache = {};
        try {
            songCache = JSON.parse(localStorage.getItem('vibemus_song_scan_cache') || '{}');
            const songKey = `${song.artist} - ${song.title}`;
            songCache[songKey] = scanTime;
            localStorage.setItem('vibemus_song_scan_cache', JSON.stringify(songCache));
        } catch (e) {
            console.error(e);
        }
        
        // Refresh metadata and explorer
        processSongsMetadata();
        
        // Update the DOM card directly instead of refreshing the list
        updateSongCardInDOM(state.songs[songIndex]);
        
        // Select the song to refresh details view without redrawing list
        selectSong(state.songs[songIndex], false);
    }
    
    // 2. Cloud Sync via Flask
    try {
        setSyncingStatus(true);
        const response = await apiUpdateFetch('/api/update', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(updatedValues)
        });
        
        if (!response.ok) throw new Error("No se pudo sincronizar en la nube");
        
        showToast("¡Armonía borrada en la nube con éxito! 🗑️");
    } catch (err) {
        console.warn("Se borró localmente, pero falló la sincronización en la nube.", err);
        showToast("Borrado local (Offline en la nube)", true);
    } finally {
        setSyncingStatus(false);
        els.deleteHarmonyBtn.disabled = false;
        els.deleteHarmonyBtn.querySelector('span').textContent = "Borrar Armonía";
    }
}

// Toast notification helper
// POST /api/update with the song's current Video ID so the server finds the row even if rows moved.
function apiUpdateFetch(url, init) {
    try {
        const body = JSON.parse(init.body);
        const song = (state.songs || []).find(s => s.row === body.row && s.artist === body.artist && s.title === body.title);
        if (song && song.videoId && !('lookupVideoId' in body)) {
            init = { ...init, body: JSON.stringify({ ...body, lookupVideoId: song.videoId }) };
        }
    } catch (e) { /* send as is */ }
    return fetch(url, init);
}

function showToast(message, isWarning = false) {
    els.toastMessage.textContent = message;
    
    if (isWarning) {
        els.toast.style.backgroundColor = "#f59e0b"; // Warning orange
    } else {
        els.toast.style.backgroundColor = "#10b981"; // Success emerald
    }
    
    els.toast.classList.remove('hide');
    setTimeout(() => {
        els.toast.classList.add('hide');
    }, 3500);
}

// Fills the confirmation modal with a harmony suggestion (Ultimate Guitar, Songsterr or PDF) and opens it
function showHarmonySuggestion(data, scanTime) {
    // Save the suggestion in state, including the scan timestamp so
    // handleAcceptSuggestion can pass it through to the API correctly.
    state.currentSuggestion = { ...data, _scanTime: scanTime };
    
    // Show confirmation Modal
    els.suggestConfidence.textContent = `${Math.round(data.confidence * 100)}% Confianza`;
    const lyricsTag = d => (d.has_lyrics === undefined ? '' : d.has_lyrics ? ' · con letra' : ' · sin letra');
    els.suggestSource.textContent = data.source + lyricsTag(data);
    els.modalRegisteredSong.textContent = `${state.selectedSong.artist} - ${state.selectedSong.title}`;
    els.modalSuggestedSong.textContent = `${data.artist} - ${data.title}`;
    
    // Previews
    els.currentChordsPreview.textContent = state.selectedSong.chord && state.selectedSong.chord.trim() !== '' 
        ? state.selectedSong.chord 
        : '— Sin acordes —';
    els.suggestedChordsPreview.textContent = data.chord && data.chord.trim() !== ''
        ? data.chord
        : '— Sin acordes en el dataset —';

    const selectorContainer = document.getElementById('candidates-selector-container');
    const selectEl = document.getElementById('candidates-select');
    
    // Songsterr track selector
    const trackSelectorContainer = document.getElementById('songsterr-track-selector-container');
    const trackSelectEl = document.getElementById('songsterr-track-select');
    if (data.songsterr_tracks && data.songsterr_tracks.length > 1) {
        trackSelectorContainer.classList.remove('hide');
        trackSelectEl.innerHTML = '';
        data.songsterr_tracks.forEach((track, idx) => {
            const opt = document.createElement('option');
            opt.value = idx;
            let trackLabel = track.name || track.instrument;
            if (track.views) trackLabel += ` (${track.views.toLocaleString()} views)`;
            if (idx === 0) trackLabel += ' ★';
            opt.textContent = trackLabel;
            trackSelectEl.appendChild(opt);
        });
    } else {
        trackSelectorContainer.classList.add('hide');
    }

    if (data.candidates && data.candidates.length > 1) {
        selectorContainer.classList.remove('hide');
        selectEl.innerHTML = '';
        
        data.candidates.forEach((cand, index) => {
            const option = document.createElement('option');
            option.value = index;
            let label = `${cand.version_label || 'Versión ' + (index + 1)}`;
            if (cand.has_lyrics !== undefined) label += cand.has_lyrics ? ' · 📝 con letra' : ' · sin letra';
            if (cand.rating && cand.votes) label += ` · ⭐ ${cand.rating.toFixed(1)} (${cand.votes} votos)`;
            if (cand.tonality) label += ` · ${cand.tonality}`;
            if (index === 0) label += ' ★';
            option.textContent = label;
            selectEl.appendChild(option);
        });
        
        // Add event listener to update preview when changing candidate
        // Using an inline named function so it can be overwritten safely
        selectEl.onchange = (e) => {
            const selectedCand = data.candidates[e.target.value];
            state.currentSuggestion = { ...selectedCand, _scanTime: scanTime };
            els.suggestSource.textContent = selectedCand.source + lyricsTag(selectedCand);
            els.modalSuggestedSong.textContent = `${selectedCand.artist} - ${selectedCand.title}`;
            
            els.suggestedChordsPreview.textContent = selectedCand.chord && selectedCand.chord.trim() !== ''
                ? selectedCand.chord
                : '— Sin acordes en el dataset —';
        };
    } else {
        selectorContainer.classList.add('hide');
        selectEl.onchange = null;
        if (trackSelectorContainer) trackSelectorContainer.classList.add('hide');
    }
        
    els.confirmModal.classList.remove('hide');
}

// Autocomplete the harmony from a chord-sheet PDF picked by the user
async function handlePdfHarmony(file) {
    if (!state.selectedSong || !file) return;
    const btn = document.getElementById('pdf-harmony-btn');
    const label = btn ? btn.querySelector('span') : null;
    if (btn) { btn.disabled = true; if (label) label.textContent = 'Leyendo PDF...'; }
    try {
        const form = new FormData();
        form.append('file', file);
        form.append('artist', state.selectedSong.artist || '');
        form.append('title', state.selectedSong.title || '');
        const response = await fetch('/api/parse-pdf-harmony', { method: 'POST', body: form });
        const data = await response.json();
        if (data && data.found) {
            showHarmonySuggestion(data, new Date().toISOString());
        } else {
            showToast((data && (data.message || data.error)) || 'No se pudo leer el PDF', true);
        }
    } catch (err) {
        console.error('Fallo al importar el PDF:', err);
        showToast('Error de conexión con el servidor', true);
    } finally {
        if (btn) { btn.disabled = false; if (label) label.textContent = 'PDF'; }
    }
}

(function setupPdfHarmony() {
    const btn = document.getElementById('pdf-harmony-btn');
    const input = document.getElementById('pdf-harmony-input');
    if (!btn || !input) return;
    btn.addEventListener('click', () => {
        if (!state.selectedSong) { showToast('Selecciona una canción primero', true); return; }
        input.click();
    });
    input.addEventListener('change', () => {
        const file = input.files[0];
        input.value = ''; // so the same file can be picked again
        handlePdfHarmony(file);
    });
})();

// Stamp "last scanned" on a song: local state and UI first, then the sheet (one retry; warns if it never lands)
async function recordScanDate(song, scanTime) {
    const idx = state.songs.findIndex(s => s.row === song.row);
    if (idx !== -1) {
        state.songs[idx].lastScanDate = scanTime;
        try { localStorage.setItem('vibemus_songs_data', JSON.stringify(state.songs)); } catch (e) { console.warn('Cache quota exceeded'); }
        updateSongCardInDOM(state.songs[idx]);
        updateSongCacheUI(state.songs[idx]);
        if (state.activeFilters.playlist && state.activeFilters.playlist !== 'all') updatePlaylistCacheUI(state.activeFilters.playlist);
    }
    for (let attempt = 0; attempt < 2; attempt++) {
        try {
            const res = await apiUpdateFetch('/api/update', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ row: song.row, artist: song.artist, title: song.title, lastScanDate: scanTime })
            });
            if (res.ok) return true;
        } catch (e) { /* retry */ }
        await new Promise(r => setTimeout(r, 1000));
    }
    showToast(`No se pudo guardar la fecha de escaneo de "${song.title}" en Google Sheets`, true);
    return false;
}

// Autodetect Harmony from Chordonomicon via Flask API
async function handleAutodetect() {
    if (!state.selectedSong) return;
    
    const artist = state.selectedSong.artist;
    const title = state.selectedSong.title;
    
    // Animate button loading state
    els.autodetectBtn.disabled = true;
    els.autodetectBtn.querySelector('span').textContent = "Buscando...";
    els.autodetectBtn.classList.add('active');
    
    // The song counts as scanned the moment the button is pressed, whatever the search finds or the user decides
    const scanTime = new Date().toISOString();
    const scanSaved = recordScanDate(state.selectedSong, scanTime);
    
    try {
        const response = await fetch('/api/suggest-harmony', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                artist: artist,
                title: title,
                source: state.selectedSource || 'Ultimate Guitar'
            })
        });
        
        if (!response.ok) throw new Error("Error en la llamada de autocompletado");
        
        const data = await response.json();
        
        await scanSaved; // the stamp is already on its way; make sure it landed before moving on
        
        if (data && data.found) {
            showHarmonySuggestion(data, scanTime);
        } else {
            showToast(`No se encontraron coincidencias en ${state.selectedSource || 'Ultimate Guitar'}.`, true);
            
            // Automatically jump to the next song since there is no harmony to check/verify here
            setTimeout(() => {
                selectNextSong();
            }, 1200);
        }
    } catch (err) {
        console.error("Fallo al buscar autodetectar:", err);
        showToast("Error de conexión con el servidor", true);
    } finally {
        els.autodetectBtn.disabled = false;
        els.autodetectBtn.querySelector('span').textContent = "Autocompletar Armonía";
        els.autodetectBtn.classList.remove('active');
    }
}

async function handleAcceptSuggestion() {
    if (!state.currentSuggestion || !state.selectedSong) return;

    const data = state.currentSuggestion;
    const song = state.selectedSong;
    els.confirmModal.classList.add('hide');

    // Recover the scan timestamp set when autodetect ran (fallback to now).
    const scanTime = data._scanTime || new Date().toISOString();

    // ── Build the final values to save ───────────────────────────────────────
    // Use the values from the suggestion directly — do not rely on form field
    // DOM state which can be stale or mismatched.
    const chord      = (data.chord      || '').trim();
    const tonality   = (data.tonality   || '').trim();
    const progression= (data.progression|| '').trim();
    const complex    = (data.complex    || 'Baja');
    const style      = (data.style      || '').trim();

    const updatedValues = {
        row: song.row, artist: song.artist, title: song.title,
        chord,
        tonality,
        progression,
        complex,
        style,
        emotional: style,
        skill: complex,
        lastScanDate: scanTime
    };
    if (data.bpm) updatedValues.bpm = data.bpm; // e.g. "BPM 87" printed on an imported PDF

    // A saved improvisation guide describes the old harmony: drop it when the new one differs, so it gets regenerated
    const sameText = (a, b) => String(a || '').replace(/\s+/g, ' ').trim() === String(b || '').replace(/\s+/g, ' ').trim();
    const harmonyChanged = !sameText(song.chord, chord) || !sameText(song.tonality, tonality) || !sameText(song.progression, progression);
    const guideCleared = harmonyChanged && !!(song.improvisation && song.improvisation.trim());
    if (guideCleared) updatedValues.improvisation = '';

    // ── 1. Update local state immediately ────────────────────────────────────
    const songIdx = state.songs.findIndex(s => s.row === song.row);
    if (songIdx !== -1) {
        state.songs[songIdx] = {
            ...state.songs[songIdx],
            ...updatedValues,
            liked: state.songs[songIdx].liked
        };
        try { localStorage.setItem('vibemus_songs_data', JSON.stringify(state.songs)); } catch(e) { console.warn('Cache quota exceeded'); }

        // Update song-level scan cache
        try {
            const cacheKey = `${song.artist} - ${song.title}`;
            const songCache = JSON.parse(localStorage.getItem('vibemus_song_scan_cache') || '{}');
            songCache[cacheKey] = scanTime;
            localStorage.setItem('vibemus_song_scan_cache', JSON.stringify(songCache));
        } catch (e) { /* non-critical */ }
    }

    // ── 2. Store lyrics for the chord sheet view ─────────────────────────────
    // Filter prose-only sections and validate density before storing
    const cleanedLyrics = _filterAndValidateLyrics(data.lyrics_with_chords);
    if (cleanedLyrics) {
        state.selectedLyrics = cleanedLyrics;
        state.chordViewMode = 'lyrics';
        // Persist cleaned (prose-stripped) lyrics in local song state
        if (songIdx !== -1) {
            state.songs[songIdx].lyrics = cleanedLyrics;
            try { localStorage.setItem('vibemus_songs_data', JSON.stringify(state.songs)); } catch(e) { console.warn('Cache quota exceeded'); }
        }
    } else {
        state.selectedLyrics = null;
        state.chordViewMode = 'diagrams';
        // Clear any previously stored invalid lyrics
        if (songIdx !== -1 && state.songs[songIdx].lyrics) {
            state.songs[songIdx].lyrics = null;
            try { localStorage.setItem('vibemus_songs_data', JSON.stringify(state.songs)); } catch(e) { console.warn('Cache quota exceeded'); }
        }
    }

    // ── 3. Update the UI ──────────────────────────────────────────────────────
    processSongsMetadata();
    if (songIdx !== -1) {
        updateSongCardInDOM(state.songs[songIdx]);
        updateSongCacheUI(state.songs[songIdx]);
    }

    // Only update the focus panel (right side) if the user is still looking at this song!
    // If they clicked the next song while the fetch was pending, we shouldn't overwrite the panel.
    const isStillSelected = state.selectedSong && state.selectedSong.row === song.row;
    
    if (isStillSelected) {
        // Sync form fields so they show correct data
        setSelectTonalityValue(tonality);
        state.lastActiveTonality = tonality;
        els.editChord.value      = chord;
        els.editComplex.value    = complex;
        els.editStyle.value      = style;
        els.editProgression.value= progression;

        // Render chord sheet (with lyrics if available)
        renderChordSheet(chord, state.selectedLyrics);
        els.focusProgressionText.textContent = progression || '— Sin Progresión Numérica';
        els.focusProgressionChords.textContent = romanProgressionToChords(progression, tonality) || '';
        renderProgressionDiagrams(document.getElementById('focus-progression-diagrams'), progression, tonality);
        els.focusBadgeComplexity.textContent = chord ? (complex || 'Baja') : '—';
        els.focusBadgeStyle.textContent      = style || 'Sin Estilo';
        shiftVibeAccentColor(style);
        if (songIdx !== -1) renderImprovisationGuide(state.songs[songIdx]);
    }

    // ── 4. Save to Google Sheets via API ─────────────────────────────────────
    try {
        setSyncingStatus(true);
        const response = await apiUpdateFetch('/api/update', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                ...updatedValues,
                lyricsWithChords: state.selectedLyrics || null
            })
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        showToast(guideCleared
            ? '¡Armonía guardada! La guía de improvisación anterior se borró: vuelve a generarla ✨'
            : '¡Armonía autocompletada y guardada en Google Sheets! ✨');
    } catch (err) {
        console.error('Error al guardar armonía autocompletada:', err);
        showToast('Guardado local (fallo de red en la nube)', true);
    } finally {
        setSyncingStatus(false);
    }

    // ── 5. Update selected song reference ────────────────────────────────────
    if (songIdx !== -1 && state.selectedSong && state.selectedSong.row === song.row) {
        state.selectedSong = state.songs[songIdx];
    }

    state.currentSuggestion = null;
}



// Autocomplete the missing harmony for all songs in the currently selected playlist with a song-level caching layer
async function handleAutocompletePlaylist() {
    const selectedPlaylist = state.activeFilters.playlist;
    if (!selectedPlaylist || selectedPlaylist === 'all') return;
    
    // Get global song-level scan cache
    let songCache = {};
    try {
        songCache = JSON.parse(localStorage.getItem('vibemus_song_scan_cache') || '{}');
    } catch (e) {
        console.error("Error al leer la caché de escaneo:", e);
    }

    // Find songs in this playlist where tonality is missing
    const allMissingSongs = state.songs.filter(song => {
        return song.playlist === selectedPlaylist && (!song.tonality || song.tonality.trim() === '');
    });
    
    if (allMissingSongs.length === 0) {
        showToast("Todas las canciones de esta playlist ya tienen tonalidad. ✨");
        return;
    }
    
    // Filter out cached songs (previously checked songs during the scans)
    const songsToProcess = allMissingSongs.filter(song => {
        const key = `${song.artist} - ${song.title}`;
        return !(song.lastScanDate || songCache[key]);
    });
    
    const skippedCount = allMissingSongs.length - songsToProcess.length;
    
    if (songsToProcess.length === 0) {
        const resetConfirm = confirm(`Todas las ${allMissingSongs.length} canciones sin armonía ya fueron buscadas recientemente.\n\n¿Deseas reiniciar la caché de estas canciones para volver a buscarlas todas?`);
        if (resetConfirm) {
            // Clear song cache for all missing songs in this playlist
            allMissingSongs.forEach(song => {
                const key = `${song.artist} - ${song.title}`;
                delete songCache[key];
            });
            localStorage.setItem('vibemus_song_scan_cache', JSON.stringify(songCache));
            showToast("Caché de la playlist reiniciada. 🔄");
            
            // Re-run the autocomplete process automatically
            handleAutocompletePlaylist();
        }
        return;
    }
    
    // Ask for confirmation
    let confirmMsg = `Se procesarán ${songsToProcess.length} canciones sin armonía de la playlist "${selectedPlaylist}" usando Ultimate Guitar.`;
    if (skippedCount > 0) {
        confirmMsg += `\n\n(${skippedCount} canciones se omitirán porque ya fueron escaneadas recientemente).`;
    }
    confirmMsg += `\n\nEl proceso tardará aprox. ${(songsToProcess.length * 5.5 / 60).toFixed(1)} minutos con intervalos de seguridad.\n\n¿Deseas iniciar la ejecución?`;
    
    if (!confirm(confirmMsg)) return;
    
    // Disable UI controls
    els.autocompletePlaylistBtn.disabled = true;
    els.filterPlaylist.disabled = true;
    if (els.resetPlaylistCacheBtn) els.resetPlaylistCacheBtn.disabled = true;
    if (els.resetSongCacheBtn) els.resetSongCacheBtn.disabled = true;
    const originalBtnHTML = els.autocompletePlaylistBtn.innerHTML;
    
    showToast(`Iniciando autocompletado de ${songsToProcess.length} canciones... 🚀`);
    
    let updatedCount = 0;
    let failedWrites = 0;
    const scanTime = new Date().toISOString();
    const updatedSongRows = []; // Track recently found song rows
    
    for (let i = 0; i < songsToProcess.length; i++) {
        const song = songsToProcess[i];
        const songKey = `${song.artist} - ${song.title}`;
        let updatedInCloud = false;
        
        // Update progress in the button
        els.autocompletePlaylistBtn.innerHTML = `<i class="ph ph-circle-notch animate-spin"></i> <span>Procesando ${i + 1}/${songsToProcess.length}...</span>`;
        
        try {
            // Call API suggest-harmony with Ultimate Guitar
            const response = await fetch('/api/suggest-harmony', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    artist: song.artist,
                    title: song.title,
                    source: state.selectedSource || 'Ultimate Guitar'
                })
            });
            
            // Mark as checked in the global song cache (whether found or not)
            songCache[songKey] = scanTime;
            localStorage.setItem('vibemus_song_scan_cache', JSON.stringify(songCache));
            
            if (response.ok) {
                const data = await response.json();
                if (data && data.found) {
                    // Safety check: for bulk playlist autocomplete, accept exact match or normalized match (&/and, accents, punctuation)
                    const normalizeForCheck = (str) => {
                        if (!str) return '';
                        return str
                            .normalize('NFD')
                            .replace(/[\u0300-\u036f]/g, '')
                            .replace(/\s*&\s*/g, ' and ')
                            .replace(/\s*\+\s*/g, ' and ')
                            .replace(/['"’`´]/g, '')
                            .replace(/[^a-zA-Z0-9]/g, '')
                            .toLowerCase();
                    };
                    const normDataArtist = normalizeForCheck(data.artist);
                    const normSongArtist = normalizeForCheck(song.artist);
                    const normDataTitle = normalizeForCheck(data.title);
                    const normSongTitle = normalizeForCheck(song.title);

                    const exactArtist = normDataArtist === normSongArtist || normDataArtist.includes(normSongArtist) || normSongArtist.includes(normDataArtist);
                    const exactTitle = normDataTitle === normSongTitle || normDataTitle.includes(normSongTitle) || normSongTitle.includes(normDataTitle);
                    
                    if (exactArtist && exactTitle) {
                        const cleanedLyrics = _filterAndValidateLyrics(data.lyrics_with_chords);
                        const finalLyrics = cleanedLyrics || song.lyrics || null;
                        const updatedValues = {
                            row: song.row, artist: song.artist, title: song.title,
                            chord: (data.chord || '').trim(),
                            tonality: (data.tonality || '').trim(),
                            progression: (data.progression || '').trim(),
                            complex: data.complex || 'Baja',
                            style: (data.style || '').trim(),
                            emotional: (data.style || '').trim(),
                            skill: data.complex || 'Baja',
                            lastScanDate: scanTime,
                            lyricsWithChords: finalLyrics
                        };
                        
                        // Update locally
                        const songIndex = state.songs.findIndex(s => s.row === song.row);
                        if (songIndex !== -1) {
                            state.songs[songIndex] = {
                                ...state.songs[songIndex],
                                ...updatedValues
                            };
                        }
                        
                        // Call update API to save in cloud
                        const saveRes = await apiUpdateFetch('/api/update', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify(updatedValues)
                        });
                        if (!saveRes.ok) failedWrites++;
                        
                        updatedInCloud = true;
                        updatedCount++;
                        updatedSongRows.push(song.row);
                    } else {
                        console.log(`[Batch Sync] Omitiendo coincidencia inexacta para "${song.artist} - ${song.title}" (Encontrado: "${data.artist} - ${data.title}")`);
                    }
                }
                
                // If not updated (either not found or non-exact match), save at least the scan date to the server
                if (!updatedInCloud) {
                    const songIndex = state.songs.findIndex(s => s.row === song.row);
                    if (songIndex !== -1) {
                        state.songs[songIndex].lastScanDate = scanTime;
                    }
                    const dateRes = await apiUpdateFetch('/api/update', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ row: song.row, artist: song.artist, title: song.title, lastScanDate: scanTime })
                    });
                    if (!dateRes.ok) failedWrites++;
                }
            }
        } catch (err) {
            console.error(`Error procesando ${song.artist} - ${song.title}:`, err);
            failedWrites++;
        }
        
        // Polite randomized delay of 4 to 7 seconds to prevent Cloudflare/Ultimate Guitar rate-limiting
        if (i < songsToProcess.length - 1) {
            const randomDelay = 4000 + Math.random() * 3000;
            await new Promise(resolve => setTimeout(resolve, randomDelay));
        }
    }
    
    if (failedWrites > 0) showToast(`${failedWrites} guardados en Google Sheets fallaron: esas canciones no se marcaron como escaneadas`, true);

    // Complete! Restore UI
    els.autocompletePlaylistBtn.disabled = false;
    els.filterPlaylist.disabled = false;
    if (els.resetPlaylistCacheBtn) els.resetPlaylistCacheBtn.disabled = false;
    if (els.resetSongCacheBtn) els.resetSongCacheBtn.disabled = false;
    els.autocompletePlaylistBtn.innerHTML = originalBtnHTML;
    
    // Refresh stats and catalog
    try { localStorage.setItem('vibemus_songs_data', JSON.stringify(state.songs)); } catch(e) { console.warn('Cache quota exceeded'); }
    processSongsMetadata();
    
    // If any songs were updated, filter list to show only those songs
    if (updatedSongRows.length > 0) {
        state.justFoundRows = updatedSongRows;
        state.activeFilters.justFound = true;
        
        if (els.justFoundCount) {
            els.justFoundCount.textContent = updatedSongRows.length;
        }
        if (els.justFoundBanner) {
            els.justFoundBanner.classList.remove('hide');
        }
    } else {
        state.activeFilters.justFound = false;
        state.justFoundRows = [];
        if (els.justFoundBanner) {
            els.justFoundBanner.classList.add('hide');
        }
    }
    
    applyFiltersAndRender();
    
    if (state.selectedSong) {
        updateSongCacheUI(state.selectedSong);
    }
    updatePlaylistCacheUI(selectedPlaylist);
    
    if (updatedSongRows.length > 0) {
        showToast(`¡Completado! Se encontraron ${updatedCount} canciones. Se ha aplicado el filtro para comprobarlas. ✨`);
    } else {
        showToast(`Búsqueda completada. No se encontraron nuevas armonías coincidentes exactas. ✨`);
    }
}

// Recover recently scanned and found songs in the last 30 minutes
function recoverRecentlyFoundSongs() {
    try {
        const songCache = JSON.parse(localStorage.getItem('vibemus_song_scan_cache') || '{}');
        const now = new Date().getTime();
        const recentRows = [];
        
        state.songs.forEach(song => {
            const key = `${song.artist} - ${song.title}`;
            const scanTimeStr = songCache[key];
            if (scanTimeStr) {
                const scanTime = new Date(scanTimeStr).getTime();
                const hasHarmony = song.chord && song.chord.trim() !== '';
                // Scanned in the last 30 minutes and has harmony
                if (hasHarmony && (now - scanTime < 30 * 60 * 1000)) {
                    recentRows.push(song.row);
                }
            }
        });
        
        if (recentRows.length > 0) {
            state.justFoundRows = recentRows;
            state.activeFilters.justFound = true;
            if (els.justFoundCount) els.justFoundCount.textContent = recentRows.length;
            if (els.justFoundBanner) els.justFoundBanner.classList.remove('hide');
        } else {
            state.activeFilters.justFound = false;
            state.justFoundRows = [];
            if (els.justFoundBanner) {
                els.justFoundBanner.classList.add('hide');
            }
        }
        applyFiltersAndRender();
    } catch (e) {
        console.error("Error al recuperar escaneos recientes:", e);
    }
}

// Format ISO string date to human readable localized string
function formatCacheDate(isoString) {
    if (!isoString) return 'Nunca';
    try {
        const date = new Date(isoString);
        return date.toLocaleString('es-ES', {
            day: '2-digit',
            month: 'short',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
    } catch (e) {
        return '—';
    }
}

// Reset cache for a specific playlist (clears cache for all songs in that playlist)
function resetPlaylistCache(playlistName) {
    if (!playlistName || playlistName === 'all') return;
    
    let songCache = {};
    try {
        songCache = JSON.parse(localStorage.getItem('vibemus_song_scan_cache') || '{}');
    } catch (e) {}
    
    // Find all songs in this playlist and remove them from song cache
    state.songs.forEach(song => {
        if (song.playlist === playlistName) {
            const key = `${song.artist} - ${song.title}`;
            if (songCache[key]) {
                delete songCache[key];
            }
        }
    });
    
    localStorage.setItem('vibemus_song_scan_cache', JSON.stringify(songCache));
    
    // Also remove from old playlist cache
    let playlistCache = {};
    try {
        playlistCache = JSON.parse(localStorage.getItem('vibemus_playlist_cache') || '{}');
        if (playlistCache[playlistName]) {
            delete playlistCache[playlistName];
            localStorage.setItem('vibemus_playlist_cache', JSON.stringify(playlistCache));
        }
    } catch (e) {}
    
    updatePlaylistCacheUI(playlistName);
    if (state.selectedSong && state.selectedSong.playlist === playlistName) {
        updateSongCacheUI(state.selectedSong);
    }
    showToast(`Caché de la playlist "${playlistName}" reiniciada. 🔄`);
}

// Update playlist cache status UI based on song-level cache
function updatePlaylistCacheUI(playlistName) {
    if (!playlistName || playlistName === 'all') {
        els.playlistCacheInfo.classList.add('hide');
        return;
    }
    
    let latestScan = null;
    let cachedCount = 0;
    
    state.songs.forEach(song => {
        if (song.playlist === playlistName) {
            const time = song.lastScanDate;
            if (time && time.trim() !== '') {
                cachedCount++;
                if (!latestScan || new Date(time) > new Date(latestScan)) {
                    latestScan = time;
                }
            }
        }
    });
    
    if (latestScan) {
        els.cacheTimeLabel.textContent = `Caché: ${cachedCount} escaneos (Último: ${formatCacheDate(latestScan)})`;
        els.playlistCacheInfo.classList.remove('hide');
    } else {
        els.cacheTimeLabel.textContent = `Último escaneo: Nunca`;
        els.playlistCacheInfo.classList.remove('hide');
    }
}

// Auto-initialize song scan cache based on pre-existing completed song data (e.g. yesterday's scan)
// DEPRECATED: We now use /api/init-scan-dates on the server to authoritatively set missing dates to today.
// This client-side logic is disabled to prevent it from injecting incorrect "yesterday" dates.
function initializeCacheFromExistingData() {
    return;
}

// Update UI of the song-specific cache information in the Focus Panel
function updateSongCacheUI(song) {
    if (!song || !els.songCacheContainer) return;
    
    const scanTime = song.lastScanDate;
    
    if (scanTime && scanTime.trim() !== '') {
        els.songCacheLabel.textContent = `Último escaneo: ${formatCacheDate(scanTime)}`;
        els.songCacheContainer.classList.remove('hide');
    } else {
        els.songCacheLabel.textContent = `Último escaneo: Nunca`;
        els.songCacheContainer.classList.remove('hide');
    }
}

// Reset scan cache for a single specific song
function resetSongCache(song) {
    if (!song) return;
    
    let songCache = {};
    try {
        songCache = JSON.parse(localStorage.getItem('vibemus_song_scan_cache') || '{}');
    } catch (e) {
        songCache = {};
    }
    
    const key = `${song.artist} - ${song.title}`;
    if (songCache[key]) {
        delete songCache[key];
        localStorage.setItem('vibemus_song_scan_cache', JSON.stringify(songCache));
    }
    
    updateSongCacheUI(song);
    showToast(`Caché de "${song.title}" reiniciada. 🔄`);
}

// Helper to remove a single song from cache on manual updates
function clearSongFromCache(artist, title) {
    let songCache = {};
    try {
        songCache = JSON.parse(localStorage.getItem('vibemus_song_scan_cache') || '{}');
        const key = `${artist} - ${title}`;
        if (songCache[key]) {
            delete songCache[key];
            localStorage.setItem('vibemus_song_scan_cache', JSON.stringify(songCache));
        }
    } catch (e) {}
}

// Automatically select the next song in the currently filtered list (enables fast bulk-tagging)
function selectNextSong() {
    if (!state.selectedSong || state.filteredSongs.length === 0) return;
    
    // Find the index of the currently selected song in the filtered list
    const currentIndex = state.filteredSongs.findIndex(s => s.row === state.selectedSong.row || 
        (s.title === state.selectedSong.title && s.artist === state.selectedSong.artist));
    
    if (currentIndex !== -1 && currentIndex < state.filteredSongs.length - 1) {
        // Select the next song in the list
        const nextSong = state.filteredSongs[currentIndex + 1];
        selectSong(nextSong);

        // Scroll the newly selected row into view inside the songs list container
        requestAnimationFrame(() => {
            const selectedRow = document.querySelector(`.song-row[data-row-num="${nextSong.row}"]`);
            if (selectedRow) {
                const container = document.querySelector('.songs-list-container');
                if (container) {
                    const containerRect = container.getBoundingClientRect();
                    const rowRect = selectedRow.getBoundingClientRect();
                    const scrollOffset = rowRect.top - containerRect.top + container.scrollTop - (containerRect.height / 2) + (rowRect.height / 2);
                    
                    container.scrollTo({
                        top: scrollOffset,
                        behavior: 'smooth'
                    });
                }
            }
        });
    } else {
        // No more songs or last song, close the focus panel elegantly
        state.selectedSong = null;
        document.querySelector('.workspace-grid').classList.remove('focus-active');
        els.harmonyFocusPanel.classList.add('hide');
        els.harmonyEmptyPanel.classList.remove('hide');
        setCSSAccent('default');
        applyFiltersAndRender();
        showToast("¡Has completado toda la lista de reproducción! 🎉");
    }
}

// Directly updates a single song row in the DOM to avoid re-filtering or moving elements while editing/scanning
function updateSongCardInDOM(song) {
    if (!song) return;
    const card = document.querySelector(`[data-row-num="${song.row}"]`);
    if (!card) return;
    
    let songCache = {};
    try {
        songCache = JSON.parse(localStorage.getItem('vibemus_song_scan_cache') || '{}');
    } catch (e) {}
    
    const hasHarmony = song.chord && song.chord.trim() !== '';
    let compBadgeClass = 'badge-none';
    let compText = '—';
    if (hasHarmony) {
        compText = song.skill || song.complex || 'Baja';
        if (compText === 'Media') compBadgeClass = 'badge-mid';
        else if (compText === 'Media-Alta' || compText === 'Alta') compBadgeClass = 'badge-high';
        else compBadgeClass = 'badge-low';
    }
    
    const key = `${song.artist} - ${song.title}`;
    const scanTime = song.lastScanDate || songCache[key];
    let scanDisplay = '';
    if (scanTime) {
        const formatted = formatCacheDate(scanTime);
        scanDisplay = `<div class="song-row-scan-date" style="font-size: 10px; color: var(--text-tertiary); margin-top: 4px; display: flex; align-items: center; gap: 4px;"><i class="ph ph-calendar"></i> Escaneado: ${formatted}</div>`;
    } else {
        scanDisplay = `<div class="song-row-scan-date" style="font-size: 10px; color: var(--text-tertiary); margin-top: 4px; display: flex; align-items: center; gap: 4px; opacity: 0.5;"><i class="ph ph-calendar-blank"></i> Nunca escaneado</div>`;
    }
    
    // Find index in filtered list to maintain index label
    const idx = state.filteredSongs.findIndex(s => s.row === song.row);
    const indexLabel = idx !== -1 ? `#${idx + 1}` : '';
    
    card.innerHTML = `
        <div class="song-row-index font-mono">${indexLabel}</div>
        <div class="song-row-info">
            <div class="song-row-title">${song.title || 'Desconocido'}</div>
            <div class="song-row-artist">${song.artist || 'Desconocido'}</div>
            ${scanDisplay}
        </div>
        <div class="song-row-album">${song.album || '—'}</div>
        <div class="song-row-tonality font-mono">${song.tonality || '—'}</div>
        <div class="song-row-badge ${compBadgeClass}">${compText}</div>
        <div class="song-row-like ${song.liked ? 'liked' : ''}"><i class="${song.liked ? 'ph-fill' : 'ph'} ph-heart"></i></div>
    `;
    
    // Maintain selection highlight
    if (state.selectedSong && state.selectedSong.row === song.row) {
        card.classList.add('selected');
    } else {
        card.classList.remove('selected');
    }
}


// ── GLOBAL PANEL COLLAPSE LOGIC ────────────────────────────────────────────────
function initPanelCollapseLogic() {
    document.querySelectorAll('.panel-toggle-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const panel = e.target.closest('.double-bezel, .collapsible-panel');
            if (!panel) return;
            
            const isCollapsed = panel.classList.toggle('panel-collapsed');
            const icon = btn.querySelector('i');
            
            if (isCollapsed) {
                if (icon) {
                    icon.classList.remove('ph-caret-up');
                    icon.classList.add('ph-caret-down');
                }
                btn.setAttribute('title', 'Mostrar Panel');
                btn.setAttribute('aria-label', 'Mostrar Panel');
            } else {
                if (icon) {
                    icon.classList.remove('ph-caret-down');
                    icon.classList.add('ph-caret-up');
                }
                btn.setAttribute('title', 'Ocultar Panel');
                btn.setAttribute('aria-label', 'Ocultar Panel');
            }
        });
    });
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initPanelCollapseLogic);
} else {
    initPanelCollapseLogic();
}


function renderImprovisationGuide(song) {
    if (!els.generateImprovBtn) return;
    if (song.improvisation && song.improvisation.trim() !== '') {
        els.generateImprovBtn.innerHTML = '<i class="ph ph-sparkle"></i><span>Ver Guía de Improvisación</span>';
        els.generateImprovBtn.title = "Abrir Guía de Improvisación maximizada";
    } else {
        els.generateImprovBtn.innerHTML = '<i class="ph ph-sparkle"></i><span>Generar Guía (IA)</span>';
        els.generateImprovBtn.title = "Generar análisis modal e improvisación con IA";
    }
}

function openImprovisationModal(song) {
    if (!song || !song.improvisation) return;
    
    if (els.expandedImprovTitle) {
        els.expandedImprovTitle.textContent = `${song.artist} - ${song.title}`;
        els.expandedImprovTitle.title = 'Abrir los acordes en una ventana flotante';
        els.expandedImprovTitle.style.cssText += 'cursor: pointer; text-decoration: underline dotted; text-underline-offset: 3px;';
    }
    if (!document.getElementById('chord-float-popup').classList.contains('hide')) {
        openChordFloat(song);
    }
    if (els.expandedImprovTonality) {
        els.expandedImprovTonality.textContent = song.tonality || '—';
    }
    if (els.expandedImprovProgression) {
        els.expandedImprovProgression.textContent = song.progression || '—';
    }
    const expandedImprovProgressionChords = document.getElementById('expanded-improv-progression-chords');
    if (expandedImprovProgressionChords) {
        expandedImprovProgressionChords.textContent = romanProgressionToChords(song.progression, song.tonality) || '—';
    }
    
    // Render mini fretboard diagrams in Improv modal
    const improvDiagramsContainer = document.getElementById('expanded-improv-progression-diagrams');
    if (improvDiagramsContainer) {
        renderProgressionDiagrams(improvDiagramsContainer, song.progression, song.tonality);
    }
    
    if (els.expandedImprovStyle) {
        els.expandedImprovStyle.textContent = song.emotional || song.style || '—';
    }
    if (els.expandedImprovContent) {
        els.expandedImprovContent.innerHTML = marked.parse(window.stripLatex ? window.stripLatex(song.improvisation) : song.improvisation);
    }
    
    // Initialize & render Interactive Guitar Fretboard & Modal Fusion
    const fbContainer = document.getElementById('improvisation-fretboard-container');
    if (fbContainer && window.GuitarFretboard) {
        window.GuitarFretboard.setupSong(fbContainer, song);
    }

    if (els.expandImprovModal) {
        els.expandImprovModal.classList.remove('hide');
    }
}

// Chord/lyrics sheet shown by the "Expandir" modal and by the floating chord window
function renderExpandedChordSheet(container, song) {
    container.innerHTML = '';
    // Same source as the key used to spell them (the editor holds unsaved transpositions)
    const chordString = (els.editChord && els.editChord.value.trim()) || song.chord || '';
    const lyricsData = state.selectedLyrics;

    const hasLyrics = !!(lyricsData && lyricsData.length > 0);
    const hasChords = !!(chordString && chordString.trim() !== '');

    if (!hasChords && !hasLyrics) {
        container.innerHTML = `<div class="empty-state font-sans" style="color: var(--text-tertiary); text-align: center;">Sin acordes estructurados cargados. Añádelos abajo para verlos y reproducirlos.</div>`;
    } else if (hasLyrics && (!hasChords || state.chordViewMode === 'lyrics')) {
        _renderLyricsSheet(container, lyricsData);
    } else {
        _renderDiagramSheet(container, chordString);
    }
}

// Floating chord window: draggable and non-modal, so the chords stay visible while using the guide
function openChordFloat(song) {
    const popup = document.getElementById('chord-float-popup');
    if (!popup || !song) return;
    document.getElementById('chord-float-title').lastChild.textContent = ` ${song.artist} - ${song.title}`;
    renderProgressionDiagrams(document.getElementById('chord-float-diagrams'), song.progression, song.tonality);
    renderExpandedChordSheet(document.getElementById('chord-float-content'), song);
    popup.classList.remove('hide');
}

function closeChordFloat() {
    const popup = document.getElementById('chord-float-popup');
    if (popup) popup.classList.add('hide');
    const content = document.getElementById('chord-float-content');
    if (content) content.innerHTML = ''; // avoid duplicate audio listeners from stale chips
}

// Swap a video that won't play for another version of the song and save it in the sheet
const triedVideos = {}; // row -> ids already tried this session, so each press moves on to a new one
async function findAlternativeVideo() {
    const song = state.selectedSong;
    if (!song) return;
    const btn = document.getElementById('youtube-alt-btn');
    const label = btn ? btn.querySelector('span') : null;
    const tried = triedVideos[song.row] || (triedVideos[song.row] = []);
    const previousVideoId = song.videoId;
    if (song.videoId && !tried.includes(song.videoId)) tried.push(song.videoId);
    if (btn) { btn.disabled = true; if (label) label.textContent = 'Buscando...'; }
    try {
        const res = await fetch(`/api/alternative-video?artist=${encodeURIComponent(song.artist)}&title=${encodeURIComponent(song.title)}&exclude=${encodeURIComponent(tried.join(','))}`);
        const data = await res.json();
        if (!data.videoId) {
            showToast(data.message || 'No se encontró otro vídeo', true);
            return;
        }
        tried.push(data.videoId);
        song.videoId = data.videoId;
        const idx = state.songs.findIndex(s => s.row === song.row);
        if (idx !== -1) {
            state.songs[idx].videoId = data.videoId;
            try { localStorage.setItem('vibemus_songs_data', JSON.stringify(state.songs)); } catch (e) { console.warn('Cache quota exceeded'); }
        }
        loadYouTubeEmbed(data.videoId);
        showToast(`Vídeo cambiado: ${data.channel} · ${data.title}`);
        try {
            await updateGoogleSheetField(song, 'videoId', data.videoId);
        } catch (err) {
            console.warn('No se pudo guardar el vídeo en la hoja:', err);
            showToast('Vídeo cambiado, pero no se pudo guardar en la hoja', true);
        }
        await syncPlaylistVideo(previousVideoId, data.videoId, song.playlist);
    } catch (err) {
        console.error('Fallo al buscar vídeo alternativo:', err);
        showToast('Error de conexión con el servidor', true);
    } finally {
        if (btn) { btn.disabled = false; if (label) label.textContent = 'Probar otro vídeo'; }
    }
}

// Mirror the swap in the YouTube Music playlist that holds the old video (needs a one-time Google authorization)
async function syncPlaylistVideo(oldVideoId, newVideoId, playlistName, retried = false) {
    if (!oldVideoId || !newVideoId) return;
    return postPlaylistSync('/api/replace-playlist-video', { oldVideoId, newVideoId, playlist: playlistName || '' },
        () => syncPlaylistVideo(oldVideoId, newVideoId, playlistName, true), retried);
}

// Puts the song's current video in the playlist entry for it, whatever video that entry has now
function syncPlaylistToCurrentVideo() {
    const song = state.selectedSong;
    if (!song || !song.videoId) { showToast('Esta canción no tiene vídeo', true); return; }
    const body = { artist: song.artist, title: song.title, videoId: song.videoId, playlist: song.playlist || '' };
    const btn = document.getElementById('youtube-sync-playlist-btn');
    const label = btn ? btn.querySelector('span') : null;
    if (btn) { btn.disabled = true; if (label) label.textContent = 'Actualizando...'; }
    const run = (retried) => postPlaylistSync('/api/sync-playlist-song', body, () => run(true), retried);
    run(false).finally(() => { if (btn) { btn.disabled = false; if (label) label.textContent = 'Actualizar playlist'; } });
}

async function postPlaylistSync(url, body, retry, retried) {
    try {
        const res = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        const data = await res.json();
        if (data.needsAuth && !retried) {
            if (!confirm('Para actualizar también tu playlist de YouTube Music hace falta autorizar el acceso a tu cuenta de YouTube (solo una vez).\n\nSe abrirá una ventana de Google. ¿Continuar?')) return;
            const auth = await fetch('/api/youtube-auth', { method: 'POST' }).then(r => r.json());
            if (!auth.ok) { showToast(auth.error || 'No se pudo autorizar YouTube', true); return; }
            return retry();
        }
        if (data.error) { showToast(data.error, true); return; }
        if (data.replaced && data.replaced.length) {
            showToast(`Playlist de YouTube Music actualizada: ${data.replaced.join(', ')} ✨`);
        } else if (data.alreadyOk) {
            showToast('Tu playlist de YouTube Music ya tenía este vídeo');
        } else {
            showToast('No se encontró esta canción en tus playlists de YouTube', true);
        }
    } catch (err) {
        console.error('No se pudo actualizar la playlist de YouTube:', err);
        showToast('No se pudo actualizar la playlist de YouTube Music', true);
    }
}

(function setupAlternativeVideo() {
    const btn = document.getElementById('youtube-alt-btn');
    if (btn) btn.addEventListener('click', findAlternativeVideo);
    const syncBtn = document.getElementById('youtube-sync-playlist-btn');
    if (syncBtn) syncBtn.addEventListener('click', syncPlaylistToCurrentVideo);
    // The player reports embedding/playback errors through postMessage (enablejsapi=1)
    window.addEventListener('message', (e) => {
        if (!/^https:\/\/(www\.)?youtube\.com$/.test(e.origin)) return;
        let msg = e.data;
        if (typeof msg === 'string') { try { msg = JSON.parse(msg); } catch (err) { return; } }
        if (msg && msg.event === 'onError') {
            showToast('Este vídeo no se puede reproducir. Pulsa «Probar otro vídeo» para buscar otra versión.', true);
            if (btn) { btn.classList.add('btn-primary'); setTimeout(() => btn.classList.remove('btn-primary'), 6000); }
        }
    });
    // enablejsapi only delivers events once the player is told someone is listening
    if (els.youtubePlayer) els.youtubePlayer.addEventListener('load', () => {
        try { els.youtubePlayer.contentWindow.postMessage(JSON.stringify({ event: 'listening' }), '*'); } catch (err) {}
    });
})();

// Play / pause / stop the (hidden) YouTube player from the improvisation guide
(function setupImprovYoutubeControls() {
    const send = (func, args = '') => {
        const frame = els.youtubePlayer;
        if (!frame || !frame.contentWindow || !frame.getAttribute('src')) {
            showToast('Esta canción no tiene vídeo de YouTube', true);
            return;
        }
        frame.contentWindow.postMessage(JSON.stringify({ event: 'command', func, args }), '*');
    };
    const bind = (id, handler) => {
        const btn = document.getElementById(id);
        if (btn) btn.addEventListener('click', handler);
    };
    bind('improv-yt-play', () => send('playVideo'));
    bind('improv-yt-pause', () => send('pauseVideo'));
    bind('improv-yt-stop', () => { send('seekTo', [0, true]); send('pauseVideo'); });

    // Mixer: song volume goes to the YouTube iframe, scale volume to the fretboard synth. Both persist.
    const loadVol = (key, def) => {
        const v = parseInt(localStorage.getItem(key), 10);
        return Number.isFinite(v) ? Math.min(100, Math.max(0, v)) : def;
    };
    const applySongVolume = () => {
        const frame = els.youtubePlayer;
        if (!frame || !frame.contentWindow || !frame.getAttribute('src')) return;
        frame.contentWindow.postMessage(JSON.stringify({ event: 'command', func: 'setVolume', args: [loadVol('vibemus_vol_song', 100)] }), '*');
    };
    const songSlider = document.getElementById('improv-vol-song');
    const scaleSlider = document.getElementById('improv-vol-scale');
    if (songSlider) {
        songSlider.value = loadVol('vibemus_vol_song', 100);
        songSlider.addEventListener('input', () => {
            localStorage.setItem('vibemus_vol_song', songSlider.value);
            applySongVolume();
        });
    }
    if (scaleSlider) {
        scaleSlider.value = loadVol('vibemus_vol_scale', 100);
        if (window.setScaleVolume) window.setScaleVolume(scaleSlider.value / 100);
        scaleSlider.addEventListener('input', () => {
            localStorage.setItem('vibemus_vol_scale', scaleSlider.value);
            if (window.setScaleVolume) window.setScaleVolume(scaleSlider.value / 100);
        });
    }
    // A new song reloads the iframe, which resets YouTube's volume
    if (els.youtubePlayer) els.youtubePlayer.addEventListener('load', applySongVolume);
})();

(function setupChordFloat() {
    const popup = document.getElementById('chord-float-popup');
    const handle = document.getElementById('chord-float-handle');
    if (!popup || !handle) return;

    document.getElementById('chord-float-close').addEventListener('click', closeChordFloat);
    if (els.expandedImprovTitle) {
        els.expandedImprovTitle.addEventListener('click', () => openChordFloat(state.selectedSong));
    }

    handle.addEventListener('pointerdown', (e) => {
        if (e.target.closest('#chord-float-close')) return;
        const rect = popup.getBoundingClientRect();
        const dx = e.clientX - rect.left;
        const dy = e.clientY - rect.top;
        handle.setPointerCapture(e.pointerId);
        const move = (ev) => {
            const left = Math.min(Math.max(0, ev.clientX - dx), window.innerWidth - 80);
            const top = Math.min(Math.max(0, ev.clientY - dy), window.innerHeight - 40);
            popup.style.left = `${left}px`;
            popup.style.top = `${top}px`;
        };
        const up = () => {
            handle.removeEventListener('pointermove', move);
            handle.removeEventListener('pointerup', up);
        };
        handle.addEventListener('pointermove', move);
        handle.addEventListener('pointerup', up);
    });
})();

function closeImprovisationModal() {
    closeChordFloat();
    if (window.GuitarFretboard) window.GuitarFretboard.stopPractice();
    if (els.expandImprovModal) {
        els.expandImprovModal.classList.add('hide');
    }
}

if (els.closeExpandImprovBtn) {
    els.closeExpandImprovBtn.addEventListener('click', closeImprovisationModal);
}

if (els.expandImprovModal) {
    els.expandImprovModal.addEventListener('click', (e) => {
        if (e.target === els.expandImprovModal) {
            closeImprovisationModal();
        }
    });
}

document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && els.expandImprovModal && !els.expandImprovModal.classList.contains('hide')) {
        closeImprovisationModal();
    }
});

if (els.generateImprovBtn) {
    els.generateImprovBtn.addEventListener('click', async () => {
        const song = state.selectedSong;
        if (!song) return;
        
        // If it already has a guide, open the maximized modal directly
        if (song.improvisation && song.improvisation.trim() !== '') {
            openImprovisationModal(song);
            return;
        }
        
        // Generate via AI
        if (!song.tonality || !song.progression) {
            showToast("Necesitas tener la Tonalidad y Progresión detectadas antes de generar la guía.", "error");
            return;
        }
        
        const originalHtml = els.generateImprovBtn.innerHTML;
        els.generateImprovBtn.innerHTML = '<i class="ph ph-spinner ph-spin"></i><span>Generando...</span>';
        els.generateImprovBtn.disabled = true;
        
        try {
            const res = await fetch('/api/generate-improvisation', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    row: song.row,
                    artist: song.artist,
                    title: song.title,
                    tonality: song.tonality,
                    progression: song.progression
                })
            });
            const data = await res.json();
            
            if (!res.ok) throw new Error(data.error || 'Error generating guide');
            
            song.improvisation = data.improvisation;
            
            // Save to sheets
            await updateGoogleSheetField(song, 'improvisation', song.improvisation);
            
            renderImprovisationGuide(song);
            openImprovisationModal(song);
            showToast("Guía generada y guardada", "success");
            
        } catch (err) {
            showToast(err.message, "error");
        } finally {
            renderImprovisationGuide(song);
            els.generateImprovBtn.disabled = false;
        }
    });
}

async function updateGoogleSheetField(song, field, value) {
    const payload = {
        row: song.row,
        artist: song.artist,
        title: song.title
    };
    payload[field] = value;
    
    const response = await apiUpdateFetch('/api/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });
    
    if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || `Error updating ${field}`);
    }
}
