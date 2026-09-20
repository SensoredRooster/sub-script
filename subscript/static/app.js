(function () {
  var form = document.getElementById("clip-form");
  if (!form) return;

  var drop = document.getElementById("drop-zone");
  var input = document.getElementById("file-input");
  var label = document.getElementById("file-label");
  var custom = document.getElementById("custom-fields");
  var busy = document.getElementById("busy");
  var btn = document.getElementById("clip-btn");
  var customRadio = form.querySelector('input[name="mode"][value="custom"]');

  function setFileName(file) {
    if (!label) return;
    label.textContent = file ? file.name : "No file chosen";
  }

  function syncCustom() {
    if (!custom || !customRadio) return;
    custom.hidden = !customRadio.checked;
  }

  if (input) {
    input.addEventListener("change", function () {
      setFileName(input.files && input.files[0]);
    });
  }

  if (drop && input) {
    ["dragenter", "dragover"].forEach(function (ev) {
      drop.addEventListener(ev, function (e) {
        e.preventDefault();
        drop.classList.add("dragover");
      });
    });
    ["dragleave", "drop"].forEach(function (ev) {
      drop.addEventListener(ev, function (e) {
        e.preventDefault();
        drop.classList.remove("dragover");
      });
    });
    drop.addEventListener("drop", function (e) {
      var files = e.dataTransfer && e.dataTransfer.files;
      if (!files || !files.length) return;
      var dt = new DataTransfer();
      dt.items.add(files[0]);
      input.files = dt.files;
      setFileName(files[0]);
    });
    drop.addEventListener("click", function (e) {
      if (e.target.closest("label")) return;
      input.click();
    });
  }

  form.querySelectorAll('input[name="mode"]').forEach(function (radio) {
    radio.addEventListener("change", syncCustom);
  });
  syncCustom();

  form.addEventListener("submit", function () {
    if (busy) busy.hidden = false;
    if (btn) {
      btn.disabled = true;
      btn.textContent = "Working…";
    }
  });
})();
