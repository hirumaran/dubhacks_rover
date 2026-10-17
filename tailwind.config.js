module.exports = {
  content: ["./app/**/*.{ts,tsx}", "./src/**/*.{ts,tsx}"],
  presets: [require("nativewind/preset")],
  theme: {
    extend: {
      colors: {
        sage: "#5B8174",
        peach: "#FCCFA5",
        ink: "#231F20",
        paper: "#FAFAF7",
      },
    },
  },
  plugins: [],
};
