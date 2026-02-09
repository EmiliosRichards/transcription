import { NextRequest, NextResponse } from "next/server";
import crypto from "crypto";

export const runtime = "nodejs";

const COOKIE_NAME = "company_auth";

function sha256Hex(input: string) {
  return crypto.createHash("sha256").update(input, "utf8").digest("hex");
}

export async function POST(req: NextRequest) {
  const passwordEnv = (process.env.COMPANY_PAGE_PASSWORD || "").trim();
  if (!passwordEnv) {
    return NextResponse.json({ detail: "Company page not configured" }, { status: 503 });
  }

  let body: any = null;
  try {
    body = await req.json();
  } catch {
    body = null;
  }
  const password = String(body?.password || "").trim();
  if (!password || password !== passwordEnv) {
    return NextResponse.json({ detail: "Invalid password" }, { status: 401 });
  }

  const res = NextResponse.json({ ok: true });
  res.cookies.set({
    name: COOKIE_NAME,
    value: sha256Hex(passwordEnv),
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 60 * 60 * 24 * 14, // 14 days
  });
  return res;
}

