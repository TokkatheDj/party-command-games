import type { Context, Config } from "@netlify/functions";
import { getStore } from "@netlify/blobs";

export default async (req: Request, context: Context) => {
  const url = new URL(req.url);
  const id = url.searchParams.get("id");
  if (!id) {
    return new Response(JSON.stringify({ status: "error", message: "Missing id" }), {
      status: 400,
      headers: { "content-type": "application/json" },
    });
  }

  const store = getStore("build-requests");
  const record = await store.get(id, { type: "json" });

  if (!record) {
    return new Response(JSON.stringify({ status: "pending" }), {
      headers: { "content-type": "application/json" },
    });
  }

  return new Response(JSON.stringify(record), {
    headers: { "content-type": "application/json" },
  });
};

export const config: Config = { path: "/api/status" };
