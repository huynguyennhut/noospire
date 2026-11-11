/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        nf: {
          950: '#09090B',
          900: '#0C0C0E',
          850: '#111113',
          800: '#18181B',
          700: '#27272A',
          600: '#3F3F46',
          500: '#71717A',
          400: '#A1A1AA',
          300: '#D4D4D8',
          200: '#E4E4E7',
          100: '#F4F4F5',
          50:  '#FAFAFA',
        },
        // Mapped to monochrome obsidian/white to preserve 100% compatibility across legacy components
        cyber: {
          950: '#09090B',
          900: '#0C0C0E',
          850: '#111113',
          800: '#18181B',
          700: '#27272A',
          600: '#3F3F46',
          500: '#FFFFFF',
          400: '#FAFAFA',
          300: '#F4F4F5',
        },
        // Mapped to pure white & neutral glass accents to enforce Black/White design system
        cyan: {
          50:  '#FAFAFA',
          100: '#F4F4F5',
          200: '#E4E4E7',
          300: '#D4D4D8',
          400: '#FFFFFF',
          500: '#FAFAFA',
          600: '#E4E4E7',
          700: '#71717A',
          800: '#27272A',
          900: '#18181B',
          950: '#111113',
        },
        glass: {
          surface:        'rgba(255, 255, 255, 0.03)',
          'surface-hover': 'rgba(255, 255, 255, 0.06)',
          elevated:       'rgba(12, 12, 14, 0.80)',
          border:         'rgba(255, 255, 255, 0.06)',
          'border-hover': 'rgba(255, 255, 255, 0.12)',
          specular:       'rgba(255, 255, 255, 0.08)',
        },
        severity: {
          critical: '#F43F5E',
          high:     '#F97316',
          medium:   '#F59E0B',
          low:      '#10B981',
          info:     '#0EA5E9',
        },
      },
      boxShadow: {
        glass:        '0 8px 32px 0 rgba(0, 0, 0, 0.40)',
        'glass-lg':   '0 12px 40px 0 rgba(0, 0, 0, 0.50), inset 0 1px 0 0 rgba(255, 255, 255, 0.08)',
        'liquid-card': '0 12px 40px 0 rgba(0, 0, 0, 0.50), inset 0 1px 0 0 rgba(255, 255, 255, 0.08)',
        specular:     'inset 0 1px 0 0 rgba(255, 255, 255, 0.08)',
        modal:        '0 24px 64px 0 rgba(0, 0, 0, 0.70), inset 0 1px 0 0 rgba(255, 255, 255, 0.10)',
      },
      backdropBlur: {
        glass:  '20px',
        liquid: '32px',
      },
      fontFamily: {
        sans: ['var(--font-inter)', 'Inter', 'ui-sans-serif', 'system-ui', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'Helvetica Neue', 'Arial', 'sans-serif'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'Monaco', 'Consolas', 'monospace'],
      },
      transitionTimingFunction: {
        'liquid': 'cubic-bezier(0.16, 1, 0.3, 1)',
      },
      keyframes: {
        fadeIn: {
          '0%':   { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%':   { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        fadeIn:  'fadeIn 0.3s cubic-bezier(0.16, 1, 0.3, 1) both',
        slideUp: 'slideUp 0.4s cubic-bezier(0.16, 1, 0.3, 1) both',
      },
    },
  },
  plugins: [],
};
