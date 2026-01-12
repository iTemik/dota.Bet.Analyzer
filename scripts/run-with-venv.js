#!/usr/bin/env node

/**
 * Helper script to run commands with activated Python venv
 * Works cross-platform (Windows, macOS, Linux)
 */

const { execSync } = require('child_process');
const path = require('path');
const fs = require('fs');

// Get the command from arguments
const command = process.argv.slice(2).join(' ');

if (!command) {
    console.error('Error: No command provided');
    process.exit(1);
}

// Detect OS and get venv python path
const isWindows = process.platform === 'win32';
const isMac = process.platform === 'darwin';

let venvPythonPath;
if (isWindows) {
    venvPythonPath = path.join(__dirname, '..', '.venv', 'Scripts', 'python.exe');
} else {
    venvPythonPath = path.join(__dirname, '..', '.venv', 'bin', 'python');
}

// Check if venv exists
if (!fs.existsSync(venvPythonPath)) {
    console.error(`Error: Virtual environment not found at ${venvPythonPath}`);
    console.error('Please create it with: python -m venv .venv');
    process.exit(1);
}

// Build the command with proper quoting
const pythonExe = `"${venvPythonPath}"`;
let fullCommand;

if (command.startsWith('python ')) {
    // Replace 'python' with venv python path
    fullCommand = pythonExe + ' ' + command.slice(7);
} else if (command.startsWith('python-')) {
    // Handle 'python-m' case
    fullCommand = pythonExe + ' -m ' + command.slice(8);
} else {
    fullCommand = command;
}

try {
    console.log(`Running: ${fullCommand}\n`);
    execSync(fullCommand, {
        stdio: 'inherit',
        cwd: path.join(__dirname, '..'),
        shell: true,
        env: { ...process.env }
    });
} catch (error) {
    // execSync throws on non-zero exit, but we want to propagate that
    process.exit(error.status || 1);
}
