"use client";

import type { PinnedLink, Trip } from "@travel/client";
import { GlobeIcon, PencilIcon, PinIcon } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useAddLink, useRemoveLink, useUpdateLink } from "@/lib/queries";

function host(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

/** Pinned links as a row of chips, with a button to pin another. */
export function LinkChips({ trip }: { trip: Trip }) {
  return (
    <div
      className="-mx-1 flex gap-3 overflow-x-auto px-1 pt-1 pb-2 sm:flex-wrap sm:overflow-visible"
      aria-label="Pinned links"
    >
      {trip.links.map((link) => (
        <LinkChip key={link.id} tripId={trip.id} link={link} />
      ))}
      <PinLink tripId={trip.id} />
    </div>
  );
}

/** The page's preview image, else its icon, else a globe; images load from the source site. */
function Thumbnail({ link }: { link: PinnedLink }) {
  const [imageFailed, setImageFailed] = useState(false);
  const [iconFailed, setIconFailed] = useState(false);
  if (link.imageUrl && !imageFailed) {
    return (
      // eslint-disable-next-line @next/next/no-img-element -- arbitrary third-party hosts
      <img
        src={link.imageUrl}
        alt=""
        loading="lazy"
        referrerPolicy="no-referrer"
        onError={() => setImageFailed(true)}
        className="h-12 w-20 shrink-0 rounded-lg bg-muted object-cover"
      />
    );
  }
  return (
    <span className="flex size-12 shrink-0 items-center justify-center rounded-lg bg-muted">
      {link.iconUrl && !iconFailed ? (
        // eslint-disable-next-line @next/next/no-img-element -- arbitrary third-party hosts
        <img
          src={link.iconUrl}
          alt=""
          loading="lazy"
          referrerPolicy="no-referrer"
          onError={() => setIconFailed(true)}
          className="size-6"
        />
      ) : (
        <GlobeIcon className="size-5 text-muted-foreground" />
      )}
    </span>
  );
}

function LinkChip({ tripId, link }: { tripId: string; link: PinnedLink }) {
  const label = link.title ?? link.pageTitle ?? host(link.url);
  return (
    <div className="group relative shrink-0">
      <a
        href={link.url}
        target="_blank"
        rel="noopener noreferrer"
        title={link.url}
        className="flex h-16 max-w-72 items-center gap-3 rounded-2xl border bg-card py-2 pr-9 pl-2 shadow-sm transition-shadow outline-none hover:shadow-md focus-visible:ring-3 focus-visible:ring-ring/60"
      >
        <Thumbnail link={link} />
        <span className="min-w-0">
          <span className="block truncate text-sm font-semibold">{label}</span>
          <span className="block truncate text-xs text-muted-foreground">{host(link.url)}</span>
        </span>
      </a>
      <EditLink tripId={tripId} link={link} />
    </div>
  );
}

function EditLink({ tripId, link }: { tripId: string; link: PinnedLink }) {
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState(link.title ?? "");
  const [url, setUrl] = useState(link.url);
  const update = useUpdateLink(tripId);
  const remove = useRemoveLink(tripId);

  function save(event: React.FormEvent) {
    event.preventDefault();
    const body: { title?: string | null; url?: string } = {};
    if ((title.trim() || null) !== link.title) body.title = title.trim() || null;
    if (url.trim() && url.trim() !== link.url) body.url = url.trim();
    if (Object.keys(body).length === 0) return setOpen(false);
    update.mutate({ linkId: link.id, ...body }, { onSuccess: () => setOpen(false) });
  }

  return (
    <Popover
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        if (o) {
          setTitle(link.title ?? "");
          setUrl(link.url);
        }
      }}
    >
      <PopoverTrigger asChild>
        <Button
          variant="ghost"
          size="icon-xs"
          aria-label={`Edit link ${link.title ?? link.pageTitle ?? host(link.url)}`}
          className="absolute top-1.5 right-1.5 text-muted-foreground opacity-60 group-hover:opacity-100 focus-visible:opacity-100"
        >
          <PencilIcon />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80">
        <form onSubmit={save} className="grid gap-3" aria-label="Edit link">
          <div className="grid gap-1.5">
            <Label htmlFor={`${link.id}-title`}>Title</Label>
            <Input
              id={`${link.id}-title`}
              placeholder={link.pageTitle ?? host(link.url)}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor={`${link.id}-url`}>URL</Label>
            <Input
              id={`${link.id}-url`}
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
            />
          </div>
          <div className="flex justify-between gap-2">
            <Button
              type="button"
              variant="destructive"
              size="sm"
              disabled={remove.isPending}
              onClick={() => remove.mutate(link.id, { onSuccess: () => setOpen(false) })}
            >
              Unpin
            </Button>
            <Button type="submit" size="sm" disabled={update.isPending}>
              {update.isPending ? "Saving…" : "Save"}
            </Button>
          </div>
        </form>
      </PopoverContent>
    </Popover>
  );
}

function PinLink({ tripId }: { tripId: string }) {
  const [open, setOpen] = useState(false);
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  const add = useAddLink(tripId);

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!url.trim()) return;
    add.mutate(
      { url: url.trim(), ...(title.trim() ? { title: title.trim() } : {}) },
      {
        onSuccess: () => {
          setUrl("");
          setTitle("");
          setOpen(false);
        },
      },
    );
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          className="h-16 shrink-0 rounded-2xl border-dashed px-4 text-muted-foreground"
        >
          <PinIcon />
          Pin link
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-80">
        <form onSubmit={submit} className="grid gap-3" aria-label="Pin a link">
          <div className="grid gap-1.5">
            <Label htmlFor="pin-url">URL</Label>
            <Input
              id="pin-url"
              type="url"
              placeholder="https://…"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              autoFocus
              required
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="pin-title">Title (optional)</Label>
            <Input
              id="pin-title"
              placeholder="Uses the page's title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </div>
          <Button type="submit" size="sm" disabled={!url.trim() || add.isPending}>
            {add.isPending ? "Fetching preview…" : "Pin"}
          </Button>
        </form>
      </PopoverContent>
    </Popover>
  );
}
