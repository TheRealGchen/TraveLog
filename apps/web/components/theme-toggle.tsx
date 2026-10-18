"use client";

import { MoonIcon, SunIcon } from "lucide-react";
import { useTheme } from "next-themes";

import { Button } from "@/components/ui/button";

/**
 * Switches between light and dark. The theme follows the OS until you pick one; the choice is
 * remembered in this browser. Icons are swapped with CSS, so server and client render the same.
 */
export function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  return (
    <Button
      variant="outline"
      size="icon-lg"
      aria-label="Toggle dark mode"
      title="Toggle dark mode"
      onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
      className="fixed top-4 right-4 z-40 rounded-full bg-card/80 shadow-sm backdrop-blur"
    >
      <SunIcon className="dark:hidden" />
      <MoonIcon className="hidden dark:block" />
    </Button>
  );
}
