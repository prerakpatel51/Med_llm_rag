/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",

  // Allow up to 5 minutes for the backend to respond (covers Ollama cold start)
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
};

module.exports = nextConfig;
