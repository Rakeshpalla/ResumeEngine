import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { useSettings, useUpdateSettings } from '../hooks/useJobs';
import Navbar from '../components/Navbar';
import api from '../api/client';

export default function Settings() {
  const { data: settings, isLoading } = useSettings();
  const updateSettings = useUpdateSettings();

  const [apiKey, setApiKey] = useState('');
  const [titles, setTitles] = useState([]);
  const [locations, setLocations] = useState([]);
  const [portals, setPortals] = useState([]);
  const [currentPw, setCurrentPw] = useState('');
  const [newPw, setNewPw] = useState('');
  const [pwMsg, setPwMsg] = useState({ type: '', text: '' });
  const [settingsMsg, setSettingsMsg] = useState('');
  const [clearing, setClearing] = useState(false);

  useEffect(() => {
    if (settings) {
      setTitles(settings.target_titles || []);
      setLocations(settings.preferred_locations || []);
      setPortals(settings.portals || []);
    }
  }, [settings]);

  const handleSaveSettings = async () => {
    try {
      const payload = {
        target_titles: titles,
        preferred_locations: locations,
        portals,
      };
      if (apiKey) payload.anthropic_api_key = apiKey;
      await updateSettings.mutateAsync(payload);
      setSettingsMsg('Settings saved!');
      setTimeout(() => setSettingsMsg(''), 3000);
    } catch {
      setSettingsMsg('Failed to save settings.');
    }
  };

  const handleChangePassword = async () => {
    setPwMsg({ type: '', text: '' });
    if (!currentPw || !newPw) {
      setPwMsg({ type: 'error', text: 'Both fields are required.' });
      return;
    }
    try {
      await api.post('/auth/change-password', {
        current_password: currentPw,
        new_password: newPw,
      });
      setPwMsg({ type: 'success', text: 'Password changed!' });
      setCurrentPw('');
      setNewPw('');
    } catch (err) {
      setPwMsg({ type: 'error', text: err.response?.data?.detail || 'Failed to change password.' });
    }
  };

  const handleClearData = async () => {
    if (!window.confirm('Delete all scraped jobs and search history? This cannot be undone.')) return;
    setClearing(true);
    try {
      await api.delete('/settings/clear-data');
      window.location.reload();
    } catch {
      alert('Failed to clear data.');
    } finally {
      setClearing(false);
    }
  };

  const portalOptions = ['linkedin', 'indeed', 'naukri'];

  const addItem = (list, setter, value) => {
    const v = value.trim();
    if (v && !list.includes(v)) setter([...list, v]);
  };
  const removeItem = (list, setter, idx) => setter(list.filter((_, i) => i !== idx));

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

  return (
    <div className="min-h-screen">
      <Navbar />
      <div className="mx-auto max-w-2xl px-4 py-10">
        <h1 className="mb-8 font-[family-name:var(--font-display)] text-3xl font-bold">Settings</h1>

        {/* API Key Section — Gemini (free) or Anthropic */}
        <Section title="API Key (required for resume tailoring)">
          <label className="mb-1.5 block text-sm text-text-secondary">
            AI API Key {settings?.has_api_key && <span className="text-success">(configured)</span>}
          </label>
          <p className="mb-2 text-xs text-text-secondary">
            Use a <strong className="text-success">free</strong> Google Gemini key — no credit card. Get it at{' '}
            <a href="https://aistudio.google.com" target="_blank" rel="noopener noreferrer" className="text-primary underline hover:no-underline">
              aistudio.google.com
            </a>
            {' '}→ Get API key → Create. Or paste an Anthropic key (sk-ant-...).
          </p>
          <input
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={settings?.has_api_key ? '••••••••••••' : 'AIza... or sk-ant-...'}
            className="w-full rounded-lg border border-border bg-bg-surface px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-primary"
          />
        </Section>

        {/* Search Defaults */}
        <Section title="Default Search Preferences">
          <TagEditor label="Job Titles" items={titles} setItems={setTitles} placeholder="Add a title..." />
          <TagEditor label="Locations" items={locations} setItems={setLocations} placeholder="Add a location..." />
          <div className="mt-4">
            <label className="mb-2 block text-sm text-text-secondary">Portals</label>
            <div className="flex gap-2">
              {portalOptions.map((p) => (
                <button
                  key={p}
                  onClick={() =>
                    setPortals((prev) =>
                      prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p]
                    )
                  }
                  className={`rounded-lg border px-4 py-2 text-sm font-medium capitalize transition-colors ${
                    portals.includes(p)
                      ? 'border-primary bg-primary/15 text-primary'
                      : 'border-border text-text-secondary hover:border-primary/30'
                  }`}
                >
                  {p}
                </button>
              ))}
            </div>
          </div>
        </Section>

        {settingsMsg && (
          <p className="mb-4 text-sm text-success">{settingsMsg}</p>
        )}
        <button
          onClick={handleSaveSettings}
          disabled={updateSettings.isPending}
          className="mb-10 w-full rounded-lg bg-primary py-2.5 text-sm font-semibold text-white hover:bg-primary-light disabled:opacity-60"
        >
          {updateSettings.isPending ? 'Saving...' : 'Save Settings'}
        </button>

        {/* Change Password */}
        <Section title="Change Password">
          <input
            type="password"
            value={currentPw}
            onChange={(e) => setCurrentPw(e.target.value)}
            placeholder="Current password"
            className="mb-3 w-full rounded-lg border border-border bg-bg-surface px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-primary"
          />
          <input
            type="password"
            value={newPw}
            onChange={(e) => setNewPw(e.target.value)}
            placeholder="New password"
            className="mb-3 w-full rounded-lg border border-border bg-bg-surface px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-primary"
          />
          {pwMsg.text && (
            <p className={`mb-3 text-sm ${pwMsg.type === 'error' ? 'text-danger' : 'text-success'}`}>
              {pwMsg.text}
            </p>
          )}
          <button
            onClick={handleChangePassword}
            className="rounded-lg border border-border px-5 py-2 text-sm font-medium text-text-secondary hover:border-primary hover:text-primary"
          >
            Update Password
          </button>
        </Section>

        {/* Resume Info */}
        <Section title="Current Resume">
          <p className="text-sm text-text-secondary">
            {settings?.base_resume_filename
              ? `Uploaded: ${settings.base_resume_filename}`
              : 'No resume uploaded yet.'}
          </p>
        </Section>

        {/* Danger Zone */}
        <div className="mt-10 rounded-xl border border-danger/30 p-6">
          <h2 className="mb-2 text-lg font-semibold text-danger">Danger Zone</h2>
          <p className="mb-4 text-sm text-text-secondary">
            Permanently delete all scraped jobs, scores, and search history.
          </p>
          <button
            onClick={handleClearData}
            disabled={clearing}
            className="rounded-lg bg-danger/15 px-5 py-2 text-sm font-semibold text-danger hover:bg-danger/25 disabled:opacity-60"
          >
            {clearing ? 'Clearing...' : 'Clear All Job Data'}
          </button>
        </div>
      </div>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="mb-6 rounded-xl border border-border bg-bg-card p-6"
    >
      <h2 className="mb-4 font-[family-name:var(--font-display)] text-base font-semibold">{title}</h2>
      {children}
    </motion.div>
  );
}

function TagEditor({ label, items, setItems, placeholder }) {
  const [input, setInput] = useState('');

  const add = () => {
    const v = input.trim();
    if (v && !items.includes(v)) setItems([...items, v]);
    setInput('');
  };

  return (
    <div className="mb-3">
      <label className="mb-1.5 block text-sm text-text-secondary">{label}</label>
      <div className="flex flex-wrap items-center gap-1.5 rounded-lg border border-border bg-bg-surface px-3 py-2">
        {items.map((item, i) => (
          <span key={i} className="flex items-center gap-1 rounded-md bg-primary/15 px-2 py-0.5 text-xs font-medium text-primary">
            {item}
            <button onClick={() => setItems(items.filter((_, j) => j !== i))} className="text-primary/60 hover:text-primary">×</button>
          </span>
        ))}
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); add(); } }}
          onBlur={add}
          placeholder={items.length === 0 ? placeholder : ''}
          className="min-w-[100px] flex-1 bg-transparent text-sm text-text-primary outline-none placeholder:text-text-secondary/50"
        />
      </div>
    </div>
  );
}
