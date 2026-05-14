"use strict";

const POSITIONS = ["ALL", "QB", "RB", "WR", "TE", "K"];

const state = {
  season: null,
  seasons: [],
  screen: "players",
  players: { q: "", position: "ALL" },
  rankings: { scope: "season", week: 1, scoring: "ppr", position: "ALL" },
};

const $ = (sel) => document.querySelector(sel);
const el = (tag, cls, text) => {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text != null) node.textContent = text;
  return node;
};

let loadingCount = 0;
function showLoading(on) {
  loadingCount += on ? 1 : -1;
  loadingCount = Math.max(0, loadingCount);
  $("#loading").classList.toggle("hidden", loadingCount === 0);
}

async function api(path) {
  showLoading(true);
  try {
    const res = await fetch(path);
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
    return data;
  } finally {
    showLoading(false);
  }
}

function fmt(n) {
  if (n == null) return "0";
  return Number.isInteger(n) ? String(n) : n.toFixed(1);
}

function avatar(url, name) {
  const img = el("img", "avatar");
  img.alt = name || "";
  img.loading = "lazy";
  img.src = url || "";
  img.onerror = () => { img.style.visibility = "hidden"; };
  return img;
}

const KNOWN_POSITIONS = ["QB", "RB", "WR", "TE", "K"];

function posPill(position) {
  const pos = (position || "").toUpperCase();
  const key = KNOWN_POSITIONS.includes(pos) ? pos.toLowerCase() : "na";
  return el("span", `pos-pill pos-${key}`, pos || "—");
}

function playerSub(parts) {
  const text = parts.filter(Boolean).join(" · ");
  return text ? el("span", "sub-text", text) : null;
}

function showError(container, message) {
  container.innerHTML = "";
  container.appendChild(el("div", "error-banner", message));
}

/* ---------------- Navigation ---------------- */

function switchScreen(name) {
  state.screen = name;
  document.querySelectorAll(".screen").forEach((s) => s.classList.remove("active"));
  $(`#screen-${name}`).classList.add("active");
  document.querySelectorAll(".tab").forEach((t) =>
    t.classList.toggle("active", t.dataset.screen === name)
  );
  $("#screen-title").textContent = name === "players" ? "Players" : "Rankings";
  if (name === "rankings") loadRankings();
}

/* ---------------- Players screen ---------------- */

function renderChipRow(container, values, current, onPick) {
  container.innerHTML = "";
  values.forEach((value) => {
    let cls = "";
    if (KNOWN_POSITIONS.includes(value)) cls += `pos-${value.toLowerCase()} `;
    if (value === current) cls += "active";
    const btn = el("button", cls.trim(), value);
    btn.addEventListener("click", () => onPick(value));
    container.appendChild(btn);
  });
}

function playerRow(p, opts = {}) {
  const row = el("div", "player-row");
  if (opts.rank != null) {
    const r = el("div", "rank-num" + (opts.rank <= 3 ? " top" : ""), String(opts.rank));
    row.appendChild(r);
  }
  row.appendChild(avatar(p.headshot_url, p.name));
  const meta = el("div", "player-meta");
  meta.appendChild(el("div", "player-name", p.name));
  const sub = el("div", "player-sub");
  sub.appendChild(posPill(p.position));
  const subText = playerSub([p.team, opts.sub]);
  if (subText) sub.appendChild(subText);
  meta.appendChild(sub);
  row.appendChild(meta);
  const pts = el("div", "player-points");
  pts.appendChild(el("div", "points-value", fmt(p.points)));
  pts.appendChild(el("div", "points-label", opts.pointsLabel || "FPTS"));
  row.appendChild(pts);
  row.addEventListener("click", () => openDetail(p.id));
  return row;
}

let searchTimer = null;
async function loadPlayers() {
  const listEl = $("#players-list");
  try {
    const params = new URLSearchParams({
      season: state.season,
      q: state.players.q,
      position: state.players.position,
    });
    const data = await api(`/api/players?${params}`);
    listEl.innerHTML = "";
    $("#players-empty").classList.toggle("hidden", data.players.length > 0);
    data.players.forEach((p) =>
      listEl.appendChild(playerRow(p, { sub: `${p.games_played} G`, pointsLabel: "PPR" }))
    );
  } catch (err) {
    showError(listEl, err.message);
  }
}

/* ---------------- Rankings screen ---------------- */

