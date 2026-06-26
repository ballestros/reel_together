"use strict";

const BASE = window.__BASE__ || "";
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

const COLUMNS = [
  { key: "want", label: "Want to Watch", dot: "var(--dot-want)", empty: "Add something you want to watch." },
  { key: "watching", label: "Watching Now", dot: "var(--accent)", empty: "Nothing in progress yet." },
  { key: "watched", label: "Finished", dot: "var(--dot-finished)", empty: "Watched titles land here." },
];
const SERVICES = ["Netflix", "Max", "Hulu", "Prime Video", "Disney+", "Apple TV+", "Peacock", "Other"];
const ACCENTS = {
  Marigold: { a: "oklch(0.74 0.135 70)", soft: "oklch(0.95 0.05 80)", ink: "#4a3410" },
  Teal: { a: "oklch(0.70 0.095 195)", soft: "oklch(0.95 0.03 195)", ink: "#0e3033" },
  Rose: { a: "oklch(0.70 0.135 28)", soft: "oklch(0.95 0.045 30)", ink: "#4a1812" },
  Plum: { a: "oklch(0.62 0.13 320)", soft: "oklch(0.95 0.04 320)", ink: "#3a1238" },
};
const PERSON_COLORS = ["#4f7396", "#b5677a", "#7d8a5c", "#9a7bb0", "#c0823f", "#4aa0a0"];

const state = {
  me: null, users: {}, config: {},
  titles: [],
  typeFilter: "all", personFilter: "everyone", serviceFilter: "", search: "",
  modalSel: null,
};

// ---- helpers --------------------------------------------------------------
async function api(path, opts = {}) {
  const res = await fetch(BASE + path, { headers: { "Content-Type": "application/json" }, ...opts });
  if (!res.ok) {
    let m = res.statusText;
    try { m = (await res.json()).error || m; } catch (_) {}
    throw new Error(m);
  }
  return res.status === 204 ? null : res.json();
}
function initials(n) { return (n || "?").trim().split(/\s+/).map(w => w[0]).slice(0, 2).join("").toUpperCase(); }
function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }
function toast(msg) { const t = $("#toast"); t.textContent = msg; t.hidden = false; clearTimeout(toast._t); toast._t = setTimeout(() => (t.hidden = true), 2400); }
function userColor(id) { return (state.users[id] && state.users[id].color) || "#999"; }

function assignColors() {
  const ids = Object.keys(state.users);
  ids.sort((a, b) => a === state.me.id ? -1 : b === state.me.id ? 1 : (state.users[a].display_name || "").localeCompare(state.users[b].display_name || ""));
  ids.forEach((id, i) => (state.users[id].color = PERSON_COLORS[i % PERSON_COLORS.length]));
}

// ---- boot -----------------------------------------------------------------
async function boot() {
  applyAccent(localStorage.getItem("rt_accent") || "Marigold");
  applyCompact(localStorage.getItem("rt_compact") === "1");
  try {
    const me = await api("/api/me");
    state.me = me.user; state.config = me.config || {};
    for (const u of me.users) state.users[u.id] = { ...u };
    if (!state.users[me.user.id]) state.users[me.user.id] = { ...me.user };
    assignColors();
    renderMe();
    await loadTitles();
  } catch (e) { toast("Couldn't load: " + e.message); }
  wireUI();
  // Gentle background refresh: surfaces TMDB enrichment and other people's
  // changes without a manual reload. Skipped while busy to avoid disruption.
  setInterval(() => {
    if (document.hidden) return;
    if (!$("#modal-backdrop").hidden) return;
    if (!$("#rematch-backdrop").hidden) return;
    if (document.querySelector(".card.dragging")) return;
    loadTitles().catch(() => {});
  }, 15000);
}

async function loadTitles() {
  const data = await api("/api/titles");
  state.titles = data.titles || [];
  populateServiceFilter();
  renderBoard();
}

function renderMe() {
  const av = $("#me-avatar");
  av.textContent = initials(state.me.display_name);
  av.style.background = userColor(state.me.id);
  av.title = state.me.display_name + (state.config.provider ? `  ·  ${state.config.provider}` : "");
}

function populateServiceFilter() {
  const sel = $("#service-filter");
  const present = [...new Set(state.titles.map(t => t.service).filter(Boolean))];
  const opts = [...new Set([...present, ...SERVICES])];
  sel.innerHTML = `<option value="">All services</option>` + opts.map(s => `<option value="${esc(s)}">${esc(s)}</option>`).join("");
  sel.value = state.serviceFilter;
}

