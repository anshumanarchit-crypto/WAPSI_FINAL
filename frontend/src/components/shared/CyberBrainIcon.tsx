import React from 'react';

interface CyberBrainIconProps {
  className?: string;
  size?: number;
}

export const CyberBrainIcon: React.FC<CyberBrainIconProps> = ({ 
  className = 'w-7 h-7', 
  size 
}) => {
  return (
    <svg
      viewBox="0 0 64 64"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      style={size ? { width: size, height: size } : undefined}
    >
      <defs>
        {/* Left Hemisphere Gradient (Cyan to Electric Blue) */}
        <linearGradient id="cyberBrainLeft" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#38BDF8" />
          <stop offset="50%" stopColor="#0284C7" />
          <stop offset="100%" stopColor="#6366F1" />
        </linearGradient>

        {/* Right Hemisphere Gradient (Electric Purple to Vivid Magenta) */}
        <linearGradient id="cyberBrainRight" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#818CF8" />
          <stop offset="50%" stopColor="#A855F7" />
          <stop offset="100%" stopColor="#EC4899" />
        </linearGradient>

        {/* Neon Glow Filter */}
        <filter id="brainGlow" x="-20%" y="-20%" width="140%" height="140%">
          <feGaussianBlur stdDeviation="1.5" result="blur" />
          <feComposite in="SourceGraphic" in2="blur" operator="over" />
        </filter>
      </defs>

      <g filter="url(#brainGlow)">
        {/* Longitudinal Fissure (Center Divider) */}
        <line
          x1="32"
          y1="9"
          x2="32"
          y2="46"
          stroke="#C7D2FE"
          strokeWidth="2.2"
          strokeLinecap="round"
          strokeDasharray="1.5 2"
          opacity="0.85"
        />

        {/* Brain Stem & Cerebellar Stalk at Bottom */}
        <path
          d="M28 47C28 47 26 53 29 57C30.5 59 33.5 59 35 57C38 53 36 47 36 47"
          stroke="url(#cyberBrainLeft)"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <line x1="32" y1="48" x2="32" y2="56" stroke="#C084FC" strokeWidth="2" strokeLinecap="round" />

        {/* LEFT HEMISPHERE (Cyan / Blue Neural Lobes) */}
        <g stroke="url(#cyberBrainLeft)" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
          {/* Outer Contour Left */}
          <path d="M30 10C24 10 18 13 14 18C10 23 9 29 12 34C10 38 12 43 16 45C19 47 24 47 28 46" />
          
          {/* Frontal & Parietal Sulci Left */}
          <path d="M21 16C19 19 22 23 27 22" />
          <path d="M14 26C18 25 22 28 29 27" />
          <path d="M16 35C20 34 23 37 28 35" />
          <path d="M22 41C25 40 28 42 30 43" />

          {/* Neural Synapse Nodes Left */}
          <circle cx="21" cy="16" r="1.3" fill="#38BDF8" />
          <circle cx="27" cy="22" r="1.3" fill="#38BDF8" />
          <circle cx="14" cy="26" r="1.3" fill="#38BDF8" />
          <circle cx="22" cy="35" r="1.3" fill="#38BDF8" />
        </g>

        {/* RIGHT HEMISPHERE (Purple / Magenta Cyber Lobes) */}
        <g stroke="url(#cyberBrainRight)" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
          {/* Outer Contour Right */}
          <path d="M34 10C40 10 46 13 50 18C54 23 55 29 52 34C54 38 52 43 48 45C45 47 40 47 36 46" />
          
          {/* Parietal & Occipital Sulci Right */}
          <path d="M43 16C45 19 42 23 37 22" />
          <path d="M50 26C46 25 42 28 35 27" />
          <path d="M48 35C44 34 41 37 36 35" />
          <path d="M42 41C39 40 36 42 34 43" />

          {/* Neural Synapse Nodes Right */}
          <circle cx="43" cy="16" r="1.3" fill="#F472B6" />
          <circle cx="37" cy="22" r="1.3" fill="#F472B6" />
          <circle cx="50" cy="26" r="1.3" fill="#F472B6" />
          <circle cx="42" cy="35" r="1.3" fill="#F472B6" />
        </g>
      </g>
    </svg>
  );
};
