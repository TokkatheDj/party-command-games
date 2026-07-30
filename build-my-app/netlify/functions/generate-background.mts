import type { Context, Config } from "@netlify/functions";
import { getStore } from "@netlify/blobs";
import { createHash } from "node:crypto";

function buildPrompt(criteria: any, requesterName: string) {
  const mechanics = (criteria.mechanics || []).join(", ");
  const lines = [
    `You are generating exactly ONE self-contained HTML app for "Build My App", a tool that turns a one-line idea into a playable web app.`,
    ``,
    `App type: ${criteria.app_type || "unspecified"}`,
    criteria.theme ? `Theme/subject: ${criteria.theme}` : "",
    `Target age range: ${criteria.age_range || "All ages"}`,
    `Visual color vibe: ${criteria.color_vibe || "Bright & Playful"}`,
    `One-line idea: ${criteria.idea}`,
    mechanics ? `Requested mechanics: ${mechanics}` : "",
    criteria.difficulty ? `Difficulty: ${criteria.difficulty}` : "",
    criteria.tech_requests ? `Specific technical requests: ${criteria.tech_requests}` : "",
    criteria.inspired_by ? `Should feel similar in spirit to: ${criteria.inspired_by}` : "",
    requesterName ? `Requested by: ${requesterName}` : "",
    ``,
    `OUTPUT FORMAT -- this is the single most important rule:`,
    `Respond with ONLY the complete, raw contents of one HTML file. No markdown code fences, no explanation before or after, no commentary. Your entire response must be valid to save directly as a .html file.`,
    ``,
    `MANDATORY HTML APP CONVENTIONS:`,
    `- First line of the file must be: <!-- CONCEPT: one-sentence description -->`,
    `- Must include this exact viewport meta tag verbatim: <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">`,
    `- Single self-contained HTML file: all CSS and JS inline, no external dependencies, no CDN links, no external fonts or images. There is no server and no internet access available to the app -- if the request mentions "online" or networked multiplayer, build local same-device pass-and-play or split-screen multiplayer instead.`,
    `- Always include this universal reset: * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }`,
    `- Always include this on html, body: margin: 0; padding: 0; touch-action: manipulation; user-select: none; -webkit-user-select: none;`,
    `- Use CSS custom properties (:root { --var: value; }) for theme colors.`,
    `- Vanilla JS only, in one <script> tag at the end of <body>.`,
    `- Mobile-first: works at 375px wide with no horizontal scroll, all tap targets >= 44px, no hover-only interactions.`,
    `- If you persist any state, use localStorage with keys namespaced as 'build-my-app-{key}'.`,
    `- Give the app a clear on-screen title and, if it's a game or puzzle, a way to restart/reset.`,
    `- Match the visual vibe requested above using colors, not just a label in a comment.`,
    ``,
    `MAKE IT FEEL FINISHED, NOT JUST FUNCTIONAL:`,
    `- Add short sound effects for key interactions, synthesized live with the Web Audio API -- no external audio files.`,
    `- Animate state changes instead of snapping: CSS transitions/keyframes or a JS easing loop.`,
    `- Give it a title/start screen with a clear call-to-action button, and a real win/complete/game-over state with a way to play again.`,
    `- Any illustration or drawn asset should be shaded/filled and use the full color palette, not a thin outline sketch.`,
    ``,
    `Build the complete, working app in one pass -- do not ask clarifying questions, do not produce placeholder or skeleton code.`,
  ];
  return lines.filter(Boolean).join("\n");
}

function extractHtml(text: string) {
  let html = (text || "").trim();
  html = html.replace(/^```(?:html)?\s*\n?/i, "").replace(/```\s*$/, "").trim();
  return html;
}

function slugify(text: string) {
  return (
    (text || "app")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 40) || "app"
  );
}

async function createSite(token: string, baseName: string) {
  let lastError = "";
  for (let attempt = 0; attempt < 3; attempt++) {
    const name = attempt === 0 ? baseName : `${baseName}-${Math.random().toString(36).slice(2, 6)}`;
    const resp = await fetch("https://api.netlify.com/api/v1/sites", {
      method: "POST",
      headers: {
        authorization: `Bearer ${token}`,
        "content-type": "application/json",
      },
      body: JSON.stringify({ name }),
    });
    if (resp.ok) return await resp.json();
    lastError = await resp.text();
    if (resp.status !== 422) break;
  }
  throw new Error(`Site creation failed: ${lastError.slice(0, 300)}`);
}

