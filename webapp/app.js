"use strict";

const tg = window.Telegram && window.Telegram.WebApp;
const $view = document.getElementById("view");
const $cta = document.getElementById("cta");
const $tabbar = document.getElementById("tabbar");

// ================= Справочники =================

const ICONS = {
  bulb: '<path d="M9 18h6"/><path d="M10 22h4"/><path d="M15.09 14c.18-.98.65-1.74 1.41-2.5A4.65 4.65 0 0 0 18 8 6 6 0 0 0 6 8c0 1 .23 2.23 1.5 3.5A4.61 4.61 0 0 1 8.91 14"/>',
  magnet: '<path d="m6 15-4-4 6.75-6.77a7.79 7.79 0 0 1 11 11L13 22l-4-4 6.39-6.36a2.14 2.14 0 0 0-3-3L6 15"/><path d="m5 8 4 4"/><path d="m12 15 4 4"/>',
  scan: '<path d="M3 7V5a2 2 0 0 1 2-2h2"/><path d="M17 3h2a2 2 0 0 1 2 2v2"/><path d="M21 17v2a2 2 0 0 1-2 2h-2"/><path d="M7 21H5a2 2 0 0 1-2-2v-2"/><circle cx="12" cy="12" r="3"/><path d="m16 16-1.9-1.9"/>',
  phone: '<rect x="5" y="2" width="14" height="20" rx="2.5"/><path d="M12 18h.01"/>',
  zap: '<path d="M13 2 3 14h9l-1 8 10-12h-9l1-8z"/>',
  clapper: '<path d="M20.2 6 3 11l-.9-2.4c-.3-1.1.3-2.2 1.3-2.5l13.5-4c1.1-.3 2.2.3 2.5 1.3Z"/><path d="m6.2 5.3 3.1 3.9"/><path d="m12.4 3.4 3.1 4"/><path d="M3 11h18v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/>',
  layers: '<path d="m12 2 10 5-10 5L2 7z"/><path d="m2 17 10 5 10-5"/><path d="m2 12 10 5 10-5"/>',
  aperture: '<circle cx="12" cy="12" r="10"/><path d="m14.31 8 5.74 9.94"/><path d="M9.69 8h11.48"/><path d="m7.38 12 5.74-9.94"/><path d="M9.69 16 3.95 6.06"/><path d="M14.31 16H2.83"/><path d="m16.62 12-5.74 9.94"/>',
  image: '<rect x="3" y="3" width="18" height="18" rx="2.5"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.1-3.1a2 2 0 0 0-2.8 0L6 21"/>',
  sparkles: '<path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z"/><path d="M19 3v4"/><path d="M17 5h4"/><path d="M5 17v4"/><path d="M3 19h4"/>',
  video: '<path d="m16 13 5.2 3.5a.5.5 0 0 0 .8-.4V7.9a.5.5 0 0 0-.8-.4L16 11"/><rect x="2" y="6" width="14" height="12" rx="2.5"/>',
  mic: '<rect x="9" y="2" width="6" height="12" rx="3"/><path d="M19 10v1a7 7 0 0 1-14 0v-1"/><path d="M12 18v4"/>',
  user: '<rect x="3" y="3" width="18" height="18" rx="2.5"/><circle cx="12" cy="10" r="3"/><path d="M7 21v-2a2 2 0 0 1 2-2h6a2 2 0 0 1 2 2v2"/>',
  home: '<path d="m3 10 9-7 9 7v10a2 2 0 0 1-2 2h-4v-7H9v7H5a2 2 0 0 1-2-2z"/>',
  clock: '<circle cx="12" cy="12" r="9.5"/><path d="M12 7v5l3 2"/>',
  sliders: '<path d="M4 21v-7"/><path d="M4 10V3"/><path d="M12 21v-9"/><path d="M12 8V3"/><path d="M20 21v-5"/><path d="M20 12V3"/><path d="M1 14h6"/><path d="M9 8h6"/><path d="M17 16h6"/>',
  search: '<circle cx="11" cy="11" r="7.5"/><path d="m20.5 20.5-4.2-4.2"/>',
  back: '<path d="m15 18-6-6 6-6"/>',
  down: '<path d="m6 9 6 6 6-6"/>',
  right: '<path d="m9 18 6-6-6-6"/>',
  copy: '<rect x="9" y="9" width="13" height="13" rx="2.5"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
  send: '<path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/>',
  refresh: '<path d="M3 12a9 9 0 0 1 15-6.7L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-15 6.7L3 16"/><path d="M8 16H3v5"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  checkCircle: '<circle cx="12" cy="12" r="10"/><path d="m8.5 12 2.5 2.5 5-5"/>',
  x: '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
  upload: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m17 8-5-5-5 5"/><path d="M12 3v12"/>',
  file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/>',
  music: '<path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>',
  film: '<rect x="3" y="3" width="18" height="18" rx="2.5"/><path d="M7 3v18"/><path d="M17 3v18"/><path d="M3 12h18"/><path d="M3 7.5h4"/><path d="M3 16.5h4"/><path d="M17 7.5h4"/><path d="M17 16.5h4"/>',
  info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
  alert: '<circle cx="12" cy="12" r="10"/><path d="M12 8v4"/><path d="M12 16h.01"/>',
  minus: '<path d="M5 12h14"/>',
  plus: '<path d="M12 5v14"/><path d="M5 12h14"/>',
  cpu: '<rect x="4" y="4" width="16" height="16" rx="2.5"/><rect x="9" y="9" width="6" height="6" rx="1"/><path d="M9 1v3"/><path d="M15 1v3"/><path d="M9 20v3"/><path d="M15 20v3"/><path d="M20 9h3"/><path d="M20 14h3"/><path d="M1 9h3"/><path d="M1 14h3"/>',
  trash: '<path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>',
  chat: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
};

