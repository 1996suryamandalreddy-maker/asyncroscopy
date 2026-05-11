// This file was automatically generated.

// This file is not supported by IE9 because of async - fetch

// Checks all Jupyter links on the page. Decorates the links if Jupyter is not supported or the server is not running.
async function checkAllJupyterLinks() {
    var isServerRunning = await checkServerStatus();
    var browserSupported = browserTypeSupported();

    if (!isServerRunning) {
        decorateJupyterLinks("server not available");
    }
    else if (!browserSupported) {
        decorateJupyterLinks("browser not supported");
    }
}

const jupyterURL = "http://localhost:8888/notebooks/AutoScriptTEM.ipynb";

async function checkServerStatus() {
    try {
        await fetch(jupyterURL, { mode: "no-cors", method: "HEAD"  });
        return true;
    } catch (error) {
        return false;
    }
}

function browserTypeSupported() {
    var browserType = getBrowserType();

    if (browserType === "IE" || browserType === null) {
        console.log(false);
        return false;
    }

    return true;
}

function getBrowserType() {
    function testUserAgent(regexp) {
        return regexp.test(navigator.userAgent);
    }

    if (testUserAgent(/opr\//i) || !!window.opr) return "Opera";
    if (testUserAgent(/edg/i)) return "Edge";
    if (testUserAgent(/chrome|chromium|crios/i)) return "Chrome";
    if (testUserAgent(/firefox|fxios/i)) return "Firefox";
    if (testUserAgent(/safari/i)) return "Safari";
    if (testUserAgent(/trident/i)) return "IE";

    return null;
}