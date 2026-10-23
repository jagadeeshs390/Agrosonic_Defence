/**
 * AgroSonic Defence - Real-Time Dashboard Controller & Web Audio Engine
 * Handles telemetry polling, dynamic oscilloscope rendering, Web Audio synthesis,
 * visual strobe synchronization, and hackathon test injection controls.
 */

// Global State
let audioContext = null;
let isAudioMuted = false;
let isCvWindowActive = true;
let lastKnownState = "ARMED";
let lastDeterrenceStart = 0;
let lastRenderedEventId = 0;
let cachedEvents = [];

let currentTargetFreqKhz = 0;
let activeHabituationLevel = 1;
let isDeterringActive = false;

// Initialize Web Audio Context (lazily upon user gesture if needed)
function getAudioContext() {
    if (!audioContext) {
        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        if (AudioCtx) {
            audioContext = new AudioCtx();
        }
    }
    if (audioContext && audioContext.state === 'suspended') {
        audioContext.resume();
    }
    return audioContext;
}

/**
 * Synthesizes and plays authentic emergency perimeter sirens through browser audio.
 * Eliminates high-pitch discrete beeping in favor of continuous emergency wailing & yelping sweeps.
 */
function playWebAudioSiren(category, freqKhz, habituationLevel) {
    if (isAudioMuted) return;

    // 1. Try playing high-fidelity perimeter siren PCM audio file
    try {
        const soundFile = (habituationLevel >= 4 || category === "Birds")
            ? '/static/audio/alarm_yelp.wav'
            : '/static/audio/perimeter_siren.wav';
        const sirenAudio = new Audio(soundFile);
        sirenAudio.volume = 0.85;
        const playPromise = sirenAudio.play();
        if (playPromise !== undefined) {
            playPromise.then(() => {
                return;
            }).catch(() => {
                // If browser autoplay policy or sandbox blocked HTML5 Audio, synthesize with Web Audio API
                synthesizeWebAudioSiren(category, habituationLevel);
            });
            return;
        }
    } catch (e) {
        // Fall through to real-time synthesis
    }

    synthesizeWebAudioSiren(category, habituationLevel);
}

/**
 * Real-time Web Audio API Siren Synthesizer:
 * Uses carrier oscillator modulated by an LFO (Low-Frequency Oscillator)
 * routed through a loudspeaker resonant Biquad filter to generate an authentic analog wailing siren.
 */
function synthesizeWebAudioSiren(category, habituationLevel) {
    try {
        const actx = getAudioContext();
        if (!actx) return;

        const now = actx.currentTime;
        const duration = 2.6; // 2.6s siren duration matching perimeter deterrence cycle

        // 1. Carrier Oscillator (rich harmonics)
        const carrier = actx.createOscillator();
        carrier.type = "sawtooth";

        // 2. LFO Modulator (continuous frequency wail/sweep)
        const lfo = actx.createOscillator();
        const lfoGain = actx.createGain();

        // 3. Horn Loudspeaker Resonant Filter
        const filter = actx.createBiquadFilter();
        filter.type = "lowpass";
        filter.frequency.setValueAtTime(2200, now);
        filter.Q.setValueAtTime(2.8, now);

        // 4. Master Volume Envelope
        const masterGain = actx.createGain();

        if (category === "Birds" || habituationLevel >= 4) {
            // Fast Urgent Yelp Siren
            carrier.frequency.setValueAtTime(980, now);
            lfo.type = "sawtooth";
            lfo.frequency.setValueAtTime(2.8, now); // 2.8 Hz rapid yelp cycle
            lfoGain.gain.setValueAtTime(380, now);   // sweeps 600 Hz to 1360 Hz
        } else if (category === "Wild Animals" || habituationLevel >= 2) {
            // Deep Emergency Perimeter Wail Siren
            carrier.frequency.setValueAtTime(780, now);
            lfo.type = "sine";
            lfo.frequency.setValueAtTime(1.15, now); // 1.15 Hz smooth classic wail cycle
            lfoGain.gain.setValueAtTime(340, now);   // sweeps 440 Hz to 1120 Hz
        } else {
            // Boundary Warning Sweep
            carrier.frequency.setValueAtTime(620, now);
            lfo.type = "sine";
            lfo.frequency.setValueAtTime(0.9, now);
            lfoGain.gain.setValueAtTime(220, now);
        }

        // Connect LFO -> Carrier Frequency
        lfo.connect(lfoGain);
        lfoGain.connect(carrier.frequency);

        // Route: Carrier -> Resonant Filter -> Master Gain -> Speakers
        carrier.connect(filter);
        filter.connect(masterGain);
        masterGain.connect(actx.destination);

        // Smooth volume envelope: 0.12s attack, sustained wail, 0.35s decay
        masterGain.gain.setValueAtTime(0.001, now);
        masterGain.gain.linearRampToValueAtTime(0.24, now + 0.12);
        masterGain.gain.setValueAtTime(0.24, now + duration - 0.35);
        masterGain.gain.exponentialRampToValueAtTime(0.001, now + duration);

        carrier.start(now);
        lfo.start(now);
        carrier.stop(now + duration + 0.05);
        lfo.stop(now + duration + 0.05);
    } catch (e) {
        console.warn("WebAudio siren synthesis error:", e);
    }
}

