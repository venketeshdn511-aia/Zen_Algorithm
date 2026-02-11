import React from 'react';
import { motion } from 'framer-motion';
import { API_BASE_URL } from '../../utils/apiConfig';

const AIBrain = () => {
    const [insights, setInsights] = React.useState([]);
    const [isLoading, setIsLoading] = React.useState(true);

    React.useEffect(() => {
        const fetchInsights = async () => {
            try {
                const res = await fetch(`${API_BASE_URL}/api/brain`);
                const data = await res.json();

                if (data.insights && Object.keys(data.insights).length > 0) {
                    const mapped = [];
                    if (data.is_cooling_off) {
                        mapped.push({ title: 'Safety Protocol', desc: `Cooling-off active for ${data.cooling_off_remaining} mins due to volatility.`, status: 'HEDGE' });
                    }

                    Object.entries(data.strategy_adjustments || {}).forEach(([name, adj]) => {
                        if (adj.risk_adjustment > 1.0) {
                            mapped.push({ title: 'Alpha Scaling', desc: `${name} performing well. Increasing allocation by ${Math.round((adj.risk_adjustment - 1) * 100)}%.`, status: 'ACTION' });
                        } else if (adj.stop_hit_ratio > 0.5) {
                            mapped.push({ title: 'Risk Guard', desc: `${name} stop-loss hit rate elevated. Tightening filters.`, status: 'ALERT' });
                        }
                    });

                    if (data.insights.streak_analysis?.is_losing_streak) {
                        mapped.push({ title: 'Drawdown Alert', desc: 'Current cluster of losses detected. System in defensive mode.', status: 'ALERT' });
                    }

                    setInsights(mapped.length > 0 ? mapped : [{ title: 'Scanning Patterns', desc: 'Analyzing live flow for regime shifts. No immediate adjustments needed.', status: 'INFO' }]);
                } else {
                    setInsights([{ title: 'Initial Calibration', desc: 'Intelligence engine is observing market micro-structure. Learning in progress.', status: 'INFO' }]);
                }
            } catch (err) {
                console.error("Brain sync error:", err);
            } finally {
                setIsLoading(false);
            }
        };

        fetchInsights();
        const interval = setInterval(fetchInsights, 60000);
        return () => clearInterval(interval);
    }, []);

    const getStatusColor = (status) => {
        switch (status) {
            case 'ALERT': return 'text-[#ff3b30]';
            case 'ACTION': return 'text-[#007aff]';
            case 'HEDGE': return 'text-[#af52de]';
            default: return 'text-[#34c759]';
        }
    };

    return (
        <div className="space-y-8">
            <div className="flex items-center gap-3">
                <h3 className="text-lg font-bold text-[var(--text-color)] tracking-tight">Intelligence Report</h3>
                <span className="px-2 py-0.5 bg-[var(--border-color)] rounded text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest">{isLoading ? 'Syncing...' : 'Live Flow'}</span>
            </div>

            <div className="space-y-8 min-h-[300px]">
                {insights.map((insight, idx) => (
                    <motion.div
                        key={idx}
                        initial={{ opacity: 0, x: -10 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: idx * 0.1 }}
                        whileHover={{ x: 5 }}
                        className="flex items-start gap-5 group cursor-default"
                    >
                        <div className="mt-1.5 w-2 h-2 rounded-full bg-current shrink-0 animate-pulse" style={{ color: getStatusColor(insight.status).replace('text-', '').replace('[', '').replace(']', '') }} />
                        <div className="space-y-1">
                            <h4 className={`text-[11px] font-black uppercase tracking-widest ${getStatusColor(insight.status)}`}>{insight.title}</h4>
                            <p className="text-[16px] text-[var(--text-color)] opacity-90 font-medium leading-relaxed group-hover:opacity-100 transition-opacity">{insight.desc}</p>
                        </div>
                    </motion.div>
                ))}
            </div>

            <button className="w-full py-4 mt-4 bg-[var(--text-color)] text-[var(--bg-color)] font-bold text-sm rounded-xl hover:opacity-90 transition-all shadow-lg">
                Apply Intelligence Protocol
            </button>
        </div>
    );
};

export default AIBrain;
