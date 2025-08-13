"use client";

import { memo, useEffect, useMemo, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import { Button } from '@/components/ui/button';
import { useMediaReviewStore } from '@/lib/stores/useMediaReviewStore';
import { cn } from '@/lib/utils';

interface TranscriptViewerProps {
  heightClass?: string;
  extraActions?: React.ReactNode;
}

export default function TranscriptViewer({ heightClass = "h-[60vh]", extraActions }: TranscriptViewerProps) {
  const { vttCues, currentTime, setSeekToTime } = useMediaReviewStore();
  const [query, setQuery] = useState('');
  const [autoScroll, setAutoScroll] = useState(true);
  const [autoScrollSnoozed, setAutoScrollSnoozed] = useState(false);
  const snoozeTimeoutRef = useRef<number | null>(null);

  type DisplayCue = { start: number; end: number; speaker: string; text: string };
  const displayCues: DisplayCue[] = useMemo(() => {
    return vttCues.map(c => {
      const n = normalizeCueForDisplay(c);
      return { start: c.start, end: c.end, speaker: n.speaker, text: n.text };
    });
  }, [vttCues]);

  const activeInfo = useMemo(() => {
    const MIN_ACTIVE_WINDOW = 1.0; // seconds: force cues to be considered active for at least 1s
    const OVERLAP_EPS = 0.3;       // seconds: reduce highlight noise near exact boundaries
    if (!vttCues || vttCues.length === 0) return { indices: new Set<number>(), primary: -1 };
    const indices: number[] = [];
    for (let i = 0; i < vttCues.length; i++) {
      const c = vttCues[i];
      // Ensure every cue remains "active" for at least 1s from its start
      const activeUntil = Math.max(c.end - OVERLAP_EPS, c.start + MIN_ACTIVE_WINDOW);
      if (currentTime >= c.start && currentTime < activeUntil) {
        indices.push(i);
      }
    }
    const primary = indices.length > 0 ? indices[0] : -1;
    return { indices: new Set(indices), primary };
  }, [vttCues, currentTime]);

  const filteredIndices = useMemo(() => {
    if (!query.trim()) return displayCues.map((_, i) => i);
    const q = query.toLowerCase();
    return displayCues
      .map((c, i) => ({ c, i }))
      .filter(({ c }) =>
        c.text.toLowerCase().includes(q) || (c.speaker ? c.speaker.toLowerCase().includes(q) : false)
      )
      .map(({ i }) => i);
  }, [displayCues, query]);

  const containerRef = useRef<HTMLDivElement>(null);
  const itemRefs = useRef<(HTMLDivElement | null)[]>([]);
  const suppressNextScrollRef = useRef(false);
  const lingerUntilRef = useRef<Map<number, number>>(new Map());
  const LINGER_MS = 1000;

  const scrollActiveIntoView = () => {
    // If there is a filter, find the position of the active item within the filtered set
    const visibleIndex = filteredIndices.indexOf(activeInfo.primary);
    const targetIndex = visibleIndex >= 0 ? visibleIndex : -1;
    if (targetIndex >= 0 && itemRefs.current[targetIndex] && containerRef.current) {
      const el = itemRefs.current[targetIndex]!;
      const container = containerRef.current!;
      const elTop = el.offsetTop;
      const elBottom = elTop + el.offsetHeight;
      const viewTop = container.scrollTop;
      const viewBottom = viewTop + container.clientHeight;
      if (elTop < viewTop || elBottom > viewBottom) {
        suppressNextScrollRef.current = true;
        container.scrollTo({ top: elTop - container.clientHeight / 3, behavior: 'smooth' });
      }
    }
  };

  useEffect(() => {
    if (!autoScroll || autoScrollSnoozed) return;
    scrollActiveIntoView();
  }, [activeInfo.primary, filteredIndices, autoScroll, autoScrollSnoozed]);

  // Track a 1s linger for recently active indices to keep highlight visible
  useEffect(() => {
    const now = Date.now();
    activeInfo.indices.forEach((i) => {
      lingerUntilRef.current.set(i, now + LINGER_MS);
    });
  }, [activeInfo.indices]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const onScroll = () => {
      if (!autoScroll) return;
      if (suppressNextScrollRef.current) {
        // Ignore programmatic scrolls we just initiated
        suppressNextScrollRef.current = false;
        return;
      }
      setAutoScrollSnoozed(true);
      if (snoozeTimeoutRef.current) window.clearTimeout(snoozeTimeoutRef.current);
      snoozeTimeoutRef.current = window.setTimeout(() => {
        setAutoScrollSnoozed(false);
        scrollActiveIntoView();
      }, 6000);
    };
    container.addEventListener('scroll', onScroll, { passive: true });
    return () => {
      container.removeEventListener('scroll', onScroll as EventListener);
      if (snoozeTimeoutRef.current) window.clearTimeout(snoozeTimeoutRef.current);
    };
  }, [autoScroll, filteredIndices, activeInfo.primary]);

  if (!vttCues || vttCues.length === 0) {
    return <div className="text-sm text-gray-500">Load a VTT file to see transcript.</div>;
  }

  return (
    <div className="w-full">
      <div className="mb-2 flex items-center gap-2">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search transcript..."
          className="flex-1 px-3 py-2 text-sm border rounded-md bg-white dark:bg-gray-900"
        />
        <Button
          variant="ghost"
          size="sm"
          className={"rounded-full bg-gradient-to-br from-gray-100 to-gray-200 text-gray-800 hover:from-gray-200 hover:to-gray-300 dark:from-gray-800 dark:to-gray-700 dark:text-gray-100 dark:hover:from-gray-700 dark:hover:to-gray-600 shadow-sm"}
          onClick={() => setAutoScroll((v) => !v)}
        >
          Auto-scroll: {autoScroll ? 'On' : 'Off'}
        </Button>
        {extraActions}
      </div>
      <div ref={containerRef} className={cn("w-full overflow-y-auto overflow-x-hidden p-3 border rounded-md bg-white dark:bg-gray-900", heightClass)}>
        <div className="flex flex-col divide-y divide-gray-200 dark:divide-gray-800">
          {filteredIndices.map((origIdx, i) => {
            const c = displayCues[origIdx];
            const now = Date.now();
            const isActive = activeInfo.indices.has(origIdx) || (lingerUntilRef.current.get(origIdx) ?? 0) > now;
            return (
              <TranscriptRow
                key={`${c.start}-${origIdx}`}
                refSetter={(el) => { itemRefs.current[i] = el; }}
                cue={c}
                isActive={isActive}
                isOverlapping={isActive && activeInfo.indices.size > 1}
                autoScroll={autoScroll}
                onClick={() => setSeekToTime(c.start)}
              />
            );
          })}
        </div>
      </div>
    </div>
  );
}