// Backward compatibility alias
const playWebAudioChirp = playWebAudioSiren;

/**
 * Immediate siren test trigger for dashboard verification
 */
function testPerimeterSiren() {
    getAudioContext();
    playWebAudioSiren("Wild Animals", 34.0, 2);
}



/**
 * Main Telemetry Poller:
 * Queries `/api/status` every 400ms to update all UI components in real time.
 */
async function fetchTelemetry() {
    try {
        const response = await fetch('/api/status');
        if (!response.ok) return;
        const data = await response.json();
        updateDashboardUI(data);
    } catch (err) {
        console.warn("Telemetry polling warning:", err);
    }
}

function updateDashboardUI(data) {
    const sysStatus = data.system_status || "ARMED";
    const det = data.detection || {};
    const detrr = data.deterrence || {};
    const esp = data.esp32 || {};
    const hab = data.habituation || {};
    const events = data.events || [];

    // 1. Header HUD Status
    const statusPill = document.getElementById('systemStatusPill');
    const statusDot = document.getElementById('systemStatusDot');
    const statusText = document.getElementById('systemStatusText');

    if (detrr.active) {
        statusDot.className = "status-dot red";
        statusText.textContent = "DETERRENCE ACTIVE";
        isDeterringActive = true;
    } else {
        statusDot.className = "status-dot green";
        statusText.textContent = "SYSTEM ARMED";
        isDeterringActive = false;
    }

    const nodeBadge = document.getElementById('nodeIdBadge');
    if (nodeBadge) nodeBadge.textContent = esp.node_id || "ESP32-AGRO-01";
    const camBadge = document.getElementById('cameraSourceBadge');
    if (camBadge) camBadge.textContent = data.camera_source || "Webcam Live";

    // 2. Detection Tactical Banner
    const banner = document.getElementById('liveDetectionBanner');
    const bannerTitle = document.getElementById('bannerTitle');
    const bannerSubtitle = document.getElementById('bannerSubtitle');
    const bannerActuation = document.getElementById('bannerActuation');
    const bannerIcon = document.getElementById('bannerIcon');

    if (det.detected && det.category !== "None") {
        banner.classList.remove('hidden');
        bannerTitle.textContent = `${det.category.toUpperCase()} DETECTED`;
        bannerSubtitle.textContent = `Target: ${det.class_name} | Confidence: ${Math.round(det.confidence * 100)}%`;
        bannerActuation.textContent = `ACTUATING ${detrr.frequency_display}`;
        bannerActuation.style.borderColor = "var(--color-amber)";
        bannerActuation.style.color = "var(--color-amber)";
        bannerActuation.style.background = "rgba(245, 158, 11, 0.15)";
        
        const icons = {
            "Birds": "🐦",
            "Wild Animals": "🐘",
            "Livestock": "🐄"
        };
        bannerIcon.textContent = icons[det.category] || "⚠️";
    } else {
        banner.classList.add('hidden');
    }

    // 3. Strobe Visual Simulation
    const videoWrapper = document.getElementById('videoWrapper');
    const hudStrobe = document.getElementById('hudStrobeIndicator');
    const screenOverlay = document.getElementById('screenStrobeOverlay');
    const strobeDisplay = document.getElementById('strobeRateDisplay');

    if (detrr.strobe_active && detrr.active) {
        if (videoWrapper) videoWrapper.classList.add('strobe-flashing');
        if (hudStrobe) hudStrobe.classList.remove('hidden');
        if (screenOverlay) screenOverlay.classList.add('flashing');
        if (strobeDisplay) strobeDisplay.textContent = `${detrr.strobe_hz} Hz`;
    } else {
        if (videoWrapper) videoWrapper.classList.remove('strobe-flashing');
        if (hudStrobe) hudStrobe.classList.add('hidden');
        if (screenOverlay) screenOverlay.classList.remove('flashing');
    }

    currentTargetFreqKhz = detrr.frequency_khz || 0.0;
    activeHabituationLevel = detrr.habituation_level || 1;

    // Trigger browser emergency perimeter siren if a new deterrence event just started
    if (detrr.active && detrr.start_time !== lastDeterrenceStart) {
        lastDeterrenceStart = detrr.start_time;
        playWebAudioSiren(detrr.category, detrr.frequency_khz, detrr.habituation_level);
    }

    // 5. Habituation Mitigation Matrix (if present in DOM)
    const levelBadge = document.getElementById('habituationLevelBadge');
    if (levelBadge) {
        levelBadge.textContent = `LEVEL ${detrr.habituation_level || 1}: ${getHabituationName(detrr.habituation_level || 1)}`;
    }
    const stratName = document.getElementById('mitigationStrategyName');
    if (stratName) {
        stratName.textContent = detrr.strategy || "Standard Monitoring";
    }

    // Highlight active tier in habituation grid if present
    for (let i = 1; i <= 5; i++) {
        const item = document.getElementById(`hLevel${i}`);
        if (item) {
            if (i === (detrr.habituation_level || 1)) {
                item.classList.add('active');
            } else {
                item.classList.remove('active');
            }
        }
    }

    // Event History Table
    cachedEvents = events;
    const countBadge = document.getElementById('eventCountBadge');
    if (countBadge) {
        countBadge.textContent = `${data.total_events || events.length} events logged`;
    }
    renderEventsTable(events);
}

