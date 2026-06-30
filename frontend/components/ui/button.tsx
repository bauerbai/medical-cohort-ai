import * as React from "react";

import { cn } from "@/lib/utils";

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "default" | "secondary" | "ghost";
};

const variants = {
  default: "bg-neutral-950 text-white hover:bg-neutral-800",
  secondary: "bg-white text-neutral-900 border border-neutral-200 hover:bg-neutral-50",
  ghost: "text-neutral-700 hover:bg-neutral-100",
};

export function Button({ className, variant = "default", ...props }: ButtonProps) {
  return (
    <button
      className={cn(
        "inline-flex h-10 items-center justify-center rounded-md px-4 text-sm font-medium transition disabled:pointer-events-none disabled:opacity-50",
        variants[variant],
        className,
      )}
      {...props}
    />
  );
}
