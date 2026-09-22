import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

export default function Layout() {
  const { user, logout, can } = useAuth();

  return (
    <div className="shell">
      <aside className="rail">
        <div className="rail-brand">
          <span className="rail-mark" aria-hidden="true" />
          Tender Registry
        </div>

        <nav className="rail-nav">
          {/* Links are hidden for capabilities the account lacks. The backend
              enforces the same rules, so this is convenience, not security. */}
          {can("search_tenders") && <NavLink to="/search">New search</NavLink>}
          {can("save_lists") && <NavLink to="/searches">Saved lists</NavLink>}
          <NavLink to="/review">Review</NavLink>
          <NavLink to="/tenders">Saved tenders</NavLink>
          <NavLink to="/sites">Sites</NavLink>
          <NavLink to="/categories">Categories</NavLink>
          <NavLink to="/scheduling">Scheduling</NavLink>
          {can("manage_users") && <NavLink to="/users">Users</NavLink>}
          {can("run_admin_tasks") && (
            <NavLink to="/maintenance">Maintenance</NavLink>
          )}
        </nav>

        <div className="rail-foot">
          <NavLink to="/account" className="rail-user">
            <strong>{user?.full_name}</strong>
            <span className="mono">{user?.username}</span>
            <span className="tag tag-caps">
              {user?.capabilities?.length ?? 0} permission
              {user?.capabilities?.length === 1 ? "" : "s"}
            </span>
          </NavLink>
          <button className="btn btn-quiet btn-block" onClick={logout}>
            Sign out
          </button>
        </div>
      </aside>

      <main className="stage">
        <Outlet />
      </main>
    </div>
  );
}