async function loadRankings() {
  const listEl = $("#rankings-list");
  try {
    const r = state.rankings;
    const params = new URLSearchParams({
      season: state.season,
      scope: r.scope,
      scoring: r.scoring,
      position: r.position,
    });
    if (r.scope === "week") params.set("week", r.week);
    const data = await api(`/api/rankings?${params}`);
    listEl.innerHTML = "";
    $("#rankings-empty").classList.toggle("hidden", data.rankings.length > 0);
    data.rankings.forEach((p) => {
      const sub = r.scope === "week" ? `vs ${p.opponent}` : `${p.points_per_game} / G`;
      listEl.appendChild(playerRow(p, { rank: p.rank, sub, pointsLabel: r.scoring }));
    });
  } catch (err) {
    showError(listEl, err.message);
  }
}

/* ---------------- Player detail ---------------- */

const TOTAL_TILES = [
  { key: "passing_yards", label: "Pass Yds" },
  { key: "passing_tds", label: "Pass TD" },
  { key: "passing_interceptions", label: "INT" },
  { key: "rushing_yards", label: "Rush Yds" },
  { key: "rushing_tds", label: "Rush TD" },
  { key: "carries", label: "Carries" },
  { key: "receptions", label: "Rec" },
  { key: "receiving_yards", label: "Rec Yds" },
  { key: "receiving_tds", label: "Rec TD" },
  { key: "targets", label: "Targets" },
  { key: "fg_made", label: "FG Made" },
  { key: "pat_made", label: "XP Made" },
];

const LOG_COLS = [
  { key: "week", label: "Wk" },
  { key: "opponent", label: "Opp" },
  { key: "completions", label: "Cmp" },
  { key: "attempts", label: "Att" },
  { key: "passing_yards", label: "PaYd" },
  { key: "passing_tds", label: "PaTD" },
  { key: "passing_interceptions", label: "INT" },
  { key: "carries", label: "Car" },
  { key: "rushing_yards", label: "RuYd" },
  { key: "rushing_tds", label: "RuTD" },
  { key: "receptions", label: "Rec" },
  { key: "targets", label: "Tgt" },
  { key: "receiving_yards", label: "ReYd" },
  { key: "receiving_tds", label: "ReTD" },
];

function nonZeroTiles(totals) {
  return TOTAL_TILES.filter((t) => (totals[t.key] || 0) !== 0);
}

async function openDetail(playerId) {
  const sheet = $("#detail-sheet");
  const content = $("#detail-content");
  content.innerHTML = "";
  sheet.classList.remove("hidden");
  try {
    const p = await api(`/api/player/${encodeURIComponent(playerId)}?season=${state.season}`);
    const totals = p.season_totals;

    const header = el("div", "detail-header");
    header.appendChild(avatar(p.headshot_url, p.name));
    const hmeta = el("div", "player-meta");
    hmeta.appendChild(el("h2", null, p.name));
    const hsub = el("div", "player-sub");
    hsub.appendChild(posPill(p.position));
    const hsubText = playerSub([p.team, `${p.season} season`]);
    if (hsubText) hsub.appendChild(hsubText);
    hmeta.appendChild(hsub);
    header.appendChild(hmeta);
    content.appendChild(header);

    // Fantasy summary tiles
    content.appendChild(el("div", "section-title", "Fantasy Points"));
    const fantasyGrid = el("div", "totals-grid");
    [
      { v: totals.fantasy_points_ppr, l: "PPR" },
      { v: totals.fantasy_points_half_ppr, l: "Half-PPR" },
      { v: totals.fantasy_points, l: "Standard" },
    ].forEach((t) => {
      const tile = el("div", "stat-tile highlight");
      tile.appendChild(el("div", "v", fmt(t.v)));
      tile.appendChild(el("div", "l", t.l));
      fantasyGrid.appendChild(tile);
    });
    content.appendChild(fantasyGrid);

    // Season totals tiles
    content.appendChild(el("div", "section-title",
      `Season Totals · ${totals.games_played} games`));
    const totalsGrid = el("div", "totals-grid");
    nonZeroTiles(totals).forEach((t) => {
      const tile = el("div", "stat-tile");
      tile.appendChild(el("div", "v", fmt(totals[t.key])));
      tile.appendChild(el("div", "l", t.label));
      totalsGrid.appendChild(tile);
    });
    content.appendChild(totalsGrid);

    // Per-game log
    content.appendChild(el("div", "section-title", "Game Log"));
    content.appendChild(buildGameLog(p.games));
  } catch (err) {
    showError(content, err.message);
  }
}