function icon(name, cls = "") {
  return `<svg class="ic ${cls}" viewBox="0 0 24 24" aria-hidden="true">${ICONS[name] || ICONS.sparkles}</svg>`;
}

const CATS = {
  scripts: { name: "Сценарии", tint: "#8b7cff" },
  prompts: { name: "Промпты", tint: "#f2a33a" },
  visual: { name: "Визуал", tint: "#20b8a0" },
  media: { name: "Видео и голос", tint: "#ef5b84" },
};
const PROVIDERS = [["claude", "Claude"], ["openai", "ChatGPT"], ["gemini", "Gemini"]];
const SERVICE_NAMES = { claude: "Claude", openai: "ChatGPT", gemini: "Gemini", elevenlabs: "ElevenLabs" };
const LANGS = [["ru", "Русский"], ["uz", "O'zbek"], ["en", "English"]];
const THEMES = [
  ["indigo", "Индиго", "#0b0c10", "#7c6cff"],
  ["emerald", "Изумруд", "#090c0b", "#10b981"],
  ["ocean", "Океан", "#080b12", "#3b82f6"],
  ["light", "Светлая", "#f4f5f8", "#5b4cff"],
];
const STATUS_TEXT = ["Отправляю запрос…", "Модель анализирует задачу…", "Пишу результат…", "Ещё немного…", "Почти готово…"];

// ================= Состояние =================

const S = {
  cfg: null,
  tab: "home",
  tool: null,
  historyItem: null,
  values: {},
  files: {},
  provider: "",
  busy: false,
  voices: null,
  query: "",
  cat: "all",
  settings: Object.assign({ provider: "", lang: "ru", toChat: true, theme: "indigo" }, load("settings", {})),
};

// ================= Утилиты =================

