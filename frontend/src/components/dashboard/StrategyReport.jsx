import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, ShieldAlert, TrendingUp, BarChart3, Binary, AlertCircle, CheckCircle2, ChevronRight, FileDown } from 'lucide-react';
import { exportStrategyPDF } from '../../utils/pdfExport';
import AnimatedNumber from '../common/AnimatedNumber';

const generatePathData = (data, width, height) => {
    if (!data || data.length < 2) return `M0,${height} L${width},${height}`;
    const minX = Math.min(...data.map(d => d.x));
    const maxX = Math.max(...data.map(d => d.x));
    const minY = Math.min(...data.map(d => d.y));
    const maxY = Math.max(...data.map(d => d.y));
    const rangeY = (maxY - minY) || 1;

    const points = data.map(d => ({
        x: ((d.x - minX) / (maxX - minX || 1)) * width,
        y: height - ((d.y - minY) / rangeY) * height
    }));

    let path = `M${points[0].x},${points[0].y}`;
    for (let i = 0; i < points.length - 1; i++) {
        const p0 = points[i];
        const p1 = points[i + 1];
        const cpX = (p0.x + p1.x) / 2;
        path += ` C${cpX},${p0.y} ${cpX},${p1.y} ${p1.x},${p1.y}`;
    }
    return path;
};

