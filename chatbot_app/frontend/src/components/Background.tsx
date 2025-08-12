"use client";

import React, { useEffect, useState } from "react";
import { useTheme } from "next-themes";

/**
 * AppBackground renders a full-viewport background with a subtle image + gradient overlay.
 *
 * Drop optional files `public/bg-light.jpg` and `public/bg-dark.jpg` to customize the look.
 * If those files are missing, the gradient alone provides a pleasing backdrop.
 */
export function AppBackground(): JSX.Element | null {
  const { resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  // Avoid hydration mismatches by rendering only on the client
  if (!mounted) return null;

  const isDark = resolvedTheme === "dark";

  // Use project image as the background. Remove optional bg-light/dark variants to avoid 404s.
  const defaultImage = "/pastel-gradient-background-etu0z7lbeebg6mlf.jpg";

  // Layered gradients for atmosphere; tuned for light/dark.
  const gradientTop = isDark
    ? "radial-gradient(1200px 600px at 80% 10%, rgba(120,119,198,0.28), transparent 60%)"
    : "radial-gradient(1200px 600px at 80% 10%, rgba(59,130,246,0.28), transparent 60%)";

  const gradientBottom = isDark
    ? "radial-gradient(900px 500px at 20% 85%, rgba(2,6,23,0.65), transparent 60%)"
    : "radial-gradient(900px 500px at 20% 85%, rgba(255,255,255,0.7), transparent 60%)";

  const colorWash = isDark
    ? "linear-gradient(to bottom right, rgba(2,6,23,0.75), rgba(2,6,23,0.25))"
    : "linear-gradient(to bottom right, rgba(255,255,255,0.85), rgba(255,255,255,0.35))";

  // Compose backgrounds: overlay gradients first, then image.
  const backgroundImage = `${gradientTop}, ${gradientBottom}, ${colorWash}, url(${defaultImage})`;

  return (
    <div
      aria-hidden
      className="pointer-events-none fixed inset-0 -z-10 bg-cover bg-center"
      style={{
        backgroundImage,
        // Gentle vignette to focus content area and avoid harsh edges on large screens
        WebkitMaskImage:
          "radial-gradient(1600px 800px at 50% 30%, black 60%, transparent 100%)",
        maskImage:
          "radial-gradient(1600px 800px at 50% 30%, black 60%, transparent 100%)",
      }}
    />
  );
}

export default AppBackground;


