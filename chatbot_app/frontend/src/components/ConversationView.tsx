"use client";

import React from 'react';

interface ConversationViewProps {
  transcription: string;
}

interface Turn {
  speaker: string;
  dialogue: string;
}

const ConversationView: React.FC<ConversationViewProps> = ({ transcription }) => {
  const parsedTurns = React.useMemo((): Turn[] => {
    if (!transcription) return [];
    // The string contains literal '\\n' characters.
    // We split by the newline, then process each segment.
    return transcription.split(/\\n/).flatMap(line => {
        if (line.trim() === '') return [];
        const match = line.match(/^\[(.*?)\]:\s*(.*)$/);
        if (match) {
          return [{ speaker: match[1], dialogue: match[2] }];
        }
        // This handles cases where a line might not have a speaker tag,
        // though the current prompt format should prevent this.
        return [{ speaker: 'UNKNOWN', dialogue: line }];
      });
  }, [transcription]);

  const getSpeakerStyle = (speaker: string) => {
    switch (speaker) {
      case 'AGENT':
        return 'justify-end';
      case 'DECISION_MAKER':
      case 'GATEKEEPER':
      case 'OTHER':
      default:
        return 'justify-start';
    }
  };

  const getBubbleStyle = (speaker: string) => {
    switch (speaker) {
      case 'AGENT':
        return 'bg-blue-500 text-white';
      case 'DECISION_MAKER':
        return 'bg-green-500 text-white';
      case 'GATEKEEPER':
        return 'bg-gray-300 dark:bg-gray-700 text-gray-800 dark:text-gray-200';
      case 'OTHER':
      default:
        return 'bg-gray-200 dark:bg-gray-600 text-gray-800 dark:text-gray-200';
    }
  };

  return (
    <div className="space-y-4">
      {parsedTurns.map((turn, index) => (
        <div key={index} className={`flex ${getSpeakerStyle(turn.speaker)}`}>
          <div
            className={`max-w-xs md:max-w-md lg:max-w-lg rounded-lg px-4 py-2 ${getBubbleStyle(
              turn.speaker
            )}`}
          >
            <p className="font-bold text-sm mb-1">{turn.speaker}</p>
            <p>{turn.dialogue}</p>
          </div>
        </div>
      ))}
    </div>
  );
};

export default ConversationView;