function getHabituationName(level) {
    const names = {
        1: "LINEAR SWEEP",
        2: "DUAL HARMONIC BURST",
        3: "FREQUENCY HOPPING",
        4: "CHIRP DISRUPTOR",
        5: "CHAOS AGITATION"
    };
    return names[level] || "STANDARD SWEEP";
}

function formatUptime(seconds) {
    const hrs = Math.floor(seconds / 3600).toString().padStart(2, '0');
    const mins = Math.floor((seconds % 3600) / 60).toString().padStart(2, '0');
    const secs = (seconds % 60).toString().padStart(2, '0');
    return `${hrs}:${mins}:${secs}`;
}

function renderEventsTable(events) {
    const tbody = document.getElementById('eventsTableBody');
    if (!tbody) return;
    if (!events || events.length === 0) {
        tbody.innerHTML = `<tr class="empty-row"><td colspan="7">System armed and scanning. No intrusion events recorded yet.</td></tr>`;
        return;
    }

    let rowsHtml = "";
    events.forEach(evt => {
        let tagClass = "tag-bird";
        if (evt.category === "Wild Animals") tagClass = "tag-wild";
        else if (evt.category === "Livestock") tagClass = "tag-livestock";

        let statusBadge = `<span class="status-success-tag">✓ ACTIVE</span>`;

        rowsHtml += `
            <tr>
                <td class="font-mono">#${evt.id}</td>
                <td class="font-mono">${evt.timestamp}</td>
                <td><span class="badge-tag ${tagClass}">${evt.category}</span></td>
                <td class="strategy-col">${evt.strategy}</td>
                <td class="font-mono">${evt.frequency_khz} kHz</td>
                <td class="font-mono">${evt.strobe_hz} Hz</td>
                <td>${statusBadge}</td>
            </tr>
        `;
    });
    tbody.innerHTML = rowsHtml;
}


// Interactive API Handlers for Judges & Operators
async function injectTestSample(sampleName) {
    getAudioContext();
    try {
        const res = await fetch(`/api/test_sample/${sampleName}`, { method: 'POST' });
        const data = await res.json();
        console.log(`[AgroSonic] Injected sample ${sampleName}:`, data);
    } catch (e) {
        console.error("Sample injection failed:", e);
    }
}

