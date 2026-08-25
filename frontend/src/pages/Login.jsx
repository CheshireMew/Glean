import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useLoginForm } from '../hooks/useLoginForm';

const Login = () => {
    const navigate = useNavigate();
    const { loading, error, submit } = useLoginForm(navigate);

    const handleSubmit = (event) => {
        event.preventDefault();
        const form = new FormData(event.currentTarget);
        void submit({
            username: String(form.get('username') || ''),
            password: String(form.get('password') || ''),
        });
    };

    return (
        <div className="flex min-h-screen items-center justify-center bg-slate-100 px-4 text-slate-900">
            <main className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-7 shadow-xl shadow-slate-200/60">
                <div className="mb-6">
                    <p className="text-xs font-semibold uppercase tracking-[0.2em] text-blue-600">AINews</p>
                    <h1 className="mt-2 text-2xl font-bold">管理员登录</h1>
                    <p className="mt-1 text-sm text-slate-500">使用服务器配置的管理员账号进入后台。</p>
                </div>
                <form onSubmit={handleSubmit} className="space-y-4">
                    <label className="block text-sm font-medium text-slate-700">
                        用户名
                        <input
                            name="username"
                            autoComplete="username"
                            required
                            aria-label="用户名"
                            placeholder="管理员用户名"
                            className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2.5 outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
                        />
                    </label>
                    <label className="block text-sm font-medium text-slate-700">
                        密码
                        <input
                            name="password"
                            type="password"
                            autoComplete="current-password"
                            required
                            aria-label="密码"
                            placeholder="管理员密码"
                            className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2.5 outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
                        />
                    </label>
                    {error && (
                        <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
                            {error}
                        </p>
                    )}
                    <button
                        type="submit"
                        disabled={loading}
                        className="w-full rounded-lg bg-blue-600 px-4 py-2.5 font-semibold text-white transition hover:bg-blue-700 disabled:cursor-wait disabled:opacity-60"
                    >
                        {loading ? '正在登录…' : '登录'}
                    </button>
                </form>
            </main>
        </div>
    );
};

export default Login;