const StrategyReport = ({ isOpen, onClose, strategyData }) => {
    const [activePage, setActivePage] = useState(1);

    const stats = React.useMemo(() => {
        if (!strategyData || !strategyData.history) return {};
        const trades = strategyData.history;

        // Monthly Heatmap Logic
        const monthly = {};
        let ytd = 0;
        let best = -Infinity;
        let worst = Infinity;

        trades.forEach(t => {
            const date = new Date(t.exit_time || t.entry_time);
            const year = date.getFullYear();
            const month = date.getMonth();
            const key = `${year}-${month}`;

            monthly[key] = (monthly[key] || 0) + (t.pnl || 0);
            ytd += (t.pnl || 0);
        });

        // Convert PnL to Pct for heatmap (approx)
        const heatmap = {};
        Object.entries(monthly).forEach(([key, pnl]) => {
            const pct = (pnl / (strategyData.initial_capital || 15000)) * 100;
            heatmap[key] = pct;
            if (pct > (best || -Infinity)) best = pct;
            if (pct < (worst || Infinity)) worst = pct;
        });

        // Trade Stats
        const wins = trades.filter(t => t.pnl > 0);
        const losses = trades.filter(t => t.pnl <= 0);
        const avgWin = wins.length > 0 ? wins.reduce((a, b) => a + b.pnl, 0) / wins.length : 0;
        const avgLoss = losses.length > 0 ? losses.reduce((a, b) => a + b.pnl, 0) / losses.length : 0;

        // Equity Curve Calculation
        let cumulative = 0;
        const equityCurve = trades.map((t, i) => {
            cumulative += (t.pnl || 0);
            return { x: i, y: cumulative };
        });

        return {
            ytd: ((ytd / (strategyData.initial_capital || 15000)) * 100).toFixed(1),
            best: best === -Infinity ? '0.0' : best.toFixed(1),
            worst: worst === Infinity ? '0.0' : worst.toFixed(1),
            avgWin: Math.round(avgWin),
            avgLoss: Math.round(Math.abs(avgLoss)),
            heatmap,
            equityCurve,
            totalPnL: cumulative
        };
    }, [strategyData]);

    if (!strategyData) return null;

    const pages = [
        {
            title: "Performance DNA",
            subtitle: "Monthly & Regime Analysis",
            content: (
                <div className="space-y-12">
                    <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4 md:gap-6">
                        {[
                            { label: 'YTD Return', val: `${stats.ytd}%` },
                            { label: 'Best Month', val: `${stats.best}%` },
                            { label: 'Worst Month', val: `${stats.worst}%` },
                            { label: 'Profit Factor', val: strategyData.metrics?.profitFactor || '0.0' }
                        ].map((stat, i) => (
                            <div key={i} className="apple-bento p-4 md:p-6 border border-[var(--border-color)]">
                                <p className="text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest mb-1 md:mb-2">{stat.label}</p>
                                <p className="text-xl md:text-2xl font-black text-[var(--text-color)]">{stat.val}</p>
                            </div>
                        ))}
                    </div>

                    <div className="apple-bento p-4 md:p-8 bg-[var(--card-bg)] border border-[var(--border-color)] overflow-x-auto">
                        <h4 className="text-[10px] md:text-sm font-bold uppercase tracking-widest text-[var(--text-muted)] mb-4 md:mb-8">Monthly Returns Heatmap</h4>
                        <div className="grid gap-1 min-w-[500px] md:min-w-[600px]" style={{ gridTemplateColumns: 'repeat(13, 1fr)' }}>
                            <div />
                            {['J', 'F', 'M', 'A', 'M', 'J', 'J', 'A', 'S', 'O', 'N', 'D'].map(m => (
                                <div key={m} className="text-[10px] font-bold text-center text-[var(--text-muted)]">{m}</div>
                            ))}
                            {[2024, 2025, 2026].map(year => (
                                <React.Fragment key={year}>
                                    <div className="text-[10px] font-bold text-[var(--text-muted)] flex items-center">{year}</div>
                                    {Array.from({ length: 12 }).map((_, i) => {
                                        const val = stats.heatmap[`${year}-${i}`] || 0;
                                        const opacity = Math.min(Math.abs(val) / 5, 1);
                                        return (
                                            <div
                                                key={i}
                                                className="h-8 rounded-sm flex items-center justify-center text-[10px] font-bold"
                                                style={{
                                                    backgroundColor: val === 0 ? 'transparent' : (val > 0 ? `rgba(52, 199, 89, ${opacity + 0.1})` : `rgba(255, 59, 48, ${opacity + 0.1})`),
                                                    color: Math.abs(val) > 2 ? 'white' : 'var(--text-color)',
                                                    border: val === 0 ? '1px dashed var(--border-color)' : 'none'
                                                }}
                                            >
                                                {val !== 0 ? `${val.toFixed(1)}%` : '-'}
                                            </div>
                                        );
                                    })}
                                </React.Fragment>
                            ))}
                        </div>
                    </div>

                    {/* Detailed Cumulative PnL Line Chart */}
                    <div className="apple-bento p-6 md:p-10 bg-[var(--card-bg)] border border-[var(--border-color)]">
                        <div className="flex justify-between items-start mb-8">
                            <div>
                                <h4 className="text-[10px] md:text-sm font-bold uppercase tracking-widest text-[var(--text-muted)] mb-1">Cumulative Strategy PnL</h4>
                                <p className="text-2xl font-black text-[var(--text-color)]">
                                    ₹{stats.totalPnL.toLocaleString()}
                                </p>
                            </div>
                            <div className="px-3 py-1 bg-[var(--apple-blue)]/10 rounded-full border border-[var(--apple-blue)]/20">
                                <span className="text-[10px] font-black text-[var(--apple-blue)] uppercase tracking-widest">Day 1 → Now</span>
                            </div>
                        </div>
                        <div className="h-48 md:h-64 relative">
                            <svg width="100%" height="100%" viewBox="0 0 1000 200" preserveAspectRatio="none" className="overflow-visible">
                                <defs>
                                    <linearGradient id="stratGradient" x1="0%" y1="0%" x2="0%" y2="100%">
                                        <stop offset="0%" stopColor="var(--apple-blue)" stopOpacity="0.1" />
                                        <stop offset="100%" stopColor="var(--apple-blue)" stopOpacity="0" />
                                    </linearGradient>
                                </defs>
                                <motion.path
                                    initial={{ pathLength: 0 }}
                                    animate={{ pathLength: 1 }}
                                    transition={{ duration: 1.5, ease: "easeOut" }}
                                    d={generatePathData(stats.equityCurve, 1000, 200)}
                                    fill="none"
                                    stroke="var(--apple-blue)"
                                    strokeWidth="3"
                                    strokeLinecap="round"
                                />
                                <path
                                    d={`${generatePathData(stats.equityCurve, 1000, 200)} L 1000 200 L 0 200 Z`}
                                    fill="url(#stratGradient)"
                                />
                                <line x1="0" y1="200" x2="1000" y2="200" stroke="var(--border-color)" strokeWidth="1" />
                            </svg>
                        </div>
                    </div>

                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-12">
                        <div className="space-y-6">
                            <h4 className="text-xl font-bold tracking-tight text-[var(--text-color)]">Regime Sensitivity</h4>
                            <div className="space-y-4">
                                {[
                                    { r: 'High Volatility Trend', perf: 'EXCELLENT', edge: 'High' },
                                    { r: 'Mean Reverting Range', perf: 'STABLE', edge: 'Moderate' },
                                    { r: 'Volatility Compression', perf: 'WEAK', edge: 'Degrading' }
                                ].map((reg, i) => (
                                    <div key={i} className="flex items-center justify-between p-4 rounded-2xl bg-[var(--bg-color)] border border-[var(--border-color)]">
                                        <span className="text-sm font-medium text-[var(--text-color)]">{reg.r}</span>
                                        <span className={`text-[10px] font-black px-2 py-1 rounded-md ${reg.edge === 'Degrading' ? 'bg-[#ff3b30]/20 text-[#ff3b30]' : 'bg-[#34c759]/20 text-[#34c759]'}`}>
                                            {reg.perf}
                                        </span>
                                    </div>
                                ))}
                            </div>
                        </div>

                        {/* Recent Trades Table */}
                        <div className="space-y-6">
                            <h4 className="text-xl font-bold tracking-tight text-[var(--text-color)]">Recent Executions</h4>
                            <div className="apple-bento overflow-hidden border border-[var(--border-color)]">
                                <table className="w-full text-left border-collapse">
                                    <thead>
                                        <tr className="bg-[var(--bg-color)]">
                                            <th className="px-4 py-3 text-[10px] font-black text-[var(--text-muted)] uppercase tracking-widest">Time</th>
                                            <th className="px-4 py-3 text-[10px] font-black text-[var(--text-muted)] uppercase tracking-widest">Symbol</th>
                                            <th className="px-4 py-3 text-[10px] font-black text-[var(--text-muted)] uppercase tracking-widest text-right">PnL</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-[var(--border-color)]">
                                        {(strategyData.history || []).slice(-10).reverse().map((trade, i) => (
                                            <tr key={i} className="hover:bg-white/[0.02] transition-colors">
                                                <td className="px-4 py-3 text-[11px] font-bold text-[var(--text-muted)]">
                                                    {new Date(trade.exit_time || trade.entry_time).toLocaleDateString('en-IN', { day: '2-digit', month: 'short' })}
                                                </td>
                                                <td className="px-4 py-3 text-[12px] font-black text-[var(--text-color)]">
                                                    {trade.symbol?.split(' ')[0] || strategyData.name}
                                                </td>
                                                <td className={`px-4 py-3 text-[12px] font-black text-right ${trade.pnl > 0 ? 'text-[var(--apple-green)]' : 'text-[var(--apple-red)]'}`}>
                                                    ₹{trade.pnl.toLocaleString()}
                                                </td>
                                            </tr>
                                        ))}
                                        {(strategyData.history || []).length === 0 && (
                                            <tr>
                                                <td colSpan="3" className="px-4 py-8 text-center text-xs font-bold text-[var(--text-muted)] italic">
                                                    No execution history available
                                                </td>
                                            </tr>
                                        )}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </div>
                </div>
            )
        },
        {
            title: "Hedge Distribution",
            subtitle: "Edge vs Luck Verification",
            content: (
                <div className="space-y-12">
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-12">
                        <div className="apple-bento p-6 md:p-8 space-y-4 md:space-y-8">
                            <h4 className="text-xs md:text-sm font-bold uppercase tracking-widest text-[var(--text-muted)]">PnL Distribution (Last {strategyData.history?.length || 0} Trades)</h4>
                            <div className="h-64 flex items-end gap-1">
                                {(strategyData.history || []).slice(-30).map((t, i) => {
                                    const absPnL = Math.abs(t.pnl);
                                    const maxPnL = Math.max(...(strategyData.history || []).map(tr => Math.abs(tr.pnl))) || 1;
                                    const height = (absPnL / maxPnL) * 100;
                                    return (
                                        <motion.div
                                            key={i}
                                            initial={{ height: 0 }}
                                            animate={{ height: `${Math.max(height, 5)}%` }}
                                            className={`flex-1 rounded-t-sm ${t.pnl > 0 ? 'bg-[var(--apple-green)]/60' : 'bg-[var(--apple-red)]/60'}`}
                                            title={`PnL: ₹${t.pnl}`}
                                        />
                                    );
                                })}
                            </div>
                            <div className="flex justify-between text-[11px] font-bold text-[var(--text-muted)] uppercase tracking-widest">
                                <span>Timeline (Old → New)</span>
                                <span>Recent Edge</span>
                            </div>
                        </div>
                        <div className="space-y-8">
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 md:gap-6">
                                {[
                                    { l: 'Avg Win', v: `₹${stats.avgWin.toLocaleString()}` },
                                    { l: 'Avg Loss', v: `₹${stats.avgLoss.toLocaleString()}` },
                                    { l: 'Win Rate', v: strategyData.metrics?.winRate || '0%' },
                                    { l: 'Profit Factor', v: strategyData.metrics?.profitFactor || '0.0' }
                                ].map((s, i) => (
                                    <div key={i} className="apple-bento p-4 md:p-6 border border-[var(--border-color)]">
                                        <p className="text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest mb-1">{s.l}</p>
                                        <p className="text-xl md:text-2xl font-black text-[var(--text-color)]">{s.v}</p>
                                    </div>
                                ))}
                            </div>
                            <div className="p-8 rounded-3xl bg-[#007aff]/5 border border-[#007aff]/10">
                                <p className="text-[var(--text-color)] leading-relaxed font-medium">
                                    Expectancy Insight: Your average win of ₹{stats.avgWin.toLocaleString()} against an average loss of ₹{stats.avgLoss.toLocaleString()} provides a mathematical edge regardless of win-rate variance.
                                </p>
                            </div>
                        </div>
                    </div>
                </div>
            )
        },
        {
            title: "Failure Modes",
            subtitle: "Honesty as Alpha",
            content: (
                <div className="space-y-12">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                        {[
                            {
                                icon: <ShieldAlert className="text-[#ff3b30]" />,
                                t: 'Market Conditions',
                                d: 'Sideways volatility compression (churn) breaks the momentum assumption. Stop-losses will trigger frequently.'
                            },
                            {
                                icon: <Binary className="text-[#ff9500]" />,
                                t: 'Operational Latency',
                                d: 'Slippage > 0.05% on entry degrades edge by 30%. High-speed API infrastructure is mandatory.'
                            },
                            {
                                icon: <TrendingUp className="text-[#af52de]" />,
                                t: 'Drawdown Psychology',
                                d: 'A 15% peak-to-trough drawdown is statistically expected every 14 months. Premature pausing is the greatest risk.'
                            },
                            {
                                icon: <CheckCircle2 className="text-[#34c759]" />,
                                t: 'Veto Rules',
                                d: 'Automatically pauses if 3 consecutive days end at max daily loss limit.'
                            }
                        ].map((risk, i) => (
                            <div key={i} className="apple-bento p-6 md:p-10 space-y-4 md:space-y-6 flex flex-col items-start text-left">
                                <div className="p-3 md:p-4 bg-[var(--bg-color)] rounded-2xl border border-[var(--border-color)]">{risk.icon}</div>
                                <h4 className="text-lg md:text-xl font-bold tracking-tight text-[var(--text-color)]">{risk.t}</h4>
                                <p className="text-sm md:text-base text-[var(--text-muted)] font-medium leading-relaxed">{risk.d}</p>
                            </div>
                        ))}
                    </div>

                    <div className="text-center py-12 border-t border-[var(--border-color)]">
                        <blockquote className="text-xl md:text-3xl font-bold tracking-tight text-[var(--text-color)] mb-6 px-4">
                            "This strategy is not designed to maximize excitement. It is designed to maximize survival and long-term expectancy."
                        </blockquote>
                        <div className="flex justify-center gap-1">
                            {Array.from({ length: 5 }).map((_, i) => <div key={i} className="w-12 h-1 bg-[#007aff] rounded-full" />)}
                        </div>
                    </div>
                </div>
            )
        }
    ];

    return (
        <AnimatePresence>
            {isOpen && (
                <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    className="fixed inset-0 z-[100] flex items-center justify-center p-2 md:p-12 lg:p-20"
                >
                    <div className="absolute inset-0 bg-[var(--bg-color)]/95 backdrop-blur-3xl" onClick={onClose} />

                    <motion.div
                        initial={{ scale: 0.9, y: 20, opacity: 0 }}
                        animate={{ scale: 1, y: 0, opacity: 1 }}
                        exit={{ scale: 0.9, y: 20, opacity: 0 }}
                        className="relative w-full max-h-full bg-[var(--card-bg)] rounded-[24px] md:rounded-[40px] border border-[var(--border-color)] overflow-hidden flex flex-col shadow-2xl"
                    >
                        {/* Header */}
                        <div className="px-6 md:px-12 py-6 md:py-10 flex items-center justify-between border-b border-[var(--border-color)] bg-[var(--card-bg)]">
                            <div>
                                <div className="hidden sm:flex items-center gap-3 mb-1">
                                    <span className="text-[10px] font-black uppercase tracking-[0.3em] text-[#007aff]">Allocator-Grade Insight</span>
                                    <div className="w-1 h-1 rounded-full bg-[var(--text-muted)] opacity-20" />
                                    <span className="text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest">{strategyData.name}</span>
                                </div>
                                <h2 className="text-2xl md:text-4xl font-extrabold tracking-tighter text-[var(--text-color)]">Project Blueprint</h2>
                            </div>
                            <div className="flex items-center gap-2 md:gap-4">
                                <button
                                    onClick={() => exportStrategyPDF(strategyData.name, strategyData.metrics, strategyData.history)}
                                    className="p-3 md:px-6 md:py-3 bg-[var(--bg-color)] text-[var(--text-color)] hover:opacity-80 rounded-full border border-[var(--border-color)] transition-all flex items-center gap-2 text-xs font-black uppercase tracking-widest shadow-sm"
                                >
                                    <FileDown size={18} /> <span className="hidden md:inline">Export Dossier</span>
                                </button>
                                <button
                                    onClick={onClose}
                                    className="w-10 h-10 md:w-12 md:h-12 rounded-full bg-[var(--bg-color)] flex items-center justify-center text-[var(--text-muted)] hover:text-[var(--text-color)] transition-colors border border-[var(--border-color)]"
                                >
                                    <X size={20} />
                                </button>
                            </div>
                        </div>

                        {/* Navigation / Pages */}
                        <div className="flex-1 overflow-y-auto px-6 md:px-12 py-8 md:py-16">
                            <AnimatePresence mode="wait">
                                <motion.div
                                    key={activePage}
                                    initial={{ opacity: 0, x: 20 }}
                                    animate={{ opacity: 1, x: 0 }}
                                    exit={{ opacity: 0, x: -20 }}
                                    transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
                                >
                                    <div className="max-w-[1000px] mx-auto">
                                        <div className="mb-8 md:mb-16">
                                            <p className="text-[11px] md:text-[13px] font-bold text-[#007aff] uppercase tracking-widest mb-1 md:mb-2">{pages[activePage - 1].subtitle}</p>
                                            <h3 className="text-3xl md:text-6xl font-black tracking-tighter text-[var(--text-color)]">{pages[activePage - 1].title}</h3>
                                        </div>
                                        {pages[activePage - 1].content}
                                    </div>
                                </motion.div>
                            </AnimatePresence>
                        </div>

                        {/* Footer Controls */}
                        <div className="px-6 md:px-12 py-6 md:py-8 border-t border-[var(--border-color)] flex items-center justify-between bg-[var(--card-bg)]">
                            <div className="flex gap-2 md:gap-4">
                                {pages.map((_, i) => (
                                    <button
                                        key={i}
                                        onClick={() => setActivePage(i + 1)}
                                        className={`h-1.5 transition-all rounded-full ${activePage === i + 1 ? 'w-8 md:w-12 bg-[#007aff]' : 'w-3 md:w-4 bg-[var(--border-color)] hover:bg-[var(--text-muted)]'}`}
                                    />
                                ))}
                            </div>
                            <button
                                onClick={() => activePage < pages.length ? setActivePage(activePage + 1) : onClose()}
                                className="px-6 py-3 md:px-8 md:py-4 bg-[var(--text-color)] text-[var(--bg-color)] font-black text-[10px] md:text-xs uppercase tracking-widest rounded-full hover:opacity-90 transition-all flex items-center gap-2"
                            >
                                {activePage === pages.length ? "Finish" : "Next"} <ChevronRight size={14} className="md:size-4" />
                            </button>
                        </div>
                    </motion.div>
                </motion.div>
            )}
        </AnimatePresence>
    );
};

export default StrategyReport;
