import { ReactNode } from "react";
import { Navigation } from "./Navigation";

export function Shell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-background text-foreground selection:bg-primary/30">
      <Navigation />
      <main className="md:pl-64 pb-16 md:pb-0 min-h-screen flex flex-col">
        <div className="flex-1 max-w-7xl mx-auto w-full p-4 md:p-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
          {children}
        </div>
      </main>
    </div>
  );
}
