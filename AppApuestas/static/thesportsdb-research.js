/* Fuente auxiliar TheSportsDB. No sustituye PitchAPI. */
(function(){
  "use strict";
  const $=id=>document.getElementById(id);
  const state={events:[],selected:null,busy:false,loaded:false};
  function esc(value){return String(value==null?"":value).replace(/[&<>"']/g,ch=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));}
  async function get(path){
    const response=await fetch(path,{cache:"no-store"});
    let data={};try{data=await response.json();}catch(_){}
    if(!response.ok){const d=data.detail;throw new Error(typeof d==="string"?d:d&&(d.mensaje||d.codigo)||("HTTP "+response.status));}
    return data;
  }
  function today(){
    const parts=new Intl.DateTimeFormat("en-CA",{timeZone:"America/El_Salvador",year:"numeric",month:"2-digit",day:"2-digit"}).formatToParts(new Date());
    const d={};parts.forEach(p=>{if(p.type!=="literal")d[p.type]=p.value;});
    return d.year+"-"+d.month+"-"+d.day;
  }
  function status(text,error){
    const el=$("tsdb-status");el.textContent=text;el.className="research-status"+(error?" error":"");
  }
  function eventLabel(e){
    const score=e.score_home==null||e.score_away==null?"":" · "+e.score_home+"-"+e.score_away;
    return (e.time_local||"Hora pendiente")+" · "+(e.home_team?.name||"Local")+" vs "+(e.away_team?.name||"Visitante")+score+" · "+(e.league||"Liga");
  }
  async function loadEvents(){
    if(state.busy)return;
    const date=$("tsdb-date").value;if(!date){status("Selecciona una fecha válida.",true);return;}
    state.busy=true;$("tsdb-load").disabled=true;$("tsdb-event").disabled=true;$("tsdb-analyze").disabled=true;$("tsdb-output").innerHTML="";
    status("Consultando cartelera de TheSportsDB…");
    try{
      const data=await get("/api/v1/research/thesportsdb/events?fecha="+encodeURIComponent(date));
      state.events=Array.isArray(data.eventos)?data.eventos:[];
      const select=$("tsdb-event");
      select.innerHTML='<option value="">Selecciona un partido</option>'+state.events.map(e=>'<option value="'+esc(e.id)+'">'+esc(eventLabel(e))+'</option>').join("");
      select.disabled=!state.events.length;
      if(state.events.length){select.value=state.events[0].id;state.selected=state.events[0];$("tsdb-analyze").disabled=false;status(state.events.length+" partidos encontrados en la cobertura de TheSportsDB.");}
      else{state.selected=null;status("No hay partidos publicados por TheSportsDB para esa fecha. Esto no significa que no existan partidos.");}
      state.loaded=true;
    }catch(err){state.loaded=false;status("No fue posible consultar TheSportsDB: "+err.message,true);}
    finally{state.busy=false;$("tsdb-load").disabled=false;}
  }
  function selectEvent(){
    state.selected=state.events.find(e=>String(e.id)===$("tsdb-event").value)||null;
    $("tsdb-analyze").disabled=!state.selected;$("tsdb-output").innerHTML="";
  }
  function lineupTable(rows,side){
    const subset=rows.filter(x=>x.side===side);
    if(!subset.length)return '<p class="pitch-empty">TheSportsDB no publicó alineación para este equipo.</p>';
    const starters=subset.filter(x=>x.starter),subs=subset.filter(x=>!x.starter);
    function table(list){
      if(!list.length)return '<p class="research-muted">Sin registros.</p>';
      return '<div class="research-table-scroll"><table class="research-table"><thead><tr><th>#</th><th>Jugador</th><th>Posición</th><th>Tipo</th></tr></thead><tbody>'+list.map(p=>'<tr><td>'+esc(p.number||"—")+'</td><td>'+esc(p.player)+'</td><td>'+esc(p.position||"—")+'</td><td>'+ (p.starter?"Titular":"Suplente")+'</td></tr>').join("")+'</tbody></table></div>';
    }
    return '<h4>Titulares</h4>'+table(starters)+'<h4>Suplentes registrados</h4>'+table(subs);
  }
  function statsTable(rows){
    if(!rows.length)return '<p class="pitch-empty">Estadísticas no publicadas para este partido.</p>';
    return '<div class="research-table-scroll"><table class="research-table"><thead><tr><th>Indicador</th><th>Local</th><th>Visitante</th></tr></thead><tbody>'+rows.map(s=>'<tr><td>'+esc(s.name)+'</td><td>'+esc(s.home??"—")+'</td><td>'+esc(s.away??"—")+'</td></tr>').join("")+'</tbody></table></div>';
  }
  function rosterTable(roster){
    if(!roster||!roster.length)return '<p class="pitch-empty">No hay fichas activas publicadas para este club.</p>';
    return '<div class="research-table-scroll"><table class="research-table"><thead><tr><th>#</th><th>Jugador</th><th>Posición</th><th>Nacionalidad</th></tr></thead><tbody>'+roster.map(p=>'<tr><td>'+esc(p.number||"—")+'</td><td>'+esc(p.name)+'</td><td>'+esc(p.position||"—")+'</td><td>'+esc(p.nationality||"—")+'</td></tr>').join("")+'</tbody></table></div>';
  }
  function render(data){
    const e=state.selected||{},alineaciones=Array.isArray(data.alineaciones)?data.alineaciones:[];
    const plantillas=data.plantillas||{},stats=Array.isArray(data.estadisticas)?data.estadisticas:[];
    const home=e.home_team?.name||"Local",away=e.away_team?.name||"Visitante";
    let html='<section class="research-card"><div class="pitch-research-statusline"><span class="pitch-chip">'+esc(e.status_text||"Estado no publicado")+'</span><span class="pitch-chip">'+esc(e.league||"Fútbol")+'</span></div><h3>'+esc(home)+' '+esc(e.score_home??"—")+' - '+esc(e.score_away??"—")+' '+esc(away)+'</h3><p class="pitch-data-note">'+esc(e.date_local||e.date||"Fecha no disponible")+' · '+esc(e.venue||"Estadio no publicado")+'</p></section>';
    html+='<section class="research-card"><h3>Estadísticas del partido</h3>'+statsTable(stats)+'</section>';
    html+='<section class="research-card"><h3>Alineaciones registradas</h3><div class="pitch-two-col"><div class="pitch-subcard"><h4>'+esc(home)+'</h4>'+lineupTable(alineaciones,"home")+'</div><div class="pitch-subcard"><h4>'+esc(away)+'</h4>'+lineupTable(alineaciones,"away")+'</div></div></section>';
    html+='<section class="research-card"><h3>Muestra de jugadores activos</h3><p class="pitch-data-note">La API gratuita limita esta muestra; no es la plantilla completa.</p><div class="pitch-two-col"><div class="pitch-subcard"><h4>'+esc(home)+'</h4>'+rosterTable(plantillas.home?.jugadores||[])+'</div><div class="pitch-subcard"><h4>'+esc(away)+'</h4>'+rosterTable(plantillas.away?.jugadores||[])+'</div></div></section>';
    if(Array.isArray(data.timeline)&&data.timeline.length){
      html+='<section class="research-card"><h3>Eventos registrados</h3><div class="research-table-scroll"><table class="research-table"><thead><tr><th>Minuto</th><th>Evento</th><th>Jugador</th><th>Equipo</th></tr></thead><tbody>'+data.timeline.map(t=>'<tr><td>'+esc(t.strTimeline||t.strTime||"—")+'</td><td>'+esc(t.strEvent||t.strType||"—")+'</td><td>'+esc(t.strPlayer||"—")+'</td><td>'+esc(t.strTeam||"—")+'</td></tr>').join("")+'</tbody></table></div></section>';
    }
    html+='<p class="research-muted">'+esc(data.advertencia||"Fuente auxiliar; verificar cobertura y actualidad.")+'</p>';
    $("tsdb-output").innerHTML=html;status("Consulta completada. Contrasta los datos con PitchAPI antes de utilizarlos.");
  }
  async function analyse(){
    if(!state.selected)return;
    const e=state.selected,b=$("tsdb-analyze"),old=b.textContent;b.disabled=true;b.textContent="Consultando…";$("tsdb-output").innerHTML="";
    status("Consultando evento, estadísticas, alineaciones y muestras de jugadores…");
    const url="/api/v1/research/thesportsdb/events/"+encodeURIComponent(e.id)+"/analysis?home_team_id="+encodeURIComponent(e.home_team.id)+"&away_team_id="+encodeURIComponent(e.away_team.id);
    try{const data=await get(url);render(data);}catch(err){status("No se pudo completar la consulta: "+err.message,true);}
    finally{b.disabled=false;b.textContent=old;}
  }
  function init(){
    if(!$("tsdb-date"))return;
    $("tsdb-date").value=today();
    $("tsdb-load").addEventListener("click",loadEvents);
    $("tsdb-event").addEventListener("change",selectEvent);
    $("tsdb-analyze").addEventListener("click",analyse);
    $("research-toggle").addEventListener("click",()=>{if(!$("research-view").hidden&&!state.loaded)loadEvents();});
    $("tsdb-date").addEventListener("change",()=>{state.loaded=false;state.events=[];state.selected=null;$("tsdb-event").innerHTML='<option value="">Pulsa Buscar partidos</option>';$("tsdb-event").disabled=true;$("tsdb-analyze").disabled=true;$("tsdb-output").innerHTML="";});
  }
  if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",init);else init();
})();
