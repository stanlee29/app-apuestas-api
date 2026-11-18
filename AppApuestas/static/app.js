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
    const raw=String(value); const date=new Date(/[zZ]$|[+-]\d\d:\d\d$/.test(raw)?raw:raw.replace(" ","T")+"-06:00");
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
    if(!values.length) return {label:"EV teórico no calculable",positive:false};
    const positive=values.filter((entry)=>entry[1]&&entry[1].es_valor_positivo);
    if(!positive.length) return {label:"EV teórico sin señal",positive:false};
    const labels=positive.map((entry)=>{
      const key=entry[0]==="local"?"L":entry[0]==="visitante"?"V":"E";
      return key+" +"+(Number(entry[1].valor_esperado)*100).toFixed(1)+"%";
    });
    return {label:"EV teórico+ "+labels.join(" · "),positive:true};
  }
  function renderEvent(event) {
    const p=event.probabilidades_modelo||{}, odds=event.cuotas||{}, ev=formatEV(event.analisis_ev);
    const live=event.estado_evento==="En vivo", modelAvailable=Boolean(event.modelo_disponible);
    const html=[
      '<article class="event-card"><div class="event-head"><div><div class="league-name">',
      escapeHtml(event.liga||"Competición no identificada"),'</div><div class="event-time">',
      formatKickoff(event.fecha_hora),'</div></div><span class="event-status ',live?"live":"",'">',
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
  let currentMarkets = [];
  let showAllMarkets = false;
  let marketLimit = 80;
  let marketQuery = "";

  function marketHasPrices(market) {
    return (Array.isArray(market.selecciones)?market.selecciones:[]).some((selection)=>
      (Array.isArray(selection.casas)?selection.casas:[]).some((house)=>
        Number.isFinite(Number(house.cuota_decimal)) && Number(house.cuota_decimal)>1
      )
    );
  }

  function marketMatchesQuery(market, query) {
    if(!query) return true;
    const selections=(market.selecciones||[]).map((item)=>item.nombre||item.lado||"").join(" ");
    const haystack=[
      market.nombre,market.periodo,market.stat_id,market.entidad_id,market.linea,selections
    ].join(" ").toLocaleLowerCase();
    return haystack.includes(query);
  }

  function renderMarket(market, pricedOnly) {
    let selections=Array.isArray(market.selecciones)?market.selecciones:[];
    if(pricedOnly) selections=selections.filter((selection)=>
      (Array.isArray(selection.casas)?selection.casas:[]).some((house)=>
        Number.isFinite(Number(house.cuota_decimal)) && Number(house.cuota_decimal)>1
      )
    );
    const selectionHtml=selections.map((selection)=>{
      const houses=Array.isArray(selection.casas)?selection.casas:[];
      const oddsHtml=houses.length?houses.filter((house)=>Number(house.cuota_decimal)>1).slice(0,6).map((house)=>{
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

  function updateMarketView() {
    const results=$("market-results");
    const count=$("market-count");
    const more=$("market-more");
    if(!results||!count||!more)return;
    const query=marketQuery.trim().toLocaleLowerCase();
    const filtered=currentMarkets.filter((market)=>
      (showAllMarkets||marketHasPrices(market)) && marketMatchesQuery(market,query)
    );
    const visible=filtered.slice(0,marketLimit);
    const pricedCount=currentMarkets.filter(marketHasPrices).length;
    count.textContent=showAllMarkets
      ? filtered.length+" de "+currentMarkets.length+" mercados"
      : pricedCount+" con cuotas de "+currentMarkets.length+" mercados";
    results.innerHTML=visible.length
      ? visible.map((market)=>renderMarket(market,!showAllMarkets)).join("")
      : '<div class="market-loading">'+(query?"No hay mercados que coincidan con la búsqueda.":"No hay precios de casas disponibles para este evento.")+'</div>';
    more.hidden=visible.length>=filtered.length;
    more.textContent="Cargar "+Math.min(80,filtered.length-visible.length)+" más · "+(filtered.length-visible.length)+" restantes";
  }

  async function loadMarkets(eventId) {
    const dialog=$("market-dialog"),body=$("market-content"),title=$("market-title");
    title.textContent="Mercados del evento";
    currentMarkets=[];showAllMarkets=false;marketLimit=80;marketQuery="";
    body.innerHTML='<div class="market-loading">Consultando precios publicados…</div>';
    if(typeof dialog.showModal==="function"&&!dialog.open)dialog.showModal();
    try {
      const response=await fetch("/api/v1/events/"+encodeURIComponent(eventId)+"/markets",{cache:"no-store"});
      const payload=await response.json();
      if(!response.ok)throw new Error(typeof payload.detail==="string"?payload.detail:"Error "+response.status);
      currentMarkets=Array.isArray(payload.mercados)?payload.mercados:[];
      body.innerHTML=
        '<div class="market-toolbar">'+
          '<input id="market-search" type="search" autocomplete="off" placeholder="Buscar mercado o selección…" aria-label="Buscar mercados">'+
          '<label class="market-all-toggle"><input id="market-show-all" type="checkbox"> Mostrar también mercados sin cuotas</label>'+
          '<span id="market-count" class="market-count"></span>'+
        '</div>'+
        '<div id="market-results" class="market-results"></div>'+
        '<div class="market-pagination"><button id="market-more" type="button" hidden>Cargar más mercados</button></div>';
      title.textContent="Mercados del evento · "+currentMarkets.length;
      $("market-search").addEventListener("input",(event)=>{
        marketQuery=event.target.value||"";marketLimit=80;updateMarketView();
      });
      $("market-show-all").addEventListener("change",(event)=>{
        showAllMarkets=event.target.checked;marketLimit=80;updateMarketView();
      });
      $("market-more").addEventListener("click",()=>{
        marketLimit+=80;updateMarketView();
      });
      updateMarketView();
    } catch(error) {
      body.innerHTML='<div class="market-loading error-text">'+escapeHtml(error.message)+'</div>';
    }
  }

  function selectSport(sport) {
    if(!SPORTS[sport])return;
    researchMode(false);
    if(state.sport===sport)return;
    state.sport=sport;
    document.querySelectorAll("[data-sport]").forEach((button)=>{
      button.setAttribute("aria-pressed",String(button.dataset.sport===sport));
    });
    loadCartelera();
  }

  $("events-list").addEventListener("click",(event)=>{
    const button=event.target.closest("[data-markets-id]");
    if(button&&button.dataset.marketsId)loadMarkets(button.dataset.marketsId);
  });
  $("market-close").addEventListener("click",()=> $("market-dialog").close());
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

  const researchState = { competitions: [], matches: [], selectedMatch: null, loaded: false, busy: false };
  const researchHideSelector = ".main-content > section:not(#research-view), .main-content > .notice, .main-content > footer";

  function researchName(value) {
    if (value && typeof value === "object") return String(value.name || value.home_team_name || value.away_team_name || "");
    return String(value || "");
  }

  function researchStatus(message, error) {
    const el = $("research-status");
    el.textContent = message;
    el.className = "research-status" + (error ? " error" : "");
  }

  function researchToday() {
    const parts = new Intl.DateTimeFormat("en", {
      timeZone: "America/El_Salvador", year: "numeric", month: "2-digit", day: "2-digit"
    }).formatToParts(new Date());
    const values = {};
    parts.forEach(part => { values[part.type] = part.value; });
    return values.year + "-" + values.month + "-" + values.day;
  }

  async function researchGet(path) {
    const response = await fetch(path, { cache: "no-store" });
    let data = {};
    try { data = await response.json(); } catch (_) {}
    if (!response.ok) {
      const detail = data.detail;
      throw new Error(typeof detail === "string" ? detail :
        (detail && (detail.mensaje || detail.message)) || ("HTTP " + response.status));
    }
    return data;
  }

  function researchFill(id, rows, placeholder) {
    const select = $(id);
    select.innerHTML = '<option value="">' + escapeHtml(placeholder) + "</option>" +
      rows.map(row => '<option value="' + escapeHtml(row.value) + '">' + escapeHtml(row.label) + "</option>").join("");
    select.disabled = rows.length === 0;
  }

  async function researchLoadCatalog() {
    if (researchState.busy) return;
    researchState.busy = true;
    $("research-refresh").disabled = true;
    researchStatus("Consultando competiciones históricas StatsBomb…");
    try {
      const data = await researchGet("/api/v1/research/statsbomb/competitions");
      researchState.competitions = Array.isArray(data.competiciones) ? data.competiciones : [];
      researchFill("research-competition", researchState.competitions.map(comp => ({
        value: comp.competition_id,
        label: (comp.country_name ? comp.country_name + " · " : "") + comp.competition_name
      })), "Selecciona competición");
      researchState.loaded = true;
      if (researchState.competitions.length) {
        $("research-competition").value = String(researchState.competitions[0].competition_id);
        await researchLoadSeasons();
        researchStatus("Catálogo cargado: " + researchState.competitions.length + " competiciones. La cobertura varía por temporada.");
      } else researchStatus("No hay competiciones disponibles en StatsBomb.", true);
    } catch (error) {
      researchStatus("No se pudo cargar el catálogo: " + error.message, true);
    } finally {
      researchState.busy = false;
      $("research-refresh").disabled = false;
    }
  }

  async function researchLoadSeasons() {
    const comp = researchState.competitions.find(item => String(item.competition_id) === $("research-competition").value);
    researchState.matches = [];
    researchState.selectedMatch = null;
    researchFill("research-season", [], "Selecciona temporada");
    researchFill("research-match", [], "Selecciona partido histórico");
    researchFill("research-home", [], "Selecciona equipo local");
    researchFill("research-away", [], "Selecciona equipo visitante");
    $("research-output").innerHTML = "";
    if (!comp) return;
    const seasons = Array.isArray(comp.seasons) ? comp.seasons : [];
    researchFill("research-season", seasons.map(season => ({
      value: season.season_id, label: season.season_name || String(season.season_id)
    })), "Selecciona temporada");
    if (seasons.length) {
      $("research-season").value = String(seasons[0].season_id);
      await researchLoadMatches();
    }
  }

  async function researchLoadMatches() {
    const comp = $("research-competition").value;
    const season = $("research-season").value;
    researchFill("research-match", [], "Cargando partidos…");
    researchFill("research-home", [], "Cargando equipos…");
    researchFill("research-away", [], "Cargando equipos…");
    researchState.matches = [];
    researchState.selectedMatch = null;
    if (!comp || !season) return;
    researchStatus("Cargando partidos históricos y equipos…");
    try {
      const data = await researchGet("/api/v1/research/statsbomb/competitions/" +
        encodeURIComponent(comp) + "/seasons/" + encodeURIComponent(season) + "/matches");
      researchState.matches = Array.isArray(data.partidos) ? data.partidos : [];
      const teams = new Map();
      researchState.matches.forEach(match => {
        const home = researchName(match.home_team) || String(match.home_team_name || "");
        const away = researchName(match.away_team) || String(match.away_team_name || "");
        if (home) teams.set(home.toLowerCase(), home);
        if (away) teams.set(away.toLowerCase(), away);
      });
      const teamRows = Array.from(teams.values()).sort((a,b) => a.localeCompare(b,"es"))
        .map(name => ({ value:name, label:name }));
      researchFill("research-home", teamRows, "Selecciona equipo local");
      researchFill("research-away", teamRows, "Selecciona equipo visitante");
      const matches = researchState.matches.map(match => {
        const home = researchName(match.home_team) || String(match.home_team_name || "");
        const away = researchName(match.away_team) || String(match.away_team_name || "");
        const score = match.home_score == null ? "" : " · " + match.home_score + "-" + match.away_score;
        return { value:match.match_id, label:(match.match_date || "Sin fecha") + " · " + home + " vs " + away + score };
      });
      researchFill("research-match", matches, "Selecciona partido histórico");
      researchStatus(researchState.matches.length + " partidos y " + teamRows.length + " equipos cargados.");
    } catch (error) {
      researchStatus("No se pudieron cargar los partidos: " + error.message, true);
    }
  }

  function researchSelectMatch() {
    const match = researchState.matches.find(item => String(item.match_id) === $("research-match").value);
    researchState.selectedMatch = match || null;
    if (!match) return;
    $("research-home").value = researchName(match.home_team) || String(match.home_team_name || "");
    $("research-away").value = researchName(match.away_team) || String(match.away_team_name || "");
    $("research-date").value = String(match.match_date || "").slice(0,10);
  }

  function researchInputs() {
    const data = {
      competition_id: $("research-competition").value,
      season_id: $("research-season").value,
      fecha_partido: $("research-date").value,
      local: $("research-home").value,
      visitante: $("research-away").value
    };
    if (!data.competition_id || !data.season_id || !data.fecha_partido || !data.local || !data.visitante)
      throw new Error("Completa competición, temporada, fecha y equipos.");
    if (data.local === data.visitante) throw new Error("Los equipos deben ser diferentes.");
    return data;
  }

  function researchTable(headers, rows) {
    return '<div class="research-table-scroll"><table class="research-table"><thead><tr>' +
      headers.map(item => "<th>" + escapeHtml(item) + "</th>").join("") + "</tr></thead><tbody>" +
      rows.map(row => "<tr>" + row.map(item => "<td>" + escapeHtml(item) + "</td>").join("") + "</tr>").join("") +
      "</tbody></table></div>";
  }

  function researchWarnings(items) {
    if (!Array.isArray(items) || !items.length) return "";
    return '<div class="research-warning"><strong>Advertencias</strong><ul>' +
      items.map(item => "<li>" + escapeHtml(item) + "</li>").join("") + "</ul></div>";
  }

  function researchCard(title, body) {
    return '<section class="research-card"><h3>' + escapeHtml(title) + "</h3>" + body + "</section>";
  }

  async function researchCalculate(kind) {
    let params;
    try { params = researchInputs(); }
    catch (error) { researchStatus(error.message, true); return; }
    const id = kind === "goals" ? "research-goals" : "research-counts";
    const button = $(id), previous = button.textContent;
    button.disabled = true; button.textContent = "Calculando…";
    researchStatus(kind === "goals" ? "Calculando Poisson + Dixon-Coles…" : "Procesando eventos para remates, córners, faltas y tarjetas…");
    try {
      if (kind === "counts") params.ventana = $("research-window").value;
      const query = new URLSearchParams(params);
      const route = kind === "goals" ? "predict" : "markets-predict";
      const data = await researchGet("/api/v1/research/statsbomb/" + route + "?" + query.toString());
      $("research-output").innerHTML = kind === "goals" ? researchGoalsHtml(data) : researchCountsHtml(data);
      researchStatus("Cálculo terminado. Revisa la muestra y las advertencias antes de interpretar los porcentajes.");
    } catch (error) {
      researchStatus("No se pudo calcular: " + error.message, true);
    } finally {
      button.disabled = false; button.textContent = previous;
    }
  }

  function researchGoalsHtml(data) {
    const p = data.probabilidades_1x2_pct || {};
    const g = data.goles_esperados || {};
    const b = data.ambos_marcan_pct || {};
    const summary = [["Local",p.local],["Empate",p.empate],["Visitante",p.visitante],
      ["Goles esperados local",g.local],["Goles esperados visitante",g.visitante],["Ambos marcan",b.si]]
      .map(item => '<div><small>' + escapeHtml(item[0]) + '</small><strong>' +
        escapeHtml(item[1] == null ? "—" : Number(item[1]).toFixed(1) + (item[0].includes("marcan") || item[0] === "Local" || item[0] === "Empate" || item[0] === "Visitante" ? "%" : "")) +
        "</strong></div>").join("");
    const totals = Object.entries(data.totales_goles_pct || {}).map(entry =>
      [entry[0],Number(entry[1].over).toFixed(1)+"%",Number(entry[1].under).toFixed(1)+"%"]);
    const scores = (data.marcadores_mas_probables || []).map(item =>
      [item.marcador,Number(item.probabilidad_pct).toFixed(1)+"%"]);
    return researchCard("Poisson + Dixon-Coles · " + (data.estado_validacion || "exploratorio"),
      '<div class="research-summary-grid">' + summary + "</div>" +
      "<h4>Probabilidades de goles</h4>" + researchTable(["Línea","Over","Under"],totals) +
      "<h4>Marcadores probables</h4>" + researchTable(["Marcador","Probabilidad"],scores) +
      researchWarnings(data.advertencias));
  }

  function researchCountsHtml(data) {
    let html = researchCard("Muestra · " + (data.estado_validacion || "experimental"),
      '<div class="research-summary-grid">' +
      [["Local en casa",data.muestra?.local_en_casa],["Visitante fuera",data.muestra?.visitante_fuera],
       ["Omitidos",data.muestra?.partidos_omitidos],["Ventana",data.muestra?.ventana_solicitada_por_equipo]]
      .map(item => '<div><small>' + escapeHtml(item[0]) + '</small><strong>' + escapeHtml(item[1] ?? "—") + "</strong></div>").join("") +
      "</div>" + researchWarnings(data.advertencias));
    Object.entries(data.mercados || {}).forEach(entry => {
      const market = entry[1];
      ["local","visitante","total_partido"].forEach(side => {
        const item = market[side] || {};
        const rows = (item.lineas || []).map(line =>
          [line.linea,Number(line.over_pct).toFixed(1)+"%",Number(line.under_pct).toFixed(1)+"%"]);
        const sideName = side === "local" ? "Local" : side === "visitante" ? "Visitante" : "Total partido";
        html += researchCard((market.nombre || entry[0]) + " · " + sideName + " · Media " + (item.media_esperada ?? "—"),
          researchTable(["Línea","Over","Under"],rows));
      });
    });
    return html;
  }

  async function researchAnalyse() {
    const match = researchState.selectedMatch;
    if (!match) { researchStatus("Selecciona un partido histórico primero.", true); return; }
    const button = $("research-analysis"), previous = button.textContent;
    button.disabled = true; button.textContent = "Analizando…";
    researchStatus("Consultando xG, remates y estadísticas del partido…");
    try {
      const query = new URLSearchParams({
        competition_id:$("research-competition").value,
        season_id:$("research-season").value
      });
      const data = await researchGet("/api/v1/research/statsbomb/matches/" +
        encodeURIComponent(match.match_id) + "/analysis?" + query.toString());
      const m = data.metricas || {}, h = m.local || {}, a = m.visitante || {};
      const rows = [["xG",h.xg,a.xg],["Remates",h.remates,a.remates],
        ["Remates a puerta",h.remates_a_puerta,a.remates_a_puerta]];
      $("research-output").innerHTML = researchCard("Estadísticas históricas",
        researchTable(["Métrica","Local","Visitante"],rows) +
        '<p class="research-muted">Fuente: StatsBomb Open Data. Datos históricos seleccionados; atribución requerida al publicar análisis derivados.</p>');
      researchStatus("Análisis del partido cargado. No representa tracking continuo de jugadores.");
    } catch (error) {
      researchStatus("No se pudo analizar el partido: " + error.message, true);
    } finally {
      button.disabled = false; button.textContent = previous;
    }
  }

  function researchMode(active) {
    document.querySelectorAll(researchHideSelector).forEach(el => { el.hidden = active; });
    $("research-view").hidden = !active;
    $("research-toggle").setAttribute("aria-pressed",String(active));
    if (active && !researchState.loaded) researchLoadCatalog();
  }

  $("research-toggle").addEventListener("click",() => researchMode($("research-view").hidden));
  $("research-refresh").addEventListener("click",researchLoadCatalog);
  $("research-competition").addEventListener("change",researchLoadSeasons);
  $("research-season").addEventListener("change",researchLoadMatches);
  $("research-match").addEventListener("change",researchSelectMatch);
  $("research-goals").addEventListener("click",() => researchCalculate("goals"));
  $("research-counts").addEventListener("click",() => researchCalculate("counts"));
  $("research-analysis").addEventListener("click",researchAnalyse);
  $("research-date").value = researchToday();

  checkHealth().then(loadCartelera);
})();