"use client";

import { Suspense, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

function LoginInner() {
  const router = useRouter();
  const params = useSearchParams();
  const nextPath = useMemo(() => params.get("next") || "/", [params]);

  const [username, setUsername] = useState("guest");
  const [password, setPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState("");

  async function onSubmit() {
    setError("");
    setIsSubmitting(true);
    try {
      const res = await fetch("/api/auth", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Invalid credentials.");
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
            <CardTitle>Sign in</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="text-sm text-muted-foreground">
              Enter the shared credentials to access the app.
            </div>
            <div className="space-y-2">
              <Input
                placeholder="Username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
              />
              <Input
                type="password"
                placeholder="Password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") onSubmit();
                }}
                autoComplete="current-password"
              />
            </div>
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

export default function LoginPage() {
  return (
    <Suspense
      fallback={
        <div className="p-6 min-h-screen flex flex-col items-center justify-center">
          <div className="w-full max-w-md text-sm text-muted-foreground">Loading…</div>
        </div>
      }
    >
      <LoginInner />
    </Suspense>
  );
}

