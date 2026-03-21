import { Link, useNavigate, useLocation } from 'react-router-dom';
import { motion } from 'framer-motion';

export default function Navbar() {
  const navigate = useNavigate();
  const location = useLocation();

  const handleLogout = () => {
    localStorage.removeItem('jobcraft_token');
    navigate('/login');
  };

  const navLinks = [
    { path: '/dashboard', label: 'Dashboard' },
    { path: '/upload', label: 'New Search' },
    { path: '/settings', label: 'Settings' },
  ];

  return (
    <nav className="sticky top-0 z-50 border-b border-border bg-bg-dark/80 backdrop-blur-xl">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6">
        <Link to="/dashboard" className="flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary text-white text-sm font-bold">
            JC
          </div>
          <span className="font-[family-name:var(--font-display)] text-lg font-bold text-text-primary">
            JobCraft
          </span>
        </Link>

        <div className="hidden items-center gap-1 sm:flex">
          {navLinks.map((link) => {
            const isActive = location.pathname === link.path;
            return (
              <Link
                key={link.path}
                to={link.path}
                className={`relative rounded-lg px-3.5 py-2 text-sm font-medium transition-colors ${
                  isActive
                    ? 'text-primary'
                    : 'text-text-secondary hover:text-text-primary'
                }`}
              >
                {link.label}
                {isActive && (
                  <motion.div
                    layoutId="nav-indicator"
                    className="absolute inset-x-1 -bottom-[1.05rem] h-0.5 rounded-full bg-primary"
                    transition={{ type: 'spring', stiffness: 500, damping: 35 }}
                  />
                )}
              </Link>
            );
          })}
        </div>

        <button
          onClick={handleLogout}
          className="rounded-lg border border-border px-3.5 py-1.5 text-sm text-text-secondary transition-colors hover:border-danger hover:text-danger"
        >
          Sign Out
        </button>
      </div>
    </nav>
  );
}
