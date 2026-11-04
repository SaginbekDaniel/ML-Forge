import { afterEach, describe, expect, it, vi } from "vitest";

import { api, ApiError } from "./api";

afterEach(() => vi.unstubAllGlobals());

describe("api client", () => {
  it("surfaces the server error envelope", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({
      error_code: "skill_locked", message: "locked", request_id: "abc", details: { skill_id: "x" },
    }), { status: 409 })));
    const err = await api("/x").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 409, code: "skill_locked", requestId: "abc", details: { skill_id: "x" } });
  });

  it("maps proxy failures and network errors to explicit codes", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("Internal Server Error", { status: 500 })));
    await expect(api("/x")).rejects.toMatchObject({ code: "api_unreachable" });
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("failed"); }));
    await expect(api("/x")).rejects.toMatchObject({ code: "network_error", status: 0 });
  });

  it("sends JSON bodies and prefixes /api/v1", async () => {
    const f = vi.fn(async () => new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", f);
    await api("/profile", { method: "POST", json: { a: 1 } });
    const [url, init] = f.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/v1/profile");
    expect(init.body).toBe('{"a":1}');
    expect((init.headers as Record<string, string>)["content-type"]).toBe("application/json");
  });
});
