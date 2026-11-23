/* NFL + MLB Research (optional data adapters, source and terms reported clearly). */
(function(){
  "use strict";
  const $=id=>document.getElementById(id);
  const state={nflGames:[],selectedNflGame:null};
  function esc(v){return String(v==null?"":v).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));}
  function val(row,keys, fallback){for(const k of keys){if(row&&row[k]!=null&&row[k]!=="")return row[k];}return fallback;}
  async function get(path){
    const r=await fetch(path,{cache:"no-store"});let d={};try{d=await r.json();}catch(_){}
    if(!r.ok){const e=d.detail;throw new Error(typeof e==="string"?e:e&&(e.mensaje||e.codigo)||("HTTP "+r.status));}
    return d;
  }
  function status(msg,error){const node=$("pro-sports-status");if(!node)return;node.textContent=msg;node.className="research-status"+(error?" error":"");}
  function table(rows,columns,limit){
    if(!Array.isArray(rows)||!rows.length)return '<div class="pitch-empty">No hay registros disponibles con estos filtros.</div>';
    const cols=columns.filter(c=>rows.some(r=>r[c]!=null));
    if(!cols.length)return '<div class="pitch-empty">La fuente no devolvió campos de esta tabla.</div>';
    return '<div class="research-table-scroll"><table class="research-table"><thead><tr>'+cols.map(c=>'<th>'+esc(c.replaceAll("_"," "))+'</th>').join("")+'</tr></thead><tbody>'+
      rows.slice(0,limit||30).map(r=>'<tr>'+cols.map(c=>'<td>'+esc(r[c]??"—")+'</td>').join("")+'</tr>').join("")+'</tbody></table></div><p class="research-muted">Mostrando '+Math.min(rows.length,limit||30)+' de '+rows.length+' registros devueltos.</p>';
  }
  async function loadProviderStatus(){
    try{
      const [nfl,mlb]=await Promise.all([
        get("/api/v1/research/nfl/status"),get("/api/v1/research/mlb/status")
      ]);
      $("nfl-source-status").textContent=nfl.instalado?"nflreadpy instalado":"nflreadpy no instalado · requiere instalación opcional";
      $("mlb-source-status").textContent=mlb.instalado?"pybaseball instalado":"pybaseball no instalado · requiere instalación opcional";
    }catch(error){status("No se pudo verificar el estado de las fuentes: "+error.message,true);}
  }
  function nflParams(){
    return new URLSearchParams({season:$("nfl-season").value||"2026",...( $("nfl-week").value?{week:$("nfl-week").value}:{})});
  }
  function dynamicTable(rows,limit){
    if(!Array.isArray(rows)||!rows.length)return '<div class="pitch-empty">No hay registros para estos filtros.</div>';
    const columns=Object.keys(rows[0]).slice(0,16);
    return table(rows,columns,limit||35);
  }
  async function loadNFLStats(){
    const params=nflParams();
    params.set("entity",$("nfl-stats-entity").value);
    params.set("summary_level",$("nfl-stats-level").value);
    params.set("limit","2500");
    status("Consultando estadísticas NFL por jugador/equipo…");
    try{
      const data=await get("/api/v1/research/nfl/statistics?"+params.toString());
      $("nfl-output").innerHTML='<section class="research-card"><h3>Estadísticas NFL · '+esc(data.entity)+' · '+esc(data.summary_level)+'</h3>'+dynamicTable(data.estadisticas,35)+'</section>';
      status(data.total_registros+" registros estadísticos NFL devueltos.");
    }catch(error){status("NFL estadísticas: "+error.message,true);}
  }
  async function loadNFLSnapCounts(){
    const params=nflParams();params.delete("week");params.set("limit","3000");
    status("Consultando snaps NFL…");
    try{
      const data=await get("/api/v1/research/nfl/snap-counts?"+params.toString());
      $("nfl-output").innerHTML='<section class="research-card"><h3>Snap counts NFL · '+esc(data.season)+'</h3>'+dynamicTable(data.snap_counts,40)+'</section>';
      status(data.total_registros+" registros de snap counts devueltos.");
    }catch(error){status("NFL snaps: "+error.message,true);}
  }
  async function loadNFLNextGen(){
    const params=nflParams();params.delete("week");params.set("stat_type",$("nfl-nextgen-type").value);params.set("limit","3000");
    status("Consultando Next Gen Stats NFL…");
    try{
      const data=await get("/api/v1/research/nfl/nextgen-stats?"+params.toString());
      $("nfl-output").innerHTML='<section class="research-card"><h3>Next Gen Stats · '+esc(data.stat_type)+'</h3>'+dynamicTable(data.estadisticas,40)+'</section>';
      status(data.total_registros+" registros de Next Gen Stats devueltos.");
    }catch(error){status("NFL Next Gen Stats: "+error.message,true);}
  }
  async function loadNFLPFR(){
    const params=nflParams();params.delete("week");
    params.set("stat_type",$("nfl-pfr-type").value);params.set("summary_level",$("nfl-pfr-level").value);params.set("limit","3000");
    status("Consultando métricas avanzadas de Pro Football Reference…");
    try{
      const data=await get("/api/v1/research/nfl/pfr-advanced?"+params.toString());
      $("nfl-output").innerHTML='<section class="research-card"><h3>PFR advanced · '+esc(data.stat_type)+' · '+esc(data.summary_level)+'</h3>'+dynamicTable(data.estadisticas,40)+'</section>';
      status(data.total_registros+" registros de métricas avanzadas devueltos.");
    }catch(error){status("NFL PFR Advanced: "+error.message,true);}
  }
  async function loadNFLschedule(){
    status("Consultando calendario NFL…");
    try{
      const data=await get("/api/v1/research/nfl/schedule?"+nflParams().toString());
      state.nflGames=Array.isArray(data.partidos)?data.partidos:[];
      const select=$("nfl-game");
      select.innerHTML='<option value="">Selecciona partido para play-by-play</option>'+state.nflGames.map(g=>{
        const id=val(g,["game_id","GAME_ID"],"");
        const home=val(g,["home_team","home_team_name"],"Home"),away=val(g,["away_team","away_team_name"],"Away");
        return '<option value="'+esc(id)+'">'+esc((g.week?"W"+g.week+" · ":"")+away+" @ "+home+" · "+val(g,["gameday","game_date"],""))+'</option>';
      }).join("");
      $("nfl-pbp").disabled=!state.nflGames.length;
      $("nfl-output").innerHTML='<section class="research-card"><h3>Calendario NFL · '+esc(data.season)+'</h3>'+table(data.partidos,["week","gameday","game_id","away_team","home_team","away_score","home_score","result","game_type","roof","surface","spread_line","total_line"],40)+'</section>';
      status(state.nflGames.length+" partidos encontrados en calendario NFL.");
    }catch(error){$("nfl-output").innerHTML="";status("NFL: "+error.message,true);}
  }
  async function loadNFLpbp(){
    const game=$("nfl-game").value,season=$("nfl-season").value||"2026";
    if(!game){status("Selecciona un partido NFL.",true);return;}
    status("Consultando play-by-play del partido NFL…");
    try{
      const data=await get("/api/v1/research/nfl/games/"+encodeURIComponent(game)+"/pbp?"+new URLSearchParams({season,limit:"1000"}).toString());
      $("nfl-output").innerHTML='<section class="research-card"><h3>Play-by-play · '+esc(game)+'</h3>'+table(data.jugadas,["play_id","qtr","time","down","ydstogo","posteam","defteam","play_type","desc","yards_gained","epa","wpa","touchdown","interception","fumble"],50)+'</section>';
      status(data.total_jugadas+" jugadas devueltas para "+game+".");
    }catch(error){status("NFL PBP: "+error.message,true);}
  }
  async function loadNFLrosters(){
    const params=nflParams();params.set("limit","1500");
    status("Consultando plantillas NFL de temporada/semana…");
    try{
      const data=await get("/api/v1/research/nfl/rosters?"+params.toString());
      $("nfl-output").innerHTML='<section class="research-card"><h3>Rosters semanales NFL</h3>'+table(data.roster,["season","week","team","player_name","position","status","jersey_number","entry_year","rookie_year","birth_date","college"],60)+'</section>';
      status(data.total_jugadores+" filas de roster publicadas.");
    }catch(error){status("NFL rosters: "+error.message,true);}
  }
  async function loadNFLinjuries(){
    const season=$("nfl-season").value||"2026";
    status("Consultando informes de lesiones NFL…");
    try{
      const data=await get("/api/v1/research/nfl/injuries?"+new URLSearchParams({season,limit:"1500"}).toString());
      $("nfl-output").innerHTML='<section class="research-card"><h3>Lesiones NFL · '+esc(season)+'</h3>'+table(data.lesiones,["season","week","team","player_name","position","report_status","practice_status","date_modified","report_primary_injury","report_secondary_injury"],60)+'</section>';
      status(data.total_registros+" registros de lesiones devueltos.");
    }catch(error){status("NFL lesiones: "+error.message,true);}
  }
  async function loadNFLdepth(){
    const season=$("nfl-season").value||"2026";
    status("Consultando depth charts NFL…");
    try{
      const data=await get("/api/v1/research/nfl/depth-charts?"+new URLSearchParams({season,limit:"1500"}).toString());
      $("nfl-output").innerHTML='<section class="research-card"><h3>Depth charts NFL · '+esc(season)+'</h3>'+table(data.depth_charts,["season","team","week","position","depth_position","full_name","gsis_id","jersey_number"],60)+'</section>';
      status(data.total_registros+" registros de profundidad devueltos.");
    }catch(error){status("NFL depth charts: "+error.message,true);}
  }
  function mlbParams(){
    const p=new URLSearchParams({start_date:$("mlb-start").value,end_date:$("mlb-end").value,limit:"2000"});
    const batter=$("mlb-batter-id").value.trim(),pitcher=$("mlb-pitcher-id").value.trim();
    if(batter)p.set("batter_id",batter);if(pitcher)p.set("pitcher_id",pitcher);
    return p;
  }
  function pitchChart(rows){
    const valid=rows.filter(r=>Number.isFinite(Number(r.plate_x))&&Number.isFinite(Number(r.plate_z)));
    if(!valid.length)return '<div class="pitch-empty">Statcast no devolvió coordenadas de ubicación de lanzamiento para el filtro.</div>';
    const dots=valid.map(r=>{
      const x=Math.max(30,Math.min(370,200+Number(r.plate_x)*48));
      const y=Math.max(30,Math.min(370,350-Number(r.plate_z)*55));
      const desc=String(r.description||"");
      const strike=/strike|foul|in_play|hit_into_play/i.test(desc);
      const tip=(r.pitch_name||r.pitch_type||"Pitcheo")+" · "+(r.release_speed==null?"—":r.release_speed+" mph")+" · "+desc;
      return '<circle class="mlb-pitch-dot '+(strike?"strike":"ball")+'" cx="'+x.toFixed(1)+'" cy="'+y.toFixed(1)+'" r="5"><title>'+esc(tip)+'</title></circle>';
    }).join("");
    return '<div class="pitch-chart-wrap"><svg class="mlb-zone" viewBox="0 0 400 400" role="img" aria-label="Ubicación de lanzamientos Statcast"><rect class="mlb-zone-bg" x="0" y="0" width="400" height="400"/><rect class="mlb-zone-line" x="128" y="100" width="144" height="165"/><line class="mlb-zone-line" x1="128" y1="182" x2="272" y2="182"/><line class="mlb-zone-line" x1="200" y1="100" x2="200" y2="265"/><path class="mlb-zone-line" d="M 155 280 L 200 310 L 245 280"/>'+dots+'</svg><div class="pitch-chart-legend"><span><i class="pitch-dot mlb-strike"></i>Strike / foul / in-play</span><span><i class="pitch-dot mlb-ball"></i>Otros lanzamientos</span><span>'+valid.length+' ubicaciones con plate_x/plate_z</span></div></div>';
  }
  async function loadMLB(){
    if(!$("mlb-start").value||!$("mlb-end").value){status("Selecciona las fechas inicial y final de Statcast.",true);return;}
    const batter=$("mlb-batter-id").value.trim(),pitcher=$("mlb-pitcher-id").value.trim();
    if(batter&&pitcher){status("Filtra por bateador o lanzador, no ambos al mismo tiempo.",true);return;}
    status("Consultando Statcast MLB…");
    try{
      const data=await get("/api/v1/research/mlb/statcast?"+mlbParams().toString());
      const rows=Array.isArray(data.lanzamientos)?data.lanzamientos:[];
      const speeds=rows.map(r=>Number(r.release_speed)).filter(Number.isFinite);
      const exit=rows.map(r=>Number(r.launch_speed)).filter(Number.isFinite);
      const avg=a=>a.length?(a.reduce((x,y)=>x+y,0)/a.length).toFixed(1):"—";
      $("mlb-output").innerHTML='<section class="research-card"><h3>Statcast · '+esc(data.fecha_inicio)+' al '+esc(data.fecha_fin)+'</h3><div class="pitch-analysis-grid"><div class="pitch-kpi"><small>Lanzamientos</small><strong>'+rows.length+'</strong><em>registros devueltos</em></div><div class="pitch-kpi"><small>Velocidad media</small><strong>'+avg(speeds)+'</strong><em>mph</em></div><div class="pitch-kpi"><small>Exit velocity media</small><strong>'+avg(exit)+'</strong><em>mph</em></div><div class="pitch-kpi"><small>Ventana</small><strong>'+esc((data.fecha_fin===data.fecha_inicio)?"1":"varios")+'</strong><em>días seleccionados</em></div></div><h4>Ubicación de lanzamientos</h4>'+pitchChart(rows)+'<h4>Eventos recientes</h4>'+table(rows,["game_date","player_name","pitch_name","release_speed","release_spin_rate","launch_speed","launch_angle","events","description","inning","balls","strikes"],30)+'<p class="research-muted">Los registros provienen de Statcast. La ventana está limitada a tres días por consulta.</p></section>';
      status(rows.length+" registros Statcast devueltos.");
    }catch(error){$("mlb-output").innerHTML="";status("MLB Statcast: "+error.message,true);}
  }
  function init(){
    if(!$("pro-sports-research"))return;
    const today=new Date(),iso=new Intl.DateTimeFormat("en-CA",{timeZone:"America/El_Salvador"}).format(today);
    $("mlb-start").value=iso;$("mlb-end").value=iso;
    $("nfl-load-schedule").addEventListener("click",loadNFLschedule);
    $("nfl-pbp").addEventListener("click",loadNFLpbp);
    $("nfl-rosters").addEventListener("click",loadNFLrosters);
    $("nfl-injuries").addEventListener("click",loadNFLinjuries);
    $("nfl-depth").addEventListener("click",loadNFLdepth);
    $("nfl-stats").addEventListener("click",loadNFLStats);
    $("nfl-snap-counts").addEventListener("click",loadNFLSnapCounts);
    $("nfl-nextgen").addEventListener("click",loadNFLNextGen);
    $("nfl-pfr").addEventListener("click",loadNFLPFR);
    $("mlb-load").addEventListener("click",loadMLB);
    $("nfl-game").addEventListener("change",()=>{$("nfl-pbp").disabled=!$("nfl-game").value;});
    loadProviderStatus();
  }
  if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",init);else init();
})();
