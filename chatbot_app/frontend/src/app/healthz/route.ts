import { NextResponse } from "next/server";

// Simple healthcheck endpoint for Railway.
// Must not depend on backend connectivity or auth.
export async function GET() {
  return NextResponse.json({ ok: true }, { status: 200 });
}

