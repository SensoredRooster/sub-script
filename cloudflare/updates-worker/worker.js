// SubScript public release host. GET/HEAD: only latest.json and releases/*. Writes need Bearer UPLOAD_TOKEN.
const PUBLIC = /^(latest\.json|releases\/[A-Za-z0-9._-]+\.(exe|json|txt|sha256))$/;
// CORS only for a website reading latest.json. Installers and everything else get no CORS headers.
// No public site reads the SubScript feed yet, so this stays empty on purpose.
export const CORS_ORIGINS = new Set([]);
export function corsOrigin(req, key) {
  const origin = req.headers.get('origin');
  return key === 'latest.json' && origin && CORS_ORIGINS.has(origin) ? origin : null;
}
function addCors(h, origin) {
  h.append('vary', 'Origin');
  if (origin) h.set('access-control-allow-origin', origin);
}
export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    let key;
    try { key = decodeURIComponent(url.pathname.slice(1)); } catch { return new Response('Not found', { status: 404 }); }
    if (req.method === 'OPTIONS') {
      if (key !== 'latest.json') return new Response('Method not allowed', { status: 405 });
      const origin = corsOrigin(req, key);
      const h = new Headers({ vary: 'Origin' });
      if (!origin) return new Response(null, { status: 403, headers: h });
      h.set('access-control-allow-origin', origin);
      h.set('access-control-allow-methods', 'GET');
      h.set('access-control-max-age', '86400');
      return new Response(null, { status: 204, headers: h });
    }
    if (req.method === 'GET' || req.method === 'HEAD') {
      if (!PUBLIC.test(key)) return new Response('Not found', { status: 404 });
      const obj = req.method === 'HEAD' ? await env.RELEASES.head(key) : await env.RELEASES.get(key, { range: req.headers, onlyIf: req.headers });
      if (!obj) return new Response('Not found', { status: 404 });
      const h = new Headers(); obj.writeHttpMetadata(h); h.set('etag', obj.httpEtag); h.set('accept-ranges', 'bytes');
      h.set('cache-control', key === 'latest.json' ? 'no-cache, max-age=0' : 'public, max-age=86400');
      if (key === 'latest.json') addCors(h, req.method === 'GET' ? corsOrigin(req, key) : null);
      if (key.endsWith('.exe')) h.set('content-disposition', `attachment; filename="${key.split('/').pop()}"`);
      if (!('body' in obj)) { h.set('content-length', obj.size); return new Response(null, { headers: h }); }
      if (!obj.body) return new Response(null, { status: 304, headers: h });
      let status = 200;
      if (obj.range && req.headers.has('range')) { status = 206; const o = obj.range.offset ?? 0, l = obj.range.length ?? obj.size - o; h.set('content-range', `bytes ${o}-${o + l - 1}/${obj.size}`); }
      return new Response(obj.body, { status, headers: h });
    }
    if ((req.headers.get('authorization') || '') !== `Bearer ${env.UPLOAD_TOKEN}` || !env.UPLOAD_TOKEN) return new Response('Unauthorized', { status: 401 });
    if (!PUBLIC.test(key)) return new Response('Bad key', { status: 400 });
    const ct = key.endsWith('.json') ? 'application/json' : 'application/octet-stream';
    const action = url.searchParams.get('action');
    if (req.method === 'PUT' && !action) { await env.RELEASES.put(key, req.body, { httpMetadata: { contentType: ct } }); return Response.json({ ok: true, key }); }
    if (req.method === 'POST' && action === 'mpu-create') { const m = await env.RELEASES.createMultipartUpload(key, { httpMetadata: { contentType: ct } }); return Response.json({ uploadId: m.uploadId }); }
    if (req.method === 'PUT' && action === 'mpu-part') { const m = env.RELEASES.resumeMultipartUpload(key, url.searchParams.get('uploadId')); const p = await m.uploadPart(Number(url.searchParams.get('part')), req.body); return Response.json(p); }
    if (req.method === 'POST' && action === 'mpu-complete') { const m = env.RELEASES.resumeMultipartUpload(key, url.searchParams.get('uploadId')); const o = await m.complete((await req.json()).parts); return Response.json({ ok: true, etag: o.httpEtag, size: o.size }); }
    if (req.method === 'DELETE' && action === 'mpu-abort') { await env.RELEASES.resumeMultipartUpload(key, url.searchParams.get('uploadId')).abort(); return Response.json({ ok: true }); }
    return new Response('Method not allowed', { status: 405 });
  }
};
