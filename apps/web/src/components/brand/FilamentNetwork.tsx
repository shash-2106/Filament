import React, { useEffect, useRef } from 'react';

interface FilamentNetworkProps {
  className?: string;
  interactive?: boolean;
}

interface Node {
  id: string;
  label: string;
  sublabel: string;
  type: 'evidence' | 'memory' | 'condition' | 'outcome';
  x: number;
  y: number;
  targetX: number;
  targetY: number;
  status: 'applicable' | 'drifted' | 'disputed' | 'active';
  radius: number;
}

interface Edge {
  source: string;
  target: string;
  status: 'applicable' | 'drifted' | 'disputed';
  label?: string;
  progress: number;
}

export const FilamentNetwork: React.FC<FilamentNetworkProps> = ({
  className = '',
  interactive = true,
}) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const mouseRef = useRef<{ x: number; y: number; active: boolean }>({ x: 0, y: 0, active: false });

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animId: number;
    let width = (canvas.width = canvas.offsetWidth);
    let height = (canvas.height = canvas.offsetHeight);

    const handleResize = () => {
      if (!canvas) return;
      width = canvas.width = canvas.offsetWidth;
      height = canvas.height = canvas.offsetHeight;
      layoutNodes();
    };

    window.addEventListener('resize', handleResize);

    // Conceptually structured nodes: Evidence -> Memory -> Conditions -> Applicability
    let nodes: Node[] = [];
    let edges: Edge[] = [];

    const layoutNodes = () => {
      const centerY = height / 2;
      const col1 = width * 0.12;
      const col2 = width * 0.38;
      const col3 = width * 0.64;
      const col4 = width * 0.88;

      nodes = [
        // Column 1: Evidence & Sources
        {
          id: 'ev-1',
          label: 'User Turn #1',
          sublabel: 'pgvector pool: 5',
          type: 'evidence',
          x: col1,
          y: centerY - 90,
          targetX: col1,
          targetY: centerY - 90,
          status: 'applicable',
          radius: 18,
        },
        {
          id: 'ev-2',
          label: 'Security Turn #2',
          sublabel: 'sslmode=verify-full',
          type: 'evidence',
          x: col1,
          y: centerY + 10,
          targetX: col1,
          targetY: centerY + 10,
          status: 'applicable',
          radius: 18,
        },
        {
          id: 'ev-3',
          label: 'DevOps Turn #3',
          sublabel: 'SQLite cancelled',
          type: 'evidence',
          x: col1,
          y: centerY + 105,
          targetX: col1,
          targetY: centerY + 105,
          status: 'disputed',
          radius: 16,
        },

        // Column 2: Memory & Assertions
        {
          id: 'mem-1',
          label: 'Memory #4881',
          sublabel: 'Postgres pgvector pool',
          type: 'memory',
          x: col2,
          y: centerY - 65,
          targetX: col2,
          targetY: centerY - 65,
          status: 'applicable',
          radius: 22,
        },
        {
          id: 'mem-2',
          label: 'Memory #4882',
          sublabel: 'Enforce SSL verification',
          type: 'memory',
          x: col2,
          y: centerY + 50,
          targetX: col2,
          targetY: centerY + 50,
          status: 'applicable',
          radius: 22,
        },

        // Column 3: Environmental Conditions
        {
          id: 'cond-1',
          label: 'Env: Postgres 15',
          sublabel: 'docker/db:15',
          type: 'condition',
          x: col3,
          y: centerY - 70,
          targetX: col3,
          targetY: centerY - 70,
          status: 'applicable',
          radius: 17,
        },
        {
          id: 'cond-2',
          label: 'Env: SSL Root CA',
          sublabel: 'aws-pooler cert',
          type: 'condition',
          x: col3,
          y: centerY + 30,
          targetX: col3,
          targetY: centerY + 30,
          status: 'applicable',
          radius: 17,
        },

        // Column 4: Verification Outcomes
        {
          id: 'out-1',
          label: 'Applicable',
          sublabel: 'Valid in cluster',
          type: 'outcome',
          x: col4,
          y: centerY - 40,
          targetX: col4,
          targetY: centerY - 40,
          status: 'applicable',
          radius: 24,
        },
        {
          id: 'out-2',
          label: 'Condition Drift',
          sublabel: 'Re-check warning',
          type: 'outcome',
          x: col4,
          y: centerY + 65,
          targetX: col4,
          targetY: centerY + 65,
          status: 'drifted',
          radius: 20,
        },
      ];

      edges = [
        { source: 'ev-1', target: 'mem-1', status: 'applicable', progress: 0 },
        { source: 'ev-2', target: 'mem-2', status: 'applicable', progress: 0.3 },
        { source: 'ev-3', target: 'mem-1', status: 'disputed', progress: 0.7 },
        { source: 'mem-1', target: 'cond-1', status: 'applicable', progress: 0.2 },
        { source: 'mem-2', target: 'cond-2', status: 'applicable', progress: 0.5 },
        { source: 'cond-1', target: 'out-1', status: 'applicable', progress: 0.8 },
        { source: 'cond-2', target: 'out-1', status: 'applicable', progress: 0.4 },
        { source: 'cond-2', target: 'out-2', status: 'drifted', progress: 0.1 },
      ];
    };

    layoutNodes();

    const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
    const isReduced = mediaQuery.matches;

    // Mouse tracking for interactive tension
    const handleMouseMove = (e: MouseEvent) => {
      if (!interactive) return;
      const rect = canvas.getBoundingClientRect();
      mouseRef.current = {
        x: e.clientX - rect.left,
        y: e.clientY - rect.top,
        active: true,
      };
    };

    const handleMouseLeave = () => {
      mouseRef.current.active = false;
    };

    canvas.addEventListener('mousemove', handleMouseMove);
    canvas.addEventListener('mouseleave', handleMouseLeave);

    let time = 0;

    const render = () => {
      ctx.clearRect(0, 0, width, height);
      time += 0.02;

      // Draw subtle background grid
      ctx.strokeStyle = '#14231D';
      ctx.lineWidth = 1;
      const gridSize = 40;
      for (let x = 0; x < width; x += gridSize) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, height);
        ctx.stroke();
      }
      for (let y = 0; y < height; y += gridSize) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(width, y);
        ctx.stroke();
      }

      // Map nodes by id
      const nodeMap = new Map<string, Node>();
      for (const n of nodes) {
        // Interactive mouse gentle push
        if (mouseRef.current.active && interactive) {
          const dx = mouseRef.current.x - n.x;
          const dy = mouseRef.current.y - n.y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          if (dist < 100) {
            const force = (100 - dist) / 100;
            n.x -= (dx / dist) * force * 2.5;
            n.y -= (dy / dist) * force * 2.5;
          }
        }
        // Elastic return to target position
        n.x += (n.targetX - n.x) * 0.08;
        n.y += (n.targetY - n.y) * 0.08;
        nodeMap.set(n.id, n);
      }

      // 1. Draw Curved Connecting Filaments
      for (const edge of edges) {
        const src = nodeMap.get(edge.source);
        const tgt = nodeMap.get(edge.target);
        if (!src || !tgt) continue;

        const cp1x = src.x + (tgt.x - src.x) * 0.5;
        const cp1y = src.y;
        const cp2x = src.x + (tgt.x - src.x) * 0.5;
        const cp2y = tgt.y;

        ctx.beginPath();
        ctx.moveTo(src.x, src.y);
        ctx.bezierCurveTo(cp1x, cp1y, cp2x, cp2y, tgt.x, tgt.y);

        if (edge.status === 'applicable') {
          ctx.strokeStyle = 'rgba(127, 221, 157, 0.45)';
          ctx.lineWidth = 2;
        } else if (edge.status === 'drifted') {
          ctx.strokeStyle = 'rgba(214, 125, 101, 0.45)';
          ctx.lineWidth = 1.5;
        } else {
          ctx.strokeStyle = 'rgba(169, 101, 128, 0.45)';
          ctx.lineWidth = 1.5;
        }
        ctx.stroke();

        // 2. Animate Traveling Signal Pulse along filament
        if (!isReduced) {
          edge.progress = (edge.progress + 0.006) % 1.0;
          const t = edge.progress;
          // Cubic Bezier interpolation
          const u = 1 - t;
          const tt = t * t;
          const uu = u * u;
          const uuu = uu * u;
          const ttt = tt * t;

          const px = uuu * src.x + 3 * uu * t * cp1x + 3 * u * tt * cp2x + ttt * tgt.x;
          const py = uuu * src.y + 3 * uu * t * cp1y + 3 * u * tt * cp2y + ttt * tgt.y;

          ctx.beginPath();
          ctx.arc(px, py, 3, 0, Math.PI * 2);
          ctx.fillStyle = edge.status === 'applicable' ? '#7FDD9D' : edge.status === 'drifted' ? '#D67D65' : '#A96580';
          ctx.shadowColor = ctx.fillStyle;
          ctx.shadowBlur = 8;
          ctx.fill();
          ctx.shadowBlur = 0;
        }
      }

      // 3. Draw Nodes with Technical Inspection Rings
      for (const n of nodes) {
        // Outer glow & halo
        ctx.beginPath();
        ctx.arc(n.x, n.y, n.radius + 6, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(20, 35, 29, 0.6)';
        ctx.fill();

        // Main node circle
        ctx.beginPath();
        ctx.arc(n.x, n.y, n.radius, 0, Math.PI * 2);
        ctx.fillStyle = '#14231D';
        ctx.fill();

        // Border according to status
        ctx.beginPath();
        ctx.arc(n.x, n.y, n.radius, 0, Math.PI * 2);
        ctx.lineWidth = 2;
        if (n.status === 'applicable') {
          ctx.strokeStyle = '#7FDD9D';
        } else if (n.status === 'drifted') {
          ctx.strokeStyle = '#D67D65';
        } else if (n.status === 'disputed') {
          ctx.strokeStyle = '#A96580';
        } else {
          ctx.strokeStyle = '#58B985';
        }
        ctx.stroke();

        // Inner glowing core
        ctx.beginPath();
        ctx.arc(n.x, n.y, 4, 0, Math.PI * 2);
        ctx.fillStyle = n.status === 'applicable' ? '#7FDD9D' : n.status === 'drifted' ? '#D67D65' : '#A96580';
        ctx.fill();

        // Technical Labeling
        ctx.font = '500 11px "Space Grotesk", sans-serif';
        ctx.fillStyle = '#E7F0EA';
        ctx.textAlign = 'center';
        ctx.fillText(n.label, n.x, n.y + n.radius + 15);

        ctx.font = '400 9px "IBM Plex Mono", monospace';
        ctx.fillStyle = '#647D70';
        ctx.fillText(n.sublabel, n.x, n.y + n.radius + 27);
      }

      animId = requestAnimationFrame(render);
    };

    render();

    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener('resize', handleResize);
      canvas.removeEventListener('mousemove', handleMouseMove);
      canvas.removeEventListener('mouseleave', handleMouseLeave);
    };
  }, [interactive]);

  return (
    <div className={`relative w-full h-full min-h-[340px] rounded-lg overflow-hidden border border-[#294537] bg-[#070D0B] ${className}`}>
      {/* Legend Header */}
      <div className="absolute top-3 left-4 right-4 z-10 flex items-center justify-between text-[11px] font-mono text-graphite-text-tertiary">
        <div className="flex items-center gap-3">
          <span className="flex items-center gap-1.5 text-graphite-text-secondary">
            <span className="w-2 h-2 rounded-full bg-phosphor" />
            Evidence &rarr; Memory &rarr; Conditions &rarr; Applicability
          </span>
        </div>
        <div className="flex items-center gap-3">
          <span className="flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-phosphor" /> Applicable
          </span>
          <span className="flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-[#D67D65]" /> Condition Drift
          </span>
          <span className="flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-[#A96580]" /> Disputed
          </span>
        </div>
      </div>

      <canvas ref={canvasRef} className="w-full h-full block" />
    </div>
  );
};

