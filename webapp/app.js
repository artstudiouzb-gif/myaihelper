"use strict";

const tg = window.Telegram && window.Telegram.WebApp;
const $view = document.getElementById("view");

const PROVIDERS = [
  ["claude", "Claude"],
  ["openai", "ChatGPT"],
  ["gemini", "Gemini"],
];
const SERVICE_NAMES = { claude: "Claude", openai: "ChatGPT", gemini: "Gemini", elevenlabs: "ElevenLabs" };
const LANGS = [["ru", "Русский"], ["uz", "O'zbek"], ["en", "English"]];

const S = {
  cfg: null,
  tab: "home",
  tool: null,         // открытый раздел
  historyItem: null,  // открытая запись истории
  values: {},
  files: {},
  provider: "",
  busy: false,
  voices: null,
  settings: Object.assign({ provider: "", lang: "ru", toChat: true }, load("settings", {})),
};

// ---------- утилиты ----------

function load(key, fallback) {
  try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; }
}
function save(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* хранилище недоступно */ }
}
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function haptic(type = "light") {
  try { tg.HapticFeedback.impactOccurred(type); } catch { /* вне Telegram */ }
}
function toast(text) {
  const el = document.getElementById("toast");
  el.textContent = text;
  el.classList.add("show");
  clearTimeout(toast.t);
  toast.t = setTimeout(() => el.classList.remove("show"), 1800);
}
async function copy(text) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.append(ta);
    ta.select();
    document.execCommand("copy");
    ta.remove();
  }
  haptic();
  toast("Скопировано");
}
function grad(colors) {
  return `background: linear-gradient(135deg, ${colors[0]}, ${colors[1]})`;
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
function defaultProvider() {
  const p = providers();
  if (S.settings.provider && p[S.settings.provider]) return S.settings.provider;
  return (PROVIDERS.find(([id]) => p[id]) || ["claude"])[0];
}

// ---------- Markdown ----------

function inline(s) {
  return esc(s)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[\s(])\*([^*\s][^*]*)\*(?=[\s).,!?:;]|$)/g, "$1<em>$2</em>");
}

function codebox(code) {
  return `<div class="codebox"><pre>${esc(code)}</pre><button class="copy" type="button">Копировать</button></div>`;
}

