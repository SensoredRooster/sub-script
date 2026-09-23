const MAX_UPLOAD_BYTES = 75 * 1024 * 1024;
const SESSION_SECONDS = 12 * 60 * 60;
const FOLDERS = ["Releases","Tester Uploads","Screenshots","Bug Reports","Logs","Archived"];
const TESTER_UPLOAD_FOLDERS = new Set(["Tester Uploads", "Screenshots", "Bug Reports", "Logs"]);
const META_LATEST = "__portal/latest.json";
const encoder = new TextEncoder();

function baseHeaders(extra = {}) {
  return {
    "cache-control": "no-store",
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
    "permissions-policy": "camera=(), microphone=(), geolocation=()",
    ...extra,
  };
}
function json(value, status = 200, extra = {}) {
  return new Response(JSON.stringify(value), { status, headers: baseHeaders({ "content-type": "application/json; charset=utf-8", ...extra }) });
}
function html(value, status = 200, extra = {}) {
  return new Response(value, { status, headers: baseHeaders({ "content-type": "text/html; charset=utf-8", ...extra }) });
}
function b64url(bytes) {
  let binary = ""; for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}
function fromB64url(value) {
  const normalized = value.replace(/-/g, "+").replace(/_/g, "/");
  const padded = normalized + "=".repeat((4 - normalized.length % 4) % 4);
  const binary = atob(padded);
  return Uint8Array.from(binary, c => c.charCodeAt(0));
}
async function hmac(secret, value) {
  const key = await crypto.subtle.importKey("raw", encoder.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return new Uint8Array(await crypto.subtle.sign("HMAC", key, encoder.encode(value)));
}
function constantEqual(a, b) {
  if (typeof a !== "string" || typeof b !== "string" || a.length !== b.length) return false;
  let diff = 0; for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i); return diff === 0;
}
function sessionSecret(env) { return env.SHARE_SESSION_SECRET || env.SHARE_ADMIN_PASSWORD || ""; }
async function signSession(env, role) {
  const payload = b64url(encoder.encode(JSON.stringify({ role, exp: Math.floor(Date.now()/1000)+SESSION_SECONDS, project: "subscript" })));
  const sig = b64url(await hmac(sessionSecret(env), payload));
  return payload + "." + sig;
}
async function verifySession(request, env) {
  const cookie = request.headers.get("cookie") || "";
  const match = cookie.match(/(?:^|;\s*)share_session=([^;]+)/);
  if (!match || !sessionSecret(env)) return null;
  const parts = match[1].split("."); if (parts.length !== 2) return null;
  const expected = b64url(await hmac(sessionSecret(env), parts[0]));
  if (!constantEqual(expected, parts[1])) return null;
  try {
    const payload = JSON.parse(new TextDecoder().decode(fromB64url(parts[0])));
    if (payload.project !== "subscript" || payload.exp < Math.floor(Date.now()/1000)) return null;
    if (!["admin","tester"].includes(payload.role)) return null;
    return payload;
  } catch { return null; }
}
function normalizeKey(raw) {
  let value = decodeURIComponent(String(raw || "")).replace(/\\/g, "/");
  value = value.split("/").filter(part => part && part !== "." && part !== "..").join("/");
  if (!value || value.startsWith("__portal/") || value.length > 500) return "";
  return value;
}
function topFolder(key) { return key.split("/")[0] || ""; }
function safeFilename(name) { return String(name || "download.bin").replace(/[\r\n"\\/]+/g, "_").slice(0,180); }
function canUpload(role, key) {
  const folder = topFolder(key);
  if (!FOLDERS.includes(folder)) return false;
  return role === "admin" || TESTER_UPLOAD_FOLDERS.has(folder);
}
async function readLatest(env) {
  const obj = await env.SHARE_BUCKET.get(META_LATEST); if (!obj) return null;
  try { return JSON.parse(await obj.text()); } catch { return null; }
}

const LOGIN = `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SubScript Tester Share</title>
<style>:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;font-family:Inter,system-ui,sans-serif;background:#080b12;color:#f5f7ff;min-height:100vh;display:grid;place-items:center}.card{width:min(92vw,460px);padding:28px;border-radius:22px;background:linear-gradient(180deg,#151b2a,#0e1320);border:1px solid #293246;box-shadow:0 24px 70px #0008}.eyebrow{font-size:12px;letter-spacing:.16em;text-transform:uppercase;color:#7dd3fc;font-weight:800}h1{margin:8px 0 6px;font-size:28px}.muted{color:#9da8bc;line-height:1.5}input,select,button{width:100%;margin-top:12px;border-radius:12px;border:1px solid #30394e;background:#0a0f19;color:#fff;padding:12px 14px;font:inherit}button{background:#2563eb;border-color:#3b82f6;font-weight:800;cursor:pointer}.error{min-height:22px;color:#fca5a5;margin-top:10px}</style></head>
<body><main class="card"><div class="eyebrow">Private tester share</div><h1>SubScript</h1><p class="muted">Use the tester password for shared files or the admin password for release management.</p><select id="role"><option value="tester">Tester</option><option value="admin">Admin</option></select><input id="password" type="password" autocomplete="current-password" placeholder="Password"><button id="login">Sign in</button><div class="error" id="error"></div></main>
<script>document.getElementById("login").onclick=async()=>{const b=document.getElementById("login");b.disabled=true;const r=await fetch("/login",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({role:document.getElementById("role").value,password:document.getElementById("password").value})});if(r.ok)location.href="/";else{const d=await r.json().catch(()=>({}));document.getElementById("error").textContent=d.error||"Sign in failed.";b.disabled=false;}};document.getElementById("password").addEventListener("keydown",e=>{if(e.key==="Enter")document.getElementById("login").click()});</script></body></html>`;

const PORTAL = `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SubScript Tester Share</title>
<style>:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;font-family:Inter,system-ui,sans-serif;background:#070a10;color:#eef3ff}header{position:sticky;top:0;z-index:3;background:#090d16ef;backdrop-filter:blur(16px);border-bottom:1px solid #222b3d;padding:14px 20px;display:flex;align-items:center;gap:12px;justify-content:space-between}.brand strong{display:block;font-size:18px}.brand span{color:#8fa1ba;font-size:12px}.wrap{max-width:1180px;margin:auto;padding:22px}.grid{display:grid;grid-template-columns:220px 1fr;gap:18px}.panel{background:#101622;border:1px solid #263044;border-radius:18px;padding:16px}.folders button{display:block;width:100%;text-align:left;margin:4px 0;padding:10px 12px;border:0;border-radius:10px;background:transparent;color:#cbd5e1;cursor:pointer}.folders button.active{background:#1d4ed8;color:#fff}.toolbar{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:12px}button,input{border-radius:10px;border:1px solid #334057;background:#0a101b;color:#fff;padding:9px 11px;font:inherit}button{cursor:pointer}.primary{background:#2563eb;border-color:#3b82f6;font-weight:750}.danger{background:#7f1d1d;border-color:#b91c1c}.files{width:100%;border-collapse:collapse}.files th,.files td{padding:10px 8px;border-bottom:1px solid #202a3d;text-align:left;font-size:13px}.files th{color:#94a3b8}.files a{color:#7dd3fc;text-decoration:none}.latest{margin-bottom:14px;padding:14px;border:1px solid #245a9c;border-radius:14px;background:#0d2441}.latest a{color:#93c5fd}.muted{color:#8fa1ba}.progress{height:7px;background:#1f2937;border-radius:999px;overflow:hidden;margin-top:8px}.progress i{display:block;height:100%;background:#38bdf8;width:0}.hidden{display:none!important}@media(max-width:760px){.grid{grid-template-columns:1fr}.folders{display:flex;overflow:auto;gap:5px}.folders button{white-space:nowrap;width:auto}.files th:nth-child(3),.files td:nth-child(3){display:none}}</style></head>
<body><header><div class="brand"><strong>SubScript Tester Share</strong><span id="role"></span></div><button id="logout">Sign out</button></header><div class="wrap"><div id="latest" class="latest hidden"></div><div class="grid"><aside class="panel folders" id="folders"></aside><section class="panel"><div class="toolbar"><input id="file" type="file"><input id="desc" placeholder="Optional description"><button class="primary" id="upload">Upload</button><span class="muted" id="status"></span></div><div class="progress hidden" id="progress"><i></i></div><table class="files"><thead><tr><th>Name</th><th>Size</th><th>Uploaded</th><th>Description</th><th>Actions</th></tr></thead><tbody id="rows"></tbody></table></section></div></div>
<script>let role="tester",folder="Releases";const folders=["Releases","Tester Uploads","Screenshots","Bug Reports","Logs","Archived"];const fmt=n=>n<1024?n+" B":n<1048576?(n/1024).toFixed(1)+" KB":n<1073741824?(n/1048576).toFixed(1)+" MB":(n/1073741824).toFixed(1)+" GB";async function api(url,opt){const r=await fetch(url,opt);if(r.status===401){location.href="/login";throw new Error("Unauthorized")}const d=await r.json().catch(()=>({}));if(!r.ok)throw new Error(d.error||("HTTP "+r.status));return d}
async function init(){const me=await api("/api/me");role=me.role;document.getElementById("role").textContent=role==="admin"?"Administrator":"Tester";const box=document.getElementById("folders");folders.forEach(f=>{const b=document.createElement("button");b.textContent=f;b.onclick=()=>selectFolder(f);b.dataset.folder=f;box.appendChild(b)});await selectFolder("Releases");await loadLatest()}
async function selectFolder(f){folder=f;document.querySelectorAll("[data-folder]").forEach(b=>b.classList.toggle("active",b.dataset.folder===f));const can=role==="admin"||["Tester Uploads","Screenshots","Bug Reports","Logs"].includes(f);document.getElementById("file").disabled=!can;document.getElementById("desc").disabled=!can;document.getElementById("upload").disabled=!can;const d=await api("/api/list?prefix="+encodeURIComponent(f+"/"));const rows=document.getElementById("rows");rows.innerHTML="";d.objects.forEach(o=>{const tr=document.createElement("tr");const name=o.key.slice((f+"/").length);const actions=[`<a href="/file/${encodeURIComponent(o.key)}">Download</a>`];if(role==="admin"){if(f==="Releases")actions.push(`<button data-latest="${encodeURIComponent(o.key)}">Latest</button>`);actions.push(`<button class="danger" data-delete="${encodeURIComponent(o.key)}">Delete</button>`)}tr.innerHTML=`<td>${escapeHtml(name)}</td><td>${fmt(o.size)}</td><td>${new Date(o.uploaded).toLocaleString()}</td><td>${escapeHtml(o.description||"")}</td><td>${actions.join(" ")}</td>`;rows.appendChild(tr)});rows.querySelectorAll("[data-delete]").forEach(b=>b.onclick=()=>removeFile(decodeURIComponent(b.dataset.delete)));rows.querySelectorAll("[data-latest]").forEach(b=>b.onclick=()=>markLatest(decodeURIComponent(b.dataset.latest)))}
function escapeHtml(s){return String(s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[c]))}
document.getElementById("upload").onclick=async()=>{const input=document.getElementById("file"),file=input.files[0];if(!file)return;const key=folder+"/"+file.name;const p=document.getElementById("progress"),bar=p.querySelector("i");p.classList.remove("hidden");bar.style.width="15%";try{const r=await fetch("/api/upload",{method:"POST",headers:{"x-file-path":encodeURIComponent(key),"x-description":encodeURIComponent(document.getElementById("desc").value||""),"content-type":file.type||"application/octet-stream"},body:file});bar.style.width="100%";if(!r.ok){const d=await r.json().catch(()=>({}));throw new Error(d.error||"Upload failed")}document.getElementById("status").textContent="Uploaded "+file.name;input.value="";await selectFolder(folder)}catch(e){document.getElementById("status").textContent=e.message}finally{setTimeout(()=>p.classList.add("hidden"),600)}};
async function removeFile(key){if(!confirm("Delete this file?"))return;await api("/api/file?key="+encodeURIComponent(key),{method:"DELETE"});await selectFolder(folder);await loadLatest()}async function markLatest(key){await api("/api/latest",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({key})});await loadLatest()}async function loadLatest(){const d=await api("/api/latest");const box=document.getElementById("latest");if(!d.latest){box.classList.add("hidden");return}box.classList.remove("hidden");box.innerHTML=`<strong>Latest test build</strong><br><a href="/file/${encodeURIComponent(d.latest.key)}">${escapeHtml(d.latest.key.replace("Releases/",""))}</a><span class="muted"> · marked ${new Date(d.latest.marked_at).toLocaleString()}</span>`}document.getElementById("logout").onclick=async()=>{await fetch("/logout",{method:"POST"});location.href="/login"};init().catch(e=>document.getElementById("status").textContent=e.message);</script></body></html>`;

export default { async fetch(request, env) {
  const url = new URL(request.url); const ip = request.headers.get("cf-connecting-ip") || "unknown";
  if (request.method === "GET" && url.pathname === "/health") return json({ ok:true, service:"subscript-tester-share", storage:"r2" });
  if (request.method === "GET" && url.pathname === "/login") return html(LOGIN);
  if (request.method === "POST" && url.pathname === "/login") {
    const rate = await env.AUTH_RATE_LIMITER.limit({key:ip}); if (!rate.success) return json({error:"Too many sign-in attempts."},429);
    if (!env.SHARE_ADMIN_PASSWORD || !env.SHARE_TESTER_PASSWORD) return json({error:"Portal authentication is not configured."},503);
    let body; try { body=await request.json(); } catch { return json({error:"Invalid request."},400); }
    const role=body?.role==="admin"?"admin":"tester"; const expected=role==="admin"?env.SHARE_ADMIN_PASSWORD:env.SHARE_TESTER_PASSWORD;
    if (!constantEqual(String(body?.password||""),expected)) return json({error:"Invalid password."},401);
    const token=await signSession(env,role);
    return json({ok:true,role},200,{"set-cookie":`share_session=${token}; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=${SESSION_SECONDS}`});
  }
  if (request.method === "POST" && url.pathname === "/logout") return new Response(null,{status:204,headers:baseHeaders({"set-cookie":"share_session=; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=0"})});
  const session=await verifySession(request,env);
  if (!session) { if (url.pathname.startsWith("/api/")||url.pathname.startsWith("/file/")) return json({error:"Unauthorized"},401); return Response.redirect(url.origin+"/login",302); }
  if (request.method==="GET"&&url.pathname==="/") return html(PORTAL);
  if (request.method==="GET"&&url.pathname==="/api/me") return json({role:session.role});
  if (request.method==="GET"&&url.pathname==="/api/list") {
    const prefix=normalizeKey(url.searchParams.get("prefix")||""); if(!prefix||!FOLDERS.includes(topFolder(prefix)))return json({error:"Invalid folder."},400);
    const listed=await env.SHARE_BUCKET.list({prefix,include:["customMetadata"],limit:1000});
    return json({objects:listed.objects.filter(o=>!o.key.endsWith("/")).map(o=>({key:o.key,size:o.size,uploaded:o.uploaded,description:o.customMetadata?.description||"",uploader_role:o.customMetadata?.uploader_role||""})).sort((a,b)=>String(b.uploaded).localeCompare(String(a.uploaded))),truncated:listed.truncated});
  }
  if (request.method==="POST"&&url.pathname==="/api/upload") {
    const rate=await env.UPLOAD_RATE_LIMITER.limit({key:ip}); if(!rate.success)return json({error:"Upload rate limit reached."},429);
    const rawLength=Number(request.headers.get("content-length")||"0"); if(rawLength>MAX_UPLOAD_BYTES)return json({error:"File is larger than 75 MB."},413);
    const key=normalizeKey(request.headers.get("x-file-path")||""); if(!key||!canUpload(session.role,key))return json({error:"You cannot upload to that folder."},403);
    const body=await request.arrayBuffer(); if(!body.byteLength)return json({error:"Empty upload."},400); if(body.byteLength>MAX_UPLOAD_BYTES)return json({error:"File is larger than 75 MB."},413);
    const description=decodeURIComponent(request.headers.get("x-description")||"").slice(0,500);
    await env.SHARE_BUCKET.put(key,body,{httpMetadata:{contentType:request.headers.get("content-type")||"application/octet-stream"},customMetadata:{description,uploader_role:session.role,uploaded_at:new Date().toISOString()}});
    return json({ok:true,key,size:body.byteLength});
  }
  if (request.method==="GET"&&url.pathname.startsWith("/file/")) {
    const key=normalizeKey(url.pathname.slice("/file/".length)); if(!key||!FOLDERS.includes(topFolder(key)))return json({error:"Invalid file."},400);
    const obj=await env.SHARE_BUCKET.get(key); if(!obj)return json({error:"File not found."},404);
    return new Response(obj.body,{headers:baseHeaders({"content-type":obj.httpMetadata?.contentType||"application/octet-stream","content-disposition":`attachment; filename="${safeFilename(key.split("/").pop())}"`})});
  }
  if (request.method==="DELETE"&&url.pathname==="/api/file") {
    if(session.role!=="admin")return json({error:"Admin access required."},403); const key=normalizeKey(url.searchParams.get("key")||""); if(!key||!FOLDERS.includes(topFolder(key)))return json({error:"Invalid file."},400);
    await env.SHARE_BUCKET.delete(key); const latest=await readLatest(env); if(latest?.key===key)await env.SHARE_BUCKET.delete(META_LATEST); return json({ok:true});
  }
  if (request.method==="GET"&&url.pathname==="/api/latest") return json({latest:await readLatest(env)});
  if (request.method==="POST"&&url.pathname==="/api/latest") {
    if(session.role!=="admin")return json({error:"Admin access required."},403); let body;try{body=await request.json()}catch{return json({error:"Invalid request."},400)}
    const key=normalizeKey(body?.key||""); if(!key||topFolder(key)!=="Releases")return json({error:"Latest build must be in Releases."},400); const existing=await env.SHARE_BUCKET.head(key);if(!existing)return json({error:"Release not found."},404);
    const latest={key,marked_at:new Date().toISOString()}; await env.SHARE_BUCKET.put(META_LATEST,JSON.stringify(latest),{httpMetadata:{contentType:"application/json"}}); return json({ok:true,latest});
  }
  return json({error:"Not found."},404);
}};