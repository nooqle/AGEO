/**
 * Recharts SVG props (stroke, fill, tick) don't support CSS var().
 * These constants mirror the restrained Specta evidence palette.
 */

export const chart = {
  grid: '#D8D0C2',
  axis: {
    tick: '#8F897D',       // --text-tertiary
    fontSize: 12,
  },
  tooltip: {
    bg: '#FFFDF7',         // --bg-elevated (light)
    border: '#DDD2C1',
    radius: '8px',
    text: '#242821',
  },
  colors: {
    primary: '#1F7A6B',
    source: '#4F6F88',
    evidence: '#7B6A4C',
    green: '#3F8F62',
    yellow: '#B7792B',
    red: '#B44D45',
    neutral: '#8F897D',
    secondary: '#6F695E',
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
  chart.colors.source,
  chart.colors.evidence,
  chart.colors.green,
  chart.colors.yellow,
  chart.colors.red,
] as const;
