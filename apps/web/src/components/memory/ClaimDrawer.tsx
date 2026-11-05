import React, { useState } from 'react';
import {
  X,
  ShieldCheck,
  GitFork,
  FileText,
  Activity,
  Play,
} from 'lucide-react';
import { useClaimDetailQuery, useEvaluateClaimMutation } from '../../api/queries';
import { Badge } from '../common/Badge';
import { Button } from '../common/Button';

interface ClaimDrawerProps {
  claimId: string;
  onClose: () => void;
}

export const ClaimDrawer: React.FC<ClaimDrawerProps> = ({ claimId, onClose }) => {
  const { data, isLoading, isError, refetch } = useClaimDetailQuery(claimId);
  const evaluateMutation = useEvaluateClaimMutation();
  const [evalResult, setEvalResult] = useState<any | null>(null);

  const handleEvaluate = () => {
    evaluateMutation.mutate(
      { claimId, snapshotId: 'current' },
      {
        onSuccess: (res) => {
          setEvalResult(res);
          refetch();
        },
      }
    );
  };

  return (
    <div className="fixed inset-y-0 right-0 z-50 w-full max-w-xl bg-[#0E1714] border-l border-[#294537] shadow-2xl flex flex-col select-none">
      {/* Drawer Header */}
      <div className="p-4 border-b border-[#294537] flex items-center justify-between bg-[#14231D]">
        <div className="flex items-center gap-2">
          <ShieldCheck className="w-4 h-4 text-phosphor" />
          <h2 className="font-heading text-sm font-bold text-graphite-text">
            Memory Inspection & Provenance
          </h2>
        </div>
        <button
          onClick={onClose}
          className="text-graphite-text-tertiary hover:text-graphite-text p-1 rounded hover:bg-[#1C3027] transition-colors"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Drawer Body */}
      <div className="p-5 overflow-y-auto flex-1 space-y-6 text-xs bg-[#0B1210]">
        {isLoading ? (
          <div className="p-8 text-center font-mono text-graphite-text-tertiary animate-pulse">
            Loading memory telemetry from Supabase...
          </div>
        ) : isError || !data ? (
          <div className="p-4 bg-[#A96580]/15 border border-[#A96580]/40 rounded text-[#A96580] font-mono">
            Failed to load memory inspection details.
          </div>
        ) : (
          <>
            {/* Primary Statement Card */}
            <div className="p-4 rounded bg-[#14231D] border border-[#294537] space-y-3">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <Badge variant="type" type={data.claim.claim_type}>
                    {data.claim.claim_type}
                  </Badge>
                  <Badge variant="status" status={data.claim.status}>
                    {data.claim.status}
                  </Badge>
                </div>
                <span className="font-mono text-[10px] text-graphite-text-tertiary">
                  ID: {data.claim.id.slice(0, 8)}...
                </span>
              </div>

              <div>
                <h3 className="font-mono text-xs text-phosphor font-semibold">
                  {data.claim.subject} : {data.claim.predicate}
                </h3>
                <p className="mt-2 text-sm text-graphite-text font-sans leading-relaxed">
                  {data.claim.raw_statement}
                </p>
              </div>

              <div className="pt-2 border-t border-[#1C3027] flex items-center justify-between text-[11px] font-mono text-graphite-text-tertiary">
                <span>Confidence: {(Number(data.claim.confidence) * 100).toFixed(0)}%</span>
                <span>Scope: {data.claim.scope}</span>
                <span>Version: v{data.claim.version}</span>
              </div>
            </div>

            {/* Environmental Conditions & Verification Section */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h4 className="font-mono text-xs font-semibold uppercase tracking-wider text-graphite-text flex items-center gap-1.5">
                  <GitFork className="w-3.5 h-3.5 text-phosphor" />
                  <span>Validity Requirements & Evaluation</span>
                </h4>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={handleEvaluate}
                  disabled={evaluateMutation.isPending}
                  icon={<Play className={`w-3 h-3 text-phosphor ${evaluateMutation.isPending ? 'animate-spin' : ''}`} />}
                >
                  {evaluateMutation.isPending ? 'Auditing...' : 'Evaluate Against Environment'}
                </Button>
              </div>

              <p className="text-xs text-graphite-text-secondary leading-relaxed font-sans">
                Test whether this memory's environmental requirements are satisfied in current infrastructure.
              </p>

              {evalResult && (
                <div className={`p-3 rounded border text-xs font-mono space-y-1 ${
                  evalResult.outcome === 'applicable'
                    ? 'bg-[#14231D] border-phosphor/50 text-phosphor'
                    : 'bg-[#A96580]/15 border-[#A96580]/40 text-[#D67D65]'
                }`}>
                  <div className="font-bold flex items-center gap-1.5 uppercase">
                    Outcome: {evalResult.outcome}
                  </div>
                  <div className="text-[11px] text-graphite-text-secondary">
                    {evalResult.explanation || 'Verification completed against environment state.'}
                  </div>
                </div>
              )}
            </div>

            {/* Cryptographic Evidence & Provenance Section */}
            <div className="space-y-3">
              <h4 className="font-mono text-xs font-semibold uppercase tracking-wider text-graphite-text flex items-center gap-1.5">
                <FileText className="w-3.5 h-3.5 text-phosphor" />
                <span>Supporting Evidence Provenance ({data.evidence?.length || 0})</span>
              </h4>

              {data.evidence && data.evidence.length > 0 ? (
                <div className="space-y-2.5">
                  {data.evidence.map((ev: any, idx: number) => (
                    <div
                      key={ev.id || idx}
                      className="p-3 bg-[#14231D] border border-[#294537] rounded space-y-2 font-mono text-[11px]"
                    >
                      <div className="flex items-center justify-between text-graphite-text-tertiary">
                        <span className="text-phosphor uppercase">
                          Source: {ev.source_type}
                        </span>
                        <span className="text-[10px]">
                          {ev.created_at ? new Date(ev.created_at).toLocaleTimeString() : 'Verified'}
                        </span>
                      </div>

                      {ev.raw_snippet && (
                        <div className="p-2 bg-[#0B1210] border border-[#1C3027] rounded text-graphite-text italic">
                          "{ev.raw_snippet}"
                        </div>
                      )}

                      <div className="text-[10px] text-graphite-text-tertiary truncate">
                        URI: {ev.source_uri}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="p-3 bg-[#14231D] border border-[#294537] rounded text-center text-graphite-text-tertiary font-mono">
                  No explicit evidence recorded for this claim.
                </div>
              )}
            </div>

            {/* Technical Structured Payload */}
            <div className="space-y-2">
              <h4 className="font-mono text-xs font-semibold uppercase tracking-wider text-graphite-text flex items-center gap-1.5">
                <Activity className="w-3.5 h-3.5 text-phosphor" />
                <span>Structured Value</span>
              </h4>
              <pre className="p-3 bg-[#0B1210] border border-[#294537] rounded font-mono text-[11px] text-graphite-text overflow-x-auto">
                {JSON.stringify(data.claim.object_value, null, 2)}
              </pre>
            </div>
          </>
        )}
      </div>
    </div>
  );
};
