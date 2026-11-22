/* Explorador ESPN público: fuente complementaria y experimental. */
(function(){
  "use strict";
  const $ = id => document.getElementById(id);
  const state = { events: [], selected: null, loaded: false, busy: false };
  function esc(value){
    return String(value == null ? "" : value).replace(/[&<>"']/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
  }
  async function get(path){
    const response = await fetch(path,{cache:"no-store"});
    let data = {}; try { data = await response.json(); } catch (_) {}
    if(!response.ok){
      const detail = data.detail;
      throw new Error(typeof detail === "string" ? detail : detail && (detail.mensaje || detail.code) || ("HTTP "+response.status));
    }
    return data;
  }
  function setStatus(message,error){
    const el=$("espn-status"); if(!el)return;
    el.textContent=message; el.className="research-status"+(error?" error":"");
  }
  function todayElSalvador(){
    const parts = new Intl.DateTimeFormat("en-CA",{timeZone:"America/El_Salvador",year:"numeric",month:"2-digit",day:"2-digit"}).formatToParts(new Date());
    const values={}; parts.forEach(p=>{if(p.type!=="literal")values[p.type]=p.value;});
    return values.year+"-"+values.month+"-"+values.day;
  }
  function matchDate(value){
    if(!value)return "Horario no disponible";
    const d=new Date(value); if(Number.isNaN(d.getTime()))return String(value);
    return new Intl.DateTimeFormat("es-SV",{timeZone:"America/El_Salvador",day:"2-digit",month:"short",hour:"2-digit",minute:"2-digit"}).format(d);
  }
  function eventLabel(item){
    const home=item.home_team && item.home_team.name || "Local";
    const away=item.away_team && item.away_team.name || "Visitante";
    const status=item.status==="finished"?"FINAL "+(item.score_home ?? "—")+"-"+(item.score_away ?? "—"):item.status==="live"?"EN VIVO": "PROGRAMADO";
    return matchDate(item.date)+" · "+home+" vs "+away+" · "+status;
  }
  async function loadScoreboard(){
    if(state.busy)return;
    const league=$("espn-league").value, day=$("espn-date").value;
    if(!day){setStatus("Selecciona una fecha válida.",true);return;}
    state.busy=true; $("espn-load").disabled=true; $("espn-match").disabled=true;
    $("espn-analyze").disabled=true; $("espn-output").innerHTML="";
    setStatus("Consultando cartelera pública ESPN…");
    try{
      const data=await get("/api/v1/research/espn/scoreboard?league="+encodeURIComponent(league)+"&fecha="+encodeURIComponent(day));
      state.events=Array.isArray(data.eventos)?data.eventos:[];
      state.events.sort((a,b)=>{
        const rank=x=>x.status==="live"?0:x.status==="scheduled"?1:2;
        return rank(a)-rank(b)||(Date.parse(a.date||"")||0)-(Date.parse(b.date||"")||0);
      });
      const select=$("espn-match");
      select.innerHTML='<option value="">Selecciona un partido</option>'+state.events.map(item=>'<option value="'+esc(item.id)+'">'+esc(eventLabel(item))+'</option>').join("");
      select.disabled=state.events.length===0;
      if(state.events.length){
        select.value=state.events[0].id; state.selected=state.events[0]; $("espn-analyze").disabled=false;
        setStatus(state.events.length+" partidos encontrados · "+esc(data.liga||league)+". Selecciona uno para consultar sus estadísticas y plantillas.");
      }else{
        state.selected=null; setStatus("ESPN no devolvió partidos para esa liga y fecha. Prueba otra fecha o competición.");
      }
      state.loaded=true;
    }catch(error){state.loaded=false;setStatus("No se pudo consultar ESPN: "+error.message,true);}
    finally{state.busy=false;$("espn-load").disabled=false;}
  }
  function selectedEvent(){
    state.selected=state.events.find(item=>String(item.id)===$("espn-match").value)||null;
    $("espn-analyze").disabled=!state.selected;
    $("espn-output").innerHTML="";
  }
  function number(value){return value==null||value===""?"—":esc(value);}
  function statTable(item){
    const stats=Array.isArray(item.statistics)?item.statistics:[];
    if(!stats.length)return '<div class="pitch-empty">Estadísticas de partido todavía no publicadas.</div>';
    const priority=["possessionPct","totalShots","shotsOnTarget","wonCorners","foulsCommitted","yellowCards","redCards","offsides","saves","totalPasses","accuratePasses","effectiveTackles","interceptions"];
    stats.sort((a,b)=>priority.indexOf(a.key)-priority.indexOf(b.key));
    return '<div class="research-table-scroll"><table class="research-table"><thead><tr><th>Indicador</th><th>Dato</th></tr></thead><tbody>'+stats.map(s=>'<tr><td>'+esc(s.label||s.key)+'</td><td>'+number(s.value)+'</td></tr>').join("")+'</tbody></table></div>';
  }
  function rosterTable(roster){
    const players=Array.isArray(roster && roster.jugadores)?roster.jugadores:[];
    if(!players.length)return '<div class="pitch-empty">'+esc(roster && roster.error || "La fuente no publicó plantilla para este equipo.")+'</div>';
    const rows=players.map(p=>{
      const s=p.stats||{};
      const injury=p.injured?'<span class="pitch-chip provisional">LESIÓN REGISTRADA</span>':"";
      return '<tr><td>'+number(p.jersey)+'</td><td><strong>'+esc(p.name)+'</strong><br><small>'+esc(p.nationality||"")+'</small></td><td>'+esc(p.position||"—")+'</td><td>'+number(p.age)+'</td><td>'+number(s.appearances)+'</td><td>'+number(s.goals)+'</td><td>'+number(s.assists)+'</td><td>'+number(s.shots)+'</td><td>'+number(s.shots_on_target)+'</td><td>'+injury+'</td></tr>';
    }).join("");
    return '<p class="pitch-data-note">'+esc(roster.total_jugadores||players.length)+' futbolistas · '+esc(roster.season||"Temporada reportada por ESPN")+'</p><div class="research-table-scroll"><table class="research-table"><thead><tr><th>#</th><th>Jugador</th><th>Pos.</th><th>Edad</th><th>APP</th><th>G</th><th>A</th><th>REM</th><th>AP</th><th>Estado</th></tr></thead><tbody>'+rows+'</tbody></table></div>';
  }
  function renderAnalysis(data){
    const match=state.selected||{};
    const teams=Array.isArray(data.estadisticas_equipo)?data.estadisticas_equipo:[];
    const rosters=data.plantillas||{};
    const homeName=match.home_team && match.home_team.name || "Local";
    const awayName=match.away_team && match.away_team.name || "Visitante";
    let html='<section class="research-card"><div class="pitch-research-statusline"><span class="pitch-chip">'+esc(match.status==="live"?"EN VIVO":match.status==="finished"?"FINALIZADO":"PROGRAMADO")+'</span><span class="pitch-chip">ESPN · '+esc(match.league||"Fútbol")+'</span><span class="pitch-chip">'+esc(match.date||"Fecha no disponible")+'</span></div><h3>'+esc(homeName)+' '+esc(match.score_home==null?"—":match.score_home)+' - '+esc(match.score_away==null?"—":match.score_away)+' '+esc(awayName)+'</h3><p class="pitch-data-note">Estadio: '+esc(match.venue||"No publicado")+'</p></section>';
    html+='<section class="research-card"><h3>Estadísticas del partido</h3><div class="pitch-two-col">';
    for(const side of ["home","away"]){
      const team=teams.find(t=>t.side===side);
      html+='<div class="pitch-subcard"><h4>'+esc(side==="home"?homeName:awayName)+'</h4>'+(team?statTable(team):'<div class="pitch-empty">No hay boxscore publicado para este partido.</div>')+'</div>';
    }
    html+='</div></section>';
    html+='<section class="research-card"><h3>Plantillas actuales de los clubes</h3><p class="pitch-data-note">Esto es plantilla del equipo y estadísticas acumuladas de temporada; no confirma quién será titular ni quién está disponible para jugar.</p><div class="pitch-two-col">';
    html+='<div class="pitch-subcard"><h4>'+esc(homeName)+'</h4>'+rosterTable(rosters.home||{})+'</div>';
    html+='<div class="pitch-subcard"><h4>'+esc(awayName)+'</h4>'+rosterTable(rosters.away||{})+'</div></div></section>';
    const leaders=Array.isArray(data.lideres_del_partido)?data.lideres_del_partido:[];
    if(leaders.length){
      html+='<section class="research-card"><h3>Líderes del partido</h3><div class="research-table-scroll"><table class="research-table"><thead><tr><th>Equipo</th><th>Indicador</th><th>Jugador</th><th>Valor</th></tr></thead><tbody>'+leaders.map(x=>'<tr><td>'+esc(x.team)+'</td><td>'+esc(x.category)+'</td><td>'+esc(x.player)+'</td><td>'+esc(x.value)+'</td></tr>').join("")+'</tbody></table></div></section>';
    }
    if(Array.isArray(data.advertencias)&&data.advertencias.length)html+='<p class="research-muted">'+esc(data.advertencias.join(" · "))+'</p>';
    $("espn-output").innerHTML=html;
    setStatus("Consulta completada. Plantillas y estadísticas proceden del endpoint público de ESPN; verifica su actualidad antes de usar.");
  }
  async function analyse(){
    const item=state.selected; if(!item)return;
    const button=$("espn-analyze"), old=button.textContent;
    button.disabled=true;button.textContent="Consultando…";setStatus("Consultando resumen del partido y plantillas de ambos clubes…");$("espn-output").innerHTML="";
    const path="/api/v1/research/espn/matches/"+encodeURIComponent(item.id)+"/analysis?league="+encodeURIComponent($("espn-league").value)+"&home_team_id="+encodeURIComponent(item.home_team.id)+"&away_team_id="+encodeURIComponent(item.away_team.id);
    try{const data=await get(path);renderAnalysis(data);}
    catch(error){setStatus("No se pudo completar el análisis ESPN: "+error.message,true);}
    finally{button.disabled=false;button.textContent=old;}
  }
  function init(){
    if(!$("espn-league"))return;
    $("espn-date").value=todayElSalvador();
    $("espn-load").addEventListener("click",loadScoreboard);
    $("espn-match").addEventListener("change",selectedEvent);
    $("espn-analyze").addEventListener("click",analyse);
    $("research-toggle").addEventListener("click",()=>{
      if(!$("research-view").hidden&&!state.loaded)loadScoreboard();
    });
    const dateField=$("espn-date");
    dateField.addEventListener("change",()=>{state.loaded=false;state.events=[];state.selected=null;$("espn-match").innerHTML='<option value="">Pulsa Buscar partidos</option>';$("espn-match").disabled=true;$("espn-analyze").disabled=true;$("espn-output").innerHTML="";});
  }
  if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",init);else init();
})();
