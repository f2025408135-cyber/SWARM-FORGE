import { useQueryClient } from "@tanstack/react-query";
import { Link } from "wouter";
import { 
  useGetDashboardStats, 
  getGetDashboardStatsQueryKey,
  useListSwarms,
  getListSwarmsQueryKey,
  useGetSecurityEvents,
  getGetSecurityEventsQueryKey
} from "@workspace/api-client-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { ShieldAlert, Network, Hammer, Activity, CheckCircle2, XCircle } from "lucide-react";
import { formatDuration, formatTokens, formatDate } from "@/lib/formatters";
import { StatusBadge } from "@/components/ui/status-badge";

export default function Dashboard() {
  const { data: stats, isLoading: statsLoading } = useGetDashboardStats({
    query: { refetchInterval: 5000 }
  });
  
  const { data: swarmsData, isLoading: swarmsLoading } = useListSwarms(
    { limit: 5 }, 
    { query: { refetchInterval: 5000 } }
  );

  const { data: securityData, isLoading: securityLoading } = useGetSecurityEvents(
    { limit: 5 },
    { query: { refetchInterval: 5000 } }
  );

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Operations Dashboard</h1>
        <p className="text-muted-foreground mt-2">Real-time command center for SWARM-FORGE deployments.</p>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card className="bg-card border-border">
          <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0">
            <CardTitle className="text-sm font-medium">Active Swarms</CardTitle>
            <Activity className="h-4 w-4 text-primary" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{statsLoading ? "-" : stats?.activeSwarms || 0}</div>
            <p className="text-xs text-muted-foreground">Running right now</p>
          </CardContent>
        </Card>
        
        <Card className="bg-card border-border">
          <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0">
            <CardTitle className="text-sm font-medium">Total Tokens</CardTitle>
            <Network className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{statsLoading ? "-" : formatTokens(stats?.totalTokensConsumed)}</div>
            <p className="text-xs text-muted-foreground">Across all operations</p>
          </CardContent>
        </Card>

        <Card className="bg-card border-border">
          <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0">
            <CardTitle className="text-sm font-medium">Success Rate</CardTitle>
            <CheckCircle2 className="h-4 w-4 text-chart-3" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{statsLoading ? "-" : `${Math.round((stats?.successRate || 0) * 100)}%`}</div>
            <p className="text-xs text-muted-foreground">Completed vs Failed</p>
          </CardContent>
        </Card>

        <Card className="bg-card border-border">
          <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0">
            <CardTitle className="text-sm font-medium">Firewall Interventions</CardTitle>
            <ShieldAlert className="h-4 w-4 text-destructive" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-destructive">{statsLoading ? "-" : stats?.firewallBlocked || 0}</div>
            <p className="text-xs text-muted-foreground">Malicious payloads dropped</p>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card className="border-border bg-card">
          <CardHeader>
            <CardTitle>Active Swarms</CardTitle>
            <CardDescription>Recently created or currently running</CardDescription>
          </CardHeader>
          <CardContent>
            {swarmsLoading ? (
              <div className="space-y-4">
                {[1,2,3].map(i => <div key={i} className="h-12 bg-muted/50 rounded animate-pulse" />)}
              </div>
            ) : swarmsData?.swarms && swarmsData.swarms.length > 0 ? (
              <div className="space-y-4">
                {swarmsData.swarms.map(swarm => (
                  <div key={swarm.id} className="flex items-center justify-between border-b border-border/50 pb-4 last:border-0 last:pb-0">
                    <div className="space-y-1 overflow-hidden">
                      <Link href={`/swarms/${swarm.id}`} className="font-medium hover:underline text-sm truncate block">
                        {swarm.task}
                      </Link>
                      <div className="text-xs text-muted-foreground">
                        {formatDate(swarm.createdAt)}
                      </div>
                    </div>
                    <div className="ml-4 shrink-0">
                      <StatusBadge status={swarm.status} />
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-8">
                <p className="text-muted-foreground mb-4">No active swarms found.</p>
                <Link href="/forge" className="inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 bg-primary text-primary-foreground hover:bg-primary/90 h-10 px-4 py-2">
                  <Hammer className="mr-2 h-4 w-4" />
                  Forge your first swarm
                </Link>
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="border-border bg-card flex flex-col">
          <CardHeader>
            <CardTitle>Security Feed</CardTitle>
            <CardDescription>Recent zero-trust firewall events</CardDescription>
          </CardHeader>
          <CardContent className="flex-1">
             {securityLoading ? (
              <div className="space-y-4">
                {[1,2,3].map(i => <div key={i} className="h-12 bg-muted/50 rounded animate-pulse" />)}
              </div>
            ) : securityData?.events && securityData.events.length > 0 ? (
              <div className="space-y-4">
                {securityData.events.map(event => (
                  <div key={event.id} className="flex items-start gap-3 border-b border-border/50 pb-4 last:border-0 last:pb-0">
                    <div className="mt-0.5">
                      {event.severity === 'critical' ? (
                        <XCircle className="h-4 w-4 text-destructive" />
                      ) : event.severity === 'warn' ? (
                        <ShieldAlert className="h-4 w-4 text-chart-4" />
                      ) : (
                        <ShieldAlert className="h-4 w-4 text-chart-1" />
                      )}
                    </div>
                    <div className="space-y-1">
                      <p className="text-sm font-medium">
                        {event.eventType.replace(/_/g, ' ')}
                      </p>
                      <p className="text-xs text-muted-foreground font-mono truncate max-w-[200px] md:max-w-xs">
                        {event.payload}
                      </p>
                      <p className="text-[10px] text-muted-foreground">
                        {formatDate(event.timestamp)}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-8">
                <p className="text-muted-foreground">No recent security events.</p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
