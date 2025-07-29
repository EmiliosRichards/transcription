"use client";

import { BarChart as RCBarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";

const data = [
  { name: "Product A", sales: 2400 },
  { name: "Product B", sales: 4567 },
  { name: "Product C", sales: 1398 },
  { name: "Product D", sales: 9800 },
];

export default function BarChart() {
  return (
    <ResponsiveContainer width="100%" height={300}>
      <RCBarChart data={data}>
        <XAxis dataKey="name" />
        <YAxis />
        <Tooltip />
        <Bar dataKey="sales" fill="#9333ea" />
      </RCBarChart>
    </ResponsiveContainer>
  );
}