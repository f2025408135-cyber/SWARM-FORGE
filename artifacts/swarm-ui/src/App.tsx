import { Switch, Route, Router as WouterRouter } from "wouter";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import NotFound from "@/pages/not-found";
import { Shell } from "@/components/layout/Shell";
import Dashboard from "@/pages/dashboard";
import Forge from "@/pages/forge";
import Swarms from "@/pages/swarms";
import SwarmDetail from "@/pages/swarm-detail";
import Security from "@/pages/security";
import History from "@/pages/history";

const queryClient = new QueryClient();

function Router() {
  return (
    <Shell>
      <Switch>
        <Route path="/" component={Dashboard} />
        <Route path="/forge" component={Forge} />
        <Route path="/swarms" component={Swarms} />
        <Route path="/swarms/:id" component={SwarmDetail} />
        <Route path="/security" component={Security} />
        <Route path="/history" component={History} />
        <Route component={NotFound} />
      </Switch>
    </Shell>
  );
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <WouterRouter base={import.meta.env.BASE_URL.replace(/\/$/, "")}>
          <Router />
        </WouterRouter>
        <Toaster />
      </TooltipProvider>
    </QueryClientProvider>
  );
}

export default App;

