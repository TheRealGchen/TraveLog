"use client";

import { AlertCircleIcon } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/lib/api";
import { useAddTravelers } from "@/lib/queries";
import { errorsByRow, parseTravelerLines } from "@/lib/travelers";
import { cn } from "@/lib/utils";

function submitLabel(count: number): string {
  if (count === 0) return "Add travelers";
  return `Add ${count} traveler${count === 1 ? "" : "s"}`;
}

/** Paste one traveler per line; the API validates the whole batch (all or nothing). */
export function BulkTravelersDialog({
  tripId,
  open,
  onOpenChange,
}: {
  tripId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [text, setText] = useState("");
  const [errors, setErrors] = useState<Map<number, string[]>>(new Map());
  const add = useAddTravelers(tripId);
  const rows = parseTravelerLines(text);

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (rows.length === 0) return;
    add.mutate(rows, {
      onSuccess: () => {
        toast.success(`Added ${rows.length} traveler${rows.length === 1 ? "" : "s"}`);
        setText("");
        setErrors(new Map());
        onOpenChange(false);
      },
      onError: (error) => {
        if (error instanceof ApiError && error.status === 422) {
          setErrors(errorsByRow(error.problem?.errors ?? [{ path: "", message: error.message }]));
        }
      },
    });
  }

  const general = errors.get(-1);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-2xl">
        <form onSubmit={submit} className="grid gap-5">
          <DialogHeader>
            <DialogTitle>Add multiple travelers</DialogTitle>
            <DialogDescription>
              One per line: <span className="font-mono">Name, email, passport</span>. Email and
              passport are optional. Rows pasted from a spreadsheet work too.
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-2">
            <Label htmlFor="bulk-travelers">Travelers</Label>
            <Textarea
              id="bulk-travelers"
              rows={6}
              className="font-mono text-sm"
              placeholder={"Sam Lee, sam@example.com, X12345678\nAna Ruiz, ana@example.com\nKai"}
              value={text}
              onChange={(e) => {
                setText(e.target.value);
                setErrors(new Map());
              }}
              autoFocus
            />
          </div>

          {general && (
            <p className="flex items-start gap-2 text-sm text-destructive">
              <AlertCircleIcon className="mt-0.5 size-4 shrink-0" />
              {general.join("; ")}
            </p>
          )}

          {rows.length > 0 && (
            <div className="overflow-x-auto rounded-xl border">
              <table className="w-full text-sm" aria-label="Preview">
                <thead className="bg-muted/60 text-left text-muted-foreground">
                  <tr>
                    <th className="px-3 py-2 font-medium">#</th>
                    <th className="px-3 py-2 font-medium">Name</th>
                    <th className="px-3 py-2 font-medium">Email</th>
                    <th className="px-3 py-2 font-medium">Passport</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row, i) => {
                    const rowErrors = errors.get(i);
                    return (
                      <tr
                        key={i}
                        className={cn("border-t align-top", rowErrors && "bg-destructive/5")}
                      >
                        <td className="px-3 py-2 text-muted-foreground tabular-nums">{i + 1}</td>
                        <td className="px-3 py-2 font-medium">
                          {row.name || <span className="text-muted-foreground">(no name)</span>}
                          {rowErrors && (
                            <ul className="mt-1 space-y-0.5 text-xs font-normal text-destructive">
                              {rowErrors.map((message) => (
                                <li key={message}>{message}</li>
                              ))}
                            </ul>
                          )}
                        </td>
                        <td className="px-3 py-2">{row.email ?? "—"}</td>
                        <td className="px-3 py-2 font-mono">{row.passportNumber ?? "—"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          <DialogFooter>
            <Button type="submit" size="lg" disabled={rows.length === 0 || add.isPending}>
              {add.isPending ? "Adding…" : submitLabel(rows.length)}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
