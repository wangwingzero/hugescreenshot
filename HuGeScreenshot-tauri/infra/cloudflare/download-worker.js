const DEFAULT_ORIGIN_HOST = "downloads.example.com";
const DEFAULT_REGION = "us-east-1";
const RELEASE_PATH_RE = /^\/v\d+\.\d+\.\d+\//;
const SIGNED_HEADERS = "host;x-amz-content-sha256;x-amz-date";
const PRESIGNED_HEADERS = "host";
const PRESIGNED_EXPIRES_SECONDS = 60 * 60;
const UNSIGNED_PAYLOAD = "UNSIGNED-PAYLOAD";

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (request.method !== "GET" && request.method !== "HEAD") {
      return new Response("Method Not Allowed", {
        status: 405,
        headers: corsHeaders(new Headers({ allow: "GET, HEAD" })),
      });
    }

    if (url.pathname === "/") {
      const originHost = env.ORIGIN_HOST || DEFAULT_ORIGIN_HOST;
      return Response.redirect(`https://${originHost}/`, 302);
    }

    const isReleaseAsset = RELEASE_PATH_RE.test(url.pathname);
    const isLatestManifest = url.pathname === "/latest.json";

    if (isReleaseAsset) {
      const location = await createPresignedR2Url(request, env);
      const headers = corsHeaders(new Headers({
        location,
        "cache-control": "no-store",
      }));
      headers.set("x-hugescreenshot-accelerated", "cloudflare-r2-presigned");

      return new Response(null, {
        status: 307,
        headers,
      });
    }

    const r2Request = await createR2Request(request, env);
    const r2Response = await fetch(r2Request);
    const headers = corsHeaders(new Headers(r2Response.headers));

    headers.set("x-hugescreenshot-accelerated", "cloudflare-r2-worker");
    headers.set("content-type", contentTypeForPath(url.pathname, headers.get("content-type")));

    if (isLatestManifest) {
      headers.set("cache-control", "no-store, no-cache, must-revalidate, max-age=0");
    }

    return new Response(r2Response.body, {
      status: r2Response.status,
      statusText: r2Response.statusText,
      headers,
    });
  },
};

async function createR2Request(request, env) {
  const { endpoint, bucket, accessKeyId, secretAccessKey, region } = getR2Config(env);

  const inputUrl = new URL(request.url);
  const endpointUrl = new URL(endpoint);
  const r2Url = new URL(endpoint);
  r2Url.pathname = `/${bucket}${inputUrl.pathname}`;
  r2Url.search = inputUrl.search;

  const now = new Date();
  const amzDate = toAmzDate(now);
  const dateStamp = amzDate.slice(0, 8);
  const credentialScope = `${dateStamp}/${region}/s3/aws4_request`;
  const canonicalUri = r2Url.pathname
    .split("/")
    .map((segment) => encodeRFC3986(decodeURIComponent(segment)))
    .join("/");
  const canonicalQueryString = canonicalizeQuery(r2Url.searchParams);
  const canonicalHeaders = [
    `host:${endpointUrl.host}`,
    `x-amz-content-sha256:${UNSIGNED_PAYLOAD}`,
    `x-amz-date:${amzDate}`,
    "",
  ].join("\n");

  const canonicalRequest = [
    request.method,
    canonicalUri,
    canonicalQueryString,
    canonicalHeaders,
    SIGNED_HEADERS,
    UNSIGNED_PAYLOAD,
  ].join("\n");

  const stringToSign = [
    "AWS4-HMAC-SHA256",
    amzDate,
    credentialScope,
    await sha256Hex(canonicalRequest),
  ].join("\n");

  const signingKey = await getSignatureKey(secretAccessKey, dateStamp, region, "s3");
  const signature = await hmacHex(signingKey, stringToSign);
  const authorization = `AWS4-HMAC-SHA256 Credential=${accessKeyId}/${credentialScope}, SignedHeaders=${SIGNED_HEADERS}, Signature=${signature}`;

  const headers = new Headers();
  headers.set("authorization", authorization);
  headers.set("host", endpointUrl.host);
  headers.set("x-amz-content-sha256", UNSIGNED_PAYLOAD);
  headers.set("x-amz-date", amzDate);

  copyHeader(request.headers, headers, "range");
  copyHeader(request.headers, headers, "if-match");
  copyHeader(request.headers, headers, "if-none-match");
  copyHeader(request.headers, headers, "if-modified-since");
  copyHeader(request.headers, headers, "if-unmodified-since");

  return new Request(r2Url.toString(), {
    method: request.method,
    headers,
  });
}