function load(key, fallback) {
  try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; }
}
function save(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* хранилище недоступно */ }
}
function saveSettings() { save("settings", S.settings); }

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function rgba(hex, a) {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
}
function haptic(kind = "light") {
  try {
    if (kind === "success" || kind === "error") tg.HapticFeedback.notificationOccurred(kind);
    else if (kind === "select") tg.HapticFeedback.selectionChanged();
    else tg.HapticFeedback.impactOccurred(kind);
  } catch { /* вне Telegram */ }
}
function toast(text, ic = "check") {
  const el = document.getElementById("toast");
  el.innerHTML = `${icon(ic, "sm")}<span>${esc(text)}</span>`;
  el.classList.add("show");
  clearTimeout(toast.t);
  toast.t = setTimeout(() => el.classList.remove("show"), 1900);
}
async function copy(text) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.append(ta);
    ta.select();
    document.execCommand("copy");
    ta.remove();
  }
  haptic("success");
  toast("Скопировано");
}
function fileSize(bytes) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} КБ`;
  return `${(bytes / 1024 / 1024).toFixed(1)} МБ`;
}
function fmtTime(ts) {
  return new Date(ts).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
}
function dayLabel(ts) {
  const d = new Date(ts), today = new Date();
  const diff = Math.round((new Date(today.toDateString()) - new Date(d.toDateString())) / 86400000);
  if (diff === 0) return "Сегодня";
  if (diff === 1) return "Вчера";
  return d.toLocaleDateString("ru-RU", { day: "numeric", month: "long" });
}

async function api(path, opts = {}) {
  const headers = Object.assign({ "X-Telegram-Init-Data": (tg && tg.initData) || "" }, opts.headers || {});
  const resp = await fetch(path, Object.assign({}, opts, { headers }));
  let data;
  try { data = await resp.json(); } catch { data = {}; }
  if (!resp.ok) throw new Error(data.error || `Ошибка сервера (${resp.status})`);
  return data;
}

function providers() { return (S.cfg && S.cfg.providers) || {}; }
function providerName(id) { return (PROVIDERS.find(([p]) => p === id) || [id, id])[1]; }
function defaultProvider() {
  const p = providers();
  if (S.settings.provider && p[S.settings.provider]) return S.settings.provider;
  return (PROVIDERS.find(([id]) => p[id]) || ["claude"])[0];
}
function tint(tool) { return (CATS[tool.category] || CATS.scripts).tint; }
function tileIcon(tool, size = "") {
  const t = tint(tool);
  return `<div class="tile-ic ${size}" style="background:${rgba(t, 0.15)};color:${t}">${icon(tool.icon)}</div>`;
}
function toolById(id) {
  return (S.cfg.tools || []).find((t) => t.id === id) || { id, icon: "file", category: "scripts", title: "" };
}
function engineTag(tool) {
  const p = providers();
  if (tool.needs.some((n) => !p[n])) return "Нет ключа";
  if (tool.needs.includes("elevenlabs")) return "ElevenLabs";
  if (tool.needs.includes("gemini")) return "Gemini";
  return "";
}

// ================= Тема =================

function applyTheme() {
  const theme = THEMES.some(([id]) => id === S.settings.theme) ? S.settings.theme : "indigo";
  document.documentElement.dataset.theme = theme;
  const bg = getComputedStyle(document.documentElement).getPropertyValue("--bg").trim();
  try {
    tg.setHeaderColor(bg);
    tg.setBackgroundColor(bg);
    tg.setBottomBarColor(bg);
  } catch { /* старый клиент Telegram */ }
}

// ================= Шторка выбора =================

function openSheet({ title, options, value, onPick }) {
  const wrap = document.createElement("div");
  wrap.className = "sheet-wrap";
  let lastGroup = null;
  const rows = options.map((o, i) => {
    let head = "";
    if (o.group && o.group !== lastGroup) { head = `<div class="group">${esc(o.group)}</div>`; lastGroup = o.group; }
    const on = o.value === value;
    return `${head}<button class="opt ${on ? "on" : ""}" data-i="${i}" ${o.disabled ? "disabled" : ""}>
      <span>${esc(o.label)}${o.sub ? `<small>${esc(o.sub)}</small>` : ""}</span>${on ? icon("check") : ""}</button>`;
  }).join("");
  wrap.innerHTML = `<div class="scrim"></div><div class="sheet" role="dialog"><div class="handle"></div>
    <h3>${esc(title)}</h3><div class="opts">${rows}</div></div>`;
  const close = () => wrap.remove();
  wrap.querySelector(".scrim").onclick = close;
  wrap.querySelectorAll(".opt").forEach((b) => {
    b.onclick = () => { haptic("select"); close(); onPick(options[+b.dataset.i].value); };
  });
  document.body.append(wrap);
  haptic();
}

// ================= Markdown =================

function inline(s) {
  return esc(s)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[\s(])\*([^*\s][^*]*)\*(?=[\s).,!?:;]|$)/g, "$1<em>$2</em>");
}

function codeBlock(code, lang) {
  const label = /^(srt|json|html|css|js)$/i.test(lang) ? lang.toUpperCase() : "Промпт";
  return `<div class="code"><div class="code-head"><span>${esc(label)}</span>
    <button type="button" data-copy-code>${icon("copy", "sm")}Копировать</button></div><pre>${esc(code)}</pre></div>`;
}

function markdown(src) {
  const codes = [];
  src = String(src || "").replace(/```([^\n]*)\n([\s\S]*?)```/g, (_, lang, code) => {
    codes.push([code.replace(/\n+$/, ""), lang.trim()]);
    return `\n\u0000${codes.length - 1}\u0000\n`;
  });

  let html = "";
  let para = [], list = null, table = [];
  const flushPara = () => { if (para.length) html += `<p>${para.map(inline).join("<br>")}</p>`; para = []; };
  const flushList = () => { if (list) html += `<${list.tag}>${list.items.map((i) => `<li>${inline(i)}</li>`).join("")}</${list.tag}>`; list = null; };
  const flushTable = () => {
    if (!table.length) return;
    const rows = table.filter((r) => !/^\|?\s*:?-{2,}/.test(r))
      .map((r) => r.replace(/^\||\|$/g, "").split("|").map((c) => c.trim()));
    const [head, ...body] = rows;
    html += `<div class="table-wrap"><table><thead><tr>${head.map((c) => `<th>${inline(c)}</th>`).join("")}</tr></thead>`
      + `<tbody>${body.map((r) => `<tr>${r.map((c) => `<td>${inline(c)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
    table = [];
  };
  const flushAll = () => { flushPara(); flushList(); flushTable(); };

  for (const raw of src.split("\n")) {
    const t = raw.trim();
    let m;
    if ((m = t.match(/^\u0000(\d+)\u0000$/))) { flushAll(); html += codeBlock(...codes[+m[1]]); continue; }
    if (!t) { flushAll(); continue; }
    if (t.startsWith("|")) { flushPara(); flushList(); table.push(t); continue; }
    flushTable();
    if ((m = t.match(/^(#{1,4})\s+(.*)$/))) { flushAll(); const n = Math.min(3, m[1].length); html += `<h${n}>${inline(m[2])}</h${n}>`; continue; }
    if (/^(-{3,}|\*{3,}|_{3,})$/.test(t)) { flushAll(); html += "<hr>"; continue; }
    if ((m = t.match(/^[-*•]\s+(.*)$/)) || (m = t.match(/^\d+[.)]\s+(.*)$/))) {
      const tag = /^\d/.test(t) ? "ol" : "ul";
      flushPara();
      if (!list || list.tag !== tag) { flushList(); list = { tag, items: [] }; }
      list.items.push(m[1]);
      continue;
    }
    flushList();
    para.push(t);
  }
  flushAll();
  return html;
}

// ================= Навигация =================

function setTab(tab) {
  if (S.busy) return;
  S.tab = tab;
  S.tool = null;
  S.historyItem = null;
  render();
}

function goBack() {
  if (S.busy) { toast("Дождитесь окончания генерации", "info"); return; }
  S.tool = null;
  S.historyItem = null;
  render();
}

function render() {
  window.scrollTo(0, 0);
  const inner = Boolean(S.tool || S.historyItem);
  if (tg && tg.BackButton) inner ? tg.BackButton.show() : tg.BackButton.hide();
  $tabbar.classList.toggle("hidden", Boolean(S.tool));
  $tabbar.querySelectorAll("button").forEach((b) => b.classList.toggle("active", b.dataset.tab === S.tab));
  $cta.innerHTML = "";
  $view.classList.toggle("with-cta", Boolean(S.tool));
  // перезапуск анимации появления
  $view.style.animation = "none";
  void $view.offsetWidth;
  $view.style.animation = "";

  if (S.tool) return renderTool(S.tool);
  if (S.historyItem) return renderHistoryItem(S.historyItem);
  if (S.tab === "history") return renderHistory();
  if (S.tab === "settings") return renderSettings();
  return renderHome();
}

// ================= Главная =================

function greeting() {
  const h = new Date().getHours();
  if (h < 5) return "Доброй ночи";
  if (h < 12) return "Доброе утро";
  if (h < 18) return "Добрый день";
  return "Добрый вечер";
}

function toolCard(t) {
  const tag = engineTag(t);
  return `<button class="card ${tag === "Нет ключа" ? "off" : ""}" data-tool="${t.id}">
    ${tileIcon(t)}${tag ? `<span class="tag">${tag}</span>` : ""}
    <h4>${esc(t.title)}</h4><p>${esc(t.subtitle)}</p></button>`;
}

function chooseDefaultModel(after) {
  const p = providers(), models = S.cfg.models || {};
  openSheet({
    title: "Модель по умолчанию",
    value: defaultProvider(),
    options: PROVIDERS.map(([id, label]) => ({ value: id, label, sub: p[id] ? models[id] : "Нет ключа API", disabled: !p[id] })),
    onPick: (v) => { S.settings.provider = v; saveSettings(); toast(`Модель: ${providerName(v)}`); after(); },
  });
}

function renderHome() {
  const user = S.cfg.user || {};
  const name = [user.first_name, user.last_name].filter(Boolean).join(" ");
  const initials = (user.first_name || "A").slice(0, 1).toUpperCase();
  const q = S.query.trim().toLowerCase();
  const tools = S.cfg.tools.filter((t) =>
    (S.cat === "all" || t.category === S.cat) &&
    (!q || `${t.title} ${t.subtitle}`.toLowerCase().includes(q)));

  let content = "";
  if (!tools.length) {
    content = `<div class="empty"><div class="tile-ic lg">${icon("search")}</div>Ничего не найдено</div>`;
  } else if (S.cat === "all" && !q) {
    const recent = load("history", []).slice(0, 6);
    if (recent.length) {
      content += `<div class="sec"><div class="sec-head"><h3>Недавние</h3><span data-goto="history">Все</span></div>
        <div class="recent">${recent.map((it) => {
          const t = toolById(it.tool);
          return `<button class="recent-card" data-h="${it.id}"><div class="row">${tileIcon(t, "sm")}<b>${esc(it.title)}</b></div>
            <p>${esc(preview(it))}</p></button>`;
        }).join("")}</div></div>`;
    }
    for (const [cat, info] of Object.entries(CATS)) {
      const list = tools.filter((t) => t.category === cat);
      if (!list.length) continue;
      content += `<div class="sec"><div class="sec-head"><h3>${info.name}</h3><span>${list.length}</span></div>
        <div class="grid">${list.map(toolCard).join("")}</div></div>`;
    }
  } else {
    content = `<div class="grid">${tools.map(toolCard).join("")}</div>`;
  }

  $view.innerHTML = `
    <div class="home-head">
      <div class="avatar">${user.photo_url ? `<img src="${esc(user.photo_url)}" alt="">` : initials}</div>
      <div class="who"><small>${greeting()}</small><b>${esc(name || "Создатель")}</b></div>
      <button class="model-pill" id="modelPill"><span class="dot"></span>${providerName(defaultProvider())}${icon("down", "sm")}</button>
    </div>
    <div class="search">${icon("search")}<input id="search" type="search" placeholder="Найти инструмент" value="${esc(S.query)}" autocomplete="off"></div>
    <div class="chips">${[["all", "Все"], ...Object.entries(CATS).map(([k, v]) => [k, v.name])].map(([k, l]) =>
      `<button class="chip ${S.cat === k ? "on" : ""}" data-cat="${k}">${l}</button>`).join("")}</div>
    <div id="homeContent">${content}</div>`;

  $view.querySelector("#modelPill").onclick = () => chooseDefaultModel(render);
  const search = $view.querySelector("#search");
  search.oninput = () => {
    S.query = search.value;
    const pos = search.selectionStart;
    renderHome();
    const s2 = $view.querySelector("#search");
    s2.focus();
    s2.setSelectionRange(pos, pos);
  };
  $view.querySelectorAll("[data-cat]").forEach((b) => { b.onclick = () => { S.cat = b.dataset.cat; haptic("select"); renderHome(); }; });
  $view.querySelectorAll("[data-tool]").forEach((el) => { el.onclick = () => { haptic(); openTool(toolById(el.dataset.tool)); }; });
  $view.querySelectorAll("[data-h]").forEach((el) => {
    el.onclick = () => { S.historyItem = load("history", []).find((i) => String(i.id) === el.dataset.h); render(); };
  });
  const all = $view.querySelector("[data-goto]");
  if (all) all.onclick = () => setTab("history");
}

// ================= Экран инструмента =================

function openTool(tool) {
  S.tool = tool;
  S.values = {};
  S.files = {};
  S.provider = defaultProvider();
  for (const f of tool.fields) {
    if (f.type === "checkbox") S.values[f.name] = f.default ? "1" : "0";
    else if (f.default !== undefined && f.default !== null) S.values[f.name] = String(f.default);
    else S.values[f.name] = "";
  }
  render();
}

function isSegmented(f) {
  return f.options.length <= 4 && f.options.every(([, label]) => label.length <= 12);
}

function optionLabel(f, v) {
  const o = f.options.find(([val]) => val === v);
  return o ? o[1] : "Выбрать";
}

function fieldHTML(f) {
  const label = `<div class="lbl"><span>${esc(f.label)}${f.required ? '<span class="req">*</span>' : ""}</span>${
    f.type === "file" && f.multiple ? `<small>до ${f.max}</small>` : ""}</div>`;
  const v = S.values[f.name];
  let inner = "";
  switch (f.type) {
    case "text":
      inner = `<input class="input" type="text" data-f="${f.name}" value="${esc(v)}" placeholder="${esc(f.placeholder || "")}">`;
      break;
    case "textarea":
      inner = `<textarea class="textarea" data-f="${f.name}" placeholder="${esc(f.placeholder || "")}">${esc(v)}</textarea>`;
      break;
    case "number":
      inner = `<div class="stepper" data-step="${f.name}">
        <button type="button" data-d="-1" aria-label="Меньше">${icon("minus")}</button>
        <output>${esc(v)}</output>
        <button type="button" data-d="1" aria-label="Больше">${icon("plus")}</button></div>`;
      break;
    case "select":
      inner = isSegmented(f)
        ? `<div class="segmented" data-seg="${f.name}">${f.options.map(([val, l]) =>
            `<button type="button" data-v="${esc(val)}" class="${val === v ? "on" : ""}">${esc(l)}</button>`).join("")}</div>`
        : `<button type="button" class="picker" data-pick="${f.name}"><span>${esc(optionLabel(f, v))}</span>${icon("down", "sm")}</button>`;
      break;
    case "voice":
      inner = `<button type="button" class="picker" data-voice="${f.name}"><span>Загрузка голосов…</span>${icon("down", "sm")}</button>`;
      break;
    case "checkbox":
      return `<div class="field" data-field="${f.name}"><label class="switch-row"><span>${esc(f.label)}</span>
        <input type="checkbox" data-f="${f.name}" ${v === "1" ? "checked" : ""}><i class="switch"></i></label></div>`;
    case "file": {
      const kinds = [];
      if (f.accept.includes("video")) kinds.push("видео");
      if (f.accept.includes("audio")) kinds.push("аудио");
      if (f.accept.includes("image")) kinds.push("изображение");
      inner = `<label class="dropzone"><input type="file" data-file="${f.name}" accept="${esc(f.accept)}" ${f.multiple ? "multiple" : ""}>
        <div class="tile-ic">${icon("upload")}</div>
        <div><b>${f.multiple ? "Добавить файлы" : "Загрузить файл"}</b><small>${kinds.join(", ")}${f.multiple ? ` · до ${f.max} шт.` : ""}</small></div>
      </label><div class="files" data-files="${f.name}"></div>`;
      break;
    }
  }
  return `<div class="field" data-field="${f.name}">${label}${inner}</div>`;
}

function visible(f) {
  if (!f.show_if) return true;
  return Object.entries(f.show_if).every(([k, allowed]) => allowed.includes(S.values[k]));
}

function refreshVisibility() {
  for (const f of S.tool.fields) {
    const el = $view.querySelector(`[data-field="${f.name}"]`);
    if (el) el.classList.toggle("hidden", !visible(f));
  }
}

function renderFiles(name) {
  const box = $view.querySelector(`[data-files="${name}"]`);
  if (!box) return;
  box.innerHTML = "";
  (S.files[name] || []).forEach((file, i) => {
    const row = document.createElement("div");
    row.className = "file-row";
    const kind = file.type.startsWith("image/") ? "image" : file.type.startsWith("video/") ? "film" : "music";
    row.innerHTML = `<div class="thumb">${kind === "image" ? `<img src="${URL.createObjectURL(file)}" alt="">` : icon(kind)}</div>
      <div class="meta"><b>${esc(file.name)}</b><small>${fileSize(file.size)}</small></div>
      <button type="button" aria-label="Удалить">${icon("x")}</button>`;
    row.querySelector("button").onclick = () => { S.files[name].splice(i, 1); renderFiles(name); haptic(); };
    box.append(row);
  });
}

function renderTool(tool) {
  const p = providers();
  const missing = tool.needs.filter((n) => !p[n]);
  const cat = CATS[tool.category] || CATS.scripts;
  const providerField = tool.uses_llm ? `<div class="field"><div class="lbl"><span>Модель</span></div>
    <div class="segmented" id="providerSeg">${PROVIDERS.map(([id, label]) =>
      `<button type="button" data-p="${id}" class="${id === S.provider ? "on" : ""}" ${p[id] ? "" : "disabled"}>${label}</button>`).join("")}</div></div>` : "";

  $view.innerHTML = `
    <div class="topbar"><button class="icon-btn" id="back" aria-label="Назад">${icon("back")}</button>
      <div class="title muted">${esc(cat.name)}</div></div>
    <div class="hero">${tileIcon(tool, "lg")}<div><h1>${esc(tool.title)}</h1><p>${esc(tool.subtitle)}</p></div></div>
    ${missing.length ? `<div class="notice danger">${icon("alert")}<div>Нужен ключ ${missing.map((n) => SERVICE_NAMES[n]).join(", ")}. Добавьте его в переменные сервера.</div></div>` : ""}
    ${tool.hint ? `<div class="notice">${icon("info")}<div>${esc(tool.hint)}</div></div>` : ""}
    <form class="form" id="form" novalidate>${providerField}${tool.fields.map(fieldHTML).join("")}</form>
    <div class="result" id="result"></div>`;

  $cta.innerHTML = `<div class="cta-bar"><div class="inner">
    <button class="btn-primary" id="run" type="button">${icon("sparkles")}<span>Сгенерировать</span></button></div></div>`;

  $view.querySelector("#back").onclick = goBack;
  $cta.querySelector("#run").onclick = submit;
  $view.querySelector("#form").onsubmit = (e) => { e.preventDefault(); submit(); };

  const seg = $view.querySelector("#providerSeg");
  if (seg) seg.querySelectorAll("button").forEach((b) => {
    b.onclick = () => { S.provider = b.dataset.p; seg.querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b)); haptic("select"); };
  });

  $view.querySelectorAll("[data-f]").forEach((el) => {
    const update = () => { S.values[el.dataset.f] = el.type === "checkbox" ? (el.checked ? "1" : "0") : el.value; refreshVisibility(); };
    el.addEventListener("input", update);
    el.addEventListener("change", update);
  });

  $view.querySelectorAll("[data-seg]").forEach((box) => {
    box.querySelectorAll("button").forEach((b) => {
      b.onclick = () => {
        S.values[box.dataset.seg] = b.dataset.v;
        box.querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b));
        refreshVisibility();
        haptic("select");
      };
    });
  });

  $view.querySelectorAll("[data-pick]").forEach((btn) => {
    const f = tool.fields.find((x) => x.name === btn.dataset.pick);
    btn.onclick = () => openSheet({
      title: f.label,
      value: S.values[f.name],
      options: f.options.map(([value, label]) => ({ value, label })),
      onPick: (v) => { S.values[f.name] = v; btn.querySelector("span").textContent = optionLabel(f, v); refreshVisibility(); },
    });
  });

  $view.querySelectorAll("[data-step]").forEach((box) => {
    const f = tool.fields.find((x) => x.name === box.dataset.step);
    const out = box.querySelector("output");
    const [dec, inc] = box.querySelectorAll("button");
    const sync = () => { const n = +S.values[f.name]; out.textContent = n; dec.disabled = n <= f.min; inc.disabled = n >= f.max; };
    box.querySelectorAll("button").forEach((b) => {
      b.onclick = () => { S.values[f.name] = String(Math.min(f.max, Math.max(f.min, +S.values[f.name] + +b.dataset.d))); sync(); haptic("select"); };
    });
    sync();
  });

  $view.querySelectorAll("[data-file]").forEach((input) => {
    const f = tool.fields.find((x) => x.name === input.dataset.file);
    input.onchange = () => {
      const picked = Array.from(input.files || []);
      const combined = f.multiple ? (S.files[f.name] || []).concat(picked) : picked;
      if (combined.length > f.max) toast(`Максимум файлов: ${f.max}`, "info");
      S.files[f.name] = combined.slice(0, f.max);
      input.value = "";
      renderFiles(f.name);
    };
  });

  const voiceBtn = $view.querySelector("[data-voice]");
  if (voiceBtn) setupVoicePicker(voiceBtn);
  refreshVisibility();
}

