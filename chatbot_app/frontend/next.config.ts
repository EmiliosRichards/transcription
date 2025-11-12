import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  env: {
    NEXT_PUBLIC_API_BASE_URL: process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000",
    API_BASE_URL_SERVER: process.env.API_BASE_URL_SERVER || "http://127.0.0.1:8000",
  },
  async rewrites() {
    // Prefer private domain for server-to-server traffic if provided
    let backendUrl = (process.env.API_BASE_URL_SERVER || process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000").trim();
    const hasScheme = backendUrl.startsWith("http://") || backendUrl.startsWith("https://");
    if (process.env.NODE_ENV === "production" && !hasScheme) {
      // Decide based on host when scheme is missing
      const hostCandidate = backendUrl.split("/")[0];
      const hostNoPort = hostCandidate.split(":")[0];
      const isPrivateHost = hostNoPort === "railway.internal" || hostNoPort.endsWith(".railway.internal");
      backendUrl = `${isPrivateHost ? "http" : "https"}://${backendUrl}`;
    }
    // Normalize and auto-append port 8080 for Railway private domains when missing
    try {
      const u = new URL(backendUrl);
      // Do not force a port; Railway private domains route to the correct internal port
      // Use origin (scheme://host[:port]) to avoid duplicate slashes
      backendUrl = u.origin;
    } catch {
      // leave as-is if URL parsing fails
    }
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },
  eslint: {
    ignoreDuringBuilds: true,
  },
  experimental: {
    serverActions: {
      allowedOrigins: (() => {
        const origins = ["localhost:5000", "127.0.0.1:5000"];
        // Add Replit domain
        if (process.env.REPLIT_DEV_DOMAIN) {
          origins.push(`https://${process.env.REPLIT_DEV_DOMAIN}`);
        }
        // Add Railway domain
        if (process.env.RAILWAY_PUBLIC_DOMAIN) {
          origins.push(`https://${process.env.RAILWAY_PUBLIC_DOMAIN}`);
        }
        return origins;
      })(),
    },
  },
};

export default nextConfig;
