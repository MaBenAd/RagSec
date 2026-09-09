import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

async function tokenIsAdmin(token: string): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/v1/auth/me`, {
      method: "GET",
      headers: {
        Authorization: `Bearer ${token}`,
      },
      cache: "no-store",
    });

    if (!response.ok) return false;
    const payload = (await response.json()) as { role?: string };
    return payload.role === "admin";
  } catch {
    return false;
  }
}

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  const isProtected =
    pathname === "/chat" ||
    pathname.startsWith("/chat/") ||
    pathname === "/admin" ||
    pathname.startsWith("/admin/") ||
    pathname === "/profile" ||
    pathname.startsWith("/profile/");

  if (!isProtected) {
    return NextResponse.next();
  }

  const token = request.cookies.get("access_token")?.value || request.cookies.get("token")?.value;
  if (!token) {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  if (pathname === "/admin" || pathname.startsWith("/admin/")) {
    const isAdmin = await tokenIsAdmin(token);
    if (!isAdmin) {
      return NextResponse.redirect(new URL("/chat", request.url));
    }
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/chat", "/chat/:path*", "/admin", "/admin/:path*", "/profile", "/profile/:path*"],
};
