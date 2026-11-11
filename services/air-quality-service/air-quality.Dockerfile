# Image of the air quality service. Build it with the repository root as context:
#   docker compose build air-quality-service
# It is not called "Dockerfile" on purpose: deploy-pro.yml builds a file with that exact name using its
# own folder as context, and a file called <name>.Dockerfile in a folder of services/ using the root
# of the repository as context. This service needs nothing outside its folder: it uses the root only
# to be built the same way as the other services.

# Stage 1: compile the TypeScript. The tests and the tools to compile stay in this stage.
FROM node:22-slim AS build
WORKDIR /app
COPY services/air-quality-service/package.json services/air-quality-service/package-lock.json ./
# --ignore-scripts: no package runs code while it is installed.
RUN npm ci --ignore-scripts
COPY services/air-quality-service/tsconfig.json services/air-quality-service/tsconfig.build.json ./
COPY services/air-quality-service/src src
RUN npm run build

# Stage 2: only what runs. No compiler, no test tools.
FROM node:22-slim
ENV NODE_ENV=production
WORKDIR /app
COPY services/air-quality-service/package.json services/air-quality-service/package-lock.json ./
RUN npm ci --omit=dev --ignore-scripts && npm cache clean --force
COPY --from=build /app/dist dist

# The image of Node brings this user: the service does not run as root.
USER node
EXPOSE 8000
# The log comes from the application (JSON). It listens on every interface of the container, but the
# compose publishes no port: only the other containers of the internal network can reach it.
CMD ["node", "dist/server.js"]
