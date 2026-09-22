import { useState } from "react";
import { Link } from "wouter";
import { useListSwarms } from "@workspace/api-client-react";
import { Card, CardContent } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/status-badge";
import { formatDate, formatDuration } from "@/lib/formatters";
import { Clock, Network, Cpu } from "lucide-react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
type ListSwarmsStatus = "pending" | "planning" | "running" | "completed" | "failed" | "aborted";

export default function Swarms() {
  const [statusFilter, setStatusFilter] = useState<string>("all");
  
  const { data, isLoading } = useListSwarms(
    statusFilter !== "all" ? { status: statusFilter as ListSwarmsStatus } : {},
    { query: { refetchInterval: 5000 } as any }
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Swarms</h1>
          <p className="text-muted-foreground mt-2">Manage and monitor all agent operations.</p>
        </div>
        
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-[180px] bg-card">
            <SelectValue placeholder="Filter by status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Statuses</SelectItem>
            <SelectItem value="pending">Pending</SelectItem>
            <SelectItem value="planning">Planning</SelectItem>
            <SelectItem value="running">Running</SelectItem>
            <SelectItem value="completed">Completed</SelectItem>
            <SelectItem value="failed">Failed</SelectItem>
            <SelectItem value="aborted">Aborted</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-4">
        {isLoading ? (
          Array.from({ length: 5 }).map((_, i) => (
            <Card key={i} className="animate-pulse bg-card">
              <CardContent className="h-24" />
            </Card>
          ))
        ) : data?.swarms?.length === 0 ? (
          <Card className="bg-card">
            <CardContent className="flex flex-col items-center justify-center h-48 text-center">
              <Network className="h-8 w-8 text-muted-foreground mb-4" />
              <p className="text-lg font-medium">No swarms found</p>
              <p className="text-muted-foreground text-sm">Adjust your filters or forge a new swarm.</p>
            </CardContent>
          </Card>
        ) : (
          data?.swarms?.map((swarm) => (
            <Link key={swarm.id} href={`/swarms/${swarm.id}`}>
              <Card className="bg-card border-border hover:border-primary/50 transition-colors cursor-pointer group">
                <CardContent className="p-6">
                  <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                    <div className="space-y-2 flex-1">
                      <div className="flex items-center gap-3">
                        <span className="font-mono text-xs text-muted-foreground bg-muted px-2 py-0.5 rounded">
                          {swarm.id.substring(0, 8)}
                        </span>
                        <StatusBadge status={swarm.status} />
                        {swarm.mockMode && (
                          <span className="text-[10px] uppercase tracking-wider text-chart-4 border border-chart-4/30 px-1.5 py-0.5 rounded bg-chart-4/10">
                            Mock
                          </span>
                        )}
                      </div>
                      <p className="text-sm font-medium line-clamp-2 text-foreground group-hover:text-primary transition-colors">
                        {swarm.task}
                      </p>
                    </div>

                    <div className="flex items-center gap-6 text-sm text-muted-foreground shrink-0">
                      <div className="flex items-center gap-1.5" title="Nodes (Success / Total)">
                        <Network className="h-4 w-4" />
                        <span>{swarm.nodesSucceeded} / {swarm.nodesTotal}</span>
                      </div>
                      <div className="flex items-center gap-1.5" title="Execution Time">
                        <Clock className="h-4 w-4" />
                        <span>{formatDuration(swarm.executionDurationMs)}</span>
                      </div>
                      <div className="flex items-center gap-1.5" title="Tokens Consumed">
                        <Cpu className="h-4 w-4" />
                        <span>{swarm.tokensConsumed > 0 ? (swarm.tokensConsumed / 1000).toFixed(1) + 'k' : '0'}</span>
                      </div>
                      <div className="text-xs text-right min-w-[100px]">
                        {formatDate(swarm.createdAt)}
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </Link>
          ))
        )}
      </div>
    </div>
  );
}
