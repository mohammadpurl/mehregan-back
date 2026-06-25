# Frontend production image — controlled from Backend2 deploy folder.
# Patches legacy Classbon files on every build so old frontend git branches still compile.
#
# Compose: context=../Frontend-Next3/erp, dockerfile=deploy/docker/frontend.Dockerfile

FROM node:20-alpine AS deps
WORKDIR /app

RUN apk add --no-cache libc6-compat

COPY package.json package-lock.json ./
RUN npm ci


FROM node:20-alpine AS builder
WORKDIR /app

RUN apk add --no-cache libc6-compat

ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ARG API_URL=http://backend:8000

ENV NEXT_TELEMETRY_DISABLED=1
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV API_URL=$API_URL

COPY --from=deps /app/node_modules ./node_modules
COPY . .

RUN node <<'PATCH'
const fs = require("fs");
const path = require("path");

function write(rel, content) {
  const full = path.join("/app", rel);
  fs.mkdirSync(path.dirname(full), { recursive: true });
  fs.writeFileSync(full, content, "utf8");
  console.log("[frontend-build-patch]", rel);
}

write(
  "app/(auth)/_components/verification-form.tsx",
  `'use client';\nexport { SignInForm as VerificationForm } from './sign-in-form';\n`
);

write(
  "lib/classbon-icons.tsx",
  `export {
  Clock,
  MessageCircle as Message,
  Phone,
  Eye,
  User,
  Check,
  X,
} from "lucide-react";\n`
);

write(
  "_components/general/button.tsx",
  `export { Button } from "@/app/components/button";\n`
);

write(
  "_components/general/textbox.tsx",
  `export { TextBox } from "@/app/components/textbox";\n`
);

const legacyHttp = "/app/app/core/http-service/http-service-yk.ts";
if (fs.existsSync(legacyHttp)) {
  fs.unlinkSync(legacyHttp);
  console.log("[frontend-build-patch] removed app/core/http-service/http-service-yk.ts");
}

const tsconfigPath = "/app/tsconfig.json";
const tsconfig = JSON.parse(fs.readFileSync(tsconfigPath, "utf8"));
tsconfig.compilerOptions.paths = {
  "@/_components/general/button": ["./app/components/button.tsx"],
  "@/_components/general/textbox": ["./app/components/textbox.tsx"],
  "@classbon/icons": ["./lib/classbon-icons.tsx"],
  ...(tsconfig.compilerOptions.paths || {}),
};
fs.writeFileSync(tsconfigPath, JSON.stringify(tsconfig, null, 2) + "\n");
console.log("[frontend-build-patch] tsconfig.json paths updated");
PATCH

RUN npm run build


FROM node:20-alpine AS runner
WORKDIR /app

RUN apk add --no-cache libc6-compat

ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ARG API_URL=http://backend:8000

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV API_URL=$API_URL

COPY package.json package-lock.json ./
COPY --from=deps /app/node_modules ./node_modules
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/next.config.ts ./next.config.ts

EXPOSE 3000

CMD ["npm", "run", "start", "--", "-H", "0.0.0.0", "-p", "3000"]
