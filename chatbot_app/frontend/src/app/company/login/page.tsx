"use client";

import { useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export default function CompanyLoginPage() {
  const router = useRouter();
  const params = useSearchParams();
  const nextPath = useMemo(() => params.get("next") || "/company", [params]);

  const [password, setPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState("");

  async function onSubmit() {
    setError("");
    setIsSubmitting(true);
    try {
      const res = await fetch("/api/company-auth", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Invalid password.");
      }
      router.replace(nextPath);
      router.refresh();
    } catch (e: any) {
      setError(e?.message || "Login failed.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="p-6 min-h-screen flex flex-col items-center justify-center">
      <div className="w-full max-w-md">
        <Card>
          <CardHeader>
            <CardTitle>Company Pitch Access</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="text-sm text-muted-foreground">
              Enter the password to access the company evaluation and pitch tools.
            </div>
            <Input
              type="password"
              placeholder="Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") onSubmit();
              }}
            />
            {error && <div className="text-sm text-red-500 whitespace-pre-wrap">{error}</div>}
            <div className="flex gap-2">
              <Button onClick={onSubmit} disabled={!password || isSubmitting} className="flex-1">
                {isSubmitting ? "Signing in…" : "Sign in"}
              </Button>
              <Link href="/">
                <Button variant="ghost">Cancel</Button>
              </Link>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

