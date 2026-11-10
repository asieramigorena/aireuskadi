// Air quality service entry point. Routes and the PostgreSQL pool go here.
import Fastify from "fastify";

const app = Fastify({ logger: true });

const port = Number(process.env.PORT ?? 3000);
await app.listen({ host: "0.0.0.0", port });
