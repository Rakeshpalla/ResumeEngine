import { motion } from 'framer-motion';

function getScoreColor(score) {
  if (score >= 85) return '#10B981';
  if (score >= 70) return '#6366F1';
  if (score >= 55) return '#F59E0B';
  return '#EF4444';
}

export default function ScoreRing({ score = 0, size = 80, strokeWidth = 6, label }) {
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (score / 100) * circumference;
  const color = getScoreColor(score);

  return (
    <div className="relative flex flex-col items-center">
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="var(--color-border)"
          strokeWidth={strokeWidth}
        />
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={circumference}
          initial={{ strokeDashoffset: circumference }}
          animate={{ strokeDashoffset: offset }}
          transition={{ duration: 1, ease: 'easeOut' }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span
          className="font-[family-name:var(--font-display)] text-lg font-bold"
          style={{ color }}
        >
          {Math.round(score)}
        </span>
      </div>
      {label && (
        <span className="mt-1 text-xs text-text-secondary">{label}</span>
      )}
    </div>
  );
}
