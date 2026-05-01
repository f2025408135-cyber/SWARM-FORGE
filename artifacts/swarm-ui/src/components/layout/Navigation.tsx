import { Link, useLocation } from "wouter";
import { LayoutDashboard, Hammer, ShieldAlert, History, Network } from "lucide-react";
import { cn } from "@/lib/utils";

const links = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/forge", label: "Forge", icon: Hammer },
  { href: "/swarms", label: "Swarms", icon: Network },
  { href: "/security", label: "Security", icon: ShieldAlert },
  { href: "/history", label: "History", icon: History },
];

export function Navigation() {
  const [location] = useLocation();

  return (
    <>
      {/* Desktop Sidebar */}
      <div className="hidden md:flex w-64 flex-col fixed inset-y-0 z-50 bg-card border-r border-border">
        <div className="h-16 flex items-center px-6 border-b border-border">
          <Network className="h-6 w-6 text-primary mr-3" />
          <span className="font-bold text-lg tracking-tight text-foreground uppercase">Swarm-Forge</span>
        </div>
        <div className="flex-1 overflow-y-auto py-6 px-4 space-y-2">
          {links.map((link) => {
            const isActive = location === link.href || (link.href !== "/" && location.startsWith(link.href));
            return (
              <Link key={link.href} href={link.href} className={cn(
                "flex items-center gap-3 px-3 py-2.5 rounded-md transition-colors text-sm font-medium",
                isActive ? "bg-primary/10 text-primary" : "text-muted-foreground hover:text-foreground hover:bg-muted"
              )}>
                <link.icon className="h-5 w-5" />
                {link.label}
              </Link>
            );
          })}
        </div>
      </div>

      {/* Mobile Bottom Nav */}
      <div className="md:hidden fixed bottom-0 inset-x-0 z-50 bg-card border-t border-border flex items-center justify-around h-16 pb-safe">
        {links.map((link) => {
          const isActive = location === link.href || (link.href !== "/" && location.startsWith(link.href));
          return (
            <Link key={link.href} href={link.href} className={cn(
              "flex flex-col items-center justify-center w-full h-full space-y-1",
              isActive ? "text-primary" : "text-muted-foreground hover:text-foreground"
            )}>
              <link.icon className="h-5 w-5" />
              <span className="text-[10px] font-medium">{link.label}</span>
            </Link>
          );
        })}
      </div>
    </>
  );
}
