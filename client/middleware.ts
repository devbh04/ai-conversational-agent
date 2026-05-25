import { NextRequest, NextResponse } from "next/server";

export function middleware(req: NextRequest) {
  // Only protect /admin routes with auth
  if (
    req.nextUrl.pathname.startsWith("/admin") ||
    req.nextUrl.pathname.startsWith("/api/admin")
  ) {
    const authCookie = req.cookies.get("auth");
    if (!authCookie || authCookie.value !== "authenticated") {
      if (req.nextUrl.pathname.startsWith("/api/")) {
        return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
      }
      // If we are already on the login page, let it render
      if (req.nextUrl.searchParams.get("login") === "1") {
        return NextResponse.next();
      }
      // Otherwise, redirect to admin with login flag
      const url = new URL("/admin", req.url);
      url.searchParams.set("login", "1");
      return NextResponse.redirect(url);
    }
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/admin/:path*", "/api/admin/:path*"],
};
