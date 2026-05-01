import { useRoute } from "wouter";
import { 
  useGetSwarm, 
  useDeploySwarm, 
  useAbortSwarm,
  getGetSwarmQueryKey 
} from "@workspace/api-client-react";
import { useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/status-badge";
import { Button } from "@/components/ui/button";
import { formatDuration, formatTokens, formatDate } from "@/lib/formatters";
import { Play, Square, AlertTriangle, CheckCircle2, ChevronRight, Terminal } from "lucide-react";
import { DAGVisualizer } from "@/components/DAGVisualizer";
import { useToast } from "@/hooks/use-toast";
import { ScrollArea } from "@/components/ui/scroll-area";

export default function SwarmDetail() {
  const [, params] = useRoute("/swarms/:id");
  const id = params?.id || "";
  const { toast } = useToast();
  const queryClient = useQueryClient();

  const { data: swarm, isLoading } = useGetSwarm(id, {
    query: {
      enabled: !!id,
      refetchInterval: (query) => {
        // Poll if running
        return query.state.data?.status === 'running' ? 2000 : false;
      }
    }
  });

  const deploySwarm = useDeploySwarm({
    mutation: {
      onSuccess: () => {
        toast({ title: "Swarm Deployed", description: "Execution has begun." });
        queryClient.invalidateQueries({ queryKey: getGetSwarmQueryKey(id) });
      }
    }
  });

  const abortSwarm = useAbortSwarm({
    mutation: {
      onSuccess: () => {
        toast({ title: "Swarm Aborted", description: "Execution halted." });
        queryClient.invalidateQueries({ queryKey: getGetSwarmQueryKey(id) });
      }
    }
  });

  if (isLoading) {
    return <div className="p-8 animate-pulse bg-muted rounded-xl h-64" />;
  }

  if (!swarm) {
    return <div>Swarm not found.</div>;
  }

  const isDeployable = swarm.status === 'planning' || swarm.status === 'pending';
  const isAbortable = swarm.status === 'running';

  const visualizerNodes = swarm.nodes.map(n => ({
    id: n.nodeId,
    label: n.taskDescription,
    status: n.status,
    dependencies: n.dependencies
  }));

  return (
    <div className="space-y-6">
      <div className="flex flex-col md:flex-row md:items-start justify-between gap-4">
        <div className="space-y-2">
          <div className="flex items-center gap-3">
            <h1 className="text-3xl font-bold tracking-tight font-mono uppercase">Operation {swarm.id.substring(0,8)}</h1>
            <StatusBadge status={swarm.status} className="text-sm px-3 py-1" />
            {swarm.mockMode && (
              <span className="text-xs uppercase tracking-wider text-chart-4 border border-chart-4/30 px-2 py-0.5 rounded bg-chart-4/10">
                Mock Mode
              </span>
            )}
          </div>
          <p className="text-muted-foreground text-sm max-w-2xl">{swarm.task}</p>
        </div>
        
        <div className="flex items-center gap-3">
          {isDeployable && (
            <Button 
              onClick={() => deploySwarm.mutate({ swarmId: id })} 
              disabled={deploySwarm.isPending}
            >
              <Play className="mr-2 h-4 w-4" />
              Deploy Swarm
            </Button>
          )}
          {isAbortable && (
            <Button 
              variant="destructive" 
              onClick={() => abortSwarm.mutate({ swarmId: id })}
              disabled={abortSwarm.isPending}
            >
              <Square className="mr-2 h-4 w-4" />
              Abort
            </Button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card className="bg-card border-border">
          <CardContent className="p-4">
            <div className="text-xs text-muted-foreground mb-1 uppercase tracking-wider font-mono">Created</div>
            <div className="font-medium text-sm">{formatDate(swarm.createdAt)}</div>
          </CardContent>
        </Card>
        <Card className="bg-card border-border">
          <CardContent className="p-4">
            <div className="text-xs text-muted-foreground mb-1 uppercase tracking-wider font-mono">Duration</div>
            <div className="font-medium text-sm">{formatDuration(swarm.executionDurationMs)}</div>
          </CardContent>
        </Card>
        <Card className="bg-card border-border">
          <CardContent className="p-4">
            <div className="text-xs text-muted-foreground mb-1 uppercase tracking-wider font-mono">Tokens</div>
            <div className="font-medium text-sm">{formatTokens(swarm.tokensConsumed)}</div>
          </CardContent>
        </Card>
        <Card className="bg-card border-border">
          <CardContent className="p-4">
            <div className="text-xs text-muted-foreground mb-1 uppercase tracking-wider font-mono">Nodes</div>
            <div className="font-medium text-sm">
              <span className="text-chart-3">{swarm.nodesSucceeded}</span>
              {" "}/ {swarm.nodesTotal}
            </div>
          </CardContent>
        </Card>
      </div>

      <Card className="border-border bg-card overflow-hidden">
        <CardHeader className="bg-muted/30 border-b border-border/50">
          <CardTitle className="text-lg flex items-center gap-2">
            <Network className="h-5 w-5" /> DAG Visualization
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <DAGVisualizer 
            nodes={visualizerNodes} 
            edges={swarm.edges} 
            parallelGroups={swarm.parallelGroups} 
          />
        </CardContent>
      </Card>

      <Card className="border-border bg-card">
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <Terminal className="h-5 w-5" /> Node Outputs
          </CardTitle>
          <CardDescription>Execution traces and returned payloads from individual agents.</CardDescription>
        </CardHeader>
        <CardContent>
          <ScrollArea className="h-[400px] rounded-md border border-border/50">
            <div className="p-4 space-y-6">
              {swarm.nodes.length === 0 && (
                <div className="text-center text-muted-foreground py-8">No nodes to display.</div>
              )}
              {swarm.nodes.map(node => (
                <div key={node.nodeId} className="space-y-2">
                  <div className="flex items-center gap-2 text-sm font-mono border-b border-border/50 pb-1">
                    <StatusBadge status={node.status} className="px-1.5 py-0 text-[10px]" />
                    <span className="font-bold">{node.nodeId}</span>
                    <span className="text-muted-foreground ml-auto">{formatDuration(node.executionDurationMs)}</span>
                  </div>
                  <div className="text-sm text-muted-foreground pl-2 border-l-2 border-primary/30">
                    {node.taskDescription}
                  </div>
                  {node.errorMessage && (
                    <div className="bg-destructive/10 text-destructive text-sm p-3 rounded-md font-mono mt-2">
                      <AlertTriangle className="h-4 w-4 inline mr-2" />
                      {node.errorMessage}
                    </div>
                  )}
                  {node.output && (
                    <div className="bg-muted/30 p-3 rounded-md mt-2 overflow-x-auto text-xs font-mono text-foreground/80">
                      <pre>{node.output}</pre>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </ScrollArea>
        </CardContent>
      </Card>

    </div>
  );
}
