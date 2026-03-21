import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useSearchStatus } from '../hooks/useJobs';
import LoadingAgent from '../components/LoadingAgent';
import Navbar from '../components/Navbar';

export default function Loading() {
  const navigate = useNavigate();
  const { data: status } = useSearchStatus();

  useEffect(() => {
    if (status && !status.running && status.progress >= 100) {
      const timer = setTimeout(() => navigate('/dashboard'), 1500);
      return () => clearTimeout(timer);
    }
  }, [status, navigate]);

  return (
    <div className="min-h-screen">
      <Navbar />
      <LoadingAgent />
    </div>
  );
}
