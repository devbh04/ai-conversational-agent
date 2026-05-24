import { NextRequest, NextResponse } from "next/server";

export function middleware(req: NextRequest) {
  // Public routes — skip auth
  const publicPaths = ["/api/auth", "/api/keepalive"];
  if (publicPaths.some((p) => req.nextUrl.pathname.startsWith(p))) {
    return NextResponse.next();
  }

  // Allow static assets
  if (
    req.nextUrl.pathname.startsWith("/_next") ||
    req.nextUrl.pathname.startsWith("/favicon")
  ) {
    return NextResponse.next();
  }

  // Check auth cookie
  const authCookie = req.cookies.get("auth");
  if (!authCookie || authCookie.value !== "authenticated") {
    // For API routes, return 401
    if (req.nextUrl.pathname.startsWith("/api/")) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    // The page component handles login UI client-side, so let it through
    return NextResponse.next();
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
