const puppeteer = require('puppeteer-core');
const fs = require('fs');
const path = require('path');
const os = require('os');
const readline = require('readline');

(async () => {
    // Standard macOS paths
    const chromePath = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';

    // Create an isolated profile exclusively for Vibemus
    const userDataDir = path.join(__dirname, 'chrome_auth_profile');
    if (!fs.existsSync(userDataDir)) {
        fs.mkdirSync(userDataDir, { recursive: true });
    }

    console.log(`\n======================================================`);
    console.log(`🎵 VIBEMUS AUTHENTICATOR`);
    console.log(`======================================================`);
    console.log(`\nLaunching an isolated Chrome window specifically for Vibemus.`);
    console.log(`If you haven't logged in yet, you will need to SIGN IN to your Google account.`);
    console.log(`Once you are signed in and viewing YouTube Music, CLOSE the Chrome window.`);

    try {
        const browser = await puppeteer.launch({
            executablePath: chromePath,
            userDataDir: userDataDir,
            headless: false, // Must be visible so the user can log in
            args: [
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-blink-features=AutomationControlled'
            ]
        });

        const page = await browser.newPage();

        let foundHeaders = null;

        // Intercept network requests continuously
        await page.setRequestInterception(true);
        page.on('request', request => {
            const url = request.url();
            // We look for authenticated POST requests the YouTube UI naturally makes
            if (url.includes('music.youtube.com/youtubei/v1/browse') ||
                url.includes('music.youtube.com/youtubei/v1/next')) {
                const headers = request.headers();
                if (headers.authorization && headers.cookie && !foundHeaders) {
                    foundHeaders = headers;
                    console.log("\n✅ INTERCEPTED AUTHENTICATED HEADERS! You can now close the browser window.");
                }
            }
            request.continue();
        });

        console.log("\nNavigating to music.youtube.com...");
        await page.goto('https://music.youtube.com', { waitUntil: 'networkidle2', timeout: 0 }).catch(() => { });

        // Wait for the browser to be closed by the user or until we get headers
        return new Promise((resolve) => {
            browser.on('disconnected', () => {
                if (foundHeaders) {
                    saveHeaders(foundHeaders);
                    process.exit(0);
                } else {
                    console.log("\n❌ Browser closed before authentication could be intercepted. Did you log in?");
                    process.exit(1);
                }
            });

            // Or if they leave it open but we caught it, wait 5 seconds and self-close
            const checkInterval = setInterval(async () => {
                if (foundHeaders) {
                    clearInterval(checkInterval);
                    console.log("Saving headers and auto-closing...");
                    saveHeaders(foundHeaders);
                    await browser.close();
                    process.exit(0);
                }
            }, 2000);
        });

    } catch (e) {
        console.error("Automation failed:", e.message);
        process.exit(1);
    }
})();

function saveHeaders(foundHeaders) {
    const cleanHeaders = {
        "accept": "*/*",
        "accept-language": foundHeaders["accept-language"] || "en-US,en;q=0.9",
        "authorization": foundHeaders["authorization"],
        "content-type": "application/json",
        "cookie": foundHeaders["cookie"],
        "origin": "https://music.youtube.com",
        "user-agent": foundHeaders["user-agent"],
        "x-goog-authuser": foundHeaders["x-goog-authuser"] || "0",
        "x-origin": "https://music.youtube.com",
    };

    if (foundHeaders["x-goog-visitor-id"]) {
        cleanHeaders["x-goog-visitor-id"] = foundHeaders["x-goog-visitor-id"];
    }

    // Ensure config directory exists
    if (!fs.existsSync('config')) {
        fs.mkdirSync('config');
    }

    fs.writeFileSync('config/browser.json', JSON.stringify(cleanHeaders, null, 4));
    console.log("Successfully wrote pristine authenticated headers to config/browser.json!");
}
