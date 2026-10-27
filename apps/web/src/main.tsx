import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import App from "./App";
import "./styles.css";


const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // The workbench asks the API again while the run is still moving.
      // A failed ask is worth one more try, and no more: a run that is
      // not there stays not there.
      retry: 1,
    },
  },
});


createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
