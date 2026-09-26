import { Navigate, Route, Routes } from "react-router";
import { AuthGuard } from "@/components/auth/AuthGuard";
import { GeneratedRoutes } from "@/generated/routes";
import HomePage from "@/pages/HomePage";
import LoginPage from "@/pages/LoginPage";
import NotFoundPage from "@/pages/NotFoundPage";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<AuthGuard />}>
        <Route path="/" element={<HomePage />} />
        <Route path="/home" element={<Navigate to="/" replace />} />
        {GeneratedRoutes}
      </Route>
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