async function setupVoicePicker(btn) {
  const name = btn.dataset.voice;
  const label = btn.querySelector("span");
  try {
    if (!S.voices) S.voices = (await api("/api/voices")).voices;
  } catch (e) {
    label.textContent = e.message;
    return;
  }
  const mine = (v) => ["cloned", "generated", "professional"].includes(v.category);
  const voices = S.voices;
  if (!voices.length) { label.textContent = "Голосов нет"; return; }
  if (!voices.some((v) => v.id === S.values[name])) S.values[name] = voices[0].id;
  const show = () => { label.textContent = (voices.find((v) => v.id === S.values[name]) || {}).name || "Выбрать"; };
  show();
  btn.onclick = () => openSheet({
    title: "Голос",
    value: S.values[name],
    options: voices.map((v) => ({ value: v.id, label: v.name, group: mine(v) ? "Мои голоса" : "Библиотека ElevenLabs" })),
    onPick: (v) => { S.values[name] = v; show(); },
  });
}

function setRunning(running, started) {
  const btn = $cta.querySelector("#run");
  if (!btn) return;
  clearInterval(setRunning.timer);
  btn.disabled = running;
  if (!running) {
    btn.innerHTML = `${icon("refresh")}<span>Сгенерировать ещё раз</span>`;
    return;
  }
  const tick = () => {
    const sec = Math.round((Date.now() - started) / 1000);
    btn.innerHTML = `<span class="spinner"></span><span>Генерация · ${sec} с</span><i class="progress"></i>`;
    const line = $view.querySelector("#statusText");
    if (line) line.textContent = STATUS_TEXT[Math.min(STATUS_TEXT.length - 1, Math.floor(sec / 6))];
  };
  tick();
  setRunning.timer = setInterval(tick, 1000);
}

