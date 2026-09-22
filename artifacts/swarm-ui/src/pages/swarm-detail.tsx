import { useRoute } from "wouter";
import {
  useGetSwarm,
  useDeploySwarm,
  useAbortSwarm,
  getGetSwarmQueryKey,
} from "@workspace/api-client-react";
import { useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/status-badge";
import { Button } from "@/components/ui/button";
import { formatDuration, formatTokens, formatDate } from "@/lib/formatters";
import { Play, Square, AlertTriangle, Terminal, Network } from "lucide-react";
import { DAGVisualizer } from "@/components/DAGVisualizer";
import { useToast } from "@/hooks/use-toast";
import { ScrollArea } from "@/components/ui/scroll-area";

// ── Tier metadata ──────────────────────────────────────────────────────────
const TIER_COLORS: Record<string, string> = {
  nano:     "text-slate-400  border-slate-400/30  bg-slate-400/10",
  small:    "text-blue-400   border-blue-400/30   bg-blue-400/10",
  medium:   "text-cyan-400   border-cyan-400/30   bg-cyan-400/10",
  large:    "text-violet-400 border-violet-400/30 bg-violet-400/10",
  frontier: "text-amber-400  border-amber-400/30  bg-amber-400/10",
};

// ── Provider metadata ──────────────────────────────────────────────────────
const PROVIDER_COLORS: Record<string, string> = {
  openai:     "#10A37F",
  anthropic:  "#CC785C",
  google:     "#4285F4",
  mistral:    "#FF7000",
  groq:       "#F55036",
  cohere:     "#39594D",
  openrouter: "#6D28D9",
};

const PROVIDER_LABELS: Record<string, string> = {
  openai:     "OpenAI",
  anthropic:  "Anthropic",
  google:     "Google",
  mistral:    "Mistral AI",
  groq:       "Groq",
  cohere:     "Cohere",
  openrouter: "OpenRouter",
};

function TierBadge({ tier }: { tier?: string | null }) {
  if (!tier) return null;
  const cls = TIER_COLORS[tier] ?? "text-muted-foreground border-border bg-muted/20";
  return (
    <span className={`inline-flex items-center px-1.5 py-0 text-[10px] font-mono uppercase tracking-wider border rounded ${cls}`}>
      {tier}
    </span>
  );
}

function ProviderBadge({ provider, model }: { provider?: string | null; model?: string | null }) {
  if (!provider) return null;
  const color = PROVIDER_COLORS[provider] ?? "#888";
  const label = PROVIDER_LABELS[provider] ?? provider;
  return (
    <span
      className="inline-flex items-center gap-1 px-1.5 py-0 text-[10px] font-mono rounded border"
      style={{
        color,
        borderColor: `${color}40`,
        backgroundColor: `${color}12`,
      }}
      title={model ?? label}
    >
      <span className="inline-block w-1.5 h-1.5 rounded-full" style={{ backgroundColor: color }} />
      {model ? model.split("/").pop()!.split("-").slice(0, 3).join("-") : label}
    </span>
  );
}

export default function SwarmDetail() {
  const [, params] = useRoute("/swarms/:id");
  const id = params?.id || "";
  const { toast } = useToast();
  const queryClient = useQueryClient();

  const { data: swarm, isLoading } = useGetSwarm(id, {
    query: {
      enabled: !!id,
      refetchInterval: (query: any) =>
        query.state.data?.status === "running" ? 2000 : false,
    } as any,
  });

  const deploySwarm = useDeploySwarm({
    mutation: {
      onSuccess: () => {
        toast({ title: "Swarm Deployed", description: "Execution has begun." });
        queryClient.invalidateQueries({ queryKey: getGetSwarmQueryKey(id) });
      },
    },
  });

  const abortSwarm = useAbortSwarm({
    mutation: {
      onSuccess: () => {
        toast({ title: "Swarm Aborted", description: "Execution halted." });
        queryClient.invalidateQueries({ queryKey: getGetSwarmQueryKey(id) });
      },
    },
  });

  if (isLoading) {
    return <div className="p-8 animate-pulse bg-muted rounded-xl h-64" />;
  }

  if (!swarm) {
    return <div>Swarm not found.</div>;
  }

  const isDeployable = swarm.status === "planning" || swarm.status === "pending";
  const isAbortable = swarm.status === "running";

  const visualizerNodes = swarm.nodes.map((n) => ({
    id: n.nodeId,
    label: n.taskDescription,
    status: n.status,
    dependencies: n.dependencies,
  }));

  // Summary: count tiers used
  const tierCounts: Record<string, number> = {};
  for (const n of swarm.nodes) {
    const t = (n as any).modelTier ?? "medium";
    tierCounts[t] = (tierCounts[t] ?? 0) + 1;
  }

  // Summary: unique providers
  const providerSet = new Set(
    swarm.nodes.map((n) => (n as any).resolvedProvider).filter(Boolean)
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-start justify-between gap-4">
        <div className="space-y-2">
          <div className="flex items-center flex-wrap gap-3">
            <h1 className="text-3xl font-bold tracking-tight font-mono uppercase">
              Operation {swarm.id.substring(0, 8)}
            </h1>
            <StatusBadge status={swarm.status} className="text-sm px-3 py-1" />
            {swarm.mockMode && (
              <span className="text-xs uppercase tracking-wider text-chart-4 border border-chart-4/30 px-2 py-0.5 rounded bg-chart-4/10">
                Mock Mode
              </span>
            )}
            {(swarm as any).preferredProvider && (
              <ProviderBadge
                provider={(swarm as any).preferredProvider}
                model={null}
              />
            )}
          </div>
          <p className="text-muted-foreground text-sm max-w-2xl">{swarm.task}</p>

          {/* Tier + Provider summary chips */}
          <div className="flex flex-wrap gap-1.5 pt-1">
            {Object.entries(tierCounts).map(([tier, count]) => (
              <TierBadge key={tier} tier={tier} />
            ))}
            {Array.from(providerSet).map((p) => (
              <ProviderBadge key={p as string} provider={p as string} model={null} />
            ))}
          </div>
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

      {/* Stats row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: "Created",  value: formatDate(swarm.createdAt) },
          { label: "Duration", value: formatDuration(swarm.executionDurationMs) },
          { label: "Tokens",   value: formatTokens(swarm.tokensConsumed) },
          { label: "Nodes",    value: `${swarm.nodesSucceeded} / ${swarm.nodesTotal}` },
        ].map(({ label, value }) => (
          <Card key={label} className="bg-card border-border">
            <CardContent className="p-4">
              <div className="text-xs text-muted-foreground mb-1 uppercase tracking-wider font-mono">{label}</div>
              <div className="font-medium text-sm">{value}</div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* DAG */}
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

      {/* Node Outputs */}
      <Card className="border-border bg-card">
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <Terminal className="h-5 w-5" /> Node Execution Trace
          </CardTitle>
          <CardDescription>
            Resolved provider, model tier, and output for each agent node.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ScrollArea className="h-[500px] rounded-md border border-border/50">
            <div className="p-4 space-y-6">
              {swarm.nodes.length === 0 && (
                <div className="text-center text-muted-foreground py-8">
                  No nodes to display.
                </div>
              )}
              {swarm.nodes.map((node) => {
                const tier = (node as any).modelTier;
                const resolvedProvider = (node as any).resolvedProvider;
                const resolvedModel = (node as any).resolvedModel;
                return (
                  <div key={node.nodeId} className="space-y-2">
                    {/* Node header */}
                    <div className="flex items-center flex-wrap gap-2 text-sm font-mono border-b border-border/50 pb-2">
                      <StatusBadge status={node.status} className="px-1.5 py-0 text-[10px]" />
                      <span className="font-bold">{node.nodeId}</span>
                      <TierBadge tier={tier} />
                      {resolvedProvider && (
                        <ProviderBadge provider={resolvedProvider} model={resolvedModel} />
                      )}
                      <span className="text-muted-foreground ml-auto text-xs">
                        {formatDuration(node.executionDurationMs)}
                        {(node.tokensConsumed ?? 0) > 0 && (
                          <> · {formatTokens(node.tokensConsumed ?? 0)}</>
                        )}
                      </span>
                    </div>

                    {/* Task description */}
                    <div className="text-sm text-muted-foreground pl-2 border-l-2 border-primary/30">
                      {node.taskDescription}
                    </div>

                    {/* Firewall status */}
                    {node.firewallPassed === false && (
                      <div className="text-xs font-mono text-amber-400 flex items-center gap-1 pl-2">
                        <AlertTriangle className="h-3 w-3" /> Firewall intercepted this node
                      </div>
                    )}

                    {/* Error */}
                    {node.errorMessage && (
                      <div className="bg-destructive/10 text-destructive text-sm p-3 rounded-md font-mono">
                        <AlertTriangle className="h-4 w-4 inline mr-2" />
                        {node.errorMessage}
                      </div>
                    )}

                    {/* Output */}
                    {node.output && (
                      <div className="bg-muted/30 p-3 rounded-md overflow-x-auto text-xs font-mono text-foreground/80">
                        <pre>
                          {(() => {
                            try {
                              return JSON.stringify(JSON.parse(node.output), null, 2);
                            } catch {
                              return node.output;
                            }
                          })()}
                        </pre>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </ScrollArea>
        </CardContent>
      </Card>
    </div>
  );
}
