import React, { useState } from 'react';
import {
  X,
  ShieldCheck,
  GitFork,
  FileText,
  Activity,
  Play,
  CheckCircle2,
  AlertTriangle,
  Clock,
  Layers,
} from 'lucide-react';
import {
  useClaimDetailQuery,
  useClaimConditionsQuery,
  useSnapshotsQuery,
  useEvaluateClaimMutation,
} from '../../api/queries';
import { Badge } from '../common/Badge';
import { Button } from '../common/Button';

interface ClaimDrawerProps {
  claimId: string;
  onClose: () => void;
}

export const ClaimDrawer: React.FC<ClaimDrawerProps> = ({ claimId, onClose }) => {
  const { data, isLoading, isError, refetch } = useClaimDetailQuery(claimId);
  const { data: conditionSet, isLoading: isCondLoading } = useClaimConditionsQuery(claimId);
  const { data: snapshots } = useSnapshotsQuery();
  const evaluateMutation = useEvaluateClaimMutation();
  const [selectedSnapshotId, setSelectedSnapshotId] = useState<string>('');
  const [evalResult, setEvalResult] = useState<any | null>(null);

  // Auto-select latest or matching snapshot
  const activeSnapshotId = selectedSnapshotId || (snapshots && snapshots.length > 0 ? snapshots[0].id : '');

  const handleEvaluate = () => {
    if (!activeSnapshotId) return;
    evaluateMutation.mutate(
      { claimId, snapshotId: activeSnapshotId },
      {
        onSuccess: (res) => {
          setEvalResult(res);
          refetch();
        },
      }
    );
  };

  return (
    <div className="fixed inset-y-0 right-0 z-50 w-full max-w-xl md:max-w-2xl bg-[#0E1714] border-l border-[#294537] shadow-2xl flex flex-col select-none">
      {/* Drawer Header */}
      <div className="p-4 border-b border-[#294537] flex items-center justify-between bg-[#14231D] shrink-0">
        <div className="flex items-center gap-2">
          <ShieldCheck className="w-4 h-4 text-phosphor" />
          <h2 className="font-heading text-sm font-bold text-graphite-text">
            Memory Inspection & Provenance
          </h2>
        </div>
        <button
          onClick={onClose}
          className="text-graphite-text-tertiary hover:text-graphite-text p-1.5 rounded hover:bg-[#1C3027] transition-colors"
          title="Close Drawer"
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
            <div className="space-y-3 bg-[#14231D] border border-[#294537] rounded p-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <h4 className="font-mono text-xs font-semibold uppercase tracking-wider text-graphite-text flex items-center gap-1.5">
                  <GitFork className="w-3.5 h-3.5 text-phosphor" />
                  <span>Validity Requirements & Evaluation</span>
                </h4>
                {conditionSet && (
                  <span className="font-mono text-[10px] text-phosphor bg-[#1C3027] px-2 py-0.5 rounded border border-[#294537]">
                    req: v{conditionSet.version} ({conditionSet.conditions.length} conditions)
                  </span>
                )}
              </div>

              <p className="text-xs text-graphite-text-secondary leading-relaxed font-sans">
                Test whether this memory's environmental requirements are satisfied in current infrastructure.
              </p>

              {/* Conditions List */}
              {isCondLoading ? (
                <div className="p-3 text-center font-mono text-graphite-text-tertiary animate-pulse">
                  Loading governing conditions...
                </div>
              ) : conditionSet && conditionSet.conditions.length > 0 ? (
                <div className="space-y-2 pt-1">
                  {conditionSet.conditions.map((cond) => (
                    <div
                      key={cond.id}
                      className="p-2.5 rounded bg-[#0B1210] border border-[#294537] font-mono text-[11px] space-y-1.5"
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-phosphor font-medium">{cond.condition_type}</span>
                        <span className={`text-[10px] px-1.5 py-0.2 rounded border ${
                          cond.is_critical
                            ? 'bg-[#A96580]/15 text-[#D67D65] border-[#A96580]/40'
                            : 'bg-[#1C3027] text-graphite-text-tertiary border-[#294537]'
                        }`}>
                          {cond.is_critical ? 'CRITICAL' : 'OPTIONAL'}
                        </span>
                      </div>
                      <div className="text-graphite-text break-all">
                        <span className="text-graphite-text-tertiary">Target:</span> {cond.target_path}
                      </div>
                      <div className="text-graphite-text-secondary text-[10px] flex items-center gap-2">
                        <span>Comparator: <span className="text-phosphor">{cond.comparator}</span></span>
                      </div>
                      {cond.expected_hash && (
                        <div className="text-[10px] text-graphite-text-tertiary truncate">
                          Expected Hash: <span className="font-mono">{cond.expected_hash}</span>
                        </div>
                      )}
                    </div>
                  ))}
                  {conditionSet.rationale && (
                    <p className="text-[11px] font-sans text-graphite-text-tertiary italic pt-1">
                      Rationale: "{conditionSet.rationale}"
                    </p>
                  )}
                </div>
              ) : (
                <div className="p-3 bg-[#0B1210] border border-[#294537] rounded text-center text-graphite-text-tertiary font-mono text-xs">
                  No validity requirements configured for this claim.
                </div>
              )}

              {/* Snapshot Evaluation Selector & Action */}
              <div className="pt-3 border-t border-[#1C3027] space-y-2.5">
                <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
                  <div className="flex items-center gap-1.5 flex-1 min-w-0">
                    <Layers className="w-3.5 h-3.5 text-phosphor shrink-0" />
                    <select
                      value={activeSnapshotId}
                      onChange={(e) => setSelectedSnapshotId(e.target.value)}
                      className="w-full bg-[#0B1210] border border-[#294537] rounded px-2.5 py-1.5 text-xs text-graphite-text font-mono focus:outline-none focus:border-phosphor truncate"
                    >
                      {snapshots && snapshots.length > 0 ? (
                        snapshots.map((s) => (
                          <option key={s.id} value={s.id}>
                            {s.source_ref} ({s.id.slice(0, 8)})
                          </option>
                        ))
                      ) : (
                        <option value="">No snapshots recorded</option>
                      )}
                    </select>
                  </div>
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={handleEvaluate}
                    disabled={evaluateMutation.isPending || !activeSnapshotId}
                    icon={<Play className={`w-3 h-3 text-phosphor ${evaluateMutation.isPending ? 'animate-spin' : ''}`} />}
                  >
                    {evaluateMutation.isPending ? 'Auditing...' : 'Evaluate Against Snapshot'}
                  </Button>
                </div>

                {evalResult && (
                  <div className={`p-3 rounded border text-xs font-mono space-y-2 ${
                    evalResult.outcome === 'applicable'
                      ? 'bg-[#0B1210] border-phosphor/50 text-phosphor'
                      : 'bg-[#A96580]/15 border-[#A96580]/40 text-[#D67D65]'
                  }`}>
                    <div className="font-bold flex items-center justify-between uppercase">
                      <span className="flex items-center gap-1.5">
                        {evalResult.outcome === 'applicable' ? (
                          <CheckCircle2 className="w-4 h-4 text-phosphor" />
                        ) : (
                          <AlertTriangle className="w-4 h-4 text-[#D67D65]" />
                        )}
                        Outcome: {evalResult.outcome.replace('_', ' ')}
                      </span>
                      <span className="text-[10px] font-normal lowercase text-graphite-text-tertiary">
                        req v{evalResult.active_condition_version}
                      </span>
                    </div>

                    {evalResult.condition_results && evalResult.condition_results.length > 0 && (
                      <div className="space-y-1.5 pt-1 border-t border-white/5">
                        {evalResult.condition_results.map((cr: any, idx: number) => (
                          <div key={idx} className="text-[11px] flex flex-col gap-0.5">
                            <div className="flex items-center justify-between">
                              <span className="text-graphite-text font-medium">{cr.target || cr.target_path}</span>
                              <span className={`text-[10px] px-1 py-0.2 rounded ${
                                cr.status === 'SATISFIED'
                                  ? 'bg-phosphor/20 text-phosphor'
                                  : 'bg-[#A96580]/30 text-[#D67D65]'
                              }`}>
                                {cr.status} ({cr.reason})
                              </span>
                            </div>
                            {cr.status !== 'SATISFIED' && cr.details && (
                              <div className="text-[10px] text-graphite-text-secondary break-all">
                                expected: {cr.details.expected_hash?.slice(0, 16)}... | actual: {cr.details.actual_hash?.slice(0, 16)}...
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
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
                      key={ev.evidence_id || ev.id || idx}
                      className="p-3 bg-[#14231D] border border-[#294537] rounded space-y-2 font-mono text-[11px]"
                    >
                      <div className="flex items-center justify-between text-graphite-text-tertiary">
                        <span className="text-phosphor uppercase font-medium">
                          Source: {ev.source_type || 'unspecified'}
                        </span>
                        <span className="text-[10px] flex items-center gap-1">
                          <Clock className="w-3 h-3 text-graphite-text-tertiary" />
                          {ev.created_at ? new Date(ev.created_at).toLocaleString() : 'Verified'}
                        </span>
                      </div>

                      {ev.raw_snippet && (
                        <div className="p-2.5 bg-[#0B1210] border border-[#1C3027] rounded text-graphite-text font-sans text-xs italic leading-relaxed">
                          "{ev.raw_snippet}"
                        </div>
                      )}

                      <div className="space-y-1 text-[10px] text-graphite-text-tertiary">
                        <div>
                          <span className="text-graphite-text-secondary">Source URI:</span>{' '}
                          <span className="text-graphite-text font-mono">
                            {ev.source_uri ? ev.source_uri : 'No source URI provided'}
                          </span>
                        </div>
                        {ev.evidence_id && (
                          <div className="truncate">
                            <span className="text-graphite-text-secondary">Evidence ID:</span> {ev.evidence_id}
                          </div>
                        )}
                        {ev.content_hash && (
                          <div className="truncate">
                            <span className="text-graphite-text-secondary">Digest:</span> {ev.content_hash}
                          </div>
                        )}
                        {ev.extraction_notes && (
                          <div className="font-sans text-graphite-text-secondary italic">
                            Notes: {ev.extraction_notes}
                          </div>
                        )}
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