// ---- board ----------------------------------------------------------------
function columnFor(t) {
  if (state.personFilter === "me") return t.my_status; // null/'skip' dropped by the bucket guard
  const st = (t.interests || []).map(i => i.status);
  if (st.includes("watching")) return "watching";
  if (st.includes("want")) return "want";
  if (st.includes("watched")) return "watched";
  if (st.length) return null; // only 'skip' → don't show
  return "want"; // in catalog but nobody has a status yet → Want to Watch
}

function visibleTitles() {
  return state.titles.filter(t => {
    if (state.typeFilter !== "all" && t.type !== state.typeFilter) return false;
    if (state.serviceFilter && t.service !== state.serviceFilter) return false;
    if (state.search && !(t.title || "").toLowerCase().includes(state.search)) return false;
    if (state.personFilter === "me" && !t.my_status) return false;
    return true;
  });
}

function renderBoard() {
  const board = $("#board");
  const items = visibleTitles();
  const buckets = { want: [], watching: [], watched: [] };
  for (const t of items) {
    const c = columnFor(t);
    if (buckets[c]) buckets[c].push(t);
  }
  board.innerHTML = "";
  for (const col of COLUMNS) {
    const list = buckets[col.key];
    const el = document.createElement("section");
    el.className = "column";
    el.dataset.col = col.key;
    el.innerHTML = `
      <div class="column-head">
        <span class="dot" style="background:${col.dot}"></span>
        <h2>${col.label}</h2>
        <span class="count">${list.length}</span>
      </div>
      <div class="cards"></div>`;
    const cards = $(".cards", el);
    if (!list.length) cards.innerHTML = `<div class="column-empty">${col.empty}</div>`;
    else for (const t of list) cards.appendChild(card(t, col.key));
    wireDrop(el, col.key);
    board.appendChild(el);
  }
}

function dotsHtml(t) {
  const ints = (t.interests || []).slice(0, 4);
  const extra = (t.interests || []).length - ints.length;
  let h = ints.map(i => `<span class="pd" title="${esc(i.display_name)} — ${i.status}" style="background:${userColor(i.user_id)}">${initials(i.display_name)}</span>`).join("");
  if (extra > 0) h += `<span class="pd" style="background:var(--faint2)">+${extra}</span>`;
  return h;
}

function card(t, colKey) {
  const el = document.createElement("article");
  el.className = "card";
  el.draggable = true;
  const sub = [t.year, t.type !== "unknown" ? (t.type === "tv" ? "TV" : "Movie") : null].filter(Boolean).join(" · ");
  const together = colKey === "want" && t.want_count >= 2;
  el.innerHTML = `
    <div class="top">
      ${t.poster_url ? `<img class="poster" src="${esc(t.poster_url)}" alt="" loading="lazy">` : `<div class="poster noart">🎬</div>`}
      <div class="meta">
        <div class="title">${esc(t.title)}</div>
        <div class="sub">${esc(sub)}</div>
        ${t.service ? `<span class="service">${esc(t.service)}</span>` : ""}
        ${together ? `<span class="together-badge">★ Together</span>` : ""}
      </div>
      <div class="dots">${dotsHtml(t)}</div>
      <button class="remove" title="Remove">&times;</button>
    </div>`;

  $(".remove", el).onclick = (e) => { e.stopPropagation(); removeTitle(t); };
  if (state.config.tmdb_enabled) {
    const rb = document.createElement("button");
    rb.className = "rematch";
    rb.textContent = "↻";
    rb.title = "Not the right match? Re-match from TMDB";
    rb.onclick = (e) => { e.stopPropagation(); openRematch(t); };
    $(".top", el).appendChild(rb);
  }

  if (colKey === "watching") {
    if (t.type === "tv" && t.episodes_total) el.appendChild(episodeBlock(t));
    el.appendChild(markFinished(t));
  }
  if (colKey === "watched") el.appendChild(starsBlock(t));

  el.addEventListener("dragstart", (e) => { e.dataTransfer.setData("text/plain", String(t.id)); e.dataTransfer.effectAllowed = "move"; el.classList.add("dragging"); });
  el.addEventListener("dragend", () => el.classList.remove("dragging"));
  return el;
}

