import React, { useEffect, useRef } from 'react';

interface NeuralThreadsCanvasProps {
  className?: string;
  density?: 'low' | 'medium' | 'high';
  interactive?: boolean;
}

interface Node {
  x: number;
  y: number;
  vx: number;
  vy: number;
  radius: number;
  baseRadius: number;
  type: 'memory' | 'evidence' | 'condition';
  pulse: number;
}

interface Thread {
  source: number;
  target: number;
  progress: number;
  speed: number;
}

export const NeuralThreadsCanvas: React.FC<NeuralThreadsCanvasProps> = ({
  className = '',
  density = 'medium',
  interactive = true,
}) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const mouseRef = useRef<{ x: number; y: number; active: boolean }>({ x: 0, y: 0, active: false });

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animationFrameId: number;
    let width = (canvas.width = canvas.offsetWidth);
    let height = (canvas.height = canvas.offsetHeight);

    const handleResize = () => {
      if (!canvas) return;
      width = canvas.width = canvas.offsetWidth;
      height = canvas.height = canvas.offsetHeight;
      initNodes();
    };

    window.addEventListener('resize', handleResize);

    const nodeCount = density === 'low' ? 22 : density === 'high' ? 55 : 36;
    let nodes: Node[] = [];
    let threads: Thread[] = [];

    const initNodes = () => {
      nodes = [];
      const types: ('memory' | 'evidence' | 'condition')[] = ['memory', 'evidence', 'condition'];
      for (let i = 0; i < nodeCount; i++) {
        const type = types[i % types.length];
        const baseRadius = type === 'memory' ? 3.5 : type === 'condition' ? 2.5 : 2.0;
        nodes.push({
          x: Math.random() * width,
          y: Math.random() * height,
          vx: (Math.random() - 0.5) * 0.45,
          vy: (Math.random() - 0.5) * 0.45,
          radius: baseRadius,
          baseRadius,
          type,
          pulse: Math.random() * Math.PI * 2,
        });
      }

      // Pre-seed connected threads
      threads = [];
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const dx = nodes[i].x - nodes[j].x;
          const dy = nodes[i].y - nodes[j].y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          if (dist < 140 && Math.random() > 0.4) {
            threads.push({
              source: i,
              target: j,
              progress: Math.random(),
              speed: 0.004 + Math.random() * 0.006,
            });
          }
        }
      }
    };

    initNodes();

    // Check prefers-reduced-motion
    const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
    const isReduced = mediaQuery.matches;

    const render = () => {
      ctx.clearRect(0, 0, width, height);

      // 1. Draw interconnected threads
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const a = nodes[i];
          const b = nodes[j];
          const dx = a.x - b.x;
          const dy = a.y - b.y;
          const dist = Math.sqrt(dx * dx + dy * dy);

          const maxDist = 160;
          if (dist < maxDist) {
            const alpha = (1 - dist / maxDist) * 0.35;
            ctx.beginPath();
            ctx.moveTo(a.x, a.y);

            // Natural curved filaments
            const midX = (a.x + b.x) / 2 + Math.sin(a.pulse) * 4;
            const midY = (a.y + b.y) / 2 + Math.cos(b.pulse) * 4;
            ctx.quadraticCurveTo(midX, midY, b.x, b.y);

            // Copper to brass filament gradient
            const grad = ctx.createLinearGradient(a.x, a.y, b.x, b.y);
            grad.addColorStop(0, `rgba(194, 106, 62, ${alpha})`);
            grad.addColorStop(0.5, `rgba(217, 138, 91, ${alpha * 1.2})`);
            grad.addColorStop(1, `rgba(197, 155, 78, ${alpha})`);
            ctx.strokeStyle = grad;
            ctx.lineWidth = 1;
            ctx.stroke();
          }
        }
      }

      // 2. Animate traveling pulses along threads
      if (!isReduced) {
        for (const thread of threads) {
          const a = nodes[thread.source];
          const b = nodes[thread.target];
          if (!a || !b) continue;

          thread.progress += thread.speed;
          if (thread.progress > 1) thread.progress = 0;

          const px = a.x + (b.x - a.x) * thread.progress;
          const py = a.y + (b.y - a.y) * thread.progress;

          ctx.beginPath();
          ctx.arc(px, py, 1.5, 0, Math.PI * 2);
          ctx.fillStyle = 'rgba(232, 162, 121, 0.8)';
          ctx.fill();
        }
      }

      // 3. Draw Nodes (Memories, Evidence, Conditions)
      for (const node of nodes) {
        if (!isReduced) {
          node.x += node.vx;
          node.y += node.vy;
          node.pulse += 0.02;

          // Gentle bounds bounce
          if (node.x < 10 || node.x > width - 10) node.vx *= -1;
          if (node.y < 10 || node.y > height - 10) node.vy *= -1;

          // Mouse attraction if interactive
          if (interactive && mouseRef.current.active) {
            const mdx = mouseRef.current.x - node.x;
            const mdy = mouseRef.current.y - node.y;
            const mdist = Math.sqrt(mdx * mdx + mdy * mdy);
            if (mdist < 140) {
              node.x += (mdx / mdist) * 0.6;
              node.y += (mdy / mdist) * 0.6;
            }
          }
        }

        // Render node with glow
        ctx.beginPath();
        const pulseR = node.baseRadius + (isReduced ? 0 : Math.sin(node.pulse) * 0.6);
        ctx.arc(node.x, node.y, pulseR, 0, Math.PI * 2);

        if (node.type === 'memory') {
          ctx.fillStyle = '#C26A3E'; // Copper
        } else if (node.type === 'condition') {
          ctx.fillStyle = '#C59B4E'; // Brass
        } else {
          ctx.fillStyle = '#7A8D7E'; // Sage
        }
        ctx.fill();

        // Outer synaptic halo
        ctx.beginPath();
        ctx.arc(node.x, node.y, pulseR + 2, 0, Math.PI * 2);
        ctx.strokeStyle = node.type === 'memory' ? 'rgba(194, 106, 62, 0.3)' : 'rgba(197, 155, 78, 0.25)';
        ctx.lineWidth = 1;
        ctx.stroke();
      }

      if (!isReduced) {
        animationFrameId = requestAnimationFrame(render);
      }
    };

    render();

    const handleMouseMove = (e: MouseEvent) => {
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

    if (interactive) {
      canvas.addEventListener('mousemove', handleMouseMove);
      canvas.addEventListener('mouseleave', handleMouseLeave);
    }

    return () => {
      window.removeEventListener('resize', handleResize);
      if (interactive) {
        canvas.removeEventListener('mousemove', handleMouseMove);
        canvas.removeEventListener('mouseleave', handleMouseLeave);
      }
      cancelAnimationFrame(animationFrameId);
    };
  }, [density, interactive]);

  return (
    <canvas
      ref={canvasRef}
      className={`w-full h-full block pointer-events-auto ${className}`}
    />
  );
};

