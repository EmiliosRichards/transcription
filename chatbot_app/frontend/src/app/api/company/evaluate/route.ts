import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";

function normalizeBaseUrl(raw: string) {
  const s = (raw || "").trim().replace(/\/+$/, "");
  if (!s) return "";
  if (s.startsWith("http://") || s.startsWith("https://")) return s;
  return `https://${s}`;
}

export async function POST(req: NextRequest) {
  const backendBase =
    normalizeBaseUrl(process.env.API_BASE_URL_SERVER || "") ||
    normalizeBaseUrl(process.env.NEXT_PUBLIC_API_BASE_URL || "");

  if (!backendBase) {
    return NextResponse.json({ detail: "Backend base URL not configured" }, { status: 500 });
  }

  const apiKey = (process.env.COMPANY_API_KEY || process.env.API_KEY || "").trim();
  if (!apiKey) {
    return NextResponse.json({ detail: "Missing API key config (set COMPANY_API_KEY or API_KEY)" }, { status: 500 });
  }

  const body = await req.text();
  const upstream = await fetch(`${backendBase}/api/company/evaluate`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": apiKey,
    },
    body,
  });

  const text = await upstream.text();
  return new NextResponse(text, {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("content-type") || "application/json" },
  });
}

