import React from 'react';
import { Search, Bell, Wifi } from 'lucide-react';

const Navbar = ({ tradingMode, onToggleMode }) => {
    return (
        <header className="h-16 fixed top-0 right-0 left-[260px] z-40 px-8 flex items-center justify-between bg-black/80 backdrop-blur-md border-b border-white/[0.05]">
            <div className="flex items-center gap-6">
                {/* Paper/Real Toggle - Apple Style */}
                <div className="bg-[#1c1c1e] p-[3px] rounded-lg flex items-center border border-white/[0.05]">
                    <button
                        onClick={() => onToggleMode('PAPER')}
                        className={`px-4 py-1.5 rounded-md text-[11px] font-bold transition-all ${tradingMode === 'PAPER'
                                ? 'bg-[#3a3a3c] text-white'
                                : 'text-[#86868b] hover:text-white'
                            }`}
                    >
                        PAPER
                    </button>
                    <button
                        onClick={() => onToggleMode('REAL')}
                        className={`px-4 py-1.5 rounded-md text-[11px] font-bold transition-all ${tradingMode === 'REAL'
                                ? 'bg-[#007aff] text-white'
                                : 'text-[#86868b] hover:text-white'
                            }`}
                    >
                        LIVE
                    </button>
                </div>

                <div className="w-[1px] h-4 bg-white/[0.05]" />

                <div className="flex items-center gap-2">
                    <Wifi size={14} className="text-[#34c759]" />
                    <span className="text-[11px] font-bold text-[#34c759] uppercase tracking-wider">110ms</span>
                </div>
            </div>

            <div className="flex items-center gap-6">
                <div className="relative">
                    <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#86868b]" />
                    <input
                        type="text"
                        placeholder="Search"
                        className="bg-[#1c1c1e] border border-white/[0.05] rounded-lg py-1.5 pl-9 pr-4 text-xs text-white focus:outline-none focus:border-[#007aff]/50 w-48 transition-all"
                    />
                </div>

                <div className="flex items-center gap-4">
                    <button className="text-[#86868b] hover:text-white transition-colors">
                        <Bell size={18} />
                    </button>
                    <div className="w-8 h-8 bg-[#1c1c1e] rounded-full flex items-center justify-center text-xs font-bold text-white border border-white/[0.1] cursor-pointer hover:bg-[#2c2c2e] transition-all">
                        V
                    </div>
                </div>
            </div>
        </header>
    );
};

export default Navbar;
