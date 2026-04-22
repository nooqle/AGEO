"use client";

import React from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  RiBrainLine,
  RiToolsLine,
  RiEyeLine,
  RiCheckLine,
  RiLoader4Line,
  RiErrorWarningLine,
} from "@remixicon/react";
import { getUserFacingStageLabel, sanitizeUserFacingWorkflowText } from "@/lib/workflowStageLabels";

export interface ProcessStep {
  id: string;
  type: "thinking" | "action" | "observation" | "error" | "complete";
  content?: string;
  tool?: string;
  params?: Record<string, unknown>;
  data?: Record<string, unknown>;
  message?: string;
  progress?: number;
  error?: string;
  subtype?: "progress" | "result";
  timestamp?: Date;
}

interface ProcessTimelineProps {
  steps: ProcessStep[];
  isExpanded?: boolean;
  onToggle?: () => void;
}

const phaseConfig = {
  thinking: {
    icon: RiBrainLine,
    label: "思考",
    color: "var(--phase-thought)",
    bgColor: "bg-violet-500/10",
    borderColor: "border-violet-500/30",
  },
  action: {
    icon: RiToolsLine,
    label: "执行",
    color: "var(--phase-action)",
    bgColor: "bg-amber-500/10",
    borderColor: "border-amber-500/30",
  },
  observation: {
    icon: RiEyeLine,
    label: "观察",
    color: "var(--phase-observe)",
    bgColor: "bg-emerald-500/10",
    borderColor: "border-emerald-500/30",
  },
  error: {
    icon: RiErrorWarningLine,
    label: "错误",
    color: "var(--error)",
    bgColor: "bg-red-500/10",
    borderColor: "border-red-500/30",
  },
  complete: {
    icon: RiCheckLine,
    label: "完成",
    color: "var(--success)",
    bgColor: "bg-green-500/10",
    borderColor: "border-green-500/30",
  },
};

function formatToolName(tool?: string): string {
  if (!tool) return "";
  return sanitizeUserFacingWorkflowText(getUserFacingStageLabel(tool) || tool) || tool;
}

export function ProcessTimeline({ steps, isExpanded = false, onToggle }: ProcessTimelineProps) {
  // Group steps by tool execution
  const groupedSteps = React.useMemo(() => {
    const groups: { tool?: string; steps: ProcessStep[] }[] = [];
    let currentGroup: { tool?: string; steps: ProcessStep[] } | null = null;

    steps.forEach((step) => {
      if (step.tool) {
        if (!currentGroup || currentGroup.tool !== step.tool) {
          currentGroup = { tool: step.tool, steps: [] };
          groups.push(currentGroup);
        }
        currentGroup.steps.push(step);
      } else {
        if (!currentGroup) {
          currentGroup = { steps: [] };
          groups.push(currentGroup);
        }
        currentGroup.steps.push(step);
      }
    });

    return groups;
  }, [steps]);

  if (steps.length === 0) return null;

  return (
    <div className="bg-[var(--bg-secondary)] border border-[var(--border-subtle)] rounded-lg overflow-hidden">
      {/* Header */}
      <button
        onClick={onToggle}
        className="w-full px-4 py-3 flex items-center justify-between hover:bg-[var(--bg-tertiary)] transition-colors"
      >
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            {steps.some((s) => s.type === "error") ? (
              <RiErrorWarningLine className="w-4 h-4 text-[var(--error)]" />
            ) : steps[steps.length - 1]?.type === "complete" ? (
              <RiCheckLine className="w-4 h-4 text-[var(--success)]" />
            ) : (
              <RiLoader4Line className="w-4 h-4 text-[var(--brand-primary)] animate-spin" />
            )}
            <span className="text-sm font-medium text-[var(--text-primary)]">
              {steps[steps.length - 1]?.type === "complete"
                ? "分析完成"
                : steps.some((s) => s.type === "error")
                ? "执行出错"
                : "分析中..."}
            </span>
          </div>
          <span className="text-xs text-[var(--text-tertiary)]">
            {steps.length} 个步骤
          </span>
        </div>
        <motion.div
          animate={{ rotate: isExpanded ? 180 : 0 }}
          transition={{ duration: 0.2 }}
        >
          <svg className="w-4 h-4 text-[var(--text-tertiary)]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </motion.div>
      </button>

      {/* Timeline Content */}
      <AnimatePresence>
        {isExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.3 }}
            className="border-t border-[var(--border-subtle)]"
          >
            <div className="p-4 max-h-96 overflow-y-auto">
              <div className="space-y-4">
                {groupedSteps.map((group, groupIndex) => (
                  <div key={groupIndex} className="relative">
                    {/* Tool Header */}
                    {group.tool && (
                      <div className="flex items-center gap-2 mb-2 px-2">
                        <div className="w-2 h-2 rounded-full bg-[var(--brand-primary)]" />
                        <span className="text-xs font-medium text-[var(--text-secondary)] uppercase tracking-wider">
                          {formatToolName(group.tool)}
                        </span>
                      </div>
                    )}

                    {/* Steps */}
                    <div className="space-y-2">
                      {group.steps.map((step, stepIndex) => {
                        const config = phaseConfig[step.type] || phaseConfig.thinking;
                        const Icon = config.icon;

                        return (
                          <motion.div
                            key={step.id}
                            initial={{ opacity: 0, x: -10 }}
                            animate={{ opacity: 1, x: 0 }}
                            transition={{ delay: stepIndex * 0.05 }}
                            className={`flex items-start gap-3 p-3 rounded-lg border ${config.bgColor} ${config.borderColor}`}
                          >
                            {/* Icon */}
                            <div
                              className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
                              style={{ backgroundColor: config.color }}
                            >
                              <Icon className="w-4 h-4 text-white" />
                            </div>

                            {/* Content */}
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2 mb-1">
                                <span className="text-xs font-medium" style={{ color: config.color }}>
                                  {config.label}
                                </span>
                                {step.subtype && (
                                  <span className="text-xs text-[var(--text-tertiary)]">
                                    {step.subtype === "progress" ? "进行中" : "结果"}
                                  </span>
                                )}
                              </div>
                              {step.content && (
                                <p className="text-sm text-[var(--text-secondary)] line-clamp-2">
                                  {step.content}
                                </p>
                              )}
                              {step.message && (
                                <p className="text-sm text-[var(--text-secondary)] mt-1">
                                  {step.message}
                                </p>
                              )}
                              {step.error && (
                                <p className="text-sm text-red-400 mt-1">{step.error}</p>
                              )}
                              {step.progress !== undefined && step.progress > 0 && (
                                <div className="mt-2">
                                  <div className="h-1 bg-[var(--bg-tertiary)] rounded-full overflow-hidden">
                                    <motion.div
                                      className="h-full rounded-full"
                                      style={{ backgroundColor: config.color }}
                                      initial={{ width: 0 }}
                                      animate={{ width: `${step.progress}%` }}
                                      transition={{ duration: 0.3 }}
                                    />
                                  </div>
                                  <span className="text-xs text-[var(--text-tertiary)] mt-1">
                                    {step.progress}%
                                  </span>
                                </div>
                              )}
                            </div>
                          </motion.div>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
