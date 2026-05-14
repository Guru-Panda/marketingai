import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import "./styles.css";
import AuthLogin from "./pages/AuthLogin";
import AuthSignup from "./pages/AuthSignup";
import BusinessForm from "./pages/BusinessForm";
import LeadsDashboard from "./pages/LeadsDashboard";
import SuggestedChannels from "./pages/SuggestedChannels";
import Profile from "./pages/Profile";
import RequireAuth from "./components/RequireAuth";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigate to="/auth/login" replace />} />
        <Route path="/dashboard" element={<Navigate to="/dashboard/leads" replace />} />
        <Route path="/auth/login" element={<AuthLogin />} />
        <Route path="/auth/signup" element={<AuthSignup />} />
        <Route element={<RequireAuth />}>
          <Route path="/dashboard/business" element={<BusinessForm />} />
          <Route path="/dashboard/channels" element={<SuggestedChannels />} />
          <Route path="/dashboard/leads" element={<LeadsDashboard />} />
          <Route path="/dashboard/profile" element={<Profile />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </React.StrictMode>
);
