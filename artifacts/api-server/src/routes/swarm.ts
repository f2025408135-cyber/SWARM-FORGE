import { Router } from "express";
import { createProxyMiddleware } from "http-proxy-middleware";
import type { Request } from "express";

const SWARM_PORT = process.env.SWARM_PORT ?? 5000;

const swarmProxy = createProxyMiddleware({
  target: `http://localhost:${SWARM_PORT}`,
  changeOrigin: true,
  pathRewrite: (_path: string, req: Request) =>
    (req.originalUrl ?? _path).replace(/^\/api/, ""),
  on: {
    error: (_err: unknown, _req: unknown, res: any) => {
      res.status(502).json({
        error: "swarm_service_unavailable",
        message:
          "SWARM-FORGE service is starting up. Please try again in a moment.",
      });
    },
  },
});

const swarmRouter = Router();

swarmRouter.use("/swarms", swarmProxy);
swarmRouter.use("/dashboard/stats", swarmProxy);
swarmRouter.use("/security/events", swarmProxy);
swarmRouter.use("/security/firewall/test", swarmProxy);

export default swarmRouter;
