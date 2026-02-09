"use client";

import { Suspense, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";

// Backwards-compat: old link. Redirect to app-wide login.
function CompanyLoginRedirectInner() {
  const router = useRouter();
  const params = useSearchParams();

  useEffect(() => {
    const next = params.get("next") || "/company";
    router.replace(`/login?next=${encodeURIComponent(next)}`);
  }, [params, router]);

  return null;
}

export default function CompanyLoginRedirect() {
  return (
    <Suspense fallback={null}>
      <CompanyLoginRedirectInner />
    </Suspense>
  );
}

