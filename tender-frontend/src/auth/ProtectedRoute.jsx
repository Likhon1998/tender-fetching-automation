import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "./AuthContext";

/** Gate for signed-in-only pages. Sends people to sign in and remembers where
 *  they were headed so they land there afterwards. */
export default function ProtectedRoute({ children }) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) return <div className="boot">Checking your session…</div>;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;

  return children;
}
