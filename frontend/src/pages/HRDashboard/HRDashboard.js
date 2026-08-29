/**
 * HRDashboard.js  — Finalized HR Recruitment Module
 *
 * Sections:
 *   1. Stats banner          — real DB counts
 *   2. Job Requirements      — create / list / edit / delete
 *   3. Bulk Resume Upload    — auto name+email extraction, per-file status
 *   4. Candidate Table       — real data, email col, timestamp, filter/sort
 *   5. View Details panel    — full AI breakdown + extracted text
 *   6. Edit Candidate modal  — correct name / email only
 *
 * Gemini AI analysis is UNCHANGED — Analyze button triggers existing flow.
 */

import React, { useState, useRef, useEffect, useCallback } from 'react';
import {
  createJob, listJobs, updateJob, deleteJob,
  bulkUploadResumes, listResumes, getResume,
  updateResume, deleteResume,
  analyzeResumes, getRecruitmentStats,
} from '../../api/recruitmentApi';
import '../Recruitment/Recruitment.css';
import './HRDashboard.css';

// ── helpers ──────────────────────────────────────────────────────────

function getUser() {
  try { return JSON.parse(localStorage.getItem('user')) || {}; }
  catch { return {}; }
}

function parseDetail(resume) {
  if (!resume.ai_summary) return null;
  try { return JSON.parse(resume.ai_summary); }
  catch { return { short_reason: resume.ai_summary }; }
}

function fmtDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleString('en-IN', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit', hour12: true,
  });
}

const REC_BADGE = { selected: 'green', hold: 'amber', rejected: 'red' };
const REC_LABEL = { selected: 'Strong Match', hold: 'Review', rejected: 'Not Recommended' };
const STATUS_BADGE = {
  extracted: 'blue', uploaded: 'amber', analysed: 'green', error: 'red',
};
const FILE_ICON = { ok: '✅', error: '❌', duplicate: '⚠️', pending: '⏳' };

const EXP_LABELS = {
  entry: 'Entry (Fresher)', junior: 'Junior (1–2 yrs)',
  mid: 'Mid (3–5 yrs)', senior: 'Senior (5+ yrs)', lead: 'Lead / Manager',
};

// ── component ────────────────────────────────────────────────────────

