import { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useDropzone } from 'react-dropzone';
import { motion, AnimatePresence } from 'framer-motion';
import { useUploadResume, useStartSearch, useSettings } from '../hooks/useJobs';
import Navbar from '../components/Navbar';

function TagInput({ label, tags, onChange, placeholder }) {
  const [input, setInput] = useState('');

  const addTag = () => {
    const value = input.trim();
    if (value && !tags.includes(value)) {
      onChange([...tags, value]);
    }
    setInput('');
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      addTag();
    }
    if (e.key === 'Backspace' && !input && tags.length) {
      onChange(tags.slice(0, -1));
    }
  };

  return (
    <div>
      <label className="mb-1.5 block text-sm font-medium text-text-secondary">{label}</label>
      <div className="flex flex-wrap items-center gap-1.5 rounded-lg border border-border bg-bg-surface px-3 py-2">
        {tags.map((tag, i) => (
          <span
            key={i}
            className="flex items-center gap-1 rounded-md bg-primary/15 px-2 py-0.5 text-xs font-medium text-primary"
          >
            {tag}
            <button onClick={() => onChange(tags.filter((_, j) => j !== i))} className="text-primary/60 hover:text-primary">
              ×
            </button>
          </span>
        ))}
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          onBlur={addTag}
          placeholder={tags.length === 0 ? placeholder : ''}
          className="min-w-[120px] flex-1 bg-transparent text-sm text-text-primary outline-none placeholder:text-text-secondary/50"
        />
      </div>
    </div>
  );
}

export default function Upload() {
  const navigate = useNavigate();
  const uploadResume = useUploadResume();
  const startSearch = useStartSearch();
  const { data: settings } = useSettings();

  const [file, setFile] = useState(null);
  const [uploaded, setUploaded] = useState(false);
  const [titles, setTitles] = useState(settings?.target_titles || []);
  const [locations, setLocations] = useState(settings?.preferred_locations || []);
  const [portals, setPortals] = useState(settings?.portals || ['linkedin', 'indeed', 'naukri']);
  const [error, setError] = useState('');

  const onDrop = useCallback(async (accepted, rejected) => {
    if (rejected.length) {
      setError('Only PDF and DOCX files under 5MB are allowed.');
      return;
    }
    const f = accepted[0];
    if (f) {
      setFile(f);
      setError('');
      try {
        await uploadResume.mutateAsync(f);
        setUploaded(true);
      } catch (err) {
        setError(err.response?.data?.detail || 'Upload failed.');
      }
    }
  }, [uploadResume]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/pdf': ['.pdf'],
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
    },
    maxSize: 5 * 1024 * 1024,
    maxFiles: 1,
  });

  const togglePortal = (name) => {
    setPortals((prev) =>
      prev.includes(name) ? prev.filter((p) => p !== name) : [...prev, name]
    );
  };

  const handleStart = async () => {
    if (!uploaded && !settings?.base_resume_filename) {
      setError('Please upload your resume first.');
      return;
    }
    if (titles.length === 0) {
      setError('Add at least one target job title.');
      return;
    }
    if (locations.length === 0) {
      setError('Add at least one location.');
      return;
    }
    setError('');
    try {
      const res = await startSearch.mutateAsync({ titles, locations, portals });
      navigate(`/select-jobs?run_id=${encodeURIComponent(res?.run_id)}`);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to start search.');
    }
  };

  const portalOptions = [
    { id: 'linkedin', label: 'LinkedIn', color: '#0A66C2' },
    { id: 'indeed', label: 'Indeed', color: '#2164F3' },
    { id: 'naukri', label: 'Naukri', color: '#4A90D9' },
  ];

  return (
    <div className="min-h-screen">
      <Navbar />
      <div className="mx-auto max-w-2xl px-4 py-12">
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
          <h1 className="mb-2 font-[family-name:var(--font-display)] text-3xl font-bold">
            Start a New Search
          </h1>
          <p className="mb-10 text-text-secondary">
            Upload your resume, set preferences, and let JobCraft find your perfect role.
          </p>

          {/* Step 1 — Resume Upload */}
          <div className="mb-10">
            <h2 className="mb-4 text-lg font-semibold">
              <span className="mr-2 inline-flex h-6 w-6 items-center justify-center rounded-full bg-primary text-xs font-bold text-white">
                1
              </span>
              Upload Resume
            </h2>
            <div
              {...getRootProps()}
              className={`cursor-pointer rounded-xl border-2 border-dashed p-10 text-center transition-colors ${
                isDragActive
                  ? 'border-primary bg-primary/5'
                  : 'border-border hover:border-primary/50'
              }`}
            >
              <input {...getInputProps()} />
              {file ? (
                <div>
                  <p className="text-sm font-medium text-text-primary">
                    {uploaded ? '✓' : '⬆'} {file.name}
                  </p>
                  <p className="mt-1 text-xs text-text-secondary">
                    {(file.size / 1024).toFixed(0)} KB
                    {uploaded && ' — Uploaded successfully'}
                  </p>
                </div>
              ) : (
                <div>
                  <p className="mb-1 text-3xl">📄</p>
                  <p className="text-sm text-text-secondary">
                    Drag & drop your resume here, or <span className="text-primary">browse</span>
                  </p>
                  <p className="mt-1 text-xs text-text-secondary/70">PDF or DOCX, max 5MB</p>
                </div>
              )}
            </div>
            {uploadResume.isPending && (
              <p className="mt-2 text-sm text-primary">Uploading...</p>
            )}
          </div>

          {/* Step 2 — Job Preferences */}
          <div className="mb-10">
            <h2 className="mb-4 text-lg font-semibold">
              <span className="mr-2 inline-flex h-6 w-6 items-center justify-center rounded-full bg-primary text-xs font-bold text-white">
                2
              </span>
              Job Preferences
            </h2>
            <div className="space-y-4 rounded-xl border border-border bg-bg-card p-6">
              <TagInput
                label="Target Job Titles"
                tags={titles}
                onChange={setTitles}
                placeholder="e.g. Product Manager, Software Engineer"
              />
              <TagInput
                label="Preferred Locations"
                tags={locations}
                onChange={setLocations}
                placeholder="e.g. Hyderabad, Remote, San Francisco"
              />
              <div>
                <label className="mb-2 block text-sm font-medium text-text-secondary">
                  Job Portals
                </label>
                <div className="flex flex-wrap gap-2">
                  {portalOptions.map((p) => (
                    <button
                      key={p.id}
                      onClick={() => togglePortal(p.id)}
                      className={`rounded-lg border px-4 py-2 text-sm font-medium transition-colors ${
                        portals.includes(p.id)
                          ? 'border-primary bg-primary/15 text-primary'
                          : 'border-border text-text-secondary hover:border-primary/30'
                      }`}
                    >
                      {p.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>

          <AnimatePresence>
            {error && (
              <motion.p
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                className="mb-4 rounded-lg bg-danger/10 px-4 py-2.5 text-sm text-danger"
              >
                {error}
              </motion.p>
            )}
          </AnimatePresence>

          <button
            onClick={handleStart}
            disabled={startSearch.isPending}
            className="w-full rounded-xl bg-primary py-3.5 text-base font-bold text-white transition-colors hover:bg-primary-light disabled:opacity-60"
          >
            {startSearch.isPending ? 'Starting...' : '🚀 Start Search'}
          </button>
        </motion.div>
      </div>
    </div>
  );
}
