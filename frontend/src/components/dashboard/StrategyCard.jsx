import React, { useState, useMemo } from 'react';
import { motion } from 'framer-motion';
import { Power, ArrowRight, Zap, ShieldAlert, Play, Pause } from 'lucide-react';
import AnimatedNumber from '../common/AnimatedNumber';
import { exportStrategyPDF } from '../../utils/pdfExport';

const StrategyCard = ({ name, profit, profitPct, status, isPro, history = [0, 10, -5, 15, 5, 20], metrics = {}, thoughts, activeTrade, onOpenBlueprint, onToggleStatus, isMasterLive = true }) => {
    const [isFlipped, setIsFlipped] = useState(false);
    const isPositive = profit >= 0;
    const isPaused = status === 'Paused' || !isMasterLive;

    // Memoize path data computation
    const pathData = useMemo(() => {
        const data = history;
        if (!data || data.length < 2) return "M0,20 L100,20";
        // Extract PnL values if data is objects
        const vals = typeof data[0] === 'object' ? data.map(t => t.pnl) : data;

        const min = Math.min(...vals);
        const max = Math.max(...vals);
        const range = max - min || 1;

        return vals.map((val, i) => {
            const x = (i / (vals.length - 1)) * 400; // Scaled to 400 for viewBox
            const y = 110 - ((val - min) / range) * 100; // Scale to fit 120px height
            return `${i === 0 ? 'M' : 'L'}${x},${y}`;
        }).join(' ');
    }, [history]);

    return (
        <div
            className={`perspective-1000 h-[320px] w-full cursor-pointer group relative ${!isMasterLive ? 'pointer-events-none opacity-80' : ''}`}
            onClick={(e) => {
                e.stopPropagation();
                setIsFlipped(!isFlipped);
            }}
        >
            <motion.div
                initial={false}
                animate={{ rotateY: isFlipped ? 180 : 0 }}
                transition={{ duration: 0.6, ease: [0.23, 1, 0.32, 1] }}
                style={{ transformStyle: 'preserve-3d' }}
                className="w-full h-full relative"
                whileHover={{ zIndex: 50 }}
            >
                {/* Front Side */}
                <div
                    className={`apple-bento h-full w-full flex flex-col absolute inset-0 backface-hidden shadow-sm transition-opacity duration-500 ${isPaused ? 'opacity-60 grayscale-[0.5]' : ''}`}
                    style={{ transform: 'translateZ(0px)' }}
                >
                    {isPro && (
                        <div className="absolute top-4 right-4 px-2 py-0.5 bg-[var(--apple-blue)]/10 text-[var(--apple-blue)] rounded-full text-[8px] font-black uppercase tracking-widest border border-[var(--apple-blue)]/20 flex items-center gap-1">
                            <Zap size={8} fill="currentColor" /> Pro Engine
                        </div>
                    )}

                    <div className="p-6 pb-2 flex-1 flex flex-col">
                        <div className="flex justify-between items-start mb-1">
                            <div>
                                <h3 className="text-lg font-bold tracking-tight text-[var(--text-color)]">{name}</h3>
                                <div className="flex items-center gap-2 mt-0.5">
                                    <div className={`w-1.5 h-1.5 rounded-full ${isPaused ? 'bg-[var(--text-muted)]' : 'bg-[var(--apple-green)] animate-pulse'}`} />
                                    <span className="text-[10px] uppercase font-black tracking-widest text-[var(--text-muted)]">
                                        {!isMasterLive ? 'Mesh Hibernating' : status}
                                    </span>
                                </div>
                            </div>
                        </div>

                        {/* Neural Thought Stream */}
                        <div className="bg-[var(--bg-color)]/50 border border-[var(--border-color)] rounded-xl px-3 py-2 my-3 overflow-hidden">
                            <p className="text-[9px] font-medium text-[var(--apple-indigo)] animate-pulse line-clamp-1 italic">
                                "{!isMasterLive ? 'Global safety lock active. Subroutines suspended.' : (thoughts || 'Scanning alpha vectors...')}"
                            </p>
                        </div>

                        {activeTrade ? (
                            /* Active Trade Panel — Redesigned for clarity */
                            <div className="bg-[var(--apple-blue)]/5 border border-[var(--apple-blue)]/20 rounded-xl p-3 mb-2 animate-in fade-in slide-in-from-bottom-2 duration-500">
                                <div className="flex justify-between items-center mb-2">
                                    <span className="text-[9px] font-black text-[var(--apple-blue)] uppercase tracking-widest">Active Execution</span>
                                    <span className="text-[10px] font-bold text-[var(--text-color)]">{activeTrade.strike}</span>
                                </div>
                                {/* Row 1: Entry + LTP */}
                                <div className="grid grid-cols-2 gap-3 mb-2">
                                    <div className="text-center">
                                        <p className="text-[8px] text-[var(--text-muted)] uppercase font-bold mb-0.5">Entry</p>
                                        <div className="text-xs font-black text-[var(--text-color)]">
                                            <AnimatedNumber value={parseFloat(activeTrade.entry || 0)} precision={1} />
                                        </div>
                                    </div>
                                    <div className="text-center bg-[var(--apple-blue)]/10 rounded-lg py-1.5">
                                        <p className="text-[8px] text-[var(--apple-blue)] uppercase font-bold mb-0.5 animate-pulse">LTP</p>
                                        <div className="text-xs font-black text-[var(--apple-blue)]">
                                            <AnimatedNumber value={parseFloat(activeTrade.ltp || activeTrade.entry || 0)} precision={1} />
                                        </div>
                                    </div>
                                </div>
                                {/* Row 2: SL + TGT */}
                                <div className="grid grid-cols-2 gap-3">
                                    <div className="text-center">
                                        <p className="text-[8px] text-[var(--apple-red)] uppercase font-bold mb-0.5">Stop Loss</p>
                                        <div className="text-xs font-black text-[var(--apple-red)]">
                                            <AnimatedNumber value={parseFloat(activeTrade.sl || 0)} precision={1} />
                                        </div>
                                    </div>
                                    <div className="text-center">
                                        <p className="text-[8px] text-[var(--apple-green)] uppercase font-bold mb-0.5">Target</p>
                                        <div className="text-xs font-black text-[var(--apple-green)]">
                                            <AnimatedNumber value={parseFloat(activeTrade.target || 0)} precision={1} />
                                        </div>
                                    </div>
                                </div>
                            </div>
                        ) : (
                            /* History Graph - Scaled down to fit thoughts */
                            <div className="h-16 w-full opacity-60 group-hover:opacity-100 transition-opacity">
                                <svg width="100%" height="100%" viewBox="0 0 400 120" preserveAspectRatio="none">
                                    <defs>
                                        <linearGradient id={`gradient-${name}`} x1="0" y1="0" x2="0" y2="1">
                                            <stop offset="0%" stopColor={isPositive ? '#34c759' : '#ff3b30'} stopOpacity="0.3" />
                                            <stop offset="100%" stopColor={isPositive ? '#34c759' : '#ff3b30'} stopOpacity="0" />
                                        </linearGradient>
                                    </defs>
                                    <motion.path
                                        initial={{ pathLength: 0, opacity: 0 }}
                                        animate={{ pathLength: 1, opacity: 1 }}
                                        transition={{ duration: 1.5, ease: "easeOut" }}
                                        d={pathData}
                                        fill="none"
                                        stroke={isPositive ? '#34c759' : '#ff3b30'}
                                        strokeWidth="4"
                                        strokeLinecap="round"
                                    />
                                    <motion.path
                                        initial={{ opacity: 0 }}
                                        animate={{ opacity: 1 }}
                                        transition={{ duration: 1, delay: 0.5 }}
                                        d={`${pathData} L 400 120 L 0 120 Z`}
                                        fill={`url(#gradient-${name})`}
                                    />
                                </svg>
                            </div>
                        )}
                    </div>

                    <div className="flex justify-between items-center text-[var(--text-muted)] text-[10px] font-bold uppercase tracking-widest pt-3 border-t border-[var(--border-color)] px-6 py-4">
                        <span>Win Rate: <span className="text-[var(--text-color)]">{metrics.winRate || '68%'}</span></span>
                        <span>Factor: <span className="text-[var(--text-color)]">{metrics.profitFactor || '1.8'}</span></span>
                    </div>
                </div>

                {/* Back Face: Stats Deep-Dive */}
                <div
                    className="absolute inset-0 backface-hidden apple-bento p-6 flex flex-col justify-between shadow-2xl"
                    style={{
                        transform: 'rotateY(180deg) translateZ(1px)',
                        backgroundColor: 'var(--card-bg)'
                    }}
                >
                    <div className="space-y-4">
                        <div className="flex justify-between items-center mb-2">
                            <h4 className="text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)]">Institutional Stats</h4>
                            <ShieldAlert size={12} className="text-[#007aff]" />
                        </div>
                        <div className="grid grid-cols-2 gap-y-4">
                            <div>
                                <p className="text-[9px] font-bold text-[var(--text-muted)] uppercase tracking-widest mb-0.5">Total Trades</p>
                                <p className="text-lg font-bold text-[var(--text-color)]">{metrics.totalTrades || '0'}</p>
                            </div>
                            <div>
                                <p className="text-[9px] font-bold text-[var(--text-muted)] uppercase tracking-widest mb-0.5">Max Drawdown</p>
                                <p className="text-lg font-bold text-[#ff3b30]">{metrics.maxDrawdown || '0.0%'}</p>
                            </div>
                            <div>
                                <p className="text-[9px] font-bold text-[var(--text-muted)] uppercase tracking-widest mb-0.5">Expectancy</p>
                                <p className="text-lg font-bold text-[var(--text-color)]">{metrics.expectancy || '-'}</p>
                            </div>
                            <div>
                                <p className="text-[9px] font-bold text-[var(--text-muted)] uppercase tracking-widest mb-0.5">Recovery</p>
                                <p className="text-lg font-bold text-[var(--text-color)]">{metrics.recovery || 'Active'}</p>
                            </div>
                        </div>

                        <div className="flex flex-col gap-2 mt-2">
                            <div className="flex gap-2">
                                <button
                                    onClick={(e) => {
                                        e.stopPropagation();
                                        onToggleStatus();
                                    }}
                                    className={`flex-1 py-3 font-black text-[10px] uppercase tracking-widest rounded-xl transition-all flex items-center justify-center gap-2 border ${isPaused
                                        ? 'bg-[var(--apple-green)] text-white border-[var(--apple-green)] hover:opacity-80'
                                        : 'bg-transparent text-[var(--apple-red)] border-[var(--apple-red)]/50 hover:bg-[var(--apple-red)] hover:text-white'
                                        }`}
                                >
                                    {isPaused ? <Play size={12} fill="currentColor" /> : <Pause size={12} fill="currentColor" />}
                                    {isPaused ? 'Continue Bot' : 'Pause Engine'}
                                </button>
                                {/* Spacing div for extraction safety */}
                                <div className="w-1"></div>
                                <button
                                    onClick={(e) => {
                                        e.stopPropagation();
                                        exportStrategyPDF(name, metrics, history);
                                    }}
                                    className="px-4 py-3 bg-[var(--border-color)] text-[var(--text-muted)] border border-[var(--border-color)] font-black text-[10px] uppercase tracking-widest rounded-xl hover:bg-[var(--text-color)] hover:text-[var(--bg-color)] transition-all flex items-center justify-center gap-2"
                                >
                                    PDF
                                </button>
                            </div>
                            <button
                                onClick={(e) => {
                                    e.stopPropagation();
                                    if (onOpenBlueprint) {
                                        onOpenBlueprint({ name, profit, profitPct, status, isPro, history, metrics });
                                    }
                                }}
                                className="w-full py-3 bg-[var(--text-color)] text-[var(--bg-color)] font-black text-[10px] uppercase tracking-widest rounded-xl hover:opacity-80 transition-all flex items-center justify-center gap-2 shadow-lg"
                            >
                                View Detailed Blueprint
                            </button>
                        </div>
                    </div>
                </div>
            </motion.div>
        </div>
    );
};

export default React.memo(StrategyCard);