function skeletonHTML() {
  const widths = [92, 78, 85, 60, 88, 70, 45];
  return `<div class="result-body"><div class="status-line"><span class="spinner"></span><span id="statusText">${STATUS_TEXT[0]}</span></div>
    <div class="skeleton">${widths.map((w) => `<i style="width:${w}%"></i>`).join("")}</div></div>
    <div class="foot-note">${icon("info", "sm")}Можно свернуть приложение — результат придёт в чат.</div>`;
}

async function submit() {
  if (S.busy) return;
  const tool = S.tool;
  const box = $view.querySelector("#result");

  for (const f of tool.fields) {
    if (!f.required || !visible(f)) continue;
    const empty = f.type === "file" ? !(S.files[f.name] || []).length : !String(S.values[f.name] || "").trim();
    if (empty) {
      box.innerHTML = `<div class="error-box">${icon("alert")}<div>Заполните поле «${esc(f.label)}»</div></div>`;
      const el = $view.querySelector(`[data-field="${f.name}"]`);
      if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
      haptic("error");
      return;
    }
  }

  const fd = new FormData();
  for (const f of tool.fields) {
    if (!visible(f)) continue;
    if (f.type === "file") (S.files[f.name] || []).forEach((file) => fd.append(f.name, file, file.name));
    else fd.append(f.name, S.values[f.name] ?? "");
  }
  fd.append("_provider", S.provider);
  fd.append("_lang", S.settings.lang);
  fd.append("_to_chat", S.settings.toChat ? "1" : "0");

  const started = Date.now();
  S.busy = true;
  box.innerHTML = skeletonHTML();
  box.scrollIntoView({ behavior: "smooth", block: "start" });
  setRunning(true, started);
  haptic("medium");

  try {
    const res = await api(`/api/run/${tool.id}`, { method: "POST", body: fd });
    if (tool.id === "voices" && S.values.mode === "clone") S.voices = null;
    const item = addHistory(tool, res, tool.uses_llm ? providerName(S.provider) : "");
    if (S.tool !== tool) return;
    const secs = Math.round((Date.now() - started) / 1000);
    box.innerHTML = resultHTML(res, { meta: `за ${secs} с${item.model ? " · " + item.model : ""}`, rerun: true });
    bindResult(box, res.text, tool.title);
    haptic("success");
  } catch (e) {
    if (S.tool === tool) box.innerHTML = `<div class="error-box">${icon("alert")}<div>${esc(e.message)}</div></div>`;
    haptic("error");
  } finally {
    S.busy = false;
    if (S.tool === tool) setRunning(false);
  }
}

