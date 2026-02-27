'use client';

import type { ChartCanvasContent, ChartDataItem, ChartSeries } from '@/types/canvas';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  LineChart,
  Line,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
} from 'recharts';

interface ChartContentProps {
  content: ChartCanvasContent;
}

const COLORS = ['#6366F1', '#8B5CF6', '#EC4899', '#F59E0B', '#10B981', '#3B82F6'];

export function ChartContent({ content }: ChartContentProps) {
  const data = content.data;
  const chartType = data.chartType ?? 'bar';
  const chartData: ChartDataItem[] = data.data ?? [];

  const renderChart = () => {
    switch (chartType) {
      case 'bar':
        return (
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey={data.xAxisKey ?? 'name'} />
              <YAxis />
              <Tooltip />
              <Legend />
              {(data.series ?? [{ key: 'value', name: '数值' }]).map((s: ChartSeries, i: number) => (
                <Bar key={s.key} dataKey={s.key} name={s.name} fill={COLORS[i % COLORS.length]} />
              ))}
            </BarChart>
          </ResponsiveContainer>
        );

      case 'pie':
        return (
          <ResponsiveContainer width="100%" height={300}>
            <PieChart>
              <Pie
                data={chartData}
                cx="50%"
                cy="50%"
                labelLine={false}
                label={({ name, percent }) => `${name} ${((percent || 0) * 100).toFixed(0)}%`}
                outerRadius={100}
                fill="#8884d8"
                dataKey={data.valueKey ?? 'value'}
              >
                {chartData.map((_, index: number) => (
                  <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        );

      case 'line':
        return (
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey={data.xAxisKey ?? 'name'} />
              <YAxis />
              <Tooltip />
              <Legend />
              {(data.series ?? [{ key: 'value', name: '数值' }]).map((s: ChartSeries, i: number) => (
                <Line
                  key={s.key}
                  type="monotone"
                  dataKey={s.key}
                  name={s.name}
                  stroke={COLORS[i % COLORS.length]}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        );

      case 'radar':
        return (
          <ResponsiveContainer width="100%" height={300}>
            <RadarChart cx="50%" cy="50%" outerRadius="80%" data={chartData}>
              <PolarGrid />
              <PolarAngleAxis dataKey={data.angleKey ?? 'subject'} />
              <PolarRadiusAxis />
              {(data.series ?? [{ key: 'A', name: 'A' }]).map((s: ChartSeries, i: number) => (
                <Radar
                  key={s.key}
                  name={s.name}
                  dataKey={s.key}
                  stroke={COLORS[i % COLORS.length]}
                  fill={COLORS[i % COLORS.length]}
                  fillOpacity={0.3}
                />
              ))}
              <Legend />
              <Tooltip />
            </RadarChart>
          </ResponsiveContainer>
        );

      default:
        return <div className="text-center text-[--text-tertiary] py-8">不支持的图表类型</div>;
    }
  };

  return (
    <div className="p-6">
      {/* 图表描述 */}
      {data.description && (
        <p className="text-sm text-[--text-secondary] mb-4">{data.description}</p>
      )}

      {/* 图表 */}
      <div className="bg-[--bg-elevated] rounded-lg">
        {renderChart()}
      </div>

      {/* 数据摘要 */}
      {data.summary && (
        <div className="mt-4 p-4 bg-[--bg-tertiary] rounded-lg">
          <h4 className="font-medium text-[--text-primary] mb-2">数据摘要</h4>
          <div className="text-sm text-[--text-secondary]">{data.summary}</div>
        </div>
      )}
    </div>
  );
}
