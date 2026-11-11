// Before the browser tests: copy the ACADEMIC DEMONSTRATION INR price list into the *_test databases (never the
// development ones — scripts/apply_demo_inr_prices.py --target test refuses anything that isn't *_test).
const path = require('path');
const { execFileSync } = require('child_process');

const ROOT = path.resolve(__dirname, '..', '..', '..');
const run = (...args) => execFileSync(path.join(ROOT, 'backend/.venv/bin/python'),
  [path.join(ROOT, 'scripts/apply_demo_inr_prices.py'), '--target', 'test', ...args], { cwd: ROOT, stdio: 'pipe' });

module.exports = async () => { run(); };
module.exports.run = run;
