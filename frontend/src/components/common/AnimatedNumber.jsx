import React, { useEffect, useRef } from 'react';
import { motion, useMotionValue, useSpring, useTransform, animate } from 'framer-motion';

const AnimatedNumber = ({ value, precision = 0, prefix = '', suffix = '' }) => {
    const motionValue = useMotionValue(0);
    const springValue = useSpring(motionValue, {
        stiffness: 100,
        damping: 30,
        restDelta: 0.001
    });

    const displayValue = useTransform(springValue, (latest) => {
        const formatted = latest.toFixed(precision);
        // Add commas for thousands
        return formatted.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
    });

    useEffect(() => {
        motionValue.set(value);
    }, [value, motionValue]);

    return (
        <span>
            {prefix}
            <motion.span>{displayValue}</motion.span>
            {suffix}
        </span>
    );
};

export default AnimatedNumber;
