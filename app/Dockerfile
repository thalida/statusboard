FROM node:22-alpine AS build
WORKDIR /srv/app
RUN corepack enable
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY . .
RUN pnpm build

FROM nginx:1.27-alpine AS runtime
# Rebuilt every image, so a cached layer cannot pin an apk state to
# the day it was first built. The API's Dockerfile does the same.
RUN apk upgrade --no-cache
COPY --from=build /srv/app/dist /usr/share/nginx/html
# A template, not a config. nginx does not expand a variable in a
# config file, and the official image renders this one with envsubst
# at start. It substitutes the names it finds in the environment, so
# nginx's own $uri survives.
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY security-headers.template /etc/nginx/templates/security-headers.template
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
  CMD wget -qO- http://localhost:8080/ >/dev/null || exit 1
ENTRYPOINT ["/entrypoint.sh"]
CMD ["nginx", "-g", "daemon off;"]
