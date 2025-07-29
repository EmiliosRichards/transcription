import { Card, CardContent } from "@/components/ui/card";

interface KPICardProps {
  title: string;
  value: string;
  change?: string;
}

export default function KPICard({ title, value, change }: KPICardProps) {
  return (
    <Card>
      <CardContent className="p-4 flex flex-col">
        <span className="text-gray-500">{title}</span>
        <span className="text-2xl font-bold">{value}</span>
        {change && (
          <span className="text-sm text-green-500 font-medium">{change}</span>
        )}
      </CardContent>
    </Card>
  );
}