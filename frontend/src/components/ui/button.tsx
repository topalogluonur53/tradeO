import type { ButtonHTMLAttributes } from "react";

import { cn } from "@/lib/utils";

type ButtonVariant = "primary" | "secondary" | "danger" | "ghost";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
};

const variants: Record<ButtonVariant, string> = {
  primary: "border-accent/50 bg-accent text-slate-950 hover:bg-teal-300",
  secondary: "border-line bg-panelMuted text-textPrimary hover:border-slate-500",
  danger: "border-danger/60 bg-danger/12 text-rose-100 hover:bg-danger/20",
  ghost: "border-transparent bg-transparent text-textMuted hover:bg-panelMuted hover:text-textPrimary"
};

export function Button({ className, variant = "secondary", ...props }: ButtonProps) {
  return (
    <button
      className={cn(
        "inline-flex h-10 items-center justify-center gap-2 rounded-md border px-3 text-sm font-semibold transition focus:outline-none focus:ring-2 focus:ring-accent/60 disabled:cursor-not-allowed disabled:opacity-50",
        variants[variant],
        className
      )}
      {...props}
    />
  );
}
