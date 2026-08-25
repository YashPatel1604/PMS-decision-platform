import { type NextRequest } from "next/server";

const API = process.env.API_INTERNAL_URL || "http://127.0.0.1:8000";

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
  const dest = `${API}/${path.join("/")}${req.nextUrl.search}`;
  const headers = new Headers();
  req.headers.forEach((value, key) => {
    if (!DROP.has(key.toLowerCase())) headers.set(key, value);
  });
  const hasBody = req.method !== "GET" && req.method !== "HEAD";
  const upstream = await fetch(dest, {
    method: req.method,
    headers,
    body: hasBody ? await req.arrayBuffer() : undefined,
    redirect: "manual",
  });
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
