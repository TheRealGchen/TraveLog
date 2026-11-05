"use client";

import type { TicketKind } from "@travel/client";
import {
  BugIcon,
  CircleHelpIcon,
  CrosshairIcon,
  EllipsisIcon,
  LightbulbIcon,
  MessageSquareTextIcon,
  XIcon,
} from "lucide-react";
import { useTheme } from "next-themes";
import { useParams, usePathname } from "next/navigation";
import { useEffect, useState } from "react";
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
import {
  type ContextChoice,
  type FeedbackElement,
  collectContext,
  elementFromDataset,
  lastElement,
  recordElement,
  recordPageError,
} from "@/lib/feedback";
import { useCreateTicket } from "@/lib/queries";

const KINDS: { value: TicketKind; label: string; icon: typeof BugIcon }[] = [
  { value: "bug", label: "Bug", icon: BugIcon },
  { value: "idea", label: "Idea", icon: LightbulbIcon },
  { value: "question", label: "Question", icon: CircleHelpIcon },
  { value: "other", label: "Other", icon: EllipsisIcon },
];

/** Marks UI that must not count as "the part of the page the feedback is about". */
const IGNORE = "[data-feedback-ignore]";

/** The nearest element tagged with `data-feedback` around an event target. */
function taggedElement(target: EventTarget | null): HTMLElement | null {
  if (!(target instanceof Element) || target.closest(IGNORE)) return null;
  return target.closest<HTMLElement>("[data-feedback]");
}

/**
 * A small button on every page that opens a feedback form. The form attaches what the app
 * already knows (the page, the part of it last touched, recent errors and failed requests, and
 * the records on screen); the person can remove any of it before sending.
 */
