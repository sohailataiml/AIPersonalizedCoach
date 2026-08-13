import type { Config } from 'tailwindcss';

/**
 * Design direction: a coach operations product.
 *
 * Light canvas, white cards, one dark navy rail. The palette is narrow on
 * purpose and colour is semantic: teal = safe, amber = cautioned/down-ranked,
 * red = removed by the graph, violet = graph/provenance affordances. If
 * something is amber on this page it is because the graph down-ranked it, never
 * because it looked good.
 */
const config: Config = {
  darkMode: 'class',
  content: [
    './app/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
    './features/**/*.{ts,tsx}',
    './lib/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        // Dark rail + primary text
        navy: {
          50: '#f4f6fb',
          100: '#e6eaf4',
          200: '#c6cfe4',
          300: '#95a4c8',
          400: '#5f73a4',
          500: '#3d5183',
          600: '#2b3c68',
          700: '#1f2d51',
          800: '#16213d',
          900: '#101a30',
          950: '#0a1122',
        },
        ink: {
          50: '#f8f9fb',
          100: '#f1f3f7',
          200: '#e3e7ee',
          300: '#cbd2de',
          400: '#98a2b3',
          500: '#697586',
          600: '#4b5565',
          700: '#364152',
          800: '#242e3f',
          900: '#161d29',
        },
        brand: {
          50: '#eff6ff',
          100: '#dbeafe',
          200: '#bfdbfe',
          400: '#60a5fa',
          500: '#3b82f6',
          600: '#2563eb',
          700: '#1d4ed8',
        },
        safe: {
          50: '#ecfdf5',
          100: '#d1fae5',
          200: '#a7f3d0',
          500: '#10b981',
          600: '#059669',
          700: '#047857',
        },
        caution: {
          50: '#fffbeb',
          100: '#fef3c7',
          200: '#fde68a',
          500: '#f59e0b',
          600: '#d97706',
          700: '#b45309',
        },
        danger: {
          50: '#fef2f2',
          100: '#fee2e2',
          200: '#fecaca',
          500: '#ef4444',
          600: '#dc2626',
          700: '#b91c1c',
        },
        graph: {
          50: '#f5f3ff',
          100: '#ede9fe',
          200: '#ddd6fe',
          500: '#8b5cf6',
          600: '#7c3aed',
          700: '#6d28d9',
        },
      },
      fontFamily: {
        sans: ['var(--font-sans)', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['var(--font-mono)', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      fontSize: {
        '2xs': ['0.6875rem', { lineHeight: '1rem' }],
      },
      borderRadius: {
        card: '0.875rem',
      },
      boxShadow: {
        card: '0 1px 2px rgba(16, 26, 48, 0.04), 0 1px 3px rgba(16, 26, 48, 0.06)',
        raised: '0 4px 12px -2px rgba(16, 26, 48, 0.10), 0 2px 6px -2px rgba(16, 26, 48, 0.06)',
        pop: '0 12px 32px -8px rgba(16, 26, 48, 0.22)',
      },
      keyframes: {
        'fade-up': {
          from: { opacity: '0', transform: 'translateY(4px)' },
          to: { opacity: '1', transform: 'none' },
        },
        shimmer: {
          '100%': { transform: 'translateX(100%)' },
        },
      },
      animation: {
        'fade-up': 'fade-up 220ms cubic-bezier(0.16, 1, 0.3, 1) both',
      },
    },
  },
  plugins: [],
};

export default config;
