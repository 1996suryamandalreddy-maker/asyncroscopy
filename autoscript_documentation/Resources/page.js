// This file was automatically generated.

// Hooks the onContentLoaded function to start once the page finishes loading
function addLoadEvent(shellPath) {
    // attachEvent for IE, EventListener for modern browsers
    window.attachEvent ?
        window.attachEvent('onload', function () {
            onContentLoaded(shellPath);

            try {
                checkAllJupyterLinks();
            } catch (e) {
                disableAllJupyterLinks();
            };
        }) :

        window.addEventListener('load', function () {
            onContentLoaded(shellPath);

            try {
                checkAllJupyterLinks();
            } catch (e) {
                disableAllJupyterLinks();
            };
        });
}

// Event fires when the DOM content fully loads.
function onContentLoaded(shellPath) {
    redirectIfNotInFrame(shellPath);
    sendFrameData();
    hookWindowResize();
    createCopyButtons();
    highlightSearchPhrase();
    addScrollToTop();
}

// Opens page in shell html view with target content in frame if the page is not in frame.
function redirectIfNotInFrame(shellPath) {
    // not in a frame
    if (window.top === window.self) {
        setUrl(addUrlParameter(shellPath, targetUrlParam, getUrl()));
    }
}

// Sends frame data as a message.
// Frame data must be sent as a message to avoid cross origin frame.
function sendFrameData() {
    if (parent.postMessage) {
        var jsonMessage = JSON.stringify({ "height": window.document.body.scrollHeight, "location": getUrl() });
        parent.postMessage(jsonMessage, "*");
    }
}

// Hooks message event that fires when the window resizes.
function hookWindowResize() {
    hookMessageEvent(function() {
        sendFrameData();
    });
}

var coppiedClass  = "copied";

// Creates copy button to all pre elements (code examples).
function createCopyButtons() {
    if (!isClipboardSupported()) {
        return;
    }

    var preElements = document.getElementsByTagName("pre");

    for (var index = 0; index < preElements.length; index++) {
        var preElement = preElements[index];

        var copyButton =  document.createElement("button");
        copyButton.title = "Copy snippet to clipboard";
        copyButton.onclick = createOnClickHandler(copyButton, preElement);

        preElement.appendChild(copyButton);
    }
}

// Checks if the clipboard API is supported by the browser.
function isClipboardSupported() {
    return navigator.clipboard && navigator.clipboard.writeText;
}

// Creates on click handler for the copy button.
// This is a workaround for the var scoping issue in the for loop (IE doesn't support let).
function createOnClickHandler(copyButton, preElement) {
    return function() {
        navigator.clipboard.writeText(preElement.innerText);
        copyButton.classList.add(coppiedClass);
        setTimeout(function() {
            copyButton.classList.remove(coppiedClass);
        }, 2000);
    };
}

// Highlights the inner body html based on the search phrase available as url parameter.
function highlightSearchPhrase() {
    var url = getUrl();
    var searchPhrase = getUrlParameter(url, searchPhraseUrlParam);

    if (searchPhrase) {
        markPhrase(window.document.body, searchPhrase);
    }
}

// Every link inside the frame sends a message to the window when clicked, to scroll to the top of the page
function addScrollToTop() {
    var links = document.querySelectorAll('a');

    for (var i = 0; i < links.length; i++) {
        links[i].addEventListener('click', function (event) {
            parent.postMessage("ScrollToTop", "*")
        });
    }
}
