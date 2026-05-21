/* ============================================================
   Pokladna - jednoduchý SSE listener s velkou vizualizací
   ============================================================ */

const els = {
    screens: {
        default: document.getElementById('screen-default'),
        accept: document.getElementById('screen-accept'),
        deny: document.getElementById('screen-deny'),
    },
    checkpointLabel: document.getElementById('checkpoint-label'),
    passportName: document.getElementById('passport-name'),
    passportGenderIcon: document.getElementById('passport-gender-icon'),
    passportYear: document.getElementById('passport-year'),
    progressFill: document.getElementById('progress-fill'),
    progressText: document.getElementById('progress-text'),
    completionBadge: document.getElementById('completion-badge'),
    denyMessage: document.getElementById('deny-message'),
    connIndicator: document.getElementById('conn-indicator'),
};

let showResultMs = 5000;
let totalCountries = 11;
let returnTimer = null;

// --- Helpers ---

function showScreen(name) {
    Object.entries(els.screens).forEach(([k, el]) => {
        if (!el) return;
        if (k === name) el.classList.add('visible');
        else el.classList.remove('visible');
    });
}

function scheduleReturn() {
    if (returnTimer) clearTimeout(returnTimer);
    returnTimer = setTimeout(() => showScreen('default'), showResultMs);
}

function setConnection(ok) {
    els.connIndicator.classList.toggle('fail', !ok);
}

// --- Event handlery ---

function handleInit(data) {
    console.log('[init]', data);
    if (data.checkpoint_label) {
        els.checkpointLabel.textContent = data.checkpoint_label;
        document.title = `Pokladna ${data.checkpoint_label}`;
    }
    if (data.show_result_seconds) {
        showResultMs = data.show_result_seconds * 1000;
    }
    if (data.total_countries) {
        totalCountries = data.total_countries;
    }
    showScreen('default');
}

function handleAccept(data) {
    console.log('[accept]', data);
    const p = data.passport;

    els.passportName.textContent = p.first_name;
    els.passportGenderIcon.textContent = p.gender === 'M' ? '👦' : '👧';
    els.passportYear.textContent = `Ročník ${p.birth_year}`;

    // Progress
    const percent = (p.unique_countries / p.total_countries) * 100;
    els.progressFill.style.width = `${percent}%`;
    els.progressText.textContent = `${p.unique_countries} / ${p.total_countries} zemí`;

    if (p.completed) {
        els.completionBadge.hidden = false;
    } else {
        els.completionBadge.hidden = true;
    }

    showScreen('accept');
    scheduleReturn();
}

function handleDeny(data) {
    console.log('[deny]', data);
    els.denyMessage.textContent = data.message || 'Pas nelze ověřit.';
    showScreen('deny');
    scheduleReturn();
}

// --- SSE ---

function connectSSE() {
    const source = new EventSource('/events');
    source.onopen = () => setConnection(true);
    source.onerror = () => setConnection(false);
    source.onmessage = (e) => {
        try {
            const payload = JSON.parse(e.data);
            const type = payload.type;
            const data = payload.data || {};
            switch (type) {
                case 'init': handleInit(data); break;
                case 'accept': handleAccept(data); break;
                case 'deny': handleDeny(data); break;
                default: console.warn('Unknown event:', type);
            }
        } catch (err) {
            console.error('SSE parse:', err);
        }
    };
}

document.addEventListener('DOMContentLoaded', () => {
    showScreen('default');
    connectSSE();
});
