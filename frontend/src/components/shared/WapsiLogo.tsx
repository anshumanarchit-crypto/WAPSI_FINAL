import React from 'react';

interface WapsiLogoProps {
  size?: number;
  className?: string;
}

export const WapsiLogo: React.FC<WapsiLogoProps> = ({ size = 32, className = '' }) => {
  return (
    <div 
      className={`relative flex items-center justify-center shrink-0 ${className}`}
      style={{ width: size, height: size }}
    >
      {/* Ambient purple/indigo glow */}
      <div 
        className="absolute inset-0 rounded-xl bg-indigo-600/30 blur-md"
      />
      
      {/* Gradient Logo Container */}
      <div 
        className="relative w-full h-full rounded-xl bg-gradient-to-tr from-indigo-900 via-indigo-600 to-purple-500 border border-indigo-400/40 flex items-center justify-center shadow-lg shadow-indigo-500/30 overflow-hidden"
      >
        {/* Constellation Nodes as in user image */}
        <svg 
          viewBox="0 0 32 32" 
          fill="none" 
          xmlns="http://www.w3.org/2000/svg"
          className="w-5/6 h-5/6"
        >
          {/* Subtle connection glow */}
          <circle cx="16" cy="16" r="7" stroke="rgba(255, 255, 255, 0.15)" strokeWidth="1" strokeDasharray="2 2" />
          
          {/* Central elongated pill */}
          <rect x="14" y="11" width="4" height="10" rx="2" fill="white" />
          
          {/* Top node */}
          <circle cx="16" cy="6" r="2.2" fill="#E0E7FF" />
          
          {/* Bottom node */}
          <circle cx="16" cy="26" r="2.2" fill="#E0E7FF" />
          
          {/* Left node */}
          <circle cx="7" cy="16" r="2.2" fill="#E0E7FF" />
          
          {/* Right node */}
          <circle cx="25" cy="16" r="2.2" fill="#E0E7FF" />
        </svg>
      </div>
    </div>
  );
};
