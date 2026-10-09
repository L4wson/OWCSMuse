import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { Analytics } from "@vercel/analytics/react";
import { SpeedInsights } from "@vercel/speed-insights/react";

import App from "./App.jsx";
import "./styles.css";

// Vercel Web Analytics and Speed Insights: each loads its script from the deployment's own /_vercel path, so they
// report only from a Vercel deployment with the feature enabled; locally and in tests they send nothing.
createRoot(document.getElementById("root")).render(
  <StrictMode>
    <App />
    <Analytics />
    <SpeedInsights />
  </StrictMode>,
);
