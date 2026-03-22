/**
 * Human-readable message for failed API calls (network, 404, CORS, etc.).
 */
export function describeApiError(err, fallback = 'Request failed.') {
  if (!err) return fallback;
  const msg = err.response?.data?.detail;
  if (typeof msg === 'string' && msg.trim()) return msg;
  if (Array.isArray(msg)) return msg.map((m) => m?.msg || m).join(' ') || fallback;

  const code = err.code || err?.cause?.code;
  if (code === 'ERR_NETWORK' || code === 'ECONNABORTED') {
    return (
      'Cannot reach the JobCraft API. Deploy the backend and set VITE_API_BASE_URL in Vercel ' +
      '(e.g. https://your-api.railway.app/api), plus CORS and PUBLIC_DEMO_MODE on the server.'
    );
  }

  const status = err.response?.status;
  if (status === 404) {
    return (
      'API not found (404). The Vercel site only hosts the UI — point VITE_API_BASE_URL to your FastAPI server.'
    );
  }
  if (status === 401 || status === 403) {
    return err.response?.data?.detail || 'Not authorized. Check API settings (PUBLIC_DEMO_MODE / CORS).';
  }

  if (!err.response) {
    return (
      'No response from server. Check VITE_API_BASE_URL, that the API is running, and CORS allows this site.'
    );
  }

  return fallback;
}
