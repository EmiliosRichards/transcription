import { NextRequest, NextResponse } from "next/server";

const COOKIE_NAME = "company_auth";

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

export async function middleware(req: NextRequest) {
  const pathname = req.nextUrl.pathname;

  // Allow login + auth endpoints through.
  if (pathname.startsWith("/company/login") || pathname.startsWith("/api/company-auth")) {
    return NextResponse.next();
  }

  const password = (process.env.COMPANY_PAGE_PASSWORD || "").trim();

  // If password isn't configured, fail closed in production, open in dev.
  if (!password) {
    if (process.env.NODE_ENV === "production") {
      if (pathname.startsWith("/api/")) {
        return NextResponse.json({ detail: "Company page not configured" }, { status: 503 });
      }
      return new NextResponse("Company page not configured", { status: 503 });
    }
    return NextResponse.next();
  }

  const cookie = req.cookies.get(COOKIE_NAME)?.value || "";
  const expected = await sha256Hex(password);
  const ok = cookie && cookie === expected;

  if (ok) {
    return NextResponse.next();
  }

  // For API routes, return 401 JSON (don't redirect).
  if (pathname.startsWith("/api/")) {
    return NextResponse.json({ detail: "Unauthorized" }, { status: 401 });
  }

  const loginUrl = req.nextUrl.clone();
  loginUrl.pathname = "/company/login";
  loginUrl.searchParams.set("next", pathname);
  return NextResponse.redirect(loginUrl);
}

export const config = {
  matcher: ["/company/:path*", "/api/company/:path*"],
};

