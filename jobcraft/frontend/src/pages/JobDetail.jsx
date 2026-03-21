import { useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { useJobDetail, useRegenerateResume } from '../hooks/useJobs';
import Navbar from '../components/Navbar';
import ScoreRing from '../components/ScoreRing';
import ResumePreview from '../components/ResumePreview';

function ScoreCard({ label, score, reasoning }) {
  const color =
    score >= 85 ? 'text-success' :
    score >= 70 ? 'text-primary' :
    score >= 55 ? 'text-warning' : 'text-danger';

  return (
    <div className="rounded-xl border border-border bg-bg-card p-4">
      <div className="mb-1 flex items-center justify-between">
        <span className="text-xs font-medium text-text-secondary">{label}</span>
        <span className={`font-[family-name:var(--font-display)] text-lg font-bold ${color}`}>
          {Math.round(score)}
        </span>
      </div>
      {reasoning && (
        <p className="mt-2 text-xs leading-relaxed text-text-secondary">{reasoning}</p>
      )}
    </div>
  );
}

export default function JobDetail() {
  const { id } = useParams();
  const { data: job, isLoading, error } = useJobDetail(id);
  const regenerate = useRegenerateResume();
  const [activeTab, setActiveTab] = useState('resume');

  if (isLoading) {
    return (
      <div className="min-h-screen">
        <Navbar />
        <div className="flex justify-center py-20">
          <span className="h-8 w-8 animate-spin rounded-full border-2 border-primary/30 border-t-primary" />
        </div>
      </div>
    );
  }

  if (error || !job) {
    return (
      <div className="min-h-screen">
        <Navbar />
        <div className="mx-auto max-w-3xl px-4 py-12 text-center">
          <p className="text-lg text-danger">Job not found.</p>
          <Link to="/dashboard" className="mt-4 inline-block text-sm text-primary hover:underline">
            Back to Dashboard
          </Link>
        </div>
      </div>
    );
  }

  const handleDownload = async (format = 'pdf') => {
    const token = localStorage.getItem('jobcraft_token');
    if (!token) return;
    try {
      const response = await fetch(`/api/jobs/${id}/download?format=${format}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) {
        throw new Error(`Download failed (${response.status})`);
      }
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${(job.company || 'Company').replace(/\s+/g, '_')}_${(job.title || 'Resume').replace(/\s+/g, '_')}.${format}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      // Keep UX simple and explicit for failed downloads.
      window.alert('Download failed. Please try again.');
      console.error(err);
    }
  };

  return (
    <div className="min-h-screen">
      <Navbar />
      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
        {/* Breadcrumb */}
        <Link to="/dashboard" className="mb-6 inline-flex items-center gap-1 text-sm text-text-secondary hover:text-primary">
          ← Back to Dashboard
        </Link>

        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-6 flex flex-wrap items-start justify-between gap-4"
        >
          <div>
            <h1 className="font-[family-name:var(--font-display)] text-2xl font-bold">
              {job.title}
            </h1>
            <p className="mt-1 text-text-secondary">
              {job.company} · {job.location} · {job.portal}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <ScoreRing score={job.composite_score} size={64} strokeWidth={5} />
            <span className={`rounded-lg border px-3 py-1 text-lg font-bold ${
              job.grade === 'A' ? 'border-success/30 bg-success/15 text-success' :
              job.grade === 'B' ? 'border-primary/30 bg-primary/15 text-primary' :
              job.grade === 'C' ? 'border-warning/30 bg-warning/15 text-warning' :
              'border-danger/30 bg-danger/15 text-danger'
            }`}>
              {job.grade}
            </span>
          </div>
        </motion.div>

        {/* Mobile Tab Switcher */}
        <div className="mb-6 flex gap-1 rounded-lg bg-bg-surface p-1 lg:hidden">
          {['resume', 'description'].map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`flex-1 rounded-md py-2 text-sm font-medium capitalize transition-colors ${
                activeTab === tab ? 'bg-primary text-white' : 'text-text-secondary'
              }`}
            >
              {tab === 'resume' ? 'Tailored Resume' : 'Job Description'}
            </button>
          ))}
        </div>

        {/* Split Layout */}
        <div className="grid gap-6 lg:grid-cols-5">
          {/* Left: Job Description */}
          <div className={`lg:col-span-2 ${activeTab === 'description' ? '' : 'hidden lg:block'}`}>
            <div className="sticky top-20 space-y-4">
              <div className="rounded-xl border border-border bg-bg-card p-5">
                <h2 className="mb-3 font-[family-name:var(--font-display)] text-sm font-semibold uppercase tracking-wider text-text-secondary">
                  Job Description
                </h2>
                <div className="max-h-[60vh] overflow-y-auto text-sm leading-relaxed text-text-primary/80 whitespace-pre-wrap">
                  {job.description || 'No description available.'}
                </div>
              </div>

              {job.apply_url && (
                <a
                  href={job.apply_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="block rounded-xl bg-success py-3 text-center text-sm font-bold text-white transition-colors hover:bg-success/90"
                >
                  Apply on {job.portal || 'Portal'} →
                </a>
              )}
            </div>
          </div>

          {/* Right: Resume + Scores */}
          <div className={`lg:col-span-3 space-y-6 ${activeTab === 'resume' ? '' : 'hidden lg:block'}`}>
            {/* Scores */}
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <ScoreCard label="ATS Score" score={job.ats_score} />
              <ScoreCard label="Keyword Match" score={job.keyword_score} />
              <ScoreCard label="Experience Fit" score={job.experience_fit_score} reasoning={job.experience_fit_reasoning} />
              <ScoreCard label="Recruiter Hook" score={job.recruiter_hook_score} reasoning={job.recruiter_hook_reasoning} />
            </div>

            {/* Tailoring Notes */}
            {job.tailoring_notes && (
              <div className="rounded-xl border border-primary/20 bg-primary/5 p-4">
                <h3 className="mb-1 text-xs font-semibold uppercase tracking-wider text-primary">
                  AI Reasoning
                </h3>
                <p className="text-sm text-text-primary/80">{job.tailoring_notes}</p>
              </div>
            )}

            {/* Tailored Resume */}
            <ResumePreview resume={job.tailored_resume} />

            {/* Actions */}
            <div className="flex flex-wrap gap-3">
              <button
                onClick={() => handleDownload('pdf')}
                className="rounded-lg bg-primary px-6 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-primary-light"
              >
                ⬇ Download Resume PDF
              </button>
              <button
                onClick={() => handleDownload('docx')}
                className="rounded-lg bg-bg-surface px-6 py-2.5 text-sm font-semibold text-text-primary transition-colors hover:bg-bg-card"
              >
                ⬇ Download Resume DOCX
              </button>
              <button
                onClick={() => regenerate.mutate(Number(id))}
                disabled={regenerate.isPending}
                className="rounded-lg border border-border px-6 py-2.5 text-sm font-semibold text-text-secondary transition-colors hover:border-primary hover:text-primary disabled:opacity-50"
              >
                {regenerate.isPending ? 'Regenerating...' : '🔄 Regenerate Resume'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
