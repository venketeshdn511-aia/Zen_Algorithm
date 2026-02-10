import React from 'react';
import { LayoutDashboard, Settings, PieChart, Activity, Zap, ShieldCheck } from 'lucide-react';

const Sidebar = ({ activeTab, setActiveTab }) => {
    const menuItems = [
        { icon: <LayoutDashboard size={18} />, label: 'Dashboard' },
        { icon: <PieChart size={18} />, label: 'Strategies' },
        { icon: <Activity size={18} />, label: 'Market Regime' },
        { icon: <ShieldCheck size={18} />, label: 'Risk Metrics' },
        { icon: <Settings size={18} />, label: 'Settings' },
    ];

    return (
        <aside className="w-[260px] h-screen border-r border-white/[0.05] flex flex-col fixed left-0 top-0 z-50 bg-black">
            <div className="p-8 pb-12 flex items-center gap-3">
                <div className="w-8 h-8 bg-white rounded-lg flex items-center justify-center">
                    <Zap className="text-black fill-black" size={18} />
                </div>
                <span className="text-lg font-semibold tracking-tight text-white">
                    AlgoBot
                </span>
            </div>

            <nav className="flex-1 px-4 space-y-1">
                {menuItems.map((item, index) => (
                    <button
                        key={index}
                        onClick={() => setActiveTab(item.label)}
                        className={`w-full flex items-center gap-3 px-4 py-2.5 rounded-lg transition-all duration-200 ${activeTab === item.label
                                ? 'bg-white/[0.08] text-white shadow-sm'
                                : 'text-[#86868b] hover:text-white'
                            }`}
                    >
                        {item.icon}
                        <span className="text-[14px] font-medium tracking-tight">{item.label}</span>
                    </button>
                ))}
            </nav>

            <div className="p-6">
                <div className="bg-[#1c1c1e] rounded-2xl p-5 border border-white/[0.05]">
                    <p className="text-[11px] text-[#86868b] font-semibold mb-2 uppercase tracking-wide">System Status</p>
                    <div className="flex items-center gap-2">
                        <div className="w-1.5 h-1.5 rounded-full bg-[#34c759]" />
                        <span className="text-xs text-white font-medium">Connected</span>
                    </div>
                </div>
            </div>
        </aside>
    );
};

export default Sidebar;
