/**
 * pages/HRDashboard/HRDashboard.js
 *
 * HR Recruitment Dashboard — Phase 2 (Gemini AI connected)
 *
 * Changes from Phase 1:
 *  - Loads all jobs from backend on mount (fixes persistence)
 *  - "Analyze Resumes" button calls POST /jobs/{id}/analyze
 *  - Results table shows real AI score, recommendation, status
 *  - Detail panel parses ai_summary JSON for full breakdown
 *
 * UI structure and CSS are unchanged.
 */

import React, { useState, useRef, useEffect } from 'react';
import {
  createJob, listJobs, uploadResume,
  listResumes, analyzeResumes,
} from '../../api/recruitmentApi';
import '../Recruitment/Recruitment.css';
import './HRDashboard.css';

// ── helpers ─────────────────────────────────────────────────────────
function getUser() {
  try { return JSON.parse(localStorage.getItem('user')) || {}; }
  catch { return {}; }
}

/** Parse ai_summary JSON field — falls back gracefully if not JSON */
function parseDetail(resume) {
  if (!resume.ai_summary) return null;
  try { return JSON.parse(resume.ai_summary); }
  catch { return { short_reason: resume.ai_summary }; }
}

const REC_BADGE    = { selected: 'green', hold: 'amber', rejected: 'red' };
const STATUS_BADGE = { extracted: 'blue', uploaded: 'amber', analysed: 'green', error: 'red' };

