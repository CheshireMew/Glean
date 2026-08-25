import React from 'react';
import PropTypes from 'prop-types';


export class RouteErrorBoundary extends React.Component {
    constructor(props) {
        super(props);
        this.state = { error: null };
    }

    static getDerivedStateFromError(error) {
        return { error };
    }

    componentDidCatch(error, info) {
        console.error('Route rendering failed:', error, info);
    }

    render() {
        if (!this.state.error) return this.props.children;
        return (
            <main role="alert" className="min-h-screen flex items-center justify-center bg-gray-50 px-6 text-center">
                <div className="max-w-lg rounded-2xl bg-white p-10 shadow-sm">
                    <div className="mb-4 text-4xl" aria-hidden="true">!</div>
                    <h1 className="mb-3 text-xl font-semibold text-gray-900">页面资源加载失败</h1>
                    <p className="mb-6 text-sm leading-6 text-gray-600">
                        应用可能刚刚更新，或当前网络未能加载页面资源。刷新后会重新获取完整版本。
                    </p>
                    <button
                        type="button"
                        className="rounded-lg bg-blue-600 px-5 py-2 text-sm font-medium text-white hover:bg-blue-700"
                        onClick={() => window.location.reload()}
                    >
                        刷新页面
                    </button>
                </div>
            </main>
        );
    }
}

RouteErrorBoundary.propTypes = {
    children: PropTypes.node.isRequired,
};
