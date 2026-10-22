const app = document.querySelector("#app");
const state = {
  stack: [],
  account: null,
  clients: [],
  roles: [],
  upcoming: [],
  resultSales: [],
  clientId: "",
  filterOpen: false,
  filters: { sex: "", foaled: "", sire: "", surface: "", min_fee: "", max_fee: "" },
  shortList: false,
  dismissed: new Set(JSON.parse(localStorage.getItem("sales-hub-dismissed") || "[]")),
  starred: new Set(JSON.parse(localStorage.getItem("sales-hub-starred") || "[]")),
  panelOrder: ["pedigree", "crosses", "family", "projected", "physical", "notes"],
  familyOpen: false,
  activeCross: 0,
  voiceStatus: "",
  flash: "",
};

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[ch]));
}

function yoy(value) {
  if (value === null || value === undefined || value === "") return "";
  const number = Number(value);
  const cls = number >= 0 ? "pos" : "neg";
  const sign = number > 0 ? "+" : "";
  return `<span class="${cls}">${sign}${number.toFixed(1)}%</span>`;
}

function preferenceLine(preference) {
  if (!preference) return "";
  const bits = [];
  if (preference.sex === "C") bits.push("Colts");
  if (preference.sex === "F") bits.push("Fillies");
  if (preference.foaled) bits.push(`Foaled ${preference.foaled}`);
  if (preference.surface) bits.push(preference.surface);
  if (preference.min_stud_fee) bits.push(`stud fee ≥ $${Number(preference.min_stud_fee).toLocaleString()}`);
  if (preference.max_stud_fee) bits.push(`stud fee ≤ $${Number(preference.max_stud_fee).toLocaleString()}`);
  if (preference.sire_name) bits.push(preference.sire_name);
  return bits.join(" · ") || "Any hip";
}

function persistSets() {
  localStorage.setItem("sales-hub-dismissed", JSON.stringify([...state.dismissed]));
  localStorage.setItem("sales-hub-starred", JSON.stringify([...state.starred]));
}

function markKey(saleYear, hip) {
  return `${saleYear}:${hip}`;
}

async function api(path, options) {
  const response = await fetch(path, options);
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail || response.statusText);
  }
  return response.json();
}

function navigate(view) {
  state.stack.push(view);
  state.familyOpen = false;
  state.activeCross = 0;
  history.pushState({ depth: state.stack.length }, "");
  render();
}

function goBack() {
  if (state.stack.length <= 1) return;
  history.back();
}

window.addEventListener("popstate", () => {
  if (state.stack.length > 1) state.stack.pop();
  state.familyOpen = false;
  render();
});

function current() {
  return state.stack[state.stack.length - 1] || null;
}

async function boot() {
  const data = await api("/api/bootstrap");
  state.account = data.account;
  state.clients = data.clients;
  state.roles = data.roles;
  state.upcoming = data.upcoming;
  state.resultSales = data.result_sales;
  history.replaceState({ depth: 0 }, "");
  render();
}

function commandBar(title) {
  const back = state.stack.length > 1
    ? `<button class="back-btn" type="button" data-action="back">Back</button>`
    : "";
  return `
    <header class="command">
      ${back}
      <h1>${esc(title)}</h1>
      <button type="button" data-action="results">Sales results</button>
      <button type="button" data-action="upcoming">Upcoming sales</button>
      <button type="button" data-action="filter" aria-pressed="${state.filterOpen}">Filter</button>
    </header>
    <div class="filter-drawer ${state.filterOpen ? "open" : ""}">
      <label>Sex<select data-filter="sex">
        <option value="">Any</option>
        <option value="C" ${state.filters.sex === "C" ? "selected" : ""}>Colt</option>
        <option value="F" ${state.filters.sex === "F" ? "selected" : ""}>Filly</option>
      </select></label>
      <label>Foaled<input data-filter="foaled" value="${esc(state.filters.foaled)}" placeholder="KY" /></label>
      <label>Sire<input data-filter="sire" value="${esc(state.filters.sire)}" placeholder="Name" /></label>
      <label>Surface<select data-filter="surface">
        <option value="">Any</option>
        <option value="Dirt" ${state.filters.surface === "Dirt" ? "selected" : ""}>Dirt</option>
        <option value="Turf" ${state.filters.surface === "Turf" ? "selected" : ""}>Turf</option>
        <option value="Both" ${state.filters.surface === "Both" ? "selected" : ""}>Both</option>
      </select></label>
      <label>Min stud fee<input data-filter="min_fee" value="${esc(state.filters.min_fee)}" inputmode="numeric" /></label>
      <label>Max stud fee<input data-filter="max_fee" value="${esc(state.filters.max_fee)}" inputmode="numeric" /></label>
    </div>`;
}

