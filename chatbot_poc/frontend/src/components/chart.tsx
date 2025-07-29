"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

interface ChartProps {
  data: any[];
  xAxisKey: string;
  yAxisKey: string;
}

export function Chart({ data, xAxisKey, yAxisKey }: ChartProps) {
  return (
    <ResponsiveContainer width="100%" height={300}>
      <BarChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
        <XAxis dataKey={xAxisKey} stroke="#9ca3af" />
        <YAxis stroke="#9ca3af" />
        <Tooltip
          contentStyle={{
            backgroundColor: "#1f2937",
            borderColor: "#374151",
          }}
        />
        <Legend wrapperStyle={{ color: "#9ca3af" }} />
        <Bar dataKey={yAxisKey} fill="#6366f1" />
      </BarChart>
    </ResponsiveContainer>
  );
}