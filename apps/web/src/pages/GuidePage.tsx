import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Compass,
  Database,
  ShieldCheck,
  GitFork,
  Bot,
  Activity,
  Layers,
  Sparkles,
  ArrowRight,
  CheckCircle2,
  RotateCcw,
  BookOpen,
  PlayCircle,
} from 'lucide-react';
import { Card } from '../components/common/Card';
import { Button } from '../components/common/Button';
import { useAuth } from '../context/auth';
import { api } from '../api/client';

export const GuidePage: React.FC = () => {
  const navigate = useNavigate();
  const { isConfigured } = useAuth();

  const [activeSection, setActiveSection] = useState<'intro' | 'tour' | 'interactive_demo' | 'glossary'>('intro');

  // Interactive Demo State
  const [demoStep, setDemoStep] = useState<number>(1);
  const [demoStatus, setDemoStatus] = useState<'idle' | 'running' | 'success' | 'error'>('idle');
  const [demoError, setDemoError] = useState<string>('');
  const [demoLogs, setDemoLogs] = useState<string[]>([]);

  // Demo Record IDs
  const [demoEvidenceHash, setDemoEvidenceHash] = useState<string>('');
  const [demoClaimId, setDemoClaimId] = useState<string>('');
  const [demoSnapshotAId, setDemoSnapshotAId] = useState<string>('');
  const [demoSnapshotCId, setDemoSnapshotCId] = useState<string>('');

  const addLog = (msg: string) => {
    setDemoLogs((prev) => [...prev, `[${new Date().toLocaleTimeString()}] ${msg}`]);
  };

  // Step 1: Create Memory
  const handleStep1CreateMemory = async () => {
    setDemoStatus('running');
    setDemoError('');
    try {
      const claim = await api.createClaim({
        claim_type: 'fact',
        subject: 'redis.connection_pool',
        predicate: 'max_connections_setting',
        object_value: { max_connections: 20, timeout_seconds: 5 },
        raw_statement: 'Setting Redis max_connections to 20 and timeout to 5s resolves connection dropouts in high load.',
        scope: 'team',
        confidence: 0.95,
      });
      setDemoClaimId(claim.id);
      addLog(`Created memory: "${claim.subject}" (ID: ${claim.id.slice(0, 8)}...)`);
      setDemoStatus('success');
      setDemoStep(2);
    } catch (err: any) {
      setDemoStatus('error');
      setDemoError(err.message || 'Failed to create memory. Ensure your API key is configured.');
    }
  };

  // Step 2: Record & Link Evidence
  const handleStep2AddEvidence = async () => {
    if (!demoClaimId) return;
    setDemoStatus('running');
    setDemoError('');
    try {
      const snippet = 'redis_pool = ConnectionPool(max_connections=20, timeout=5)\n# Benchmark: 0 timeouts under 500 req/s';
      const ev = await api.recordEvidence({
        source_type: 'file',
        source_uri: 'src/services/redis_client.py',
        raw_snippet: snippet,
      });
      setDemoEvidenceHash(ev.content_hash);
      addLog(`Recorded evidence artifact: ${ev.source_uri} (Hash: ${ev.content_hash.slice(0, 12)}...)`);

      await api.linkEvidence(demoClaimId, {
        evidence_id: ev.id,
        support_type: 'supports',
        confidence_weight: 1.0,
        extraction_notes: 'Empirical benchmark confirming 0 timeouts with pool size 20.',
      });
      addLog(`Linked supporting evidence to memory ${demoClaimId.slice(0, 8)}...`);

      setDemoStatus('success');
      setDemoStep(3);
    } catch (err: any) {
      setDemoStatus('error');
      setDemoError(err.message || 'Failed to record or link evidence.');
    }
  };

  // Step 3: Define Validity Requirements
  const handleStep3DefineRequirements = async () => {
    if (!demoClaimId || !demoEvidenceHash) return;
    setDemoStatus('running');
    setDemoError('');
    try {
      // 1. Take Baseline Snapshot A
      const snapA = await api.recordSnapshot({
        source_ref: 'git:main:baseline_config',
        scan_scope: 'full_repository',
        snapshot_data: {
          scanned_roots: ['.'],
          files: {
            'src/services/redis_client.py': demoEvidenceHash,
            'README.md': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
          },
          packages: {
            'pypi:redis': { version: '5.0.1' },
          },
        },
      });
      setDemoSnapshotAId(snapA.id);
      addLog(`Captured baseline Environment State A (ID: ${snapA.id.slice(0, 8)}...)`);

      // 2. Establish Requirements based on Snapshot A
      await api.establishConditions(demoClaimId, {
        based_on_snapshot_id: snapA.id,
        rationale: 'Valid only when Redis client matches the benchmarked pool configuration.',
        conditions: [
          {
            condition_type: 'file_hash',
            target_path: 'src/services/redis_client.py',
            comparator: 'hash_equals',
            expected_hash: demoEvidenceHash,
            is_critical: true,
          },
        ],
      });
      addLog('Established Validity Requirements v1 (bound to redis_client.py hash)');

      setDemoStatus('success');
      setDemoStep(4);
    } catch (err: any) {
      setDemoStatus('error');
      setDemoError(err.message || 'Failed to establish validity requirements.');
    }
  };

  // Step 4: Check Memory (Evaluation Baseline)
  const handleStep4CheckBaseline = async () => {
    if (!demoClaimId || !demoSnapshotAId) return;
    setDemoStatus('running');
    setDemoError('');
    try {
      const res = await api.evaluateClaim(demoClaimId, demoSnapshotAId);
      addLog(`Checked validity against Environment A: ${res.outcome.toUpperCase()} (Usable: ${res.is_applicable})`);
      setDemoStatus('success');
      setDemoStep(5);
    } catch (err: any) {
      setDemoStatus('error');
      setDemoError(err.message || 'Evaluation failed.');
    }
  };

  // Step 5: Test Environmental Changes (Unrelated vs Relevant)
  const handleStep5SimulateChanges = async () => {
    if (!demoClaimId || !demoEvidenceHash) return;
    setDemoStatus('running');
    setDemoError('');
    try {
      // 1. Unrelated Change Snapshot B (Only README modified)
      const snapB = await api.recordSnapshot({
        source_ref: 'git:main:readme_typo_fix',
        snapshot_data: {
          scanned_roots: ['.'],
          files: {
            'src/services/redis_client.py': demoEvidenceHash, // UNCHANGED
            'README.md': '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef', // CHANGED
          },
        },
      });

      const evalB = await api.evaluateClaim(demoClaimId, snapB.id);
      addLog(`Checked after README update: ${evalB.outcome.toUpperCase()} (Still valid! Unrelated files do not break memories)`);

      // 2. Relevant Change Snapshot C (redis_client.py drifted)
      const driftedHash = 'ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff';
      const snapC = await api.recordSnapshot({
        source_ref: 'git:main:refactor_redis_pool',
        snapshot_data: {
          scanned_roots: ['.'],
          files: {
            'src/services/redis_client.py': driftedHash, // DRIFTED
          },
        },
      });
      setDemoSnapshotCId(snapC.id);

      const evalC = await api.evaluateClaim(demoClaimId, snapC.id);
      addLog(`Checked after redis_client.py changed: ${evalC.outcome.toUpperCase()} (Warning! Environment no longer matches)`);

      setDemoStatus('success');
      setDemoStep(6);
    } catch (err: any) {
      setDemoStatus('error');
      setDemoError(err.message || 'Drift simulation failed.');
    }
  };

  // Step 6: Review & Update
  const handleStep6Reverify = async () => {
    if (!demoClaimId || !demoSnapshotCId) return;
    setDemoStatus('running');
    setDemoError('');
    try {
      const driftedHash = 'ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff';
      const reverifyRes = await api.reverifyClaim(demoClaimId, {
        snapshot_id: demoSnapshotCId,
        action: 'adopt_new_conditions',
        expected_condition_version: 1,
        attestation_notes: 'Reviewed the refactored Redis pool; verified it retains 20 max connections safely.',
        adopt_rationale: 'Updated validity requirement to match the new redis_client.py hash.',
        proposed_conditions: [
          {
            condition_type: 'file_hash',
            target_path: 'src/services/redis_client.py',
            comparator: 'hash_equals',
            expected_hash: driftedHash,
            is_critical: true,
          },
        ],
      });

      addLog(`Adopted updated requirements: Validity Requirements upgraded to v${reverifyRes.active_condition_version}`);
      addLog('Complete audit history and verification records stored immutably in Supabase.');
      setDemoStatus('success');
      setDemoStep(7);
    } catch (err: any) {
      setDemoStatus('error');
      setDemoError(err.message || 'Re-verification failed.');
    }
  };

  const handleResetDemo = () => {
    setDemoStep(1);
    setDemoStatus('idle');
    setDemoError('');
    setDemoLogs([]);
    setDemoEvidenceHash('');
    setDemoClaimId('');
    setDemoSnapshotAId('');
    setDemoSnapshotCId('');
  };

  return (
    <div className="space-y-8 max-w-7xl mx-auto pb-16 animate-in fade-in duration-200">
      {/* Guide Header Banner */}
      <div className="border-b border-stone-border pb-6 flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-xs font-mono text-copper uppercase tracking-wider mb-1.5 font-medium">
            <BookOpen className="w-4 h-4 text-copper" />
            <span>Product Guide & Interactive Demonstration</span>
          </div>
          <h1 className="font-editorial text-3xl md:text-4xl text-aubergine font-normal">
            Understanding Filament
          </h1>
          <p className="text-sm text-stone-muted mt-1 font-sans max-w-3xl leading-relaxed">
            Filament ensures AI systems do not blindly trust outdated memories. By connecting memories to supporting evidence and environment requirements, Filament alerts you when real-world conditions change.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button
            size="sm"
            onClick={() => setActiveSection('interactive_demo')}
            icon={<PlayCircle className="w-3.5 h-3.5" />}
          >
            Start Interactive Demo
          </Button>
        </div>
      </div>

      {/* Guide Navigation Tabs */}
      <div className="flex items-center gap-2 border-b border-stone-border text-xs font-mono">
        <button
          onClick={() => setActiveSection('intro')}
          className={`py-2.5 px-4 font-medium transition-colors cursor-pointer border-b-2 ${
            activeSection === 'intro'
              ? 'border-copper text-copper font-semibold'
              : 'border-transparent text-stone-muted hover:text-aubergine'
          }`}
        >
          1. What is Filament?
        </button>
        <button
          onClick={() => setActiveSection('tour')}
          className={`py-2.5 px-4 font-medium transition-colors cursor-pointer border-b-2 ${
            activeSection === 'tour'
              ? 'border-copper text-copper font-semibold'
              : 'border-transparent text-stone-muted hover:text-aubergine'
          }`}
        >
          2. Workstation Tour
        </button>
        <button
          onClick={() => setActiveSection('interactive_demo')}
          className={`py-2.5 px-4 font-medium transition-colors cursor-pointer border-b-2 ${
            activeSection === 'interactive_demo'
              ? 'border-copper text-copper font-semibold'
              : 'border-transparent text-stone-muted hover:text-aubergine'
          }`}
        >
          3. Guided Demonstration
        </button>
        <button
          onClick={() => setActiveSection('glossary')}
          className={`py-2.5 px-4 font-medium transition-colors cursor-pointer border-b-2 ${
            activeSection === 'glossary'
              ? 'border-copper text-copper font-semibold'
              : 'border-transparent text-stone-muted hover:text-aubergine'
          }`}
        >
          4. Concept Glossary
        </button>
      </div>

      {/* SECTION 1: What is Filament? */}
      {activeSection === 'intro' && (
        <div className="space-y-6 animate-in fade-in duration-150">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <Card title="The Problem: Stale AI Knowledge" subtitle="Why traditional memory systems fail">
              <div className="space-y-3 text-xs text-aubergine-light font-sans leading-relaxed">
                <p>
                  Most AI memory solutions simply store text snippets or vector embeddings into a database. When an AI recalls a memory weeks later, it has no way of knowing whether the underlying codebase, dependencies, or configuration have changed.
                </p>
                <div className="p-3 bg-terracotta/10 rounded-sm border border-terracotta/30 text-terracotta-dark font-mono text-[11px]">
                  ⚠️ <strong>Real-World Risk:</strong> An AI remembers: <em>"Use psycopg2 for PostgreSQL connections."</em> Later, your team upgrades the codebase to async SQLAlchemy with <code>asyncpg</code>. An autonomous agent blindly follows the old memory, installs obsolete packages, and breaks your project.
                </div>
              </div>
            </Card>

            <Card title="The Solution: Condition-Bound Validity" subtitle="Memories that know when they're valid">
              <div className="space-y-3 text-xs text-aubergine-light font-sans leading-relaxed">
                <p>
                  Filament introduces <strong>condition-bound memory governance</strong>. Instead of assuming memories are permanently valid, every memory records:
                </p>
                <ul className="space-y-1.5 list-disc pl-4 text-aubergine">
                  <li><strong>The Fact or Decision:</strong> What was learned.</li>
                  <li><strong>Supporting Evidence:</strong> The code excerpt, benchmark, or log that proved it.</li>
                  <li><strong>Validity Requirements:</strong> The exact file digests or library versions in place when established.</li>
                </ul>
                <div className="p-3 bg-sage/15 rounded-sm border border-sage/40 text-sage-dark font-mono text-[11px]">
                  ✓ <strong>Filament Invariant:</strong> When your environment changes, Filament immediately flags dependent memories for review before an agent can misuse them.
                </div>
              </div>
            </Card>
          </div>

          {/* Visual 3-Pillar Architecture Diagram */}
          <Card title="The Filament Governance Triad">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-2">
              <div className="p-4 rounded-sm bg-parchment border border-stone-border space-y-2">
                <div className="flex items-center gap-2 text-copper font-mono text-xs font-semibold">
                  <Database className="w-4 h-4" />
                  <span>1. Memory Assertion</span>
                </div>
                <p className="text-xs text-stone-muted font-sans leading-relaxed">
                  The factual claim or decision. Immutable and versioned. Never silently modified.
                </p>
              </div>

              <div className="p-4 rounded-sm bg-parchment border border-stone-border space-y-2">
                <div className="flex items-center gap-2 text-copper font-mono text-xs font-semibold">
                  <ShieldCheck className="w-4 h-4" />
                  <span>2. Supporting Evidence</span>
                </div>
                <p className="text-xs text-stone-muted font-sans leading-relaxed">
                  Cryptographically hashed source artifacts (file excerpts, commit SHAs, or test outputs) proving why the memory exists.
                </p>
              </div>

              <div className="p-4 rounded-sm bg-parchment border border-stone-border space-y-2">
                <div className="flex items-center gap-2 text-copper font-mono text-xs font-semibold">
                  <Sparkles className="w-4 h-4" />
                  <span>3. Validity Requirements</span>
                </div>
                <p className="text-xs text-stone-muted font-sans leading-relaxed">
                  Preconditions that specify the exact file hashes or packages required for the memory to remain safe to use.
                </p>
              </div>
            </div>
          </Card>
        </div>
      )}

      {/* SECTION 2: Workstation Tour */}
      {activeSection === 'tour' && (
        <div className="space-y-4 animate-in fade-in duration-150">
          <p className="text-sm text-stone-muted font-sans">
            Here is a tour of the pages in the Filament Workstation and when to use them:
          </p>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card title="Overview" subtitle="Project / Workspace Health">
              <div className="flex items-start gap-3">
                <Compass className="w-5 h-5 text-copper flex-shrink-0 mt-0.5" />
                <div className="text-xs text-aubergine-light font-sans space-y-1">
                  <p><strong>What it does:</strong> High-level command center showing your active project identity, total memories, and attention queue.</p>
                  <p><strong>When to use:</strong> Start here to quickly see whether any memories have drifted and require your review.</p>
                </div>
              </div>
            </Card>

            <Card title="Memories" subtitle="Browse, Create & Check Memories">
              <div className="flex items-start gap-3">
                <Database className="w-5 h-5 text-copper flex-shrink-0 mt-0.5" />
                <div className="text-xs text-aubergine-light font-sans space-y-1">
                  <p><strong>What it does:</strong> Browse all established memories with live search and status filters (Current, Needs Review, Disputed, Superseded).</p>
                  <p><strong>When to use:</strong> Open memories to inspect their supporting evidence, run validity checks, or establish requirements.</p>
                </div>
              </div>
            </Card>

            <Card title="Supporting Evidence" subtitle="Immutable Source Artifacts">
              <div className="flex items-start gap-3">
                <ShieldCheck className="w-5 h-5 text-copper flex-shrink-0 mt-0.5" />
                <div className="text-xs text-aubergine-light font-sans space-y-1">
                  <p><strong>What it does:</strong> Cryptographic catalog of source snippets, git commits, and tool outputs with SHA-256 integrity digests.</p>
                  <p><strong>When to use:</strong> Ingest new evidence or inspect the source artifact behind any memory assertion.</p>
                </div>
              </div>
            </Card>

            <Card title="Memory Connections" subtitle="Dependencies & Supersessions">
              <div className="flex items-start gap-3">
                <GitFork className="w-5 h-5 text-copper flex-shrink-0 mt-0.5" />
                <div className="text-xs text-aubergine-light font-sans space-y-1">
                  <p><strong>What it does:</strong> Visualizes directed relationships between memories (such as <em>depends on</em> or <em>supersedes</em>).</p>
                  <p><strong>When to use:</strong> Understand how changes to an upstream memory automatically cascade to mark downstream memories as <em>needs review</em>.</p>
                </div>
              </div>
            </Card>

            <Card title="Connected AI Agents" subtitle="Agent Identities & Default Scopes">
              <div className="flex items-start gap-3">
                <Bot className="w-5 h-5 text-copper flex-shrink-0 mt-0.5" />
                <div className="text-xs text-aubergine-light font-sans space-y-1">
                  <p><strong>What it does:</strong> Lists autonomous AI agents authorized in this project, their hashed credentials, and default scopes.</p>
                  <p><strong>When to use:</strong> Audit agent actors and their access permissions.</p>
                </div>
              </div>
            </Card>

            <Card title="Activity History" subtitle="Append-Only Governance History">
              <div className="flex items-start gap-3">
                <Activity className="w-5 h-5 text-copper flex-shrink-0 mt-0.5" />
                <div className="text-xs text-aubergine-light font-sans space-y-1">
                  <p><strong>What it does:</strong> Tamper-evident audit stream protected by database triggers. Records every memory creation, evidence link, and recheck.</p>
                  <p><strong>When to use:</strong> Review who created or updated a memory and inspect complete chronological change logs.</p>
                </div>
              </div>
            </Card>

            <Card title="Integrations" subtitle="Environment Ingestion Adapters">
              <div className="flex items-start gap-3">
                <Layers className="w-5 h-5 text-copper flex-shrink-0 mt-0.5" />
                <div className="text-xs text-aubergine-light font-sans space-y-1">
                  <p><strong>What it does:</strong> Overview of automated environment state ingestion adapters (CLI, CI/CD, and MCP).</p>
                  <p><strong>When to use:</strong> Learn how to pipe automated codebase scans into Filament during pull requests or builds.</p>
                </div>
              </div>
            </Card>
          </div>
        </div>
      )}

      {/* SECTION 3: Guided Product Demonstration */}
      {activeSection === 'interactive_demo' && (
        <div className="space-y-6 animate-in fade-in duration-150">
          {/* Demo Introduction & Safeguards */}
          <div className="p-4 rounded-sm bg-parchment border border-stone-border flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
            <div>
              <h3 className="font-editorial text-lg text-aubergine font-medium">Interactive Walkthrough</h3>
              <p className="text-xs text-stone-muted font-sans mt-0.5">
                Execute the complete real-world memory workflow live against your backend and database in 6 clear steps.
              </p>
            </div>

            <div className="flex items-center gap-2">
              <Button
                variant="secondary"
                size="sm"
                onClick={handleResetDemo}
                icon={<RotateCcw className="w-3.5 h-3.5" />}
              >
                Reset Demo
              </Button>
            </div>
          </div>

          {!isConfigured && (
            <div className="p-4 rounded-sm bg-citron-tint border border-citron-border text-xs text-aubergine font-sans">
              ⚠️ <strong>Authentication Required:</strong> Please configure your Agent Bearer API key in the top navigation bar before running the live demo.
            </div>
          )}

          {/* Stepper Progress Bar */}
          <div className="grid grid-cols-2 md:grid-cols-6 gap-2 text-xs font-mono">
            {[
              { num: 1, label: 'Create Memory' },
              { num: 2, label: 'Add Evidence' },
              { num: 3, label: 'Define Validity' },
              { num: 4, label: 'Check Memory' },
              { num: 5, label: 'Change Environment' },
              { num: 6, label: 'Review & Update' },
            ].map((s) => (
              <div
                key={s.num}
                className={`p-2.5 rounded-sm border text-center transition-all ${
                  demoStep === s.num
                    ? 'bg-copper text-parchment-light border-copper font-medium shadow-xs'
                    : demoStep > s.num
                    ? 'bg-sage/15 text-sage-dark border-sage/40'
                    : 'bg-parchment text-stone-muted border-stone-border'
                }`}
              >
                <div className="text-[10px] uppercase tracking-wider">Step {s.num}</div>
                <div className="text-xs truncate font-sans font-medium">{s.label}</div>
              </div>
            ))}
          </div>

          {/* Active Step Card */}
          <Card className="border-copper/40 bg-parchment-light">
            {demoStep === 1 && (
              <div className="space-y-4">
                <div className="border-b border-stone-border pb-3">
                  <span className="text-[11px] font-mono text-copper uppercase tracking-wider font-semibold">Step 1 of 6</span>
                  <h3 className="font-editorial text-xl text-aubergine font-normal mt-0.5">
                    Create an Architectural Memory
                  </h3>
                  <p className="text-xs text-stone-muted font-sans mt-1">
                    An autonomous agent discovers an important technical fact: <em>"Setting Redis max_connections to 20 and timeout to 5s resolves connection dropouts under load."</em>
                  </p>
                </div>

                <div className="p-3 bg-parchment rounded-sm border border-stone-border text-xs font-mono space-y-1">
                  <div><strong>Subject:</strong> redis.connection_pool</div>
                  <div><strong>Predicate:</strong> max_connections_setting</div>
                  <div><strong>Statement:</strong> "Setting Redis max_connections to 20 and timeout to 5s resolves connection dropouts in high load."</div>
                  <div><strong>Scope:</strong> team</div>
                </div>

                <div className="flex items-center justify-between pt-2">
                  <span className="text-xs text-stone-muted font-sans">
                    Action will create a real, versioned memory record in your project.
                  </span>
                  <Button
                    onClick={handleStep1CreateMemory}
                    disabled={demoStatus === 'running' || !isConfigured}
                    icon={<ArrowRight className="w-3.5 h-3.5" />}
                  >
                    {demoStatus === 'running' ? 'Creating...' : 'Create Memory'}
                  </Button>
                </div>
              </div>
            )}

            {demoStep === 2 && (
              <div className="space-y-4">
                <div className="border-b border-stone-border pb-3">
                  <span className="text-[11px] font-mono text-copper uppercase tracking-wider font-semibold">Step 2 of 6</span>
                  <h3 className="font-editorial text-xl text-aubergine font-normal mt-0.5">
                    Attach Supporting Evidence
                  </h3>
                  <p className="text-xs text-stone-muted font-sans mt-1">
                    Memories without evidence cannot be verified. We now attach the code snippet and benchmark observation that justified this decision.
                  </p>
                </div>

                <div className="p-3 bg-aubergine-deep text-parchment-light rounded-sm font-mono text-xs border border-aubergine-border">
                  <pre className="whitespace-pre-wrap">
                    {"redis_pool = ConnectionPool(max_connections=20, timeout=5)\n# Benchmark: 0 timeouts under 500 req/s"}
                  </pre>
                </div>

                <div className="flex items-center justify-between pt-2">
                  <span className="text-xs text-stone-muted font-sans">
                    Stores the snippet, computes its cryptographic SHA-256 digest, and links it to the memory.
                  </span>
                  <Button
                    onClick={handleStep2AddEvidence}
                    disabled={demoStatus === 'running'}
                    icon={<ArrowRight className="w-3.5 h-3.5" />}
                  >
                    {demoStatus === 'running' ? 'Attaching...' : 'Attach Supporting Evidence'}
                  </Button>
                </div>
              </div>
            )}

            {demoStep === 3 && (
              <div className="space-y-4">
                <div className="border-b border-stone-border pb-3">
                  <span className="text-[11px] font-mono text-copper uppercase tracking-wider font-semibold">Step 3 of 6</span>
                  <h3 className="font-editorial text-xl text-aubergine font-normal mt-0.5">
                    Define When the Memory is Valid (Validity Requirements)
                  </h3>
                  <p className="text-xs text-stone-muted font-sans mt-1">
                    This is Filament's distinguishing feature. We capture a baseline snapshot of the repository and declare that this memory is valid <strong>only while <code>src/services/redis_client.py</code> has this exact content hash</strong>.
                  </p>
                </div>

                <div className="p-3 bg-parchment rounded-sm border border-stone-border text-xs font-mono space-y-1">
                  <div><strong>Baseline Environment:</strong> Snapshot A (git:main:baseline_config)</div>
                  <div><strong>Critical Condition:</strong> <code>src/services/redis_client.py</code> == <span className="text-copper">{demoEvidenceHash.slice(0, 16)}...</span></div>
                </div>

                <div className="flex items-center justify-between pt-2">
                  <span className="text-xs text-stone-muted font-sans">
                    Binds the memory to exact environmental invariants.
                  </span>
                  <Button
                    onClick={handleStep3DefineRequirements}
                    disabled={demoStatus === 'running'}
                    icon={<ArrowRight className="w-3.5 h-3.5" />}
                  >
                    {demoStatus === 'running' ? 'Establishing...' : 'Define Validity Requirements'}
                  </Button>
                </div>
              </div>
            )}

            {demoStep === 4 && (
              <div className="space-y-4">
                <div className="border-b border-stone-border pb-3">
                  <span className="text-[11px] font-mono text-copper uppercase tracking-wider font-semibold">Step 4 of 6</span>
                  <h3 className="font-editorial text-xl text-aubergine font-normal mt-0.5">
                    Check Memory Validity
                  </h3>
                  <p className="text-xs text-stone-muted font-sans mt-1">
                    An AI agent is about to use this memory. It first runs a validity check against the current environment state.
                  </p>
                </div>

                <div className="p-4 bg-parchment rounded-sm border border-stone-border text-xs font-sans space-y-2">
                  <p>
                    Testing whether <strong>Environment A</strong> satisfies all critical conditions for this memory.
                  </p>
                </div>

                <div className="flex items-center justify-between pt-2">
                  <span className="text-xs text-stone-muted font-sans">
                    Evaluates requirements deterministically without modifying database state.
                  </span>
                  <Button
                    onClick={handleStep4CheckBaseline}
                    disabled={demoStatus === 'running'}
                    icon={<ArrowRight className="w-3.5 h-3.5" />}
                  >
                    {demoStatus === 'running' ? 'Checking...' : 'Check Memory Now'}
                  </Button>
                </div>
              </div>
            )}

            {demoStep === 5 && (
              <div className="space-y-4">
                <div className="border-b border-stone-border pb-3">
                  <span className="text-[11px] font-mono text-copper uppercase tracking-wider font-semibold">Step 5 of 6</span>
                  <h3 className="font-editorial text-xl text-aubergine font-normal mt-0.5">
                    Simulate Environmental Drift
                  </h3>
                  <p className="text-xs text-stone-muted font-sans mt-1">
                    Watch how Filament handles two kinds of codebase changes:
                  </p>
                  <ol className="list-decimal pl-4 text-xs text-aubergine mt-2 space-y-1">
                    <li><strong>Unrelated Change (README.md):</strong> The memory remains valid because the documentation change does not touch the required Redis client.</li>
                    <li><strong>Relevant Change (redis_client.py):</strong> The file is modified. Filament immediately flags the memory as <span className="font-mono text-terracotta font-semibold">DRIFTED / ENVIRONMENT MISMATCH</span>.</li>
                  </ol>
                </div>

                <div className="flex items-center justify-between pt-2">
                  <span className="text-xs text-stone-muted font-sans">
                    Simulates both changes and evaluates validity in real time.
                  </span>
                  <Button
                    onClick={handleStep5SimulateChanges}
                    disabled={demoStatus === 'running'}
                    icon={<ArrowRight className="w-3.5 h-3.5" />}
                  >
                    {demoStatus === 'running' ? 'Simulating...' : 'Simulate Codebase Changes'}
                  </Button>
                </div>
              </div>
            )}

            {demoStep === 6 && (
              <div className="space-y-4">
                <div className="border-b border-stone-border pb-3">
                  <span className="text-[11px] font-mono text-copper uppercase tracking-wider font-semibold">Step 6 of 6</span>
                  <h3 className="font-editorial text-xl text-aubergine font-normal mt-0.5">
                    Review & Update Validity Requirements
                  </h3>
                  <p className="text-xs text-stone-muted font-sans mt-1">
                    A drifted memory is not automatically false—it just means the world changed. A human or agent reviews the new code, confirms the finding still holds, and <strong>explicitly adopts new validity requirements</strong> (upgrading to Requirements v2).
                  </p>
                </div>

                <div className="p-3 bg-parchment rounded-sm border border-stone-border text-xs font-mono space-y-1">
                  <div><strong>Action:</strong> Adopt New Requirements (upgrade condition set)</div>
                  <div><strong>Attestation Note:</strong> "Reviewed the refactored Redis pool; verified it retains 20 max connections safely."</div>
                  <div><strong>New Requirement:</strong> Updates expected file digest to match the new code.</div>
                </div>

                <div className="flex items-center justify-between pt-2">
                  <span className="text-xs text-stone-muted font-sans">
                    Records the attestation and creates an immutable audit trail entry.
                  </span>
                  <Button
                    onClick={handleStep6Reverify}
                    disabled={demoStatus === 'running'}
                    icon={<CheckCircle2 className="w-3.5 h-3.5" />}
                  >
                    {demoStatus === 'running' ? 'Updating...' : 'Adopt New Requirements'}
                  </Button>
                </div>
              </div>
            )}

            {demoStep === 7 && (
              <div className="space-y-4 py-2">
                <div className="flex items-center gap-2 text-sage font-mono text-sm font-semibold">
                  <CheckCircle2 className="w-5 h-5 text-sage" />
                  <span>Demonstration Complete!</span>
                </div>
                <h3 className="font-editorial text-2xl text-aubergine font-normal">
                  You Have Verified Condition-Bound Governance
                </h3>
                <p className="text-xs text-aubergine-light font-sans leading-relaxed">
                  You just witnessed the core superpower of Filament: memories that stay grounded in cryptographic evidence and automatically sound the alarm when your codebase changes.
                </p>

                <div className="flex items-center gap-3 pt-2">
                  <Button
                    size="sm"
                    onClick={() => navigate('/memory')}
                    icon={<Database className="w-3.5 h-3.5" />}
                  >
                    View in Memory Browser
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => navigate('/activity')}
                    icon={<Activity className="w-3.5 h-3.5" />}
                  >
                    Inspect Activity History
                  </Button>
                </div>
              </div>
            )}

            {demoError && (
              <div className="mt-4 p-3 rounded-sm bg-terracotta/10 border border-terracotta/30 text-xs font-mono text-terracotta-dark">
                {demoError}
              </div>
            )}
          </Card>

          {/* Live Demonstration Execution Log */}
          {demoLogs.length > 0 && (
            <Card title="Live Demonstration Activity Log">
              <div className="p-3 bg-aubergine-deep text-parchment-light rounded-sm font-mono text-xs space-y-1 max-h-48 overflow-y-auto border border-aubergine-border">
                {demoLogs.map((log, idx) => (
                  <div key={idx} className="leading-snug">{log}</div>
                ))}
              </div>
            </Card>
          )}
        </div>
      )}

      {/* SECTION 4: Concept Glossary */}
      {activeSection === 'glossary' && (
        <div className="space-y-4 animate-in fade-in duration-150">
          <p className="text-sm text-stone-muted font-sans">
            Plain-language explanations of essential Filament concepts:
          </p>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card title="Memory (formerly Claim)">
              <p className="text-xs text-aubergine-light font-sans leading-relaxed">
                An assertion, decision, or fact recorded by an AI agent or human. Memories are immutable and versioned.
                <br /><span className="text-stone-muted font-mono text-[11px] block mt-1">Example: "Use port 5433 for local testing."</span>
              </p>
            </Card>

            <Card title="Supporting Evidence">
              <p className="text-xs text-aubergine-light font-sans leading-relaxed">
                The verifiable proof that backs up a memory, such as a snippet from a configuration file, a git commit SHA, or a test log.
                <br /><span className="text-stone-muted font-mono text-[11px] block mt-1">Example: An excerpt from docker-compose.yml showing port 5433 mapped.</span>
              </p>
            </Card>

            <Card title="Validity Requirements (formerly Condition Set)">
              <p className="text-xs text-aubergine-light font-sans leading-relaxed">
                The specific environment rules that must remain true for this memory to be trusted.
                <br /><span className="text-stone-muted font-mono text-[11px] block mt-1">Example: The SHA-256 hash of docker-compose.yml must match its baseline.</span>
              </p>
            </Card>

            <Card title="Environment State (formerly Snapshot)">
              <p className="text-xs text-aubergine-light font-sans leading-relaxed">
                A point-in-time inventory of your codebase, including file hashes and installed library versions.
                <br /><span className="text-stone-muted font-mono text-[11px] block mt-1">Example: An automated scan captured on git commit 3002742.</span>
              </p>
            </Card>

            <Card title="Drift">
              <p className="text-xs text-aubergine-light font-sans leading-relaxed">
                When a relevant file or dependency in your codebase changes, causing a memory's validity requirements to fail.
                <br /><span className="text-stone-muted font-mono text-[11px] block mt-1">Filament flags drifted memories so agents do not make decisions on stale assumptions.</span>
              </p>
            </Card>

            <Card title="Recheck & Update (formerly Reverification)">
              <p className="text-xs text-aubergine-light font-sans leading-relaxed">
                The explicit act of confirming whether a drifted memory still holds, or adopting new requirements to match the updated environment.
              </p>
            </Card>

            <Card title="Memory Connections">
              <p className="text-xs text-aubergine-light font-sans leading-relaxed">
                Directed relationships between memories (such as <em>depends on</em> or <em>supersedes</em>). When an upstream memory is replaced, downstream memories are automatically flagged for review.
              </p>
            </Card>

            <Card title="Connected AI Agent">
              <p className="text-xs text-aubergine-light font-sans leading-relaxed">
                An autonomous agent or model authorized to record memories, attach evidence, and run validity checks using a secure API key.
              </p>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
};
