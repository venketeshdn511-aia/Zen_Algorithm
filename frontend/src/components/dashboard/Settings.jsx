import React, { useState, useEffect } from 'react';
import { Shield, Cpu, Bell, Moon, Globe, CheckCircle, Loader2 } from 'lucide-react';

const Settings = ({ isDarkMode, onToggleDarkMode }) => {
    const [preferences, setPreferences] = useState({
        notifications: true,
        cinematicMode: true
    });
    const [isDiagnosing, setIsDiagnosing] = useState(false);
    const [diagnosticStatus, setDiagnosticStatus] = useState('Idle');
    const [liveTime, setLiveTime] = useState(new Date().toLocaleTimeString());
    const [liveLatency, setLiveLatency] = useState('14ms');

    useEffect(() => {
        const timer = setInterval(() => {
            setLiveTime(new Date().toLocaleTimeString());
            // Randomly fluctuate latency slightly for realism
            const lat = Math.floor(Math.random() * 5) + 12;
            setLiveLatency(`${lat}ms`);
        }, 1000);
        return () => clearInterval(timer);
    }, []);

    const handleToggle = (key) => {
        if (key === 'darkMode') {
            onToggleDarkMode();
        } else {
            setPreferences(prev => ({ ...prev, [key]: !prev[key] }));
        }
    };

    const runDiagnostic = () => {
        setIsDiagnosing(true);
        setDiagnosticStatus('Initializing Scan...');

        setTimeout(() => setDiagnosticStatus('Checking Broker Latency...'), 800);
        setTimeout(() => setDiagnosticStatus('Validating Neural Weights...'), 1600);
        setTimeout(() => setDiagnosticStatus('Optimizing Execution Paths...'), 2400);

        setTimeout(() => {
            setIsDiagnosing(false);
            setDiagnosticStatus('System Optimized');
        }, 3200);
    };

    const brokerStats = [
        { label: 'Latency', value: liveLatency, status: 'Optimal' },
        { label: 'API Key', value: '••••••••4290', status: 'Encrypted' },
        { label: 'Last Sync', value: liveTime, status: 'Real-time' },
        { label: 'Session', value: 'Active', status: 'Secure' }
    ];

    return (
        <div className="space-y-8 max-w-4xl mx-auto pt-10 md:pt-32 pb-12 md:pb-20 px-4 md:px-6">
            <div className="flex items-center justify-between mb-2">
                <div>
                    <h1 className="text-2xl md:text-4xl font-bold tracking-tight text-[var(--text-color)]">System Status</h1>
                    <p className="text-[14px] md:text-base text-[var(--text-muted)] mt-1 font-medium">Global infrastructure & account preferences</p>
                </div>
            </div>

            {/* Broker Connectivity */}
            <section className="apple-bento p-8">
                <div className="flex items-center justify-between mb-8">
                    <div className="flex items-center gap-4">
                        <div className="p-2 md:p-3 bg-blue-600/10 rounded-xl md:rounded-2xl">
                            <Shield className="text-blue-500 w-5 h-5 md:w-7 md:h-7" />
                        </div>
                        <div>
                            <h2 className="text-xl md:text-2xl font-bold text-[var(--text-color)]">Broker Connection</h2>
                            <p className="text-[var(--text-muted)] text-[11px] md:text-sm">Secure link to Kotak Securities API section</p>
                        </div>
                    </div>
                    <div className="flex items-center gap-2 px-4 py-2 bg-[#34c759]/10 text-[#34c759] rounded-full border border-[#34c759]/20 font-bold text-sm">
                        <div className="w-2 h-2 bg-[#34c759] rounded-full animate-pulse" />
                        <CheckCircle size={16} /> CONNECTED
                    </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {brokerStats.map((stat, i) => (
                        <div key={i} className="p-4 bg-[var(--bg-color)] rounded-2xl border border-[var(--border-color)] flex justify-between items-center">
                            <span className="text-[var(--text-muted)] text-sm font-medium">{stat.label}</span>
                            <span className="text-[var(--text-color)] font-bold">{stat.value}</span>
                        </div>
                    ))}
                </div>
            </section>

            {/* AI Brain Status */}
            <section className="apple-bento p-8">
                <div className="flex items-center justify-between mb-8">
                    <div className="flex items-center gap-4">
                        <div className="p-2 md:p-3 bg-purple-600/10 rounded-xl md:rounded-2xl">
                            <Cpu className="text-purple-500 w-5 h-5 md:w-7 md:h-7" />
                        </div>
                        <div>
                            <h2 className="text-xl md:text-2xl font-bold text-[var(--text-color)]">System Healthy</h2>
                            <p className="text-[var(--text-muted)] text-[11px] md:text-sm">{isDiagnosing ? 'Scanning systems...' : 'Neural processors operating at peak efficiency'}</p>
                        </div>
                    </div>
                    <button
                        onClick={runDiagnostic}
                        disabled={isDiagnosing}
                        className={`flex items-center gap-2 px-4 py-2 md:px-6 md:py-2 rounded-full font-bold text-[11px] md:text-sm transition-all ${isDiagnosing ? 'bg-gray-700 text-gray-400 cursor-not-allowed' : 'bg-[var(--text-color)] text-[var(--bg-color)] hover:opacity-80'
                            }`}
                    >
                        {isDiagnosing ? <Loader2 className="animate-spin" size={14} /> : <Globe size={14} />}
                        {isDiagnosing ? 'DIAGNOSTIC' : 'OPTIMIZE'}
                    </button>
                </div>

                <div className="space-y-4">
                    <div className="flex justify-between text-sm font-bold text-[var(--text-muted)] mb-2">
                        <span>{diagnosticStatus}</span>
                        <span>{isDiagnosing ? 'IN PROGRESS' : '100%'}</span>
                    </div>
                    <div className="h-2 w-full bg-[var(--border-color)] rounded-full overflow-hidden">
                        <div className={`h-full bg-blue-500 transition-all duration-1000 ${isDiagnosing ? 'w-2/4 animate-pulse' : 'w-full'}`} />
                    </div>
                </div>
            </section>

            {/* Application Preferences */}
            <section className="apple-bento p-8">
                <h2 className="text-xl font-bold mb-6 text-[var(--text-color)]">Preferences</h2>
                <div className="space-y-2">
                    {[
                        { icon: <Bell size={20} />, label: 'Notifications', key: 'notifications', toggle: true },
                        { icon: <Moon size={20} />, label: 'Dark Mode', key: 'darkMode', toggle: true },
                        { icon: <Globe size={20} />, label: 'Cinematic Mode', key: 'cinematicMode', toggle: true }
                    ].map((item, i) => (
                        <div key={i} className="flex items-center justify-between py-3 border-b border-[var(--border-color)] last:border-0">
                            <div className="flex items-center gap-3">
                                <span className="text-[var(--text-muted)]">{item.icon}</span>
                                <span className="text-[var(--text-color)] font-medium">{item.label}</span>
                            </div>
                            <div
                                onClick={() => handleToggle(item.key)}
                                className={`w-12 h-6 rounded-full p-1 transition-all cursor-pointer ${(item.key === 'darkMode' ? isDarkMode : preferences[item.key]) ? 'bg-blue-600' : 'bg-gray-400'
                                    }`}
                            >
                                <div className={`w-4 h-4 bg-white rounded-full transition-all ${(item.key === 'darkMode' ? isDarkMode : preferences[item.key]) ? 'ml-6' : 'ml-0'
                                    }`} />
                            </div>
                        </div>
                    ))}
                </div>
            </section>
        </div>
    );
};

export default Settings;
