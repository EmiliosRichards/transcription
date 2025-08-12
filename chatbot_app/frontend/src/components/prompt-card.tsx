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
    <Card className="flex flex-col text-left h-full bg-white/50 dark:bg-black/20 select-none">
      <CardHeader>
        {icon}
      </CardHeader>
      <CardContent className="flex-grow">
        <p className="font-semibold text-blue-900 dark:text-blue-200">{title}</p>
        <p className="text-sm text-muted-foreground">{description}</p>
      </CardContent>
      <CardFooter>
        <Button variant="outline" className="w-full whitespace-nowrap" onClick={onClick}>
          {buttonText}
        </Button>
      </CardFooter>
    </Card>
  );
}