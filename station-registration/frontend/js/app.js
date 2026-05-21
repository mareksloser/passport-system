/* ============================================================
   Registrační stanice - desktop UI (bez fotky)
   ============================================================ */

const els = {
    connDot: document.getElementById('conn-dot'),
    connLabel: document.getElementById('conn-label'),

    chipStates: {
        empty: document.getElementById('chip-state-empty'),
        blank: document.getElementById('chip-state-blank'),
        registered: document.getElementById('chip-state-registered'),
        invalid: document.getElementById('chip-state-invalid'),
    },
    existingName: document.getElementById('existing-name'),
    existingGender: document.getElementById('existing-gender'),
    existingYear: document.getElementById('existing-year'),
    existingCountries: document.getElementById('existing-countries'),
    existingCompletedRow: document.getElementById('existing-completed-row'),

    form: document.getElementById('register-form'),
    firstName: document.getElementById('first_name'),
    birthYear: document.getElementById('birth_year'),
    overwriteField: document.getElementById('overwrite-field'),
    forceOverwrite: document.getElementById('force_overwrite'),
    submitBtn: document.getElementById('submit-btn'),
    formStatus: document.getElementById('form-status'),

    toast: document.getElementById('toast'),
    successModal: document.getElementById('success-modal'),
    successText: document.getElementById('success-text'),
    closeModal: document.getElementById('close-modal'),
};

let currentTagType = 'empty';

// ============================================================
// Helpers
// ============================================================

function showChipState(type) {
    currentTagType = type;
    Object.entries(els.chipStates).forEach(([key, el]) => {
        if (!el) return;
        el.classList.toggle('visible', key === type);
    });
    updateFormState();
}

function updateFormState() {
    const hasName = els.firstName.value.trim().length > 0;
    const hasGender = !!els.form.querySelector('input[name="gender"]:checked');
    const year = parseInt(els.birthYear.value);
    const hasYear = !isNaN(year) && year >= 2005 && year <= 2025;

    const formValid = hasName && hasGender && hasYear;
    const tagOk = currentTagType === 'blank'
        || (currentTagType === 'registered' && els.forceOverwrite.checked);

    els.submitBtn.disabled = !(formValid && tagOk);

    // Zobrazit checkbox "přepsat" jen u registrovaného
    els.overwriteField.hidden = currentTagType !== 'registered';

    // Informace dle stavu čipu
    if (currentTagType === 'empty') {
        setFormStatus('Polož pas na čtečku, abys mohl/a zaregistrovat.', 'info');
    } else if (currentTagType === 'invalid') {
        setFormStatus('Tento čip nelze použít. Vlož jiný.', 'error');
    } else if (currentTagType === 'registered' && !els.forceOverwrite.checked) {
        setFormStatus('Pas je již zaregistrován. Pokud chceš přepsat, zaškrtni "Přepsat existující".', 'info');
    } else if (currentTagType === 'blank' && !formValid) {
        setFormStatus('Vyplň všechna pole formuláře.', 'info');
    } else {
        setFormStatus(null);
    }
}

function setFormStatus(message, type = 'info') {
    if (!message) {
        els.formStatus.hidden = true;
        return;
    }
    els.formStatus.textContent = message;
    els.formStatus.className = `form-status ${type}`;
    els.formStatus.hidden = false;
}

function showToast(msg, type = 'info', duration = 3500) {
    els.toast.textContent = msg;
    els.toast.className = `toast ${type}`;
    els.toast.hidden = false;
    setTimeout(() => { els.toast.hidden = true; }, duration);
}

function setConnection(ok, label) {
    els.connDot.classList.toggle('ok', ok);
    els.connDot.classList.toggle('fail', !ok);
    els.connLabel.textContent = label || (ok ? 'Připojeno' : 'Odpojeno');
}

// ============================================================
// SSE handlery
// ============================================================

