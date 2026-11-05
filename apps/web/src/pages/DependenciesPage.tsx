import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowRight,
  Database,
} from 'lucide-react';
import { useClaimRelationsQuery, useClaimsQuery } from '../api/queries';
import { useAuth } from '../context/auth';
import { Card } from '../components/common/Card';
import { Badge } from '../components/common/Badge';
import { Button } from '../components/common/Button';
import { EmptyState } from '../components/common/EmptyState';

export const DependenciesPage: React.FC = () => {
  const navigate = useNavigate();
  const { isConfigured } = useAuth();
  const { data: relations, isLoading: relLoading, isError: relError, error } = useClaimRelationsQuery();
  const { data: claims, isLoading: claimsLoading } = useClaimsQuery({ limit: 50 });

  const [selectedRelationId, setSelectedRelationId] = useState<string | null>(null);

  // Map claim IDs to claim objects for rich visualization
  const claimsMap = new Map((claims || []).map((c) => [c.id, c]));

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-12 animate-in fade-in duration-200">
      {/* Header Banner */}
      <div className="border-b border-stone-border pb-5 flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-xs font-mono text-copper uppercase tracking-wider mb-1.5 font-medium">
            <span className="w-2 h-2 rounded-full bg-copper inline-block animate-pulse" />
            <span>Neural Graph & Invalidation Cascades</span>
          </div>
          <h1 className="font-editorial text-3xl md:text-4xl text-charcoal font-normal">
            Memory Connections
          </h1>
          <p className="text-sm text-stone-muted mt-1 font-sans max-w-2xl leading-relaxed">
            Deterministic DAG relationships tracking supersession, prerequisites, and cascading invalidation across agent memories.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="secondary"
            onClick={() => navigate('/memory')}
            icon={<Database className="w-3.5 h-3.5 text-copper" />}
          >
            Explore Memories
          </Button>
        </div>
      </div>

      {!isConfigured ? (
        <Card title="Memory Relationship Graph">
          <EmptyState
            icon={Database}
            title="Authentication Required"
            description="Configure your Agent Bearer API key in the header to inspect active relationship edges."
          />
        </Card>
      ) : relLoading || claimsLoading ? (
        <div className="py-24 text-center text-xs font-mono text-stone-muted animate-pulse">
          Reconstructing neural memory DAG...
        </div>
      ) : relError ? (
        <div className="p-4 rounded-sm bg-terracotta/10 border border-terracotta/30 text-xs font-mono text-terracotta-dark">
          Failed to load memory relationships: {error?.message}
        </div>
      ) : relations && relations.length > 0 ? (
        <div className="space-y-6">
          {/* Interactive Neural Relationship Graph Canvas / SVG Viewport */}
          <div className="glass-panel p-6 rounded-md relative overflow-hidden">
            <div className="flex items-center justify-between mb-4 border-b border-stone-border/60 pb-3">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-copper" />
                <h3 className="font-editorial text-lg text-charcoal font-medium">
                  Neural Connection Topology
                </h3>
              </div>
              <span className="text-[11px] font-mono text-stone-muted">
                {relations.length} active edge{relations.length !== 1 ? 's' : ''}
              </span>
            </div>

            {/* Visual SVG Network Representation */}
            <div className="bg-bone-card/60 border border-stone-border/80 rounded-sm p-6 overflow-x-auto">
              <div className="min-w-[600px] flex flex-col gap-6">
                {relations.map((rel) => {
                  const source = claimsMap.get(rel.source_claim_id);
                  const target = claimsMap.get(rel.target_claim_id);
                  const isSelected = selectedRelationId === rel.id;

                  return (
                    <div
                      key={rel.id}
                      onClick={() => setSelectedRelationId(isSelected ? null : rel.id)}
                      className={`p-4 rounded-sm border transition-all cursor-pointer relative ${
                        isSelected
                          ? 'bg-bone-light border-copper shadow-sm ring-1 ring-copper/40'
                          : 'bg-bone border-stone-border/80 hover:border-copper/60 hover:bg-bone-light'
                      }`}
                    >
                      <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
                        {/* Source Memory Node */}
                        <div className="flex-1 p-3 rounded-sm bg-bone-light border border-stone-border">
                          <div className="flex items-center justify-between gap-2 mb-1">
                            <span className="text-[10px] font-mono text-stone-muted uppercase">Source Memory</span>
                            {source && <Badge status={source.status} />}
                          </div>
                          <div className="font-mono text-xs font-semibold text-charcoal truncate">
                            {source?.subject || rel.source_claim_id.slice(0, 12)}
                          </div>
                          <p className="text-[11px] font-sans text-stone-muted truncate mt-0.5">
                            {source?.raw_statement || 'Referenced assertion node'}
                          </p>
                        </div>

                        {/* Directed Neural Thread Edge */}
                        <div className="flex flex-col items-center justify-center px-4 py-1 flex-shrink-0">
                          <span className="text-[10px] font-mono font-medium text-copper uppercase px-2 py-0.5 rounded-full bg-copper/10 border border-copper/30 mb-1">
                            {rel.relation_type}
                          </span>
                          <div className="flex items-center gap-1 text-copper">
                            <span className="w-8 h-0.5 bg-copper" />
                            <ArrowRight className="w-3.5 h-3.5 -ml-1 text-copper" />
                          </div>
                        </div>

                        {/* Target Memory Node */}
                        <div className="flex-1 p-3 rounded-sm bg-bone-light border border-stone-border">
                          <div className="flex items-center justify-between gap-2 mb-1">
                            <span className="text-[10px] font-mono text-stone-muted uppercase">Target Memory</span>
                            {target && <Badge status={target.status} />}
                          </div>
                          <div className="font-mono text-xs font-semibold text-charcoal truncate">
                            {target?.subject || rel.target_claim_id.slice(0, 12)}
                          </div>
                          <p className="text-[11px] font-sans text-stone-muted truncate mt-0.5">
                            {target?.raw_statement || 'Dependent assertion node'}
                          </p>
                        </div>
                      </div>

                      {/* Rationale & Provenance Drawer if selected */}
                      {isSelected && (
                        <div className="mt-4 pt-3 border-t border-stone-border/70 text-xs space-y-2 animate-in fade-in duration-150">
                          <div className="font-sans text-charcoal bg-bone p-3 rounded-sm border border-stone-border/60">
                            <strong className="text-copper font-medium">Link Rationale:</strong> "{rel.rationale}"
                          </div>
                          <div className="flex items-center justify-between text-[11px] font-mono text-stone-muted pt-1">
                            <span>edge_id: {rel.id}</span>
                            <span>Created: {new Date(rel.created_at).toLocaleString()}</span>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Educational Governance Cascade Explainer */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <Card title="How Invalidation Cascades Work" subtitle="Guaranteed by Filament Backend Triggers">
              <p className="text-xs text-charcoal leading-relaxed font-sans">
                When an upstream memory assertion is superseded or its environment requirements drift, Filament's server triggers automatically traverse this dependency graph, flagging all downstream dependent memories as <span className="font-mono text-terracotta font-medium">needs_review</span>.
              </p>
            </Card>

            <Card title="Cryptographic Grounding" subtitle="Lineage Integrity">
              <p className="text-xs text-stone-muted leading-relaxed font-sans">
                Every edge in the memory DAG is immutable and append-only. Deleting or overwriting relationship history is strictly prohibited at the database boundary to preserve audit fidelity.
              </p>
            </Card>
          </div>
        </div>
      ) : (
        <Card title="Workspace Claim Relationships">
          <EmptyState
            icon={Database}
            title="No Memory Relationships Established"
            description="No supersession or prerequisite links currently exist between memories in this workspace. Create relationships in the Guided Demonstration."
            actionLabel="Open Interactive Guide"
            onAction={() => navigate('/guide')}
          />
        </Card>
      )}
    </div>
  );
};