async function createPresignedR2Url(request, env) {
  const { endpoint, bucket, accessKeyId, secretAccessKey, region } = getR2Config(env);

  const inputUrl = new URL(request.url);
  const endpointUrl = new URL(endpoint);
  const r2Url = new URL(endpoint);
  r2Url.pathname = `/${bucket}${inputUrl.pathname}`;
  r2Url.search = inputUrl.search;

  const now = new Date();
  const amzDate = toAmzDate(now);
  const dateStamp = amzDate.slice(0, 8);
  const credentialScope = `${dateStamp}/${region}/s3/aws4_request`;

  r2Url.searchParams.set("X-Amz-Algorithm", "AWS4-HMAC-SHA256");
  r2Url.searchParams.set("X-Amz-Credential", `${accessKeyId}/${credentialScope}`);
  r2Url.searchParams.set("X-Amz-Date", amzDate);
  r2Url.searchParams.set("X-Amz-Expires", String(PRESIGNED_EXPIRES_SECONDS));
  r2Url.searchParams.set("X-Amz-SignedHeaders", PRESIGNED_HEADERS);

  const canonicalUri = r2Url.pathname
    .split("/")
    .map((segment) => encodeRFC3986(decodeURIComponent(segment)))
    .join("/");
  const canonicalQueryString = canonicalizeQuery(r2Url.searchParams);
  const canonicalHeaders = `host:${endpointUrl.host}\n`;

  const canonicalRequest = [
    request.method,
    canonicalUri,
    canonicalQueryString,
    canonicalHeaders,
    PRESIGNED_HEADERS,
    UNSIGNED_PAYLOAD,
  ].join("\n");

  const stringToSign = [
    "AWS4-HMAC-SHA256",
    amzDate,
    credentialScope,
    await sha256Hex(canonicalRequest),
  ].join("\n");

  const signingKey = await getSignatureKey(secretAccessKey, dateStamp, region, "s3");
  const signature = await hmacHex(signingKey, stringToSign);
  r2Url.searchParams.set("X-Amz-Signature", signature);

  return r2Url.toString();
}

function getR2Config(env) {
  return {
    endpoint: required(env.R2_ENDPOINT, "R2_ENDPOINT").replace(/\/+$/, ""),
    bucket: required(env.R2_BUCKET, "R2_BUCKET").replace(/^\/+|\/+$/g, ""),
    accessKeyId: required(env.R2_ACCESS_KEY_ID, "R2_ACCESS_KEY_ID"),
    secretAccessKey: required(env.R2_SECRET_ACCESS_KEY, "R2_SECRET_ACCESS_KEY"),
    region: env.R2_REGION || DEFAULT_REGION,
  };
}

function required(value, name) {
  if (!value) throw new Error(`Missing ${name}`);
  return value;
}

function copyHeader(from, to, name) {
  const value = from.get(name);
  if (value) to.set(name, value);
}

function corsHeaders(headers) {
  headers.set("access-control-allow-origin", "*");
  headers.set("access-control-allow-methods", "GET, HEAD");
  headers.set("access-control-expose-headers", "content-length, content-range, accept-ranges, etag");
  return headers;
}

function contentTypeForPath(pathname, currentValue) {
  if (pathname.endsWith(".json")) return "application/json; charset=utf-8";
  if (pathname.endsWith(".sig")) return "text/plain; charset=utf-8";
  if (pathname.endsWith(".zip")) return "application/zip";
  if (pathname.endsWith(".exe")) return "application/octet-stream";
  return currentValue || "application/octet-stream";
}

function toAmzDate(date) {
  return date.toISOString().replace(/[:-]|\.\d{3}/g, "");
}

function canonicalizeQuery(searchParams) {
  const pairs = [];
  for (const [key, value] of searchParams) {
    pairs.push([encodeRFC3986(key), encodeRFC3986(value)]);
  }
  pairs.sort(([aKey, aValue], [bKey, bValue]) => (
    aKey === bKey ? aValue.localeCompare(bValue) : aKey.localeCompare(bKey)
  ));
  return pairs.map(([key, value]) => `${key}=${value}`).join("&");
}

function encodeRFC3986(value) {
  return encodeURIComponent(value).replace(/[!'()*]/g, (char) => (
    `%${char.charCodeAt(0).toString(16).toUpperCase()}`
  ));
}

async function sha256Hex(value) {
  const bytes = new TextEncoder().encode(value);
  const hash = await crypto.subtle.digest("SHA-256", bytes);
  return bytesToHex(new Uint8Array(hash));
}

async function hmac(keyBytes, value) {
  const key = await crypto.subtle.importKey(
    "raw",
    keyBytes,
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const signature = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(value));
  return new Uint8Array(signature);
}

async function hmacHex(keyBytes, value) {
  return bytesToHex(await hmac(keyBytes, value));
}

async function getSignatureKey(secretAccessKey, dateStamp, regionName, serviceName) {
  const dateKey = await hmac(new TextEncoder().encode(`AWS4${secretAccessKey}`), dateStamp);
  const dateRegionKey = await hmac(dateKey, regionName);
  const dateRegionServiceKey = await hmac(dateRegionKey, serviceName);
  return hmac(dateRegionServiceKey, "aws4_request");
}

function bytesToHex(bytes) {
  return [...bytes].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}
