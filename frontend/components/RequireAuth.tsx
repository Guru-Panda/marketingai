import { Navigate, Outlet } from "react-router-dom";
import { auth } from "../api/client";

export default function RequireAuth() {
  if (!auth.isLoggedIn()) {
    return <Navigate to="/auth/login" replace />;
  }
  return <Outlet />;
}
