import React, { useState } from 'react';
import {
  ShieldCheck,
  FileCode,
  Terminal,
  Plus,
  Hash,
  Copy,
  Check,
  Search,
} from 'lucide-react';
import { useEvidenceQuery, useRecordEvidenceMutation } from '../api/queries';
import { useAuth } from '../context/auth';
import { Card } from '../components/common/Card';
import { Button } from '../components/common/Button';
import { EmptyState } from '../components/common/EmptyState';

export const EvidencePage: React.FC = () => {
  const { isConfigured } = useAuth();
  const { data: evidenceList, isLoading, isError, error } = useEvidenceQuery();
  const recordMutation = useRecordEvidenceMutation();

  const [showCreateModal, setShowCreateModal] = useState(false);
  const [sourceType, setSourceType] = useState('tool_output');
  const [sourceUri, setSourceUri] = useState('');
  const [rawSnippet, setRawSnippet] = useState('');
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [searchFilter, setSearchFilter] = useState('');

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(text);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const handleRecord = (e: React.FormEvent) => {
    e.preventDefault();
    if (!sourceUri.trim() || !rawSnippet.trim()) return;

    recordMutation.mutate(
      {
        source_type: sourceType,
        source_uri: sourceUri.trim(),
        raw_snippet: rawSnippet,
      },
      {
        onSuccess: () => {
          setShowCreateModal(false);
          setSourceUri('');
          setRawSnippet('');
        },
      }
    );
  };

  const filteredEvidence = (evidenceList || []).filter((item) => {
    if (!searchFilter) return true;
    const q = searchFilter.toLowerCase();
    return (
      item.source_uri.toLowerCase().includes(q) ||
      item.source_type.toLowerCase().includes(q) ||
      item.content_hash.toLowerCase().includes(q) ||
      item.raw_snippet.toLowerCase().includes(q)
    );
  });

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-12 animate-in fade-in duration-200">
      {/* Header Banner */}
      <div className="border-b border-stone-border pb-5 flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-xs font-mono text-copper uppercase tracking-wider mb-1.5 font-medium">
            <span className="w-2 h-2 rounded-full bg-copper inline-block" />
            <span>Cryptographic Provenance</span>
          </div>
          <h1 className="font-editorial text-3xl md:text-4xl text-charcoal font-normal">
            Supporting Evidence
          </h1>
          <p className="text-sm text-stone-muted mt-1 font-sans max-w-2xl leading-relaxed">
            Content-addressed SHA-256 artifacts, git commits, and tool execution outputs providing mathematical grounding for memory assertions.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button
            size="sm"
            onClick={() => setShowCreateModal(true)}
            icon={<Plus className="w-3.5 h-3.5" />}
          >
            Record Evidence
          </Button>
        </div>
      </div>

      {!isConfigured ? (
        <Card title="Workspace Evidence Ledger">
          <EmptyState
            icon={ShieldCheck}
            title="Authentication Required"
            description="Configure your Agent Bearer API key in the header to view or record immutable evidence."
          />
        </Card>
      ) : isLoading ? (
        <div className="py-24 text-center text-xs font-mono text-stone-muted animate-pulse">
          Querying immutable evidence artifacts...
        </div>
      ) : isError ? (
        <div className="p-4 rounded-sm bg-terracotta/10 border border-terracotta/30 text-xs font-mono text-terracotta-dark">
          Failed to load evidence: {error?.message}
        </div>
      ) : evidenceList && evidenceList.length > 0 ? (
        <div className="space-y-4">
          {/* Search bar */}
          <div className="flex items-center justify-between gap-4">
            <div className="relative flex-1 max-w-md">
              <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-stone-muted" />
              <input
                type="text"
                value={searchFilter}
                onChange={(e) => setSearchFilter(e.target.value)}
                placeholder="Filter by URI, SHA-256 hash, or snippet content..."
                className="w-full bg-bone border border-stone-border rounded-sm py-1.5 pl-8 pr-3 text-xs font-sans text-charcoal focus:outline-none focus:border-copper focus:ring-1 focus:ring-copper/40"
              />
            </div>
            <span className="text-xs font-mono text-stone-muted">
              {filteredEvidence.length} artifact{filteredEvidence.length !== 1 ? 's' : ''}
            </span>
          </div>

          {/* Grid of Evidence Artifacts */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {filteredEvidence.map((ev) => (
              <Card key={ev.id} className="bg-bone-light border-stone-border hover:border-copper/60 transition-colors">
                <div className="space-y-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <div className="w-7 h-7 rounded-sm bg-bone border border-stone-border flex items-center justify-center text-copper">
                        {ev.source_type === 'git_commit' ? (
                          <Terminal className="w-3.5 h-3.5" />
                        ) : ev.source_type === 'tool_output' ? (
                          <FileCode className="w-3.5 h-3.5" />
                        ) : (
                          <ShieldCheck className="w-3.5 h-3.5" />
                        )}
                      </div>
                      <div>
                        <span className="text-[10px] font-mono uppercase tracking-wider text-copper font-medium">
                          {ev.source_type}
                        </span>
                        <h4 className="text-xs font-mono font-medium text-charcoal truncate max-w-xs" title={ev.source_uri}>
                          {ev.source_uri}
                        </h4>
                      </div>
                    </div>

                    <span className="text-[10px] font-mono text-stone-muted">
                      {new Date(ev.created_at).toLocaleDateString()}
                    </span>
                  </div>

                  {/* SHA-256 Hash Display */}
                  <div className="flex items-center justify-between text-xs font-mono p-2 rounded-sm bg-bone border border-stone-border/80">
                    <div className="flex items-center gap-1.5 min-w-0">
                      <Hash className="w-3 h-3 text-stone-muted flex-shrink-0" />
                      <span className="truncate text-stone-muted text-[11px]" title={ev.content_hash}>
                        {ev.content_hash}
                      </span>
                    </div>
                    <button
                      onClick={() => handleCopy(ev.content_hash)}
                      className="text-stone-muted hover:text-copper ml-2 cursor-pointer flex-shrink-0"
                      title="Copy content hash"
                    >
                      {copiedId === ev.content_hash ? (
                        <Check className="w-3.5 h-3.5 text-sage" />
                      ) : (
                        <Copy className="w-3.5 h-3.5" />
                      )}
                    </button>
                  </div>

                  {/* Snippet Preview */}
                  <div className="p-2.5 rounded-sm bg-bone border border-stone-border/70 text-xs font-mono text-charcoal line-clamp-3 whitespace-pre-wrap leading-relaxed">
                    {ev.raw_snippet}
                  </div>
                </div>
              </Card>
            ))}
          </div>
        </div>
      ) : (
        <Card title="Workspace Evidence Ledger">
          <EmptyState
            icon={ShieldCheck}
            title="No Supporting Evidence Artifacts"
            description="No cryptographic evidence has been recorded in this workspace yet. Record evidence to ground AI memories in verifiable ground truth."
            actionLabel="Record First Evidence"
            onAction={() => setShowCreateModal(true)}
          />
        </Card>
      )}

      {/* Record Evidence Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 bg-charcoal-deep/60 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-bone-light border border-stone-border rounded-sm max-w-lg w-full shadow-lg overflow-hidden animate-in fade-in duration-150">
            <div className="px-5 py-4 border-b border-stone-border bg-bone flex items-center justify-between">
              <h3 className="font-editorial text-lg text-charcoal font-medium">
                Record Supporting Evidence
              </h3>
              <button
                onClick={() => setShowCreateModal(false)}
                className="text-stone-muted hover:text-charcoal text-sm"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleRecord} className="p-5 space-y-4">
              <div>
                <label className="block text-xs font-mono uppercase tracking-wider text-charcoal font-medium mb-1">
                  Source Type
                </label>
                <select
                  value={sourceType}
                  onChange={(e) => setSourceType(e.target.value)}
                  className="w-full bg-bone border border-stone-border rounded-sm p-2 text-xs font-mono text-charcoal focus:outline-none focus:border-copper"
                >
                  <option value="tool_output">tool_output (CLI or Tool result)</option>
                  <option value="git_commit">git_commit (Git commit hash/diff)</option>
                  <option value="api_response">api_response (External API payload)</option>
                  <option value="user_turn">user_turn (User prompt or assertion)</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-mono uppercase tracking-wider text-charcoal font-medium mb-1">
                  Source URI / Path
                </label>
                <input
                  type="text"
                  value={sourceUri}
                  onChange={(e) => setSourceUri(e.target.value)}
                  placeholder="e.g., config/auth.json or commit:8ace12..."
                  className="w-full bg-bone border border-stone-border rounded-sm p-2 text-xs font-mono text-charcoal focus:outline-none focus:border-copper"
                  required
                />
              </div>

              <div>
                <label className="block text-xs font-mono uppercase tracking-wider text-charcoal font-medium mb-1">
                  Raw Content / Code Snippet
                </label>
                <textarea
                  value={rawSnippet}
                  onChange={(e) => setRawSnippet(e.target.value)}
                  placeholder="Paste snippet or file contents to compute cryptographic SHA-256 hash..."
                  rows={4}
                  className="w-full bg-bone border border-stone-border rounded-sm p-2 text-xs font-mono text-charcoal focus:outline-none focus:border-copper"
                  required
                />
              </div>

              <div className="pt-2 flex items-center justify-end gap-2 border-t border-stone-border">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => setShowCreateModal(false)}
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  size="sm"
                  disabled={recordMutation.isPending}
                >
                  {recordMutation.isPending ? 'Computing SHA-256...' : 'Record Evidence'}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
