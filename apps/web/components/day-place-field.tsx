"use client";

import type { Location } from "@travel/client";
import { useState } from "react";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

/**
 * An always-editable place (lodging or start location). Saves on Enter or when it loses focus;
 * clearing the text clears the place. Remount it (via `key`) when the server value changes.
 */
export function DayPlaceField({
  id,
  label,
  icon,
  placeholder,
  value,
  onSave,
}: {
  id: string;
  label: string;
  icon: React.ReactNode;
  placeholder: string;
  value: Location | null;
  onSave: (value: Location | null) => void;
}) {
  const [text, setText] = useState(value?.name ?? "");

  function save() {
    const name = text.trim();
    if (name === (value?.name ?? "")) return;
    onSave(name ? { name } : null);
  }

  return (
    <div className="grid gap-2 rounded-2xl border bg-card p-4 shadow-sm">
      <Label htmlFor={id} className="flex items-center gap-2 text-muted-foreground">
        {icon}
        {label}
      </Label>
      <Input
        id={id}
        value={text}
        placeholder={placeholder}
        onChange={(e) => setText(e.target.value)}
        onBlur={save}
        onKeyDown={(e) => {
          if (e.key === "Enter") e.currentTarget.blur();
          if (e.key === "Escape") setText(value?.name ?? "");
        }}
        className="h-11 border-0 bg-transparent px-0 text-lg font-medium shadow-none focus-visible:ring-0"
      />
    </div>
  );
}
