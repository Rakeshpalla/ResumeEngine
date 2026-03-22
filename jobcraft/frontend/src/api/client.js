import axios from 'axios';
import { isPublicDemo } from '../config';

// Production: set VITE_API_BASE_URL in Vercel (e.g. https://your-api.railway.app/api)
// Dev: leave unset to use Vite proxy (/api -> localhost:8080)
const baseURL = import.meta.env.VITE_API_BASE_URL || '/api';

const api = axios.create({
  baseURL,
  headers: { 'Content-Type': 'application/json' },
});

// Attach JWT token to every request if present in localStorage
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('jobcraft_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// On 401, clear token and redirect to login
api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401 && !isPublicDemo) {
      localStorage.removeItem('jobcraft_token');
      if (window.location.pathname !== '/login') {
        window.location.href = '/login';
      }
    }
    return Promise.reject(err);
  }
);

export default api;
