'use client';

import React, { useState, useMemo, useEffect, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { cn } from '@/lib/cn';

interface PersonaNode {
  id: string;
  persona_name: string;
  persona_description: string;
  persona_priority: string;
  demographics?: {
    age_range?: string;
    gender?: string;
    city_tier?: string;
    occupation?: string;
  };
  marketing_pain_points?: Array<{
    pain_point_category: string;
    pain_point_description: string;
  }>;
  usage_scenarios?: Array<{
    scenario_name: string;
    scenario_description: string;
  }>;
}

interface PersonaGraphProps {
  personas?: PersonaNode[];
  brandName?: string;
  className?: string;
}

interface TooltipData {
  visible: boolean;
  x: number;
  y: number;
  title: string;
  subtitle?: string;
  type: 'brand' | 'persona' | 'scenario' | 'pain_point';
  color: string;
}

// Layout constants
const NODE_H = 32;
const NODE_PAD_X = 16;
const NODE_PAD_Y = 8;
const LEVEL_GAP_X = 180;
const SIBLING_GAP_Y = 6;
const CHILD_GROUP_GAP_Y = 16;
const BRAND_R = 36;

const PRIORITY_COLORS: Record<string, string> = {
  '\u6838\u5fc3\u4eba\u7fa4': '#EF4444',
  '\u91cd\u70b9\u4eba\u7fa4': '#F59E0B',
  '\u589e\u957f\u4eba\u7fa4': '#F59E0B',
  '\u673a\u4f1a\u4eba\u7fa4': '#22C55E',
};

function getPriorityColor(priority: string): string {
  return PRIORITY_COLORS[priority] || '#6B7280';
}

function truncateLabel(text: string, maxChars: number): string {
  if (text.length <= maxChars) return text;
  return text.slice(0, maxChars - 1) + '\u2026';
}

// Measure text width approximately (Chinese chars ~14px at 12px font, Latin ~7px)
function estimateTextWidth(text: string, fontSize: number = 12): number {
  let width = 0;
  for (const ch of text) {
    width += ch.charCodeAt(0) > 127 ? fontSize * 1.15 : fontSize * 0.62;
  }
  return width;
}

// ---------- Tree layout types ----------

interface TreeNode {
  id: string;
  label: string;
  fullLabel: string;
  type: 'brand' | 'persona' | 'scenario' | 'pain_point';
  color: string;
  tooltipSubtitle?: string;
  children: TreeNode[];
}

interface LayoutNode extends TreeNode {
  x: number;
  y: number;
  width: number;
  height: number;
  children: LayoutNode[];
  collapsed: boolean;
}

function buildTree(personas: PersonaNode[], brandName: string): TreeNode {
  const root: TreeNode = {
    id: 'brand',
    label: truncateLabel(brandName, 6),
    fullLabel: brandName,
    type: 'brand',
    color: '#6366F1',
    children: [],
  };

  personas.forEach((persona, pi) => {
    const pColor = getPriorityColor(persona.persona_priority);
    const personaNode: TreeNode = {
      id: `p-${pi}`,
      label: truncateLabel(persona.persona_name, 8),
      fullLabel: persona.persona_name,
      type: 'persona',
      color: pColor,
      tooltipSubtitle: persona.persona_priority || undefined,
      children: [],
    };

    persona.usage_scenarios?.forEach((s, si) => {
      personaNode.children.push({
        id: `p-${pi}-s-${si}`,
        label: truncateLabel(s.scenario_name, 10),
        fullLabel: s.scenario_name,
        type: 'scenario',
        color: '#8B5CF6',
        tooltipSubtitle: s.scenario_description,
        children: [],
      });
    });

    persona.marketing_pain_points?.forEach((pp, ppi) => {
      personaNode.children.push({
        id: `p-${pi}-pp-${ppi}`,
        label: truncateLabel(pp.pain_point_category, 10),
        fullLabel: pp.pain_point_category,
        type: 'pain_point',
        color: '#EC4899',
        tooltipSubtitle: pp.pain_point_description,
        children: [],
      });
    });

    root.children.push(personaNode);
  });

  return root;
}

function layoutTree(
  root: TreeNode,
  collapsedSet: Set<string>,
): { layoutRoot: LayoutNode; totalWidth: number; totalHeight: number } {
  // Recursive bottom-up: compute subtree height, then assign y positions
  function measure(node: TreeNode, depth: number): LayoutNode {
    const collapsed = collapsedSet.has(node.id);
    const labelWidth = node.type === 'brand'
      ? BRAND_R * 2
      : estimateTextWidth(node.label, 12) + NODE_PAD_X * 2;
    const nodeWidth = Math.max(labelWidth, 60);
    const nodeHeight = node.type === 'brand' ? BRAND_R * 2 : NODE_H;

    const layoutChildren: LayoutNode[] = [];
    if (!collapsed) {
      node.children.forEach((child) => {
        layoutChildren.push(measure(child, depth + 1));
      });
    }

    return {
      ...node,
      x: 0,
      y: 0,
      width: nodeWidth,
      height: nodeHeight,
      children: layoutChildren,
      collapsed,
    };
  }

  function subtreeHeight(node: LayoutNode): number {
    if (node.children.length === 0) return node.height;
    let total = 0;
    node.children.forEach((child, i) => {
      total += subtreeHeight(child);
      if (i < node.children.length - 1) total += SIBLING_GAP_Y;
    });
    // Add extra gap between persona groups (level 1 children)
    return total;
  }

  function assignPositions(node: LayoutNode, x: number, yStart: number): void {
    const childrenH = node.children.reduce((acc, child, i) => {
      return acc + subtreeHeight(child) + (i > 0 ? SIBLING_GAP_Y : 0);
    }, 0);

    // Center this node vertically relative to its children
    if (node.children.length > 0) {
      node.x = x;
      node.y = yStart + childrenH / 2 - node.height / 2;
    } else {
      node.x = x;
      node.y = yStart;
    }

    // Position children
    let cy = yStart;
    const childX = x + LEVEL_GAP_X;
    node.children.forEach((child, i) => {
      if (i > 0) cy += SIBLING_GAP_Y;
      assignPositions(child, childX, cy);
      cy += subtreeHeight(child);
    });
  }

  const layoutRoot = measure(root, 0);
  const totalH = subtreeHeight(layoutRoot);
  assignPositions(layoutRoot, 40, 20);

  // Compute total width (max x + node width + padding)
  function maxX(node: LayoutNode): number {
    let mx = node.x + node.width;
    node.children.forEach((child) => {
      mx = Math.max(mx, maxX(child));
    });
    return mx;
  }

  return {
    layoutRoot,
    totalWidth: maxX(layoutRoot) + 40,
    totalHeight: totalH + 40,
  };
}

// ---------- SVG rendering helpers ----------

function renderEdge(parent: LayoutNode, child: LayoutNode, key: string) {
  const x1 = parent.type === 'brand'
    ? parent.x + parent.width / 2
    : parent.x + parent.width;
  const y1 = parent.y + parent.height / 2;
  const x2 = child.x;
  const y2 = child.y + child.height / 2;
  const midX = (x1 + x2) / 2;

  return (
    <path
      key={key}
      d={`M ${x1} ${y1} C ${midX} ${y1}, ${midX} ${y2}, ${x2} ${y2}`}
      fill="none"
      stroke={child.color}
      strokeWidth={1.5}
      opacity={0.4}
      className="transition-opacity duration-200"
    />
  );
}

function collectEdges(node: LayoutNode): React.ReactNode[] {
  const edges: React.ReactNode[] = [];
  node.children.forEach((child) => {
    edges.push(renderEdge(node, child, `edge-${node.id}-${child.id}`));
    edges.push(...collectEdges(child));
  });
  return edges;
}

function collectNodes(
  node: LayoutNode,
  onToggle: (id: string) => void,
  onEnter: (e: React.MouseEvent, node: LayoutNode) => void,
  onLeave: () => void,
): React.ReactNode[] {
  const nodes: React.ReactNode[] = [];

  if (node.type === 'brand') {
    const cx = node.x + node.width / 2;
    const cy = node.y + node.height / 2;
    nodes.push(
      <g
        key={node.id}
        className="cursor-pointer"
        onMouseEnter={(e) => onEnter(e, node)}
        onMouseLeave={onLeave}
        onClick={() => onToggle(node.id)}
      >
        <circle cx={cx} cy={cy} r={BRAND_R + 4} fill="none" stroke="#6366F1" strokeWidth={1.5} opacity={0.3} />
        <circle cx={cx} cy={cy} r={BRAND_R} fill="#6366F1" />
        <text
          x={cx}
          y={cy + 1}
          textAnchor="middle"
          dominantBaseline="central"
          fill="#fff"
          fontSize={14}
          fontWeight={700}
        >
          {node.label}
        </text>
      </g>,
    );
  } else {
    const hasChildren = node.children.length > 0 || node.collapsed;
    const rx = 6;
    nodes.push(
      <g
        key={node.id}
        className={hasChildren ? 'cursor-pointer' : 'cursor-default'}
        onMouseEnter={(e) => onEnter(e, node)}
        onMouseLeave={onLeave}
        onClick={() => {
          if (hasChildren) onToggle(node.id);
        }}
      >
        <rect
          x={node.x}
          y={node.y}
          width={node.width}
          height={node.height}
          rx={rx}
          ry={rx}
          fill={`${node.color}18`}
          stroke={node.color}
          strokeWidth={1}
          className="transition-all duration-150"
        />
        <text
          x={node.x + node.width / 2}
          y={node.y + node.height / 2 + 1}
          textAnchor="middle"
          dominantBaseline="central"
          fill="var(--text-primary, #E5E5E5)"
          fontSize={12}
          fontWeight={500}
        >
          {node.label}
        </text>
        {/* Expand/collapse indicator */}
        {node.collapsed && (
          <text
            x={node.x + node.width - 10}
            y={node.y + node.height / 2 + 1}
            textAnchor="middle"
            dominantBaseline="central"
            fill={node.color}
            fontSize={10}
          >
            +
          </text>
        )}
      </g>,
    );
  }

  node.children.forEach((child) => {
    nodes.push(...collectNodes(child, onToggle, onEnter, onLeave));
  });

  return nodes;
}

// ---------- Main component ----------

export const PersonaGraph = React.memo(function PersonaGraph({
  personas = [],
  brandName,
  className,
}: PersonaGraphProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerWidth, setContainerWidth] = useState(600);
  const [collapsedSet, setCollapsedSet] = useState<Set<string>>(() => new Set());
  const [tooltip, setTooltip] = useState<TooltipData>({
    visible: false,
    x: 0,
    y: 0,
    title: '',
    type: 'brand',
    color: '#6366F1',
  });

  // Zoom / pan state
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const isPanningRef = useRef(false);
  const lastPanRef = useRef({ x: 0, y: 0 });

  // Observe container width
  useEffect(() => {
    if (!containerRef.current) return;
    const el = containerRef.current;
    const ro = new ResizeObserver((entries) => {
      const { width } = entries[0].contentRect;
      if (width > 0) setContainerWidth(width);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const tree = useMemo(() => buildTree(personas, brandName || '\u54c1\u724c'), [personas, brandName]);
  const { layoutRoot, totalWidth, totalHeight } = useMemo(
    () => layoutTree(tree, collapsedSet),
    [tree, collapsedSet],
  );

  const toggleCollapse = useCallback((id: string) => {
    setCollapsedSet((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const handleNodeEnter = useCallback((e: React.MouseEvent, node: LayoutNode) => {
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect) return;
    setTooltip({
      visible: true,
      x: e.clientX - rect.left + 14,
      y: e.clientY - rect.top - 14,
      title: node.fullLabel,
      subtitle: node.tooltipSubtitle,
      type: node.type,
      color: node.color,
    });
  }, []);

  const handleNodeLeave = useCallback(() => {
    setTooltip((prev) => ({ ...prev, visible: false }));
  }, []);

  // Zoom handler (wheel)
  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    setZoom((prev) => Math.min(2, Math.max(0.3, prev - e.deltaY * 0.001)));
  }, []);

  // Pan handlers
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    if (e.button !== 0) return;
    isPanningRef.current = true;
    lastPanRef.current = { x: e.clientX, y: e.clientY };
  }, []);

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (!isPanningRef.current) return;
    const dx = e.clientX - lastPanRef.current.x;
    const dy = e.clientY - lastPanRef.current.y;
    lastPanRef.current = { x: e.clientX, y: e.clientY };
    setPan((prev) => ({ x: prev.x + dx, y: prev.y + dy }));
  }, []);

  const handleMouseUp = useCallback(() => {
    isPanningRef.current = false;
  }, []);

  const viewHeight = Math.max(400, Math.min(totalHeight * zoom + 40, 600));

  const TYPE_LABELS: Record<string, string> = {
    brand: '\u76ee\u6807\u54c1\u724c',
    persona: '\u7528\u6237\u753b\u50cf',
    scenario: '\u4f7f\u7528\u573a\u666f',
    pain_point: '\u8425\u9500\u75db\u70b9',
  };

  if (personas.length === 0) {
    return (
      <div
        className={cn('rounded-xl p-8', className)}
        style={{ backgroundColor: 'var(--bg-secondary, #0D0D0D)', border: '1px solid var(--border-default, #262626)' }}
      >
        <div className="flex flex-col items-center justify-center h-[400px] text-center">
          <div
            className="w-16 h-16 rounded-2xl flex items-center justify-center mb-4"
            style={{ backgroundColor: 'var(--bg-elevated, #1A1A1A)', border: '1px solid var(--border-strong, #333333)' }}
          >
            <svg className="w-8 h-8" style={{ color: 'var(--text-muted, #737373)' }} fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
            </svg>
          </div>
          <h3 className="text-lg font-medium mb-2" style={{ color: 'var(--text-tertiary, #A3A3A3)' }}>
            等待画像数据
          </h3>
          <p className="text-sm max-w-[280px]" style={{ color: 'var(--text-muted, #737373)' }}>
            A2 用户画像生成完成后，将在此处显示用户画像图谱
          </p>
        </div>
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn('rounded-xl overflow-hidden relative', className)}
      style={{ backgroundColor: 'var(--bg-secondary, #0D0D0D)', border: '1px solid var(--border-default, #262626)' }}
    >
      {/* Header */}
      <div className="px-4 py-3" style={{ borderBottom: '1px solid var(--border-default, #262626)' }}>
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-base font-semibold" style={{ color: 'var(--text-primary, #E5E5E5)' }}>
              用户画像关系图谱
            </h3>
            <p className="text-sm mt-0.5" style={{ color: 'var(--text-secondary, #A3A3A3)' }}>
              {personas.length} 个用户画像 · 包含场景和痛点分析 · 点击节点可展开/收起
            </p>
          </div>
          <div className="flex items-center gap-3 text-xs">
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-[#6366F1]" />
              <span style={{ color: 'var(--text-secondary, #A3A3A3)' }}>品牌</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-[#EF4444]" />
              <span style={{ color: 'var(--text-secondary, #A3A3A3)' }}>核心</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-[#F59E0B]" />
              <span style={{ color: 'var(--text-secondary, #A3A3A3)' }}>增长</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-[#8B5CF6]" />
              <span style={{ color: 'var(--text-secondary, #A3A3A3)' }}>场景</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-[#EC4899]" />
              <span style={{ color: 'var(--text-secondary, #A3A3A3)' }}>痛点</span>
            </div>
          </div>
        </div>
      </div>

      {/* SVG Tree Graph */}
      <div
        ref={containerRef}
        className="w-full overflow-hidden select-none"
        style={{ height: viewHeight, cursor: isPanningRef.current ? 'grabbing' : 'grab' }}
        onWheel={handleWheel}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
      >
        <svg
          width={containerWidth}
          height={viewHeight}
          className="select-none"
        >
          <g transform={`translate(${pan.x}, ${pan.y}) scale(${zoom})`}>
            {/* Edges first (below nodes) */}
            {collectEdges(layoutRoot)}
            {/* Nodes */}
            {collectNodes(layoutRoot, toggleCollapse, handleNodeEnter, handleNodeLeave)}
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
            style={{
              left: Math.min(tooltip.x, containerWidth - 220),
              top: Math.max(tooltip.y, 8),
            }}
          >
            <div
              className="rounded-lg px-3.5 py-2.5 shadow-lg min-w-[160px] max-w-[260px]"
              style={{ backgroundColor: 'var(--bg-elevated, #1A1A1A)', border: '1px solid var(--border-strong, #333333)' }}
            >
              <div className="flex items-center gap-2 mb-1">
                <span className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ backgroundColor: tooltip.color }} />
                <span className="text-sm font-semibold" style={{ color: 'var(--text-primary, #E5E5E5)' }}>
                  {tooltip.title}
                </span>
              </div>
              <div className="text-xs" style={{ color: 'var(--text-secondary, #A3A3A3)' }}>
                {TYPE_LABELS[tooltip.type] || tooltip.type}
              </div>
              {tooltip.subtitle && (
                <div className="text-xs mt-1 line-clamp-3" style={{ color: 'var(--text-secondary, #A3A3A3)' }}>
                  {tooltip.subtitle}
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
});

PersonaGraph.displayName = 'PersonaGraph';

export default PersonaGraph;
