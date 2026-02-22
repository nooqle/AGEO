'use client';

import { useRef, useEffect, useState, useCallback, useMemo } from 'react';
import {
  RiUserLine,
  RiCompassLine,
  RiLightbulbLine,
} from '@remixicon/react';
import type { PipelineData, PipelineNode as PipelineNodeType, PipelineEdge } from '@/types/touchpoint';
import { useContextStore } from '@/stores/contextStore';

interface PersonaPipelineProps {
  data: PipelineData;
  onNodeClick?: (nodeId: string, columnKey: string) => void;
  selectedNodeId?: string | null;
  checkedIds?: Set<string>;
  onCheckChange?: (nodeId: string, checked: boolean) => void;
  selectionMode?: boolean;
}

const COLUMN_ICONS = {
  profile: RiUserLine,
  scenario: RiCompassLine,
  intent: RiLightbulbLine,
};

const COLUMN_COLORS: Record<string, { accent: string; bg: string; border: string; text: string }> = {
  purple: {
    accent: '#a855f7',
    bg: 'rgba(168, 85, 247, 0.08)',
    border: 'rgba(168, 85, 247, 0.3)',
    text: '#a855f7',
  },
  blue: {
    accent: '#3b82f6',
    bg: 'rgba(59, 130, 246, 0.08)',
    border: 'rgba(59, 130, 246, 0.3)',
    text: '#3b82f6',
  },
  orange: {
    accent: '#f59e0b',
    bg: 'rgba(245, 158, 11, 0.08)',
    border: 'rgba(245, 158, 11, 0.3)',
    text: '#f59e0b',
  },
};

