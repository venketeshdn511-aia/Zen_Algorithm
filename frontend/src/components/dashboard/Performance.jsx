import React from 'react';
import { motion } from 'framer-motion';
import { TrendingUp, Award, AlertTriangle, Binary, RefreshCw, Edit3, X, GripVertical, Check } from 'lucide-react';
import { AnimatePresence, Reorder } from 'framer-motion';
import { API_BASE_URL } from '../../utils/apiConfig';

const Performance = ({ tradingMode }) => {
    const [timeframe, setTimeframe] = React.useState('ALL');
    const [liveEquity, setLiveEquity] = React.useState(0);
    const [allocations, setAllocations] = React.useState([]);
    const [allStrategies, setAllStrategies] = React.useState([]);
    const [modalStrategies, setModalStrategies] = React.useState([]); // Decoupled state for smooth drag
    const [showEditModal, setShowEditModal] = React.useState(false);
    const [totalInitial, setTotalInitial] = React.useState(0);
    const [pnlPct, setPnlPct] = React.useState(0);
    const [totalCapital, setTotalCapital] = React.useState(0);
    const [isSyncing, setIsSyncing] = React.useState(true);
    const [equityCurve, setEquityCurve] = React.useState([]);
    const [portfolioStats, setPortfolioStats] = React.useState({});
    const [isSaving, setIsSaving] = React.useState(false);

    // Load strategy preferences from localStorage
    const [strategyOrder, setStrategyOrder] = React.useState(() => {
        const saved = localStorage.getItem('algo_strategy_priority');
        return saved ? JSON.parse(saved) : [];
    });

    // Calculate Drawdown Curve
    const drawdownCurve = React.useMemo(() => {
        if (!equityCurve || equityCurve.length === 0) return [];
        let maxSoFar = equityCurve[0].y;
        return equityCurve.map(d => {
            if (d.y > maxSoFar) maxSoFar = d.y;
            const dd = maxSoFar > 0 ? ((maxSoFar - d.y) / maxSoFar) * 100 : 0;
            return { x: d.x, y: dd };
        });
    }, [equityCurve]);

    const maxDrawdown = React.useMemo(() => {
        if (drawdownCurve.length === 0) return 0;
        return Math.max(...drawdownCurve.map(d => d.y));
    }, [drawdownCurve]);

    // Live Metrics Sync
    React.useEffect(() => {
        const fetchMetrics = async () => {
            if (showEditModal || isSaving) return; // PAUSE SYNC: Prevents drag jank or state reversion
            try {
                setIsSyncing(true);
                const statsRes = await fetch(`${API_BASE_URL}/api/stats?mode=${tradingMode}`);
                const statsData = await statsRes.json();

                if (statsData.total_capital !== undefined) {
                    setLiveEquity(statsData.total_capital);
                    setTotalInitial(statsData.total_initial || 0);
                    setPnlPct(statsData.total_pnl_pct || 0);
                    setTotalCapital(statsData.total_capital);
                    setEquityCurve(statsData.equity_curve || []);
                    setPortfolioStats(statsData);

                    if (statsData.strategies) {
                        const colors = ['bg-[var(--apple-blue)]', 'bg-[var(--apple-green)]', 'bg-[var(--apple-red)]', 'bg-[var(--apple-indigo)]', 'bg-[var(--text-muted)]'];
                        const mapped = statsData.strategies.map((s, idx) => ({
                            id: s.name,
                            name: s.name,
                            capital: s.capital,
                            pct: (s.capital / (statsData.total_capital || 1)) * 100,
                            color: colors[idx % colors.length]
                        }));
                        setAllStrategies(mapped);
                    }
                }
            } catch (error) {
                console.error('Failed to sync performance metrics:', error);
            } finally {
                setIsSyncing(false);
            }
        };

        fetchMetrics();
        const metricsTimer = setInterval(fetchMetrics, 30000);
        return () => clearInterval(metricsTimer);
    }, [tradingMode, showEditModal, isSaving]);

    // Sync modal state when opened
    React.useEffect(() => {
        if (showEditModal) {
            let sorted = [...allStrategies];
            if (strategyOrder.length > 0) {
                sorted.sort((a, b) => {
                    const indexA = strategyOrder.indexOf(a.name);
                    const indexB = strategyOrder.indexOf(b.name);
                    if (indexA === -1 && indexB === -1) return 0;
                    if (indexA === -1) return 1;
                    if (indexB === -1) return -1;
                    return indexA - indexB;
                });
            }
            setModalStrategies(sorted);
        }
    }, [showEditModal, allStrategies, strategyOrder]);

    // Determine displayed Top 5 based on priority order
    const displayedAllocations = React.useMemo(() => {
        let sorted = [...allStrategies];

        if (strategyOrder.length > 0) {
            sorted.sort((a, b) => {
                const indexA = strategyOrder.indexOf(a.name);
                const indexB = strategyOrder.indexOf(b.name);
                if (indexA === -1 && indexB === -1) return 0;
                if (indexA === -1) return 1;
                if (indexB === -1) return -1;
                return indexA - indexB;
            });
        } else {
            sorted.sort((a, b) => b.pct - a.pct);
        }

        return sorted.slice(0, 5);
    }, [allStrategies, strategyOrder]);

    const saveOrder = async (newOrder, updatedStrategies) => {
        setStrategyOrder(newOrder);
        localStorage.setItem('algo_strategy_priority', JSON.stringify(newOrder));

        setIsSaving(true);
        // Sync Capital Changes to Backend
        for (const s of updatedStrategies) {
            const original = allStrategies.find(os => os.name === s.name);

            // Validate Capital: Must be a number and greater than 0
            const isValid = typeof s.capital === 'number' && !isNaN(s.capital) && s.capital > 0;

            if (isValid && original && original.capital !== s.capital) {
                try {
                    await fetch(`${API_BASE_URL}/api/strategy/allocation`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ strategy: s.name, capital: s.capital })
                    });
                } catch (e) { console.error("Sync failed:", e); }
            }
        }

        // Mode-aware recalculation for immediate feedback
        const isReal = tradingMode === 'REAL';
        // Only sum valid capitals
        const validStrategies = updatedStrategies.map(s => ({
            ...s,
            capital: (typeof s.capital === 'number' && !isNaN(s.capital) && s.capital > 0) ? s.capital : (allStrategies.find(os => os.name === s.name)?.capital || 0)
        }));

        const sumOfCapitals = validStrategies.reduce((sum, s) => sum + s.capital, 0);

        // In REAL mode, percentages are relative to account balance (totalCapital)
        // In PAPER mode, percentages are relative to the sum of allocations
        const denominator = isReal ? (totalCapital || sumOfCapitals) : sumOfCapitals;

        const finalMapped = updatedStrategies.map(s => ({
            ...s,
            pct: (s.capital / (denominator || 1)) * 100
        }));

        if (!isReal) {
            setTotalCapital(sumOfCapitals);
        }

        setAllStrategies(finalMapped);
        setShowEditModal(false);

        // Wait for backend persistence to settle before resuming background sync
        setTimeout(() => setIsSaving(false), 5000);
    };

    const generatePathData = React.useCallback((data, width, height) => {
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
    }, []);

    const stats = [
        { label: 'Total PnL %', value: `${pnlPct.toFixed(1)}%`, icon: <Award className="text-[#007aff]" size={20} />, trend: pnlPct >= 0 ? `+${pnlPct.toFixed(1)}%` : `${pnlPct.toFixed(1)}%` },
        { label: 'Win Rate', value: `${portfolioStats.total_win_rate || 0}%`, icon: <TrendingUp className="text-[#34c759]" size={20} />, trend: `+${portfolioStats.total_wins || 0} Wins` },
        { label: 'Total Trades', value: portfolioStats.total_trades || 0, icon: <AlertTriangle className="text-[#ff3b30]" size={20} />, trend: `-${portfolioStats.total_losses || 0} Losses` },
        { label: 'System Alpha', value: (pnlPct / 10).toFixed(2), icon: <Binary className="text-[#af52de]" size={20} />, trend: 'Live' }
    ];

    return (
        <div className="space-y-12 pb-20">
            <header className="space-y-4">
                <h1 className="text-[32px] md:text-[56px] font-black tracking-tighter text-[var(--text-color)] leading-none">Performance.</h1>
                <p className="text-[16px] md:text-[20px] text-[var(--text-muted)] font-medium max-w-xl">
                    Quantitative audit of your algorithm's edge and historical stability.
                </p>
            </header>

            {/* Main Equity Curve */}
            <section className="apple-bento p-1 overflow-hidden shadow-2xl mx-1 md:mx-0" style={{ transform: 'translate3d(0,0,0)' }}>
                <div className="bg-[var(--card-bg)] p-6 md:p-12 min-h-[400px] md:min-h-[500px] flex flex-col">
                    <div className="flex justify-between items-start mb-8">
                        <div>
                            <p className="text-[12px] font-bold text-[var(--text-muted)] uppercase tracking-widest mb-1">Total Net Equity</p>
                            <h2 className="text-2xl md:text-4xl font-extrabold tracking-tight text-[var(--text-color)]">
                                ₹{liveEquity.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                            </h2>
                        </div>
                        <div className="flex flex-wrap gap-2 md:gap-4">
                            {['1D', '1W', '1M', '1Y', 'ALL'].map(t => (
                                <button
                                    key={t}
                                    onClick={() => setTimeframe(t)}
                                    className={`px-3 md:px-4 py-1.5 rounded-lg text-[10px] md:text-[11px] font-black transition-all ${timeframe === t ? 'bg-[var(--text-color)] text-[var(--bg-color)]' : 'text-[var(--text-muted)] hover:text-[var(--text-color)]'}`}
                                >
                                    {t}
                                </button>
                            ))}
                        </div>
                    </div>

                    <div className="flex-1 w-full relative">
                        <svg width="100%" height="300" viewBox="0 0 1000 300" preserveAspectRatio="none" className="overflow-visible">
                            <defs>
                                <linearGradient id="equityGradient" x1="0%" y1="0%" x2="0%" y2="100%">
                                    <stop offset="0%" stopColor="var(--apple-blue)" stopOpacity="0.15" />
                                    <stop offset="100%" stopColor="var(--apple-blue)" stopOpacity="0" />
                                </linearGradient>
                            </defs>
                            {[0, 75, 150, 225, 300].map(y => (
                                <line key={y} x1="0" y1={y} x2="1000" y2={y} stroke="var(--border-color)" strokeWidth="1" strokeDasharray="5,5" />
                            ))}
                            <motion.path
                                initial={{ pathLength: 0, opacity: 0 }}
                                animate={{ pathLength: 1, opacity: 1 }}
                                transition={{ duration: 2, ease: [0.16, 1, 0.3, 1] }}
                                d={generatePathData(equityCurve, 1000, 300)}
                                fill="none"
                                stroke="var(--apple-blue)"
                                strokeWidth="3"
                                strokeLinecap="round"
                            />
                            <motion.path
                                initial={{ opacity: 0 }}
                                animate={{ opacity: 1 }}
                                transition={{ duration: 1.5, delay: 0.5 }}
                                d={`${generatePathData(equityCurve, 1000, 300)} L 1000 300 L 0 300 Z`}
                                fill="url(#equityGradient)"
                            />
                        </svg>
                    </div>
                </div>
            </section>

            {/* Metrics Chips */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
                {stats.map((stat, i) => (
                    <div key={i} className="apple-bento p-6 md:p-8 border border-[var(--border-color)]">
                        <div className="flex justify-between items-start mb-4">
                            <div className="p-3 bg-[var(--bg-color)] rounded-xl border border-[var(--border-color)]">
                                {stat.icon}
                            </div>
                            <span className={`text-[11px] font-bold px-2 py-0.5 rounded-md bg-[var(--bg-color)] border border-[var(--border-color)] ${String(stat.trend).startsWith('+') ? 'text-[var(--apple-green)]' : (String(stat.trend).startsWith('-') ? 'text-[var(--apple-red)]' : 'text-[var(--text-muted)]')}`}>
                                {stat.trend}
                            </span>
                        </div>
                        <p className="text-[12px] font-bold text-[var(--text-muted)] uppercase tracking-widest mb-1">{stat.label}</p>
                        <p className="text-2xl md:text-3xl font-black text-[var(--text-color)] tracking-tighter">{stat.value}</p>
                    </div>
                ))}
            </div>

            {/* Secondary Charts: Drawdown & Allocation */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                <div className="apple-bento p-6 md:p-10 space-y-6 md:space-y-8">
                    <div className="flex justify-between items-center">
                        <h3 className="text-xl font-bold tracking-tight text-[var(--text-color)]">Drawdown Profile</h3>
                        <div className={`text-[11px] font-bold uppercase tracking-widest px-3 py-1 rounded-full border ${maxDrawdown > 5 ? 'text-[var(--apple-red)] bg-[var(--apple-red)]/10 border-[var(--apple-red)]/20' : 'text-[var(--text-muted)] bg-[var(--bg-color)] border-[var(--border-color)]'}`}>
                            {maxDrawdown > 5 ? 'High Risk Delta' : 'Stable Volatility'}
                        </div>
                    </div>
                    <div className="h-48 w-full">
                        <svg width="100%" height="100%" viewBox="0 0 1000 100" preserveAspectRatio="none">
                            <motion.path
                                initial={{ opacity: 0, scaleY: 0 }}
                                animate={{ opacity: 1, scaleY: 1 }}
                                transition={{ duration: 1, delay: 0.8 }}
                                d={generatePathData(drawdownCurve, 1000, 100)}
                                fill="none"
                                stroke="var(--apple-red)"
                                strokeWidth="2"
                                strokeLinecap="round"
                            />
                            <motion.path
                                initial={{ opacity: 0 }}
                                animate={{ opacity: 0.1 }}
                                transition={{ duration: 1, delay: 1 }}
                                d={`${generatePathData(drawdownCurve, 1000, 100)} L 1000 0 L 0 0 Z`}
                                fill="var(--apple-red)"
                            />
                        </svg>
                    </div>
                    <div className="flex justify-between text-[11px] font-bold text-[var(--text-muted)] uppercase">
                        <span>Max Peak-to-Trough: {maxDrawdown.toFixed(1)}%</span>
                        <span>Performance: LIVE</span>
                    </div>
                </div>

                <div className="apple-bento p-6 md:p-10 space-y-6 md:space-y-8 relative">
                    <div className="flex justify-between items-center">
                        <h3 className="text-xl font-bold tracking-tight text-[var(--text-color)]">Live Allocation (Top 5)</h3>
                        <button
                            onClick={() => setShowEditModal(true)}
                            className="p-2 hover:bg-[var(--border-color)] rounded-xl transition-all text-[var(--text-muted)] hover:text-[var(--apple-blue)] flex items-center gap-2 text-[10px] font-black uppercase tracking-widest"
                        >
                            <Edit3 size={14} /> Edit Rankings
                        </button>
                    </div>
                    <div className="space-y-6">
                        {displayedAllocations.map((s, i) => (
                            <motion.div
                                key={s.id}
                                layout
                                initial={{ opacity: 0, x: -20 }}
                                animate={{ opacity: 1, x: 0 }}
                                transition={{ delay: i * 0.1, duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
                                className="space-y-3"
                            >
                                <div className="flex justify-between items-end">
                                    <div className="space-y-1">
                                        <span className="text-[14px] font-bold text-[var(--text-color)] block">{s.name}</span>
                                        <span className="text-[11px] text-[var(--text-muted)] font-black uppercase tracking-widest">
                                            ₹{s.capital.toLocaleString()} CAPITAL
                                        </span>
                                    </div>
                                    <span className={`text-[13px] font-black ${s.pct > 0 ? 'text-[var(--text-color)]' : 'text-[var(--text-muted)]'}`}>{s.pct.toFixed(1)}%</span>
                                </div>
                                <div className="group relative pt-2">
                                    <div className="h-1.5 w-full bg-[var(--bg-color)] border border-[var(--border-color)] rounded-full overflow-hidden">
                                        <motion.div
                                            initial={false}
                                            animate={{ width: `${s.pct}%` }}
                                            transition={{ duration: 1.2, ease: "circOut" }}
                                            className={`h-full ${s.color}`}
                                        />
                                    </div>
                                </div>
                            </motion.div>
                        ))}

                        <div className="pt-4 border-t border-[var(--border-color)] flex justify-between items-center">
                            <div className="flex flex-col gap-1">
                                <span className="text-[11px] font-black text-[var(--text-muted)] uppercase tracking-widest flex items-center gap-2">
                                    Total Active Capital
                                    {isSyncing ? (
                                        <RefreshCw size={10} className="animate-spin text-[var(--apple-blue)]" />
                                    ) : (
                                        <span className="w-1 h-1 rounded-full bg-[var(--apple-green)] shadow-[0_0_5px_var(--apple-green)]" />
                                    )}
                                </span>
                                <span className="text-[9px] font-bold text-[var(--apple-blue)] uppercase tracking-widest px-2 py-0.5 bg-[var(--apple-blue)]/10 rounded-full w-fit">
                                    Kotak Live Sync
                                </span>
                            </div>
                            <span className="text-lg font-black text-[var(--text-color)]">₹{totalCapital.toLocaleString()}</span>
                        </div>
                    </div>
                </div>
            </div>

            {/* Strategy Priority Modal */}
            <AnimatePresence>
                {showEditModal && (
                    <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        className="fixed inset-0 z-[100] flex items-center justify-center p-6 bg-black/60 backdrop-blur-md"
                    >
                        <motion.div
                            initial={{ scale: 0.9, opacity: 0, y: 20 }}
                            animate={{ scale: 1, opacity: 1, y: 0 }}
                            exit={{ scale: 0.9, opacity: 0, y: 20 }}
                            className="bg-[var(--card-bg)] w-full max-w-xl rounded-[24px] md:rounded-[32px] border border-[var(--border-color)] overflow-hidden shadow-2xl flex flex-col max-h-[90vh]"
                        >
                            <div className="p-8 border-b border-[var(--border-color)] flex justify-between items-center bg-[#1c1c1e]/50">
                                <div>
                                    <h2 className="text-2xl font-bold tracking-tight">Strategy Rankings</h2>
                                    <p className="text-[12px] text-[var(--text-muted)] font-medium mt-1 uppercase tracking-widest">Drag to reorder. Top 5 will be pinned to dashboard.</p>
                                </div>
                                <button
                                    onClick={() => setShowEditModal(false)}
                                    className="p-3 hover:bg-[var(--border-color)] rounded-full transition-colors"
                                >
                                    <X size={20} />
                                </button>
                            </div>

                            <div className="flex-1 overflow-y-auto p-6 space-y-4 custom-scrollbar">
                                <Reorder.Group
                                    axis="y"
                                    values={modalStrategies.map(s => s.name)}
                                    onReorder={(newOrder) => {
                                        const reordered = newOrder.map(name => modalStrategies.find(s => s.name === name));
                                        setModalStrategies(reordered);
                                    }}
                                    className="space-y-3"
                                >
                                    {modalStrategies.map((s, idx) => (
                                        <Reorder.Item
                                            key={s.name}
                                            value={s.name}
                                            whileDrag={{ scale: 1.02, boxShadow: "0 20px 40px rgba(0,0,0,0.4)" }}
                                            className="bg-[var(--bg-color)] p-5 rounded-2xl border border-[var(--border-color)] flex items-center gap-6 group hover:border-[var(--apple-blue)]/40 transition-colors"
                                        >
                                            <div className="text-[var(--text-muted)] cursor-grab active:cursor-grabbing p-2 hover:bg-[var(--border-color)] rounded-lg">
                                                <GripVertical size={18} />
                                            </div>
                                            <div className="flex-1">
                                                <div className="flex items-center gap-2">
                                                    <span className="text-base font-bold text-[var(--text-color)]">{s.name}</span>
                                                    {idx < 5 && <span className="text-[9px] font-black bg-[var(--apple-blue)]/10 text-[var(--apple-blue)] px-2 py-0.5 rounded-full uppercase tracking-widest border border-[var(--apple-blue)]/20">Pinned</span>}
                                                </div>
                                                <div className="flex items-center gap-2 mt-2">
                                                    <span className="text-[10px] text-[var(--text-muted)] font-black uppercase tracking-widest">Manual Cap (₹)</span>
                                                </div>
                                            </div>

                                            <div className="flex items-center gap-4">
                                                <div className="relative">
                                                    <span className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)] text-[12px] font-bold">₹</span>
                                                    <input
                                                        type="number"
                                                        value={s.capital}
                                                        onChange={(e) => {
                                                            const rawVal = e.target.value;
                                                            if (rawVal === '') {
                                                                const next = modalStrategies.map(ms => ms.name === s.name ? { ...ms, capital: '' } : ms);
                                                                setModalStrategies(next);
                                                                return;
                                                            }
                                                            const val = parseFloat(rawVal);
                                                            if (!isNaN(val)) {
                                                                const next = modalStrategies.map(ms => ms.name === s.name ? { ...ms, capital: val } : ms);
                                                                setModalStrategies(next);
                                                            }
                                                        }}
                                                        onPointerDown={(e) => e.stopPropagation()} // Allow input focus on drag items
                                                        className="w-32 py-2.5 pl-7 pr-3 bg-[var(--card-bg)] border border-[var(--border-color)] rounded-xl text-sm font-black focus:outline-none focus:border-[var(--apple-blue)] transition-all"
                                                    />
                                                </div>
                                                <div className="text-right min-w-[50px]">
                                                    <span className="text-base font-black text-[var(--text-color)]">{((s.capital / (totalCapital || 1)) * 100).toFixed(1)}%</span>
                                                </div>
                                            </div>
                                        </Reorder.Item>
                                    ))}
                                </Reorder.Group>
                            </div>

                            <div className="p-8 border-t border-[var(--border-color)] bg-[#1c1c1e]/50 flex gap-4">
                                <button
                                    onClick={() => {
                                        saveOrder(modalStrategies.map(s => s.name), modalStrategies);
                                    }}
                                    className="flex-1 py-4 bg-[var(--text-color)] text-[var(--bg-color)] font-black uppercase tracking-widest text-[12px] rounded-2xl hover:opacity-90 transition-all flex items-center justify-center gap-3"
                                >
                                    <Check size={18} /> Save Allocation & Priority
                                </button>
                                <button
                                    onClick={() => setShowEditModal(false)}
                                    className="px-8 py-4 bg-[var(--border-color)] text-[var(--text-color)] font-black uppercase tracking-widest text-[12px] rounded-2xl hover:bg-[var(--card-hover)] transition-all"
                                >
                                    Cancel
                                </button>
                            </div>
                        </motion.div>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
};

export default Performance;
