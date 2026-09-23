const MAX_BYTES = 75 * 1024 * 1024;

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json; charset=utf-8" },
  });
}

function authorized(request, env) {
  const expected = env.SUPPORT_UPLOAD_TOKEN || "";
  return expected && request.headers.get("authorization") === `Bearer ${expected}`;
}

function safeName(value, fallback = "unknown") {
  const clean = String(value || "").trim().replace(/[^A-Za-z0-9._-]+/g, "-").replace(/^[.-]+|[.-]+$/g, "");
  return clean.slice(0, 140) || fallback;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (request.method === "GET" && url.pathname === "/health") {
      return json({ ok: true, service: "subscript-support-collector" });
    }

    if (!authorized(request, env)) {
      return json({ error: "Unauthorized" }, 401);
    }

    if (request.method === "POST" && url.pathname === "/upload") {
      const length = Number(request.headers.get("content-length") || "0");
      if (length > MAX_BYTES) return json({ error: "Bundle too large" }, 413);

      const body = await request.arrayBuffer();
      if (!body.byteLength) return json({ error: "Empty bundle" }, 400);
      if (body.byteLength > MAX_BYTES) return json({ error: "Bundle too large" }, 413);

      const bytes = new Uint8Array(body);
      if (bytes.length < 2 || bytes[0] !== 0x50 || bytes[1] !== 0x4b) {
        return json({ error: "Expected a ZIP support bundle" }, 415);
      }

      const session = safeName(request.headers.get("x-subscript-session"), "unknown-session");
      const version = safeName(request.headers.get("x-subscript-version"), "unknown-version");
      const original = safeName(request.headers.get("x-subscript-filename"), "SubScript-Support.zip");
      const stamp = new Date().toISOString().replace(/[-:]/g, "").replace(/\.\d{3}Z$/, "Z");
      const key = `bundles/${stamp}-${session}-${original}`;

      await env.SUPPORT_BUCKET.put(key, body, {
        httpMetadata: { contentType: "application/zip" },
        customMetadata: { session, version, receivedAt: new Date().toISOString() },
      });

      return json({ ok: true, bundle: key.split("/").pop(), session_id: session });
    }

    if (request.method === "GET" && url.pathname === "/bundles") {
      const listed = await env.SUPPORT_BUCKET.list({ prefix: "bundles/" });
      return json({
        bundles: listed.objects
          .map((obj) => ({
            name: obj.key.split("/").pop(),
            size_bytes: obj.size,
            uploaded: obj.uploaded,
            session_id: obj.customMetadata?.session || null,
            version: obj.customMetadata?.version || null,
          }))
          .sort((a, b) => String(b.uploaded).localeCompare(String(a.uploaded))),
      });
    }

    if (request.method === "GET" && url.pathname.startsWith("/bundles/")) {
      const name = safeName(decodeURIComponent(url.pathname.slice("/bundles/".length)), "");
      if (!name || !name.endsWith(".zip")) return json({ error: "Invalid bundle name" }, 400);
      const obj = await env.SUPPORT_BUCKET.get(`bundles/${name}`);
      if (!obj) return json({ error: "Bundle not found" }, 404);
      return new Response(obj.body, {
        headers: {
          "content-type": "application/zip",
          "content-disposition": `attachment; filename="${name}"`,
        },
      });
    }

    return json({ error: "Not found" }, 404);
  },
};
