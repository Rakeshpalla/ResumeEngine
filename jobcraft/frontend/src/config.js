/**
 * Skip login (public demo UI).
 * - Explicit VITE_PUBLIC_DEMO_MODE=false or 0 → require login.
 * - Explicit true/1 → skip login.
 * - Unset: **production builds** (e.g. Vercel) skip login by default; `npm run dev` keeps login.
 *   This avoids relying on .env.production being picked up by every CI setup.
 */
const flag = import.meta.env.VITE_PUBLIC_DEMO_MODE;

export const isPublicDemo =
  flag === 'false' || flag === '0'
    ? false
    : flag === 'true' || flag === '1'
      ? true
      : Boolean(import.meta.env.PROD);