function entryView() {
  app.innerHTML = `
    <main class="entry">
      <section class="entry-card">
        <h1>Which book?</h1>
        <p>Results already in the book, or a catalog that has not sold yet.</p>
        <div class="choice-row">
          <button class="choice" type="button" data-action="results">See Sales Results<small>Average, million-dollar horses, and growth versus the previous edition</small></button>
          <button class="choice" type="button" data-action="upcoming">See Upcoming Sales<small>Catalog workspace for the next sale</small></button>
        </div>
      </section>
    </main>`;
}

async function resultsHome() {
  const cards = state.resultSales.map((sale) => `
    <button class="sale-card" type="button" data-sale="${esc(sale.sale_title)}">${esc(sale.sale_title)}<small class="muted" style="display:block;margin-top:4px">${esc(sale.sale_company)}</small></button>
  `).join("");
  app.innerHTML = `<main class="shell">${commandBar("Sales results")}<div class="catalog-list">${cards || "<p>No results are loaded.</p>"}</div></main>`;
}

async function resultDetail(view) {
  const report = await api(`/api/stats?sale_title=${encodeURIComponent(view.saleTitle)}`);
  const latest = report.latest;
  const growth = report.growth_vs_previous;
  const rows = report.rows.map((row) => `
    <tr>
      <td>${esc(row.year)}</td>
      <td>${esc(row.offered_display)} ${yoy(row.offered_yoy)}</td>
      <td>${esc(row.gross_display)} ${yoy(row.gross_yoy)}</td>
      <td>${esc(row.average_display)} ${yoy(row.average_yoy)}</td>
      <td>${esc(row.median_display)} ${yoy(row.median_yoy)}</td>
      <td>${esc(row.sold_pct_display)}</td>
      <td>${esc(row.rna_display)}</td>
      <td>${esc(row.millionaires_display)} ${yoy(row.millionaires_yoy)}</td>
    </tr>`).join("");
  const highs = report.highs;
  app.innerHTML = `
    <main class="shell">
      ${commandBar(report.sale_title)}
      <section class="stats-grid">
        <article class="stat"><span>Average · ${esc(latest.year)}</span><strong>${esc(latest.average_display)}</strong></article>
        <article class="stat"><span>Million-dollar horses</span><strong>${esc(latest.millionaires_display)}</strong></article>
        <article class="stat"><span>Growth vs ${esc(report.previous_year || "prior")}</span><strong>${growth === null ? "—" : `${growth > 0 ? "+" : ""}${growth.toFixed(1)}%`}</strong></article>
      </section>
      <p class="muted">Offered ${esc(latest.offered_display)} · gross ${esc(latest.gross_display)} · median ${esc(latest.median_display)} · sold ${esc(latest.sold_pct_display)} · RNA ${esc(latest.rna_display)}</p>
      <div style="overflow:auto;margin-top:14px">
        <table>
          <thead><tr><th>Year</th><th>Offered</th><th>Gross</th><th>Average</th><th>Median</th><th>Sold</th><th>RNA</th><th>$1M+</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
      <h2 class="ui" style="margin:18px 0 8px;font-size:0.8rem;letter-spacing:0.08em;text-transform:uppercase">Sale highs</h2>
      <p>Most offered ${esc(highs.most_offered.display)} in ${esc(highs.most_offered.year)} · Highest gross ${esc(highs.highest_gross.display)} in ${esc(highs.highest_gross.year)} · Highest average ${esc(highs.highest_average.display)} in ${esc(highs.highest_average.year)} · Highest median ${esc(highs.highest_median.display)} in ${esc(highs.highest_median.year)} · Most millionaires ${esc(highs.most_millionaires.display)} in ${esc(highs.most_millionaires.year)}</p>
    </main>`;
}

