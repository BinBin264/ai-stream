import type { Config } from 'tailwindcss'

const config: Config = {
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}', './lib/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: '#101418',
        panel: '#f7f8fa',
        line: '#d9dee6',
        live: '#e11d48',
      },
    },
  },
  plugins: [],
}

export default config
