"use client";

import React from "react";
import { cn } from "@/lib/utils";

interface SkeletonProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: "text" | "circular" | "rectangular" | "rounded";
  width?: string | number;
  height?: string | number;
  animation?: "pulse" | "wave" | "none";
}

export function Skeleton({
  className,
  variant = "text",
  width,
  height,
  animation = "pulse",
  style,
  ...props
}: SkeletonProps) {
  const variants = {
    text: "rounded",
    circular: "rounded-full",
    rectangular: "rounded-none",
    rounded: "rounded-lg",
  };

  const animations = {
    pulse: "animate-pulse",
    wave: "animate-shimmer",
    none: "",
  };

  return (
    <div
      className={cn(
        "bg-[var(--bg-tertiary)]",
        variants[variant],
        animations[animation],
        className
      )}
      style={{
        width: width,
        height: height,
        ...style,
      }}
      {...props}
    />
  );
}

// Pre-built skeleton patterns
export function TextSkeleton({ lines = 3, className }: { lines?: number; className?: string }) {
  return (
    <div className={cn("space-y-2", className)}>
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton
          key={i}
          width={i === lines - 1 ? "80%" : "100%"}
          height={16}
          className="rounded"
        />
      ))}
    </div>
  );
}

export function CardSkeleton({ className }: { className?: string }) {
  return (
    <div className={cn("bg-[var(--bg-secondary)] rounded-xl p-4 border border-[var(--border-default)]", className)}>
      <div className="flex items-center gap-4">
        <Skeleton variant="circular" width={48} height={48} />
        <div className="flex-1 space-y-2">
          <Skeleton width="60%" height={20} />
          <Skeleton width="40%" height={14} />
        </div>
      </div>
      <div className="mt-4 space-y-2">
        <Skeleton width="100%" height={14} />
        <Skeleton width="90%" height={14} />
        <Skeleton width="70%" height={14} />
      </div>
    </div>
  );
}

export function MetricCardSkeleton({ className }: { className?: string }) {
  return (
    <div className={cn("bg-[var(--bg-secondary)] rounded-xl p-6 border border-[var(--border-default)]", className)}>
      <div className="flex items-start justify-between">
        <div>
          <Skeleton width={80} height={14} className="mb-2" />
          <Skeleton width={120} height={36} />
        </div>
        <Skeleton variant="circular" width={40} height={40} />
      </div>
      <div className="mt-4">
        <Skeleton width={100} height={16} />
      </div>
    </div>
  );
}

export function ChartSkeleton({ className }: { className?: string }) {
  return (
    <div className={cn("bg-[var(--bg-secondary)] rounded-xl p-4 border border-[var(--border-default)]", className)}>
      <Skeleton width={150} height={20} className="mb-4" />
      <Skeleton width="100%" height={300} variant="rounded" />
    </div>
  );
}

export function MessageSkeleton({ className }: { className?: string }) {
  return (
    <div className={cn("flex gap-3", className)}>
      <Skeleton variant="circular" width={32} height={32} />
      <div className="flex-1 space-y-2">
        <Skeleton width={60} height={14} />
        <div className="bg-[var(--bg-secondary)] rounded-lg p-3 border border-[var(--border-default)]">
          <TextSkeleton lines={3} />
        </div>
      </div>
    </div>
  );
}

export function ProcessTimelineSkeleton({ className }: { className?: string }) {
  return (
    <div className={cn("bg-[var(--bg-secondary)] rounded-lg border border-[var(--border-default)] overflow-hidden", className)}>
      <div className="px-4 py-3 border-b border-[var(--border-default)]">
        <Skeleton width={100} height={16} />
      </div>
      <div className="p-4 space-y-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="flex items-start gap-3">
            <Skeleton variant="rounded" width={32} height={32} />
            <div className="flex-1 space-y-2">
              <Skeleton width={80} height={14} />
              <Skeleton width="90%" height={12} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