function episodeBlock(t) {
  const wrap = document.createElement("div");
  wrap.className = "episodes";
  const w = t.episodes_watched || 0, tot = t.episodes_total;
  const pct = tot ? Math.round((w / tot) * 100) : 0;
  wrap.innerHTML = `
    <div class="epbar"><span style="width:${pct}%"></span></div>
    <div class="eprow">
      <span class="label">${w} / ${tot} eps${t.seasons ? ` · ${t.seasons} season${t.seasons > 1 ? "s" : ""}` : ""}</span>
      <span class="stepper"><button data-d="-1">−</button><button data-d="1">+</button></span>
    </div>`;
  $$(".stepper button", wrap).forEach(b => b.onclick = (e) => { e.stopPropagation(); stepEpisodes(t, parseInt(b.dataset.d, 10)); });
  return wrap;
}

function markFinished(t) {
  const b = document.createElement("button");
  b.className = "markfin";
  b.textContent = "Mark finished";
  b.onclick = (e) => { e.stopPropagation(); setStatus(t.id, "watched"); };
  return b;
}

function starsBlock(t) {
  const wrap = document.createElement("div");
  wrap.className = "stars";
  for (let i = 1; i <= 5; i++) {
    const s = document.createElement("span");
    s.textContent = "★";
    if (t.my_rating && i <= t.my_rating) s.classList.add("lit");
    s.onclick = (e) => { e.stopPropagation(); rate(t.id, i); };
    wrap.appendChild(s);
  }
  return wrap;
}

function wireDrop(colEl, colKey) {
  colEl.addEventListener("dragover", (e) => { e.preventDefault(); colEl.classList.add("drag-over"); });
  colEl.addEventListener("dragleave", (e) => { if (!colEl.contains(e.relatedTarget)) colEl.classList.remove("drag-over"); });
  colEl.addEventListener("drop", (e) => {
    e.preventDefault();
    colEl.classList.remove("drag-over");
    const id = parseInt(e.dataTransfer.getData("text/plain"), 10);
    if (id) setStatus(id, colKey);
  });
}

// ---- mutations ------------------------------------------------------------
async function setStatus(id, status) {
  try { await api(`/api/titles/${id}/interest`, { method: "PUT", body: JSON.stringify({ status }) }); await loadTitles(); }
  catch (e) { toast("Update failed: " + e.message); }
}
async function rate(id, rating) {
  try { await api(`/api/titles/${id}/interest`, { method: "PUT", body: JSON.stringify({ rating }) }); await loadTitles(); }
  catch (e) { toast("Rating failed: " + e.message); }
}
async function stepEpisodes(t, delta) {
  const next = Math.max(0, Math.min(t.episodes_total || 9999, (t.episodes_watched || 0) + delta));
  try { await api(`/api/titles/${t.id}`, { method: "PUT", body: JSON.stringify({ episodes_watched: next }) }); await loadTitles(); }
  catch (e) { toast("Update failed: " + e.message); }
}
async function removeTitle(t) {
  if (!confirm(`Remove "${t.title}" from your shared list?`)) return;
  try { await api(`/api/titles/${t.id}`, { method: "DELETE" }); toast(`Removed "${t.title}"`); await loadTitles(); }
  catch (e) { toast("Remove failed: " + e.message); }
}

// ---- add modal ------------------------------------------------------------
function openModal() {
  state.modalSel = null;
  $("#modal-search").value = "";
  $("#modal-results").hidden = true; $("#modal-results").innerHTML = "";
  $("#modal-selected").hidden = true;
  $("#tv-fields").hidden = true;
  $("#f-type").value = "movie";
  $("#f-service").innerHTML = `<option value="">—</option>` + SERVICES.map(s => `<option>${esc(s)}</option>`).join("");
  $("#f-seasons").value = 1; $("#f-episodes").value = "";
  $$("#f-status button").forEach((b, i) => b.classList.toggle("on", i === 0));
  // who chips
  const who = $("#f-who");
  who.innerHTML = Object.values(state.users).map(u =>
    `<span class="who-chip ${u.id === state.me.id ? "on" : ""}" data-uid="${esc(u.id)}">
       <span class="pd" style="background:${userColor(u.id)}">${initials(u.display_name)}</span>${esc(u.id === state.me.id ? "Me" : u.display_name)}
     </span>`).join("");
  $$(".who-chip", who).forEach(c => c.onclick = () => c.classList.toggle("on"));
  $("#modal-add").disabled = true;
  $("#modal-backdrop").hidden = false;
  $("#modal-search").focus();
}
function closeModal() { $("#modal-backdrop").hidden = true; }

