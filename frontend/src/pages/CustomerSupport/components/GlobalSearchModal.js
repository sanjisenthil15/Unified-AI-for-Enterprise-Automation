/**
 * pages/CustomerSupport/components/GlobalSearchModal.js
 *
 * Unified Cross-Entity Global Search Modal:
 *   - Searches Knowledge Base, Support Tickets, and Categories
 *   - Type badges, snippet previews, and instant navigation
 */

import React, { useState, useEffect } from 'react';
import { globalSupportSearch } from '../../../api/customerSupportApi';

export default function GlobalSearchModal({
  isOpen,
  onClose,
  onSelectKnowledgeDoc,
  onSelectTicket,
}) {
  const [searchTerm, setSearchTerm] = useState('');
  const [results, setResults] = useState([]);
  const [isSearching, setIsSearching] = useState(false);

  useEffect(() => {
    if (!searchTerm.trim()) {
      setResults([]);
      setIsSearching(false);
      return;
    }

    const timer = setTimeout(async () => {
      setIsSearching(true);
      try {
        const res = await globalSupportSearch(searchTerm.trim(), 15);
        setResults(res.results || []);
      } catch (err) {
        setResults([]);
      } finally {
        setIsSearching(false);
      }
    }, 250);

    return () => clearTimeout(timer);
  }, [searchTerm]);

  if (!isOpen) return null;

  return (
    <div className="cs-modal-overlay" onClick={onClose}>
      <div className="cs-search-modal" onClick={(e) => e.stopPropagation()}>
        <div className="cs-search-modal-header">
          <span className="cs-search-modal-icon">🔍</span>
          <input
            autoFocus
            type="text"
            className="cs-search-modal-input"
            placeholder="Search verified knowledge base, tickets, policies, and categories..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
          <button type="button" className="cs-close-btn" onClick={onClose}>
            ✕
          </button>
        </div>

        <div className="cs-search-modal-body">
          {isSearching ? (
            <div className="cs-search-loading">
              <div className="cs-spinner small"></div>
              <span>Searching enterprise systems...</span>
            </div>
          ) : results.length === 0 ? (
            <div className="cs-search-empty">
              {searchTerm ? (
                <p>No matching enterprise knowledge articles or tickets found.</p>
              ) : (
                <p>Type keywords to search across verified policies, FAQs, tickets, and categories.</p>
              )}
            </div>
          ) : (
            <div className="cs-search-results-list">
              {results.map((item) => (
                <div
                  key={item.id}
                  className="cs-search-item"
                  onClick={() => {
                    onClose();
                    if (item.type === 'knowledge') {
                      const docId = item.id.replace('kb_', '');
                      onSelectKnowledgeDoc(Number(docId));
                    } else if (item.type === 'ticket') {
                      const tktId = item.id.replace('tkt_', '');
                      onSelectTicket(Number(tktId));
                    }
                  }}
                >
                  <div className="cs-search-item-top">
                    <span className={`cs-search-badge ${item.type}`}>
                      {item.type === 'knowledge' ? '📚 KNOWLEDGE' : item.type === 'ticket' ? '🎫 TICKET' : '📂 CATEGORY'}
                    </span>
                    <span className="cs-search-item-title">{item.title}</span>
                    {item.status && <span className="cs-search-item-status">{item.status}</span>}
                  </div>

                  {item.snippet && (
                    <div className="cs-search-item-snippet">{item.snippet}</div>
                  )}

                  <div className="cs-search-item-footer">
                    <span>{item.category_name || 'General'}</span>
                    <span className="cs-search-action-tag">Open item ➔</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
