import { BarChart, DollarSign, Lightbulb } from "lucide-react";
import { PromptCard } from "@/components/prompt-card";

interface WelcomeScreenProps {
  onPromptClick: (prompt: string) => void;
}

export function WelcomeScreen({ onPromptClick }: WelcomeScreenProps) {
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
      <div className="text-3xl mb-2 bg-gradient-to-r from-blue-900 to-blue-500 text-transparent bg-clip-text p-2">Good Morning, Lorenz</div>
      <p className="text-muted-foreground mb-2">
        How can I help with your campaign analysis today?
      </p>
      <p className="text-sm text-muted-foreground mb-12">
        Campaign: <span className="font-semibold">Medlytics</span>
      </p>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 w-full max-w-4xl">
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
    </div>
  );
}