function buildGameLog(games) {
  // Only show stat columns that have a non-zero value in some game.
  const activeCols = LOG_COLS.filter((c) =>
    c.key === "week" || c.key === "opponent" ||
    games.some((g) => (g[c.key] || 0) !== 0)
  );
  const wrap = el("div", "gamelog-wrap");
  const table = el("table", "gamelog");
  const thead = el("thead");
  const hrow = el("tr");
  activeCols.forEach((c) => hrow.appendChild(el("th", null, c.label)));
  hrow.appendChild(el("th", null, "FPTS"));
  thead.appendChild(hrow);
  table.appendChild(thead);

  const tbody = el("tbody");
  games.forEach((g) => {
    const tr = el("tr");
    activeCols.forEach((c) => {
      const val = c.key === "opponent" ? (g.opponent || "-") : fmt(g[c.key]);
      tr.appendChild(el("td", null, val));
    });
    tr.appendChild(el("td", "fpts", fmt(g.fantasy_points_ppr)));
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  wrap.appendChild(table);
  return wrap;
}

function closeDetail() {
  $("#detail-sheet").classList.add("hidden");
}

/* ---------------- Init ---------------- */

function populateSeasons() {
  const sel = $("#season-select");
  sel.innerHTML = "";
  state.seasons.forEach((s) => {
    const opt = el("option", null, String(s));
    opt.value = s;
    sel.appendChild(opt);
  });
  sel.value = state.season;
}

function populateWeeks() {
  const sel = $("#rankings-week");
  sel.innerHTML = "";
  for (let w = 1; w <= 18; w++) {
    const opt = el("option", null, `Week ${w}`);
    opt.value = w;
    sel.appendChild(opt);
  }
  sel.value = state.rankings.week;
}

function wireEvents() {
  document.querySelectorAll(".tab").forEach((tab) =>
    tab.addEventListener("click", () => switchScreen(tab.dataset.screen))
  );

  $("#season-select").addEventListener("change", (e) => {
    state.season = Number(e.target.value);
    loadPlayers();
    if (state.screen === "rankings") loadRankings();
  });

  $("#search-input").addEventListener("input", (e) => {
    state.players.q = e.target.value.trim();
    clearTimeout(searchTimer);
    searchTimer = setTimeout(loadPlayers, 220);
  });

  $("#detail-close").addEventListener("click", closeDetail);
  $(".sheet-backdrop").addEventListener("click", closeDetail);

  // Rankings scope
  $("#rankings-scope").querySelectorAll("button").forEach((btn) =>
    btn.addEventListener("click", () => {
      state.rankings.scope = btn.dataset.scope;
      $("#rankings-scope").querySelectorAll("button").forEach((b) =>
        b.classList.toggle("active", b === btn));
      $("#rankings-week-wrap").classList.toggle("hidden", state.rankings.scope !== "week");
      loadRankings();
    })
  );

  $("#rankings-week").addEventListener("change", (e) => {
    state.rankings.week = Number(e.target.value);
    loadRankings();
  });

  // Rankings scoring
  $("#rankings-scoring").querySelectorAll("button").forEach((btn) =>
    btn.addEventListener("click", () => {
      state.rankings.scoring = btn.dataset.scoring;
      $("#rankings-scoring").querySelectorAll("button").forEach((b) =>
        b.classList.toggle("active", b === btn));
      loadRankings();
    })
  );
}

async function init() {
  wireEvents();
  populateWeeks();
  renderChipRow($("#players-positions"), POSITIONS, state.players.position, (pos) => {
    state.players.position = pos;
    document.querySelectorAll("#players-positions button").forEach((b) =>
      b.classList.toggle("active", b.textContent === pos));
    loadPlayers();
  });
  renderChipRow($("#rankings-positions"), POSITIONS, state.rankings.position, (pos) => {
    state.rankings.position = pos;
    document.querySelectorAll("#rankings-positions button").forEach((b) =>
      b.classList.toggle("active", b.textContent === pos));
    loadRankings();
  });

  try {
    const data = await api("/api/seasons");
    state.seasons = data.seasons.length ? data.seasons : [data.default];
    state.season = data.default;
    populateSeasons();
    await loadPlayers();
  } catch (err) {
    showError($("#players-list"), err.message);
  }
}

document.addEventListener("DOMContentLoaded", init);
