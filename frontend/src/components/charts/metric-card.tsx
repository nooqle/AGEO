"use client";

import React from "react";
import { motion } from "framer-motion";
import { RiArrowUpLine, RiArrowDownLine, RiSubtractLine } from "@remixicon/react";

export interface MetricCardProps {
  title: string;
  value: string | number;
  unit?: string;
  trend?: "up" | "down" | "neutral";
  trendValue?: string;
  description?: string;
  icon?: React.ReactNode;
  color?: "primary" | "success" | "warning" | "error";
}

const colorConfig = {
  primary: {
    bg: "bg-indigo-500/10",
    border: "border-indigo-500/30",
    text: "text-indigo-400",
  },
  success: {
    bg: "bg-emerald-500/10",
    border: "border-emerald-500/30",
    text: "text-emerald-400",
  },
  warning: {
    bg: "bg-amber-500/10",
    border: "border-amber-500/30",
    text: "text-amber-400",
  },
  error: {
    bg: "bg-red-500/10",
    border: "border-red-500/30",
    text: "text-red-400",
  },
};

export function MetricCard({
  title,
  value,
  unit,
  trend,
  trendValue,
  description,
  icon,
  color = "primary",
}: MetricCardProps) {
  const colors = colorConfig[color];

  const TrendIcon = trend === "up" ? RiArrowUpLine : trend === "down" ? RiArrowDownLine : RiSubtractLine;
  const trendColor =
    trend === "up" ? "text-emerald-400" : trend === "down" ? "text-red-400" : "text-gray-400";

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className={`relative overflow-hidden rounded-xl border ${colors.border} ${colors.bg} p-6`}
    >
      {/* Background decoration */}
      <div className={`absolute -right-4 -top-4 w-24 h-24 rounded-full ${colors.bg} blur-2xl`} />

      <div className="relative">
        {/* Header */}
        <div className="flex items-start justify-between mb-4">
          <div>
            <p className="text-sm text-[var(--text-secondary)]">{title}</p>
            {description && <p className="text-xs text-[var(--text-tertiary)] mt-1">{description}</p>}
          </div>
          {icon && <div className={`${colors.text}`}>{icon}</div>}
        </div>

        {/* Value */}
        <div className="flex items-baseline gap-2">
          <span className="text-3xl font-bold text-[var(--text-primary)]">{value}</span>
          {unit && <span className="text-sm text-[var(--text-secondary)]">{unit}</span>}
        </div>

        {/* Trend */}
        {trend && trendValue && (
          <div className={`flex items-center gap-1 mt-3 ${trendColor}`}>
            <TrendIcon className="w-4 h-4" />
            <span className="text-sm font-medium">{trendValue}</span>
            <span className="text-xs text-[var(--text-tertiary)] ml-1">较上期</span>
          </div>
        )}
      </div>
    </motion.div>
  );
}

interface MetricGridProps {
  metrics: MetricCardProps[];
}

export function MetricGrid({ metrics }: MetricGridProps) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {metrics.map((metric, index) => (
        <motion.div
          key={metric.title}
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: index * 0.1 }}
        >
          <MetricCard {...metric} />
        </motion.div>
      ))}
    </div>
  );
}
