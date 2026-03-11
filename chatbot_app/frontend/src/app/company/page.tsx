"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Loader2 } from "lucide-react";

type EvalResponse = {
  input_url: string;
  company_name: string;
  score: number;
  confidence: "low" | "medium" | "high" | string;
  reasoning: string;
  positives?: string[] | null;
  concerns?: string[] | null;
  fit_attributes?: Record<string, any> | null;
  description?: string | null;
};

type PitchResponse = {
  matched_partner_name: string;
  sales_pitch: string;
  match_reasoning: string[] | string;
};

function clamp(n: number, min: number, max: number) {
  return Math.max(min, Math.min(max, n));
}

export default function CompanyPage() {
  const [url, setUrl] = useState<string>("");
  const [evalResult, setEvalResult] = useState<EvalResponse | null>(null);
  const [pitchResult, setPitchResult] = useState<PitchResponse | null>(null);
  const [isEvaluating, setIsEvaluating] = useState(false);
  const [isPitching, setIsPitching] = useState(false);
  const [error, setError] = useState<string>("");
  const [copied, setCopied] = useState(false);
  const [pitchTemplate, setPitchTemplate] = useState<"classic" | "bullets">("bullets");

  const scorePct = useMemo(() => {
    if (!evalResult) return 0;
    return clamp((Number(evalResult.score) / 10) * 100, 0, 100);
  }, [evalResult]);

  async function onEvaluate() {
    const trimmed = url.trim();
    if (!trimmed) return;
    setError("");
    setCopied(false);
    setPitchResult(null);
    setIsEvaluating(true);
    try {
      const res = await fetch("/api/company/evaluate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: trimmed, include_description: true }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Company evaluation failed.");
      }
      const data = (await res.json()) as EvalResponse;
      setEvalResult(data);
    } catch (e: any) {
      setEvalResult(null);
      setError(e?.message || "Company evaluation failed.");
    } finally {
      setIsEvaluating(false);
    }
  }

  async function onGeneratePitch() {
    if (!evalResult) return;
    setError("");
    setCopied(false);
    setIsPitching(true);
    try {
      const res = await fetch("/api/company/pitch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: url.trim() || evalResult.input_url,
          company_name: evalResult.company_name || "",
          description: evalResult.description || null,
          eval_positives: Array.isArray(evalResult.positives) ? evalResult.positives : [],
          eval_concerns: Array.isArray(evalResult.concerns) ? evalResult.concerns : [],
          fit_attributes: evalResult.fit_attributes && typeof evalResult.fit_attributes === "object" ? evalResult.fit_attributes : {},
          pitch_template: pitchTemplate,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Pitch generation failed.");
      }
      const data = (await res.json()) as PitchResponse;
      setPitchResult(data);
    } catch (e: any) {
      setPitchResult(null);
      setError(e?.message || "Pitch generation failed.");
    } finally {
      setIsPitching(false);
    }
  }

  async function onCopyPitch() {
    if (!pitchResult?.sales_pitch) return;
    try {
      await navigator.clipboard.writeText(pitchResult.sales_pitch);
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    } catch (e) {
      setCopied(false);
    }
  }

  return (
    <div className="p-6 min-h-screen flex flex-col items-center">
      <div className="w-full max-w-4xl">
        <div className="flex justify-between items-center mb-6">
          <h1 className="text-3xl text-gray-800 dark:text-white">Company Evaluation & Sales Pitch</h1>
          <div className="flex gap-2">
            <Link href="/">
              <Button
                variant="ghost"
                className="rounded-full bg-gradient-to-br from-gray-100 to-gray-200 text-gray-800 hover:from-gray-200 hover:to-gray-300 dark:from-gray-800 dark:to-gray-700 dark:text-gray-100 dark:hover:from-gray-700 dark:hover:to-gray-600 shadow-sm"
                size="sm"
              >
                Back
              </Button>
            </Link>
          </div>
        </div>

        <Card className="w-full">
          <CardHeader>
            <CardTitle>1) Evaluate a company</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <div className="text-sm text-muted-foreground">
              Paste a company website URL. We’ll evaluate fit (0–10) and explain why.
            </div>
            <form
              className="flex flex-col md:flex-row gap-3"
              onSubmit={(e) => {
                e.preventDefault();
                if (!url.trim() || isEvaluating) return;
                onEvaluate();
              }}
            >
              <Input
                placeholder="https://company.com"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
              />
              <Button
                type="submit"
                disabled={!url.trim() || isEvaluating}
                variant="ghost"
                className="rounded-full bg-gradient-to-br from-gray-100 to-gray-200 text-gray-800 hover:from-gray-200 hover:to-gray-300 dark:from-gray-800 dark:to-gray-700 dark:text-gray-100 dark:hover:from-gray-700 dark:hover:to-gray-600 shadow-sm"
              >
                {isEvaluating ? "Evaluating..." : "Evaluate"}
              </Button>
            </form>

            {isEvaluating && (
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                <div>Researching and scoring…</div>
              </div>
            )}

            {evalResult && (
              <Card className="border-gray-200/60 dark:border-gray-800/60">
                <CardHeader>
                  <CardTitle className="text-base">Result</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-2">
                    <div className="text-sm">
                      <span className="font-medium">Company:</span>{" "}
                      <span className="text-muted-foreground">{evalResult.company_name || "Unknown"}</span>
                    </div>
                    <div className="text-sm">
                      <span className="font-medium">Confidence:</span>{" "}
                      <span className="text-muted-foreground">{evalResult.confidence}</span>
                    </div>
                  </div>

                  <div className="space-y-1">
                    <div className="flex items-center justify-between text-sm">
                      <span className="font-medium">Score</span>
                      <span className="text-muted-foreground">{Number(evalResult.score).toFixed(1)} / 10</span>
                    </div>
                    <Progress value={scorePct} className="w-full [&>div]:bg-blue-500" />
                  </div>

                  <div className="text-sm">
                    <div className="font-medium">Zusammenfassung:</div>
                    <div className="mt-1 whitespace-pre-wrap text-muted-foreground">{evalResult.reasoning}</div>

                    {Array.isArray(evalResult.positives) && evalResult.positives.length > 0 && (
                      <div className="mt-3">
                        <div className="font-medium">Positive Punkte:</div>
                        <ul className="list-disc ml-5 mt-1 space-y-1 text-muted-foreground">
                          {evalResult.positives.map((p, i) => (
                            <li key={i}>{p}</li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {Array.isArray(evalResult.concerns) && evalResult.concerns.length > 0 && (
                      <div className="mt-3">
                        <div className="font-medium">Bedenken / offene Fragen:</div>
                        <ul className="list-disc ml-5 mt-1 space-y-1 text-muted-foreground">
                          {evalResult.concerns.map((c, i) => (
                            <li key={i}>{c}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>

                  {evalResult.description && (
                    <details className="text-sm">
                      <summary className="cursor-pointer text-muted-foreground">Company description (used for matching)</summary>
                      <div className="mt-2 whitespace-pre-wrap">{evalResult.description}</div>
                    </details>
                  )}
                </CardContent>
              </Card>
            )}
          </CardContent>
        </Card>

        <Card className="w-full mt-6">
          <CardHeader>
            <CardTitle>2) Generate a sales pitch</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <div className="text-sm text-muted-foreground">
              This compares the company to our “golden partners” and generates a pitch you can copy.
            </div>
            <div className="text-sm">
              <div className="font-medium mb-2">Pitch template</div>
              <div className="flex flex-col gap-2">
                <label className="flex items-start gap-2 cursor-pointer">
                  <input
                    type="radio"
                    name="pitchTemplate"
                    value="classic"
                    checked={pitchTemplate === "classic"}
                    onChange={() => setPitchTemplate("classic")}
                    disabled={isPitching}
                    className="mt-1"
                  />
                  <div>
                    <div>Classic (2 sentences + CTA)</div>
                    <div className="text-xs text-muted-foreground">
                      “Wir haben … telefoniert … dort generieren wir aktuell etwa X Leads pro Tag.”
                    </div>
                  </div>
                </label>
                <label className="flex items-start gap-2 cursor-pointer">
                  <input
                    type="radio"
                    name="pitchTemplate"
                    value="bullets"
                    checked={pitchTemplate === "bullets"}
                    onChange={() => setPitchTemplate("bullets")}
                    disabled={isPitching}
                    className="mt-1"
                  />
                  <div>
                    <div>Bullets (current)</div>
                    <div className="text-xs text-muted-foreground">Intro + bullet proof points + closing paragraph.</div>
                  </div>
                </label>
              </div>
            </div>
            <div className="flex gap-3">
              <Button
                onClick={onGeneratePitch}
                disabled={!evalResult || isPitching}
                variant="ghost"
                className="rounded-full bg-gradient-to-br from-gray-100 to-gray-200 text-gray-800 hover:from-gray-200 hover:to-gray-300 dark:from-gray-800 dark:to-gray-700 dark:text-gray-100 dark:hover:from-gray-700 dark:hover:to-gray-600 shadow-sm"
              >
                {isPitching ? "Generating..." : "Generate pitch"}
              </Button>
            </div>

            {isPitching && (
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                <div>Generating pitch…</div>
              </div>
            )}

            {pitchResult && (
              <Card className="border-gray-200/60 dark:border-gray-800/60">
                <CardHeader>
                  <CardTitle className="text-base">Pitch output</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  {(() => {
                    const matched = (pitchResult.matched_partner_name || "").trim();
                    const hasMatch = matched && matched.toLowerCase() !== "no suitable match found";
                    const rationaleLabel = hasMatch ? "Match reasoning:" : "Pitch rationale:";
                    return (
                      <>
                  <div className="text-sm">
                    <span className="font-medium">Golden partner match:</span>{" "}
                    <span className="text-muted-foreground">{pitchResult.matched_partner_name || "—"}</span>
                  </div>

                  <div className="text-sm">
                    <span className="font-medium">{rationaleLabel}</span>
                    <ul className="list-disc ml-5 mt-1 space-y-1 text-muted-foreground">
                      {Array.isArray(pitchResult.match_reasoning)
                        ? pitchResult.match_reasoning.map((r, i) => <li key={i}>{r}</li>)
                        : <li>{pitchResult.match_reasoning}</li>}
                    </ul>
                  </div>
                      </>
                    );
                  })()}

                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <div className="text-sm font-medium">Sales pitch</div>
                      <Button onClick={onCopyPitch} size="sm" variant="outline" disabled={!pitchResult.sales_pitch}>
                        {copied ? "Copied" : "Copy"}
                      </Button>
                    </div>
                    <textarea
                      value={pitchResult.sales_pitch || ""}
                      readOnly
                      className="w-full min-h-[320px] resize-y rounded-md border border-gray-200/60 dark:border-gray-800/60 bg-transparent p-3 text-sm"
                    />
                  </div>
                </CardContent>
              </Card>
            )}
          </CardContent>
        </Card>

        {error && (
          <Card className="w-full mt-6 border-red-300/40">
            <CardHeader>
              <CardTitle className="text-red-400">Error</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-red-300 whitespace-pre-wrap">{error}</p>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}

