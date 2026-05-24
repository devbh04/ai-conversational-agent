import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8001";

export async function GET(req: NextRequest) {
  const agent = req.nextUrl.searchParams.get("agent") || "real_estate";
  const limit = req.nextUrl.searchParams.get("limit") || "50";
  try {
    const res = await fetch(`${BACKEND_URL}/api/admin/calls?agent=${agent}&limit=${limit}`, { cache: "no-store" });
    const data = await res.json();
    return NextResponse.json(data);
  } catch {
    return NextResponse.json({ error: "Backend unreachable" }, { status: 503 });
  }
}
