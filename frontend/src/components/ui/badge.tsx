import type { HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

type BadgeTone = "paper" | "neutral" | "warning" | "danger";

const tones: Record<BadgeTone, string> = {
  paper: "border-accent/40 bg-accent/12 text-teal-100",
  neutral: "border-line bg-panelMuted text-textMuted",
  warning: "border-amber/50 bg-amber/12 text-amber-100",
  danger: "border-danger/50 bg-danger/12 text-rose-100"
};

type BadgeProps = HTMLAttributes<HTMLSpanElement> & {
  tone?: BadgeTone;
};

export function Badge({ className, tone = "neutral", ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex min-h-7 items-center rounded-md border px-2.5 text-xs font-bold uppercase tracking-normal",
        tones[tone],
        className
      )}
      {...props}
    />
  );
}
