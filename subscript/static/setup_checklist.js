// Setup checklist (home card) -- fail-soft
(function loadSetupChecklist() {
  var list = document.getElementById("setup-list");
  var summary = document.getElementById("setup-summary");
  var card = document.getElementById("setup-checklist-card");
  if (!list && !card) return;
  fetch("/setup/status")
    .then(function (r) { return r.json(); })
    .then(function (data) {
      if (summary && data && data.summary) summary.textContent = data.summary;
      if (!list) return;
      list.innerHTML = "";
      var items = (data && data.items) || [];
      items.forEach(function (it) {
        var li = document.createElement("li");
        li.className = "setup-row";
        var dot = document.createElement("span");
        dot.className = "setup-dot " + (it.status || "yellow");
        dot.title = it.status || "";
        var label = document.createElement("span");
        label.className = "setup-label";
        label.textContent = it.label || it.id || "";
        var detail = document.createElement("span");
        detail.className = "setup-detail";
        detail.textContent = it.detail || "";
        var fix = document.createElement("span");
        fix.className = "setup-fix";
        fix.textContent = it.fix || "";
        li.appendChild(dot);
        li.appendChild(label);
        li.appendChild(detail);
        li.appendChild(fix);
        list.appendChild(li);
      });
      if (!items.length) {
        list.innerHTML =
          '<li class="setup-row"><span class="setup-dot yellow"></span>' +
          '<span class="setup-label">No checks returned</span></li>';
      }
    })
    .catch(function () {
      if (summary) summary.textContent = "Could not load setup status (app still works).";
      if (list) {
        list.innerHTML =
          '<li class="setup-row"><span class="setup-dot yellow"></span>' +
          '<span class="setup-label">Checklist unavailable</span>' +
          '<span class="setup-fix">Refresh the page after the server starts.</span></li>';
      }
    });
})();