export function PersonaPipeline({
  data,
  onNodeClick,
  selectedNodeId,
  checkedIds,
  onCheckChange,
  selectionMode = false,
}: PersonaPipelineProps) {
  const canvasRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const nodeRefs = useRef<Map<string, HTMLDivElement>>(new Map());
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);
  const addContextTag = useContextStore((s) => s.addContextTag);

  // Build set of connected node IDs for hover highlighting
  const connectedMap = useMemo(() => {
    const map = new Map<string, Set<string>>();
    for (const edge of data.edges) {
      if (!map.has(edge.source)) map.set(edge.source, new Set());
      if (!map.has(edge.target)) map.set(edge.target, new Set());
      map.get(edge.source)!.add(edge.target);
      map.get(edge.target)!.add(edge.source);
    }
    return map;
  }, [data.edges]);

  // Get all connected nodes (transitive) for a given node
  const getHighlightedIds = useCallback((nodeId: string | null): Set<string> => {
    if (!nodeId) return new Set();
    const result = new Set<string>([nodeId]);
    const queue = [nodeId];
    while (queue.length > 0) {
      const current = queue.shift()!;
      const neighbors = connectedMap.get(current);
      if (neighbors) {
        for (const n of neighbors) {
          if (!result.has(n)) {
            result.add(n);
            queue.push(n);
          }
        }
      }
    }
    return result;
  }, [connectedMap]);

  const highlightedIds = useMemo(
    () => getHighlightedIds(hoveredNodeId ?? selectedNodeId ?? null),
    [hoveredNodeId, selectedNodeId, getHighlightedIds]
  );

  const drawPipes = useCallback(() => {
    const svg = svgRef.current;
    const canvas = canvasRef.current;
    if (!svg || !canvas) return;

    const canvasRect = canvas.getBoundingClientRect();
    svg.style.width = canvas.scrollWidth + 'px';
    svg.style.height = canvas.scrollHeight + 'px';

    // Clear existing paths
    while (svg.firstChild) svg.removeChild(svg.firstChild);

    for (const edge of data.edges) {
      const startEl = nodeRefs.current.get(edge.source);
      const endEl = nodeRefs.current.get(edge.target);
      if (!startEl || !endEl) continue;

      const rect1 = startEl.getBoundingClientRect();
      const rect2 = endEl.getBoundingClientRect();

      const startX = rect1.right - canvasRect.left + canvas.scrollLeft;
      const startY = rect1.top - canvasRect.top + canvas.scrollTop + rect1.height / 2;
      const endX = rect2.left - canvasRect.left + canvas.scrollLeft;
      const endY = rect2.top - canvasRect.top + canvas.scrollTop + rect2.height / 2;

      const curvature = Math.min(60, (endX - startX) * 0.4);

      const pathData = `M ${startX} ${startY} C ${startX + curvature} ${startY}, ${endX - curvature} ${endY}, ${endX} ${endY}`;

      const isHighlighted = highlightedIds.size > 0 &&
        highlightedIds.has(edge.source) && highlightedIds.has(edge.target);

      // Background pipe
      const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      path.setAttribute('d', pathData);
      path.setAttribute('stroke', isHighlighted ? '#94a3b8' : '#cbd5e1');
      path.setAttribute('stroke-width', '20');
      path.setAttribute('fill', 'none');
      path.setAttribute('opacity', isHighlighted ? '0.4' : '0.15');
      path.setAttribute('stroke-linecap', 'round');

      // Inner line
      const innerPath = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      innerPath.setAttribute('d', pathData);
      innerPath.setAttribute('stroke', isHighlighted ? '#64748b' : '#94a3b8');
      innerPath.setAttribute('stroke-width', '2');
      innerPath.setAttribute('fill', 'none');
      innerPath.setAttribute('opacity', isHighlighted ? '0.5' : '0.15');

      svg.appendChild(path);
      svg.appendChild(innerPath);
    }
  }, [data.edges, highlightedIds]);

  useEffect(() => {
    drawPipes();
  }, [drawPipes]);

  // ResizeObserver for responsive redraw
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const observer = new ResizeObserver(() => {
      requestAnimationFrame(drawPipes);
    });
    observer.observe(canvas);

    return () => observer.disconnect();
  }, [drawPipes]);

  const setNodeRef = useCallback((id: string, el: HTMLDivElement | null) => {
    if (el) {
      nodeRefs.current.set(id, el);
    } else {
      nodeRefs.current.delete(id);
    }
  }, []);

  const renderTags = (tags: Record<string, string | string[]> | undefined) => {
    if (!tags) return null;
    return (
      <div className="flex flex-col gap-1.5 mt-3" style={{ borderTop: '1px solid var(--border-default)', paddingTop: '10px' }}>
        {Object.entries(tags).map(([key, value]) => {
          if (!value || (Array.isArray(value) && value.length === 0)) return null;
          return (
            <div key={key} className="flex justify-between items-start gap-2">
              <span className="text-[11px] flex-shrink-0" style={{ color: 'var(--text-muted)' }}>{key}</span>
              <span className="text-[11px] text-right leading-relaxed" style={{ color: 'var(--text-primary)' }}>
                {Array.isArray(value) ? value.join('\u3001') : value}
              </span>
            </div>
          );
        })}
      </div>
    );
  };

  return (
    <div
      ref={canvasRef}
      className="relative flex gap-8 p-6 overflow-auto"
      style={{ minHeight: '400px' }}
    >
      {/* SVG layer for pipes */}
      <svg
        ref={svgRef}
        className="absolute top-0 left-0 pointer-events-none"
        style={{ zIndex: 0 }}
      />

      {data.columns.map((col) => {
        const colors = COLUMN_COLORS[col.color] || COLUMN_COLORS.blue;
        const Icon = COLUMN_ICONS[col.key] || RiLightbulbLine;
        const isFirstCol = col.key === 'profile';

        return (
          <div key={col.key} className="flex flex-col gap-4 flex-shrink-0" style={{ width: '220px', zIndex: 1 }}>
            {/* Column header */}
            <div
              className="flex items-center gap-2 pb-2 mb-1"
              style={{ borderBottom: `2px solid ${colors.accent}` }}
            >
              <Icon className="w-4 h-4" style={{ color: colors.accent }} />
              <span className="text-xs font-semibold" style={{ color: colors.accent }}>
                {col.label}
              </span>
              <span className="text-[10px] ml-auto" style={{ color: 'var(--text-muted)' }}>
                {col.nodes.length}
              </span>
            </div>

            {/* Nodes */}
            {col.nodes.map((node) => {
              const isDimmed = highlightedIds.size > 0 && !highlightedIds.has(node.id);
              const isActive = selectedNodeId === node.id;
              const isChecked = checkedIds?.has(node.id);

              return (
                <div
                  key={node.id}
                  ref={(el) => setNodeRef(node.id, el)}
                  className="rounded-xl cursor-pointer transition-all duration-200"
                  style={{
                    padding: '14px',
                    background: 'var(--bg-primary)',
                    border: isActive
                      ? `2px solid ${colors.accent}`
                      : `1px solid var(--border-default)`,
                    boxShadow: isActive
                      ? `0 0 0 3px ${colors.border}`
                      : '0 2px 6px rgba(0,0,0,0.06)',
                    opacity: isDimmed ? 0.35 : 1,
                    transform: hoveredNodeId === node.id ? 'translateY(-2px)' : undefined,
                  }}
                  onClick={() => {
                    onNodeClick?.(node.id, col.key);
                    if (!selectionMode) {
                      addContextTag({
                        id: node.id,
                        type: col.key as 'profile' | 'scenario' | 'intent',
                        label: node.label,
                      });
                    }
                  }}
                  onMouseEnter={() => setHoveredNodeId(node.id)}
                  onMouseLeave={() => setHoveredNodeId(null)}
                >
                  {/* Card header */}
                  <div className="flex items-center gap-3">
                    {selectionMode && isFirstCol && (
                      <input
                        type="checkbox"
                        checked={isChecked ?? false}
                        onChange={(e) => {
                          e.stopPropagation();
                          onCheckChange?.(node.id, e.target.checked);
                        }}
                        className="w-4 h-4 rounded flex-shrink-0"
                        style={{ accentColor: colors.accent }}
                      />
                    )}
                    <div
                      className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
                      style={{ backgroundColor: colors.bg }}
                    >
                      <span className="text-sm font-bold" style={{ color: colors.accent }}>
                        {node.label.charAt(0)}
                      </span>
                    </div>
                    <div className="flex-1 min-w-0">
                      <h4 className="text-sm font-medium truncate" style={{ color: 'var(--text-primary)' }}>
                        {node.label}
                      </h4>
                      {node.subtitle && (
                        <p className="text-[11px] truncate mt-0.5" style={{ color: 'var(--text-muted)' }}>
                          {node.subtitle}
                        </p>
                      )}
                    </div>
                    {node.priority && (
                      <span
                        className="text-[10px] px-1.5 py-0.5 rounded flex-shrink-0"
                        style={{
                          backgroundColor: colors.bg,
                          color: colors.text,
                        }}
                      >
                        {node.priority}
                      </span>
                    )}
                  </div>

                  {/* Tags */}
                  {renderTags(node.tags)}
                </div>
              );
            })}

            {col.nodes.length === 0 && (
              <div className="flex items-center justify-center py-8 rounded-xl" style={{ border: '1px dashed var(--border-default)' }}>
                <span className="text-xs" style={{ color: 'var(--text-muted)' }}>暂无数据</span>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
