(() => {
  "use strict";
  const SPORTS = { futbol:{name:"Fútbol"}, nba:{name:"NBA"}, nfl:{name:"NFL"}, mlb:{name:"MLB"} };
  const state = { sport:"futbol", days:2, loading:false, installPrompt:null };
  const $ = (id) => document.getElementById(id);
  const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
  }[c]));

  function setApiStatus(label, status) {
    const el=$("api-status"); el.className="connection-pill"+(status?" "+status:"");
    el.querySelector("span:last-child").textContent=label;
  }
  async function checkHealth() {
    try {
      const response=await fetch("/health",{cache:"no-store"});
      if(!response.ok) throw new Error("HTTP "+response.status);
      const health=await response.json();
      const configured=health.proveedor?.configurado===true; setApiStatus(configured?"Fuente conectada":"Falta clave del proveedor",configured?"connected":"error");
    } catch (_) { setApiStatus("API sin conexión","error"); }
  }
  function formatDateRange(range) {
    if(!range) return "Rango no disponible";
    const parts=String(range).split("-");
    const fmt=(raw)=>{
      if(!/^\d{8}$/.test(raw)) return raw;
      return new Date(Number(raw.slice(0,4)),Number(raw.slice(4,6))-1,Number(raw.slice(6,8)))
        .toLocaleDateString("es-SV",{day:"2-digit",month:"short"});
    };
    return parts.length===2?fmt(parts[0])+" — "+fmt(parts[1]):fmt(parts[0]);
  }
  function formatKickoff(value) {
    if(!value) return "Horario no disponible";
    const raw=String(value); const date=new Date(/[zZ]$|[+-]\\d\\d:\\d\\d$/.test(raw)?raw:raw.replace(" ","T")+"-06:00");
    if(Number.isNaN(date.getTime())) return escapeHtml(value);
    return new Intl.DateTimeFormat("es-SV",{
      weekday:"short",day:"2-digit",month:"short",hour:"2-digit",minute:"2-digit",
      timeZone:"America/El_Salvador"
    }).format(date);
  }
  function formatOdds(value) {
    const n=Number(value); return Number.isFinite(n)&&n>1?n.toFixed(2):"No disp.";
  }
  function formatEV(entries) {
    const values=Object.entries(entries||{});
    if(!values.length) return {label:"EV no calculable",positive:false};
    const positive=values.filter((entry)=>entry[1]&&entry[1].es_valor_positivo);
    if(!positive.length) return {label:"EV sin ventaja",positive:false};
    const labels=positive.map((entry)=>{
      const key=entry[0]==="local"?"L":entry[0]==="visitante"?"V":"E";
      return key+" +"+(Number(entry[1].valor_esperado)*100).toFixed(1)+"%";
    });
    return {label:"EV+ "+labels.join(" · "),positive:true};
  }
  function renderEvent(event) {
    const p=event.probabilidades_modelo||{}, odds=event.cuotas||{}, ev=formatEV(event.analisis_ev);
    const live=event.estado_evento==="En vivo", modelAvailable=Boolean(event.modelo_disponible);
    const html=[
      '<article class="event-card"><div class="event-head"><div><div class="league-name">',
      escapeHtml(event.liga||"Competición no identificada"),'</div><div class="event-time">',
      formatKickoff(event.fecha_hora),'</div></div><span class="event-status ',live?"live":"","">',
      live?"EN VIVO":"PROGRAMADO",'</span></div>',
      '<div class="teams"><div class="team"><span class="team-label">LOCAL</span><strong class="team-name" title="',
      escapeHtml(event.local),'">',escapeHtml(event.local),'</strong></div><div class="vs">VS</div>',
      '<div class="team"><span class="team-label">VISITANTE</span><strong class="team-name" title="',
      escapeHtml(event.visitante),'">',escapeHtml(event.visitante),'</strong></div></div>',
      '<div class="data-table" aria-label="Probabilidades estimadas">',
      '<div class="data-cell"><small>PROB. LOCAL</small><strong>',escapeHtml(p.local||"—"),'</strong></div>',
      '<div class="data-cell"><small>PROB. EMPATE</small><strong>',escapeHtml(p.empate||"—"),'</strong></div>',
      '<div class="data-cell"><small>PROB. VISITANTE</small><strong>',escapeHtml(p.visitante||"—"),'</strong></div></div>',
      '<div class="data-table" aria-label="Cuotas decimales publicadas">',
      '<div class="data-cell"><small>CUOTA LOCAL</small><strong class="',odds.local?"":"muted-value",'">',formatOdds(odds.local),'</strong></div>',
      '<div class="data-cell"><small>CUOTA EMPATE</small><strong class="',odds.empate?"":"muted-value",'">',formatOdds(odds.empate),'</strong></div>',
      '<div class="data-cell"><small>CUOTA VISITANTE</small><strong class="',odds.visitante?"":"muted-value",'">',formatOdds(odds.visitante),'</strong></div></div>',
      '<div class="event-foot"><span class="model-state ',modelAvailable?"available":"",'" title="',
      escapeHtml(event.error_modelo||""),'">',modelAvailable?"Modelo disponible":"Sin histórico compatible",
      '</span><span class="ev-tag ',ev.positive?"positive":"",'" title="',
      escapeHtml(event.fuente_cuotas?"Cuotas: "+event.fuente_cuotas:"Sin cuotas publicadas"),'">',
      escapeHtml(ev.label),'</span></div><button class="markets-button" type="button" data-markets-id="',escapeHtml(event.evento_id||""),'">Ver mercados (',escapeHtml(event.mercados_disponibles??0),')</button></article>'
    ];
    return html.join("");
  }
  function render(data) {
    const events=Array.isArray(data.cartelera)?data.cartelera:[];
    $("metric-events").textContent=data.total_partidos_analizados??events.length;
    $("metric-model").textContent=data.total_con_probabilidades??events.filter(e=>e.modelo_disponible).length;
    $("metric-odds").textContent=data.total_con_cuotas??events.filter(e=>e.fuente_cuotas).length;
    $("metric-value").textContent=data.partidos_con_valor_positivo??events.filter(e=>e.tiene_valor_positivo).length;
    $("selected-sport-title").textContent=SPORTS[state.sport].name;
    $("date-range").textContent=formatDateRange(data.rango_fechas);
    $("results-count").textContent=events.length+(events.length===1?" evento":" eventos");
    const notice=$("notice");
    if(Array.isArray(data.errores_fuente)&&data.errores_fuente.length){
      notice.hidden=false;notice.className="notice";
      notice.textContent="Una o más ligas no respondieron. Se muestran únicamente los eventos consultados correctamente.";
    } else {notice.hidden=true;notice.textContent="";}
    if(!events.length){
      $("events-list").innerHTML='<article class="empty-card"><div class="empty-symbol">⌕</div>'+
        '<strong>No hay eventos disponibles en este rango</strong><p>'+
        escapeHtml(data.mensaje||"Amplía el rango o consulta otro deporte. No se muestran partidos simulados.")+
        "</p></article>";
    } else {$("events-list").innerHTML=events.map(renderEvent).join("");}
    $("events-list").setAttribute("aria-busy","false");
    $("last-updated").textContent="Consultado "+new Intl.DateTimeFormat("es-SV",{
      hour:"2-digit",minute:"2-digit",day:"2-digit",month:"short",timeZone:"America/El_Salvador"
    }).format(new Date());
  }
  async function loadCartelera() {
    if(state.loading) return;
    state.loading=true;$("refresh-btn").disabled=true;$("refresh-btn").classList.add("is-loading");
    $("events-list").setAttribute("aria-busy","true");
    $("events-list").innerHTML='<article class="loading-card"><span class="loader"></span>'+
      "<strong>Consultando cartelera</strong><small>Solicitando eventos y datos del modelo...</small></article>";
    try {
      const url="/cartelera/"+encodeURIComponent(state.sport)+"?dias="+state.days;
      const response=await fetch(url,{cache:"no-store"});
      const payload=await response.json();
      if(!response.ok){
        const detail=payload.detail;
        throw new Error(typeof detail==="string"?detail:"La API respondió con error "+response.status);
      }
      render(payload);setApiStatus("API conectada","connected");
    } catch(error) {
      setApiStatus("Error de consulta","error");
      $("notice").hidden=false;$("notice").className="notice error";
      $("notice").textContent="No fue posible cargar la cartelera: "+error.message;
      $("events-list").innerHTML='<article class="empty-card"><div class="empty-symbol">!</div>'+
        "<strong>No se pudo consultar la cartelera</strong><p>Comprueba la conexión y vuelve a intentarlo. Los datos faltantes no se reemplazan con simulaciones.</p></article>";
      $("events-list").setAttribute("aria-busy","false");
    } finally {
      state.loading=false;$("refresh-btn").disabled=false;$("refresh-btn").classList.remove("is-loading");
    }
  }
  function selectSport(sport) {
    if(!SPORTS[sport]||state.sport===sport)return;
    state.sport=sport;
  
  function renderMarket(market) {
    const selections=Array.isArray(market.selecciones)?market.selecciones:[];
    const selectionHtml=selections.map((selection)=>{
      const houses=Array.isArray(selection.casas)?selection.casas:[];
      const oddsHtml=houses.length?houses.slice(0,6).map((house)=>{
        const label=escapeHtml(house.casa||house.casa_id||"Casa");
        const price=Number(house.cuota_decimal);
        const quote=Number.isFinite(price)?price.toFixed(2):"—";
        const anchor=house.enlace?'<a href="'+escapeHtml(house.enlace)+'" target="_blank" rel="noopener noreferrer">Abrir casa</a>':"";
        return '<span class="book-price"><strong>'+quote+'</strong><small>'+label+'</small>'+anchor+'</span>';
      }).join(""):'<span class="muted-value">Sin precio disponible</span>';
      return '<div class="selection-row"><div class="selection-name">'+escapeHtml(selection.nombre||selection.lado||"Selección")+'</div><div class="book-prices">'+oddsHtml+'</div></div>';
    }).join("");
    return '<article class="market-card"><header><strong>'+escapeHtml(market.nombre||"Mercado")+'</strong><span>'+escapeHtml(market.periodo||"")+(market.linea!=null?' · Línea '+escapeHtml(market.linea):"")+'</span></header>'+selectionHtml+'</article>';
  }
  async function loadMarkets(eventId) {
    const dialog=$("market-dialog"),body=$("market-content"),title=$("market-title");
    title.textContent="Mercados del evento";
    body.innerHTML='<div class="market-loading">Consultando precios publicados…</div>';
    if(typeof dialog.showModal==="function"&&!dialog.open)dialog.showModal();
    try {
      const response=await fetch("/api/v1/events/"+encodeURIComponent(eventId)+"/markets",{cache:"no-store"});
      const payload=await response.json();
      if(!response.ok)throw new Error(typeof payload.detail==="string"?payload.detail:"Error "+response.status);
      const markets=Array.isArray(payload.mercados)?payload.mercados:[];
      title.textContent="Mercados · "+markets.length;
      body.innerHTML=markets.length?markets.map(renderMarket).join(""):'<div class="market-loading">El proveedor no entregó mercados disponibles para este evento.</div>';
    } catch(error) {
      body.innerHTML='<div class="market-loading error-text">'+escapeHtml(error.message)+'</div>';
    }
  }

  $("events-list").addEventListener("click",(event)=>{const button=event.target.closest("[data-markets-id]");if(button&&button.dataset.marketsId)loadMarkets(button.dataset.marketsId);});
  $("market-close").addEventListener("click",()=> $("market-dialog").close());
  document.querySelectorAll("[data-sport]").forEach((button)=>{
      button.setAttribute("aria-pressed",String(button.dataset.sport===sport));
    });
    loadCartelera();
  }
  document.querySelectorAll("[data-sport]").forEach(button=>button.addEventListener("click",()=>selectSport(button.dataset.sport)));
  $("days-filter").addEventListener("change",event=>{state.days=Number(event.target.value);loadCartelera();});
  $("refresh-btn").addEventListener("click",loadCartelera);
  window.addEventListener("beforeinstallprompt",event=>{
    event.preventDefault();state.installPrompt=event;$("install-btn").hidden=false;
  });
  $("install-btn").addEventListener("click",async()=>{
    if(!state.installPrompt)return;
    state.installPrompt.prompt();await state.installPrompt.userChoice;
    state.installPrompt=null;$("install-btn").hidden=true;
  });
  window.addEventListener("appinstalled",()=>{$("install-btn").hidden=true;state.installPrompt=null;});
  if("serviceWorker" in navigator)window.addEventListener("load",()=>navigator.serviceWorker.register("/service-worker.js").catch(()=>{}));
  checkHealth().then(loadCartelera);
  window.setInterval(()=>{if(!document.hidden)loadCartelera();},600000);
})();