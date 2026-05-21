/** @type {import('next').NextConfig} */
const nextConfig = {
  transpilePackages: ["@voice-to-pdf/types"],
  webpack: (config) => {
    // pdfjs-dist tries to require 'canvas' in Node environments.
    // Aliasing it to false prevents the build error in Next.js SSR.
    config.resolve.alias.canvas = false;
    return config;
  },
};

module.exports = nextConfig;
