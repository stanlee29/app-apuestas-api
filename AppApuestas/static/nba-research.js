/* NBA Research: scoreboard, rosters, shot chart y game logs desde nba_api. */
(function(){
  "use strict";
  const $ = id => document.getElementById(id);
  const state = { games: [], selected: null, busy: false, logs: [] };

  function esc(value){
    return String(value == null ? "" : value).replace(/[&<>"']/g,ch=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
  }
  function pick(object, keys, fallback){
    for(const key of keys){ if(object && object[key] != null && object[key] !== "") return object[key]; }
    return fallback;
  }
  function teamObject(value, side, game){
    if(value && typeof value === "object") return value;
    if(typeof value === "string"){
      try { return JSON.parse(value); } catch(_) { return {teamName:value}; }
    }
    const name = pick(game, [side+"TeamName", side+"Team"], side === "home" ? "Local" : "Visitante");
    return {teamName:name, score:pick(game,[side+"TeamScore",side+"Score"],null)};
  }
  function gameInfo(game){
    const home=teamObject(game.homeTeam,"home",game), away=teamObject(game.awayTeam,"away",game);
    const id=String(pick(game,["gameId","GAME_ID","game_id"],""));
    const homeName=pick(home,["teamName","teamCity","name","TEAM_NAME"],pick(game,["homeTeamName"],"Local"));
    const awayName=pick(away,["teamName","teamCity","name","TEAM_NAME"],pick(game,["awayTeamName"],"Visitante"));
    const homeScore=pick(home,["score","points","PTS"],pick(game,["homeTeamScore"],null));
    const awayScore=pick(away,["score","points","PTS"],pick(game,["awayTeamScore"],null));
    const status=pick(game,["gameStatusText","GAME_STATUS_TEXT","gameStatus"],"Programado");
    return {id,home,away,homeName,awayName,homeScore,awayScore,status};
  }
  async function get(path){
    const response=await fetch(path,{cache:"no-store"});
    let body={}; try{body=await response.json();}catch(_){}
    if(!response.ok){
      const detail=body.detail;
      const message=typeof detail==="string"?detail:detail&&(detail.mensaje||detail.message||detail.codigo);
      throw new Error(message||("HTTP "+response.status));
    }
    return body;
  }
  function status(message,error){
    const node=$("nba-status"); if(!node)return;
    node.textContent=message;
    node.className="research-status"+(error?" error":"");
  }
  function localDate(){
    const now=new Date();
    const parts=new Intl.DateTimeFormat("en-CA",{timeZone:"America/El_Salvador",year:"numeric",month:"2-digit",day:"2-digit"}).formatToParts(now);
    const values={}; parts.forEach(p=>values[p.type]=p.value);
    return values.year+"-"+values.month+"-"+values.day;
  }
  function currentSeason(){
    const now=new Date();
    const parts=new Intl.DateTimeFormat("en-US",{timeZone:"America/El_Salvador",year:"numeric",month:"numeric"}).formatToParts(now);
    const values={};parts.forEach(p=>values[p.type]=Number(p.value));
    const start=values.month>=10?values.year:values.year-1;
    return start+"-"+String((start+1)%100).padStart(2,"0");
  }
  function fillGames(games){
    const select=$("nba-game");
    const options=games.map(game=>{
      const info=gameInfo(game);
      const score=info.homeScore!=null&&info.awayScore!=null?" · "+info.homeScore+"-"+info.awayScore:"";
      return '<option value="'+esc(info.id)+'">'+esc(info.homeName+" vs "+info.awayName+" · "+info.status+score)+'</option>';
    }).join("");
    select.innerHTML='<option value="">Selecciona partido</option>'+options;
    select.disabled=!games.length;
    $("nba-shots").disabled=!games.length;
    if(games.length){select.value=gameInfo(games[0]).id; state.selected=games[0];}
  }
  async function loadScoreboard(){
    if(state.busy)return;
    const day=$("nba-date").value;
    if(!day){status("Selecciona una fecha.",true);return;}
    state.busy=true; $("nba-load").disabled=true;
    status("Consultando cartelera y marcadores de NBA.com…");
    try{
      const data=await get("/api/v1/research/nba/scoreboard?fecha="+encodeURIComponent(day));
      state.games=Array.isArray(data.partidos)?data.partidos:[];
      fillGames(state.games);
      status(state.games.length+" partidos encontrados para "+day+". La cobertura depende de NBA.com.");
      $("nba-output").innerHTML=state.games.length?renderGames(state.games):'<div class="pitch-empty">NBA.com no devolvió partidos para esta fecha.</div>';
    }catch(error){state.games=[];fillGames([]);status("No se pudo consultar NBA.com: "+error.message,true);}
    finally{state.busy=false;$("nba-load").disabled=false;}
  }
  function renderGames(games){
    const rows=games.map(game=>{
      const g=gameInfo(game);
      const homeScore=g.homeScore==null?"—":g.homeScore, awayScore=g.awayScore==null?"—":g.awayScore;
      const rawTime=pick(game,["gameTimeUTC","gameEt"],"");
      let time=rawTime || pick(game,["gameCode"],"");
      if(rawTime){const parsed=new Date(rawTime);if(!Number.isNaN(parsed.getTime()))time=new Intl.DateTimeFormat("es-SV",{timeZone:"America/El_Salvador",dateStyle:"short",timeStyle:"short"}).format(parsed);}
      return '<tr><td>'+esc(g.homeName)+'</td><td>'+esc(homeScore)+" - "+esc(awayScore)+'</td><td>'+esc(g.awayName)+'</td><td>'+esc(g.status)+'</td><td>'+esc(time)+'</td></tr>';
    }).join("");
    return '<section class="research-card"><h3>Cartelera NBA</h3><div class="research-table-scroll"><table class="research-table"><thead><tr><th>Local</th><th>Marcador</th><th>Visitante</th><th>Estado</th><th>Hora / código</th></tr></thead><tbody>'+rows+'</tbody></table></div></section>';
  }
  function selectGame(){
    const id=$("nba-game").value;
    state.selected=state.games.find(game=>gameInfo(game).id===id)||null;
    $("nba-shots").disabled=!state.selected;
  }
  function fieldSVG(){
    return '<rect class="nba-court-bg" x="0" y="0" width="500" height="472"/>'+
      '<rect class="nba-court-line" x="0" y="0" width="500" height="472"/>'+
      '<line class="nba-court-line" x1="0" y1="472" x2="500" y2="472"/>'+
      '<rect class="nba-court-line" x="170" y="320" width="160" height="152"/>'+
      '<circle class="nba-court-line" cx="250" cy="320" r="60"/>'+
      '<path class="nba-court-line" d="M 30 472 A 220 220 0 0 1 470 472"/>'+
      '<path class="nba-court-line" d="M 185 420 A 65 65 0 0 0 315 420"/>'+
      '<line class="nba-court-line" x1="220" y1="435" x2="280" y2="435"/>'+
      '<circle class="nba-court-line" cx="250" cy="420" r="7"/>';
  }
  function renderShotChart(data){
    const shots=Array.isArray(data.tiros)?data.tiros:[];
    const valid=shots.filter(s=>s.LOC_X!=null&&s.LOC_X!==""&&s.LOC_Y!=null&&s.LOC_Y!==""&&Number.isFinite(Number(s.LOC_X))&&Number.isFinite(Number(s.LOC_Y))&&Number(s.LOC_X)>=-250&&Number(s.LOC_X)<=250&&Number(s.LOC_Y)>=-60&&Number(s.LOC_Y)<=430);
    if(!valid.length)return '<div class="pitch-empty">NBA.com no devolvió tiros con coordenadas para este filtro.</div>';
    const marks=valid.map(shot=>{
      const x=Number(shot.LOC_X)+250;
      const y=420-(Number(shot.LOC_Y));
      const made=Number(shot.SHOT_MADE_FLAG)===1;
      const player=shot.PLAYER_NAME||"Jugador";
      const distance=shot.SHOT_DISTANCE==null?"—":shot.SHOT_DISTANCE;
      const period=shot.PERIOD==null?"—":shot.PERIOD;
      const zone=shot.SHOT_ZONE_BASIC||shot.ACTION_TYPE||"Tiro";
      const tip=player+" · "+distance+" ft · periodo "+period+" · "+(made?"Anotado":"Fallado")+" · "+zone;
      return '<circle class="nba-shot '+(made?"made":"missed")+'" cx="'+x.toFixed(1)+'" cy="'+y.toFixed(1)+'" r="5"><title>'+esc(tip)+'</title></circle>';
    }).join("");
    const made=valid.filter(s=>Number(s.SHOT_MADE_FLAG)===1).length;
    const missed=valid.length-made;
    return '<div class="pitch-chart-wrap"><svg class="nba-court" viewBox="0 0 500 472" role="img" aria-label="Mapa de tiros NBA">'+fieldSVG()+marks+'</svg>'+
      '<div class="pitch-chart-legend"><span><i class="pitch-dot nba-made"></i>Anotados: '+made+'</span><span><i class="pitch-dot nba-missed"></i>Fallados: '+missed+'</span><span>Total: '+valid.length+' tiros · coordenadas nativas NBA</span></div></div>';
  }
  async function loadShots(){
    if(!state.selected)return;
    const info=gameInfo(state.selected);
    const teamFilter=$("nba-team-filter").value;
    const teamId=teamFilter==="home"?pick(info.home,["teamId","TEAM_ID"],0):teamFilter==="away"?pick(info.away,["teamId","TEAM_ID"],0):0;
    const playerId=$("nba-player-id").value.trim();
    if(playerId&&!/^\d+$/.test(playerId)){status("El ID del jugador debe ser numérico.",true);return;}
    const season=$("nba-season").value||"2026-27";
    $("nba-shots").disabled=true; status("Descargando tiros y coordenadas del encuentro…");
    try{
      const params=new URLSearchParams({season,team_id:String(teamId||0),player_id:String(playerId||0)});
      const data=await get("/api/v1/research/nba/games/"+encodeURIComponent(info.id)+"/shots?"+params.toString());
      $("nba-shot-output").innerHTML='<section class="research-card"><h3>Mapa de tiros · '+esc(info.homeName)+" vs "+esc(info.awayName)+'</h3><p class="research-muted">'+data.total_tiros+' registros devueltos por NBA.com. La muestra cambia según equipo, jugador y cobertura del partido.</p>'+renderShotChart(data)+'</section>';
      status("Mapa de tiros actualizado: "+data.total_tiros+" registros.");
    }catch(error){$("nba-shot-output").innerHTML="";status("No se pudo consultar el mapa de tiros: "+error.message,true);}
    finally{$("nba-shots").disabled=false;}
  }
  async function loadBoxscore(){
    if(!state.selected){status("Selecciona un partido NBA primero.",true);return;}
    const id=gameInfo(state.selected).id;
    status("Consultando box score tradicional, avanzado y tracking NBA…");
    try{
      const data=await get("/api/v1/research/nba/games/"+encodeURIComponent(id)+"/boxscore");
      const playerCols=["firstName","familyName","teamTricode","position","minutes","points","reboundsTotal","assists","steals","blocks","turnovers","plusMinusPoints"];
      const advancedCols=["firstName","familyName","teamTricode","minutes","offensiveRating","defensiveRating","netRating","assistPercentage","trueShootingPercentage","usagePercentage","pace","possessions","PIE"];
      const trackingCols=["firstName","familyName","teamTricode","minutes","speed","distance","touches","passes","assists","contestedFieldGoalsMade","defendedAtRimFieldGoalsMade"];
      $("nba-extra-output").innerHTML=
        '<section class="research-card"><h3>Box score tradicional</h3>'+renderGeneric(data.jugadores,["firstName","familyName","teamTricode","position","minutes","fieldGoalsMade","fieldGoalsAttempted","fieldGoalsPercentage","threePointersMade","threePointersAttempted","threePointersPercentage","freeThrowsMade","freeThrowsAttempted","reboundsTotal","assists","steals","blocks","turnovers","points","plusMinusPoints"])+'</section>'+
        '<section class="research-card"><h3>Box score avanzado</h3>'+renderGeneric(data.jugadores_avanzado,advancedCols)+'</section>'+
        '<section class="research-card"><h3>Player tracking</h3>'+renderGeneric(data.tracking_jugadores,trackingCols)+'</section>'+
        '<section class="research-card"><h3>Resumen por equipo</h3>'+renderGeneric(data.equipos,["teamName","teamTricode","minutes","points","reboundsTotal","assists","steals","blocks","turnovers","plusMinusPoints"])+'</section>'+
        (data.advertencias&&data.advertencias.length?'<p class="research-muted">'+esc(data.advertencias.join(" · "))+'</p>':"");
      status("Box score cargado: "+data.jugadores.length+" líneas de jugadores · "+data.advertencias.length+" advertencias opcionales.");
    }catch(error){$("nba-extra-output").innerHTML="";status("No se pudo consultar el box score: "+error.message,true);}
  }
  function renderGeneric(rows,columns){
    if(!Array.isArray(rows)||!rows.length)return '<div class="pitch-empty">Bloque no publicado por NBA.com.</div>';
    const available=columns.filter(c=>rows.some(r=>r[c]!=null));
    return '<div class="research-table-scroll"><table class="research-table"><thead><tr>'+available.map(c=>'<th>'+esc(c)+'</th>').join("")+'</tr></thead><tbody>'+
      rows.slice(0,40).map(r=>'<tr>'+available.map(c=>'<td>'+esc(r[c]??"—")+'</td>').join("")+'</tr>').join("")+'</tbody></table></div>';
  }
  async function loadPlayByPlay(){
    if(!state.selected){status("Selecciona un partido NBA primero.",true);return;}
    const id=gameInfo(state.selected).id;
    status("Consultando jugada por jugada NBA…");
    try{
      const data=await get("/api/v1/research/nba/games/"+encodeURIComponent(id)+"/play-by-play?limit=1500");
      const rows=Array.isArray(data.jugadas)?data.jugadas:[];
      const columns=["actionNumber","clock","period","teamTricode","playerName","actionType","subType","description","shotDistance","shotResult","pointsTotal","scoreHome","scoreAway"];
      $("nba-extra-output").innerHTML='<section class="research-card"><h3>Play-by-play NBA · '+esc(id)+'</h3>'+renderGeneric(rows,columns)+'</section>';
      status(rows.length+" acciones NBA devueltas.");
    }catch(error){$("nba-extra-output").innerHTML="";status("No se pudo consultar el play-by-play: "+error.message,true);}
  }
  async function loadSeasonStats(){
    const params=new URLSearchParams({
      season:$("nba-season").value||currentSeason(),
      entity:$("nba-season-entity").value,
      measure_type:$("nba-measure-type").value,
      per_mode:$("nba-per-mode").value,
      limit:"1000"
    });
    status("Consultando estadísticas NBA de temporada…");
    try{
      const data=await get("/api/v1/research/nba/season-stats?"+params.toString());
      const rows=Array.isArray(data.estadisticas)?data.estadisticas:[];
      const cols=data.entity==="player"
        ?["PLAYER_NAME","TEAM_ABBREVIATION","GP","W_PCT","MIN","PTS","REB","AST","STL","BLK","FG_PCT","FG3_PCT","FT_PCT","PLUS_MINUS"]
        :["TEAM_NAME","GP","W","L","W_PCT","MIN","PTS","REB","AST","STL","BLK","FG_PCT","FG3_PCT","PLUS_MINUS"];
      $("nba-extra-output").innerHTML='<section class="research-card"><h3>NBA · '+esc(data.entity)+' · '+esc(data.measure_type)+' · '+esc(data.per_mode)+'</h3>'+renderGeneric(rows,cols)+'</section>';
      status(rows.length+" filas de estadísticas NBA de temporada.");
    }catch(error){$("nba-extra-output").innerHTML="";status("No se pudieron consultar las estadísticas de temporada: "+error.message,true);}
  }
  function renderLogs(data){
    const rows=Array.isArray(data.registros)?data.registros:[];
    if(!rows.length)return '<div class="pitch-empty">No hay game logs para estos filtros.</div>';
    const first=rows[0],preferred=Object.keys(first).filter(k=>["GAME_DATE","TEAM_NAME","TEAM_ABBREVIATION","MATCHUP","WL","PTS","REB","AST","FGM","FGA","FG_PCT","MIN","PLAYER_NAME","PLUS_MINUS"].includes(k));
    const cols=preferred.slice(0,10);
    return '<div class="research-table-scroll"><table class="research-table"><thead><tr>'+cols.map(k=>'<th>'+esc(k.replaceAll("_"," "))+'</th>').join("")+'</tr></thead><tbody>'+
      rows.slice(0,30).map(row=>'<tr>'+cols.map(k=>'<td>'+esc(row[k]??"—")+'</td>').join("")+'</tr>').join("")+'</tbody></table></div><p class="research-muted">Mostrando '+Math.min(rows.length,30)+' de '+rows.length+' registros recibidos.</p>';
  }
  async function loadTeams(){
    if(!$("nba-team-roster-select"))return;
    try{
      const data=await get("/api/v1/research/nba/teams");
      const rows=Array.isArray(data.equipos)?data.equipos:[];
      $("nba-team-roster-select").innerHTML='<option value="">Selecciona equipo NBA</option>'+rows.map(t=>
        '<option value="'+esc(t.id)+'">'+esc(t.nombre+" · "+t.abreviatura)+'</option>').join("");
    }catch(error){
      $("nba-team-roster-select").innerHTML='<option value="">No se pudo cargar el catálogo</option>';
      status("No se pudo cargar el catálogo NBA: "+error.message,true);
    }
  }
  function renderRoster(data){
    const rows=Array.isArray(data.jugadores)?data.jugadores:[];
    if(!rows.length)return '<div class="pitch-empty">NBA.com no devolvió jugadores para el equipo y temporada seleccionados.</div>';
    const cols=["PLAYER","PLAYER_ID","NUM","POSITION","HEIGHT","WEIGHT","AGE","EXP","SCHOOL"];
    return '<div class="research-table-scroll"><table class="research-table"><thead><tr>'+cols.map(k=>'<th>'+esc(k)+'</th>').join("")+'</tr></thead><tbody>'+
      rows.map(player=>'<tr>'+cols.map(k=>'<td>'+esc(player[k]??"—")+'</td>').join("")+'</tr>').join("")+
      '</tbody></table></div>';
  }
  async function loadRoster(){
    const teamId=$("nba-team-roster-select").value, season=$("nba-season").value||"2026-27";
    if(!teamId){status("Selecciona un equipo para consultar su roster.",true);return;}
    $("nba-roster").disabled=true;status("Consultando roster actual para "+season+"…");
    try{
      const data=await get("/api/v1/research/nba/teams/"+encodeURIComponent(teamId)+"/roster?season="+encodeURIComponent(season));
      $("nba-roster-output").innerHTML='<section class="research-card"><h3>Plantilla NBA · '+esc(season)+'</h3>'+renderRoster(data)+'</section>';
      status(data.total_jugadores+" jugadores devueltos por NBA.com para la temporada "+season+".");
    }catch(error){$("nba-roster-output").innerHTML="";status("No se pudo cargar el roster: "+error.message,true);}
    finally{$("nba-roster").disabled=false;}
  }
  async function loadLogs(){
    const season=$("nba-season").value||"2026-27", entity=$("nba-log-entity").value;
    $("nba-logs").disabled=true;status("Consultando historial NBA…");
    try{
      const data=await get("/api/v1/research/nba/logs?"+new URLSearchParams({season,entity,limit:"200"}).toString());
      $("nba-log-output").innerHTML='<section class="research-card"><h3>Historial NBA · '+esc(season)+'</h3>'+renderLogs(data)+'</section>';
      status("Historial cargado: "+data.total_registros+" registros.");
    }catch(error){$("nba-log-output").innerHTML="";status("No se pudo consultar el historial: "+error.message,true);}
    finally{$("nba-logs").disabled=false;}
  }
  function init(){
    if(!$("nba-research")||!window.fetch)return;
    $("nba-date").value=localDate();
    $("nba-season").value=currentSeason();
    $("nba-load").addEventListener("click",loadScoreboard);
    $("nba-game").addEventListener("change",selectGame);
    $("nba-shots").addEventListener("click",loadShots);
    $("nba-boxscore").addEventListener("click",loadBoxscore);
    $("nba-pbp").addEventListener("click",loadPlayByPlay);
    $("nba-season-stats").addEventListener("click",loadSeasonStats);
    $("nba-logs").addEventListener("click",loadLogs);
    $("nba-roster").addEventListener("click",loadRoster);
    $("nba-log-entity").addEventListener("change",()=>{ $("nba-log-label").textContent=$("nba-log-entity").value==="P"?"ID jugador / Player logs":"Equipo / Team logs";});
    loadTeams();
  }
  if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",init);else init();
})();