async function upcomingHome() {
  const cards = state.upcoming.map((sale) => `
    <button class="sale-card" type="button" data-upcoming="${esc(sale.sale_year)}" data-title="${esc(sale.sale_title)}">
      ${esc(sale.sale_title)} · ${esc(sale.sale_year)}
      <small class="muted" style="display:block;margin-top:4px">${esc(sale.source_file)}</small>
    </button>`).join("");
  app.innerHTML = `<main class="shell">${commandBar("Upcoming sales")}<div class="catalog-list">${cards}</div></main>`;
}

function queryFilters() {
  const params = new URLSearchParams({ sale_year: "2026", account_id: state.account.account_id });
  if (state.clientId) params.set("client_id", state.clientId);
  Object.entries(state.filters).forEach(([key, value]) => { if (value) params.set(key, value); });
  return params;
}

async function catalogView(view) {
  const data = await api(`/api/catalog?${queryFilters().toString()}`);
  let hips = data.hips.filter((hip) => !state.dismissed.has(markKey(hip.sale_year, hip.hip)));
  if (state.shortList) {
    hips = hips.filter((hip) => state.starred.has(markKey(hip.sale_year, hip.hip)) || hip.starred === "*");
  }
  const rows = hips.map((hip) => `
    <button class="hip-row ${!state.clientId && hip.fits_any_client ? "fit" : ""}" type="button" data-open-hip="${esc(hip.hip)}" data-year="${esc(hip.sale_year)}" data-title="${esc(hip.sale_title)}">
      <span class="num">Hip ${esc(hip.hip)}</span>
      <span>${esc(hip.horse_name)}</span>
      <span class="hide-sm">${esc(hip.sire)}</span>
      <span>${esc(hip.sex_word || hip.sex)}</span>
      <span class="hide-sm">${esc(hip.foaled)}</span>
      <span class="hide-sm">${esc(hip.year_of_birth)}</span>
    </button>`).join("");
  const clientName = state.clients.find((client) => String(client.client_id) === String(state.clientId));
  app.innerHTML = `
    <main class="shell">
      ${commandBar(`${view.saleTitle} · ${view.saleYear}`)}
      <p class="muted" style="margin-top:10px">${hips.length} hips${clientName ? ` for ${esc(clientName.client_name)}` : ""}${!state.clientId ? " · highlighted hip numbers fit at least one client" : ""}</p>
      <div class="desk" style="margin-top:8px">
        <div class="catalog-list">${rows || "<p>No hips match.</p>"}</div>
        ${toolsHtml()}
      </div>
    </main>`;
}

function nameButton(name, year, klass, extra) {
  if (!name) return "";
  return `<button class="name-btn" type="button" data-horse="${esc(name)}"><span>${esc(name)}${year ? ` (${esc(year)})` : ""}</span><span>${klass ? `<i class="class-pill">${esc(klass)}</i>` : ""} ${extra ? `<span class="sub">${esc(extra)}</span>` : ""}</span></button>`;
}

function damLabel(generation) {
  return ["1st dam", "2nd dam", "3rd dam", "4th dam", "5th dam", "6th dam"][generation - 1] || `Dam ${generation}`;
}

