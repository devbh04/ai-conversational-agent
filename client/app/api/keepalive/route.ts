import { NextResponse } from "next/server";

export async function GET() {
  const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8001";
  try {
    const res = await fetch(`${backendUrl}/health`, { next: { revalidate: 0 } });
    const data = await res.json();
    return NextResponse.json({ ok: true, backend: data });
  } catch {
    return NextResponse.json({ ok: false, error: "Backend unreachable" }, { status: 503 });
  }
}