async function deployHtmlToSite(token: string, site: any, html: string) {
  const sha1 = createHash("sha1").update(html, "utf8").digest("hex");

  const deployResp = await fetch(`https://api.netlify.com/api/v1/sites/${site.id}/deploys`, {
    method: "POST",
    headers: {
      authorization: `Bearer ${token}`,
      "content-type": "application/json",
    },
    body: JSON.stringify({ files: { "/index.html": sha1 } }),
  });
  if (!deployResp.ok) {
    const errText = await deployResp.text();
    throw new Error(`Deploy creation failed: ${errText.slice(0, 300)}`);
  }
  const deploy = await deployResp.json();

  if (Array.isArray(deploy.required) && deploy.required.includes(sha1)) {
    const uploadResp = await fetch(
      `https://api.netlify.com/api/v1/deploys/${deploy.id}/files/index.html`,
      {
        method: "PUT",
        headers: {
          authorization: `Bearer ${token}`,
          "content-type": "application/octet-stream",
        },
        body: html,
      }
    );
    if (!uploadResp.ok) {
      const errText = await uploadResp.text();
      throw new Error(`File upload failed: ${errText.slice(0, 300)}`);
    }
  }

  let liveUrl = site.ssl_url || site.url || `https://${site.name}.netlify.app`;
  for (let i = 0; i < 10; i++) {
    const statusResp = await fetch(
      `https://api.netlify.com/api/v1/sites/${site.id}/deploys/${deploy.id}`,
      { headers: { authorization: `Bearer ${token}` } }
    );
    if (statusResp.ok) {
      const d = await statusResp.json();
      if (d.state === "ready") {
        liveUrl = d.ssl_url || d.deploy_ssl_url || liveUrl;
        break;
      }
    }
    await new Promise((r) => setTimeout(r, 1000));
  }

  return liveUrl;
}

export default async (req: Request, context: Context) => {
  const store = getStore("build-requests");
  let body: any;
  try {
    body = await req.json();
  } catch {
    return;
  }
  const { id, criteria, requester_name, skip_publish } = body || {};
  if (!id || !criteria || !criteria.idea) return;

  await store.setJSON(id, { status: "pending", startedAt: Date.now() });

  try {
    const apiKey = Netlify.env.get("ANTHROPIC_API_KEY");
    if (!apiKey) {
      await store.setJSON(id, { status: "error", message: "Builder isn't configured with an API key yet." });
      return;
    }

    const prompt = buildPrompt(criteria, requester_name || "");
    const resp = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-api-key": apiKey,
        "anthropic-version": "2023-06-01",
      },
      body: JSON.stringify({
        model: "claude-sonnet-5",
        max_tokens: 16000,
        messages: [{ role: "user", content: prompt }],
      }),
    });

    if (!resp.ok) {
      const errText = await resp.text();
      // detail stays in the function log -- upstream bodies can name the provider/model
      console.error(`builder API error (${resp.status}): ${errText.slice(0, 400)}`);
      await store.setJSON(id, {
        status: "error",
        message: `The builder couldn't be reached (error ${resp.status}). Try again in a bit.`,
      });
      return;
    }

    const data = await resp.json();
    const rawText = (data?.content || [])
      .filter((block: any) => block.type === "text")
      .map((block: any) => block.text || "")
      .join("");
    const html = extractHtml(rawText);

    if (!html || !/<html/i.test(html)) {
      await store.setJSON(id, {
        status: "error",
        message: "The builder didn't return a usable app. Try simplifying your idea and building again.",
      });
      return;
    }

    let liveUrl: string | null = null;
    let publishError: string | null = null;
    try {
      const deployToken = Netlify.env.get("NETLIFY_DEPLOY_TOKEN");
      if (skip_publish) {
        publishError = null;
      } else if (deployToken) {
        const baseName = `${slugify(criteria.idea)}-${Math.random().toString(36).slice(2, 6)}`;
        const site = await createSite(deployToken, baseName);
        liveUrl = await deployHtmlToSite(deployToken, site, html);
      } else {
        publishError = "Publishing isn't configured yet.";
      }
    } catch (err: any) {
      publishError = String(err?.message || err);
    }

    await store.setJSON(id, { status: "done", html, liveUrl, publishError, finishedAt: Date.now() });
  } catch (err: any) {
    // same reason as above -- raw errors can carry the provider host name
    console.error("build failed:", String(err?.stack || err?.message || err));
    await store.setJSON(id, {
      status: "error",
      message: "Something went wrong building your app. Try again in a bit.",
    });
  }
};

export const config: Config = { path: "/api/generate" };
