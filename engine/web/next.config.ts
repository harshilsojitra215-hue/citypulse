import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  turbopack: {
    // this folder is the project root (there is another lockfile higher up on this machine)
    root: __dirname,
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
