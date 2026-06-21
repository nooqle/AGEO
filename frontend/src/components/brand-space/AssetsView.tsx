import { useMemo } from 'react';
import {
  Archive,
  ArrowRight,
  Database,
  Download,
  ExternalLink,
  FileJson,
  FileText,
  Filter,
  FolderOpen,
  Loader2,
  X,
} from 'lucide-react';
import styles from './BrandSpace.module.css';
import type {
  ArtifactDetail,
  ArtifactPreview,
  ArtifactRef,
  ArtifactTraceLink,
  AssetListSummary,
  PaginationInfo,
} from '@/types/brandSpace';

interface AssetsViewProps {
  artifacts: ArtifactRef[];
  detail?: ArtifactDetail | null;
  summary?: AssetListSummary | null;
  pagination?: PaginationInfo | null;
  isDetailLoading?: boolean;
  isLoadingAssets?: boolean;
  selectedArtifactId?: string | null;
  selectedType?: string;
  onTypeChange?: (artifactType: string) => void;
  onLoadMore?: () => void;
  onOpenArtifact?: (artifact: ArtifactRef) => void;
  onCloseDetail?: () => void;
  onTraceTarget?: (link: ArtifactTraceLink) => void;
  onDownloadArtifact?: (artifact: ArtifactRef) => void;
  downloadingArtifactIds?: string[];
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
  review_queue: '审阅队列',
  graph_update: '图谱更新',
  report: '报告',
};

const traceKindLabels: Record<string, string> = {
  board_run: '画布',
  node_run: '节点',
  graph_update: '图谱更新',
  report_version: '报告',
};

function artifactStableId(artifact: ArtifactRef) {
  return artifact.artifactId ?? artifact.id;
}

function formatValue(value: unknown) {
  if (value === null || value === undefined || value === '') return '-';
  if (typeof value === 'number') return new Intl.NumberFormat('zh-CN').format(value);
  return String(value);
}

