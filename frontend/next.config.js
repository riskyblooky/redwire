/** @type {import('next').NextConfig} */
const nextConfig = {
    reactStrictMode: true,
    output: 'standalone',
    // No /api rewrite: nginx routes /api to the backend before a request
    // reaches Next (dev and prod). The old rewrite pointed /api at
    // NEXT_PUBLIC_API_URL, which is itself /api — a loop that never ran.
};

module.exports = nextConfig;
