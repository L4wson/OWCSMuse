// Two routes - the landing page and /q/<slug> - so a router dependency would be
// more code to configure than to write. History state is the source of truth;
// back and forward work because popstate is the only other way in.

import { useCallback, useEffect, useState } from "react";

const SLUG = /^\/q\/([A-Za-z0-9_-]{4,64})\/?$/;

export function pathToRoute(path) {
  const match = SLUG.exec(path || "/");
  return match ? { name: "query", slug: match[1] } : { name: "home" };
}

export function routeToPath(route) {
  return route?.name === "query" && route.slug ? `/q/${route.slug}` : "/";
}

export function useRoute() {
  const [route, setRoute] = useState(() => pathToRoute(window.location.pathname));

  useEffect(() => {
    const onPop = () => setRoute(pathToRoute(window.location.pathname));
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const navigate = useCallback((path, { replace = false } = {}) => {
    if (path !== window.location.pathname) {
      window.history[replace ? "replaceState" : "pushState"]({}, "", path);
    }
    setRoute(pathToRoute(path));
  }, []);

  return [route, navigate];
}
