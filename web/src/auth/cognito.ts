/**
 * Cognito hosted-UI OAuth2 authorization-code + PKCE flow.
 *
 * This module deliberately avoids `amazon-cognito-identity-js` — the hosted UI
 * does the heavy lifting, and we only need a small PKCE dance + token cache.
 * Config comes from Vite env vars so a build without them (local dev) still
 * runs against the FastAPI `X-Test-User` fallback.
 */

const DOMAIN = (import.meta.env.VITE_COGNITO_DOMAIN as string | undefined) ?? "";
const CLIENT_ID =
  (import.meta.env.VITE_COGNITO_CLIENT_ID as string | undefined) ?? "";
const REDIRECT_URI =
  (import.meta.env.VITE_COGNITO_REDIRECT_URI as string | undefined) ??
  (typeof window !== "undefined"
    ? `${window.location.origin}/auth/callback`
    : "");
const LOGOUT_URI =
  (import.meta.env.VITE_COGNITO_LOGOUT_URI as string | undefined) ??
  (typeof window !== "undefined" ? window.location.origin : "");

const SCOPE = "openid email profile";

const STORAGE_PREFIX = "dealgate.cognito";
const KEY_ACCESS = `${STORAGE_PREFIX}.access_token`;
const KEY_ID = `${STORAGE_PREFIX}.id_token`;
const KEY_REFRESH = `${STORAGE_PREFIX}.refresh_token`;
const KEY_EXPIRES = `${STORAGE_PREFIX}.expires_at`;
const KEY_VERIFIER = `${STORAGE_PREFIX}.pkce_verifier`;
const KEY_RETURN = `${STORAGE_PREFIX}.return_to`;
const KEY_STATE = `${STORAGE_PREFIX}.state`;

/** Are the Cognito env vars set? Local dev leaves them empty. */
export function isCognitoConfigured(): boolean {
  return Boolean(DOMAIN && CLIENT_ID && REDIRECT_URI);
}

export interface IdTokenClaims {
  sub: string;
  email?: string;
  name?: string;
  "cognito:groups"?: string[];
  "cognito:username"?: string;
  exp?: number;
  iat?: number;
  [k: string]: unknown;
}

// --- PKCE helpers ----------------------------------------------------------

function base64UrlEncode(bytes: Uint8Array): string {
  let bin = "";
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function randomBytes(len: number): Uint8Array {
  const out = new Uint8Array(len);
  crypto.getRandomValues(out);
  return out;
}

async function sha256(input: string): Promise<Uint8Array> {
  const data = new TextEncoder().encode(input);
  const digest = await crypto.subtle.digest("SHA-256", data);
  return new Uint8Array(digest);
}

async function makePkcePair(): Promise<{ verifier: string; challenge: string }> {
  const verifier = base64UrlEncode(randomBytes(32));
  const challenge = base64UrlEncode(await sha256(verifier));
  return { verifier, challenge };
}

// --- Storage ---------------------------------------------------------------

interface StoredTokens {
  accessToken: string | null;
  idToken: string | null;
  refreshToken: string | null;
  expiresAt: number | null; // epoch ms
}

function loadTokens(): StoredTokens {
  if (typeof sessionStorage === "undefined") {
    return { accessToken: null, idToken: null, refreshToken: null, expiresAt: null };
  }
  const expires = sessionStorage.getItem(KEY_EXPIRES);
  return {
    accessToken: sessionStorage.getItem(KEY_ACCESS),
    idToken: sessionStorage.getItem(KEY_ID),
    refreshToken: sessionStorage.getItem(KEY_REFRESH),
    expiresAt: expires ? Number(expires) : null,
  };
}

function storeTokens(tokens: {
  access_token: string;
  id_token: string;
  refresh_token?: string;
  expires_in: number;
}): void {
  if (typeof sessionStorage === "undefined") return;
  sessionStorage.setItem(KEY_ACCESS, tokens.access_token);
  sessionStorage.setItem(KEY_ID, tokens.id_token);
  if (tokens.refresh_token) {
    sessionStorage.setItem(KEY_REFRESH, tokens.refresh_token);
  }
  const expiresAt = Date.now() + tokens.expires_in * 1000;
  sessionStorage.setItem(KEY_EXPIRES, String(expiresAt));
}

/** Wipe the tokens; used on logout and on refresh failure. */
export function clearTokens(): void {
  if (typeof sessionStorage === "undefined") return;
  for (const k of [KEY_ACCESS, KEY_ID, KEY_REFRESH, KEY_EXPIRES, KEY_VERIFIER, KEY_STATE]) {
    sessionStorage.removeItem(k);
  }
}

// --- JWT decode ------------------------------------------------------------

function decodeJwtPayload<T = unknown>(token: string): T | null {
  const parts = token.split(".");
  if (parts.length < 2) return null;
  try {
    const payload = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const padded = payload + "=".repeat((4 - (payload.length % 4)) % 4);
    return JSON.parse(atob(padded)) as T;
  } catch {
    return null;
  }
}

/** Decode the id_token claims from sessionStorage. Returns null if absent. */
export function getIdTokenClaims(): IdTokenClaims | null {
  const { idToken } = loadTokens();
  if (!idToken) return null;
  return decodeJwtPayload<IdTokenClaims>(idToken);
}

// --- Login / logout / callback --------------------------------------------

/**
 * Kick off the hosted-UI login. Stores the current path so the callback can
 * bring the user back to where they came from.
 */
export async function login(returnTo?: string): Promise<void> {
  if (!isCognitoConfigured()) {
    throw new Error("Cognito is not configured");
  }
  const { verifier, challenge } = await makePkcePair();
  const state = base64UrlEncode(randomBytes(16));
  sessionStorage.setItem(KEY_VERIFIER, verifier);
  sessionStorage.setItem(KEY_STATE, state);
  const target = returnTo ?? window.location.pathname + window.location.search;
  sessionStorage.setItem(KEY_RETURN, target);

  const params = new URLSearchParams({
    response_type: "code",
    client_id: CLIENT_ID,
    redirect_uri: REDIRECT_URI,
    scope: SCOPE,
    code_challenge: challenge,
    code_challenge_method: "S256",
    state,
  });
  window.location.assign(`${DOMAIN}/oauth2/authorize?${params.toString()}`);
}

/** Hosted-UI logout, then bounce back to `VITE_COGNITO_LOGOUT_URI`. */
export function logout(): void {
  clearTokens();
  if (!isCognitoConfigured()) {
    if (typeof window !== "undefined") window.location.assign("/");
    return;
  }
  const params = new URLSearchParams({
    client_id: CLIENT_ID,
    logout_uri: LOGOUT_URI,
  });
  window.location.assign(`${DOMAIN}/logout?${params.toString()}`);
}

interface TokenResponse {
  access_token: string;
  id_token: string;
  refresh_token?: string;
  expires_in: number;
  token_type: string;
}

async function exchangeCodeForTokens(code: string, verifier: string): Promise<TokenResponse> {
  const body = new URLSearchParams({
    grant_type: "authorization_code",
    client_id: CLIENT_ID,
    code,
    redirect_uri: REDIRECT_URI,
    code_verifier: verifier,
  });
  const res = await fetch(`${DOMAIN}/oauth2/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: body.toString(),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Token exchange failed (${res.status}): ${text}`);
  }
  return (await res.json()) as TokenResponse;
}

