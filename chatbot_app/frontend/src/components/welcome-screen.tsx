import { BarChart, DollarSign, Lightbulb } from "lucide-react";
import { PromptCard } from "@/components/prompt-card";
import { useEffect, useRef, useState } from "react";

interface WelcomeScreenProps {
  onPromptClick: (prompt: string) => void;
}

export function WelcomeScreen({ onPromptClick }: WelcomeScreenProps) {
  const [showPrompts, setShowPrompts] = useState(true);
  const [viewportWidth, setViewportWidth] = useState<number>(typeof window !== 'undefined' ? window.innerWidth : 0);
  const gridWrapperRef = useRef<HTMLDivElement | null>(null);

  // Hide the cards entirely when the available width can't fit 3 cards at standard sizing.
  // Threshold tuned so cards remain visible until roughly half-window widths on common screens.
  useEffect(() => {
    const MIN_VIEWPORT = 900; // show cards when viewport is approx >= half-width on typical screens
    const onResize = () => setViewportWidth(window.innerWidth);
    window.addEventListener("resize", onResize);
    // Initial
    onResize();

    return () => window.removeEventListener("resize", onResize);
  }, []);

  useEffect(() => {
    const MIN_VIEWPORT = 900;
    // Simple, reliable rule: toggle purely based on viewport width
    setShowPrompts(viewportWidth >= MIN_VIEWPORT);
  }, [viewportWidth]);
  const prompts = [
    {
      icon: <BarChart />,
      title: "What are the key positive signals in our calls?",
      description: "Identify moments of high customer interest and agreement in the campaign transcripts.",
      buttonText: "Analyze Positive Signals",
    },
    {
      icon: <DollarSign />,
      title: "What are the top objections in this campaign?",
      description: "Surface the most common objections and pain points to refine the sales script.",
      buttonText: "Find Top Objections",
    },
    {
      icon: <Lightbulb />,
      title: "Summarize the last 10 calls.",
      description: "Get a high-level summary of the most recent interactions to quickly gauge progress.",
      buttonText: "Summarize Recent Calls",
    },
  ];

  return (
    <div className="flex flex-col items-center justify-center h-full text-center px-4 py-8">
      <div className="text-3xl mb-2 bg-gradient-to-r from-blue-800 to-sky-400 dark:from-sky-300 dark:to-blue-200 text-transparent bg-clip-text p-2">Good Morning, Lorenz</div>
      <p className="text-muted-foreground mb-2">
        How can I help with your campaign analysis today?
      </p>
      <p className="text-sm text-muted-foreground mb-12">
        Campaign: <span className="font-semibold">Medlytics</span>
      </p>
      <div ref={gridWrapperRef} className="w-full max-w-4xl">
        {showPrompts && (
          <div className="grid grid-cols-3 gap-4">
            {prompts.map((prompt, index) => (
              <PromptCard
                key={index}
                icon={prompt.icon}
                title={prompt.title}
                description={prompt.description}
                buttonText={prompt.buttonText}
                onClick={() => onPromptClick(prompt.title)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}