import { Navigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

export default function ProtectedRoute({ children, requiredRole }) {
  const { user, loading } = useAuth();

  if (loading) return <div className="loading">Loading...</div>;
  if (!user) return <Navigate to="/login" />;

  if (requiredRole) {
    const roles = { viewer: 1, operator: 2, admin: 3 };
    if ((roles[user.role] || 0) < (roles[requiredRole] || 0)) {
      return <div className="empty">권한이 없습니다 (필요: {requiredRole})</div>;
    }
  }

  return children;
}
