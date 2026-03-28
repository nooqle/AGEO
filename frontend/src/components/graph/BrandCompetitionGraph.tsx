'use client';

import React, { useEffect, useRef, useState, useMemo, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { cn } from '@/lib/cn';

interface BrandCompetitionGraphProps {
  brandProfile?: {
    brand_name: string;
    brand_name_en?: string;
    industry?: string;
  };
  competitors?: Array<{
    name: string;
    name_en?: string;
    relevance_score: number;
    competition_type: string;
    competitive_advantage?: string;
  }>;
  className?: string;
}

interface TooltipData {
  visible: boolean;
  x: number;
  y: number;
  title: string;
  type: string;
  score?: number;
  description?: string;
}

const TYPE_COLORS: Record<string, string> = {
  '直接竞争': '#EF4444',
  '间接竞争': '#F59E0B',
  '潜在竞争': '#6B7280',
};

function getTypeColor(type: string) {
  return TYPE_COLORS[type] || '#6B7280';
}

/** Truncate text to fit within a given pixel width (approximate). */
function truncateLabel(text: string, maxChars: number): string {
  if (text.length <= maxChars) return text;
  return text.slice(0, maxChars - 1) + '…';
}

export const BrandCompetitionGraph = React.memo(function BrandCompetitionGraph({
  brandProfile,
  competitors = [],
  className,
}: BrandCompetitionGraphProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ width: 460, height: 400 });
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [tooltip, setTooltip] = useState<TooltipData>({
    visible: false, x: 0, y: 0, title: '', type: '',
  });

  // Measure container width via ResizeObserver
  useEffect(() => {
    if (!containerRef.current) return;
    const el = containerRef.current;
    const ro = new ResizeObserver((entries) => {
      const { width } = entries[0].contentRect;
      if (width > 0) {
        setDimensions({ width, height: Math.max(340, Math.min(420, width * 0.85)) });
      }
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Compute node positions (radial layout)
  const { cx, cy, brandR, compR, orbitR, nodes } = useMemo(() => {
    const w = dimensions.width;
    const h = dimensions.height;
    const centerX = w / 2;
    const centerY = h / 2;
    const orbit = Math.min(centerX, centerY) * 0.62;
    const bR = 42;
    const cR = 28;
    const n = competitors.length;

    const positioned = competitors.map((comp, i) => {
      const angle = n === 1
        ? -Math.PI / 2
        : (2 * Math.PI * i) / n - Math.PI / 2;
      return {
        ...comp,
        id: `comp-${i}`,
        x: centerX + orbit * Math.cos(angle),
        y: centerY + orbit * Math.sin(angle),
        color: getTypeColor(comp.competition_type),
      };
    });

    return { cx: centerX, cy: centerY, brandR: bR, compR: cR, orbitR: orbit, nodes: positioned };
  }, [competitors, dimensions]);

  const handleNodeEnter = useCallback((e: React.MouseEvent<SVGGElement>, node: typeof nodes[number]) => {
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect) return;
    setTooltip({
      visible: true,
      x: e.clientX - rect.left + 12,
      y: e.clientY - rect.top - 12,
      title: node.name,
      type: node.competition_type,
      score: node.relevance_score,
      description: node.competitive_advantage,
    });
  }, []);

  const handleBrandEnter = useCallback((e: React.MouseEvent<SVGGElement>) => {
    if (!brandProfile) return;
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect) return;
    setTooltip({
      visible: true,
      x: e.clientX - rect.left + 12,
      y: e.clientY - rect.top - 12,
      title: brandProfile.brand_name,
      type: '目标品牌',
      description: brandProfile.industry,
    });
  }, [brandProfile]);

  const handleNodeLeave = useCallback(() => {
    setTooltip((prev) => ({ ...prev, visible: false }));
  }, []);

  const handleNodeClick = useCallback((id: string) => {
    setSelectedNode((prev) => (prev === id ? null : id));
  }, []);

  const handleSvgClick = useCallback((e: React.MouseEvent<SVGSVGElement>) => {
    if ((e.target as SVGElement).tagName === 'svg') {
      setSelectedNode(null);
    }
  }, []);

  if (!brandProfile) {
    return (
      <div className={cn('rounded-xl p-8', className)}
        style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-subtle)' }}
      >
        <div className="flex flex-col items-center justify-center h-[340px] text-center">
          <div className="w-16 h-16 rounded-2xl flex items-center justify-center mb-4"
            style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-strong)' }}
          >
            <svg className="w-8 h-8" style={{ color: 'var(--text-muted)' }} fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
          </div>
          <h3 className="text-lg font-medium mb-2" style={{ color: 'var(--text-tertiary)' }}>等待品牌数据</h3>
          <p className="text-sm max-w-[280px]" style={{ color: 'var(--text-muted)' }}>
            完成品牌档案分析后，将在此处显示竞品关系图谱
          </p>
        </div>
      </div>
    );
  }

  const isNodeDimmed = (id: string) => {
    if (!selectedNode) return false;
    if (selectedNode === id) return false;
    // Brand or a node connected to brand are never dimmed when brand is selected
    if (selectedNode === 'brand') return false;
    if (id === 'brand') return false;
    return true;
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn('rounded-xl overflow-hidden relative', className)}
      style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-subtle)' }}
    >
      {/* Header */}
      <div className="px-4 py-3" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-base font-semibold" style={{ color: 'var(--text-primary)' }}>品牌竞品关系图谱</h3>
            <p className="text-sm mt-0.5" style={{ color: 'var(--text-secondary)' }}>
              {brandProfile.brand_name} · {brandProfile.industry || '行业分析'}
            </p>
          </div>
          <div className="flex items-center gap-3 text-xs">
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-[#6366F1]" />
              <span style={{ color: 'var(--text-secondary)' }}>目标品牌</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-[#EF4444]" />
              <span style={{ color: 'var(--text-secondary)' }}>直接竞争</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-[#F59E0B]" />
              <span style={{ color: 'var(--text-secondary)' }}>间接竞争</span>
            </div>
          </div>
        </div>
      </div>

      {/* SVG Graph */}
      <div ref={containerRef} className="w-full" style={{ height: dimensions.height }}>
        <svg
          width={dimensions.width}
          height={dimensions.height}
          onClick={handleSvgClick}
          className="select-none"
        >
          {/* Orbit ring (decorative) */}
          <circle
            cx={cx} cy={cy} r={orbitR}
            fill="none"
            stroke="var(--border-subtle)"
            strokeWidth={1}
            strokeDasharray="4 4"
            opacity={0.5}
          />

          {/* Edges */}
          {nodes.map((node) => {
            const dimmed = isNodeDimmed(node.id);
            const highlighted = selectedNode === node.id || selectedNode === 'brand';
            return (
              <line
                key={`edge-${node.id}`}
                x1={cx} y1={cy}
                x2={node.x} y2={node.y}
                stroke={node.color}
                strokeWidth={highlighted ? 2.5 : Math.max(1, node.relevance_score / 4)}
                opacity={dimmed ? 0.15 : 0.6}
                className="transition-all duration-200"
              />
            );
          })}

          {/* Competitor nodes */}
          {nodes.map((node) => {
            const dimmed = isNodeDimmed(node.id);
            const selected = selectedNode === node.id;
            return (
              <g
                key={node.id}
                className="cursor-pointer"
                style={{ opacity: dimmed ? 0.25 : 1, transition: 'opacity 0.2s' }}
                onMouseEnter={(e) => handleNodeEnter(e, node)}
                onMouseLeave={handleNodeLeave}
                onClick={(e) => { e.stopPropagation(); handleNodeClick(node.id); }}
              >
                {/* Glow ring on selected */}
                {selected && (
                  <circle
                    cx={node.x} cy={node.y} r={compR + 5}
                    fill="none" stroke={node.color} strokeWidth={2}
                    opacity={0.5}
                  />
                )}
                <circle
                  cx={node.x} cy={node.y} r={compR}
                  fill={node.color}
                  stroke={selected ? '#fff' : 'transparent'}
                  strokeWidth={selected ? 2 : 0}
                  className="transition-all duration-150"
                />
                {/* Score inside circle */}
                <text
                  x={node.x} y={node.y + 1}
                  textAnchor="middle"
                  dominantBaseline="central"
                  fill="#fff"
                  fontSize={14}
                  fontWeight={600}
                >
                  {node.relevance_score}
                </text>
                {/* Label below */}
                <text
                  x={node.x} y={node.y + compR + 16}
                  textAnchor="middle"
                  dominantBaseline="central"
                  fill="var(--text-secondary)"
                  fontSize={13}
                  fontWeight={500}
                >
                  {truncateLabel(node.name, 6)}
                </text>
              </g>
            );
          })}

          {/* Brand node (center, on top) */}
          <g
            className="cursor-pointer"
            onMouseEnter={handleBrandEnter}
            onMouseLeave={handleNodeLeave}
            onClick={(e) => { e.stopPropagation(); handleNodeClick('brand'); }}
          >
            {/* Outer glow */}
            <circle cx={cx} cy={cy} r={brandR + 6} fill="none" stroke="#6366F1" strokeWidth={1.5} opacity={0.3} />
            <circle cx={cx} cy={cy} r={brandR} fill="#6366F1" />
            {selectedNode === 'brand' && (
              <circle cx={cx} cy={cy} r={brandR} fill="none" stroke="#fff" strokeWidth={2.5} />
            )}
            <text
              x={cx} y={cy + 1}
              textAnchor="middle"
              dominantBaseline="central"
              fill="#fff"
              fontSize={15}
              fontWeight={700}
            >
              {truncateLabel(brandProfile.brand_name, 5)}
            </text>
          </g>
        </svg>
      </div>

      {/* Tooltip */}
      <AnimatePresence>
        {tooltip.visible && (
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            transition={{ duration: 0.12 }}
            className="absolute z-10 pointer-events-none"
            style={{ left: Math.min(tooltip.x, dimensions.width - 200), top: tooltip.y }}
          >
            <div className="rounded-lg px-3.5 py-2.5 shadow-lg min-w-[180px]"
              style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-strong)' }}
            >
              <div className="flex items-center gap-2 mb-1">
                <span className={cn(
                  'w-2.5 h-2.5 rounded-full',
                  tooltip.type === '目标品牌' ? 'bg-[#6366F1]' :
                  tooltip.type === '直接竞争' ? 'bg-[#EF4444]' :
                  tooltip.type === '间接竞争' ? 'bg-[#F59E0B]' : 'bg-[#6B7280]'
                )} />
                <span className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{tooltip.title}</span>
              </div>
              <div className="text-xs" style={{ color: 'var(--text-secondary)' }}>{tooltip.type}</div>
              {tooltip.score !== undefined && (
                <div className="text-sm mt-1 font-medium" style={{ color: 'var(--color-primary)' }}>
                  相关度: {tooltip.score}/10
                </div>
              )}
              {tooltip.description && tooltip.description !== '目标品牌' && (
                <div className="text-sm mt-1 line-clamp-2" style={{ color: 'var(--text-secondary)' }}>
                  {tooltip.description}
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
});

BrandCompetitionGraph.displayName = 'BrandCompetitionGraph';

export default BrandCompetitionGraph;
