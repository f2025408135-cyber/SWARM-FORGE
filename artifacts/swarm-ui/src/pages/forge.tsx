import { useState } from "react";
import { useLocation } from "wouter";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { useCreateSwarm, useGetProvidersStatus } from "@workspace/api-client-react";
import { useToast } from "@/hooks/use-toast";
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from "@/components/ui/card";
import { Form, FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Hammer, Loader2, Zap, CheckCircle2, XCircle, Info } from "lucide-react";

const TIER_META: Record<string, { label: string; description: string; color: string }> = {
  nano:     { label: "Nano",     color: "text-slate-400",   description: "Ultra-fast · tagging, classification, simple extraction" },
  small:    { label: "Small",    color: "text-blue-400",    description: "Lightweight · summarization, basic Q&A, simple code review" },
  medium:   { label: "Medium",   color: "text-cyan-400",    description: "Balanced · multi-step reasoning, analysis, code generation" },
  large:    { label: "Large",    color: "text-violet-400",  description: "Advanced · strategic planning, complex synthesis, advanced code" },
  frontier: { label: "Frontier", color: "text-amber-400",   description: "Maximum · highest reasoning, critical decisions, creative synthesis" },
};

const PROVIDER_META: Record<string, { label: string; color: string }> = {
  openai:     { label: "OpenAI",      color: "#10A37F" },
  anthropic:  { label: "Anthropic",   color: "#CC785C" },
  google:     { label: "Google",      color: "#4285F4" },
  mistral:    { label: "Mistral AI",  color: "#FF7000" },
  groq:       { label: "Groq",        color: "#F55036" },
  cohere:     { label: "Cohere",      color: "#39594D" },
  openrouter: { label: "OpenRouter",  color: "#6D28D9" },
};

const formSchema = z.object({
  task: z.string().min(10, "Task description must be at least 10 characters.").max(2000),
  maxWorkers: z.coerce.number().min(1).max(16).default(5),
  preferredProvider: z.string().nullable().default(null),
  mockMode: z.boolean().default(true),
});

