import React from 'react';

class ErrorBoundary extends React.Component {
    constructor(props) {
        super(props);
        this.state = { hasError: false, error: null, errorInfo: null };
    }

    static getDerivedStateFromError(error) {
        return { hasError: true };
    }

    componentDidCatch(error, errorInfo) {
        console.error("Uncaught error:", error, errorInfo);
        this.setState({ error, errorInfo });
    }

    render() {
        if (this.state.hasError) {
            return (
                <div className="min-h-screen flex items-center justify-center bg-[var(--bg-color)] text-[var(--text-color)] p-10 flex-col text-center">
                    <h1 className="text-4xl font-bold text-[#ff3b30] mb-4">Something went wrong.</h1>
                    <p className="text-xl text-[var(--text-muted)] mb-8">The application encountered an unexpected error.</p>
                    <div className="bg-[var(--card-bg)] p-4 rounded-xl border border-[var(--border-color)] text-left max-w-2xl overflow-auto mb-6">
                        <p className="font-mono text-sm text-[var(--apple-red)]">{this.state.error && this.state.error.toString()}</p>
                        <pre className="font-mono text-xs text-[var(--text-muted)] mt-2">
                            {this.state.errorInfo && this.state.errorInfo.componentStack}
                        </pre>
                    </div>
                    <button
                        onClick={() => window.location.reload()}
                        className="px-6 py-3 bg-[var(--text-color)] text-[var(--bg-color)] font-bold rounded-xl hover:opacity-80"
                    >
                        Reload Application
                    </button>
                </div>
            );
        }

        return this.props.children;
    }
}

export default ErrorBoundary;
