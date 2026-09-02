import { AlertTriangle, Loader2, SearchX } from "lucide-react";

import { cn } from "@/lib/utils";

type StateBlockProps = {
  title: string;
  detail?: string;
  className?: string;
};

export function LoadingState({ title, detail, className }: StateBlockProps) {
  return (
    <div className={cn("flex min-h-32 items-center justify-center gap-3 text-textMuted", className)}>
      <Loader2 className="h-5 w-5 animate-spin text-accent" aria-hidden="true" />
      <div>
        <p className="text-sm font-semibold text-textPrimary">{title}</p>
        {detail ? <p className="text-xs">{detail}</p> : null}
      </div>
    </div>
  );
}

export function EmptyState({ title, detail, className }: StateBlockProps) {
  return (
    <div className={cn("flex min-h-32 items-center justify-center gap-3 text-textMuted", className)}>
      <SearchX className="h-5 w-5 text-accent" aria-hidden="true" />
      <div>
        <p className="text-sm font-semibold text-textPrimary">{title}</p>
        {detail ? <p className="text-xs">{detail}</p> : null}
      </div>
    </div>
  );
}

export function ErrorState({ title, detail, className }: StateBlockProps) {
  return (
    <div className={cn("flex min-h-32 items-center justify-center gap-3 text-rose-200", className)}>
      <AlertTriangle className="h-5 w-5 text-danger" aria-hidden="true" />
      <div>
        <p className="text-sm font-semibold text-rose-100">{title}</p>
        {detail ? <p className="text-xs text-rose-200/75">{detail}</p> : null}
      </div>
    </div>
  );
}