function curveSvg(crosses) {
  const width = 320;
  const height = 140;
  function point(score) {
    const t = Math.max(0, Math.min(100, score)) / 100;
    const x = 16 + t * (width - 32);
    const z = (t - 0.5) * 3.2;
    const gaussian = Math.exp(-0.5 * z * z);
    const y = 118 - gaussian * 90;
    return { x, y };
  }
  let path = "";
  for (let i = 0; i <= 40; i += 1) {
    const spot = point((i / 40) * 100);
    path += `${i === 0 ? "M" : "L"}${spot.x.toFixed(1)},${spot.y.toFixed(1)} `;
  }
  const dots = crosses.map((cross, index) => {
    const spot = point(cross.score);
    return `<circle data-cross="${index}" cx="${spot.x}" cy="${spot.y}" r="6" fill="${cross.exact ? "#8a3a28" : "#241c16"}" stroke="#fbf6ee" stroke-width="1.5"><title>${esc(cross.label)}</title></circle>`;
  }).join("");
  return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Crosses from good to best">
    <path d="${path}" fill="none" stroke="#241c16" stroke-width="1.6"></path>
    <text x="12" y="132" font-family="Liberation Sans, sans-serif" font-size="12">Good</text>
    <text x="274" y="132" font-family="Liberation Sans, sans-serif" font-size="12">Best</text>
    ${dots}
  </svg>`;
}

function toolsHtml() {
  const isAgent = state.account && state.account.industry_role === "Bloodstock Agent";
  const clients = state.clients.map((client) => `
    <button class="client-btn" type="button" data-client="${esc(client.client_id)}" aria-pressed="${String(state.clientId) === String(client.client_id)}">
      ${esc(client.client_name)}
      <small>${esc(preferenceLine(client.preference))}</small>
    </button>`).join("");
  const roleOptions = state.roles.map((role) => `<option value="${esc(role.role_name)}">${esc(role.role_name)}</option>`).join("");
  return `
    <aside class="tools panel">
      <h2>Catalog</h2>
      <div class="tool-grid">
        <button class="tool-btn" type="button" data-action="view-full">View full</button>
        <button class="tool-btn" type="button" data-action="short-list" aria-pressed="${state.shortList}">Short list</button>
        <button class="tool-btn" type="button" data-action="dismiss">Dismiss</button>
        <button class="tool-btn" type="button" data-action="star">Star</button>
      </div>
      <h2 style="margin-top:14px">Clients</h2>
      <p class="muted">${esc(state.account.display_name)} · ${esc(state.account.industry_role)}</p>
      <div class="client-scroll">
        <button class="client-btn" type="button" data-client="" aria-pressed="${!state.clientId}">All clients<small>Highlight hips that fit anyone</small></button>
        ${clients || "<p class='muted'>No clients yet.</p>"}
      </div>
      ${isAgent ? `<form id="client-form" class="stack">
        <input name="client_name" placeholder="New client" required />
        <select name="sex"><option value="">Any sex</option><option value="C">Colt</option><option value="F">Filly</option></select>
        <input name="foaled" placeholder="Foaled state, e.g. KY" />
        <select name="surface"><option value="">Any surface</option><option>Dirt</option><option>Turf</option><option>Both</option></select>
        <input name="min_stud_fee" placeholder="Min stud fee" inputmode="numeric" />
        <input name="max_stud_fee" placeholder="Max stud fee" inputmode="numeric" />
        <input name="sire_name" placeholder="Sire, if they want one" />
        <button class="linkish" type="submit">Add client</button>
      </form>` : ""}
      <form id="account-form" class="stack">
        <input name="display_name" placeholder="Your name" required />
        <input name="email" placeholder="Email" />
        <select name="industry_role" required>
          <option value="">Role in the industry</option>
          ${roleOptions}
        </select>
        <button class="linkish secondary" type="submit">New account</button>
      </form>
      <p class="status muted" id="form-status">${esc(state.flash)}</p>
    </aside>`;
}

function pedigreeHtml(pedigree, openFamily) {
  const sires = (pedigree.sire_line || []).map((horse) => nameButton(
    horse.name, horse.year, horse.class_label, horse.generation === 1 ? "sire" : ""
  )).join("") || "<p class='muted'>No sire line on file.</p>";
  const dams = (pedigree.dams || []).map((dam) => nameButton(
    dam.name, dam.year, dam.class_label, `${damLabel(dam.generation)}${dam.damsire ? ` · by ${dam.damsire}` : ""}`
  )).join("") || "<p class='muted'>No dam line on file.</p>";
  return `<div class="stack"><h3 class="ui" style="font-size:0.85rem">Sire line</h3>${sires}<h3 class="ui" style="font-size:0.85rem">Dam line</h3>${dams}${openFamily ? "" : ""}</div>`;
}

async function hipView(view) {
  const detail = await api(`/api/hip?sale_year=${encodeURIComponent(view.saleYear)}&hip=${encodeURIComponent(view.hip)}&account_id=${encodeURIComponent(state.account.account_id)}`);
  view.detail = detail;
  const header = detail.header;
  const fields = [
    ["Foaled", header.foaled],
    ["Color", header.color],
    ["Sex", header.sex],
    ["Year", header.year],
    ["Hip", header.hip],
    ["Consigned by", header.consignor],
  ];
  const head = fields.map(([label, value]) => `<div><span>${esc(label)}</span><strong class="${label === "Hip" ? "hip-no" : ""}">${esc(value)}</strong></div>`).join("");
  const crosses = detail.crosses || [];
  if (view.activeCross === undefined) {
    const withProgeny = crosses.findIndex((cross) => (cross.auction_progeny || []).length || (cross.stakes_progeny || []).length);
    view.activeCross = withProgeny >= 0 ? withProgeny : 0;
  }
  const activeIndex = view.activeCross;
  const crossButtons = crosses.map((cross, index) => `
    <button type="button" data-cross="${index}" class="${cross.exact ? "exact" : ""}">${esc(cross.label)}${cross.exact ? " · this cross" : ""}</button>`).join("");
  const active = crosses[activeIndex] || null;
  const progeny = !active ? "" : `
    <div class="progeny">
      <p><strong>${esc(active.label)}</strong></p>
      ${active.catalog_note ? `<p class="muted">${esc(active.catalog_note)}</p>` : ""}
      <p class="ui" style="margin-top:8px">Auction progeny</p>
      <ul>${(active.auction_progeny || []).map((item) => `<li>${esc(item.name)} · ${esc(item.sale_type)} · ${esc(item.sale_title)} ${esc(item.sale_year)} · ${esc(item.detail)}</li>`).join("") || "<li>None in the loaded sale book.</li>"}</ul>
      <p class="ui">Stakes progeny</p>
      <ul>${(active.stakes_progeny || []).map((item) => `<li>${esc(item.name)} · ${esc(item.sale_type)} ${esc(item.grade)} · ${esc(item.sale_title)} ${esc(item.sale_year)}</li>`).join("") || "<li>None recorded.</li>"}</ul>
    </div>`;
  const further = detail.family_more || { further_dams: [], siblings: [], produce: [] };
  const moreHtml = state.familyOpen ? `
    <div class="stack">
      ${(further.further_dams || []).map((dam) => nameButton(dam.name, dam.year, dam.class_label, damLabel(dam.generation))).join("")}
      <p class="ui">Same dam in this catalog</p>
      ${(further.siblings || []).map((sib) => `<button class="name-btn" type="button" data-open-hip="${esc(sib.hip)}" data-year="${esc(sib.sale_year)}" data-title="${esc(detail.sale_title)}"><span>Hip ${esc(sib.hip)} ${esc(sib.name)}</span><span class="sub">${esc(sib.sale_type)}</span></button>`).join("") || "<p class='muted'>No other hips by this dam.</p>"}
      <p class="ui">Family on file</p>
      ${(further.produce || []).map((horse) => nameButton(horse.name, horse.year, horse.class_label, horse.sire)).join("") || "<p class='muted'>No further family rows.</p>"}
    </div>` : "";
  const noteBody = detail.note ? detail.note.body : (detail.catalog_note || "");
  const panels = {
    pedigree: `<section class="panel" data-drag="pedigree"><h2>Pedigree <span class="drag-handle" draggable="true">drag</span></h2><p class="muted">${esc(detail.horse_name)} · in the ring as ${esc(detail.sold_as || "catalog hip")}</p>${pedigreeHtml(detail.pedigree)}</section>`,
    crosses: `<section class="panel" data-drag="crosses"><h2>Similar crosses <span class="drag-handle" draggable="true">drag</span></h2><div class="curve-wrap">${curveSvg(crosses)}</div><div class="cross-list">${crossButtons || "<p class='muted'>No recorded crosses yet. The curve is still here.</p>"}</div>${progeny}</section>`,
    family: `<section class="panel" data-drag="family"><h2>Female family <span class="drag-handle" draggable="true">drag</span></h2>${(detail.pedigree.dams || []).map((dam) => nameButton(dam.name, dam.year, dam.class_label, damLabel(dam.generation))).join("") || "<p class='muted'>No dam line.</p>"}<p class="muted" style="margin-top:8px">${esc(detail.dam_success_producer || detail.dam_success_racer || "")}</p><button class="linkish secondary" type="button" data-action="more-family" style="margin-top:8px">${state.familyOpen ? "Show less" : "Open more of the family"}</button>${moreHtml}</section>`,
    projected: `<section class="panel" data-drag="projected"><h2>Projected value <span class="drag-handle" draggable="true">drag</span></h2><div class="blank-value" aria-label="Projected value"></div></section>`,
    physical: `<section class="panel" data-drag="physical"><h2>Physical <span class="drag-handle" draggable="true">drag</span></h2><div class="stack"><p><span class="sub">Hip height</span><br />${esc(detail.physical.hip_height)}</p><p><span class="sub">Hip conformation</span><br />${esc(detail.physical.hip_conformation)}</p><p><span class="sub">${esc(detail.physical.sire_name)} · sire height</span><br />${esc(detail.physical.sire_height)}</p><p class="preserve"><span class="sub">Sire conformation</span><br />${esc(detail.physical.sire_conformation)}</p><p><span class="sub">Sire surface</span><br />${esc(detail.physical.sire_surface)}</p></div></section>`,
    notes: `<section class="panel" data-drag="notes"><h2>Notes <span class="drag-handle" draggable="true">drag</span></h2><div class="notes-box"><textarea id="note-body">${esc(noteBody)}</textarea><div class="note-actions"><button type="button" data-action="save-note">Save note</button><button class="secondary" type="button" data-action="voice">Voice</button></div><p class="status muted" id="note-status">${esc(state.voiceStatus)}</p></div></section>`,
  };
  const ordered = state.panelOrder.map((id) => panels[id]).join("");
  app.innerHTML = `
    <main class="shell">
      ${commandBar(`${detail.sale_title} · ${detail.sale_year}`)}
      <section class="horse-head">${head}</section>
      <div class="desk">
        <div class="board" id="board">${ordered}</div>
        ${toolsHtml()}
      </div>
    </main>`;
  enableDrag();
}

async function horseView(view) {
  const horse = await api(`/api/horse?name=${encodeURIComponent(view.name)}`);
  const head = [
    ["Foaled", horse.foaling_year],
    ["Color", horse.color],
    ["Sex", horse.sex],
    ["Year", horse.foaling_year],
    ["Class", horse.class_label],
    ["Farm", (horse.farm || "").replaceAll("_", " ")],
  ].map(([label, value]) => `<div><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`).join("");
  const further = (horse.family_more && horse.family_more.further_dams) || [];
  app.innerHTML = `
    <main class="shell">
      ${commandBar(horse.display_name || horse.name)}
      <section class="horse-head">${head}</section>
      <div class="board">
        <section class="panel"><h2>Pedigree</h2>${pedigreeHtml(horse.pedigree)}
          ${further.map((dam) => nameButton(dam.name, dam.year, dam.class_label, damLabel(dam.generation))).join("")}
        </section>
        <section class="panel"><h2>Physical</h2>
          <p><span class="sub">Height</span><br />${esc(horse.height)}</p>
          <p class="preserve" style="margin-top:8px"><span class="sub">Conformation</span><br />${esc(horse.conformation)}</p>
          <p style="margin-top:8px"><span class="sub">Surface</span><br />${esc(horse.surface)}</p>
          <p style="margin-top:8px"><span class="sub">Stud fee</span><br />${horse.stud_fee ? `$${Number(horse.stud_fee).toLocaleString()}` : ""}</p>
        </section>
        <section class="panel"><h2>Major wins</h2><p class="preserve">${esc(horse.major_wins)}</p></section>
        <section class="panel"><h2>Career</h2><p class="preserve">${esc(horse.career_highlight)}</p></section>
      </div>
    </main>`;
}

function enableDrag() {
  const board = document.querySelector("#board");
  if (!board) return;
  let dragId = "";
  board.querySelectorAll("[data-drag]").forEach((panel) => {
    const handle = panel.querySelector(".drag-handle");
    if (!handle) return;
    handle.addEventListener("dragstart", (event) => {
      dragId = panel.dataset.drag;
      panel.classList.add("dragging");
      event.dataTransfer.setData("text/plain", dragId);
    });
    handle.addEventListener("dragend", () => panel.classList.remove("dragging"));
    panel.addEventListener("dragover", (event) => event.preventDefault());
    panel.addEventListener("drop", (event) => {
      event.preventDefault();
      const source = dragId || event.dataTransfer.getData("text/plain");
      const target = panel.dataset.drag;
      if (!source || source === target) return;
      const order = state.panelOrder.slice();
      const from = order.indexOf(source);
      const to = order.indexOf(target);
      if (from < 0 || to < 0) return;
      order.splice(from, 1);
      order.splice(to, 0, source);
      state.panelOrder = order;
      render();
    });
  });
}

async function render() {
  const view = current();
  if (!view) {
    entryView();
    return;
  }
  try {
    if (view.type === "results") await resultsHome();
    else if (view.type === "result") await resultDetail(view);
    else if (view.type === "upcoming") await upcomingHome();
    else if (view.type === "catalog") await catalogView(view);
    else if (view.type === "hip") await hipView(view);
    else if (view.type === "horse") await horseView(view);
  } catch (error) {
    app.innerHTML = `<main class="shell"><p>${esc(error.message)}</p></main>`;
  }
  state.flash = "";
}

function openHipFrom(button) {
  navigate({
    type: "hip",
    hip: button.dataset.openHip,
    saleYear: button.dataset.year,
    saleTitle: button.dataset.title,
  });
}

async function saveNote(source) {
  const view = current();
  if (!view || view.type !== "hip" || !view.detail) return;
  const body = document.querySelector("#note-body");
  const status = document.querySelector("#note-status");
  const saved = await api("/api/notes", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      account_id: state.account.account_id,
      sale_title: view.detail.sale_title,
      hip: view.detail.hip,
      body: body ? body.value : "",
      source,
    }),
  });
  view.detail.note = saved.note;
  if (status) status.textContent = source === "voice" ? "Voice note saved." : "Note saved.";
}

function startVoice() {
  const box = document.querySelector("#note-body");
  const status = document.querySelector("#note-status");
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Recognition) {
    state.voiceStatus = "This browser has no speech recognition. Type the note, then save it.";
    if (status) status.textContent = state.voiceStatus;
    if (box) box.focus();
    return;
  }
  const recognizer = new Recognition();
  recognizer.lang = "en-US";
  if (status) status.textContent = "Listening…";
  recognizer.onresult = async (event) => {
    const transcript = event.results[0][0].transcript;
    if (box) box.value = `${box.value ? `${box.value.trim()} ` : ""}${transcript}`.trim();
    state.voiceStatus = "Voice captured.";
    await saveNote("voice");
  };
  recognizer.onerror = () => {
    if (status) status.textContent = "Voice did not start. Type the note and save it.";
  };
  recognizer.start();
}

app.addEventListener("click", async (event) => {
  const target = event.target.closest("button, circle");
  if (!target) return;
  if (target.dataset.action === "results") {
    navigate({ type: "results" });
    return;
  }
  if (target.dataset.action === "upcoming") {
    navigate({ type: "upcoming" });
    return;
  }
  if (target.dataset.action === "back") {
    goBack();
    return;
  }
  if (target.dataset.action === "filter") {
    state.filterOpen = !state.filterOpen;
    render();
    return;
  }
  if (target.dataset.sale) {
    navigate({ type: "result", saleTitle: target.dataset.sale });
    return;
  }
  if (target.dataset.upcoming) {
    navigate({ type: "catalog", saleYear: target.dataset.upcoming, saleTitle: target.dataset.title });
    return;
  }
  if (target.dataset.openHip) {
    openHipFrom(target);
    return;
  }
  if (target.dataset.horse) {
    navigate({ type: "horse", name: target.dataset.horse });
    return;
  }
  if (target.dataset.cross !== undefined && current() && current().type === "hip") {
    current().activeCross = Number(target.dataset.cross);
    render();
    return;
  }
  if (target.dataset.client !== undefined) {
    state.clientId = target.dataset.client;
    const view = current();
    if (view && view.type === "hip") {
      navigate({
        type: "catalog",
        saleYear: view.saleYear,
        saleTitle: view.detail ? view.detail.sale_title : view.saleTitle,
      });
    } else {
      render();
    }
    return;
  }
  if (target.dataset.action === "short-list") {
    state.shortList = !state.shortList;
    const view = current();
    if (view && view.type === "hip") {
      navigate({
        type: "catalog",
        saleYear: view.saleYear,
        saleTitle: view.detail ? view.detail.sale_title : view.saleTitle,
      });
    } else {
      render();
    }
    return;
  }
  if (target.dataset.action === "view-full") {
    state.shortList = false;
    state.familyOpen = true;
    state.filterOpen = false;
    state.filters = { sex: "", foaled: "", sire: "", surface: "", min_fee: "", max_fee: "" };
    render();
    return;
  }
  if (target.dataset.action === "dismiss") {
    const view = current();
    if (view && view.type === "hip") {
      state.dismissed.add(markKey(view.saleYear, view.hip));
      persistSets();
      goBack();
    }
    return;
  }
  if (target.dataset.action === "star") {
    const view = current();
    if (view && view.type === "hip") {
      const key = markKey(view.saleYear, view.hip);
      if (state.starred.has(key)) state.starred.delete(key);
      else state.starred.add(key);
      persistSets();
      const status = document.querySelector("#form-status");
      if (status) status.textContent = state.starred.has(key) ? "Starred." : "Star removed.";
    }
    return;
  }
  if (target.dataset.action === "more-family") {
    state.familyOpen = !state.familyOpen;
    render();
    return;
  }
  if (target.dataset.action === "save-note") {
    await saveNote("typed");
    return;
  }
  if (target.dataset.action === "voice") {
    startVoice();
  }
});

app.addEventListener("change", (event) => {
  const input = event.target.closest("[data-filter]");
  if (!input) return;
  state.filters[input.dataset.filter] = input.value.trim();
  const view = current();
  if (view && (view.type === "catalog" || view.type === "hip")) render();
});

app.addEventListener("submit", async (event) => {
  const form = event.target;
  if (form.id === "account-form") {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(form).entries());
    try {
      const created = await api("/api/accounts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });
      state.account = created.account;
      state.clients = [];
      state.clientId = "";
      state.flash = `${created.account.display_name} signed in as ${created.account.industry_role}.`;
      render();
    } catch (error) {
      const status = document.querySelector("#form-status");
      if (status) status.textContent = error.message;
    }
  }
  if (form.id === "client-form") {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(form).entries());
    data.account_id = state.account.account_id;
    try {
      const created = await api("/api/clients", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });
      state.clients.push(created.client);
      state.clientId = String(created.client.client_id);
      render();
    } catch (error) {
      const status = document.querySelector("#form-status");
      if (status) status.textContent = error.message;
    }
  }
});

boot();
