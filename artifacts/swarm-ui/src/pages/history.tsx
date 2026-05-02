import { useListSwarms } from "@workspace/api-client-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { StatusBadge } from "@/components/ui/status-badge";
import { formatDate, formatDuration, formatTokens } from "@/lib/formatters";
import { Link } from "wouter";

export default function History() {
  // Fetch historical data (in a real app, maybe with a different filter, but here we list all)
  const { data, isLoading } = useListSwarms(
    { limit: 100 },
    { query: { refetchInterval: 30000 } as any }
  );

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Operation History</h1>
        <p className="text-muted-foreground mt-2">Audit trail of all executed swarms.</p>
      </div>

      <Card className="border-border bg-card">
        <CardHeader>
          <CardTitle>Historical Records</CardTitle>
          <CardDescription>Complete log of past and present executions.</CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="space-y-4">
               {[1,2,3,4,5].map(i => <div key={i} className="h-12 bg-muted/50 rounded animate-pulse" />)}
            </div>
          ) : data?.swarms && data.swarms.length > 0 ? (
            <div className="rounded-md border border-border/50 overflow-x-auto">
              <Table>
                <TableHeader className="bg-muted/30">
                  <TableRow>
                    <TableHead className="w-[100px]">ID</TableHead>
                    <TableHead>Task</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Created</TableHead>
                    <TableHead className="text-right">Duration</TableHead>
                    <TableHead className="text-right">Tokens</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.swarms.map((swarm) => (
                    <TableRow key={swarm.id} className="hover:bg-muted/20">
                      <TableCell className="font-mono text-xs">
                        <Link href={`/swarms/${swarm.id}`} className="hover:underline text-primary">
                          {swarm.id.substring(0, 8)}
                        </Link>
                      </TableCell>
                      <TableCell className="max-w-[200px] md:max-w-md truncate">
                        {swarm.task}
                      </TableCell>
                      <TableCell>
                        <StatusBadge status={swarm.status} className="px-2 py-0.5 text-[10px]" />
                      </TableCell>
                      <TableCell className="text-muted-foreground text-xs whitespace-nowrap">
                        {formatDate(swarm.createdAt)}
                      </TableCell>
                      <TableCell className="text-right text-muted-foreground text-xs whitespace-nowrap">
                        {formatDuration(swarm.executionDurationMs)}
                      </TableCell>
                      <TableCell className="text-right text-muted-foreground text-xs whitespace-nowrap">
                        {formatTokens(swarm.tokensConsumed)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          ) : (
            <div className="text-center py-12 text-muted-foreground">
              No historical data available.
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