let modalTimer = null;
function onModalSearch(e) {
  const q = e.target.value.trim();
  clearTimeout(modalTimer);
  if (q.length < 2) { $("#modal-results").hidden = true; return; }
  modalTimer = setTimeout(() => runModalSearch(q), 250);
}
async function runModalSearch(q) {
  let data; try { data = await api("/api/search?q=" + encodeURIComponent(q)); } catch (_) { return; }
  const box = $("#modal-results");
  box.innerHTML = "";
  if (!data.results.length) { box.innerHTML = `<div class="mr-item muted">No matches</div>`; box.hidden = false; return; }
  for (const r of data.results) {
    const row = document.createElement("div");
    row.className = "mr-item";
    const sub = [r.year, r.type !== "unknown" ? (r.type === "tv" ? "TV" : "Movie") : null].filter(Boolean).join(" · ");
    row.innerHTML = `${r.poster_url ? `<img src="${esc(r.poster_url)}" alt="">` : `<div class="ph"></div>`}
      <div><div class="t">${esc(r.title)}</div><div class="s">${esc(sub || (r.in_catalog ? "Already on your list" : ""))}</div></div>`;
    row.onclick = () => selectModalResult(r);
    box.appendChild(row);
  }
  box.hidden = false;
}
function selectModalResult(r) {
  state.modalSel = r;
  $("#modal-results").hidden = true;
  $("#modal-search").value = r.title;
  const sel = $("#modal-selected");
  sel.hidden = false;
  sel.innerHTML = `${r.poster_url ? `<img src="${esc(r.poster_url)}" alt="">` : `<div class="ph"></div>`}
    <div><div class="t">${esc(r.title)}</div><div class="s muted">${esc([r.year, r.source].filter(Boolean).join(" · "))}</div></div>`;
  if (r.type === "tv") { $("#f-type").value = "tv"; $("#tv-fields").hidden = false; }
  else { $("#f-type").value = "movie"; $("#tv-fields").hidden = true; }
  $("#modal-add").disabled = false;
}
async function submitModal() {
  if (!state.modalSel) return;
  const type = $("#f-type").value;
  const status = $("#f-status button.on").dataset.status;
  const who = $$(".who-chip.on").map(c => c.dataset.uid);
  const body = {
    ...state.modalSel,
    type,
    service: $("#f-service").value || null,
    seasons: type === "tv" ? (parseInt($("#f-seasons").value, 10) || null) : null,
    episodes_total: type === "tv" ? (parseInt($("#f-episodes").value, 10) || null) : null,
    who: who.length ? who : [state.me.id],
    status,
  };
  $("#modal-add").disabled = true;
  try {
    await api("/api/titles", { method: "POST", body: JSON.stringify(body) });
    toast(`Added "${state.modalSel.title}"`);
    closeModal();
    populateServiceFilter();
    await loadTitles();
    // Background enrichment usually lands within a second or two — pick it up.
    setTimeout(() => loadTitles().catch(() => {}), 2500);
  } catch (e) { toast("Add failed: " + e.message); $("#modal-add").disabled = false; }
}

// ---- re-match (fix a wrong TMDB match) ------------------------------------
let rematchTarget = null, rematchTimer = null;
function openRematch(t) {
  rematchTarget = t;
  $("#rematch-for").textContent = `Currently showing: ${t.title}${t.year ? " (" + t.year + ")" : ""}. Pick the correct entry below.`;
  $("#rematch-search").value = t.title;
  $("#rematch-results").innerHTML = "";
  $("#rematch-backdrop").hidden = false;
  $("#rematch-search").focus();
  runRematchSearch(t.title);
}
function closeRematch() { $("#rematch-backdrop").hidden = true; rematchTarget = null; }
async function runRematchSearch(q) {
  if (!rematchTarget || !q || q.length < 2) return;
  let data;
  try { data = await api(`/api/titles/${rematchTarget.id}/matches?q=` + encodeURIComponent(q)); }
  catch (e) { toast(e.message); return; }
  const box = $("#rematch-results");
  box.innerHTML = "";
  if (!data.results || !data.results.length) { box.innerHTML = `<div class="mr-item muted">No TMDB matches</div>`; return; }
  for (const r of data.results) {
    const row = document.createElement("div");
    row.className = "mr-item";
    const sub = [r.year, r.type === "tv" ? "TV" : "Movie"].filter(Boolean).join(" · ");
    row.innerHTML = `${r.poster_url ? `<img src="${esc(r.poster_url)}" alt="">` : `<div class="ph"></div>`}
      <div><div class="t">${esc(r.title)}</div><div class="s">${esc(sub)}</div></div>`;
    row.onclick = () => applyRematch(r);
    box.appendChild(row);
  }
}
async function applyRematch(r) {
  if (!rematchTarget) return;
  try {
    await api(`/api/titles/${rematchTarget.id}/rematch`, { method: "POST", body: JSON.stringify({ tmdb_id: r.source_id, type: r.type }) });
    toast(`Updated match to "${r.title}"`);
    closeRematch();
    await loadTitles();
  } catch (e) { toast("Re-match failed: " + e.message); }
}

