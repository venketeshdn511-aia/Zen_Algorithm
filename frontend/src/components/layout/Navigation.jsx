import React, { useState, useEffect } from 'react';
import { LayoutDashboard, Settings, PieChart, Activity, Zap, ShieldCheck, Search } from 'lucide-react';
import { motion } from 'framer-motion';


import { API_BASE_URL } from '../../utils/apiConfig';

export const TopBar = ({ tradingMode, onToggleMode, activeTab, setActiveTab }) => {
    const [isConnected, setIsConnected] = useState(false);

    useEffect(() => {
        const checkConnection = async () => {
            try {
                const res = await fetch(`${API_BASE_URL}/debug`);
                if (res.ok) setIsConnected(true);
                else setIsConnected(false);
            } catch (e) {
                setIsConnected(false);
            }
        };
        checkConnection();
        const interval = setInterval(checkConnection, 5000);
        return () => clearInterval(interval);
    }, []);
    const navItems = [
        { label: 'Overview', id: 'Dashboard' },
        { label: 'Strategies', id: 'Strategies' },
        { label: 'Performance', id: 'Performance' },
        { label: 'Intelligence', id: 'Intelligence' },
        { label: 'System', id: 'Settings' }
    ];

    return (
        <nav className="fixed top-2 md:top-6 left-0 right-0 z-50 px-2 md:px-6">
            <div className="max-w-[1200px] mx-auto glass-island h-12 md:h-14 flex items-center justify-between px-4 md:px-6">
                <div className="flex items-center gap-8">
                    <div onClick={() => setActiveTab('Dashboard')} className="flex items-center gap-2 group cursor-pointer">
                        <Zap className="text-[var(--text-color)] fill-[var(--text-color)] group-hover:scale-110 transition-transform" size={20} />
                        <span className="text-[17px] font-bold tracking-tight text-[var(--text-color)]">AlgoBot Pro</span>
                    </div>

                    <div className="hidden md:block h-4 w-[1px] bg-[var(--border-color)]" />

                    <div className="hidden md:flex gap-6 text-[13px] font-medium text-[var(--text-muted)]">
                        {navItems.map(item => (
                            <button
                                key={item.id}
                                onClick={() => setActiveTab(item.id)}
                                className={`hover:text-[var(--text-color)] transition-colors ${activeTab === item.id ? 'text-[var(--text-color)]' : ''}`}
                            >
                                {item.label}
                            </button>
                        ))}
                    </div>
                </div>



                <div className="flex items-center gap-4">
                    {/* Connection Status for TestSprite */}
                    <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full border ${isConnected ? 'bg-[#34c759]/10 border-[#34c759]/20' : 'bg-[#ff3b30]/10 border-[#ff3b30]/20'}`}>
                        <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-[#34c759] animate-pulse' : 'bg-[#ff3b30]'}`} />
                        <span className={`text-[10px] font-bold uppercase tracking-wider ${isConnected ? 'text-[#34c759]' : 'text-[#ff3b30]'}`}>
                            {isConnected ? 'Connected' : 'Disconnected'}
                        </span>
                    </div>
                    {/* Mode Switcher */}
                    <div className="flex bg-[var(--bg-color)] p-1 rounded-xl border border-[var(--border-color)] overflow-hidden">
                        <button
                            onClick={() => onToggleMode('PAPER')}
                            className={`px-4 py-1.5 rounded-lg text-[11px] font-black transition-all ${tradingMode === 'PAPER' ? 'bg-[var(--text-color)] text-[var(--bg-color)] shadow-sm' : 'text-[var(--text-muted)] hover:text-[var(--text-color)]'
                                }`}
                        >
                            PAPER
                        </button>
                        <button
                            onClick={() => onToggleMode('REAL')}
                            className={`px-4 py-1.5 rounded-lg text-[11px] font-black transition-all ${tradingMode === 'REAL' ? 'bg-[#007aff] text-white shadow-sm' : 'text-[var(--text-muted)] hover:text-[var(--text-color)]'
                                }`}
                        >
                            LIVE
                        </button>
                    </div>

                    <button className="hidden md:block text-[var(--text-muted)] hover:text-[var(--text-color)] transition-colors"><Search size={18} /></button>
                    <div className="w-6 h-6 md:w-8 md:h-8 rounded-full bg-gradient-to-br from-gray-700 to-gray-900 border border-[var(--border-color)] flex items-center justify-center text-[8px] md:text-[10px] font-bold text-white uppercase tracking-tighter">V</div>
                </div>
            </div>
        </nav >
    );
};

export const Dock = ({ activeTab, setActiveTab }) => {
    const items = [
        { id: 'Dashboard', icon: <LayoutDashboard size={22} />, label: 'Home' },
        { id: 'Strategies', icon: <PieChart size={22} />, label: 'Strategies' },
        { id: 'Performance', icon: <Activity size={22} />, label: 'Performance' },
        { id: 'Intelligence', icon: <Zap size={22} />, label: 'Brain' },
        { id: 'Settings', icon: <Settings size={22} />, label: 'Settings' },
    ];

    return (
        <div className="fixed bottom-4 md:bottom-10 left-0 right-0 z-50 flex justify-center px-4 pointer-events-none">
            <div className="glass-island h-16 md:h-20 px-2 md:px-4 flex items-center gap-1 md:gap-2 pointer-events-auto shadow-2xl">
                {items.map((item) => (
                    <motion.button
                        key={item.id}
                        whileHover={{ scale: 1.2, y: -10 }}
                        whileTap={{ scale: 0.9 }}
                        onClick={() => setActiveTab(item.id)}
                        className={`w-10 h-10 md:w-14 md:h-14 rounded-xl md:rounded-2xl flex flex-col items-center justify-center transition-all relative ${activeTab === item.id ? 'bg-[var(--text-color)] text-[var(--bg-color)] shadow-xl' : 'text-[var(--text-muted)] hover:text-[var(--text-color)]'
                            }`}
                    >
                        {item.icon}
                        {activeTab === item.id && (
                            <motion.div layoutId="dock-dot" className="absolute -bottom-2 w-1.5 h-1.5 bg-[var(--text-color)] rounded-full" />
                        )}
                    </motion.button>
                ))}
                <div className="hidden md:block w-[1px] h-10 bg-[var(--border-color)] mx-2" />
                <motion.button
                    whileHover={{ scale: 1.2, y: -10 }}
                    className="w-10 h-10 md:w-14 md:h-14 rounded-xl md:rounded-2xl bg-[#34c759]/10 text-[#34c759] flex items-center justify-center border border-[#34c759]/20"
                >
                    <ShieldCheck size={20} className="md:size-[26px]" />
                </motion.button>
            </div>
        </div>
    );
};
