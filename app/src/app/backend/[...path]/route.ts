import { type NextRequest } from "next/server";

/** Inside the UI container, localhost is the UI — never the API. */
function apiBase(): string {
  const raw = (process.env.API_INTERNAL_URL || "").trim().replace(/\/$/, "");
  const isLoopback =
    !raw ||
    /^https?:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/i.test(raw);
  if (isLoopback) {
    return process.env.NODE_ENV === "production" ? "http://api:8000" : "http://127.0.0.1:8000";
  }
  return raw;
}

const DROP = new Set([
  "connection",
  "content-encoding",
  "content-length",
  "host",
  "keep-alive",
  "transfer-encoding",
  "upgrade",
]);

async function proxy(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  const API = apiBase();
  const dest = `${API}/${path.join("/")}${req.nextUrl.search}`;
  const headers = new Headers();
  req.headers.forEach((value, key) => {
    if (!DROP.has(key.toLowerCase())) headers.set(key, value);
  });
  const hasBody = req.method !== "GET" && req.method !== "HEAD";
  let upstream: Response;
  try {
    upstream = await fetch(dest, {
      method: req.method,
      headers,
      body: hasBody ? await req.arrayBuffer() : undefined,
      redirect: "manual",
      signal: AbortSignal.timeout(120_000),
    });
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    return Response.json(
      {
        detail: `API unreachable (${API}): ${detail}. Set API_INTERNAL_URL=http://api:8000 in .env and recreate ui.`,
      },
      { status: 502 },
    );
  }
  const out = new Headers();
  upstream.headers.forEach((value, key) => {
    if (!DROP.has(key.toLowerCase()) && key.toLowerCase() !== "set-cookie") {
      out.append(key, value);
    }
  });
  const cookies =
    typeof upstream.headers.getSetCookie === "function" ? upstream.headers.getSetCookie() : [];
  for (const cookie of cookies) out.append("set-cookie", cookie);
  return new Response(upstream.body, { status: upstream.status, headers: out });
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
export const OPTIONS = proxy;
