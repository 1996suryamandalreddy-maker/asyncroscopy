// This file was automatically generated.

// Event fires when the body of the shell fully loads. 
function onBodyLoaded(frameName, navTreeId, searchInputId) {
    addScrollToTopToNavTree(navTreeId);
    addSendSearchPhraseToNavTree(navTreeId, searchInputId);
    setFrameTarget(frameName);
}

// Adds scroll to top action to all links in nav tree menu.
function addScrollToTopToNavTree(navTreeId) {
    function addScrollToTop(menuItem) {
        menuItem.addEventListener('click', function (event) {

            // Do nothing if inside label (which means the link is a category with further elements)
            if (this.parentElement.tagName && this.parentElement.tagName.toLowerCase() == 'label') {
                return
            }

            // Basic scroll to top (no smooth behavior in IE)
            window.scrollTo(0, 0);
        });
    }

    applyToAllMenuItems(navTreeId, addScrollToTop, "a");
}

// Adds send search phrase to all links in nav tree menu.
function addSendSearchPhraseToNavTree(navTreeId, searchInputId) {
    function addSendSearch(menuItem) {
        menuItem.onclick = function () {
            var searchPhrase = getSearchPhrase(searchInputId);

            var newUrl = searchPhrase
                ? addUrlParameter(menuItem.getAttribute("href"), searchPhraseUrlParam, searchPhrase)
                : removeUrlParameter(menuItem.getAttribute("href"), searchPhraseUrlParam);
            
            menuItem.href = newUrl;
        };
    }

    applyToAllMenuItems(navTreeId, addSendSearch, "a");
}

// Sets frame location based on the target url parameter.
function setFrameTarget(frameName) {
    var frame = getFrame(frameName);
    var target = getUrlParameter(getUrl(), targetUrlParam);

    if (frame && target) {
        frame.location = target;
    }
}

// Gets frame by its name.
function getFrame(frameName) {
    return window.frames[frameName];
}

// Event fires when the iframe fully loads.
function onFrameLoaded(frame, navTreeId) {
    // Change URL to match the page loaded in the frame (so it actually works like a URL) when possible
    try {
        // The url is about:blank when the page first loads (e.g. when clicking a link someone sent you)
        if (frame.contentDocument.URL != "about:blank") {
            window.history.replaceState({}, "", addUrlParameter("shell.html", targetUrlParam, frame.contentDocument.URL))
        }
    }
    catch (error){
        console.log("Changing url failed with: ", error)
    }

    hookFrameChange(frame, navTreeId);
}

// Last visited frame location.
var lastLocation;

// Hooks message event that fires when the frame changes or when a link is clicked inside the frame.
function hookFrameChange(frame, navTreeId) {
    if (frame) {
        hookMessageEvent(function (messageArg) {

            // a link was clicked - scrolling to top of the page
            if (messageArg.data == "ScrollToTop") {
                window.scrollTo(0, 0);
                return;
            }

            // frame was resized
            var parsedObject = JSON.parse(messageArg.data);
            resizeFrame(frame, parseInt(parsedObject.height));

            lastLocation = parsedObject.location;
            expandTreeMenuToShowCurrent(parsedObject.location, navTreeId);
        });
    }
}

// Resizes the frame based on the information from the message argument.
function resizeFrame(frame, height) {
    var heightWithMargin = height + 60; // margin to be sure
    frame.style.height = heightWithMargin + "px";
}

// Expands tree menu to show current page.
function expandTreeMenuToShowCurrent(currentPage, navTreeId) {
    var link = findNavTreeLinkByHref(currentPage, navTreeId);
    expandLink(link);
}

// Finds the first link in navtree based on its href. If there are no links, returns null. 
function findNavTreeLinkByHref(href, navTreeId) {
    var replacedHref = href.replace(" ", "%20");
    var links = window.document.getElementById(navTreeId).getElementsByTagName("a");

    for (var i = 0, l = links.length; i < l; i++) {
        if (links[i].href === href || links[i].href === replacedHref) {
            return links[i];
        }
    }

    return null;
}

// Expands tree menu from link element.
function expandLink(link) {
    if (link) {
        // if the link has label as its parent, we need to go one layer higher
        if (link.parentElement && link.parentElement.tagName.toLowerCase() === "label") {
            expandTreeNode(link.parentElement.parentElement);
        } else {
            expandTreeNode(link.parentElement);
        }
    }
}

// Recursive function that expands and shows all related tree node elements. Always has to start on the li element.
function expandTreeNode(parent) {
    if (parent && parent.tagName.toLowerCase() === "li") {
        showElement(parent);
        var input = parent.getElementsByTagName("input")[0];

        if (input) {
            input.checked = true;
        }

        var grandParent = parent.parentElement;

        if (grandParent && grandParent.tagName.toLowerCase() === "ul") {
            expandTreeNode(grandParent.parentElement);
        }
    }
}