// ---- appearance -----------------------------------------------------------
function applyAccent(name) {
  const a = ACCENTS[name] || ACCENTS.Marigold;
  const r = document.documentElement.style;
  r.setProperty("--accent", a.a); r.setProperty("--accent-soft", a.soft); r.setProperty("--accent-ink", a.ink);
  localStorage.setItem("rt_accent", name);
}
function applyCompact(on) { document.body.classList.toggle("compact", on); localStorage.setItem("rt_compact", on ? "1" : ""); }

function toggleAccentMenu() {
  const m = $("#accent-menu");
  if (!m.hidden) { m.hidden = true; return; }
  const cur = localStorage.getItem("rt_accent") || "Marigold";
  const compact = document.body.classList.contains("compact");
  m.innerHTML = `
    <div class="row">${Object.entries(ACCENTS).map(([n, a]) =>
      `<span class="swatch ${n === cur ? "on" : ""}" title="${n}" data-accent="${n}" style="background:${a.a}"></span>`).join("")}</div>
    <label>Compact cards <input type="checkbox" id="compact-toggle" ${compact ? "checked" : ""}></label>`;
  $$(".swatch", m).forEach(s => s.onclick = () => { applyAccent(s.dataset.accent); $$(".swatch", m).forEach(x => x.classList.remove("on")); s.classList.add("on"); });
  $("#compact-toggle", m).onchange = (e) => applyCompact(e.target.checked);
  const r = $("#accent-btn").getBoundingClientRect();
  m.style.top = (r.bottom + 8) + "px";
  m.style.right = (window.innerWidth - r.right) + "px";
  m.hidden = false;
}

// ---- wiring ---------------------------------------------------------------
function wireUI() {
  $("#type-filter").addEventListener("click", e => { const b = e.target.closest("button"); if (!b) return; state.typeFilter = b.dataset.type; setOn("#type-filter", b); renderBoard(); });
  $("#person-filter").addEventListener("click", e => { const b = e.target.closest("button"); if (!b) return; state.personFilter = b.dataset.person; setOn("#person-filter", b); renderBoard(); });
  $("#service-filter").addEventListener("change", e => { state.serviceFilter = e.target.value; renderBoard(); });
  $("#board-search").addEventListener("input", e => { state.search = e.target.value.trim().toLowerCase(); renderBoard(); });
  $("#add-btn").addEventListener("click", openModal);
  $("#modal-close").addEventListener("click", closeModal);
  $("#modal-cancel").addEventListener("click", closeModal);
  $("#modal-add").addEventListener("click", submitModal);
  $("#modal-search").addEventListener("input", onModalSearch);
  $("#f-type").addEventListener("change", e => { $("#tv-fields").hidden = e.target.value !== "tv"; });
  $("#f-status").addEventListener("click", e => { const b = e.target.closest("button"); if (b) setOn("#f-status", b); });
  $("#modal-backdrop").addEventListener("click", e => { if (e.target.id === "modal-backdrop") closeModal(); });
  $("#rematch-close").addEventListener("click", closeRematch);
  $("#rematch-cancel").addEventListener("click", closeRematch);
  $("#rematch-backdrop").addEventListener("click", e => { if (e.target.id === "rematch-backdrop") closeRematch(); });
  $("#rematch-search").addEventListener("input", e => { clearTimeout(rematchTimer); const q = e.target.value.trim(); rematchTimer = setTimeout(() => runRematchSearch(q), 250); });
  $("#accent-btn").addEventListener("click", (e) => { e.stopPropagation(); toggleAccentMenu(); });
  document.addEventListener("click", e => { if (!e.target.closest("#accent-menu") && !e.target.closest("#accent-btn")) $("#accent-menu").hidden = true; });
  document.addEventListener("keydown", e => { if (e.key === "Escape") { closeModal(); closeRematch(); $("#accent-menu").hidden = true; } });
}
function setOn(container, btn) { $$(container + " button").forEach(b => b.classList.remove("on")); btn.classList.add("on"); }

document.addEventListener("DOMContentLoaded", boot);
