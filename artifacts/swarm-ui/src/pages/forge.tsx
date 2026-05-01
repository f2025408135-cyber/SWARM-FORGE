import { useState } from "react";
import { useLocation } from "wouter";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { useCreateSwarm } from "@workspace/api-client-react";
import { useToast } from "@/hooks/use-toast";
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from "@/components/ui/card";
import { Form, FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Hammer, Loader2 } from "lucide-react";

const formSchema = z.object({
  task: z.string().min(10, "Task description must be at least 10 characters.").max(2000),
  maxWorkers: z.coerce.number().min(1).max(16).default(5),
  modelTier: z.enum(["haiku", "sonnet", "opus"]).default("sonnet"),
  mockMode: z.boolean().default(true),
});

export default function Forge() {
  const [, setLocation] = useLocation();
  const { toast } = useToast();
  
  const form = useForm<z.infer<typeof formSchema>>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      task: "",
      maxWorkers: 5,
      modelTier: "sonnet",
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
      onError: (error) => {
        toast({
          variant: "destructive",
          title: "Failed to plan swarm",
          description: error.message || "An unexpected error occurred.",
        });
      },
    }
  });

  function onSubmit(values: z.infer<typeof formSchema>) {
    createSwarm.mutate({ data: values });
  }

  return (
    <div className="space-y-6 max-w-3xl mx-auto">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Swarm Forge</h1>
        <p className="text-muted-foreground mt-2">Initialize and plan a new AI agent swarm.</p>
      </div>

      <Card className="border-border bg-card">
        <CardHeader>
          <CardTitle>Mission Directives</CardTitle>
          <CardDescription>
            Provide natural language instructions. The orchestrator will plan a DAG of specialized agents to execute the task.
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
                        placeholder="e.g. Analyze the current attack surface of the target web application and suggest mitigations..." 
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
                  name="modelTier"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Model Tier</FormLabel>
                      <Select onValueChange={field.onChange} defaultValue={field.value}>
                        <FormControl>
                          <SelectTrigger className="bg-background">
                            <SelectValue placeholder="Select a tier" />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          <SelectItem value="haiku">Haiku (Fast/Cheap)</SelectItem>
                          <SelectItem value="sonnet">Sonnet (Balanced)</SelectItem>
                          <SelectItem value="opus">Opus (Maximum Reasoning)</SelectItem>
                        </SelectContent>
                      </Select>
                      <FormDescription>
                        Determines the underlying LLM capability for agents.
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
                        Maximum number of agents running in parallel.
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
                        Run simulation without calling external LLM APIs (saves credits)
                      </FormDescription>
                    </div>
                    <FormControl>
                      <Switch
                        checked={field.value}
                        onCheckedChange={field.onChange}
                      />
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
