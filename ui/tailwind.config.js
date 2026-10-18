module.exports = {
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./src/**/*.{ts,tsx}"],
  presets: [require("nativewind/preset")],
  theme: {
    extend: {
      colors: {
        sage: "#4B2E83",
        peach: "#E8D8A1",
        ink: "#251B36",
        paper: "#FAF8FC",
      },
    },
  },
  plugins: [],
};
