import { useState } from "react";
import { useGetSecurityEvents, useTestFirewall } from "@workspace/api-client-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription, CardFooter } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ShieldAlert, ShieldCheck, Shield, AlertOctagon, Terminal } from "lucide-react";
import { formatDate } from "@/lib/formatters";
import { useToast } from "@/hooks/use-toast";

export default function Security() {
  const { toast } = useToast();
  const [testPayload, setTestPayload] = useState("");
  const [testResult, setTestResult] = useState<any>(null);

  const { data, isLoading } = useGetSecurityEvents(
    { limit: 20 },
    { query: { refetchInterval: 5000 } }
  );

  const testFirewall = useTestFirewall({
    mutation: {
      onSuccess: (res) => {
        setTestResult(res);
        toast({
          title: res.passed ? "Payload Passed" : "Payload Blocked",
          description: res.verdictMessage,
          variant: res.passed ? "default" : "destructive"
        });
      }
    }
  });

  const handleTest = () => {
    if (!testPayload.trim()) return;
    testFirewall.mutate({ data: { payload: testPayload } });
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Security Console</h1>
        <p className="text-muted-foreground mt-2">Zero-trust firewall monitoring and testing.</p>
      </div>

      <div className="grid lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          <Card className="border-border bg-card">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <ShieldAlert className="h-5 w-5" /> Recent Interventions
              </CardTitle>
              <CardDescription>All payloads evaluated by the Zero-Trust Action Firewall</CardDescription>
            </CardHeader>
            <CardContent>
              {isLoading ? (
                <div className="space-y-4">
                  {[1,2,3,4].map(i => <div key={i} className="h-16 bg-muted/50 rounded animate-pulse" />)}
                </div>
              ) : data?.events && data.events.length > 0 ? (
                <div className="space-y-0">
                  {data.events.map(event => (
                    <div key={event.id} className="flex flex-col sm:flex-row sm:items-center justify-between border-b border-border/50 py-4 last:border-0 last:pb-0 first:pt-0">
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          {event.verdict === 'passed' ? (
                            <ShieldCheck className="h-4 w-4 text-chart-3" />
                          ) : event.verdict === 'dropped' ? (
                            <AlertOctagon className="h-4 w-4 text-chart-4" />
                          ) : (
                            <ShieldAlert className="h-4 w-4 text-destructive" />
                          )}
                          <span className="font-mono text-xs uppercase tracking-wider font-bold">
                            {event.eventType.replace(/_/g, ' ')}
                          </span>
                        </div>
                        <div className="text-sm font-mono bg-muted/30 p-2 rounded truncate max-w-md text-muted-foreground">
                          {event.payload}
                        </div>
                        {event.blockedPattern && (
                          <div className="text-xs text-destructive">Pattern matched: {event.blockedPattern}</div>
                        )}
                        {event.droppedCapabilities.length > 0 && (
                          <div className="text-xs text-chart-4">Dropped: {event.droppedCapabilities.join(', ')}</div>
                        )}
                      </div>
                      <div className="text-xs text-muted-foreground mt-2 sm:mt-0 text-right shrink-0">
                        {formatDate(event.timestamp)}
                        {event.swarmId && <div className="font-mono mt-1 opacity-50">Swarm: {event.swarmId.substring(0,6)}</div>}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-12 text-muted-foreground">No security events recorded.</div>
              )}
            </CardContent>
          </Card>
        </div>

        <div className="space-y-6">
          <Card className="border-border bg-card">
            <CardHeader className="bg-primary/5 border-b border-border/50">
              <CardTitle className="flex items-center gap-2 text-primary">
                <Terminal className="h-5 w-5" /> Payload Tester
              </CardTitle>
              <CardDescription>Test a payload against current firewall rules.</CardDescription>
            </CardHeader>
            <CardContent className="pt-6 space-y-4">
              <Textarea 
                placeholder="Enter bash command, JSON, or any payload to evaluate..."
                className="font-mono text-sm min-h-[120px] bg-background"
                value={testPayload}
                onChange={(e) => setTestPayload(e.target.value)}
              />
              <Button 
                className="w-full" 
                onClick={handleTest}
                disabled={testFirewall.isPending || !testPayload.trim()}
              >
                Evaluate Payload
              </Button>

              {testResult && (
                <div className={`p-4 rounded-md border mt-4 text-sm ${
                  testResult.passed ? 'bg-chart-3/10 border-chart-3/30 text-chart-3' : 'bg-destructive/10 border-destructive/30 text-destructive'
                }`}>
                  <div className="font-bold mb-2 flex items-center gap-2">
                    {testResult.passed ? <ShieldCheck className="h-4 w-4" /> : <ShieldAlert className="h-4 w-4" />}
                    {testResult.verdictMessage}
                  </div>
                  {!testResult.passed && testResult.blockedPattern && (
                    <div className="font-mono text-xs opacity-90 mt-1">Rule: {testResult.blockedPattern}</div>
                  )}
                  {testResult.droppedCapabilities.length > 0 && (
                    <div className="text-xs opacity-90 mt-1">Dropped tools: {testResult.droppedCapabilities.join(', ')}</div>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
