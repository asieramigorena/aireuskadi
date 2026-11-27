# Image of the air quality service. Build it with the repository root as context:
#   docker compose build air-quality-service
# It is not called "Dockerfile" on purpose: deploy-pro.yml builds a file with that exact name using its
# own folder as context, and a file called <name>.Dockerfile in a folder of services/ using the root
# of the repository as context. This service needs nothing outside its folder: it uses the root only
# to be built the same way as the other services.

# Node runs the TypeScript as it is: it erases the types when it loads a file (type stripping, on by
# default since Node 22.18), so there is nothing to compile and one stage is enough. The types are
# checked in the CI (npm run lint), not here. Only the packages that run: no compiler, no test tools.
# The base image by its digest: a tag can be published again.
# Security fix by Claude (audit 2026-11-26).
FROM node:22-slim@sha256:be979e5523c76fa4d5ca4ebd3099078f220aa47ec39c48ad5b5df9314debd6eb
ENV NODE_ENV=production
WORKDIR /app
COPY services/air-quality-service/package.json services/air-quality-service/package-lock.json ./
# --ignore-scripts: no package runs code while it is installed.
RUN npm ci --omit=dev --ignore-scripts && npm cache clean --force
COPY services/air-quality-service/src src

# The image of Node brings this user: the service does not run as root.
USER node
EXPOSE 8000
# The log comes from the application (JSON). It listens on every interface of the container, but the
# compose publishes no port: only the other containers of the internal network can reach it.
CMD ["node", "src/server.ts"]
