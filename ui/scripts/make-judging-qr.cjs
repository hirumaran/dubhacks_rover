const QRCode = require("qrcode");
const fs = require("node:fs");
const url = "https://huskyfind-uw.expo.app";
fs.mkdirSync("public", { recursive: true });
QRCode.toFile("public/judging-qr.png", url, {
  width: 600,
  margin: 4,
  color: { dark: "#4B2E83", light: "#FFFFFF" },
  errorCorrectionLevel: "M",
})
  .then(() => console.log("Permanent judging QR:", url))
  .catch((error) => {
    console.error(error.message);
    process.exitCode = 1;
  });