// Sends information about window resize to the iframe.
// Information must be sent as a message to avoid cross origin frame.
function sendResizeInfo(frameName) {
    var frame = getFrame(frameName);

    if (frame && frame.postMessage) {
        frame.postMessage("WindowResized", "*");
    }
}

// Executes search of the manual. If any keyword was found in the index, shows the full text result.
// If not, filters the menu.
// If the filter phrase is null or empty, shows all menu items and expands the current.
function searchMenu(searchInputId, navTreeId, menuEmptyInfoId) {
    var searchPhrase = getSearchPhrase(searchInputId);
    var keyWords = splitIntoWords(searchPhrase);

    hideAllMenuItems(navTreeId);
    showElementById(menuEmptyInfoId);

    if (searchPhrase) {
        var searchResults = searchWords(keyWords);

        if (searchResults != null && searchResults.length > 0) {
            applyFullTextSearch(searchResults, navTreeId, menuEmptyInfoId);
        }

        applyFilterSearch(searchPhrase, navTreeId, menuEmptyInfoId);
    } else {
        resetMenu(navTreeId, menuEmptyInfoId);
    }
}

// Returns a normalized search phrase from the given search input.
function getSearchPhrase(searchInputId) {
    return document.getElementById(searchInputId).value.toLowerCase();
}

// Applies full text result to the menu and shows only found pages.
function applyFullTextSearch(searchResults, navTreeId, menuEmptyInfoId) {
    function expandFoundLink(link) {
        var linkUrl = getMainUrlPart(link.getAttribute("href"));

        if (searchResults.indexOf(linkUrl) > -1) {
            expandLink(link);
            hideElementById(menuEmptyInfoId);
        }
    }

    applyToAllMenuItems(navTreeId, expandFoundLink, "a");
}

// Filters the menu and shows only links that contain the filterPhrase.
function applyFilterSearch(filterPhrase, navTreeId, menuEmptyInfoId) {
    function expandFoundLink(link) {
        var searchWords = splitIntoWords(filterPhrase);
        var text = link.textContent || link.innerText;

        if (areWordsInText(text, searchWords)) {
            expandLink(link);
            hideElementById(menuEmptyInfoId);
        }
    }

    applyToAllMenuItems(navTreeId, expandFoundLink, "a");
}

// Returns true if all words are in the text. If the words collection is empty, returns true.
function areWordsInText(text, words) {
    var found = true;

    for (var i = 0; i < words.length; i++) {
        if (text.toLowerCase().indexOf(words[i]) < 0) {
            found = false;
        }
    }

    return found;
}

// Clears the given search input and resets the menu.
function clearSearch(searchInputId, navTreeId, menuEmptyInfoId) {
    document.getElementById(searchInputId).value = "";
    resetMenu(navTreeId, menuEmptyInfoId);
}

// Un-expands all menu items.
function hideAllMenuItems(navTreeId) {
    applyToAllMenuItems(navTreeId, hideElement, "li");
    applyToAllMenuItems(navTreeId, uncheckElement, "input");
}

// Resets the menu into an original state: all folders are expanded, the last location path is visible, menu empty info is hidden.
function resetMenu(navTreeId, menuEmptyInfoId) {
    applyToAllMenuItems(navTreeId, showElement, "li");

    if (lastLocation) {
        expandTreeMenuToShowCurrent(lastLocation, navTreeId);
    }

    hideElementById(menuEmptyInfoId);
}

// Applies function to all list elements in menu.
function applyToAllMenuItems(navTreeId, action, tag) {
    var menuItems = document.getElementById(navTreeId).getElementsByTagName(tag);

    for (var i = 0; i < menuItems.length; i++) {
        action(menuItems[i]);
    }
}

// Executes an index lookup for each search word and returns a list of pages.
// If no pages were found, returns an empty array.
// If no index was found, returns null.
function searchWords(keyWords) {
    if (typeof index === 'undefined') {
        return null;
    }

    var searchResults;

    for (var i = 0; i < keyWords.length; i++) {
        var keyWord = keyWords[i];
        var keyWordResults = index[keyWord];

        // Stop if any keyword returns no results
        if (!keyWordResults) {
            return [];
        }

        if (!searchResults) {
            // The first found key word adds all the pages
            searchResults = keyWordResults;
        } else {
            // Every other key words removes pages that don't contain the word
            searchResults = intersect(searchResults, keyWordResults);
        }
    }

    return searchResults;
}