export default function HRDashboard() {
  const user = getUser();

  // ── stats ────────────────────────────────────────────────────────
  const [stats, setStats] = useState(null);

  // ── jobs ─────────────────────────────────────────────────────────
  const [jobs,       setJobs]       = useState([]);
  const [jobForm,    setJobForm]    = useState(blankJobForm());
  const [editJobId,  setEditJobId]  = useState(null);   // null = create mode
  const [jobMsg,     setJobMsg]     = useState(null);
  const [jobLoading, setJobLoading] = useState(false);
  const [showJobForm, setShowJobForm] = useState(false);

  // ── upload ───────────────────────────────────────────────────────
  const [uploadJobId,  setUploadJobId]  = useState('');
  const [files,        setFiles]        = useState([]);        // File[]
  const [fileResults,  setFileResults]  = useState([]);        // per-file status
  const [uploadMsg,    setUploadMsg]    = useState(null);
  const [uploading,    setUploading]    = useState(false);
  const fileRef = useRef();

  // ── candidate table ───────────────────────────────────────────────
  const [resumes,      setResumes]      = useState([]);
  const [resultsJobId, setResultsJobId] = useState('');
  const [loadingList,  setLoadingList]  = useState(false);
  const [analyzing,    setAnalyzing]    = useState(false);
  const [analyzeMsg,   setAnalyzeMsg]   = useState(null);
  const [filterStatus, setFilterStatus] = useState('all');
  const [sortBy,       setSortBy]       = useState('newest');

  // ── detail panel ─────────────────────────────────────────────────
  const [detailResume, setDetailResume] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // ── edit candidate modal ──────────────────────────────────────────
  const [editResume,  setEditResume]  = useState(null);  // resume obj
  const [editName,    setEditName]    = useState('');
  const [editEmail,   setEditEmail]   = useState('');
  const [editSaving,  setEditSaving]  = useState(false);
  const [editMsg,     setEditMsg]     = useState(null);

  // ── init ─────────────────────────────────────────────────────────
  const refreshStats = useCallback(() => {
    getRecruitmentStats().then(setStats).catch(() => {});
  }, []);

  useEffect(() => {
    listJobs().then(setJobs).catch(() => {});
    refreshStats();
  }, [refreshStats]);

  // ── job form ─────────────────────────────────────────────────────

  function blankJobForm() {
    return {
      title: '', required_skills: '', experience_level: 'entry',
      min_education: "Bachelor's Degree", description: '',
    };
  }

  function startCreateJob() {
    setEditJobId(null);
    setJobForm(blankJobForm());
    setJobMsg(null);
    setShowJobForm(true);
  }

  function startEditJob(job) {
    setEditJobId(job.id);
    setJobForm({
      title:            job.title,
      required_skills:  job.required_skills,
      experience_level: job.experience_level,
      min_education:    job.min_education,
      description:      job.description || '',
    });
    setJobMsg(null);
    setShowJobForm(true);
  }

  function handleJobField(e) {
    setJobForm(f => ({ ...f, [e.target.name]: e.target.value }));
  }

  async function handleSaveJob(e) {
    e.preventDefault();
    if (!jobForm.title.trim() || !jobForm.required_skills.trim()) {
      setJobMsg({ type: 'error', text: 'Job Title and Required Skills are required.' });
      return;
    }
    setJobLoading(true);
    setJobMsg(null);
    try {
      const payload = {
        title:            jobForm.title.trim(),
        required_skills:  jobForm.required_skills.trim(),
        experience_level: jobForm.experience_level,
        min_education:    jobForm.min_education,
        description:      jobForm.description.trim() || null,
      };
      if (editJobId) {
        await updateJob(editJobId, payload);
        setJobMsg({ type: 'success', text: 'Job updated.' });
      } else {
        await createJob(payload);
        setJobMsg({ type: 'success', text: `Job "${payload.title}" created.` });
      }
      const refreshed = await listJobs();
      setJobs(refreshed);
      setShowJobForm(false);
      setEditJobId(null);
      refreshStats();
    } catch (err) {
      setJobMsg({ type: 'error', text: err.response?.data?.detail || 'Failed to save job.' });
    } finally {
      setJobLoading(false);
    }
  }

  async function handleDeleteJob(job) {
    if (!window.confirm(`Close job posting "${job.title}" (id ${job.id})?\n\nThis will hide it from the list but will NOT delete uploaded resumes.`)) return;
    try {
      await deleteJob(job.id);
      const refreshed = await listJobs();
      setJobs(refreshed);
      if (String(resultsJobId) === String(job.id)) {
        setResumes([]);
        setResultsJobId('');
      }
      refreshStats();
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to delete job.');
    }
  }

  // ── upload ───────────────────────────────────────────────────────

  function handleFileChange(e) {
    const picked = Array.from(e.target.files).filter(f => f.name.toLowerCase().endsWith('.pdf'));
    setFiles(prev => {
      const existing = new Set(prev.map(f => f.name));
      return [...prev, ...picked.filter(f => !existing.has(f.name))];
    });
    setFileResults([]);
    e.target.value = '';
  }

  function removeFile(name) {
    setFiles(prev => prev.filter(f => f.name !== name));
  }

  async function handleBulkUpload(e) {
    e.preventDefault();
    if (!uploadJobId) { setUploadMsg({ type: 'error', text: 'Select a job posting first.' }); return; }
    if (files.length === 0) { setUploadMsg({ type: 'error', text: 'Select at least one PDF.' }); return; }

    setUploading(true);
    setUploadMsg({ type: 'info', text: `Uploading ${files.length} file(s)…` });
    setFileResults(files.map(f => ({ file_name: f.name, status: 'pending' })));

    try {
      const data = await bulkUploadResumes(Number(uploadJobId), files);
      setFileResults(data.files);
      setFiles([]);
      setUploadMsg({
        type: data.failed > 0 ? 'error' : 'success',
        text: `Done: ${data.succeeded} uploaded, ${data.duplicates} duplicate(s), ${data.failed} failed.`,
      });
      // Auto-load results for this job
      setResultsJobId(String(uploadJobId));
      await loadResults(uploadJobId);
      refreshStats();
    } catch (err) {
      setUploadMsg({ type: 'error', text: err.response?.data?.detail || 'Upload failed.' });
    } finally {
      setUploading(false);
    }
  }

  // ── candidate table ───────────────────────────────────────────────

  async function loadResults(jobId) {
    if (!jobId) return;
    setLoadingList(true);
    try {
      const data = await listResumes(Number(jobId));
      setResumes(data);
      setResultsJobId(String(jobId));
    } catch {
      setResumes([]);
    } finally {
      setLoadingList(false);
    }
  }

  async function handleAnalyze() {
    if (!resultsJobId) { setAnalyzeMsg({ type: 'error', text: 'Select a job first.' }); return; }
    setAnalyzing(true);
    setAnalyzeMsg({ type: 'info', text: 'Analyzing resumes with Gemini AI… this may take a moment.' });
    try {
      const data = await analyzeResumes(Number(resultsJobId));
      setResumes(data.results);
      setAnalyzeMsg({
        type: 'success',
        text: `Analysis complete — ${data.analysed} resume(s) analyzed.`,
      });
      refreshStats();
    } catch (err) {
      setAnalyzeMsg({ type: 'error', text: err.response?.data?.detail || 'AI analysis failed.' });
    } finally {
      setAnalyzing(false);
    }
  }

  async function handleDeleteResume(resume) {
    if (!window.confirm(`Delete resume for "${resume.candidate_name}" (${resume.file_name})?\n\nThis cannot be undone.`)) return;
    try {
      await deleteResume(resume.id);
      setResumes(prev => prev.filter(r => r.id !== resume.id));
      if (detailResume?.id === resume.id) setDetailResume(null);
      refreshStats();
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to delete resume.');
    }
  }

  // ── detail panel ─────────────────────────────────────────────────

  async function openDetail(resumeListItem) {
    setDetailLoading(true);
    setDetailResume(null);
    try {
      const full = await getResume(resumeListItem.id);
      setDetailResume(full);
    } catch {
      setDetailResume(resumeListItem);   // fallback to list data
    } finally {
      setDetailLoading(false);
    }
    // scroll to top of detail panel
    setTimeout(() => document.getElementById('detail-panel')?.scrollIntoView({ behavior: 'smooth' }), 100);
  }

  // ── edit candidate modal ──────────────────────────────────────────

  function openEditResume(resume) {
    setEditResume(resume);
    setEditName(resume.candidate_name || '');
    setEditEmail(resume.candidate_email || '');
    setEditMsg(null);
  }

  async function handleSaveEditResume(e) {
    e.preventDefault();
    if (!editName.trim()) { setEditMsg({ type: 'error', text: 'Name cannot be empty.' }); return; }
    setEditSaving(true);
    setEditMsg(null);
    try {
      const updated = await updateResume(editResume.id, {
        candidate_name:  editName.trim(),
        candidate_email: editEmail.trim() || null,
      });
      // patch in both resumes list and detail panel
      setResumes(prev => prev.map(r => r.id === updated.id ? { ...r, ...updated } : r));
      if (detailResume?.id === updated.id) setDetailResume(prev => ({ ...prev, ...updated }));
      setEditResume(null);
    } catch (err) {
      setEditMsg({ type: 'error', text: err.response?.data?.detail || 'Failed to save.' });
    } finally {
      setEditSaving(false);
    }
  }

  // ── filtered + sorted resumes ─────────────────────────────────────

  const displayedResumes = (() => {
    let list = [...resumes];
    // filter
    if (filterStatus === 'waiting')  list = list.filter(r => r.status === 'extracted');
    else if (filterStatus === 'analysed') list = list.filter(r => r.status === 'analysed');
    else if (filterStatus === 'selected') list = list.filter(r => r.recommendation === 'selected');
    else if (filterStatus === 'hold')     list = list.filter(r => r.recommendation === 'hold');
    else if (filterStatus === 'rejected') list = list.filter(r => r.recommendation === 'rejected');
    else if (filterStatus === 'error')    list = list.filter(r => r.status === 'error');
    // sort
    if (sortBy === 'score') list.sort((a, b) => (b.ai_score ?? -1) - (a.ai_score ?? -1));
    else list.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
    return list;
  })();

  // ── render ────────────────────────────────────────────────────────

  return (
    <div className="hr-dashboard">

      {/* ── Welcome ─────────────────────────────────────────────── */}
      <div className="hr-welcome">
        <h1>Welcome, {user.full_name || 'HR Manager'} 👋</h1>
        <p>AI-powered recruitment — bulk upload resumes, auto-extract candidate info, and get Gemini AI match scores.</p>
      </div>

      {/* ── Stats banner ────────────────────────────────────────── */}
      {stats && (
        <div className="stats-row">
          {[
            { label: 'Open Positions',  val: stats.open_positions, color: '#2563eb' },
            { label: 'Applications',    val: stats.applications,   color: '#7c3aed' },
            { label: 'Pending AI',      val: stats.waiting,        color: '#d97706' },
            { label: 'Shortlisted',     val: stats.shortlisted,    color: '#16a34a' },
            { label: 'Not Recommended', val: stats.rejected,       color: '#dc2626' },
          ].map(s => (
            <div className="stat-card" key={s.label}>
              <div className="stat-value" style={{ color: s.color }}>{s.val}</div>
              <div className="stat-label">{s.label}</div>
            </div>
          ))}
        </div>
      )}

      {/* ── Job Requirements ────────────────────────────────────── */}
      <div className="content-panel" style={{ marginBottom: '1.5rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <h2 className="section-title" style={{ marginBottom: 0, borderBottom: 'none' }}>📋 Job Requirements</h2>
          <button className="btn-primary" style={{ padding: '0.5rem 1rem', fontSize: '0.85rem' }}
            onClick={startCreateJob}>+ New Job</button>
        </div>

        {/* Job form (create or edit) */}
        {showJobForm && (
          <div className="job-form-box">
            <h3 style={{ fontSize: '0.95rem', fontWeight: 700, marginBottom: '1rem', color: 'var(--text-primary)' }}>
              {editJobId ? `Edit Job #${editJobId}` : 'Create New Job Requirement'}
            </h3>
            {jobMsg && <div className={`alert ${jobMsg.type}`}>{jobMsg.text}</div>}
            <form onSubmit={handleSaveJob}>
              <div className="form-grid">
                <div className="field-group full-width">
                  <label>Job Title *</label>
                  <input className="field-input" name="title" value={jobForm.title}
                    onChange={handleJobField} placeholder="e.g. Junior Python Developer" required />
                </div>
                <div className="field-group full-width">
                  <label>Required Skills *</label>
                  <input className="field-input" name="required_skills" value={jobForm.required_skills}
                    onChange={handleJobField} placeholder="e.g. Python, FastAPI, SQL" required />
                </div>
                <div className="field-group">
                  <label>Experience Level</label>
                  <select className="field-select" name="experience_level"
                    value={jobForm.experience_level} onChange={handleJobField}>
                    <option value="entry">Entry (Fresher)</option>
                    <option value="junior">Junior (1–2 yrs)</option>
                    <option value="mid">Mid (3–5 yrs)</option>
                    <option value="senior">Senior (5+ yrs)</option>
                    <option value="lead">Lead / Manager</option>
                  </select>
                </div>
                <div className="field-group">
                  <label>Minimum Education</label>
                  <select className="field-select" name="min_education"
                    value={jobForm.min_education} onChange={handleJobField}>
                    <option>High School</option>
                    <option>Diploma</option>
                    <option>Bachelor's Degree</option>
                    <option>Master's Degree</option>
                    <option>PhD</option>
                  </select>
                </div>
                <div className="field-group full-width">
                  <label>Job Description (optional)</label>
                  <textarea className="field-input" name="description" rows={3}
                    value={jobForm.description} onChange={handleJobField}
                    placeholder="Additional context for the AI to use when scoring resumes…"
                    style={{ resize: 'vertical' }} />
                </div>
              </div>
              <div style={{ display: 'flex', gap: '0.75rem', marginTop: '1rem' }}>
                <button type="submit" className="btn-primary" disabled={jobLoading}>
                  {jobLoading ? 'Saving…' : editJobId ? '💾 Save Changes' : '+ Create Job'}
                </button>
                <button type="button" className="btn-secondary"
                  onClick={() => { setShowJobForm(false); setEditJobId(null); setJobMsg(null); }}>
                  Cancel
                </button>
              </div>
            </form>
          </div>
        )}

        {/* Jobs list */}
        {jobs.length === 0 ? (
          <p style={{ color: 'var(--text-muted)', fontSize: '0.88rem' }}>No active jobs. Click "+ New Job" to create one.</p>
        ) : (
          <div className="jobs-list">
            {jobs.map(j => (
              <div key={j.id} className="job-row">
                <div className="job-row-info">
                  <span className="job-row-title">{j.title}</span>
                  <span className="job-row-meta">
                    {EXP_LABELS[j.experience_level] || j.experience_level}
                    {' · '}{j.min_education}
                    {' · '}<span style={{ color: 'var(--text-muted)', fontSize: '0.78rem' }}>#{j.id}</span>
                  </span>
                  <span className="job-row-skills">{j.required_skills}</span>
                </div>
                <div className="job-row-actions">
                  <button className="btn-link" onClick={() => startEditJob(j)}>Edit</button>
                  <button className="btn-link danger" onClick={() => handleDeleteJob(j)}>Delete</button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── Bulk Resume Upload ───────────────────────────────────── */}
      <div className="content-panel" style={{ marginBottom: '1.5rem' }}>
        <h2 className="section-title">📂 Bulk Resume Upload</h2>
        <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '1rem' }}>
          Select a job and upload multiple PDF resumes at once. Candidate name and email are extracted automatically.
        </p>

        {uploadMsg && <div className={`alert ${uploadMsg.type}`}>{uploadMsg.text}</div>}

        <form onSubmit={handleBulkUpload}>
          <div className="job-selector" style={{ marginBottom: '1rem' }}>
            <label>Job Posting:</label>
            <select className="field-select" style={{ minWidth: 260 }}
              value={uploadJobId} onChange={e => setUploadJobId(e.target.value)}>
              <option value="">— select a job —</option>
              {jobs.map(j => (
                <option key={j.id} value={j.id}>{j.id}. {j.title}</option>
              ))}
            </select>
          </div>

          <div className="upload-area" onClick={() => fileRef.current.click()}>
            <input ref={fileRef} type="file" accept=".pdf" multiple onChange={handleFileChange} />
            <div className="upload-icon">📄</div>
            <p>Click to select PDF resume(s) — multiple files supported</p>
            <p style={{ fontSize: '0.78rem', marginTop: '0.3rem', color: 'var(--text-muted)' }}>
              PDF only · Name and email auto-detected from each resume
            </p>
          </div>

          {files.length > 0 && (
            <div className="file-list" style={{ marginTop: '0.75rem' }}>
              {files.map(f => (
                <div key={f.name} className="file-chip">
                  <span>📎</span>
                  <span style={{ flex: 1 }}>{f.name}</span>
                  <button type="button" className="btn-link" onClick={() => removeFile(f.name)}>remove</button>
                </div>
              ))}
              <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', margin: '0.35rem 0 0' }}>
                {files.length} file(s) selected
              </p>
            </div>
          )}

          <div style={{ marginTop: '1rem' }}>
            <button type="submit" className="btn-primary" disabled={uploading || files.length === 0}>
              {uploading ? '⬆ Uploading…' : `⬆ Upload ${files.length > 0 ? files.length + ' Resume(s)' : 'Resumes'}`}
            </button>
          </div>
        </form>

        {/* Per-file extraction results */}
        {fileResults.length > 0 && (
          <div className="file-results-list">
            <div style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--text-secondary)',
              textTransform: 'uppercase', marginBottom: '0.5rem' }}>Upload Results</div>
            {fileResults.map((fr, i) => (
              <div key={i} className="file-result-row">
                <span className="file-result-icon">{FILE_ICON[fr.status] || '⏳'}</span>
                <span className="file-result-name">{fr.file_name}</span>
                {fr.status === 'ok' && (
                  <span className="file-result-detail">
                    {fr.candidate_name && fr.candidate_name !== 'Not detected'
                      ? `✓ ${fr.candidate_name}` : '⚠ Name not detected'}
                    {fr.candidate_email ? ` · ✓ ${fr.candidate_email}` : ' · ⚠ Email not detected'}
                    {' · '}
                    {fr.extraction_status === 'extracted' ? '✓ Text extracted' : '❌ Extraction failed'}
                  </span>
                )}
                {fr.status === 'duplicate' && (
                  <span className="file-result-detail" style={{ color: '#d97706' }}>
                    Duplicate — already uploaded for this job
                  </span>
                )}
                {fr.status === 'error' && (
                  <span className="file-result-detail" style={{ color: '#dc2626' }}>{fr.error}</span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── Candidate Results ────────────────────────────────────── */}
      <div className="content-panel" style={{ marginBottom: '1.5rem' }}>
        <h2 className="section-title">🏆 Candidate Results</h2>

        {analyzeMsg && <div className={`alert ${analyzeMsg.type}`}>{analyzeMsg.text}</div>}

        {/* Controls row */}
        <div className="controls-row">
          <div className="job-selector" style={{ margin: 0 }}>
            <label>Job:</label>
            <select className="field-select" style={{ minWidth: 240 }}
              value={resultsJobId} onChange={e => setResultsJobId(e.target.value)}>
              <option value="">— select —</option>
              {jobs.map(j => (
                <option key={j.id} value={j.id}>{j.id}. {j.title}</option>
              ))}
            </select>
            <button className="btn-secondary"
              onClick={() => loadResults(resultsJobId)} disabled={!resultsJobId || loadingList}>
              {loadingList ? 'Loading…' : '🔄 Load'}
            </button>
          </div>

          <button className="btn-primary" onClick={handleAnalyze}
            disabled={!resultsJobId || analyzing} style={{ whiteSpace: 'nowrap' }}>
            {analyzing ? '🤖 Analyzing…' : '🤖 Analyze Resumes'}
          </button>
        </div>

        {/* Filter + sort row */}
        {resumes.length > 0 && (
          <div className="filter-row">
            <div className="filter-chips">
              {[
                { k: 'all',      label: `All (${resumes.length})` },
                { k: 'waiting',  label: `Pending AI (${resumes.filter(r => r.status === 'extracted').length})` },
                { k: 'analysed', label: `Analysed (${resumes.filter(r => r.status === 'analysed').length})` },
                { k: 'selected', label: `Strong Match (${resumes.filter(r => r.recommendation === 'selected').length})` },
                { k: 'hold',     label: `Review (${resumes.filter(r => r.recommendation === 'hold').length})` },
                { k: 'rejected', label: `Not Recommended (${resumes.filter(r => r.recommendation === 'rejected').length})` },
                { k: 'error',    label: `Error (${resumes.filter(r => r.status === 'error').length})` },
              ].map(f => (
                <button key={f.k}
                  className={`filter-chip ${filterStatus === f.k ? 'active' : ''}`}
                  onClick={() => setFilterStatus(f.k)}>
                  {f.label}
                </button>
              ))}
            </div>
            <select className="field-select" style={{ fontSize: '0.82rem', padding: '0.4rem 0.7rem' }}
              value={sortBy} onChange={e => setSortBy(e.target.value)}>
              <option value="newest">↕ Newest first</option>
              <option value="score">↕ Highest score</option>
            </select>
          </div>
        )}

        {displayedResumes.length > 0 ? (
          <div style={{ overflowX: 'auto' }}>
            <table className="data-table" aria-label="Candidate results">
              <thead>
                <tr>
                  <th>Candidate</th>
                  <th>Email</th>
                  <th>File</th>
                  <th>Uploaded At</th>
                  <th>Status</th>
                  <th>AI Score</th>
                  <th>Recommendation</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {displayedResumes.map(r => {
                  const detail   = parseDetail(r);
                  const recLabel = detail?.recommendation_label || REC_LABEL[r.recommendation] || '';
                  return (
                    <tr key={r.id}>
                      <td><strong>{r.candidate_name}</strong></td>
                      <td style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
                        {r.candidate_email || <span style={{ color: 'var(--text-muted)' }}>—</span>}
                      </td>
                      <td style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', maxWidth: 160,
                        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                        title={r.file_name}>{r.file_name}</td>
                      <td style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>
                        {fmtDate(r.created_at)}
                      </td>
                      <td>
                        <span className={`badge ${STATUS_BADGE[r.status] || 'blue'}`}>{r.status}</span>
                      </td>
                      <td>
                        {r.ai_score != null
                          ? <strong>{Math.round(r.ai_score)}%</strong>
                          : <span style={{ color: 'var(--text-muted)', fontSize: '0.82rem' }}>—</span>}
                      </td>
                      <td>
                        {recLabel
                          ? <span className={`badge ${REC_BADGE[r.recommendation] || 'blue'}`}>{recLabel}</span>
                          : <span style={{ color: 'var(--text-muted)', fontSize: '0.82rem' }}>—</span>}
                      </td>
                      <td style={{ whiteSpace: 'nowrap' }}>
                        <button className="btn-link" style={{ marginRight: '0.6rem' }}
                          onClick={() => openDetail(r)}>View</button>
                        <button className="btn-link" style={{ marginRight: '0.6rem' }}
                          onClick={() => openEditResume(r)}>Edit</button>
                        <button className="btn-link danger"
                          onClick={() => handleDeleteResume(r)}>Delete</button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginTop: '1rem' }}>
            {resultsJobId
              ? (resumes.length > 0 ? 'No candidates match the current filter.' : 'No resumes uploaded for this job yet.')
              : 'Select a job and click Load.'}
          </p>
        )}
      </div>

      {/* ── Detail Panel ────────────────────────────────────────── */}
      {(detailLoading || detailResume) && (
        <div className="detail-panel" id="detail-panel">
          {detailLoading && <p style={{ color: 'var(--text-muted)' }}>Loading details…</p>}
          {!detailLoading && detailResume && (() => {
            const r      = detailResume;
            const detail = parseDetail(r);
            const recLabel = detail?.recommendation_label || REC_LABEL[r.recommendation] || '';
            const job    = jobs.find(j => j.id === r.job_posting_id);
            return (
              <>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem' }}>
                  <div>
                    <h3 style={{ margin: 0 }}>👤 {r.candidate_name}</h3>
                    {r.candidate_email && (
                      <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginTop: '0.2rem' }}>
                        {r.candidate_email}
                      </div>
                    )}
                  </div>
                  <button className="btn-link" onClick={() => setDetailResume(null)}>✕ Close</button>
                </div>

                {/* Meta row */}
                <div className="detail-meta-grid">
                  <div><span className="dmeta-label">File</span><span>{r.file_name}</span></div>
                  <div><span className="dmeta-label">Job</span><span>{job?.title || `#${r.job_posting_id}`}</span></div>
                  <div><span className="dmeta-label">Uploaded</span><span>{fmtDate(r.created_at)}</span></div>
                  <div><span className="dmeta-label">Status</span>
                    <span className={`badge ${STATUS_BADGE[r.status] || 'blue'}`}>{r.status}</span></div>
                </div>

                {/* AI badge row */}
                <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', margin: '1rem 0' }}>
                  {r.ai_score != null && (
                    <span className="badge blue" style={{ fontSize: '0.9rem', padding: '0.4rem 0.9rem' }}>
                      Match Score: <strong>{Math.round(r.ai_score)}%</strong>
                    </span>
                  )}
                  {recLabel && (
                    <span className={`badge ${REC_BADGE[r.recommendation] || 'blue'}`}
                      style={{ fontSize: '0.9rem', padding: '0.4rem 0.9rem' }}>
                      {recLabel}
                    </span>
                  )}
                  {!r.ai_score && (
                    <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                      AI analysis not yet run for this resume.
                    </span>
                  )}
                </div>

                {/* AI breakdown grid */}
                {detail && (
                  <div className="detail-ai-grid">
                    {[
                      { label: '✅ Matched Skills',  val: detail.matched_skills  },
                      { label: '⚠ Missing Skills',   val: detail.missing_skills  },
                      { label: '🎓 Education Match',  val: detail.education_match },
                      { label: '💼 Experience Match', val: detail.experience_match},
                      { label: '💪 Strengths',        val: detail.strengths       },
                      { label: '🔴 Concerns',         val: detail.concerns        },
                    ].map(({ label, val }) => (
                      <div key={label} className="detail-ai-cell">
                        <div className="detail-ai-label">{label}</div>
                        <div className="detail-ai-val">{val || 'Not specified'}</div>
                      </div>
                    ))}
                  </div>
                )}

                {/* Summary */}
                {detail?.short_reason && (
                  <div style={{ marginBottom: '1rem' }}>
                    <div className="detail-ai-label" style={{ marginBottom: '0.3rem' }}>📝 AI Summary</div>
                    <div style={{ fontSize: '0.9rem', lineHeight: 1.65, color: 'var(--text-primary)' }}>
                      {detail.short_reason}
                    </div>
                  </div>
                )}

                {/* Extracted text */}
                <div>
                  <div className="detail-ai-label" style={{ marginBottom: '0.4rem' }}>📄 Extracted Resume Text</div>
                  {r.extracted_text
                    ? <div className="detail-text">{r.extracted_text}</div>
                    : <div className="detail-text" style={{ color: 'var(--text-muted)' }}>
                        No text extracted — PDF may be image-based or extraction failed.
                      </div>}
                </div>

                {/* Edit shortcut */}
                <div style={{ marginTop: '1rem' }}>
                  <button className="btn-secondary" onClick={() => { setDetailResume(null); openEditResume(r); }}>
                    ✏️ Edit Candidate Info
                  </button>
                </div>
              </>
            );
          })()}
        </div>
      )}

      {/* ── Edit Candidate Modal ─────────────────────────────────── */}
      {editResume && (
        <div className="modal-overlay" role="dialog" aria-modal="true" aria-label="Edit candidate">
          <div className="modal-box">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 700 }}>✏️ Edit Candidate Info</h3>
              <button className="btn-link" onClick={() => setEditResume(null)}>✕</button>
            </div>
            <p style={{ fontSize: '0.82rem', color: 'var(--text-muted)', marginBottom: '1rem' }}>
              Correct auto-extracted name or email. AI scores and recommendations cannot be edited manually.
            </p>
            {editMsg && <div className={`alert ${editMsg.type}`}>{editMsg.text}</div>}
            <form onSubmit={handleSaveEditResume}>
              <div className="field-group" style={{ marginBottom: '1rem' }}>
                <label>Candidate Name *</label>
                <input className="field-input" value={editName}
                  onChange={e => setEditName(e.target.value)} required />
              </div>
              <div className="field-group" style={{ marginBottom: '1.25rem' }}>
                <label>Candidate Email</label>
                <input className="field-input" type="email" value={editEmail}
                  onChange={e => setEditEmail(e.target.value)} placeholder="email@example.com" />
              </div>
              <div style={{ display: 'flex', gap: '0.75rem' }}>
                <button type="submit" className="btn-primary" disabled={editSaving}>
                  {editSaving ? 'Saving…' : '💾 Save'}
                </button>
                <button type="button" className="btn-secondary" onClick={() => setEditResume(null)}>
                  Cancel
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

    </div>
  );
}
