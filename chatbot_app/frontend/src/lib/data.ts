import fs from 'fs';
import path from 'path';

export interface CallData {
  phone: string;
  campaign_name: string;
  total_recordings: number;
  first_call_time: string;
  last_call_time: string;
  recording_urls: string[];
}

export async function getCallData(): Promise<CallData[]> {
  const filePath = path.join(process.cwd(), 'public', 'mock-data.csv');
  const fileContent = await fs.promises.readFile(filePath, 'utf-8');
  const rows = fileContent.split('\n').slice(1);

  return rows.map((row) => {
    const [
      phone,
      campaign_name,
      total_recordings,
      first_call_time,
      last_call_time,
      ...recording_urls
    ] = row.split(',');

    return {
      phone,
      campaign_name,
      total_recordings: parseInt(total_recordings, 10),
      first_call_time,
      last_call_time,
      recording_urls,
    };
  });
}