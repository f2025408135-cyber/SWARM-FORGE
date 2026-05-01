import { cva, type VariantProps } from "class-variance-authority";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const statusVariants = cva("capitalize whitespace-nowrap", {
  variants: {
    status: {
      pending: "bg-muted text-muted-foreground border-muted",
      planning: "bg-primary/20 text-primary border-primary/30",
      running: "bg-primary text-primary-foreground status-pulse border-primary",
      completed: "bg-chart-3/20 text-chart-3 border-chart-3/30",
      success: "bg-chart-3/20 text-chart-3 border-chart-3/30",
      failed: "bg-destructive/20 text-destructive border-destructive/30",
      skipped: "bg-muted text-muted-foreground border-muted",
      blocked: "bg-chart-4/20 text-chart-4 border-chart-4/30",
      aborted: "bg-destructive text-destructive-foreground border-destructive",
    },
  },
  defaultVariants: {
    status: "pending",
  },
});

export interface StatusBadgeProps extends VariantProps<typeof statusVariants> {
  className?: string;
  children?: React.ReactNode;
  status: any;
}

export function StatusBadge({ status, className, children }: StatusBadgeProps) {
  return (
    <Badge variant="outline" className={cn(statusVariants({ status }), className)}>
      {children || status}
    </Badge>
  );
}