async function refreshWithToken(refreshToken: string): Promise<TokenResponse> {
  const body = new URLSearchParams({
    grant_type: "refresh_token",
    client_id: CLIENT_ID,
    refresh_token: refreshToken,
  });
  const res = await fetch(`${DOMAIN}/oauth2/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: body.toString(),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Token refresh failed (${res.status}): ${text}`);
  }
  return (await res.json()) as TokenResponse;
}

/**
 * Called by the /auth/callback route. Reads `code`+`state` from the URL,
 * validates state, exchanges the code, stores tokens, and returns the path
 * the caller stashed before login.
 */
export async function handleCallback(): Promise<string> {
  if (!isCognitoConfigured()) {
    throw new Error("Cognito is not configured");
  }
  const url = new URL(window.location.href);
  const code = url.searchParams.get("code");
  const state = url.searchParams.get("state");
  if (!code) throw new Error("No `code` in callback URL");

  const expectedState = sessionStorage.getItem(KEY_STATE);
  if (!expectedState || state !== expectedState) {
    throw new Error("OAuth state mismatch");
  }
  const verifier = sessionStorage.getItem(KEY_VERIFIER);
  if (!verifier) throw new Error("Missing PKCE verifier");

  const tokens = await exchangeCodeForTokens(code, verifier);
  storeTokens(tokens);
  sessionStorage.removeItem(KEY_VERIFIER);
  sessionStorage.removeItem(KEY_STATE);
  const returnTo = sessionStorage.getItem(KEY_RETURN) ?? "/";
  sessionStorage.removeItem(KEY_RETURN);
  return returnTo;
}

/**
 * Return a valid access token, refreshing silently if it has expired.
 * Returns null when no tokens are present (caller should route to login).
 */
export async function getAccessToken(): Promise<string | null> {
  const t = loadTokens();
  if (!t.accessToken || !t.expiresAt) return null;
  // 30s skew so we don't hand out a token that dies mid-request.
  if (Date.now() < t.expiresAt - 30_000) return t.accessToken;
  if (!t.refreshToken || !isCognitoConfigured()) {
    clearTokens();
    return null;
  }
  try {
    const refreshed = await refreshWithToken(t.refreshToken);
    // Cognito may omit refresh_token on refresh — keep the old one.
    storeTokens({
      ...refreshed,
      refresh_token: refreshed.refresh_token ?? t.refreshToken,
    });
    return refreshed.access_token;
  } catch {
    clearTokens();
    return null;
  }
}

/** Cheap synchronous check for the AuthProvider bootstrap. */
export function hasStoredTokens(): boolean {
  const { accessToken } = loadTokens();
  return Boolean(accessToken);
}
