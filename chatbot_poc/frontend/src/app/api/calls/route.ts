import { getCallData } from '@/lib/data';
import { NextResponse } from 'next/server';

export async function GET() {
  const data = await getCallData();
  return NextResponse.json(data);
}