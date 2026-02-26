"use client";

import React from "react";
import {
  Radar,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  ResponsiveContainer,
  Legend,
  Tooltip,
} from "recharts";

interface RadarChartProps {
  data: {
    subject: string;
    [key: string]: string | number;
  }[];
  brands: string[];
  colors?: string[];
}

const defaultColors = ["#6366F1", "#EC4899", "#22C55E", "#F59E0B", "#8B5CF6"];

export function BrandRadarChart({ data, brands, colors = defaultColors }: RadarChartProps) {
  return (
    <div className="w-full h-[400px]">
      <ResponsiveContainer width="100%" height="100%">
        <RadarChart cx="50%" cy="50%" outerRadius="80%" data={data}>
          <PolarGrid stroke="var(--border-subtle)" />
          <PolarAngleAxis
            dataKey="subject"
            tick={{ fill: "var(--text-secondary)", fontSize: 12 }}
          />
          <PolarRadiusAxis
            angle={90}
            domain={[0, 100]}
            tick={{ fill: "var(--text-tertiary)", fontSize: 10 }}
            stroke="var(--border-subtle)"
          />
          {brands.map((brand, index) => (
            <Radar
              key={brand}
              name={brand}
              dataKey={brand}
              stroke={colors[index % colors.length]}
              fill={colors[index % colors.length]}
              fillOpacity={0.1}
              strokeWidth={2}
            />
          ))}
          <Legend
            wrapperStyle={{ paddingTop: "20px" }}
            formatter={(value) => (
              <span style={{ color: "var(--text-secondary)" }}>{value}</span>
            )}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "var(--bg-secondary)",
              border: "1px solid var(--border-subtle)",
              borderRadius: "8px",
              color: "var(--text-primary)",
            }}
            itemStyle={{ color: "var(--text-secondary)" }}
          />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
}