function resultHTML(res, { meta = "", rerun = false } = {}) {
  const imgs = res.images || [];
  const hasMedia = imgs.length || res.audio || res.video;
  let body = "";
  if (res.chat_note) body += `<div class="notice">${icon("info")}<div>${esc(res.chat_note)}</div></div>`;
  if (imgs.length) {
    body += `<div class="media-grid ${imgs.length === 1 ? "one" : ""}">${imgs.map((u) =>
      `<a href="${u}" data-open><img src="${u}" alt="" loading="lazy"></a>`).join("")}</div>`;
  }
  if (res.video) body += `<video class="player" src="${res.video}" controls playsinline></video>`;
  if (res.audio) body += `<audio class="player" src="${res.audio}" controls></audio>`;
  if (res.text) body += `<div class="md">${markdown(res.text)}</div>`;

  const actions = [];
  if (res.text) actions.push(`<button class="tool-btn" data-act="copy">${icon("copy", "sm")}Копировать</button>`);
  if (res.text) actions.push(`<button class="tool-btn" data-act="send">${icon("send", "sm")}В чат</button>`);
  if (rerun) actions.push(`<button class="tool-btn" data-act="rerun">${icon("refresh", "sm")}Ещё раз</button>`);

  return `<div class="result-head"><h3>${icon("checkCircle")}Готово</h3><small>${esc(meta)}</small></div>
    <div class="result-body">${body}</div>
    ${actions.length ? `<div class="toolbar" style="grid-template-columns:repeat(${actions.length},1fr)">${actions.join("")}</div>` : ""}
    ${hasMedia ? `<div class="foot-note">${icon("chat", "sm")}Файлы также отправлены в чат с ботом.</div>` : ""}`;
}