function markdown(src) {
  const codes = [];
  src = String(src || "").replace(/```[^\n]*\n([\s\S]*?)```/g, (_, code) => {
    codes.push(code.replace(/\n+$/, ""));
    return `\n\u0000${codes.length - 1}\u0000\n`;
  });

  let html = "";
  let para = [], list = null, table = [];
  const flushPara = () => { if (para.length) html += `<p>${para.map(inline).join("<br>")}</p>`; para = []; };
  const flushList = () => { if (list) html += `<${list.tag}>${list.items.map((i) => `<li>${inline(i)}</li>`).join("")}</${list.tag}>`; list = null; };
  const flushTable = () => {
    if (!table.length) return;
    const rows = table
      .filter((r) => !/^\|?\s*:?-{2,}/.test(r))
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
    if ((m = t.match(/^\u0000(\d+)\u0000$/))) { flushAll(); html += codebox(codes[+m[1]]); continue; }
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

// ---------- навигация ----------

function setTab(tab) {
  S.tab = tab;
  S.tool = null;
  S.historyItem = null;
  document.querySelectorAll("#tabbar button").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  render();
}

function goBack() {
  if (S.busy) return;
  S.tool = null;
  S.historyItem = null;
  render();
}

function render() {
  window.scrollTo(0, 0);
  const inner = S.tool || S.historyItem;
  if (tg && tg.BackButton) inner ? tg.BackButton.show() : tg.BackButton.hide();
  if (S.tool) return renderTool(S.tool);
  if (S.historyItem) return renderHistoryItem(S.historyItem);
  if (S.tab === "history") return renderHistory();
  if (S.tab === "settings") return renderSettings();
  return renderHome();
}

// ---------- главная ----------

function renderHome() {
  const p = providers();
  const name = (S.cfg.user && S.cfg.user.first_name) || "";
  const current = PROVIDERS.find(([id]) => id === defaultProvider());
  const services = Object.keys(SERVICE_NAMES)
    .map((k) => `<span class="svc ${p[k] ? "on" : ""}"><i></i>${SERVICE_NAMES[k]}</span>`).join("");

  const tiles = S.cfg.tools.map((t) => {
    const missing = t.needs.filter((n) => !p[n]);
    return `<button class="tile ${missing.length ? "off" : ""}" data-tool="${t.id}">
      ${missing.length ? `<span class="badge">НЕТ КЛЮЧА</span>` : ""}
      <div class="ico" style="${grad(t.colors)}">${t.icon}</div>
      <h3>${esc(t.title)}</h3><p>${esc(t.subtitle)}</p>
    </button>`;
  }).join("");

  $view.innerHTML = `
    <div class="top">
      <div><div class="logo">my<b>ai</b>helper</div><div class="hello">Привет${name ? ", " + esc(name) : ""} 👋</div></div>
      <span class="chip">Личный</span>
    </div>
    <div class="status">
      <div class="status-row">
        <div><div class="status-title">Модель по умолчанию</div>
          <div class="status-sub">Текстовые разделы работают через <b>${current ? current[1] : "—"}</b></div></div>
        <button class="btn-accent" id="chooseModel">Сменить</button>
      </div>
      <hr>
      <div class="services">${services}</div>
      <div class="bar"></div>
    </div>
    <div class="section-label">Разделы</div>
    <div class="grid">${tiles}</div>`;

  $view.querySelector("#chooseModel").onclick = () => setTab("settings");
  $view.querySelectorAll("[data-tool]").forEach((el) => {
    el.onclick = () => { haptic(); openTool(S.cfg.tools.find((t) => t.id === el.dataset.tool)); };
  });
}

// ---------- раздел ----------

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

function useSegments(f) {
  return f.options.length <= 4 && f.options.every(([, label]) => label.length <= 24);
}

function fieldHTML(f) {
  const req = f.required ? " <em>*</em>" : "";
  const label = `<label class="lbl">${esc(f.label)}${req}</label>`;
  const val = esc(S.values[f.name]);
  const ph = esc(f.placeholder || "");
  let inner = "";
  switch (f.type) {
    case "text":
      inner = `<input type="text" data-f="${f.name}" value="${val}" placeholder="${ph}">`;
      break;
    case "textarea":
      inner = `<textarea data-f="${f.name}" placeholder="${ph}">${val}</textarea>`;
      break;
    case "number":
      inner = `<input type="number" inputmode="numeric" data-f="${f.name}" value="${val}" min="${f.min}" max="${f.max}">`;
      break;
    case "select":
      inner = useSegments(f)
        ? `<div class="seg" data-seg="${f.name}">${f.options.map(([v, l]) =>
            `<button type="button" data-v="${esc(v)}" class="${v === S.values[f.name] ? "on" : ""}">${esc(l)}</button>`).join("")}</div>`
        : `<select data-f="${f.name}">${f.options.map(([v, l]) =>
            `<option value="${esc(v)}" ${v === S.values[f.name] ? "selected" : ""}>${esc(l)}</option>`).join("")}</select>`;
      break;
    case "voice":
      inner = `<select data-f="${f.name}" data-voice><option value="">Загрузка голосов…</option></select>`;
      break;
    case "checkbox":
      return `<div class="field" data-field="${f.name}"><label class="toggle"><span>${esc(f.label)}</span>
        <input type="checkbox" data-f="${f.name}" ${S.values[f.name] === "1" ? "checked" : ""}><i></i></label></div>`;
    case "file": {
      const many = f.multiple ? `до ${f.max} файлов` : "1 файл";
      inner = `<label class="drop"><input type="file" data-file="${f.name}" accept="${esc(f.accept)}" ${f.multiple ? "multiple" : ""}>
        <b>Выбрать файл</b> · ${many}</label><div class="thumbs" data-thumbs="${f.name}"></div>`;
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

function renderThumbs(name) {
  const box = $view.querySelector(`[data-thumbs="${name}"]`);
  if (!box) return;
  box.innerHTML = "";
  (S.files[name] || []).forEach((file, i) => {
    const el = document.createElement("div");
    el.className = "thumb";
    if (file.type.startsWith("image/")) {
      el.innerHTML = `<img src="${URL.createObjectURL(file)}">`;
    } else {
      el.textContent = (file.type.startsWith("video/") ? "🎬 " : "🎵 ") + file.name.slice(0, 24);
    }
    const x = document.createElement("button");
    x.className = "x";
    x.type = "button";
    x.textContent = "✕";
    x.onclick = (e) => { e.preventDefault(); S.files[name].splice(i, 1); renderThumbs(name); };
    el.append(x);
    box.append(el);
  });
}

function renderTool(tool) {
  const p = providers();
  const missing = tool.needs.filter((n) => !p[n]);
  const providerSeg = tool.uses_llm ? `
    <div class="field"><label class="lbl">Модель</label><div class="seg" id="providerSeg">
      ${PROVIDERS.map(([id, label]) => `<button type="button" data-p="${id}" class="${id === S.provider ? "on" : ""}" ${p[id] ? "" : "disabled"}>${label}</button>`).join("")}
    </div></div>` : "";

  $view.innerHTML = `
    <button class="back" id="back">‹ Назад</button>
    <div class="tool-head">
      <div class="ico" style="${grad(tool.colors)}">${tool.icon}</div>
      <div><h2>${esc(tool.title)}</h2><p>${esc(tool.subtitle)}</p></div>
    </div>
    ${missing.length ? `<div class="error">Для этого раздела нужен ключ: ${missing.map((n) => SERVICE_NAMES[n]).join(", ")}. Добавьте его на сервере.</div><br>` : ""}
    ${tool.hint ? `<div class="hint">💡 ${esc(tool.hint)}</div>` : ""}
    <form class="form" id="form" novalidate>
      ${providerSeg}
      ${tool.fields.map(fieldHTML).join("")}
      <div>
        <button class="submit" id="submit" type="submit">Создать</button>
        <div class="wait-note" id="waitNote" hidden>Можно свернуть приложение — результат придёт в чат.</div>
      </div>
    </form>
    <div class="result" id="result"></div>`;

  $view.querySelector("#back").onclick = goBack;

  const seg = $view.querySelector("#providerSeg");
  if (seg) seg.querySelectorAll("button").forEach((b) => {
    b.onclick = () => { S.provider = b.dataset.p; seg.querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b)); haptic(); };
  });

  $view.querySelectorAll("[data-f]").forEach((el) => {
    const update = () => {
      S.values[el.dataset.f] = el.type === "checkbox" ? (el.checked ? "1" : "0") : el.value;
      refreshVisibility();
    };
    el.addEventListener("input", update);
    el.addEventListener("change", update);
  });

  $view.querySelectorAll("[data-seg]").forEach((box) => {
    box.querySelectorAll("button").forEach((b) => {
      b.onclick = () => {
        S.values[box.dataset.seg] = b.dataset.v;
        box.querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b));
        refreshVisibility();
        haptic();
      };
    });
  });

  $view.querySelectorAll("[data-file]").forEach((input) => {
    const f = tool.fields.find((x) => x.name === input.dataset.file);
    input.onchange = () => {
      const picked = Array.from(input.files || []);
      const combined = f.multiple ? (S.files[f.name] || []).concat(picked) : picked;
      if (combined.length > f.max) toast(`Максимум файлов: ${f.max}`);
      S.files[f.name] = combined.slice(0, f.max);
      input.value = "";
      renderThumbs(f.name);
    };
  });

  const voiceSelect = $view.querySelector("[data-voice]");
  if (voiceSelect) fillVoices(voiceSelect);

  $view.querySelector("#form").onsubmit = (e) => { e.preventDefault(); submit(); };
  refreshVisibility();
}

async function fillVoices(select) {
  try {
    if (!S.voices) S.voices = (await api("/api/voices")).voices;
    const mine = S.voices.filter((v) => ["cloned", "generated", "professional"].includes(v.category));
    const other = S.voices.filter((v) => !mine.includes(v));
    const opt = (v) => `<option value="${esc(v.id)}">${esc(v.name)}</option>`;
    select.innerHTML = (mine.length ? `<optgroup label="Мои голоса">${mine.map(opt).join("")}</optgroup>` : "")
      + `<optgroup label="Библиотека">${other.map(opt).join("")}</optgroup>`;
    if (!S.voices.length) select.innerHTML = `<option value="">Голосов нет</option>`;
    S.values[select.dataset.f] = select.value;
  } catch (e) {
    select.innerHTML = `<option value="">${esc(e.message)}</option>`;
  }
}

async function submit() {
  if (S.busy) return;
  const tool = S.tool;
  const resultBox = $view.querySelector("#result");

  for (const f of tool.fields) {
    if (!f.required || !visible(f)) continue;
    const empty = f.type === "file" ? !(S.files[f.name] || []).length : !String(S.values[f.name] || "").trim();
    if (empty) {
      resultBox.innerHTML = `<div class="error">Заполните поле «${esc(f.label)}»</div>`;
      haptic("medium");
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

  const btn = $view.querySelector("#submit");
  const started = Date.now();
  S.busy = true;
  btn.disabled = true;
  $view.querySelector("#waitNote").hidden = false;
  resultBox.innerHTML = "";
  const tick = () => { btn.innerHTML = `<span class="spinner"></span> Генерация… ${Math.round((Date.now() - started) / 1000)} с`; };
  tick();
  const timer = setInterval(tick, 1000);

  try {
    const res = await api(`/api/run/${tool.id}`, { method: "POST", body: fd });
    if (tool.id === "voices" && S.values.mode === "clone") S.voices = null;
    if (S.tool !== tool) return;  // пользователь ушёл с экрана
    resultBox.innerHTML = resultHTML(res, tool.title);
    bindResult(resultBox, res.text, tool.title);
    addHistory(tool, res);
    haptic("medium");
    try { tg.HapticFeedback.notificationOccurred("success"); } catch { /* вне Telegram */ }
    setTimeout(() => resultBox.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
  } catch (e) {
    if (S.tool === tool) resultBox.innerHTML = `<div class="error">${esc(e.message)}</div>`;
    try { tg.HapticFeedback.notificationOccurred("error"); } catch { /* вне Telegram */ }
  } finally {
    clearInterval(timer);
    S.busy = false;
    if (S.tool === tool) {
      btn.disabled = false;
      btn.textContent = "Создать ещё раз";
      $view.querySelector("#waitNote").hidden = true;
    }
  }
}

function resultHTML(res, title) {
  const imgs = res.images || [];
  let html = `<div class="result-card">`;
  if (res.chat_note) html += `<div class="note">⚠️ ${esc(res.chat_note)}</div>`;
  if (imgs.length) {
    html += `<div class="media-grid ${imgs.length === 1 ? "single" : ""}">${imgs.map((u) =>
      `<a href="${u}" data-open><img src="${u}" alt="${esc(title)}"></a>`).join("")}</div>`;
  }
  if (res.video) html += `<video class="out" src="${res.video}" controls playsinline></video>`;
  if (res.audio) html += `<audio src="${res.audio}" controls></audio>`;
  if (res.text) html += `<div class="md">${markdown(res.text)}</div>`;
  if (imgs.length || res.audio || res.video) {
    html += `<div class="muted" style="margin-top:8px">Файлы также отправлены в чат с ботом.</div>`;
  }
  html += `</div>`;
  if (res.text) {
    html += `<div class="result-actions">
      <button class="btn-ghost" data-act="copy">Копировать всё</button>
      <button class="btn-ghost" data-act="send">Отправить в чат</button></div>`;
  }
  return html;
}

function bindResult(box, text, title) {
  box.querySelectorAll(".codebox .copy").forEach((b) => { b.onclick = () => copy(b.previousElementSibling.textContent); });
  box.querySelectorAll("[data-open]").forEach((a) => {
    a.onclick = (e) => {
      e.preventDefault();
      const url = new URL(a.getAttribute("href"), location.href).href;
      if (tg && tg.openLink) tg.openLink(url); else window.open(url, "_blank");
    };
  });
  const c = box.querySelector('[data-act="copy"]');
  if (c) c.onclick = () => copy(text);
  const s = box.querySelector('[data-act="send"]');
  if (s) s.onclick = async () => {
    try {
      await api("/api/send", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ title, text }) });
      toast("Отправлено в чат");
    } catch (e) { toast(e.message); }
  };
}

// ---------- история ----------

function addHistory(tool, res) {
  const items = load("history", []);
  items.unshift({
    id: Date.now(),
    tool: tool.id,
    title: tool.title,
    ts: Date.now(),
    text: (res.text || "").slice(0, 40000),
    media: (res.images || []).length + (res.audio ? 1 : 0) + (res.video ? 1 : 0),
  });
  save("history", items.slice(0, 50));
}

function toolById(id) { return S.cfg.tools.find((t) => t.id === id) || { icon: "📄", colors: ["#444", "#222"], title: "" }; }

function renderHistory() {
  const items = load("history", []);
  $view.innerHTML = `<div class="page-title">История</div>` + (items.length
    ? `<div class="list">${items.map((it) => {
        const t = toolById(it.tool);
        const preview = it.text ? it.text.replace(/[#*`|>-]/g, "").slice(0, 160) : `📎 Медиафайлов: ${it.media} (отправлены в чат)`;
        return `<button class="item" data-h="${it.id}"><div class="ico" style="${grad(t.colors)}">${t.icon}</div>
          <div><b>${esc(it.title)}</b><small>${new Date(it.ts).toLocaleString("ru-RU", { dateStyle: "short", timeStyle: "short" })}</small>
          <p>${esc(preview)}</p></div></button>`;
      }).join("")}</div>`
    : `<div class="empty">Здесь появятся ваши результаты.<br>История хранится только на этом устройстве.</div>`);
  $view.querySelectorAll("[data-h]").forEach((el) => {
    el.onclick = () => { S.historyItem = items.find((i) => String(i.id) === el.dataset.h); render(); };
  });
}

function renderHistoryItem(it) {
  const t = toolById(it.tool);
  $view.innerHTML = `
    <button class="back" id="back">‹ Назад</button>
    <div class="tool-head"><div class="ico" style="${grad(t.colors)}">${t.icon}</div>
      <div><h2>${esc(it.title)}</h2><p>${new Date(it.ts).toLocaleString("ru-RU")}</p></div></div>
    <div id="result">${resultHTML({ text: it.text || "Медиафайлы были отправлены в чат с ботом." }, it.title)}</div>`;
  $view.querySelector("#back").onclick = goBack;
  bindResult($view.querySelector("#result"), it.text, it.title);
}

// ---------- настройки ----------

function renderSettings() {
  const p = providers();
  const st = S.settings;
  const models = S.cfg.models || {};
  $view.innerHTML = `
    <div class="page-title">Настройки</div>
    <div class="panel"><h4>Модель по умолчанию</h4>
      <div class="seg" id="setProvider">${PROVIDERS.map(([id, l]) =>
        `<button data-v="${id}" class="${id === defaultProvider() ? "on" : ""}" ${p[id] ? "" : "disabled"}>${l}</button>`).join("")}</div>
      <p class="muted">Используется во всех текстовых разделах. Видео всегда анализирует Gemini.</p>
    </div>
    <div class="panel"><h4>Язык ответов</h4>
      <div class="seg" id="setLang">${LANGS.map(([id, l]) => `<button data-v="${id}" class="${id === st.lang ? "on" : ""}">${l}</button>`).join("")}</div>
      <p class="muted">Промпты для генераторов всегда пишутся на английском — так они работают лучше.</p>
    </div>
    <div class="panel">
      <label class="toggle"><span>Дублировать текст в чат с ботом</span><input type="checkbox" id="setChat" ${st.toChat ? "checked" : ""}><i></i></label>
      <p class="muted">Картинки, аудио и видео отправляются в чат всегда.</p>
    </div>
    <div class="panel"><h4>Подключённые сервисы</h4>
      ${Object.keys(SERVICE_NAMES).map((k) => `<div class="row"><span>${p[k] ? "🟢" : "⚪️"} ${SERVICE_NAMES[k]}</span><span>${p[k] ? esc(models[k] || "") : "нет ключа"}</span></div>`).join("")}
    </div>
    <button class="btn-ghost" id="clearHistory" style="width:100%">Очистить историю</button>`;

  const bindSeg = (id, key) => $view.querySelectorAll(`#${id} button`).forEach((b) => {
    b.onclick = () => {
      st[key] = b.dataset.v;
      save("settings", st);
      $view.querySelectorAll(`#${id} button`).forEach((x) => x.classList.toggle("on", x === b));
      haptic();
    };
  });
  bindSeg("setProvider", "provider");
  bindSeg("setLang", "lang");
  $view.querySelector("#setChat").onchange = (e) => { st.toChat = e.target.checked; save("settings", st); };
  $view.querySelector("#clearHistory").onclick = () => { save("history", []); toast("История очищена"); };
}

// ---------- старт ----------

async function init() {
  if (tg) {
    tg.ready();
    tg.expand();
    try { tg.setHeaderColor("#0a0b0d"); tg.setBackgroundColor("#0a0b0d"); tg.setBottomBarColor("#0c0d10"); } catch { /* старый клиент */ }
    if (tg.BackButton) tg.BackButton.onClick(goBack);
  }
  document.querySelectorAll("#tabbar button").forEach((b) => { b.onclick = () => { if (!S.busy) setTab(b.dataset.tab); }; });

  $view.innerHTML = `<div class="empty"><span class="spinner" style="display:inline-block"></span></div>`;
  try {
    S.cfg = await api("/api/config");
    render();
  } catch (e) {
    $view.innerHTML = `<div class="logo" style="margin:10px 0 20px">my<b>ai</b>helper</div><div class="error">${esc(e.message)}</div>`;
  }
}

init();
