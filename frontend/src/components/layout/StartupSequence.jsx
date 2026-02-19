import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Cpu, Globe, Shield, Zap, Activity } from 'lucide-react';

const StartupSequence = ({ onComplete }) => {
    const [progress, setProgress] = useState(0);
    const [status, setStatus] = useState('INITIALIZING MESH NETWORK...');
    const [logs, setLogs] = useState([]);

    const logMessages = [
        { msg: 'ESTABLISHING SECURE BROKER HANDSHAKE...', time: 800, icon: <Shield className="w-3 h-3" /> },
        { msg: 'LOADING NEURAL CORE (GEMINI 1.5 FLASH)...', time: 1500, icon: <Cpu className="w-3 h-3" /> },
        { msg: 'CONFIGURING WEBSOCKET REAL-TIME BRIDGE...', time: 2200, icon: <Globe className="w-3 h-3" /> },
        { msg: 'CALIBRATING BRAIN: CLASSIFYING MARKET REGIMES...', time: 3000, icon: <Activity className="w-3 h-3" /> },
        { msg: 'SYNCING PORTFOLIO STATE...', time: 3800, icon: <Zap className="w-3 h-3" /> },
        { msg: 'READY.', time: 4500, icon: null }
    ];

    useEffect(() => {
        let currentLog = 0;
        const interval = setInterval(() => {
            setProgress(prev => {
                if (prev >= 100) {
                    clearInterval(interval);
                    setTimeout(onComplete, 1000);
                    return 100;
                }
                return prev + 1;
            });
        }, 50);

        logMessages.forEach((item, index) => {
            setTimeout(() => {
                setLogs(prev => [...prev, item]);
                setStatus(item.msg);
            }, item.time);
        });

        return () => clearInterval(interval);
    }, [onComplete]);

    return (
        <motion.div
            initial={{ opacity: 1 }}
            exit={{ opacity: 0, filter: 'blur(20px)' }}
            transition={{ duration: 1.5, ease: "easeInOut" }}
            className="fixed inset-0 z-[9999] bg-[#050505] flex flex-col items-center justify-center font-mono overflow-hidden"
        >
            {/* Ambient Neural Gradients */}
            <div className="absolute inset-0 z-0">
                <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-blue-600/10 rounded-full blur-[120px] animate-pulse" />
                <div className="absolute top-1/4 right-1/4 w-[300px] h-[300px] bg-purple-600/5 rounded-full blur-[100px]" />
            </div>

            <div className="relative z-10 w-full max-w-lg px-8 space-y-12">
                {/* Visual Identity */}
                <div className="text-center space-y-4">
                    <motion.div
                        initial={{ scale: 0.8, opacity: 0 }}
                        animate={{ scale: 1, opacity: 1 }}
                        className="w-20 h-20 mx-auto bg-blue-500/10 rounded-2xl border border-blue-500/20 flex items-center justify-center shadow-[0_0_50px_rgba(59,130,246,0.2)]"
                    >
                        <Activity className="w-10 h-10 text-blue-400" />
                    </motion.div>
                    <div className="space-y-1">
                        <h1 className="text-2xl font-black tracking-tighter text-white">ZEN ALGO CORE</h1>
                        <p className="text-[10px] text-white/30 tracking-[0.4em] font-black uppercase">V2.0.0.1 ALPHA INTEL</p>
                    </div>
                </div>

                {/* Technical Logs */}
                <div className="h-40 bg-white/[0.02] border border-white/5 rounded-2xl p-6 relative overflow-hidden group">
                    <div className="absolute top-0 left-0 w-full h-[1px] bg-gradient-to-r from-transparent via-white/10 to-transparent" />
                    <div className="space-y-3">
                        {logs.map((log, i) => (
                            <motion.div
                                initial={{ opacity: 0, x: -10 }}
                                animate={{ opacity: 1, x: 0 }}
                                key={i}
                                className="flex items-center gap-3 text-[10px] tracking-wider"
                            >
                                <span className="text-white/20">[{new Date().toLocaleTimeString()}]</span>
                                <span className="text-blue-500/50">{log.icon && log.icon}</span>
                                <span className={i === logs.length - 1 ? "text-blue-400 font-bold" : "text-white/40"}>
                                    {log.msg}
                                </span>
                            </motion.div>
                        ))}
                    </div>
                    {/* Scanline Effect */}
                    <div className="absolute inset-0 pointer-events-none bg-scanline opacity-[0.03]" />
                </div>

                {/* Progress Bar */}
                <div className="space-y-3">
                    <div className="flex justify-between items-end">
                        <span className="text-[10px] text-white/40 font-black tracking-widest">{status}</span>
                        <span className="text-lg font-black text-blue-500 italic">{progress}%</span>
                    </div>
                    <div className="h-[4px] w-full bg-white/5 rounded-full overflow-hidden">
                        <motion.div
                            initial={{ width: 0 }}
                            animate={{ width: `${progress}%` }}
                            className="h-full bg-gradient-to-r from-blue-600 to-blue-400 shadow-[0_0_15px_rgba(59,130,246,0.5)]"
                        />
                    </div>
                </div>
            </div>
        </motion.div>
    );
};

export default StartupSequence;
