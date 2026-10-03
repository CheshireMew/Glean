import React, { lazy, Suspense } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { PublicLayout } from './layouts/PublicLayout';
import { useAuthSession } from './auth/useAuthSession';
import { RouteErrorBoundary } from './components/RouteErrorBoundary';

const Dashboard = lazy(() => import('./pages/Dashboard'));
const NewsFeed = lazy(() => import('./pages/NewsFeed'));
const Login = lazy(() => import('./pages/Login'));
const EventDetail = lazy(() => import('./pages/EventDetail'));
const TopicDetail = lazy(() => import('./pages/TopicDetail'));

// 路由守卫：保护后台路由
const ProtectedRoute = ({ children }) => {
  const { authenticated, loading, error, retry } = useAuthSession();
  const location = useLocation();
  if (loading) return <div role="status" className="p-8 text-center">正在验证登录状态…</div>;
  if (error) return <div role="alert" className="p-8 text-center">无法验证登录状态：{error} <button onClick={retry}>重试</button></div>;
  if (!authenticated) {
    return <Navigate to="/login" state={{ returnTo: location.pathname + location.search }} replace />;
  }
  return children;
};

const App = () => {
  return (
    <Router>
      <RouteErrorBoundary>
        <Suspense fallback={<div role="status" className="min-h-screen flex items-center justify-center text-gray-500">正在加载页面…</div>}>
          <Routes>
          {/* 公开路由 - 前台展示 */}
          <Route path="/" element={<PublicLayout />}>
            <Route index element={<NewsFeed />} />
            <Route path="ai" element={<Navigate to="/?channel=ai" replace />} />
            <Route path="events/:eventId" element={<EventDetail />} />
            <Route path="entities/:slug" element={<TopicDetail type="entity" />} />
            <Route path="narratives/:slug" element={<TopicDetail type="narrative" />} />
          </Route>

          {/* 登录页面 */}
          <Route path="/login" element={<Login />} />

          {/* 后台管理路由 - 需要认证 */}
          <Route
            path="/admin"
            element={
              <ProtectedRoute>
                <Dashboard />
              </ProtectedRoute>
            }
          />

          {/* 默认重定向 */}
          <Route path="/dashboard" element={<Navigate to="/admin" replace />} />
          <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
      </RouteErrorBoundary>
    </Router>
  );
};

export default App;
