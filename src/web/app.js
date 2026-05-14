"use strict";

const POSITIONS = ["ALL", "QB", "RB", "WR", "TE", "K"];
const SCORING_LABEL = { ppr: "PPR", half: "Half-PPR", standard: "Standard" };

const state = {
  season: null,
  seasons: [],
  screen: "players",
  players: { q: "", position: "ALL" },
  rankings: { scope: "season", week: 1, scoring: "ppr", position: "ALL" },
  leagues: { view: "list", detailTab: "standings", current: null, scoreboardWeek: 1 },
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

async function apiSend(path, method, body) {
  showLoading(true);
  try {
    const res = await fetch(path, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
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

const SCREEN_TITLES = { players: "Players", rankings: "Rankings", leagues: "Leagues" };

function switchScreen(name) {
  state.screen = name;
  document.querySelectorAll(".screen").forEach((s) => s.classList.remove("active"));
  $(`#screen-${name}`).classList.add("active");
  document.querySelectorAll(".tab").forEach((t) =>
    t.classList.toggle("active", t.dataset.screen === name)
  );
  $("#screen-title").textContent = SCREEN_TITLES[name] || name;
  if (name === "rankings") loadRankings();
  if (name === "leagues") showLeaguesList();
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

/* ---------------- Leagues screen ---------------- */

function openSheet(id) { $(`#${id}`).classList.remove("hidden"); }
function closeSheet(id) { $(`#${id}`).classList.add("hidden"); }

function field(labelText, control, hint) {
  const wrap = el("div", "field");
  wrap.appendChild(el("label", null, labelText));
  wrap.appendChild(control);
  if (hint) wrap.appendChild(el("div", "hint", hint));
  return wrap;
}

function showLeaguesList() {
  state.leagues.view = "list";
  $("#leagues-list-view").classList.remove("hidden");
  $("#league-detail-view").classList.add("hidden");
  loadLeagues();
}

async function loadLeagues() {
  const listEl = $("#leagues-list");
  try {
    const data = await api("/api/leagues");
    listEl.innerHTML = "";
    $("#leagues-empty").classList.toggle("hidden", data.leagues.length > 0);
    data.leagues.forEach((lg) => {
      const card = el("div", "league-card");
      card.appendChild(el("div", "name", lg.name));
      const scoring = SCORING_LABEL[lg.scoring] || lg.scoring;
      card.appendChild(el("div", "meta",
        `${lg.season} season · ${lg.team_count} teams · ${scoring}`));
      card.addEventListener("click", () => openLeague(lg.id));
      listEl.appendChild(card);
    });
  } catch (err) {
    showError(listEl, err.message);
  }
}

async function openLeague(id) {
  try {
    const league = await api(`/api/leagues/${encodeURIComponent(id)}`);
    enterLeague(league, "standings");
  } catch (err) {
    showError($("#leagues-list"), err.message);
  }
}

function enterLeague(league, tab) {
  state.leagues.current = league;
  state.leagues.view = "detail";
  state.leagues.detailTab = tab;
  state.leagues.scoreboardWeek = league.weeks[0] || 1;
  $("#leagues-list-view").classList.add("hidden");
  $("#league-detail-view").classList.remove("hidden");
  renderLeagueDetail();
}

function renderLeagueDetail() {
  const league = state.leagues.current;
  const head = $("#league-detail-head");
  head.innerHTML = "";
  const box = el("div", "league-head");
  box.appendChild(el("h2", null, league.name));
  const scoring = SCORING_LABEL[league.scoring] || league.scoring;
  box.appendChild(el("div", "meta",
    `${league.season} season · ${league.teams.length} teams · ${scoring}`));
  head.appendChild(box);
  $("#league-tabs").querySelectorAll("button").forEach((b) =>
    b.classList.toggle("active", b.dataset.view === state.leagues.detailTab));
  renderLeagueView();
}

function renderLeagueView() {
  const tab = state.leagues.detailTab;
  if (tab === "scoreboard") renderScoreboard();
  else if (tab === "rosters") renderRosters();
  else renderStandings();
}

function renderStandings() {
  const league = state.leagues.current;
  const content = $("#league-view-content");
  content.innerHTML = "";
  const anyPlayed = league.standings.some((s) => s.games > 0);
  content.appendChild(el("div", "section-title",
    anyPlayed ? "Standings" : "Standings · set rosters to start scoring"));

  const table = el("table", "standings");
  const thead = el("thead");
  const hr = el("tr");
  [["", "rk"], ["Team", "team-cell"], ["W", null], ["L", null], ["T", null],
   ["PF", null], ["PA", null]].forEach(([label, cls]) =>
    hr.appendChild(el("th", cls, label)));
  thead.appendChild(hr);
  table.appendChild(thead);
  const tbody = el("tbody");
  league.standings.forEach((s) => {
    const tr = el("tr");
    tr.appendChild(el("td", "rk" + (s.rank === 1 ? " top" : ""), String(s.rank)));
    const teamTd = el("td", "team-cell");
    teamTd.appendChild(el("div", "nm", s.name));
    tr.appendChild(teamTd);
    tr.appendChild(el("td", "rec", String(s.wins)));
    tr.appendChild(el("td", null, String(s.losses)));
    tr.appendChild(el("td", null, String(s.ties)));
    tr.appendChild(el("td", null, fmt(s.points_for)));
    tr.appendChild(el("td", null, fmt(s.points_against)));
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  content.appendChild(table);

  const del = el("button", "danger-btn", "Delete league");
  del.addEventListener("click", () => deleteLeague(league.id));
  content.appendChild(del);
}

function renderScoreboard() {
  const league = state.leagues.current;
  const content = $("#league-view-content");
  content.innerHTML = "";

  const weekWrap = el("div", "week-wrap");
  const picker = el("label", "week-picker");
  picker.appendChild(el("span", null, "Week"));
  const sel = el("select");
  league.weeks.forEach((w) => {
    const opt = el("option", null, `Week ${w}`);
    opt.value = w;
    sel.appendChild(opt);
  });
  sel.value = state.leagues.scoreboardWeek;
  sel.addEventListener("change", (e) => {
    state.leagues.scoreboardWeek = Number(e.target.value);
    loadScoreboard();
  });
  picker.appendChild(sel);
  weekWrap.appendChild(picker);
  content.appendChild(weekWrap);

  const board = el("div", "list");
  board.id = "scoreboard-board";
  content.appendChild(board);
  loadScoreboard();
}

async function loadScoreboard() {
  const board = $("#scoreboard-board");
  if (!board) return;
  const league = state.leagues.current;
  const week = state.leagues.scoreboardWeek;
  try {
    const data = await api(
      `/api/leagues/${encodeURIComponent(league.id)}/scoreboard?week=${week}`);
    board.innerHTML = "";
    data.matchups.forEach((m) => board.appendChild(matchupCard(m)));
    data.byes.forEach((b) =>
      board.appendChild(el("div", "bye-note", `${b.name} — bye week`)));
    if (!data.matchups.length && !data.byes.length) {
      board.appendChild(el("div", "empty", "No matchups this week."));
    }
  } catch (err) {
    showError(board, err.message);
  }
}

function matchupCard(m) {
  const card = el("div", "matchup-card");
  card.appendChild(el("div", "matchup-tag", m.played ? "Final" : "Not yet played"));
  const homeWin = m.played && m.home.points > m.away.points;
  const awayWin = m.played && m.away.points > m.home.points;
  card.appendChild(matchupSide(m.home, homeWin));
  card.appendChild(matchupSide(m.away, awayWin));
  return card;
}

function matchupSide(side, isWinner) {
  const row = el("div", "matchup-side" + (isWinner ? " winner" : ""));
  row.appendChild(el("div", "nm", side.name));
  row.appendChild(el("div", "pts", fmt(side.points)));
  return row;
}

function renderRosters() {
  const league = state.leagues.current;
  const content = $("#league-view-content");
  content.innerHTML = "";
  content.appendChild(el("div", "section-title", "Teams & rosters"));
  league.teams.forEach((team) => {
    const card = el("div", "team-card");
    const head = el("div", "team-card-head");
    head.appendChild(el("div", "nm", team.name));
    const right = el("div", "team-card-actions");
    right.appendChild(el("span", "ct", `${team.roster.length} players`));
    const editBtn = el("button", "ghost-btn", "Edit");
    editBtn.addEventListener("click", () => openRosterSheet(team));
    right.appendChild(editBtn);
    head.appendChild(right);
    card.appendChild(head);

    if (!team.roster.length) {
      card.appendChild(el("div", "roster-empty", "No players yet — tap Edit to add."));
    } else {
      team.roster.forEach((p) => {
        const line = el("div", "roster-line");
        line.appendChild(posPill(p.position));
        line.appendChild(el("div", "nm", p.name));
        line.appendChild(el("div", "pts", `${fmt(p.points)} pts`));
        card.appendChild(line);
      });
    }
    content.appendChild(card);
  });
}

/* ---- Create league ---- */

function openCreateSheet() {
  const content = $("#create-content");
  content.innerHTML = "";
  content.appendChild(el("h2", "sheet-title", "New League"));

  const nameInput = el("input");
  nameInput.type = "text";
  nameInput.id = "create-name";
  nameInput.placeholder = "My Fantasy League";
  content.appendChild(field("League name", nameInput));

  const seasonSel = el("select");
  seasonSel.id = "create-season";
  state.seasons.forEach((s) => {
    const opt = el("option", null, String(s));
    opt.value = s;
    seasonSel.appendChild(opt);
  });
  seasonSel.value = state.season;
  content.appendChild(field("Season", seasonSel));

  const scoringSel = el("select");
  scoringSel.id = "create-scoring";
  ["ppr", "half", "standard"].forEach((v) => {
    const opt = el("option", null, SCORING_LABEL[v]);
    opt.value = v;
    scoringSel.appendChild(opt);
  });
  content.appendChild(field("Scoring", scoringSel));

  const teams = el("textarea");
  teams.id = "create-teams";
  teams.placeholder = "One team name per line";
  teams.value = "Team 1\nTeam 2\nTeam 3\nTeam 4";
  content.appendChild(field("Teams (one per line)", teams,
    "2-16 teams. A round-robin schedule is generated automatically."));

  const submit = el("button", "primary-btn", "Create League");
  submit.addEventListener("click", submitCreate);
  content.appendChild(submit);

  openSheet("create-sheet");
}

async function submitCreate() {
  const name = $("#create-name").value.trim();
  const season = Number($("#create-season").value);
  const scoring = $("#create-scoring").value;
  const teamNames = $("#create-teams").value
    .split("\n").map((t) => t.trim()).filter(Boolean);
  if (teamNames.length < 2) {
    alert("Add at least 2 teams, one per line.");
    return;
  }
  try {
    const league = await apiSend("/api/leagues", "POST",
      { name, season, scoring, teams: teamNames });
    closeSheet("create-sheet");
    enterLeague(league, "rosters");
  } catch (err) {
    alert(err.message);
  }
}

async function deleteLeague(id) {
  if (!confirm("Delete this league? This cannot be undone.")) return;
  try {
    await apiSend(`/api/leagues/${encodeURIComponent(id)}`, "DELETE");
    showLeaguesList();
  } catch (err) {
    alert(err.message);
  }
}

/* ---- Roster editor ---- */

let rosterSearchTimer = null;
const rosterEdit = { team: null, ids: [], q: "", results: [], info: {} };

function openRosterSheet(team) {
  rosterEdit.team = team;
  rosterEdit.ids = team.roster_ids.slice();
  rosterEdit.q = "";
  rosterEdit.results = [];
  rosterEdit.info = {};
  team.roster.forEach((p) => { rosterEdit.info[p.id] = p; });
  buildRosterSheet();
  openSheet("roster-sheet");
}

function buildRosterSheet() {
  const content = $("#roster-content");
  content.innerHTML = "";
  content.appendChild(el("h2", "sheet-title", rosterEdit.team.name));
  content.appendChild(el("div", "hint-line",
    "Add or remove players, then tap Done to save."));

  const current = el("div");
  current.id = "roster-current";
  content.appendChild(current);

  content.appendChild(el("div", "section-title", "Add players"));
  const search = el("input", "roster-editor-search");
  search.type = "search";
  search.placeholder = "Search players, teams";
  search.autocomplete = "off";
  search.addEventListener("input", (e) => {
    rosterEdit.q = e.target.value.trim();
    clearTimeout(rosterSearchTimer);
    rosterSearchTimer = setTimeout(loadRosterSearch, 220);
  });
  content.appendChild(search);

  const results = el("div", "list");
  results.id = "roster-results";
  content.appendChild(results);

  renderRosterCurrent();
  renderRosterResults();
}

function renderRosterCurrent() {
  const cur = $("#roster-current");
  if (!cur) return;
  cur.innerHTML = "";
  cur.appendChild(el("div", "section-title", `Roster · ${rosterEdit.ids.length}`));
  if (!rosterEdit.ids.length) {
    cur.appendChild(el("div", "roster-empty", "No players yet. Search below to add."));
    return;
  }
  const list = el("div", "list");
  rosterEdit.ids.forEach((pid) => {
    const p = rosterEdit.info[pid] ||
      { id: pid, name: pid, position: "", team: "", headshot_url: "" };
    list.appendChild(rosterAddRow(p, true));
  });
  cur.appendChild(list);
}

async function loadRosterSearch() {
  if (!rosterEdit.q) {
    rosterEdit.results = [];
    renderRosterResults();
    return;
  }
  try {
    const params = new URLSearchParams({
      season: state.leagues.current.season,
      q: rosterEdit.q,
      limit: 30,
    });
    const data = await api(`/api/players?${params}`);
    rosterEdit.results = data.players;
    data.players.forEach((p) => { rosterEdit.info[p.id] = p; });
    renderRosterResults();
  } catch (err) {
    showError($("#roster-results"), err.message);
  }
}

function renderRosterResults() {
  const results = $("#roster-results");
  if (!results) return;
  results.innerHTML = "";
  if (!rosterEdit.q) {
    results.appendChild(el("div", "roster-empty", "Type a name to search players."));
    return;
  }
  if (!rosterEdit.results.length) {
    results.appendChild(el("div", "roster-empty", "No players found."));
    return;
  }
  rosterEdit.results.forEach((p) =>
    results.appendChild(rosterAddRow(p, rosterEdit.ids.includes(p.id))));
}

function rosterAddRow(p, rostered) {
  const row = el("div", "roster-add-row");
  row.appendChild(avatar(p.headshot_url, p.name));
  const meta = el("div", "player-meta");
  meta.appendChild(el("div", "player-name", p.name));
  const sub = el("div", "player-sub");
  sub.appendChild(posPill(p.position));
  const subText = playerSub([p.team]);
  if (subText) sub.appendChild(subText);
  meta.appendChild(sub);
  row.appendChild(meta);

  const btn = el("button", "pill-btn " + (rostered ? "remove" : "add"),
    rostered ? "−" : "+");
  btn.addEventListener("click", () => {
    if (rosterEdit.ids.includes(p.id)) {
      rosterEdit.ids = rosterEdit.ids.filter((id) => id !== p.id);
    } else {
      rosterEdit.ids.push(p.id);
    }
    renderRosterCurrent();
    renderRosterResults();
  });
  row.appendChild(btn);
  return row;
}

async function saveRosterAndClose() {
  const league = state.leagues.current;
  const team = rosterEdit.team;
  if (!league || !team) {
    closeSheet("roster-sheet");
    return;
  }
  try {
    const updated = await apiSend(
      `/api/leagues/${encodeURIComponent(league.id)}/roster`, "POST",
      { team_id: team.id, player_ids: rosterEdit.ids });
    state.leagues.current = updated;
    closeSheet("roster-sheet");
    renderLeagueDetail();
  } catch (err) {
    alert(err.message);
  }
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
  $("#detail-sheet .sheet-backdrop").addEventListener("click", closeDetail);

  // Leagues
  $("#new-league-btn").addEventListener("click", openCreateSheet);
  $("#league-back").addEventListener("click", showLeaguesList);
  $("#league-tabs").querySelectorAll("button").forEach((btn) =>
    btn.addEventListener("click", () => {
      state.leagues.detailTab = btn.dataset.view;
      $("#league-tabs").querySelectorAll("button").forEach((b) =>
        b.classList.toggle("active", b === btn));
      renderLeagueView();
    })
  );
  document.querySelectorAll("[data-close]").forEach((node) =>
    node.addEventListener("click", () => closeSheet(node.dataset.close))
  );
  $("#roster-backdrop").addEventListener("click", saveRosterAndClose);
  $("#roster-done").addEventListener("click", saveRosterAndClose);

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