export default function Forge() {
  const [, setLocation] = useLocation();
  const { toast } = useToast();

  const { data: providerStatus } = useGetProvidersStatus();

  const form = useForm<z.infer<typeof formSchema>>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      task: "",
      maxWorkers: 5,
      preferredProvider: null,
      mockMode: true,
    },
  });

  const createSwarm = useCreateSwarm({
    mutation: {
      onSuccess: (data) => {
        toast({
          title: "Swarm Planned",
          description: "Your swarm has been planned and is ready for review.",
        });
        setLocation(`/swarms/${data.id}`);
      },
      onError: (error: any) => {
        toast({
          variant: "destructive",
          title: "Failed to plan swarm",
          description: error.message || "An unexpected error occurred.",
        });
      },
    },
  });

  function onSubmit(values: z.infer<typeof formSchema>) {
    createSwarm.mutate({
      data: {
        task: values.task,
        maxWorkers: values.maxWorkers,
        preferredProvider: values.preferredProvider as any,
        mockMode: values.mockMode,
      },
    });
  }

  const availableProviders = providerStatus?.availableProviders ?? [];
  const hasAnyKey = (providerStatus?.hasAnyKey) ?? false;

  return (
    <div className="space-y-6 max-w-3xl mx-auto">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Swarm Forge</h1>
        <p className="text-muted-foreground mt-2">
          Initialize and plan a new AI agent swarm. The orchestrator selects the best available model per task node.
        </p>
      </div>

      {/* Provider Status Panel */}
      <Card className="border-border bg-card">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-mono uppercase tracking-wider flex items-center gap-2">
            <Zap className="h-4 w-4 text-primary" /> Configured Providers
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-2">
            {Object.entries(PROVIDER_META).map(([id, meta]) => {
              const configured = availableProviders.includes(id);
              return (
                <div
                  key={id}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full border text-xs font-mono transition-all ${
                    configured
                      ? "border-primary/30 bg-primary/10 text-foreground"
                      : "border-border/30 bg-muted/20 text-muted-foreground opacity-50"
                  }`}
                >
                  {configured
                    ? <CheckCircle2 className="h-3 w-3 text-primary" />
                    : <XCircle className="h-3 w-3" />
                  }
                  <span style={{ color: configured ? meta.color : undefined }}>{meta.label}</span>
                </div>
              );
            })}
          </div>
          {!hasAnyKey && (
            <p className="text-xs text-muted-foreground mt-3 flex items-center gap-1.5">
              <Info className="h-3 w-3" />
              No API keys configured — swarms will run in mock mode. Add provider keys as environment secrets to enable live execution.
            </p>
          )}
        </CardContent>
      </Card>

      {/* Tier Reference */}
      <Card className="border-border bg-card">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-mono uppercase tracking-wider">Model Tier Reference</CardTitle>
          <CardDescription>The orchestrator automatically assigns tiers to each node based on task complexity.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 sm:grid-cols-5 gap-2">
            {Object.entries(TIER_META).map(([tier, meta]) => {
              const tierInfo = providerStatus?.tiers?.[tier];
              const model = tierInfo?.resolvedModel ?? tierInfo?.mockModel;
              const provider = tierInfo?.resolvedProvider ?? tierInfo?.mockProvider;
              return (
                <div key={tier} className="rounded-lg border border-border/50 bg-muted/10 p-3 space-y-1">
                  <div className={`text-xs font-bold uppercase tracking-wider font-mono ${meta.color}`}>{meta.label}</div>
                  <div className="text-[10px] text-muted-foreground leading-tight">{meta.description}</div>
                  {model && (
                    <div className="text-[10px] font-mono text-primary/70 mt-1 truncate" title={`${provider}: ${model}`}>
                      → {model}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {/* Main Form */}
      <Card className="border-border bg-card">
        <CardHeader>
          <CardTitle>Mission Directives</CardTitle>
          <CardDescription>
            Provide natural language instructions. The orchestrator will plan a DAG of specialized agents and route each node to the optimal model tier.
          </CardDescription>
        </CardHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)}>
            <CardContent className="space-y-6">
              <FormField
                control={form.control}
                name="task"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Task Description</FormLabel>
                    <FormControl>
                      <Textarea
                        placeholder="e.g. Perform a comprehensive security audit of the authentication system, including JWT analysis and endpoint enumeration..."
                        className="min-h-[150px] font-mono text-sm bg-background"
                        {...field}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <div className="grid md:grid-cols-2 gap-6">
                <FormField
                  control={form.control}
                  name="preferredProvider"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Preferred Provider</FormLabel>
                      <Select
                        onValueChange={(val) => field.onChange(val === "auto" ? null : val)}
                        defaultValue="auto"
                      >
                        <FormControl>
                          <SelectTrigger className="bg-background">
                            <SelectValue placeholder="Auto-select" />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          <SelectItem value="auto">
                            <span className="flex items-center gap-2">
                              <Zap className="h-3 w-3 text-primary" /> Auto-select (recommended)
                            </span>
                          </SelectItem>
                          {Object.entries(PROVIDER_META).map(([id, meta]) => {
                            const configured = availableProviders.includes(id);
                            return (
                              <SelectItem key={id} value={id} disabled={!configured && hasAnyKey}>
                                <span className="flex items-center gap-2">
                                  <span
                                    className="inline-block w-2 h-2 rounded-full"
                                    style={{ backgroundColor: meta.color }}
                                  />
                                  {meta.label}
                                  {!configured && (
                                    <span className="text-muted-foreground text-xs">(no key)</span>
                                  )}
                                </span>
                              </SelectItem>
                            );
                          })}
                        </SelectContent>
                      </Select>
                      <FormDescription>
                        Override the router to force a specific provider for all nodes.
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="maxWorkers"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Max Concurrent Workers</FormLabel>
                      <FormControl>
                        <Input type="number" min={1} max={16} className="bg-background" {...field} />
                      </FormControl>
                      <FormDescription>
                        Maximum agents running in parallel per DAG stage.
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>

              <FormField
                control={form.control}
                name="mockMode"
                render={({ field }) => (
                  <FormItem className="flex flex-row items-center justify-between rounded-lg border border-border p-4 bg-muted/20">
                    <div className="space-y-0.5">
                      <FormLabel className="text-base">Mock Execution Mode</FormLabel>
                      <FormDescription>
                        Simulate execution without calling any LLM APIs — shows which models would be used.
                      </FormDescription>
                    </div>
                    <FormControl>
                      <Switch checked={field.value} onCheckedChange={field.onChange} />
                    </FormControl>
                  </FormItem>
                )}
              />
            </CardContent>
            <CardFooter className="flex justify-end border-t border-border/50 pt-6">
              <Button type="submit" disabled={createSwarm.isPending} className="w-full md:w-auto">
                {createSwarm.isPending ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Hammer className="mr-2 h-4 w-4" />
                )}
                Generate Execution Plan
              </Button>
            </CardFooter>
          </form>
        </Form>
      </Card>
    </div>
  );
}
