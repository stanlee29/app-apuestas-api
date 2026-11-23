"use strict";
const CACHE_NAME="app-apuestas-shell-v13";
const APP_SHELL=["/","/static/styles.css","/static/app.js","/static/research-live.js","/static/thesportsdb-research.js","/static/nba-research.js","/static/pro-sports-research.js","/static/icon.svg","/manifest.webmanifest"];

self.addEventListener("install",(event)=>{
  event.waitUntil(caches.open(CACHE_NAME).then(cache=>cache.addAll(APP_SHELL)).then(()=>self.skipWaiting()));
});
self.addEventListener("activate",(event)=>{
  event.waitUntil(caches.keys()
    .then(keys=>Promise.all(keys.filter(key=>key!==CACHE_NAME).map(key=>caches.delete(key))))
    .then(()=>self.clients.claim()));
});
self.addEventListener("fetch",(event)=>{
  const request=event.request,url=new URL(request.url);
  if(request.method!=="GET"||url.origin!==self.location.origin)return;
  if(url.pathname.startsWith("/cartelera/")||url.pathname.startsWith("/api/")||
     url.pathname.startsWith("/equipos/")||url.pathname.startsWith("/predecir")||
     url.pathname==="/health")return;
  event.respondWith(caches.match(request).then(cached=>cached||fetch(request).then(response=>{
    if(response.ok){const copy=response.clone();caches.open(CACHE_NAME).then(cache=>cache.put(request,copy));}
    return response;
  })));
});
