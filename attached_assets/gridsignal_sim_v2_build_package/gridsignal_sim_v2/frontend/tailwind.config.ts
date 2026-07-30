import type { Config } from 'tailwindcss'

export default {
  content: [
    './index.html',
    './src/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        // GridSignal design language — dark operational palette
        canvas:  '#0d1117',
        surface: '#161b22',
        border:  '#30363d',
        muted:   '#8b949e',
        text:    '#e6edf3',
        accent:  '#58a6ff',
        warn:    '#f0883e',
        danger:  '#f85149',
        ok:      '#3fb950',
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
    },
  },
  plugins: [],
} satisfies Config
