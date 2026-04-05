/** @type {import('next').NextConfig} */

const isProd = process.env.NODE_ENV === "production";

const nextConfig = {
  // In production: static export for S3/CloudFront
  // In development: standalone with proxy rewrites
  output: isProd ? "export" : "standalone",

  // Disable image optimization for static export (S3 can't run Next.js server)
  images: {
    unoptimized: true,
  },

  // Only apply proxy rewrites in development (not used in static export)
  ...(isProd ? {} : {
    experimental: {
      proxyTimeout: 300000,
    },
    async rewrites() {
      return [
        {
          source: "/api/:path*",
          destination: `${process.env.BACKEND_URL || "http://backend:8000"}/api/:path*`,
        },
        {
          source: "/health",
          destination: `${process.env.BACKEND_URL || "http://backend:8000"}/health`,
        },
      ];
    },
  }),
};

module.exports = nextConfig;
