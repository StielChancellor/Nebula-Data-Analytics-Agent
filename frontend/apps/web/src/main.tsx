/**
 * Entry point. The contract (PRD § Critical files):
 *   1. applyBrand() runs BEFORE React mounts so CSS vars + title + favicon
 *      are correct on first paint.
 *   2. Only then do we ReactDOM.createRoot(...).render(...).
 */
import React from "react";
import ReactDOM from "react-dom/client";
import { applyBrand } from "@insnav/brand-runtime";
import { App } from "./App";
import "./index.css";

async function bootstrap() {
  const brand = await applyBrand();
  const root = ReactDOM.createRoot(document.getElementById("root")!);
  root.render(
    <React.StrictMode>
      <App brand={brand} />
    </React.StrictMode>,
  );
}

void bootstrap();