// ── component ────────────────────────────────────────────────────────
export default function HRDashboard() {
  const user = getUser();

  // ── Job form ────────────────────────────────────────────────────
  const [jobForm, setJobForm] = useState({
    title: '', required_skills: '', experience_level: 'entry',
    min_education: "Bachelor's Degree", openings: 1,
    employment_type: 'Full-time', location: '', salary: '',
  });
  const [jobs,       setJobs]       = useState([]);
  const [jobMsg,     setJobMsg]     = useState(null);
  const [jobLoading, setJobLoading] = useState(false);

  // ── Upload ──────────────────────────────────────────────────────
  const [selectedJobId,  setSelectedJobId]  = useState('');
  const [candidateName,  setCandidateName]  = useState('');
  const [candidateEmail, setCandidateEmail] = useState('');
  const [files,          setFiles]          = useState([]);
  const [uploadMsg,      setUploadMsg]      = useState(null);
  const [uploading,      setUploading]      = useState(false);
  const fileRef = useRef();

  // ── Results ─────────────────────────────────────────────────────
  const [resumes,      setResumes]      = useState([]);
  const [resultsJobId, setResultsJobId] = useState('');
  const [loadingList,  setLoadingList]  = useState(false);
  const [analyzing,    setAnalyzing]    = useState(false);
  const [analyzeMsg,   setAnalyzeMsg]   = useState(null);

  // ── Detail panel ────────────────────────────────────────────────
  const [selected, setSelected] = useState(null);

  // ── Load all jobs from backend on first render (fixes persistence) ──
  useEffect(() => {
    listJobs()
      .then(data => setJobs(data))
      .catch(() => {/* silently ignore — user can still create jobs */});
  }, []);

  // ── Job form handlers ────────────────────────────────────────────
  function handleJobField(e) {
    setJobForm(f => ({ ...f, [e.target.name]: e.target.value }));
  }

  async function handleCreateJob(e) {
    e.preventDefault();
    if (!jobForm.title.trim() || !jobForm.required_skills.trim()) {
      setJobMsg({ type: 'error', text: 'Job Title and Required Skills are required.' });
      return;
    }
    setJobLoading(true);
    setJobMsg(null);
    try {
      const job = await createJob({
        title:            jobForm.title,
        required_skills:  jobForm.required_skills,
        experience_level: jobForm.experience_level,
        min_education:    jobForm.min_education,
        description:
          `Employment: ${jobForm.employment_type} | Location: ${jobForm.location} | ` +
          `Openings: ${jobForm.openings}` +
          (jobForm.salary ? ` | Salary: ${jobForm.salary}` : ''),
      });
      // Refresh full list from backend to keep order consistent
      const refreshed = await listJobs();
      setJobs(refreshed);
      setSelectedJobId(String(job.id));
      setJobMsg({ type: 'success', text: `Job "${job.title}" created (ID: ${job.id}).` });
      setJobForm({
        title: '', required_skills: '', experience_level: 'entry',
        min_education: "Bachelor's Degree", openings: 1,
        employment_type: 'Full-time', location: '', salary: '',
      });
    } catch (err) {
      setJobMsg({ type: 'error', text: err.response?.data?.detail || 'Failed to create job.' });
    } finally {
      setJobLoading(false);
    }
  }

  // ── Upload handlers ──────────────────────────────────────────────
  function handleFileChange(e) {
    const picked = Array.from(e.target.files).filter(f => f.name.endsWith('.pdf'));
    setFiles(prev => {
      const existing = prev.map(f => f.name);
      return [...prev, ...picked.filter(f => !existing.includes(f.name))];
    });
  }

  function removeFile(name) {
    setFiles(prev => prev.filter(f => f.name !== name));
  }

  async function handleUpload(e) {
    e.preventDefault();
    if (!selectedJobId)       { setUploadMsg({ type: 'error', text: 'Select a job first.' }); return; }
    if (!candidateName.trim()){ setUploadMsg({ type: 'error', text: 'Candidate name is required.' }); return; }
    if (files.length === 0)   { setUploadMsg({ type: 'error', text: 'Select at least one PDF.' }); return; }

    setUploading(true);
    setUploadMsg(null);
    let count = 0;
    for (const file of files) {
      try {
        await uploadResume(Number(selectedJobId), candidateName, candidateEmail, file);
        count++;
      } catch (err) {
        setUploadMsg({ type: 'error', text: err.response?.data?.detail || `Failed: ${file.name}` });
        setUploading(false);
        return;
      }
    }
    setFiles([]);
    setCandidateName('');
    setCandidateEmail('');
    setUploadMsg({ type: 'success', text: `${count} resume(s) uploaded and text extracted.` });
    setUploading(false);
    // Auto-refresh results if the same job is selected
    if (resultsJobId === selectedJobId) loadResults(selectedJobId);
  }

  // ── Results handlers ─────────────────────────────────────────────
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
    setAnalyzeMsg({ type: 'info', text: 'Analyzing resumes with AI… this may take a moment.' });
    try {
      const data = await analyzeResumes(Number(resultsJobId));
      setResumes(data.results);
      setAnalyzeMsg({
        type: 'success',
        text: `Analysis complete. ${data.analysed} resume(s) analyzed by Gemini AI.`,
      });
    } catch (err) {
      setAnalyzeMsg({
        type: 'error',
        text: err.response?.data?.detail || 'AI analysis failed.',
      });
    } finally {
      setAnalyzing(false);
    }
  }

  return (
    <div className="hr-dashboard">

      {/* ── Section 1: Welcome ──────────────────────────────────── */}
      <div className="hr-welcome">
        <h1>Welcome, {user.full_name || 'HR Manager'} 👋</h1>
        <p>Create job postings, upload resumes, and review AI-assisted candidate screening.</p>
      </div>

      {/* ── Section 2: Job Requirement Form ─────────────────────── */}
      <div className="content-panel" style={{ marginBottom: '1.5rem' }}>
        <h2 className="section-title">📋 Create Job Requirement</h2>
        {jobMsg && <div className={`alert ${jobMsg.type}`}>{jobMsg.text}</div>}
        <form onSubmit={handleCreateJob}>
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
            <div className="field-group">
              <label>Number of Openings</label>
              <input className="field-input" type="number" name="openings" min="1"
                value={jobForm.openings} onChange={handleJobField} />
            </div>
            <div className="field-group">
              <label>Employment Type</label>
              <select className="field-select" name="employment_type"
                value={jobForm.employment_type} onChange={handleJobField}>
                <option>Full-time</option>
                <option>Part-time</option>
                <option>Contract</option>
                <option>Internship</option>
                <option>Remote</option>
              </select>
            </div>
            <div className="field-group">
              <label>Location</label>
              <input className="field-input" name="location" value={jobForm.location}
                onChange={handleJobField} placeholder="e.g. Chennai, Remote" />
            </div>
            <div className="field-group">
              <label>Salary (optional)</label>
              <input className="field-input" name="salary" value={jobForm.salary}
                onChange={handleJobField} placeholder="e.g. ₹4–6 LPA" />
            </div>
          </div>
          <div style={{ marginTop: '1.25rem' }}>
            <button type="submit" className="btn-primary" disabled={jobLoading}>
              {jobLoading ? 'Creating…' : '+ Create Job'}
            </button>
          </div>
        </form>
      </div>

      {/* ── Section 3: Resume Upload ─────────────────────────────── */}
      <div className="content-panel" style={{ marginBottom: '1.5rem' }}>
        <h2 className="section-title">📂 Upload Resumes</h2>
        {uploadMsg && <div className={`alert ${uploadMsg.type}`}>{uploadMsg.text}</div>}
        <form onSubmit={handleUpload}>
          <div className="job-selector">
            <label>Select Job Posting:</label>
            <select className="field-select" style={{ minWidth: 240 }}
              value={selectedJobId} onChange={e => setSelectedJobId(e.target.value)}>
              <option value="">— choose a job —</option>
              {jobs.map(j => (
                <option key={j.id} value={j.id}>{j.id}. {j.title}</option>
              ))}
            </select>
            {jobs.length === 0 && (
              <span style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>
                Create a job above first.
              </span>
            )}
          </div>
          <div className="upload-meta">
            <div className="field-group">
              <label>Candidate Name *</label>
              <input className="field-input" value={candidateName}
                onChange={e => setCandidateName(e.target.value)} placeholder="Full name" />
            </div>
            <div className="field-group">
              <label>Candidate Email (optional)</label>
              <input className="field-input" type="email" value={candidateEmail}
                onChange={e => setCandidateEmail(e.target.value)} placeholder="email@example.com" />
            </div>
          </div>
          <div className="upload-area" onClick={() => fileRef.current.click()}>
            <input ref={fileRef} type="file" accept=".pdf" multiple onChange={handleFileChange} />
            <div className="upload-icon">📄</div>
            <p>Click to select PDF resume(s)</p>
            <p style={{ fontSize: '0.78rem', marginTop: '0.3rem' }}>Only PDF files accepted</p>
          </div>
          {files.length > 0 && (
            <div className="file-list">
              {files.map(f => (
                <div key={f.name} className="file-chip">
                  <span>📎</span>{f.name}
                  <button type="button" className="btn-link" style={{ marginLeft: 'auto' }}
                    onClick={() => removeFile(f.name)}>remove</button>
                </div>
              ))}
            </div>
          )}
          <div style={{ marginTop: '1rem' }}>
            <button type="submit" className="btn-primary" disabled={uploading}>
              {uploading ? 'Uploading…' : '⬆ Upload Resume'}
            </button>
          </div>
        </form>
      </div>

      {/* ── Section 4: Candidate Results ─────────────────────────── */}
      <div className="content-panel" style={{ marginBottom: '1.5rem' }}>
        <h2 className="section-title">🏆 Candidate Results</h2>

        {analyzeMsg && <div className={`alert ${analyzeMsg.type}`}>{analyzeMsg.text}</div>}

        <div className="job-selector" style={{ marginBottom: '1rem' }}>
          <label>View results for job:</label>
          <select className="field-select" style={{ minWidth: 240 }}
            value={resultsJobId} onChange={e => setResultsJobId(e.target.value)}>
            <option value="">— select —</option>
            {jobs.map(j => (
              <option key={j.id} value={j.id}>{j.id}. {j.title}</option>
            ))}
          </select>
          <button type="button" className="btn-secondary"
            onClick={() => loadResults(resultsJobId)} disabled={!resultsJobId || loadingList}>
            {loadingList ? 'Loading…' : '🔄 Load'}
          </button>
          <button type="button" className="btn-primary"
            onClick={handleAnalyze} disabled={!resultsJobId || analyzing}
            style={{ marginLeft: '0.5rem' }}>
            {analyzing ? '🤖 Analyzing…' : '🤖 Analyze Resumes'}
          </button>
        </div>

        {resumes.length > 0 ? (
          <table className="data-table" aria-label="Candidate results">
            <thead>
              <tr>
                <th>Candidate</th>
                <th>File</th>
                <th>Match Score</th>
                <th>Recommendation</th>
                <th>Status</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {resumes.map(r => {
                const detail = parseDetail(r);
                const recLabel = detail?.recommendation_label || r.recommendation || '';
                return (
                  <tr key={r.id}>
                    <td><strong>{r.candidate_name}</strong></td>
                    <td style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>{r.file_name}</td>
                    <td>
                      {r.ai_score != null
                        ? <strong>{Math.round(r.ai_score)}%</strong>
                        : <span style={{ color: 'var(--text-muted)', fontSize: '0.82rem' }}>Pending AI</span>}
                    </td>
                    <td>
                      {recLabel
                        ? <span className={`badge ${REC_BADGE[r.recommendation] || 'blue'}`}>{recLabel}</span>
                        : <span style={{ color: 'var(--text-muted)', fontSize: '0.82rem' }}>—</span>}
                    </td>
                    <td>
                      <span className={`badge ${STATUS_BADGE[r.status] || 'blue'}`}>{r.status}</span>
                    </td>
                    <td>
                      <button className="btn-link" onClick={() => setSelected(r)}>
                        View Details
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        ) : (
          <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>
            {resultsJobId ? 'No resumes uploaded for this job yet.' : 'Select a job and click Load.'}
          </p>
        )}
      </div>

      {/* ── Section 5: Candidate Detail Panel ───────────────────── */}
      {selected && (() => {
        const detail = parseDetail(selected);
        return (
          <div className="detail-panel">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3>👤 {selected.candidate_name}</h3>
              <button className="btn-link" onClick={() => setSelected(null)}>✕ Close</button>
            </div>

            {/* Badge row */}
            <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', marginBottom: '1.25rem' }}>
              <span className={`badge ${STATUS_BADGE[selected.status] || 'blue'}`}>{selected.status}</span>
              {selected.ai_score != null && (
                <span className="badge blue">Match Score: {Math.round(selected.ai_score)}%</span>
              )}
              {detail?.recommendation_label && (
                <span className={`badge ${REC_BADGE[selected.recommendation] || 'blue'}`}>
                  {detail.recommendation_label}
                </span>
              )}
            </div>

            {/* AI analysis grid */}
            {detail && (
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
                {[
                  { label: '✅ Matched Skills',   val: detail.matched_skills    },
                  { label: '⚠ Missing Skills',    val: detail.missing_skills    },
                  { label: '🎓 Education Match',   val: detail.education_match   },
                  { label: '💼 Experience Match',  val: detail.experience_match  },
                  { label: '💪 Strengths',         val: detail.strengths         },
                  { label: '🔴 Concerns',          val: detail.concerns          },
                ].map(({ label, val }) => (
                  <div key={label}>
                    <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-secondary)',
                      textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '0.2rem' }}>
                      {label}
                    </div>
                    <div style={{ fontSize: '0.88rem', color: val ? 'var(--text-primary)' : 'var(--text-muted)' }}>
                      {val || '—'}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Short reason */}
            {detail?.short_reason && (
              <div style={{ marginBottom: '1rem' }}>
                <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-secondary)',
                  textTransform: 'uppercase', marginBottom: '0.3rem' }}>📝 Summary</div>
                <div style={{ fontSize: '0.9rem', lineHeight: 1.6 }}>{detail.short_reason}</div>
              </div>
            )}

            {/* Extracted text */}
            <div>
              <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-secondary)',
                textTransform: 'uppercase', marginBottom: '0.4rem' }}>📄 Extracted Resume Text</div>
              {selected.extracted_text
                ? <div className="detail-text">{selected.extracted_text}</div>
                : <div className="detail-text" style={{ color: 'var(--text-muted)' }}>
                    No text extracted — PDF may be image-based.
                  </div>}
            </div>
          </div>
        );
      })()}
    </div>
  );
}
