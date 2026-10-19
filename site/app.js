// Appy site: the live board, the agent session, and the small working fragments.
// roles.json is written by `python3 shortlist.py --days 7 --json` (see .github/workflows/pages.yml).

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const DAY = 864e5;
const FIELD_WORDS = { all: 'technical', software: 'software', data: 'AI and data', quant: 'quant', hardware: 'hardware', product: 'product' };
const store = {
  get() { try { return new Set(JSON.parse(localStorage.getItem('appy-applied') || '[]')); } catch { return new Set(); } },
  set(urls) { try { localStorage.setItem('appy-applied', JSON.stringify([...urls])); } catch { /* private window */ } },
};

const state = { roles: [], generated: null, field: 'all', askDays: 3, day: null, query: '', shown: 12, showApplied: false, applied: store.get() };

const esc = (text) => String(text).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const safeUrl = (url) => (/^https?:\/\//i.test(url) ? url : '#');
const ago = (ms) => { const h = Math.floor(ms / 36e5); return h < 1 ? 'just now' : h < 48 ? `${h}h ago` : `${Math.floor(h / 24)}d ago`; };
const place = (role) => (role.locations.length ? role.locations.slice(0, 2).join('; ') + (role.locations.length > 2 ? ` +${role.locations.length - 2}` : '') : 'Location not listed');
const dayKey = (t) => new Date(t).toLocaleDateString('en-CA');
const matches = (role) => (state.field === 'all' || role.field === state.field)
  && (!state.query || `${role.company} ${role.title} ${role.locations.join(' ')}`.toLowerCase().includes(state.query));

/* ---------- the agent session in the hero ---------- */
function renderAsk() {
  const now = Date.now();
  const inWindow = state.roles.filter((r) => now - r.t <= state.askDays * DAY && (state.field === 'all' || r.field === state.field));
  const fresh = inWindow.filter((r) => !state.applied.has(r.url));
  const skipped = inWindow.length - fresh.length;
  const span = state.askDays === 1 ? 'in the last day' : `in the last ${state.askDays} days`;
  const word = FIELD_WORDS[state.field];
  $('#ask-summary').innerHTML = fresh.length
    ? `<strong>${fresh.length} ${esc(word)} ${fresh.length === 1 ? 'role' : 'roles'}</strong> posted ${span}${skipped ? `, after skipping ${skipped} you marked applied` : ''}. The newest:`
    : `No new ${esc(word)} roles ${span}${skipped ? ` beyond the ${skipped} you marked applied` : ''}. Try a longer window.`;
  $('#ask-hits').innerHTML = fresh.slice(0, 5).map((r, i) => `<li><a class="hit enter" style="--i:${i}" href="${esc(safeUrl(r.url))}" target="_blank" rel="noopener">
    <span class="hit-co">${esc(r.company)}</span><span class="hit-when">${ago(now - r.t)}</span>
    <span class="hit-title">${esc(r.title)} · ${esc(place(r))}</span></a></li>`).join('');
  $('#ask-next').innerHTML = fresh.length
    ? `Want me to prepare the first three? I'll stop before each submit. <a href="#board">See all ${fresh.length} on the board</a>`
    : `<a href="#board">Open this week's board</a>`;
}

/* ---------- the board ---------- */
function renderDays() {
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const counts = {};
  for (const r of state.roles) if (matches(r) && (state.showApplied || !state.applied.has(r.url))) counts[dayKey(r.t)] = (counts[dayKey(r.t)] || 0) + 1;
  const days = Array.from({ length: 7 }, (_, i) => new Date(today.getTime() - i * DAY));
  if (!state.day) state.day = dayKey((days.find((d) => counts[dayKey(d)]) || today).getTime());
  $('#days').innerHTML = days.map((d, i) => {
    const key = dayKey(d.getTime());
    const name = i === 0 ? 'Today' : i === 1 ? 'Yesterday' : d.toLocaleDateString('en-US', { weekday: 'long' });
    const n = counts[key] || 0;
    return `<button type="button" class="day" role="tab" data-day="${key}" aria-selected="${key === state.day}" tabindex="${key === state.day ? 0 : -1}">
      <b><span class="day-long">${name}</span><span class="day-short">${i === 0 ? 'Today' : d.toLocaleDateString('en-US', { weekday: 'short' })}</span></b>
      <span><span class="day-date">${d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })} · </span>${n}<span class="day-unit"> ${n === 1 ? 'role' : 'roles'}</span></span></button>`;
  }).join('');
  const total = Object.values(counts).reduce((a, b) => a + b, 0);
  $$('[data-week-count]').forEach((el) => { el.textContent = `${total} ${state.field === 'all' ? '' : FIELD_WORDS[state.field] + ' '}${total === 1 ? 'internship' : 'internships'}`; });
}

function band(r, i) {
  const applied = state.applied.has(r.url);
  const time = new Date(r.t).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
  return `<li class="band enter${applied ? ' is-applied' : ''}" style="--i:${i}">
    <span class="band-time">${time}</span>
    <div><p class="band-co">${esc(r.company)}</p><p class="band-sub">${esc(r.title)} <span>· ${esc(place(r))}</span></p></div>
    <div class="band-actions">
      <button type="button" class="mark" data-url="${esc(r.url)}" aria-pressed="${applied}">${applied ? 'Applied, undo' : 'Mark applied'}</button>
      <a class="open" href="${esc(safeUrl(r.url))}" target="_blank" rel="noopener">Open posting</a>
    </div></li>`;
}

function renderBands() {
  const list = state.roles.filter((r) => dayKey(r.t) === state.day && matches(r) && (state.showApplied || !state.applied.has(r.url)));
  const label = $(`.day[data-day="${state.day}"] .day-long`)?.textContent.toLowerCase() || "that day";
  $('#bands').innerHTML = list.length
    ? list.slice(0, state.shown).map(band).join('')
    : `<li class="band band-note"><p>No ${state.field === 'all' ? '' : esc(FIELD_WORDS[state.field]) + ' '}roles posted ${label === 'today' || label === 'yesterday' ? label : 'on ' + label}${state.query ? ` matching “${esc(state.query)}”` : ''}. Try another day or field.</p></li>`;
  const more = $('#board-more');
  more.hidden = list.length <= state.shown;
  more.textContent = `Show ${Math.min(24, list.length - state.shown)} more of ${list.length}`;
  const hidden = state.roles.filter((r) => state.applied.has(r.url)).length;
  $('#board-hidden').innerHTML = hidden
    ? `You've marked ${hidden} applied; ${state.showApplied ? 'they show greyed out.' : 'they stay hidden in this browser, the way Appy skips roles in your tracker.'} <button type="button" id="toggle-applied">${state.showApplied ? 'Hide them' : 'Show them'}</button>`
    : `${state.generated ? `Last refreshed ${ago(Date.now() - state.generated)}.` : ''} Mark a role applied and it leaves your list, in this browser only.`;
}

function renderBoard() { renderDays(); renderBands(); }
function renderAll() { renderAsk(); renderBoard(); updateCommand(); }

function setField(field) {
  state.field = field;
  state.shown = 12;
  $('#ask-field').value = field;
  $$('#board-fields button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.field === field)));
  renderAll();
}

$('#ask-field').addEventListener('change', (e) => setField(e.target.value));
$('#ask-days').addEventListener('change', (e) => { state.askDays = Number(e.target.value); renderAsk(); });
$('#board-fields').addEventListener('click', (e) => { const b = e.target.closest('button'); if (b) setField(b.dataset.field); });
$('#board-search').addEventListener('input', (e) => { state.query = e.target.value.trim().toLowerCase(); state.shown = 12; renderBoard(); });
$('#board-more').addEventListener('click', () => { state.shown += 24; renderBands(); });
$('#days').addEventListener('click', (e) => { const b = e.target.closest('.day'); if (!b) return; state.day = b.dataset.day; state.shown = 12; renderBoard(); $(`.day[data-day="${state.day}"]`).focus(); });
$('#days').addEventListener('keydown', (e) => {
  if (!['ArrowDown', 'ArrowUp', 'ArrowLeft', 'ArrowRight'].includes(e.key)) return;
  e.preventDefault();
  const tabs = $$('.day'); const i = tabs.findIndex((t) => t.dataset.day === state.day);
  const next = tabs[(i + (e.key === 'ArrowDown' || e.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length];
  next.click();
});
document.addEventListener('click', (e) => {
  const mark = e.target.closest('.mark');
  if (mark) {
    const url = mark.dataset.url;
    if (state.applied.has(url)) state.applied.delete(url); else state.applied.add(url);
    store.set(state.applied);
    renderAll();
  }
  if (e.target.closest('#toggle-applied')) { state.showApplied = !state.showApplied; renderBands(); renderDays(); }
});

fetch('roles.json', { cache: 'no-cache' })
  .then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
  .then((data) => {
    state.generated = Date.parse(data.generated_at);
    state.roles = data.roles.map((r) => ({ ...r, t: Date.parse(r.posted_at) })).sort((a, b) => b.t - a.t);
    renderAll();
  })
  .catch(() => {
    $('#ask-summary').textContent = "I couldn't reach this week's list just now. In your terminal, python3 shortlist.py shows the same roles.";
    $('#bands').innerHTML = '<li class="band band-note"><p>This week\'s list didn\'t load. Run <code>python3 shortlist.py --days 7</code> to see it in your terminal.</p></li>';
  });

/* ---------- how it works: one row through four stages ---------- */
const STAGES = [
  ['First, it finds the role', "Discovery reads the public feed and employer boards, then checks your whole tracker, so a role you've applied to never comes back."],
  ['Then you review the form', 'Your agent fills the form in Chrome from your profile and resume. Your prompt decides whether it may submit or must stop for you.'],
  ['It waits for the receipt', "A submission is recorded only after the employer's confirmation arrives. The row gets the date and the receipt."],
  ['Replies find their row', 'The optional Gmail monitor matches each recruiter email to its role, moves the stage, and writes your next step.'],
];
const how = $('#how');
function setStage(n) {
  const page = $('.row-page');
  $('#how-range').value = n;
  $('#how-fill').style.setProperty('--p', n / 3);
  $$('#how-stops button').forEach((b) => (Number(b.dataset.stage) === n ? b.setAttribute('aria-current', 'step') : b.removeAttribute('aria-current')));
  how.classList.add('is-swapping');
  setTimeout(() => {
    $('#how-title').textContent = STAGES[n][0];
    $('#how-note').textContent = STAGES[n][1];
    how.classList.remove('is-swapping');
  }, matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 200);
  page.dataset.stage = n;
  $$('[data-text]', page).forEach((el) => { const v = el.dataset.text.split('|')[n]; el.textContent = v; el.classList.toggle('is-empty', v === 'Empty'); });
  $$('.prop', page).forEach((p) => p.classList.toggle('changed', (p.dataset.changes || '').split(' ').includes(String(n))));
}
$('#how-range').addEventListener('input', (e) => setStage(Number(e.target.value)));
$('#how-stops').addEventListener('click', (e) => { const b = e.target.closest('button'); if (b) setStage(Number(b.dataset.stage)); });
setStage(0);

/* ---------- paperwork: output index ---------- */
const tabs = $$('.paper-names [role="tab"]');
function showSheet(tab) {
  tabs.forEach((t) => { const on = t === tab; t.setAttribute('aria-selected', String(on)); t.tabIndex = on ? 0 : -1; $('#' + t.getAttribute('aria-controls')).hidden = !on; });
  const caption = $('#paper-caption');
  caption.classList.add('is-swapping');
  setTimeout(() => { caption.textContent = $('#' + tab.getAttribute('aria-controls')).dataset.caption; caption.classList.remove('is-swapping'); }, 160);
}
tabs.forEach((t, i) => {
  t.addEventListener('click', () => showSheet(t));
  t.addEventListener('keydown', (e) => {
    const step = { ArrowDown: 1, ArrowRight: 1, ArrowUp: -1, ArrowLeft: -1 }[e.key];
    if (!step) return;
    e.preventDefault();
    const next = tabs[(i + step + tabs.length) % tabs.length]; next.focus(); showSheet(next);
  });
});

/* ---------- questions: one answer at a time ---------- */
const questions = $$('#questions > li > button');
const pane = $('#faq-pane-text');
function ask(button, toggle) {
  const open = toggle && button.getAttribute('aria-expanded') === 'true' && !matchMedia('(min-width: 56.25em)').matches;
  questions.forEach((q) => { const on = q === button && !open; q.setAttribute('aria-expanded', String(on)); $('#' + q.getAttribute('aria-controls')).hidden = !on; });
  if (open) return;
  const text = $('#' + button.getAttribute('aria-controls')).textContent.trim();
  if (pane.textContent === text) return;
  pane.classList.add('is-swapping');
  setTimeout(() => { pane.textContent = text; pane.classList.remove('is-swapping'); }, 150);
}
questions.forEach((q) => {
  q.addEventListener('click', () => ask(q, true));
  q.addEventListener('focus', () => { if (matchMedia('(min-width: 56.25em)').matches) ask(q); });
  q.addEventListener('mouseenter', () => { if (matchMedia('(hover: hover) and (min-width: 56.25em)').matches) ask(q); });
});

/* ---------- first step: build and copy the commands ---------- */
const starter = $('#starter');
function updateCommand() {
  const where = $('#starter-where').value.trim().replace(/"/g, '');
  const days = $('input[name="days"]:checked', starter).value;
  const field = state.field === 'all' ? '' : ` --field ${state.field}`;
  $('#starter-code').textContent = `git clone https://github.com/Cole-Godfrey/appy.git\ncd appy\npython3 shortlist.py${field} --days ${days}${where ? ` --where "${where}"` : ''}`;
}
starter.addEventListener('input', updateCommand);
starter.addEventListener('submit', async (e) => {
  e.preventDefault();
  const button = $('#starter-copy');
  try {
    await navigator.clipboard.writeText($('#starter-code').textContent);
    button.textContent = 'Copied. Paste it in your terminal';
  } catch {
    getSelection().selectAllChildren($('#starter-code'));
    button.textContent = 'Selected. Press Ctrl+C or ⌘C';
  }
  setTimeout(() => { button.textContent = 'Copy commands'; }, 2600);
});
updateCommand();

/* ---------- reveal once on entry; never leaves content hidden ---------- */
(() => {
  const targets = $$('[data-reveal]');
  if (!('IntersectionObserver' in window)) { targets.forEach((el) => el.classList.add('is-in')); return; }
  const io = new IntersectionObserver((entries) => {
    for (const entry of entries) if (entry.isIntersecting) { entry.target.classList.add('is-in'); io.unobserve(entry.target); }
  }, { rootMargin: '0px 0px -10% 0px', threshold: 0.1 });
  targets.forEach((el) => io.observe(el));
  addEventListener('load', () => setTimeout(() => targets.forEach((el) => { const r = el.getBoundingClientRect(); if (r.top < innerHeight && r.bottom > 0) el.classList.add('is-in'); }), 2500));
})();
