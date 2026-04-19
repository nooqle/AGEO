'use client';

import { RiFileTextLine, RiBarChartBoxLine, RiTableLine, RiGroupLine, RiArrowRightLine, RiRobot2Line } from '@remixicon/react';
import { OutputCard as OutputCardType } from '@/types/message';
import type { CanvasContent, CanvasContentDataMap } from '@/types/canvas';
import { useCanvasStore } from '@/stores/canvasStore';
import { cn } from '@/lib/cn';

interface OutputCardProps {
  card: OutputCardType;
}

const typeConfig = {
  workflow: {
    icon: RiFileTextLine,
    label: '流程可视化',
    colors: {
      bg: 'bg-[var(--bg-elevated)]',
      border: 'border-[var(--border-subtle)]',
      hoverBorder: 'hover:border-violet-500/60',
      icon: 'text-violet-300',
      title: 'text-[var(--text-primary)]',
      label: 'text-violet-300',
      glow: 'group-hover:shadow-[0_0_0_1px_rgba(124,58,237,0.35),0_10px_30px_rgba(124,58,237,0.2)]',
    },
  },
  questionList: {
    icon: RiFileTextLine,
    label: '问题列表',
    colors: {
      bg: 'bg-[var(--bg-elevated)]',
      border: 'border-[var(--border-subtle)]',
      hoverBorder: 'hover:border-sky-500/60',
      icon: 'text-sky-300',
      title: 'text-[var(--text-primary)]',
      label: 'text-sky-300',
      glow: 'group-hover:shadow-[0_0_0_1px_rgba(56,189,248,0.35),0_10px_30px_rgba(14,165,233,0.2)]',
    },
  },
  fetchResults: {
    icon: RiFileTextLine,
    label: '抓取结果',
    colors: {
      bg: 'bg-[var(--bg-elevated)]',
      border: 'border-[var(--border-subtle)]',
      hoverBorder: 'hover:border-teal-500/60',
      icon: 'text-teal-300',
      title: 'text-[var(--text-primary)]',
      label: 'text-teal-300',
      glow: 'group-hover:shadow-[0_0_0_1px_rgba(20,184,166,0.35),0_10px_30px_rgba(13,148,136,0.2)]',
    },
  },
  report: {
    icon: RiFileTextLine,
    label: '分析报告',
    colors: {
      bg: 'bg-[var(--bg-elevated)]',
      border: 'border-[var(--border-subtle)]',
      hoverBorder: 'hover:border-indigo-500/60',
      icon: 'text-indigo-300',
      title: 'text-[var(--text-primary)]',
      label: 'text-indigo-300',
      glow: 'group-hover:shadow-[0_0_0_1px_rgba(99,102,241,0.35),0_10px_30px_rgba(79,70,229,0.2)]',
    },
  },
  chart: {
    icon: RiBarChartBoxLine,
    label: '数据图表',
    colors: {
      bg: 'bg-[var(--bg-elevated)]',
      border: 'border-[var(--border-subtle)]',
      hoverBorder: 'hover:border-emerald-500/60',
      icon: 'text-emerald-300',
      title: 'text-[var(--text-primary)]',
      label: 'text-emerald-300',
      glow: 'group-hover:shadow-[0_0_0_1px_rgba(16,185,129,0.35),0_10px_30px_rgba(5,150,105,0.2)]',
    },
  },
  dataTable: {
    icon: RiTableLine,
    label: '数据表格',
    colors: {
      bg: 'bg-[var(--bg-elevated)]',
      border: 'border-[var(--border-subtle)]',
      hoverBorder: 'hover:border-blue-500/60',
      icon: 'text-blue-300',
      title: 'text-[var(--text-primary)]',
      label: 'text-blue-300',
      glow: 'group-hover:shadow-[0_0_0_1px_rgba(59,130,246,0.35),0_10px_30px_rgba(37,99,235,0.2)]',
    },
  },
  selection: {
    icon: RiGroupLine,
    label: '选择确认',
    colors: {
      bg: 'bg-[var(--bg-elevated)]',
      border: 'border-[var(--border-subtle)]',
      hoverBorder: 'hover:border-purple-500/60',
      icon: 'text-purple-300',
      title: 'text-[var(--text-primary)]',
      label: 'text-purple-300',
      glow: 'group-hover:shadow-[0_0_0_1px_rgba(168,85,247,0.35),0_10px_30px_rgba(147,51,234,0.2)]',
    },
  },
};

export function OutputCard({ card }: OutputCardProps) {
  const { openCanvas, setActiveContentById, contents } = useCanvasStore();
  const isSiteConfidenceCard = (
    (card.id || '').toLowerCase().includes('site_confidence') ||
    (card.title || '').includes('官网 AI 友好度')
  );
  const config = isSiteConfidenceCard
    ? {
        ...typeConfig.report,
        icon: RiRobot2Line,
        label: '官网',
        colors: {
          ...typeConfig.report.colors,
          hoverBorder: 'hover:border-sky-500/60',
          icon: 'text-sky-300',
          label: 'text-sky-300',
          glow: 'group-hover:shadow-[0_0_0_1px_rgba(56,189,248,0.35),0_10px_30px_rgba(14,165,233,0.2)]',
        },
      }
    : typeConfig[card.type as keyof typeof typeConfig] || typeConfig.report;
  const Icon = config.icon;
  const displayTitle = isSiteConfidenceCard ? '官网 AI 友好度' : card.title;

  const handleClick = () => {
    const existing = contents.find((content) => content.id === card.id);
    if (existing) {
      setActiveContentById(existing.id);
      openCanvas();
      return;
    }

    const previewData = {
      description: card.preview.description,
      metrics: card.preview.metrics,
      itemCount: card.preview.itemCount,
    } as CanvasContentDataMap['report'];
    const content = {
      id: card.id,
      type: card.type,
      title: displayTitle,
      data: previewData,
      createdAt: new Date(),
      relatedMessageId: '',
      versions: [],
      currentVersionIndex: -1,
    };
    openCanvas(content as CanvasContent);
  };

  return (
    <button
      onClick={handleClick}
      className={cn(
        'w-full text-left rounded-xl border p-4 transition-all',
        'cursor-pointer group relative',
        'hover:-translate-y-0.5 active:translate-y-0',
        'shadow-[0_0_0_1px_rgba(255,255,255,0.02)]',
        config.colors.bg,
        config.colors.border,
        config.colors.hoverBorder,
        config.colors.glow
      )}
    >
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className={cn('p-1.5 rounded-lg bg-[var(--bg-tertiary)] border border-[var(--border-subtle)]', config.colors.icon)}>
            <Icon className="w-4 h-4" />
          </div>
          <div>
            <div className={cn('font-medium', config.colors.title)}>
              {displayTitle}
            </div>
            <div className={cn('text-xs', config.colors.label)}>{config.label}</div>
          </div>
        </div>
        <RiArrowRightLine className="w-4 h-4 text-[var(--text-tertiary)] group-hover:translate-x-1 transition-transform" />
      </div>

      {card.preview?.metrics && (
        <div className="grid grid-cols-3 gap-2">
          {Object.entries(card.preview.metrics).slice(0, 3).map(([key, value]) => (
            <div key={key} className="bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-lg px-2 py-1.5">
              <div className="text-xs text-[var(--text-secondary)]">{key}</div>
              <div className="font-medium text-[var(--text-primary)] truncate">{String(value)}</div>
            </div>
          ))}
        </div>
      )}

      {card.preview?.description && (
        <p className="text-sm text-[var(--text-secondary)] mt-2 line-clamp-2">
          {card.preview.description}
        </p>
      )}
    </button>
  );
}


