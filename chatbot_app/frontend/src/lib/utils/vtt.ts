import { VttCue } from '@/lib/stores/useMediaReviewStore';

const TIME_PATTERN = /(?:(\d{2}):)?(\d{2}):(\d{2})[\.,](\d{3})/;

function parseTimestampToSeconds(ts: string): number {
  const match = ts.match(TIME_PATTERN);
  if (!match) return 0;
  const hasHours = !!match[1];
  const hours = hasHours ? parseInt(match[1]!, 10) : 0;
  const minutes = parseInt(match[2]!, 10);
  const seconds = parseInt(match[3]!, 10);
  const millis = parseInt(match[4]!, 10);
  return hours * 3600 + minutes * 60 + seconds + millis / 1000;
}

export function parseWebVttToCues(vttText: string): VttCue[] {
  const lines = vttText.split(/\r?\n/);
  const cues: VttCue[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i].trim();
    // Find timecode line like: 00:00:01.000 --> 00:00:03.000
    if (line.includes('-->')) {
      const [startRaw, endRaw] = line.split('-->').map((s) => s.trim());
      const start = parseTimestampToSeconds(startRaw);
      const end = parseTimestampToSeconds(endRaw);
      i++;
      const textLines: string[] = [];
      while (i < lines.length && lines[i].trim() !== '') {
        textLines.push(lines[i]);
        i++;
      }
      const rawText = textLines.join(' ').trim();
      // Attempt speaker extraction in common formats:
      // 1) WebVTT voice tags: <v Speaker Name>Text
      // 2) [SPEAKER] Text
      // 3) SPEAKER: Text
      let speaker: string | undefined;
      let text = rawText;

      const voiceTagMatch = rawText.match(/^\s*<v\s+([^>]+)>([\s\S]*)$/i);
      if (voiceTagMatch) {
        speaker = voiceTagMatch[1].trim();
        text = voiceTagMatch[2].trim();
      } else {
        const bracketMatch = rawText.match(/^\s*\[([^\]]+)\]\s*(.*)$/);
        const colonMatch = rawText.match(/^\s*([^:]{1,40}):\s*(.*)$/);
        if (bracketMatch) {
          speaker = bracketMatch[1].trim();
          text = bracketMatch[2].trim();
        } else if (colonMatch) {
          speaker = colonMatch[1].trim();
          text = colonMatch[2].trim();
        }
      }

      // Strip any remaining simple HTML/VTT tags from text
      text = text.replace(/<[^>]+>/g, '').trim();
      cues.push({ start, end, text, speaker });
    }
    i++;
  }

  return cues;
}


