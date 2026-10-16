/**
 * Vibemus — Interactive Guitar Fretboard & Modal Fusion Visualizer
 * Renders horizontal guitar fretboard diagrams for scales and modal transitions.
 * Fully synchronized: maintains active fusion state when switching modal targets,
 * prevents ghost highlights, and supports intelligent song filtering with "Ver todos".
 */

(function(window) {
    'use strict';

    const CHROMATIC_SHARP = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];

    const ENHARMONIC_MAP = {
        'Db': 'C#', 'Eb': 'D#', 'Gb': 'F#', 'Ab': 'G#', 'Bb': 'A#',
        'B#': 'C', 'E#': 'F', 'Cb': 'B', 'Fb': 'E',
        'Do': 'C', 'Re': 'D', 'Mi': 'E', 'Fa': 'F', 'Sol': 'G', 'La': 'A', 'Si': 'B',
        'Do#': 'C#', 'Reb': 'C#', 'Re#': 'D#', 'Mib': 'D#', 'Fa#': 'F#', 'Solb': 'F#',
        'Sol#': 'G#', 'Lab': 'G#', 'La#': 'A#', 'Sib': 'A#'
    };

    function normalizeNote(note) {
        if (!note) return 'A';
        // Fix casing: "EB"/"eb" → "Eb", "f#" → "F#" (a flat sign must stay lowercase)
        const clean = note.trim().replace(/^([A-Ga-g])([#bB]?)/, (m, l, acc) => l.toUpperCase() + (acc === 'B' ? 'b' : acc));
        return ENHARMONIC_MAP[clean] || clean;
    }

    // Display-only: show flats instead of sharps when the song's key uses flats (internal state stays sharp)
    const SHARP_TO_FLAT = { 'C#': 'Db', 'D#': 'Eb', 'F#': 'Gb', 'G#': 'Ab', 'A#': 'Bb' };
    function dn(name) {
        return window.vibemusPreferFlats && SHARP_TO_FLAT[name] ? SHARP_TO_FLAT[name] : name;
    }

    function noteToSemitone(note) {
        const norm = normalizeNote(note);
        const idx = CHROMATIC_SHARP.indexOf(norm);
        return idx !== -1 ? idx : 0;
    }

    // Standard 6-String Guitar Tuning (String 1 = High E, String 6 = Low E)
    const STRINGS = [
        { name: 'e', root: 'E', midi: 64, semitone: 4, gauge: 1.6 },
        { name: 'B', root: 'B', midi: 59, semitone: 11, gauge: 2.0 },
        { name: 'G', root: 'G', midi: 55, semitone: 7, gauge: 2.5 },
        { name: 'D', root: 'D', midi: 50, semitone: 2, gauge: 3.0 },
        { name: 'A', root: 'A', midi: 45, semitone: 9, gauge: 3.6 },
        { name: 'E', root: 'E', midi: 40, semitone: 4, gauge: 4.4 }
    ];

    const SCALES = {
        'major': {
            name: 'Mayor / Jónica',
            desc: 'La opción más segura y luminosa',
            intervals: [0, 2, 4, 5, 7, 9, 11],
            degrees: ['1', '2', '3', '4', '5', '6', '7']
        },
        'pentatonic_major': {
            name: 'Pentatónica Mayor',
            desc: 'Sonido abierto y directo, sin notas de choque',
            intervals: [0, 2, 4, 7, 9],
            degrees: ['1', '2', '3', '5', '6']
        },
        'minor': {
            name: 'Menor Natural / Eólica',
            desc: 'Melancólica y oscura',
            intervals: [0, 2, 3, 5, 7, 8, 10],
            degrees: ['1', '2', 'b3', '4', '5', 'b6', 'b7']
        },
        'pentatonic_minor': {
            name: 'Pentatónica Menor',
            desc: 'El pilar del rock, blues y solos potentes',
            intervals: [0, 3, 5, 7, 10],
            degrees: ['1', 'b3', '4', '5', 'b7']
        },
        'dorian': {
            name: 'Dórica',
            desc: 'Menor pero brillante gracias a la 6ª mayor (sonido Santana/Pink Floyd)',
            intervals: [0, 2, 3, 5, 7, 9, 10],
            degrees: ['1', '2', 'b3', '4', '5', '6', 'b7']
        },
        'phrygian': {
            name: 'Frigia',
            desc: 'Toque exótico y flamenco por la 2ª menor (b2)',
            intervals: [0, 1, 3, 5, 7, 8, 10],
            degrees: ['1', 'b2', 'b3', '4', '5', 'b6', 'b7']
        },
        'lydian': {
            name: 'Lidia',
            desc: 'Mística y cinematográfica por la 4ª aumentada (#4)',
            intervals: [0, 2, 4, 6, 7, 9, 11],
            degrees: ['1', '2', '3', '#4', '5', '6', '7']
        },
        'mixolydian': {
            name: 'Mixolidia',
            desc: 'Mayor con sabor blues/rock sureño por la 7ª menor (b7)',
            intervals: [0, 2, 4, 5, 7, 9, 10],
            degrees: ['1', '2', '3', '4', '5', '6', 'b7']
        },
        'locrian': {
            name: 'Lócria',
            desc: 'Tensa e inestable por la 5ª disminuida (b5)',
            intervals: [0, 1, 3, 5, 6, 8, 10],
            degrees: ['1', 'b2', 'b3', '4', 'b5', 'b6', 'b7']
        },
        'blues': {
            name: 'Escala Blues',
            desc: 'Pentatónica menor con la blue note (b5)',
            intervals: [0, 3, 5, 6, 7, 10],
            degrees: ['1', 'b3', '4', 'b5', '5', 'b7']
        },
        'harmonic_minor': {
            name: 'Menor Armónica',
            desc: 'Clásica y neoclásica con 7ª mayor',
            intervals: [0, 2, 3, 5, 7, 8, 11],
            degrees: ['1', '2', 'b3', '4', '5', 'b6', '7']
        },
        'phrygian_dominant': {
            name: 'Frigia Dominante',
            desc: 'Sonido flamenco, español y neoclásico (V modo de la menor armónica)',
            intervals: [0, 1, 4, 5, 7, 8, 10],
            degrees: ['1', 'b2', '3', '4', '5', 'b6', 'b7']
        },
        'melodic_minor': {
            name: 'Menor Melódica',
            desc: 'Jazz y fusión contemporánea con 6ª y 7ª mayores',
            intervals: [0, 2, 3, 5, 7, 9, 11],
            degrees: ['1', '2', 'b3', '4', '5', '6', '7']
        },
        'altered': {
            name: 'Alterada',
            desc: 'Escala dominante alterada (7º modo de la menor melódica) — tensión máxima para acordes V7#9, V7b9, V7b5',
            intervals: [0, 1, 3, 4, 6, 8, 10],
            degrees: ['1', 'b2', '#2', '3', 'b5', 'b6', 'b7']
        },
        'blues_chromatic': {
            name: 'Blues + Cromatismos',
            desc: 'Escala blues enriquecida con pasos cromáticos para turnarounds y transiciones',
            intervals: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11],
            degrees: ['1', 'b2', '2', 'b3', '3', '4', 'b5', '5', 'b6', '6', 'b7', '7']
        }
    };

    // Chord-scale roles per scale (Berklee-style avoid notes: a half step above a chord tone, except b9/b13 over dominants)
    const NOTE_ROLES = {
        'major':             { chord: ['1', '3', '5', '7'],   characteristic: ['7'],                   avoid: ['4'] },
        'dorian':            { chord: ['1', 'b3', '5', 'b7'], characteristic: ['6'],                   avoid: [] },
        'phrygian':          { chord: ['1', 'b3', '5', 'b7'], characteristic: ['b2'],                  avoid: ['b2', 'b6'] },
        'lydian':            { chord: ['1', '3', '5', '7'],   characteristic: ['#4'],                  avoid: [] },
        'mixolydian':        { chord: ['1', '3', '5', 'b7'],  characteristic: ['b7'],                  avoid: ['4'] },
        'minor':             { chord: ['1', 'b3', '5', 'b7'], characteristic: ['b6'],                  avoid: ['b6'] },
        'locrian':           { chord: ['1', 'b3', 'b5', 'b7'],characteristic: ['b5'],                  avoid: ['b2'] },
        'harmonic_minor':    { chord: ['1', 'b3', '5', '7'],  characteristic: ['7'],                   avoid: ['b6'] },
        'melodic_minor':     { chord: ['1', 'b3', '5', '7'],  characteristic: ['6', '7'],              avoid: [] },
        'phrygian_dominant': { chord: ['1', '3', '5', 'b7'],  characteristic: ['b2'],                  avoid: ['4'] },
        'altered':           { chord: ['1', '3', 'b7'],       characteristic: ['b2', '#2', 'b5', 'b6'], avoid: [] },
        'pentatonic_major':  { chord: ['1', '3', '5'],        characteristic: [],                      avoid: [] },
        'pentatonic_minor':  { chord: ['1', 'b3', '5', 'b7'], characteristic: [],                      avoid: [] },
        'blues':             { chord: ['1', 'b3', '5', 'b7'], characteristic: ['b5'],                  avoid: ['b5'] },
        'blues_chromatic':   { chord: [],                     characteristic: [],                      avoid: [] }
    };

    const INTERVAL_NAMES = ['1', 'b2', '2', 'b3', '3', '4', 'b5', '5', 'b6', '6', 'b7', '7'];

    function getNoteRole(scaleKey, degree) {
        const roles = NOTE_ROLES[scaleKey];
        if (!roles) return { chord: false, characteristic: false, avoid: false };
        return {
            chord: roles.chord.includes(degree),
            characteristic: roles.characteristic.includes(degree),
            avoid: roles.avoid.includes(degree)
        };
    }

    function getRoleStyle(scaleKey, noteData) {
        if (noteData.isBlue) {
            return {
                fill: '#4f46e5', stroke: '#a5b4fc', width: 2.5, text: '#ffffff', dash: '',
                label: noteData.interval === 3
                    ? 'b3 de blues (pentatónica mixta): tócala y resuelve a la 3 mayor'
                    : 'Blue note (b5): tensión de paso, resuélvela a la 5 o a la 4'
            };
        }
        const role = getNoteRole(scaleKey, noteData.degree);
        const s = { fill: '#09090b', stroke: '#52525b', width: 2, text: '#ffffff', dash: '', label: 'Tensión / nota de paso' };
        if (noteData.isRoot) {
            Object.assign(s, { fill: '#ef4444', stroke: '#b91c1c', width: 2.5, label: 'Tónica' });
        } else if (role.characteristic) {
            Object.assign(s, { fill: '#f59e0b', stroke: '#b45309', width: 2.5, text: '#000000', label: 'Nota característica del modo' });
        } else if (role.chord) {
            Object.assign(s, { fill: '#059669', stroke: '#047857', label: 'Nota del acorde (reposo)' });
        }
        if (role.avoid) {
            s.dash = '3 2';
            s.width = 2.5;
            if (role.characteristic) {
                s.stroke = '#fef3c7';
                s.label += ' — úsala de paso, no te detengas';
            } else {
                Object.assign(s, { stroke: '#a1a1aa', text: '#a1a1aa', label: 'Nota a evitar (no te detengas en ella)' });
            }
        }
        return s;
    }

    // Legend line explaining what the "Blues" toggle added to the scale on screen
    function describeBlues() {
        const root = fbState.fusionActive ? fbState.root2 : fbState.root1;
        const key = fbState.fusionActive ? fbState.scaleKey2 : fbState.scaleKey1;
        const def = SCALES[key] || SCALES['major'];
        const rootSemi = noteToSemitone(root);
        const note = iv => `<strong style="color: #a5b4fc; font-family: 'Geist Mono', monospace;">${dn(CHROMATIC_SHARP[(rootSemi + iv) % 12])} (${INTERVAL_NAMES[iv]})</strong>`;
        const adds = getBluesAdditions(def.intervals);
        const flavour = { mixolydian: ' — el llamado <em>Mixoblues</em>', dorian: ' — blues menor tipo BB King / Clapton', major: ' — pentatónica mixta sobre el modo mayor' }[key] || '';
        let msg;
        if (!adds.length) {
            msg = `${dn(root)} ${def.name} ya contiene la b5: no hay notas que añadir.`;
        } else {
            const parts = [];
            if (adds.includes(3)) parts.push(`${note(3)}: alterna b3 → 3 sobre el acorde (Stevie Ray Vaughan, Freddie King)`);
            if (adds.includes(6)) parts.push(`${note(6)}: la <em>blue note</em>, de paso hacia la 5 o la 4`);
            msg = `${dn(root)} ${def.name} + blues${flavour}. Añadidas ${parts.join(' · ')}.`;
        }
        return `
            <div style="display: flex; align-items: center; gap: 8px; margin-top: 8px; font-size: 12px; color: var(--text-secondary); background: rgba(79,70,229,0.08); padding: 6px 10px; border-radius: 6px; border: 1px solid rgba(165,180,252,0.25); line-height: 1.6;">
                <span style="width: 12px; height: 12px; border-radius: 50%; display: inline-block; flex-shrink: 0; background: #4f46e5; border: 1.5px solid #a5b4fc;"></span>
                <span>${msg}</span>
            </div>`;
    }

    function describeAvoidNotes(scaleMap, scaleKey) {
        const roles = NOTE_ROLES[scaleKey];
        if (!roles || roles.avoid.length === 0) return '';
        const entries = [...scaleMap.entries()];
        return roles.avoid.map(deg => {
            const found = entries.find(([, d]) => d.degree === deg);
            if (!found) return '';
            const [semi, data] = found;
            const below = scaleMap.get((semi + 11) % 12);
            const clash = below && roles.chord.includes(below.degree)
                ? `choca a medio tono con la ${below.noteName} (${below.degree}) del acorde`
                : 'úsala solo de paso';
            return `<strong style="color: #e4e4e7; font-family: 'Geist Mono', monospace;">${data.noteName} (${deg})</strong>: ${clash}`;
        }).filter(Boolean).join(' · ');
    }

    // Global Visualizer State
    const fbState = {
        bluesActive: false, // "Blues" toggle: adds the blue note (and b3 on major modes) to the scales
        root1: 'A',
        scaleKey1: 'major',
        root2: 'D',
        scaleKey2: 'lydian',
        fusionActive: false,
        labelType: 'degrees', // 'degrees' or 'notes'
        showAll: false,
        maxFrets: 15,
        containerEl: null,
        song: null,
        activeTransitionIndex: -1,
        activeTransitionItem: null,
        songModes: {
            baseRoots: ['A'],
            baseModesMap: new Map(),
            transitionRoots: ['D', 'E'],
            transitionModesMap: new Map(),
            allSongModesMap: new Map(),
            transitionItems: []
        }
    };

    // Older guides may contain LaTeX around chords ($Dm^7$, $C^{maj7}$): show them as plain text (Dm7, Cmaj7)
    window.stripLatex = function(text) {
        return String(text || '').replace(/\$([^$\n]+)\$/g, (m, inner) => inner
            .replace(/\\sharp/g, '#').replace(/\\flat/g, 'b').replace(/\\natural/g, '')
            .replace(/[\^_]\{([^}]*)\}/g, '$1').replace(/[\^_](\w+)/g, '$1')
            .replace(/[{}\\]/g, ''));
    };

    // Extract relevant and recommended modes from the song's tonality, chords, and AI guide
    function extractSongModes(song) {
        function getDegreeFromChordString(str, tonalityStr) {
            if (!str) return 0;
            const romanMatch = str.trim().match(/^([b#]?)(i{1,3}v?|v?i{0,3}|IV|V|I{1,3})/i);
            if (romanMatch && romanMatch[2]) {
                const romanStr = romanMatch[2].toUpperCase();
                const map = { 'I':1, 'II':2, 'III':3, 'IV':4, 'V':5, 'VI':6, 'VII':7 };
                return map[romanStr] || 0;
            }
            if (typeof window.getChordAnalysis === 'function') {
                const parentMatch = str.match(/\(([A-G][#b]?[^)]*)\)/);
                const cleanChord = parentMatch ? parentMatch[1] : str.trim();
                const analysis = window.getChordAnalysis(cleanChord, tonalityStr);
                return analysis.degree || 0;
            }
            return 0;
        }

        const tonality = (song && song.tonality ? song.tonality : '').trim();
        let mainRoot = 'A';
        let isMajor = true;

        const match = tonality.match(/^([A-G][#b]?)\s*(.*)$/i);
        if (match) {
            mainRoot = normalizeNote(match[1]);
            const modePart = (match[2] || '').trim().toLowerCase();
            // Important: "major" and "mayor" start with 'm', so do NOT use .includes('m')!
            if (modePart.startsWith('maj') || modePart.startsWith('may') || modePart === '') {
                isMajor = true;
            } else if (modePart.startsWith('min') || modePart.startsWith('men') || modePart === 'm' || /\bm\b/i.test(modePart)) {
                isMajor = false;
            } else {
                isMajor = true;
            }
        }

        const baseModesMap = new Map();
        const transitionModesMap = new Map();
        const allSongModesMap = new Map();
        const transitionItems = [];

        function addMode(map, root, scaleKey) {
            if (!SCALES[scaleKey]) return;
            const normRoot = normalizeNote(root);
            if (!map.has(normRoot)) map.set(normRoot, new Set());
            map.get(normRoot).add(scaleKey);

            if (!allSongModesMap.has(normRoot)) allSongModesMap.set(normRoot, new Set());
            allSongModesMap.get(normRoot).add(scaleKey);
        }

        function matchScaleKey(str) {
            const sNorm = (str || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
            if (sNorm.includes('alterad') || sNorm.includes('altered') || sNorm.includes('superlocri') || sNorm.includes('super locri')) return 'altered';
            if (sNorm.includes('mixolidi') || sNorm.includes('mixolydian')) return 'mixolydian';
            if (sNorm.includes('lidi') || sNorm.includes('lydian')) return 'lydian';
            if (sNorm.includes('doric') || sNorm.includes('dorian')) return 'dorian';
            if (sNorm.includes('frig') || sNorm.includes('phrygian')) {
                return sNorm.includes('dominan') ? 'phrygian_dominant' : 'phrygian';
            }
            if (sNorm.includes('pentat') || sNorm.includes('pentatonic')) {
                return (sNorm.includes('menor') || sNorm.includes('minor')) ? 'pentatonic_minor' : 'pentatonic_major';
            }
            if (sNorm.includes('armonic') || sNorm.includes('harmonic')) return 'harmonic_minor';
            if (sNorm.includes('melodic')) return 'melodic_minor';
            if (sNorm.includes('blues') && (sNorm.includes('cromat') || sNorm.includes('chromat'))) return 'blues_chromatic';
            if (sNorm.includes('blues')) return 'blues';
            if (sNorm.includes('eolic') || sNorm.includes('aeolian') || sNorm.includes('menor') || sNorm.includes('minor')) return 'minor';
            if (sNorm.includes('locri') || sNorm.includes('locrian')) return 'locrian';
            if (sNorm.includes('jonic') || sNorm.includes('ionian') || sNorm.includes('mayor') || sNorm.includes('major')) return 'major';
            return 'major';
        }

        // 1. Primary Base Modes
        if (isMajor) {
            addMode(baseModesMap, mainRoot, 'major');
            addMode(baseModesMap, mainRoot, 'pentatonic_major');
        } else {
            addMode(baseModesMap, mainRoot, 'minor');
            addMode(baseModesMap, mainRoot, 'pentatonic_minor');
            addMode(baseModesMap, mainRoot, 'dorian');
        }

        // 2. Parse AI Guide Markdown if generated in song.improvisation
        // When the AI guide exists, its recommended scales and chords are the authoritative, curated transitions.
        const guideText = window.stripLatex(song && song.improvisation ? song.improvisation : '');
        let guideModesFound = 0;

        const scaleRegex = /\b([A-G][#b]?|Do[#b]?|Re[#b]?|Mi[#b]?|Fa[#b]?|Sol[#b]?|La[#b]?|Si[#b]?)\s+(Mayor|Menor(?:\s+(?:Natural|Arm[oó]nic[ao]|Mel[oó]dic[ao]))?|J[oó]nic[ao]|D[oó]ric[ao]|Frigi[ao](?:\s+Dominante)?|Lidi[ao]|Mixolidi[ao]|E[oó]lic[ao]|L[oó]cri[ao]|Pentat[oó]nica(?:\s+(?:Mayor|Menor))?|Blues(?:\s*\+?\s*Cromatis?mos?)?|Alterad[ao]|Altered|Ionian|Dorian|Phrygian(?:\s+Dominant)?|Lydian|Mixolydian|Aeolian|Locrian|Major|Minor)\b/i;

        if (guideText) {
            const lines = guideText.split('\n');
            for (let line of lines) {
                const trimmed = line.trim();
                if (!trimmed.startsWith('|')) continue;
                const cols = trimmed.split('|').map(c => c.trim());
                if (cols.length < 5) continue;
                const c1 = cols[1]; // Acorde
                const c2 = cols[2]; // Escala
                const c3 = cols[3]; // Notas principales
                const c4 = cols[4]; // Comentario

                if (/acorde/i.test(c1) && /escala/i.test(c2)) continue;
                if (/^:?-+:?$/.test(c1)) continue;

                const chordClean = c1.replace(/\*\*/g, '').replace(/`/g, '').trim();
                const scaleClean = c2.replace(/\*\*/g, '').replace(/`/g, '').trim();
                const notesClean = c3.replace(/\*\*/g, '').replace(/`/g, '').trim();
                const commentClean = c4.replace(/\*\*/g, '').replace(/`/g, '').trim();

                if (!chordClean && !scaleClean) continue;

                const sm = scaleRegex.exec(scaleClean);
                let sRoot = mainRoot;
                let matchedKey = 'major';

                if (sm) {
                    sRoot = normalizeNote(sm[1]);
                    matchedKey = matchScaleKey(sm[2]);
                } else {
                    matchedKey = matchScaleKey(scaleClean);
                }

                addMode(transitionModesMap, sRoot, matchedKey);
                guideModesFound++;

                transitionItems.push({
                    chord: chordClean,
                    degree: getDegreeFromChordString(chordClean, tonality),
                    root: sRoot,
                    scaleKey: matchedKey,
                    scaleDisplayName: `${dn(sRoot)} ${SCALES[matchedKey] ? SCALES[matchedKey].name : matchedKey}`,
                    keyNotes: notesClean,
                    comment: commentClean
                });
            }

            // Fallback if guideText exists but no table rows were matched
            if (guideModesFound === 0) {
                const globalScaleRegex = new RegExp(scaleRegex.source, 'gi');
                let gsm;
                while ((gsm = globalScaleRegex.exec(guideText)) !== null) {
                    const sRoot = normalizeNote(gsm[1]);
                    const matchedKey = matchScaleKey(gsm[2]);
                    addMode(transitionModesMap, sRoot, matchedKey);
                    guideModesFound++;
                    transitionItems.push({
                        chord: '',
                        degree: 0,
                        root: sRoot,
                        scaleKey: matchedKey,
                        scaleDisplayName: `${dn(sRoot)} ${SCALES[matchedKey] ? SCALES[matchedKey].name : matchedKey}`,
                        keyNotes: '',
                        comment: ''
                    });
                }
            }
        }

        // 3. Fallback only if no AI guide modes were found (e.g. guide not yet generated)
        if (guideModesFound === 0) {
            // Parse explicit chords if available in song.chord
            const chordStr = (song && song.chord ? song.chord : '');
            if (chordStr) {
                const chordRegex = /\b([A-G][#b]?)(m|min|maj|sus|dim|aug|7|9|11|13|add)?([^\s]*)\b/gi;
                let cm;
                while ((cm = chordRegex.exec(chordStr)) !== null) {
                    const cRoot = normalizeNote(cm[1]);
                    const cQual = (cm[2] || '').toLowerCase();
                    const cExtra = (cm[3] || '').toLowerCase();
                    const fullChord = cm[0];
                    let key = 'major';
                    const hasAlteredTension = /[#b]\d|alt/i.test(cExtra) || /[#b](9|5|13)/i.test(cQual + cExtra);
                    if (cQual.includes('m') && !cQual.includes('maj')) {
                        key = 'dorian';
                        addMode(transitionModesMap, cRoot, 'dorian');
                        addMode(transitionModesMap, cRoot, 'minor');
                    } else if ((cQual.includes('7') || cQual === '9' || cQual === '13') && !cQual.includes('maj') && hasAlteredTension) {
                        key = 'altered';
                        addMode(transitionModesMap, cRoot, 'altered');
                    } else if ((cQual.includes('7') || cQual === '9' || cQual === '13') && !cQual.includes('maj')) {
                        key = 'mixolydian';
                        addMode(transitionModesMap, cRoot, 'mixolydian');
                    } else if (cQual.includes('sus')) {
                        key = 'mixolydian';
                        addMode(transitionModesMap, cRoot, 'mixolydian');
                    } else if (cQual.includes('maj') || cQual.includes('6')) {
                        key = 'lydian';
                        addMode(transitionModesMap, cRoot, 'lydian');
                        addMode(transitionModesMap, cRoot, 'major');
                    } else {
                        key = 'major';
                        addMode(transitionModesMap, cRoot, 'major');
                    }
                    if (!transitionItems.some(ti => ti.chord === fullChord)) {
                        transitionItems.push({
                            chord: fullChord,
                            degree: getDegreeFromChordString(fullChord, tonality),
                            root: cRoot,
                            scaleKey: key,
                            scaleDisplayName: `${dn(cRoot)} ${SCALES[key] ? SCALES[key].name : key}`,
                            keyNotes: '',
                            comment: `Modo sugerido para el acorde ${fullChord}`
                        });
                    }
                }
            }

            // Diatonic & Modal Transitions inferred from Tonality
            const rootSemi = noteToSemitone(mainRoot);
            if (isMajor) {
                const ivRoot = CHROMATIC_SHARP[(rootSemi + 5) % 12];
                const vRoot = CHROMATIC_SHARP[(rootSemi + 7) % 12];
                const iiRoot = CHROMATIC_SHARP[(rootSemi + 2) % 12];
                const viRoot = CHROMATIC_SHARP[(rootSemi + 9) % 12];

                addMode(transitionModesMap, ivRoot, 'lydian');
                addMode(transitionModesMap, vRoot, 'mixolydian');
                addMode(transitionModesMap, iiRoot, 'dorian');
                addMode(transitionModesMap, viRoot, 'minor');
            } else {
                const ivRoot = CHROMATIC_SHARP[(rootSemi + 5) % 12];
                const vRoot = CHROMATIC_SHARP[(rootSemi + 7) % 12];
                const viRoot = CHROMATIC_SHARP[(rootSemi + 8) % 12];
                const viiRoot = CHROMATIC_SHARP[(rootSemi + 10) % 12];
                const iiiRoot = CHROMATIC_SHARP[(rootSemi + 3) % 12];

                addMode(transitionModesMap, vRoot, 'dorian');
                addMode(transitionModesMap, vRoot, 'phrygian');
                addMode(transitionModesMap, ivRoot, 'dorian');
                addMode(transitionModesMap, viRoot, 'lydian');
                addMode(transitionModesMap, viiRoot, 'mixolydian');
                addMode(transitionModesMap, iiiRoot, 'major');
            }
        }

        const baseRoots = Array.from(baseModesMap.keys());
        const transitionRoots = Array.from(transitionModesMap.keys());

        return {
            baseRoots: baseRoots.length ? baseRoots : [mainRoot],
            baseModesMap,
            transitionRoots: transitionRoots.length ? transitionRoots : (baseRoots.length ? baseRoots : [mainRoot]),
            transitionModesMap,
            allSongModesMap,
            transitionItems
        };
    }

    // Build Scale Map: returns a Map of semitone -> { degree, isRoot }
    function getScaleMap(rootNote, scaleKey) {
        const rootSemi = noteToSemitone(rootNote);
        const scaleDef = SCALES[scaleKey] || SCALES['major'];
        const map = new Map();

        scaleDef.intervals.forEach((interval, idx) => {
            const semi = (rootSemi + interval) % 12;
            map.set(semi, {
                degree: scaleDef.degrees[idx],
                interval: interval,
                isRoot: interval === 0,
                noteName: dn(CHROMATIC_SHARP[semi])
            });
        });

        getBluesAdditions(scaleDef.intervals).forEach(interval => {
            const semi = (rootSemi + interval) % 12;
            map.set(semi, {
                degree: INTERVAL_NAMES[interval],
                interval: interval,
                isRoot: false,
                isBlue: true,
                noteName: dn(CHROMATIC_SHARP[semi])
            });
        });

        return map;
    }

    // "Blues" toggle: the blue note (b5) on any mode, plus the b3 on major-third modes
    // (mixed major/minor pentatonic). Empty when the toggle is off.
    function getBluesAdditions(intervals) {
        if (!fbState.bluesActive) return [];
        const adds = [];
        if (intervals.includes(4) && !intervals.includes(3)) adds.push(3);
        if (!intervals.includes(6)) adds.push(6);
        return adds;
    }

    function getScaleIntervals(scaleKey) {
        const intervals = (SCALES[scaleKey] || SCALES['major']).intervals;
        return [...intervals, ...getBluesAdditions(intervals)];
    }

    // ── Shared sound bank (fretboard notes and chord playback in app.js) ─────────
    // 'original' keeps the legacy synths; the others are additive voices built from these presets.
    const INSTRUMENTS = {
        original:  { label: 'Original (por defecto)' },
        acoustic:  { label: 'Guitarra acústica', harm: [1, .6, .4, .25, .15, .1, .06, .04], attack: .004, decay: 1.3, sustain: 0, fStart: 9, fEnd: 1.8, fTime: .5, gain: .3 },
        electric:  { label: 'Guitarra eléctrica limpia', harm: [1, .5, .3, .15, .1, .05], attack: .005, decay: 1.8, sustain: 0, fStart: 6, fEnd: 2.2, fTime: .9, gain: .32 },
        piano:     { label: 'Piano', harm: [1, .5, .3, .2, .1, .08, .05], attack: .003, decay: 2.2, sustain: 0, fStart: 7, fEnd: 2, fTime: .7, detune: 3, gain: .3 },
        organ:     { label: 'Órgano', harm: [1, .9, .7, 0, .5, 0, 0, .3], attack: .02, decay: .1, sustain: 1, release: .08, fStart: 8, fEnd: 8, fTime: 1, gain: .2 },
        strings:   { label: 'Cuerdas (pad)', harm: [1, .5, .33, .25, .2, .16, .14, .12], attack: .3, decay: .5, sustain: .8, release: .6, fStart: 4, fEnd: 4, fTime: 1, detune: 7, gain: .14 },
        synth:     { label: 'Sintetizador lead', harm: [1, 0, .33, 0, .2, 0, .14, 0, .11], attack: .01, decay: .3, sustain: .7, release: .15, fStart: 5, fEnd: 5, fTime: 1, vibrato: [5.5, 8], detune: 5, gain: .2 },
        flute:     { label: 'Flauta', harm: [1, .2, .1, .05], attack: .07, decay: .3, sustain: .8, release: .15, fStart: 5, fEnd: 5, fTime: 1, vibrato: [5, 10], gain: .38 }
    };
    const waveCache = {};
    function getInstrumentId() {
        const id = localStorage.getItem('vibemus_instrument');
        return INSTRUMENTS[id] ? id : 'original';
    }

    // Builds one note of a preset instrument and returns the oscillators so callers can cut it short
    function playInstrumentNote(ctx, dest, freq, t, len, id, volume = 1) {
        const p = INSTRUMENTS[id];
        if (!p || !p.harm) return [];
        const wave = waveCache[id] || (waveCache[id] = ctx.createPeriodicWave(
            new Float32Array([0, ...p.harm.map(() => 0)]), new Float32Array([0, ...p.harm])));
        const release = p.release || .25;
        const peak = p.gain * volume;
        const env = ctx.createGain();
        env.gain.setValueAtTime(0.0001, t);
        env.gain.linearRampToValueAtTime(peak, t + p.attack);
        env.gain.exponentialRampToValueAtTime(Math.max(peak * p.sustain, 0.0001), t + p.attack + p.decay);
        env.gain.setValueAtTime(Math.max(peak * p.sustain, 0.0001), Math.max(t + p.attack + p.decay, t + len));
        env.gain.exponentialRampToValueAtTime(0.0001, t + len + release);
        const filter = ctx.createBiquadFilter();
        filter.type = 'lowpass';
        filter.frequency.setValueAtTime(Math.min(freq * p.fStart, 12000), t);
        filter.frequency.exponentialRampToValueAtTime(Math.min(freq * p.fEnd, 12000), t + p.fTime);
        filter.connect(env);
        env.connect(dest);
        const oscs = [];
        const cents = p.detune ? [-p.detune, p.detune] : [0];
        cents.forEach(c => {
            const o = ctx.createOscillator();
            o.setPeriodicWave(wave);
            o.frequency.setValueAtTime(freq, t);
            o.detune.setValueAtTime(c, t);
            if (p.vibrato) {
                const lfo = ctx.createOscillator();
                const lg = ctx.createGain();
                lfo.frequency.value = p.vibrato[0];
                lg.gain.setValueAtTime(0, t);
                lg.gain.linearRampToValueAtTime(p.vibrato[1], t + .35);
                lfo.connect(lg);
                lg.connect(o.detune);
                lfo.start(t);
                lfo.stop(t + len + release + .05);
                oscs.push(lfo);
            }
            o.connect(filter);
            o.start(t);
            o.stop(t + len + release + .05);
            oscs.push(o);
        });
        return oscs;
    }

    window.VibemusSound = {
        instruments: INSTRUMENTS,
        getId: getInstrumentId,
        setId: id => { if (INSTRUMENTS[id]) localStorage.setItem('vibemus_instrument', id); },
        playNote: playInstrumentNote
    };

    // Master volume for scale/exercise notes (0–1), driven by the mixer in the improvisation guide
    function getFretboardMaster(ctx) {
        if (!window.__fbMasterGain) {
            window.__fbMasterGain = ctx.createGain();
            window.__fbMasterGain.gain.value = window.vibemusScaleVolume;
            window.__fbMasterGain.connect(ctx.destination);
        }
        return window.__fbMasterGain;
    }

    window.vibemusScaleVolume = 1;
    window.setScaleVolume = function(v) {
        window.vibemusScaleVolume = v;
        if (window.__fbMasterGain) window.__fbMasterGain.gain.value = v;
    };

    // Play guitar note synthesis
    function playFretboardNote(midiNumber) {
        try {
            const AudioCtx = window.AudioContext || window.webkitAudioContext;
            if (!AudioCtx) return;
            if (!window.__fbAudioCtx) {
                window.__fbAudioCtx = new AudioCtx();
            }
            const ctx = window.__fbAudioCtx;
            if (ctx.state === 'suspended') ctx.resume();

            const freq = 440 * Math.pow(2, (midiNumber - 69) / 12);
            const now = ctx.currentTime;

            const instrument = getInstrumentId();
            if (instrument !== 'original') {
                playInstrumentNote(ctx, getFretboardMaster(ctx), freq, now, 1.0, instrument);
                return;
            }

            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            const filter = ctx.createBiquadFilter();

            osc.type = 'triangle';
            osc.frequency.setValueAtTime(freq, now);

            filter.type = 'lowpass';
            filter.frequency.setValueAtTime(3200, now);
            filter.frequency.exponentialRampToValueAtTime(600, now + 1.2);

            gain.gain.setValueAtTime(0.35, now);
            gain.gain.exponentialRampToValueAtTime(0.001, now + 1.4);

            osc.connect(filter);
            filter.connect(gain);
            gain.connect(getFretboardMaster(ctx));

            osc.start(now);
            osc.stop(now + 1.5);
        } catch (e) {
            console.warn('Audio play error:', e);
        }
    }

    // ── Practice exercises (CAGED positions + playback) ──────────────────────────
    const PRACTICE_EXERCISES = [
        { id: 'asc', label: 'Escala ascendente' },
        { id: 'desc', label: 'Escala descendente' },
        { id: 'updown', label: 'Escala ascendente + descendente' },
        { id: 'chord', label: 'Solo notas del acorde' },
        { id: 'chord_char', label: 'Notas del acorde + nota característica' },
        { id: 'thirds', label: 'Secuencia en terceras (1-3, 2-4, 3-5…)' },
        { id: 'group3', label: 'Grupos de 3 (1-2-3, 2-3-4…)' },
        { id: 'group4', label: 'Grupos de 4 (1-2-3-4, 2-3-4-5…)' },
        { id: 'arp_scale', label: 'Arpegio ascendente + escala descendente' },
        { id: 'zigzag', label: 'Zigzag (salta 2 arriba, baja 1)' },
        { id: 'zigzag_inv', label: 'Zigzag inverso (salta 2 abajo, sube 1)' },
        { id: 'call_resp', label: 'Llamada y respuesta (frase + silencio)' },
        { id: 'landing', label: 'Frase libre aterrizando en 1, 3 o 7' }
    ];

    // Window of frets (relative to the form's root fret) and the string where that form holds its root
    const CAGED_FORMS = {
        C: { label: 'C', rootString: 4, lo: -3, hi: 1 },
        A: { label: 'A', rootString: 4, lo: -1, hi: 3 },
        G: { label: 'G', rootString: 5, lo: -3, hi: 1 },
        E: { label: 'E', rootString: 5, lo: -1, hi: 3 },
        D: { label: 'D', rootString: 3, lo: -1, hi: 3 },
        all: { label: 'Todas' }
    };

    // Semitones to subtract from a scale's root to get the major key whose CAGED shapes contain it
    const PARENT_MAJOR_OFFSET = {
        major: 0, pentatonic_major: 0, dorian: 2, phrygian: 4, lydian: 5, mixolydian: 7,
        minor: 9, pentatonic_minor: 9, blues: 9, harmonic_minor: 9, melodic_minor: 9,
        locrian: 11, phrygian_dominant: 4, altered: 8
    };

    // Intervals (semitones from the root) that give each mode its flavour
    const CHARACTERISTIC_INTERVALS = {
        major: [5], dorian: [9], phrygian: [1], lydian: [6], mixolydian: [10], minor: [8], locrian: [6],
        harmonic_minor: [11], phrygian_dominant: [1, 4], melodic_minor: [9, 11], altered: [1, 3], blues: [6]
    };

    fbState.practice = { exercise: 'asc', form: 'all', bpm: 90, playing: false, show313: false };

    // Scale the exercises use: the transition mode when fusion is on, otherwise the base scale
    function getPracticeScale() {
        return fbState.fusionActive
            ? { root: fbState.root2, key: fbState.scaleKey2 }
            : { root: fbState.root1, key: fbState.scaleKey1 };
    }

    // Frets [lo, hi] covered by the chosen CAGED form on the current base scale
    function getCagedWindow(formKey) {
        const maxF = fbState.maxFrets;
        const form = CAGED_FORMS[formKey];
        if (!form || formKey === 'all') return { lo: 0, hi: maxF };
        const ps = getPracticeScale();
        const parentSemi = (noteToSemitone(ps.root) - (PARENT_MAJOR_OFFSET[ps.key] || 0) + 12) % 12;
        const rootFret = (parentSemi - STRINGS[form.rootString].semitone + 12) % 12;
        for (let k = -1; k <= 1; k++) {
            const lo = rootFret + form.lo + 12 * k;
            const hi = rootFret + form.hi + 12 * k;
            if (Math.min(hi, maxF) - Math.max(lo, 0) >= 3) return { lo: Math.max(lo, 0), hi: Math.min(hi, maxF) };
        }
        return { lo: 0, hi: maxF };
    }

    // Intervals (from the scale root) that count as chord tones: 1, 3, 5 and 7 when the scale has them
    function getChordToneIntervals(intervals) {
        const pick = (...opts) => opts.find(i => intervals.includes(i));
        return [0, pick(4, 3), pick(7, 6), pick(10, 11)].filter(i => i !== undefined);
    }

    // Notes of the exercise inside the CAGED window: [{ midi, semi }] sorted low → high
    function getPracticeNotes() {
        const { exercise, form } = fbState.practice;
        const win = getCagedWindow(form);
        const ps = getPracticeScale();
        const def = SCALES[ps.key] || SCALES['major'];
        const rootSemi = noteToSemitone(ps.root);
        let allowed = getScaleIntervals(ps.key);
        if (exercise === 'chord') allowed = getChordToneIntervals(def.intervals);
        if (exercise === 'chord_char') {
            const chars = (CHARACTERISTIC_INTERVALS[ps.key] || []).filter(i => def.intervals.includes(i));
            allowed = [...new Set([...getChordToneIntervals(def.intervals), ...chars, ...getBluesAdditions(def.intervals)])];
        }
        const seen = new Set();
        const notes = [];
        STRINGS.forEach(str => {
            for (let f = win.lo; f <= win.hi; f++) {
                const midi = str.midi + f;
                const semi = (str.semitone + f) % 12;
                if (!allowed.includes((semi - rootSemi + 12) % 12) || seen.has(midi)) continue;
                seen.add(midi);
                notes.push({ midi, semi });
            }
        });
        return notes.sort((a, b) => a.midi - b.midi);
    }

    // Sistema 3-1-3: from the lowest tonic up, take 3 scale notes, then 1 on the next string, then 3, and so on.
    // Each group continues from the pitch where the previous one stopped. Returns [{ sIdx, f, midi, size }]
    function getPattern313() {
        const win = getCagedWindow(fbState.practice.form);
        const ps = getPracticeScale();
        const intervals = getScaleIntervals(ps.key);
        const rootSemi = noteToSemitone(ps.root);
        const out = [];
        // Start on the lowest tonic in the window so the pattern is anchored on the root
        let startS = STRINGS.length - 1, lastMidi = -1, lowest = Infinity;
        STRINGS.forEach((str, sIdx) => {
            for (let f = win.lo; f <= win.hi; f++) {
                if ((str.semitone + f) % 12 === rootSemi && str.midi + f < lowest) {
                    lowest = str.midi + f;
                    startS = sIdx;
                    lastMidi = lowest - 1;
                }
            }
        });
        for (let sIdx = startS, g = 0; sIdx >= 0; sIdx--, g++) {
            const want = g % 2 === 0 ? 3 : 1;
            const str = STRINGS[sIdx];
            let taken = 0;
            for (let f = win.lo; f <= win.hi && taken < want; f++) {
                const midi = str.midi + f;
                if (midi <= lastMidi) continue;
                if (!intervals.includes(((str.semitone + f) % 12 - rootSemi + 12) % 12)) continue;
                out.push({ sIdx, f, midi, size: want });
                taken++;
            }
            if (taken) lastMidi = out[out.length - 1].midi;
        }
        return out;
    }

    // Melodic sequences over the ascending note list. A null entry is a rest.
    function buildSequence(exercise, asc) {
        const n = asc.length;
        const out = [];
        const pick = i => asc[i];
        // Slide a window of `size` degrees along the scale, one degree at a time
        const groups = size => {
            for (let i = 0; i + size <= n; i++) for (let k = 0; k < size; k++) out.push(pick(i + k));
            return out;
        };
        switch (exercise) {
            case 'thirds':
                for (let i = 0; i + 2 < n; i++) out.push(pick(i), pick(i + 2));
                return out;
            case 'group3': return groups(3);
            case 'group4': return groups(4);
            case 'arp_scale': {
                const ps = getPracticeScale();
                const tones = getChordToneIntervals((SCALES[ps.key] || SCALES['major']).intervals);
                const rootSemi = noteToSemitone(ps.root);
                const arp = asc.filter(m => tones.includes(((m % 12) - rootSemi + 12) % 12));
                return arp.concat(asc.slice().reverse().filter(m => m < arp[arp.length - 1]));
            }
            case 'zigzag':
                for (let i = 0; i + 2 < n; i++) out.push(pick(i), pick(i + 2), pick(i + 1));
                return out.length ? out : asc;
            case 'zigzag_inv':
                for (let i = n - 1; i - 2 >= 0; i--) out.push(pick(i), pick(i - 2), pick(i - 1));
                return out.length ? out : asc;
            case 'call_resp':
                // Short 4-note phrase, then 4 steps of silence so the line breathes
                for (let i = 0; i + 3 < n; i += 2) {
                    out.push(pick(i), pick(i + 2), pick(i + 1), pick(i + 3), null, null, null, null);
                }
                return out.length ? out : asc;
            case 'landing': {
                // Random walk by scale steps (new phrase every loop) that always ends on a 1, 3 or 7
                const ps = getPracticeScale();
                const rootSemi = noteToSemitone(ps.root);
                const isTarget = m => [0, 3, 4, 10, 11].includes(((m % 12) - rootSemi + 12) % 12);
                let idx = Math.max(0, asc.findIndex(m => m % 12 === rootSemi));
                out.push(pick(idx));
                for (let step = 0; step < 11; step++) {
                    const move = [-2, -1, 1, 2][Math.floor(Math.random() * 4)];
                    idx = Math.min(n - 1, Math.max(0, idx + move));
                    out.push(pick(idx));
                }
                let land = idx;
                for (let d = 0; d < n && !isTarget(asc[land]); d++) {
                    const cands = [idx + d, idx - d].filter(i => i >= 0 && i < n && isTarget(asc[i]));
                    if (cands.length) { land = cands[0]; break; }
                }
                out.push(pick(land));
                return out;
            }
        }
        return asc;
    }

    function getPracticeSequence() {
        const asc = fbState.practice.show313
            ? getPattern313().map(n => n.midi)
            : getPracticeNotes().map(n => n.midi);
        const desc = asc.slice().reverse();
        switch (fbState.practice.exercise) {
            case 'desc': return desc;
            case 'updown': return asc.concat(desc.slice(1));
            case 'asc': case 'chord': case 'chord_char': return asc;
            default: return buildSequence(fbState.practice.exercise, asc);
        }
    }

    let practiceTimers = [];

    function clearNoteHighlight() {
        document.querySelectorAll('.fret-note-group.playing-note').forEach(g => g.classList.remove('playing-note'));
    }

    function highlightPlayingNote(midi) {
        clearNoteHighlight();
        if (!fbState.containerEl) return;
        fbState.containerEl.querySelectorAll(`.fret-note-group[data-midi="${midi}"]`)
            .forEach(g => g.classList.add('playing-note'));
    }

    function syncPracticePanel() {
        const panel = document.getElementById('improv-practice-panel');
        if (!panel) return;
        const p = fbState.practice;
        const playBtn = panel.querySelector('#practice-play');
        if (playBtn) {
            playBtn.innerHTML = p.playing
                ? '<i class="ph-fill ph-stop"></i> Parar'
                : '<i class="ph-fill ph-play"></i> Play';
        }
        const scaleLabel = panel.querySelector('#practice-scale-label');
        if (scaleLabel) {
            const ps = getPracticeScale();
            scaleLabel.textContent = `${dn(ps.root)} ${(SCALES[ps.key] || SCALES['major']).name}${fbState.bluesActive ? ' + Blues' : ''}`;
        }
        panel.querySelectorAll('[data-caged]').forEach(btn => {
            const on = btn.dataset.caged === p.form;
            btn.style.background = on ? 'var(--theme-accent, #6366f1)' : 'rgba(255,255,255,0.04)';
            btn.style.color = on ? '#fff' : 'var(--text-secondary)';
        });
        const bpmLabel = panel.querySelector('#practice-bpm-label');
        if (bpmLabel) bpmLabel.textContent = `${p.bpm} BPM`;
        const bpmSlider = panel.querySelector('#practice-bpm');
        if (bpmSlider) bpmSlider.value = p.bpm;
    }

    function clearPracticeTimers() {
        practiceTimers.forEach(clearTimeout);
        practiceTimers = [];
    }

    function stopPractice() {
        clearPracticeTimers();
        clearNoteHighlight();
        if (fbState.practice.playing) {
            fbState.practice.playing = false;
            syncPracticePanel();
        }
    }

    // Plays the exercise on a loop until stopped; calling it again swaps in the current scale without a pause
    function startPractice(fromTonic = false) {
        clearPracticeTimers();
        let seq = getPracticeSequence();
        if (fromTonic) {
            // Begin on the first tonic in playing order (lowest going up, highest going down)
            const rootSemi = noteToSemitone(getPracticeScale().root);
            const tonicIdx = seq.findIndex(m => m !== null && m % 12 === rootSemi);
            if (tonicIdx > 0) seq = seq.slice(tonicIdx);
        }
        if (!seq.length) return stopPractice();
        const stepMs = 60000 / fbState.practice.bpm / 2; // eighth notes
        fbState.practice.playing = true;
        syncPracticePanel();
        seq.forEach((midi, idx) => {
            if (midi === null) return; // rest
            practiceTimers.push(setTimeout(() => {
                playFretboardNote(midi);
                highlightPlayingNote(midi);
            }, idx * stepMs));
        });
        practiceTimers.push(setTimeout(() => startPractice(), seq.length * stepMs));
    }

    function restartIfPlaying(fromTonic = false) {
        if (fbState.practice.playing) startPractice(fromTonic);
    }

    function refreshFretboardView() {
        fbState.practice.lastWin = getCagedWindow(fbState.practice.form);
        if (fbState.containerEl) renderSVG(fbState.containerEl);
        syncPracticePanel();
    }

    function renderPracticePanel() {
        const panel = document.getElementById('improv-practice-panel');
        if (!panel) return;
        const p = fbState.practice;
        const chipStyle = 'padding: 4px 10px; font-size: 11.5px; border-radius: 6px; border: 1px solid var(--border-hairline-light); cursor: pointer; font-weight: 600;';
        panel.innerHTML = `
            <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px;">
                <span style="font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-tertiary); font-weight: 700;">Práctica · <span id="practice-scale-label" style="color: var(--text-primary);"></span></span>
            </div>
            <select id="practice-exercise" class="select-field" style="padding: 5px 8px; font-size: 12.5px; width: 100%;">
                ${PRACTICE_EXERCISES.map(e => `<option value="${e.id}" ${e.id === p.exercise ? 'selected' : ''}>${e.label}</option>`).join('')}
            </select>
            <div style="display: flex; align-items: center; gap: 6px; flex-wrap: wrap;">
                <span style="font-size: 11px; color: var(--text-tertiary); font-weight: 700; text-transform: uppercase;">CAGED</span>
                ${['C', 'A', 'G', 'E', 'D'].map(k => `<button type="button" data-caged="${k}" title="Forma ${k}" style="${chipStyle}">${k}</button>`).join('')}
                <button type="button" data-caged="all" title="Todas las formas (conectado)" style="${chipStyle}">Todas</button>
            </div>
            <div style="position: relative; display: flex; align-items: center; gap: 6px; flex-wrap: wrap;">
                <label style="display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text-secondary); cursor: pointer;">
                    <input type="checkbox" id="practice-313" ${p.show313 ? 'checked' : ''} style="accent-color: #22d3ee;">
                    Ver patrón <strong style="color: var(--text-primary);">3-1-3</strong>
                    <span style="display: inline-flex; align-items: center; gap: 4px;"><span style="width: 10px; height: 10px; border-radius: 50%; border: 2.5px solid #22d3ee;"></span>3 notas</span>
                    <span style="display: inline-flex; align-items: center; gap: 4px;"><span style="width: 10px; height: 10px; border-radius: 50%; border: 2.5px solid #e879f9;"></span>1 nota</span>
                </label>
                <button type="button" id="practice-313-info" title="Picking y dedos" aria-label="Picking y dedos" style="display: ${p.show313 ? 'inline-flex' : 'none'}; align-items: center; justify-content: center; width: 20px; height: 20px; padding: 0; border-radius: 50%; border: 1px solid rgba(34,211,238,0.5); background: rgba(34,211,238,0.1); color: #22d3ee; font-size: 12px; font-weight: 700; cursor: pointer;">i</button>
                <div id="practice-313-tip" hidden style="position: absolute; top: calc(100% + 6px); left: 0; right: 0; z-index: 50; font-size: 11.5px; line-height: 1.5; color: var(--text-primary); background: #18181b; border: 1px solid rgba(34,211,238,0.4); border-radius: 8px; padding: 8px 12px; box-shadow: 0 8px 24px rgba(0,0,0,0.6);">
                    <strong style="color: #22d3ee;">Picking:</strong> alterna púa abajo/arriba en cada grupo de 3. Con economy picking, la nota suelta y la primera del siguiente grupo van en el mismo sentido.
                    <br><strong style="color: #22d3ee;">Dedos:</strong> 1-2-4 o 1-3-4 en los grupos de 3, según la forma. Indicación genérica, no del PDF.
                </div>
            </div>
            <div style="display: flex; align-items: center; gap: 10px;">
                <button type="button" id="practice-play" class="btn btn-primary" style="justify-content: center; padding: 8px 22px; font-size: 14px; font-weight: 700; background: var(--theme-accent, #6366f1); border-color: var(--theme-accent, #6366f1); color: #fff;"></button>
                <input type="range" id="practice-bpm" min="40" max="200" step="5" value="${p.bpm}" style="flex: 1; accent-color: var(--theme-accent, #6366f1);">
                <span id="practice-bpm-label" style="font-family: 'Geist Mono', monospace; font-size: 12px; color: var(--text-secondary); min-width: 62px; text-align: right;"></span>
            </div>
        `;
        panel.querySelector('#practice-exercise').addEventListener('change', e => {
            p.exercise = e.target.value;
            restartIfPlaying();
            refreshFretboardView();
        });
        panel.querySelectorAll('[data-caged]').forEach(btn => btn.addEventListener('click', () => {
            p.form = btn.dataset.caged;
            restartIfPlaying();
            refreshFretboardView();
        }));
        panel.querySelector('#practice-313').addEventListener('change', e => {
            p.show313 = e.target.checked;
            restartIfPlaying();
            panel.querySelector('#practice-313-info').style.display = p.show313 ? 'inline-flex' : 'none';
            if (!p.show313) panel.querySelector('#practice-313-tip').hidden = true;
            refreshFretboardView();
        });
        const tip313 = panel.querySelector('#practice-313-tip');
        panel.querySelector('#practice-313-info').addEventListener('click', () => { tip313.hidden = !tip313.hidden; });
        panel.querySelector('#practice-bpm').addEventListener('input', e => {
            p.bpm = parseInt(e.target.value, 10);
            syncPracticePanel();
        });
        panel.querySelector('#practice-play').addEventListener('click', () => {
            if (p.playing) stopPractice(); else startPractice();
        });
        syncPracticePanel();
    }

    // Render SVG Fretboard
    function renderSVG(container) {
        const svgW = 1040;
        const svgH = 220;
        const nutX = 60;
        const endX = 1010;
        const totalFrets = fbState.maxFrets;
        const fretWidth = (endX - nutX) / totalFrets;

        const scaleMap1 = getScaleMap(fbState.root1, fbState.scaleKey1);
        const scaleMap2 = fbState.fusionActive ? getScaleMap(fbState.root2, fbState.scaleKey2) : null;
        const practiceWin = getCagedWindow(fbState.practice.form);
        const practiceMidis = new Set(getPracticeNotes().map(n => n.midi));
        const pattern313 = fbState.practice.show313 ? getPattern313() : null;
        const pattern313Map = pattern313 ? new Map(pattern313.map((n, i) => [`${n.sIdx}:${n.f}`, { ...n, order: i + 1 }])) : null;

        // Collect transition notes analysis
        let transitionInfo = null;
        if (fbState.fusionActive) {
            const sharedSemis = [];
            const only1Semis = [];
            const only2Semis = [];

            for (let s = 0; s < 12; s++) {
                const in1 = scaleMap1.has(s);
                const in2 = scaleMap2.has(s);
                if (in1 && in2) sharedSemis.push(s);
                else if (in1) only1Semis.push(s);
                else if (in2) only2Semis.push(s);
            }

            transitionInfo = {
                sharedCount: sharedSemis.length,
                only1Notes: only1Semis.map(s => dn(CHROMATIC_SHARP[s])),
                only2Notes: only2Semis.map(s => dn(CHROMATIC_SHARP[s])),
                diffCount: only1Semis.length + only2Semis.length
            };
        }

        let svgHtml = `
        <svg viewBox="0 0 ${svgW} ${svgH}" class="guitar-fretboard-svg" style="width: 100%; height: auto; display: block; border-radius: 8px; user-select: none;">
            <defs>
                <linearGradient id="fretboardWood" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stop-color="#141519" />
                    <stop offset="50%" stop-color="#181920" />
                    <stop offset="100%" stop-color="#111215" />
                </linearGradient>
                <linearGradient id="nutGrad" x1="0" y1="0" x2="1" y2="0">
                    <stop offset="0%" stop-color="#cbd5e1" />
                    <stop offset="50%" stop-color="#f8fafc" />
                    <stop offset="100%" stop-color="#94a3b8" />
                </linearGradient>
                <filter id="badgeGlow" x="-30%" y="-30%" width="160%" height="160%">
                    <feDropShadow dx="0" dy="2" stdDeviation="3" flood-color="rgba(0,0,0,0.6)" />
                </filter>
            </defs>

            <!-- Fretboard Body -->
            <rect x="${nutX}" y="24" width="${endX - nutX}" height="152" rx="4" fill="url(#fretboardWood)" stroke="#27272a" stroke-width="1.5" />
        `;

        // Position Inlays
        const inlays = [3, 5, 7, 9, 15];
        inlays.forEach(fretNum => {
            if (fretNum <= totalFrets) {
                const centerX = nutX + (fretNum - 0.5) * fretWidth;
                svgHtml += `<circle cx="${centerX}" cy="100" r="7.5" fill="rgba(255, 255, 255, 0.15)" />`;
            }
        });

        // 12th Fret Double Inlay
        if (totalFrets >= 12) {
            const centerX12 = nutX + (12 - 0.5) * fretWidth;
            svgHtml += `
                <circle cx="${centerX12}" cy="65" r="6" fill="rgba(255, 255, 255, 0.18)" />
                <circle cx="${centerX12}" cy="135" r="6" fill="rgba(255, 255, 255, 0.18)" />
            `;
        }

        // Fret Wires (Vertical Lines)
        for (let i = 1; i <= totalFrets; i++) {
            const fx = nutX + i * fretWidth;
            svgHtml += `
                <line x1="${fx}" y1="24" x2="${fx}" y2="176" stroke="#475569" stroke-width="2.5" />
                <line x1="${fx - 0.8}" y1="24" x2="${fx - 0.8}" y2="176" stroke="#94a3b8" stroke-width="0.8" opacity="0.6" />
            `;
        }

        // Nut (Cejuela at Fret 0)
        svgHtml += `
            <rect x="${nutX - 6}" y="22" width="7" height="156" rx="2" fill="url(#nutGrad)" stroke="#64748b" stroke-width="1" />
        `;

        // Strings (Horizontal Lines)
        STRINGS.forEach((str, sIdx) => {
            const y = 38 + sIdx * 25;
            svgHtml += `
                <line x1="${nutX}" y1="${y + 1}" x2="${endX}" y2="${y + 1}" stroke="rgba(0,0,0,0.5)" stroke-width="${str.gauge}" />
                <line x1="20" y1="${y}" x2="${endX}" y2="${y}" stroke="#94a3b8" stroke-width="${str.gauge}" />
                <line x1="20" y1="${y - 0.5}" x2="${endX}" y2="${y - 0.5}" stroke="#f8fafc" stroke-width="${Math.max(0.6, str.gauge * 0.35)}" opacity="0.8" />
                <text x="14" y="${y + 4}" fill="#64748b" font-family="'Geist Mono', monospace" font-size="12" font-weight="700" text-anchor="middle">${str.name}</text>
            `;
        });

        // Fret Numbers at bottom
        [1, 3, 5, 7, 9, 12, 15].forEach(fretNum => {
            if (fretNum <= totalFrets) {
                const centerX = nutX + (fretNum - 0.5) * fretWidth;
                svgHtml += `
                    <text x="${centerX}" y="200" fill="#94a3b8" font-family="'Geist Mono', monospace" font-size="12" font-weight="600" text-anchor="middle">${fretNum}</text>
                `;
            }
        });

        // Notes on Frets
        STRINGS.forEach((str, sIdx) => {
            const y = 38 + sIdx * 25;

            for (let f = 0; f <= totalFrets; f++) {
                const semitone = (str.semitone + f) % 12;
                const midi = str.midi + f;
                const noteName = dn(CHROMATIC_SHARP[semitone]);

                const noteData1 = scaleMap1.get(semitone);
                const noteData2 = scaleMap2 ? scaleMap2.get(semitone) : null;

                if (!noteData1 && !noteData2) continue;

                const cx = f === 0 ? nutX - 22 : nutX + (f - 0.5) * fretWidth;

                let fillColor = '#18181b';
                let strokeColor = '#3f3f46';
                let strokeWidth = 2;
                let textColor = '#ffffff';
                let labelText = '';
                let isPulse = false;
                let tooltip = '';
                let strokeDash = '';

                const applyRole = (scaleKey, noteData) => {
                    const s = getRoleStyle(scaleKey, noteData);
                    fillColor = s.fill;
                    strokeColor = s.stroke;
                    strokeWidth = s.width;
                    textColor = s.text;
                    strokeDash = s.dash;
                    labelText = fbState.labelType === 'notes' ? noteName : noteData.degree;
                    return s.label;
                };

                if (!fbState.fusionActive) {
                    const roleLabel = applyRole(fbState.scaleKey1, noteData1);
                    tooltip = `${noteName} (Grado ${noteData1.degree}) · ${roleLabel} - Cuerda ${sIdx + 1}, Traste ${f}`;
                } else {
                    const in1 = !!noteData1;
                    const in2 = !!noteData2;
                    const target = `${dn(fbState.root2)} ${SCALES[fbState.scaleKey2].name}`;

                    if (in2) {
                        const roleLabel = applyRole(fbState.scaleKey2, noteData2);
                        if (in1) {
                            tooltip = `${noteName} (${noteData2.degree} en ${target}) · ${roleLabel} · Común a ambos modos`;
                        } else {
                            isPulse = true;
                            tooltip = `¡NOTA DE CAMBIO! ${noteName} (${noteData2.degree}) · ${roleLabel} · No está en ${dn(fbState.root1)} ${SCALES[fbState.scaleKey1].name}`;
                        }
                    } else if (in1) {
                        fillColor = '#3b82f6';
                        strokeColor = '#1d4ed8';
                        textColor = '#ffffff';
                        const degreeVsTarget = INTERVAL_NAMES[(semitone - noteToSemitone(fbState.root2) + 12) % 12];
                        labelText = fbState.labelType === 'notes' ? noteName : degreeVsTarget;
                        tooltip = `${noteName} (${degreeVsTarget} respecto a ${dn(fbState.root2)}): Solo en ${dn(fbState.root1)} ${SCALES[fbState.scaleKey1].name} — déjala al pasar a ${target}`;
                    }
                }

                // Fade notes outside the chosen CAGED shape / exercise scale
                let noteOpacity = 1;
                if (f < practiceWin.lo || f > practiceWin.hi) noteOpacity = 0.12;
                else if (!practiceMidis.has(midi)) noteOpacity = 0.4;
                const p313 = pattern313Map ? pattern313Map.get(`${sIdx}:${f}`) : null;
                if (pattern313Map && f >= practiceWin.lo && f <= practiceWin.hi) noteOpacity = p313 ? 1 : 0.15;
                const ring313 = p313
                    ? `<circle cx="${cx}" cy="${y}" r="16" fill="none" stroke="${p313.size === 3 ? '#22d3ee' : '#e879f9'}" stroke-width="3" />
                       <text x="${cx + 13}" y="${y - 12}" fill="${p313.size === 3 ? '#22d3ee' : '#e879f9'}" font-family="'Geist Mono', monospace" font-size="10" font-weight="700" text-anchor="middle" pointer-events="none">${p313.order}</text>`
                    : '';

                svgHtml += `
                    <g class="fret-note-group" data-midi="${midi}" opacity="${noteOpacity}" style="cursor: pointer;" title="${tooltip}">
                        ${isPulse ? `<circle cx="${cx}" cy="${y}" r="15" fill="none" stroke="#f59e0b" stroke-width="2" opacity="0.6" />` : ''}
                        ${ring313}
                        <circle cx="${cx}" cy="${y}" r="12.5" fill="${fillColor}" stroke="${strokeColor}" stroke-width="${strokeWidth}" ${strokeDash ? `stroke-dasharray="${strokeDash}"` : ''} filter="url(#badgeGlow)" />
                        <text x="${cx}" y="${y + 4.2}" fill="${textColor}" font-family="'Geist Mono', sans-serif" font-size="${labelText.length > 2 ? '10' : '11.5'}" font-weight="700" text-anchor="middle" pointer-events="none">${labelText}</text>
                    </g>
                `;
            }
        });

        svgHtml += `</svg>`;

        // Legend & Explanations Container
        let legendHtml = '';
        const dot = (style) => `<span style="width: 12px; height: 12px; border-radius: 50%; display: inline-block; ${style}"></span>`;
        if (!fbState.fusionActive) {
            const def = SCALES[fbState.scaleKey1] || SCALES['major'];
            const roles = NOTE_ROLES[fbState.scaleKey1] || { chord: [], characteristic: [], avoid: [] };
            const hasChord = roles.chord.some(d => d !== '1');
            const hasChar = roles.characteristic.length > 0;
            const hasAvoid = roles.avoid.length > 0;
            const charNotes = [...scaleMap1.values()]
                .filter(d => roles.characteristic.includes(d.degree))
                .map(d => `${d.noteName} (${d.degree})`).join(', ');
            const avoidMsg = describeAvoidNotes(scaleMap1, fbState.scaleKey1);
            legendHtml = `
                <div class="fretboard-legend flex flex-col gap-2 mt-3" style="font-size: 13px; color: var(--text-secondary);">
                    <div class="flex items-center justify-between flex-wrap gap-4">
                        <div class="flex items-center gap-4 flex-wrap">
                            <span class="inline-flex items-center gap-2">${dot('background: #ef4444;')} <strong style="color: var(--text-primary);">Tónica</strong> (${dn(fbState.root1)})</span>
                            ${hasChord ? `<span class="inline-flex items-center gap-2">${dot('background: #059669;')} Notas del acorde (destácalas)</span>` : ''}
                            ${hasChar ? `<span class="inline-flex items-center gap-2">${dot('background: #f59e0b;')} <strong style="color: #f59e0b;">Característica</strong></span>` : ''}
                            ${hasAvoid ? `<span class="inline-flex items-center gap-2">${dot('background: #09090b; border: 1.5px dashed #a1a1aa;')} Evitar / solo de paso</span>` : ''}
                            <span class="inline-flex items-center gap-2">${dot('background: #09090b; border: 1px solid #52525b;')} Otras notas de la escala</span>
                        </div>
                        <span class="text-xs" style="color: var(--text-tertiary);"><i class="ph ph-hand-pointing"></i> Haz clic en cualquier nota para escucharla</span>
                    </div>
                    <div style="font-size: 12px; color: var(--text-secondary); background: rgba(255,255,255,0.03); padding: 6px 10px; border-radius: 6px; border: 1px solid var(--border-hairline-light); line-height: 1.6;">
                        <em>${def.desc}</em>
                        ${hasChar ? `<br><i class="ph ph-sparkle" style="color: #f59e0b;"></i> Destaca <strong style="color: #f59e0b; font-family: 'Geist Mono', monospace;">${charNotes}</strong> para que suene a ${dn(fbState.root1)} ${def.name}.` : ''}
                        ${avoidMsg ? `<br><i class="ph ph-warning" style="color: #a1a1aa;"></i> No te detengas en ${avoidMsg}.` : ''}
                    </div>
                </div>
            `;
        } else {
            const def1 = SCALES[fbState.scaleKey1] || SCALES['major'];
            const def2 = SCALES[fbState.scaleKey2] || SCALES['major'];
            const items = fbState.songModes ? (fbState.songModes.transitionItems || []) : [];
            let activeItem = fbState.activeTransitionItem;
            if (!activeItem && items.length > 0) {
                activeItem = items.find(it => it.root === fbState.root2 && it.scaleKey === fbState.scaleKey2) || items[0];
            }
            let activeIdx = fbState.activeTransitionIndex;
            if (activeIdx < 0 && activeItem) {
                activeIdx = items.indexOf(activeItem);
            }
            if (activeIdx < 0 && items.length > 0) activeIdx = 0;

            const diffMsg = (transitionInfo && transitionInfo.only2Notes.length > 0)
                ? `Al modular a <strong>${dn(fbState.root2)} ${def2.name}</strong>, las notas que marcan la diferencia son: <span style="color: #f59e0b; font-weight: 700; font-family: 'Geist Mono';">${transitionInfo.only2Notes.join(', ')}</span>. ¡Enfócalas para crear el impacto modal!`
                : `Ambos modos comparten exactamente las mismas notas (son modos relativos con diferente centro tonal / tónica).`;

            const roles2 = NOTE_ROLES[fbState.scaleKey2] || { chord: [], characteristic: [], avoid: [] };
            const charNotes2 = [...scaleMap2.values()]
                .filter(d => roles2.characteristic.includes(d.degree))
                .map(d => `${d.noteName} (${d.degree})`).join(', ');
            const avoidMsg2 = describeAvoidNotes(scaleMap2, fbState.scaleKey2);

            legendHtml = `
                <div class="fretboard-legend flex flex-col gap-2 mt-3" style="font-size: 13px;">
                    <div class="flex items-center justify-between flex-wrap gap-4" style="color: var(--text-secondary);">
                        <div class="flex items-center gap-4 flex-wrap">
                            <span class="inline-flex items-center gap-2">${dot('background: #ef4444;')} <strong style="color: var(--text-primary);">Tónica</strong> (${dn(fbState.root2)})</span>
                            ${roles2.chord.some(d => d !== '1') ? `<span class="inline-flex items-center gap-2">${dot('background: #059669;')} Notas del acorde</span>` : ''}
                            ${roles2.characteristic.length ? `<span class="inline-flex items-center gap-2">${dot('background: #f59e0b;')} <strong style="color: #f59e0b;">Característica</strong></span>` : ''}
                            ${roles2.avoid.length ? `<span class="inline-flex items-center gap-2">${dot('background: #09090b; border: 1.5px dashed #a1a1aa;')} Evitar / solo de paso</span>` : ''}
                            <span class="inline-flex items-center gap-2">${dot('background: #09090b; border: 1px solid #52525b; box-shadow: 0 0 0 2px #090a0d, 0 0 0 3.5px rgba(245, 158, 11, 0.7);')} <strong style="color: #f59e0b;">Nota de cambio</strong> (nueva)</span>
                            <span class="inline-flex items-center gap-2">${dot('background: #3b82f6;')} Solo en ${dn(fbState.root1)} ${def1.name}</span>
                        </div>
                        <div style="color: var(--text-tertiary); font-size: 11.5px;">
                            <i class="ph ph-hand-pointing"></i> Haz clic en cualquier nota para escucharla
                        </div>
                    </div>

                    <!-- Modal Transition Chord Card -->
                    <div class="modal-transition-card" style="background: linear-gradient(135deg, rgba(245, 158, 11, 0.09) 0%, rgba(18, 20, 26, 0.8) 100%); border: 1px solid rgba(245, 158, 11, 0.28); border-left: 4px solid #f59e0b; padding: 12px 16px; border-radius: 8px; margin-top: 4px; display: flex; flex-direction: column; gap: 8px;">
                        <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px;">
                            <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                                ${activeItem && activeItem.chord ? `
                                    <span class="chip-chord-tag ${activeItem.degree ? 'chord-degree-' + activeItem.degree : ''}" style="font-size: 12.5px; padding: 2.5px 9px;">
                                        <i class="ph ph-music-note"></i> Acorde: <strong>${activeItem.chord}</strong>
                                    </span>
                                    <i class="ph ph-arrow-right" style="color: rgba(255,255,255,0.3); font-size: 12px;"></i>
                                ` : ''}
                                <span style="font-weight: 700; color: #f59e0b; font-size: 13.5px; display: inline-flex; align-items: center; gap: 6px;">
                                    ${dn(fbState.root2)} ${def2.name}
                                </span>
                                ${activeItem && activeItem.keyNotes ? `
                                    <span style="font-size: 11.5px; color: var(--text-secondary); background: rgba(255,255,255,0.04); padding: 2px 8px; border-radius: 4px; border: 1px solid var(--border-hairline-light);">
                                        <strong style="color: #cbd5e1;">Notas clave:</strong> <span style="color: #f8fafc; font-family: 'Geist Mono', monospace;">${activeItem.keyNotes}</span>
                                    </span>
                                ` : ''}
                            </div>

                            ${items.length > 1 ? `
                                <div style="display: flex; align-items: center; gap: 6px;">
                                    <button type="button" class="btn-fb-step btn-fb-step-prev" title="Acorde anterior en la progresión">
                                        <i class="ph ph-caret-left"></i> Anterior
                                    </button>
                                    <span style="font-size: 11px; color: var(--text-tertiary); font-family: 'Geist Mono', monospace; padding: 0 4px;">
                                        ${activeIdx + 1} / ${items.length}
                                    </span>
                                    <button type="button" class="btn-fb-step btn-fb-step-next" title="Acorde siguiente en la progresión">
                                        Siguiente <i class="ph ph-caret-right"></i>
                                    </button>
                                </div>
                            ` : ''}
                        </div>

                        ${activeItem && activeItem.comment ? `
                            <div style="font-size: 12.5px; color: #e2e8f0; line-height: 1.5; padding: 6px 12px; background: rgba(0,0,0,0.32); border-radius: 6px; border-left: 2px solid rgba(245, 158, 11, 0.5);">
                                <strong style="color: #fbbf24; display: inline-flex; align-items: center; gap: 4px; margin-right: 4px;">
                                    <i class="ph ph-chat-circle-text"></i> Consejo:
                                </strong>
                                ${activeItem.comment}
                            </div>
                        ` : ''}

                        <div style="font-size: 12px; color: var(--text-secondary); display: flex; align-items: center; gap: 6px;">
                            <i class="ph ph-sparkle" style="color: #f59e0b; flex-shrink: 0;"></i>
                            <span>${diffMsg}</span>
                        </div>
                        ${charNotes2 || avoidMsg2 ? `
                            <div style="font-size: 12px; color: var(--text-secondary); line-height: 1.6;">
                                ${charNotes2 ? `<div><i class="ph ph-sparkle" style="color: #f59e0b;"></i> Destaca <strong style="color: #f59e0b; font-family: 'Geist Mono', monospace;">${charNotes2}</strong> para que suene a ${dn(fbState.root2)} ${def2.name}.</div>` : ''}
                                ${avoidMsg2 ? `<div><i class="ph ph-warning" style="color: #a1a1aa;"></i> No te detengas en ${avoidMsg2}.</div>` : ''}
                            </div>
                        ` : ''}
                    </div>
                </div>
            `;
        }

        const canvasEl = container.querySelector('.fretboard-canvas-wrapper');
        const legendEl = container.querySelector('.fretboard-legend-wrapper');
        if (fbState.bluesActive) legendHtml += describeBlues();
        if (canvasEl) canvasEl.innerHTML = svgHtml;
        if (legendEl) legendEl.innerHTML = legendHtml;

        // Attach Step Prev / Next button click handlers
        const prevBtn = container.querySelector('.btn-fb-step-prev');
        const nextBtn = container.querySelector('.btn-fb-step-next');
        if (prevBtn) {
            prevBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                const items = fbState.songModes ? (fbState.songModes.transitionItems || []) : [];
                let curIdx = fbState.activeTransitionIndex;
                if (curIdx < 0) curIdx = 0;
                selectTransitionByIndex(container, curIdx - 1);
            });
        }
        if (nextBtn) {
            nextBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                const items = fbState.songModes ? (fbState.songModes.transitionItems || []) : [];
                let curIdx = fbState.activeTransitionIndex;
                if (curIdx < 0) curIdx = 0;
                selectTransitionByIndex(container, curIdx + 1);
            });
        }

        // Attach audio click events
        container.querySelectorAll('.fret-note-group').forEach(el => {
            el.addEventListener('click', () => {
                const midi = parseInt(el.getAttribute('data-midi'));
                if (!isNaN(midi)) {
                    playFretboardNote(midi);
                    el.style.transform = 'scale(1.2)';
                    el.style.transformOrigin = 'center';
                    setTimeout(() => { el.style.transform = 'scale(1)'; }, 150);
                }
            });
        });
    }

    function selectTransitionByIndex(container, newIdx) {
        const items = fbState.songModes ? (fbState.songModes.transitionItems || []) : [];
        if (!items || items.length === 0) return;

        const count = items.length;
        const validIdx = ((newIdx % count) + count) % count;
        const item = items[validIdx];

        fbState.fusionActive = true;
        fbState.root2 = item.root;
        fbState.scaleKey2 = item.scaleKey;
        fbState.activeTransitionIndex = validIdx;
        fbState.activeTransitionItem = item;

        syncUIState(container);
    }

    // Helper to populate select elements dynamically
    function populateDropdown(selectEl, values, selectedVal, textFn) {
        if (!selectEl) return;
        selectEl.innerHTML = values.map(val => {
            const isSel = val === selectedVal ? 'selected' : '';
            const text = textFn ? textFn(val) : val;
            return `<option value="${val}" ${isSel}>${text}</option>`;
        }).join('');
    }

    // Refresh all 4 selectors according to filter (showAll vs songModes)
    function refreshDropdowns(container) {
        if (!container) return;

        const root1El = container.querySelector('#fb-root-1');
        const scale1El = container.querySelector('#fb-scale-1');
        const root2El = container.querySelector('#fb-root-2');
        const scale2El = container.querySelector('#fb-scale-2');

        const sm = fbState.songModes;

        // 1. Root 1
        const availableRoots1 = (fbState.showAll || !sm) ? CHROMATIC_SHARP : sm.baseRoots;
        if (!availableRoots1.includes(fbState.root1)) {
            fbState.root1 = availableRoots1[0] || 'A';
        }
        populateDropdown(root1El, availableRoots1, fbState.root1, dn);

        // 2. Scale 1
        let availableScales1 = Object.keys(SCALES);
        if (!fbState.showAll && sm) {
            const set1 = sm.baseModesMap.get(fbState.root1) || sm.allSongModesMap.get(fbState.root1);
            availableScales1 = set1 && set1.size ? Array.from(set1) : ['major'];
        }
        if (!availableScales1.includes(fbState.scaleKey1)) {
            fbState.scaleKey1 = availableScales1[0] || 'major';
        }
        populateDropdown(scale1El, availableScales1, fbState.scaleKey1, k => SCALES[k] ? SCALES[k].name : k);

        // 3. Root 2 (Transition)
        const availableRoots2 = (fbState.showAll || !sm) ? CHROMATIC_SHARP : sm.transitionRoots;
        if (!availableRoots2.includes(fbState.root2)) {
            fbState.root2 = availableRoots2[0] || 'D';
        }
        populateDropdown(root2El, availableRoots2, fbState.root2, dn);

        // 4. Scale 2 (Transition)
        let availableScales2 = Object.keys(SCALES);
        if (!fbState.showAll && sm) {
            const set2 = sm.transitionModesMap.get(fbState.root2) || sm.allSongModesMap.get(fbState.root2);
            availableScales2 = set2 && set2.size ? Array.from(set2) : ['lydian'];
        }
        if (!availableScales2.includes(fbState.scaleKey2)) {
            fbState.scaleKey2 = availableScales2[0] || 'lydian';
        }
        populateDropdown(scale2El, availableScales2, fbState.scaleKey2, k => SCALES[k] ? SCALES[k].name : k);
    }

    // Synchronize quick chip highlights strictly based on current state
    function syncChipsVisual(container) {
        if (!container) return;

        container.querySelectorAll('.btn-quick-scale').forEach(chip => {
            chip.classList.remove('active-base', 'active-target');

            const category = chip.getAttribute('data-category');
            const cRoot = chip.getAttribute('data-root');
            const cScale = chip.getAttribute('data-scale');
            const cIdx = parseInt(chip.getAttribute('data-idx'));

            if (!fbState.fusionActive) {
                // In single mode: highlight currently selected mode
                if (cRoot === fbState.root1 && cScale === fbState.scaleKey1) {
                    chip.classList.add('active-base');
                }
            } else {
                // In fusion mode:
                // Base mode gets purple/accent highlight
                if (category === 'base' && cRoot === fbState.root1 && cScale === fbState.scaleKey1) {
                    chip.classList.add('active-base');
                }
                // Target mode gets amber/gold highlight
                if (category === 'transition') {
                    if (!isNaN(cIdx) && fbState.activeTransitionIndex >= 0) {
                        if (cIdx === fbState.activeTransitionIndex) {
                            chip.classList.add('active-target');
                        }
                    } else if (cRoot === fbState.root2 && cScale === fbState.scaleKey2) {
                        chip.classList.add('active-target');
                    }
                }
            }
        });
    }

    // Master state synchronization: synchronizes controls, chips, dropdowns, and SVG
    function syncUIState(container) {
        if (!container) return;

        // On a mode change, move to the nearest CAGED shape; if playing, carry straight on with the new mode
        const p = fbState.practice;
        const ps = getPracticeScale();
        const sig = `${fbState.fusionActive}|${ps.root}|${ps.key}`;
        const modeChanged = sig !== p.lastScaleSig;
        p.lastScaleSig = sig;
        if (modeChanged) {
            if (p.form !== 'all' && p.lastWin) {
                const prevCenter = (p.lastWin.lo + p.lastWin.hi) / 2;
                const dist = k => {
                    const w = getCagedWindow(k);
                    return Math.abs((w.lo + w.hi) / 2 - prevCenter);
                };
                p.form = ['C', 'A', 'G', 'E', 'D'].reduce((best, k) => dist(k) < dist(best) ? k : best);
            }
            if (p.playing) startPractice(true);
        }

        const fusionToggle = container.querySelector('#fb-fusion-toggle');
        const scale2Controls = container.querySelector('#fb-scale2-controls');
        const fusionLabel = container.querySelector('label[for="fb-fusion-toggle"]');
        const showAllToggle = container.querySelector('#fb-show-all-toggle');
        const showAllLabel = container.querySelector('label[for="fb-show-all-toggle"]');

        if (fusionToggle) fusionToggle.checked = fbState.fusionActive;
        if (scale2Controls) scale2Controls.classList.toggle('hide', !fbState.fusionActive);
        if (fusionLabel) {
            fusionLabel.style.color = fbState.fusionActive ? '#f59e0b' : 'var(--text-secondary)';
        }
        if (showAllToggle) showAllToggle.checked = fbState.showAll;
        const bluesLabel = container.querySelector('label[for="fb-blues-toggle"]');
        if (bluesLabel) bluesLabel.style.color = fbState.bluesActive ? '#a5b4fc' : 'var(--text-secondary)';
        if (showAllLabel) {
            showAllLabel.style.color = fbState.showAll ? '#ffffff' : 'var(--text-secondary)';
        }

        refreshDropdowns(container);
        syncChipsVisual(container);
        renderSVG(container);
        syncPracticePanel();
        fbState.practice.lastWin = getCagedWindow(fbState.practice.form);
    }

    // Render Full Fretboard Component UI (Controls + Canvas + Legend)
    function renderComponent(container) {
        fbState.containerEl = container;

        container.innerHTML = `
            <div class="fretboard-box double-bezel" style="background: #090a0d; border: 1px solid var(--border-hairline); border-radius: 14px; padding: 18px 20px;">
                
                <!-- Quick Preset Chips: Row 1 (Base Tonality & View Toggle) -->
                <div class="fretboard-presets-row-1 mb-2" style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px;">
                    <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                        <span style="font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-tertiary); font-weight: 700; display: inline-flex; align-items: center; gap: 4px; white-space: nowrap;">
                            <i class="ph ph-music-note"></i> Base:
                        </span>
                        <div id="fretboard-base-chips" style="display: flex; align-items: center; gap: 6px; flex-wrap: wrap;">
                            <!-- Populated with base modes -->
                        </div>
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px; flex-shrink: 0;">
                        <div class="btn-group" style="display: flex; background: rgba(255,255,255,0.04); padding: 2px; border-radius: 8px; border: 1px solid var(--border-hairline-light);">
                            <button type="button" class="btn-chip ${fbState.labelType === 'degrees' ? 'active' : ''}" id="fb-toggle-degrees" style="padding: 4px 10px; font-size: 11.5px; border-radius: 6px; border: none; background: ${fbState.labelType === 'degrees' ? 'var(--theme-accent, #6366f1)' : 'transparent'}; color: #fff; cursor: pointer;">
                                Grados (1, 2, 3...)
                            </button>
                            <button type="button" class="btn-chip ${fbState.labelType === 'notes' ? 'active' : ''}" id="fb-toggle-notes" style="padding: 4px 10px; font-size: 11.5px; border-radius: 6px; border: none; background: ${fbState.labelType === 'notes' ? 'var(--theme-accent, #6366f1)' : 'transparent'}; color: #fff; cursor: pointer;">
                                Notas (A, B, C#...)
                            </button>
                        </div>
                    </div>
                </div>

                <!-- Quick Preset Chips: Row 2 (Modal Chord Transitions) -->
                <div class="fretboard-presets-row-2 mb-3" style="padding-top: 8px; border-top: 1px dashed rgba(255,255,255,0.07); display: flex; align-items: flex-start; gap: 10px;">
                    <div id="fretboard-transition-chips" style="display: flex; flex-wrap: wrap; gap: 6px; flex: 1; min-width: 0;">
                        <!-- Populated with transition modes -->
                    </div>
                </div>

                <!-- Custom Selectors, Fusion Toggle & "Ver todos" Checkbox -->
                <div class="fretboard-selectors-row flex items-center justify-between flex-wrap gap-3 pb-3 mb-3" style="border-bottom: 1px solid var(--border-hairline-light);">
                    <div class="flex items-center gap-3 flex-wrap">
                        <div class="flex items-center gap-2">
                            <span style="font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-tertiary); font-weight: 700;">Modo Base:</span>
                            <select id="fb-root-1" class="select-field" style="padding: 4px 8px; font-size: 12.5px; width: 68px;"></select>
                            <select id="fb-scale-1" class="select-field" style="padding: 4px 10px; font-size: 12.5px; min-width: 170px;"></select>
                        </div>

                        <div class="flex items-center gap-2" style="background: rgba(255,255,255,0.03); padding: 4px 10px; border-radius: 8px; border: 1px solid var(--border-hairline-light);">
                            <input type="checkbox" id="fb-fusion-toggle" ${fbState.fusionActive ? 'checked' : ''} style="cursor: pointer; accent-color: #f59e0b;">
                            <label for="fb-fusion-toggle" style="font-size: 12px; cursor: pointer; color: ${fbState.fusionActive ? '#f59e0b' : 'var(--text-secondary)'}; font-weight: 600; display: flex; align-items: center; gap: 4px;">
                                <i class="ph ph-intersect"></i> Fusionar / Transición Modal
                            </label>
                        </div>

                        <div class="flex items-center gap-2" style="background: rgba(255,255,255,0.03); padding: 4px 10px; border-radius: 8px; border: 1px solid var(--border-hairline-light);" title="Convierte el modo en escala de blues: añade la blue note (b5) y, en modos mayores, la b3 (pentatónica mixta)">
                            <input type="checkbox" id="fb-blues-toggle" ${fbState.bluesActive ? 'checked' : ''} style="cursor: pointer; accent-color: #6366f1;">
                            <label for="fb-blues-toggle" style="font-size: 12px; cursor: pointer; color: ${fbState.bluesActive ? '#a5b4fc' : 'var(--text-secondary)'}; font-weight: 600; display: flex; align-items: center; gap: 4px;">
                                <i class="ph ph-music-note"></i> Blues
                            </label>
                        </div>

                        <div class="flex items-center gap-2 ${fbState.fusionActive ? '' : 'hide'}" id="fb-scale2-controls">
                            <span style="font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; color: #f59e0b; font-weight: 700;">Hacia Modo:</span>
                            <select id="fb-root-2" class="select-field" style="padding: 4px 8px; font-size: 12.5px; width: 68px; border-color: rgba(245, 158, 11, 0.4);"></select>
                            <select id="fb-scale-2" class="select-field" style="padding: 4px 10px; font-size: 12.5px; min-width: 170px; border-color: rgba(245, 158, 11, 0.4);"></select>
                        </div>
                    </div>

                    <!-- "Ver todos" Checkbox -->
                    <div class="flex items-center gap-2" style="background: rgba(255,255,255,0.025); padding: 4px 10px; border-radius: 8px; border: 1px solid var(--border-hairline-light);" title="Mostrar todas las notas y escalas sin filtrar por la canción">
                        <input type="checkbox" id="fb-show-all-toggle" ${fbState.showAll ? 'checked' : ''} style="cursor: pointer; accent-color: var(--theme-accent, #6366f1);">
                        <label for="fb-show-all-toggle" style="font-size: 11.5px; cursor: pointer; color: ${fbState.showAll ? '#fff' : 'var(--text-secondary)'}; font-weight: 600; display: flex; align-items: center; gap: 4px;">
                            <i class="ph ph-sliders"></i> Ver todos
                        </label>
                    </div>
                </div>

                <!-- SVG Fretboard Canvas Wrapper -->
                <div class="fretboard-canvas-wrapper" style="overflow-x: auto; -webkit-overflow-scrolling: touch; padding-bottom: 4px;">
                    <!-- SVG injected here -->
                </div>

                <!-- Fretboard Legend & Modal Explanation -->
                <div class="fretboard-legend-wrapper">
                    <!-- Legend injected here -->
                </div>
            </div>
        `;

        // Bind interactive events
        const root1El = container.querySelector('#fb-root-1');
        const scale1El = container.querySelector('#fb-scale-1');
        const root2El = container.querySelector('#fb-root-2');
        const scale2El = container.querySelector('#fb-scale-2');
        const fusionToggle = container.querySelector('#fb-fusion-toggle');
        const showAllToggle = container.querySelector('#fb-show-all-toggle');
        const btnDegrees = container.querySelector('#fb-toggle-degrees');
        const btnNotes = container.querySelector('#fb-toggle-notes');

        root1El.addEventListener('change', (e) => {
            fbState.root1 = e.target.value;
            if (!fbState.showAll && fbState.songModes) {
                const set1 = fbState.songModes.baseModesMap.get(fbState.root1) || fbState.songModes.allSongModesMap.get(fbState.root1);
                const avail = set1 && set1.size ? Array.from(set1) : ['major'];
                if (!avail.includes(fbState.scaleKey1)) fbState.scaleKey1 = avail[0] || 'major';
            }
            syncUIState(container);
        });

        scale1El.addEventListener('change', (e) => {
            fbState.scaleKey1 = e.target.value;
            syncUIState(container);
        });

        root2El.addEventListener('change', (e) => {
            fbState.root2 = e.target.value;
            if (!fbState.showAll && fbState.songModes) {
                const set2 = fbState.songModes.transitionModesMap.get(fbState.root2) || fbState.songModes.allSongModesMap.get(fbState.root2);
                const avail = set2 && set2.size ? Array.from(set2) : ['lydian'];
                if (!avail.includes(fbState.scaleKey2)) fbState.scaleKey2 = avail[0] || 'lydian';
            }
            const items = fbState.songModes ? (fbState.songModes.transitionItems || []) : [];
            const foundIdx = items.findIndex(it => it.root === fbState.root2 && it.scaleKey === fbState.scaleKey2);
            fbState.activeTransitionIndex = foundIdx;
            fbState.activeTransitionItem = foundIdx !== -1 ? items[foundIdx] : null;

            syncUIState(container);
        });

        scale2El.addEventListener('change', (e) => {
            fbState.scaleKey2 = e.target.value;
            const items = fbState.songModes ? (fbState.songModes.transitionItems || []) : [];
            const foundIdx = items.findIndex(it => it.root === fbState.root2 && it.scaleKey === fbState.scaleKey2);
            fbState.activeTransitionIndex = foundIdx;
            fbState.activeTransitionItem = foundIdx !== -1 ? items[foundIdx] : null;

            syncUIState(container);
        });

        fusionToggle.addEventListener('change', (e) => {
            fbState.fusionActive = e.target.checked;
            if (fbState.fusionActive) {
                // When activating fusion, ensure root2 & scaleKey2 point to a sensible transition mode
                const sm = fbState.songModes;
                if (sm && sm.transitionRoots.length) {
                    if (!sm.transitionRoots.includes(fbState.root2)) {
                        fbState.root2 = sm.transitionRoots.find(r => r !== fbState.root1) || sm.transitionRoots[0];
                    }
                    const transScales = Array.from(sm.transitionModesMap.get(fbState.root2) || ['dorian']);
                    if (!transScales.includes(fbState.scaleKey2)) {
                        fbState.scaleKey2 = transScales[0] || 'dorian';
                    }
                }
            }
            syncUIState(container);
        });

        showAllToggle.addEventListener('change', (e) => {
            fbState.showAll = e.target.checked;
            syncUIState(container);
        });

        container.querySelector('#fb-blues-toggle').addEventListener('change', (e) => {
            fbState.bluesActive = e.target.checked;
            restartIfPlaying();
            syncUIState(container);
        });

        btnDegrees.addEventListener('click', () => {
            fbState.labelType = 'degrees';
            btnDegrees.style.background = 'var(--theme-accent, #6366f1)';
            btnNotes.style.background = 'transparent';
            renderSVG(container);
        });

        btnNotes.addEventListener('click', () => {
            fbState.labelType = 'notes';
            btnNotes.style.background = 'var(--theme-accent, #6366f1)';
            btnDegrees.style.background = 'transparent';
            renderSVG(container);
        });

        // Initialize state & render
        syncUIState(container);
    }

    // Default the practice tempo to the song's BPM: read from the sheet's "bpm" column, or looked up
    // (and saved there) by the server the first time
    const songBpmCache = new Map();
    function applySongTempo(song) {
        if (!song || !song.artist || !song.title) return;
        const key = `${song.artist}|${song.title}`;
        if (song.bpm) songBpmCache.set(key, song.bpm);
        const apply = bpm => {
            if (!bpm || !fbState.song || `${fbState.song.artist}|${fbState.song.title}` !== key) return;
            fbState.practice.bpm = Math.min(200, Math.max(40, bpm));
            syncPracticePanel();
        };
        if (songBpmCache.has(key)) return apply(songBpmCache.get(key));
        fetch(`/api/bpm?artist=${encodeURIComponent(song.artist)}&title=${encodeURIComponent(song.title)}&row=${song.row || ''}`)
            .then(r => r.json())
            .then(d => { songBpmCache.set(key, d.bpm); if (d.bpm) song.bpm = d.bpm; apply(d.bpm); })
            .catch(() => {});
    }

    // Configure presets based on active song
    function setupSongPresets(container, song) {
        if (!container || !song) return;

        fbState.song = song;
        applySongTempo(song);
        window.vibemusPreferFlats = typeof window.isFlatKey === 'function' && !!song.tonality && window.isFlatKey(song.tonality);
        fbState.songModes = extractSongModes(song);
        fbState.fusionActive = false; // start clean in single mode
        stopPractice();
        fbState.practice.lastWin = null; // a different song has no previous shape to stay close to

        // Set initial roots and scales from extracted modes
        const sm = fbState.songModes;
        if (sm.baseRoots.length) {
            fbState.root1 = sm.baseRoots[0];
            const baseScales = Array.from(sm.baseModesMap.get(fbState.root1) || ['major']);
            fbState.scaleKey1 = baseScales[0];
        }

        if (sm.transitionItems && sm.transitionItems.length > 0) {
            fbState.activeTransitionIndex = 0;
            fbState.activeTransitionItem = sm.transitionItems[0];
            fbState.root2 = sm.transitionItems[0].root;
            fbState.scaleKey2 = sm.transitionItems[0].scaleKey;
        } else if (sm.transitionRoots.length) {
            const diffRoot = sm.transitionRoots.find(r => r !== fbState.root1) || sm.transitionRoots[0];
            fbState.root2 = diffRoot;
            const transScales = Array.from(sm.transitionModesMap.get(fbState.root2) || ['lydian']);
            fbState.scaleKey2 = transScales[0];
            fbState.activeTransitionIndex = -1;
            fbState.activeTransitionItem = null;
        }

        renderComponent(container);
        renderPracticePanel();

        // Build dynamic quick preset chips across both rows (Base & Transitions)
        const baseChipsContainer = container.querySelector('#fretboard-base-chips');
        const transChipsContainer = container.querySelector('#fretboard-transition-chips');

        const baseChips = [];
        const transChips = [];

        // 1. Primary Base Scale (Tonalidad)
        const baseRoot = sm.baseRoots[0] || fbState.root1;
        const baseScales = Array.from(sm.baseModesMap.get(baseRoot) || ['major']);
        const primaryScale = baseScales[0] || 'major';
        baseChips.push(`
            <button type="button" class="btn-quick-scale" data-category="base" data-root="${baseRoot}" data-scale="${primaryScale}">
                <span style="width: 8px; height: 8px; border-radius: 50%; background: #ef4444; display: inline-block;"></span>
                ${dn(baseRoot)} ${SCALES[primaryScale].name}
            </button>
        `);

        // 2. Pentatonic
        const pentKey = primaryScale.includes('min') ? 'pentatonic_minor' : 'pentatonic_major';
        if (SCALES[pentKey]) {
            baseChips.push(`
                <button type="button" class="btn-quick-scale" data-category="base" data-root="${baseRoot}" data-scale="${pentKey}">
                    <i class="ph ph-lightning"></i>
                    ${dn(baseRoot)} ${SCALES[pentKey].name}
                </button>
            `);
        }

        // Additional base modes for the primary root if any (e.g. dorian if song is minor)
        baseScales.forEach(s => {
            if (s !== primaryScale && s !== pentKey) {
                baseChips.push(`
                    <button type="button" class="btn-quick-scale" data-category="base" data-root="${baseRoot}" data-scale="${s}">
                        <i class="ph ph-music-notes"></i>
                        ${dn(baseRoot)} ${SCALES[s].name}
                    </button>
                `);
            }
        });

        // 3. Transition Modes for this song (Chord modes)
        if (sm.transitionItems && sm.transitionItems.length > 0) {
            sm.transitionItems.forEach((item, idx) => {
                const chordBadge = item.chord
                    ? `<span class="chip-chord-tag ${item.degree ? 'chord-degree-' + item.degree : ''}">${item.chord}</span>`
                    : '';
                transChips.push(`
                    <button type="button" class="btn-quick-scale btn-transition-chip" data-idx="${idx}" data-category="transition" data-root="${item.root}" data-scale="${item.scaleKey}" title="${item.chord ? item.chord + ' ➔ ' : ''}${item.scaleDisplayName}">
                        <i class="ph ph-sparkle"></i>
                        ${chordBadge}
                        <span class="chip-scale-text">${item.scaleDisplayName}</span>
                    </button>
                `);
            });
        } else {
            sm.transitionModesMap.forEach((scales, r) => {
                scales.forEach(s => {
                    if (r === baseRoot && baseScales.includes(s)) return;
                    transChips.push(`
                        <button type="button" class="btn-quick-scale" data-category="transition" data-root="${r}" data-scale="${s}">
                            <i class="ph ph-sparkle"></i>
                            ${dn(r)} ${SCALES[s] ? SCALES[s].name : s}
                        </button>
                    `);
                });
            });
        }

        if (baseChipsContainer) baseChipsContainer.innerHTML = baseChips.join('');
        if (transChipsContainer) {
            transChipsContainer.innerHTML = transChips.length
                ? transChips.join('')
                : '<span style="font-size: 11.5px; color: var(--text-tertiary); font-style: italic;">No hay transiciones registradas</span>';
        }

        // Click Handler for all quick chips across both rows
        container.querySelectorAll('.btn-quick-scale').forEach(chip => {
            chip.addEventListener('click', () => {
                const category = chip.getAttribute('data-category');
                const cRoot = chip.getAttribute('data-root');
                const cScale = chip.getAttribute('data-scale');
                const cIdx = parseInt(chip.getAttribute('data-idx'));

                if (category === 'transition') {
                    // Activate Fusion Mode immediately when clicking a transition!
                    fbState.fusionActive = true;
                    fbState.root2 = cRoot;
                    fbState.scaleKey2 = cScale;
                    if (!isNaN(cIdx) && sm.transitionItems && sm.transitionItems[cIdx]) {
                        fbState.activeTransitionIndex = cIdx;
                        fbState.activeTransitionItem = sm.transitionItems[cIdx];
                    } else {
                        const foundIdx = (sm.transitionItems || []).findIndex(it => it.root === cRoot && it.scaleKey === cScale);
                        fbState.activeTransitionIndex = foundIdx;
                        fbState.activeTransitionItem = foundIdx !== -1 ? sm.transitionItems[foundIdx] : null;
                    }
                } else {
                    // Clicking a base mode updates the BASE (MODO BASE)
                    fbState.root1 = cRoot;
                    fbState.scaleKey1 = cScale;
                }

                syncUIState(container);
            });
        });

        // Initial visual highlight
        syncChipsVisual(container);
    }

    // Public API
    window.GuitarFretboard = {
        render: renderComponent,
        setupSong: setupSongPresets,
        playNote: playFretboardNote,
        stopPractice,
        getState: () => fbState
    };

})(window);