function formatTime(t: number) {
  const s = Math.max(0, Math.round(t));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${String(m).padStart(2, '0')}:${String(r).padStart(2, '0')}`;
}

function getSpeakerBadgeClass(speaker: string) {
  const palette = [
    "bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-100",
    "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-100",
    "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-100",
    "bg-violet-100 text-violet-800 dark:bg-violet-900/40 dark:text-violet-100",
    "bg-sky-100 text-sky-800 dark:bg-sky-900/40 dark:text-sky-100",
  ];
  let hash = 0;
  for (let i = 0; i < speaker.length; i++) {
    hash = (hash * 31 + speaker.charCodeAt(i)) >>> 0;
  }
  return palette[hash % palette.length];
}

function normalizeCueForDisplay(c: { text: string; speaker?: string }) {
  let speaker = c.speaker?.trim() || '';
  let text = c.text || '';

  // Voice-tag: <v ...> ... </v>
  const voiceOpen = text.match(/<v\s+([^>]+)>/i);
  if (voiceOpen) {
    const raw = voiceOpen[1].trim();
    const withoutClasses = raw.replace(/^\.[^ ]*\s*/, '').trim();
    if (withoutClasses.length > 0) speaker = speaker || withoutClasses;
  }
  // Strip any HTML-like tags remaining
  text = text.replace(/<[^>]+>/g, '').trim();

  // [SPEAKER] Text
  if (!speaker) {
    const m = text.match(/^\s*\[([^\]]+)\]\s*(.*)$/);
    if (m) {
      speaker = m[1].trim();
      text = m[2].trim();
    }
  }
  // SPEAKER: Text
  if (!speaker) {
    const m = text.match(/^\s*([^:]{1,40}):\s*(.*)$/);
    if (m) {
      speaker = m[1].trim();
      text = m[2].trim();
    }
  }
  return { speaker, text };
}

interface TranscriptRowProps {
  cue: { start: number; end: number; speaker: string; text: string };
  isActive: boolean;
  isOverlapping: boolean;
  autoScroll: boolean;
  onClick: () => void;
  refSetter: (el: HTMLDivElement | null) => void;
}

const TranscriptRow = memo(function TranscriptRow({ cue, isActive, isOverlapping, autoScroll, onClick, refSetter }: TranscriptRowProps) {
  return (
    <div
      ref={refSetter}
      className={cn(
        "relative p-3 cursor-pointer rounded-md transition-colors duration-300 hover:bg-gray-50 dark:hover:bg-gray-800/60"
      )}
      onClick={onClick}
    >
      <motion.div
        className="pointer-events-none absolute inset-0 rounded-md bg-blue-50 dark:bg-blue-900/30"
        initial={false}
        animate={{ opacity: isActive ? 1 : 0 }}
        transition={{ duration: 0.25, ease: 'easeOut' }}
      />
      <div className="flex items-start gap-2">
        <div className="flex-1">
          <div className="flex items-center justify-between mb-1">
            <div className="flex items-center gap-2">
              {cue.speaker && (
                <span className={cn(
                  "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
                  isActive ? "bg-blue-100 text-blue-800 dark:bg-blue-800/50 dark:text-blue-100" : getSpeakerBadgeClass(cue.speaker)
                )}>
                  {cue.speaker}
                </span>
              )}
            </div>
            <span className="text-[10px] text-gray-500">{formatTime(cue.start)}–{formatTime(cue.end)}</span>
          </div>
          <div className="flex items-start gap-2">
            <div className={cn(
              "mt-[6px] h-2 w-2 rounded-full transition-colors duration-200 flex-shrink-0",
              isActive ? "bg-blue-500" : "bg-gray-300 dark:bg-gray-600"
            )} />
            <div className={cn(
              "text-sm leading-6 relative z-10 transition-all duration-200 break-words",
              isActive ? "text-gray-900 dark:text-gray-50" : "text-gray-800 dark:text-gray-200",
              autoScroll && !isActive ? "opacity-60 blur-[0.5px]" : ""
            )}>{cue.text}</div>
          </div>
          {isOverlapping && (
            <div className="mt-1 text-[10px] text-blue-600 dark:text-blue-300 relative z-10">Simultaneous speech</div>
          )}
        </div>
      </div>
    </div>
  );
});