function bindResult(box, text, title) {
  box.querySelectorAll("[data-copy-code]").forEach((b) => {
    b.onclick = () => copy(b.closest(".code").querySelector("pre").textContent);
  });
  box.querySelectorAll("[data-open]").forEach((a) => {
    a.onclick = (e) => {
      e.preventDefault();
      const url = new URL(a.getAttribute("href"), location.href).href;
      if (tg && tg.openLink) tg.openLink(url); else window.open(url, "_blank");
    };
  });
  const act = (name, fn) => { const b = box.querySelector(`[data-act="${name}"]`); if (b) b.onclick = fn; };
  act("copy", () => copy(text));
  act("rerun", submit);
  act("send", async () => {
    try {
      await api("/api/send", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ title, text }) });
      haptic("success");
      toast("Отправлено в чат", "send");
    } catch (e) { toast(e.message, "alert"); }
  });
}

// ================= История =================

function addHistory(tool, res, model) {
  const items = load("history", []);
  const item = {
    id: Date.now(),
    tool: tool.id,
    title: tool.title,
    ts: Date.now(),
    model,
    text: (res.text || "").slice(0, 40000),
    media: (res.images || []).length + (res.audio ? 1 : 0) + (res.video ? 1 : 0),
  };
  items.unshift(item);
  save("history", items.slice(0, 60));
  return item;
}

