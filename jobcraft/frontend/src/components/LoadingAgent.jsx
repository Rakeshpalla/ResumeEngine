import { motion } from 'framer-motion';
import { useSearchStatus } from '../hooks/useJobs';

export default function LoadingAgent() {
  const { data: status } = useSearchStatus();

  const progress = status?.progress || 0;
  const messages = status?.messages || [];

  return (
    <div className="flex min-h-[80vh] flex-col items-center justify-center px-4">
      {/* Animated Agent Icon */}
      <motion.div
        animate={{ scale: [1, 1.05, 1], rotate: [0, 5, -5, 0] }}
        transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
        className="mb-8 flex h-24 w-24 items-center justify-center rounded-2xl bg-primary/20 text-5xl"
      >
        🤖
      </motion.div>

      <h2 className="mb-2 font-[family-name:var(--font-display)] text-2xl font-bold text-text-primary">
        Agent is working...
      </h2>
      <p className="mb-8 text-sm text-text-secondary">
        Sit tight — we're searching, tailoring, and scoring your opportunities.
      </p>

      {/* Progress Bar */}
      <div className="mb-8 w-full max-w-md">
        <div className="mb-2 flex items-center justify-between text-sm">
          <span className="text-text-secondary">Progress</span>
          <span className="font-[family-name:var(--font-display)] font-bold text-primary">
            {progress}%
          </span>
        </div>
        <div className="h-2.5 overflow-hidden rounded-full bg-border">
          <motion.div
            className="h-full rounded-full bg-primary"
            initial={{ width: 0 }}
            animate={{ width: `${progress}%` }}
            transition={{ duration: 0.5, ease: 'easeOut' }}
          />
        </div>
      </div>

      {/* Status Log */}
      <div className="w-full max-w-md rounded-xl border border-border bg-bg-card p-4">
        <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-text-secondary">
          Live Status
        </h3>
        <div className="max-h-52 space-y-1.5 overflow-y-auto">
          {messages.map((msg, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              className="text-sm text-text-primary/80"
            >
              {msg}
            </motion.div>
          ))}
          {messages.length === 0 && (
            <p className="text-sm text-text-secondary">Waiting for updates...</p>
          )}
        </div>
      </div>
    </div>
  );
}
