import { Archive, ExternalLink, FileText, FolderOpen } from 'lucide-react';
import styles from './BrandSpace.module.css';
import type { ArtifactRef } from '@/types/brandSpace';

interface AssetsViewProps {
  artifacts: ArtifactRef[];
}

function classNames(...classes: Array<string | false | undefined>) {
  return classes.filter(Boolean).join(' ');
}

const artifactTypeLabels: Record<string, string> = {
  entity_lexicon: '实体词表',
  question_set: '问题集',
  raw_answers: '原始答案',
  parsed_answers: '标准化回答',
  entity_relation_set: '实体关系集',
  graph_patch_set: '图谱补丁集',
  graph_update: '图谱更新',
  report: '报告',
};

export function AssetsView({ artifacts }: AssetsViewProps) {
  const groups = artifacts.reduce<Record<string, ArtifactRef[]>>((acc, artifact) => {
    acc[artifact.type] = acc[artifact.type] ? [...acc[artifact.type], artifact] : [artifact];
    return acc;
  }, {});

  return (
    <div className="space-y-4">
      <section className={classNames(styles.surface, 'rounded-xl p-5')}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs font-medium uppercase text-[var(--text-tertiary)]">资产</p>
            <h1 className="mt-1 text-xl font-semibold text-[var(--text-primary)]">运行产物可追溯查看</h1>
          </div>
          <span className="rounded-lg border px-3 py-2 text-xs font-medium text-[var(--text-secondary)]" style={{ borderColor: 'var(--border-subtle)' }}>
            {artifacts.length} 个资产
          </span>
        </div>
      </section>

      <div className="grid gap-4 xl:grid-cols-2">
        {Object.entries(groups).map(([type, items]) => (
          <section key={type} className={classNames(styles.surface, 'rounded-xl p-4')}>
            <div className="mb-3 flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <FolderOpen className="h-4 w-4 text-[var(--brand-primary)]" />
                <h2 className="text-sm font-semibold text-[var(--text-primary)]">{artifactTypeLabels[type] ?? type}</h2>
              </div>
              <span className="text-xs text-[var(--text-tertiary)]">{items.length}</span>
            </div>

            <div className="space-y-3">
              {items.map((artifact) => (
                <article key={artifact.id} className="rounded-xl border p-3" style={{ borderColor: 'var(--border-subtle)', background: 'var(--bg-elevated)' }}>
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex min-w-0 items-start gap-3">
                      <span className="mt-0.5 flex h-8 w-8 items-center justify-center rounded-lg bg-[var(--brand-bg)] text-[var(--brand-text)]">
                        <FileText className="h-4 w-4" />
                      </span>
                      <div className="min-w-0">
                        <h3 className="text-sm font-semibold text-[var(--text-primary)]">{artifact.label}</h3>
                        <p className="mt-1 break-all text-xs leading-5 text-[var(--text-tertiary)]">{artifact.path}</p>
                      </div>
                    </div>
                    <button type="button" className="rounded-lg p-2 text-[var(--text-tertiary)] hover:bg-[var(--bg-tertiary)]" title="打开资产">
                      <ExternalLink className="h-4 w-4" />
                    </button>
                  </div>
                  <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-[var(--text-secondary)]">
                    <span className="rounded-md bg-[var(--bg-tertiary)] px-2 py-1">{artifact.rowCount ?? 1} 行</span>
                    <span className="rounded-md bg-[var(--bg-tertiary)] px-2 py-1">{artifact.createdAt}</span>
                    {artifact.linkedNodeId ? <span className="rounded-md bg-[var(--bg-tertiary)] px-2 py-1">{artifact.linkedNodeId}</span> : null}
                  </div>
                </article>
              ))}
            </div>
          </section>
        ))}
      </div>

      <section className={classNames(styles.surface, 'rounded-xl p-4')}>
        <div className="flex items-start gap-3">
          <Archive className="mt-0.5 h-4 w-4 text-[var(--brand-primary)]" />
          <p className="text-sm leading-6 text-[var(--text-secondary)]">
            资产是辅助证据面。用户可以查看原始答案、结构化输出、图谱补丁和报告，但主交付仍然是图谱状态更新。
          </p>
        </div>
      </section>
    </div>
  );
}
