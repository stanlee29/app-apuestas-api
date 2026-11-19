/* Research actual de AppApuestas: PitchAPI */
(function(){
  "use strict";
  const $ = id => document.getElementById(id);
  const state = { leagues: [], matches: [], selected: null, loaded: false, busy: false };
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
    else if (state.includes("live") || state === "in_progress" || state === "1h" || state === "2h") suffix = " · EN VIVO";
    else suffix = " · POR JUGAR";
    return formatDate(match) + " · " + home + " vs " + away + suffix;
  }
  function matchOrder(a,b) {
    const aState = String(a.status || "").toLowerCase(), bState = String(b.status || "").toLowerCase();
    const aLive = aState.includes("live") || aState === "in_progress" || aState === "1h" || aState === "2h";
    const bLive = bState.includes("live") || bState === "in_progress" || bState === "1h" || bState === "2h";
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
  function selectMatch() {
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
    if (!teams.length) return '<div class="pitch-empty">La analítica avanzada por eventos no está disponible para este partido; no se sustituye con cifras inventadas.</div>';
    return '<div class="pitch-two-col">' + teams.map(item => {
      const name = item.team && item.team.name || "Equipo", pass=item.passing||{}, def=item.defending||{}, territory=item.territory||{}, tempo=item.tempo||{}, pv=item.possession_value||{};
      const metrics = [["Precisión de pase",pass.pass_accuracy==null?null:fmt(pass.pass_accuracy,1)+"%"],["Pases progresivos",pass.progressive_passes],["Pases clave",pass.key_passes],["PPDA",def.ppda],["Recuperaciones altas",def.high_turnovers],["Field tilt",territory.field_tilt==null?null:fmt(territory.field_tilt,1)+"%"],["Entradas al área",territory.box_entries],["xT total",pv.xt_total==null?null:fmt(pv.xt_total,3)]];
      return '<div class="pitch-subcard"><h4>' + esc(name) + '</h4>' + metrics.filter(x=>x[1]!=null).map(x=>'<div class="pitch-teamline"><span>'+esc(x[0])+'</span><strong>'+esc(x[1])+'</strong></div>').join("") + '</div>';
    }).join("") + '</div>';
  }
  function renderAnalysis(data) {
    const match = data.partido || state.selected || {};
    const home = match.home_team || {}, away = match.away_team || {};
    const homeName = home.name || "Local", awayName = away.name || "Visitante";
    const homeId = home.id || (data.alineaciones && data.alineaciones.home_team && data.alineaciones.home_team.id) || "home";
    const awayId = away.id || (data.alineaciones && data.alineaciones.away_team && data.alineaciones.away_team.id) || "away";
    const stats = data.estadisticas_equipo || [];
    const xg = data.metricas_calculadas_desde_remates || {};
    const shots = Array.isArray(data.remates) ? data.remates.slice().sort((a,b)=>(Number(b.expected_goals)||0)-(Number(a.expected_goals)||0)).slice(0,10) : [];
    const shotRows = shots.map(item => ['<td>'+esc(item.player && item.player.name || "—")+'</td>','<td>'+esc(item.minute==null?"—":item.minute+"'")+'</td>','<td>'+esc(fmt(item.expected_goals,3))+'</td>','<td>'+esc(item.event_type||"—")+'</td>'].join("")).join("");
    const shotTable = shotRows ? '<div class="research-table-scroll"><table class="research-table"><thead><tr><th>Jugador</th><th>Min</th><th>xG</th><th>Resultado</th></tr></thead><tbody>'+shotRows+'</tbody></table></div>' : '<div class="pitch-empty">No se publicaron remates con xG para este encuentro.</div>';
    const availability = data.disponibilidad || {};
    const coverage = Object.entries(availability).filter(entry=>entry[1]===true).map(entry=>entry[0].replaceAll("_"," "));
    const stateText = String(match.status || "").toLowerCase();
    const isLive = stateText.includes("live") || stateText === "in_progress" || stateText === "1h" || stateText === "2h";
    const isFinished = stateText === "finished" || stateText === "ft" || stateText === "after_extra_time" || stateText === "after_penalties";
    const badge = isLive ? '<span class="pitch-chip live">EN VIVO</span>' : isFinished ? '<span class="pitch-chip finished">FINALIZADO</span>' : '<span class="pitch-chip">PROGRAMADO</span>';
    let html = '<div class="research-card"><div class="pitch-research-statusline">'+badge+'<span class="pitch-chip">FUENTE: PITCHAPI</span><span class="pitch-chip">'+esc(match.date || "Fecha no disponible")+'</span></div>';
    html += '<div class="pitch-analysis-grid"><div class="pitch-kpi"><small>Marcador</small><strong>'+esc(match.score_home==null?"—":match.score_home)+ ' - '+esc(match.score_away==null?"—":match.score_away)+'</strong><em>'+ (isFinished?"Resultado registrado":"Sin resultado final")+'</em></div>';
    html += '<div class="pitch-kpi"><small>xG local</small><strong>'+esc(fmt(xg.local && xg.local.xg,2))+'</strong><em>'+esc(homeName)+'</em></div><div class="pitch-kpi"><small>xG visitante</small><strong>'+esc(fmt(xg.visitante && xg.visitante.xg,2))+'</strong><em>'+esc(awayName)+'</em></div><div class="pitch-kpi"><small>Remates detectados</small><strong>'+esc(data.remates ? data.remates.length : "—")+'</strong><em>Eventos con xG disponibles</em></div></div>';
    html += '<p class="research-muted">Datos analíticos disponibles: '+esc(coverage.length?coverage.join(" · "):"sin bloques avanzados confirmados")+'. '+esc(data.nota||"")+'</p></div>';
    html += '<section class="research-card"><h3>Estadísticas del partido</h3>'+renderTeamStats(stats,homeName,awayName,xg)+'</section>';
    const lineups = data.alineaciones || {};
    html += '<section class="research-card"><h3>Alineaciones y jugadores del encuentro</h3><div class="pitch-two-col">'+renderLineupSide(homeName,lineups.home)+renderLineupSide(awayName,lineups.away)+'</div><p class="pitch-data-note">Las alineaciones previstas se marcan como provisionales. Solo la etiqueta CONFIRMADA indica que la fuente reporta un XI confirmado.</p></section>';
    html += renderPlayerStats(data.estadisticas_jugadores,homeId,awayId,homeName,awayName);
    html += '<section class="research-card"><h3>Remates de mayor xG</h3>'+shotTable+'</section>';
    html += '<section class="research-card"><h3>Mapas de actividad</h3>'+renderHeatmaps(data)+'</section>';
    html += '<section class="research-card"><h3>Analítica avanzada por equipo</h3>'+renderAdvanced(data)+'</section>';
    const h2h = data.h2h && Array.isArray(data.h2h.recent_matches) ? data.h2h.recent_matches.filter(item=>item.finished===true).slice(0,8) : [];
    if (h2h.length) html += '<section class="research-card"><h3>Enfrentamientos recientes</h3><div class="research-table-scroll"><table class="research-table"><thead><tr><th>Fecha</th><th>Local</th><th>Marcador</th><th>Visitante</th></tr></thead><tbody>'+h2h.map(item=>'<tr><td>'+esc(item.time_utc||"—")+'</td><td>'+esc(item.home && item.home.name||"—")+'</td><td>'+esc(item.score_home)+"-"+esc(item.score_away)+'</td><td>'+esc(item.away && item.away.name||"—")+'</td></tr>').join("")+'</tbody></table></div></section>';
    $("pitch-output").innerHTML = html;
    status(isFinished ? "Análisis del encuentro finalizado cargado." : isLive ? "Datos del encuentro en vivo cargados. La antigüedad depende del último snapshot de la fuente." : "Partido programado cargado. La alineación puede ser provisional y las estadísticas se completarán después del encuentro.");
  }
  async function analyse() {
    if (!state.selected) { status("Selecciona un partido primero.",true); return; }
    const button = $("pitch-analyze"), old = button.textContent;
    button.disabled = true; button.textContent = "Analizando…";
    status("Consultando partido, alineaciones, jugadores, remates, mapas y estadísticas…");
    try {
      const data = await get("/api/v1/research/football/matches/" + encodeURIComponent(state.selected.id) + "/analysis");
      renderAnalysis(data);
    } catch (error) { status("No se pudo analizar este partido: " + error.message,true); }
    finally { button.disabled = false; button.textContent = old; }
  }
  function init() {
    if (!("fetch" in window) || !( $("pitch-league") )) return;
    $("pitch-refresh").addEventListener("click",loadLeagues);
    $("pitch-league").addEventListener("change",loadSeasons);
    $("pitch-season").addEventListener("change",loadMatches);
    $("pitch-match").addEventListener("change",selectMatch);
    $("pitch-analyze").addEventListener("click",analyse);
    $("research-toggle").addEventListener("click",() => { if (!$ ("research-view").hidden && !state.loaded) loadLeagues(); });
    if ($("statsbomb-archive")) $("statsbomb-archive").addEventListener("toggle",() => { if ($("statsbomb-archive").open) status("Archivo StatsBomb abierto: es exclusivamente histórico. Para plantillas y rendimiento actual usa el panel principal PitchAPI."); });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded",init); else init();
})();
