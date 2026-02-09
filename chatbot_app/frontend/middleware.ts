import { NextRequest, NextResponse } from "next/server";

const COOKIE_NAME = "app_auth";

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

  // Allow login + auth endpoints through.
  if (pathname.startsWith("/login") || pathname.startsWith("/api/auth")) return true;

  return false;
}

export async function middleware(req: NextRequest) {
  const pathname = req.nextUrl.pathname;

  if (isPublicPath(pathname)) {
    return NextResponse.next();
  }

  const username = (process.env.APP_AUTH_USERNAME || "guest").trim();
  const password = (process.env.APP_AUTH_PASSWORD || "").trim();

  // If auth isn't configured, fail closed in production, open in dev.
  if (!password) {
    if (process.env.NODE_ENV === "production") {
      if (pathname.startsWith("/api/")) {
        return NextResponse.json({ detail: "App auth not configured" }, { status: 503 });
      }
      return new NextResponse("App auth not configured", { status: 503 });
    }
    return NextResponse.next();
  }

  const cookie = req.cookies.get(COOKIE_NAME)?.value || "";
  const expected = await sha256Hex(`${username}:${password}`);
  const ok = cookie && cookie === expected;

  if (ok) {
    return NextResponse.next();
  }

  // For API routes, return 401 JSON (don't redirect).
  if (pathname.startsWith("/api/")) {
    return NextResponse.json({ detail: "Unauthorized" }, { status: 401 });
  }

  const loginUrl = req.nextUrl.clone();
  loginUrl.pathname = "/login";
  loginUrl.searchParams.set("next", pathname);
  return NextResponse.redirect(loginUrl);
}

export const config = {
  // Apply to all pages and APIs, excluding Next internals via `isPublicPath`.
  matcher: ["/:path*"],
};

