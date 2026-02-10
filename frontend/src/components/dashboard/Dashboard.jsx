import React from 'react';
import StatCard from './StatCard';
import StrategyCard from './StrategyCard';
import AIBrain from '../ai/AIBrain';
import { motion } from 'framer-motion';
import { ArrowUpRight, TrendingUp, Cpu, Globe } from 'lucide-react';

const Dashboard = ({ onOpenBlueprint, tradingMode }) => {
    const [liveEquity, setLiveEquity] = React.useState(0);
    const [ping, setPing] = React.useState(0);
    const [pnlPct, setPnlPct] = React.useState(0);
    const [lastUpdate, setLastUpdate] = React.useState('Just Now');
    const [equityCurve, setEquityCurve] = React.useState([]);
    const [recentTrades, setRecentTrades] = React.useState([]);

    React.useEffect(() => {
        const fetchData = async () => {
            const start = performance.now();
            try {
                const response = await fetch(`/api/stats?mode=${tradingMode}`);
                const data = await response.json();
                const end = performance.now();

                setPing(Math.round(end - start));
                if (data.total_capital !== undefined) {
                    setLiveEquity(data.total_capital);
                }
                if (data.total_pnl_pct !== undefined) {
                    setPnlPct(data.total_pnl_pct);
                }
                if (data.equity_curve) {
                    setEquityCurve(data.equity_curve);
                }
                if (data.recent_trades) {
                    setRecentTrades(data.recent_trades);
                }
                setLastUpdate(new Date().toLocaleTimeString());
            } catch (err) {
                console.error("Dashboard sync error:", err);
            }
        };

        fetchData();
        const interval = setInterval(fetchData, 5000);
        return () => clearInterval(interval);
    }, [tradingMode]);

    // Generate dynamic SVG path for the hero chart
    const generatePathData = (data) => {
        if (!data || data.length < 2) return "M0,250 L1000,250";
        const minY = Math.min(...data.map(d => d.y));
        const maxY = Math.max(...data.map(d => d.y));
        const range = maxY - minY || 1;

        return data.map((d, i) => {
            const x = (i / (data.length - 1)) * 1000;
            const y = 250 - ((d.y - minY) / range) * 200; // Standardize to 200px height range
            return `${i === 0 ? 'M' : 'L'}${x},${y}`;
        }).join(' ');
    };

    const pathData = generatePathData(equityCurve);

    return (
        <div className="space-y-32 pb-64">
            {/* Hero Product Section */}
            <section className="relative pt-20">
                <div className="text-center space-y-6">
                    <motion.span
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        className="text-[17px] font-bold text-[#007aff] uppercase tracking-widest"
                    >
                        Real-time Portfolio Intelligence
                    </motion.span>
                    <motion.h1
                        initial={{ opacity: 0, y: 30 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: 0.1, duration: 0.8 }}
                        className="hero-text"
                    >
                        Precision execution.<br />Mathematically superior.
                    </motion.h1>
                    <motion.p
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: 0.2, duration: 0.8 }}
                        className="sub-hero-text max-w-2xl mx-auto"
                    >
                        AlgoBot Pro orchestrates your capital across multiple strategies with microsecond latency and AI-driven regime detection.
                    </motion.p>
                </div>

                {/* Big Product Shot - Equity Display */}
                <motion.div
                    initial={{ opacity: 0, scale: 0.95 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ delay: 0.4, duration: 1.2 }}
                    className="mt-20 apple-bento p-1 overflow-hidden shadow-2xl"
                >
                    <div className="bg-[var(--card-bg)] p-12 h-[600px] relative flex flex-col justify-between">
                        <div className="flex justify-between items-start">
                            <div>
                                <p className="text-[14px] font-bold text-[var(--text-muted)] uppercase tracking-widest mb-1">Total Net Equity</p>
                                <h2 className="text-[64px] font-extrabold tracking-tighter text-[var(--text-color)]">
                                    ₹{liveEquity.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                </h2>
                            </div>
                            <div className="flex items-center gap-2 px-6 py-2 bg-[#34c759]/10 text-[#34c759] rounded-full border border-[#34c759]/20 font-bold text-lg">
                                <TrendingUp size={24} /> +{pnlPct.toFixed(1)}%
                            </div>
                        </div>

                        {/* Cinematic Line Graph Visualization */}
                        <div className="flex-1 w-full py-20 relative overflow-hidden">
                            <div className="absolute inset-0 bg-gradient-to-t from-[#007aff0a] to-transparent opacity-50" />

                            <svg width="100%" height="100%" viewBox="0 0 1000 300" preserveAspectRatio="none" className="relative z-10">
                                <defs>
                                    <linearGradient id="heroGradient" x1="0%" y1="0%" x2="100%" y2="0%">
                                        <stop offset="0%" stopColor="rgba(0, 122, 255, 0.2)" />
                                        <stop offset="50%" stopColor="rgba(0, 122, 255, 1)" />
                                        <stop offset="100%" stopColor="rgba(52, 199, 89, 1)" />
                                    </linearGradient>
                                    <filter id="glow">
                                        <feGaussianBlur stdDeviation="4" result="coloredBlur" />
                                        <feMerge>
                                            <feMergeNode in="coloredBlur" />
                                            <feMergeNode in="SourceGraphic" />
                                        </feMerge>
                                    </filter>
                                </defs>
                                <motion.path
                                    initial={{ pathLength: 0, opacity: 0 }}
                                    animate={{ pathLength: 1, opacity: 1 }}
                                    transition={{ duration: 3, ease: [0.16, 1, 0.3, 1] }}
                                    d={pathData}
                                    fill="none"
                                    stroke="url(#heroGradient)"
                                    strokeWidth="4"
                                    strokeLinecap="round"
                                    filter="url(#glow)"
                                />
                                {/* Area fill for depth */}
                                <motion.path
                                    initial={{ opacity: 0 }}
                                    animate={{ opacity: 0.1 }}
                                    transition={{ duration: 2, delay: 1 }}
                                    d={`${pathData} L 1000 300 L 0 300 Z`}
                                    fill="url(#heroGradient)"
                                />
                            </svg>

                            <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                                <div className="text-[140px] font-black text-[var(--text-color)] opacity-[0.03] uppercase select-none tracking-tighter">PERFORMANCE</div>
                            </div>
                        </div>

                        <div className="flex justify-between items-center text-[var(--text-muted)] text-xs font-bold uppercase tracking-widest">
                            <div className="flex gap-12">
                                <div>Ping: <span className="text-[var(--text-color)]">{ping}ms</span></div>
                                <div>Server: <span className="text-[var(--text-color)]">Local Node</span></div>
                            </div>
                            <div>Last Update: <span className="text-[var(--text-color)]">{lastUpdate}</span></div>
                        </div>
                    </div>
                </motion.div>
            </section>

            {/* Feature Grid - Bento 2.0 */}
            <section className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                <div className="apple-bento p-10 lg:col-span-2 flex flex-col justify-between min-h-[400px]">
                    <div className="space-y-2">
                        <div className="p-3 bg-[var(--border-color)] w-fit rounded-2xl border border-[var(--border-color)] mb-6">
                            <Cpu className="text-[#007aff]" size={32} />
                        </div>
                        <h3 className="text-4xl font-bold tracking-tight text-[var(--text-color)]">AI Multi-Regime Core</h3>
                        <p className="text-xl text-[var(--text-muted)] font-medium leading-normal max-w-lg">
                            Our neural networks analyze 40+ market factors to identify shifting regimes before they impact your PnL.
                        </p>
                    </div>

                    <div className="grid grid-cols-3 gap-8 mt-12 pt-12 border-t border-[var(--border-color)]">
                        <div>
                            <p className="text-[11px] font-bold text-[var(--text-muted)] uppercase tracking-widest mb-2">Market Regime</p>
                            <p className="text-2xl font-bold text-[#34c759]">BULLISH VOLATILE</p>
                        </div>
                        <div>
                            <p className="text-[11px] font-bold text-[var(--text-muted)] uppercase tracking-widest mb-2">Signal Strength</p>
                            <p className="text-2xl font-bold text-[var(--text-color)]">84%</p>
                        </div>
                        <div>
                            <p className="text-[11px] font-bold text-[var(--text-muted)] uppercase tracking-widest mb-2">Alpha Decay</p>
                            <p className="text-2xl font-bold text-[var(--text-color)]">LOW</p>
                        </div>
                    </div>
                </div>

                <div className="apple-bento p-10 flex flex-col justify-between min-h-[400px]">
                    <div className="space-y-4">
                        <div className="p-3 bg-[var(--border-color)] w-fit rounded-2xl border border-[var(--border-color)] mb-4">
                            <Globe className="text-[#34c759]" size={32} />
                        </div>
                        <h3 className="text-3xl font-bold tracking-tight text-[var(--text-color)]">System Telemetry</h3>
                        <p className="text-lg text-[var(--text-muted)] font-medium leading-relaxed">
                            Active connections across 12 data centers worldwide.
                        </p>
                    </div>
                    <div className="space-y-6">
                        <div className="flex justify-between items-end">
                            <span className="text-sm font-bold text-[var(--text-muted)]">API HEALTH</span>
                            <span className="text-sm font-bold text-[#34c759]">EXCELLENT</span>
                        </div>
                        <div className="h-2 w-full bg-[var(--border-color)] rounded-full overflow-hidden">
                            <motion.div
                                initial={{ width: 0 }}
                                animate={{ width: "98%" }}
                                transition={{ duration: 2, delay: 0.5 }}
                                className="h-full bg-[#34c759]"
                            />
                        </div>
                        <div className="flex justify-between text-[11px] text-[var(--text-muted)] font-mono">
                            <span>NSE: 12ms</span>
                            <span>BSE: 18ms</span>
                            <span>MCX: 24ms</span>
                        </div>
                    </div>
                </div>
            </section>

            {/* Strategies Showcase */}
            <section className="space-y-16">
                <div className="flex justify-between items-end">
                    <div className="space-y-4 text-left">
                        <h2 className="text-5xl font-bold tracking-tight text-[var(--text-color)]">Active Engines.</h2>
                        <p className="text-xl text-[var(--text-muted)] font-medium leading-relaxed">
                            Independent machines harvesting specific market inefficiencies.
                        </p>
                    </div>
                    <div className="flex gap-4 mb-4">
                        <div className="px-4 py-2 glass-island text-[13px] font-bold text-[var(--text-color)]">ALL STRATEGIES (8)</div>
                        <div className="px-4 py-2 text-[13px] font-bold text-[var(--text-muted)] hover:text-[var(--text-color)] cursor-pointer transition-colors">PRO ONLY</div>
                    </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
                    <StrategyCard
                        name="Failed Auction b2"
                        profit={1240}
                        profitPct={2.4}
                        status="Active"
                        isPro={true}
                        history={[0, 400, 200, 800, 600, 1240]}
                        metrics={{ winRate: '64%', profitFactor: '2.4', maxDrawdown: '1.2%', totalTrades: '248' }}
                        onOpenBlueprint={onOpenBlueprint}
                    />
                    <StrategyCard
                        name="BankNifty Breakout"
                        profit={3290}
                        profitPct={6.2}
                        status="Active"
                        isPro={true}
                        history={[0, 1000, 800, 2200, 1800, 3290]}
                        metrics={{ winRate: '72%', profitFactor: '3.1', maxDrawdown: '0.8%', totalTrades: '124' }}
                        onOpenBlueprint={onOpenBlueprint}
                    />
                    <StrategyCard
                        name="EMA Reversion"
                        profit={-450}
                        profitPct={-0.8}
                        status="Paused"
                        history={[0, -200, 100, -300, -100, -450]}
                        metrics={{ winRate: '48%', profitFactor: '0.9', maxDrawdown: '5.4%', totalTrades: '86' }}
                        onOpenBlueprint={onOpenBlueprint}
                    />
                    <StrategyCard
                        name="Gamma Scalper"
                        profit={8540}
                        profitPct={12.4}
                        status="Active"
                        isPro={true}
                        history={[0, 2000, -500, 4000, 3000, 8540]}
                        metrics={{ winRate: '82%', profitFactor: '4.8', maxDrawdown: '2.1%', totalTrades: '1,042' }}
                        onOpenBlueprint={onOpenBlueprint}
                    />
                    <StrategyCard
                        name="Mean Revert Pro"
                        profit={1120}
                        profitPct={1.2}
                        status="Active"
                        history={[0, 300, 200, 1000, 800, 1120]}
                        metrics={{ winRate: '58%', profitFactor: '1.4', maxDrawdown: '3.2%', totalTrades: '420' }}
                        onOpenBlueprint={onOpenBlueprint}
                    />
                    <StrategyCard
                        name="Volatility Arb"
                        profit={-120}
                        profitPct={-0.2}
                        status="Active"
                        history={[0, -500, -200, 400, 100, -120]}
                        metrics={{ winRate: '52%', profitFactor: '0.98', maxDrawdown: '1.8%', totalTrades: '156' }}
                        onOpenBlueprint={onOpenBlueprint}
                    />
                </div>
            </section>

            {/* Intelligence Snapshot */}
            <section className="apple-bento p-12 grid grid-cols-1 lg:grid-cols-2 gap-20">
                <div>
                    <h2 className="text-4xl font-bold mb-6 tracking-tight text-[var(--text-color)]">Gemini Insight Panel</h2>
                    <p className="text-lg text-[var(--text-muted)] mb-10 font-medium leading-relaxed">
                        Direct link to LLM-powered market analysis. We translate complex data into actionable behavioral insights.
                    </p>
                    <AIBrain />
                </div>
                <div className="bg-[var(--bg-color)] opacity-80 rounded-3xl p-8 border border-[var(--border-color)] flex flex-col justify-center items-center text-center space-y-6">
                    <div className="w-24 h-24 rounded-full bg-gradient-to-tr from-[#007aff] to-[#34c759] animate-pulse blur-xl opacity-20 absolute" />
                    <Cpu size={64} className="text-[#007aff] relative" />
                    <h4 className="text-2xl font-bold tracking-tight text-[var(--text-color)]">Brain Status: Learning</h4>
                    <div className="text-[13px] font-mono text-[var(--text-muted)] line-clamp-6 bg-[var(--card-bg)] p-4 rounded-xl border border-[var(--border-color)]">
                        {`{ "epoch": 104, "loss": 0.024, "regime": "expanding_volatility", "sentiment": 0.62, "last_action": "REWEIGHT_BANKS" }`}
                    </div>
                </div>
            </section>
        </div>
    );
};

export default Dashboard;
