import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router";
import "./index.css";
import Home from "./routes/Home";
import Response from "./routes/Response";
import CrisisSupport from "./routes/CrisisSupport";
import ThinkingTrap from "./routes/ThinkingTrap";
import Breathing from "./routes/Breathing";
import Settings from "./routes/Settings";
import LookingBack from "./routes/LookingBack";

// basename="/app" keeps every in-app route under /app/... — Welcome
// (index.html, at the domain root) is a separate static page outside this
// router entirely. See frontend/README.md.
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter basename="/app">
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/response" element={<Response />} />
        <Route path="/crisis" element={<CrisisSupport />} />
        <Route path="/thinking-trap" element={<ThinkingTrap />} />
        <Route path="/breathe" element={<Breathing />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/looking-back" element={<LookingBack />} />
      </Routes>
    </BrowserRouter>
  </StrictMode>,
);
