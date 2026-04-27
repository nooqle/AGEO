'use client';

import { RiFileTextLine, RiBarChartBoxLine, RiTableLine, RiGroupLine, RiArrowRightLine } from '@remixicon/react';
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
      bg: 'bg-[var(--bg-report)]',
      border: 'border-[var(--border-subtle)]',
      hoverBorder: 'hover:border-[var(--brand-border)]',
      icon: 'text-[var(--evidence-secondary)]',
      title: 'text-[var(--text-primary)]',
      label: 'text-[var(--evidence-secondary)]',
    },
  },
  questionList: {
    icon: RiFileTextLine,
    label: '问题列表',
    colors: {
      bg: 'bg-[var(--bg-report)]',
      border: 'border-[var(--border-subtle)]',
      hoverBorder: 'hover:border-[var(--brand-border)]',
      icon: 'text-[var(--evidence-source)]',
      title: 'text-[var(--text-primary)]',
      label: 'text-[var(--evidence-source)]',
    },
  },
  fetchResults: {
    icon: RiFileTextLine,
    label: '抓取结果',
    colors: {
      bg: 'bg-[var(--bg-report)]',
      border: 'border-[var(--border-subtle)]',
      hoverBorder: 'hover:border-[var(--brand-border)]',
      icon: 'text-[var(--evidence-primary)]',
      title: 'text-[var(--text-primary)]',
      label: 'text-[var(--evidence-primary)]',
    },
  },
  report: {
    icon: RiFileTextLine,
    label: '分析报告',
    colors: {
      bg: 'bg-[var(--bg-report)]',
      border: 'border-[var(--border-subtle)]',
      hoverBorder: 'hover:border-[var(--brand-border)]',
      icon: 'text-[var(--brand-text)]',
      title: 'text-[var(--text-primary)]',
      label: 'text-[var(--brand-text)]',
    },
  },
  chart: {
    icon: RiBarChartBoxLine,
    label: '数据图表',
    colors: {
      bg: 'bg-[var(--bg-report)]',
      border: 'border-[var(--border-subtle)]',
      hoverBorder: 'hover:border-[var(--brand-border)]',
      icon: 'text-[var(--success)]',
      title: 'text-[var(--text-primary)]',
      label: 'text-[var(--success)]',
    },
  },
  dataTable: {
    icon: RiTableLine,
    label: '数据表格',
    colors: {
      bg: 'bg-[var(--bg-report)]',
      border: 'border-[var(--border-subtle)]',
      hoverBorder: 'hover:border-[var(--brand-border)]',
      icon: 'text-[var(--info)]',
      title: 'text-[var(--text-primary)]',
      label: 'text-[var(--info)]',
    },
  },
  selection: {
    icon: RiGroupLine,
    label: '选择确认',
    colors: {
      bg: 'bg-[var(--bg-report)]',
      border: 'border-[var(--border-subtle)]',
      hoverBorder: 'hover:border-[var(--brand-border)]',
      icon: 'text-[var(--evidence-secondary)]',
      title: 'text-[var(--text-primary)]',
      label: 'text-[var(--evidence-secondary)]',
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
        icon: RiFileTextLine,
        label: '官网',
        colors: {
          ...typeConfig.report.colors,
          icon: 'text-[var(--evidence-source)]',
          label: 'text-[var(--evidence-source)]',
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
      sourceOutputId: card.outputId,
      isHydrationStub: true,
      versions: [],
      currentVersionIndex: -1,
    };
    openCanvas(content as CanvasContent);
  };

  return (
    <button
      onClick={handleClick}
      className={cn(
        'w-full text-left rounded-[14px] border p-4 transition-all',
        'cursor-pointer group relative',
        'hover:-translate-y-0.5 active:translate-y-0',
        'hover:shadow-[var(--shadow-md)]',
        config.colors.bg,
        config.colors.border,
        config.colors.hoverBorder
      )}
    >
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className={cn('p-1.5 rounded-md bg-[var(--bg-report-muted)] border border-[var(--border-subtle)]', config.colors.icon)}>
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
            <div key={key} className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-report-muted)] px-2 py-1.5">
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


