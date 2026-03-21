import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import Navbar from '../components/Navbar';
import { useProcessSelectedJobs, useSearchCandidates, useSearchStatus } from '../hooks/useJobs';

function PortalLabel({ portal }) {
  const map = {
    linkedin: 'LinkedIn',
    indeed: 'Indeed',
    naukri: 'Naukri',
  };
  return <span className="font-semibold">{map[portal] || portal}</span>;
}

export default function SelectJobs() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const runId = searchParams.get('run_id');

  const { data: statusData } = useSearchStatus();
  const { data, isLoading, error } = useSearchCandidates(runId);
  const candidates = data?.candidates || [];

  const [selectedIds, setSelectedIds] = useState([]);
  const [selectionError, setSelectionError] = useState('');

  const grouped = useMemo(() => {
    const groups = {};
    for (const c of candidates) {
      const p = c.portal || 'unknown';
      groups[p] = groups[p] || [];
      groups[p].push(c);
    }
    return groups;
  }, [candidates]);

  useEffect(() => {
    if (!candidates.length) return;
    // Default behavior: select all shortlisted jobs once.
    setSelectedIds((prev) => (prev.length ? prev : candidates.map((c) => c.id)));
  }, [candidates]);

  const toggle = (jobId) => {
    setSelectedIds((prev) => (prev.includes(jobId) ? prev.filter((id) => id !== jobId) : [...prev, jobId]));
  };

  const processSelected = useProcessSelectedJobs(runId);

  const handleProcess = async () => {
    setSelectionError('');
    if (!selectedIds.length) {
      setSelectionError('Please select at least one job.');
      return;
    }
    try {
      await processSelected.mutateAsync(selectedIds);
      navigate('/loading');
    } catch (e) {
      setSelectionError(e?.response?.data?.detail || 'Failed to create resumes.');
    }
  };

  const runStatus = data?.run_status || '';
  const runMsg = data?.status_message || '';
  const progress = data?.progress ?? statusData?.progress ?? 0;

  return (
    <div className="min-h-screen">
      <Navbar />
      <div className="mx-auto max-w-5xl px-4 py-8 sm:px-6">
        <div className="mb-6">
          <h1 className="font-[family-name:var(--font-display)] text-2xl font-bold">Choose Jobs to Tailor</h1>
          <p className="mt-1 text-sm text-text-secondary">
            Shortlisted top jobs appear here. Select which ones you want tailored resumes for.
          </p>
        </div>

        <div className="mb-6 rounded-xl border border-border bg-bg-card p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-text-primary">Agent Status</div>
              <div className="mt-1 text-sm text-text-secondary">{runMsg || (isLoading ? 'Waiting...' : 'Ready')}</div>
            </div>
            <div className="text-right">
              <div className="text-xs text-text-secondary">Progress</div>
              <div className="text-lg font-bold text-primary">{progress}%</div>
            </div>
          </div>
        </div>

        {error && (
          <div className="mb-4 rounded-xl border border-danger/30 bg-danger/10 p-4 text-sm text-danger">
            Failed to load candidates.
          </div>
        )}

        {runStatus === 'failed' && (
          <div className="mb-4 rounded-xl border border-danger/30 bg-danger/10 p-4 text-sm text-danger">
            {runMsg || 'Agent failed. Please start a new search.'}
          </div>
        )}

        {!candidates.length && !error && runStatus !== 'failed' && (
          <div className="rounded-xl border border-border bg-bg-card p-8 text-center">
            <div className="text-4xl">🔎</div>
            <div className="mt-3 font-semibold">Searching for jobs…</div>
            <div className="mt-1 text-sm text-text-secondary">This usually completes in under a minute.</div>
          </div>
        )}

        {candidates.length > 0 && (
          <>
            {Object.keys(grouped).map((portal) => (
              <div key={portal} className="mb-6">
                <div className="mb-3 text-sm font-semibold text-text-secondary">
                  Portal: <PortalLabel portal={portal} />
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                  {grouped[portal].map((c) => (
                    <div key={c.id} className="rounded-xl border border-border bg-bg-card p-4">
                      <label className="flex cursor-pointer items-start gap-3">
                        <input
                          type="checkbox"
                          checked={selectedIds.includes(c.id)}
                          onChange={() => toggle(c.id)}
                          className="mt-1 h-4 w-4 accent-primary"
                        />
                        <div className="min-w-0 flex-1">
                          <div className="truncate text-sm font-semibold text-text-primary">{c.title}</div>
                          <div className="truncate text-xs text-text-secondary">{c.company}</div>
                          <div className="mt-1 text-xs text-text-secondary">{c.location}</div>
                          <div className="mt-2 text-xs">
                            <span className="font-semibold text-text-primary">ATS:</span>{' '}
                            <span className="font-bold text-primary">{Math.round(c.ats_score || 0)}%</span>
                          </div>
                        </div>
                      </label>
                    </div>
                  ))}
                </div>
              </div>
            ))}

            {selectionError && (
              <div className="mb-4 rounded-xl border border-danger/30 bg-danger/10 p-4 text-sm text-danger">
                {selectionError}
              </div>
            )}

            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="text-sm text-text-secondary">
                Selected: <span className="font-semibold text-text-primary">{selectedIds.length}</span>
              </div>
              <button
                onClick={handleProcess}
                disabled={processSelected.isPending}
                className="rounded-xl bg-primary px-6 py-3 text-sm font-semibold text-white transition-colors hover:bg-primary-light disabled:opacity-60"
              >
                {processSelected.isPending ? 'Creating resumes...' : 'Create Tailored Resumes'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

