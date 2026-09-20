(function () {
  var form = document.getElementById("clip-form");
  if (form) {
    var drop = document.getElementById("drop-zone");
    var input = document.getElementById("file-input");
    var label = document.getElementById("file-label");
    var custom = document.getElementById("custom-fields");
    var busy = document.getElementById("busy");
    var btn = document.getElementById("clip-btn");
    var customRadio = form.querySelector('input[name="mode"][value="custom"]');
    var last30Radio = form.querySelector('input[name="mode"][value="last30"]');
    var autoHl = document.getElementById("auto-highlights");
    var hlPanel = document.getElementById("highlights-panel");
    var hlStatus = document.getElementById("highlights-status");
    var hlChips = document.getElementById("highlight-chips");
    var startInput = document.getElementById("clip-start");
    var durInput = document.getElementById("clip-duration");
    var localPath = document.getElementById("local-path");
    var hlTimer = null;
    var hlSeq = 0;

    function setFileName(file) {
      if (!label) return;
      label.textContent = file ? file.name : "No file chosen";
    }

    function syncCustom() {
      if (!custom || !customRadio) return;
      custom.hidden = !customRadio.checked;
    }

    function fmtTime(sec) {
      if (sec == null || sec === "") return "last";
      sec = Math.max(0, Number(sec) || 0);
      var h = Math.floor(sec / 3600);
      var m = Math.floor((sec % 3600) / 60);
      var s = Math.floor(sec % 60);
      if (h > 0) {
        return h + ":" + String(m).padStart(2, "0") + ":" + String(s).padStart(2, "0");
      }
      return m + ":" + String(s).padStart(2, "0");
    }

    function selectSuggestion(s, chipEl) {
      if (hlChips) {
        Array.prototype.forEach.call(hlChips.querySelectorAll(".hl-chip"), function (c) {
          c.classList.remove("active");
        });
      }
      if (chipEl) chipEl.classList.add("active");
      if (s.start == null) {
        if (last30Radio) last30Radio.checked = true;
        syncCustom();
        return;
      }
      if (customRadio) customRadio.checked = true;
      syncCustom();
      if (startInput) startInput.value = String(s.start);
      if (durInput) durInput.value = String(s.duration);
    }

    function renderHighlights(data) {
      if (!hlPanel || !hlChips || !hlStatus) return;
      hlPanel.hidden = false;
      hlChips.innerHTML = "";
      var suggestions = (data && data.suggestions) || [];
      if (data && data.fallback) {
        hlStatus.className = "meta warn";
        hlStatus.textContent = data.message || "Analysis failed — using last 30s.";
      } else {
        hlStatus.className = "meta";
        hlStatus.textContent =
          suggestions.length
            ? "Suggested clips (loudest moments). Click one to fill start/length."
            : "No suggestions.";
      }
      suggestions.forEach(function (s, i) {
        var chip = document.createElement("button");
        chip.type = "button";
        chip.className = "hl-chip" + (s.start == null ? " fallback" : "");
        chip.setAttribute("role", "listitem");
        var labelTxt =
          s.start == null
            ? "Last " + (s.duration || 30) + "s"
            : "#" + (i + 1) + "  " + fmtTime(s.start) + " · " + Math.round(Number(s.duration) || 0) + "s";
        if (s.score != null && s.start != null) {
          labelTxt += "  (" + Math.round(Number(s.score) * 100) + "%)";
        }
        chip.textContent = labelTxt;
        chip.addEventListener("click", function () {
          selectSuggestion(s, chip);
        });
        hlChips.appendChild(chip);
      });
      if (suggestions.length) {
        selectSuggestion(suggestions[0], hlChips.querySelector(".hl-chip"));
      }
    }

    function clearHighlights() {
      if (hlPanel) hlPanel.hidden = true;
      if (hlChips) hlChips.innerHTML = "";
      if (hlStatus) {
        hlStatus.className = "meta";
        hlStatus.textContent = "";
      }
    }

    function requestHighlights() {
      if (!autoHl || !autoHl.checked) {
        clearHighlights();
        return;
      }
      var hasFile = input && input.files && input.files[0];
      var pathVal = localPath && localPath.value ? localPath.value.trim() : "";
      if (!hasFile && !pathVal) {
        clearHighlights();
        return;
      }
      if (!hlPanel || !hlStatus) return;
      hlPanel.hidden = false;
      hlStatus.className = "meta";
      hlStatus.textContent = "Analyzing audio for highlight peaks…";
      if (hlChips) hlChips.innerHTML = "";

      var seq = ++hlSeq;
      var fd = new FormData();
      if (hasFile) fd.append("file", input.files[0]);
      if (pathVal) fd.append("local_path", pathVal);
      fd.append("top_n", "5");

      fetch("/highlights", { method: "POST", body: fd })
        .then(function (r) {
          return r.json().then(function (j) {
            return { ok: r.ok, j: j };
          });
        })
        .then(function (res) {
          if (seq !== hlSeq) return;
          if (!res.ok && res.j && res.j.detail) {
            renderHighlights({
              fallback: true,
              message: String(res.j.detail),
              suggestions: [{ start: null, duration: 30, score: 0 }],
            });
            return;
          }
          renderHighlights(res.j || {});
        })
        .catch(function (err) {
          if (seq !== hlSeq) return;
          renderHighlights({
            fallback: true,
            message: "Auto highlights request failed: " + err,
            suggestions: [{ start: null, duration: 30, score: 0 }],
          });
        });
    }

    function scheduleHighlights() {
      if (hlTimer) clearTimeout(hlTimer);
      hlTimer = setTimeout(requestHighlights, 250);
    }

    if (input) {
      input.addEventListener("change", function () {
        setFileName(input.files && input.files[0]);
        scheduleHighlights();
      });
    }

    if (localPath) {
      localPath.addEventListener("change", scheduleHighlights);
      localPath.addEventListener("blur", scheduleHighlights);
    }

    if (autoHl) {
      autoHl.addEventListener("change", function () {
        if (autoHl.checked) scheduleHighlights();
        else clearHighlights();
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
        scheduleHighlights();
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
  }

  // Branding panel
  var brandForm = document.getElementById("brand-form");
  if (brandForm) {
    var opacity = document.getElementById("brand-opacity");
    var opacityVal = document.getElementById("brand-opacity-val");
    var logoInput = document.getElementById("brand-logo-input");
    var preview = document.getElementById("brand-preview");
    var previewWrap = document.getElementById("brand-preview-wrap");
    var previewEmpty = document.getElementById("brand-preview-empty");
    var saveBtn = document.getElementById("brand-save");
    var objectUrl = null;

    function syncOpacity() {
      if (!opacity || !opacityVal) return;
      opacityVal.textContent = opacity.value;
    }

    if (opacity) {
      opacity.addEventListener("input", syncOpacity);
      syncOpacity();
    }

    if (logoInput) {
      logoInput.addEventListener("change", function () {
        var file = logoInput.files && logoInput.files[0];
        if (!file || !preview) return;
        if (objectUrl) URL.revokeObjectURL(objectUrl);
        objectUrl = URL.createObjectURL(file);
        preview.src = objectUrl;
        if (previewWrap) previewWrap.hidden = false;
        if (previewEmpty) previewEmpty.hidden = true;
      });
    }

    brandForm.addEventListener("submit", function () {
      if (saveBtn) {
        saveBtn.disabled = true;
        saveBtn.textContent = "Saving…";
      }
    });
  }

  // Live hotkey status card
  var liveCard = document.getElementById("live-hotkey-card");
  if (!liveCard) return;

  var startBtn = document.getElementById("live-start");
  var stopBtn = document.getElementById("live-stop");
  var armedLabel = document.getElementById("live-armed-label");
  var liveDot = document.getElementById("live-dot");
  var liveMsg = document.getElementById("live-msg");

  function applyStatus(data) {
    var armed = !!(data && data.armed);
    if (armedLabel) {
      armedLabel.textContent = armed ? "Armed" : "Not armed";
    }
    if (liveDot) {
      liveDot.classList.toggle("on", armed);
      liveDot.classList.toggle("off", !armed);
    }
    if (startBtn) startBtn.disabled = armed;
    if (stopBtn) stopBtn.disabled = !armed;
    if (liveMsg) {
      if (data && data.last_error) {
        liveMsg.textContent = "Last error: " + data.last_error;
      } else if (data && data.last_ok) {
        liveMsg.textContent =
          data.last_ok +
          (data.fire_count ? " (fires: " + data.fire_count + ")" : "");
      } else if (data && data.source_hint) {
        liveMsg.textContent = data.source_hint;
      }
    }
  }

  function refresh() {
    fetch("/live/status")
      .then(function (r) {
        return r.json();
      })
      .then(applyStatus)
      .catch(function () {});
  }

  function post(url) {
    if (startBtn) startBtn.disabled = true;
    if (stopBtn) stopBtn.disabled = true;
    fetch(url, { method: "POST" })
      .then(function (r) {
        return r.json();
      })
      .then(applyStatus)
      .catch(function (err) {
        if (liveMsg) liveMsg.textContent = "Request failed: " + err;
        refresh();
      });
  }

  if (startBtn) {
    startBtn.addEventListener("click", function () {
      post("/live/start");
    });
  }
  if (stopBtn) {
    stopBtn.addEventListener("click", function () {
      post("/live/stop");
    });
  }

  refresh();
  setInterval(refresh, 4000);
})();
