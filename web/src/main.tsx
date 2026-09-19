import "@fontsource-variable/inter";
// Fraunces (weights 500 + 600) is reserved for the executive banner
// headline and page H1 only — see the v2.1 addendum typography rule.
import "@fontsource/fraunces/500.css";
import "@fontsource/fraunces/600.css";
import "./index.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { AuthProvider } from "./auth/AuthProvider";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AuthProvider>
      <App />
    </AuthProvider>
  </StrictMode>,
);
