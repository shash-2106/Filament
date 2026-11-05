import React, { useState } from 'react';
import {
  Compass,
  ArrowRight,
  Key,
  ShieldCheck,
  Cpu,
  Layers,
} from 'lucide-react';
import { FilamentNetwork } from '../components/brand/FilamentNetwork';
import { FilamentLogo } from '../components/brand/FilamentLogo';
import { Button } from '../components/common/Button';
import { useAuth } from '../context/auth';
import { useNavigate } from 'react-router-dom';

export const WelcomePage: React.FC = () => {
  const navigate = useNavigate();
  const { apiKey, setApiKey, isConfigured } = useAuth();
  const [demoKeyInput, setDemoKeyInput] = useState(
    apiKey || 'fil_demo_key_12345'
  );

  const handleEnterWorkstation = (e: React.FormEvent) => {
    e.preventDefault();
    if (demoKeyInput.trim()) {
      setApiKey(demoKeyInput.trim());
    }
    navigate('/overview');
  };

  return (
    <div className="min-h-screen bg-[#0B1210] text-graphite-text flex flex-col relative overflow-hidden select-none">
      {/* Top Floating Glass Navigation Header */}
      <header className="fixed top-0 left-0 right-0 z-50 px-6 py-4">
        <div className="max-w-7xl mx-auto bg-[#14231D]/80 backdrop-blur-md border border-[#294537] px-5 py-3 rounded flex items-center justify-between shadow-lg">
          <div className="flex items-center gap-3">
            <FilamentLogo size="md" showWordmark={true} animated={true} />
            <span className="hidden md:inline-block text-[11px] font-mono text-graphite-text-tertiary border-l border-[#294537] pl-3">
              Developer Intelligence Workstation
            </span>
          </div>

          <div className="flex items-center gap-3">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => navigate('/guide')}
              icon={<Compass className="w-3.5 h-3.5 text-phosphor" />}
            >
              Interactive Guide
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={() => navigate('/overview')}
              icon={<ArrowRight className="w-3.5 h-3.5" />}
            >
              {isConfigured ? 'Open Workstation' : 'Launch Demo'}
            </Button>
          </div>
        </div>
      </header>

      {/* Hero Section */}
      <section className="relative pt-28 pb-16 md:pt-36 md:pb-24 px-6 flex-1 flex flex-col justify-center">
        <div className="relative z-10 max-w-6xl mx-auto w-full space-y-8">
          <div className="text-center space-y-4 max-w-3xl mx-auto">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[#14231D] border border-[#294537] text-xs font-mono text-phosphor shadow-xs">
              <span className="w-2 h-2 rounded-full bg-phosphor animate-pulse" />
              <span>Evidence-Backed • Condition-Aware AI Memory</span>
            </div>

            <h1 className="font-heading text-4xl sm:text-5xl md:text-6xl text-graphite-text font-bold tracking-tight leading-[1.1]">
              Memory is only useful while its{' '}
              <span className="text-phosphor font-normal">assumptions hold.</span>
            </h1>

            <p className="font-sans text-base sm:text-lg text-graphite-text-secondary max-w-2xl mx-auto leading-relaxed">
              Filament gives AI agents evidence-backed, condition-aware memory. Track where knowledge
              came from, what it depends on, and when it needs to be rechecked.
            </p>
          </div>

          {/* Interactive Neural Network Visual Centerpiece */}
          <div className="w-full max-w-5xl mx-auto shadow-2xl rounded-lg overflow-hidden border border-[#294537]">
            <FilamentNetwork className="h-[360px] md:h-[420px]" interactive={true} />
          </div>

          {/* Quick Connect & Entry Form */}
          <div className="pt-2 max-w-md mx-auto">
            <form
              onSubmit={handleEnterWorkstation}
              className="bg-[#14231D] border border-[#294537] p-5 rounded space-y-3.5 text-left shadow-xl"
            >
              <div className="flex items-center justify-between">
                <label className="text-xs font-mono font-medium text-graphite-text flex items-center gap-1.5">
                  <Key className="w-3.5 h-3.5 text-phosphor" />
                  <span>Agent Bearer Key</span>
                </label>
                <span className="text-[10px] font-mono text-phosphor-secondary bg-[#1C3027] px-2 py-0.5 rounded border border-[#294537]">
                  Demo Preset
                </span>
              </div>

              <input
                type="text"
                value={demoKeyInput}
                onChange={(e) => setDemoKeyInput(e.target.value)}
                placeholder="fil_live_..."
                className="w-full bg-[#0B1210] border border-[#294537] rounded px-3 py-2 text-xs font-mono text-graphite-text placeholder:text-graphite-text-tertiary focus:outline-none focus:border-phosphor focus:ring-1 focus:ring-phosphor/30 transition-all"
              />

              <Button
                type="submit"
                variant="primary"
                size="md"
                className="w-full justify-center"
                icon={<ArrowRight className="w-4 h-4" />}
              >
                Launch Governed Workstation
              </Button>
            </form>
          </div>

          {/* Core Architectural Pillars */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-6 max-w-5xl mx-auto">
            <div className="p-4 rounded bg-[#14231D] border border-[#294537] space-y-2">
              <div className="flex items-center gap-2 text-xs font-mono text-phosphor font-medium uppercase tracking-wider">
                <ShieldCheck className="w-4 h-4" />
                <span>01 — Cryptographic Provenance</span>
              </div>
              <p className="text-xs text-graphite-text-secondary leading-relaxed font-sans">
                Every memory points directly to immutable conversation excerpts or tool outputs. Untraceable assertions are rejected.
              </p>
            </div>

            <div className="p-4 rounded bg-[#14231D] border border-[#294537] space-y-2">
              <div className="flex items-center gap-2 text-xs font-mono text-phosphor font-medium uppercase tracking-wider">
                <Cpu className="w-4 h-4" />
                <span>02 — Environmental Validity</span>
              </div>
              <p className="text-xs text-graphite-text-secondary leading-relaxed font-sans">
                Memories link to required environment states (e.g. Postgres versions, ports, flags). If the environment drifts, the memory flags for review.
              </p>
            </div>

            <div className="p-4 rounded bg-[#14231D] border border-[#294537] space-y-2">
              <div className="flex items-center gap-2 text-xs font-mono text-phosphor font-medium uppercase tracking-wider">
                <Layers className="w-4 h-4" />
                <span>03 — Budget-Governed Inference</span>
              </div>
              <p className="text-xs text-graphite-text-secondary leading-relaxed font-sans">
                Meta Muse Spark extraction runs under atomic global database ledgers. Spend is pre-estimated, capped, and transparently auditable.
              </p>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
};
