/**
 * grab_cookies.js
 * Opens an isolated Chrome window for YouTube Music login.
 * On close, extracts cookies and saves them to config/browser.json
 * in the format expected by ytmusicapi's browser auth.
 */

const puppeteer = require('puppeteer-core');
const chromePaths = require('chrome-paths');
const fs = require('fs');
const path = require('path');
const readline = require('readline');

const CONFIG_DIR = path.join(__dirname, 'config');
const OUTPUT_FILE = path.join(CONFIG_DIR, 'browser.json');
const USER_DATA_DIR = path.join(__dirname, 'chrome_auth_profile');
const YTM_URL = 'https://music.youtube.com';

async function main() {
    const executablePath = chromePaths.chrome || chromePaths.chromium;
    if (!executablePath) {
        console.error('❌ No se encontró Chrome/Chromium. Instálalo con: brew install --cask google-chrome');
        process.exit(1);
    }

    console.log('🚀 Abriendo Chrome para autenticación de YouTube Music...');
    console.log('   → Inicia sesión en YouTube Music y luego cierra la ventana del navegador.');
    console.log('   → Las cookies se guardarán automáticamente en config/browser.json\n');

    const browser = await puppeteer.launch({
        executablePath,
        headless: false,
        userDataDir: USER_DATA_DIR,
        args: [
            '--no-first-run',
            '--no-default-browser-check',
            '--disable-blink-features=AutomationControlled',
        ],
        defaultViewport: null,
    });

    const pages = await browser.pages();
    const page = pages[0] || await browser.newPage();
    await page.goto(YTM_URL, { waitUntil: 'domcontentloaded' });

    console.log('⏳ Esperando a que cierres la ventana de Chrome...');

    // Wait for the browser to be closed by the user
    await new Promise((resolve) => {
        browser.on('disconnected', resolve);
    });

    console.log('\n✅ Ventana cerrada. Extrayendo cookies...');

    // Re-launch headlessly to extract cookies from the saved profile
    const browser2 = await puppeteer.launch({
        executablePath,
        headless: true,
        userDataDir: USER_DATA_DIR,
        args: ['--no-first-run', '--no-default-browser-check'],
    });

    const page2 = await browser2.newPage();
    await page2.goto(YTM_URL, { waitUntil: 'networkidle2', timeout: 30000 }).catch(() => {});

    const cookies = await page2.cookies(YTM_URL);
    await browser2.close();

    if (!cookies || cookies.length === 0) {
        console.error('❌ No se encontraron cookies. Asegúrate de haber iniciado sesión.');
        process.exit(1);
    }

    // Also grab request headers by intercepting a YTM API call
    const browser3 = await puppeteer.launch({
        executablePath,
        headless: true,
        userDataDir: USER_DATA_DIR,
        args: ['--no-first-run', '--no-default-browser-check'],
    });

    const page3 = await browser3.newPage();
    let capturedHeaders = null;

    await page3.setRequestInterception(true);
    page3.on('request', (req) => {
        const url = req.url();
        if (url.includes('music.youtube.com/youtubei') && !capturedHeaders) {
            capturedHeaders = req.headers();
        }
        req.continue();
    });

    await page3.goto(YTM_URL, { waitUntil: 'networkidle2', timeout: 30000 }).catch(() => {});
    // Trigger a browse request
    await page3.evaluate(() => {
        return fetch('https://music.youtube.com/youtubei/v1/browse', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ browseId: 'FEmusic_home' }),
            credentials: 'include',
        }).catch(() => {});
    }).catch(() => {});

    await new Promise(r => setTimeout(r, 2000));
    await browser3.close();

    // Build ytmusicapi browser auth format
    const cookieHeader = cookies.map(c => `${c.name}=${c.value}`).join('; ');

    const authData = {
        authorization: 'SAPISIDHASH dummy',
        origin: 'https://music.youtube.com',
        cookie: cookieHeader,
        'x-goog-authuser': '0',
        ...(capturedHeaders ? {
            'user-agent': capturedHeaders['user-agent'] || '',
            'x-goog-visitor-id': capturedHeaders['x-goog-visitor-id'] || '',
            'x-youtube-client-name': capturedHeaders['x-youtube-client-name'] || '67',
            'x-youtube-client-version': capturedHeaders['x-youtube-client-version'] || '',
        } : {}),
    };

    if (!fs.existsSync(CONFIG_DIR)) {
        fs.mkdirSync(CONFIG_DIR, { recursive: true });
    }

    fs.writeFileSync(OUTPUT_FILE, JSON.stringify(authData, null, 2), 'utf8');

    console.log(`✅ Cookies guardadas en: ${OUTPUT_FILE}`);
    console.log(`   (${cookies.length} cookies capturadas)`);
    console.log('\n🎵 Autenticación completada. Ya puedes usar vibemus normalmente.');
}

main().catch((err) => {
    console.error('❌ Error durante la autenticación:', err.message);
    process.exit(1);
});
