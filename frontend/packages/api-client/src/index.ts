/**
 * @insnav/api-client
 *
 * Generated REST client from /v1/openapi.json + SSE wrapper for streaming
 * agent responses.
 *
 * TODO Phase 1.5: wire `tools/openapi-codegen` to pull /v1/openapi.json on
 * prebuild and emit typed methods here. Until then, this module exposes a
 * minimal hand-written fetch wrapper sufficient for /v1/me/brand and
 * /v1/me/datasets.
 */

const DEFAULT_BASE = "/api";

export interface ApiClientOptions {
  baseUrl?: string;
  getToken?: () => string | null | Promise<string | null>;
}

export class ApiClient {
  private baseUrl: string;
  private getToken: () => string | null | Promise<string | null>;

  constructor(opts: ApiClientOptions = {}) {
    this.baseUrl = opts.baseUrl ?? DEFAULT_BASE;
    this.getToken = opts.getToken ?? (() => null);
  }

  async get<T>(path: string): Promise<T> {
    const token = await this.getToken();
    const res = await fetch(`${this.baseUrl}${path}`, {
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      credentials: "include",
    });
    if (!res.ok) throw new Error(`GET ${path} -> ${res.status}`);
    return (await res.json()) as T;
  }
}
