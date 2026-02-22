/**
 * Recharts SVG props (stroke, fill, tick) don't support CSS var().
 * These constants mirror design-system.css values.
 * Update BOTH files when changing theme.
 */

export const chart = {
  grid: '#333333',
  axis: {
    tick: '#737373',       // --text-tertiary
    fontSize: 12,
  },
  tooltip: {
    bg: '#1A1A1A',         // --bg-tertiary
    border: '#333333',
    radius: '8px',
    text: '#E5E5E5',
  },
  colors: {
    primary: '#6366F1',    // --color-primary
    purple: '#8B5CF6',
    green: '#22C55E',
    yellow: '#F59E0B',     // --status-warning
    red: '#EF4444',        // --status-error
    cyan: '#06B6D4',       // --color-accent-cyan
    pink: '#EC4899',       // --color-accent-pink
    neutral: '#737373',    // --text-tertiary
    secondary: '#A3A3A3',  // --text-secondary
  },
} as const;

/** Recharts tooltip contentStyle */
export const tooltipStyle = {
  backgroundColor: chart.tooltip.bg,
  border: `1px solid ${chart.tooltip.border}`,
  borderRadius: chart.tooltip.radius,
  color: chart.tooltip.text,
} as const;

/** Recharts axis tick props */
export const axisTick = {
  fill: chart.axis.tick,
  fontSize: chart.axis.fontSize,
} as const;

/** Pie/donut chart color palette */
export const PIE_COLORS = [
  chart.colors.primary,
  chart.colors.purple,
  chart.colors.green,
  chart.colors.yellow,
  chart.colors.red,
  chart.colors.cyan,
  chart.colors.pink,
] as const;
