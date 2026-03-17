'use client';

import { useState, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  RiDownloadLine,
  RiCloseLine,
  RiFileCopyLine,
  RiShareLine,
  RiCheckLine,
  RiFileTextLine,
  RiTableLine,
  RiExpandDiagonalLine,
  RiCollapseDiagonalLine,
  RiArrowDownSLine,
  RiChatForwardLine,
  RiHistoryLine,
  RiShieldCheckLine,
  RiLinkM,
  RiSparklingLine,
  RiLoader4Line,
} from '@remixicon/react';
import { CanvasContent } from '@/types/canvas';
import { useCanvasStore } from '@/stores/canvasStore';
import { useConversationStore } from '@/stores/conversationStore';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/cn';
import { modalScrimClassName } from '@/components/ui/modal-scrim';
import { toast } from '@/components/ui/toast';
import {
  exportCanvasContent,
  getCanvasContentText,
  getCanvasExportLabel,
  isCanvasContentExportable,
  type SupportedExportFormat,
} from '@/lib/canvasExport';

interface CanvasHeaderProps {
  content: CanvasContent;
}

function formatTimestamp(ts: string): string {
  try {
    const d = new Date(ts);
    return d.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })
      + ' ' + d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
  } catch {
    return ts;
  }
}

export function CanvasHeader({ content }: CanvasHeaderProps) {
  const { mode, setMode, closeCanvas, setContentVersion, contents } = useCanvasStore();
  const [copied, setCopied] = useState(false);
  const [exportMenuOpen, setExportMenuOpen] = useState(false);
  const [versionMenuOpen, setVersionMenuOpen] = useState(false);
  const [artifactInputOpen, setArtifactInputOpen] = useState(false);
  const [artifactInputValue, setArtifactInputValue] = useState('');
  const [exportingFormat, setExportingFormat] = useState<SupportedExportFormat | null>(null);
  const sendArtifactAction = useConversationStore((state) => state.wsArtifactAction);

  const versions = useMemo(() => content.versions || [], [content.versions]);
  const hasVersions = versions.length > 0;
  const isViewingHistory = content.currentVersionIndex >= 0;
  const effectiveContent = useMemo(() => {
    if (isViewingHistory && content.currentVersionIndex < versions.length) {
      return {
        ...content,
        data: versions[content.currentVersionIndex].data as CanvasContent['data'],
      } as CanvasContent;
    }
    return content;
  }, [content, isViewingHistory, versions]);
  const isConfidenceSignal = effectiveContent.type === 'report' && effectiveContent.data?.report_kind === 'confidence_signal';
  const confidenceComposer = isConfidenceSignal ? effectiveContent.data?.composer : undefined;
  const confidenceStatus = isConfidenceSignal ? effectiveContent.data?.status : undefined;
  const isArtifactActionRunning = confidenceStatus?.phase === 'running';
  const exportable = useMemo(() => isCanvasContentExportable(content), [content]);
  const exportLabel = useMemo(() => getCanvasExportLabel(content), [content]);

  // Determine which linkedMessageId to use for "jump to conversation"
  const activeLinkedMessageId = useMemo(() => {
    if (isViewingHistory && content.currentVersionIndex < versions.length) {
      return versions[content.currentVersionIndex].linkedMessageId;
    }
    return content.linkedMessageId;
  }, [isViewingHistory, content.currentVersionIndex, versions, content.linkedMessageId]);

  const toggleMode = () => {
    setMode(mode === 'split' ? 'focused' : 'split');
  };

  const handleVersionSelect = (index: number) => {
    setContentVersion(content.id, index);
    setVersionMenuOpen(false);
  };

  // Clear hasNewVersion when opening version menu
  const handleVersionMenuToggle = () => {
    if (!versionMenuOpen && content.hasNewVersion) {
      // Clear the NEW badge when user opens version selector
      const idx = contents.findIndex(c => c.id === content.id);
      if (idx !== -1) {
        useCanvasStore.setState((state) => {
          const newContents = [...state.contents];
          newContents[idx] = { ...newContents[idx], hasNewVersion: false } as CanvasContent;
          return { contents: newContents };
        });
      }
    }
    setVersionMenuOpen(!versionMenuOpen);
  };

  const handleJumpToConversation = () => {
    if (!activeLinkedMessageId) return;
    // Dispatch custom event for ChatPanel to handle scrolling
    window.dispatchEvent(new CustomEvent('scroll-to-message', {
      detail: { messageId: activeLinkedMessageId },
    }));
  };

  const handleArtifactSubmit = () => {
    const rawInput = artifactInputValue.trim();
    if (!sendArtifactAction || !rawInput || !isConfidenceSignal || isArtifactActionRunning) {
      if (!sendArtifactAction && isConfidenceSignal) {
        toast.error('当前连接不可用，请稍后重试');
      }
      return;
    }
    sendArtifactAction(content.id, 'extra_evaluate', { raw_input: rawInput });
    toast.info('已开始额外评估，结果会写回当前报告');
    setArtifactInputValue('');
    setArtifactInputOpen(false);
  };

  // Copy content to clipboard
  const handleCopy = async () => {
    try {
      let contentText: string;
      const d = effectiveContent.data as Record<string, unknown>;

      if (exportable) {
        contentText = getCanvasContentText(content, contents);
      } else if (effectiveContent.type === 'dataTable') {
        const cols = Array.isArray(d.columns) ? (d.columns as Array<Record<string, string>>) : [];
        const rows = Array.isArray(d.rows) ? (d.rows as Array<Record<string, unknown>>) : [];
        const header = cols.map((c) => c.label || c.key || '').join('\t');
        const body = rows.map((row) =>
          cols.map((c) => {
            const val = row[c.key || ''];
            return val != null ? String(val) : '';
          }).join('\t')
        ).join('\n');
        contentText = header + '\n' + body;
      } else if (effectiveContent.type === 'questionList') {
        const questions = Array.isArray(d.questions) ? (d.questions as Array<Record<string, string>>) : [];
        contentText = questions.map((q, i) => `${i + 1}. ${q.text || q.question || JSON.stringify(q)}`).join('\n');
      } else {
        const summary = typeof d.description === 'string' ? d.description : '';
        contentText = summary || JSON.stringify(d, null, 2);
      }

      await navigator.clipboard.writeText(contentText);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (error) {
      console.error('Copy failed:', error);
    }
  };

  // Export content
  const handleExport = async (format: SupportedExportFormat) => {
    if (!exportable || exportingFormat) {
      return;
    }

    try {
      setExportingFormat(format);
      setExportMenuOpen(false);
      const fileName = await exportCanvasContent(content, contents, format);
      toast.success(`已导出 ${fileName}`);
    } catch (error) {
      console.error('Export failed:', error);
      toast.error(error instanceof Error ? error.message : '导出失败');
    } finally {
      setExportingFormat(null);
    }
  };

  // Get icon based on content type
  const getTypeIcon = () => {
    switch (content.type) {
      case 'report':
        if (content.data?.report_kind === 'confidence_signal') {
          return <RiShieldCheckLine className="w-4 h-4" style={{ color: 'var(--warning)' }} />;
        }
        return <RiFileTextLine className="w-4 h-4" style={{ color: 'var(--color-primary)' }} />;
      case 'dataTable':
        return <RiTableLine className="w-4 h-4" style={{ color: 'var(--info)' }} />;
      default:
        return <RiFileTextLine className="w-4 h-4" style={{ color: 'var(--text-tertiary)' }} />;
    }
  };

  const actionBtnStyle = { color: 'var(--text-tertiary)' };
  const handleActionEnter = (e: React.MouseEvent<HTMLButtonElement>) => {
    e.currentTarget.style.background = 'var(--bg-elevated)';
    e.currentTarget.style.color = 'var(--text-primary)';
  };
  const handleActionLeave = (e: React.MouseEvent<HTMLButtonElement>) => {
    e.currentTarget.style.background = 'transparent';
    e.currentTarget.style.color = 'var(--text-tertiary)';
  };
  const handleMenuItemEnter = (e: React.MouseEvent<HTMLButtonElement>) => {
    e.currentTarget.style.background = 'var(--bg-elevated)';
  };
  const handleMenuItemLeave = (e: React.MouseEvent<HTMLButtonElement>) => {
    e.currentTarget.style.background = 'transparent';
  };

  const dropdownClass = 'absolute right-0 top-full mt-1 rounded-lg shadow-lg py-1 z-20 min-w-[140px]';
  const dropdownStyle = {
    backgroundColor: 'var(--bg-secondary)',
    border: '1px solid var(--border-subtle)',
  };
  const menuItemClass = 'w-full px-3 py-2 text-left text-sm flex items-center gap-2 transition-colors';

  return (
    <div
      className="transition-colors"
      style={{
        borderBottom: '1px solid var(--border-subtle)',
        backgroundColor: 'var(--bg-primary)',
      }}
    >
      {/* Top row: title + actions */}
      <div className="flex items-center justify-between px-4 py-3">
        {/* Left: Title and type */}
        <div className="flex items-center gap-3 min-w-0">
          <div
            className="p-1.5 rounded-lg"
            style={{
              backgroundColor: 'var(--bg-elevated)',
              border: '1px solid var(--border-subtle)',
            }}
          >
            {getTypeIcon()}
          </div>
          <div className="min-w-0">
            <h2 className="font-semibold truncate text-sm" style={{ color: 'var(--text-primary)' }}>
              {content.title}
            </h2>
            <span className="text-xs flex items-center gap-1.5" style={{ color: 'var(--text-tertiary)' }}>
              <span className="capitalize">
                {content.type === 'dataTable' ? '数据表格' :
                 effectiveContent.type === 'report' ? (
                   effectiveContent.data?.report_kind === 'confidence_signal' ? '置信度报告' : '分析报告'
                 ) :
                 effectiveContent.type === 'chart' ? '数据图表' :
                 effectiveContent.type === 'questionList' ? '问题列表' :
                 effectiveContent.type === 'fetchResults' ? '抓取结果' :
                 '选择项'}
              </span>
              {content.category === 'baseline' && (
                <span className="px-1.5 py-0.5 text-[10px] font-medium rounded bg-violet-500/15 text-violet-300 border border-violet-500/30">
                  基线
                </span>
              )}
              {content.category === 'scenario' && (
                <span className="px-1.5 py-0.5 text-[10px] font-medium rounded bg-sky-500/15 text-sky-300 border border-sky-500/30">
                  {content.scenarioLabel || '场景'}
                </span>
              )}
            </span>
          </div>
        </div>

        {/* Right: Action buttons */}
        <div className="flex items-center gap-1">
          {isConfidenceSignal ? (
            <button
              onClick={() => setArtifactInputOpen(true)}
              className="mr-2 inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-[12px] font-medium transition-all duration-200 active:scale-95"
              style={{
                borderColor: 'var(--border-subtle)',
                color: 'var(--text-primary)',
                backgroundColor: 'var(--bg-secondary)',
              }}
              title="额外评估"
            >
              <RiSparklingLine className="h-3.5 w-3.5" />
              额外评估
            </button>
          ) : null}

          {/* Copy button */}
          <button
            onClick={handleCopy}
            className="p-2 rounded-lg transition-all duration-200 active:scale-95 cursor-pointer"
            style={copied
              ? { backgroundColor: 'var(--status-success-bg, rgba(34,197,94,0.1))', color: 'var(--status-success)' }
              : actionBtnStyle
            }
            onMouseEnter={copied ? undefined : handleActionEnter}
            onMouseLeave={copied ? undefined : handleActionLeave}
            title={copied ? '已复制' : '复制内容'}
          >
            <AnimatePresence mode="wait">
              {copied ? (
                <motion.div key="check" initial={{ scale: 0 }} animate={{ scale: 1 }} exit={{ scale: 0 }}>
                  <RiCheckLine className="w-4 h-4" />
                </motion.div>
              ) : (
                <motion.div key="copy" initial={{ scale: 0 }} animate={{ scale: 1 }} exit={{ scale: 0 }}>
                  <RiFileCopyLine className="w-4 h-4" />
                </motion.div>
              )}
            </AnimatePresence>
          </button>

          {/* Share button — disabled */}
          <button
            disabled
            className="p-2 rounded-lg transition-all duration-200 cursor-not-allowed opacity-40"
            style={actionBtnStyle}
            title="即将推出"
          >
            <RiShareLine className="w-4 h-4" />
          </button>

          {/* Export button with dropdown */}
          {exportable && (
            <div className="relative">
              <button
                onClick={() => setExportMenuOpen(!exportMenuOpen)}
                className="p-2 rounded-lg transition-all duration-200 active:scale-95 cursor-pointer"
                style={actionBtnStyle}
                onMouseEnter={exportingFormat ? undefined : handleActionEnter}
                onMouseLeave={exportingFormat ? undefined : handleActionLeave}
                title="导出"
                disabled={Boolean(exportingFormat)}
              >
                {exportingFormat ? <RiLoader4Line className="w-4 h-4 animate-spin" /> : <RiDownloadLine className="w-4 h-4" />}
              </button>

              <AnimatePresence>
                {exportMenuOpen && (
                  <motion.div
                    initial={{ opacity: 0, y: -5, scale: 0.95 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    exit={{ opacity: 0, y: -5, scale: 0.95 }}
                    className={dropdownClass}
                    style={dropdownStyle}
                  >
                    <button
                      onClick={() => handleExport('pdf')}
                      className={menuItemClass}
                      style={{ color: 'var(--text-primary)' }}
                      onMouseEnter={handleMenuItemEnter}
                      onMouseLeave={handleMenuItemLeave}
                      disabled={Boolean(exportingFormat)}
                    >
                      <RiFileTextLine className="w-3.5 h-3.5" />
                      导出 PDF
                    </button>
                    <button
                      onClick={() => handleExport('md')}
                      className={menuItemClass}
                      style={{ color: 'var(--text-primary)' }}
                      onMouseEnter={handleMenuItemEnter}
                      onMouseLeave={handleMenuItemLeave}
                      disabled={Boolean(exportingFormat)}
                    >
                      <span className="text-[11px] font-semibold tracking-[0.08em]">MD</span>
                      导出 MD
                    </button>
                    <div className="px-3 pb-2 pt-1 text-[11px]" style={{ color: 'var(--text-tertiary)' }}>
                      文件名：品牌名 + {exportLabel} + 时间 + 版本号
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          )}

          {/* Divider */}
          <div className="w-px h-4 mx-1" style={{ backgroundColor: 'var(--border-subtle)' }} />

          {/* Expand/Collapse button */}
          <button
            onClick={toggleMode}
            className="p-2 rounded-lg transition-all duration-200 active:scale-95 cursor-pointer"
            style={actionBtnStyle}
            onMouseEnter={handleActionEnter}
            onMouseLeave={handleActionLeave}
            title={mode === 'split' ? '展开' : '收起'}
          >
            {mode === 'split' ? (
              <RiExpandDiagonalLine className="w-4 h-4" />
            ) : (
              <RiCollapseDiagonalLine className="w-4 h-4" />
            )}
          </button>

          {/* Close button */}
          <button
            onClick={closeCanvas}
            className="p-2 rounded-lg transition-all duration-200 active:scale-95 cursor-pointer"
            style={actionBtnStyle}
            onMouseEnter={handleActionEnter}
            onMouseLeave={handleActionLeave}
            title="关闭"
          >
            <RiCloseLine className="w-4 h-4" />
          </button>
        </div>

        {/* Click outside to close menus */}
        {(exportMenuOpen || versionMenuOpen) && (
          <div
            className="fixed inset-0 z-10"
            onClick={() => {
              setExportMenuOpen(false);
              setVersionMenuOpen(false);
            }}
          />
        )}
      </div>

      {/* Version bar: version selector + jump to conversation */}
      {(hasVersions || activeLinkedMessageId) && (
        <div
          className="flex items-center justify-between px-4 py-2"
          style={{ borderTop: '1px solid var(--border-subtle)', backgroundColor: 'var(--bg-secondary)' }}
        >
          <div className="flex items-center gap-3">
            {/* Version selector */}
            {hasVersions && (
              <div className="relative">
                <button
                  onClick={handleVersionMenuToggle}
                  className={cn(
                    'flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs transition-colors cursor-pointer',
                    isViewingHistory
                      ? 'bg-[var(--brand-bg)] text-[var(--brand-primary)] border border-[var(--brand-border)]'
                      : 'text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] border border-transparent'
                  )}
                >
                  <RiHistoryLine className="w-3.5 h-3.5" />
                  {isViewingHistory
                    ? `v${versions[content.currentVersionIndex]?.versionNumber ?? '?'}`
                    : `v${versions.length + 1} (最新)`
                  }
                  <RiArrowDownSLine className="w-3.5 h-3.5" />
                  {content.hasNewVersion && (
                    <span
                      className="absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full"
                      style={{ backgroundColor: 'var(--error)' }}
                    />
                  )}
                </button>

                <AnimatePresence>
                  {versionMenuOpen && (
                    <motion.div
                      initial={{ opacity: 0, y: -5, scale: 0.95 }}
                      animate={{ opacity: 1, y: 0, scale: 1 }}
                      exit={{ opacity: 0, y: -5, scale: 0.95 }}
                      className="absolute left-0 top-full mt-1 rounded-lg shadow-lg py-1 z-20 min-w-[220px]"
                      style={dropdownStyle}
                    >
                      {/* Latest (current) */}
                      <button
                        onClick={() => handleVersionSelect(-1)}
                        className={cn(menuItemClass, 'text-xs')}
                        style={{
                          color: !isViewingHistory ? 'var(--brand-primary)' : 'var(--text-primary)',
                          backgroundColor: !isViewingHistory ? 'var(--brand-bg)' : undefined,
                        }}
                        onMouseEnter={isViewingHistory ? handleMenuItemEnter : undefined}
                        onMouseLeave={isViewingHistory ? handleMenuItemLeave : undefined}
                      >
                        <span className="font-medium">v{versions.length + 1}</span>
                        <span style={{ color: 'var(--text-tertiary)' }}>
                          {formatTimestamp(content.createdAt?.toISOString?.() || new Date().toISOString())}
                        </span>
                        <span
                          className="ml-auto px-1.5 py-0.5 rounded text-[10px]"
                          style={{ backgroundColor: 'var(--status-success-bg)', color: 'var(--success)' }}
                        >
                          最新
                        </span>
                      </button>
                      {/* Historical versions */}
                      {versions.map((v, idx) => (
                        <button
                          key={idx}
                          onClick={() => handleVersionSelect(idx)}
                          className={cn(menuItemClass, 'text-xs')}
                          style={{
                            color: isViewingHistory && content.currentVersionIndex === idx
                              ? 'var(--brand-primary)'
                              : 'var(--text-primary)',
                            backgroundColor: isViewingHistory && content.currentVersionIndex === idx
                              ? 'var(--brand-bg)'
                              : undefined,
                          }}
                          onMouseEnter={handleMenuItemEnter}
                          onMouseLeave={handleMenuItemLeave}
                        >
                          <span className="font-medium">v{v.versionNumber}</span>
                          <span style={{ color: 'var(--text-tertiary)' }}>
                            {formatTimestamp(v.timestamp)}
                          </span>
                        </button>
                      ))}
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            )}

            {/* Viewing history indicator */}
            {isViewingHistory && (
              <button
                onClick={() => handleVersionSelect(-1)}
                className="text-xs px-2 py-1 rounded-md cursor-pointer transition-colors"
                style={{ color: 'var(--brand-primary)' }}
              >
                回到最新版本
              </button>
            )}
          </div>

          {/* Jump to conversation */}
          {activeLinkedMessageId && (
            <button
              onClick={handleJumpToConversation}
              className="flex items-center gap-1 text-xs px-2 py-1 rounded-md transition-colors cursor-pointer"
              style={{ color: 'var(--text-tertiary)' }}
              onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--brand-primary)'; }}
              onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--text-tertiary)'; }}
            >
              <RiChatForwardLine className="w-3.5 h-3.5" />
              跳转到对应对话
            </button>
          )}
        </div>
      )}

      {artifactInputOpen && isConfidenceSignal ? (
        <div className={modalScrimClassName('z-40 flex items-center justify-center px-4 py-6')}>
          <div
            className="w-full max-w-[640px] rounded-[24px] border bg-[var(--bg-primary)] p-5 shadow-[0_24px_60px_rgba(15,23,42,0.28)]"
            style={{ borderColor: 'var(--border-subtle)' }}
          >
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="text-[18px] font-semibold text-[var(--text-primary)]">额外评估</div>
                <div className="mt-1 text-[13px] leading-6 text-[var(--text-secondary)]">
                  在当前置信度报告中追加一个链接或一段文本，系统会把结果写回当前交付物。
                </div>
              </div>
              <button
                onClick={() => setArtifactInputOpen(false)}
                className="rounded-lg p-2 text-[var(--text-tertiary)] transition-colors hover:bg-[var(--bg-secondary)] hover:text-[var(--text-primary)]"
                title="关闭"
              >
                <RiCloseLine className="h-4 w-4" />
              </button>
            </div>

            <textarea
              value={artifactInputValue}
              onChange={(event) => setArtifactInputValue(event.target.value)}
              placeholder={confidenceComposer?.placeholder || '粘贴链接或文本，生成额外评估'}
              className="mt-5 min-h-[180px] w-full resize-y rounded-[18px] border bg-[var(--bg-secondary)] px-4 py-4 text-[14px] leading-7 text-[var(--text-primary)] outline-none transition-colors placeholder:text-[var(--text-tertiary)] focus:border-[var(--brand-primary)]"
              style={{ borderColor: 'var(--border-subtle)' }}
            />

            <div className="mt-3 flex flex-wrap gap-2 text-[12px] text-[var(--text-tertiary)]">
              <span className="rounded-full bg-[var(--bg-secondary)] px-3 py-1.5">支持链接</span>
              <span className="rounded-full bg-[var(--bg-secondary)] px-3 py-1.5">支持文本</span>
              <span className="rounded-full bg-[var(--bg-secondary)] px-3 py-1.5">不支持混合提交</span>
            </div>

            <div className="mt-4 flex items-center justify-between gap-4">
              <div className="text-[12px] leading-6 text-[var(--text-secondary)]">
                {confidenceComposer?.helper_text || '支持单个链接、多个链接或一段文本；当前不支持问题抓取命令。'}
              </div>
              <div className="flex items-center gap-2">
                <Button variant="ghost" onClick={() => setArtifactInputOpen(false)}>
                  取消
                </Button>
                <Button
                  onClick={handleArtifactSubmit}
                  disabled={!confidenceComposer?.enabled || !sendArtifactAction || !artifactInputValue.trim() || isArtifactActionRunning}
                  isLoading={isArtifactActionRunning}
                  leftIcon={<RiLinkM className="h-4 w-4" />}
                >
                  开始评估
                </Button>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
