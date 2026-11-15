'use client';

import React, { createContext, useContext, useEffect, useState, ReactNode } from 'react';

export type Theme = 'obsidian-dark' | 'warm-light';

export interface ThemeContextType {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
  isDark: boolean;
}

const ThemeContext = createContext<ThemeContextType>({
  theme: 'obsidian-dark',
  setTheme: () => {},
  toggleTheme: () => {},
  isDark: true,
});

const STORAGE_KEY = 'sentinel_theme';

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>('obsidian-dark');

  const applyTheme = (targetTheme: Theme) => {
    if (typeof document === 'undefined') return;
    const root = document.documentElement;
    if (targetTheme === 'warm-light') {
      root.classList.remove('dark');
      root.classList.add('light', 'theme-warm');
      root.setAttribute('data-theme', 'warm');
    } else {
      root.classList.remove('light', 'theme-warm');
      root.classList.add('dark');
      root.setAttribute('data-theme', 'obsidian-dark');
    }
  };

  useEffect(() => {
    try {
      const savedTheme = localStorage.getItem(STORAGE_KEY) as Theme | null;
      if (savedTheme === 'obsidian-dark' || savedTheme === 'warm-light') {
        setThemeState(savedTheme);
        applyTheme(savedTheme);
      } else {
        applyTheme('obsidian-dark');
      }
    } catch (_) {
      applyTheme('obsidian-dark');
    }
  }, []);

  const setTheme = (newTheme: Theme) => {
    setThemeState(newTheme);
    applyTheme(newTheme);
    try {
      localStorage.setItem(STORAGE_KEY, newTheme);
    } catch (_) {}
  };

  const toggleTheme = () => {
    const nextTheme: Theme = theme === 'obsidian-dark' ? 'warm-light' : 'obsidian-dark';
    setTheme(nextTheme);
  };

  return (
    <ThemeContext.Provider value={{ theme, setTheme, toggleTheme, isDark: theme === 'obsidian-dark' }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme(): ThemeContextType {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return context;
}
