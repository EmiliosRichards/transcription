import { NextRequest, NextResponse } from "next/server";

const COOKIE_NAME = "app_auth";
const MW_HEADER = "x-app-auth-middleware";

function toHex(bytes: ArrayBuffer) {
  return Array.from(new Uint8Array(bytes))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

async function sha256Hex(input: string): Promise<string> {
  const enc = new TextEncoder();
  const digest = await crypto.subtle.digest("SHA-256", enc.encode(input));
  return toHex(digest);
}

function isPublicPath(pathname: string) {
  // Always allow Next.js internals and common public files.
  if (
    pathname.startsWith("/_next/") ||
    pathname.startsWith("/favicon") ||
    pathname === "/robots.txt" ||
    pathname === "/sitemap.xml"
  ) {
    return true;
  }

  // Allow healthcheck unauthenticated (Railway uses this).
  if (pathname === "/healthz") return true;

  return false;
}

function parseMaxAgeSeconds() {
  const raw = String(process.env.APP_AUTH_MAX_AGE_SECONDS || "").trim();
  if (!raw) return null; // session cookie
  const n = Number(raw);
  if (!Number.isFinite(n) || n <= 0) return null;
  return Math.floor(n);
}

function parseBasicAuth(headerValue: string | null): { username: string; password: string } | null {
  if (!headerValue) return null;
  const v = headerValue.trim();
  if (!v.toLowerCase().startsWith("basic ")) return null;
  const token = v.slice(6).trim();
  if (!token) return null;
  try {
    // Edge runtime provides atob.
    const decoded = globalThis.atob(token);
    const idx = decoded.indexOf(":");
    if (idx < 0) return null;
    const username = decoded.slice(0, idx);
    const password = decoded.slice(idx + 1);
    return { username, password };
  } catch {
    return null;
  }
}

export async function middleware(req: NextRequest) {
  const pathname = req.nextUrl.pathname;

  if (isPublicPath(pathname)) {
    const res = NextResponse.next();
    res.headers.set(MW_HEADER, "public");
    return res;
  }

  const expectedUsername = (process.env.APP_AUTH_USERNAME || "guest").trim();
  const expectedPassword = (process.env.APP_AUTH_PASSWORD || "").trim();

  // If auth isn't configured, fail closed in production, open in dev.
  if (!expectedPassword) {
    if (process.env.NODE_ENV === "production") {
      if (pathname.startsWith("/api/")) {
        const res = NextResponse.json({ detail: "App auth not configured" }, { status: 503 });
        res.headers.set(MW_HEADER, "misconfigured");
        return res;
      }
      const res = new NextResponse("App auth not configured", { status: 503 });
      res.headers.set(MW_HEADER, "misconfigured");
      return res;
    }
    const res = NextResponse.next();
    res.headers.set(MW_HEADER, "dev-open");
    return res;
  }

  const cookie = req.cookies.get(COOKIE_NAME)?.value || "";
  const expected = await sha256Hex(`${expectedUsername}:${expectedPassword}`);
  const ok = cookie && cookie === expected;

  if (ok) {
    const res = NextResponse.next();
    res.headers.set(MW_HEADER, "cookie");
    return res;
  }

  // Fall back to HTTP Basic Auth (browser-native prompt) and mint a cookie.
  const creds = parseBasicAuth(req.headers.get("authorization"));
  if (creds && creds.username === expectedUsername && creds.password === expectedPassword) {
    const res = NextResponse.next();
    const maxAge = parseMaxAgeSeconds();
    res.cookies.set({
      name: COOKIE_NAME,
      value: expected,
      httpOnly: true,
      sameSite: "lax",
      secure: process.env.NODE_ENV === "production",
      path: "/",
      ...(maxAge ? { maxAge } : {}),
    });
    res.headers.set(MW_HEADER, "basic");
    return res;
  }

  const headers = new Headers();
  headers.set("WWW-Authenticate", 'Basic realm="TranscriptFlow", charset="UTF-8"');
  headers.set(MW_HEADER, "challenge");

  // For API routes, return 401 JSON.
  if (pathname.startsWith("/api/")) {
    return NextResponse.json({ detail: "Unauthorized" }, { status: 401, headers });
  }
  return new NextResponse("Authentication required", { status: 401, headers });
}

export const config = {
  // Apply to all pages and APIs, excluding Next internals via `isPublicPath`.
  matcher: ["/:path*"],
};

