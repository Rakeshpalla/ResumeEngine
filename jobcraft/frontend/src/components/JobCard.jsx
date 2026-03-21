import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import ScoreRing from './ScoreRing';

function getGradeStyle(grade) {
  switch (grade) {
    case 'A': return 'bg-success/15 text-success border-success/30';
    case 'B': return 'bg-primary/15 text-primary border-primary/30';
    case 'C': return 'bg-warning/15 text-warning border-warning/30';
    default:  return 'bg-danger/15 text-danger border-danger/30';
  }
}

function ScoreBar({ label, value }) {
  const color =
    value >= 85 ? 'bg-success' :
    value >= 70 ? 'bg-primary' :
    value >= 55 ? 'bg-warning' : 'bg-danger';

  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-16 shrink-0 text-text-secondary">{label}</span>
      <div className="h-1.5 flex-1 rounded-full bg-border">
        <motion.div
          className={`h-full rounded-full ${color}`}
          initial={{ width: 0 }}
          animate={{ width: `${value}%` }}
          transition={{ duration: 0.8, ease: 'easeOut' }}
        />
      </div>
      <span className="w-8 text-right text-text-secondary">{Math.round(value)}</span>
    </div>
  );
}

export default function JobCard({ job, index = 0 }) {
  const initials = (job.company || '??')
    .split(' ')
    .map((w) => w[0])
    .join('')
    .slice(0, 2)
    .toUpperCase();

  const portalColors = {
    linkedin: '#0A66C2',
    indeed: '#2164F3',
    naukri: '#4A90D9',
    glassdoor: '#0CAA41',
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: index * 0.05 }}
      className="group flex flex-col rounded-xl border border-border bg-bg-card p-5 transition-colors hover:border-primary/40"
    >
      <div className="mb-4 flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-sm font-bold text-white"
            style={{ backgroundColor: portalColors[job.portal] || '#6366F1' }}
          >
            {initials}
          </div>
          <div className="min-w-0">
            <h3 className="truncate text-sm font-semibold text-text-primary">{job.title}</h3>
            <p className="truncate text-xs text-text-secondary">{job.company}</p>
          </div>
        </div>
        <span className={`shrink-0 rounded-md border px-2 py-0.5 text-xs font-bold ${getGradeStyle(job.grade)}`}>
          {job.grade}
        </span>
      </div>

      <div className="mb-4 flex items-center gap-3 text-xs text-text-secondary">
        <span>📍 {job.location || 'N/A'}</span>
        <span>•</span>
        <span>{job.date_posted || 'Recent'}</span>
      </div>

      <div className="mb-4 flex justify-center">
        <ScoreRing score={job.composite_score} size={90} strokeWidth={7} />
      </div>

      <div className="mb-4 space-y-2">
        <ScoreBar label="ATS" value={job.ats_score} />
        <ScoreBar label="Keyword" value={job.keyword_score} />
        <ScoreBar label="Fit" value={job.experience_fit_score} />
        <ScoreBar label="Hook" value={job.recruiter_hook_score} />
      </div>

      <div className="mt-auto flex gap-2">
        <Link
          to={`/jobs/${job.id}`}
          className="flex-1 rounded-lg bg-primary/10 py-2 text-center text-sm font-medium text-primary transition-colors hover:bg-primary/20"
        >
          View Resume
        </Link>
        {job.apply_url && (
          <a
            href={job.apply_url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex-1 rounded-lg bg-success/10 py-2 text-center text-sm font-medium text-success transition-colors hover:bg-success/20"
          >
            Apply Now
          </a>
        )}
      </div>
    </motion.div>
  );
}
