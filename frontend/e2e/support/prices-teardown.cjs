// After the browser tests: remove the demonstration INR rows from the *_test databases again.
const { run } = require('./prices-setup.cjs');

module.exports = async () => { run('--remove'); };