function handleInit(data) {
    console.log('[init]', data);
    setConnection(true, 'Připojeno');
}

function handleTagPresent(data) {
    console.log('[tag_present]', data);
    if (data.type === 'blank') {
        showChipState('blank');
    } else if (data.type === 'invalid') {
        showChipState('invalid');
    } else if (data.type === 'registered') {
        showChipState('registered');
        const p = data.passport;
        els.existingName.textContent = p.first_name;
        els.existingGender.textContent = p.gender === 'M' ? '👦 Chlapec' : '👧 Dívka';
        els.existingYear.textContent = p.birth_year;
        els.existingCountries.textContent = p.unique_countries;
        els.existingCompletedRow.hidden = !p.completed;
    }
}

function handleTagRemoved() {
    showChipState('empty');
}

function handleRegistered(data) {
    console.log('[registered]', data);
    // Server notifikuje - UI to už ukazuje přes modal v register flow
}

function connectSSE() {
    const source = new EventSource('/events');
    source.onopen = () => setConnection(true, 'Připojeno');
    source.onerror = () => setConnection(false, 'Připojuji…');
    source.onmessage = (e) => {
        try {
            const payload = JSON.parse(e.data);
            switch (payload.type) {
                case 'init': handleInit(payload.data); break;
                case 'tag_present': handleTagPresent(payload.data); break;
                case 'tag_removed': handleTagRemoved(); break;
                case 'registered': handleRegistered(payload.data); break;
                default: console.warn('Unknown event:', payload.type);
            }
        } catch (err) {
            console.error('SSE parse:', err, e.data);
        }
    };
}

// ============================================================
// Form submit
// ============================================================

async function handleSubmit(e) {
    e.preventDefault();

    const data = {
        first_name: els.firstName.value.trim(),
        gender: els.form.querySelector('input[name="gender"]:checked').value,
        birth_year: parseInt(els.birthYear.value),
        force_overwrite: els.forceOverwrite.checked,
    };

    els.submitBtn.disabled = true;
    els.submitBtn.textContent = 'Zapisuji na čip…';
    setFormStatus('Zapisuji data na čip a ověřuji…', 'info');

    try {
        const r = await fetch('/api/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });

        const responseData = await r.json();

        if (!r.ok) {
            setFormStatus(responseData.error || 'Neznámá chyba', 'error');
            showToast(responseData.error || 'Registrace selhala', 'error');
            return;
        }

        // Úspěch - ukaž modal
        const p = responseData.passport;
        const genderLabel = p.gender === 'M' ? 'chlapec' : 'dívka';
        els.successText.textContent = `${p.first_name} (${genderLabel}, ${p.birth_year})`;
        els.successModal.hidden = false;

    } catch (e) {
        setFormStatus('Chyba spojení: ' + e.message, 'error');
        showToast('Chyba spojení', 'error');
    } finally {
        els.submitBtn.textContent = 'Zaregistrovat na čip';
        // Tlačítko zůstane zakázané dokud se nepřiloží nový čip
        updateFormState();
    }
}

function resetForm() {
    els.form.reset();
    els.birthYear.value = 2014;
    els.forceOverwrite.checked = false;
    setFormStatus(null);
    els.successModal.hidden = true;
    els.firstName.focus();
}

// ============================================================
// Init
// ============================================================

document.addEventListener('DOMContentLoaded', () => {
    showChipState('empty');
    connectSSE();

    // Form events
    els.form.addEventListener('submit', handleSubmit);
    els.firstName.addEventListener('input', updateFormState);
    els.birthYear.addEventListener('input', updateFormState);
    els.form.querySelectorAll('input[name="gender"]').forEach(r =>
        r.addEventListener('change', updateFormState)
    );
    els.forceOverwrite.addEventListener('change', updateFormState);

    // Modal
    els.closeModal.addEventListener('click', resetForm);

    // Focus na jméno hned po načtení
    els.firstName.focus();
});
