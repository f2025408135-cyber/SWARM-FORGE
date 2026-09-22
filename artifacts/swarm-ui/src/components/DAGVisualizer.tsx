import { useMemo } from "react";

// Note: A real DAG visualizer would use a library like react-flow. 
// For this design constraint, we'll build a CSS-grid/flex based layout or simple canvas approximation.
// To keep things responsive and purely React based, we'll render a simplified column-based DAG view.

type NodeStatus = "pending" | "running" | "success" | "failed" | "skipped" | "blocked";

interface Node {
  id: string;
  label: string;
  status: NodeStatus;
  dependencies: string[];
}

export function DAGVisualizer({ nodes, edges, parallelGroups }: { nodes: Node[], edges: string[][], parallelGroups: string[][] }) {
  // Simple heuristic: display by parallel groups which loosely represents topological sort layers
  
  if (!parallelGroups || parallelGroups.length === 0) {
    return <div className="p-8 text-center text-muted-foreground">No DAG generated yet.</div>;
  }

  const getStatusColor = (status: NodeStatus) => {
    switch (status) {
      case 'pending': return 'border-muted-foreground text-muted-foreground bg-muted/20';
      case 'running': return 'border-primary text-primary bg-primary/20 animate-pulse';
      case 'success': return 'border-chart-3 text-chart-3 bg-chart-3/20';
      case 'failed': return 'border-destructive text-destructive bg-destructive/20';
      case 'skipped': return 'border-muted text-muted-foreground opacity-50';
      case 'blocked': return 'border-chart-4 text-chart-4 bg-chart-4/20';
      default: return 'border-border text-foreground bg-card';
    }
  };

  return (
    <div className="w-full overflow-x-auto pb-4">
      <div className="flex gap-8 items-center min-w-max p-4">
        {parallelGroups.map((group, groupIdx) => (
          <div key={groupIdx} className="flex flex-col gap-4 relative">
            {/* If not first group, draw an incoming connector hint */}
            {groupIdx > 0 && (
              <div className="absolute -left-6 top-1/2 w-4 border-t border-dashed border-border" />
            )}
            
            <div className="text-[10px] uppercase text-muted-foreground text-center tracking-widest font-mono">
              Stage {groupIdx + 1}
            </div>
            
            {group.map((nodeId) => {
              const node = nodes.find(n => n.id === nodeId);
              if (!node) return null;
              
              return (
                <div 
                  key={node.id} 
                  className={`p-3 rounded-md border text-sm font-mono w-48 shadow-sm flex flex-col justify-center transition-colors ${getStatusColor(node.status)}`}
                  title={node.label}
                >
                  <div className="truncate font-bold mb-1 opacity-80">{node.id}</div>
                  <div className="truncate text-xs">{node.label}</div>
                </div>
              );
            })}

            {/* If not last group, draw an outgoing connector hint */}
            {groupIdx < parallelGroups.length - 1 && (
              <div className="absolute -right-6 top-1/2 w-4 border-t border-dashed border-border" />
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
