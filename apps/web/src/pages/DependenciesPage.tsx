import React from 'react';
import { GitFork } from 'lucide-react';
import { Card } from '../components/common/Card';
import { EmptyState } from '../components/common/EmptyState';

export const DependenciesPage: React.FC = () => {
  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-12 animate-in fade-in duration-200">
      <div className="border-b border-stone-border pb-5">
        <div className="flex items-center gap-2 text-xs font-mono text-copper uppercase tracking-wider mb-1.5 font-medium">
          <span className="w-2 h-2 rounded-full bg-copper inline-block" />
          <span>Lineage & Invalidation</span>
        </div>
        <h1 className="font-editorial text-3xl text-aubergine font-normal">
          Dependency Graph & Cascades
        </h1>
        <p className="text-sm text-stone-muted mt-1 font-sans max-w-2xl">
          Deterministic DAG visualization tracking supersession cascades and downstream invalidation paths.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="md:col-span-2">
          <Card title="Interactive Invalidation DAG">
            <EmptyState
              icon={GitFork}
              title="Graph Visualization Component"
              description="Dependency relations and cycle-checked supersessions are enforced server-side via POST /api/v1/claims/{id}/relations. The visual DAG rendering canvas will be connected once the graph traversal route is exposed."
              unconnectedNotice={true}
            />
          </Card>
        </div>

        <div className="space-y-4">
          <Card title="Cascade Invariant">
            <p className="text-xs text-stone-muted leading-relaxed font-sans">
              When an upstream claim is superseded, Filament cascades the transition to all transitive dependent claims, automatically marking them as <span className="font-mono text-terracotta font-medium">needs_review</span>.
            </p>
          </Card>
        </div>
      </div>
    </div>
  );
};
