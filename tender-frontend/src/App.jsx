import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import ProtectedRoute from "./auth/ProtectedRoute";
import Categories from "./pages/Categories";
import Login from "./pages/Login";
import Maintenance from "./pages/Maintenance";
import Profile from "./pages/Profile";
import Review from "./pages/Review";
import SearchHistory from "./pages/SearchHistory";
import SearchResults from "./pages/SearchResults";
import SearchWizard from "./pages/SearchWizard";
import Scheduling from "./pages/Scheduling";
import Sites from "./pages/Sites";
import Tenders from "./pages/Tenders";
import Users from "./pages/Users";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />

      <Route
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route path="/search" element={<SearchWizard />} />
        <Route path="/searches" element={<SearchHistory />} />
        <Route path="/searches/:id" element={<SearchResults />} />
        <Route path="/review" element={<Review />} />
        <Route path="/tenders" element={<Tenders />} />
        <Route path="/sites" element={<Sites />} />
        <Route path="/scheduling" element={<Scheduling />} />
        <Route path="/categories" element={<Categories />} />
        <Route path="/users" element={<Users />} />
        <Route path="/maintenance" element={<Maintenance />} />
        <Route path="/account" element={<Profile />} />
      </Route>

      <Route path="*" element={<Navigate to="/search" replace />} />
    </Routes>
  );
}