async function clearTestSample() {
    try {
        const res = await fetch('/api/clear_sample', { method: 'POST' });
        const data = await res.json();
        console.log("[AgroSonic] Cleared sample injection:", data);
    } catch (e) {
        console.error("Clear sample failed:", e);
    }
}

async function triggerManualDeterrence() {
    getAudioContext();
    try {
        const res = await fetch('/api/trigger_manual', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ category: 'Wild Animals' })
        });
        const data = await res.json();
        console.log("[AgroSonic] Manual deterrence triggered:", data);
    } catch (e) {
        console.error("Manual deterrence trigger failed:", e);
    }
}

async function updateConfidence(val) {
    document.getElementById('confValue').textContent = `${val}%`;
    const threshold = val / 100.0;
    try {
        await fetch('/api/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ confidence_threshold: threshold })
        });
    } catch (e) {
        console.error("Update confidence failed:", e);
    }
}

async function clearEventLogs() {
    try {
        await fetch('/api/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ clear_events: true })
        });
        document.getElementById('eventsTableBody').innerHTML = `<tr class="empty-row"><td colspan="9">Event log cleared.</td></tr>`;
    } catch (e) {
        console.error("Clear events failed:", e);
    }
}

function exportEventsCsv() {
    if (!cachedEvents || cachedEvents.length === 0) {
        alert("No events recorded yet to export.");
        return;
    }
    let csv = "Event ID,Timestamp,Category,Strategy,Frequency (kHz),Strobe (Hz),Habituation Level,Sound (dB)\n";
    cachedEvents.forEach(e => {
        csv += `${e.id},"${e.timestamp}","${e.category}","${e.strategy}",${e.frequency_khz},${e.strobe_hz},${e.habituation_level},${e.sound_db}\n`;
    });

    const blob = new Blob([csv], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.setAttribute('href', url);
    a.setAttribute('download', `agrosonic_events_${Date.now()}.csv`);
    a.click();
}

// Optional control buttons (safely guarded if removed)
const audioBtn = document.getElementById('audioToggleBtn');
if (audioBtn) {
    audioBtn.addEventListener('click', async () => {
        getAudioContext();
        isAudioMuted = !isAudioMuted;
        const statusEl = document.getElementById('audioStatusText');
        const iconEl = document.getElementById('audioIcon');
        if (statusEl) statusEl.textContent = isAudioMuted ? "MUTED" : "ON";
        if (iconEl) iconEl.textContent = isAudioMuted ? "🔇" : "🔊";

        try {
            await fetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ local_audio_enabled: !isAudioMuted })
            });
        } catch (e) {}
    });
}

const cvBtn = document.getElementById('cvWindowToggleBtn');
if (cvBtn) {
    cvBtn.addEventListener('click', async () => {
        isCvWindowActive = !isCvWindowActive;
        const cvText = document.getElementById('cvWindowStatusText');
        if (cvText) cvText.textContent = isCvWindowActive ? "ACTIVE" : "HIDDEN";

        try {
            await fetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ cv_window_active: isCvWindowActive })
            });
        } catch (e) {}
    });
}

// Toggle Mirror / Horizontal Flip
async function toggleMirror() {
    try {
        const res = await fetch('/api/toggle_flip', { method: 'POST' });
        const data = await res.json();
        const mirrorText = document.getElementById('mirrorStatusText');
        if (mirrorText) {
            mirrorText.textContent = data.flip_horizontal ? "FLIPPED" : "NORMAL";
        }
    } catch (e) {
        console.error("Toggle mirror failed:", e);
    }
}

// Live Digital Clock (safely guarded)
const clockEl = document.getElementById('liveClock');
if (clockEl) {
    setInterval(() => {
        const now = new Date();
        clockEl.textContent = now.toTimeString().split(' ')[0];
    }, 1000);
}

// Permanent Light Theme Enforced
try {
    localStorage.removeItem('agrosonic_theme');
} catch (e) {}

// Polling Interval (every 600ms for lightweight, snappy telemetry)
setInterval(fetchTelemetry, 600);
fetchTelemetry();

