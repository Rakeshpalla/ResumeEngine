import { useState, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { useJobs } from '../hooks/useJobs';
import Navbar from '../components/Navbar';
import JobCard from '../components/JobCard';

export default function Dashboard() {
  const [sortBy, setSortBy] = useState('composite_score');
  const [gradeFilter, setGradeFilter] = useState('');
  const [search, setSearch] = useState('');

  const { data: jobs = [], isLoading, error } = useJobs({
    sortBy,
    grade: gradeFilter || undefined,
    search: search || undefined,
  });

  const stats = useMemo(() => {
    if (!jobs.length) return { total: 0, topScore: 0, tailored: 0 };
    return {
      total: jobs.length,
      topScore: Math.max(...jobs.map((j) => j.composite_score)),
      tailored: jobs.length,
    };
  }, [jobs]);

  const grades = ['A', 'B', 'C', 'D'];

  return (
    <div className="min-h-screen">
      <Navbar />
      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
        {/* Header */}
        <div className="mb-8 flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="font-[family-name:var(--font-display)] text-3xl font-bold">
              Dashboard
            </h1>
            <p className="mt-1 text-sm text-text-secondary">
              Your ranked job opportunities
            </p>
          </div>
          <Link
            to="/upload"
            className="rounded-lg bg-primary px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-primary-light"
          >
            + New Search
          </Link>
        </div>

        {/* Summary Cards */}
        <div className="mb-8 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[
            { label: 'Jobs Found', value: stats.total, icon: '📋' },
            { label: 'Top Score', value: stats.topScore.toFixed(1), icon: '🏆' },
            { label: 'Resumes Tailored', value: stats.tailored, icon: '📝' },
            { label: 'Grade A Jobs', value: jobs.filter((j) => j.grade === 'A').length, icon: '⭐' },
          ].map((card) => (
            <motion.div
              key={card.label}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="rounded-xl border border-border bg-bg-card p-4"
            >
              <div className="mb-1 text-2xl">{card.icon}</div>
              <p className="font-[family-name:var(--font-display)] text-2xl font-bold text-text-primary">
                {card.value}
              </p>
              <p className="text-xs text-text-secondary">{card.label}</p>
            </motion.div>
          ))}
        </div>

        {/* Filters */}
        <div className="mb-6 flex flex-wrap items-center gap-3">
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value)}
            className="rounded-lg border border-border bg-bg-surface px-3 py-2 text-sm text-text-primary outline-none focus:border-primary"
          >
            <option value="composite_score">Sort: Composite Score</option>
            <option value="ats_score">Sort: ATS Score</option>
            <option value="keyword_score">Sort: Keyword Match</option>
            <option value="created_at">Sort: Date Added</option>
          </select>

          <div className="flex gap-1">
            <button
              onClick={() => setGradeFilter('')}
              className={`rounded-lg px-3 py-2 text-xs font-medium transition-colors ${
                !gradeFilter ? 'bg-primary text-white' : 'bg-bg-surface text-text-secondary hover:text-text-primary'
              }`}
            >
              All
            </button>
            {grades.map((g) => (
              <button
                key={g}
                onClick={() => setGradeFilter(gradeFilter === g ? '' : g)}
                className={`rounded-lg px-3 py-2 text-xs font-medium transition-colors ${
                  gradeFilter === g ? 'bg-primary text-white' : 'bg-bg-surface text-text-secondary hover:text-text-primary'
                }`}
              >
                {g}
              </button>
            ))}
          </div>

          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search company or title..."
            className="rounded-lg border border-border bg-bg-surface px-3 py-2 text-sm text-text-primary outline-none placeholder:text-text-secondary/50 focus:border-primary"
          />
        </div>

        {/* Jobs Grid */}
        {isLoading ? (
          <div className="flex justify-center py-20">
            <span className="h-8 w-8 animate-spin rounded-full border-2 border-primary/30 border-t-primary" />
          </div>
        ) : error ? (
          <div className="rounded-xl border border-danger/30 bg-danger/10 p-8 text-center text-sm text-danger">
            Failed to load jobs. Please try again.
          </div>
        ) : jobs.length === 0 ? (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="rounded-xl border border-border bg-bg-card p-12 text-center"
          >
            <p className="mb-2 text-4xl">🔍</p>
            <p className="text-lg font-medium text-text-primary">No jobs found yet</p>
            <p className="mt-1 text-sm text-text-secondary">
              Start a new search to discover opportunities.
            </p>
            <Link
              to="/upload"
              className="mt-4 inline-block rounded-lg bg-primary px-6 py-2.5 text-sm font-semibold text-white hover:bg-primary-light"
            >
              Start Searching
            </Link>
          </motion.div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {jobs.map((job, index) => (
              <JobCard key={job.id} job={job} index={index} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
