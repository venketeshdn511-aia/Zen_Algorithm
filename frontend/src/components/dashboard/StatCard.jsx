import React from 'react';
import AnimatedNumber from '../common/AnimatedNumber';

const StatCard = ({ label, value, subValue, trend, trendValue }) => {
    // Parse numeric value from string like "₹1,24,000"
    const numericValue = typeof value === 'string'
        ? parseFloat(value.replace(/[^0-9.-]+/g, ""))
        : value;

    const isCurrency = typeof value === 'string' && value.includes('₹');

    return (
        <div className="apple-bento p-10 group">
            <p className="text-[14px] font-bold text-[#86868b] mb-2 uppercase tracking-widest">{label}</p>
            <h3 className="text-[44px] font-extrabold text-white leading-tight tracking-tighter mb-2">
                <AnimatedNumber
                    value={numericValue}
                    prefix={isCurrency ? '₹' : ''}
                    precision={isCurrency ? 0 : 2}
                />
            </h3>
            <div className="flex items-center gap-3">
                {trend && (
                    <span className={`text-[15px] font-black ${trend === 'up' ? 'text-[#34c759]' : 'text-[#ff453a]'}`}>
                        {trend === 'up' ? '↗' : '↘'} {trendValue}
                    </span>
                )}
                {subValue && <span className="text-[15px] font-bold text-[#86868b]">{subValue}</span>}
            </div>
        </div>
    );
};

export default StatCard;
