// This file was automatically generated.

var searchPhraseUrlParam = "searchPhrase";
var targetUrlParam = "target";

function hookMessageEvent(messageHandler) {
    var eventMethod = window.addEventListener ? "addEventListener" : "attachEvent";
    var eventer = window[eventMethod];
    var messageEvent = eventMethod === "attachEvent" ? "onmessage" : "message";

    if (eventer != null) {
        eventer(messageEvent, messageHandler);
    }
}

// Returns the full current location url.
function getUrl() {
    return window.document.location.href;
}

// Sets the current location url to a given value.
function setUrl(url) {
    window.document.location.href = url;
}

// Returns a parameter value from the url.
function getUrlParameter(url, parameterName) {
    var parameters = getUrlParameters(url);
    return parameters[parameterName];
}

// Return all url parameters as a dictionary.
function getUrlParameters(url) {
    parameters = {};

    decodeURIComponent(url).replace(/[?&]+([^=&]+)=([^&]*)/gi,
        function(_, key, value) {
            return parameters[key] = value;
        });

    return parameters;
}

// Sets ulr parameters from a dictionary.
function setUrlParameters(url, dictionary) {
    var mainUrlPart = getMainUrlPart(url);
    var keys = Object.keys(dictionary);
    var parameters = "";

    for(var i = 0; i < keys.length; i++) {
        if (i > 0) {
            parameters += "&";
        }

        var key = keys[i];
        var value = dictionary[keys[i]];
        parameters += encodeURIComponent(key) + "=" + encodeURIComponent(value);
    }

    return mainUrlPart + "?" + parameters;
}

// Returns the main part of the url (before the question mark).
function getMainUrlPart(url) {
    return url.split("?")[0];
}

// Adds a new parameter to the url and returns the url.
function addUrlParameter(url, key, value) {
    parameters = getUrlParameters(url);
    parameters[key] = value;
    return setUrlParameters(url, parameters);
}

// Removes a parameter from the url and returns the url.
function removeUrlParameter(url, key) {
    parameters = getUrlParameters(url);
    delete parameters[key];
    return setUrlParameters(url, parameters);
}

// Splits input text into words using regex.
function splitIntoWords(text) {
    return text.match(/\b(\w+)\b/g);
}

// Intersects two arrays.
function intersect(array1, array2) {
    // Switch array to loop over the shorter one
    if (array2.length > array1.length) {
        var temp;
        temp = array2, array2 = array1, array1 = temp;
    }

    return array1.filter(function(element) {
        return array2.indexOf(element) > -1;
    });
}

// Hides given element by ID (sets display to none).
function hideElementById(elementId) {
    hideElement(document.getElementById(elementId));
}

// Hides given element (sets display to none).
function hideElement(element) {
    element.style.display = "none";
}

// Shows given element by ID (sets display to empty string).
function showElementById(elementId) {
    showElement(document.getElementById(elementId));
}

// Shows given element (sets display to block).
function showElement(element) {
    element.style.display = "block";
}

// Colapses parent node in menu (sets checked to false).
function uncheckElement(element) {
    element.checked = false;
}

// Marks the given text with the highlight css class. Treats each word separately.
function markPhrase(element, phrase) {
    var words = splitIntoWords(phrase);

    // Sort longer matches first to avoid highlighting words within words.
    words.sort(function(a, b) {
        return b.length - a.length;
    });

    var wordsRegex = RegExp(words.join("|"), "ig"); // Global case-insensitive search
    markWords(element, wordsRegex);
}

// Recursive function to mark words in the element and all its children.
function markWords(element, wordsRegex) {
    forEach(element.childNodes, function(child){
        if (child.nodeType !== 3) { // Not a text node
            markWords(child, wordsRegex);
        } else if (wordsRegex.test(child.textContent)) {
            var fragment = document.createDocumentFragment();
            var lastIdx = 0;

            child.textContent.replace(wordsRegex, function(match, idx) {
                var part = document.createTextNode(child.textContent.slice(lastIdx, idx));

                var marked = document.createElement("span");
                marked.textContent = match;
                marked.classList.add("highlight");

                fragment.appendChild(part);
                fragment.appendChild(marked);

                lastIdx = idx + match.length;
            });

            var end = document.createTextNode(child.textContent.slice(lastIdx));
            fragment.appendChild(end);
            child.parentNode.replaceChild(fragment, child);
        }
    });
}

// A foreach function that works with arrays and array-like objects.
function forEach(array, callback) {
    var length = array.length;

    for (var i = 0; i < length; i++) {
        callback(array[i], i, array);
    }
}

// Scrolls the given elementId into view.
function ScrollTo(elementId) {
    document.getElementById(elementId).scrollIntoView();
}