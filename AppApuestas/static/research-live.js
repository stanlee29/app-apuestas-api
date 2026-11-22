/* Research actual de AppApuestas: PitchAPI */
(function(){
  "use strict";
  const $ = id => document.getElementById(id);
  const state = { leagues: [], matches: [], selected: null, loaded: false, busy: false, lastAnalysis: null, liveTimer: null };
  const positionNames = {1:"POR",2:"DEF",3:"MED",4:"DEL"};

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
  }
  function safeImage(value) {
    try { const url = new URL(String(value || "")); return url.protocol === "https:" ? url.href : ""; }
    catch (_) { return ""; }
  }
  function status(message, error) {
    const el = $("pitch-status"); if (!el) return;
    el.textContent = message;
    el.className = "research-status" + (error ? " error" : "");
  }
  async function get(path) {
    const response = await fetch(path, {cache:"no-store"});
    let data = {}; try { data = await response.json(); } catch (_) {}
    if (!response.ok) {
      const detail = data.detail;
      const message = typeof detail === "string" ? detail : detail && (detail.mensaje || detail.message || detail.code);
      throw new Error(message || ("HTTP " + response.status));
    }
    return data;
  }
  function fill(id, rows, placeholder) {
    const select = $(id);
    select.innerHTML = '<option value="">' + esc(placeholder) + '</option>' + rows.map(row =>
      '<option value="' + esc(row.value) + '">' + esc(row.label) + '</option>').join("");
    select.disabled = rows.length === 0;
  }
  function seasonYear(season) {
    const match = String(season || "").match(/(19|20)\d{2}/);
    return match ? Number(match[0]) : 0;
  }
  function formatDate(match) {
    const value = match.time_utc || match.date;
    if (!value) return "Fecha sin confirmar";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(match.date || value);
    return new Intl.DateTimeFormat("es-SV", {timeZone:"America/El_Salvador",day:"2-digit",month:"short",hour:"2-digit",minute:"2-digit"}).format(date);
  }
  function matchLabel(match) {
    const home = match.home_team && match.home_team.name || "Local";
    const away = match.away_team && match.away_team.name || "Visitante";
    const state = String(match.status || "").toLowerCase();
    let suffix = "";
    if (state === "finished" || state === "ft" || state === "after_extra_time" || state === "after_penalties") suffix = " · FINAL " + (match.score_home ?? "—") + "-" + (match.score_away ?? "—");
    else if (state.includes("live") || state === "started" || state === "in_progress" || state === "1h" || state === "2h") suffix = " · EN VIVO";
    else suffix = " · POR JUGAR";
    return formatDate(match) + " · " + home + " vs " + away + suffix;
  }
  function matchOrder(a,b) {
    const aState = String(a.status || "").toLowerCase(), bState = String(b.status || "").toLowerCase();
    const aLive = aState.includes("live") || aState === "started" || aState === "in_progress" || aState === "1h" || aState === "2h";
    const bLive = bState.includes("live") || bState === "started" || bState === "in_progress" || bState === "1h" || bState === "2h";
    if (aLive !== bLive) return aLive ? -1 : 1;
    const aFuture = !(aState === "finished" || aState === "ft" || aState === "after_extra_time" || aState === "after_penalties");
    const bFuture = !(bState === "finished" || bState === "ft" || bState === "after_extra_time" || bState === "after_penalties");
    if (aFuture !== bFuture) return aFuture ? -1 : 1;
    const av = Date.parse(a.time_utc || a.date || "") || 0, bv = Date.parse(b.time_utc || b.date || "") || 0;
    return aFuture ? av - bv : bv - av;
  }
  async function loadLeagues() {
    if (state.busy) return;
    state.busy = true; $("pitch-refresh").disabled = true;
    status("Consultando catálogo de ligas y temporadas de PitchAPI…");
    try {
      const data = await get("/api/v1/research/football/leagues");
      state.leagues = Array.isArray(data.ligas) ? data.ligas : [];
      state.leagues.sort((a,b) => String(a.country_code || "").localeCompare(String(b.country_code || "")) || String(a.name || "").localeCompare(String(b.name || ""),"es"));
      fill("pitch-league", state.leagues.map(item => ({value:item.id,label:(item.country_code ? item.country_code + " · " : "") + item.name})), "Selecciona liga");
      state.loaded = true;
      if (!state.leagues.length) { status("PitchAPI respondió, pero no devolvió ligas disponibles.",true); return; }
      const preferred = state.leagues.findIndex(item => /premier league/i.test(item.name || ""));
      $("pitch-league").value = String(state.leagues[preferred >= 0 ? preferred : 0].id);
      await loadSeasons();
      status("Catálogo de PitchAPI cargado: " + state.leagues.length + " ligas. Temporadas y cobertura según disponibilidad de cada competición.");
    } catch (error) {
      state.loaded = false;
      status("No se pudo conectar con PitchAPI: " + error.message + ". Verifica que PITCHAPI_API_KEY esté guardada en Render como variable privada.",true);
    } finally { state.busy = false; $("pitch-refresh").disabled = false; }
  }
  async function loadSeasons() {
    const league = state.leagues.find(item => String(item.id) === $("pitch-league").value);
    state.matches = []; state.selected = null;
    fill("pitch-season", [], "Cargando temporadas…"); fill("pitch-match", [], "Selecciona temporada");
    $("pitch-analyze").disabled = true; $("pitch-output").innerHTML = "";
    if (!league) return;
    const seasons = Array.isArray(league.seasons) ? league.seasons.slice() : [];
    seasons.sort((a,b) => seasonYear(b)-seasonYear(a) || String(b).localeCompare(String(a)));
    fill("pitch-season", seasons.map(item => ({value:item,label:item})), "Selecciona temporada");
    if (seasons.length) { $("pitch-season").value = String(seasons[0]); await loadMatches(); }
    else status("Esta liga todavía no tiene temporadas publicadas por PitchAPI.",true);
  }
  async function loadMatches() {
    const league = $("pitch-league").value, season = $("pitch-season").value;
    state.matches = []; state.selected = null; $("pitch-analyze").disabled = true; $("pitch-output").innerHTML = "";
    fill("pitch-match", [], "Consultando partidos…");
    if (!league || !season) return;
    status("Cargando resultados y próximos partidos de la temporada " + season + "…");
    try {
      const data = await get("/api/v1/research/football/leagues/" + encodeURIComponent(league) + "/matches?season=" + encodeURIComponent(season) + "&status=all");
      state.matches = Array.isArray(data.eventos) ? data.eventos.slice().sort(matchOrder) : [];
      const options = state.matches.map(item => ({value:item.id,label:matchLabel(item)}));
      fill("pitch-match", options, "Selecciona partido");
      const first = state.matches[0];
      if (first) { $("pitch-match").value = String(first.id); selectMatch(); }
      status(state.matches.length + " partidos encontrados en " + season + ". Los próximos aparecen primero; los finalizados quedan disponibles para consultar sus estadísticas.");
    } catch (error) { fill("pitch-match",[],"Sin partidos disponibles"); status("No se pudieron cargar los partidos: " + error.message,true); }
  }
  function stopLivePolling() {
    if (state.liveTimer) window.clearInterval(state.liveTimer);
    state.liveTimer = null;
  }
  function selectMatch() {
    stopLivePolling();
    state.lastAnalysis = null;
    state.selected = state.matches.find(item => String(item.id) === $("pitch-match").value) || null;
    $("pitch-analyze").disabled = !state.selected;
    $("pitch-output").innerHTML = "";
  }
  function valueFor(stats, keys) {
    for (const key of keys) if (stats[key] != null) {
      const item = stats[key];
      if (item && typeof item === "object") return item.stat && item.stat.value != null ? item.stat.value : item.value != null ? item.value : null;
      return item;
    }
    return null;
  }
  function flattenStats(record) {
    const out = {};
    (record.stats || []).forEach(group => {
      const entries = group && group.stats && typeof group.stats === "object" ? group.stats : {};
      Object.entries(entries).forEach(([label,item]) => { if (item && typeof item === "object") out[item.key || label] = item.stat || item; });
    });
    return out;
  }
  function fmt(value, digits) {
    if (value == null || value === "") return "—";
    const n = Number(value); return Number.isFinite(n) ? n.toFixed(digits == null ? 1 : digits) : String(value);
  }
  function initials(name) { return String(name || "?").split(/\s+/).slice(0,2).map(x => x[0] || "").join("").toUpperCase(); }
  function playerAvatar(player) {
    const src = safeImage(player && player.image_url);
    return src ? '<img class="pitch-player-avatar" src="' + esc(src) + '" alt="" loading="lazy">' : '<span class="pitch-player-avatar pitch-player-avatar-fallback">' + esc(initials(player && player.name)) + '</span>';
  }
  function renderLineupSide(name, team) {
    if (!team) return '<div class="pitch-subcard"><h4>' + esc(name) + '</h4><div class="pitch-empty">Alineación no publicada para este partido.</div></div>';
    const confirmed = team.confirmed === true;
    const starters = Array.isArray(team.starters) ? team.starters : [];
    const subs = Array.isArray(team.subs) ? team.subs : [];
    const all = (items) => items.map(player => '<span class="pitch-player-pill"><b>' + esc(player.shirt_number || "·") + '</b>' + esc(player.name || "Jugador") + '<small>' + esc(positionNames[player.position_id] || "") + '</small></span>').join("");
    const note = confirmed ? '<span class="pitch-chip finished">CONFIRMADA</span>' : '<span class="pitch-chip provisional">PROVISIONAL · VERIFICAR</span>';
    let html = '<div class="pitch-subcard"><div class="pitch-lineup-top"><strong>' + esc(name) + (team.formation ? ' · ' + esc(team.formation) : '') + '</strong>' + note + '</div>';
    if (team.coach && team.coach.name) html += '<p class="pitch-data-note">Director técnico: ' + esc(team.coach.name) + '</p>';
    html += '<div class="pitch-player-list">' + (starters.length ? all(starters) : '<span class="pitch-data-note">Titulares todavía no publicados.</span>') + '</div>';
    if (subs.length) html += '<h4 style="margin-top:12px">Suplentes</h4><div class="pitch-player-list">' + all(subs) + '</div>';
    return html + '</div>';
  }
  function renderPlayerStats(players, homeId, awayId, homeName, awayName) {
    if (!Array.isArray(players) || !players.length) return '<div class="pitch-empty">El proveedor no ha publicado estadísticas individuales para este partido. En encuentros futuros, los datos aparecen cuando se registran participaciones.</div>';
    const groups = [{id:homeId,name:homeName},{id:awayId,name:awayName}];
    return groups.map(group => {
      const rows = players.filter(item => String(item.team_id) === String(group.id)).map(item => {
        const stats = flattenStats(item), player = item.player || {};
        const cells = [
          '<td><div class="pitch-player-row">' + playerAvatar(player) + '<span><span class="pitch-player-name">' + esc(player.name || "Jugador") + '</span><br><small class="pitch-team-label">' + esc(positionNames[player.position_id] || "") + '</small></span></div></td>',
          '<td>' + esc(valueFor(stats,["minutes_played"]) ?? "—") + '</td>',
          '<td>' + esc(fmt(valueFor(stats,["rating_title","rating"]),1)) + '</td>',
          '<td>' + esc(valueFor(stats,["goals"]) ?? "—") + '</td>',
          '<td>' + esc(valueFor(stats,["assists"]) ?? "—") + '</td>',
          '<td>' + esc(fmt(valueFor(stats,["expected_goals","xg"]),2)) + '</td>',
          '<td>' + esc(fmt(valueFor(stats,["expected_assists","xa"]),2)) + '</td>',
          '<td>' + esc(valueFor(stats,["total_shots","shots"]) ?? "—") + '</td>'
        ];
        return '<tr>' + cells.join("") + '</tr>';
      }).join("");
      if (!rows) return '';
      return '<section class="research-card"><h3>' + esc(group.name) + ' · rendimiento individual</h3><div class="research-table-scroll"><table class="research-table"><thead><tr><th>Jugador</th><th>Min</th><th>Rating</th><th>G</th><th>A</th><th>xG</th><th>xA</th><th>Rem.</th></tr></thead><tbody>' + rows + '</tbody></table></div></section>';
    }).join("");
  }
  function renderLivePlayerStats(snapshot, homeName, awayName) {
    const lineups = snapshot && snapshot.lineups || {};
    const sides = [{key:"home",name:homeName},{key:"away",name:awayName}];
    const html = sides.map(side => {
      const lineup = lineups[side.key] || {};
      const players = [...(Array.isArray(lineup.starters) ? lineup.starters : []), ...(Array.isArray(lineup.subs) ? lineup.subs : [])];
      if (!players.length) return "";
      const rows = players.map(player => {
        const liveStats = Array.isArray(player.stats) ? player.stats : [];
        const stat = key => { const item = liveStats.find(value => value && value.key === key); return item && item.value != null ? item.value : "—"; };
        let role = player.status === "on_pitch" ? "EN CANCHA" : player.status === "bench" ? "BANCA" : player.status === "sent_off" || player.red_card_minute != null ? "EXPULSADO" : player.subbed_off_minute != null ? "SUSTITUIDO" : "PLANTILLA";
        if (player.subbed_on_minute != null) role = "ENTRÓ " + player.subbed_on_minute + "'";
        return '<tr><td><strong>' + esc(player.shirt_number || "·") + '</strong> ' + esc(player.name || "Jugador") + '</td><td>' + esc(role) + '</td><td>' + esc(stat("goals")) + '</td><td>' + esc(stat("rating")) + '</td></tr>';
      }).join("");
      return '<section class="pitch-subcard"><h4>' + esc(side.name) + (lineup.formation ? " · " + esc(lineup.formation) : "") + '</h4><div class="research-table-scroll"><table class="research-table"><thead><tr><th>Jugador</th><th>Estado</th><th>G</th><th>Rating</th></tr></thead><tbody>' + rows + '</tbody></table></div></section>';
    }).join("");
    return html ? '<div class="pitch-two-col">' + html + '</div>' : '<div class="pitch-empty">La fuente todavía no publica el once en vivo.</div>';
  }
  function renderLiveEvents(snapshot) {
    const events = Array.isArray(snapshot && snapshot.events) ? snapshot.events.slice(-12).reverse() : [];
    if (!events.length) return '<div class="pitch-empty">Todavía no hay eventos registrados en el snapshot.</div>';
    const rows = events.map(event => {
      const actor = event.player && event.player.name || event.player_in && event.player_in.name || event.player_out && event.player_out.name || "—";
      const detail = [event.detail, event.player_in && ("Entra " + event.player_in.name), event.player_out && ("Sale " + event.player_out.name)].filter(Boolean).join(" · ");
      const minute = event.minute == null ? "—" : String(event.minute) + (event.added ? "+" + event.added : "") + "'";
      const score = event.score_home == null || event.score_away == null ? "—" : event.score_home + "-" + event.score_away;
      return '<tr><td>' + esc(minute) + '</td><td>' + esc(String(event.type || "Evento").replaceAll("_"," ").toUpperCase()) + '</td><td>' + esc(actor) + '</td><td>' + esc(detail || "—") + '</td><td>' + esc(score) + '</td></tr>';
    }).join("");
    return '<div class="research-table-scroll"><table class="research-table"><thead><tr><th>Min</th><th>Evento</th><th>Jugador</th><th>Detalle</th><th>Marcador</th></tr></thead><tbody>' + rows + '</tbody></table></div>';
  }
  async function refreshLiveSnapshot(matchId) {
    if (!state.selected || String(state.selected.id) !== String(matchId) || !state.lastAnalysis) { stopLivePolling(); return; }
    try {
      const live = await get("/api/v1/research/football/matches/" + encodeURIComponent(matchId) + "/live");
      state.lastAnalysis.live_snapshot = live;
      if (live.status) state.lastAnalysis.partido = { ...(state.lastAnalysis.partido || state.selected), status: live.status, score_home: live.score_home ?? (state.lastAnalysis.partido || state.selected).score_home, score_away: live.score_away ?? (state.lastAnalysis.partido || state.selected).score_away };
      renderAnalysis(state.lastAnalysis);
      if (live.live !== true) stopLivePolling();
    } catch (error) {
      status("Se conserva el último snapshot en vivo. No se pudo actualizar: " + error.message,true);
    }
  }
  function startLivePolling(matchId, live) {
    stopLivePolling();
    if (!live || live.live !== true) return;
    // PitchAPI establece un mínimo de 10 s entre consultas live; usamos 15 s.
    state.liveTimer = window.setInterval(() => refreshLiveSnapshot(matchId),15000);
  }
  function renderHeatmapCard(item, title, grid) {
    const width = Number(grid && grid.length) || 16, height = Number(grid && grid.width) || 12;
    const cells = Array.isArray(item.cells) ? item.cells : [];
    const dense = Array(width * height).fill(0); let max = 0;
    cells.forEach(cell => { if (!Array.isArray(cell) || cell.length < 3) return; const x=Number(cell[0]), y=Number(cell[1]), n=Number(cell[2]); if(Number.isInteger(x)&&Number.isInteger(y)&&x>=0&&x<width&&y>=0&&y<height){dense[y*width+x]=n;max=Math.max(max,n);} });
    const parts = dense.map(n => '<span class="pitch-heat-cell" title="Acciones: ' + n + '" style="--heat:' + (max ? Math.max(.035,n/max).toFixed(2) : .035) + '"></span>').join("");
    return '<div class="pitch-heatmap"><strong>' + esc(title) + '</strong><div class="pitch-heat-grid" style="grid-template-columns:repeat(' + width + ',minmax(0,1fr))">' + parts + '</div><small>' + esc(item.actions || 0) + ' acciones · ' + esc((grid && grid.frame) || "orientación no indicada") + '</small></div>';
  }
  function renderHeatmaps(data) {
    const heat = data.mapas_calor || {}, grid = heat.grid || {};
    const teams = Array.isArray(heat.teams) ? heat.teams : [];
    const players = Array.isArray(heat.players) ? heat.players.slice(0,4) : [];
    if (!teams.length && !players.length) return '<div class="pitch-empty">No hay mapas de actividad disponibles para este encuentro.</div>';
    let html = '<div class="pitch-heatmaps">';
    teams.forEach(item => html += renderHeatmapCard(item, (item.team && item.team.name) || "Actividad del equipo",grid));
    players.forEach(item => html += renderHeatmapCard(item, ((item.player && item.player.name) || "Jugador") + ' · ' + ((item.team && item.team.name) || ""),grid));
    return html + '</div><p class="pitch-data-note">PitchAPI normaliza la dirección de ataque. Cada mapa individual usa la orientación indicada por la fuente; las acciones no equivalen a tracking continuo ni a minutos jugados.</p>';
  }
  function renderTeamStats(stats, homeName, awayName, fallback) {
    const rows = Array.isArray(stats) ? stats : [];
    const usefulKeys = ["expected_goals","total_shots","shots_on_target","corners","fouls","yellow_cards","red_cards","BallPossesion","accurate_passes","big_chances"];
    let selected = rows.filter(item => usefulKeys.includes(item.key));
    if (!selected.length && fallback && fallback.local) {
      selected = [
        {title:"Remates",home:fallback.local.remates,away:fallback.visitante && fallback.visitante.remates},
        {title:"Remates a puerta",home:fallback.local.remates_a_puerta,away:fallback.visitante && fallback.visitante.remates_a_puerta},
        {title:"xG de remates",home:fallback.local.xg,away:fallback.visitante && fallback.visitante.xg}
      ];
    }
    if (!selected.length) return '<div class="pitch-empty">Estadísticas de equipo no disponibles para este encuentro.</div>';
    return '<div class="research-table-scroll"><table class="research-table"><thead><tr><th>Métrica</th><th>' + esc(homeName) + '</th><th>' + esc(awayName) + '</th></tr></thead><tbody>' + selected.map(item => '<tr><td>' + esc(item.title || item.key || "Métrica") + '</td><td>' + esc(item.home ?? "—") + '</td><td>' + esc(item.away ?? "—") + '</td></tr>').join("") + '</tbody></table></div>';
  }
  function renderAdvanced(data) {
    const teams = data.analitica_avanzada && Array.isArray(data.analitica_avanzada.teams) ? data.analitica_avanzada.teams : [];
    if (!teams.length) return '<div class="pitch-empty">La analítica avanzada por eventos no está disponible para este partido; no se sustituyen métricas ausentes por cifras inventadas.</div>';
    return '<div class="pitch-two-col">' + teams.map(item => {
      const name = item.team && item.team.name || "Equipo", pass=item.passing||{}, def=item.defending||{}, territory=item.territory||{}, tempo=item.tempo||{}, pv=item.possession_value||{}, carry=item.carrying||{}, creation=item.creation||{};
      const metrics = [
        ["Valor de posesión xT",pv.xt_total,3],["VAEP total",pv.vaep_total,3],["VAEP ofensivo",pv.vaep_offensive,3],["VAEP defensivo",pv.vaep_defensive,3],
        ["Pases intentados",pass.passes,0],["Precisión de pase",pass.pass_accuracy==null?null:fmt(pass.pass_accuracy,1)+"%",1],
        ["Pases progresivos",pass.progressive_passes,0],["Pases al área",pass.passes_into_box,0],["Pases clave",pass.key_passes,0],
        ["Conducciones progresivas",carry.progressive_carries,0],["Conducciones al área",carry.carries_into_box,0],["Duelos 1v1 ganados",carry.take_ons_won,0],
        ["Ocasiones creadas",creation.chances_created,0],["xAG",creation.xag,2],
        ["Tackles",def.tackles,0],["Intercepciones",def.interceptions,0],["PPDA",def.ppda,2],
        ["Recuperaciones altas",def.high_turnovers,0],["Recuperaciones en 5 s",def.counterpress_regains_5s,0],
        ["Posesión",territory.possession_pct==null?null:fmt(territory.possession_pct,1)+"%",1],
        ["Field tilt",territory.field_tilt==null?null:fmt(territory.field_tilt,1)+"%",1],["Entradas al área",territory.box_entries,0],
        ["Pases por secuencia",tempo.passes_per_sequence,2],["Ataques directos",tempo.direct_attacks,0]
      ];
      return '<div class="pitch-subcard"><h4>' + esc(name) + '</h4>' + metrics.filter(x=>x[1]!=null).map(x=>'<div class="pitch-teamline"><span>'+esc(x[0])+'</span><strong>'+esc(typeof x[1]==="number" ? fmt(x[1],x[2]) : x[1])+'</strong></div>').join("") + '</div>';
    }).join("") + '</div><p class="pitch-data-note">xT y VAEP son métricas de valor de acciones. PPDA, presión, progresión y posesión se muestran solo cuando el proveedor los publica.</p>';
  }

  function pitchFieldSvg() {
    return '<rect class="pitch-field" x="20" y="20" width="680" height="440" rx="2"/>' +
      '<line class="pitch-field-line" x1="360" y1="20" x2="360" y2="460"/>' +
      '<circle class="pitch-field-line" cx="360" cy="240" r="62"/>' +
      '<circle class="pitch-field-line" cx="360" cy="240" r="2" fill="currentColor"/>' +
      '<rect class="pitch-field-line" x="20" y="108" width="107" height="264"/>' +
      '<rect class="pitch-field-line" x="593" y="108" width="107" height="264"/>' +
      '<rect class="pitch-field-line" x="20" y="174" width="36" height="132"/>' +
      '<rect class="pitch-field-line" x="664" y="174" width="36" height="132"/>' +
      '<path class="pitch-field-line" d="M127 198 A62 62 0 0 1 127 282 M593 198 A62 62 0 0 0 593 282"/>' +
      '<path class="pitch-field-line" d="M20 194 L12 194 L12 286 L20 286 M700 194 L708 194 L708 286 L700 286"/>';
  }
  function renderShotMap(data, homeName, awayName, homeId, awayId) {
    const shots = Array.isArray(data.remates) ? data.remates : [];
    const usable = shots.filter(shot => {
      const x = Number(shot.x), y = Number(shot.y), team = String(shot.team_id || "");
      return Number.isFinite(x) && Number.isFinite(y) && x >= 0 && x <= 105 && y >= 0 && y <= 68 &&
        (team === String(homeId) || team === String(awayId));
    });
    if (!usable.length) return '<div class="pitch-empty">El proveedor no entregó coordenadas de remates para dibujar este mapa.</div>';
    const marks = usable.map(shot => {
      const isAway = String(shot.team_id) === String(awayId);
      const x = Number(shot.x), y = Number(shot.y);
      // PitchAPI ya normaliza los tiros para que cada equipo ataque hacia x=105.
      // No se debe girar el visitante: ambas coordenadas ya comparten el mismo marco de ataque.
      const px = 20 + (x / 105) * 680, py = 20 + (y / 68) * 440;
      const rawXg = Number(shot.expected_goals);
      const xg = Number.isFinite(rawXg) ? Math.max(0, Math.min(1, rawXg)) : 0;
      const radius = 4 + Math.sqrt(xg) * 12;
      const goal = String(shot.event_type || "").toLowerCase() === "goal";
      const cls = (isAway ? "away" : "home") + (goal ? " goal" : "");
      const player = shot.player && shot.player.name || "Jugador no identificado";
      const minute = shot.minute == null ? "—" : String(shot.minute) + "'";
      const tip = player + " · " + minute + " · xG " + (Number.isFinite(rawXg) ? rawXg.toFixed(3) : "—") + " · " + (shot.event_type || "Remate");
      return '<circle class="pitch-shot ' + cls + '" cx="' + px.toFixed(1) + '" cy="' + py.toFixed(1) + '" r="' + radius.toFixed(1) + '"><title>' + esc(tip) + '</title></circle>';
    }).join("");
    const homeCount = usable.filter(s => String(s.team_id) === String(homeId)).length;
    const awayCount = usable.length - homeCount;
    return '<div class="pitch-chart-wrap"><svg class="pitch-svg" viewBox="0 0 720 480" role="img" aria-label="Mapa de remates">' +
      pitchFieldSvg() + marks + '</svg><div class="pitch-chart-legend">' +
      '<span><i class="pitch-dot home"></i>' + esc(homeName) + ' · ' + homeCount + '</span>' +
      '<span><i class="pitch-dot away"></i>' + esc(awayName) + ' · ' + awayCount + '</span>' +
      '<span>El tamaño representa xG; los círculos destacados son goles.</span></div></div>';
  }
  function renderXgTimeline(data, homeName, awayName, homeId, awayId) {
    const shots = (Array.isArray(data.remates) ? data.remates : []).filter(s =>
      s && s.team_id != null && s.expected_goals != null &&
      Number.isFinite(Number(s.minute)) && Number.isFinite(Number(s.expected_goals)) &&
      (String(s.team_id) === String(homeId) || String(s.team_id) === String(awayId))
    );
    if (!shots.length) return '<div class="pitch-empty">No hay remates con xG suficiente para construir la evolución acumulada.</div>';
    const maxMinute = Math.max(90, ...shots.map(s => Number(s.minute) + (Number(s.minute_added) || 0)));
    const groups = [{id:String(homeId),name:homeName,cls:"home"},{id:String(awayId),name:awayName,cls:"away"}];
    const summaries = [];
    let maxXg = 0.5;
    groups.forEach(group => {
      const rows = shots.filter(s => String(s.team_id) === group.id)
        .sort((a,b) => (Number(a.minute)+(Number(a.minute_added)||0)) - (Number(b.minute)+(Number(b.minute_added)||0)));
      let cumulative = 0;
      const points = [{minute:0,value:0}];
      rows.forEach(s => {
        cumulative += Math.max(0, Number(s.expected_goals));
        points.push({minute:Number(s.minute)+(Number(s.minute_added)||0),value:cumulative,shot:s});
      });
      maxXg = Math.max(maxXg,cumulative);
      summaries.push({...group,points,total:cumulative});
    });
    const yMax = Math.ceil(maxXg * 1.2 * 2) / 2 || 1;
    const x = minute => 45 + (minute / maxMinute) * 610;
    const y = value => 166 - (value / yMax) * 126;
    const paths = summaries.map(group => {
      let d = "";
      group.points.forEach((p,i) => { d += (i ? " L " : "M ") + x(p.minute).toFixed(1) + " " + y(p.value).toFixed(1); });
      d += " L " + x(maxMinute).toFixed(1) + " " + y(group.total).toFixed(1);
      const dots = group.points.slice(1).map(p => '<circle class="pitch-chart-point ' + group.cls + '" cx="' + x(p.minute).toFixed(1) + '" cy="' + y(p.value).toFixed(1) + '" r="3"><title>' + esc((p.shot && p.shot.player && p.shot.player.name) || "Remate") + ' · ' + p.minute + "' · xG acumulado " + p.value.toFixed(2) + '</title></circle>').join("");
      return '<path class="pitch-chart-line ' + group.cls + '" d="' + d + '"/>' + dots;
    }).join("");
    const ticks = [0,15,30,45,60,75,90].map(t => '<text class="pitch-chart-label" x="' + x(t).toFixed(1) + '" y="190" text-anchor="middle">' + t + "'</text>").join("");
    return '<div class="pitch-chart-wrap"><svg class="pitch-line-chart" viewBox="0 0 680 212" role="img" aria-label="xG acumulado por minuto">' +
      '<line class="pitch-chart-axis" x1="45" y1="166" x2="655" y2="166"/><line class="pitch-chart-axis" x1="45" y1="40" x2="45" y2="166"/>' +
      '<line class="pitch-chart-gridline" x1="45" y1="103" x2="655" y2="103"/>' +
      '<text class="pitch-chart-label" x="10" y="43">xG</text>' + ticks + paths + '</svg>' +
      '<div class="pitch-chart-legend">' + summaries.map(g => '<span><i class="pitch-dot ' + g.cls + '"></i>' + esc(g.name) + ' · ' + g.total.toFixed(2) + ' xG</span>').join("") + '</div></div>';
  }
  function renderPassNetworks(data) {
    const root = data && data.red_pases || {};
    const networks = Array.isArray(root.networks) ? root.networks : [];
    const cards = networks.map(network => {
      const nodes = Array.isArray(network.nodes) ? network.nodes.filter(n =>
        n && n.player && Number.isFinite(Number(n.avg_x)) && Number.isFinite(Number(n.avg_y)) &&
        Number(n.avg_x) >= 0 && Number(n.avg_x) <= 105 && Number(n.avg_y) >= 0 && Number(n.avg_y) <= 68
      ) : [];
      const edges = Array.isArray(network.edges) ? network.edges : [];
      if (!nodes.length) return "";
      const lookup = new Map(nodes.map(n => [String(n.player.id),n]));
      const lines = edges.map(edge => {
        const from = lookup.get(String(edge.from && edge.from.id)), to = lookup.get(String(edge.to && edge.to.id));
        if (!from || !to) return "";
        const x1 = 20 + (Number(from.avg_x) / 105) * 600, y1 = 20 + (Number(from.avg_y) / 68) * 350;
        const x2 = 20 + (Number(to.avg_x) / 105) * 600, y2 = 20 + (Number(to.avg_y) / 68) * 350;
        const passes = Math.max(1,Number(edge.passes)||1);
        const width = Math.min(6,0.8 + Math.sqrt(passes) * 0.65);
        return '<line class="pitch-network-edge" x1="' + x1.toFixed(1) + '" y1="' + y1.toFixed(1) + '" x2="' + x2.toFixed(1) + '" y2="' + y2.toFixed(1) + '" stroke-width="' + width.toFixed(1) + '"><title>' + esc((edge.from && edge.from.name)||"") + ' → ' + esc((edge.to && edge.to.name)||"") + ' · ' + passes + ' pases</title></line>';
      }).join("");
      const circles = nodes.map(node => {
        const px = 20 + (Number(node.avg_x) / 105) * 600, py = 20 + (Number(node.avg_y) / 68) * 350;
        const strength = Math.max(0,Number(node.strength)||((Number(node.passes)||0)+(Number(node.passes_received)||0)));
        const radius = Math.max(7,Math.min(14,6 + Math.sqrt(strength)*0.65));
        const playerName = node.player.name || "Jugador";
        return '<g><circle class="pitch-network-node" cx="' + px.toFixed(1) + '" cy="' + py.toFixed(1) + '" r="' + radius.toFixed(1) + '"><title>' + esc(playerName) + ' · ' + (node.passes||0) + ' pases · ' + (node.passes_received||0) + ' recibidos</title></circle><text class="pitch-network-label" x="' + px.toFixed(1) + '" y="' + (py+radius+12).toFixed(1) + '" text-anchor="middle">' + esc(playerName) + '</text></g>';
      }).join("");
      const center = network.centralization == null ? "—" : (Number(network.centralization)*100).toFixed(1) + "%";
      return '<div class="pitch-network-card"><div class="pitch-network-head"><strong>' + esc(network.team && network.team.name || "Equipo") + '</strong><span>Centralización: ' + center + '</span></div>' +
        '<svg class="pitch-network-svg" viewBox="0 0 640 390" role="img" aria-label="Red de pases">' +
        '<rect class="pitch-field" x="20" y="20" width="600" height="350" rx="2"/><line class="pitch-field-line" x1="320" y1="20" x2="320" y2="370"/><circle class="pitch-field-line" cx="320" cy="195" r="50"/>' +
        '<rect class="pitch-field-line" x="20" y="105" width="94" height="180"/><rect class="pitch-field-line" x="526" y="105" width="94" height="180"/>' +
        lines + circles + '</svg><small>Ventana: hasta la primera sustitución · ' + nodes.length + ' jugadores · ' + edges.length + ' conexiones</small></div>';
    }).filter(Boolean);
    return cards.length ? '<div class="pitch-network-grid">' + cards.join("") + '</div>' :
      '<div class="pitch-empty">La red de pases no está disponible en este partido. La fuente solo la genera cuando existe analítica de eventos suficiente.</div>';
  }
  function renderMomentum(data, homeName, awayName) {
    const points = Array.isArray(data.momentum) ? data.momentum.filter(p =>
      p && Number.isFinite(Number(p.minute)) && Number.isFinite(Number(p.value))
    ).sort((a,b)=>Number(a.minute)-Number(b.minute)) : [];
    if (points.length < 2) return '<div class="pitch-empty">El proveedor no dispone de curva de momentum para este encuentro.</div>';
    const maxMinute = Math.max(90,...points.map(p=>Number(p.minute)));
    const maxAbs = Math.max(1,...points.map(p=>Math.abs(Number(p.value))));
    const x = minute => 38 + (minute / maxMinute) * 604;
    const y = value => 100 - (value / maxAbs) * 72;
    const segments = points.slice(1).map((p,i) => {
      const prev = points[i], avg = (Number(prev.value)+Number(p.value))/2;
      return '<line class="' + (avg >= 0 ? "pitch-momentum-home" : "pitch-momentum-away") + '" x1="' + x(Number(prev.minute)).toFixed(1) + '" y1="' + y(Number(prev.value)).toFixed(1) + '" x2="' + x(Number(p.minute)).toFixed(1) + '" y2="' + y(Number(p.value)).toFixed(1) + '"/>';
    }).join("");
    const labels = [0,15,30,45,60,75,90].map(t=>'<text class="pitch-chart-label" x="'+x(t).toFixed(1)+'" y="190" text-anchor="middle">'+t+"'</text>").join("");
    return '<div class="pitch-chart-wrap"><svg class="pitch-line-chart" viewBox="0 0 680 210" role="img" aria-label="Momentum del partido">' +
      '<line class="pitch-chart-axis" x1="38" y1="100" x2="642" y2="100"/><line class="pitch-chart-gridline" x1="38" y1="28" x2="642" y2="28"/><line class="pitch-chart-gridline" x1="38" y1="172" x2="642" y2="172"/>' +
      '<text class="pitch-chart-label" x="8" y="32">+' + Math.round(maxAbs) + '</text><text class="pitch-chart-label" x="8" y="174">-' + Math.round(maxAbs) + '</text>' +
      segments + labels + '</svg><div class="pitch-chart-legend"><span><i class="pitch-dot home"></i>' + esc(homeName) + ' · presión favorable sobre la línea cero</span><span><i class="pitch-dot away"></i>' + esc(awayName) + ' · presión favorable bajo la línea cero</span></div></div>';
  }
  function renderAdvancedPlayers(data, homeName, awayName, homeId, awayId) {
    const raw = data && data.analitica_avanzada_jugadores;
    const players = Array.isArray(raw) ? raw : raw && Array.isArray(raw.players) ? raw.players : [];
    if (!players.length) return '<div class="pitch-empty">No se publicaron métricas avanzadas individuales para este partido.</div>';
    const sides = [{id:String(homeId),name:homeName},{id:String(awayId),name:awayName}];
    const cards = sides.map(side => {
      const rows = players.filter(p=>String(p.team_id||"")===side.id).sort((a,b)=>
        (Number(b.possession_value && b.possession_value.vaep_total)||Number(b.possession_value && b.possession_value.xt_total)||0) -
        (Number(a.possession_value && a.possession_value.vaep_total)||Number(a.possession_value && a.possession_value.xt_total)||0)
      ).slice(0,12);
      if (!rows.length) return "";
      const body = rows.map(p=>{
        const pv=p.possession_value||{}, pass=p.passing||{}, carry=p.carrying||{}, create=p.creation||{}, def=p.defending||{};
        const player=p.player||{};
        return '<tr><td>' + esc(player.name||"Jugador") + '</td><td>' + esc(p.minutes_played??"—") + '</td>' +
          '<td>' + esc(pv.vaep_total==null?"—":fmt(pv.vaep_total,3)) + '</td><td>' + esc(pv.xt_total==null?"—":fmt(pv.xt_total,3)) + '</td>' +
          '<td>' + esc(pass.progressive_passes??"—") + '</td><td>' + esc(carry.progressive_carries??"—") + '</td>' +
          '<td>' + esc(create.xag==null?"—":fmt(create.xag,2)) + '</td><td>' + esc(def.tackles??"—") + '</td><td>' + esc(def.interceptions??"—") + '</td></tr>';
      }).join("");
      return '<div class="pitch-subcard"><h4>' + esc(side.name) + '</h4><div class="research-table-scroll"><table class="research-table"><thead><tr><th>Jugador</th><th>Min</th><th>VAEP</th><th>xT</th><th>P. prog.</th><th>C. prog.</th><th>xAG</th><th>Tkl</th><th>Int</th></tr></thead><tbody>' + body + '</tbody></table></div></div>';
    }).filter(Boolean);
    return cards.length ? '<div class="pitch-two-col">' + cards.join("") + '</div>' :
      '<div class="pitch-empty">La fuente no publicó métricas individuales para los futbolistas de este encuentro.</div>';
  }
  function renderMatchEvents(data) {
    const events = Array.isArray(data && data.eventos) ? data.eventos.slice().sort((a,b)=>
      (Number(a.minute)||0)+(Number(a.minute_added)||0)/1000 - ((Number(b.minute)||0)+(Number(b.minute_added)||0)/1000)
    ) : [];
    if (!events.length) return '<div class="pitch-empty">No hay goles, tarjetas, sustituciones ni penaltis publicados en la cronología.</div>';
    const labels = {goal:"GOL",yellowcard:"AMARILLA",redcard:"ROJA",substitution:"CAMBIO",penalty:"PENALTI"};
    const rows = events.map(e=>{
      const kind=String(e.event_type||e.type||"evento").toLowerCase().replaceAll("_","");
      const label=labels[kind]||kind.toUpperCase();
      const person=e.player && e.player.name || e.sub_in_player && e.sub_in_player.name || e.player_name || "—";
      const detail=e.sub_in_player && e.player ? ("Entra " + e.sub_in_player.name + " · Sale " + e.player.name) : (e.detail||"—");
      const minute=e.minute==null?"—":String(e.minute)+(e.minute_added?"+"+e.minute_added:"")+"' ";
      const score=e.score_home==null||e.score_away==null?"—":e.score_home+"-"+e.score_away;
      return '<tr><td>' + esc(minute) + '</td><td>' + esc(label) + '</td><td>' + esc(person) + '</td><td>' + esc(detail) + '</td><td>' + esc(score) + '</td></tr>';
    }).join("");
    return '<div class="research-table-scroll"><table class="research-table"><thead><tr><th>Min</th><th>Evento</th><th>Jugador</th><th>Detalle</th><th>Marcador</th></tr></thead><tbody>' + rows + '</tbody></table></div>';
  }

  function renderAnalysis(data) {
    const live = data.live_snapshot && data.live_snapshot.live === true ? data.live_snapshot : null;
    const baseMatch = data.partido || state.selected || {};
    const match = live ? {
      ...baseMatch,
      status: live.status || "started",
      score_home: live.score_home ?? baseMatch.score_home,
      score_away: live.score_away ?? baseMatch.score_away
    } : baseMatch;
    const home = match.home_team || {}, away = match.away_team || {};
    const homeName = home.name || "Local", awayName = away.name || "Visitante";
    const homeId = home.id || (data.alineaciones && data.alineaciones.home_team && data.alineaciones.home_team.id) || "home";
    const awayId = away.id || (data.alineaciones && data.alineaciones.away_team && data.alineaciones.away_team.id) || "away";
    const stats = live && Array.isArray(live.stats) ? live.stats : data.estadisticas_equipo || [];
    const xg = data.metricas_calculadas_desde_remates || {};
    const shots = Array.isArray(data.remates) ? data.remates.slice().sort((a,b)=>(Number(b.expected_goals)||0)-(Number(a.expected_goals)||0)).slice(0,10) : [];
    const shotRows = shots.map(item => ['<td>'+esc(item.player && item.player.name || "—")+'</td>','<td>'+esc(item.minute==null?"—":item.minute+"'")+'</td>','<td>'+esc(fmt(item.expected_goals,3))+'</td>','<td>'+esc(item.event_type||"—")+'</td>'].join("")).join("");
    const shotTable = shotRows ? '<div class="research-table-scroll"><table class="research-table"><thead><tr><th>Jugador</th><th>Min</th><th>xG</th><th>Resultado</th></tr></thead><tbody>'+shotRows+'</tbody></table></div>' : '<div class="pitch-empty">No se publicaron remates con xG para este encuentro.</div>';
    const availability = data.disponibilidad || {};
    const coverage = Object.entries(availability).filter(entry=>entry[1]===true).map(entry=>entry[0].replaceAll("_"," "));
    const stateText = String(match.status || "").toLowerCase();
    const isLive = stateText.includes("live") || stateText === "started" || stateText === "in_progress" || stateText === "1h" || stateText === "2h";
    const isFinished = stateText === "finished" || stateText === "ft" || stateText === "after_extra_time" || stateText === "after_penalties";
    const badge = isLive ? '<span class="pitch-chip live">EN VIVO</span>' : isFinished ? '<span class="pitch-chip finished">FINALIZADO</span>' : '<span class="pitch-chip">PROGRAMADO</span>';
    const clock = live && live.clock && live.clock.display ? '<span class="pitch-chip live">' + esc(live.clock.display) + '</span>' : '';
    const freshness = live ? (live.stale ? '<span class="pitch-chip provisional">SNAPSHOT ANTERIOR · ' + esc(live.age_seconds == null ? "antigüedad desconocida" : live.age_seconds + " s") + '</span>' : '<span class="pitch-chip finished">ACTUALIZADO · ' + esc(live.age_seconds == null ? "reciente" : live.age_seconds + " s") + '</span>') : '';
    let html = '<div class="research-card"><div class="pitch-research-statusline">'+badge+clock+freshness+'<span class="pitch-chip">FUENTE: PITCHAPI</span><span class="pitch-chip">'+esc(match.date || "Fecha no disponible")+'</span></div>';
    html += '<div class="pitch-analysis-grid"><div class="pitch-kpi"><small>Marcador</small><strong>'+esc(match.score_home==null?"—":match.score_home)+ ' - '+esc(match.score_away==null?"—":match.score_away)+'</strong><em>'+ (isFinished?"Resultado registrado":isLive?"Marcador en curso":"Sin resultado final")+'</em></div>';
    html += '<div class="pitch-kpi"><small>xG local</small><strong>'+esc(fmt(xg.local && xg.local.xg,2))+'</strong><em>'+esc(homeName)+'</em></div><div class="pitch-kpi"><small>xG visitante</small><strong>'+esc(fmt(xg.visitante && xg.visitante.xg,2))+'</strong><em>'+esc(awayName)+'</em></div><div class="pitch-kpi"><small>Remates detectados</small><strong>'+esc(data.remates ? data.remates.length : "—")+'</strong><em>Eventos con xG disponibles</em></div></div>';
    html += '<p class="research-muted">Datos analíticos disponibles: '+esc(coverage.length?coverage.join(" · "):"sin bloques avanzados confirmados")+'. '+esc(data.nota||"")+'</p></div>';
    html += '<section class="research-card"><h3>Estadísticas del partido</h3>'+renderTeamStats(stats,homeName,awayName,xg)+'</section>';
    const lineups = live && live.lineups ? live.lineups : data.alineaciones || {};
    html += '<section class="research-card"><h3>'+(live?"Alineación actual y situación de jugadores":"Alineaciones y jugadores del encuentro")+'</h3><div class="pitch-two-col">'+renderLineupSide(homeName,lineups.home)+renderLineupSide(awayName,lineups.away)+'</div><p class="pitch-data-note">'+(live?"La fuente indica quién sigue en cancha, quién está en banca y las sustituciones registradas.":"Las alineaciones previstas se marcan como provisionales. Solo la etiqueta CONFIRMADA indica que la fuente reporta un XI confirmado.")+'</p>';
    if (live) html += renderLivePlayerStats(live,homeName,awayName);
    html += '</section>';
    if (!live) html += renderPlayerStats(data.estadisticas_jugadores,homeId,awayId,homeName,awayName);
    html += '<section class="research-card"><h3>Remates de mayor xG</h3>'+shotTable+'</section>';
    html += '<section class="research-card"><h3>Mapa de tiros</h3>'+renderShotMap(data,homeName,awayName,homeId,awayId)+'</section>';
    html += '<section class="research-card"><h3>xG acumulado durante el partido</h3>'+renderXgTimeline(data,homeName,awayName,homeId,awayId)+'</section>';
    html += '<section class="research-card"><h3>Mapas de actividad</h3>'+renderHeatmaps(data)+'</section>';
    html += '<section class="research-card"><h3>Red de pases</h3>'+renderPassNetworks(data)+'</section>';
    html += '<section class="research-card"><h3>Momentum y dominio por minuto</h3>'+renderMomentum(data,homeName,awayName)+'</section>';
    html += '<section class="research-card"><h3>Analítica avanzada por equipo</h3>'+renderAdvanced(data)+'</section>';
    html += '<section class="research-card"><h3>Rendimiento avanzado por jugador</h3>'+renderAdvancedPlayers(data,homeName,awayName,homeId,awayId)+'</section>';
    if (live) html += '<section class="research-card"><h3>Eventos en directo</h3>'+renderLiveEvents(live)+'<p class="pitch-data-note">Actualización automática cada 15 segundos mientras el proveedor mantiene el partido en estado live. El snapshot incluye la antigüedad y si el dato anterior se está sirviendo como respaldo.</p></section>';
    else html += '<section class="research-card"><h3>Cronología del encuentro</h3>'+renderMatchEvents(data)+'</section>';
    const h2h = data.h2h && Array.isArray(data.h2h.recent_matches) ? data.h2h.recent_matches.filter(item=>item.finished===true).slice(0,8) : [];
    if (h2h.length) html += '<section class="research-card"><h3>Enfrentamientos recientes</h3><div class="research-table-scroll"><table class="research-table"><thead><tr><th>Fecha</th><th>Local</th><th>Marcador</th><th>Visitante</th></tr></thead><tbody>'+h2h.map(item=>'<tr><td>'+esc(item.time_utc||"—")+'</td><td>'+esc(item.home && item.home.name||"—")+'</td><td>'+esc(item.score_home)+"-"+esc(item.score_away)+'</td><td>'+esc(item.away && item.away.name||"—")+'</td></tr>').join("")+'</tbody></table></div></section>';
    $("pitch-output").innerHTML = html;
    if (live) status("Partido en vivo · " + (live.clock && live.clock.display || "en curso") + ". La información se actualiza cada 15 segundos.");
    else if (isFinished) status("Análisis del encuentro finalizado cargado.");
    else status("Partido programado cargado. La alineación puede ser provisional y las estadísticas se completarán después del encuentro.");
  }
  async function analyse() {
    if (!state.selected) { status("Selecciona un partido primero.",true); return; }
    const button = $("pitch-analyze"), old = button.textContent;
    button.disabled = true; button.textContent = "Analizando…";
    stopLivePolling();
    state.lastAnalysis = null;
    status("Consultando partido, alineaciones, jugadores, remates, mapas y estadísticas…");
    const matchId = state.selected.id;
    try {
      const data = await get("/api/v1/research/football/matches/" + encodeURIComponent(matchId) + "/analysis");
      const matchStatus = String(state.selected && state.selected.status || "").toLowerCase();
      if (matchStatus === "started" || matchStatus === "in_progress" || matchStatus.includes("live") || matchStatus === "1h" || matchStatus === "2h") {
        try {
          data.live_snapshot = await get("/api/v1/research/football/matches/" + encodeURIComponent(matchId) + "/live");
          if (data.live_snapshot.status) data.partido = { ...(data.partido || state.selected), status: data.live_snapshot.status, score_home: data.live_snapshot.score_home ?? (data.partido || state.selected).score_home, score_away: data.live_snapshot.score_away ?? (data.partido || state.selected).score_away };
        } catch (liveError) { data.live_warning = liveError.message; }
      }
      state.lastAnalysis = data;
      renderAnalysis(data);
      startLivePolling(matchId,data.live_snapshot);
    } catch (error) { status("No se pudo analizar este partido: " + error.message,true); }
    finally { button.disabled = false; button.textContent = old; }
  }
  function init() {
    if (!("fetch" in window) || !$("pitch-league")) return;
    $("pitch-refresh").addEventListener("click",loadLeagues);
    $("pitch-league").addEventListener("change",loadSeasons);
    $("pitch-season").addEventListener("change",loadMatches);
    $("pitch-match").addEventListener("change",selectMatch);
    $("pitch-analyze").addEventListener("click",analyse);
    $("research-toggle").addEventListener("click",() => { if (!$("research-view").hidden && !state.loaded) loadLeagues(); });
    if ($("statsbomb-archive")) $("statsbomb-archive").addEventListener("toggle",() => { if ($("statsbomb-archive").open) status("Archivo StatsBomb abierto: es exclusivamente histórico. Para plantillas y rendimiento actual usa el panel principal PitchAPI."); });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded",init); else init();
})();
