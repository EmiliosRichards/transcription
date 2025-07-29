"use client";

import { LineChart as RCLineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";

const data = [
  { month: "Jan", sales: 4000 },
  { month: "Feb", sales: 3000 },
  { month: "Mar", sales: 5000 },
  { month: "Apr", sales: 7000 },
  { month: "May", sales: 6000 },
];

export default function LineChart() {
  return (
    <ResponsiveContainer width="100%" height={300}>
      <RCLineChart data={data}>
        <XAxis dataKey="month" />
        <YAxis />
        <Tooltip />
        <Line type="monotone" dataKey="sales" stroke="#2563eb" strokeWidth={3} />
      </RCLineChart>
    </ResponsiveContainer>
  );
}