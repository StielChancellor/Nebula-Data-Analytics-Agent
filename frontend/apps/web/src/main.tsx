/**
 * Entry point. The contract (PRD § Critical files):
 *   1. applyBrand() runs BEFORE React mounts so CSS vars + title + favicon
 *      are correct on first paint.
 *   2. Only then do we ReactDOM.createRoot(...).render(...).
 *   3. AuthProvider wraps <App/> so any descendant can call useAuth().
 */
import React from "react";
import ReactDOM from "react-dom/client";
import { applyBrand } from "@insnav/brand-runtime";
import { AuthProvider } from "@insnav/auth";
import { App } from "./App";
import "./index.css";

const API_BASE = import.meta.env.VITE_API_BASE || "/api";

async function bootstrap() {
  const brand = await applyBrand();
  const root = ReactDOM.createRoot(document.getElementById("root")!);
  root.render(
    <React.StrictMode>
      <AuthProvider apiBase={API_BASE}>
        <App brand={brand} />
      </AuthProvider>
    </React.StrictMode>,
  );
}

void bootstrap();
