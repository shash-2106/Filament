import React, { useState } from 'react';
import {
  X,
  ShieldCheck,
  Copy,
  Check,
  Sparkles,
} from 'lucide-react';
import { useClaimDetailQuery, useEvaluateClaimMutation } from '../../api/queries';
import { Badge } from '../common/Badge';
import { Button } from '../common/Button';

interface ClaimDrawerProps {
  claimId: string | null;
  onClose: () => void;
}

export const ClaimDrawer: React.FC<ClaimDrawerProps> = ({ claimId, onClose }) => {
  const { data: detail, isLoading, isError, error } = useClaimDetailQuery(claimId);
  const claim = detail?.claim;
  const evidenceLinks = detail?.evidence || [];
  const evaluateMutation = useEvaluateClaimMutation();
  const [copied, setCopied] = useState(false);
  const [snapshotInput, setSnapshotInput] = useState('');
  const [showEvalInput, setShowEvalInput] = useState(false);

  if (!claimId) return null;

  const handleCopyId = () => {
    if (claimId) {
      navigator.clipboard.writeText(claimId);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleEvaluate = (e: React.FormEvent) => {
    e.preventDefault();
    if (!snapshotInput.trim() || !claimId) return;
    evaluateMutation.mutate({
      claimId,
      snapshotId: snapshotInput.trim(),
    });
  };

  return (
    <div className="fixed inset-y-0 right-0 z-40 w-full max-w-xl bg-parchment-light border-l border-stone-border shadow-2xl flex flex-col animate-in slide-in-from-right duration-200">
      {/* Drawer Header */}
      <div className="p-5 border-b border-stone-border bg-parchment/70 flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-1.5 flex-wrap">
            {claim && (
              <>
                <Badge type={claim.claim_type} />
                <Badge status={claim.status} />
                <Badge scope={claim.scope} />
              </>
            )}
          </div>
          <h2 className="font-editorial text-2xl text-aubergine font-normal truncate">
            {claim?.subject || 'Claim Inspection'}
          </h2>
          <div className="flex items-center gap-2 text-xs font-mono text-stone-muted mt-1">
            <span className="text-copper font-medium">{claim?.predicate}</span>
            <span>•</span>
            <button
              onClick={handleCopyId}
              className="hover:text-aubergine flex items-center gap-1 cursor-pointer transition-colors"
              title="Copy UUID"
            >
              <span>{claimId.slice(0, 8)}...</span>
              {copied ? <Check className="w-3 h-3 text-sage" /> : <Copy className="w-3 h-3" />}
            </button>
          </div>
        </div>

        <button
          onClick={onClose}
          className="p-1 rounded-sm text-stone-muted hover:text-aubergine hover:bg-stone/30 transition-colors cursor-pointer"
        >
          <X className="w-5 h-5" />
        </button>
      </div>

      {/* Drawer Body */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {isLoading ? (
          <div className="py-16 text-center text-xs font-mono text-stone-muted animate-pulse">
            Retrieving claim assertion and evidence linkages...
          </div>
        ) : isError ? (
          <div className="p-4 rounded-sm bg-terracotta/10 border border-terracotta/30 text-xs font-mono text-terracotta-dark">
            Failed to load claim detail: {error?.message || 'Entity not found or unauthorized.'}
          </div>
        ) : claim ? (
          <>
            {/* Raw Statement Banner */}
            <div className="p-4 rounded-sm bg-parchment border border-stone-border/80">
              <span className="block text-[10px] font-mono uppercase tracking-wider text-stone-muted mb-1.5">
                Statement
              </span>
              <p className="font-editorial text-lg text-aubergine leading-snug italic">
                "{claim.raw_statement}"
              </p>
            </div>

            {/* Structured Object Value */}
            <div>
              <span className="block text-xs font-mono uppercase tracking-wider text-aubergine mb-2 font-medium">
                Structured Value
              </span>
              <div className="p-3 bg-aubergine-deep text-parchment-light rounded-sm font-mono text-xs overflow-x-auto border border-aubergine-border">
                <pre>{JSON.stringify(claim.object_value, null, 2)}</pre>
              </div>
            </div>

            {/* Condition Governance Status */}
            <div className="p-4 rounded-sm bg-stone-light/30 border border-stone-border space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Sparkles className="w-4 h-4 text-copper" />
                  <span className="font-sans text-sm font-medium text-aubergine">
                    Condition-Bound Validity
                  </span>
                </div>
                <Badge variant="citron">
                  {claim.active_condition_version
                    ? `Set v${claim.active_condition_version}`
                    : 'Unconditioned'}
                </Badge>
              </div>

              <p className="text-xs text-stone-muted leading-relaxed">
                {claim.active_condition_version
                  ? `This assertion is bound to Condition Set version ${claim.active_condition_version}. It requires specific file hashes and package versions to remain applicable.`
                  : 'This assertion does not have condition sets established yet. It is unconditioned.'}
              </p>

              <div className="pt-2 border-t border-stone-border/60 flex items-center justify-between">
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => setShowEvalInput(!showEvalInput)}
                  icon={<Sparkles className="w-3.5 h-3.5 text-copper" />}
                >
                  {showEvalInput ? 'Hide Evaluation Form' : 'Evaluate Against Snapshot'}
                </Button>
              </div>

              {/* Transient Evaluation Input */}
              {showEvalInput && (
                <form onSubmit={handleEvaluate} className="pt-2 space-y-2">
                  <label className="block text-[11px] font-mono text-aubergine">
                    Target Environment Snapshot UUID
                  </label>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      placeholder="e.g. 550e8400-e29b-41d4-a716-446655440000"
                      value={snapshotInput}
                      onChange={(e) => setSnapshotInput(e.target.value)}
                      className="flex-1 bg-parchment border border-stone-border rounded-sm py-1 px-2.5 text-xs font-mono text-aubergine focus:outline-none focus:border-copper"
                    />
                    <Button
                      type="submit"
                      size="sm"
                      disabled={evaluateMutation.isPending || !snapshotInput.trim()}
                    >
                      {evaluateMutation.isPending ? 'Evaluating...' : 'Run Check'}
                    </Button>
                  </div>

                  {evaluateMutation.isError && (
                    <div className="text-[11px] font-mono text-terracotta mt-1">
                      {evaluateMutation.error?.message}
                    </div>
                  )}

                  {evaluateMutation.isSuccess && (
                    <div className="p-2.5 rounded-sm bg-parchment border border-stone-border text-xs font-mono mt-2 space-y-1">
                      <div className="flex items-center justify-between">
                        <span className="text-stone-muted">Evaluation Outcome:</span>
                        <Badge outcome={evaluateMutation.data.outcome} />
                      </div>
                      <div className="text-[11px] text-stone-muted">
                        Conditions checked: {evaluateMutation.data.condition_results?.length || 0}
                      </div>
                    </div>
                  )}
                </form>
              )}
            </div>

            {/* Linked Evidence Section */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-1.5 text-xs font-mono uppercase tracking-wider text-aubergine font-medium">
                  <ShieldCheck className="w-4 h-4 text-copper" />
                  <span>Linked Provenance Evidence ({evidenceLinks.length})</span>
                </div>
              </div>

              {evidenceLinks.length > 0 ? (
                <div className="space-y-2">
                  {evidenceLinks.map((link) => (
                    <div
                      key={link.evidence_id}
                      className="p-3 bg-parchment rounded-sm border border-stone-border/80 space-y-1.5"
                    >
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-mono text-aubergine font-medium truncate max-w-[200px]">
                          {link.evidence_id}
                        </span>
                        <span className="text-[11px] font-mono text-copper uppercase font-medium">
                          {link.support_type} ({Math.round(link.confidence_weight * 100)}%)
                        </span>
                      </div>
                      {link.extraction_notes && (
                        <p className="text-xs text-stone-muted font-sans">
                          {link.extraction_notes}
                        </p>
                      )}
                      <div className="flex items-center justify-between text-[11px] font-mono text-stone-muted pt-1 border-t border-stone-border/50">
                        <span>source: {link.source_type || 'file'}</span>
                        <span>{new Date(link.created_at).toLocaleDateString()}</span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="p-4 rounded-sm border border-dashed border-stone-border text-center text-xs text-stone-muted font-sans">
                  No evidence records linked to this claim.
                </div>
              )}
            </div>

            {/* Technical Metadata */}
            <div className="p-4 rounded-sm bg-parchment-dark/30 border border-stone-border text-xs font-mono space-y-1.5 text-stone-muted">
              <div className="flex items-center justify-between">
                <span>Claim Version:</span>
                <span className="text-aubergine font-medium">v{claim.version}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Confidence Score:</span>
                <span className="text-aubergine font-medium">{claim.confidence}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Authoring Agent:</span>
                <span className="text-aubergine truncate max-w-[240px]">{claim.agent_id}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Established Date:</span>
                <span className="text-aubergine">{new Date(claim.created_at).toLocaleString()}</span>
              </div>
            </div>
          </>
        ) : null}
      </div>
    </div>
  );
};
