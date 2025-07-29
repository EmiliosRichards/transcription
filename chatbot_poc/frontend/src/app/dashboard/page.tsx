"use client";

import { useEffect, useState } from 'react';
import { Card, CardContent } from "@/components/ui/card";
import KPICard from "@/components/ui/KPICard";
import LineChart from "@/components/charts/LineChart";
import BarChart from "@/components/charts/BarChart";

import { CallData } from "@/lib/data";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { motion } from "framer-motion";
import { ModeToggle } from "@/components/theme-toggle";
import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function DashboardPage() {
  const [data, setData] = useState<CallData[]>([]);
  const [filteredData, setFilteredData] = useState<CallData[]>([]);
  const [selectedCampaign, setSelectedCampaign] = useState("all");

  useEffect(() => {
    async function fetchData() {
      const response = await fetch("/api/calls");
      const callData = await response.json();
      setData(callData);
      setFilteredData(callData);
    }
    fetchData();
  }, []);

  useEffect(() => {
    if (selectedCampaign === "all") {
      setFilteredData(data);
    } else {
      setFilteredData(
        data.filter((item) => item.campaign_name === selectedCampaign)
      );
    }
  }, [selectedCampaign, data]);

  const totalRecordings = filteredData.reduce(
    (acc, item) => acc + item.total_recordings,
    0
  );
  const totalCampaigns = [...new Set(data.map((item) => item.campaign_name))]
    .length;
  const avgRecordings =
    filteredData.length > 0
      ? (totalRecordings / filteredData.length).toFixed(2)
      : 0;

  const campaignData = filteredData.reduce((acc, item) => {
    const existing = acc.find((i) => i.name === item.campaign_name);
    if (existing) {
      existing.recordings += item.total_recordings;
    } else {
      acc.push({
        name: item.campaign_name,
        recordings: item.total_recordings,
      });
    }
    return acc;
  }, [] as { name: string; recordings: number }[]);

  const campaigns = ["all", ...[...new Set(data.map((item) => item.campaign_name))]];

  return (
    <div className="p-6 bg-gray-50 min-h-screen">
      {/* Top Title */}
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-3xl text-gray-800 dark:text-white">📊 Call Analytics Dashboard</h1>
        <div className="flex items-center gap-4">
          <Select onValueChange={setSelectedCampaign} defaultValue="all">
            <SelectTrigger className="w-[180px]">
              <SelectValue placeholder="Select a campaign" />
            </SelectTrigger>
            <SelectContent>
              {campaigns.map((campaign, index) => (
                <SelectItem key={`${campaign}-${index}`} value={campaign}>
                  {campaign}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <ModeToggle />
          <Link href="/">
            <Button>Back to Chatbot</Button>
          </Link>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <KPICard
          title="Total Recordings"
          value={totalRecordings.toString()}
          change=""
        />
        <KPICard
          title="Total Campaigns"
          value={totalCampaigns.toString()}
          change=""
        />
        <KPICard
          title="Avg Recordings per Call"
          value={avgRecordings.toString()}
          change=""
        />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
        >
          <Card className="rounded-2xl shadow-lg">
            <CardContent>
              <h2 className="text-lg mb-4 text-gray-800 dark:text-white">
                Recordings per Campaign
              </h2>
              <BarChart />
            </CardContent>
          </Card>
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.2 }}
        >
          <Card className="rounded-2xl shadow-lg">
            <CardContent>
              <h2 className="text-lg mb-4 text-gray-800 dark:text-white">
                Recordings Over Time
              </h2>
              <LineChart />
            </CardContent>
          </Card>
        </motion.div>
      </div>
    </div>
  );
}