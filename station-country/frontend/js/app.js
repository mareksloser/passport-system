/* Frontend pro stanoviště země - 800x480 kiosk */

const els = {
    screens: {
        default: document.getElementById('screen-default'),
        scan: document.getElementById('screen-scan'),
        completion: document.getElementById('screen-completion'),
        error: document.getElementById('screen-error'),
    },
    countryName: document.getElementById('country-name'),
    countryDefaultImg: document.getElementById('country-default-img'),
    countryCustomImg: document.getElementById('country-custom-img'),
    greeting: document.getElementById('greeting-text'),
    fact: document.getElementById('fact-text'),
    completion: document.getElementById('completion-text'),
    error: document.getElementById('error-text'),
    connIndicator: document.getElementById('conn-indicator'),
};

let returnToDefaultMs = 20000;
let completionShowMs = 45000;
let returnTimer = null;

function showScreen(name) {
    Object.entries(els.screens).forEach(([k, el]) => {
        if (k === name) el.classList.add('visible');
        else el.classList.remove('visible');
    });
}

function scheduleReturn(ms) {
    if (returnTimer) clearTimeout(returnTimer);
    returnTimer = setTimeout(() => showScreen('default'), ms);
}

/**
 * Obarvi jméno a název země (lokativ) v textu.
 * Backend posílá hotovou větu; tady jen heuristicky obalujeme dvě klíčová slova.
 */
function decorateGreeting(text, countryName) {
    if (!text) return '';
    let html = escapeHtml(text);

    // Obarvi lokativ země - hledáme základ názvu (např. "Hav" pro "na Havaji",
    // "Franc" pro "ve Francii", "Brit" pro "Velké Británii"...)
    if (countryName) {
        // Pro každé slovo v countryName zkus najít kořen a obalit
        const words = countryName.split(/\s+/);
        for (const word of words) {
            if (word.length < 3) continue;
            const stem = word.substring(0, Math.max(3, Math.floor(word.length * 0.6)))
                .replace(/[áéíóúýě]$/i, '');
            if (!stem) continue;
            const re = new RegExp(
                `\\b(${escapeRegex(stem)}[a-záčďéěíňóřšťúůýž]*)\\b`,
                'gi'
            );
            html = html.replace(re, '<span class="country">$1</span>');
        }
    }

    // Obarvi vlastní jména (slova s velkým písmenem, která nejsou na začátku
    // a nejsou stopword)
    const stopWords = new Set([
        'Ahoj', 'Vítej', 'Jak', 'Jsme', 'Letos', 'Gratulujeme',
        'Doufáme', 'Užij', 'Tým', 'Srdcem', 'Ondráška'
    ]);
    html = html.replace(
        /(^|[\s,.!?:;])([A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ][a-záčďéěíňóřšťúůýž]+)/g,
        (m, prefix, word) => {
            if (stopWords.has(word)) return m;
            // Pokud je to už obaleno jako "country", nech být
            return `${prefix}<span class="name">${word}</span>`;
        }
    );

    return html;
}

function escapeHtml(s) {
    return s.replace(/[&<>"']/g, c => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;',
        '"': '&quot;', "'": '&#39;'
    })[c]);
}

function escapeRegex(s) {
    return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

// --- Event handlery ---

function handleInit(data) {
    console.log('[init]', data);
    if (data.country_name) {
        els.countryName.textContent = data.country_name;
        document.title = `Srdcem pro Ondráška - ${data.country_name}`;
    }
    if (data.country_code) {
        const code = data.country_code.toLowerCase().replace('_', '-');
        els.countryDefaultImg.src = `/assets/country-${code}-default.svg`;
        els.countryCustomImg.src = `/assets/country-${code}-custom.svg`;
        // Fallback na placeholder pokud neexistuje
        els.countryDefaultImg.onerror = () => {
            els.countryDefaultImg.onerror = null;
            els.countryDefaultImg.src = '/assets/country-default.svg';
        };
        els.countryCustomImg.onerror = () => {
            els.countryCustomImg.onerror = null;
            els.countryCustomImg.src = '/assets/country-custom.svg';
        };
    }
    if (data.return_to_default_seconds) {
        returnToDefaultMs = data.return_to_default_seconds * 1000;
    }
    if (data.completion_show_seconds) {
        completionShowMs = data.completion_show_seconds * 1000;
    }
    showScreen('default');
}

function handleScan(data) {
    console.log('[scan]', data);
    const countryName = els.countryName.textContent;
    els.greeting.innerHTML = decorateGreeting(data.greeting, countryName);
    els.fact.textContent = data.fact || '';
    showScreen('scan');
    scheduleReturn(returnToDefaultMs);
}

function handleCompletion(data) {
    console.log('[completion]', data);
    els.completion.innerHTML = decorateGreeting(data.greeting, null);
    showScreen('completion');
    scheduleReturn(completionShowMs);
}

function handleError(data) {
    console.log('[error]', data);
    els.error.textContent = data.message || 'Něco se pokazilo.';
    showScreen('error');
    scheduleReturn(returnToDefaultMs);
}

// --- SSE ---

function setConn(ok) {
    els.connIndicator.classList.toggle('fail', !ok);
}

function connectSSE() {
    const source = new EventSource('/events');
    source.onopen = () => setConn(true);
    source.onerror = () => setConn(false);
    source.onmessage = (e) => {
        try {
            const payload = JSON.parse(e.data);
            const type = payload.type;
            const data = payload.data || {};
            switch (type) {
                case 'init': handleInit(data); break;
                case 'scan': handleScan(data); break;
                case 'completion': handleCompletion(data); break;
                case 'error': handleError(data); break;
                default: console.warn('Unknown event:', type);
            }
        } catch (err) {
            console.error('SSE parse:', err, e.data);
        }
    };
}

document.addEventListener('DOMContentLoaded', () => {
    showScreen('default');
    connectSSE();
});
