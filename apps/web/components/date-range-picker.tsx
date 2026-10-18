"use client";

import { CalendarIcon } from "lucide-react";
import { useState } from "react";
import type { DateRange } from "react-day-picker";

import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { formatDateOnly, formatDateRange, parseDateOnly } from "@/lib/time";
import { cn } from "@/lib/utils";

export interface DateRangeValue {
  startDate?: string;
  endDate?: string;
}

/** A react-day-picker range calendar in a popover. Values are "YYYY-MM-DD" calendar dates. */
export function DateRangePicker({
  value,
  onChange,
  onClose,
  id,
  className,
  children,
}: {
  value: DateRangeValue;
  onChange: (value: DateRangeValue) => void;
  /** Called when the popover closes (Done or click outside). */
  onClose?: () => void;
  id?: string;
  className?: string;
  /** Custom trigger content; defaults to the formatted range. */
  children?: React.ReactNode;
}) {
  const [open, setOpenState] = useState(false);
  const setOpen = (next: boolean) => {
    setOpenState(next);
    if (!next) onClose?.();
  };
  const selected: DateRange | undefined = value.startDate
    ? {
        from: parseDateOnly(value.startDate),
        to: value.endDate ? parseDateOnly(value.endDate) : undefined,
      }
    : undefined;
  const label =
    value.startDate && value.endDate
      ? formatDateRange(value.startDate, value.endDate)
      : value.startDate
        ? `${formatDateRange(value.startDate, value.startDate)} – …`
        : "Pick dates";

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        {children ? (
          <button type="button" id={id} className={className}>
            {children}
          </button>
        ) : (
          <Button
            type="button"
            id={id}
            variant="outline"
            className={cn(
              "h-10 w-full justify-start gap-2 font-normal",
              !value.startDate && "text-muted-foreground",
              className,
            )}
          >
            <CalendarIcon />
            {label}
          </Button>
        )}
      </PopoverTrigger>
      <PopoverContent className="w-auto p-0" align="start">
        <Calendar
          mode="range"
          numberOfMonths={2}
          defaultMonth={selected?.from}
          selected={selected}
          onSelect={(range) =>
            onChange({
              startDate: range?.from ? formatDateOnly(range.from) : undefined,
              endDate: range?.to ? formatDateOnly(range.to) : undefined,
            })
          }
        />
        <div className="flex justify-end border-t p-2">
          <Button
            type="button"
            size="sm"
            disabled={!value.startDate || !value.endDate}
            onClick={() => setOpen(false)}
          >
            Done
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
