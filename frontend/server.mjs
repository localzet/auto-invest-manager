import { createReadStream, statSync } from "node:fs";
import { createServer, request as proxyRequest } from "node:http";
import { extname, join, normalize, sep } from "node:path";

const root = join(import.meta.dirname, "dist");
const backend = new URL(process.env.BACKEND_URL ?? "http://backend:8000");
const contentTypes = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
};

function proxy(clientRequest, clientResponse) {
  const upstream = proxyRequest(
    {
      hostname: backend.hostname,
      port: backend.port,
      path: clientRequest.url,
      method: clientRequest.method,
      headers: { ...clientRequest.headers, host: backend.host },
    },
    (upstreamResponse) => {
      clientResponse.writeHead(upstreamResponse.statusCode ?? 502, upstreamResponse.headers);
      upstreamResponse.pipe(clientResponse);
    },
  );
  upstream.on("error", () => {
    clientResponse.writeHead(502, { "content-type": "application/json" });
    clientResponse.end(JSON.stringify({ detail: "Backend is unavailable" }));
  });
  clientRequest.pipe(upstream);
}

function staticFile(clientRequest, clientResponse) {
  const pathname = decodeURIComponent(new URL(clientRequest.url, "http://localhost").pathname);
  const candidate = normalize(join(root, pathname));
  let file = candidate === root || candidate.startsWith(`${root}${sep}`)
    ? candidate
    : join(root, "index.html");
  try {
    if (!statSync(file).isFile()) file = join(root, "index.html");
  } catch {
    file = join(root, "index.html");
  }
  clientResponse.writeHead(200, {
    "content-type": contentTypes[extname(file)] ?? "application/octet-stream",
    "x-content-type-options": "nosniff",
  });
  createReadStream(file).pipe(clientResponse);
}

createServer((clientRequest, clientResponse) => {
  if (clientRequest.url.startsWith("/api/") || clientRequest.url.startsWith("/health/")) {
    proxy(clientRequest, clientResponse);
  } else {
    staticFile(clientRequest, clientResponse);
  }
}).listen(3000, "0.0.0.0");