function preview(it) {
  if (!it.text) return `Медиафайлов: ${it.media} — отправлены в чат`;
  return it.text.replace(/```[\s\S]*?```/g, " ").replace(/[#*`|>_-]/g, " ").replace(/\s+/g, " ").trim().slice(0, 140);
}

function renderHistory() {
  const items = load("history", []);
  if (!items.length) {
    $view.innerHTML = `<div class="page-title">История</div>
      <div class="empty"><div class="tile-ic lg">${icon("clock")}</div>Здесь появятся ваши результаты.<br>История хранится только на этом устройстве.</div>`;
    return;
  }
  let html = `<div class="page-title">История</div>`;
  let day = null;
  let open = false;
  for (const it of items) {
    const d = dayLabel(it.ts);
    if (d !== day) {
      if (open) html += `</div>`;
      html += `<div class="history-day">${d}</div><div class="list">`;
      day = d;
      open = true;
    }
    const t = toolById(it.tool);
    html += `<button class="list-row" data-h="${it.id}">${tileIcon(t, "sm")}
      <div class="body"><b>${esc(it.title)}</b><small>${esc(preview(it))}</small></div>
      <div class="end">${fmtTime(it.ts)}</div></button>`;
  }
  if (open) html += `</div>`;
  $view.innerHTML = html;
  $view.querySelectorAll("[data-h]").forEach((el) => {
    el.onclick = () => { S.historyItem = items.find((i) => String(i.id) === el.dataset.h); render(); };
  });
}

function renderHistoryItem(it) {
  const t = toolById(it.tool);
  const meta = `${dayLabel(it.ts)}, ${fmtTime(it.ts)}${it.model ? " · " + it.model : ""}`;
  $view.innerHTML = `
    <div class="topbar"><button class="icon-btn" id="back" aria-label="Назад">${icon("back")}</button><div class="title muted">История</div></div>
    <div class="hero">${tileIcon(t, "lg")}<div><h1>${esc(it.title)}</h1><p>${esc(meta)}</p></div></div>
    <div id="result">${resultHTML({ text: it.text || "Медиафайлы были отправлены в чат с ботом." })}</div>`;
  $view.querySelector("#back").onclick = goBack;
  bindResult($view.querySelector("#result"), it.text, it.title);
}

// ================= Настройки =================

function renderSettings() {
  const p = providers();
  const st = S.settings;
  const models = S.cfg.models || {};
  const current = defaultProvider();

  $view.innerHTML = `
    <div class="page-title">Настройки</div>

    <div class="group-label">Оформление</div>
    <div class="themes">${THEMES.map(([id, name, bg, accent]) => `
      <button class="theme-opt ${st.theme === id ? "on" : ""}" data-theme-id="${id}">
        <span class="swatch" style="background:${bg};--sw:${accent}"></span>${name}</button>`).join("")}</div>

    <div class="group-label">Модель по умолчанию</div>
    <div class="list">${PROVIDERS.map(([id, label]) => `
      <button class="list-row" data-provider="${id}" ${p[id] ? "" : "disabled"}>
        <div class="tile-ic sm" style="background:var(--accent-soft);color:var(--accent)">${icon("cpu")}</div>
        <div class="body"><b>${label}</b><small>${p[id] ? esc(models[id] || "") : "Нет ключа API"}</small></div>
        <div class="end">${id === current ? `<span class="check">${icon("check")}</span>` : ""}</div></button>`).join("")}
    </div>

    <div class="group-label">Язык ответов</div>
    <div class="segmented" id="langSeg">${LANGS.map(([id, l]) => `<button data-v="${id}" class="${id === st.lang ? "on" : ""}">${l}</button>`).join("")}</div>
    <p class="muted" style="font-size:12.5px;margin:8px 4px 0">Промпты для генераторов всегда на английском — так они работают точнее.</p>

    <div class="group-label">Чат</div>
    <label class="switch-row"><span>Дублировать текст в чат с ботом</span>
      <input type="checkbox" id="toChat" ${st.toChat ? "checked" : ""}><i class="switch"></i></label>
    <p class="muted" style="font-size:12.5px;margin:8px 4px 0">Изображения, аудио и видео отправляются в чат всегда.</p>

    <div class="group-label">Сервисы</div>
    <div class="list">${Object.keys(SERVICE_NAMES).map((k) => `
      <div class="list-row"><span class="dot ${p[k] ? "" : "off"}"></span>
        <div class="body"><b>${SERVICE_NAMES[k]}</b><small>${p[k] ? esc(models[k] || "Подключено") : "Ключ не задан"}</small></div></div>`).join("")}
    </div>

    <div class="group-label">Данные</div>
    <div class="list"><button class="list-row danger" id="clear">${icon("trash", "sm")}Очистить историю</button></div>
    <div class="about">AI Studio · личная версия</div>`;

  $view.querySelectorAll("[data-theme-id]").forEach((b) => {
    b.onclick = () => { st.theme = b.dataset.themeId; saveSettings(); applyTheme(); haptic("select"); renderSettings(); };
  });
  $view.querySelectorAll("[data-provider]").forEach((b) => {
    b.onclick = () => { st.provider = b.dataset.provider; saveSettings(); haptic("select"); renderSettings(); };
  });
  $view.querySelectorAll("#langSeg button").forEach((b) => {
    b.onclick = () => {
      st.lang = b.dataset.v;
      saveSettings();
      $view.querySelectorAll("#langSeg button").forEach((x) => x.classList.toggle("on", x === b));
      haptic("select");
    };
  });
  $view.querySelector("#toChat").onchange = (e) => { st.toChat = e.target.checked; saveSettings(); };
  $view.querySelector("#clear").onclick = () => {
    const doClear = () => { save("history", []); toast("История очищена", "trash"); };
    if (tg && tg.showConfirm && tg.initData) tg.showConfirm("Удалить всю историю?", (ok) => ok && doClear());
    else if (confirm("Удалить всю историю?")) doClear();
  };
}

// ================= Старт =================

async function init() {
  applyTheme();
  $tabbar.querySelectorAll("[data-icon]").forEach((el) => { el.innerHTML = icon(el.dataset.icon); });
  $tabbar.querySelectorAll("button").forEach((b) => { b.onclick = () => { haptic("select"); setTab(b.dataset.tab); }; });

  if (tg) {
    tg.ready();
    tg.expand();
    try { tg.disableVerticalSwipes(); } catch { /* старый клиент */ }
    if (tg.BackButton) tg.BackButton.onClick(goBack);
  }

  $view.innerHTML = `<div class="boot"><span class="spinner"></span></div>`;
  try {
    S.cfg = await api("/api/config");
    render();
  } catch (e) {
    $tabbar.classList.add("hidden");
    $view.innerHTML = `<div class="empty"><div class="tile-ic lg">${icon("alert")}</div>${esc(e.message)}</div>`;
  }
}

init();
