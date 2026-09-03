/**
 * Tiny runtime-config layer in front of the static dashboard.
 *
 * CARTO requires the browser to request basemap tiles directly, so this Worker
 * does not proxy or cache map tiles. It only keeps the key out of the Git
 * repository and supplies it to the browser at request time. Like every key
 * used by a browser application, it remains visible in browser developer tools.
 */
export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === "/carto-config.js") {
      if (request.method !== "GET" && request.method !== "HEAD") {
        return new Response("Method Not Allowed", {
          status: 405,
          headers: { Allow: "GET, HEAD" },
        });
      }

      // An empty value lets the first deployment convert the existing
      // assets-only project into a scripted Worker. The secret can then be
      // attached in Cloudflare without ever putting it in this repository.
      const cartoBasemapKey = typeof env.CARTO_BASEMAP_KEY === "string"
        ? env.CARTO_BASEMAP_KEY
        : "";
      const body = request.method === "HEAD"
        ? null
        : `globalThis.DINO_CONFIG = Object.freeze({ cartoBasemapKey: ${JSON.stringify(cartoBasemapKey)} });\n`;

      return new Response(body, {
        headers: {
          "Cache-Control": "private, no-store",
          "Content-Type": "application/javascript; charset=utf-8",
          "X-Content-Type-Options": "nosniff",
        },
      });
    }

    return env.ASSETS.fetch(request);
  },
};
