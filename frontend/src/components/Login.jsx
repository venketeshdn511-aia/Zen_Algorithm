import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Lock, User, Key, ShieldCheck, ArrowRight } from 'lucide-react';

const Login = ({ onLogin }) => {
    const [mode, setMode] = useState('LOGIN'); // LOGIN | RESET
    const [formData, setFormData] = useState({
        username: '',
        password: '',
        panAnswer: '',
        newPassword: ''
    });
    const [error, setError] = useState('');
    const [success, setSuccess] = useState('');

    // Credentials (Hardcoded as per request)
    const CREDENTIALS = {
        USER: 'DACCHU VINAY',
        PASS: 'DACCHUVINAY8310268127',
        PAN_ANSWER: 'COWPV8951F'
    };

    const handleInput = (e) => {
        const { name, value } = e.target;
        setFormData(prev => ({
            ...prev,
            [name]: value.toUpperCase() // Force Uppercase
        }));
        setError('');
    };

    const handleSubmit = (e) => {
        e.preventDefault();
        setError('');
        setSuccess('');

        if (mode === 'LOGIN') {
            if (formData.username === CREDENTIALS.USER && formData.password === CREDENTIALS.PASS) {
                onLogin();
            } else {
                setError('INVALID CREDENTIALS. ACCESS DENIED.');
            }
        } else {
            // Reset Mode
            if (formData.panAnswer === CREDENTIALS.PAN_ANSWER) {
                setSuccess('IDENTITY VERIFIED. PASSWORD RESET SIMULATED.');
                setTimeout(() => {
                    setMode('LOGIN');
                    setSuccess('');
                    setFormData(prev => ({ ...prev, password: '', panAnswer: '' }));
                }, 2000);
            } else {
                setError('IDENTITY VERIFICATION FAILED.');
            }
        }
    };

    return (
        <div className="min-h-screen w-full flex items-center justify-center bg-[#050505] overflow-hidden relative">
            {/* Premium Neural Background */}
            <div className="absolute inset-0 z-0 pointer-events-none">
                <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_50%,#007aff10,transparent_70%)]" />
                <motion.div
                    animate={{
                        opacity: [0.2, 0.4, 0.2],
                        scale: [1, 1.1, 1]
                    }}
                    transition={{ duration: 10, repeat: Infinity, ease: "easeInOut" }}
                    className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-blue-600/5 rounded-full blur-[120px]"
                />
                <motion.div
                    animate={{
                        opacity: [0.1, 0.3, 0.1],
                        scale: [1, 1.2, 1]
                    }}
                    transition={{ duration: 15, repeat: Infinity, ease: "easeInOut", delay: 2 }}
                    className="absolute bottom-[-10%] right-[-10%] w-[50%] h-[50%] bg-purple-600/5 rounded-full blur-[150px]"
                />

                {/* Animated Grid/Dots Pattern */}
                <div className="absolute inset-0 opacity-10"
                    style={{ backgroundImage: 'radial-gradient(#ffffff20 1px, transparent 1px)', backgroundSize: '40px 40px' }} />
            </div>

            <motion.div
                initial={{ opacity: 0, y: 40, filter: 'blur(10px)' }}
                animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
                transition={{ duration: 1, ease: [0.16, 1, 0.3, 1] }}
                className="w-full max-w-md p-10 bg-white/[0.02] border border-white/10 rounded-[40px] shadow-2xl relative z-10 backdrop-blur-3xl overflow-hidden"
            >
                {/* Visual Accent */}
                <div className="absolute top-0 left-0 w-full h-[2px] bg-gradient-to-r from-transparent via-blue-500/50 to-transparent" />

                <div className="relative z-10">
                    <div className="text-center mb-10">
                        <motion.div
                            initial={{ scale: 0.5, opacity: 0 }}
                            animate={{ scale: 1, opacity: 1 }}
                            transition={{ delay: 0.2, duration: 0.8 }}
                            className="mx-auto w-20 h-20 bg-blue-500/10 rounded-3xl flex items-center justify-center mb-6 border border-blue-500/20 rotate-12"
                        >
                            <ShieldCheck className="w-10 h-10 text-blue-400 -rotate-12" />
                        </motion.div>
                        <h2 className="text-3xl font-bold tracking-tighter text-white mb-2">
                            {mode === 'LOGIN' ? 'AUTHENTICATION' : 'RECOVERY'}
                        </h2>
                        <p className="text-white/40 text-xs tracking-[0.2em] font-black uppercase">
                            {mode === 'LOGIN' ? 'AUTHORIZED ACCESS ONLY' : 'IDENTITY VERIFICATION'}
                        </p>
                    </div>

                    <form onSubmit={handleSubmit} className="space-y-6">
                        <AnimatePresence mode="wait">
                            {mode === 'LOGIN' ? (
                                <motion.div
                                    key="login-fields"
                                    initial={{ opacity: 0, x: -20 }}
                                    animate={{ opacity: 1, x: 0 }}
                                    exit={{ opacity: 0, x: 20 }}
                                    className="space-y-4"
                                >
                                    <div className="space-y-2">
                                        <label className="text-[10px] uppercase tracking-[0.2em] text-white/30 font-black ml-1">Terminal Identity</label>
                                        <div className="relative">
                                            <User className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-white/20" />
                                            <input
                                                type="text"
                                                name="username"
                                                value={formData.username}
                                                onChange={handleInput}
                                                className="w-full bg-white/5 border border-white/10 rounded-2xl py-4 pl-12 pr-4 text-white placeholder-white/10 focus:outline-none focus:border-blue-500/50 focus:bg-white/10 transition-all font-mono text-sm"
                                                placeholder="UID-XXXX-XXXX"
                                                autoComplete="off"
                                                required
                                            />
                                        </div>
                                    </div>
                                    <div className="space-y-2">
                                        <label className="text-[10px] uppercase tracking-[0.2em] text-white/30 font-black ml-1">Access Protocol</label>
                                        <div className="relative">
                                            <Lock className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-white/20" />
                                            <input
                                                type="password"
                                                name="password"
                                                value={formData.password}
                                                onChange={handleInput}
                                                className="w-full bg-white/5 border border-white/10 rounded-2xl py-4 pl-12 pr-4 text-white placeholder-white/10 focus:outline-none focus:border-blue-500/50 focus:bg-white/10 transition-all font-mono text-sm"
                                                placeholder="••••••••••••"
                                                required
                                            />
                                        </div>
                                    </div>
                                </motion.div>
                            ) : (
                                <motion.div
                                    key="reset-fields"
                                    initial={{ opacity: 0, x: 20 }}
                                    animate={{ opacity: 1, x: 0 }}
                                    exit={{ opacity: 0, x: -20 }}
                                    className="space-y-6"
                                >
                                    <div className="space-y-2">
                                        <label className="text-[10px] uppercase tracking-[0.2em] text-white/30 font-black ml-1">Security Question</label>
                                        <div className="p-4 bg-blue-500/5 border border-blue-500/20 rounded-2xl text-white/60 text-sm font-medium">
                                            "Verify your Permanent Account Number"
                                        </div>
                                    </div>
                                    <div className="space-y-2">
                                        <label className="text-[10px] uppercase tracking-[0.2em] text-white/30 font-black ml-1">Verification Token</label>
                                        <div className="relative">
                                            <Key className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-white/20" />
                                            <input
                                                type="text"
                                                name="panAnswer"
                                                value={formData.panAnswer}
                                                onChange={handleInput}
                                                className="w-full bg-white/5 border border-white/10 rounded-2xl py-4 pl-12 pr-4 text-white placeholder-white/10 focus:outline-none focus:border-blue-500/50 focus:bg-white/10 transition-all font-mono text-sm"
                                                placeholder="ENTER PAN VALUE"
                                                autoComplete="off"
                                                required
                                            />
                                        </div>
                                    </div>
                                </motion.div>
                            )}
                        </AnimatePresence>

                        {error && (
                            <motion.div
                                initial={{ opacity: 0, scale: 0.95 }}
                                animate={{ opacity: 1, scale: 1 }}
                                className="text-red-400 text-[10px] font-black tracking-widest text-center bg-red-500/10 p-4 rounded-2xl border border-red-500/20 uppercase"
                            >
                                {error}
                            </motion.div>
                        )}

                        {success && (
                            <motion.div
                                initial={{ opacity: 0, scale: 0.95 }}
                                animate={{ opacity: 1, scale: 1 }}
                                className="text-emerald-400 text-[10px] font-black tracking-widest text-center bg-emerald-500/10 p-4 rounded-2xl border border-emerald-500/20 uppercase"
                            >
                                {success}
                            </motion.div>
                        )}

                        <button
                            type="submit"
                            className="w-full py-5 bg-blue-600 hover:bg-blue-500 text-white rounded-2xl font-black text-xs tracking-[0.3em] transition-all shadow-[0_20px_40px_rgba(37,99,235,0.2)] hover:shadow-[0_25px_50px_rgba(37,99,235,0.3)] hover:-translate-y-1 active:scale-[0.98] flex items-center justify-center gap-3"
                        >
                            {mode === 'LOGIN' ? 'INITIALIZE SESSION' : 'EXECUTE VERIFICATION'}
                            <ArrowRight className="w-4 h-4" />
                        </button>
                    </form>

                    <div className="mt-8 text-center">
                        <button
                            onClick={() => {
                                setMode(mode === 'LOGIN' ? 'RESET' : 'LOGIN');
                                setError('');
                                setSuccess('');
                            }}
                            className="text-[10px] text-white/20 hover:text-white/50 transition-colors uppercase tracking-[0.2em] font-black"
                        >
                            {mode === 'LOGIN' ? 'Forgot Passkey?' : 'Return to Terminal'}
                        </button>
                    </div>
                </div>
            </motion.div>
        </div>
    );
};

export default Login;
