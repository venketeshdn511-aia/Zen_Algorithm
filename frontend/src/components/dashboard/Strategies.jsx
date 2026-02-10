import React, { useState, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Search, Filter, Play, Pause, ChevronDown, Binary, Zap, RefreshCw } from 'lucide-react';
import StrategyCard from './StrategyCard';

const Strategies = ({ onOpenBlueprint, tradingMode }) => {
    const [searchQuery, setSearchQuery] = useState('');
    const [activeFilter, setActiveFilter] = useState('All');
    const [isSyncing, setIsSyncing] = useState(false);
    const [isLiveBotActive, setIsLiveBotActive] = useState(true);
    const [strategies, setStrategies] = useState([]);
    const [totalStats, setTotalStats] = useState({ aum: 0, winRate: '0%', alpha: '0.00' });

    const fetchData = React.useCallback(async () => {
        setIsSyncing(true);
        try {
            const response = await fetch(`/api/stats?mode=${tradingMode}`);
            const data = await response.json();

            if (data.strategies) {
                // Map backend strategies to frontend format
                const mappedStrategies = data.strategies.map((s, idx) => ({
                    id: idx + 1,
                    name: s.name,
                    profit: s.pnl,
                    profitPct: s.pnl_pct,
                    status: s.status === 'Monitoring...' ? 'Active' : s.status,
                    isPro: s.pnl_pct > 10,
                    history: s.trades || [], // Full trade objects for analytics
                    metrics: {
                        winRate: `${s.win_rate}%`,
                        profitFactor: (s.wins / (s.losses || 1) * 1.5).toFixed(2), // ContextualPF
                        maxDrawdown: s.pnl_pct < 0 ? `${Math.abs(s.pnl_pct).toFixed(1)}%` : '0.0%',
                        totalTrades: (s.wins + s.losses).toString()
                    },
                    thoughts: s.status,
                    activeTrade: s.position
                }));
                setStrategies(mappedStrategies);
                setTotalStats({
                    aum: data.total_capital,
                    winRate: `${data.total_win_rate}%`,
                    alpha: (data.total_pnl_pct / 10).toFixed(2)
                });
                setIsLiveBotActive(data.running);
            }
        } catch (err) {
            console.error("Strategies sync error:", err);
        } finally {
            setIsSyncing(false);
        }
    }, [tradingMode]);

    React.useEffect(() => {
        fetchData();
        const interval = setInterval(fetchData, 10000); // Sync every 10s
        return () => clearInterval(interval);
    }, [fetchData]);

    const handleSync = () => {
        fetchData();
    };

    const toggleStrategyStatus = async (id, name) => {
        // In a real app, this would call a backend toggle endpoint
        console.log(`Toggling ${name}`);
    };

    const filters = ['All', 'Active', 'Paused', 'Pro Only', 'Top Gainers'];

    const filteredStrategies = useMemo(() => {
        if (!strategies) return [];
        return strategies.filter(s => {
            const matchesSearch = s.name.toLowerCase().includes(searchQuery.toLowerCase());
            if (!matchesSearch) return false;

            if (activeFilter === 'All') return true;
            if (activeFilter === 'Active') return s.status === 'Active';
            if (activeFilter === 'Paused') return s.status === 'Paused';
            if (activeFilter === 'Pro Only') return s.isPro;
            if (activeFilter === 'Top Gainers') return s.profitPct > 5;
            return true;
        });
    }, [searchQuery, activeFilter, strategies]);

    return (
        <div className="space-y-12">
            {/* Header Controls */}
            <header className="flex flex-col md:flex-row justify-between items-start md:items-end gap-8">
                <div className="space-y-4">
                    <div className="flex items-center gap-4">
                        <h1 className="text-[56px] font-black tracking-tighter text-[var(--text-color)] leading-none">Strategies.</h1>
                        <div
                            onClick={() => setIsLiveBotActive(!isLiveBotActive)}
                            className={`mt-4 px-4 py-2 rounded-full cursor-pointer transition-all flex items-center gap-2 border ${isLiveBotActive
                                ? 'bg-[var(--apple-green)]/10 text-[var(--apple-green)] border-[var(--apple-green)]/20 shadow-[0_0_20px_rgba(52,199,89,0.2)]'
                                : 'bg-[var(--text-muted)]/10 text-[var(--text-muted)] border-[var(--border-color)]'
                                }`}
                        >
                            <div className={`w-2 h-2 rounded-full ${isLiveBotActive ? 'bg-[var(--apple-green)] animate-pulse' : 'bg-[var(--text-muted)]'}`} />
                            <span className="text-[11px] font-black uppercase tracking-widest">{isLiveBotActive ? 'Live Mesh Active' : 'Mesh Hibernating'}</span>
                        </div>
                    </div>
                    <p className="text-[20px] text-[var(--text-muted)] font-medium max-w-xl">
                        Deploy, monitor, and refine your autonomous trading mesh.
                    </p>
                </div>

                <div className="flex flex-wrap gap-4 w-full md:w-auto">
                    <div className="relative flex-1 md:w-80">
                        <Search className="absolute left-4 top-1/2 -translate-y-1/2 text-[var(--text-muted)]" size={18} />
                        <input
                            type="text"
                            placeholder="Search engines..."
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            className="w-full h-12 pl-12 pr-4 bg-[var(--card-bg)] border border-[var(--border-color)] rounded-2xl text-[14px] font-medium focus:outline-none focus:border-[var(--apple-blue)] transition-all"
                        />
                    </div>
                    <button
                        onClick={handleSync}
                        disabled={isSyncing}
                        className={`h-12 px-6 apple-bento flex items-center gap-2 hover:bg-[var(--card-hover)] transition-all ${isSyncing ? 'opacity-50 cursor-not-allowed' : ''}`}
                    >
                        <RefreshCw size={18} className={`text-[var(--apple-blue)] ${isSyncing ? 'animate-spin' : ''}`} />
                        <span className="text-[13px] font-bold text-[var(--text-color)]">
                            {isSyncing ? 'Syncing...' : 'Sync All'}
                        </span>
                    </button>
                </div>
            </header>

            {/* Filter Bar */}
            <div className="flex gap-3 overflow-x-auto pb-4 no-scrollbar">
                {filters.map(filter => (
                    <button
                        key={filter}
                        onClick={() => setActiveFilter(filter)}
                        className={`px-6 py-2.5 rounded-full text-[13px] font-bold transition-all whitespace-nowrap border ${activeFilter === filter
                            ? 'bg-[var(--text-color)] text-[var(--bg-color)] border-[var(--text-color)]'
                            : 'bg-transparent text-[var(--text-muted)] border-[var(--border-color)] hover:border-[var(--text-muted)]'
                            }`}
                    >
                        {filter}
                    </button>
                ))}
            </div>

            {/* Stats Overview */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
                {[
                    {
                        label: 'Active Engines',
                        value: strategies.filter(s => s.status === 'Active').length,
                        color: 'text-[var(--apple-blue)]'
                    },
                    {
                        label: 'Total AUM',
                        value: typeof totalStats.aum === 'number'
                            ? `₹${totalStats.aum >= 100000
                                ? (totalStats.aum / 100000).toFixed(2) + 'L'
                                : totalStats.aum.toLocaleString()}`
                            : '₹0',
                        color: 'text-[var(--text-color)]'
                    },
                    { label: 'Avg Win Rate', value: totalStats.winRate, color: 'text-[var(--apple-green)]' },
                    { label: 'System Alpha', value: `+${totalStats.alpha}`, color: 'text-[var(--text-color)]' }
                ].map((stat, i) => (
                    <div key={i} className="apple-bento p-6 border border-[var(--border-color)]">
                        <p className="text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest mb-2">{stat.label}</p>
                        <p className={`text-2xl font-black ${stat.color}`}>{stat.value}</p>
                    </div>
                ))}
            </div>

            {/* Strategy Grid */}
            <AnimatePresence mode="popLayout">
                <motion.div
                    layout
                    className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8"
                >
                    {filteredStrategies.map((strategy) => (
                        <motion.div
                            key={strategy.name}
                            layout
                            initial={{ opacity: 0, scale: 0.9 }}
                            animate={{ opacity: 1, scale: 1 }}
                            exit={{ opacity: 0, scale: 0.9 }}
                            transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
                        >
                            <StrategyCard
                                {...strategy}
                                onOpenBlueprint={onOpenBlueprint}
                                onToggleStatus={() => toggleStrategyStatus(strategy.id)}
                                isMasterLive={isLiveBotActive}
                            />
                        </motion.div>
                    ))}
                </motion.div>
            </AnimatePresence>

            {filteredStrategies.length === 0 && (
                <div className="py-20 text-center">
                    <p className="text-[var(--text-muted)] text-lg font-medium">No strategies match your current filters.</p>
                </div>
            )}
        </div>
    );
};

export default Strategies;
