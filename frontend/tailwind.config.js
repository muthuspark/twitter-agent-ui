export default {
  content: ["./index.html", "./src/**/*.{vue,js}"],
  theme: {
    extend: {
      colors: Object.fromEntries([
        'ink', 'ink-hover', 'ink-secondary', 'muted', 'accent', 'accent-wash',
        'paper', 'paper-shade', 'rule', 'rule-strong', 'success', 'success-wash',
        'success-rule', 'warning', 'warning-wash', 'warning-rule',
        'danger', 'danger-wash', 'danger-rule',
      ].map((name) => [name, `var(--${name})`])),
      fontFamily: {
        sans: ['"Courier Prime"', '"Courier New"', 'monospace'],
        mono: ['"Courier Prime"', '"Courier New"', 'monospace'],
      },
    },
  },
  plugins: [],
};
