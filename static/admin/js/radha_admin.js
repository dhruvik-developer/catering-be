(function () {
  function ready(callback) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", callback);
      return;
    }

    callback();
  }

  ready(function () {
    var body = document.body;
    var header = document.getElementById("header");
    var sidebar = document.getElementById("nav-sidebar");

    if (body && body.classList.contains("radha-login-page")) {
      var username = document.getElementById("id_username");
      var password = document.getElementById("id_password");

      if (username && !username.getAttribute("placeholder")) {
        username.setAttribute("placeholder", "Enter your username");
      }

      if (password && !password.getAttribute("placeholder")) {
        password.setAttribute("placeholder", "Enter your password");
      }
    }

    if (!body || !header || !sidebar) {
      return;
    }

    var toggle = document.createElement("button");
    toggle.className = "radha-sidebar-toggle";
    toggle.type = "button";
    toggle.setAttribute("aria-controls", "nav-sidebar");
    toggle.setAttribute("aria-expanded", "false");
    toggle.setAttribute("aria-label", "Toggle navigation");
    toggle.innerHTML = '<span aria-hidden="true"></span><span aria-hidden="true"></span><span aria-hidden="true"></span>';

    var overlay = document.createElement("button");
    overlay.className = "radha-sidebar-overlay";
    overlay.type = "button";
    overlay.setAttribute("aria-label", "Close navigation");

    function setSidebar(open) {
      body.classList.toggle("radha-sidebar-open", open);
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    }

    toggle.addEventListener("click", function () {
      setSidebar(!body.classList.contains("radha-sidebar-open"));
    });

    overlay.addEventListener("click", function () {
      setSidebar(false);
    });

    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") {
        setSidebar(false);
      }
    });

    header.insertBefore(toggle, header.firstChild);
    document.body.appendChild(overlay);
  });
})();