function formatDate(value: string) {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function formatBytes(value: number | null | undefined) {
  if (!value || value <= 0) return '-';
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

function accessReasonLabel(reason?: string | null) {
  const labels: Record<string, string> = {
    object_not_materialized: '对象尚未物化',
    object_is_directory: '对象为目录',
    missing_object_key: '缺少对象 key',
    external_url_not_supported: '暂不支持外部 URL',
    absolute_path_not_allowed: '不允许绝对路径',
    unsafe_or_unsupported_object_key: '对象 key 不受支持',
    object_key_escapes_storage_root: '对象 key 越界',
  };
  return reason ? labels[reason] ?? reason : '可下载';
}

function PreviewBlock({ preview }: { preview?: ArtifactPreview }) {
  if (!preview) {
    return (
      <div className={styles.assetPreviewEmpty}>
        <FileText className="h-5 w-5" />
        <p>选择一个资产后显示安全预览。</p>
      </div>
    );
  }

  if (preview.kind === 'table') {
    const columns = preview.columns ?? [];
    const rows = preview.rows ?? [];
    return (
      <div className={styles.assetPreview}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3>{preview.title}</h3>
          <span>{formatValue(preview.rowCount)} 行{preview.truncated ? ' · 已截断' : ''}</span>
        </div>
        <div className={styles.assetTableWrap}>
          <table className={styles.assetTable}>
            <thead>
              <tr>
                {columns.map((column) => (
                  <th key={column.key}>{column.label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.length ? (
                rows.map((row, rowIndex) => (
                  <tr key={`row-${rowIndex}`}>
                    {columns.map((column) => (
                      <td key={column.key}>{formatValue(row[column.key])}</td>
                    ))}
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={Math.max(columns.length, 1)}>没有可内联预览的行。</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  if (preview.kind === 'json') {
    return (
      <div className={styles.assetPreview}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3>{preview.title}</h3>
          <span>{preview.truncated ? '已截断' : 'JSON'}</span>
        </div>
        <pre>{JSON.stringify(preview.json ?? {}, null, 2)}</pre>
      </div>
    );
  }

  if (preview.kind === 'jsonl') {
    const lines = preview.lines ?? [];
    return (
      <div className={styles.assetPreview}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3>{preview.title}</h3>
          <span>{formatValue(preview.rowCount)} 行{preview.truncated ? ' · 已截断' : ''}</span>
        </div>
        {lines.length ? (
          <pre>{lines.join('\n')}</pre>
        ) : (
          <p className="text-sm leading-7 text-[var(--text-secondary)]">
            {preview.emptySummary ?? '没有可内联预览的 JSONL 行。'}
          </p>
        )}
      </div>
    );
  }

  return (
    <div className={styles.assetPreview}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3>{preview.title}</h3>
        <span>{formatValue(preview.rowCount)} 行</span>
      </div>
      <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)]">{preview.summary}</p>
      {preview.items?.length ? (
        <div className={styles.assetMetaGrid}>
          {preview.items.map((item) => (
            <div key={item.label}>
              <p>{item.label}</p>
              <strong>{formatValue(item.value)}</strong>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function AssetsView({
  artifacts,
  detail,
  summary,
  pagination,
  isDetailLoading = false,
  isLoadingAssets = false,
  selectedArtifactId,
  selectedType = 'all',
  onTypeChange,
  onLoadMore,
  onOpenArtifact,
  onCloseDetail,
  onTraceTarget,
  onDownloadArtifact,
  downloadingArtifactIds = [],
}: AssetsViewProps) {
  const typeOptions = useMemo(() => {
    const counts = summary?.by_type ?? artifacts.reduce<Record<string, number>>((acc, artifact) => {
      acc[artifact.type] = (acc[artifact.type] ?? 0) + 1;
      return acc;
    }, {});
    return [
      { type: 'all', label: '全部资产', count: summary?.total ?? artifacts.length },
      ...Object.entries(counts).map(([type, count]) => ({
        type,
        label: artifactTypeLabels[type] ?? type,
        count,
      })),
    ];
  }, [artifacts, summary]);
  const filteredArtifacts = artifacts;
  const activeDetailId = detail ? artifactStableId(detail.artifact) : selectedArtifactId;
  const displayedCount = pagination ? Math.min(pagination.offset + artifacts.length, pagination.total) : filteredArtifacts.length;
  const totalCount = pagination?.total ?? summary?.total ?? filteredArtifacts.length;
  const activeDownloadId = detail?.artifact ? artifactStableId(detail.artifact) : null;
  const isDownloadingActive = activeDownloadId ? downloadingArtifactIds.includes(activeDownloadId) : false;
  const canDownloadActive = Boolean(detail?.access?.available && detail.access.downloadUrl);

  return (
    <div className="space-y-4">
      <section className={classNames(styles.surface, 'rounded-xl p-5')}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs font-medium uppercase text-[var(--text-tertiary)]">资产</p>
            <h1 className="mt-1 text-xl font-semibold text-[var(--text-primary)]">运行产物可追溯查看</h1>
          </div>
          <span className="rounded-lg border px-3 py-2 text-xs font-medium text-[var(--text-secondary)]" style={{ borderColor: 'var(--border-subtle)' }}>
            {displayedCount} / {totalCount} 个资产
          </span>
        </div>
      </section>

      <div className={styles.assetToolbar}>
        <div className="flex items-center gap-2 text-xs font-medium text-[var(--text-secondary)]">
          <Filter className="h-4 w-4" />
          类型筛选
        </div>
        <div className="flex flex-wrap gap-2">
          {typeOptions.map((option) => (
            <button
              key={option.type}
              type="button"
              onClick={() => onTypeChange?.(option.type)}
              className={classNames(
                styles.assetTypeButton,
                selectedType === option.type && styles.assetTypeButtonActive,
              )}
              aria-pressed={selectedType === option.type}
              aria-label={`筛选资产类型：${option.label}`}
            >
              {option.label}
              <span>{option.count}</span>
            </button>
          ))}
        </div>
      </div>

      <div className={classNames(styles.assetLayout, detail || isDetailLoading ? styles.assetLayoutWithDrawer : undefined)}>
        <section className={styles.assetList}>
          {filteredArtifacts.length ? (
            filteredArtifacts.map((artifact) => {
              const active = activeDetailId === artifactStableId(artifact);
              return (
                <article
                  key={artifact.id}
                  className={classNames(styles.assetCard, active && styles.assetCardActive)}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex min-w-0 items-start gap-3">
                      <span className={styles.assetIcon}>
                        {artifact.type.includes('json') || artifact.mimeType?.includes('json') ? (
                          <FileJson className="h-4 w-4" />
                        ) : artifact.type.includes('answer') ? (
                          <Database className="h-4 w-4" />
                        ) : (
                          <FileText className="h-4 w-4" />
                        )}
                      </span>
                      <div className="min-w-0">
                        <p className="text-[11px] font-semibold text-[var(--brand-text)]">
                          {artifactTypeLabels[artifact.type] ?? artifact.type}
                        </p>
                        <h3>{artifact.label}</h3>
                        <p className="mt-1 break-all text-xs leading-5 text-[var(--text-tertiary)]">{artifact.path}</p>
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => onOpenArtifact?.(artifact)}
                      className={styles.assetOpenButton}
                      title="打开资产详情"
                      aria-label={`打开资产详情：${artifact.label}`}
                    >
                      {isDetailLoading && active ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <ExternalLink className="h-4 w-4" />
                      )}
                    </button>
                  </div>
                  <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-[var(--text-secondary)]">
                    <span className={styles.assetChip}>{formatValue(artifact.rowCount ?? 1)} 行</span>
                    <span className={styles.assetChip}>{formatDate(artifact.createdAt)}</span>
                    {artifact.linkedNodeId ? <span className={styles.assetChip}>{artifact.linkedNodeId}</span> : null}
                  </div>
                </article>
              );
            })
          ) : (
            <div className={styles.assetEmpty}>
              <FolderOpen className="h-5 w-5" />
              <p>当前筛选下没有资产。</p>
            </div>
          )}
        </section>

        {detail || isDetailLoading ? (
          <aside className={styles.assetDrawer}>
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-xs font-medium uppercase text-[var(--text-tertiary)]">资产详情</p>
                <h2>{detail?.artifact.label ?? '加载中'}</h2>
              </div>
              <button type="button" onClick={onCloseDetail} className={styles.assetOpenButton} title="关闭详情" aria-label="关闭资产详情">
                <X className="h-4 w-4" />
              </button>
            </div>

            {isDetailLoading && !detail ? (
              <div className={styles.assetPreviewEmpty}>
                <Loader2 className="h-5 w-5 animate-spin" />
                <p>正在读取资产详情...</p>
              </div>
            ) : (
              <>
                <div className={styles.assetMetaGrid}>
                  <div>
                    <p>类型</p>
                    <strong>{detail ? artifactTypeLabels[detail.artifact.type] ?? detail.artifact.type : '-'}</strong>
                  </div>
                  <div>
                    <p>MIME</p>
                    <strong>{detail?.artifact.mimeType ?? '-'}</strong>
                  </div>
                  <div>
                    <p>记录数</p>
                    <strong>{formatValue(detail?.artifact.rowCount)}</strong>
                  </div>
                  <div>
                    <p>来源节点</p>
                    <strong>{detail?.artifact.linkedNodeId ?? '-'}</strong>
                  </div>
                </div>

                {detail?.access ? (
                  <section className={styles.assetAccessPanel}>
                    <div>
                      <p>对象存储</p>
                      <strong>{accessReasonLabel(detail.access.reason)}</strong>
                    </div>
                    <div>
                      <p>对象 key</p>
                      <strong>{detail.access.objectKey ?? '-'}</strong>
                    </div>
                    <div>
                      <p>大小</p>
                      <strong>{formatBytes(detail.access.sizeBytes)}</strong>
                    </div>
                    <button
                      type="button"
                      onClick={() => detail?.artifact && onDownloadArtifact?.(detail.artifact)}
                      disabled={!canDownloadActive || isDownloadingActive}
                      className={styles.assetDownloadButton}
                      aria-label={`下载资产对象：${detail.artifact.label}`}
                    >
                      {isDownloadingActive ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Download className="h-4 w-4" />
                      )}
                      下载对象
                    </button>
                  </section>
                ) : null}

                <PreviewBlock preview={detail?.preview} />

                <section className={styles.tracePanel}>
                  <div className="flex items-center gap-2">
                    <Archive className="h-4 w-4 text-[var(--brand-primary)]" />
                    <h3>追溯链</h3>
                  </div>
                  <div className="mt-3 space-y-2">
                    {detail?.trace.links.length ? (
                      detail.trace.links.map((link) => (
                        <button
                          key={`${link.kind}-${link.id}`}
                          type="button"
                          onClick={() => onTraceTarget?.(link)}
                          className={styles.traceLink}
                          aria-label={`跳转到${traceKindLabels[link.kind] ?? link.kind}：${link.label}`}
                        >
                          <span>{traceKindLabels[link.kind] ?? link.kind}</span>
                          <strong>{link.label}</strong>
                          <ArrowRight className="h-4 w-4" />
                        </button>
                      ))
                    ) : (
                      <p className="text-sm leading-7 text-[var(--text-secondary)]">
                        该资产还没有可跳转的上游或下游对象。
                      </p>
                    )}
                  </div>
                </section>
              </>
            )}
          </aside>
        ) : null}
      </div>

      {pagination?.has_more ? (
        <div className="flex justify-center">
          <button
            type="button"
            onClick={onLoadMore}
            disabled={isLoadingAssets}
            className={styles.assetLoadMoreButton}
            aria-label="加载更多资产"
          >
            {isLoadingAssets ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                正在加载
              </>
            ) : (
              <>
                加载更多资产
                <span>{displayedCount} / {totalCount}</span>
              </>
            )}
          </button>
        </div>
      ) : null}

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
