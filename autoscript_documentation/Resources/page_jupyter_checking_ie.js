// This file was automatically generated.

// Checks all Jupyter links on the page. Decorates the links if Jupyter is not supported or the server is not running.
function disableAllJupyterLinks() {
    decorateJupyterLinks("browser not supported");
}

function decorateJupyterLinks(errorMessage) {
    var links = document.getElementsByClassName("link-jupyter");

    Array.prototype.forEach.call(links, function(link) {
        link.innerHTML += "<span> (" + errorMessage + ")</span>";
        link.style.setProperty("text-decoration", "line-through");
    })
}