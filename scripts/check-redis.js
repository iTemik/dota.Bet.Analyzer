#!/usr/bin/env node
/**
 * Check if Redis is running before starting dev environment
 * Attempts to connect to Redis on localhost:6379
 */

const net = require('net');

function checkRedis() {
    return new Promise((resolve) => {
        const socket = new net.Socket();
        const timeout = 2000;

        socket.setTimeout(timeout);

        socket.on('connect', () => {
            socket.destroy();
            console.log('✅ Redis is running on localhost:6379');
            resolve(true);
        });

        socket.on('timeout', () => {
            socket.destroy();
            console.error('❌ Redis connection timeout');
            resolve(false);
        });

        socket.on('error', () => {
            console.error('❌ Redis is not running on localhost:6379');
            resolve(false);
        });

        socket.connect(6379, 'localhost');
    });
}

async function main() {
    console.log('Checking Redis availability...');
    const isRunning = await checkRedis();

    if (!isRunning) {
        console.error('\nRedis must be running before starting the dev environment.');
        console.error('\nChoose one option:\n');
        console.error('Option 1 - Docker (recommended):');
        console.error('  docker run -d -p 6379:6379 redis:latest\n');
        console.error('Option 2 - Local Redis:');
        console.error('  1. Download: https://github.com/microsoftarchive/redis/releases');
        console.error('  2. Install and run: redis-server\n');
        process.exit(1);
    }

    process.exit(0);
}

main();
