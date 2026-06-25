import type { NextConfig } from "next";

const apiProxyBase = (
  process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8001/api/v1"
).replace(/\/$/, "");

const nextConfig: NextConfig = {
  allowedDevOrigins: ["127.0.0.1"],
  serverExternalPackages: ["playwright-core"],
  turbopack: {
    root: __dirname,
  },
  async rewrites() {
    return [
      {
        source: '/api/v1/:path*',
        destination: `${apiProxyBase}/:path*`,
      },
    ];
  },
  async redirects() {
    return [
      {
        source: '/entities',
        destination: '/dashboard',
        permanent: false,
      },
      {
        source: '/touchpoints',
        destination: '/dashboard',
        permanent: false,
      },
      {
        source: '/reports',
        destination: '/dashboard',
        permanent: false,
      },
    ];
  },
};

export default nextConfig;
