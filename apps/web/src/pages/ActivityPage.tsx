import React from 'react';
import { Activity, Lock } from 'lucide-react';
import { Card } from '../components/common/Card';
import { EmptyState } from '../components/common/EmptyState';

export const ActivityPage: React.FC = () => {
  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-12 animate-in fade-in duration-200">
      <div className="border-b border-stone-border pb-5">
        <div className="flex items-center gap-2 text-xs font-mono text-copper uppercase tracking-wider mb-1.5 font-medium">
          <span className="w-2 h-2 rounded-full bg-copper inline-block" />
          <span>Governance Stream</span>
        </div>
        <h1 className="font-editorial text-3xl text-aubergine font-normal">
          Immutable Audit Trail
        </h1>
        <p className="text-sm text-stone-muted mt-1 font-sans max-w-2xl">
          Database-enforced append-only record of all claim establishments, condition changes, evidence links, and reverifications.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="md:col-span-2">
          <Card title="Activity Stream">
            <EmptyState
              icon={Activity}
              title="Audit Stream Endpoint Pending"
              description="Audit events are strictly recorded on every state mutation and protected by the trg_protect_audit_events database trigger. An activity query endpoint (GET /api/v1/audit) is scheduled for the next milestone."
              unconnectedNotice={true}
            />
          </Card>
        </div>

        <div>
          <Card title="Security Invariant">
            <div className="flex items-start gap-2 text-xs text-stone-muted leading-relaxed font-sans">
              <Lock className="w-4 h-4 text-copper flex-shrink-0 mt-0.5" />
              <span>
                Filament audit logs are tamper-evident. Database triggers prevent any UPDATE or DELETE operations from modifying historical audit records.
              </span>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
};
