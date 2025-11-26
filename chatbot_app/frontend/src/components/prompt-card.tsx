import { Button } from "./ui/button";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "./ui/card";

interface PromptCardProps {
  icon: React.ReactNode;
  title: string;
  description: string;
  buttonText: string;
  onClick: () => void;
}

export function PromptCard({ icon, title, description, buttonText, onClick }: PromptCardProps) {
  return (
    <Card className="relative flex flex-col text-left h-full bg-white/50 dark:bg-black/20 select-none hover:cursor-not-allowed" aria-disabled="true">
      <CardHeader>
        {icon}
      </CardHeader>
      <CardContent className="flex-grow">
        <p className="font-semibold text-blue-900 dark:text-blue-200">{title}</p>
        <p className="text-sm text-muted-foreground">{description}</p>
      </CardContent>
      <CardFooter>
        <Button variant="outline" className="w-full whitespace-nowrap hover:cursor-not-allowed" onClick={onClick}>
          {buttonText}
        </Button>
      </CardFooter>
      <div
        className="absolute inset-0 z-10 cursor-not-allowed"
        title="Temporarily disabled"
        aria-hidden="true"
        onClick={(e) => { e.preventDefault(); e.stopPropagation(); }}
        onMouseDown={(e) => { e.preventDefault(); e.stopPropagation(); }}
      />
    </Card>
  );
}