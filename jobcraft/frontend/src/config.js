/** True when built with VITE_PUBLIC_DEMO_MODE=true (skip login; for public demo / Vercel UI). */
export const isPublicDemo =
  import.meta.env.VITE_PUBLIC_DEMO_MODE === 'true' ||
  import.meta.env.VITE_PUBLIC_DEMO_MODE === '1';