export function FeedbackButton() {
  const pathname = usePathname();
  const params = useParams();
  const { resolvedTheme } = useTheme();
  const createTicket = useCreateTicket();
  const [open, setOpen] = useState(false);
  const [picking, setPicking] = useState(false);
  const [body, setBody] = useState("");
  const [kind, setKind] = useState<TicketKind>("other");
  const [all, setAll] = useState<ContextChoice[]>([]);
  const [removed, setRemoved] = useState<Set<string>>(new Set());
  const choices = all.filter((c) => !removed.has(c.key));

  // Remember the tagged element the person last touched, and errors the page throws.
  useEffect(() => {
    function onPointerDown(event: PointerEvent) {
      const el = taggedElement(event.target);
      if (el) recordElement(elementFromDataset(el.dataset), window.location.pathname);
    }
    function onError(event: ErrorEvent) {
      recordPageError({ message: event.message, stack: event.error?.stack });
    }
    function onRejection(event: PromiseRejectionEvent) {
      const reason = event.reason;
      recordPageError({
        message: reason instanceof Error ? reason.message : String(reason),
        stack: reason instanceof Error ? reason.stack : undefined,
      });
    }
    document.addEventListener("pointerdown", onPointerDown, true);
    window.addEventListener("error", onError);
    window.addEventListener("unhandledrejection", onRejection);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown, true);
      window.removeEventListener("error", onError);
      window.removeEventListener("unhandledrejection", onRejection);
    };
  }, []);

  function gather(element: FeedbackElement | null) {
    return collectContext(
      {
        pathname,
        params: params ?? {},
        viewport: `${window.innerWidth}x${window.innerHeight}`,
        theme: resolvedTheme === "dark" || resolvedTheme === "light" ? resolvedTheme : undefined,
        build: process.env.NEXT_PUBLIC_BUILD || undefined,
      },
      element,
    );
  }

  function openForm() {
    setAll(gather(lastElement(pathname)));
    setRemoved(new Set());
    setOpen(true);
  }

  function picked(element: FeedbackElement | null) {
    setPicking(false);
    if (element) {
      recordElement(element, pathname);
      setAll(gather(element));
      // A newly picked element (and its record) is sent even if the old one was removed.
      setRemoved((r) => new Set([...r].filter((k) => k !== "element" && k !== `entity-${element.entityId}`)));
    }
    setOpen(true);
  }

  function submit(event: { preventDefault(): void }) {
    event.preventDefault();
    if (!body.trim()) return;
    createTicket.mutate(
      { body: body.trim(), kind, context: choices.map((c) => c.item) },
      {
        onSuccess: () => {
          toast.success("Thanks! Your feedback was sent.");
          setOpen(false);
          setBody("");
          setKind("other");
          recordElement(null, pathname);
        },
      },
    );
  }

  return (
    <>
      <Button
        data-feedback-ignore
        variant="outline"
        size="icon-lg"
        onClick={openForm}
        aria-label="Send feedback"
        title="Send feedback"
        className="fixed top-4 right-15 z-40 rounded-full bg-card/80 shadow-sm backdrop-blur"
      >
        <MessageSquareTextIcon />
      </Button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent data-feedback-ignore className="sm:max-w-lg">
          <form onSubmit={submit} className="grid gap-5">
            <DialogHeader>
              <DialogTitle>Send feedback</DialogTitle>
              <DialogDescription>
                What&apos;s broken, confusing, or missing? Where you were in the app is sent with it.
              </DialogDescription>
            </DialogHeader>

            <div className="flex flex-wrap gap-2" role="group" aria-label="Kind of feedback">
              {KINDS.map(({ value, label, icon: Icon }) => (
                <Button
                  key={value}
                  type="button"
                  size="sm"
                  variant={kind === value ? "default" : "outline"}
                  aria-pressed={kind === value}
                  onClick={() => setKind(value)}
                  className="rounded-full"
                >
                  <Icon />
                  {label}
                </Button>
              ))}
            </div>

            <div className="grid gap-2">
              <Label htmlFor="feedback-body">Your feedback</Label>
              <Textarea
                id="feedback-body"
                className="min-h-28"
                placeholder="The notes on an activity get cut off on my phone…"
                value={body}
                maxLength={10_000}
                onChange={(e) => setBody(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submit(e);
                }}
                autoFocus
                required
              />
            </div>

            <div className="grid gap-2">
              <div className="flex items-center justify-between gap-2">
                <Label>Sent with it</Label>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setOpen(false);
                    setPicking(true);
                  }}
                >
                  <CrosshairIcon />
                  Point at something
                </Button>
              </div>
              {choices.length ? (
                <ul className="flex flex-wrap gap-1.5" aria-label="Context sent with your feedback">
                  {choices.map((choice) => (
                    <li
                      key={choice.key}
                      className="flex max-w-full items-center gap-1 rounded-full border bg-muted/50 py-0.5 pr-0.5 pl-2.5 text-xs"
                    >
                      <span className="truncate">{choice.label}</span>
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon-xs"
                        className="rounded-full"
                        aria-label={`Don't send ${choice.label}`}
                        onClick={() => setRemoved((r) => new Set(r).add(choice.key))}
                      >
                        <XIcon />
                      </Button>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-xs text-muted-foreground">Nothing but your words.</p>
              )}
            </div>

            <DialogFooter>
              <Button type="submit" size="lg" disabled={!body.trim() || createTicket.isPending}>
                {createTicket.isPending ? "Sending…" : "Send feedback"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {picking && <ElementPicker onDone={picked} />}
    </>
  );
}

/**
 * Highlights tagged parts of the page under the pointer; a click picks one, Escape cancels.
 * Clicks are swallowed while picking so nothing on the page reacts.
 */
function ElementPicker({ onDone }: { onDone: (element: FeedbackElement | null) => void }) {
  const [box, setBox] = useState<DOMRect | null>(null);

  useEffect(() => {
    function swallow(event: Event) {
      if (event.target instanceof Element && event.target.closest(IGNORE)) return;
      event.preventDefault();
      event.stopPropagation();
    }
    function onMove(event: PointerEvent) {
      setBox(taggedElement(event.target)?.getBoundingClientRect() ?? null);
    }
    function onClick(event: MouseEvent) {
      if (event.target instanceof Element && event.target.closest(IGNORE)) return;
      swallow(event);
      const el = taggedElement(event.target);
      if (el) onDone(elementFromDataset(el.dataset));
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onDone(null);
    }
    const blocked = ["pointerdown", "mousedown", "pointerup", "mouseup"] as const;
    blocked.forEach((type) => document.addEventListener(type, swallow, true));
    document.addEventListener("pointermove", onMove, true);
    document.addEventListener("click", onClick, true);
    document.addEventListener("keydown", onKey, true);
    document.body.style.cursor = "crosshair";
    return () => {
      blocked.forEach((type) => document.removeEventListener(type, swallow, true));
      document.removeEventListener("pointermove", onMove, true);
      document.removeEventListener("click", onClick, true);
      document.removeEventListener("keydown", onKey, true);
      document.body.style.cursor = "";
    };
  }, [onDone]);

  return (
    <>
      {box && (
        <div
          aria-hidden
          className="pointer-events-none fixed z-50 rounded-xl border-2 border-primary bg-primary/10 transition-all duration-75"
          style={{ top: box.top - 4, left: box.left - 4, width: box.width + 8, height: box.height + 8 }}
        />
      )}
      <div
        data-feedback-ignore
        role="status"
        className="fixed inset-x-4 top-4 z-50 mx-auto flex max-w-md items-center justify-between gap-3 rounded-full border bg-card px-4 py-2 text-sm shadow-lg"
      >
        <span>Click the part of the page your feedback is about.</span>
        <Button size="sm" variant="ghost" onClick={() => onDone(null)}>
          Cancel
        </Button>
      </div>
    </>
  );
}
