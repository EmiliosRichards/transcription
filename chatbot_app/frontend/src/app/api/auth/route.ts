import { NextRequest, NextResponse } from "next/server";
import crypto from "crypto";

export const runtime = "nodejs";

const COOKIE_NAME = "app_auth";

function sha256Hex(input: string) {
  return crypto.createHash("sha256").update(input, "utf8").digest("hex");
}

function parseMaxAgeSeconds() {
  const raw = String(process.env.APP_AUTH_MAX_AGE_SECONDS || "").trim();
  if (!raw) return null; // session cookie
  const n = Number(raw);
  if (!Number.isFinite(n) || n <= 0) return null;
  return Math.floor(n);
}

export async function POST(req: NextRequest) {
  const expectedUser = (process.env.APP_AUTH_USERNAME || "guest").trim();
  const expectedPass = (process.env.APP_AUTH_PASSWORD || "").trim();
  if (!expectedPass) {
    return NextResponse.json({ detail: "App auth not configured" }, { status: 503 });
  }

  let body: any = null;
  try {
    body = await req.json();
  } catch {
    body = null;
  }

  const username = String(body?.username || "").trim() || "guest";
  const password = String(body?.password || "").trim();

  if (!password || username !== expectedUser || password !== expectedPass) {
    return NextResponse.json({ detail: "Invalid credentials" }, { status: 401 });
  }

  const res = NextResponse.json({ ok: true });
  const maxAge = parseMaxAgeSeconds();

  res.cookies.set({
    name: COOKIE_NAME,
    value: sha256Hex(`${expectedUser}:${expectedPass}`),
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    ...(maxAge ? { maxAge } : {}),
  });

  return res;
}

