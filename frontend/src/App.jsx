import React, { useState, useEffect } from 'react';
import { TopBar, Dock } from './components/layout/Navigation';
import Dashboard from './components/dashboard/Dashboard';
import Strategies from './components/dashboard/Strategies';
import Performance from './components/dashboard/Performance';
import Settings from './components/dashboard/Settings';
import StrategyReport from './components/dashboard/StrategyReport';
import { motion, AnimatePresence } from 'framer-motion';

function App() {
  const [tradingMode, setTradingMode] = useState('PAPER');
  const [activeTab, setActiveTab] = useState('Dashboard');
  const [isDarkMode, setIsDarkMode] = useState(true);
  // Selected strategy for deep-dive report
  const [selectedStrategy, setSelectedStrategy] = useState(null);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', isDarkMode ? 'dark' : 'light');
  }, [isDarkMode]);

  const handleOpenBlueprint = (data) => {
    console.log('App: Opening blueprint for', data.name);
    setSelectedStrategy(data);
  };

  return (
    <div className="min-h-screen w-full bg-[var(--bg-color)] text-[var(--text-color)] flex flex-col selection:bg-[#007aff]/30 transition-colors duration-500">

      {/* Floating Island Navigation */}
      <TopBar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        tradingMode={tradingMode}
        onToggleMode={setTradingMode}
      />

      <main className="flex-1 w-full relative pt-32 pb-20">
        <div className="max-w-[1240px] mx-auto px-6">
          <AnimatePresence mode="wait">
            <motion.div
              key={activeTab + tradingMode}
              initial={{ opacity: 0, scale: 0.98, filter: 'blur(10px)' }}
              animate={{ opacity: 1, scale: 1, filter: 'blur(0px)' }}
              exit={{ opacity: 0, scale: 1.02, filter: 'blur(10px)' }}
              transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
            >
              {activeTab === 'Dashboard' && (
                <Dashboard
                  onOpenBlueprint={handleOpenBlueprint}
                  tradingMode={tradingMode}
                />
              )}
              {activeTab === 'Strategies' && (
                <Strategies
                  onOpenBlueprint={handleOpenBlueprint}
                  tradingMode={tradingMode}
                />
              )}
              {activeTab === 'Performance' && (
                <Performance tradingMode={tradingMode} />
              )}
              {activeTab === 'Settings' && (
                <Settings
                  isDarkMode={isDarkMode}
                  onToggleDarkMode={() => setIsDarkMode(!isDarkMode)}
                />
              )}
              {activeTab === 'Intelligence' && (
                <div className="min-h-[60vh] flex items-center justify-center">
                  <div className="text-center space-y-8">
                    <h2 className="text-[60px] md:text-[120px] font-extrabold tracking-tighter opacity-10">BRAIN</h2>
                    <h3 className="text-4xl font-bold tracking-tight">Intelligence Experience</h3>
                    <p className="text-[var(--text-muted)] text-xl max-w-lg mx-auto font-medium">
                      The neural core is currently optimizing for the next market session. Expanded insights coming shortly.
                    </p>
                  </div>
                </div>
              )}
              {!['Dashboard', 'Strategies', 'Performance', 'Settings', 'Intelligence'].includes(activeTab) && (
                <div className="min-h-[60vh] flex items-center justify-center">
                  <div className="text-center space-y-8">
                    <h2 className="text-[60px] md:text-[120px] font-extrabold tracking-tighter opacity-10">COMING</h2>
                    <h3 className="text-4xl font-bold tracking-tight">{activeTab} Experience</h3>
                  </div>
                </div>
              )}
            </motion.div>
          </AnimatePresence>
        </div>
      </main>

      {/* macOS style Dock */}
      <Dock activeTab={activeTab} setActiveTab={setActiveTab} />

      {/* Deep-Dive Project Blueprint */}
      <StrategyReport
        isOpen={!!selectedStrategy}
        onClose={() => setSelectedStrategy(null)}
        strategyData={selectedStrategy}
      />

      {/* Ambient Backdrop Logic */}
      <motion.div
        animate={{
          opacity: tradingMode === 'REAL' ? 0.4 : 0,
          background: 'radial-gradient(circle at 50% 0%, #007aff20, transparent 70%)'
        }}
        className="fixed inset-0 pointer-events-none z-[-1]"
      />

    </div>
  );
}

export default App;
