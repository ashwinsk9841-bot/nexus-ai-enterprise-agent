const fs = require("fs");
const { transform } = require("esbuild");
const src = fs.readFileSync("frontend/src/js/app.js", "utf8");
try {
  transform(src, { loader: "js" });
  console.log("app.js parses OK");
} catch (e) {
  console.log("PARSE ERROR:", e.message);
  if (e.errors && e.errors.length) {
    e.errors.forEach((er) =>
      console.log(`  ${er.location.file}:${er.location.line}:${er.location.column} ${er.text}`)
    );
  }
}