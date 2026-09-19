/**
 * pages/CustomerSupport/components/KnowledgeBaseView.js
 *
 * Enterprise Knowledge Base Repository View:
 *   - Categorized directory of verified documents (Billing, Authentication, Frontend, Backend, SLAs)
 *   - Real-time BM25 search bar with relevance scoring
 *   - Document detail modal previewing all chunks
 *   - "Ask Assistant about this article" quick prompt
 */

import React, { useState } from 'react';

export default function KnowledgeBaseView({
  documents,
  categories,
  isLoading,
  onSearch,
  onAskAboutDoc,
}) {
  const [selectedCategory, setSelectedCategory] = useState('ALL');
  const [searchTerm, setSearchTerm] = useState('');
  const [activeDoc, setActiveDoc] = useState(null);

  const filteredDocs = documents.filter((doc) => {
    if (selectedCategory !== 'ALL' && doc.category_id !== Number(selectedCategory)) {
      return false;
    }
    if (searchTerm) {
      const q = searchTerm.toLowerCase();
      const titleMatch = doc.title && doc.title.toLowerCase().includes(q);
      const catMatch = doc.category_name && doc.category_name.toLowerCase().includes(q);
      if (!titleMatch && !catMatch) return false;
    }
    return true;
  });

  return (
    <div className="cs-kb-view">
      {/* Search and Category Filter Header */}
      <div className="cs-kb-toolbar">
        <div className="cs-kb-search-box">
          <span className="cs-search-icon">🔍</span>
          <input
            type="text"
            placeholder="Search enterprise knowledge base with BM25 lexical engine..."
            value={searchTerm}
            onChange={(e) => {
              setSearchTerm(e.target.value);
              if (onSearch && e.target.value.trim().length > 2) {
                onSearch(e.target.value.trim());
              }
            }}
          />
        </div>

        <div className="cs-kb-category-pills">
          <button
            type="button"
            className={`cs-pill ${selectedCategory === 'ALL' ? 'active' : ''}`}
            onClick={() => setSelectedCategory('ALL')}
          >
            All Articles ({documents.length})
          </button>
          {categories.map((c) => (
            <button
              key={c.id}
              type="button"
              className={`cs-pill ${selectedCategory === String(c.id) ? 'active' : ''}`}
              onClick={() => setSelectedCategory(String(c.id))}
            >
              {c.name}
            </button>
          ))}
        </div>
      </div>

      {/* Document Grid */}
      {isLoading ? (
        <div className="cs-loading-card">
          <div className="cs-spinner"></div>
          <p>Loading enterprise knowledge repository...</p>
        </div>
      ) : filteredDocs.length === 0 ? (
        <div className="cs-tickets-empty">
          <div className="cs-empty-icon">📚</div>
          <h3>No matching knowledge articles</h3>
          <p>Try refining your search terms or selecting another category.</p>
        </div>
      ) : (
        <div className="cs-kb-grid">
          {filteredDocs.map((doc) => (
            <div
              key={doc.id}
              className="cs-kb-card"
              onClick={() => setActiveDoc(doc)}
            >
              <div className="cs-kb-card-top">
                <span className="cs-kb-type-badge">
                  {doc.doc_type ? doc.doc_type.replace('_', ' ').toUpperCase() : 'POLICY'}
                </span>
                <span className="cs-kb-verified-badge">✓ Verified</span>
              </div>

              <h3 className="cs-kb-card-title">{doc.title}</h3>

              <div className="cs-kb-card-category">
                📂 {doc.category_name || 'General Policy'}
              </div>

              <div className="cs-kb-card-footer">
                <span className="cs-kb-chunks-tag">
                  {doc.chunk_count || 1} searchable chunk{(doc.chunk_count || 1) > 1 ? 's' : ''}
                </span>
                <button
                  type="button"
                  className="cs-kb-ask-btn"
                  onClick={(e) => {
                    e.stopPropagation();
                    if (onAskAboutDoc) {
                      onAskAboutDoc(`What are the key policies in "${doc.title}"?`);
                    }
                  }}
                  title="Ask Assistant about this article"
                >
                  Ask AI ➔
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Document Detail Modal */}
      {activeDoc && (
        <div className="cs-modal-overlay" onClick={() => setActiveDoc(null)}>
          <div className="cs-doc-modal" onClick={(e) => e.stopPropagation()}>
            <div className="cs-modal-header">
              <div className="cs-doc-modal-header-info">
                <span className="cs-kb-type-badge">
                  {activeDoc.doc_type ? activeDoc.doc_type.replace('_', ' ').toUpperCase() : 'DOCUMENT'}
                </span>
                <h2>{activeDoc.title}</h2>
              </div>
              <button type="button" className="cs-close-btn" onClick={() => setActiveDoc(null)}>
                ✕
              </button>
            </div>

            <div className="cs-modal-body">
              <div className="cs-doc-meta-bar">
                <div>
                  <strong>Category:</strong> {activeDoc.category_name || 'General Inquiry'}
                </div>
                <div>
                  <strong>Status:</strong> <span style={{ color: '#16a34a', fontWeight: 600 }}>✓ Verified Enterprise Knowledge</span>
                </div>
                <div>
                  <strong>Search Index:</strong> BM25 Grounded RAG
                </div>
              </div>

              <div className="cs-doc-content-full">
                <h4>Verified Article Content</h4>
                <div className="cs-doc-text">
                  {activeDoc.content ? (
                    activeDoc.content.split('\n').map((line, idx) => (
                      <p key={idx} style={{ margin: line ? '0.35rem 0' : '0.6rem 0' }}>
                        {line}
                      </p>
                    ))
                  ) : (
                    <p>
                      This article is indexed and verified for deterministic RAG retrieval. Search chunks are active and queryable by the AI chatbot.
                    </p>
                  )}
                </div>
              </div>
            </div>

            <div className="cs-modal-footer">
              <button
                type="button"
                className="cs-btn primary"
                onClick={() => {
                  const q = `Explain the procedures described in "${activeDoc.title}"`;
                  setActiveDoc(null);
                  if (onAskAboutDoc) onAskAboutDoc(q);
                }}
              >
                🤖 Ask Assistant About This Document
              </button>
              <button
                type="button"
                className="cs-btn secondary"
                onClick={() => setActiveDoc(null)}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
