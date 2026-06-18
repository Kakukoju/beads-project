// src/components/ui/Card.tsx
import React from 'react';

interface CardProps {
  children: React.ReactNode;
  className?: string;
  title?: string;
}

export const Card: React.FC<CardProps> = ({ children, className = "", title }) => (
  <div className={`bg-slate-800/50 backdrop-blur-md border border-slate-700/50 rounded-xl p-5 shadow-lg relative overflow-hidden ${className}`}>
    <div className="absolute -top-10 -right-10 w-32 h-32 bg-blue-500/10 rounded-full blur-3xl pointer-events-none"></div>
    {title && <h3 className="text-slate-300 text-lg font-medium mb-4 flex items-center gap-2">{title}</h3>}
    {children}
  </div>
);

export default Card;