// Two routes - the landing page and /q/<slug> - so a router dependency would be
// more code to configure than to write. History state is the source of truth;
// back and forward work because popstate is the only other way in.

import { useCallback, useEffect, useState } from "react";

const SLUG = /^\/q\/([A-Za-z0-9_-]{4,64})\/?$/;
// OWCS Grid (docs/grid/BETA.md): /grid is today's puzzle, /grid/<n> an earlier one, /grid/archive the list.
const GRID = /^\/grid(?:\/(archive|[1-9][0-9]{0,5}))?\/?$/;

export function pathToRoute(path) {
  const grid = GRID.exec(path || "/");
  if (grid) {
    if (grid[1] === "archive") return { name: "grid", view: "archive" };
    return grid[1] ? { name: "grid", view: "puzzle", number: Number(grid[1]) } : { name: "grid", view: "today" };
  }
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
