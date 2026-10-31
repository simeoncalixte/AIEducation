import type { ReactNode } from "react";

/** Dashed empty-state box (mirrors the .empty blocks). */
export function EmptyState({ children }: { children: ReactNode }) {
  return (
    <div className="empty">
      <p>{children}</p>
    </div>
  );
}
